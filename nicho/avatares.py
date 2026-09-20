"""
Generación de avatares con Claude (spec §4): dos pasadas — núcleos por deseo
y, por cada núcleo, sub-avatares con los campos de las dos plantillas del
cliente (doc "Desire-Based Core Avatar" y hoja "Personas") — con citas
verificadas contra el comentario real. `_llamar` es la única función que
toca la API: las pruebas la reemplazan. El modelo es el del proyecto
(`generador_prompts.MODEL`); los precios de PRECIOS_USD_POR_MILLON están
verificados contra la referencia de Anthropic (tabla del 2026-06-24).
"""
import json
import math
import re

import marca
import proyectos
from nicho import datos
from nicho.fuentes.base import MIN_CITA

MIN_COMENTARIOS = 20
MAX_COMENTARIOS = 600
MAX_CARACTERES = 250_000
MAX_NUCLEOS = 5
MAX_SUBS_POR_NUCLEO = 4
TOKENS_POR_CARACTER = 1 / 3.5          # conservador para español
TOKENS_PROMPT = 800                    # instrucciones por llamada
TOKENS_SALIDA_ESTIMADO_NUCLEOS = 1500  # lo que suele ocupar la pasada 1
TOKENS_SALIDA_ESTIMADO_SUBS = 3000     # por núcleo, pasada 2
MAX_TOKENS_NUCLEOS = 4000              # tope de salida real (no es costo: es el corte)
MAX_TOKENS_SUBS = 8000

# USD por millón de tokens (entrada, salida). Referencia de Anthropic, 2026-06-24.
PRECIOS_USD_POR_MILLON = {
    "claude-sonnet-5": {"entrada": 2.0, "salida": 10.0},
    "claude-opus-5": {"entrada": 5.0, "salida": 25.0},
    "claude-haiku-4-5": {"entrada": 1.0, "salida": 5.0},
}
IDIOMAS = {"es": "español", "en": "inglés", "pt": "portugués", "sv": "sueco", "fr": "francés", "de": "alemán",
           "it": "italiano"}


class AnalisisInvalido(RuntimeError):
    """Claude no devolvió lo pedido (JSON roto, claves faltantes, corte)."""


def modelo_actual():
    from generador_prompts import MODEL
    return MODEL


# ----------------------------------------------------------- selección ---

def seleccionar(comentarios, max_n=MAX_COMENTARIOS, max_caracteres=MAX_CARACTERES):
    """Los que entran a Claude (spec §4.1): fuera los excluidos; dentro de
    cada fuente por puntuación desc, fecha desc, id asc; se toman en ronda
    entre fuentes hasta llenar el primer tope. Un comentario que no cabe en
    los caracteres se salta (no corta la ronda)."""
    por_fuente = {}
    for c in comentarios or []:
        if c.get("excluido"):
            continue
        por_fuente.setdefault(c.get("fuente") or "texto", []).append(c)
    for lista in por_fuente.values():
        # tres ordenamientos estables = (puntuación desc, fecha desc, id asc)
        lista.sort(key=lambda c: int(c.get("id") or 0))
        lista.sort(key=lambda c: c.get("fecha") or "", reverse=True)
        lista.sort(key=lambda c: -(c.get("puntuacion") or 0))
    colas = [iter(l) for _, l in sorted(por_fuente.items())]
    salida, caracteres = [], 0
    while colas and len(salida) < max_n:
        siguientes = []
        for it in colas:
            if len(salida) >= max_n:
                break
            c = next(it, None)
            if c is None:
                continue
            siguientes.append(it)
            largo = len(c.get("texto") or "")
            if caracteres + largo > max_caracteres:
                continue
            salida.append(c)
            caracteres += largo
        colas = siguientes
    return salida


# -------------------------------------------------------------- costo ---

def _precios(modelo):
    """(precios, es_referencia). Modelo desconocido -> el más caro de la tabla."""
    if modelo in PRECIOS_USD_POR_MILLON:
        return PRECIOS_USD_POR_MILLON[modelo], False
    caro = max(PRECIOS_USD_POR_MILLON.values(), key=lambda p: p["entrada"] + p["salida"])
    return caro, True


def costo_real(tokens_entrada, tokens_salida, modelo=None):
    precios, _ = _precios(modelo or modelo_actual())
    return round((tokens_entrada * precios["entrada"] + tokens_salida * precios["salida"]) / 1e6, 4)


def estimar_costo(comentarios, modelo=None):
    """Precio ANTES de gastar (spec §4.4): la entrada se cuenta dos veces
    (pasada 1 y repartida en la pasada 2) más el prompt por llamada; la
    salida es lo esperado, con MAX_NUCLEOS en la pasada 2. Redondeado hacia
    arriba al centavo."""
    modelo = modelo or modelo_actual()
    sel = seleccionar(comentarios)
    caracteres = sum(len(c.get("texto") or "") for c in sel)
    tokens_texto = int(caracteres * TOKENS_POR_CARACTER)
    entrada = tokens_texto * 2 + TOKENS_PROMPT * (1 + MAX_NUCLEOS)
    salida = TOKENS_SALIDA_ESTIMADO_NUCLEOS + TOKENS_SALIDA_ESTIMADO_SUBS * MAX_NUCLEOS
    precios, referencia = _precios(modelo)
    usd = math.ceil((entrada * precios["entrada"] + salida * precios["salida"]) / 1e6 * 100) / 100
    return {"comentarios": len(sel), "tokens_entrada": entrada, "tokens_salida": salida, "usd": usd,
            "referencia": referencia, "modelo": modelo, "suficientes": len(sel) >= MIN_COMENTARIOS}


# ------------------------------------------------------------- prompts ---

PROMPT_NUCLEOS = """Eres estratega de investigación de clientes para la marca {marca}.
Producto que vendemos: {producto}
Nicho o tema investigado: {tema}

Abajo hay {n} comentarios reales de personas (reseñas, foros y redes), cada uno con su número entre corchetes, la fuente y, si la hay, su puntuación y el título de donde salió. Agrúpalos por el DESEO de fondo que expresan: qué quieren lograr o evitar, más allá del producto concreto. Devuelve de 2 a {max_nucleos} avatares núcleo, distintos entre sí.

Responde SOLO con un objeto JSON, sin texto antes ni después, con esta forma:
{{"nucleos": [{{"nombre": "2 a 5 palabras", "deseo": "una frase en primera persona que empiece por «Quiero»", "resumen": "quiénes son y qué comparten, 30 a 60 palabras", "comentarios": [números de los comentarios que pertenecen a este núcleo]}}]}}

Reglas: cada comentario va en un solo núcleo, o en ninguno si no aporta; no inventes nada que los comentarios no digan; escribe todo en {idioma}.

COMENTARIOS:
{comentarios}"""

PROMPT_SUBS = """Eres estratega de investigación de clientes para la marca {marca}.
Producto que vendemos: {producto}
Guía de la marca: {guia}
Nicho o tema investigado: {tema}

Avatar núcleo: {nucleo_nombre} — deseo: «{nucleo_deseo}». {nucleo_resumen}

Abajo están los comentarios reales de este núcleo, numerados. Describe de 2 a {max_subs} sub-avatares: personas concretas y distintas entre sí dentro de este deseo. Al menos uno con base "emocion" (lo que más lo define es lo que siente) y al menos uno con base "experiencia_producto" (lo que más lo define es lo que ya usó y le falló), si los comentarios lo permiten.

Responde SOLO con un objeto JSON, sin texto antes ni después, con esta forma:
{{"sub_avatares": [{{
  "base": "emocion" o "experiencia_producto",
  "nombre": "Nombre / arquetipo, por ejemplo «Melissa / La que regala con cabeza»",
  "deseo": "en primera persona",
  "demografia": "Demographics (ASL): edad, género, dónde vive, momento de vida. SOLO si los comentarios dan señales; si no, cadena vacía",
  "edad_rango": "por ejemplo 30-45, o cadena vacía si no hay señales",
  "emocion": "la emoción dominante, una línea",
  "identidad": {{"quiere_que_vean": "What are some of the characteristics your prospect wants others to see in them?", "cree_de_si": "Beliefs about self", "quiere_lograr": "What does the prospect want to achieve in society?"}},
  "soluciones_previas": [{{"que": "What are other solutions they have tried and failed at? (una por elemento)", "por_que_fallo": ["Reason for failure with those solutions: 3 a 5 problemas concretos"]}}],
  "situaciones": ["2 a 4 escenas concretas de su día a día"],
  "comportamiento": "qué hace hoy y por qué",
  "conciencia": {{"nivel": "uno de: {niveles}", "detalle": "una línea que lo justifica"}},
  "encaje_producto": "How does your product help them achieve that status/characteristics?",
  "tono": "cómo habla esta gente, una línea",
  "palabras_clave": ["3 a 6 palabras"],
  "evidencia": [{{"comentario_id": número, "cita": "fragmento LITERAL copiado del comentario; 2 a 5 citas por sub-avatar"}}]
}}]}}

Reglas: escribe en {idioma}, salvo las citas, que se copian tal cual en el idioma en que la gente escribió; no inventes datos; cada cita debe aparecer palabra por palabra en el comentario indicado.

COMENTARIOS:
{comentarios}"""


def nombre_idioma(codigo):
    return IDIOMAS.get((codigo or "").lower(), codigo or "es")


def _linea(c):
    partes = [c.get("fuente") or "texto"]
    if c.get("puntuacion") is not None:
        partes.append(str(c["puntuacion"]))
    if c.get("contexto"):
        partes.append(str(c["contexto"])[:80])
    return f"[{c['id']}] ({' · '.join(partes)}) {c.get('texto') or ''}"


def lineas_comentarios(comentarios):
    return "\n".join(_linea(c) for c in comentarios)


def armar_prompt_nucleos(estudio, comentarios, marca_nombre=""):
    return PROMPT_NUCLEOS.format(
        marca=marca_nombre or "este proyecto", producto=(estudio.get("producto") or "").strip() or "(sin describir)",
        tema=(estudio.get("tema") or "").strip() or "(sin describir)", n=len(comentarios), max_nucleos=MAX_NUCLEOS,
        idioma=nombre_idioma(estudio.get("idioma")), comentarios=lineas_comentarios(comentarios))


def armar_prompt_subs(estudio, nucleo, comentarios, guia="", marca_nombre=""):
    return PROMPT_SUBS.format(
        marca=marca_nombre or "este proyecto", producto=(estudio.get("producto") or "").strip() or "(sin describir)",
        guia=(guia or "").strip() or "(sin guía de estilo todavía)", tema=(estudio.get("tema") or "").strip() or "(sin describir)",
        nucleo_nombre=nucleo.get("nombre") or "", nucleo_deseo=nucleo.get("deseo") or "", nucleo_resumen=nucleo.get("resumen") or "",
        max_subs=MAX_SUBS_POR_NUCLEO, niveles=", ".join(datos.NIVELES_CONCIENCIA), idioma=nombre_idioma(estudio.get("idioma")),
        comentarios=lineas_comentarios(comentarios))


# -------------------------------------------------------------- parseo ---

def _json_objeto(texto):
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        data = json.loads(t)
    except ValueError:
        ini, fin = t.find("{"), t.rfind("}")
        if ini < 0 or fin <= ini:
            raise AnalisisInvalido("Claude no devolvió JSON.")
        try:
            data = json.loads(t[ini:fin + 1])
        except ValueError as e:
            raise AnalisisInvalido(f"JSON inválido: {e}")
    if not isinstance(data, dict):
        raise AnalisisInvalido("El JSON no es un objeto.")
    return data


def _str(v, largo=None):
    s = "" if v is None else str(v).strip()
    return s[:largo] if largo else s


def parsear_nucleos(texto, ids_validos):
    """-> hasta MAX_NUCLEOS núcleos con nombre, deseo, resumen y sus ids de
    comentario (solo válidos; un id repetido se queda en el primer núcleo).
    Un núcleo sin nombre, sin deseo o sin comentarios válidos se descarta."""
    data = _json_objeto(texto)
    crudos = data.get("nucleos")
    if not isinstance(crudos, list):
        raise AnalisisInvalido("El JSON no trae la lista «nucleos».")
    ids_validos = set(ids_validos)
    usados, limpios = set(), []
    for c in crudos:
        if len(limpios) >= MAX_NUCLEOS:
            break
        if not isinstance(c, dict):
            continue
        nombre, deseo = _str(c.get("nombre"), 120), _str(c.get("deseo"), 300)
        if not nombre or not deseo:
            continue
        ids = []
        for x in c.get("comentarios") or []:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if i in ids_validos and i not in usados:
                usados.add(i)
                ids.append(i)
        if not ids:
            continue
        limpios.append({"nombre": nombre, "deseo": deseo, "resumen": _str(c.get("resumen"), 1500), "comentarios": ids})
    if not limpios:
        raise AnalisisInvalido("Ningún núcleo venía completo.")
    return limpios


def parsear_subs(texto):
    """-> sub-avatares con las claves de datos.AVATAR_EDITABLES + evidencia
    (sin verificar todavía). Sin nombre o sin deseo se descarta; el resto lo
    normaliza datos.validar_campos_avatar (base, conciencia, listas, largos)."""
    data = _json_objeto(texto)
    crudos = data.get("sub_avatares")
    if not isinstance(crudos, list):
        raise AnalisisInvalido("El JSON no trae la lista «sub_avatares».")
    limpios = []
    for c in crudos[:MAX_SUBS_POR_NUCLEO + 2]:
        if not isinstance(c, dict):
            continue
        if not _str(c.get("nombre")) or not _str(c.get("deseo")):
            continue
        campos = {k: c.get(k) for k in datos.AVATAR_EDITABLES}
        campos["evidencia"] = c.get("evidencia")
        limpios.append(datos.validar_campos_avatar(campos))
    if not limpios:
        raise AnalisisInvalido("Ningún sub-avatar venía completo.")
    return limpios


# ----------------------------------------------------------- evidencia ---

_RE_BLANCOS = re.compile(r"\s+")


def _plano(t):
    return _RE_BLANCOS.sub(" ", (t or "")).strip().lower()


def verificar_evidencia(sub, comentarios_por_id):
    """Una cita vale si es fragmento literal (sin mayúsculas ni espacios
    múltiples, mínimo MIN_CITA caracteres) del comentario que dice. Las que
    no aparecen se descartan; sin ninguna, `sin_evidencia=True` (no se borra)."""
    validas = []
    for e in sub.get("evidencia") or []:
        c = comentarios_por_id.get(e.get("comentario_id"))
        cita = _plano(e.get("cita"))
        if c and len(cita) >= MIN_CITA and cita in _plano(c.get("texto")):
            validas.append({"comentario_id": c["id"], "cita": _str(e.get("cita"), 500)})
    return {**sub, "evidencia": validas, "sin_evidencia": not validas}


# ------------------------------------------------------------ generar ---

ETAPA_NUCLEOS = "Agrupando deseos"
ETAPA_SUBS = "Armando sub-avatares"


def _llamar(texto, max_tokens):
    """Una llamada a Claude (modelo del proyecto). Devuelve (texto, tokens de
    entrada, tokens de salida) — los tokens alimentan el gasto real. Las
    pruebas reemplazan esta función."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": texto}])
    if resp.stop_reason == "refusal":
        raise AnalisisInvalido("Claude rechazó la solicitud.")
    salida = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "max_tokens":
        raise AnalisisInvalido("La respuesta de Claude se cortó por largo (max_tokens).")
    uso = getattr(resp, "usage", None)
    return salida, int(getattr(uso, "input_tokens", 0) or 0), int(getattr(uso, "output_tokens", 0) or 0)


def generar(cliente, estudio_id, avanzar=None):
    """Las dos pasadas (spec §4.2, §4.5). Pasada 1 inválida: sube la excepción
    y no se guarda nada. Pasada 2: un núcleo que falla queda con `error` y sin
    sub-avatares; si TODOS fallan, sube AnalisisInvalido. No escribe en la
    base: el llamador (la tarea) guarda con datos.guardar_generacion."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    est = datos.estudio(cliente, estudio_id)
    if not est:
        raise datos.ErrorDatos("Ese estudio no existe.")
    todos = datos.comentarios_para_generar(cliente, estudio_id)
    if len(todos) < MIN_COMENTARIOS:
        raise datos.ErrorDatos(f"Hacen falta al menos {MIN_COMENTARIOS} comentarios no excluidos (hay {len(todos)}).")
    seleccion = seleccionar(todos)
    por_id = {c["id"]: c for c in seleccion}
    marca_nombre = proyectos.nombre_visible(cliente)
    avanzar(ETAPA_NUCLEOS)
    texto, entrada, salida = _llamar(armar_prompt_nucleos(est, seleccion, marca_nombre), MAX_TOKENS_NUCLEOS)
    tokens = [entrada, salida]
    nucleos = parsear_nucleos(texto, set(por_id))
    guia = marca.guia_efectiva(cliente) or ""
    resultado, errores = [], []
    for i, n in enumerate(nucleos):
        avanzar(ETAPA_SUBS, f"{i + 1}/{len(nucleos)}: {n['nombre']}")
        propios = [por_id[cid] for cid in n["comentarios"]]
        try:
            t2, e2, s2 = _llamar(armar_prompt_subs(est, n, propios, guia, marca_nombre), MAX_TOKENS_SUBS)
            tokens[0] += e2
            tokens[1] += s2
            subs = [verificar_evidencia(s, por_id) for s in parsear_subs(t2)]
            resultado.append({**n, "sub_avatares": subs})
        except Exception as e:  # noqa: BLE001 — un núcleo que falla no pierde a los demás (spec §4.5)
            errores.append(f"{n['nombre']}: {e}")
            resultado.append({**n, "sub_avatares": [], "error": str(e)[:300]})
    if errores and len(errores) == len(nucleos):
        raise AnalisisInvalido("Ningún núcleo produjo sub-avatares: " + " | ".join(errores)[:400])
    subs_todos = [s for n in resultado for s in n["sub_avatares"]]
    resumen = {
        "comentarios": len(seleccion), "nucleos": len(resultado), "subs": len(subs_todos),
        "con_evidencia": sum(1 for s in subs_todos if not s.get("sin_evidencia")),
        "sin_evidencia": sum(1 for s in subs_todos if s.get("sin_evidencia")),
        "errores": len(errores), "tokens_entrada": tokens[0], "tokens_salida": tokens[1],
        "usd": costo_real(tokens[0], tokens[1]), "modelo": modelo_actual(),
    }
    return {"nucleos": resultado, "resumen": resumen}

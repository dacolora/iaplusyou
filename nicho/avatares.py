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
import logging
import math
import re

from flask_babel import gettext

import doctrina
import marca
import proyectos
from idiomas import N_
from nicho import calidad, datos
from nicho.fuentes.base import MIN_CITA

log = logging.getLogger(__name__)

MIN_COMENTARIOS = 20
MAX_COMENTARIOS = 600
MAX_CARACTERES = 250_000
MAX_NUCLEOS = 5
MAX_SUBS_POR_NUCLEO = 4
TOKENS_POR_CARACTER = 1 / 3.5          # conservador para español
# La doctrina de investigación va en el system de cada llamada (1 + núcleos):
# el estimado del botón la cuenta (~1,4 tokens por palabra en español).
TOKENS_DOCTRINA = int(len(doctrina.texto("investigar").split()) * 1.4)
TOKENS_PROMPT = 800 + TOKENS_DOCTRINA   # instrucciones + doctrina por llamada
TOKENS_SALIDA_ESTIMADO_NUCLEOS = 1500  # lo que suele ocupar la pasada 1
TOKENS_SALIDA_ESTIMADO_SUBS = 3000     # por núcleo, pasada 2
MAX_TOKENS_NUCLEOS = 4000              # tope de salida real (no es costo: es el corte)
MAX_TOKENS_SUBS = 8000
TOKENS_SUB_JSON = 900                  # un sub-avatar incompleto dentro del prompt de completado
TOKENS_SALIDA_ESTIMADO_COMPLETAR = 1500  # por núcleo, pasada de completado
MAX_TOKENS_COMPLETAR = 6000
MAX_COMENTARIOS_COMPLETAR = 200        # comentarios que acompañan un completado de avatares ya guardados
MARCA_COMPLETAR = "Estos sub-avatares quedaron incompletos"

# USD por millón de tokens (entrada, salida). Referencia de Anthropic, 2026-06-24.
PRECIOS_USD_POR_MILLON = {
    "claude-sonnet-5": {"entrada": 2.0, "salida": 10.0},
    "claude-opus-5": {"entrada": 5.0, "salida": 25.0},
    "claude-haiku-4-5": {"entrada": 1.0, "salida": 5.0},
}
# N_ solo marca para el catálogo: el valor sigue en español, que es lo que
# nombre_idioma mete en el prompt de Claude; la pantalla lo traduce con |traducir.
IDIOMAS = {"es": N_("español"), "en": N_("inglés"), "pt": N_("portugués"), "sv": N_("sueco"), "fr": N_("francés"),
           "de": N_("alemán"), "it": N_("italiano")}


class AnalisisInvalido(RuntimeError):
    """Claude no devolvió lo pedido (JSON roto, claves faltantes, corte). Los
    tokens quedan en 0 salvo que quien la lance ya haya cobrado la llamada
    (`_llamar` los pone antes de subir el error): el intento fallido también
    se registra como gasto (spec: "on failure after paying, register what
    was paid")."""
    tokens_entrada = 0
    tokens_salida = 0


def modelo_actual():
    from generador_prompts import MODEL
    return MODEL


# ----------------------------------------------------------- selección ---

def seleccionar(comentarios, max_n=MAX_COMENTARIOS, max_caracteres=MAX_CARACTERES):
    """Los que entran a Claude (spec §4.1 y Parte 4 §3): fuera los excluidos; dentro de
    cada fuente por puntuación desc, fecha desc, id asc; se toman en ronda entre fuentes
    hasta llenar el primer tope, y en cada vuelta van primero las del mercado del estudio
    (las reseñas con `extra.mercado == "otro"` hacen su propia cola, después). Un
    comentario que no cabe en los caracteres se salta (no corta la ronda)."""
    por_fuente = {}
    for c in comentarios or []:
        if c.get("excluido"):
            continue
        ex = c.get("extra") if isinstance(c.get("extra"), dict) else {}
        clave = (1 if ex.get("mercado") == "otro" else 0, c.get("fuente") or "texto")
        por_fuente.setdefault(clave, []).append(c)
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


def _es_otro_mercado(c):
    return isinstance(c.get("extra"), dict) and c["extra"].get("mercado") == "otro"


def estimar_costo(comentarios, modelo=None):
    """Precio ANTES de gastar (spec §4.4): la entrada se cuenta dos veces
    (pasada 1 y repartida en la pasada 2) más el prompt por llamada; la
    salida es lo esperado, con MAX_NUCLEOS en la pasada 2. Redondeado hacia
    arriba al centavo. Más la pasada de completado en su peor caso: un tercer
    reparto de la entrada (los sub-avatares incompletos que vuelven al
    prompt) y su propia salida por núcleo. Cada comentario cuenta con la línea
    entera que va al prompt (`_linea`: id, fuente, puntuación, contexto y
    «otro mercado»), y si alguno es de otro mercado cada llamada lleva además
    la regla (`TOKENS_REGLA_OTRO_MERCADO`, spec Parte 4 §3)."""
    modelo = modelo or modelo_actual()
    sel = seleccionar(comentarios)
    caracteres = sum(len(_linea(c)) for c in sel)
    tokens_texto = int(caracteres * TOKENS_POR_CARACTER)
    por_llamada = TOKENS_PROMPT + (TOKENS_REGLA_OTRO_MERCADO if any(_es_otro_mercado(c) for c in sel) else 0)
    entrada = (tokens_texto * 3 + por_llamada * (1 + 2 * MAX_NUCLEOS)
               + TOKENS_SUB_JSON * MAX_NUCLEOS * MAX_SUBS_POR_NUCLEO)
    salida = TOKENS_SALIDA_ESTIMADO_NUCLEOS + (TOKENS_SALIDA_ESTIMADO_SUBS + TOKENS_SALIDA_ESTIMADO_COMPLETAR) * MAX_NUCLEOS
    precios, referencia = _precios(modelo)
    usd = math.ceil((entrada * precios["entrada"] + salida * precios["salida"]) / 1e6 * 100) / 100
    return {"comentarios": len(sel), "tokens_entrada": entrada, "tokens_salida": salida, "usd": usd,
            "referencia": referencia, "modelo": modelo, "suficientes": len(sel) >= MIN_COMENTARIOS}


ID_PEOR_CASO = 1_000_000          # ids de 7 cifras en las líneas falsas: cubre hasta 9 999 999 comentarios en la base


def comentarios_peor_caso():
    """Los comentarios falsos de `estimar_costo_maximo`: los DOS topes de
    `seleccionar` llenos a la vez, no solo el de cantidad -- una reseña real
    puede llegar a 2 000 caracteres, así que un lote de MAX_COMENTARIOS puede
    alcanzar también MAX_CARACTERES. Cada uno recibe MAX_CARACTERES //
    MAX_COMENTARIOS caracteres y los primeros MAX_CARACTERES % MAX_COMENTARIOS
    uno más, para que la suma dé MAX_CARACTERES exacto y `seleccionar` los
    conserve a todos (la suma corrida nunca pasa el tope). Y cada línea del
    prompt (`_linea`) lleva lo más largo que puede llevar una reseña real: la
    fuente de nombre más largo, puntuación, un contexto de 80 caracteres (lo que
    `_linea` deja del título) y «otro mercado» con el país de nombre más largo
    -- con eso cada llamada lleva además la regla de otro mercado."""
    base, resto = divmod(MAX_CARACTERES, MAX_COMENTARIOS)
    fuente = max(datos.FUENTES, key=len)
    pais = max(datos.NOMBRES_PAIS, key=lambda k: len(datos.NOMBRES_PAIS[k]))
    return [{"id": ID_PEOR_CASO + i, "texto": "x" * (base + 1 if i < resto else base), "fuente": fuente, "puntuacion": 5,
             "fecha": None, "contexto": "x" * 80, "extra": {"mercado": "otro", "pais": pais}}
            for i in range(MAX_COMENTARIOS)]


def estimar_costo_maximo(modelo=None):
    """Peor caso de una generación (lo que la investigación aprueba antes de
    tener comentarios): `estimar_costo` sobre `comentarios_peor_caso()`. Así
    ningún lote real cuesta más que lo aprobado para la línea de avatares."""
    return estimar_costo(comentarios_peor_caso(), modelo)


# ------------------------------------------------------------- prompts ---

PROMPT_NUCLEOS = """Eres estratega de investigación de clientes para la marca {marca}.
Producto que vendemos: {producto}
Nicho o tema investigado: {tema}

Abajo hay {n} comentarios reales de personas (reseñas, foros y redes), cada uno con su número entre corchetes, la fuente y, si la hay, su puntuación y el título de donde salió. Agrúpalos por el DESEO de fondo que expresan: qué quieren lograr o evitar, más allá del producto concreto. Devuelve de 2 a {max_nucleos} avatares núcleo, distintos entre sí.

Responde SOLO con un objeto JSON, sin texto antes ni después, con esta forma:
{{"nucleos": [{{"nombre": "2 a 5 palabras", "deseo": "una frase en primera persona que empiece por «Quiero»", "resumen": "quiénes son y qué comparten, 30 a 60 palabras", "comentarios": [números de los comentarios que pertenecen a este núcleo]}}]}}

Reglas: cada comentario va en un solo núcleo, o en ninguno si no aporta; no inventes nada que los comentarios no digan; escribe todo en {idioma}. Aplica la doctrina de investigación del principio: agrupa por el deseo de fondo y prefiere los deseos con más urgencia, permanencia y alcance.

{regla_mercado}COMENTARIOS:
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
  "demografia": "Demographics (ASL): edad, género, dónde vive, momento de vida. Si los comentarios no lo dicen, infiere lo más probable por lo que cuentan, el producto y el mercado y termina con «(inferido)»",
  "edad_rango": "por ejemplo 30-45; si no hay señales, el rango más probable seguido de «(inferido)»",
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

Reglas: todos los campos son obligatorios y ninguno puede quedar vacío; mínimos: 2 situaciones, 1 solución probada con sus motivos de falla, 3 palabras clave y 2 citas. Escribe en {idioma}, salvo las citas, que se copian tal cual en el idioma en que la gente escribió; no inventes datos ni cifras (lo inferido va marcado «(inferido)»); cada cita debe aparecer palabra por palabra en el comentario indicado. Aplica la doctrina de investigación del principio: anota literalmente lo que ya probaron y por qué les falló, y el nivel de conciencia según lo que dicen los comentarios.

{regla_mercado}COMENTARIOS:
{comentarios}"""


def nombre_idioma(codigo):
    return IDIOMAS.get((codigo or "").lower(), codigo or "es")


REGLA_OTRO_MERCADO = ("Mercado del estudio: {pais}. Los comentarios marcados «otro mercado: <país>» son de compradores de otro país: "
                      "la identidad, la demografía, la edad, el momento de vida, el tono y el nivel de conciencia salen de los "
                      "comentarios del mercado del estudio (si esos no alcanzan, infiere lo más probable y termina con «(inferido)»); "
                      "los deseos, los dolores, las soluciones que probaron, las situaciones y momentos de uso y las palabras clave "
                      "pueden salir de todos.")
# Lo que la regla suma a CADA llamada cuando el lote trae otro mercado (lo cuenta `estimar_costo`): con el
# país de nombre más largo y la línea en blanco que la separa de los comentarios, a TOKENS_POR_CARACTER.
TOKENS_REGLA_OTRO_MERCADO = math.ceil(len(REGLA_OTRO_MERCADO.format(pais=max(datos.NOMBRES_PAIS.values(), key=len)) + "\n\n")
                                      * TOKENS_POR_CARACTER)


def _regla_mercado(estudio, comentarios):
    """La regla de otro mercado (spec Parte 4 §3), solo si alguno de estos comentarios es de otro mercado."""
    if not any(_es_otro_mercado(c) for c in comentarios or []):
        return ""
    pais = (estudio.get("pais") or "").upper()
    return REGLA_OTRO_MERCADO.format(pais=datos.NOMBRES_PAIS.get(pais, pais) or "—") + "\n\n"


def _linea(c):
    partes = [c.get("fuente") or "texto"]
    if c.get("puntuacion") is not None:
        partes.append(str(c["puntuacion"]))
    if c.get("contexto"):
        partes.append(str(c["contexto"])[:80])
    ex = c.get("extra") if isinstance(c.get("extra"), dict) else {}
    if ex.get("mercado") == "otro":                  # spec Parte 4 §3: Claude sabe qué no es del mercado del estudio
        pais = str(ex.get("pais") or "").upper()
        partes.append(f"otro mercado: {datos.NOMBRES_PAIS.get(pais, pais) or '?'}")
    return f"[{c['id']}] ({' · '.join(partes)}) {c.get('texto') or ''}"


def lineas_comentarios(comentarios):
    return "\n".join(_linea(c) for c in comentarios)


def armar_prompt_nucleos(estudio, comentarios, marca_nombre=""):
    return PROMPT_NUCLEOS.format(
        marca=marca_nombre or "este proyecto", producto=(estudio.get("producto") or "").strip() or "(sin describir)",
        tema=(estudio.get("tema") or "").strip() or "(sin describir)", n=len(comentarios), max_nucleos=MAX_NUCLEOS,
        idioma=nombre_idioma(estudio.get("idioma")), regla_mercado=_regla_mercado(estudio, comentarios),
        comentarios=lineas_comentarios(comentarios))


def armar_prompt_subs(estudio, nucleo, comentarios, guia="", marca_nombre=""):
    return PROMPT_SUBS.format(
        marca=marca_nombre or "este proyecto", producto=(estudio.get("producto") or "").strip() or "(sin describir)",
        guia=(guia or "").strip() or "(sin guía de estilo todavía)", tema=(estudio.get("tema") or "").strip() or "(sin describir)",
        nucleo_nombre=nucleo.get("nombre") or "", nucleo_deseo=nucleo.get("deseo") or "", nucleo_resumen=nucleo.get("resumen") or "",
        max_subs=MAX_SUBS_POR_NUCLEO, niveles=", ".join(datos.NIVELES_CONCIENCIA), idioma=nombre_idioma(estudio.get("idioma")),
        regla_mercado=_regla_mercado(estudio, comentarios), comentarios=lineas_comentarios(comentarios))


PROMPT_COMPLETAR = """Eres estratega de investigación de clientes para la marca {marca}.
Producto que vendemos: {producto}
Guía de la marca: {guia}
Nicho o tema investigado: {tema}

Avatar núcleo: {nucleo_nombre} — deseo: «{nucleo_deseo}».

""" + MARCA_COMPLETAR + """. Para cada uno, escribe SOLO los campos que se le piden, con lo que dicen los comentarios de abajo; no cambies nada de lo que ya tiene.

{incompletos}

Responde SOLO con un objeto JSON, sin texto antes ni después:
{{"sub_avatares": [{{"indice": número del sub-avatar, "<campo pedido>": valor}}]}}
Formas: demografia, edad_rango, emocion, comportamiento, encaje_producto, tono y deseo son texto; identidad es {{"quiere_que_vean": texto, "cree_de_si": texto, "quiere_lograr": texto}}; conciencia es {{"nivel": uno de {niveles}, "detalle": texto}}; soluciones_previas es [{{"que": texto, "por_que_fallo": [textos]}}]; situaciones y palabras_clave son listas de textos; evidencia es [{{"comentario_id": número, "cita": fragmento LITERAL del comentario}}].

Reglas: escribe en {idioma}, salvo las citas, que se copian tal cual; la demografía y la edad, si los comentarios no lo dicen, se infieren de lo que cuentan, el producto y el mercado y terminan con «(inferido)»; no inventes cifras; cada cita debe aparecer palabra por palabra en el comentario indicado.

{regla_mercado}COMENTARIOS:
{comentarios}"""

_PEDIDOS = {"identidad": "identidad (las tres respuestas)", "conciencia": "conciencia (nivel y detalle)",
            "soluciones_previas": "soluciones_previas (al menos 1, con sus motivos de falla)", "situaciones": "situaciones (mínimo 2)",
            "palabras_clave": "palabras_clave (mínimo 3)", "evidencia": "evidencia (mínimo 2 citas literales)"}


def armar_prompt_completar(estudio, nucleo, comentarios, pendientes, guia="", marca_nombre=""):
    """`pendientes` = [(indice, sub, faltantes)]."""
    bloques = []
    for i, sub, falt in pendientes:
        actual = {k: sub.get(k) for k in datos.AVATAR_EDITABLES}
        bloques.append(f"[{i}] {json.dumps(actual, ensure_ascii=False)}\nFaltan: {', '.join(_PEDIDOS.get(k, k) for k in falt)}")
    return PROMPT_COMPLETAR.format(
        marca=marca_nombre or "este proyecto", producto=(estudio.get("producto") or "").strip() or "(sin describir)",
        guia=(guia or "").strip() or "(sin guía de estilo todavía)", tema=(estudio.get("tema") or "").strip() or "(sin describir)",
        nucleo_nombre=nucleo.get("nombre") or "", nucleo_deseo=nucleo.get("deseo") or "", incompletos="\n\n".join(bloques),
        niveles=", ".join(datos.NIVELES_CONCIENCIA), idioma=nombre_idioma(estudio.get("idioma")),
        regla_mercado=_regla_mercado(estudio, comentarios), comentarios=lineas_comentarios(comentarios))


def completar_subs(estudio, nucleo, comentarios, subs, guia="", marca_nombre="", tokens=None, con_evidencia=True):
    """Pasada de completado (spec 2026-09-29 §2): UNA llamada con lo que le
    falta a cada sub-avatar incompleto; funde SOLO lo vacío (`calidad.fundir`)
    y agrega las citas nuevas que pasen `verificar_evidencia`. Devuelve
    (subs, cuántos cambiaron). Si la llamada falla, los subs quedan como
    estaban: la pasada es una mejora y lo pagado antes no se pierde (los tokens
    que Claude alcanzó a cobrar ya quedaron en `tokens`)."""
    tokens = tokens if tokens is not None else [0, 0]
    try:
        # Ruling 20 (2): `calidad.faltantes` también corre acá adentro -- un
        # sub-avatar malformado (dato corrupto, quizás de una edición a mano)
        # solo hace que esta pasada se salte, nunca sube al llamador y le hace
        # perder lo que ya generó/pagó en la misma corrida.
        pendientes = [(i, s, calidad.faltantes(s, con_evidencia=con_evidencia)) for i, s in enumerate(subs)]
        pendientes = [(i, s, f) for i, s, f in pendientes if f]
        if not pendientes:
            return list(subs), 0
        prompt = armar_prompt_completar(estudio, nucleo, comentarios, pendientes, guia, marca_nombre)
        data = _json_objeto(_llamar_contando(prompt, MAX_TOKENS_COMPLETAR, tokens))
    except Exception:  # noqa: BLE001 — la pasada es una mejora: si falla (incluido un sub malformado), se guarda lo que había
        log.exception("La pasada de completado falló en el núcleo «%s»", nucleo.get("nombre"))
        return list(subs), 0
    por_id = {c["id"]: c for c in comentarios}
    validos = {i for i, _, _ in pendientes}
    salida, cambiados = list(subs), 0
    for item in data.get("sub_avatares") or []:
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("indice"))
        except (TypeError, ValueError):
            continue
        if i not in validos:
            continue
        crudos = {k: item[k] for k in datos.AVATAR_EDITABLES if k in item and k not in ("nombre", "base")}
        if "evidencia" in item:
            crudos["evidencia"] = item["evidencia"]
        try:
            nuevos = datos.validar_campos_avatar(crudos)
        except datos.ErrorDatos:
            continue
        antes = salida[i]
        fundido = calidad.fundir(antes, nuevos)
        citas = list(antes.get("evidencia") or [])
        vistas = {(e.get("comentario_id"), (e.get("cita") or "").strip().lower()) for e in citas}
        for e in verificar_evidencia({"evidencia": nuevos.get("evidencia") or []}, por_id)["evidencia"]:
            clave = (e["comentario_id"], (e["cita"] or "").strip().lower())
            if clave not in vistas:
                citas.append(e)
                vistas.add(clave)
        fundido["evidencia"] = citas[:8]
        fundido["sin_evidencia"] = not fundido["evidencia"]
        if fundido != antes:
            cambiados += 1
        salida[i] = fundido
    return salida, cambiados


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
            raise AnalisisInvalido(gettext("Claude no devolvió JSON."))
        try:
            data = json.loads(t[ini:fin + 1])
        except ValueError as e:
            raise AnalisisInvalido(gettext("JSON inválido: %(error)s", error=e))
    if not isinstance(data, dict):
        raise AnalisisInvalido(gettext("El JSON no es un objeto."))
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
        raise AnalisisInvalido(gettext("El JSON no trae la lista «nucleos»."))
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
        raise AnalisisInvalido(gettext("Ningún núcleo venía completo."))
    return limpios


def parsear_subs(texto):
    """-> sub-avatares con las claves de datos.AVATAR_EDITABLES + evidencia
    (sin verificar todavía). Sin nombre o sin deseo se descarta; el resto lo
    normaliza datos.validar_campos_avatar (base, conciencia, listas, largos).
    Filtra TODOS los crudos antes de topar a MAX_SUBS_POR_NUCLEO: si Claude
    manda algunos inválidos primero, los válidos que vienen después no se
    pierden por cortar la lista cruda de entrada."""
    data = _json_objeto(texto)
    crudos = data.get("sub_avatares")
    if not isinstance(crudos, list):
        raise AnalisisInvalido(gettext("El JSON no trae la lista «sub_avatares»."))
    limpios = []
    for c in crudos:
        if not isinstance(c, dict):
            continue
        if not _str(c.get("nombre")) or not _str(c.get("deseo")):
            continue
        campos = {k: c.get(k) for k in datos.AVATAR_EDITABLES}
        campos["evidencia"] = c.get("evidencia")
        limpios.append(datos.validar_campos_avatar(campos))
    if not limpios:
        raise AnalisisInvalido(gettext("Ningún sub-avatar venía completo."))
    return limpios[:MAX_SUBS_POR_NUCLEO]


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

ETAPA_NUCLEOS = N_("Agrupando deseos")
ETAPA_SUBS = N_("Armando sub-avatares")
ETAPA_COMPLETAR = N_("Completando avatares")


def _llamar(texto, max_tokens):
    """Una llamada a Claude (modelo del proyecto). Devuelve (texto, tokens de
    entrada, tokens de salida) — los tokens alimentan el gasto real. El uso
    se lee ANTES de mirar `refusal`/`max_tokens`: en cualquiera de los dos
    casos Claude ya cobró la llamada, así que la `AnalisisInvalido` que sube
    lleva `tokens_entrada`/`tokens_salida` puestos. Las pruebas reemplazan
    esta función."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens, system=doctrina.bloque_system("investigar"),
                                  messages=[{"role": "user", "content": texto}])
    uso = getattr(resp, "usage", None)
    entrada = int(getattr(uso, "input_tokens", 0) or 0)
    tok_salida = int(getattr(uso, "output_tokens", 0) or 0)
    if resp.stop_reason == "refusal":
        e = AnalisisInvalido(gettext("Claude rechazó la solicitud."))
        e.tokens_entrada, e.tokens_salida = entrada, tok_salida
        raise e
    salida = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "max_tokens":
        e = AnalisisInvalido(gettext("La respuesta de Claude se cortó por largo (max_tokens)."))
        e.tokens_entrada, e.tokens_salida = entrada, tok_salida
        raise e
    return salida, entrada, tok_salida


def _llamar_contando(texto, max_tokens, tokens):
    """Envuelve `_llamar`: suma sus tokens a la lista `tokens` (`[entrada,
    salida]`, mutada in place) tanto si la llamada sale bien como si sube
    `AnalisisInvalido` — un corte por `max_tokens` o un rechazo ya se cobró,
    así que también cuenta. Devuelve el texto de la respuesta, o repropaga el
    error tras contarlo."""
    try:
        texto_resp, entrada, salida = _llamar(texto, max_tokens)
    except AnalisisInvalido as e:
        tokens[0] += e.tokens_entrada
        tokens[1] += e.tokens_salida
        raise
    tokens[0] += entrada
    tokens[1] += salida
    return texto_resp


def generar(cliente, estudio_id, avanzar=None):
    """Las dos pasadas (spec §4.2, §4.5). Pasada 1 inválida: sube la excepción
    y no se guarda nada. Pasada 2: un núcleo que falla queda con `error` y sin
    sub-avatares; si TODOS fallan, sube AnalisisInvalido. No escribe en la
    base: el llamador (la tarea) guarda con datos.guardar_generacion.
    Cualquier `AnalisisInvalido` que salga de acá (pasada 1 inválida, un
    fallo de `_llamar`, o el "todos los núcleos fallaron") lleva los tokens
    acumulados hasta ese momento: el intento ya se cobró y la tarea necesita
    esa cifra para registrar el gasto igual."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    est = datos.estudio(cliente, estudio_id)
    if not est:
        raise datos.ErrorDatos(gettext("Ese estudio no existe."))
    todos = datos.comentarios_para_generar(cliente, estudio_id)
    if len(todos) < MIN_COMENTARIOS:
        raise datos.ErrorDatos(gettext("Hacen falta al menos %(minimo)s comentarios no excluidos (hay %(hay)s).",
                                       minimo=MIN_COMENTARIOS, hay=len(todos)))
    seleccion = seleccionar(todos)
    por_id = {c["id"]: c for c in seleccion}
    marca_nombre = proyectos.nombre_visible(cliente)
    avanzar(ETAPA_NUCLEOS)
    tokens = [0, 0]
    completados = 0
    try:
        texto = _llamar_contando(armar_prompt_nucleos(est, seleccion, marca_nombre), MAX_TOKENS_NUCLEOS, tokens)
        nucleos = parsear_nucleos(texto, set(por_id))
        guia = marca.guia_efectiva(cliente) or ""
        resultado, errores = [], []
        for i, n in enumerate(nucleos):
            avanzar(ETAPA_SUBS, f"{i + 1}/{len(nucleos)}: {n['nombre']}")
            propios = [por_id[cid] for cid in n["comentarios"]]
            try:
                t2 = _llamar_contando(armar_prompt_subs(est, n, propios, guia, marca_nombre), MAX_TOKENS_SUBS, tokens)
                subs = [verificar_evidencia(s, por_id) for s in parsear_subs(t2)]
                subs, n_comp = completar_subs(est, n, propios, subs, guia, marca_nombre, tokens)
                completados += n_comp
                resultado.append({**n, "sub_avatares": subs})
            except Exception as e:  # noqa: BLE001 — un núcleo que falla no pierde a los demás (spec §4.5)
                log.exception("Núcleo «%s» falló en la pasada 2", n["nombre"])
                errores.append(f"{n['nombre']}: {e}")
                resultado.append({**n, "sub_avatares": [], "error": str(e)[:300]})
        if errores and len(errores) == len(nucleos):
            raise AnalisisInvalido(gettext("Ningún núcleo produjo sub-avatares: %(errores)s",
                                       errores=" | ".join(errores)[:400]))
    except AnalisisInvalido as e:
        e.tokens_entrada, e.tokens_salida = tokens[0], tokens[1]
        raise
    subs_todos = [s for n in resultado for s in n["sub_avatares"]]
    resumen = {
        "comentarios": len(seleccion), "nucleos": len(resultado), "subs": len(subs_todos),
        "con_evidencia": sum(1 for s in subs_todos if not s.get("sin_evidencia")),
        "sin_evidencia": sum(1 for s in subs_todos if s.get("sin_evidencia")),
        "errores": len(errores), "tokens_entrada": tokens[0], "tokens_salida": tokens[1],
        "usd": costo_real(tokens[0], tokens[1]), "modelo": modelo_actual(),
        "completados": completados,
        "incompletos": sum(1 for s in subs_todos if calidad.faltantes(s)),
    }
    return {"nucleos": resultado, "resumen": resumen}


# ------------------------------------------------- completar lo guardado ---

def _sub_de_fila(f):
    return {**{k: f.get(k) for k in datos.AVATAR_EDITABLES}, "evidencia": list(f.get("evidencia") or []), "sin_evidencia": bool(f.get("sin_evidencia"))}


def completables(cliente, estudio_id):
    """[(núcleo, [subs incompletos no descartados])] de un estudio de verdad
    (el oculto de los avatares escritos a mano no tiene comentarios)."""
    est = datos.estudio(cliente, estudio_id)
    if not est or datos.es_manual(est):
        return []
    grupos = []
    for n in datos.avatares(cliente, estudio_id):
        subs = [s for s in n["subs"] if s["estado"] != "descartado" and calidad.faltantes(s)]
        if subs:
            grupos.append((n, subs))
    return grupos


def _comentarios_para_completar(cliente, estudio_id, subs):
    todos = datos.comentarios_para_generar(cliente, estudio_id)
    citados = {e.get("comentario_id") for s in subs for e in (s.get("evidencia") or [])}
    primero = [c for c in todos if c["id"] in citados]
    resto = seleccionar([c for c in todos if c["id"] not in citados], max_n=max(0, MAX_COMENTARIOS_COMPLETAR - len(primero)))
    return primero + resto


def estimar_completar(cliente, estudio_id, modelo=None):
    """Precio ANTES de completar los avatares guardados de un estudio (una
    llamada por núcleo con incompletos)."""
    modelo = modelo or modelo_actual()
    grupos = completables(cliente, estudio_id)
    entrada = salida = 0
    for _, subs in grupos:
        coms = _comentarios_para_completar(cliente, estudio_id, subs)
        entrada += int(sum(len(c.get("texto") or "") for c in coms) * TOKENS_POR_CARACTER) + TOKENS_PROMPT + TOKENS_SUB_JSON * len(subs)
        salida += TOKENS_SALIDA_ESTIMADO_COMPLETAR
    precios, referencia = _precios(modelo)
    usd = math.ceil((entrada * precios["entrada"] + salida * precios["salida"]) / 1e6 * 100) / 100 if grupos else 0.0
    return {"avatares": sum(len(s) for _, s in grupos), "tokens_entrada": entrada, "tokens_salida": salida, "usd": usd, "referencia": referencia}


def completables_por_estudio(cliente):
    """Para la página de avatares: por estudio no archivado, cuántos avatares se pueden completar y a qué precio."""
    salida = []
    for e in datos.estudios(cliente):
        est = estimar_completar(cliente, e["id"])
        if est["avatares"]:
            salida.append({"estudio_id": e["id"], "nombre": e["nombre"], "avatares": est["avatares"], "usd": est["usd"]})
    return salida


def completar_existentes(cliente, estudio_id, avanzar=None):
    """La pasada de completado sobre los avatares ya guardados de un estudio.
    No escribe: devuelve {"cambios": {avatar_id: campos que cambiaron},
    "resumen": {avatares, completados, tokens_entrada, tokens_salida, usd, modelo}}."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    est = datos.estudio(cliente, estudio_id)
    if not est:
        raise datos.ErrorDatos(gettext("Ese estudio no existe."))
    grupos = completables(cliente, estudio_id)
    guia, marca_nombre = marca.guia_efectiva(cliente) or "", proyectos.nombre_visible(cliente)
    tokens, cambios = [0, 0], {}
    for i, (n, filas) in enumerate(grupos):
        avanzar(ETAPA_COMPLETAR, f"{i + 1}/{len(grupos)}: {n['nombre']}")
        coms = _comentarios_para_completar(cliente, estudio_id, filas)
        antes = [_sub_de_fila(f) for f in filas]
        despues, _ = completar_subs(est, n, coms, antes, guia, marca_nombre, tokens)
        for fila, a, d in zip(filas, antes, despues):
            difiere = {k: d[k] for k in d if d.get(k) != a.get(k)}
            if difiere:
                cambios[fila["id"]] = difiere
    return {"cambios": cambios, "resumen": {"avatares": sum(len(f) for _, f in grupos), "completados": len(cambios),
                                           "tokens_entrada": tokens[0], "tokens_salida": tokens[1],
                                           "usd": costo_real(tokens[0], tokens[1]), "modelo": modelo_actual()}}

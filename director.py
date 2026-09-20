"""
Director de prompts de Crear (spec 2026-09-18-director-prompts-crear-design §2).

`compilar` le pide a Claude SOLO el bloque de planos (Shot N: plano, cámara,
acción, sonido) de dos versiones, los valida contra la sesión (número de
planos por duración, tiempos sin huecos, cámara del vocabulario cerrado,
tokens de referencia existentes, nada de duración/formato/resolución escritos)
y compone los textos completos con `flowplus_prompt.armar(..., planos=...)`,
así lo que devuelve es exactamente lo que se manda al modelo y lo que la
persona ve y edita. Ante una respuesta inválida pide UNA corrección; a la
segunda lanza `DirectorError` y el llamador (tareas/director.py) cae al
prompt determinista. No toca la base ni la red salvo Anthropic.
"""
import json
import os
import re

import anthropic

import flowplus_prompt
from providers import flowplus_modelos

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 4000
COSTO_LLAMADA_USD = 0.01
VERSION = 1
MAX_CARACTERES_PROMPT = 2500

_TOKEN = re.compile(r"\b(Image|Video) (\d+)\b")
# Lo que va por API y NO en el prompt (spec §2 validación 5).
_PARAMETRO_ESCRITO = re.compile(r"\b(\d+:\d+|\d{3,4}p|\d+ ?fps|\d+ segundos? de video|\d+ ?s de video)\b", re.IGNORECASE)


class DirectorError(Exception):
    def __init__(self, motivo):
        self.motivo = motivo
        super().__init__(f"El director no pudo armar los planos: {motivo}")


def _api_key():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise DirectorError("Falta ANTHROPIC_API_KEY en el .env")
    return api_key


def n_planos(duracion_s):
    d = int(duracion_s or 0)
    if d <= 5:
        return 1
    if d <= 10:
        return 2
    if d <= 15:
        return 3
    if d <= 20:
        return 4
    return 5


# --------------------------------------------------------------- plantillas ---

_REGLAS_COMUNES = """\
REGLAS
1. Intención primero: no cambies sujetos, cantidades, producto, lugar, orden de los hechos ni final. Los hechos vienen del texto; de las imágenes solo tomas rasgos visibles.
2. Planos: exactamente {n_planos} para {duracion} s. Tiempos enteros en segundos, sin huecos: el primero empieza en 0, cada fin es el inicio del siguiente, el último termina en {duracion}.
3. Cada plano: tamaño de plano ("primer plano", "plano medio", "plano general", "macro"...), UN solo movimiento de cámara elegido por su id de esta lista: {camaras}; la acción concreta (parte del cuerpo, grado, velocidad; movimientos lentos y continuos); y el sonido de ese tramo (fuente + acción + ambiente), sin voces ni música.
4. Activos: nómbralos siempre por su token y su nombre, p. ej. "Ana (Image 1)". Usa SOLO los tokens de la tabla ACTIVOS; nunca inventes otros. El producto se describe con forma, color, material y logotipo tal cual. Nunca dos personajes desde una misma imagen; sin duplicados.
5. Emociones como gestos observables (una sonrisa que crece, hombros que se relajan), nunca adjetivos.
6. No escribas duración total, formato (9:16), resolución (720p) ni fps: van por API.
7. Nada de "alta calidad", "8k", "sin deformaciones" ni packs de calidad.
8. Idioma de los textos: {idioma}. Los tokens (Image N, Video N) siempre en inglés.
9. planos_b: misma intención y mismos activos; el primer plano usa OTRO movimiento de cámara y otro arranque; diferencia_b lo explica en una frase.
10. Los planos de cada versión, juntos, no pasan de {max_chars} caracteres.
11. El sistema antepone «Hard cut.» a cada plano a partir del segundo: no escribas transiciones, fundidos ni disolvencias entre planos.

SALIDA (JSON estricto, sin texto alrededor ni markdown):
{{"planos": [{{"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "...", "camara": "dolly_in", "accion": "...", "sonido": "..."}}],
 "planos_b": [...misma forma...],
 "diferencia_b": "..."}}
"""

_FAMILIAS = {
    "wan": (
        "Eres director de fotografía y guionista de anuncios cortos. Conviertes una idea corta y unas referencias en un plan de "
        "planos para Wan 3.0 (referencia-a-video). Fórmula de Wan: entidad + escena + movimiento + control estético (luz, tamaño "
        "de plano, ángulo). Las referencias se llaman Image N y Video N; Video N es referencia de movimiento y encuadre, nunca de "
        "objetos ni personas. Órbitas de menos de 45 grados. Cierre de sonido que pondrá el sistema: \"{cierre}\".\n\n"
    ),
    "kling": (
        "Eres director de fotografía y guionista de anuncios cortos. Conviertes una idea corta y unas referencias en un plan de "
        "planos para Kling O3 Pro (referencia-a-video). Fórmula de Kling: sujeto + movimiento del sujeto + escena + cámara + luz. "
        "Frases simples y cortas; una acción y un movimiento por plano; sin números de conteo (\"tres personas\") y sin físicas "
        "complejas (rebotes, lanzamientos). Cierre de sonido que pondrá el sistema: \"{cierre}\".\n\n"
    ),
    "seedance": (
        "Eres director de fotografía y guionista de anuncios cortos. Conviertes una idea corta en un plan de planos para "
        "Seedance 2.5 (imagen-a-video): la Image 1 ya fija el sujeto, la escena y el estilo, así que describe SOLO movimiento y "
        "cámara por tramos de tiempo enteros; no vuelvas a describir el producto ni el fondo. Términos de cámara estándar "
        "(push in, pull out, pan, track, orbit). Cierre de sonido que pondrá el sistema: \"{cierre}\".\n\n"
    ),
}


def _system(familia, cierre, n, duracion, idioma):
    return _FAMILIAS[familia].format(cierre=cierre) + _REGLAS_COMUNES.format(
        n_planos=n, duracion=duracion, camaras=", ".join(flowplus_prompt.CAMARAS), idioma="español" if idioma == "es" else "inglés",
        max_chars=MAX_CARACTERES_PROMPT)


def _mensaje(sesion, idioma):
    refs = list(sesion.get("referencias") or [])
    idea = flowplus_prompt.sustituir_tokens(sesion.get("accion_central") or "", refs)
    lineas = [f"IDEA: {idea}", "ACTIVOS (token → rol → nombre → regla):"]
    for r in refs:
        if not r.get("token"):
            continue
        rol = "logo oficial" if r.get("logo") else (r.get("categoria") or ("video de referencia" if r.get("tipo") == "video" else "imagen de referencia"))
        nombre = r.get("activo") or r.get("etiqueta") or ""
        lineas.append(f"- {r['token']} → {rol} → {nombre} → {r.get('regla') or ''}".rstrip(" →"))
    lineas.append(f"ENFOQUE: {sesion.get('enfoque') or 'producto'}")
    if sesion.get("guia_marca"):
        lineas.append(f"MARCA: {sesion['guia_marca']}")
    con_sonido = bool(sesion.get("con_sonido"))
    lineas.append(f"SONIDO: {'sí' if con_sonido else 'no'}" + (f" — {sesion['sonido_texto']}" if con_sonido and sesion.get("sonido_texto") else ""))
    lineas.append(f"PRESET: {sesion.get('preset_camara') or 'auto'}")
    if sesion.get("plantilla"):
        lineas.append(f"PLANTILLA: {json.dumps(sesion['plantilla'], ensure_ascii=False)}")
    ctx = sesion.get("contexto") or {}
    if ctx.get("persona"):
        lineas.append(f"AUDIENCIA: {json.dumps(ctx['persona'], ensure_ascii=False)}")
    if ctx.get("temporada"):
        lineas.append(f"TEMPORADA: {json.dumps(ctx['temporada'], ensure_ascii=False)}")
    lineas.append(f"IDIOMA: {idioma}")
    return "\n".join(lineas)


# ------------------------------------------------------------- validación ---

def _extraer_json(texto):
    i, j = texto.find("{"), texto.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("la respuesta no trae un objeto JSON")
    return json.loads(texto[i:j + 1])


def _validar_planos(planos, n_esperado, duracion, tokens_validos, nombre):
    if not isinstance(planos, list) or len(planos) != n_esperado:
        raise ValueError(f"{nombre}: se esperaban {n_esperado} planos y llegaron {len(planos) if isinstance(planos, list) else 'ninguno'}")
    esperado_inicio = 0
    for i, p in enumerate(planos, start=1):
        if not isinstance(p, dict) or int(p.get("n", -1)) != i:
            raise ValueError(f"{nombre}: el plano {i} no está numerado {i}")
        ini, fin = int(p.get("inicio_s", -1)), int(p.get("fin_s", -1))
        if ini != esperado_inicio or fin <= ini:
            raise ValueError(f"{nombre}: el plano {i} va de {ini} a {fin}, debía empezar en {esperado_inicio}")
        esperado_inicio = fin
        if p.get("camara") not in flowplus_prompt.CAMARAS:
            raise ValueError(f"{nombre}: cámara desconocida {p.get('camara')!r} en el plano {i}")
        if not isinstance(p.get("plano"), str) or not p["plano"].strip():
            raise ValueError(f"{nombre}: el plano {i} no tiene tamaño de plano")
        texto = " ".join(str(p.get(k) or "") for k in ("plano", "accion", "sonido"))
        for m in _TOKEN.finditer(texto):
            if m.group(0) not in tokens_validos:
                raise ValueError(f"{nombre}: el plano {i} cita {m.group(0)}, que no existe")
        if _PARAMETRO_ESCRITO.search(texto):
            raise ValueError(f"{nombre}: el plano {i} escribe duración, formato o resolución (van por API)")
        if not str(p.get("accion") or "").strip():
            raise ValueError(f"{nombre}: el plano {i} no tiene acción")
    if esperado_inicio != int(duracion):
        raise ValueError(f"{nombre}: los planos terminan en {esperado_inicio} s y el video dura {duracion} s")


def _componer(cliente, sesion, planos, cierre):
    refs = list(sesion.get("referencias") or [])
    info = flowplus_prompt.ENFOQUES.get(sesion.get("enfoque") or "producto")
    return flowplus_prompt.armar(
        sesion.get("accion_central") or "", refs, con_persona=info["con_persona"] if info else False,
        guia_marca=sesion.get("guia_marca") or "", negative_marca=sesion.get("negative_marca"),
        logos=[r for r in refs if r.get("logo")], enfoque=sesion.get("enfoque"), contexto=sesion.get("contexto"),
        sonido=None, con_sonido=bool(sesion.get("con_sonido")), planos=planos, cierre_sonido=cierre,
    )


def _validar_y_componer(cliente, sesion, datos, n, duracion, cierre):
    tokens = {r["token"] for r in (sesion.get("referencias") or []) if r.get("token")}
    _validar_planos(datos.get("planos"), n, duracion, tokens, "planos")
    _validar_planos(datos.get("planos_b"), n, duracion, tokens, "planos_b")
    if datos["planos"][0]["camara"] == datos["planos_b"][0]["camara"]:
        raise ValueError("planos_b: el primer plano repite la cámara de la versión A")
    if not str(datos.get("diferencia_b") or "").strip():
        raise ValueError("falta diferencia_b")
    # El tope de longitud mide SOLO lo que escribió Claude (el bloque de
    # planos), no el prompt ya compuesto: ese trae guía de marca, reglas de
    # activos y EVITAR, que con una guía normal ya pasan de 2500 por su
    # cuenta y harían fallar al director siempre (spec ruling F1).
    con_sonido = bool(sesion.get("con_sonido"))
    for nombre, planos in (("planos", datos["planos"]), ("planos_b", datos["planos_b"])):
        bloque = "\n".join(flowplus_prompt._bloque_planos(planos, con_sonido))
        if len(bloque) > MAX_CARACTERES_PROMPT:
            raise ValueError(f"{nombre}: los planos pasan de {MAX_CARACTERES_PROMPT} caracteres")
    prompt_a = _componer(cliente, sesion, datos["planos"], cierre)
    prompt_b = _componer(cliente, sesion, datos["planos_b"], cierre)
    return {"planos": datos["planos"], "planos_b": datos["planos_b"], "prompt_a": prompt_a, "prompt_b": prompt_b,
            "diferencia_b": str(datos["diferencia_b"]).strip()}


# ----------------------------------------------------------------- público ---

def compilar(cliente, sesion, idioma="es"):
    """Devuelve {planos, planos_b, prompt_a, prompt_b, diferencia_b,
    modelo_claude, version, usd}. Lanza DirectorError si Claude no entrega
    planos válidos en dos intentos o si el modelo no tiene familia."""
    modelo = sesion.get("modelo")
    info = flowplus_modelos.VIDEO.get(modelo) or {}
    familia = info.get("familia")
    if familia not in _FAMILIAS:
        raise DirectorError(f"el modelo {modelo!r} no tiene familia de prompt")
    duracion = int(sesion.get("duracion_objetivo") or 0)
    if duracion <= 0:
        raise DirectorError("la sesión no tiene duración")
    n = n_planos(duracion)
    cierre = flowplus_modelos.cierre_sonido(modelo)
    idioma = "en" if idioma == "en" else "es"
    system = _system(familia, cierre, n, duracion, idioma)
    mensajes = [{"role": "user", "content": _mensaje(sesion, idioma)}]
    client = anthropic.Anthropic(api_key=_api_key())
    ultimo_error = None
    for _intento in range(2):
        try:
            resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system, messages=mensajes)
        except Exception as e:
            raise DirectorError(f"Anthropic: {e}") from e
        texto = "".join(getattr(b, "text", "") for b in resp.content)
        if getattr(resp, "stop_reason", None) == "max_tokens":
            # Se cortó a mitad de la respuesta: ni vale la pena intentar
            # parsear JSON. Se le pide más corto en vez de gastar el segundo
            # (y último) intento en un error de parseo que no explica la causa.
            ultimo_error = "respuesta truncada por longitud: responde más corto"
            mensajes = mensajes + [{"role": "assistant", "content": texto},
                                   {"role": "user", "content": f"Tu respuesta anterior no sirvió ({ultimo_error}). Responde solo el JSON pedido."}]
            continue
        if not texto.strip():
            # La API rechaza un turno assistant con content vacío — no se puede
            # simplemente reusar `texto` como en los demás casos de corrección.
            ultimo_error = "respuesta vacía"
            mensajes = mensajes + [{"role": "assistant", "content": "(respuesta vacía)"},
                                   {"role": "user", "content": f"Tu respuesta anterior no sirvió ({ultimo_error}). Responde solo el JSON pedido."}]
            continue
        try:
            datos = _extraer_json(texto)
            resultado = _validar_y_componer(cliente, sesion, datos, n, duracion, cierre)
        except (ValueError, TypeError, KeyError) as e:
            ultimo_error = str(e)
            mensajes = mensajes + [{"role": "assistant", "content": texto},
                                   {"role": "user", "content": f"Tu respuesta anterior no sirvió ({ultimo_error}). Responde solo el JSON pedido."}]
            continue
        resultado.update({"modelo_claude": MODEL, "version": VERSION, "usd": COSTO_LLAMADA_USD})
        return resultado
    raise DirectorError(ultimo_error or "respuesta inválida")

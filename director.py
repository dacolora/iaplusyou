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

import doctrina
import flowplus_prompt
import idiomas
import plantillas_anuncio
from providers import flowplus_modelos
from guiones.claude import tokens_entrada_equivalentes
from nicho.avatares import costo_real

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 4000
VERSION = 1
MAX_CARACTERES_PROMPT = 2500

# `Image N` / `Video N`, y la forma pegada `@Image1` de Seedance 2.5 con varias
# referencias (vía fal): un token que no está en ACTIVOS se rechaza en las dos.
_TOKEN = re.compile(r"@(?:Image|Video)\d+\b|\b(?:Image|Video) \d+\b")
_TOKEN_SUELTO = re.compile(r"(?<!@)\bImage (\d+)\b")
# Revisión final fase 3 (finding 1): con un proyecto en español la orden de
# idioma ahora permite el español salvo estas excepciones (ver idiomas._ORDENES),
# pero Claude puede seguir devolviendo el token traducido por su cuenta
# ("Imagen 1", "Vídeo 2"): _TOKEN nunca los reconoce como válidos (silenciosamente
# los deja pasar como texto libre), así que se valida aparte para que dispare el
# mismo reintento/fallback que cualquier otro plano inválido.
_TOKEN_ES = re.compile(r"\bIm[aá]gen \d+\b|\bV[ií]deo \d+\b")
# Lo que va por API y NO en el prompt (spec §2 validación 5).
_PARAMETRO_ESCRITO = re.compile(r"\b(\d+:\d+|\d{3,4}p|\d+ ?fps|\d+ segundos? de video|\d+ ?s de video)\b", re.IGNORECASE)


class DirectorError(Exception):
    def __init__(self, motivo, costo_usd=0.0):
        self.motivo = motivo
        self.costo_usd = costo_usd
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
4. Activos: nómbralos siempre por su token y su nombre, p. ej. {ejemplo_token}. Usa SOLO los tokens de la tabla ACTIVOS; nunca inventes otros. El producto se describe con forma, color, material y logotipo tal cual. Nunca dos personajes desde una misma imagen; sin duplicados.
5. Emociones como gestos observables (una sonrisa que crece, hombros que se relajan), nunca adjetivos.
6. No escribas duración total, formato (9:16), resolución (720p) ni fps: van por API.
7. Nada de "alta calidad", "8k", "sin deformaciones" ni packs de calidad.
8. Idioma de los textos: {idioma}. Los tokens ({forma_tokens}) siempre en inglés.
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
    # Seedance 2.5 referencia-a-video (vía fal, 2026-10-09): varias imágenes que
    # fijan personajes, producto y lugar; ninguna es el primer fotograma.
    "seedance_ref": (
        "Eres director de fotografía y guionista de anuncios cortos. Conviertes una idea corta y unas referencias en un plan de "
        "planos para Seedance 2.5 (referencia-a-video). Las referencias se llaman @Image1, @Image2…: cada una fija un personaje, "
        "el producto o el lugar, y ninguna es el primer fotograma. Al presentar a alguien o algo, átalo a su referencia "
        "(Ana@Image1) y nómbralo siempre igual; 2-3 rasgos fijos por sujeto. Describe la acción y la cámara por tramos de tiempo "
        "enteros, con términos de cámara estándar (push in, pull out, pan, track, orbit). Cierre de sonido que pondrá el "
        "sistema: \"{cierre}\".\n\n"
    ),
}


# Cómo se ven los tokens en las reglas comunes: la forma de siempre, salvo
# Seedance 2.5 con varias referencias (fal nombra @Image1, @Image2…). Medido el
# 2026-10-09 (docs/superpowers/evals/2026-10-09-director-seedance-ref.md): con el
# ejemplo «Ana (Image 1)» Claude escribía «Image 1» y 2 de 3 casos caían al prompt fijo.
_TOKENS_REGLAS = {
    "seedance_ref": ('"Ana@Image1"', "@Image1, @Image2…"),
}
_TOKENS_REGLAS_DEFECTO = ('"Ana (Image 1)"', "Image N, Video N")


def _system(familia, cierre, n, duracion, idioma):
    ejemplo_token, forma_tokens = _TOKENS_REGLAS.get(familia, _TOKENS_REGLAS_DEFECTO)
    return _FAMILIAS[familia].format(cierre=cierre) + _REGLAS_COMUNES.format(
        n_planos=n, duracion=duracion, camaras=", ".join(flowplus_prompt.CAMARAS), idioma=idiomas.nombre_para_claude(idioma),
        max_chars=MAX_CARACTERES_PROMPT, ejemplo_token=ejemplo_token, forma_tokens=forma_tokens)


# Qué significa cada enfoque para Claude. «producto» NO es «solo y sin nadie»
# (2026-09-28, pedido de la persona): el producto es el protagonista y las
# escenas muestran lo que hace o cambia; manos o personas solo si hacen falta.
_ENFOQUES_DIRECTOR = {
    "producto": ("el producto es el protagonista y las escenas muestran lo que hace o cambia — en uso, antes/después, "
                 "el resultado a la vista —, nunca el producto quieto; manos o personas solo si la escena lo pide"),
    "persona": ("una persona real usa el producto y las escenas muestran el resultado que consigue; el producto sigue "
                "siendo el protagonista"),
    "unboxing": "alguien recibe la compra y la abre hasta descubrir el producto (el sistema añade el bloque UNBOXING)",
}


def _mensaje(sesion, idioma):
    refs = list(sesion.get("referencias") or [])
    idea = flowplus_prompt.sustituir_tokens(sesion.get("accion_central") or "", refs)
    lineas = [f"IDEA: {idea}"]
    angulo_txt = doctrina.angulo_a_texto(sesion.get("angulo"))
    if angulo_txt:
        lineas += [angulo_txt,
                   "Traduce el ángulo a planos: el producto aparece pronto; el mecanismo, si lo hay, se demuestra en "
                   "cámara; la prueba es algo que se ve pasar; el gancho puede ser lo que se lee en el primer plano. "
                   "La IDEA sigue mandando en sujetos, lugar y orden de los hechos."]
    lineas.append("ACTIVOS (token → rol → nombre → regla):")
    for r in refs:
        if not r.get("token"):
            continue
        rol = "logo oficial" if r.get("logo") else (r.get("categoria") or ("video de referencia" if r.get("tipo") == "video" else "imagen de referencia"))
        nombre = r.get("activo") or r.get("etiqueta") or ""
        lineas.append(f"- {r['token']} → {rol} → {nombre} → {r.get('regla') or ''}".rstrip(" →"))
    enfoque = sesion.get("enfoque") or "producto"
    if enfoque == "libre":
        lineas.append("ENFOQUE: libre — sin producto ni activos; la escena sale solo de la IDEA")
    else:
        lineas.append(f"ENFOQUE: {enfoque} — {_ENFOQUES_DIRECTOR.get(enfoque, _ENFOQUES_DIRECTOR['producto'])}")
    if sesion.get("guia_marca"):
        lineas.append(f"MARCA: {sesion['guia_marca']}")
    con_sonido = bool(sesion.get("con_sonido"))
    lineas.append(f"SONIDO: {'sí' if con_sonido else 'no'}" + (f" — {sesion['sonido_texto']}" if con_sonido and sesion.get("sonido_texto") else ""))
    lineas.append(f"PRESET: {sesion.get('preset_camara') or 'auto'}")
    plantilla = plantillas_anuncio.por_id(sesion.get("plantilla"))
    if plantilla:
        lineas += plantillas_anuncio.bloque_director(plantilla, sesion.get("duracion_objetivo"), refs)
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
        m_es = _TOKEN_ES.search(texto)
        if m_es:
            # Sin "en español"/"al español" literal en este mensaje: vuelve a
            # Claude como corrección (compilar()) y test_i18n_claude.py escanea
            # TODO el archivo por esa frase, no solo los prompts de _system().
            raise ValueError(f"{nombre}: el plano {i} cita {m_es.group(0)!r}: los tokens no se traducen, van siempre en inglés (Image N / Video N)")
        if _PARAMETRO_ESCRITO.search(texto):
            raise ValueError(f"{nombre}: el plano {i} escribe duración, formato o resolución (van por API)")
        if not str(p.get("accion") or "").strip():
            raise ValueError(f"{nombre}: el plano {i} no tiene acción")
    if esperado_inicio != int(duracion):
        raise ValueError(f"{nombre}: los planos terminan en {esperado_inicio} s y el video dura {duracion} s")


def _componer(cliente, sesion, planos, cierre, idioma):
    refs = list(sesion.get("referencias") or [])
    info = flowplus_prompt.ENFOQUES.get(sesion.get("enfoque") or "producto")
    return flowplus_prompt.armar(
        sesion.get("accion_central") or "", refs, con_persona=info["con_persona"] if info else False,
        guia_marca=sesion.get("guia_marca") or "", negative_marca=sesion.get("negative_marca"),
        logos=[r for r in refs if r.get("logo")], enfoque=sesion.get("enfoque"), contexto=sesion.get("contexto"),
        sonido=None, con_sonido=bool(sesion.get("con_sonido")), planos=planos, cierre_sonido=cierre, idioma=idioma,
    )


def _a_tokens_pegados(planos):
    """«Image 2» → «@Image2» en lo que escribió Claude, cuando el modelo nombra
    sus imágenes con la forma pegada (Seedance 2.5 vía fal): es la misma
    referencia y no hay ambigüedad. Un número que no existe sigue sin pasar
    la validación."""
    for p in planos if isinstance(planos, list) else []:
        if isinstance(p, dict):
            for k in ("plano", "accion", "sonido"):
                if isinstance(p.get(k), str):
                    p[k] = _TOKEN_SUELTO.sub(r"@Image\1", p[k])


def _validar_y_componer(cliente, sesion, datos, n, duracion, cierre, idioma):
    tokens = {r["token"] for r in (sesion.get("referencias") or []) if r.get("token")}
    if any(t.startswith("@Image") for t in tokens):
        _a_tokens_pegados(datos.get("planos"))
        _a_tokens_pegados(datos.get("planos_b"))
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
        bloque = "\n".join(flowplus_prompt._bloque_planos(planos, con_sonido, idioma))
        if len(bloque) > MAX_CARACTERES_PROMPT:
            raise ValueError(f"{nombre}: los planos pasan de {MAX_CARACTERES_PROMPT} caracteres")
    prompt_a = _componer(cliente, sesion, datos["planos"], cierre, idioma)
    prompt_b = _componer(cliente, sesion, datos["planos_b"], cierre, idioma)
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
    plantilla = plantillas_anuncio.por_id(sesion.get("plantilla"))
    if plantilla:
        # Con receta, al menos un plano por acto (spec §9).
        n = plantillas_anuncio.n_planos(plantilla, duracion, n)
    cierre = flowplus_modelos.cierre_sonido(modelo)
    idioma = "en" if idioma == "en" else "es"
    system = doctrina.bloque_system("video", extra=_system(familia, cierre, n, duracion, idioma), idioma=idioma)
    mensajes = [{"role": "user", "content": _mensaje(sesion, idioma)}]
    client = anthropic.Anthropic(api_key=_api_key(), max_retries=0)
    ultimo_error = None
    entrada = salida = 0
    for _intento in range(2):
        try:
            resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system, messages=mensajes)
        except Exception as e:
            raise DirectorError(f"Anthropic: {e}", costo_real(entrada, salida, MODEL)) from e
        uso = getattr(resp, "usage", None)
        entrada += tokens_entrada_equivalentes(uso)
        salida += int(getattr(uso, "output_tokens", 0) or 0)
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
            resultado = _validar_y_componer(cliente, sesion, datos, n, duracion, cierre, idioma)
        except (ValueError, TypeError, KeyError) as e:
            ultimo_error = str(e)
            mensajes = mensajes + [{"role": "assistant", "content": texto},
                                   {"role": "user", "content": f"Tu respuesta anterior no sirvió ({ultimo_error}). Responde solo el JSON pedido."}]
            continue
        except Exception as e:
            raise DirectorError(str(e), costo_real(entrada, salida, MODEL)) from e
        resultado.update({"modelo_claude": MODEL, "version": VERSION, "usd": costo_real(entrada, salida, MODEL)})
        return resultado
    raise DirectorError(ultimo_error or "respuesta inválida", costo_real(entrada, salida, MODEL))

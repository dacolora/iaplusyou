"""
Análisis de una referencia con Claude (visión), persistido en
`referencia.analisis` (spec §1.5). Es lo que después alimenta el prompt
maestro de la Parte 2. `_llamar` es la única función que toca la API: las
pruebas la reemplazan.
"""
import base64
import json
import os

from flask_babel import gettext

import doctrina
import idiomas
from sprints import datos

CLAVES = ("resumen", "paleta", "composicion", "iluminacion", "movimiento", "tipografia", "estetica",
          "storytelling", "elementos")
# Claves opcionales (spec 2026-09-25 §5.3): un análisis viejo sin ellas sigue valiendo.
PRUEBAS_REFERENCIA = ("demostracion", "testimonio", "cifra", "autoridad", "ninguna")

PROMPT_ANALISIS = """Eres director de arte de anuncios cortos para redes sociales. Vas a ver una referencia visual (una imagen, o fotogramas en orden de un video) que una persona subió para inspirar contenido de la marca {marca}.
Lo que le interesa reutilizar de esta referencia: {intencion}.
Lo que escribió sobre ella: «{descripcion}».

Responde SOLO con un objeto JSON, sin texto antes ni después, con exactamente estas claves:
- "resumen": qué se ve y por qué funciona, máximo 40 palabras.
- "paleta": lista de 3 a 5 colores dominantes en hexadecimal (#RRGGBB).
- "composicion": encuadre, distancia y dónde está el producto o el sujeto.
- "iluminacion": tipo, dirección y temperatura de la luz.
- "movimiento": movimiento de cámara y ritmo; "sin movimiento" si es una imagen.
- "tipografia": tipografía y ubicación del texto en pantalla; "ninguna" si no hay texto.
- "estetica": estilo general en 5 a 10 palabras.
- "storytelling": qué cuenta o sugiere la escena, en una frase.
- "elementos": lista de 3 a 8 sustantivos con lo que aparece.
- "gancho": qué hace la pieza en los primeros tres segundos, o su titular si es imagen; máximo 20 palabras; "" si no se puede saber.
- "lead": cómo arranca, uno de: "oferta", "promesa", "problema_solucion", "secreto", "proclamacion", "historia"; null si no se puede saber.
- "prueba": cómo sostiene lo que promete, uno de: "demostracion", "testimonio", "cifra", "autoridad", "ninguna".
Todo en {idioma}. No menciones "fotograma" ni "imagen": describe la escena."""


class AnalisisInvalido(RuntimeError):
    pass


def _llamar(content, max_tokens=700, system=None):
    """Una llamada a Claude con bloques de texto e imagen; devuelve el texto.
    `system` (str o lista de bloques, p. ej. `doctrina.bloque_system(...)`)
    solo se manda si viene."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    extra = {"system": system} if system else {}
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": content}], **extra)
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _llamar_contando(content, max_tokens=700, system=None, timeout=None, max_retries=None, uso=None):
    """Como `_llamar`, pero devuelve (texto, tokens_entrada, tokens_salida)
    para registrar el gasto real de una acción pagada. `usage.input_tokens`
    no incluye la caché (la doctrina va en el system con cache_control): se
    suman como tokens de entrada equivalentes, escribirla a 1,25× y leerla a
    0,1× (el precio de Anthropic), para que el gasto no quede corto. `timeout`
    (segundos) y `max_retries` van al cliente cuando se dan: un sitio que corre
    dentro del worker entre dos acciones (el diagnóstico) no puede colgarse."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    opciones = {k: v for k, v in (("timeout", timeout), ("max_retries", max_retries)) if v is not None}
    client = anthropic.Anthropic(api_key=_api_key(), **opciones)
    extra = {"system": system} if system else {}
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": content}], **extra)
    u = resp.usage
    escrita = getattr(u, "cache_creation_input_tokens", None) or 0
    leida = getattr(u, "cache_read_input_tokens", None) or 0
    entrada = u.input_tokens + round(escrita * 1.25 + leida * 0.1)
    if uso is not None:
        uso["entrada"] = uso.get("entrada", 0) + entrada
        uso["salida"] = uso.get("salida", 0) + u.output_tokens
    texto = "".join(b.text for b in resp.content if b.type == "text").strip()
    return texto, entrada, u.output_tokens


def _parsear_json(texto):
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
    faltan = [k for k in CLAVES if k not in data]
    if faltan:
        raise AnalisisInvalido(gettext("Faltan claves: %(faltan)s", faltan=", ".join(faltan)))
    data["paleta"] = [c for c in (data.get("paleta") or []) if isinstance(c, str) and datos.COLOR_HEX.match(c)][:5]
    data["elementos"] = [str(e) for e in (data.get("elementos") or [])][:8]
    salida = {k: data[k] for k in CLAVES}
    salida["gancho"] = " ".join(str(data.get("gancho") or "").split())[:200]
    salida["lead"] = data.get("lead") if data.get("lead") in doctrina.LEADS else None
    salida["prueba"] = data.get("prueba") if data.get("prueba") in PRUEBAS_REFERENCIA else None
    return salida


def _bloques_imagen(referencia):
    """Imagen: su URL. Video: hasta 3 fotogramas del archivo local; si el
    archivo ya no está, el fotograma que quedó en R2."""
    bloques = []
    ruta = referencia.get("ruta_local")
    if referencia.get("tipo") == "video" and ruta and os.path.exists(ruta):
        from referencias_link import fotogramas
        for b in fotogramas(ruta, n=3):
            bloques.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(b).decode()}})
    if not bloques:
        url = referencia.get("frame_url") if referencia.get("tipo") == "video" else referencia.get("url")
        if url:
            bloques.append({"type": "image", "source": {"type": "url", "url": url}})
    return bloques


def _system(idioma="es"):
    return doctrina.bloque_system("clasificar", idioma=idioma)


def analizar(referencia, marca="", idioma="es", uso=None):
    """Devuelve el dict con CLAVES. Reintenta una sola vez si el JSON no sirve."""
    etiquetas = [datos.INTENCIONES_NOMBRE.get(i, i) for i in (referencia.get("intencion") or [])]
    intencion = ", ".join(etiquetas) or "todo lo que valga la pena reutilizar"
    if referencia.get("intencion_otro"):
        intencion += f" ({referencia['intencion_otro']})"
    texto = PROMPT_ANALISIS.format(marca=marca or "este proyecto", intencion=intencion,
                                   descripcion=referencia.get("descripcion") or "sin descripción",
                                   idioma=idiomas.nombre_para_claude(idioma))
    imagenes = _bloques_imagen(referencia)
    if not imagenes:
        raise AnalisisInvalido(gettext("La referencia no tiene imagen ni fotograma que analizar."))
    content = [{"type": "text", "text": texto}] + imagenes
    def llamar(bloques):
        if uso is None:
            return _llamar(bloques, max_tokens=4000, system=_system(idioma))
        return _llamar_contando(bloques, max_tokens=4000, system=_system(idioma),
                               max_retries=0, uso=uso)[0]
    try:
        return _parsear_json(llamar(content))
    except AnalisisInvalido as e:
        content = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). Responde solo el JSON pedido."}]
        return _parsear_json(llamar(content))

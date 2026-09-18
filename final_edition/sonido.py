"""Sonido de la escena (spec estudio S1): sugerencia con Claude de qué se
oye en la escena (1–2 líneas, sin diálogo ni música) para el campo "Sonido
de la escena" de Crear. S3 sumará aquí el respaldo video→audio."""
MAX_CARACTERES = 200

PROMPT = (
    "Eres diseñador de sonido de anuncios cortos para redes. Describe en una o dos líneas "
    "(máximo 25 palabras, en español, separadas por comas) qué se OYE en esta escena de video: "
    "ambiente, acciones, texturas, respiraciones, risas, pasos, golpes, roces. Sin diálogo hablado "
    "y sin música: solo sonido de la escena. Responde con la descripción y nada más.\n\n"
    "ESCENA: {escena}\nENFOQUE: {enfoque}\n{persona}"
)


def _llamar(texto, max_tokens=200):
    """Una llamada de texto a Claude; devuelve el texto de la respuesta."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": texto}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def sugerir_descripcion(escena, enfoque, persona=None):
    """Descripción corta del sonido de la escena. `persona` (opcional, del
    sprint): {resumen, descripcion, tono}. Con escena vacía no llama."""
    escena = (escena or "").strip()
    if not escena:
        return ""
    p = persona or {}
    linea_persona = ""
    partes = [str(p[k]).strip() for k in ("resumen", "descripcion", "tono") if p.get(k)]
    if partes:
        linea_persona = "AUDIENCIA: " + ". ".join(partes) + "\n"
    texto = PROMPT.format(escena=escena[:1000], enfoque=enfoque or "producto", persona=linea_persona)
    respuesta = (_llamar(texto) or "").strip().strip('"').strip("'").strip()
    respuesta = " ".join(respuesta.split())
    return respuesta[:MAX_CARACTERES]

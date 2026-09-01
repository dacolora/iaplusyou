"""
Genera prompts candidatos de video (para Higgsfield) a partir de una idea, usando
la API de Anthropic (Claude). Requiere ANTHROPIC_API_KEY en el .env.
"""
import json
import os

import anthropic

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

SYSTEM_PROMPT = """Eres un director creativo que escribe prompts para un modelo de \
imagen-a-video (Kling, vía Higgsfield). A partir de una idea y sabiendo que ya hay \
una imagen de referencia de un personaje (el modelo anima esa imagen, no cambia el \
personaje ni el estilo visual), escribe variantes de prompt en español.

Reglas:
- Cada prompt describe UNA sola acción física concreta del personaje y/o un \
movimiento de cámara (paneo, zoom, travelling, etc.), filmable en 5-10 segundos.
- No repitas la misma acción en dos variantes; dale variedad de planos y momentos \
dentro de la misma idea.
- No menciones texto en pantalla, marcas, ni cambies la apariencia del personaje.
- Cada prompt: 1-2 frases, directo, sin explicaciones extra ni comillas.

Responde ÚNICAMENTE con un JSON array de strings, sin texto adicional ni markdown.
Ejemplo de formato: ["prompt 1", "prompt 2", "prompt 3", "prompt 4", "prompt 5"]"""


def _api_key():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta ANTHROPIC_API_KEY en tu .env. Consíguela en console.anthropic.com "
            "(Settings > API Keys)."
        )
    return api_key


def generar_prompts(idea, n=5, guia_estilo=None):
    """guia_estilo: texto de la identidad de marca del cliente (paleta, tono,
    iluminación, ambientación), si existe — se le pide a Claude que lo respete
    en cada variante para que el contenido se mantenga consistente."""
    client = anthropic.Anthropic(api_key=_api_key())

    mensaje = f"Idea: {idea}\n\nEscribe {n} variantes de prompt."
    if guia_estilo and guia_estilo.strip():
        mensaje += (
            f"\n\nGuía de estilo de la marca (respétala en cada variante, sin "
            f"mencionarla explícitamente en el prompt):\n{guia_estilo.strip()}"
        )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": mensaje}],
    )
    texto = "".join(block.text for block in resp.content if block.type == "text").strip()

    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.lower().startswith("json"):
            texto = texto[4:]
        texto = texto.strip()

    try:
        prompts = json.loads(texto)
    except json.JSONDecodeError:
        raise RuntimeError(f"No pude interpretar la respuesta del modelo como JSON: {texto[:300]}")

    if not isinstance(prompts, list) or not all(isinstance(p, str) for p in prompts):
        raise RuntimeError(f"Respuesta con formato inesperado: {texto[:300]}")

    return prompts[:n]


CONCEPTOS_IMAGEN_SYSTEM_PROMPT = """Eres un director de arte. A partir de una idea y \
sabiendo que ya hay una imagen de referencia de un personaje (el modelo genera una \
escena nueva a partir de esa imagen, sin cambiar el personaje ni su identidad), \
describe escenas FIJAS para una fotografía — no un video, no menciones cámara, \
movimiento ni duración.

Reglas:
- Cada escena es una sola frase concreta: qué se ve, dónde, con qué luz y composición.
- Dale variedad real entre las escenas — distintos encuadres, momentos o ambientaciones \
dentro de la misma idea, nunca la misma escena repetida con otras palabras.
- No menciones texto en pantalla, marcas, ni cambies la apariencia del personaje.
- Cada escena: 1-2 frases, directo, sin explicaciones extra ni comillas.

Responde ÚNICAMENTE con un JSON array de strings, sin texto adicional ni markdown.
Ejemplo de formato: ["escena 1", "escena 2", "escena 3"]"""


def generar_conceptos_imagen(idea, n=5, guia_estilo=None):
    """Como generar_prompts(), pero para IMAGEN fija en vez de video: sin lenguaje de
    cámara/animación. Se usa en el flujo imagen-primero, antes de saber cómo se va a
    animar cada escena elegida."""
    client = anthropic.Anthropic(api_key=_api_key())

    mensaje = f"Idea: {idea}\n\nDescribe {n} escenas distintas."
    if guia_estilo and guia_estilo.strip():
        mensaje += (
            f"\n\nGuía de estilo de la marca (respétala en cada escena, sin "
            f"mencionarla explícitamente):\n{guia_estilo.strip()}"
        )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=CONCEPTOS_IMAGEN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": mensaje}],
    )
    texto = "".join(block.text for block in resp.content if block.type == "text").strip()

    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.lower().startswith("json"):
            texto = texto[4:]
        texto = texto.strip()

    try:
        escenas = json.loads(texto)
    except json.JSONDecodeError:
        raise RuntimeError(f"No pude interpretar la respuesta del modelo como JSON: {texto[:300]}")

    if not isinstance(escenas, list) or not all(isinstance(e, str) for e in escenas):
        raise RuntimeError(f"Respuesta con formato inesperado: {texto[:300]}")

    return escenas[:n]


EVALUACION_MATRIZ_SYSTEM_PROMPT = """Eres un auditor de marca estricto. Te van a \
mostrar una imagen generada y una lista numerada de reglas (invariantes) de una \
marca. Para CADA regla, evalúa qué tan bien la imagen la cumple, de 0 a 100 \
(100 = la cumple perfecto, 0 = la viola por completo). Sé exigente — no le regales \
puntos a una regla solo porque el resto de la imagen se vea bien.

Responde ÚNICAMENTE con un JSON array, sin texto adicional ni markdown, un objeto \
por regla EN EL MISMO ORDEN en que te las dieron:
[{"puntaje": 85, "motivo": "una frase corta y concreta explicando el puntaje"}, ...]"""


def evaluar_contra_matriz(image_url, invariantes):
    """invariantes: lista de dicts {"id", "name", "rule"} del root.json de la marca.
    Le muestra la imagen ya generada a Claude y le pide puntuar el cumplimiento de
    cada invariante por separado. Devuelve la misma lista con 'puntaje' (0-100) y
    'motivo' agregados a cada invariante."""
    client = anthropic.Anthropic(api_key=_api_key())
    reglas_texto = "\n".join(
        f"{i + 1}. {inv.get('name')}: {inv.get('rule')}" for i, inv in enumerate(invariantes)
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=EVALUACION_MATRIZ_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": f"Reglas a evaluar, en orden:\n{reglas_texto}"},
                {"type": "image", "source": {"type": "url", "url": image_url}},
            ],
        }],
    )
    texto = "".join(block.text for block in resp.content if block.type == "text").strip()

    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.lower().startswith("json"):
            texto = texto[4:]
        texto = texto.strip()

    try:
        resultados = json.loads(texto)
    except json.JSONDecodeError:
        raise RuntimeError(f"No pude interpretar la evaluación como JSON: {texto[:300]}")

    if not isinstance(resultados, list) or len(resultados) != len(invariantes):
        raise RuntimeError(f"La evaluación no trajo un puntaje por cada regla: {texto[:300]}")

    return [
        {**inv, "puntaje": res.get("puntaje"), "motivo": res.get("motivo")}
        for inv, res in zip(invariantes, resultados)
    ]


ANALISIS_MARCA_PROMPT = """Estas son imágenes de referencia de la identidad visual de \
una marca. Escribe una guía de estilo breve (4-6 líneas) que describa: paleta de \
colores, tipo de iluminación, tono/mood general, y tipo de ambientación/escenarios \
típicos. Es para que un director creativo la use como referencia constante al escribir \
prompts de video — no menciones nombres propios, marcas, ni texto en pantalla. \
Responde solo con la guía, sin encabezados ni explicaciones adicionales."""


def analizar_marca(image_urls):
    """Le pide a Claude que mire hasta 5 imágenes de referencia de marca (URLs
    públicas) y devuelva una guía de estilo en texto para usar en cada prompt futuro."""
    urls = [u for u in image_urls if u][:5]
    if not urls:
        raise RuntimeError("No hay imágenes de referencia para analizar.")

    client = anthropic.Anthropic(api_key=_api_key())
    content = [{"type": "text", "text": ANALISIS_MARCA_PROMPT}]
    for url in urls:
        content.append({"type": "image", "source": {"type": "url", "url": url}})

    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()

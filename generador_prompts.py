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

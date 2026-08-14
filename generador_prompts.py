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


def generar_prompts(idea, n=5):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta ANTHROPIC_API_KEY en tu .env. Consíguela en console.anthropic.com "
            "(Settings > API Keys)."
        )

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Idea: {idea}\n\nEscribe {n} variantes de prompt."}],
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

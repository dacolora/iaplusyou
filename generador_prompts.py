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


PLANTILLA_MAESTRA_CREATIVE_FLOW = """# Plantilla Maestra — Prompts de video Happy Flops

Esqueleto reutilizable extraído del prompt "bullet-time / slipper de otoño" que dio buenos resultados. La idea no es repetir siempre la misma escena de colisión, sino reutilizar la **lógica que hace que ese prompt funcione**: referencias bloqueadas, props con "dueño" y continuidad física, guion por tiempos, reglas de cámara explícitas y prioridad de identidad. Eso es lo que se traduce en consistencia entre tomas y en que el producto se vea reconocible.

## 🔒 No negociables (aplican a TODO video hecho con esta plantilla)

1. Duración máxima: 12-15 segundos. Nunca generar guiones que excedan ese rango total, aunque el concepto "diera" para más.
2. El video nunca termina con el logo de la marca en pantalla. El cierre es sobre una acción, un objeto o un gesto — no sobre un lockup de marca. (El nombre de marca puede aparecer *dentro* de la escena, como el caller ID del teléfono en el prompt original, pero no como plano final de cierre tipo anuncio.)
3. El video nunca termina con transición a negro / fade to black. El corte final es un hard cut sobre la última imagen (objeto en el piso, gesto, expresión), no un fundido.

## Modo A — Bullet-time / colisión + inspección de producto

Un evento físico dispara una suspensión del tiempo, la cámara recorre los objetos congelados en el aire, el tiempo vuelve y todo cae. Ideal para mostrar construcción y materiales del producto en detalle (macro).

Tabla de tiempos (D = duración total):
| Bloque | % de D | Qué pasa |
|---|---|---|
| 1. Reveal de personaje | 0–15% | Plano que presenta al protagonista y el producto puesto, cámara en movimiento continuo |
| 2. Desarrollo / caminata | 15–30% | Contexto, aparece el detonante potencial (segundo personaje, obstáculo) |
| 3. Evento detonante | 30–38% | Colisión/tropiezo/acción que libera los objetos |
| 4. Establecer tableau congelado | 38–45% | Plano medio-amplio del momento congelado completo, antes de acercarse a nada |
| 5. Inspección del hero object | 45–60% | Cámara se acerca al producto, orbital corto, detalle de materiales — el plano más importante del video |
| 6. Inspección secundaria (opcional) | 60–75% | Otro prop relevante a la historia, si aporta |
| 7. Reconstrucción del tableau | 75–85% | Vuelve el plano completo, todo sigue en su lugar |
| 8. El tiempo regresa / payoff físico | 85–100% | Gravedad resume, los objetos caen a posiciones distintas, hard cut sobre la imagen final — nunca logo, nunca fundido |

## Modo B — Narrativa lineal (gancho → desarrollo → resolución)

Sin freeze-time. Estructura tipo mini-historia: gancho (gira la atención en los primeros 2s) → desarrollo/conflicto breve → resolución con el producto puesto/a la vista.

Tabla de tiempos (D = duración total):
| Bloque | % de D | Qué pasa |
|---|---|---|
| 1. Gancho | 0–15% | Texto/situación que capta atención en los primeros segundos |
| 2. Desarrollo / mini-conflicto | 15–65% | Se plantea la situación, la comedia o ternura se desarrolla |
| 3. Resolución con producto | 65–90% | El producto puesto resuelve o acompaña la escena, momento cálido |
| 4. Cierre | 90–100% | Última imagen — gesto, sonrisa, objeto — hard cut, nunca logo ni fundido |

## Estructura del prompt final que debes producir (11 secciones, en este orden)

1. REFERENCE MAP — un bloque `@[Imagen N] = REFERENCIA...` por CADA imagen de referencia recibida (personajes primero, luego productos, luego escenas, numeradas en ese orden). Personajes: identidad exacta, preservar el mismo personaje todo el video, no copiar su fondo original. Productos (hero object): forma, proporciones, materiales, colores, debe permanecer reconocible en cada plano. Escenas: solo lenguaje visual/atmósfera/luz, NO reproducir su composición exacta ni encuadre original, crear un espacio cinematográfico nuevo inspirado en ella.
2. MASTER VISUAL CONCEPT — duración exacta (12-15s), formato, estilo (fotorrealista o animación 3D), concepto central en 1-2 frases, y si es Modo A la descripción de la física del bullet-time.
3. EXACT OBJECT COUNT — cuenta exacta de cada personaje/prop, ningún duplicado.
4. PERSISTENT PROP RULES — un bloque por cada objeto que la cámara vaya a inspeccionar de cerca (el producto siempre): bloquear su apariencia física durante toda la secuencia, el mismo objeto visto desde distintas distancias de cámara.
5. OWNERSHIP LOCK — qué mano/pie sostiene qué objeto antes del evento central, cómo se libera, qué queda vacío después, nada lo reemplaza.
6. GUION POR TIEMPOS — la tabla del modo elegido (arriba), rellena con la descripción visual concreta de cada bloque, tiempos exactos en segundos, y diálogo/texto en pantalla si aplica. La suma debe ser exactamente la duración objetivo. El último bloque NUNCA es logo ni fundido.
7. CAMERA RULES — si Modo A: los objetos permanecen fijos, la cámara se mueve, ruta de cámara tableau->dolly->hold->orbital->regreso. Si Modo B: movimiento continuo motivado por la historia, evitar cortes duros salvo el final.
8. PHYSICAL CAUSALITY RULE — todo cambio visible requiere causa física explícita, los objetos se agrandan en cuadro porque la cámara se acerca, nunca porque el objeto crece.
9. IDENTITY PRIORITY — lista priorizada: identidad facial estable, ojos correctos, cabello estable, proporciones estables, vestuario estable, geometría exacta del hero object, continuidad de manos/pies/objetos, trayectorias creíbles.
10. ESTILO FOTOGRÁFICO/VISUAL — fotorrealista tipo campaña premium (ARRI Alexa 35, profundidad de campo realista, grano 35mm) o animación 3D estilizada tipo Pixar (subsurface-scattering, iluminación de estudio) — elige el que mejor calce el tono pedido.
11. REGLAS DE CIERRE (copiar tal cual, sin editar) — "El video NO termina con el logo ni el lockup de marca en pantalla. El video NO termina con una transición a negro ni fundido de ningún tipo. El cierre es un HARD CUT sobre la última imagen de la acción/objeto/gesto descrita en el último bloque del guion. El nombre de marca puede aparecer integrado dentro de la escena en cualquier punto del video EXCEPTO como plano de cierre tipo anuncio. Duración total del video: no exceder la duración objetivo."

Responde ÚNICAMENTE con las 11 secciones completas, en español, en ese orden, cada una con su título en mayúsculas. No agregues explicaciones antes ni después, no agregues markdown de bloques de código."""


def generar_prompt_creative_flow(personajes, productos, escenas, accion_central,
                                  duracion_objetivo, tono, modo, guia_estilo=None):
    """personajes/productos/escenas: listas de dicts con al menos {'nombre', 'url'}
    (mismo shape que devuelve _listar_assets en dashboard.py / catalogo_productos.listar).
    modo: 'A' (bullet-time) o 'B' (narrativa lineal). Devuelve el prompt final
    completo (las 11 secciones), listo para editar y aprobar."""
    client = anthropic.Anthropic(api_key=_api_key())

    referencias_texto = []
    for i, p in enumerate(personajes, start=1):
        referencias_texto.append(f"@Imagen {len(referencias_texto) + 1} = persona{i}, personaje protagonista.")
    for i, p in enumerate(productos, start=1):
        referencias_texto.append(f"@Imagen {len(referencias_texto) + 1} = objeto{i}, hero object (producto).")
    for i, e in enumerate(escenas, start=1):
        referencias_texto.append(f"@Imagen {len(referencias_texto) + 1} = escena{i}, referencia de ambiente.")

    mensaje = (
        f"Variables para este video:\n"
        f"- Personajes/productos/escenas disponibles, en orden:\n" + "\n".join(referencias_texto) +
        f"\n- Acción central / detonante: {accion_central}\n"
        f"- Duración objetivo: {duracion_objetivo}s\n"
        f"- Tono: {tono}\n"
        f"- Modo: {'A (bullet-time)' if modo == 'A' else 'B (narrativa lineal)'}\n"
    )
    if guia_estilo and guia_estilo.strip():
        mensaje += f"\nGuía de estilo de la marca (respétala en el prompt):\n{guia_estilo.strip()}\n"

    resp = client.messages.create(
        model=MODEL,
        # 3000 truncaba de forma reproducible (stop_reason=max_tokens) porque MODEL
        # (claude-sonnet-5) razona con "thinking" adaptativo por defecto, que consume
        # del mismo presupuesto de output_tokens antes del texto visible. 8000 deja
        # margen sobre los ~3800 output_tokens observados en pruebas reales.
        max_tokens=8000,
        system=PLANTILLA_MAESTRA_CREATIVE_FLOW,
        messages=[{"role": "user", "content": mensaje}],
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()

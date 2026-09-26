# sprints/sugerencias.py
"""
Personas (arquetipos de cliente) sugeridas por Claude a partir de la guía de
estilo y el catálogo del proyecto (spec §1.6). Nacen con origen
`sugerida_ia` y se editan o descartan desde la pestaña Sprints.
"""
import json

import catalogo_productos
import doctrina
import marca
import proyectos
from sprints import analisis

COLORES = ("#4d8dff", "#7c5cff", "#3ecf8e", "#e8b339", "#ff5f7a", "#22b8cf")
_CLAVES = ("nombre", "resumen", "descripcion", "edad_rango", "tono", "senales_visuales", "palabras_clave")

PROMPT_PERSONAS = """Eres estratega de marketing para la marca {marca}.
Guía de estilo de la marca:
{guia}

Productos del catálogo:
{productos}

Propón {cuantas} arquetipos de cliente (personas) distintos entre sí y realistas para esta marca en Latinoamérica. Responde SOLO con un objeto JSON con la forma {{"personas": [...]}}, donde cada persona tiene exactamente estas claves: "nombre" (2 o 3 palabras, ej. "Cliente Premium"), "resumen" (una línea de máximo 15 palabras), "descripcion" (quién es, qué le importa, qué le duele; 40 a 70 palabras), "edad_rango" (ej. "30-45"), "tono" (cómo hablarle, máximo 12 palabras), "senales_visuales" (lista de 3 a 5 escenarios, estilos de vida u objetos que la rodean), "palabras_clave" (lista de 3 a 6 palabras) y "conciencia" (objeto {{"nivel": uno de {niveles}, "detalle": una línea que lo justifica}}: qué tanto sabe esta persona de su problema, de las soluciones y de estos productos). Todo en español, sin texto fuera del JSON."""


def _parsear(texto):
    t = (texto or "").strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise analisis.AnalisisInvalido("Claude no devolvió JSON.")
    try:
        data = json.loads(t[ini:fin + 1])
    except ValueError as e:
        raise analisis.AnalisisInvalido(f"JSON inválido: {e}")
    personas = data.get("personas") if isinstance(data, dict) else None
    if not isinstance(personas, list):
        raise analisis.AnalisisInvalido("El JSON no trae la lista «personas».")
    limpias = []
    for p in personas:
        if not isinstance(p, dict) or any(k not in p for k in _CLAVES):
            continue
        # Solo se acepta si nombre es un string no vacío; si no, se descarta.
        nombre_raw = p.get("nombre")
        if not isinstance(nombre_raw, str):
            continue
        nombre = nombre_raw.strip()
        if not nombre:
            continue
        persona_limpia = {k: p[k] for k in _CLAVES}
        persona_limpia["nombre"] = nombre
        conc = p.get("conciencia") if isinstance(p.get("conciencia"), dict) else {}
        nivel = doctrina.normalizar_consciencia(conc.get("nivel"))
        if nivel:
            persona_limpia["conciencia"] = {"nivel": nivel, "detalle": " ".join(str(conc.get("detalle") or "").split())[:300]}
        limpias.append(persona_limpia)
    if not limpias:
        raise analisis.AnalisisInvalido("Ninguna persona venía completa.")
    return limpias


def sugerir_personas(cliente, cuantas=3):
    cuantas = max(1, int(cuantas or 3))
    guia = (marca.guia_efectiva(cliente) or "").strip() or "(sin guía de estilo todavía)"
    productos = catalogo_productos.listar(cliente, "producto")
    lista = "\n".join(f"- {p['nombre']}" + (f": {p['descripcion']}" if p.get("descripcion") else "") for p in productos)
    texto = PROMPT_PERSONAS.format(marca=proyectos.nombre_visible(cliente), guia=guia,
                                   productos=lista or "- (catálogo vacío)", cuantas=cuantas,
                                   niveles=", ".join(f'"{n}"' for n in doctrina.CONSCIENCIAS))
    personas = _parsear(analisis._llamar([{"type": "text", "text": texto}], max_tokens=6000,
                                         system=doctrina.bloque_system("investigar")))[:cuantas]
    for i, p in enumerate(personas):
        p["color"] = COLORES[i % len(COLORES)]
    return personas

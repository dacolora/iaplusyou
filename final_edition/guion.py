"""Capa 0 de Final Edition: guion estructurado con Claude.

`generar_guion_base` escribe el guion en el idioma base (5 bloques en el orden
hook -> problema -> producto -> prueba -> cta, con tiempos dentro de la
duración objetivo) y `localizar_guion` lo traduce/adapta a otro idioma y país
(moneda, unidades, tono) conservando los tiempos. Ambos validan con
`tipos.validar_guion` y, si hay errores, piden UNA corrección a Claude antes de
rendirse con `GuionInvalido`.

Forma del guion:
{"bloques": [{"rol", "texto_pantalla", "texto_voz", "inicio_s", "fin_s"}],
 "idioma", "pais", "moneda", "precio_texto"}
"""
import copy
import json
import os

import anthropic

from final_edition import tipos

# Mismo patrón que generador_prompts (replicado para no acoplar este módulo al
# generador de prompts de video).
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 1500
COSTO_LLAMADA_USD = 0.01

PALABRAS_POR_SEGUNDO = 2.5
MAX_PALABRAS_PANTALLA = 6


class GuionInvalido(Exception):
    """El guion sigue inválido después de pedir corrección a Claude."""
    def __init__(self, errores):
        self.errores = list(errores)
        super().__init__("Guion inválido: " + "; ".join(self.errores))


def _api_key():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta ANTHROPIC_API_KEY en tu .env. Consíguela en console.anthropic.com "
            "(Settings > API Keys)."
        )
    return api_key


# ---------------------------------------------------------------- tiempos ---

def _presupuesto_tiempos(duracion_s):
    """Tiempos sugeridos por rol: hook 0-2 s (o 15 % si el video es corto),
    problema hasta 35 %, producto hasta 65 %, prueba hasta 85 %, cta el resto."""
    fin_hook = min(2.0, duracion_s * 0.15)
    cortes = [0.0, fin_hook, duracion_s * 0.35, duracion_s * 0.65, duracion_s * 0.85, duracion_s]
    return [
        {"rol": rol, "inicio_s": round(cortes[i], 2), "fin_s": round(cortes[i + 1], 2)}
        for i, rol in enumerate(tipos.ROLES)
    ]


def _lineas_tiempos(duracion_s):
    lineas = []
    for t in _presupuesto_tiempos(duracion_s):
        palabras = int(round((t["fin_s"] - t["inicio_s"]) * PALABRAS_POR_SEGUNDO))
        lineas.append(
            f"- {t['rol']}: {t['inicio_s']} s a {t['fin_s']} s (≈ {palabras} palabras de voz)"
        )
    return "\n".join(lineas)


# ---------------------------------------------------------------- prompts ---

FORMATO_JSON = """Responde ÚNICAMENTE con un JSON estricto (sin texto adicional ni markdown) con esta forma:
{"bloques": [{"rol": "hook", "texto_pantalla": "...", "texto_voz": "...", "inicio_s": 0, "fin_s": 2}, ...],
 "idioma": "es", "pais": "CO", "moneda": null, "precio_texto": null}"""


def _system_generar(duracion_s, idioma_base, canal_optimo=None):
    ajuste_canal = ""
    if canal_optimo:
        if canal_optimo["canal"] == "google_ads":
            # Google Ads: búsqueda, usuario buscando activamente, breve y directo
            ajuste_canal = f"""
NOTA: Este video está optimizado para {{canal_optimo["canal"]}} (ROAS {{canal_optimo["roas"]}}x).
- Hook: muy rápido, captura urgencia o curiosidad inmediata (primeros 0.5 s).
- Tono: directo, agresivo, enfocado en el beneficio inmediato.
- Estructura: problema → solución → CTA (rápido).
- Duración sugerida: {{canal_optimo.get("duracion_sugerida_s", 6)}} segundos."""
        elif canal_optimo["canal"] == "tiktok":
            # TikTok: scroll social, emocional, trending
            ajuste_canal = f"""
NOTA: Este video está optimizado para {{canal_optimo["canal"]}} (ROAS {{canal_optimo["roas"]}}x).
- Hook: emocional, engagement visual fuerte (trending music, cambios).
- Tono: conversacional, emocional, relatable.
- Estructura: gancho emocional → problema identificable → producto como solución → CTA social.
- Duración sugerida: {{canal_optimo.get("duracion_sugerida_s", 9)}} segundos."""
        elif canal_optimo["canal"] == "instagram":
            # Instagram: estético, lifestyle
            ajuste_canal = f"""
NOTA: Este video está optimizado para {{canal_optimo["canal"]}} (ROAS {{canal_optimo["roas"]}}x).
- Hook: estético, visual fuerte (cuidado con el framing).
- Tono: aspiracional, lifestyle, inspirador.
- Estructura: muestra el resultado/lifestyle → problema → producto integrado → CTA sutil.
- Duración sugerida: {{canal_optimo.get("duracion_sugerida_s", 7)}} segundos."""
        elif canal_optimo["canal"] == "pinterest":
            # Pinterest: inspiración, soluciones prácticas
            ajuste_canal = f"""
NOTA: Este video está optimizado para {{canal_optimo["canal"]}} (ROAS {{canal_optimo["roas"]}}x).
- Hook: visual limpio, inspirador, con números/datos si aplica.
- Tono: práctico, informativo, inspirador.
- Estructura: resultado/beneficio → problema → producto como solución → CTA claro.
- Duración sugerida: {{canal_optimo.get("duracion_sugerida_s", 8)}} segundos."""

    return f"""Eres un guionista de videos cortos de venta (reels, TikTok, shorts). \
Escribes guiones en el idioma '{idioma_base}' para un video de {duracion_s:g} segundos.

El guion tiene EXACTAMENTE 5 bloques, en este orden y con estos roles:
1. hook: gancho que detiene el scroll.
2. problema: el dolor o situación que vive el cliente.
3. producto: presenta el producto como la solución.
4. prueba: evidencia (beneficio concreto, resultado, testimonio, demostración).
5. cta: llamado a la acción claro.

Tiempos sugeridos por bloque (inicio_s / fin_s en segundos; el último fin_s no puede pasar de {duracion_s:g}):
{_lineas_tiempos(duracion_s)}{ajuste_canal}

Reglas:
- texto_pantalla: máximo {MAX_PALABRAS_PANTALLA} palabras, impactante, para sobreimprimir en el video.
- texto_voz: frase natural para locución, ≈ {PALABRAS_POR_SEGUNDO} palabras por segundo de duración del bloque.
- Si hay un video referente, copia su ESTRUCTURA (ritmo, tipo de gancho, forma de presentar el producto), \
NUNCA su texto literal ni su marca.
- Los bloques no se solapan y sus tiempos van en orden creciente.
- Deja "moneda" y "precio_texto" en null; se rellenan al localizar.

{FORMATO_JSON}"""


def _formato_json_localizado(idioma, pais, moneda, precio_texto):
    """Mismo formato que FORMATO_JSON pero con el ejemplo de moneda/precio_texto
    que se espera realmente para esta localización (evita que Claude copie el
    `null` del ejemplo genérico cuando sí se le pidió una moneda concreta)."""
    moneda_ej = json.dumps(moneda, ensure_ascii=False)
    precio_ej = json.dumps(precio_texto, ensure_ascii=False)
    idioma_ej = json.dumps(idioma, ensure_ascii=False)
    pais_ej = json.dumps(pais, ensure_ascii=False)
    return (
        "Responde ÚNICAMENTE con un JSON estricto (sin texto adicional ni markdown) con esta forma:\n"
        '{"bloques": [{"rol": "hook", "texto_pantalla": "...", "texto_voz": "...", "inicio_s": 0, "fin_s": 2}, ...],\n'
        f' "idioma": {idioma_ej}, "pais": {pais_ej}, "moneda": {moneda_ej}, "precio_texto": {precio_ej}}}'
    )


def _system_localizar(idioma, pais, precio_texto=None):
    info = tipos.PAISES[pais]
    return f"""Eres un traductor y adaptador de guiones de videos cortos de venta. \
Recibes un guion en JSON y lo localizas al idioma '{idioma}' para {info['nombre']} ({pais}).

El guion tiene EXACTAMENTE 5 bloques con los roles hook, problema, producto, prueba y cta, en ese orden.

Reglas:
- Traduce y adapta texto_pantalla y texto_voz al idioma '{idioma}' con el tono, expresiones, unidades y \
referencias culturales de {info['nombre']}; que suene local, no traducido.
- Si precio_texto NO es null, y el guion menciona precio, usa exactamente el precio_texto indicado y la moneda \
{info['moneda']}.
- Si precio_texto ES null: NO menciones ningún precio ni cifra en texto_pantalla ni en texto_voz aunque el guion \
base sí lo mencione — reescribe esas partes sin precio (p.ej. usa el beneficio o la llamada a la acción en su \
lugar), y deja "precio_texto": null.
- Menciona envío/entrega solo como corresponde a {info['nombre']}.
- Conserva EXACTAMENTE los roles, el orden, inicio_s y fin_s de cada bloque.
- texto_pantalla: máximo {MAX_PALABRAS_PANTALLA} palabras. texto_voz: natural, largo similar al original.
- Devuelve "idioma": "{idioma}", "pais": "{pais}", "moneda": "{info['moneda']}".

{_formato_json_localizado(idioma, pais, info['moneda'], precio_texto)}"""


def _mensaje_generar(producto, referencia, enfoque, duracion_s, marca, cliente_hint, canal_optimo=None):
    """Devuelve el contenido del mensaje de usuario: un string si no hay
    referencia con frames, o una lista de bloques (texto + imágenes) para que
    Claude vea los fotogramas del referente, no solo su conteo."""
    partes = [f"Producto: {json.dumps(producto, ensure_ascii=False)}",
              f"Enfoque del video: {enfoque}",
              f"Duración objetivo: {duracion_s:g} segundos"]
    if canal_optimo:
        partes.append(f"Canal optimizado: {canal_optimo['canal']} (ROAS {canal_optimo['roas']:.1f}x)")
    if marca and str(marca).strip():
        partes.append(f"Guía de estilo de la marca (respétala en el tono):\n{str(marca).strip()}")
    if cliente_hint and str(cliente_hint).strip():
        partes.append(f"Contexto del cliente/audiencia: {str(cliente_hint).strip()}")

    frames = []
    if referencia:
        transcripcion = (referencia.get("transcripcion") or "").strip()
        frames = list(referencia.get("frames") or [])[:6]
        partes.append(
            "Video referente (copia su ESTRUCTURA, no su texto):\n"
            f"- Frames adjuntos: {len(frames)}\n"
            f"- Transcripción: {transcripcion or '(sin transcripción)'}"
        )
    partes.append("Escribe el guion.")
    texto = "\n\n".join(partes)

    if not frames:
        return texto

    contenido = [{"type": "text", "text": texto}]
    contenido += [{"type": "image", "source": {"type": "url", "url": url}} for url in frames]
    contenido.append({
        "type": "text",
        "text": "Escribe el guion copiando la ESTRUCTURA de estos fotogramas, nunca su texto.",
    })
    return contenido


def _mensaje_localizar(guion_base, idioma, pais, moneda, precio_texto):
    return (
        f"Localiza este guion al idioma '{idioma}' para el país {pais} (moneda {moneda}).\n"
        f"precio_texto a usar: {precio_texto if precio_texto is not None else '(sin precio)'}\n\n"
        f"Guion base:\n{json.dumps(guion_base, ensure_ascii=False)}"
    )


# ---------------------------------------------------------------- Claude ---

def _llamar(client, system, mensajes):
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=mensajes,
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()


def _parsear(texto):
    """Parseo tolerante: quita fences y, si hace falta, extrae del primer '{'
    al último '}'. Devuelve None si no hay un objeto JSON interpretable."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    for candidato in (t, _recortar_llaves(t)):
        if candidato is None:
            continue
        try:
            dato = json.loads(candidato)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(dato, dict):
            return dato
    return None


def _recortar_llaves(t):
    ini, fin = t.find("{"), t.rfind("}")
    if ini == -1 or fin == -1 or fin <= ini:
        return None
    return t[ini:fin + 1]


def _generar_con_correccion(system, mensaje_usuario, duracion_s, ajustar):
    """Llama a Claude, valida y, si hay errores, pide UNA corrección
    incluyendo la lista de errores. Devuelve (guion, costo_usd)."""
    client = anthropic.Anthropic(api_key=_api_key())
    mensajes = [{"role": "user", "content": mensaje_usuario}]
    costo = 0.0
    errores = []
    for intento in range(2):
        texto = _llamar(client, system, mensajes)
        costo += COSTO_LLAMADA_USD
        guion = _parsear(texto)
        if guion is None:
            errores = ["JSON inválido"]
        else:
            guion = ajustar(guion)
            errores = tipos.validar_guion(guion, duracion_s)
            if not errores:
                return guion, costo
        if intento == 0:
            mensajes = mensajes + [
                {"role": "assistant", "content": texto or "(respuesta vacía)"},
                {"role": "user", "content": (
                    "El guion tiene estos errores:\n- " + "\n- ".join(errores) +
                    "\n\nCorrígelos y responde de nuevo ÚNICAMENTE con el JSON completo del guion."
                )},
            ]
    raise GuionInvalido(errores)


# ---------------------------------------------------------------- API ---

def generar_guion_base(producto, referencia, enfoque, duracion_s, idioma_base, marca, cliente_hint, canal_optimo=None):
    """Guion en el idioma base. `producto`: {"nombre", "descripcion", "precio",
    "moneda", "beneficios"}; `referencia`: {"frames": [urls], "transcripcion"}
    o None; `canal_optimo`: {"canal": "google_ads|tiktok|...", "roas": 3.5, "duracion_sugerida_s": 6}
    o None. Devuelve (guion, costo_usd)."""
    duracion_s = float(duracion_s)
    pais_base = _pais_por_idioma(idioma_base)

    def ajustar(g):
        g.setdefault("idioma", idioma_base)
        g.setdefault("pais", pais_base)
        g.setdefault("moneda", None)
        g.setdefault("precio_texto", None)
        return g

    return _generar_con_correccion(
        _system_generar(duracion_s, idioma_base, canal_optimo=canal_optimo),
        _mensaje_generar(producto, referencia, enfoque, duracion_s, marca, cliente_hint, canal_optimo=canal_optimo),
        duracion_s, ajustar,
    )


def localizar_guion(guion_base, idioma, pais, precio):
    """Traduce/adapta el guion base a `idioma` y `pais`, fija moneda y
    precio_texto y conserva los tiempos. Mismo idioma y país: copia sin llamar
    a Claude (costo 0). Devuelve (guion, costo_usd)."""
    if pais not in tipos.PAISES:
        raise ValueError(f"País no soportado: {pais}. Opciones: {sorted(tipos.PAISES)}")
    moneda = tipos.PAISES[pais]["moneda"]
    precio_texto = tipos.formatear_precio(precio, pais) if precio is not None else None
    tiempos = [(b.get("inicio_s"), b.get("fin_s")) for b in guion_base.get("bloques") or []]
    duracion_s = float(tiempos[-1][1]) if tiempos and tiempos[-1][1] is not None else 0.0

    def ajustar(g):
        g["idioma"] = idioma
        g["pais"] = pais
        g["moneda"] = moneda
        g["precio_texto"] = precio_texto
        for bloque, (ini, fin) in zip(g.get("bloques") or [], tiempos):
            bloque["inicio_s"], bloque["fin_s"] = ini, fin
        return g

    if idioma == guion_base.get("idioma") and pais == guion_base.get("pais"):
        g = ajustar(copy.deepcopy(guion_base))
        errores = tipos.validar_guion(g, duracion_s)
        if errores:
            raise GuionInvalido(errores)
        return g, 0.0

    return _generar_con_correccion(
        _system_localizar(idioma, pais, precio_texto),
        _mensaje_localizar(guion_base, idioma, pais, moneda, precio_texto),
        duracion_s, ajustar,
    )


VARIANTES_GUION = {
    "hook": (
        "Reescribe el hook (bloque 1) y el CTA (último bloque) con un ángulo distinto; "
        "conserva tiempos, estructura y los demás bloques salvo ajustes mínimos de continuidad."
    ),
    "estructura": (
        "Cambia el ángulo narrativo del guion con TODOS los textos nuevos, pero mantén "
        "los 5 bloques con sus roles fijos y en el mismo orden (hook, problema, producto, "
        "prueba, cta) y con sus mismos tiempos: no agregues, quites ni reordenes bloques. "
        "Varía lo que pasa dentro de cada bloque: otro problema del que parte la historia, "
        "otra prueba (testimonio, dato, comparación...), otro ritmo de frases y otra "
        "sugerencia de música, y un CTA distinto; el producto es el mismo."
    ),
}


def _mensaje_variar(guion_base, variante_tipo, marca):
    partes = [
        "Guion base (en su idioma, con tiempos):\n" + json.dumps(guion_base, ensure_ascii=False),
        f"Variante pedida ({variante_tipo}): {VARIANTES_GUION[variante_tipo]}",
    ]
    if marca and str(marca).strip():
        partes.append(f"Guía de estilo de la marca (respétala en el tono):\n{str(marca).strip()}")
    partes.append("Escribe la variante del guion, en el mismo idioma que el guion base.")
    return "\n\n".join(partes)


def variar_guion(guion_base, variante_tipo, marca):
    """Variante del guion base (mismo idioma/país, mismos tiempos) con UNA
    llamada a Claude. `variante_tipo` ∈ VARIANTES_GUION ("hook": otro gancho y
    CTA; "estructura": otro ángulo en cada bloque, textos nuevos, mismos roles/orden/tiempos). Conserva
    `idioma`, `pais` y `precio_base` del base y no lo muta. Devuelve
    (guion, costo_usd)."""
    if variante_tipo not in VARIANTES_GUION:
        raise ValueError(
            f"Tipo de variante no soportado: {variante_tipo}. Opciones: {sorted(VARIANTES_GUION)}")
    base = copy.deepcopy(guion_base)
    idioma = base.get("idioma") or "es"
    pais = base.get("pais") or _pais_por_idioma(idioma)
    tiempos = [(b.get("inicio_s"), b.get("fin_s")) for b in base.get("bloques") or []]
    duracion_s = float(tiempos[-1][1]) if tiempos and tiempos[-1][1] is not None else 0.0

    def ajustar(g):
        g["idioma"] = idioma
        g["pais"] = pais
        g["moneda"] = base.get("moneda")
        g["precio_texto"] = base.get("precio_texto")
        if "precio_base" in base:
            g["precio_base"] = base["precio_base"]
        for bloque, (ini, fin) in zip(g.get("bloques") or [], tiempos):
            bloque["inicio_s"], bloque["fin_s"] = ini, fin
        return g

    return _generar_con_correccion(
        _system_generar(duracion_s, idioma),
        _mensaje_variar(base, variante_tipo, marca),
        duracion_s, ajustar,
    )


def _pais_por_idioma(idioma):
    """País por defecto para el guion base (solo para que valide): el primero
    de PAISES con ese idioma, o CO."""
    for codigo, info in tipos.PAISES.items():
        if info["idioma"] == idioma:
            return codigo
    return "CO"

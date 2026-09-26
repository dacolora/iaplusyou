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

import doctrina
from final_edition import tipos

# Mismo patrón que generador_prompts (replicado para no acoplar este módulo al
# generador de prompts de video).
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
# Sonnet 5 piensa antes de responder y eso sale del mismo tope; con la
# doctrina y el ángulo en la salida, 1500 se quedaba corto.
MAX_TOKENS = 4000
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

FORMATO_JSON_CON_ANGULO = """Responde ÚNICAMENTE con un JSON estricto (sin texto adicional ni markdown) con esta forma:
{"angulo": {"audiencia": "...", "consciencia": "...", "sofisticacion": 3, "deseo": "...", "promesa": "...", "mecanismo": null, "pruebas": [{"texto": "...", "fuente": "ficha"}], "lead": "...", "gancho": "...", "faltantes": []},
 "bloques": [{"rol": "hook", "texto_pantalla": "...", "texto_voz": "...", "inicio_s": 0, "fin_s": 2}, ...],
 "idioma": "es", "pais": "CO", "moneda": null, "precio_texto": null}"""

# Notas por canal (Triple Whale): (duración sugerida por defecto, reglas).
_CANALES = {
    "google_ads": (6, ("Hook: muy rápido, captura urgencia o curiosidad inmediata (primeros 0.5 s).",
                       "Tono: directo, enfocado en el beneficio inmediato.",
                       "Estructura: problema → solución → CTA (rápido).")),
    "tiktok": (9, ("Hook: emocional, con un cambio visual fuerte.",
                   "Tono: conversacional, emocional, cercano.",
                   "Estructura: gancho emocional → problema identificable → producto como solución → CTA social.")),
    "instagram": (7, ("Hook: estético, visual fuerte (cuidado con el encuadre).",
                      "Tono: aspiracional, estilo de vida, inspirador.",
                      "Estructura: muestra el resultado → problema → producto integrado → CTA sutil.")),
    "pinterest": (8, ("Hook: visual limpio e inspirador, con datos reales si los hay.",
                      "Tono: práctico, informativo, inspirador.",
                      "Estructura: resultado o beneficio → problema → producto como solución → CTA claro.")),
    "facebook": (8, ("Hook: visual y con texto en pantalla; se entiende sin sonido.",
                     "Tono: cercano, de conversación.",
                     "Estructura: gancho → problema reconocible → producto en uso → prueba → CTA con razón.")),
}


def _nota_canal(canal_optimo):
    """Antes esto era un f-string con llaves dobles y a Claude le llegaba
    literal «{canal_optimo["canal"]}»; además faltaba facebook."""
    if not canal_optimo or canal_optimo.get("canal") not in _CANALES:
        return ""
    duracion_defecto, reglas = _CANALES[canal_optimo["canal"]]
    roas = canal_optimo.get("roas")
    lineas = [f"NOTA: Este video está optimizado para {canal_optimo['canal']}"
              + (f" (ROAS {float(roas):.1f}x)." if roas is not None else ".")]
    lineas += [f"- {r}" for r in reglas]
    lineas.append(f"- Duración sugerida: {canal_optimo.get('duracion_sugerida_s', duracion_defecto)} segundos.")
    return "\n" + "\n".join(lineas)


def _reglas_generar(duracion_s, idioma_base, canal_optimo=None, pedir_angulo=False):
    """Instrucciones propias del guion (van al system después de la doctrina)."""
    regla_angulo = ""
    if pedir_angulo:
        regla_angulo = ("\n- Antes del guion decide el ángulo (clave \"angulo\") con los valores de la doctrina: "
                        "consciencia uno de " + ", ".join(doctrina.CONSCIENCIAS) + "; lead uno de "
                        + ", ".join(doctrina.LEADS) + "; sofisticacion de 1 a 5; pruebas con fuente ficha, "
                        "comentarios o demostracion. Después escribe el guion desde ese ángulo.")
    formato = FORMATO_JSON_CON_ANGULO if pedir_angulo else FORMATO_JSON
    return f"""Eres un guionista de videos cortos de venta (reels, TikTok, shorts). \
Escribes guiones en el idioma '{idioma_base}' para un video de {duracion_s:g} segundos.

El guion tiene EXACTAMENTE 5 bloques, en este orden y con estos roles:
1. hook: gancho que detiene el scroll.
2. problema: el dolor o situación que vive el cliente.
3. producto: presenta el producto como la solución.
4. prueba: evidencia (beneficio concreto, resultado, testimonio, demostración).
5. cta: llamado a la acción claro.

Tiempos sugeridos por bloque (inicio_s / fin_s en segundos; el último fin_s no puede pasar de {duracion_s:g}):
{_lineas_tiempos(duracion_s)}{_nota_canal(canal_optimo)}

Reglas:
- texto_pantalla: máximo {MAX_PALABRAS_PANTALLA} palabras, impactante, para sobreimprimir en el video.
- texto_voz: frase natural para locución, ≈ {PALABRAS_POR_SEGUNDO} palabras por segundo de duración del bloque.
- El hook es el gancho del ángulo (o una versión de él con el mismo sentido); el bloque prueba usa solo las pruebas \
del ángulo o datos reales del producto, y si no hay prueba real, una demostración que se vea en el video.
- Ninguna cifra, porcentaje, testimonio ni autoridad que no esté en los datos que recibes: se verifica y se devuelve \
a corregir.
- Si hay un video referente, copia su ESTRUCTURA (ritmo, tipo de gancho, forma de presentar el producto), \
NUNCA su texto literal ni su marca.
- Los bloques no se solapan y sus tiempos van en orden creciente.
- Deja "moneda" y "precio_texto" en null; se rellenan al localizar.{regla_angulo}

{formato}"""


def _system_generar(duracion_s, idioma_base, canal_optimo=None, con_angulo=False):
    """System del guion base: doctrina (con caché) + reglas. Sin ángulo en la
    sesión, la doctrina incluye la rebanada de ángulo y se le pide decidirlo."""
    rebanadas = ("guion", "gancho") if con_angulo else ("angulo", "guion", "gancho")
    return doctrina.bloque_system(*rebanadas, extra=_reglas_generar(duracion_s, idioma_base, canal_optimo,
                                                                     pedir_angulo=not con_angulo))


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


_ENFOQUE_GUION = {
    "producto": "Enfoque: el producto es el héroe; aparece pronto, en uso y con un resultado que se ve.",
    "persona": ("Enfoque: la persona es el vehículo de identificación; el video vende el rol que el producto le da "
                "y el producto entra en su vida."),
}


def _mensaje_generar(producto, referencia, enfoque, duracion_s, marca, cliente_hint, canal_optimo=None, angulo=None):
    """Devuelve el contenido del mensaje de usuario: un string si no hay
    referencia con frames, o una lista de bloques (texto + imágenes) para que
    Claude vea los fotogramas del referente, no solo su conteo."""
    partes = [f"Producto: {json.dumps(producto, ensure_ascii=False)}"]
    if _ENFOQUE_GUION.get(enfoque):
        partes.append(_ENFOQUE_GUION[enfoque])
    partes.append(f"Duración objetivo: {duracion_s:g} segundos")
    if canal_optimo:
        roas = canal_optimo.get("roas")
        partes.append(f"Canal optimizado: {canal_optimo['canal']}"
                      + (f" (ROAS {float(roas):.1f}x)" if roas is not None else ""))
    if marca and str(marca).strip():
        partes.append(f"Guía de estilo de la marca (respétala en el tono):\n{str(marca).strip()}")
    if cliente_hint and str(cliente_hint).strip():
        partes.append(f"Contexto del cliente/audiencia: {str(cliente_hint).strip()}")
    angulo_txt = doctrina.angulo_a_texto(angulo)
    if angulo_txt:
        partes.append(angulo_txt + "\nEscribe el guion DESDE este ángulo: mismo arranque, misma promesa, mismas "
                                   "pruebas; no lo reinventes.")
    else:
        partes.append("Primero decide el ángulo (clave \"angulo\" del JSON) aplicando la doctrina y después escribe "
                      "el guion desde él.")

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


REGLA_LOCALIZAR_ANGULO = ("\n\nDel ÁNGULO, si viene, conserva el arranque, la promesa, el mecanismo y las pruebas; "
                          "adapta idioma, expresiones, unidades y precio.")


def _mensaje_localizar(guion_base, idioma, pais, moneda, precio_texto, angulo=None):
    texto = (
        f"Localiza este guion al idioma '{idioma}' para el país {pais} (moneda {moneda}).\n"
        f"precio_texto a usar: {precio_texto if precio_texto is not None else '(sin precio)'}\n\n"
        f"Guion base:\n{json.dumps(guion_base, ensure_ascii=False)}"
    )
    angulo_txt = doctrina.angulo_a_texto(angulo)
    return texto + (f"\n\n{angulo_txt}" if angulo_txt else "")


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


def _datos_verificables(*partes):
    """Texto contra el que se verifican las cifras: exactamente lo que Claude
    recibió como datos (dicts como JSON)."""
    return "\n".join(p if isinstance(p, str) else json.dumps(p, ensure_ascii=False) for p in partes if p)


def _precio_verificable(precio, pais):
    """El precio como lo puede decir el guion, para sumarlo a los datos que se
    verifican: sus dígitos enteros (si es entero) y el formato del país
    (`tipos.formatear_precio`, el mismo que usa localizar). Sin esto un
    precio float llega a los datos como «89900.0» (→ 899000) y el precio
    real dicho en la voz («89.900 pesos», «$89.900», «89900») se tomaría
    por inventado. "" si no hay precio o no se puede leer."""
    if precio is None or isinstance(precio, bool):
        return ""
    try:
        valor = float(precio)
    except (TypeError, ValueError):
        return ""
    partes = [str(int(valor))] if valor.is_integer() else []
    try:
        partes.append(tipos.formatear_precio(valor, pais))
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    return " ".join(partes)


def _errores_de_cifras(guion, datos_texto):
    errores = []
    for b in guion.get("bloques") or []:
        texto = f"{b.get('texto_pantalla') or ''} {b.get('texto_voz') or ''}"
        for cifra in doctrina.verificar_cifras(texto, datos_texto):
            errores.append(f"La cifra «{cifra}» del bloque {b.get('rol')} no está en los datos: reescríbelo sin ella "
                           "o con el dato real.")
    return errores


def _generar_con_correccion(system, mensaje_usuario, duracion_s, ajustar, datos_texto=None, errores_extra=None):
    """Llama a Claude, valida y, si hay errores, pide UNA corrección
    incluyendo la lista de errores. Devuelve (guion, costo_usd).

    `errores_extra(guion) -> list[str]` son errores NO bloqueantes (p. ej. el
    ángulo que Claude debía decidir junto con el guion): se incluyen en la
    corrección igual que los bloqueantes, pero no impiden devolver el guion
    de la segunda pasada si esa ya no tiene errores bloqueantes (los extra
    que sigan quedan para quien llama). Si la segunda pasada SÍ rompe el
    guion (error bloqueante) pero la primera no tenía ninguno — solo extra —
    se devuelve la primera: lo ya pagado nunca se pierde por una corrección
    que empeoró las cosas."""
    client = anthropic.Anthropic(api_key=_api_key())
    mensajes = [{"role": "user", "content": mensaje_usuario}]
    costo = 0.0
    errores = []
    guion_sin_bloqueo = None
    for intento in range(2):
        texto = _llamar(client, system, mensajes)
        costo += COSTO_LLAMADA_USD
        guion = _parsear(texto)
        extra = []
        if guion is None:
            errores = ["JSON inválido"]
        else:
            guion = ajustar(guion)
            errores = tipos.validar_guion(guion, duracion_s)
            if datos_texto is not None:
                errores += _errores_de_cifras(guion, datos_texto)
            if errores_extra is not None:
                extra = list(errores_extra(guion) or [])
            if not errores:
                if not extra or intento == 1:
                    return guion, costo
                guion_sin_bloqueo = guion
        if intento == 0:
            todos = errores + extra
            mensajes = mensajes + [
                {"role": "assistant", "content": texto or "(respuesta vacía)"},
                {"role": "user", "content": (
                    "El guion tiene estos errores:\n- " + "\n- ".join(todos) +
                    "\n\nCorrígelos y responde de nuevo ÚNICAMENTE con el JSON completo del guion."
                )},
            ]
    if guion_sin_bloqueo is not None:
        return guion_sin_bloqueo, costo
    raise GuionInvalido(errores)


# ---------------------------------------------------------------- API ---

def generar_guion_base(producto, referencia, enfoque, duracion_s, idioma_base, marca, cliente_hint, canal_optimo=None,
                       angulo=None):
    """Guion en el idioma base. `producto`: {"nombre", "descripcion", "regla", "precio", "moneda", "url_compra",
    "tipo"}; `referencia`: {"frames": [urls], "transcripcion"} o None; `canal_optimo`: {"canal", "roas",
    "duracion_sugerida_s"} o None; `angulo`: el de la sesión (se escribe DESDE él) o None (se le pide a
    Claude, que reusa la MISMA vuelta de corrección del guion — spec §4.2 — y vuelve ya limpio y validado
    en la clave "angulo" del guion, `origen="guion"`). Devuelve (guion, costo_usd)."""
    duracion_s = float(duracion_s)
    pais_base = _pais_por_idioma(idioma_base)

    def ajustar(g):
        g.setdefault("idioma", idioma_base)
        g.setdefault("pais", pais_base)
        g.setdefault("moneda", None)
        g.setdefault("precio_texto", None)
        return g

    datos = _datos_verificables(producto, (referencia or {}).get("transcripcion"), cliente_hint, marca,
                                doctrina.texto_verificable(angulo),
                                _precio_verificable((producto or {}).get("precio"), pais_base))

    errores_extra = None
    if not angulo:
        # Se le pidió a Claude decidir el ángulo: sus errores (campo_faltante,
        # cifra_no_verificada...) entran a la MISMA corrección del guion en
        # vez de descubrirse recién después, sin poder pedir que los arregle.
        def errores_extra(g):
            crudo = g.get("angulo") if isinstance(g.get("angulo"), dict) else {}
            _, errores_angulo = doctrina.validar_angulo(crudo, datos)
            return [f"Ángulo: {e}" for e in errores_angulo]

    guion, costo = _generar_con_correccion(
        _system_generar(duracion_s, idioma_base, canal_optimo=canal_optimo, con_angulo=bool(angulo)),
        _mensaje_generar(producto, referencia, enfoque, duracion_s, marca, cliente_hint, canal_optimo=canal_optimo,
                         angulo=angulo),
        duracion_s, ajustar, datos, errores_extra=errores_extra,
    )
    if not angulo:
        crudo = guion.get("angulo") if isinstance(guion.get("angulo"), dict) else {}
        limpio, errores_angulo = doctrina.validar_angulo(crudo, datos)
        limpio["origen"] = "guion"
        guion["angulo"] = doctrina.anotar_errores(limpio, errores_angulo)
    return guion, costo


def localizar_guion(guion_base, idioma, pais, precio, angulo=None):
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

    # Sin verificación de cifras (E): el guion base ya se verificó al generarlo;
    # aquí Claude convierte moneda/unidades a propósito («60 cm» → «24 in»,
    # el precio a otra moneda) y esas cifras nuevas nunca están en los datos
    # de origen — verificarlas solo forzaría una corrección pagada de más o
    # un GuionInvalido que bloquearía la final de todo un país.
    return _generar_con_correccion(
        doctrina.bloque_system(extra=_system_localizar(idioma, pais, precio_texto) + REGLA_LOCALIZAR_ANGULO),
        _mensaje_localizar(guion_base, idioma, pais, moneda, precio_texto, angulo=angulo),
        duracion_s, ajustar,
    )


VARIANTES_GUION = {
    "hook": (
        "Cambia SOLO el hook (bloque 1): elige otro arranque compatible con la consciencia del ÁNGULO (u otro "
        "patrón de gancho si ese arranque es el único recomendado) y reescribe el hook con él. Conserva la "
        "promesa, el mecanismo, las pruebas, el CTA (último bloque) y los demás bloques salvo ajustes mínimos "
        "de continuidad: mismo mensaje, otro gancho."
    ),
    "estructura": (
        "Mantén los 5 bloques con sus roles fijos y en el mismo orden (hook, problema, producto, prueba, cta) y con "
        "sus mismos tiempos: no agregues, quites ni reordenes bloques. Cambia cómo se dramatiza la promesa dentro de "
        "cada bloque con otra técnica de intensificación (producto en acción, el espectador dentro de la escena, "
        "cómo probarlo uno mismo, gente reaccionando, comparación con lo que usa hoy), con textos nuevos, otra "
        "sugerencia de música y un CTA distinto; conserva la promesa, el mecanismo y las pruebas; el producto es el "
        "mismo."
    ),
}

REGLA_VARIANTE = ("\n\nAdemás del guion, devuelve la clave \"angulo_variante\": {\"lead\": \"<arranque que usaste>\", "
                  "\"gancho\": \"<el gancho nuevo, máximo 12 palabras>\"}. En esta variante el gancho del ÁNGULO se "
                  "reemplaza por uno nuevo: no repitas ni parafrasees el gancho anterior.")


def _mensaje_variar(guion_base, variante_tipo, marca, angulo=None):
    partes = [
        "Guion base (en su idioma, con tiempos):\n" + json.dumps(guion_base, ensure_ascii=False),
        f"Variante pedida ({variante_tipo}): {VARIANTES_GUION[variante_tipo]}",
    ]
    angulo_txt = doctrina.angulo_a_texto(angulo)
    if angulo_txt:
        partes.append(angulo_txt)
    if marca and str(marca).strip():
        partes.append(f"Guía de estilo de la marca (respétala en el tono):\n{str(marca).strip()}")
    partes.append("Escribe la variante del guion, en el mismo idioma que el guion base.")
    return "\n\n".join(partes)


def variar_guion(guion_base, variante_tipo, marca, angulo=None):
    """Variante del guion base (mismo idioma/país, mismos tiempos) con UNA
    llamada a Claude. `variante_tipo` ∈ VARIANTES_GUION ("hook": otro arranque
    y gancho, mismo mensaje; "estructura": otra forma de dramatizar la misma
    promesa en cada bloque). Conserva `idioma`, `pais` y `precio_base` del base
    y no lo muta. El guion devuelto trae `angulo_variante: {lead, gancho}`.
    Devuelve (guion, costo_usd)."""
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
        av = g.get("angulo_variante") if isinstance(g.get("angulo_variante"), dict) else {}
        g["angulo_variante"] = {"lead": av.get("lead") if av.get("lead") in doctrina.LEADS else None,
                                "gancho": " ".join(str(av.get("gancho") or "").split())[:200]}
        return g

    return _generar_con_correccion(
        doctrina.bloque_system("gancho", extra=_reglas_generar(duracion_s, idioma) + REGLA_VARIANTE),
        _mensaje_variar(base, variante_tipo, marca, angulo=angulo),
        duracion_s, ajustar, _datos_verificables(base, doctrina.texto_verificable(angulo),
                                                 _precio_verificable(base.get("precio_base"), pais)),
    )


def _pais_por_idioma(idioma):
    """País por defecto para el guion base (solo para que valide): el primero
    de PAISES con ese idioma, o CO."""
    for codigo, info in tipos.PAISES.items():
        if info["idioma"] == idioma:
            return codigo
    return "CO"

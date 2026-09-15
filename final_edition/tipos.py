"""Tipos y constantes compartidas de Final Edition: roles del guion, países
soportados (idioma/moneda/símbolo por defecto), estilos de música, validación
del guion localizado y rutas absolutas a las fuentes TTF usadas por la capa de
texto en pantalla (Pillow).
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROLES = ("hook", "problema", "producto", "prueba", "cta")

# país -> {"nombre", "idioma" (ISO-639-1), "moneda" (ISO-4217), "simbolo"}
PAISES = {
    "CO": {"nombre": "Colombia", "idioma": "es", "moneda": "COP", "simbolo": "$"},
    "MX": {"nombre": "México", "idioma": "es", "moneda": "MXN", "simbolo": "$"},
    "US": {"nombre": "Estados Unidos", "idioma": "en", "moneda": "USD", "simbolo": "$"},
    "ES": {"nombre": "España", "idioma": "es", "moneda": "EUR", "simbolo": "€"},
    "BR": {"nombre": "Brasil", "idioma": "pt", "moneda": "BRL", "simbolo": "R$"},
    "AR": {"nombre": "Argentina", "idioma": "es", "moneda": "ARS", "simbolo": "$"},
    "CL": {"nombre": "Chile", "idioma": "es", "moneda": "CLP", "simbolo": "$"},
    "PE": {"nombre": "Perú", "idioma": "es", "moneda": "PEN", "simbolo": "S/"},
}

# Prompts en inglés (Stable Audio funciona mejor con prompts en inglés).
ESTILOS_MUSICA = {
    "energetico": "upbeat energetic electronic pop, driving beat, bright synths, motivational, commercial",
    "calmado": "calm ambient acoustic, soft piano and strings, gentle, warm, soothing background music",
    "lujo": "elegant luxury cinematic, minimal piano and strings, sophisticated, slow build, premium brand feel",
    "urbano": "modern urban hip hop beat, punchy bass, trendy, confident, street style commercial music",
}

# Países cuya moneda no se muestra con decimales (COP, ARS, CLP).
_PAISES_SIN_DECIMALES = ("CO", "AR", "CL")

FUENTES = {
    "titulo": os.path.join(BASE_DIR, "static/fonts/SpaceGrotesk-Bold.ttf"),
    "texto": os.path.join(BASE_DIR, "static/fonts/Inter-Bold.ttf"),
    "sub": os.path.join(BASE_DIR, "static/fonts/Inter-SemiBold.ttf"),
}


def formatear_precio(valor, pais):
    """Formatea `valor` según la convención de precios del país: separador de
    miles/decimales correcto, símbolo en la posición y con el espaciado que
    usa cada mercado (p.ej. "$ 89.900" en CO, "$89.90" en US, "89,90 €" en ES,
    "R$ 89,90" en BR)."""
    info = PAISES[pais]
    simbolo = info["simbolo"]

    if pais in _PAISES_SIN_DECIMALES:
        entero = int(round(valor))
        numero = f"{entero:,}".replace(",", ".")
        return f"{simbolo} {numero}"

    # Miles "." y decimal "," (BR, ES) vs. miles "," y decimal "." (US, MX, PE).
    numero = f"{valor:,.2f}"
    if pais in ("BR", "ES"):
        numero = numero.replace(",", "\x00").replace(".", ",").replace("\x00", ".")

    if pais == "BR":
        return f"{simbolo} {numero}"
    if pais == "ES":
        return f"{numero} {simbolo}"
    return f"{simbolo}{numero}"


def validar_guion(guion, duracion_s):
    """Valida la forma del guion localizado: 5 bloques en el orden de ROLES,
    tiempos crecientes y sin solapes, último fin_s dentro de la duración
    objetivo (± 0.05 s), textos no vacíos e idioma/pais presentes. Devuelve
    una lista de errores en español (vacía si el guion es válido)."""
    errores = []
    bloques = guion.get("bloques") or []

    if len(bloques) != len(ROLES):
        errores.append(f"El guion debe tener {len(ROLES)} bloques y tiene {len(bloques)}.")

    for i, rol_esperado in enumerate(ROLES):
        if i >= len(bloques):
            break
        rol_real = bloques[i].get("rol")
        if rol_real != rol_esperado:
            errores.append(
                f"El bloque {i + 1} debe tener rol '{rol_esperado}' y tiene '{rol_real}'."
            )

    for i, bloque in enumerate(bloques):
        if not (bloque.get("texto_pantalla") or "").strip():
            errores.append(f"El bloque {i + 1} no tiene texto_pantalla.")
        if not (bloque.get("texto_voz") or "").strip():
            errores.append(f"El bloque {i + 1} no tiene texto_voz.")

    fin_anterior = None
    for i, bloque in enumerate(bloques):
        inicio = bloque.get("inicio_s")
        fin = bloque.get("fin_s")
        if inicio is None or fin is None or not (inicio < fin):
            errores.append(f"El bloque {i + 1} tiene tiempos inválidos (inicio_s debe ser menor que fin_s).")
            continue
        if fin_anterior is not None and inicio < fin_anterior - 1e-6:
            errores.append(f"El bloque {i + 1} se solapa con el bloque anterior.")
        fin_anterior = fin

    if bloques:
        fin_ultimo = bloques[-1].get("fin_s")
        if fin_ultimo is not None and fin_ultimo > duracion_s + 0.05:
            errores.append(
                f"La duración del guion ({fin_ultimo}s) supera la duración objetivo ({duracion_s}s)."
            )

    if not guion.get("idioma"):
        errores.append("Falta el idioma del guion.")
    if not guion.get("pais"):
        errores.append("Falta el país del guion.")

    return errores

"""Tipos y constantes compartidas de Final Edition: roles del guion, países
soportados (idioma/moneda/símbolo por defecto), estilos de música, validación
del guion localizado y rutas absolutas a las fuentes TTF usadas por la capa de
texto en pantalla (Pillow).
"""
import os

from flask_babel import gettext

from idiomas import N_

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROLES = ("hook", "problema", "producto", "prueba", "cta")

# Etiqueta que ve la persona por cada capa de una final y por cada tipo de
# variante (el `detalle` del gasto, el nombre de la edición de una variante).
# Mismos msgid que la macro `etiqueta_fe` de `_final_macros.html`; la clave
# guardada no cambia. Se traducen donde se usan (`idiomas.traducir(valor)`).
ETIQUETAS_CAPA = {"guion": N_("guion"), "cortes": N_("cortes"), "voz": N_("voz"), "musica": N_("musica"),
                  "texto": N_("texto"), "render": N_("render"), "sonido": N_("sonido"), "mezcla": N_("mezcla")}
ETIQUETAS_VARIANTE = {"hook": N_("hook"), "estructura": N_("estructura")}

# país -> {"nombre", "idioma" (ISO-639-1), "moneda" (ISO-4217), "simbolo", "bandera" (emoji para la UI)}
# "nombre" es una constante de módulo que se muestra: marcada con N_, se
# traduce donde se usa ({{ valor|traducir }} / gettext(valor)).
PAISES = {
    "CO": {"nombre": N_("Colombia"), "idioma": "es", "moneda": "COP", "simbolo": "$", "bandera": "🇨🇴"},
    "MX": {"nombre": N_("México"), "idioma": "es", "moneda": "MXN", "simbolo": "$", "bandera": "🇲🇽"},
    "US": {"nombre": N_("Estados Unidos"), "idioma": "en", "moneda": "USD", "simbolo": "$", "bandera": "🇺🇸"},
    "ES": {"nombre": N_("España"), "idioma": "es", "moneda": "EUR", "simbolo": "€", "bandera": "🇪🇸"},
    "BR": {"nombre": N_("Brasil"), "idioma": "pt", "moneda": "BRL", "simbolo": "R$", "bandera": "🇧🇷"},
    "AR": {"nombre": N_("Argentina"), "idioma": "es", "moneda": "ARS", "simbolo": "$", "bandera": "🇦🇷"},
    "CL": {"nombre": N_("Chile"), "idioma": "es", "moneda": "CLP", "simbolo": "$", "bandera": "🇨🇱"},
    "PE": {"nombre": N_("Perú"), "idioma": "es", "moneda": "PEN", "simbolo": "S/", "bandera": "🇵🇪"},
}

# Prompts en inglés (Stable Audio funciona mejor con prompts en inglés): NUNCA
# se traducen, van tal cual al proveedor.
ESTILOS_MUSICA = {
    "energetico": "upbeat energetic electronic pop, driving beat, bright synths, motivational, commercial",
    "calmado": "calm ambient acoustic, soft piano and strings, gentle, warm, soothing background music",
    "lujo": "elegant luxury cinematic, minimal piano and strings, sophisticated, slow build, premium brand feel",
    "urbano": "modern urban hip hop beat, punchy bass, trendy, confident, street style commercial music",
}

# Etiqueta que ve la persona por cada estilo (la clave de ESTILOS_MUSICA es el
# `value` del <select> y no cambia); marcada con N_, se traduce con
# {{ valor|traducir }} donde se muestra (Configuración > Generación).
NOMBRES_ESTILOS_MUSICA = {
    "energetico": N_("energetico"),
    "calmado": N_("calmado"),
    "lujo": N_("lujo"),
    "urbano": N_("urbano"),
}

# Misma clave, etiqueta legible (Crear > Desde referencias: selects "Música al
# crear" y "Producir finales", que antes mostraban la clave cruda). Constante
# aparte de NOMBRES_ESTILOS_MUSICA de arriba para no tocar el español ya
# mostrado en Configuración > Generación (msgid distinto).
NOMBRES_ESTILO_MUSICA = {
    "energetico": N_("Energético"),
    "calmado": N_("Calmado"),
    "lujo": N_("Lujo"),
    "urbano": N_("Urbano"),
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
    la lista de errores en el idioma activo — en una ruta, el de quien mira;
    en el worker, el del proyecto — (vacía si el guion es válido)."""
    errores = []
    bloques = guion.get("bloques") or []

    if len(bloques) != len(ROLES):
        errores.append(gettext("El guion debe tener %(n)s bloques y tiene %(tiene)s.", n=len(ROLES), tiene=len(bloques)))

    for i, rol_esperado in enumerate(ROLES):
        if i >= len(bloques):
            break
        rol_real = bloques[i].get("rol")
        if rol_real != rol_esperado:
            errores.append(gettext("El bloque %(n)s debe tener rol '%(esperado)s' y tiene '%(real)s'.",
                                   n=i + 1, esperado=rol_esperado, real=rol_real))

    for i, bloque in enumerate(bloques):
        if not (bloque.get("texto_pantalla") or "").strip():
            errores.append(gettext("El bloque %(n)s no tiene texto_pantalla.", n=i + 1))
        if not (bloque.get("texto_voz") or "").strip():
            errores.append(gettext("El bloque %(n)s no tiene texto_voz.", n=i + 1))

    fin_anterior = None
    for i, bloque in enumerate(bloques):
        inicio = bloque.get("inicio_s")
        fin = bloque.get("fin_s")
        if inicio is None or fin is None or not (inicio < fin):
            errores.append(gettext("El bloque %(n)s tiene tiempos inválidos (inicio_s debe ser menor que fin_s).",
                                   n=i + 1))
            continue
        if fin_anterior is not None and inicio < fin_anterior - 1e-6:
            errores.append(gettext("El bloque %(n)s se solapa con el bloque anterior.", n=i + 1))
        fin_anterior = fin

    if bloques:
        fin_ultimo = bloques[-1].get("fin_s")
        if fin_ultimo is not None and fin_ultimo > duracion_s + 0.05:
            errores.append(gettext("La duración del guion (%(fin)ss) supera la duración objetivo (%(objetivo)ss).",
                                   fin=fin_ultimo, objetivo=duracion_s))

    if not guion.get("idioma"):
        errores.append(gettext("Falta el idioma del guion."))
    if not guion.get("pais"):
        errores.append(gettext("Falta el país del guion."))

    return errores

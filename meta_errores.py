"""Errores de Meta en palabras de persona.

`meta_ads.auth.llamar` falla con «Meta Ads (<edge>) respondió <status>: <JSON de la
Graph API cortado a 500 caracteres>». Ese texto queda guardado en el experimento (y
en su evento, completo), pero a la persona se le muestra `explicar(texto)`: qué pasó y
qué hacer. Se usa al lanzar (`lanzador.traducir_error_meta`) y al mostrar (alerta del
Tablero y tarjeta del experimento, filtro `error_meta`), así que los errores guardados
antes de esta traducción también se leen bien.

El JSON puede llegar cortado: los campos se sacan con expresiones regulares, no con
`json.loads`. Lo que no es un error crudo de Meta (nuestros propios mensajes) pasa tal cual.
"""
import json
import re

from flask_babel import gettext

_CRUDO = re.compile(r"Meta Ads \([^)]*\) respondió \d+:")


def es_crudo(texto):
    """True si el texto es la respuesta cruda de la Graph API (o la contiene)."""
    texto = str(texto or "")
    return bool(_CRUDO.search(texto)) or '"error":{' in texto


def _numero(texto, campo):
    m = re.search(r'"%s"\s*:\s*(\d+)' % campo, texto)
    return int(m.group(1)) if m else None


def _cadena(texto, campo):
    """Valor de un campo de texto del JSON, con sus \\uXXXX resueltos; None si no está
    completo (el JSON puede venir cortado a la mitad de ese campo)."""
    m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % campo, texto)
    if not m:
        return None
    try:
        return json.loads('"' + m.group(1) + '"').strip() or None
    except ValueError:
        return m.group(1).strip() or None


# Códigos de la Graph API con remedio conocido (developers.facebook.com › Graph API › errores).
_PERMISOS = {10, 200, 294}
_LIMITE = {4, 17, 32, 613, 80004}
_TEMPORAL = {1, 2}


def explicar(texto, modo="propia"):
    """Qué pasó y qué hacer, en el idioma activo. `modo` es la forma de la conexión
    con Meta del proyecto («propia» o «agencia»): cambia a quién le toca arreglarlo."""
    texto = str(texto or "")
    # La app en modo Desarrollo se reconoce también en el mensaje ya explicado que el
    # lanzador guardó (con «1885183» adentro), para volver a decirlo en el idioma de quien mira.
    app_en_desarrollo = "1885183" in texto or "modo de desarrollo" in texto or "development mode" in texto
    if not texto or not (es_crudo(texto) or app_en_desarrollo):
        return texto
    codigo, subcodigo = _numero(texto, "code"), _numero(texto, "error_subcode")
    if app_en_desarrollo:
        if modo == "agencia":
            return gettext(
                "Meta rechazó el anuncio porque la app de Meta de Creatv (modo agencia) está en modo Desarrollo "
                "(subcódigo 1885183). Avísale al admin de Creatv para que la pase a modo Live y luego reintenta el "
                "lanzamiento: la campaña, los conjuntos y los videos ya creados se reutilizan, no se duplica nada.")
        return gettext(
            "Meta rechazó el anuncio porque la app de Meta de este proyecto está en modo Desarrollo (subcódigo "
            "1885183). Pásala a modo Live en developers.facebook.com › Mis apps › tu app › «Modo de la app» y "
            "reintenta el lanzamiento: la campaña, los conjuntos y los videos ya creados se reutilizan, no se "
            "duplica nada.")
    if codigo == 190:
        return gettext("La conexión con Meta venció o se retiró: vuelve a conectar Meta en Experimentos y "
                       "reintenta.")
    if codigo in _PERMISOS:
        return gettext("A la conexión con Meta le falta un permiso para esto: vuelve a conectar Meta en "
                       "Experimentos aceptando todos los permisos que pide, y reintenta.")
    if codigo in _LIMITE:
        return gettext("Meta está frenando las llamadas por un rato (límite de uso): reintenta en unos minutos.")
    if codigo == 368:
        return gettext("Meta bloqueó esta acción por un tiempo por sus políticas: revisa los avisos en tu "
                       "Business Suite antes de reintentar.")
    if codigo in _TEMPORAL:
        return gettext("Meta tuvo una falla temporal: reintenta en unos minutos.")
    titulo, detalle = _cadena(texto, "error_user_title"), _cadena(texto, "error_user_msg")
    if titulo or detalle:
        palabras = detalle if (detalle and titulo and detalle.startswith(titulo)) else " ".join(
            x.rstrip(".") + "." for x in (titulo, detalle) if x)
        return gettext("Meta rechazó el pedido: %(motivo)s", motivo=palabras)
    mensaje = _cadena(texto, "message")
    if codigo is not None:
        return gettext("Meta rechazó el pedido (código %(codigo)s%(sub)s)%(mensaje)s.",
                       codigo=codigo, sub=f"/{subcodigo}" if subcodigo else "",
                       mensaje=f": {mensaje}" if mensaje else "")
    return gettext("Meta rechazó el pedido. Mira el detalle técnico o reintenta en unos minutos.")

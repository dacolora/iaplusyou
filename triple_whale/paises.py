"""Países de las tiendas de Triple Whale (spec 2026-10-08 §4.2).

Puro: sin Flask ni red. Lo usan la migración 0032 (para adivinar el país de la
tienda ya conectada), la ruta de conexión y las pantallas. Los nombres salen de
Babel (CLDR), así que cualquier territorio de dos letras vale, no solo los de
Final edition."""
import re
import unicodedata

from babel import Locale
from babel.core import UnknownLocaleError

# Idiomas en que una tienda puede nombrar su país: inglés, español y la lengua local.
_IDIOMAS_NOMBRE = ("en", "es", "nb", "sv", "da", "fi", "de", "fr", "it", "nl", "pt", "pl")
# No son países: unión europea, eurozona, ONU, desconocido, resto de Oceanía y los
# pseudo-idiomas de prueba de CLDR.
_NO_PAISES = frozenset({"EU", "EZ", "UN", "ZZ", "QO", "XA", "XB"})
_MAX_UNION = 4          # trozos contiguos que se unen para «new-zealand»

_mapa = None            # {nombre normalizado: código}, se construye una vez
_validos = None         # códigos de país conocidos


def _territorios(locale):
    try:
        t = Locale.parse(str(locale or "en").replace("-", "_")).territories
    except (UnknownLocaleError, ValueError):
        t = Locale("en").territories
    return {c: n for c, n in t.items() if len(c) == 2 and c.isalpha() and c not in _NO_PAISES}


def _norm(texto):
    """Sin acentos ni mayúsculas, solo [a-z]."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z]", "", t)


def _construir():
    global _mapa, _validos
    if _mapa is not None:
        return
    mapa, validos = {}, set(_territorios("en"))
    for loc in _IDIOMAS_NOMBRE:
        for codigo, nombre in _territorios(loc).items():
            clave = _norm(nombre)
            if len(clave) >= 4:
                mapa.setdefault(clave, codigo)
    _mapa, _validos = mapa, validos


def _subdominio(dominio):
    """Misma limpieza que `triple_whale.normalizar_dominio` (sin importarlo: este módulo
    no depende del cliente HTTP), más quitar «.myshopify.com»."""
    t = (dominio or "").strip().lower()
    t = re.sub(r"^[a-z]+://", "", t)
    t = t.split("/")[0].split("?")[0].split("#")[0].strip(".")
    if t.startswith("www."):
        t = t[4:]
    if t.endswith(".myshopify.com"):
        t = t[: -len(".myshopify.com")]
    return t


def adivinar_pais(dominio):
    """«happyflops-norge.myshopify.com» -> «NO»; None si el dominio no da pista."""
    _construir()
    trozos = [p for p in re.split(r"[-_.]", _subdominio(dominio)) if p]
    if not trozos:
        return None
    for largo in range(min(_MAX_UNION, len(trozos)), 0, -1):
        for i in range(len(trozos) - largo + 1):
            codigo = _mapa.get(_norm("".join(trozos[i:i + largo])))
            if codigo:
                return codigo
    ultimo = trozos[-1].upper()
    if len(ultimo) == 2 and ultimo.isalpha() and ultimo in _validos:
        return ultimo
    return None


def es_pais(codigo):
    """True si `codigo` (con o sin mayúsculas) es un país del selector: lo que llega de un
    formulario se valida con esto antes de guardarlo."""
    _construir()
    return (codigo or "").strip().upper() in _validos


def bandera(codigo):
    """«NO» -> la bandera (dos indicadores regionales)."""
    c = (codigo or "").upper()
    if len(c) != 2 or not c.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - 65) for ch in c)


def nombre_pais(codigo, locale="en"):
    c = (codigo or "").upper()
    return _territorios(locale).get(c) or c


def paises_opciones(locale="en"):
    """[(«NO», «🇳🇴 Noruega»)] de todos los territorios, ordenados por nombre sin acentos."""
    filas = sorted(_territorios(locale).items(), key=lambda kv: (_norm(kv[1]), kv[0]))
    return [(c, f"{bandera(c)} {n}") for c, n in filas]

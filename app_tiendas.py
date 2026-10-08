"""Tiendas de apps (App Store / Google Play) para el objetivo «Instalaciones de la
app»: reconocer de qué plataforma es una URL y validar el par que escribe la
persona. Funciones puras, sin red ni disco."""
from urllib.parse import urlparse

from flask_babel import gettext

PLATAFORMAS = ("ios", "android")
OS_META = {"ios": "iOS", "android": "Android"}
_HOSTS = {"apps.apple.com": "ios", "itunes.apple.com": "ios", "play.google.com": "android"}


def plataforma_de_url(url):
    """'ios' / 'android' si es una URL https de la tienda; None en cualquier otro caso."""
    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return None
    if u.scheme != "https":
        return None
    return _HOSTS.get((u.hostname or "").lower())


def validar_urls(ios_url, android_url):
    """{plataforma: url} solo con las presentes. ValueError (en el idioma de quien
    mira) si no hay ninguna o si una URL está en el campo de la otra tienda."""
    ios_url, android_url = (ios_url or "").strip(), (android_url or "").strip()
    if not ios_url and not android_url:
        raise ValueError(gettext("Pon al menos una URL de tienda: App Store (iOS) o Google Play (Android)."))
    if ios_url and plataforma_de_url(ios_url) != "ios":
        raise ValueError(gettext("La URL de iOS tiene que ser un enlace https de la App Store (apps.apple.com)."))
    if android_url and plataforma_de_url(android_url) != "android":
        raise ValueError(gettext("La URL de Android tiene que ser un enlace https de Google Play (play.google.com)."))
    return {p: u for p, u in (("ios", ios_url), ("android", android_url)) if u}


def parte_presupuesto(presupuesto_dia, n_plataformas):
    """El presupuesto diario de un país se reparte en partes iguales entre sus plataformas."""
    return float(presupuesto_dia) / max(1, int(n_plataformas))

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
    url = (url or "").strip()
    # Un navegador y urlparse no siempre leen el mismo host: con «\» o un
    # «usuario@» delante, `https://evil.com\@apps.apple.com/x` le parece a
    # urlparse de la App Store y el navegador va a evil.com. Se rechaza todo
    # lo que no sea exactamente «https://<host de la tienda>/…».
    # Contra el host disfrazado, la guarda de «\» es redundante (mutación,
    # 2026-10-08): esos casos ya los frenan la de usuario/puerto y la del host
    # exacto. Lo único que solo ella rechaza es un «\» después del host
    # (`https://apps.apple.com/co/app\x/id1`), que el navegador lee como «/»
    # en la misma tienda; se deja como defensa de más y la prueba lo fija.
    if "\\" in url or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return None
    try:
        u = urlparse(url)
        if u.username is not None or u.password is not None or u.port is not None:
            return None
    except ValueError:
        return None
    if u.scheme != "https":
        return None
    return _HOSTS.get(u.netloc.lower())


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

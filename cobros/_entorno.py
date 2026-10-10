"""Lo que comparten las pasarelas (Bold y Wompi): ¿este servidor es local?
Las llaves o marcas de pruebas solo valen en una máquina local; en un servidor
público se ignoran (revisión final de cobros 2026-10-08, E1; planes 2026-10-09 §5)."""
import os
from urllib.parse import urlsplit


def host_local(url):
    """¿El host de `url` es de una máquina local? (localhost, 127.0.0.1, ::1,
    *.localhost, *.test, como la regla de pruebas del repo)."""
    try:
        host = (urlsplit(str(url or "").strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith((".localhost", ".test"))


def plataforma_local():
    """¿PLATAFORMA_URL apunta a una máquina local? Sin PLATAFORMA_URL: no."""
    return host_local(os.environ.get("PLATAFORMA_URL"))

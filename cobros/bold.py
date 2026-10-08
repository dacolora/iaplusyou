"""Bold (pasarela colombiana): crear un link de pago, leer su estado y
verificar la firma del webhook (spec 2026-10-08 §9). El ÚNICO módulo que
habla con Bold. Docs: developers.bold.co (API Link de pagos, Webhook).

Se llama con `requests` a un host fijo (BASE), nunca a una URL que escriba
una persona (spec §11). Ningún texto de error lleva la llave: los mensajes
dicen el código HTTP o el tipo de error de red, no la respuesta ni la URL."""
import base64
import hashlib
import hmac
import os
import re
import time
from urllib.parse import urlsplit

import requests
from flask_babel import gettext

BASE = "https://integrations.api.bold.co"
CHECKOUT = "https://checkout.bold.co/"
TIEMPO = 15                 # worker y crear el link: Bold puede tardar
TIEMPO_INTERACTIVO = (3, 5)  # (conectar, leer) de un sondeo de la página: no retener un hilo de gunicorn
_LINK = re.compile(r"LNK_[A-Za-z0-9]+")


class ErrorBold(Exception):
    """Bold no respondió lo esperado. El texto va en palabras y sin llaves.
    `caida` = Bold no está disponible (red, tiempo agotado o HTTP 5xx): quien
    consulta muchas recargas seguidas para ahí en vez de esperar por cada una."""

    def __init__(self, mensaje, caida=False):
        super().__init__(mensaje)
        self.caida = bool(caida)


def _identidad():
    return (os.environ.get("BOLD_LLAVE_IDENTIDAD") or "").strip()


def _secreta():
    # strip(): una secreta de solo espacios es una clave adivinable, y un
    # espacio de más al final hacía fallar todas las firmas (revisión final B1).
    return (os.environ.get("BOLD_LLAVE_SECRETA") or "").strip()


def host_local(url):
    """¿El host de `url` es de una máquina local? (localhost, 127.0.0.1, ::1,
    *.localhost, *.test, como la regla de pruebas del repo)."""
    try:
        host = (urlsplit(str(url or "").strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith((".localhost", ".test"))


def marca_pruebas():
    return os.environ.get("BOLD_PRUEBAS") == "1"


def pruebas_activas():
    """BOLD_PRUEBAS=1 solo vale si PLATAFORMA_URL es local (revisión final
    2026-10-08, E1): en un servidor público la marca se ignora, así una marca
    olvidada en el .env del VPS no vuelve falsificables los webhooks ni crea
    links de pruebas que acreditarían saldo real."""
    return marca_pruebas() and host_local(os.environ.get("PLATAFORMA_URL"))


def pruebas_fuera_de_local():
    """La marca está puesta en un servidor que no es local: se ignora y el
    admin lo ve en /admin/cobros."""
    return marca_pruebas() and not host_local(os.environ.get("PLATAFORMA_URL"))


def configurado():
    return bool(_identidad())


def _cabeceras():
    return {"Authorization": f"x-api-key {_identidad()}", "Content-Type": "application/json"}


def _datos(respuesta):
    try:
        j = respuesta.json()
    except ValueError as e:
        raise ErrorBold(gettext("Bold respondió algo que no es JSON")) from e
    return j.get("payload", j) if isinstance(j, dict) else {}


def _sin_red(e):
    # Solo el nombre del error: el texto de una excepción de requests puede traer la URL o cabeceras.
    return ErrorBold(gettext("No se pudo hablar con Bold (%(tipo)s)", tipo=type(e).__name__), caida=True)


def crear_link(*, referencia, usd, descripcion, callback_url, correo=None, horas=24, tiempo=TIEMPO):
    if not configurado():
        raise ErrorBold(gettext("Faltan las llaves de Bold"))
    cuerpo = {
        "amount_type": "CLOSE",
        "amount": {"currency": "USD", "total_amount": int(usd), "tip_amount": 0, "taxes": []},
        "reference": referencia,
        "description": descripcion[:100],
        "callback_url": callback_url,
        "expiration_date": int((time.time() + horas * 3600) * 1_000_000_000),
    }
    if correo:
        cuerpo["payer_email"] = correo
    try:
        r = requests.post(f"{BASE}/online/link/v1", json=cuerpo, headers=_cabeceras(), timeout=tiempo)
    except requests.RequestException as e:
        raise _sin_red(e) from None
    if r.status_code >= 400:
        raise ErrorBold(gettext("Bold no aceptó el pedido (HTTP %(codigo)s)", codigo=r.status_code),
                        caida=r.status_code >= 500)
    d = _datos(r)
    link, url = d.get("payment_link"), d.get("url")
    if not link or not url or not str(url).startswith(CHECKOUT):
        raise ErrorBold(gettext("Bold no devolvió un link de pago válido"))
    return {"link_id": str(link)[:40], "url": str(url)}


def estado_link(link_id, tiempo=TIEMPO):
    if not _LINK.fullmatch(str(link_id or "")):
        raise ErrorBold(gettext("Identificador de link inválido"))
    try:
        r = requests.get(f"{BASE}/online/link/v1/{link_id}", headers=_cabeceras(), timeout=tiempo)
    except requests.RequestException as e:
        raise _sin_red(e) from None
    if r.status_code >= 400:
        raise ErrorBold(gettext("Bold no respondió el estado (HTTP %(codigo)s)", codigo=r.status_code),
                        caida=r.status_code >= 500)
    d = _datos(r)
    total = d.get("total")
    # Moneda y medio, si Bold los manda (solo de registro: se guardan en la
    # recarga cuando la consulta es la que acredita).
    moneda = str(d.get("currency") or "")[:3] or None
    medio = str(d.get("payment_method") or "")[:20] or None
    return {"status": str(d.get("status") or "").upper(), "transaction_id": d.get("transaction_id"),
            "total": int(total) if isinstance(total, (int, float)) and not isinstance(total, bool) else None,
            "moneda": moneda, "medio": medio}


def firma_valida(cuerpo, firma):
    """HMAC-SHA256 (hex) del cuerpo en base64 con la llave secreta, comparado
    en tiempo constante con x-bold-signature. En pruebas Bold firma con la
    cadena vacía: solo se acepta con BOLD_PRUEBAS=1 en un servidor local
    (`pruebas_activas`)."""
    secreta = _secreta()
    if not secreta and not pruebas_activas():
        return False
    if not firma:
        return False
    esperado = hmac.new(secreta.encode(), base64.b64encode(cuerpo or b""), hashlib.sha256).hexdigest()
    # En bytes: compare_digest con un str que no es ASCII lanza TypeError, y una
    # cabecera rara no puede tumbar el webhook en un 500 que Bold reintenta.
    return hmac.compare_digest(esperado.encode(), str(firma).strip().lower().encode("utf-8", "replace"))

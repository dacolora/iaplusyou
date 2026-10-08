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

import requests
from flask_babel import gettext

BASE = "https://integrations.api.bold.co"
CHECKOUT = "https://checkout.bold.co/"
TIEMPO = 15
_LINK = re.compile(r"LNK_[A-Za-z0-9]+")


class ErrorBold(Exception):
    """Bold no respondió lo esperado. El texto va en palabras y sin llaves."""


def _identidad():
    return (os.environ.get("BOLD_LLAVE_IDENTIDAD") or "").strip()


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
    return ErrorBold(gettext("No se pudo hablar con Bold (%(tipo)s)", tipo=type(e).__name__))


def crear_link(*, referencia, usd, descripcion, callback_url, correo=None, horas=24):
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
        r = requests.post(f"{BASE}/online/link/v1", json=cuerpo, headers=_cabeceras(), timeout=TIEMPO)
    except requests.RequestException as e:
        raise _sin_red(e) from None
    if r.status_code >= 400:
        raise ErrorBold(gettext("Bold no aceptó el pedido (HTTP %(codigo)s)", codigo=r.status_code))
    d = _datos(r)
    link, url = d.get("payment_link"), d.get("url")
    if not link or not url or not str(url).startswith(CHECKOUT):
        raise ErrorBold(gettext("Bold no devolvió un link de pago válido"))
    return {"link_id": str(link)[:40], "url": str(url)}


def estado_link(link_id):
    if not _LINK.fullmatch(str(link_id or "")):
        raise ErrorBold(gettext("Identificador de link inválido"))
    try:
        r = requests.get(f"{BASE}/online/link/v1/{link_id}", headers=_cabeceras(), timeout=TIEMPO)
    except requests.RequestException as e:
        raise _sin_red(e) from None
    if r.status_code >= 400:
        raise ErrorBold(gettext("Bold no respondió el estado (HTTP %(codigo)s)", codigo=r.status_code))
    d = _datos(r)
    total = d.get("total")
    return {"status": str(d.get("status") or "").upper(), "transaction_id": d.get("transaction_id"),
            "total": int(total) if isinstance(total, (int, float)) and not isinstance(total, bool) else None}


def firma_valida(cuerpo, firma):
    """HMAC-SHA256 (hex) del cuerpo en base64 con la llave secreta, comparado
    en tiempo constante con x-bold-signature. En pruebas Bold firma con la
    cadena vacía: solo se acepta con BOLD_PRUEBAS=1."""
    secreta = os.environ.get("BOLD_LLAVE_SECRETA") or ""
    if not secreta and os.environ.get("BOLD_PRUEBAS") != "1":
        return False
    if not firma:
        return False
    esperado = hmac.new(secreta.encode(), base64.b64encode(cuerpo or b""), hashlib.sha256).hexdigest()
    # En bytes: compare_digest con un str que no es ASCII lanza TypeError, y una
    # cabecera rara no puede tumbar el webhook en un 500 que Bold reintenta.
    return hmac.compare_digest(esperado.encode(), str(firma).strip().lower().encode("utf-8", "replace"))

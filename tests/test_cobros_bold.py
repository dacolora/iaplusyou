"""Cliente de Bold (spec 2026-10-08 §9): crear el link de pago, leer su
estado y verificar la firma del webhook. Nunca llama a la red: `requests`
falso con monkeypatch."""
import base64
import hashlib
import hmac
import time

import pytest

LLAVE = "llave-identidad-de-prueba-123"  # llave-de-prueba
SECRETA = "secreta-de-prueba-456"  # llave-de-prueba


class _Respuesta:
    def __init__(self, status_code=200, datos=None, texto=None):
        self.status_code = status_code
        self._datos = datos
        self._texto = texto

    def json(self):
        if self._texto is not None:
            raise ValueError("no es JSON")
        return self._datos


@pytest.fixture()
def bold(monkeypatch):
    from cobros import bold as mod
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", LLAVE)
    monkeypatch.delenv("BOLD_LLAVE_SECRETA", raising=False)
    monkeypatch.delenv("BOLD_PRUEBAS", raising=False)

    def _sin_red(*a, **k):
        raise AssertionError("la prueba no debe llamar a la red")
    monkeypatch.setattr(mod.requests, "post", _sin_red)
    monkeypatch.setattr(mod.requests, "get", _sin_red)
    return mod


def _link_ok():
    return _Respuesta(200, {"payload": {"payment_link": "LNK_ABC123", "url": "https://checkout.bold.co/LNK_ABC123"}})


def test_configurado_depende_de_la_llave_de_identidad(bold, monkeypatch):
    assert bold.configurado() is True
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", "  ")
    assert bold.configurado() is False


def test_crear_link_manda_cabecera_y_cuerpo_de_bold(bold, monkeypatch):
    visto = {}

    def post(url, json=None, headers=None, timeout=None):
        visto.update(url=url, json=json, headers=headers, timeout=timeout)
        return _link_ok()
    monkeypatch.setattr(bold.requests, "post", post)
    antes = time.time()
    r = bold.crear_link(referencia="cv-1-1", usd=50, descripcion="Recarga Creatv · acme",
                        callback_url="https://app.creatvmachine.com/cliente/acme/saldo/recarga/1",
                        correo="acme@prueba.local")
    assert r == {"link_id": "LNK_ABC123", "url": "https://checkout.bold.co/LNK_ABC123"}
    assert visto["url"] == "https://integrations.api.bold.co/online/link/v1"
    assert visto["headers"]["Authorization"] == f"x-api-key {LLAVE}"
    assert visto["timeout"] == 15
    cuerpo = dict(visto["json"])
    vence = cuerpo.pop("expiration_date")
    assert isinstance(vence, int)
    assert (antes + 23.9 * 3600) * 1e9 < vence < (time.time() + 24.1 * 3600) * 1e9   # nanosegundos, a 24 h
    assert cuerpo == {
        "amount_type": "CLOSE",
        "amount": {"currency": "USD", "total_amount": 50, "tip_amount": 0, "taxes": []},
        "reference": "cv-1-1",
        "description": "Recarga Creatv · acme",
        "callback_url": "https://app.creatvmachine.com/cliente/acme/saldo/recarga/1",
        "payer_email": "acme@prueba.local",
    }


def test_crear_link_sin_correo_no_manda_payer_email(bold, monkeypatch):
    visto = {}
    monkeypatch.setattr(bold.requests, "post", lambda url, json=None, **k: visto.update(json=json) or _link_ok())
    bold.crear_link(referencia="cv-1-1", usd=10, descripcion="x", callback_url="https://a/b")
    assert "payer_email" not in visto["json"]


@pytest.mark.parametrize("status", [400, 401, 403, 500, 503])
def test_crear_link_con_error_http_no_revela_la_llave(bold, monkeypatch, status):
    monkeypatch.setattr(bold.requests, "post", lambda *a, **k: _Respuesta(status, {"errors": [LLAVE]}))
    with pytest.raises(bold.ErrorBold) as e:
        bold.crear_link(referencia="cv-1-1", usd=50, descripcion="x", callback_url="https://a/b")
    assert LLAVE not in str(e.value)  # llave-de-prueba
    assert str(status) in str(e.value)


def test_crear_link_sin_red_es_error_bold(bold, monkeypatch):
    def caida(*a, **k):
        raise bold.requests.ConnectionError(f"https://x?key={LLAVE}")  # llave-de-prueba
    monkeypatch.setattr(bold.requests, "post", caida)
    with pytest.raises(bold.ErrorBold) as e:
        bold.crear_link(referencia="cv-1-1", usd=50, descripcion="x", callback_url="https://a/b")
    assert LLAVE not in str(e.value)  # llave-de-prueba


@pytest.mark.parametrize("url", ["https://evil.example/LNK_ABC123", "http://checkout.bold.co/LNK_ABC123",
                                 "https://checkout.bold.co.evil.example/LNK_1", "", None])
def test_crear_link_rechaza_una_url_que_no_es_el_checkout_de_bold(bold, monkeypatch, url):
    monkeypatch.setattr(bold.requests, "post",
                        lambda *a, **k: _Respuesta(200, {"payload": {"payment_link": "LNK_ABC123", "url": url}}))
    with pytest.raises(bold.ErrorBold):
        bold.crear_link(referencia="cv-1-1", usd=50, descripcion="x", callback_url="https://a/b")


def test_crear_link_respuesta_que_no_es_json(bold, monkeypatch):
    monkeypatch.setattr(bold.requests, "post", lambda *a, **k: _Respuesta(200, texto="<html>"))
    with pytest.raises(bold.ErrorBold):
        bold.crear_link(referencia="cv-1-1", usd=50, descripcion="x", callback_url="https://a/b")


def test_crear_link_sin_llaves_no_llama_a_la_red(bold, monkeypatch):
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD")
    with pytest.raises(bold.ErrorBold):
        bold.crear_link(referencia="cv-1-1", usd=50, descripcion="x", callback_url="https://a/b")


@pytest.mark.parametrize("datos", [
    {"status": "paid", "transaction_id": "TX1", "total": 50},
    {"payload": {"status": "PAID", "transaction_id": "TX1", "total": 50}},
])
def test_estado_link_plano_o_dentro_de_payload(bold, monkeypatch, datos):
    visto = {}

    def get(url, headers=None, timeout=None):
        visto.update(url=url, headers=headers)
        return _Respuesta(200, datos)
    monkeypatch.setattr(bold.requests, "get", get)
    assert bold.estado_link("LNK_ABC123") == {"status": "PAID", "transaction_id": "TX1", "total": 50,
                                              "moneda": None, "medio": None}
    assert visto["url"] == "https://integrations.api.bold.co/online/link/v1/LNK_ABC123"
    assert visto["headers"]["Authorization"] == f"x-api-key {LLAVE}"


def test_estado_link_sin_total_ni_transaccion(bold, monkeypatch):
    monkeypatch.setattr(bold.requests, "get", lambda *a, **k: _Respuesta(200, {"status": "ACTIVE"}))
    assert bold.estado_link("LNK_X") == {"status": "ACTIVE", "transaction_id": None, "total": None,
                                         "moneda": None, "medio": None}


def test_estado_link_trae_moneda_y_medio_si_bold_los_manda(bold, monkeypatch):
    """Revisión final 2026-10-08: cuando la consulta es la que acredita, la
    recarga guarda también moneda y medio (solo de registro)."""
    monkeypatch.setattr(bold.requests, "get", lambda *a, **k: _Respuesta(200, {
        "status": "PAID", "transaction_id": "TX1", "total": 200000, "currency": "COP", "payment_method": "PSE"}))
    e = bold.estado_link("LNK_X")
    assert (e["moneda"], e["medio"], e["total"]) == ("COP", "PSE", 200000)


@pytest.mark.parametrize("link_id", ["", None, "LNK_", "lnk_abc", "LNK_ABC/../x", "LNK_A?b=1", "https://x/LNK_A"])
def test_estado_link_rechaza_un_id_raro_sin_llamar_a_la_red(bold, link_id):
    with pytest.raises(bold.ErrorBold):
        bold.estado_link(link_id)   # el fixture revienta si se llama a requests


def test_estado_link_error_http(bold, monkeypatch):
    monkeypatch.setattr(bold.requests, "get", lambda *a, **k: _Respuesta(404, {}))
    with pytest.raises(bold.ErrorBold) as e:
        bold.estado_link("LNK_ABC123")
    assert LLAVE not in str(e.value)  # llave-de-prueba


def _firma(secreta, cuerpo):
    return hmac.new(secreta.encode(), base64.b64encode(cuerpo), hashlib.sha256).hexdigest()


def test_firma_valida(bold, monkeypatch):
    monkeypatch.setenv("BOLD_LLAVE_SECRETA", SECRETA)
    cuerpo = b'{"id":"ev1","type":"SALE_APPROVED"}'
    assert bold.firma_valida(cuerpo, _firma(SECRETA, cuerpo)) is True
    assert bold.firma_valida(cuerpo, _firma(SECRETA, cuerpo).upper()) is True   # hex en mayúsculas: la misma firma
    assert bold.firma_valida(cuerpo, "ñ" * 64) is False                         # no ASCII: False, nunca TypeError
    assert bold.firma_valida(cuerpo, _firma(SECRETA, b'{"id":"ev2"}')) is False
    assert bold.firma_valida(cuerpo, _firma("otra", cuerpo)) is False
    assert bold.firma_valida(cuerpo, "") is False
    assert bold.firma_valida(cuerpo, None) is False


def test_firma_con_secreta_vacia_solo_en_modo_pruebas(bold, monkeypatch):
    cuerpo = b'{"id":"ev1"}'
    firma_vacia = _firma("", cuerpo)
    assert bold.firma_valida(cuerpo, firma_vacia) is False          # sin BOLD_PRUEBAS=1
    monkeypatch.setenv("BOLD_PRUEBAS", "1")
    monkeypatch.setenv("PLATAFORMA_URL", "http://localhost:5050")
    assert bold.firma_valida(cuerpo, firma_vacia) is True
    assert bold.firma_valida(cuerpo, _firma(SECRETA, cuerpo)) is False


@pytest.mark.parametrize("url", ["https://app.creatvmachine.com", "http://10.0.0.2", "http://localhost.evil.com", "", None])
def test_bold_pruebas_en_un_servidor_que_no_es_local_no_acepta_la_firma_vacia(bold, monkeypatch, url):
    """Revisión final 2026-10-08 (E1): una marca BOLD_PRUEBAS=1 olvidada en el
    VPS no vuelve falsificable el webhook."""
    cuerpo = b'{"id":"ev1"}'
    monkeypatch.setenv("BOLD_PRUEBAS", "1")
    if url is None:
        monkeypatch.delenv("PLATAFORMA_URL", raising=False)
    else:
        monkeypatch.setenv("PLATAFORMA_URL", url)
    assert bold.pruebas_activas() is False and bold.pruebas_fuera_de_local() is True
    assert bold.firma_valida(cuerpo, _firma("", cuerpo)) is False


@pytest.mark.parametrize("url", ["http://localhost:5050", "http://127.0.0.1:5050/", "http://[::1]:5050",
                                 "http://creatv.localhost", "https://app.creatv.test/x"])
def test_hosts_locales(bold, url):
    assert bold.host_local(url) is True


@pytest.mark.parametrize("secreta", ["   ", "\t\n"])
def test_una_secreta_de_solo_espacios_cuenta_como_vacia(bold, monkeypatch, secreta):
    """B1: sin strip() una secreta de espacios era una clave adivinable."""
    cuerpo = b'{"id":"ev1"}'
    monkeypatch.setenv("BOLD_LLAVE_SECRETA", secreta)
    assert bold.firma_valida(cuerpo, _firma(secreta, cuerpo)) is False


def test_un_espacio_de_mas_en_la_secreta_no_rompe_las_firmas(bold, monkeypatch):
    cuerpo = b'{"id":"ev1"}'
    monkeypatch.setenv("BOLD_LLAVE_SECRETA", SECRETA + " \n")
    assert bold.firma_valida(cuerpo, _firma(SECRETA, cuerpo)) is True


# --- ronda de arreglos 1: Bold caído y tiempos de espera --------------------------------------

@pytest.mark.parametrize("status,caida", [(400, False), (404, False), (500, True), (503, True)])
def test_error_http_dice_si_bold_esta_caido(bold, monkeypatch, status, caida):
    monkeypatch.setattr(bold.requests, "get", lambda *a, **k: _Respuesta(status, {}))
    monkeypatch.setattr(bold.requests, "post", lambda *a, **k: _Respuesta(status, {}))
    with pytest.raises(bold.ErrorBold) as e:
        bold.estado_link("LNK_ABC123")
    assert e.value.caida is caida
    with pytest.raises(bold.ErrorBold) as e:
        bold.crear_link(referencia="cv-1-1", usd=50, descripcion="x", callback_url="https://a/b")
    assert e.value.caida is caida


def test_sin_red_es_bold_caido_y_un_id_raro_no(bold, monkeypatch):
    def caida(*a, **k):
        raise bold.requests.Timeout("lento")
    monkeypatch.setattr(bold.requests, "get", caida)
    with pytest.raises(bold.ErrorBold) as e:
        bold.estado_link("LNK_ABC123")
    assert e.value.caida is True
    with pytest.raises(bold.ErrorBold) as e:
        bold.estado_link("no-es-un-link")
    assert e.value.caida is False


def test_estado_link_usa_el_tiempo_de_espera_pedido(bold, monkeypatch):
    vistos = []
    monkeypatch.setattr(bold.requests, "get",
                        lambda url, headers=None, timeout=None: vistos.append(timeout) or _Respuesta(200, {"status": "ACTIVE"}))
    bold.estado_link("LNK_ABC123")
    bold.estado_link("LNK_ABC123", tiempo=bold.TIEMPO_INTERACTIVO)
    assert vistos == [15, (3, 5)]

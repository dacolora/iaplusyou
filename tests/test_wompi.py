"""Cliente de Wompi (spec planes 2026-10-09 §5; API en docs/pagos/wompi-api.md).
Nunca llama a la red: `requests` falso con monkeypatch. Las llaves son falsas
y cada línea que trae una lleva la marca de prueba."""
import hashlib
from urllib.parse import parse_qsl, urlsplit

import pytest
import requests as requests_real

PUB_T = "pub_test_PRUEBA123"  # llave-de-prueba
PRV_T = "prv_test_PRUEBA456"  # llave-de-prueba
EVE_T = "test_events_PRUEBA789"  # llave-de-prueba
INT_T = "test_integrity_PRUEBA000"  # llave-de-prueba
PUB_P = "pub_prod_PRUEBA123"  # llave-de-prueba
PRV_P = "prv_prod_PRUEBA456"  # llave-de-prueba
EVE_P = "prod_events_PRUEBA789"  # llave-de-prueba
INT_P = "prod_integrity_PRUEBA000"  # llave-de-prueba
TODAS = (PUB_T, PRV_T, EVE_T, INT_T, PUB_P, PRV_P, EVE_P, INT_P)


class _Respuesta:
    def __init__(self, status_code=200, datos=None, texto=None):
        self.status_code = status_code
        self._datos = datos
        self._texto = texto

    def json(self):
        if self._texto is not None:
            raise ValueError("no es JSON")
        return self._datos


def _poner(monkeypatch, pub, prv, eve, integ, url="http://localhost:5050"):
    for nombre, valor in (("WOMPI_LLAVE_PUBLICA", pub), ("WOMPI_LLAVE_PRIVADA", prv),
                          ("WOMPI_SECRETO_EVENTOS", eve), ("WOMPI_SECRETO_INTEGRIDAD", integ)):
        if valor is None:
            monkeypatch.delenv(nombre, raising=False)
        else:
            monkeypatch.setenv(nombre, valor)
    if url is None:
        monkeypatch.delenv("PLATAFORMA_URL", raising=False)
    else:
        monkeypatch.setenv("PLATAFORMA_URL", url)


@pytest.fixture()
def wompi(monkeypatch):
    from cobros import wompi as mod
    _poner(monkeypatch, PUB_T, PRV_T, EVE_T, INT_T)

    def _sin_red(*a, **k):
        raise AssertionError("la prueba no debe llamar a la red")
    for verbo in ("get", "post", "put", "request"):
        monkeypatch.setattr(mod.requests, verbo, _sin_red)
    return mod


def _capturar(monkeypatch, mod, verbo, respuesta):
    visto = {}

    def f(url, **k):
        visto.update(url=url, **k)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta
    monkeypatch.setattr(mod.requests, verbo, f)
    return visto


def _sin_llaves(texto):
    for llave in TODAS:
        assert llave not in texto
        assert llave.split("_")[-1] not in texto


# ------------------------------------------------------------ ambiente ---

def test_llaves_de_pruebas_en_local_van_al_sandbox(wompi):
    assert wompi.configurado() is True
    assert wompi.pruebas() is True
    assert wompi.base_url() == "https://sandbox.wompi.co/v1"


def test_llaves_de_produccion_van_a_produccion(wompi, monkeypatch):
    _poner(monkeypatch, PUB_P, PRV_P, EVE_P, INT_P, url="https://app.creatvmachine.com")
    assert wompi.configurado() is True
    assert wompi.pruebas() is False
    assert wompi.base_url() == "https://production.wompi.co/v1"


@pytest.mark.parametrize("url", ["https://app.creatvmachine.com", "http://10.0.0.5:5050", None, ""])
def test_llaves_de_pruebas_fuera_de_local_no_sirven(wompi, monkeypatch, url):
    """Una llave de pruebas olvidada en el .env del VPS no crea checkouts que
    acreditarían saldo real ni vuelve falsificables los eventos."""
    _poner(monkeypatch, PUB_T, PRV_T, EVE_T, INT_T, url=url)
    assert wompi.configurado() is False
    assert wompi.pruebas_fuera_de_local() is True
    with pytest.raises(wompi.ErrorWompi) as e:
        wompi.base_url()
    assert "pruebas" in str(e.value)
    _sin_llaves(str(e.value))
    with pytest.raises(wompi.ErrorWompi):
        wompi.firma_integridad("cv-1-1", 100000)
    with pytest.raises(wompi.ErrorWompi):
        wompi.url_checkout("cv-1-1", 100000, "https://app.creatvmachine.com/x")
    with pytest.raises(wompi.ErrorWompi):
        wompi.transaccion("1-2-3")
    with pytest.raises(wompi.ErrorWompi):
        wompi.aceptaciones()
    with pytest.raises(wompi.ErrorWompi):
        wompi.cobrar_fuente(3891, 100000, "a@b.co", "pl-1-20261109-1")
    cuerpo = _evento()
    assert wompi.evento_valido(cuerpo) is False


@pytest.mark.parametrize("cuatro", [
    (PUB_T, PRV_P, EVE_T, INT_T),          # pública de pruebas y privada de producción
    (PUB_P, PRV_P, EVE_T, INT_P),          # secreto de eventos de pruebas con llaves de producción
    (PUB_P, PRV_P, EVE_P, INT_T),
    ("llave_rara", PRV_P, EVE_P, INT_P),   # llave-de-prueba
])
def test_llaves_mezcladas_o_raras_no_configuran(wompi, monkeypatch, cuatro):
    _poner(monkeypatch, *cuatro, url="http://localhost:5050")
    assert wompi.configurado() is False
    with pytest.raises(wompi.ErrorWompi) as e:
        wompi.base_url()
    _sin_llaves(str(e.value))


@pytest.mark.parametrize("falta", range(4))
def test_falta_una_llave_no_configura(wompi, monkeypatch, falta):
    cuatro = [PUB_T, PRV_T, EVE_T, INT_T]
    cuatro[falta] = "   "
    _poner(monkeypatch, *cuatro)
    assert wompi.configurado() is False
    with pytest.raises(wompi.ErrorWompi) as e:
        wompi.base_url()
    assert "Faltan" in str(e.value)


# ---------------------------------------------------------- integridad ---

def test_firma_de_integridad(wompi):
    esperado = hashlib.sha256(f"sk8-438k4-xmxm392-sn2m2490000COP{INT_T}".encode()).hexdigest()
    assert wompi.firma_integridad("sk8-438k4-xmxm392-sn2m", 2490000) == esperado
    assert wompi.firma_integridad("sk8-438k4-xmxm392-sn2m", 2490000, moneda="COP") == esperado


def test_firma_de_integridad_con_vencimiento(wompi):
    vence = "2023-06-09T20:28:50.000Z"
    esperado = hashlib.sha256(f"sk8-438k4-xmxm392-sn2m2490000COP{vence}{INT_T}".encode()).hexdigest()
    assert wompi.firma_integridad("sk8-438k4-xmxm392-sn2m", 2490000, expiracion=vence) == esperado


def test_firma_de_integridad_toma_el_secreto_sin_espacios(wompi, monkeypatch):
    monkeypatch.setenv("WOMPI_SECRETO_INTEGRIDAD", f"  {INT_T}\n")
    esperado = hashlib.sha256(f"r12345COP{INT_T}".encode()).hexdigest()
    assert wompi.firma_integridad("r1", 2345) == esperado


@pytest.mark.parametrize("centavos", [0, -100, True, 12.5, "100", None])
def test_firma_rechaza_montos_que_no_son_enteros_positivos(wompi, centavos):
    with pytest.raises(wompi.ErrorWompi):
        wompi.firma_integridad("cv-1-1", centavos)


@pytest.mark.parametrize("ref", ["", None, "x" * 256])
def test_firma_rechaza_referencias_invalidas(wompi, ref):
    with pytest.raises(wompi.ErrorWompi):
        wompi.firma_integridad(ref, 100)


# ------------------------------------------------------------ checkout ---

def test_url_de_checkout_lleva_los_parametros_documentados(wompi):
    url = wompi.url_checkout("cv-7-1760000000", 32187500, "http://localhost:5050/cliente/acme/saldo/recarga/7",
                             correo="pagos+acme@prueba.local")
    partes = urlsplit(url)
    assert f"{partes.scheme}://{partes.netloc}{partes.path}" == "https://checkout.wompi.co/p/"
    q = dict(parse_qsl(partes.query, strict_parsing=True))
    assert q == {
        "public-key": PUB_T,
        "currency": "COP",
        "amount-in-cents": "32187500",
        "reference": "cv-7-1760000000",
        "signature:integrity": wompi.firma_integridad("cv-7-1760000000", 32187500),
        "redirect-url": "http://localhost:5050/cliente/acme/saldo/recarga/7",
        "customer-data:email": "pagos+acme@prueba.local",
    }
    # Codificada como la manda un formulario: los ':' y el '+' del correo no quedan crudos.
    assert "signature%3Aintegrity=" in partes.query
    assert "pagos%2Bacme%40prueba.local" in partes.query
    assert "/cliente/acme" not in partes.query


def test_url_de_checkout_sin_correo(wompi):
    url = wompi.url_checkout("cv-7-1", 100000, "http://localhost:5050/x")
    q = dict(parse_qsl(urlsplit(url).query))
    assert "customer-data:email" not in q


@pytest.mark.parametrize("vuelta", ["javascript:alert(1)", "ftp://x.co/a", "", "//evil.co/x"])
def test_url_de_checkout_rechaza_vueltas_raras(wompi, vuelta):
    with pytest.raises(wompi.ErrorWompi):
        wompi.url_checkout("cv-7-1", 100000, vuelta)


# -------------------------------------------------------------- eventos ---

def _evento(secreto=EVE_T, props=("transaction.id", "transaction.status", "transaction.amount_in_cents"),
            ts=1530291411, tx=None):
    tx = tx or {"id": "01-1532941443-49201", "amount_in_cents": 4490000, "reference": "cv-1-1",
                "currency": "COP", "status": "APPROVED", "payment_source_id": None}
    cuerpo = {"event": "transaction.updated", "data": {"transaction": dict(tx)},
              "sent_at": "2018-07-20T16:45:05.000Z",
              "signature": {"properties": list(props), "timestamp": ts}}
    valores = ""
    for p in props:
        nodo = cuerpo["data"]
        for parte in p.split("."):
            nodo = nodo[parte]
        valores += str(nodo)
    cuerpo["signature"]["checksum"] = hashlib.sha256(f"{valores}{ts}{secreto}".encode()).hexdigest().upper()
    return cuerpo


def test_evento_con_firma_valida(wompi):
    cuerpo = _evento()
    # La cadena firmada es la de la doc: valores en orden + timestamp + secreto.
    s = f"01-1532941443-49201APPROVED44900001530291411{EVE_T}"
    assert cuerpo["signature"]["checksum"] == hashlib.sha256(s.encode()).hexdigest().upper()
    assert wompi.evento_valido(cuerpo) is True


def test_evento_acepta_checksum_en_minusculas_y_cabecera(wompi):
    cuerpo = _evento()
    suma = cuerpo["signature"]["checksum"]
    cuerpo["signature"]["checksum"] = suma.lower()
    assert wompi.evento_valido(cuerpo, checksum_header=suma) is True
    assert wompi.evento_valido(cuerpo, checksum_header=suma.lower()) is True


def test_evento_con_cabecera_que_no_cuadra_es_invalido(wompi):
    cuerpo = _evento()
    assert wompi.evento_valido(cuerpo, checksum_header="0" * 64) is False
    assert wompi.evento_valido(cuerpo, checksum_header="ñ" * 64) is False


def test_evento_firmado_con_otro_secreto_es_invalido(wompi):
    assert wompi.evento_valido(_evento(secreto="prod_events_OTRO")) is False  # llave-de-prueba


@pytest.mark.parametrize("cambio", ["status", "amount", "id", "timestamp", "props", "reference_sin_firmar"])
def test_evento_alterado(wompi, cambio):
    cuerpo = _evento()
    tx = cuerpo["data"]["transaction"]
    if cambio == "status":
        tx["status"] = "DECLINED"
    elif cambio == "amount":
        tx["amount_in_cents"] = 4490001
    elif cambio == "id":
        tx["id"] = "01-1532941443-49202"
    elif cambio == "timestamp":
        cuerpo["signature"]["timestamp"] += 1
    elif cambio == "props":
        cuerpo["signature"]["properties"] = ["transaction.id", "transaction.status"]
    else:
        # La referencia no está entre las propiedades firmadas: cambiarla no rompe
        # la firma (por eso las rutas comprueban monto y referencia contra lo guardado).
        tx["reference"] = "cv-2-2"
        assert wompi.evento_valido(cuerpo) is True
        return
    assert wompi.evento_valido(cuerpo) is False


def test_evento_con_propiedades_que_varian(wompi):
    props = ("transaction.reference", "transaction.amount_in_cents", "transaction.currency")
    assert wompi.evento_valido(_evento(props=props)) is True


@pytest.mark.parametrize("roto", [
    lambda c: c.pop("signature"),
    lambda c: c["signature"].pop("checksum"),
    lambda c: c["signature"].update(checksum=None),
    lambda c: c["signature"].update(properties=[]),
    lambda c: c["signature"].update(properties="transaction.id"),
    lambda c: c["signature"].update(properties=["transaction.no_existe"]),
    lambda c: c["signature"].update(properties=["transaction"]),
    lambda c: c["signature"].update(properties=[1]),
    lambda c: c["signature"].update(timestamp=None),
    lambda c: c["signature"].update(timestamp=True),
    lambda c: c.update(data="x"),
    lambda c: c.pop("data"),
])
def test_evento_mal_formado_es_invalido_sin_reventar(wompi, roto):
    cuerpo = _evento()
    roto(cuerpo)
    assert wompi.evento_valido(cuerpo) is False


@pytest.mark.parametrize("cuerpo", [None, [], "x", 5])
def test_evento_que_no_es_dict(wompi, cuerpo):
    assert wompi.evento_valido(cuerpo) is False


def test_evento_sin_secreto_es_invalido(wompi, monkeypatch):
    monkeypatch.setenv("WOMPI_SECRETO_EVENTOS", "  ")
    # Firmado con la cadena vacía como secreto: no vale.
    assert wompi.evento_valido(_evento(secreto="")) is False


def test_evento_con_propiedad_nula_es_invalido(wompi):
    assert wompi.evento_valido(_evento(props=("transaction.id", "transaction.payment_source_id"))) is False


# -------------------------------------------------------- llamadas HTTP ---

def _merchant():
    return _Respuesta(200, {"data": {
        "id": 1, "name": "Creatv",
        "presigned_acceptance": {"acceptance_token": "eyJ.acepta", "type": "END_USER_POLICY",
                                 "permalink": "https://wompi.co/terminos.pdf"},
        "presigned_personal_data_auth": {"acceptance_token": "eyJ.personal", "type": "PERSONAL_DATA_AUTH",
                                         "permalink": "https://wompi.com/datos.pdf"}}})


def test_aceptaciones_usa_merchants_info_con_la_cabecera(wompi, monkeypatch):
    visto = _capturar(monkeypatch, wompi, "get", _merchant())
    r = wompi.aceptaciones()
    assert r == {"acceptance_token": "eyJ.acepta", "acceptance_url": "https://wompi.co/terminos.pdf",
                 "personal_token": "eyJ.personal", "personal_url": "https://wompi.com/datos.pdf"}
    assert visto["url"] == "https://sandbox.wompi.co/v1/merchants/info"
    assert visto["headers"]["x-merchant-public-key"] == PUB_T
    assert "Authorization" not in visto["headers"]
    assert visto["allow_redirects"] is False
    assert visto["timeout"]


def test_aceptaciones_rechaza_enlaces_que_no_son_https(wompi, monkeypatch):
    malo = _merchant()
    malo._datos["data"]["presigned_acceptance"]["permalink"] = "javascript:alert(1)"
    _capturar(monkeypatch, wompi, "get", malo)
    with pytest.raises(wompi.ErrorWompi):
        wompi.aceptaciones()


def test_aceptaciones_incompletas(wompi, monkeypatch):
    _capturar(monkeypatch, wompi, "get", _Respuesta(200, {"data": {"presigned_acceptance": {}}}))
    with pytest.raises(wompi.ErrorWompi):
        wompi.aceptaciones()


def _tx(status="APPROVED", **extra):
    d = {"id": "1292-1602113476-10985", "reference": "pl-3-20261109-1", "amount_in_cents": 322000000,
         "currency": "COP", "payment_method_type": "CARD", "status": status,
         "status_message": None, "payment_source_id": 3891}
    d.update(extra)
    return _Respuesta(200, {"data": d})


def test_transaccion_usa_la_llave_privada(wompi, monkeypatch):
    visto = _capturar(monkeypatch, wompi, "get", _tx())
    r = wompi.transaccion("1292-1602113476-10985", tiempo=(3, 5))
    assert visto["url"] == "https://sandbox.wompi.co/v1/transactions/1292-1602113476-10985"
    assert visto["headers"]["Authorization"] == f"Bearer {PRV_T}"
    assert visto["timeout"] == (3, 5)
    assert visto["allow_redirects"] is False
    assert r["id"] == "1292-1602113476-10985"
    assert r["status"] == "APPROVED"
    assert r["reference"] == "pl-3-20261109-1"
    assert r["amount_in_cents"] == 322000000
    assert r["currency"] == "COP"
    assert r["payment_source_id"] == 3891


@pytest.mark.parametrize("tid", ["../merchants/info", "1-2-3?x=1", "", None, "a/b", "1" * 80])
def test_transaccion_con_id_raro_no_sale(wompi, tid):
    with pytest.raises(wompi.ErrorWompi):
        wompi.transaccion(tid)


def test_transaccion_con_monto_que_no_es_entero(wompi, monkeypatch):
    _capturar(monkeypatch, wompi, "get", _tx(amount_in_cents="322000000"))
    assert wompi.transaccion("1-2-3")["amount_in_cents"] is None


def test_crear_fuente_de_tarjeta(wompi, monkeypatch):
    visto = _capturar(monkeypatch, wompi, "post", _Respuesta(201, {"data": {
        "id": 3891, "type": "CARD", "status": "AVAILABLE",
        "public_data": {"type": "CARD", "brand": "VISA", "last_four": "4242"}}}))
    r = wompi.crear_fuente("CARD", "tok_test_1_ABC", "pagos@acme.co", "eyJ.acepta", "eyJ.personal")
    assert r == {"id": 3891, "tipo": "CARD", "resumen": "Visa ···4242"}
    assert visto["url"] == "https://sandbox.wompi.co/v1/payment_sources"
    assert visto["headers"]["Authorization"] == f"Bearer {PRV_T}"
    assert visto["json"] == {"type": "CARD", "token": "tok_test_1_ABC", "customer_email": "pagos@acme.co",
                             "acceptance_token": "eyJ.acepta", "accept_personal_auth": "eyJ.personal"}


def test_crear_fuente_nequi_resume_el_celular(wompi, monkeypatch):
    _capturar(monkeypatch, wompi, "post", _Respuesta(201, {"data": {
        "id": 77, "type": "NEQUI", "status": "AVAILABLE",
        "public_data": {"type": "NEQUI", "phone_number": "3991111111"}}}))
    r = wompi.crear_fuente("NEQUI", "nequi_test_ABC", "pagos@acme.co", "a", "b")
    assert r == {"id": 77, "tipo": "NEQUI", "resumen": "Nequi ···1111"}


def test_crear_fuente_sin_datos_publicos_deja_resumen_vacio(wompi, monkeypatch):
    _capturar(monkeypatch, wompi, "post", _Respuesta(201, {"data": {
        "id": 5, "type": "CARD", "status": "AVAILABLE", "public_data": {"type": "CARD"}}}))
    assert wompi.crear_fuente("CARD", "tok_x", "a@b.co", "a", "b")["resumen"] == ""


@pytest.mark.parametrize("estado", ["DECLINED", "ERROR", "PENDING", None])
def test_crear_fuente_no_disponible_es_error(wompi, monkeypatch, estado):
    _capturar(monkeypatch, wompi, "post", _Respuesta(201, {"data": {"id": 5, "type": "CARD", "status": estado}}))
    with pytest.raises(wompi.ErrorWompi):
        wompi.crear_fuente("CARD", "tok_x", "a@b.co", "a", "b")


@pytest.mark.parametrize("tipo,token", [("PSE", "tok_x"), ("CARD", ""), ("CARD", "tok x/../"), ("CARD", None)])
def test_crear_fuente_valida_antes_de_salir(wompi, tipo, token):
    with pytest.raises(wompi.ErrorWompi):
        wompi.crear_fuente(tipo, token, "a@b.co", "a", "b")


def test_cobrar_fuente_manda_recurrente_cuotas_y_firma(wompi, monkeypatch):
    visto = _capturar(monkeypatch, wompi, "post", _Respuesta(201, {"data": {
        "id": "1292-1602113476-10985", "reference": "pl-3-20261109-1", "amount_in_cents": 322000000,
        "currency": "COP", "status": "PENDING", "status_message": "The transaction is being processed"}}))
    r = wompi.cobrar_fuente(3891, 322000000, "pagos@acme.co", "pl-3-20261109-1")
    assert visto["url"] == "https://sandbox.wompi.co/v1/transactions"
    assert visto["headers"]["Authorization"] == f"Bearer {PRV_T}"
    assert visto["allow_redirects"] is False
    assert visto["json"] == {
        "amount_in_cents": 322000000,
        "currency": "COP",
        "customer_email": "pagos@acme.co",
        "reference": "pl-3-20261109-1",
        "payment_source_id": 3891,
        "payment_method": {"installments": 1},
        "recurrent": True,
        "signature": wompi.firma_integridad("pl-3-20261109-1", 322000000),
    }
    assert r["status"] == "PENDING" and r["id"] == "1292-1602113476-10985"


def test_cobrar_fuente_nequi_no_manda_cuotas(wompi, monkeypatch):
    visto = _capturar(monkeypatch, wompi, "post", _tx(status="PENDING"))
    wompi.cobrar_fuente(77, 100000, "a@b.co", "pl-1-20261109-1", tipo="NEQUI")
    assert "payment_method" not in visto["json"]
    assert visto["json"]["recurrent"] is True


@pytest.mark.parametrize("fuente", [0, -1, True, "3891", None])
def test_cobrar_fuente_valida_la_fuente(wompi, fuente):
    with pytest.raises(wompi.ErrorWompi):
        wompi.cobrar_fuente(fuente, 100000, "a@b.co", "pl-1-1-1")


def test_cobrar_fuente_con_referencia_usada(wompi, monkeypatch):
    _capturar(monkeypatch, wompi, "post", _Respuesta(422, {"error": {
        "type": "INPUT_VALIDATION_ERROR", "messages": {"reference": ["The reference has already been used."]}}}))
    with pytest.raises(wompi.ErrorWompi) as e:
        wompi.cobrar_fuente(3891, 100000, "a@b.co", "pl-1-20261109-1")
    assert e.value.codigo == 422
    assert e.value.referencia_usada is True
    assert e.value.caida is False
    assert e.value.incierto is False


def test_cobrar_fuente_que_se_corta_queda_incierto(wompi, monkeypatch):
    """Un tiempo agotado leyendo la respuesta: Wompi pudo cobrar. Quien llama
    no reintenta con otra referencia (sería un segundo cobro)."""
    _capturar(monkeypatch, wompi, "post", requests_real.ReadTimeout(f"timeout Bearer {PRV_T}"))
    with pytest.raises(wompi.ErrorWompi) as e:
        wompi.cobrar_fuente(3891, 100000, "a@b.co", "pl-1-20261109-1")
    assert e.value.caida is True and e.value.incierto is True
    _sin_llaves(str(e.value))


def test_cobrar_fuente_sin_conectar_no_es_incierto(wompi, monkeypatch):
    _capturar(monkeypatch, wompi, "post", requests_real.ConnectTimeout("no conecta"))
    with pytest.raises(wompi.ErrorWompi) as e:
        wompi.cobrar_fuente(3891, 100000, "a@b.co", "pl-1-20261109-1")
    assert e.value.caida is True and e.value.incierto is False


def test_cobrar_fuente_con_5xx_queda_incierto(wompi, monkeypatch):
    _capturar(monkeypatch, wompi, "post", _Respuesta(502, texto="<html>"))
    with pytest.raises(wompi.ErrorWompi) as e:
        wompi.cobrar_fuente(3891, 100000, "a@b.co", "pl-1-20261109-1")
    assert e.value.caida is True and e.value.incierto is True and e.value.codigo == 502


@pytest.mark.parametrize("respuesta,caida", [
    (_Respuesta(401, {"error": {"type": "INVALID_ACCESS_TOKEN", "reason": f"Bearer {PRV_T}"}}), False),
    (_Respuesta(404, {"error": {"type": "NOT_FOUND_ERROR"}}), False),
    (_Respuesta(500, texto="boom"), True),
    (_Respuesta(503, {"error": {}}), True),
    (_Respuesta(302, {}), False),
    (_Respuesta(200, texto="<html>"), False),
    (_Respuesta(200, ["no", "dict"]), False),
    (requests_real.ConnectionError(f"https://sandbox.wompi.co/v1 Bearer {PRV_T}"), True),
    (requests_real.Timeout("t"), True),
])
def test_errores_http_y_de_red(wompi, monkeypatch, respuesta, caida):
    _capturar(monkeypatch, wompi, "get", respuesta)
    with pytest.raises(wompi.ErrorWompi) as e:
        wompi.transaccion("1-2-3")
    assert e.value.caida is caida
    _sin_llaves(str(e.value))
    assert e.value.__cause__ is None   # `from None`: el error de requests (con URL y cabeceras) no viaja


def test_token_nequi(wompi, monkeypatch):
    visto = _capturar(monkeypatch, wompi, "post", _Respuesta(200, {"data": {
        "id": "nequi_test_RQkUiuv3", "status": "PENDING", "phone_number": "3991111111"}}))
    assert wompi.token_nequi("399 111 1111") == "nequi_test_RQkUiuv3"
    assert visto["url"] == "https://sandbox.wompi.co/v1/tokens/nequi"
    assert visto["headers"]["Authorization"] == f"Bearer {PUB_T}"
    assert visto["json"] == {"phone_number": "3991111111"}


@pytest.mark.parametrize("cel", ["12345", "2991111111", "39911111112", "", None, "abc1111111"])
def test_token_nequi_valida_el_celular(wompi, cel):
    with pytest.raises(wompi.ErrorWompi):
        wompi.token_nequi(cel)


def test_estado_token_nequi(wompi, monkeypatch):
    visto = _capturar(monkeypatch, wompi, "get", _Respuesta(200, {"data": {
        "id": "nequi_test_RQkUiuv3", "status": "approved"}}))
    assert wompi.estado_token_nequi("nequi_test_RQkUiuv3") == "APPROVED"
    assert visto["url"] == "https://sandbox.wompi.co/v1/tokens/nequi/nequi_test_RQkUiuv3"
    assert visto["headers"]["Authorization"] == f"Bearer {PUB_T}"


@pytest.mark.parametrize("tok", ["../transactions", "", None, "nequi test"])
def test_estado_token_nequi_valida_el_token(wompi, tok):
    with pytest.raises(wompi.ErrorWompi):
        wompi.estado_token_nequi(tok)


# ------------------------------------------------------------ pasarela ---

def test_pasarela_para_recargas(wompi, monkeypatch):
    from cobros import pasarela
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", "bold-de-prueba")  # llave-de-prueba
    assert pasarela.para_recargas() == "wompi"
    monkeypatch.delenv("WOMPI_SECRETO_INTEGRIDAD")
    assert pasarela.para_recargas() == "bold"
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD")
    assert pasarela.para_recargas() is None


def test_pasarela_con_llaves_de_pruebas_en_produccion_cae_a_bold(wompi, monkeypatch):
    from cobros import pasarela
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.creatvmachine.com")
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", "bold-de-prueba")  # llave-de-prueba
    assert pasarela.para_recargas() == "bold"

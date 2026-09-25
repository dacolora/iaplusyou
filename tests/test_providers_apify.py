import pytest

import providers.apify as apify_api
from nicho.fuentes.base import ErrorFuente


class _Resp:
    def __init__(self, cuerpo, status=200):
        self._cuerpo = cuerpo
        self.status_code = status

    def json(self):
        return self._cuerpo


class _Sesion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        return self._respuestas.pop(0)


def test_cabeceras_lleva_el_token_como_bearer():
    assert apify_api.cabeceras("tok123") == {"Authorization": "Bearer tok123", "Content-Type": "application/json"}


def test_frase_estado():
    assert apify_api.frase_estado("FAILED") == "terminó en FAILED"
    assert apify_api.frase_estado(apify_api.ESTADO_SIN_TERMINAR) == "no terminó en 20 min"


def test_probar_token_ok(monkeypatch):
    monkeypatch.setattr(apify_api, "_http", apify_api._http)
    sesion = _Sesion([_Resp({"data": {"id": "u1"}})])
    r = apify_api.probar_token(sesion, "tok")
    assert r == {"ok": True, "detalle": "Apify aceptó el token."}


def test_probar_token_401():
    sesion = _Sesion([_Resp({}, status=401)])
    r = apify_api.probar_token(sesion, "tok")
    assert r["ok"] is False and "401" in r["detalle"]


def test_arrancar_ok():
    sesion = _Sesion([_Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "READY"}}, status=201)])
    run_id, dataset_id, estado = apify_api.arrancar(sesion, "tok", "apify~actor", {"a": 1}, 50, 1.23)
    assert (run_id, dataset_id, estado) == ("run1", "ds1", "READY")
    metodo, url, kw = sesion.llamadas[0]
    assert metodo == "POST" and url == f"{apify_api.URL_API}/actors/apify~actor/runs"
    assert kw["params"] == {"timeout": apify_api.MAX_ESPERA_S, "maxItems": 50, "maxTotalChargeUsd": 1.23}
    assert kw["json"] == {"a": 1}
    assert kw["headers"]["Authorization"] == "Bearer tok"


def test_arrancar_401_lanza_error_fuente():
    sesion = _Sesion([_Resp({}, status=401)])
    with pytest.raises(ErrorFuente) as exc:
        apify_api.arrancar(sesion, "tok", "apify~actor", {}, 10, 0.1)
    assert "token" in exc.value.usuario.lower()


def test_arrancar_400_lanza_error_fuente_con_mensaje():
    sesion = _Sesion([_Resp({"error": {"message": "Field input.startUrls is required"}}, status=400)])
    with pytest.raises(ErrorFuente) as exc:
        apify_api.arrancar(sesion, "tok", "apify~actor", {}, 10, 0.1)
    assert "startUrls" in exc.value.usuario


def test_arrancar_sin_ids_lanza_error_fuente():
    sesion = _Sesion([_Resp({"data": {"status": "READY"}}, status=201)])
    with pytest.raises(ErrorFuente):
        apify_api.arrancar(sesion, "tok", "apify~actor", {}, 10, 0.1)


def test_sondear_hasta_terminal(monkeypatch):
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    sesion = _Sesion([_Resp({"data": {"status": "RUNNING"}}), _Resp({"data": {"status": "SUCCEEDED"}})])
    avisos = []
    estado = apify_api.sondear(sesion, "tok", "run1", "READY", "Leyendo X", lambda etapa, detalle=None: avisos.append((etapa, detalle)))
    assert estado == "SUCCEEDED"
    assert avisos[0][0] == "Leyendo X" and "run1" in avisos[0][1]


def test_sondear_ya_terminal_no_pide_nada():
    sesion = _Sesion([])
    estado = apify_api.sondear(sesion, "tok", "run1", "SUCCEEDED", "Leyendo X")
    assert estado == "SUCCEEDED"
    assert sesion.llamadas == []


def test_sondear_vence_el_reloj(monkeypatch):
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    monkeypatch.setattr(apify_api, "MAX_ESPERA_S", 5.0)
    monkeypatch.setattr(apify_api, "PAUSA_SONDEO", 10.0)
    sesion = _Sesion([_Resp({"data": {"status": "RUNNING"}})])
    estado = apify_api.sondear(sesion, "tok", "run1", "RUNNING", "Leyendo X")
    assert estado == apify_api.ESTADO_SIN_TERMINAR


def test_sondear_se_rinde_tras_fallos_seguidos(monkeypatch):
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    monkeypatch.setattr(apify_api, "MAX_FALLOS_SONDEO", 2)
    sesion = _Sesion([_Resp({}, status=500), _Resp({}, status=500), _Resp({}, status=500), _Resp({}, status=500)])
    with pytest.raises(ErrorFuente) as exc:
        apify_api.sondear(sesion, "tok", "run1", "RUNNING", "Leyendo X")
    assert "run1" in exc.value.usuario


def test_leer_dataset_ok():
    sesion = _Sesion([_Resp([{"a": 1}, {"a": 2}])])
    lista, motivo = apify_api.leer_dataset(sesion, "tok", "ds1", 50)
    assert lista == [{"a": 1}, {"a": 2}] and motivo == ""
    _, _, kw = sesion.llamadas[0]
    assert kw["params"] == {"clean": "true", "format": "json", "limit": 50}


def test_leer_dataset_agota_intentos(monkeypatch):
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    sesion = _Sesion([_Resp({}, status=500)] * (apify_api.INTENTOS_DATASET * 2))
    lista, motivo = apify_api.leer_dataset(sesion, "tok", "ds1", 50)
    assert lista is None and "500" in motivo


def test_contar_dataset_ok():
    sesion = _Sesion([_Resp({"data": {"itemCount": 7}})])
    assert apify_api.contar_dataset(sesion, "tok", "ds1") == 7


def test_contar_dataset_falla_devuelve_none():
    sesion = _Sesion([_Resp({}, status=500), _Resp({}, status=500)])
    assert apify_api.contar_dataset(sesion, "tok", "ds1") is None

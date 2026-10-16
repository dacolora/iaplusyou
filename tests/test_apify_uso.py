"""PND-010: el uso del mes de la cuenta de Apify de Creatv contra su tope. La periódica `apify_revisar_uso` lo lee
gratis en la API (`GET /v2/users/me/limits`) y lo guarda; Alertas avisa SOLO al admin desde el 80 % y otra vez al 100 %.
Ninguna página llama a Apify. Las pruebas no tocan la red."""
import json
from datetime import datetime, timedelta, timezone

import pytest

TOKEN = "apify_api_prueba_no_real"  # llave-de-prueba

# La respuesta de ejemplo de docs.apify.com/api/v2/users-me-limits-get (2026-10-15), recortada.
LIMITES = {"data": {"monthlyUsageCycle": {"startAt": "2026-10-02T00:00:00.000Z", "endAt": "2026-11-01T23:59:59.999Z"},
                    "limits": {"maxMonthlyUsageUsd": 5, "maxMonthlyActorComputeUnits": 1000},
                    "current": {"monthlyUsageUsd": 1.99, "monthlyActorComputeUnits": 12.5}}}


class _Resp:
    def __init__(self, status, cuerpo):
        self.status_code, self._cuerpo, self.headers = status, cuerpo, {}

    def json(self):
        if isinstance(self._cuerpo, Exception):
            raise self._cuerpo
        return self._cuerpo


class _Sesion:
    def __init__(self, respuesta):
        self.respuesta, self.pedidos = respuesta, []

    def request(self, metodo, url, **kw):
        self.pedidos.append((metodo, url, kw))
        return self.respuesta


def _guardar(base, usado, tope=5, hasta=None, desde="2026-10-02T00:00:00.000Z"):
    from providers import apify_uso
    hasta = hasta or (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    with base.conectar() as con:
        con.execute(base.kv.delete().where(base.kv.c.clave == apify_uso.CLAVE))
        con.execute(base.kv.insert().values(clave=apify_uso.CLAVE, actualizado_en="2026-10-15T00:00:00", valor=json.dumps(
            {"usado_usd": usado, "tope_usd": tope, "desde": desde, "hasta": hasta, "leido_en": "2026-10-15T00:00:00"})))


# ------------------------------------------------------------------- la lectura ---

def test_uso_del_mes_lee_la_forma_de_la_api():
    from providers import apify
    s = _Sesion(_Resp(200, LIMITES))
    assert apify.uso_del_mes(s, TOKEN) == {"usado_usd": 1.99, "tope_usd": 5.0, "desde": "2026-10-02T00:00:00.000Z",
                                          "hasta": "2026-11-01T23:59:59.999Z"}
    (metodo, url, kw), = s.pedidos
    assert metodo == "GET" and url == "https://api.apify.com/v2/users/me/limits"
    assert kw["headers"]["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("respuesta", [
    _Resp(401, {"error": {"message": "token"}}),
    _Resp(200, {"data": {"current": {}, "limits": {"maxMonthlyUsageUsd": 5}}}),
    _Resp(200, {"data": {"current": {"monthlyUsageUsd": 1}, "limits": {"maxMonthlyUsageUsd": 0}}}),
    _Resp(200, {"data": {"current": {"monthlyUsageUsd": "nan"}, "limits": {"maxMonthlyUsageUsd": 5}}}),
    _Resp(200, ValueError("no es JSON")),
    _Resp(200, [1, 2]),
])
def test_uso_del_mes_sin_sus_cifras_es_un_error_en_palabras(respuesta):
    from nicho.fuentes.base import ErrorFuente
    from providers import apify
    with pytest.raises(ErrorFuente) as e:
        apify.uso_del_mes(_Sesion(respuesta), TOKEN)
    assert TOKEN not in str(e.value)


def test_revisar_sin_token_no_pide_nada(base_temporal, monkeypatch):
    from nicho.fuentes import _http
    from providers import apify_uso
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.setattr(_http, "sesion", lambda: (_ for _ in ()).throw(AssertionError("no debe pedir")))
    assert apify_uso.revisar() is None and apify_uso.vigente() is None


def test_revisar_guarda_la_lectura_y_si_apify_falla_deja_la_anterior(base_temporal, monkeypatch, caplog):
    from nicho.fuentes import _http
    from providers import apify_uso
    monkeypatch.setenv("APIFY_TOKEN", TOKEN)
    hasta = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    cuerpo = json.loads(json.dumps(LIMITES))
    cuerpo["data"]["monthlyUsageCycle"]["endAt"] = hasta
    monkeypatch.setattr(_http, "sesion", lambda: _Sesion(_Resp(200, cuerpo)))
    uso = apify_uso.revisar()
    assert uso["usado_usd"] == 1.99 and uso["tope_usd"] == 5.0 and uso["leido_en"]
    assert apify_uso.vigente()["fraccion"] == pytest.approx(0.398)
    monkeypatch.setattr(_http, "sesion", lambda: _Sesion(_Resp(500, {})))
    monkeypatch.setattr(_http, "dormir", lambda s: None)
    assert apify_uso.revisar() is None
    assert apify_uso.vigente()["usado_usd"] == 1.99
    assert TOKEN not in caplog.text


def test_una_lectura_de_un_ciclo_terminado_no_cuenta(base_temporal):
    from providers import apify_uso
    _guardar(base_temporal, 4.9, hasta=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    assert apify_uso.vigente() is None


# ------------------------------------------------------------------- la alerta ---

def _apify(lista):
    return [a for a in lista if a["clave"].startswith("saldo:apify")]


def test_desde_el_80_por_ciento_avisa_solo_al_admin(base_temporal):
    import alertas
    _guardar(base_temporal, 3.99)                                         # 79,8 %
    assert _apify(alertas._fuente_saldo("acme", "2026-10-15T12:00:00")) == []
    _guardar(base_temporal, 4.0)                                          # 80 %
    a, = _apify(alertas._fuente_saldo("acme", "2026-10-15T12:00:00"))
    assert a["clave"] == "saldo:apify_tope" and a["solo_admin"] and a["nivel"] == "atencion"
    assert a["grupo"] == "puesta_a_punto" and a["tab"] == "settings" and a["ancla"] == "llave-apify"
    assert "80 %" in a["titulo"] and "US$ 4,00" in a["detalle"] and "US$ 5,00" in a["detalle"]
    assert "Starter" in a["detalle"]
    assert alertas.es_solo_admin("saldo:apify_tope", [])
    # Un cliente no la ve, ni puede descartarla (la regla de los prefijos de admin).
    calculadas = alertas._fuente_saldo("acme", "2026-10-15T12:00:00")
    assert _apify(alertas.visibles("acme", rol="cliente", calculadas=calculadas, usuario="user_acme")["visibles"]) == []
    assert _apify(alertas.visibles("acme", rol="admin", calculadas=calculadas, usuario="admin")["visibles"])


def test_al_100_por_ciento_bloquea_y_su_huella_es_otra(base_temporal):
    import alertas
    _guardar(base_temporal, 4.2)
    ochenta, = _apify(alertas._fuente_saldo("acme", "2026-10-15T12:00:00"))
    _guardar(base_temporal, 5.0)
    cien, = _apify(alertas._fuente_saldo("acme", "2026-10-15T12:00:00"))
    assert cien["nivel"] == "bloquea" and "100 %" in cien["titulo"]
    assert cien["huella"] != ochenta["huella"]                            # descartar el 80 % no esconde el 100 %
    _guardar(base_temporal, 4.2, desde="2026-11-02T00:00:00.000Z")       # el ciclo siguiente: otra huella
    siguiente, = _apify(alertas._fuente_saldo("acme", "2026-10-15T12:00:00"))
    assert siguiente["huella"] != ochenta["huella"]


def test_la_huella_no_sigue_al_idioma_y_sale_en_ingles(base_temporal):
    import alertas
    import dashboard
    import idiomas
    _guardar(base_temporal, 4.5)
    es, = _apify(alertas._fuente_saldo("acme", "2026-10-15T12:00:00"))
    with dashboard.app.test_request_context("/"), idiomas.en_idioma("en"):
        en, = _apify(alertas._fuente_saldo("acme", "2026-10-15T12:00:00"))
    assert en["huella"] == es["huella"] and "Apify is at 90 %" in en["titulo"]


def test_la_alerta_no_llama_a_apify(base_temporal, monkeypatch):
    """La fuente de alertas se calcula en cada página: solo lee la fila guardada (una consulta), nunca la red."""
    import alertas
    from providers import apify
    monkeypatch.setattr(apify, "uso_del_mes", lambda *a, **k: (_ for _ in ()).throw(AssertionError("red")))
    _guardar(base_temporal, 4.5)
    assert _apify(alertas.calcular("acme"))


# ------------------------------------------------------------------- la periódica ---

def test_la_periodica_esta_programada_y_no_cobra(base_temporal, monkeypatch):
    import tareas
    import worker
    from providers import apify_uso
    tareas.cargar_todas()
    assert ("apify_revisar_uso", 21600) in worker.PERIODICAS
    assert "apify_revisar_uso" in tareas.TIPOS_EXENTOS_DE_COBRO and "apify_revisar_uso" not in tareas.TIPOS_QUE_COBRAN
    monkeypatch.setattr(apify_uso, "revisar", lambda: {"usado_usd": 1.99, "tope_usd": 5.0})
    assert "US$ 1,99" in tareas.REGISTRO["apify_revisar_uso"]({"payload": {}})
    monkeypatch.setattr(apify_uso, "revisar", lambda: None)
    assert tareas.REGISTRO["apify_revisar_uso"]({"payload": {}})

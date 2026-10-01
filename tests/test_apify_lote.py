"""providers.apify.correr_lote: varias corridas a la vez, dataset leído en cualquier estado terminal, sin red."""
import pytest


class _Resp:
    def __init__(self, status, json=None):
        self.status_code, self._json, self.headers = status, json, {}

    def json(self):
        return self._json


class _Sesion:
    def __init__(self, rutas):
        self.rutas, self.llamadas = rutas, []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        for fragmento, respuesta in self.rutas.items():
            if fragmento in url:
                return respuesta.pop(0) if isinstance(respuesta, list) else respuesta
        raise AssertionError(f"URL no programada: {url}")


@pytest.fixture()
def esperas(monkeypatch):
    from nicho.fuentes import _http
    lista = []
    monkeypatch.setattr(_http, "dormir", lambda s: lista.append(s))
    return lista


def _corrida(status, run_id, ds):
    return _Resp(200, {"data": {"id": run_id, "status": status, "defaultDatasetId": ds}})


def _pedidas(n):
    return [{"entrada": {"asin": f"A{i}"}, "max_items": 10, "max_usd": 0.01, "etiqueta": f"A{i}"} for i in range(n)]


def test_lote_arranca_de_a_dos_y_lee_todos_los_datasets(esperas, monkeypatch):
    from nicho.fuentes import _http
    import providers.apify as ap
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0"), _corrida("READY", "r1", "d1"), _corrida("READY", "r2", "d2")],
                 "/actor-runs/r0": [_corrida("SUCCEEDED", "r0", "d0")], "/actor-runs/r1": [_corrida("RUNNING", "r1", "d1"), _corrida("SUCCEEDED", "r1", "d1")],
                 "/actor-runs/r2": [_corrida("SUCCEEDED", "r2", "d2")],
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}]), "/datasets/d1/items": _Resp(200, [{"t": "b"}, {"t": "c"}]), "/datasets/d2/items": _Resp(200, [])})
    etapas = []
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(3), "Leyendo", lambda e, d=None: etapas.append((e, d)), max_simultaneas=2)
    posts = [(u, kw) for m, u, kw in s.llamadas if m == "POST"]
    assert len(posts) == 3 and all(kw["params"] == {"timeout": ap.MAX_ESPERA_S, "maxItems": 10, "maxTotalChargeUsd": 0.01} for _, kw in posts)
    assert posts[0][1]["json"] == {"asin": "A0"} and posts[2][1]["json"] == {"asin": "A2"}
    assert [i for i, _ in res["items"]] == [0, 1, 1] and res["resultados"] == 3
    assert [c["estado"] for c in res["corridas"]] == ["SUCCEEDED"] * 3 and [c["run_id"] for c in res["corridas"]] == ["r0", "r1", "r2"]
    assert [c["resultados"] for c in res["corridas"]] == [1, 2, 0] and res["aviso"] == ""
    assert esperas == [ap.PAUSA_SONDEO] * 2                      # una pausa por vuelta de sondeo (2 vueltas), no por corrida
    assert all("tok" not in u for _, u, _ in s.llamadas) and all(kw["headers"]["Authorization"] == "Bearer tok" for _, _, kw in s.llamadas)
    assert any("r1" in (d or "") for e, d in etapas)


def test_lote_una_fallida_con_items_y_una_que_no_arranca_dejan_aviso(esperas):
    import providers.apify as ap
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0"), _Resp(400, {"error": {"message": "entrada mala"}})],
                 "/actor-runs/r0": [_corrida("FAILED", "r0", "d0")],
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}, {"t": "b"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(2), "Leyendo")
    assert res["resultados"] == 2 and [i for i, _ in res["items"]] == [0, 0]
    assert res["corridas"][0]["estado"] == "FAILED" and res["corridas"][1]["estado"] == ap.ESTADO_NO_ARRANCO
    assert "r0" in res["aviso"] and "FAILED" in res["aviso"] and "entrada mala" in res["aviso"] and "A1" in res["aviso"]


def test_lote_todas_sin_arrancar_levanta_y_no_cobra(esperas):
    import providers.apify as ap
    from nicho.fuentes.base import ErrorFuente
    s = _Sesion({"/actors/x~y/runs": [_Resp(401), _Resp(401)]})
    with pytest.raises(ErrorFuente) as e:
        ap.correr_lote(s, "tok", "x~y", _pedidas(2), "Leyendo")
    assert "token" in str(e.value).lower() and not any("/datasets" in u for _, u, _ in s.llamadas)


def test_lote_dataset_ilegible_cae_al_itemcount_y_timeout_local(esperas, monkeypatch):
    import providers.apify as ap
    monkeypatch.setattr(ap, "MAX_ESPERA_S", ap.PAUSA_SONDEO * 2)
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0"), _corrida("READY", "r1", "d1")],
                 "/actor-runs/r0": [_corrida("SUCCEEDED", "r0", "d0")],
                 "/actor-runs/r1": [_corrida("RUNNING", "r1", "d1"), _corrida("RUNNING", "r1", "d1"), _corrida("RUNNING", "r1", "d1")],
                 "/datasets/d0/items": [_Resp(503)] * (2 * ap.INTENTOS_DATASET), "/datasets/d0": _Resp(200, {"data": {"itemCount": 7}}),
                 "/datasets/d1/items": _Resp(200, [{"t": "x"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(2), "Leyendo")
    c0, c1 = res["corridas"]
    assert c0["resultados"] == 7 and "d0" in res["aviso"] and c1["estado"] == ap.ESTADO_SIN_TERMINAR and c1["resultados"] == 1
    assert res["resultados"] == 8 and [i for i, _ in res["items"]] == [1]


def test_lote_sondeo_tolera_fallos_y_se_rinde_por_corrida(esperas):
    import providers.apify as ap
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0")],
                 "/actor-runs/r0": [_Resp(503)] * (2 * ap.MAX_FALLOS_SONDEO),
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(1), "Leyendo")
    assert res["corridas"][0]["estado"] == ap.ESTADO_SIN_ESTADO and res["corridas"][0]["resultados"] == 1 and "r0" in res["aviso"]
    assert "sin estado" not in res["aviso"] and "no se pudo saber cómo terminó" in res["aviso"]


class _SinJson(_Resp):
    """Un 2xx cuyo cuerpo no es JSON (una página de error de un proxy, un corte a la mitad)."""

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


def test_lote_sondeo_que_no_es_json_cuenta_como_lectura_mala(esperas):
    """Ola final F10: un 200 sin JSON al sondear nunca tumba el lote: la corrida ya pagada se sigue sondeando,
    su dataset se lee y sus resultados se cuentan."""
    import providers.apify as ap
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0")],
                 "/actor-runs/r0": [_SinJson(200), _corrida("SUCCEEDED", "r0", "d0")],
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}, {"t": "b"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(1), "Leyendo")
    assert res["corridas"][0]["estado"] == "SUCCEEDED" and res["resultados"] == 2 and [i for i, _ in res["items"]] == [0, 0]
    assert res["aviso"] == ""
    # siempre ilegible: se rinde como con un error HTTP, y lo cobrado se lee igual
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0")],
                 "/actor-runs/r0": [_SinJson(200)] * ap.MAX_FALLOS_SONDEO,
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(1), "Leyendo")
    assert res["corridas"][0]["estado"] == ap.ESTADO_SIN_ESTADO and res["resultados"] == 1
    assert "respuesta ilegible" in res["aviso"] and "r0" in res["aviso"]
    # una lista en vez de un objeto tampoco revienta: no trae estado y se sigue esperando
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0")],
                 "/actor-runs/r0": [_Resp(200, ["raro"]), _corrida("SUCCEEDED", "r0", "d0")],
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}])})
    assert ap.correr_lote(s, "tok", "x~y", _pedidas(1), "Leyendo")["corridas"][0]["estado"] == "SUCCEEDED"


def test_arrancar_sin_json_no_cuenta_como_lanzada(esperas):
    """Ola final F10: un 2xx sin JSON al arrancar es ErrorFuente con un mensaje claro (sin ids: no consta como
    lanzada); en un lote, las demás corridas siguen."""
    import providers.apify as ap
    from nicho.fuentes.base import ErrorFuente
    ids = []
    with pytest.raises(ErrorFuente) as e:
        ap.arrancar(_Sesion({"/actors/x~y/runs": _SinJson(201)}), "tok", "x~y", {}, 10, 0.01, on_ids=lambda r, d: ids.append((r, d)))
    assert "console.apify.com" in str(e.value) and ids == []
    s = _Sesion({"/actors/x~y/runs": [_SinJson(201), _corrida("READY", "r1", "d1")],
                 "/actor-runs/r1": [_corrida("SUCCEEDED", "r1", "d1")], "/datasets/d1/items": _Resp(200, [{"t": "a"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(2), "Leyendo")
    assert [c["estado"] for c in res["corridas"]] == [ap.ESTADO_NO_ARRANCO, "SUCCEEDED"] and res["resultados"] == 1
    assert "console.apify.com" in res["aviso"]


def test_arrancar_actor_pide_acceso_completo_no_es_token(esperas):
    """2026-10-01: `axesso_data~amazon-reviews-scraper` empezó a responder 403 con
    `error.type == "full-permission-actor-not-approved"` porque ahora pide acceso completo a la
    cuenta; el mensaje de siempre («Apify no aceptó el token») es falso acá y mandó a buscar un
    problema de APIFY_TOKEN que no existía. Nunca lleva la URL de aprobación ni el token."""
    import providers.apify as ap
    from nicho.fuentes.base import ErrorFuente
    cuerpo = {"error": {"type": "full-permission-actor-not-approved",
                        "message": "This Actor requires full access to your account. You must approve its "
                                   "permissions before running it: https://console.apify.com/actors/x~y/permissions"}}
    s = _Sesion({"/actors/x~y/runs": _Resp(403, cuerpo)})
    with pytest.raises(ErrorFuente) as e:
        ap.arrancar(s, "tok_secreto", "x~y", {}, 10, 0.01)
    assert "acceso completo" in str(e.value) and "token" not in str(e.value).lower()
    assert "console.apify.com" not in str(e.value) and "tok_secreto" not in str(e.value)


def test_arrancar_403_comun_sigue_siendo_el_de_token(esperas):
    """Un 403 sin ese `type` particular (otro motivo, o sin cuerpo legible) sigue dando el
    mensaje de siempre: solo `full-permission-actor-not-approved` tiene su propio aviso."""
    import providers.apify as ap
    from nicho.fuentes.base import ErrorFuente
    s = _Sesion({"/actors/x~y/runs": _Resp(403, {"error": {"type": "otro-motivo", "message": "nope"}})})
    with pytest.raises(ErrorFuente) as e:
        ap.arrancar(s, "tok", "x~y", {}, 10, 0.01)
    assert "token" in str(e.value).lower()
    s = _Sesion({"/actors/x~y/runs": _Resp(403, None)})           # sin cuerpo legible
    with pytest.raises(ErrorFuente) as e:
        ap.arrancar(s, "tok", "x~y", {}, 10, 0.01)
    assert "token" in str(e.value).lower()


def test_sondear_que_no_es_json_cuenta_como_lectura_mala(esperas):
    """Lo mismo en `sondear` (la fuente Apify manual de Nicho y los barridos de referentes)."""
    import providers.apify as ap
    from nicho.fuentes.base import ErrorFuente
    s = _Sesion({"/actor-runs/r0": [_SinJson(200), _corrida("SUCCEEDED", "r0", "d0")]})
    assert ap.sondear(s, "tok", "r0", "READY", "Leyendo") == "SUCCEEDED"
    s = _Sesion({"/actor-runs/r0": [_SinJson(200)] * ap.MAX_FALLOS_SONDEO})
    with pytest.raises(ErrorFuente) as e:
        ap.sondear(s, "tok", "r0", "READY", "Leyendo")
    assert "respuesta ilegible" in str(e.value) and "r0" in str(e.value)


def test_frase_estado_de_los_estados_ficticios():
    from providers import apify as ap
    assert ap.frase_estado(ap.ESTADO_NO_ARRANCO) == "no arrancó"
    assert ap.frase_estado(ap.ESTADO_SIN_ESTADO) == "no se pudo saber cómo terminó"
    assert ap.frase_estado("FAILED") == "terminó en FAILED"

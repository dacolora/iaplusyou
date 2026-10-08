# tests/test_meta_rend_graph.py
"""Lectura de Graph para el rendimiento de Meta (spec §6): paginación, informe
asíncrono, errores en palabras y nunca el token en un error."""
import pytest

from meta_rendimiento import graph

TOKEN = "EAAtoken-secreto-llave-de-prueba"


class _Resp:
    def __init__(self, datos, status=200):
        self._datos, self.status_code, self.ok = datos, status, status < 400
        self.content = b"x"

    def json(self):
        return self._datos


@pytest.fixture()
def http(monkeypatch):
    """Cola de respuestas por llamada; guarda (método, url, params)."""
    estado = {"respuestas": [], "llamadas": []}

    def _req(metodo):
        def f(url, params=None, timeout=None, data=None):
            estado["llamadas"].append((metodo, url, dict(params or data or {})))
            r = estado["respuestas"].pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return f
    monkeypatch.setattr(graph.requests, "get", _req("GET"))
    monkeypatch.setattr(graph.requests, "post", _req("POST"))
    return estado


def test_paginar_sigue_el_cursor_y_manda_el_token_solo_en_params(http):
    # Meta devuelve en `paging.next` una URL con el token adentro: no se sigue ni se registra,
    # se sigue el cursor `after` y el token va solo en params (nunca armado dentro de una URL).
    http["respuestas"] = [
        _Resp({"data": [{"id": 1}],
               "paging": {"cursors": {"after": "A"},
                          "next": "https://graph.facebook.com/v25.0/x?after=A&access_token=" + TOKEN}}),
        _Resp({"data": [{"id": 2}], "paging": {}})]
    assert graph.paginar("act_1/campaigns", TOKEN, {"limit": 500}) == [{"id": 1}, {"id": 2}]
    assert len(http["llamadas"]) == 2
    assert http["llamadas"][0][2]["access_token"] == TOKEN
    assert http["llamadas"][1][2]["access_token"] == TOKEN
    assert "after" not in http["llamadas"][0][2]
    assert http["llamadas"][1][2]["after"] == "A"
    assert http["llamadas"][1][2]["limit"] == 500
    for _metodo, url, _params in http["llamadas"]:
        assert TOKEN not in url and "access_token" not in url


def test_paginar_se_detiene_sin_next_o_sin_cursor_y_en_max_paginas(http):
    http["respuestas"] = [_Resp({"data": [{"id": 1}], "paging": {"next": "https://x", "cursors": {}}})]
    assert graph.paginar("act_1/ads", TOKEN) == [{"id": 1}]
    http["respuestas"] = [_Resp({"data": [{"id": n}], "paging": {"next": "https://x", "cursors": {"after": "A"}}})
                          for n in range(3)]
    assert graph.paginar("act_1/ads", TOKEN, max_paginas=3) == [{"id": 0}, {"id": 1}, {"id": 2}]


def test_error_de_limite_y_de_token_en_palabras_sin_token(http):
    http["respuestas"] = [_Resp({"error": {"code": 17, "message": f"User request limit reached {TOKEN}"}}, 400)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert e.value.limite and not e.value.token_roto and TOKEN not in str(e.value)
    assert e.value.codigo == 17
    http["respuestas"] = [_Resp({"error": {"code": 190, "message": "Error validating access token"}}, 400)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert e.value.token_roto and not e.value.limite


def test_error_de_meta_con_el_token_suelto_en_el_mensaje_no_lo_filtra(http):
    # El mensaje de Meta puede traer el token sin el prefijo «access_token=».
    http["respuestas"] = [_Resp({"error": {"code": 100, "message": f"Invalid parameter for {TOKEN} here"}}, 400)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert TOKEN not in str(e.value) and not e.value.limite and not e.value.token_roto
    http["respuestas"] = [_Resp({"error": {"code": 100, "message": f"bad access_token={TOKEN}&x=1"}}, 400)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert TOKEN not in str(e.value)


def test_red_caida_no_filtra_la_url(http):
    import requests
    http["respuestas"] = [requests.ConnectionError(f"https://graph.facebook.com/x?access_token={TOKEN}")]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert TOKEN not in str(e.value) and "ConnectionError" in str(e.value)


def test_post_manda_el_token_en_el_cuerpo(http):
    http["respuestas"] = [_Resp({"ok": True})]
    assert graph.post("act_1/insights", TOKEN, {"level": "ad"}) == {"ok": True}
    metodo, url, params = http["llamadas"][0]
    assert metodo == "POST" and url.endswith("/act_1/insights") and TOKEN not in url
    assert params["access_token"] == TOKEN and params["level"] == "ad"


def test_informe_asincrono_espera_y_pagina(http):
    http["respuestas"] = [_Resp({"report_run_id": "999"}),
                          _Resp({"async_status": "Job Running", "async_percent_completion": 40}),
                          _Resp({"async_status": "Job Completed", "async_percent_completion": 100}),
                          _Resp({"data": [{"ad_id": "a1"}], "paging": {}})]
    filas = graph.informe("act_1", TOKEN, {"level": "ad"}, dormir=lambda s: None)
    assert filas == [{"ad_id": "a1"}]
    assert http["llamadas"][0][0] == "POST" and http["llamadas"][0][1].endswith("/act_1/insights")
    assert http["llamadas"][-1][1].endswith("/999/insights")


def test_informe_fallido_o_eterno(http):
    http["respuestas"] = [_Resp({"report_run_id": "9"}), _Resp({"async_status": "Job Failed"})]
    with pytest.raises(graph.ErrorGraph):
        graph.informe("act_1", TOKEN, {}, dormir=lambda s: None)
    http["respuestas"] = [_Resp({"report_run_id": "9"})] + [_Resp({"async_status": "Job Running"}) for _ in range(5)]
    with pytest.raises(graph.ErrorGraph):
        graph.informe("act_1", TOKEN, {}, espera_max_s=3, intervalo_s=1, dormir=lambda s: None)


def test_informe_sin_report_run_id_falla_en_palabras(http):
    http["respuestas"] = [_Resp({})]
    with pytest.raises(graph.ErrorGraph):
        graph.informe("act_1", TOKEN, {}, dormir=lambda s: None)


def test_acciones_toma_el_primer_tipo_presente():
    lista = [{"action_type": "omni_purchase", "value": "5"}, {"action_type": "purchase", "value": "4"}]
    assert graph.acciones(lista, graph.TIPOS_COMPRA) == 4.0
    assert graph.acciones([{"action_type": "omni_purchase", "value": "5"}], graph.TIPOS_COMPRA) == 5.0
    assert graph.acciones(None, graph.TIPOS_COMPRA) == 0.0
    assert graph.acciones([{"action_type": "purchase", "value": "n/a"}], graph.TIPOS_COMPRA) == 0.0


def test_es_codigo_limite():
    import meta_errores
    assert meta_errores.es_codigo_limite(17) and meta_errores.es_codigo_limite("80000")
    assert not meta_errores.es_codigo_limite(190)
    assert not meta_errores.es_codigo_limite(None) and not meta_errores.es_codigo_limite("x")

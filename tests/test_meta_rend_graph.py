# tests/test_meta_rend_graph.py
"""Lectura de Graph para el rendimiento de Meta (spec §6): paginación, informe
asíncrono, errores en palabras y nunca el token en un error."""
import gc
import weakref

import pytest

from meta_rendimiento import graph

TOKEN = "EAAtoken-secreto-llave-de-prueba"


class _Resp:
    def __init__(self, datos, status=200, headers=None):
        self._datos, self.status_code, self.ok = datos, status, status < 400
        self.content = b"x"
        self.headers = headers or {}

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


def test_paginar_se_detiene_sin_next_o_sin_cursor(http):
    http["respuestas"] = [_Resp({"data": [{"id": 1}], "paging": {"next": "https://x", "cursors": {}}})]
    assert graph.paginar("act_1/ads", TOKEN) == [{"id": 1}]            # next sin cursor: no hay a dónde seguir
    http["respuestas"] = [_Resp({"data": [{"id": 1}], "paging": {"cursors": {"after": "A"}}})]
    assert graph.paginar("act_1/ads", TOKEN) == [{"id": 1}]            # cursor sin next: era la última


def _con_siguiente(n):
    return _Resp({"data": [{"id": n}], "paging": {"next": "https://x", "cursors": {"after": f"c{n}"}}})


def test_paginar_que_llega_al_tope_con_mas_paginas_sube_en_vez_de_devolver_a_medias(http):
    http["respuestas"] = [_con_siguiente(n) for n in range(3)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.paginar("act_1/ads", TOKEN, max_paginas=3)
    assert "más páginas de las esperadas" in str(e.value) and TOKEN not in str(e.value)
    assert len(http["llamadas"]) == 3    # leyó hasta el tope y no pidió una cuarta
    # Con callback también sube (quien llama no debe dar por completo un conjunto cortado).
    http["llamadas"].clear()
    http["respuestas"] = [_con_siguiente(n) for n in range(3)]
    with pytest.raises(graph.ErrorGraph):
        graph.paginar("act_1/ads", TOKEN, max_paginas=3, por_pagina=lambda filas: None)


def test_paginar_que_termina_justo_en_el_tope_devuelve_todo(http):
    # La tercera página es la última (sin next): llegar al tope sin que falte nada NO es un error.
    http["respuestas"] = [_con_siguiente(0), _con_siguiente(1), _Resp({"data": [{"id": 2}], "paging": {}})]
    assert graph.paginar("act_1/ads", TOKEN, max_paginas=3) == [{"id": 0}, {"id": 1}, {"id": 2}]
    http["respuestas"] = [_con_siguiente(0), _con_siguiente(1),
                          _Resp({"data": [{"id": 2}], "paging": {"cursors": {"after": "z"}}})]   # cursor sin next
    assert len(graph.paginar("act_1/ads", TOKEN, max_paginas=3)) == 3


def _muchos_datos(codigo=1):
    return _Resp({"error": {"code": codigo, "message": "Please reduce the amount of data you're asking for, "
                                                      "then retry your request"}}, 500)


def test_paginar_con_demasiados_datos_baja_el_limite_y_reintenta_el_mismo_cursor(http):
    http["respuestas"] = [
        _Resp({"data": [{"id": 1}], "paging": {"cursors": {"after": "A"}, "next": "https://x"}}),
        _muchos_datos(), _muchos_datos(),     # la página 2 falla con 100 y con 50 ...
        _Resp({"data": [{"id": 2}], "paging": {"cursors": {"after": "B"}, "next": "https://x"}}),   # ... y pasa con 25
        _Resp({"data": [{"id": 3}], "paging": {}})]
    params = {"limit": 100, "fields": "id"}
    assert graph.paginar("act_1/ads", TOKEN, params) == [{"id": 1}, {"id": 2}, {"id": 3}]
    pedidas = [(p.get("limit"), p.get("after")) for _m, _u, p in http["llamadas"]]
    # Mismo cursor «A» en los tres intentos de la segunda página; el límite reducido sigue en la tercera.
    assert pedidas == [(100, None), (100, "A"), (50, "A"), (25, "A"), (25, "B")]
    assert params == {"limit": 100, "fields": "id"}   # no se tocan los params del llamador


def test_paginar_tres_reducciones_como_maximo_y_el_codigo_2_tambien_cuenta(http):
    http["respuestas"] = [_muchos_datos(2) for _ in range(4)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.paginar("act_1/ads", TOKEN, {"limit": 500})
    assert e.value.codigo == 2
    assert [p["limit"] for _m, _u, p in http["llamadas"]] == [500, 250, 125, 62]   # 3 reducciones y se rinde
    # Con 100 se llega al piso de 25 antes: 100, 50, 25 y se rinde (nunca por debajo de 25).
    http["llamadas"].clear()
    http["respuestas"] = [_muchos_datos() for _ in range(3)]
    with pytest.raises(graph.ErrorGraph):
        graph.paginar("act_1/ads", TOKEN, {"limit": 100})
    assert [p["limit"] for _m, _u, p in http["llamadas"]] == [100, 50, 25]


def test_paginar_no_reintenta_un_limite_de_uso_ni_un_error_sin_limit(http):
    http["respuestas"] = [_Resp({"error": {"code": 17, "message": "User request limit reached"}}, 400)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.paginar("act_1/ads", TOKEN, {"limit": 500})
    assert e.value.limite and len(http["llamadas"]) == 1
    http["llamadas"].clear()
    http["respuestas"] = [_muchos_datos()]
    with pytest.raises(graph.ErrorGraph):
        graph.paginar("act_1/ads", TOKEN, {"fields": "id"})   # sin `limit` no hay qué reducir
    assert len(http["llamadas"]) == 1
    http["llamadas"].clear()
    http["respuestas"] = [_Resp({"error": {"code": 100, "message": "Invalid parameter"}}, 400)]
    with pytest.raises(graph.ErrorGraph):
        graph.paginar("act_1/ads", TOKEN, {"limit": 500})
    assert len(http["llamadas"]) == 1


class _Fila(dict):
    """Un dict que admite weakref: sirve para ver si alguien sigue sujetando una fila."""


def test_paginar_con_por_pagina_entrega_cada_pagina_y_no_acumula(http):
    def pagina(ids, siguiente):
        paging = {"next": "https://x", "cursors": {"after": siguiente}} if siguiente else {}
        return _Resp({"data": [_Fila(id=i) for i in ids], "paging": paging})
    http["respuestas"] = [pagina([1, 2], "A"), pagina([3, 4], "B"), pagina([5], None)]
    entregadas, vivas, refs = [], [], []

    def por_pagina(filas):
        gc.collect()
        # Al llegar esta página, las filas de las anteriores ya no deben estar sujetas por nadie: si paginar las
        # acumulara (aunque no las devuelva) seguirían vivas aquí.
        vivas.append(sum(1 for r in refs if r() is not None))
        entregadas.append([f["id"] for f in filas])
        refs.extend(weakref.ref(f) for f in filas)

    n = graph.paginar("act_1/ads", TOKEN, {"limit": 2}, por_pagina=por_pagina)
    assert n == 5 and isinstance(n, int)
    assert entregadas == [[1, 2], [3, 4], [5]]
    assert vivas == [0, 0, 0]


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


def test_informe_con_por_pagina_devuelve_la_cuenta_y_entrega_las_paginas(http):
    http["respuestas"] = [_Resp({"report_run_id": "999"}),
                          _Resp({"async_status": "Job Completed"}),
                          _Resp({"data": [{"ad_id": "a1"}, {"ad_id": "a2"}],
                                 "paging": {"cursors": {"after": "A"}, "next": "https://x"}}),
                          _Resp({"data": [{"ad_id": "a3"}], "paging": {}})]
    paginas = []
    n = graph.informe("act_1", TOKEN, {"level": "ad"}, dormir=lambda s: None, por_pagina=paginas.append)
    assert n == 3 and [[f["ad_id"] for f in p] for p in paginas] == [["a1", "a2"], ["a3"]]


def test_informe_usa_un_tope_de_paginas_holgado_y_sube_si_aun_asi_lo_pasa(http, monkeypatch):
    # Más de las 200 páginas de paginar por defecto: el informe no se corta a los ~12 000 filas.
    http["respuestas"] = ([_Resp({"report_run_id": "9"}), _Resp({"async_status": "Job Completed"})]
                          + [_con_siguiente(n) for n in range(250)] + [_Resp({"data": [{"id": 250}], "paging": {}})])
    assert graph.informe("act_1", TOKEN, {}, dormir=lambda s: None, por_pagina=lambda filas: None) == 251
    # Y si Meta aún tiene más después del tope, sube en vez de dejar al llamador escribir un conjunto cortado.
    monkeypatch.setattr(graph, "MAX_PAGINAS_INFORME", 3)
    http["respuestas"] = ([_Resp({"report_run_id": "9"}), _Resp({"async_status": "Job Completed"})]
                          + [_con_siguiente(n) for n in range(3)])
    with pytest.raises(graph.ErrorGraph):
        graph.informe("act_1", TOKEN, {}, dormir=lambda s: None, por_pagina=lambda filas: None)


def test_informe_sondea_con_una_espera_que_crece_hasta_30_segundos(http):
    http["respuestas"] = ([_Resp({"report_run_id": "9"})] + [_Resp({"async_status": "Job Running"}) for _ in range(9)]
                          + [_Resp({"async_status": "Job Completed"}), _Resp({"data": [], "paging": {}})])
    esperas = []
    assert graph.informe("act_1", TOKEN, {}, dormir=esperas.append) == []
    assert esperas == [5, 10, 15, 20, 25, 30, 30, 30, 30]


def test_informe_la_suma_de_las_esperas_no_pasa_del_maximo(http):
    http["respuestas"] = [_Resp({"report_run_id": "9"})] + [_Resp({"async_status": "Job Running"}) for _ in range(40)]
    esperas = []
    with pytest.raises(graph.ErrorGraph) as e:
        graph.informe("act_1", TOKEN, {}, espera_max_s=600, dormir=esperas.append)
    assert "tardó demasiado" in str(e.value)
    assert esperas[:7] == [5, 10, 15, 20, 25, 30, 30] and sum(esperas) == 600 and esperas[-1] <= 30
    # Con un máximo que no es múltiplo de la espera, la última se acorta en vez de pasarse.
    http["respuestas"] = [_Resp({"report_run_id": "9"})] + [_Resp({"async_status": "Job Running"}) for _ in range(9)]
    esperas.clear()
    with pytest.raises(graph.ErrorGraph):
        graph.informe("act_1", TOKEN, {}, espera_max_s=12, intervalo_s=5, dormir=esperas.append)
    assert esperas == [5, 7]


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


# ------------------------------------------------- freno de uso (ruling R22) ---

def _cab(**kv):
    return {k.replace("_", "-"): v for k, v in kv.items()}


def test_uso_de_la_app_en_75_o_mas_frena_con_limite_y_espera_por_defecto(http):
    import json
    http["respuestas"] = [_Resp({"id": "act_1"}, headers=_cab(
        x_app_usage=json.dumps({"call_count": 76, "total_cputime": 3, "total_time": 10})))]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert e.value.limite and not e.value.token_roto
    assert e.value.espera_min == 30 and TOKEN not in str(e.value)
    assert "límite de uso" in str(e.value)


def test_uso_de_negocio_y_de_cuenta_tambien_frenan_y_traen_la_espera_de_meta(http):
    import json
    negocio = {"123": [{"type": "ads_management", "call_count": 10, "total_cputime": 80, "total_time": 5,
                        "estimated_time_to_regain_access": 45}]}
    http["respuestas"] = [_Resp({"id": 1}, headers=_cab(x_business_use_case_usage=json.dumps(negocio)))]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert e.value.limite and e.value.espera_min == 45
    http["respuestas"] = [_Resp({"id": 1}, headers=_cab(x_ad_account_usage=json.dumps({"acc_id_util_pct": 75})))]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert e.value.limite and e.value.espera_min == 30   # sin estimated_time_to_regain_access: 30 por defecto


def test_uso_por_debajo_de_75_deja_pasar_la_respuesta(http):
    import json
    http["respuestas"] = [_Resp({"id": "act_1"}, headers=_cab(
        x_app_usage=json.dumps({"call_count": 74.9, "total_cputime": 20, "total_time": 10}),
        x_ad_account_usage=json.dumps({"acc_id_util_pct": 12})))]
    assert graph.get("act_1", TOKEN) == {"id": "act_1"}


def test_cabeceras_de_uso_mal_formadas_se_ignoran(http):
    http["respuestas"] = [_Resp({"id": "act_1"}, headers=_cab(
        x_app_usage="no es json", x_business_use_case_usage='["raro"]', x_ad_account_usage='{"acc_id_util_pct": "x"}'))]
    assert graph.get("act_1", TOKEN) == {"id": "act_1"}
    http["respuestas"] = [_Resp({"id": "act_1"}, headers=_cab(x_app_usage="[1, 2]"))]   # JSON válido pero no un objeto
    assert graph.get("act_1", TOKEN) == {"id": "act_1"}
    assert graph.uso(None) == (0.0, None)


def test_un_error_de_limite_de_meta_trae_la_espera_de_sus_cabeceras(http):
    import json
    http["respuestas"] = [_Resp({"error": {"code": 17, "message": "limit"}}, 400, headers=_cab(
        x_business_use_case_usage=json.dumps({"1": [{"estimated_time_to_regain_access": 12}]})))]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert e.value.limite and e.value.codigo == 17 and e.value.espera_min == 12


def test_el_uso_alto_a_mitad_de_una_paginacion_detiene_la_lectura(http):
    import json
    alto = _cab(x_app_usage=json.dumps({"call_count": 90}))
    http["respuestas"] = [_Resp({"data": [{"id": 1}], "paging": {"next": "https://x", "cursors": {"after": "A"}}}),
                          _Resp({"data": [{"id": 2}], "paging": {}}, headers=alto)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.paginar("act_1/ads", TOKEN)
    assert e.value.limite and len(http["llamadas"]) == 2


# ---------------------------------------------------- edges y cursores ---

def test_el_token_nunca_viaja_a_una_url_completa(http):
    # Un edge es siempre relativo: una URL completa (p. ej. un paging.next ajeno) se trata como ruta de Graph,
    # nunca como destino, así el token solo llega a graph.facebook.com.
    http["respuestas"] = [_Resp({"ok": 1})]
    graph.get("https://evil.example/steal", TOKEN)
    _metodo, url, _params = http["llamadas"][0]
    assert url.startswith(graph.meta_conexion.GRAPH_URL + "/") and "evil.example" in url.split("/", 3)[3]
    assert url.split("/")[2] == "graph.facebook.com"


def test_informe_con_report_run_id_que_no_es_numerico_no_se_usa_como_edge(http):
    http["respuestas"] = [_Resp({"report_run_id": "../me/accounts"})]
    with pytest.raises(graph.ErrorGraph):
        graph.informe("act_1", TOKEN, {}, dormir=lambda s: None)
    assert len(http["llamadas"]) == 1          # solo el POST: nunca sondeó esa «ruta»
    http["llamadas"].clear()
    http["respuestas"] = [_Resp({"report_run_id": 12345}), _Resp({"async_status": "Job Completed"}),
                          _Resp({"data": [], "paging": {}})]
    assert graph.informe("act_1", TOKEN, {}, dormir=lambda s: None) == []
    assert http["llamadas"][1][1].endswith("/12345")


def test_la_ultima_pagina_real_de_meta_cursor_sin_next_se_detiene_tras_una_llamada(http):
    # Meta en la última página manda cursors.after pero NO next: no hay una segunda llamada.
    http["respuestas"] = [_Resp({"data": [{"id": 1}], "paging": {"cursors": {"before": "B", "after": "A"}}})]
    assert graph.paginar("act_1/ads", TOKEN) == [{"id": 1}]
    assert len(http["llamadas"]) == 1

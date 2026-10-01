import json
import os

import pytest

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _fixture(nombre):
    with open(os.path.join(RAIZ, "fixtures", "nicho", nombre), encoding="utf-8") as f:
        return json.load(f)


def test_registro_de_actores_y_estimado():
    from nicho.fuentes import apify_actores as aa, base
    assert set(aa.ACTORES) == {"amazon_resenas", "tiktok_comentarios"}
    # precios del plan FREE de Apify, reverificados 2026-10-01 (antes 0.003/0.0005, por debajo de lo real)
    assert aa.ACTORES["amazon_resenas"]["actor"] == "junglee~amazon-reviews-scraper" and aa.ACTORES["amazon_resenas"]["usd_por_resultado"] == 0.006
    assert aa.ACTORES["tiktok_comentarios"]["actor"] == "clockworks~tiktok-comments-scraper" and aa.ACTORES["tiktok_comentarios"]["usd_por_resultado"] == 0.00125
    assert aa.estimar("amazon_resenas", 200) == {"actor": "junglee~amazon-reviews-scraper", "max_resultados": 200, "usd": 1.2}
    assert aa.estimar("tiktok_comentarios", 5000)["max_resultados"] == aa.MAX_RESULTADOS and aa.estimar("tiktok_comentarios", 5000)["usd"] == 1.25
    assert aa.estimar("tiktok_comentarios", "abc")["max_resultados"] == 1 and aa.estimar("tiktok_comentarios", 1)["usd"] == 0.01   # centavo hacia arriba
    with pytest.raises(base.ErrorFuente):
        aa.estimar("magia", 10)


def test_estimar_minimo_de_junglee_y_precios_reales():
    """Precios reales del plan FREE verificados 2026-10-01: junglee US$ 0,006 por reseña con un
    techo mínimo de US$ 0,50 POR CORRIDA (Apify rechaza `maxTotalChargeUsd` menor con 400
    `max-total-charge-usd-below-minimum`) -- pero desde la prueba real en producción del mismo
    día (run `wpny9jQYLztteag8Z`, el plan FREE solo lee 1 link y 10 reseñas por corrida) ese
    mínimo YA NO infla lo que `estimar()` muestra antes del clic (eso exageraría el costo de una
    corrida chica que nunca lo iba a cobrar): solo entra al armar la corrida de verdad
    (`corridas()`, ver ese test). clockworks US$ 0,00125 por comentario, sin mínimo."""
    from nicho.fuentes import apify_actores as aa
    assert aa.estimar("amazon_resenas", 10)["usd"] == 0.06            # 10 × 0.006, el peor caso real
    assert aa.estimar("amazon_resenas", 500)["usd"] == 3.0            # 500 × 0.006 = 3.0, ya sobre el mínimo igual
    assert aa.estimar("tiktok_comentarios", 1000)["usd"] == 1.25      # sin mínimo: 1000 × 0.00125


def test_corridas_amazon_una_por_link_con_el_minimo_y_memoria():
    """Fix 3 (2026-10-01): junglee en el plan FREE solo lee 1 link y entrega 10 reseñas por
    corrida, así que `corridas()` manda UNA corrida POR LINK (nunca junta varios productUrls),
    recortada al tope del actor, a 2048 MB y con el mínimo de Apify en lo que SÍ se manda
    (`max_usd`) -- nunca en el estimado de la puerta."""
    from nicho.fuentes import apify_actores as aa
    links = ["https://www.amazon.com/dp/B0TEST0001", "https://www.amazon.com/dp/B0TEST0002"]
    cs = aa.corridas("amazon_resenas", links, 500)
    assert len(cs) == 2
    assert cs[0]["entrada"] == {"productUrls": [{"url": links[0]}], "maxReviews": 10, "includeGdprSensitive": False}
    assert cs[1]["entrada"]["productUrls"] == [{"url": links[1]}]
    assert [c["max_items"] for c in cs] == [10, 10] and [c["max_usd"] for c in cs] == [0.5, 0.5]
    assert [c["memoria_mb"] for c in cs] == [2048, 2048] and [c["etiqueta"] for c in cs] == links
    # un solo link: una sola corrida, igual de recortada
    uno = aa.corridas("amazon_resenas", links[:1], 5)
    assert len(uno) == 1 and uno[0]["max_items"] == 5 and uno[0]["max_usd"] == 0.5     # 5 × 0.006 = 0.03 < el mínimo
    # TikTok sigue con UNA corrida para todos los links, como siempre (sin mínimo ni memoria)
    tiktok = ["https://www.tiktok.com/@a/video/1", "https://www.tiktok.com/@a/video/2"]
    ct = aa.corridas("tiktok_comentarios", tiktok, 150)
    assert len(ct) == 1 and ct[0]["entrada"]["postURLs"] == tiktok and ct[0]["max_items"] == 150
    assert ct[0]["max_usd"] == 0.19 and "memoria_mb" not in ct[0]                       # 150 × 0.00125 = 0.1875 -> 0.19


def test_validar_links_y_entradas():
    from nicho.fuentes import apify_actores as aa, base
    amazon = ["https://www.amazon.com/HappyFlops-Slippers/dp/B0TEST1234/ref=x", "https://www.amazon.se/gp/product/B0TEST9999"]
    assert aa.validar_links("amazon_resenas", amazon + ["", "  "]) == amazon
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("amazon_resenas", ["https://www.amazon.com/s?k=slippers"])
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("tiktok_comentarios", [])
    tiktok = ["https://www.tiktok.com/@shop/video/7399000000000000000", "https://vm.tiktok.com/ZMabc/"]
    assert aa.validar_links("tiktok_comentarios", tiktok) == tiktok
    assert aa.entrada("amazon_resenas", amazon, 150) == {"productUrls": [{"url": amazon[0]}, {"url": amazon[1]}], "maxReviews": 75, "includeGdprSensitive": False}
    assert aa.entrada("tiktok_comentarios", tiktok, 150) == {"postURLs": tiktok, "commentsPerPost": 75, "maxRepliesPerComment": 0}
    assert aa.entrada("tiktok_comentarios", tiktok[:1], 7)["commentsPerPost"] == 7
    # Extensión: URLs de Amazon que deben aceptarse
    assert aa.validar_links("amazon_resenas", ["https://www.amazon.com/dp/B0TEST1234"]) == ["https://www.amazon.com/dp/B0TEST1234"]
    assert aa.validar_links("amazon_resenas", ["https://www.amazon.co.uk/dp/B0TEST1234?ref=x"]) == ["https://www.amazon.co.uk/dp/B0TEST1234?ref=x"]
    assert aa.validar_links("amazon_resenas", ["https://amazon.de/Marca/Nombre-largo/dp/B0TEST1234/"]) == ["https://amazon.de/Marca/Nombre-largo/dp/B0TEST1234/"]
    # URLs que deben rechazarse
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("amazon_resenas", ["https://www.amazon.com/s?k=dp/B0TEST1234"])
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("amazon_resenas", ["https://www.amazon.com/dp/B0TEST12345"])  # 11 caracteres
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("amazon_resenas", ["https://www.amazon.com/gp/help/customer"])


def test_entrada_amazon_reparte_el_tope_entre_los_links():
    """C1: `maxReviews` es por URL de producto, así que con 3 links y tope 100 el
    actor no puede traer (ni cobrar) 300 reseñas."""
    from nicho.fuentes import apify_actores as aa
    tres = ["https://www.amazon.com/dp/B0TEST0001", "https://www.amazon.com/dp/B0TEST0002", "https://www.amazon.com/dp/B0TEST0003"]
    assert aa.entrada("amazon_resenas", tres, 100)["maxReviews"] == 34
    assert aa.entrada("amazon_resenas", tres[:1], 100)["maxReviews"] == 100
    assert aa.entrada("amazon_resenas", tres, 2)["maxReviews"] == 1                  # nunca baja de 1


def test_leer_items():
    from nicho.fuentes import apify_actores as aa
    a = [aa.leer_item("amazon_resenas", it) for it in _fixture("apify_amazon_items.json")]
    assert a[1] is None
    assert a[0] == {"fuente_id": "R1ABCDEFG", "texto": "Finally no heel pain. I stand 10 hours a day and these are the first slippers that hold up.",
                    "url": "https://www.amazon.com/gp/customer-reviews/R1ABCDEFG/", "contexto": "ASIN B0TEST1234", "puntuacion": 5,
                    "fecha": "2022-02-03T00:00:00", "extra": {"asin": "B0TEST1234"}}
    assert a[2]["fuente_id"] is None and a[2]["fecha"] is None and a[2]["puntuacion"] == "2" and a[2]["texto"] == "Meh. Sole flattened in a month"
    t = [aa.leer_item("tiktok_comentarios", it) for it in _fixture("apify_tiktok_items.json")]
    assert t[1] is None
    assert t[0] == {"fuente_id": "7399984975553086214", "texto": "these saved my feet at work fr",
                    "url": "https://www.tiktok.com/@shop/video/7399000000000000000", "contexto": None, "puntuacion": 246,
                    "fecha": "2024-08-06T11:21:16.000Z", "extra": {"video": "https://www.tiktok.com/@shop/video/7399000000000000000"}}


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
def entorno_apify(monkeypatch):
    from nicho.fuentes import _http
    monkeypatch.setenv("APIFY_TOKEN", "apify_secreto")
    esperas = []
    monkeypatch.setattr(_http, "dormir", lambda s: esperas.append(s))
    return esperas


def test_normalizar_params_apify():
    from nicho.fuentes import apify, base
    p = apify.normalizar_params({"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@a/video/1", " "], "max_resultados": "50000"})
    assert p == {"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@a/video/1"], "max_resultados": 1000}
    with pytest.raises(base.ErrorFuente):
        apify.normalizar_params({"actor": "magia", "links": ["https://www.tiktok.com/@a/video/1"]})
    with pytest.raises(base.ErrorFuente):
        apify.normalizar_params({"actor": "amazon_resenas", "links": ["https://www.tiktok.com/@a/video/1"]})


def test_recolectar_corre_sondea_y_baja_el_dataset(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify
    s = _Sesion({"/actors/clockworks~tiktok-comments-scraper/runs": _Resp(201, {"data": {"id": "run1", "status": "READY", "defaultDatasetId": "ds1"}}),
                 "/actor-runs/run1": [_Resp(200, {"data": {"id": "run1", "status": "RUNNING", "defaultDatasetId": "ds1"}}),
                                      _Resp(200, {"data": {"id": "run1", "status": "SUCCEEDED", "defaultDatasetId": "ds1"}})],
                 "/datasets/ds1/items": _Resp(200, _fixture("apify_tiktok_items.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    etapas = []
    f = apify.FuenteApify()
    links = ["https://www.tiktok.com/@shop/video/7399000000000000000", "https://www.tiktok.com/@shop/video/7399000000000000001"]
    lista = list(f.recolectar({"actor": "tiktok_comentarios", "links": links, "max_resultados": 100}, avanzar=lambda e, d=None: etapas.append((e, d))))
    assert [c["fuente_id"] for c in lista] == ["7399984975553086214", "7399984975553086216"] and f.resultados == 3   # 3 ítems crudos, 2 con texto
    assert lista[0]["puntuacion"] == 246 and lista[0]["fecha"] == "2024-08-06T11:21:16" and lista[0]["url"].startswith("https://www.tiktok.com/")
    metodo, url, kw = s.llamadas[0]
    assert metodo == "POST" and url == apify.URL_API + "/actors/clockworks~tiktok-comments-scraper/runs"
    assert kw["json"] == {"postURLs": links, "commentsPerPost": 50, "maxRepliesPerComment": 0}
    assert kw["params"] == {"timeout": apify.MAX_ESPERA_S, "maxItems": 100, "maxTotalChargeUsd": 0.13}    # 100 × 0.00125 = 0.125 -> 0.13
    assert kw["headers"]["Authorization"] == "Bearer apify_secreto"
    assert all("apify_secreto" not in u for _, u, _ in s.llamadas)                  # el token nunca va en la URL
    assert s.llamadas[-1][1] == apify.URL_API + "/datasets/ds1/items" and s.llamadas[-1][2]["params"] == {"clean": "true", "format": "json", "limit": 100}
    assert entorno_apify == [apify.PAUSA_SONDEO, apify.PAUSA_SONDEO]
    assert etapas[0][0] == "Buscando" and any(e == "Leyendo comentarios" and "RUNNING" in (d or "") for e, d in etapas)
    assert all("run1" in (d or "") for e, d in etapas if e == "Leyendo comentarios")   # la fila de la tarea conserva el id de la corrida
    assert f.run_id == "run1" and f.dataset_id == "ds1" and f.aviso == ""
    assert f.estimar({"actor": "tiktok_comentarios", "links": links, "max_resultados": 100}) == {"actor": "clockworks~tiktok-comments-scraper", "max_resultados": 100, "usd": 0.13}


def test_el_post_de_la_corrida_lleva_los_topes_de_cobro(entorno_apify, monkeypatch):
    """C1: además del tope por link, la corrida lleva los topes de cobro del lado de Apify
    (maxItems y maxTotalChargeUsd) y, para junglee, la memoria (2048 MB). El plan FREE solo
    entrega 10 reseñas por corrida (`max_por_link`): aunque se aprueben 30, la corrida pide como
    mucho 10; 10 × 0.006 = 0.06, bajo el mínimo de junglee, así que lo que se manda es el mínimo
    (0.50), nunca menos -- el estimado de la puerta (`estimar`), en cambio, es el peor caso real
    de las 30, sin ese mínimo."""
    from nicho.fuentes import _http, apify, apify_actores
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_t", "status": "SUCCEEDED", "defaultDatasetId": "ds_t"}}),
                 "/datasets/ds_t/items": _Resp(200, [])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 30}))
    assert s.llamadas[0][2]["params"]["maxTotalChargeUsd"] >= 0.5
    assert s.llamadas[0][2]["params"] == {"timeout": apify.MAX_ESPERA_S, "maxItems": 10, "maxTotalChargeUsd": 0.5, "memory": 2048}
    assert apify_actores.estimar("amazon_resenas", 30)["usd"] == 0.18          # 30 × 0.006, el peor caso real (sin el mínimo)


def test_recolectar_amazon_dos_links_son_dos_corridas(entorno_apify, monkeypatch):
    """Fix 3: con varios links de Amazon, `FuenteApify.recolectar` lanza UNA corrida POR LINK (el
    plan FREE de junglee solo lee 1 link por corrida) y junta los comentarios de los dos datasets;
    `corridas` (NEW) trae los dos registros con sus run ids, para rastrear el cobro. TikTok, en
    cambio, sigue mandando los links de a uno en UNA sola corrida (`test_recolectar_corre_sondea_y_baja_el_dataset`)."""
    from nicho.fuentes import _http, apify
    links = ["https://www.amazon.com/dp/B0TEST0001", "https://www.amazon.com/dp/B0TEST0002"]
    s = _Sesion({"/actors/junglee~amazon-reviews-scraper/runs": [_Resp(201, {"data": {"id": "run_1", "status": "SUCCEEDED", "defaultDatasetId": "ds_1"}}),
                                                                 _Resp(201, {"data": {"id": "run_2", "status": "SUCCEEDED", "defaultDatasetId": "ds_2"}})],
                 "/datasets/ds_1/items": _Resp(200, _fixture("apify_amazon_items.json")[:1]),
                 "/datasets/ds_2/items": _Resp(200, _fixture("apify_amazon_items.json")[2:])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    lista = list(f.recolectar({"actor": "amazon_resenas", "links": links, "max_resultados": 20}))
    assert len(lista) == 2 and f.resultados == 2                              # 1 ítem de cada dataset, los dos con texto
    posts = [(u, kw) for m, u, kw in s.llamadas if m == "POST"]
    assert len(posts) == 2
    assert posts[0][1]["json"]["productUrls"] == [{"url": links[0]}] and posts[1][1]["json"]["productUrls"] == [{"url": links[1]}]
    assert all(kw["params"]["memory"] == 2048 for _, kw in posts)
    assert [c["run_id"] for c in f.corridas] == ["run_1", "run_2"] and f.run_id == "run_1"
    assert f.aviso == ""


def test_recolectar_amazon_exito_salta_basura_y_vacios(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify
    # Escenario 1: éxito con Amazon, datos + basura
    s = _Sesion({"/actors/junglee~amazon-reviews-scraper/runs": _Resp(201, {"data": {"id": "run_a", "status": "READY", "defaultDatasetId": "ds_a"}}),
                 "/actor-runs/run_a": [_Resp(200, {"data": {"id": "run_a", "status": "RUNNING", "defaultDatasetId": "ds_a"}}),
                                       _Resp(200, {"data": {"id": "run_a", "status": "SUCCEEDED", "defaultDatasetId": "ds_a"}})],
                 "/datasets/ds_a/items": _Resp(200, _fixture("apify_amazon_items.json") + ["basura", 42])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    lista = list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 100}))
    assert len(lista) == 2
    assert lista[0]["fuente_id"] == "R1ABCDEFG"
    assert lista[0]["puntuacion"] == 5
    assert lista[0]["fecha"] == "2022-02-03T00:00:00"
    assert lista[1]["texto"] == "Meh. Sole flattened in a month"
    assert f.resultados == 5              # Apify cobra por ítem del dataset, también los vacíos y la basura
    # Escenario 2: dataset vacío
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_b", "status": "READY", "defaultDatasetId": "ds_b"}}),
                 "/actor-runs/run_b": [_Resp(200, {"data": {"id": "run_b", "status": "SUCCEEDED", "defaultDatasetId": "ds_b"}})],
                 "/datasets/ds_b/items": _Resp(200, [])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    lista = list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 100}))
    assert lista == []
    assert f.resultados == 0


def test_recolectar_corrida_fallida_y_llave_rechazada(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify, base
    # FAILED y dataset vacío: no hay nada que guardar, pero el error dice la corrida.
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run2", "status": "READY", "defaultDatasetId": "ds2"}}),
                 "/actor-runs/run2": [_Resp(200, {"data": {"id": "run2", "status": "FAILED", "defaultDatasetId": "ds2"}})],
                 "/datasets/ds2/items": _Resp(200, [])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    with pytest.raises(base.ErrorFuente) as e:
        list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "FAILED" in str(e.value) and "run2" in str(e.value) and f.resultados == 0 and f.run_id == "run2"
    s = _Sesion({"/runs": _Resp(401, {"error": {"type": "token-not-found", "message": "Authentication token is not valid"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "APIFY_TOKEN" in str(e.value) and "apify_secreto" not in str(e.value)
    s = _Sesion({"/runs": _Resp(400, {"error": {"type": "invalid-input", "message": "Field productUrls is required"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "productUrls is required" in str(e.value)


def test_corrida_sin_dataset_conserva_el_id(entorno_apify, monkeypatch):
    """C2: si Apify arrancó la corrida pero no dijo el dataset, el id igual queda en la fuente (la
    corrida pudo cobrar) y sale en el mensaje -- aunque el lote la siga sondeando (ya con el id) y
    esta SÍ termine en SUCCEEDED, sin dataset no hay nada que leer: sigue siendo el "sin
    resultados" de siempre, pero `resultados` ahora cae al tope de ESA corrida (10, el máximo de
    junglee en el plan FREE) en vez de perderse en 0, para no subregistrar un cobro."""
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_x", "status": "READY"}}),
                 "/actor-runs/run_x": _Resp(200, {"data": {"status": "SUCCEEDED"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    with pytest.raises(base.ErrorFuente) as e:
        list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "run_x" in str(e.value) and f.run_id == "run_x" and f.resultados == 10


def test_recolectar_vence_por_tiempo(entorno_apify, monkeypatch):
    """C2: al vencer el reloj local el dataset se lee igual (la corrida ya se pagó);
    vacío, el error dice los 20 min y la corrida. El lote (`correr_lote`) sondea una corrida
    hasta pasar el tope local (no al llegar a él): una vuelta más que el `sondear()` viejo."""
    from nicho.fuentes import _http, apify, base
    corriendo = _Resp(200, {"data": {"id": "run3", "status": "RUNNING", "defaultDatasetId": "ds3"}})
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run3", "status": "READY", "defaultDatasetId": "ds3"}}), "/actor-runs/run3": corriendo,
                 "/datasets/ds3/items": _Resp(200, [])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    with pytest.raises(base.ErrorFuente) as e:
        list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "20 min" in str(e.value) and "run3" in str(e.value) and f.resultados == 0
    assert len(entorno_apify) == int(apify.MAX_ESPERA_S // apify.PAUSA_SONDEO) + 1
    assert s.llamadas[-1][1] == apify.URL_API + "/datasets/ds3/items"


def test_recolectar_estado_fallido_con_items_guarda_lo_leido_y_avisa(entorno_apify, monkeypatch):
    """C2 (a): una corrida FAILED que alcanzó a dejar ítems se cobró igual, así que
    se guardan y la tarea termina con aviso (no con error)."""
    from nicho.fuentes import _http, apify
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_f", "status": "READY", "defaultDatasetId": "ds_f"}}),
                 "/actor-runs/run_f": [_Resp(200, {"data": {"id": "run_f", "status": "FAILED", "defaultDatasetId": "ds_f"}})],
                 "/datasets/ds_f/items": _Resp(200, _fixture("apify_tiktok_items.json")[:1] + _fixture("apify_tiktok_items.json")[2:])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    lista = list(f.recolectar({"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@shop/video/7399000000000000000"], "max_resultados": 50}))
    assert len(lista) == 2 and f.resultados == 2
    assert "FAILED" in f.aviso and "run_f" in f.aviso and "2 resultado(s)" in f.aviso


def test_recolectar_dataset_ilegible_cae_al_itemcount(entorno_apify, monkeypatch):
    """C2 (b): si el dataset no se puede leer, `resultados` sale del itemCount para
    que el gasto quede registrado, y el error dice corrida y dataset."""
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_d", "status": "SUCCEEDED", "defaultDatasetId": "ds_d"}}),
                 "/datasets/ds_d/items": [_Resp(503)] * (2 * apify.INTENTOS_DATASET),      # pedir() reintenta cada 5xx una vez
                 "/datasets/ds_d": _Resp(200, {"data": {"id": "ds_d", "itemCount": 7}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    with pytest.raises(base.ErrorFuente) as e:
        list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 50}))
    assert "run_d" in str(e.value) and "ds_d" in str(e.value) and "503" in str(e.value)
    assert f.resultados == 7
    assert len([1 for _, u, _ in s.llamadas if u.endswith("/items")]) == 2 * apify.INTENTOS_DATASET


def test_recolectar_sin_itemcount_registra_el_tope_aprobado(entorno_apify, monkeypatch):
    """C2 (b): ni ítems ni itemCount -> `resultados` cae al tope de la corrida (registrar
    de más es mejor que perder el registro de un cobro). Con junglee en el plan FREE esa
    corrida pide como mucho 10 (`max_por_link`), no los 50 aprobados -- ese es el tope real
    que Apify pudo llegar a cobrar en ESA corrida."""
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_e", "status": "SUCCEEDED", "defaultDatasetId": "ds_e"}}),
                 "/datasets/ds_e/items": [_Resp(503)] * (2 * apify.INTENTOS_DATASET),
                 "/datasets/ds_e": [_Resp(500), _Resp(500)]})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    with pytest.raises(base.ErrorFuente):
        list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 50}))
    assert f.resultados == 10


def test_sondeo_tolera_fallos_pasajeros_y_se_rinde_con_la_corrida(entorno_apify, monkeypatch):
    """C2 (c)/I4: un 503 pasajero leyendo el estado no abandona una corrida pagada;
    MAX_FALLOS_SONDEO seguidos sí se rinde del sondeo -- pero el lote (`correr_lote`) igual
    intenta leer el dataset de una corrida ya pagada aunque no se sepa cómo terminó (nunca se
    abandona lo que ya pudo cobrar), así que si el dataset SÍ se puede leer no es error, queda
    como aviso (`test_apify_lote.test_lote_sondeo_tolera_fallos_y_se_rinde_por_corrida` prueba
    ya el mecanismo; acá solo se confirma que `FuenteApify` lo expone igual)."""
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_s", "status": "READY", "defaultDatasetId": "ds_s"}}),
                 "/actor-runs/run_s": [_Resp(503), _Resp(503), _Resp(503), _Resp(503),          # dos lecturas malas seguidas
                                       _Resp(200, {"data": {"status": "RUNNING"}}),
                                       _Resp(200, {"data": {"status": "SUCCEEDED"}})],
                 "/datasets/ds_s/items": _Resp(200, _fixture("apify_tiktok_items.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    lista = list(f.recolectar({"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@shop/video/7399000000000000000"], "max_resultados": 50}))
    assert len(lista) == 2 and f.resultados == 3 and f.aviso == ""
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_s2", "status": "READY", "defaultDatasetId": "ds_s2"}}),
                 "/actor-runs/run_s2": [_Resp(503)] * (2 * (apify.MAX_FALLOS_SONDEO + 1)),
                 "/datasets/ds_s2/items": _Resp(200, _fixture("apify_tiktok_items.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    lista = list(f.recolectar({"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@shop/video/7399000000000000000"], "max_resultados": 50}))
    assert len(lista) == 2 and f.resultados == 3                     # el dataset se pudo leer aunque el sondeo se rindiera
    assert "run_s2" in f.aviso and "no se pudo saber cómo terminó" in f.aviso and "apify_secreto" not in f.aviso
    assert len([1 for _, u, _ in s.llamadas if "/actor-runs/" in u]) == 2 * apify.MAX_FALLOS_SONDEO


def test_resultados_cuenta_items_crudos(entorno_apify, monkeypatch):
    """C2 (d): `resultados` es lo que Apify cobra (ítems del dataset), no lo que
    entra a la base: 3 ítems, uno sin texto -> 3 cobrados, 2 guardados."""
    from nicho.fuentes import _http, apify
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_c", "status": "SUCCEEDED", "defaultDatasetId": "ds_c"}}),
                 "/datasets/ds_c/items": _Resp(200, _fixture("apify_tiktok_items.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    lista = list(f.recolectar({"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@shop/video/7399000000000000000"], "max_resultados": 50}))
    assert len(lista) == 2 and f.resultados == 3


def test_dataset_con_cuerpo_ilegible_cae_al_itemcount(entorno_apify, monkeypatch):
    """Un 200 con JSON roto cuenta como intento fallido: se agotan los intentos,
    `resultados` sale del itemCount y el error lleva corrida y dataset."""
    from nicho.fuentes import _http, apify, base

    class _RespRota(_Resp):
        def json(self):
            raise ValueError("cuerpo ilegible")

    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run_j", "status": "SUCCEEDED", "defaultDatasetId": "ds_j"}}),
                 "/datasets/ds_j/items": [_RespRota(200)] * apify.INTENTOS_DATASET,
                 "/datasets/ds_j": _Resp(200, {"data": {"id": "ds_j", "itemCount": 4}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    with pytest.raises(base.ErrorFuente) as e:
        list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 50}))
    assert "run_j" in str(e.value) and "ds_j" in str(e.value) and "ilegible" in str(e.value)
    assert f.resultados == 4
    assert len([1 for _, u, _ in s.llamadas if u.endswith("/items")]) == apify.INTENTOS_DATASET


def test_probar_y_llave_faltante(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/users/me": _Resp(200, {"data": {"username": "acme"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    assert apify.FuenteApify().probar() == {"ok": True, "detalle": "Apify aceptó el token."}
    assert s.llamadas[0][2]["headers"]["Authorization"] == "Bearer apify_secreto"
    monkeypatch.delenv("APIFY_TOKEN")
    assert apify.FuenteApify().probar()["ok"] is False
    with pytest.raises(base.ErrorFuente):
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))


def test_registro_apify():
    from nicho import fuentes
    assert fuentes.por_tipo("apify").tipo == "apify" and fuentes.por_tipo("apify").de_pago is True

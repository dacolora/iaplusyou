import json
from datetime import date

import pytest

import providers.apify as apify_api
import referentes.fuentes.apify_adlibrary as apify_adlibrary
from referentes.fuentes.base import ErrorFuente

FIXTURE_ITEM = json.load(open("tests/fixtures/apify_facebook_ads_scraper_item.json"))


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


def test_estimar_delega_al_registro_de_actores():
    r = apify_adlibrary.estimar({}, 200)
    assert r["usd_fuente"] == 1.16       # 200 × 0.0058
    assert r["resultados"] == 200


def test_traer_sin_token_lanza_error_fuente(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(ErrorFuente):
        next(apify_adlibrary.traer({"modo": "palabra", "palabra": "sandalias", "idioma": "es", "pais": "CO"}, 10, lambda **kw: None))


def test_traer_modo_palabra_arma_la_url_de_ad_library(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "palabra", "palabra": "sandalias de cuero", "idioma": "es", "pais": "CO",
                                 "formato": "imagen", "solo_activos": True}, 5, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    metodo, url, kw = sesion.llamadas[0]
    assert url == f"{apify_api.URL_API}/actors/apify~facebook-ads-scraper/runs"
    body = kw["json"]
    ad_lib_url = body["startUrls"][0]["url"]
    assert "country=CO" in ad_lib_url
    assert "q=%22sandalias%20de%20cuero%22" in ad_lib_url
    assert "content_languages%5B0%5D=es" in ad_lib_url or "content_languages[0]=es" in ad_lib_url
    assert "active_status=active" in ad_lib_url
    assert "media_type=image" in ad_lib_url
    assert body["resultsLimit"] == 5
    with pytest.raises(StopIteration):
        next(gen)


def test_url_varias_palabras_es_frase_exacta_y_una_sola_palabra_no():
    """`keyword_unordered` acepta anuncios con las palabras en cualquier parte
    (catálogos genéricos, textos que las mencionan de pasada): «dolor de pies»
    trajo un alpinista y un enchufe (2026-09-27). Con varias palabras se pide
    la frase exacta, como las comillas en la Ad Library."""
    base = {"modo": "palabra", "idioma": "es", "pais": "ALL", "formato": "imagen", "solo_activos": True}
    url = apify_adlibrary._url_ad_library({**base, "palabra": "  dolor de pies "})
    assert "q=%22dolor%20de%20pies%22" in url and "search_type=keyword_exact_phrase" in url
    url = apify_adlibrary._url_ad_library({**base, "palabra": "plantillas"})
    assert "q=plantillas" in url and "search_type=keyword_unordered" in url


def test_traer_modo_marca_usa_view_all_page_id(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "16453004404", "pais": "ALL", "formato": "imagen",
                                 "solo_activos": True}, 10, lambda **kw: None)
    next(gen)
    _, _, kw = sesion.llamadas[0]
    ad_lib_url = kw["json"]["startUrls"][0]["url"]
    assert "view_all_page_id=16453004404" in ad_lib_url
    assert "search_type=page" in ad_lib_url


def test_traer_normaliza_el_item_real(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "16453004404", "pais": "CO"}, 10, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    assert len(pagina) == 1
    a = pagina[0]
    assert a["anuncio_id"] == "1229350099285014"
    assert a["pagina_id"] == "16453004404"
    assert a["marca"] == "Sandalias Andina"
    assert a["cuerpo"] == "Cómodas, livianas y hechas a mano. Envío a toda Colombia."
    assert a["imagen_origen"] == "https://scontent.xx.fbcdn.net/v/sandalias_ad1.jpg"
    assert a["variantes"] == 3
    assert a["primera_vez"] == "2026-03-16"
    assert a["activo"] is True
    assert a["tipo"] == "imagen"
    assert cursor is None
    assert meta == {"costo_real": pytest.approx(1 * apify_actores_precio()), "run_id": "run1", "dataset_id": "ds1"}


def apify_actores_precio():
    from referentes.fuentes import apify_actores
    return apify_actores.USD_POR_RESULTADO


def test_traer_sin_resultados_no_lanza(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    assert pagina == [] and cursor is None and meta == {}


def test_traer_dataset_no_entregado_lanza_error_fuente(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    # nicho/fuentes/_http.pedir (bajo apify_api.leer_dataset) reintenta UNA vez
    # cada 5xx por su cuenta, así que cada uno de los INTENTOS_DATASET intentos
    # de leer_dataset puede consumir hasta 2 respuestas -- ver
    # tests/test_providers_apify.py::test_leer_dataset_agota_intentos, que usa
    # el mismo × 2.
    # + una respuesta más para el `contar_dataset` que `traer()` llama cuando
    # `crudos is None` (Importante 2 del review): la corrida ya se pagó, así
    # que necesita el itemCount para registrar el costo real igual.
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        *([_Resp({}, status=500)] * (apify_api.INTENTOS_DATASET * 2)),
        _Resp({"data": {"itemCount": 3}}),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    monkeypatch.setattr(apify_api, "PAUSA_SONDEO", 0)
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None)
    with pytest.raises(ErrorFuente):
        next(gen)


def test_traer_item_malformado_no_revienta_el_lote(monkeypatch):
    """Un ítem sin datos usables en snapshot (images/cards con null, u otra
    forma a medio llenar) no debe reventar todo `traer()` -- Apify ya cobró
    por el lote completo, así que perder los ítems buenos por culpa de uno
    malo perdería trabajo ya pagado (Importante 1 del review)."""
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    item_malo = {"adArchiveId": "bad1", "snapshot": {"images": [None], "cards": [None]}}
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM, item_malo]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "16453004404", "pais": "CO"}, 10, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    buenos = [a for a in pagina if a]
    assert len(buenos) == 1
    assert buenos[0]["anuncio_id"] == "1229350099285014"
    assert meta["costo_real"] == pytest.approx(round(2 * apify_actores_precio(), 4))


def test_traer_dataset_no_entregado_registra_costo_real_por_contar_dataset(monkeypatch):
    """Cuando la corrida terminó SUCCEEDED (ya cobrada) pero su dataset no se
    puede leer tras agotar los intentos, `contar_dataset` da el itemCount
    real cobrado y `traer()` lo manda como `ErrorFuente(...,
    costo_real=...)` para que `_fase_trayendo` lo registre en gastos incluso
    en error total (Importante 2 del review)."""
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        *([_Resp({}, status=500)] * (apify_api.INTENTOS_DATASET * 2)),
        _Resp({"data": {"itemCount": 5}}),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    monkeypatch.setattr(apify_api, "PAUSA_SONDEO", 0)
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None)
    with pytest.raises(ErrorFuente) as exc:
        next(gen)
    assert exc.value.costo_real == pytest.approx(round(5 * apify_actores_precio(), 4))
    assert exc.value.extra_gasto == {'run_id': 'run1', 'dataset_id': 'ds1'}


def test_arrancar_401_se_traduce_al_error_fuente_de_referentes(monkeypatch):
    """providers.apify (Tarea 1) levanta nicho.fuentes.base.ErrorFuente (usa
    nicho/fuentes/_http.py por debajo) -- traer() debe traducirlo al
    ErrorFuente de referentes.fuentes.base, que es el único que
    _fase_trayendo atrapa. Sin la traducción, este test recibiría la clase
    equivocada y pytest.raises(ErrorFuente) fallaría."""
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({}, status=401)])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    with pytest.raises(ErrorFuente) as exc:
        next(apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None))
    assert type(exc.value) is ErrorFuente        # no una subclase ni la de nicho -- la clase exacta de referentes
    assert "token" in exc.value.usuario.lower()


def test_probar_ok(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({"data": {"id": "u1"}})])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    assert apify_adlibrary.probar() is None


def test_probar_token_malo_lanza_error_fuente(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({}, status=401)])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    with pytest.raises(ErrorFuente):
        apify_adlibrary.probar()


def test_dias_activo_solo_con_fecha_de_inicio_cuenta_hasta_hoy():
    """Sin `endDateFormatted` (anuncio sigue corriendo): `dias` se cuenta
    desde `startDateFormatted` hasta hoy (Important 2 del review final)."""
    item = dict(FIXTURE_ITEM, isActive=True)
    item.pop("endDateFormatted", None)
    a = apify_adlibrary._normalizar(item)
    esperado = (date.today() - date(2026, 3, 16)).days
    assert isinstance(a["dias"], int) and a["dias"] >= 0
    assert a["dias"] == esperado


def test_dias_inactivo_con_fecha_de_cierre_cuenta_los_dias_exactos():
    """Anuncio ya parado con `endDateFormatted`: `dias` es la diferencia real
    entre inicio y cierre, no hasta hoy."""
    item = dict(FIXTURE_ITEM, isActive=False, endDateFormatted="2026-07-09T07:00:00.000Z")
    a = apify_adlibrary._normalizar(item)
    assert a["dias"] == (date(2026, 7, 9) - date(2026, 3, 16)).days


def test_dias_sin_fecha_de_inicio_es_none():
    """Sin `startDateFormatted` no hay nada que calcular -- nunca se inventa
    un número."""
    item = dict(FIXTURE_ITEM)
    item.pop("startDateFormatted", None)
    a = apify_adlibrary._normalizar(item)
    assert a["dias"] is None


def test_sondeo_fallido_conserva_costo_del_dataset(monkeypatch):
    from nicho.fuentes.base import ErrorFuente as ErrorApify
    monkeypatch.setattr(apify_adlibrary, "_token", lambda: "prueba")
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: object())
    monkeypatch.setattr(apify_api, "arrancar", lambda *a, **k: ("run", "ds", "RUNNING"))
    monkeypatch.setattr(apify_api, "sondear", lambda *a, **k: (_ for _ in ()).throw(ErrorApify("sondeo")))
    monkeypatch.setattr(apify_api, "contar_dataset", lambda *a, **k: 5)
    with pytest.raises(ErrorFuente) as exc:
        next(apify_adlibrary.traer({"modo": "palabra", "palabra": "shoes"}, 10, lambda **k: None))
    assert exc.value.costo_real == pytest.approx(round(5 * apify_actores_precio(), 4))
    assert exc.value.extra_gasto == {'run_id': 'run', 'dataset_id': 'ds'}


def test_normalizacion_fallida_conserva_cobro(monkeypatch):
    monkeypatch.setattr(apify_adlibrary, '_token', lambda: 'prueba')
    monkeypatch.setattr(apify_adlibrary, '_sesion', lambda: object())
    monkeypatch.setattr(apify_api, 'arrancar', lambda *a, **k: ('run', 'ds', 'SUCCEEDED'))
    monkeypatch.setattr(apify_api, 'sondear', lambda *a, **k: 'SUCCEEDED')
    monkeypatch.setattr(apify_api, 'leer_dataset', lambda *a, **k: ([{**FIXTURE_ITEM, 'startDateFormatted': 123}], None))
    with pytest.raises(ErrorFuente) as exc:
        next(apify_adlibrary.traer({'modo': 'palabra', 'palabra': 'shoes'}, 10, lambda **k: None))
    assert exc.value.costo_real == pytest.approx(apify_actores_precio())
    assert exc.value.extra_gasto == {'run_id': 'run', 'dataset_id': 'ds'}

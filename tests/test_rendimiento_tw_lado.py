"""Lado Triple Whale de la pestaña Rendimiento (spec 2026-10-09 R5, R9 y A4)."""
from datetime import date, timedelta

import pytest

import idiomas
import triple_whale_tiendas
from triple_whale import datos, evaluacion


@pytest.fixture(autouse=True)
def _llave_de_cifrado(monkeypatch):
    # `triple_whale_tiendas.agregar` cifra la llave de la tienda con la clave de la app.
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")


def _hace(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _tienda(cliente="acme", pais="NO", moneda="USD"):
    return triple_whale_tiendas.agregar(cliente, "tw_llave_123", f"{cliente}-{pais.lower()}.myshopify.com", pais,  # llave-de-prueba
                                        moneda=moneda)


def test_un_canal_sin_gasto_no_entra_en_anuncios_ni_en_la_serie(base_temporal):
    tid = _tienda()
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 10, "impresiones": 1000}])
    datos.reemplazar_anuncios_pixel("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "pedidos": 1, "ingresos": 50},
        {"canal": "klaviyo", "ad_id": "flujo-1", "fecha": f, "pedidos": 3, "ingresos": 300}])
    filas = datos.totales_por_anuncio("acme", tid, f, f)
    assert [(x["canal"], x["ad_id"]) for x in filas] == [("facebook-ads", "a1")]
    assert datos.totales_por_anuncio("acme", None, f, f)[0]["ingresos"] == 50
    serie = datos.serie_anuncios("acme", tid, f, f)
    assert serie[0]["ingresos"] == 50 and serie[0]["pedidos"] == 1


def test_el_filtro_de_canales_pagados_mira_la_copia_del_alcance(base_temporal):
    # Un canal con gasto en OTRA tienda no es pagado en esta: cada alcance decide por su propia copia.
    no, se = _tienda(pais="NO"), _tienda(pais="SE")
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", no, f, f, [
        {"canal": "tiktok-ads", "ad_id": "t1", "fecha": f, "gasto": 8, "impresiones": 100}])
    datos.reemplazar_anuncios_pixel("acme", se, f, f, [
        {"canal": "tiktok-ads", "ad_id": "t2", "fecha": f, "pedidos": 2, "ingresos": 80}])
    assert datos.totales_por_anuncio("acme", se, f, f) == []
    assert sorted(x["ad_id"] for x in datos.totales_por_anuncio("acme", None, f, f)) == ["t1", "t2"]


def test_cuentas_de_meta_que_llegan_por_cada_tienda(base_temporal):
    no, _se = _tienda(pais="NO"), _tienda(pais="SE")
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", no, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 5, "cuenta_id": "709406360806038"},
        {"canal": "facebook-ads", "ad_id": "a2", "fecha": f, "gasto": 5, "cuenta_id": "act_708698354181244"},
        {"canal": "tiktok-ads", "ad_id": "t1", "fecha": f, "gasto": 5, "cuenta_id": "999"}])
    assert datos.cuentas_meta_de_tiendas("acme") == {no: {"act_709406360806038", "act_708698354181244"}}
    assert datos.cuentas_meta_de_tiendas("otro") == {}


def test_ventas_por_campana_y_conjunto_solo_de_meta(base_temporal):
    tid = _tienda()
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 10, "campana_id": "c1", "conjunto_id": "s1"},
        {"canal": "facebook-ads", "ad_id": "a2", "fecha": f, "gasto": 20, "campana_id": "c1", "conjunto_id": "s2"},
        {"canal": "tiktok-ads", "ad_id": "t1", "fecha": f, "gasto": 7, "campana_id": "c1", "conjunto_id": "s1"}])
    datos.reemplazar_anuncios_pixel("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "pedidos": 1, "ingresos": 40},
        {"canal": "facebook-ads", "ad_id": "a2", "fecha": f, "pedidos": 2, "ingresos": 90}])
    assert datos.totales_por_grupo("acme", tid, f, f, "campana") == {
        "c1": {"gasto": 30.0, "pedidos": 3.0, "ingresos": 130.0}}
    assert datos.totales_por_grupo("acme", None, f, f, "conjunto")["s1"] == {
        "gasto": 10.0, "pedidos": 1.0, "ingresos": 40.0}


def test_la_alerta_sin_ventas_habla_de_meta_cuando_la_fuente_es_meta():
    ev = {"cuenta": {"m": {"gasto": 100.0}, "pct_gasto": {}}, "hay_ventas": False, "anuncios": [], "conteo": {}}
    with idiomas.en_idioma("es"):
        assert "Triple Whale" in evaluacion.alertas(ev)[0]["texto"]
        texto = evaluacion.alertas(ev, origen="meta")[0]["texto"]
    assert "Meta" in texto and "Triple Whale" not in texto


def test_contexto_sin_resultados_no_los_calcula(base_temporal, monkeypatch):
    from triple_whale import panel
    tid = _tienda()
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 10, "impresiones": 1000}])
    monkeypatch.setattr(panel, "_resultados", lambda *a, **k: (_ for _ in ()).throw(AssertionError("calculó")))
    with idiomas.en_idioma("es"):
        ctx = panel.contexto("acme", 0, tienda_id=tid, con_resultados=False)
    assert ctx["resultados"] is None and ctx["ev"]["anuncios"]


# ------------------------------------------------- tasas tras la copia ---

def _con_copia(moneda):
    tid = _tienda(moneda=moneda)
    f = _hace(3)
    datos.reemplazar_anuncios_canal("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 10, "impresiones": 1000}])
    return f


def test_la_copia_pide_las_tasas_de_la_moneda_del_proyecto(base_temporal, monkeypatch):
    from meta_rendimiento import tasas
    from tareas import triple_whale as tarea
    primero = _con_copia("NOK")
    pedidas = []
    monkeypatch.setattr(tasas, "asegurar", lambda *a, **k: pedidas.append((a, k)))
    tarea._asegurar_tasas("acme")
    assert pedidas == [((["NOK"], primero, date.today().isoformat()), {})]


def test_en_dolares_la_copia_no_pide_tasas(base_temporal, monkeypatch):
    from meta_rendimiento import tasas
    from tareas import triple_whale as tarea
    _con_copia("USD")
    monkeypatch.setattr(tasas, "asegurar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("pidió")))
    tarea._asegurar_tasas("acme")


def test_una_tasa_que_no_llega_no_tumba_la_copia(base_temporal, monkeypatch):
    from meta_rendimiento import tasas
    from tareas import triple_whale as tarea
    _con_copia("NOK")

    def _falla(*a, **k):
        raise RuntimeError("el BCE no contesta")

    monkeypatch.setattr(tasas, "asegurar", _falla)
    tarea._asegurar_tasas("acme")   # no lanza


def test_sin_ajustes_ni_copia_no_se_pide_nada(base_temporal, monkeypatch):
    from meta_rendimiento import tasas
    from tareas import triple_whale as tarea
    monkeypatch.setattr(tasas, "asegurar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("pidió")))
    tarea._asegurar_tasas("sin_tienda")
    _tienda(moneda="NOK")   # con tienda pero sin un solo día copiado
    tarea._asegurar_tasas("acme")


def test_la_tarea_pide_las_tasas_solo_cuando_la_copia_salio_bien(base_temporal, monkeypatch):
    import triple_whale
    from tareas import triple_whale as tarea
    tid = _tienda(moneda="NOK")
    f = _hace(1)
    pedidas = []
    monkeypatch.setattr(tarea.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(tarea.avisos, "revisar_y_avisar", lambda cliente: None)
    monkeypatch.setattr(tarea, "_asegurar_tasas", pedidas.append)
    monkeypatch.setattr(tarea.sync, "sincronizar", lambda *a, **k: {
        "anuncios": 1, "dias_tienda": 1, "desde": f, "hasta": f, "fallos": {}})
    tarea.tw_sincronizar({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert pedidas == ["acme"]

    def _falla(*a, **k):
        raise triple_whale.ErrorTripleWhale("sin conexión")

    monkeypatch.setattr(tarea.sync, "sincronizar", _falla)
    with pytest.raises(triple_whale.ErrorTripleWhale):
        tarea.tw_sincronizar({"payload": {"cliente": "acme", "tienda_id": tid}})
    assert pedidas == ["acme"]   # una copia fallida no pide tasas

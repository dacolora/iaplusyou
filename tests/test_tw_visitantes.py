"""NVP y etapa del embudo (spec 2026-10-09-nvp-visitantes-nuevos §2)."""
import pytest

from triple_whale import visitantes as vis


def test_nvp_es_nuevos_entre_unicos():
    assert vis.nvp(13848, 28777) == pytest.approx(48.12, abs=0.01)
    assert vis.nvp(0, 100) == 0.0
    assert vis.nvp(5, 0) is None and vis.nvp(None, None) is None and vis.nvp("x", "y") is None
    # Triple Whale redondea por canal: más nuevos que únicos nunca da más de 100.
    assert vis.nvp(120, 100) == 100.0


@pytest.mark.parametrize("porcentaje, esperada", [
    (100.0, "TOF"), (70.0, "TOF"), (69.99, "MOF"), (40.0, "MOF"), (39.99, "BOF"), (0.0, "BOF"), (None, None)])
def test_etapa_en_los_cortes_exactos(porcentaje, esperada):
    assert vis.etapa(porcentaje) == esperada


def test_resumen_sin_datos_pocos_y_ok():
    assert vis.resumen(0, 0) == {"nvp": None, "etapa": None, "nuevos": 0, "visitantes": 0, "estado": "sin_datos"}
    pocos = vis.resumen(40, 49)
    assert pocos["estado"] == "pocos" and pocos["etapa"] is None and pocos["nvp"] == pytest.approx(81.6, abs=0.1)
    ok = vis.resumen(35, 50)
    assert ok["estado"] == "ok" and ok["etapa"] == "TOF" and ok["nvp"] == 70.0
    assert vis.resumen(10, 100)["etapa"] == "BOF"
    # Los modelos lineales reparten: llegan decimales y se redondean para mostrar.
    assert vis.resumen(30.4, 99.6)["visitantes"] == 100


def test_de_fila_lee_las_columnas_de_la_copia():
    assert vis.de_fila({"visitantes_nuevos": 300, "visitantes": 400})["etapa"] == "TOF"
    assert vis.de_fila(None)["estado"] == "sin_datos"
    assert vis.de_fila({})["estado"] == "sin_datos"


def test_cada_etapa_tiene_su_explicacion():
    assert set(vis.EXPLICACION) == set(vis.ETAPAS)


def test_la_macro_pinta_el_chip_en_sus_cinco_estados(base_temporal):
    import dashboard
    with dashboard.app.test_request_context("/"):
        plantilla = dashboard.app.jinja_env.from_string(
            '{% import "_componentes.html" as cx %}'
            '{{ cx.nvp(820, 1000) }}|{{ cx.nvp(520, 1000) }}|{{ cx.nvp(250, 1000) }}|{{ cx.nvp(30, 40) }}|{{ cx.nvp(0, 0) }}'
            '|{{ cx.nvp(none, none) }}')
        tof, mof, bof, pocos, vacio, nada = plantilla.render().split("|")
    assert "chip-nvp-tof" in tof and "82&nbsp;%" in tof and ">TOF<" in tof and "820" in tof and "1000" in tof
    assert "chip-nvp-mof" in mof and ">MOF<" in mof
    assert "chip-nvp-bof" in bof and "25&nbsp;%" in bof and ">BOF<" in bof
    assert "chip-nvp-pocos" in pocos and "75&nbsp;%" in pocos and "TOF" not in pocos
    assert "chip-nvp-vacio" in vacio and "—" in vacio and "chip-nvp-vacio" in nada


def test_las_metricas_de_un_anuncio_traen_su_nvp_y_no_cambian_el_veredicto():
    from triple_whale import evaluacion
    m = evaluacion.metricas({"gasto": 10, "impresiones": 1000, "visitantes": 200, "visitantes_nuevos": 150})
    assert m["visitantes"] == 200 and m["nvp"] == 75.0 and m["etapa"] == "TOF"
    m = evaluacion.metricas({"gasto": 10, "impresiones": 1000})
    assert m["nvp"] is None and m["etapa"] is None
    pocos = evaluacion.metricas({"visitantes": 10, "visitantes_nuevos": 9})
    assert pocos["nvp"] == 90.0 and pocos["etapa"] is None


# ------------------------------------------------- lectura compartida ---

@pytest.fixture()
def copia(base_temporal, monkeypatch):
    """Dos tiendas con el mismo anuncio y un anuncio del que solo llegó el Pixel (sin campaña ese día)."""
    import triple_whale_tiendas
    from triple_whale import datos
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    t1 = triple_whale_tiendas.agregar("acme", "k1", "no.myshopify.com", pais="NO")
    t2 = triple_whale_tiendas.agregar("acme", "k2", "se.myshopify.com", pais="SE")
    otro = triple_whale_tiendas.agregar("otro", "k3", "otro.myshopify.com", pais="NO")
    ids = [t["id"] for t in triple_whale_tiendas.tiendas("acme")]
    dims = {"cuenta_id": "act_1", "campana_id": "c1", "conjunto_id": "s1"}
    datos.reemplazar_anuncios_canal("acme", ids[0], "2026-10-01", "2026-10-02", [
        dict(canal="facebook-ads", ad_id="a1", fecha="2026-10-01", **dims),
        dict(canal="facebook-ads", ad_id="a2", fecha="2026-10-01", **dims)])
    datos.reemplazar_anuncios_pixel("acme", ids[0], "2026-10-01", "2026-10-02", [
        dict(canal="facebook-ads", ad_id="a1", fecha="2026-10-01", visitantes=100, visitantes_nuevos=80),
        dict(canal="facebook-ads", ad_id="a1", fecha="2026-10-02", visitantes=50, visitantes_nuevos=10),  # sin campaña
        dict(canal="facebook-ads", ad_id="a2", fecha="2026-10-01", visitantes=0, visitantes_nuevos=0),
        dict(canal="google-ads", ad_id="a1", fecha="2026-10-01", visitantes=999, visitantes_nuevos=999)])
    datos.reemplazar_anuncios_pixel("acme", ids[1], "2026-10-01", "2026-10-01", [
        dict(canal="facebook-ads", ad_id="a1", fecha="2026-10-01", visitantes=10, visitantes_nuevos=5)])
    datos.reemplazar_anuncios_pixel("otro", [t["id"] for t in triple_whale_tiendas.tiendas("otro")][0],
                                    "2026-10-01", "2026-10-01", [
        dict(canal="facebook-ads", ad_id="a1", fecha="2026-10-01", visitantes=7, visitantes_nuevos=7)])
    return datos


def test_visitantes_por_anuncio_suma_tiendas_y_dias_sin_mezclar_canales_ni_proyectos(copia):
    assert copia.visitantes_por("acme", "ad_id", ["a1", "a2", "zz"]) == {
        "a1": {"visitantes": 160, "visitantes_nuevos": 95}}
    assert copia.visitantes_por("acme", "ad_id", ["a1"], desde="2026-10-02") == {
        "a1": {"visitantes": 50, "visitantes_nuevos": 10}}
    assert copia.visitantes_por("acme", "ad_id", []) == {}


def test_visitantes_por_campana_cuenta_tambien_los_dias_sin_campana(copia):
    for campo, objeto in (("campana_id", "c1"), ("conjunto_id", "s1"), ("cuenta_id", "act_1")):
        assert copia.visitantes_por("acme", campo, [objeto, "otra"]) == {
            objeto: {"visitantes": 160, "visitantes_nuevos": 95}}
    with pytest.raises(ValueError):
        copia.visitantes_por("acme", "anuncio; DROP", ["x"])

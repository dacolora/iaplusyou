"""exp_probar con el objetivo «Instalaciones de la app» (spec 2026-10-07): URLs de
tienda en vez de URL de destino, App ID de Meta guardado por proyecto y el
presupuesto por país repartido entre plataformas, cada parte sobre el mínimo."""
import pytest

from tests.test_experimentos_db import _pieza
from tests.test_rutas_bloque4 import _flashes
from tests.test_rutas_experimentos import FORM_PROBAR, app  # noqa: F401  (fixture)

IOS = "https://apps.apple.com/co/app/forja-habit/id6740000000"
ANDROID = "https://play.google.com/store/apps/details?id=com.forja.habit"


@pytest.fixture(autouse=True)
def _carpeta_meta_temporal(tmp_path, monkeypatch):
    """El App ID se guarda en clientes/<cliente>/: que no toque la carpeta real."""
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "_dir", lambda cliente: str(tmp_path / cliente))


def _form_app(clon, **cambios):
    data = dict(FORM_PROBAR, objetivo="OUTCOME_APP_PROMOTION", paises=["CO"], presupuesto_CO="20000",
                piezas=[str(clon)], combinaciones=[f"{clon}:CO"], app_ios_url=IOS, app_android_url=ANDROID,
                app_id="1234567890")
    data.pop("destino_url")
    data.pop("atribucion")
    data.update(cambios)
    return data


def _clon(base_temporal):
    return _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")


def test_app_crea_con_tiendas_y_guarda_app_id(app, base_temporal):
    """(a) + (e): sin destino_url, con las dos URLs y el App ID."""
    import experimentos as ex
    import meta_conexion
    clon = _clon(base_temporal)
    r = app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon))
    assert r.status_code == 302
    (e,) = ex.cargar("acme")
    assert e["objetivo_meta"] == "OUTCOME_APP_PROMOTION"
    assert e["extra"]["app"] == {"ios_url": IOS, "android_url": ANDROID, "app_id": "1234567890"}
    assert e["destino_url"] == IOS
    assert e["atribucion"] == "ninguna"   # con apps no hay compras que atribuir
    assert sorted(p["extra"]["plataforma"] for p in e["piezas"]) == ["android", "ios"]
    assert meta_conexion.cargar_app_anunciada("acme") == "1234567890"
    assert [t["tipo"] for t in app["encolados"]] == ["exp_lanzar"]


def test_app_usa_app_id_guardado_y_respeta_atribucion_elegida(app, base_temporal):
    import experimentos as ex
    import meta_conexion
    meta_conexion.guardar_app_anunciada("acme", "555666777")
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar",
                  data=_form_app(clon, app_id="", app_android_url="", atribucion="tienda"))
    (e,) = ex.cargar("acme")
    assert e["extra"]["app"] == {"ios_url": IOS, "app_id": "555666777"}
    assert e["atribucion"] == "tienda"
    assert [p["extra"]["plataforma"] for p in e["piezas"]] == ["ios"]


def test_app_sin_urls_no_crea_nada(app, base_temporal):
    """(b)"""
    import experimentos as ex
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon, app_ios_url="", app_android_url=""))
    assert ex.cargar("acme") == [] and app["encolados"] == []
    assert any("al menos una URL de tienda" in m for m in _flashes(app["c"]))


def test_app_url_de_play_en_campo_ios_es_error(app, base_temporal):
    """(c)"""
    import experimentos as ex
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon, app_ios_url=ANDROID, app_android_url=""))
    assert ex.cargar("acme") == [] and app["encolados"] == []
    assert any("App Store" in m for m in _flashes(app["c"]))


def test_app_sin_app_id_es_error(app, base_temporal):
    import experimentos as ex
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon, app_id=""))
    assert ex.cargar("acme") == [] and app["encolados"] == []
    assert any("App ID" in m for m in _flashes(app["c"]))


def test_app_presupuesto_repartido_bajo_el_minimo(app, base_temporal):
    """(d): COP, mínimo 4000; 6000 entre dos tiendas = 3000 por conjunto."""
    import experimentos as ex
    import meta_conexion
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon, presupuesto_CO="6000"))
    assert ex.cargar("acme") == [] and app["encolados"] == []
    mensajes = _flashes(app["c"])
    assert any("4000" in m and "COP" in m and "CO" in m for m in mensajes)
    assert meta_conexion.cargar_app_anunciada("acme") is None   # nada guardado si no se creó
    # Con una sola tienda los mismos 6000 sí alcanzan.
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon, presupuesto_CO="6000", app_android_url=""))
    assert len(ex.cargar("acme")) == 1


def test_otros_objetivos_siguen_exigiendo_destino(app, base_temporal):
    """(f): sin URL de destino un objetivo de tráfico sigue fallando, y los
    campos de tienda se ignoran."""
    import experimentos as ex
    clon = _clon(base_temporal)
    data = dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"], paises=["CO"], destino_url="")
    app["c"].post("/cliente/acme/experimentos/probar", data=data)
    assert ex.cargar("acme") == []
    data = dict(data, destino_url="https://tienda.co/p", app_ios_url="nada", app_id="x")
    app["c"].post("/cliente/acme/experimentos/probar", data=data)
    (e,) = ex.cargar("acme")
    assert e["objetivo_meta"] == "OUTCOME_TRAFFIC" and e["extra"] == {} and e["destino_url"] == "https://tienda.co/p"
    assert [p["extra"] for p in e["piezas"]] == [{}]


def test_formulario_trae_campos_de_tienda_y_objetivo_no_sugerido(app, base_temporal):
    import meta_conexion
    meta_conexion.guardar_app_anunciada("acme", "1234567890")
    _clon(base_temporal)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert '<option value="OUTCOME_APP_PROMOTION" >Instalaciones de la app</option>' in html
    assert 'name="app_ios_url"' in html and 'name="app_android_url"' in html
    assert 'name="app_id" inputmode="numeric" value="1234567890"' in html
    assert "data-solo-app hidden" in html and "data-solo-no-app" in html


def test_arbol_de_app_deja_pausar_y_cambiar_presupuesto(app, base_temporal):
    """Adenda 1: en apps el país no tiene meta_adset_id sino meta_adsets."""
    import experimentos as ex
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon))
    (e,) = ex.cargar("acme")
    ex.actualizar_pais("acme", e["id"], "CO", meta_adsets={"ios": "111", "android": "222"}, estado="pausado")
    ex.actualizar("acme", e["id"], estado="pausado", meta_campaign_id="999")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Activar país" in html and "Cambiar presupuesto" in html

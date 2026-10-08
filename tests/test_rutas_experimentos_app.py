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
    # Desde E2 el formulario vive en «Nuevo experimento» (_exp_probar.html), ya no en la pestaña.
    html = app["c"].get("/cliente/acme/experimentos/nuevo").get_data(as_text=True)
    import re
    opcion = re.search(r'<option value="OUTCOME_APP_PROMOTION"[^>]*>[^<]*</option>', html).group(0)
    assert "Instalaciones de la app" in opcion and "(sugerido)" not in opcion
    assert 'name="app_ios_url"' in html and 'name="app_android_url"' in html
    assert 'name="app_id" inputmode="numeric" value="1234567890"' in html
    assert "data-solo-app hidden" in html and "data-solo-no-app" in html
    # Con dos tiendas el resumen avisa que el presupuesto del país se reparte (oculto hasta entonces).
    assert ('id="exp-resumen-reparto" hidden>El presupuesto diario de cada país se reparte entre las tiendas.</p>'
            in html)
    assert "reparto.hidden = tiendasApp() < 2" in html


def test_arbol_de_app_deja_pausar_y_cambiar_presupuesto(app, base_temporal):
    """Adenda 1: en apps el país no tiene meta_adset_id sino meta_adsets."""
    import experimentos as ex
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon))
    (e,) = ex.cargar("acme")
    ex.actualizar_pais("acme", e["id"], "CO", meta_adsets={"ios": "111", "android": "222"}, estado="pausado")
    ex.actualizar("acme", e["id"], estado="pausado", meta_campaign_id="999")
    # Desde E2 la gestión del experimento llega en el fragmento del centro de resultados (_exp_gestionar.html).
    html = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={e['id']}",
                        headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    assert "Activar país" in html and "Cambiar presupuesto" in html
    # «Activar todo» dice lo que gasta al día contando el país de la app (antes solo sumaba meta_adset_id).
    import json
    import re
    confirmaciones = [json.loads(m) for m in re.findall(r"confirm\((\"[^\"]*\")\)", html)]
    (activar_todo,) = [t for t in confirmaciones if t.startswith("Activar todo")]
    assert "20.000" in activar_todo, activar_todo


def test_cada_fila_de_app_dice_su_tienda_en_la_gestion_y_en_el_panel(app, base_temporal):
    """Revisión final, ola 2 (2026-10-08): las dos filas de una pieza (una por tienda) se veían iguales; ahora cada
    una lleva el chip «iOS» o «Android» en la gestión, en el ranking y en el panel de la pieza."""
    import re
    import experimentos as ex
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon))
    (e,) = ex.cargar("acme")
    ex.actualizar_pais("acme", e["id"], "CO", meta_adsets={"ios": "111", "android": "222"}, estado="pausado")
    ex.actualizar("acme", e["id"], estado="pausado", meta_campaign_id="999")
    for pz in e["piezas"]:
        ex.actualizar_pieza("acme", pz["id"], meta_ad_id=f"ad{pz['id']}", estado="pausado")
    chip = r'<span class="tag-estado" title="Tienda de la app">(iOS|Android)</span>'
    html = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={e['id']}",
                        headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    gestion = html[html.index('id="cr-gestion-titulo"'):]
    assert sorted(set(re.findall(chip, gestion))) == ["Android", "iOS"]
    for pz in e["piezas"]:
        panel = app["c"].get(f"/cliente/acme/experimentos/pieza/{pz['id']}",
                             headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
        esperado = {"ios": "iOS", "android": "Android"}[pz["extra"]["plataforma"]]
        assert re.findall(chip, panel) == [esperado], panel[:400]


def test_fila_que_no_es_de_app_no_lleva_chip_de_tienda(app, base_temporal):
    import experimentos as ex
    clon = _clon(base_temporal)
    eid = ex.crear("acme", "Web", [{"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0}], "OUTCOME_TRAFFIC", 7,
                   500000.0, "https://tienda.co/p", "COP")
    ep = ex.agregar_pieza("acme", eid, clon, "CO")
    ex.actualizar("acme", eid, estado="pausado", meta_campaign_id="999")
    ex.actualizar_pieza("acme", ep, meta_ad_id="ad1", estado="pausado")
    html = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={eid}",
                        headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    panel = app["c"].get(f"/cliente/acme/experimentos/pieza/{ep}",
                         headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    assert "Tienda de la app" not in html and "Tienda de la app" not in panel


def test_app_id_no_se_guarda_si_falla_la_creacion(app, base_temporal, monkeypatch):
    import experimentos as ex
    import meta_conexion
    clon = _clon(base_temporal)

    def _falla(*a, **k):
        raise ValueError("no se pudo")
    monkeypatch.setattr(ex, "crear_con_piezas", _falla)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon))
    assert meta_conexion.cargar_app_anunciada("acme") is None


def test_faltan_datos_de_app_no_pide_url_de_destino(app, base_temporal):
    clon = _clon(base_temporal)
    app["c"].post("/cliente/acme/experimentos/probar", data=_form_app(clon, dias="0"))
    msgs = _flashes(app["c"])
    assert any("Faltan datos" in m for m in msgs) and not any("URL de destino" in m for m in msgs)


def test_exp_crear_rechaza_instalaciones_de_app(app):
    import experimentos as ex
    r = app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM_PROBAR, nombre="x", objetivo="OUTCOME_APP_PROMOTION"))
    assert r.status_code == 302
    assert any("usa «Nuevo experimento»" in m for m in _flashes(app["c"]))
    assert ex.cargar("acme") == []


def test_agregar_pieza_a_un_experimento_de_apps_se_rechaza(app, base_temporal):
    """Revisión final, ola 2 (2026-10-08): una fila agregada después nacía sin plataforma y bloqueaba el
    lanzamiento. En apps las piezas se eligen al crear el experimento."""
    import experimentos as ex
    clon = _clon(base_temporal)
    datos = dict(nombre="Forja", paises=[{"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0}],
                 objetivo_meta="OUTCOME_APP_PROMOTION", dias=7, tope_total=500000.0, destino_url=IOS, moneda="COP",
                 app={"ios_url": IOS, "android_url": ANDROID, "app_id": "1234567890"})
    eid = ex.crear_con_piezas("acme", datos, [(clon, "CO")])
    otro = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_otro")
    with pytest.raises(ValueError, match="las piezas se eligen al crearlo"):
        ex.agregar_pieza("acme", eid, otro, "CO")
    r = app["c"].post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": str(otro), "pais": "CO"})
    assert r.status_code == 302
    assert any("las piezas se eligen al crearlo" in m for m in _flashes(app["c"]))
    assert len(ex.piezas("acme", eid)) == 2      # solo las dos filas (una por tienda) del alta


def _experimento_app_en_meta(base_temporal, presupuesto=20000.0):
    import experimentos as ex
    clon = _clon(base_temporal)
    datos = dict(nombre="Forja", paises=[{"pais": "CO", "idioma": "es", "presupuesto_dia": presupuesto}],
                 objetivo_meta="OUTCOME_APP_PROMOTION", dias=7, tope_total=500000.0, destino_url=IOS, moneda="COP",
                 app={"ios_url": IOS, "android_url": ANDROID, "app_id": "1234567890"})
    eid = ex.crear_con_piezas("acme", datos, [(clon, "CO")])
    ex.actualizar_pais("acme", eid, "CO", meta_adsets={"ios": "as_ios", "android": "as_and"})
    ex.actualizar("acme", eid, estado="pausado", meta_campaign_id="999")
    return eid


def test_presupuesto_de_pais_en_apps_valida_cada_parte_contra_el_minimo(app, base_temporal, monkeypatch):
    d = app["dashboard"]
    eid = _experimento_app_en_meta(base_temporal)
    llamadas = []
    monkeypatch.setattr(d.lanzador, "cambiar_presupuesto_pais", lambda c, e, p, v: llamadas.append((p, v)))
    # 6000 COP pasa el mínimo (4000) como total, pero cada tienda recibiría 3000.
    app["c"].post(f"/cliente/acme/experimentos/{eid}/presupuesto", data={"pais": "CO", "presupuesto_dia": "6000"})
    msgs = _flashes(app["c"])
    assert llamadas == []
    assert any("CO" in m and "4000" in m and "COP" in m and "2" in m for m in msgs)
    app["c"].post(f"/cliente/acme/experimentos/{eid}/presupuesto", data={"pais": "CO", "presupuesto_dia": "8000"})
    assert llamadas == [("CO", 8000.0)]

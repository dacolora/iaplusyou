"""Idea → pieza → anuncio (spec 2026-09-28 §14): «Llevar a Crear» deja en el
formulario de dónde salió el texto, la sesión lo guarda como `tw_idea`, y la
pestaña enlaza cada idea con las piezas que nacieron de ella y cada anuncio
hecho en Creatv con su idea. Nada de esto genera ni gasta."""
import pytest

import creative_flow as cf
import experimentos as ex
from tests.test_rutas_experimentos import _cliente_admin
from tests.test_rutas_triple_whale import _conectar, _evaluacion_lista, _sembrar
from triple_whale import datos, puente


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(referencias_flowplus, "_path", lambda cliente: str(tmp_path / f"bandeja_{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    lanzadas = []
    monkeypatch.setattr(dashboard, "_lanzar_video_cf", lambda c, cf_id, entry: lanzadas.append(cf_id) or True)
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda job_id, tipo, payload, **kw: True)
    return {"c": _cliente_admin(dashboard), "lanzadas": lanzadas}


def _crear(app, **extra):
    data = {"accion_central": "el florero se quiebra", "duracion_objetivo": "8", "aspect_ratio": "9:16",
            "tipo": "video", "modelo": "wan3", "musica_estilo": "", "bandeja_vista": "1"}
    data.update(extra)
    assert app["c"].post("/cliente/acme/creative_flow/crear", data=data).status_code == 302
    [(cf_id, entry)] = cf.cargar("acme").items()
    return cf_id, entry


def test_el_prefill_lleva_el_origen_y_el_formulario_lo_devuelve(app):
    _conectar()
    eid = _evaluacion_lista()
    app["c"].post(f"/cliente/acme/triple-whale/evaluacion/{eid}/idea/0/crear")
    with app["c"].session_transaction() as s:
        assert s["fp_prefill"]["origen_tw"] == f"{eid}:0"
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'name="origen_tw"' in html and "prefill.origen_tw" in html


def test_crear_desde_la_idea_guarda_el_origen_y_la_pestana_enlaza_la_pieza(app):
    _conectar()
    _sembrar()
    eid = _evaluacion_lista()
    cf_id, entry = _crear(app, origen_tw=f"{eid}:0")
    assert app["lanzadas"] == [cf_id]
    assert entry["tw_idea"] == {"evaluacion_id": eid, "idea": 0, "titulo": "Caja que se abre sola"}
    piezas = datos.piezas_de_evaluacion("acme", eid)
    assert list(piezas) == [0]
    [p] = piezas[0]
    assert p["cf_id"] == cf_id and p["titulo"] == "el florero se quiebra" and p["tipo"] == "video"
    assert p["estado"] == entry["estado"]
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "Ya se hizo 1 pieza con esta idea" in html and "el florero se quiebra" in html
    assert "Nació de la idea" not in html          # todavía no corre en Meta


def test_un_origen_raro_se_ignora_y_la_pieza_se_crea_igual(app):
    _conectar()
    eid = _evaluacion_lista()
    ajena = datos.crear_evaluacion("otro", "2026-09-01", "2026-09-28", "USD", [])
    datos.actualizar_evaluacion(ajena, estado="lista", resultado={"ideas": [{"titulo": "x", "prompt": "y"}]})
    for raro in ("abc", "999:0", f"{eid}:9", f"{ajena}:0", "", None):
        assert puente.origen_desde_formulario("acme", raro) is None, raro
    en_cola = datos.crear_evaluacion("acme", "2026-09-01", "2026-09-28", "USD", [])
    assert puente.origen_desde_formulario("acme", f"{en_cola}:0") is None     # sin terminar, sin ideas
    _, entry = _crear(app, origen_tw="999:0")
    assert "tw_idea" not in entry and entry["accion_central"] == "el florero se quiebra"
    assert datos.piezas_de_evaluacion("acme", eid) == {}


def test_el_anuncio_que_nacio_de_una_idea_lo_dice_y_la_idea_muestra_su_veredicto(app):
    from tests.test_experimentos_db import PAISES
    _conectar()
    _sembrar()
    eid = _evaluacion_lista()
    cf_id, _ = _crear(app, origen_tw=f"{eid}:0")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/florero.mp4")
    [p] = datos.piezas_de_evaluacion("acme", eid)[0]
    exp = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 500.0, "https://t.co/p", "USD")
    ep_id = ex.agregar_pieza("acme", exp, p["pieza_id"], "CO")
    ex.actualizar_pieza("acme", ep_id, meta_ad_id="g1", estado="activo")
    creatv = datos.piezas_creatv("acme", ["g1", "p1"])
    assert creatv["g1"]["tw_idea"] == {"evaluacion_id": eid, "idea": 0, "titulo": "Caja que se abre sola"}
    assert set(creatv) == {"g1"}
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "Nació de la idea «Caja que se abre sola»" in html
    assert "en Meta: Ganador" in html and "Ya se hizo 1 pieza con esta idea" in html
    assert html.count("Nació de la idea") == 1

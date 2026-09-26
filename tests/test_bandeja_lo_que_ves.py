"""La bandeja de referencias es del proyecto (la comparten todas las personas
que trabajan en él). Incidente 2026-09-25: una persona creó «solo con texto»
y el servidor le metió las 4 referencias que otra persona del mismo proyecto
acababa de cargar con «Editar y crear otra»; y al crear se las vació a ella.
Regla: lo que ves es lo que se usa — el formulario manda `bandeja_vista` y los
`ref_ids` que mostraba, y al crear solo se quitan esos."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(referencias_flowplus, "_path", lambda cliente: str(tmp_path / f"bandeja_{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    lanzadas, encolados = [], []
    monkeypatch.setattr(dashboard, "_lanzar_video_cf", lambda c, cf_id, entry: lanzadas.append(cf_id) or True)
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda job_id, tipo, payload, **kw: (encolados.append(tipo), True)[1])
    return {"c": _cliente_admin(dashboard), "lanzadas": lanzadas, "encolados": encolados}


def _bandeja(*nombres):
    import referencias_flowplus
    return [referencias_flowplus.agregar("acme", "imagen", f"https://r2/{n}.png", origen="reutilizada") for n in nombres]


def _ids_en_bandeja():
    import referencias_flowplus
    return [r["id"] for r in referencias_flowplus.listar("acme")]


def _crear(app, ref_ids=(), **extra):
    data = {"accion_central": "el florero se quiebra", "duracion_objetivo": "8", "aspect_ratio": "9:16",
            "tipo": "video", "modelo": "wan3", "musica_estilo": "", "bandeja_vista": "1", "ref_ids": list(ref_ids)}
    data.update(extra)
    assert app["c"].post("/cliente/acme/creative_flow/crear", data=data).status_code == 302
    import creative_flow as cf
    return cf.cargar("acme")


def test_sin_referencias_en_pantalla_no_usa_las_de_otra_persona(app):
    otras = _bandeja("a", "b", "c", "d")                 # las cargó otra persona del proyecto
    (_, e), = _crear(app).items()                         # tu pantalla no mostraba ninguna
    assert e["enfoque"] == "libre" and e["referencias"] == [] and e["referencias_urls"] == []
    assert _ids_en_bandeja() == otras                     # y no se las vacías


@pytest.mark.parametrize("campos", [{"modo_prompt": "directo"}, {"modo_prompt": "director"},
                                    {"tipo": "imagen", "modelo": "seedream_v5_pro"}])
def test_usa_solo_las_que_se_ven_y_solo_quita_esas(app, campos):
    a, b, c = _bandeja("a", "b", "c")
    (_, e), = _crear(app, ref_ids=[a, c], **campos).items()
    assert [r["url"] for r in e["referencias"]] == ["https://r2/a.png", "https://r2/c.png"]
    assert _ids_en_bandeja() == [b]


def test_si_una_referencia_que_se_ve_ya_no_existe_no_genera_nada(app):
    (a,) = _bandeja("a")
    assert _crear(app, ref_ids=[a, "ref_que_otra_persona_uso"]) == {}
    assert app["lanzadas"] == [] and app["encolados"] == []
    assert _ids_en_bandeja() == [a]
    with app["c"].session_transaction() as s:
        assert any("bandeja" in m and "no se cobró" in m for _, m in s.get("_flashes", []))


def test_la_pagina_marca_lo_que_se_ve_en_el_formulario(app):
    (a,) = _bandeja("a")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert f'name="ref_ids" value="{a}" form="form-flowplus"' in html
    assert 'name="bandeja_vista" value="1"' in html

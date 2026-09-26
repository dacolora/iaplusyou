"""Campaña sin temporada (2026-09-26). El asistente ofrece la temporada como
«(opcional)», pero `campana.temporada_id` era NOT NULL y la consulta de
campañas hacía JOIN con `temporada`: en un proyecto sin temporadas (y no hay
pantalla para crearlas) crear un sprint fallaba con el engañoso «Esa
combinación … ya existe» y el sprint quedaba archivado."""
import json
import os

import pytest
import sqlalchemy as sa

from tests.test_rutas_sprints import app  # noqa: F401  (fixture: admin, catálogo con espejo_led)


def _sprint(datos):
    pid = datos.crear_persona("acme", "Premium")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    return pid, sid


def test_campana_sin_temporada_se_crea_y_se_lista(base_temporal):
    from sprints import datos
    pid, sid = _sprint(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    c = datos.campana("acme", cid)
    assert c is not None and c["temporada_id"] is None and c["temporada_nombre"] is None
    assert [x["id"] for x in datos.sprint("acme", sid)["campanas"]] == [cid]


def test_campana_sin_temporada_no_se_repite(base_temporal):
    from sprints import datos
    pid, sid = _sprint(datos)
    datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    with pytest.raises(datos.CampanaDuplicada):
        datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)


def test_crear_sprint_en_un_proyecto_sin_temporadas(app):
    from sprints import datos
    pid = datos.crear_persona("acme", "Premium")
    campanas = [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": None,
                 "n_videos": 2, "n_imagenes": 0, "funnel": "tof"}]
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "Octubre", "inicio": "2026-10-01",
                                                           "fin": "2026-10-31", "campanas_json": json.dumps(campanas)})
    assert r.status_code == 302
    sp = [s for s in datos.sprints("acme") if s["nombre"] == "Octubre"]
    assert sp and sp[0]["campanas_total"] == 1 and sp[0]["estado"] == "planeando"


def test_pagina_del_sprint_muestra_sin_temporada_y_no_la_exige(app):
    from sprints import datos
    pid, sid = _sprint(datos)
    datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    assert "sin temporada" in html and ">None<" not in html
    select = html[html.index('<select name="temporada_id"'):]
    select = select[:select.index(">")]
    assert "required" not in select


def test_migracion_deja_la_temporada_opcional(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command.upgrade(Config(os.path.join(raiz, "alembic.ini")), "head")
    insp = sa.inspect(db.engine())
    col = next(c for c in insp.get_columns("campana") if c["name"] == "temporada_id")
    assert col["nullable"] is True
    # Recrear la tabla (batch) no puede perder la restricción ni las llaves foráneas.
    assert "uq_campana_combinacion" in {u["name"] for u in insp.get_unique_constraints("campana")}
    assert {"sprint", "persona", "temporada"} <= {f["referred_table"] for f in insp.get_foreign_keys("campana")}
    db._reset_para_tests()

"""Ganchos de Triple Whale (spec 2026-10-09 §4.2): la tabla tw_gancho y su único escritor."""
import pytest
import sqlalchemy as sa
from sqlalchemy import event

from triple_whale import datos

GANCHOS_T = [{"n": 1, "texto": "Uno", "prompt": "Push in", "fotograma_s": 2.0},
             {"n": 3, "texto": "Tres", "prompt": "Pan left", "fotograma_s": None}]


def _analisis(cliente="acme"):
    return datos.crear_analisis(cliente, None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", {})


def test_crear_tanda_numera_y_no_deja_pedir_otra_mientras_vive(base_temporal):
    aid = _analisis()
    filas = datos.crear_tanda("acme", aid, GANCHOS_T, pedido_por="admin")
    assert [(f["tanda"], f["n"], f["estado"]) for f in filas] == [(1, 1, "preparando"), (1, 3, "preparando")]
    assert filas[0]["texto"] == "Uno" and filas[0]["fotograma_s"] == 2.0 and filas[1]["fotograma_s"] is None
    assert filas[0]["pedido_por"] == "admin" and filas[0]["cliente"] == "acme" and filas[0]["cf_id"] is None
    with pytest.raises(datos.TandaViva):
        datos.crear_tanda("acme", aid, GANCHOS_T)
    for f in filas:
        assert datos.mover(f["id"], "preparando", "error", error="se cortó")
    assert [(f["tanda"], f["n"]) for f in datos.crear_tanda("acme", aid, GANCHOS_T[:1])] == [(2, 1)]
    otro = _analisis()
    assert datos.crear_tanda("acme", otro, GANCHOS_T[:1])[0]["tanda"] == 1      # cada análisis numera sus tandas
    with pytest.raises(ValueError):
        datos.crear_tanda("acme", otro, [])


def test_una_variante_viva_bloquea_y_las_terminadas_no(base_temporal):
    aid = _analisis()
    f1, f2 = datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f1["id"], "preparando", "lista", url_final="https://r2.test/a.mp4")
    assert datos.mover(f2["id"], "preparando", "produciendo")
    with pytest.raises(datos.TandaViva):
        datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f2["id"], "produciendo", "error", error="falló")
    assert datos.crear_tanda("acme", aid, GANCHOS_T)[0]["tanda"] == 2


def test_crear_tanda_toma_el_candado_antes_de_leer(base_temporal, escritor_en_medio):
    """Regla 5: dos clics a la vez no pueden leer los dos «sin tanda viva». Justo antes de la primera lectura otra
    conexión (otro hilo de gunicorn) intenta meter una fila viva: con el candado ya tomado queda bloqueada."""
    aid = _analisis()
    estado = escritor_en_medio(
        "FROM tw_gancho",
        "INSERT INTO tw_gancho (cliente, creado_en, actualizado_en, analisis_id, tanda, n, estado) "
        f"VALUES ('acme', 'x', 'x', {aid}, 9, 1, 'preparando')")
    datos.crear_tanda("acme", aid, GANCHOS_T)
    assert estado["hecho"] and estado["resultado"].startswith("bloqueado")


def test_mover_no_avanza_dos_veces_la_misma_variante(base_temporal):
    aid = _analisis()
    f1, _ = datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f1["id"], "preparando", "generando", cf_id="cf_1", job_id="acme__cf_1__creative_flow")
    assert not datos.mover(f1["id"], "preparando", "generando", cf_id="cf_2")      # ya no está en preparando
    g = datos.gancho("acme", f1["id"])
    assert g["estado"] == "generando" and g["cf_id"] == "cf_1" and g["job_id"] == "acme__cf_1__creative_flow"
    with pytest.raises(ValueError):
        datos.mover(f1["id"], "generando", "raro")
    with pytest.raises(ValueError):
        datos.actualizar_gancho(f1["id"], estado="lista")          # el estado solo cambia con mover
    with pytest.raises(ValueError):
        datos.mover(f1["id"], "generando", "armando", texto="otro")  # el texto del gancho no se reescribe
    assert datos.actualizar_gancho(f1["id"], frame_url="https://r2.test/f.jpg")
    assert datos.gancho("acme", f1["id"])["frame_url"] == "https://r2.test/f.jpg"
    assert datos.gancho("otro", f1["id"]) is None


def test_lecturas_filtran_por_proyecto_y_son_una_consulta(base_temporal):
    a1, a2 = _analisis(), _analisis("otro")
    for f in datos.crear_tanda("acme", a1, GANCHOS_T):
        datos.mover(f["id"], "preparando", "error", error="x")
    datos.crear_tanda("acme", a1, GANCHOS_T)
    datos.crear_tanda("otro", a2, GANCHOS_T)
    consultas = []
    contar = lambda conn, cursor, statement, *a: consultas.append(statement)  # noqa: E731
    event.listen(sa.engine.Engine, "before_cursor_execute", contar)
    try:
        filas = datos.ganchos_de_analisis("acme", a1)
        vivos = datos.ganchos_vivos()
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", contar)
    assert len(consultas) == 2
    assert [(f["tanda"], f["n"]) for f in filas] == [(2, 1), (2, 3), (1, 1), (1, 3)]
    assert datos.ganchos_de_analisis("otro", a1) == []
    assert sorted((f["cliente"], f["tanda"]) for f in vivos) == [("acme", 2), ("acme", 2), ("otro", 1), ("otro", 1)]

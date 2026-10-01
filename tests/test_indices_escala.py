"""Índices de la auditoría de consultas (migración 0026) y la tabla de errores
(0027): suben y bajan, db.py declara lo mismo que las migraciones, y las
consultas calientes que recorrían la tabla entera ahora usan un índice
(EXPLAIN QUERY PLAN, el mismo criterio que rendimiento/auditar_indices.py)."""
import os

import pytest
import sqlalchemy as sa
from sqlalchemy import event

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUEVOS = {
    "pieza": {"ix_pieza_padre"}, "publicacion": {"ix_publicacion_pieza"},
    "metrica_snapshot": {"ix_metrica_snapshot_pieza_tomado", "ix_metrica_snapshot_experimento_pieza_id"},
    "gasto": {"ix_gasto_creado"}, "experimento_pieza": {"ix_experimento_pieza_pieza"},
    "evento": {"ix_evento_experimento_pieza"}, "pedido": {"ix_pedido_experimento_pieza"},
    "avatar": {"ix_avatar_padre"}, "sprint_evento": {"ix_sprint_evento_campana"},
    "referente": {"ix_referente_fuente_estado"},
    "error_app": {"ix_error_app_estado_ultima", "ix_error_app_ultima"},
}


def _indices(engine, tabla):
    return {i["name"] for i in sa.inspect(engine).get_indexes(tabla)}


def test_migraciones_0026_y_0027_suben_y_bajan(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'escala.db'}")
    db._reset_para_tests()
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    command.upgrade(cfg, "head")
    for tabla, nombres in NUEVOS.items():
        assert nombres <= _indices(db.engine(), tabla), tabla
    cols = {c["name"] for c in sa.inspect(db.engine()).get_columns("error_app")}
    assert {"huella", "origen", "tipo", "mensaje", "traza", "veces", "estado", "ultima_vez"} <= cols
    db._reset_para_tests()
    command.downgrade(cfg, "0025")
    assert "error_app" not in sa.inspect(db.engine()).get_table_names()
    assert "ix_pieza_padre" not in _indices(db.engine(), "pieza")
    # El índice viejo de solo experimento_pieza_id se queda (sirve a «la última foto»).
    assert "ix_metrica_snapshot_experimento_pieza_id" in _indices(db.engine(), "metrica_snapshot")
    db._reset_para_tests()
    command.upgrade(cfg, "head")
    db._reset_para_tests()


def test_db_py_declara_los_mismos_indices(base_temporal):
    for tabla, nombres in NUEVOS.items():
        assert nombres <= _indices(base_temporal.engine(), tabla), tabla


class _Planes:
    """Junta el plan de cada consulta de la app mientras dura el bloque."""

    def __enter__(self):
        self.planes = []

        def mirar(conn, cursor, sql, parametros, context, executemany):
            if sql.lstrip()[:6].upper() not in ("SELECT", "DELETE"):
                return
            cur = cursor.connection.cursor()
            try:
                self.planes.append((sql, [f[3] for f in cur.execute("EXPLAIN QUERY PLAN " + sql, parametros or ())]))
            finally:
                cur.close()
        self._f = mirar
        event.listen(sa.engine.Engine, "before_cursor_execute", mirar)
        return self

    def __exit__(self, *a):
        event.remove(sa.engine.Engine, "before_cursor_execute", self._f)

    def recorridos(self, tabla):
        """Consultas que recorren `tabla` entera, sin índice."""
        return [sql for sql, plan in self.planes if any(p.strip() == f"SCAN {tabla}" for p in plan)]


def _crear_pieza_con_final(cf_id="cf_1"):
    import creative_flow
    cf = creative_flow.crear("acme", [], [], [], "acción", 8, "tono", "A", legado_id=cf_id)
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4")
    fid = creative_flow.crear_final("acme", cf, "es", "CO")
    return cf, fid


@pytest.mark.parametrize("llamada, tabla", [
    ("finales", "pieza"), ("captions", "publicacion"), ("snapshots", "metrica_snapshot"), ("cobros", "gasto"),
    ("borrar_sesion", "experimento_pieza"),
])
def test_las_consultas_calientes_usan_indice(base_temporal, llamada, tabla):
    import admin
    import creative_flow
    import experimentos
    import gastos
    import organico
    from doctrina import revisor
    cf, _fid = _crear_pieza_con_final()
    sin_publicar, _ = _crear_pieza_con_final("cf_2")     # una publicación no deja borrar su pieza
    organico.crear("acme", creative_flow.pieza_id_por_legado("acme", cf), "instagram", "un caption")
    gastos.registrar("acme", "video", 0.5, "video:cf_1")
    eid = experimentos.crear("acme", "P", [{"pais": "CO", "idioma": "es", "presupuesto_dia": 10}],
                             "OUTCOME_TRAFFIC", 7, 100, "https://x.test", "COP")
    with base_temporal.conectar() as con:
        ep = con.execute(base_temporal.experimento_pieza.insert().values(
            cliente="acme", creado_en="2026-09-01T00:00:00", actualizado_en="2026-09-01T00:00:00",
            experimento_id=eid, pais="CO", estado="activo", extra={})).inserted_primary_key[0]
    experimentos.snapshot(ep, {"gasto": 1}, tomado_en="2026-09-02T00:00:00")
    hacer = {
        "finales": lambda: creative_flow.finales_por_sesion("acme"),
        "captions": lambda: revisor.ultimos_captions("acme"),
        "snapshots": lambda: experimentos.snapshots(ep, desde="2026-09-01T00:00:00"),
        "cobros": lambda: admin.ultimos_cobros(),
        "borrar_sesion": lambda: creative_flow.eliminar("acme", sin_publicar),
    }[llamada]
    with _Planes() as p:
        hacer()
    assert p.planes, "la llamada no consultó nada"
    assert not p.recorridos(tabla), p.recorridos(tabla)
    if llamada == "snapshots":
        # La base del delta no lee ni ordena todo el historial de la pieza.
        base = [plan for sql, plan in p.planes if "tomado_en <" in sql]
        assert base and any("ix_metrica_snapshot_pieza_tomado" in x for x in base[0]), base
        assert not any("TEMP B-TREE" in x for x in base[0]), base

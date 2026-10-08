"""Migración 0032 (spec 2026-10-08 §3): tw_tienda y tienda_id en las copias de Triple Whale."""
import json
import os

import pytest
import sqlalchemy as sa


def _config():
    from alembic.config import Config
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Config(os.path.join(raiz, "alembic.ini"))


@pytest.fixture
def base(tmp_path, monkeypatch):
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig32.db'}")
    db._reset_para_tests()
    yield db
    db._reset_para_tests()


def _anuncio(con, cliente, ad_id="a1", fecha="2026-10-01", tienda=None):
    cols = "cliente, fecha, canal, ad_id, actualizado_en" + (", tienda_id" if tienda is not None else "")
    vals = ":c, :f, 'facebook-ads', :a, 'x'" + (", :t" if tienda is not None else "")
    con.execute(sa.text(f"INSERT INTO tw_anuncio_dia ({cols}) VALUES ({vals})"),
                {"c": cliente, "f": fecha, "a": ad_id, "t": tienda})


def _sembrar_0031(con):
    con.execute(sa.text(
        "INSERT INTO triple_whale (cliente, creado_en, actualizado_en, llave, dominio_tienda, moneda, "
        "zona_horaria, estado, error, ultima_sincronizacion, extra) VALUES ('acme', '2026-09-01 10:00:00', "
        "'2026-09-02 10:00:00', 'cifrada', 'happyflops-norge.myshopify.com', 'USD', 'Europe/Oslo', 'error', "
        "'boom', '2026-10-01T10:00:00', :x)"),
        {"x": json.dumps({"backfill_desde": "2026-07-01", "ultimo_resumen": {"ingresos": 5},
                          "gasto_7d": 12.5, "avisados": {"k": 1}, "aviso_sin_ventas": "2026-10-01"})})
    _anuncio(con, "acme")
    _anuncio(con, "acme", ad_id="a2")
    con.execute(sa.text("INSERT INTO tw_tienda_dia (cliente, fecha, actualizado_en) VALUES ('acme', '2026-10-01', 'x')"))
    con.execute(sa.text("INSERT INTO tw_producto_dia (cliente, fecha, producto_id, actualizado_en) "
                        "VALUES ('acme', '2026-10-01', 'p1', 'x')"))
    # huérfanas: un proyecto sin conexión
    _anuncio(con, "huerfano")
    con.execute(sa.text("INSERT INTO tw_tienda_dia (cliente, fecha, actualizado_en) VALUES ('huerfano', '2026-10-01', 'x')"))
    con.execute(sa.text("INSERT INTO tw_producto_dia (cliente, fecha, producto_id, actualizado_en) "
                        "VALUES ('huerfano', '2026-10-01', 'p1', 'x')"))


def test_sube_crea_la_tienda_con_su_pais_y_llena_las_copias(base):
    from alembic import command
    db = base
    command.upgrade(_config(), "0031")
    with db.engine().begin() as con:
        _sembrar_0031(con)
    command.upgrade(_config(), "0032")
    with db.engine().begin() as con:
        t = con.execute(sa.text("SELECT * FROM tw_tienda")).mappings().all()
        assert len(t) == 1
        t = dict(t[0])
        assert t["cliente"] == "acme" and t["pais"] == "NO" and t["llave"] == "cifrada"
        assert t["dominio"] == "happyflops-norge.myshopify.com" and t["zona_horaria"] == "Europe/Oslo"
        assert t["estado"] == "error" and t["error"] == "boom"
        assert t["ultima_sincronizacion"] == "2026-10-01T10:00:00"
        assert t["creado_en"] == "2026-09-01 10:00:00"
        assert json.loads(t["extra"]) == {"backfill_desde": "2026-07-01", "ultimo_resumen": {"ingresos": 5},
                                          "gasto_7d": 12.5}
        # (a) todas las filas de copias de acme llevan su tienda
        for tabla, n in (("tw_anuncio_dia", 2), ("tw_tienda_dia", 1), ("tw_producto_dia", 1)):
            assert con.execute(sa.text(f"SELECT count(*) FROM {tabla} WHERE cliente='acme' AND tienda_id=:t"),
                               {"t": t["id"]}).scalar() == n
            # (b) las huérfanas se borraron
            assert con.execute(sa.text(f"SELECT count(*) FROM {tabla} WHERE cliente='huerfano'")).scalar() == 0
        # la fila vieja de triple_whale sigue entera
        v = con.execute(sa.text("SELECT llave, extra FROM triple_whale WHERE cliente='acme'")).mappings().one()
        assert v["llave"] == "cifrada" and json.loads(v["extra"])["avisados"] == {"k": 1}
    insp = sa.inspect(db.engine())
    for tabla in ("tw_tienda", "tw_anuncio_dia", "tw_tienda_dia", "tw_producto_dia", "triple_whale"):
        assert {c["name"] for c in insp.get_columns(tabla)} == {c.name for c in db.metadata.tables[tabla].columns}
    for tabla in ("tw_anuncio_dia", "tw_tienda_dia", "tw_producto_dia"):
        col = next(c for c in insp.get_columns(tabla) if c["name"] == "tienda_id")
        assert col["nullable"] is False
    assert {u["name"]: tuple(u["column_names"]) for u in insp.get_unique_constraints("tw_anuncio_dia")} == {
        "uq_tw_anuncio_dia": ("cliente", "tienda_id", "canal", "ad_id", "fecha")}
    assert {u["name"] for u in insp.get_unique_constraints("tw_tienda_dia")} == {"uq_tw_tienda_dia"}
    assert {u["name"] for u in insp.get_unique_constraints("tw_producto_dia")} == {"uq_tw_producto_dia"}
    assert "uq_tw_tienda_dominio" in {u["name"] for u in insp.get_unique_constraints("tw_tienda")}
    nombres = {i["name"] for i in insp.get_indexes("tw_tienda")}
    assert {"ix_tw_tienda_cliente", "uq_tw_tienda_pais"} <= nombres
    assert "ix_tw_anuncio_dia_cliente_tienda_fecha" in {i["name"] for i in insp.get_indexes("tw_anuncio_dia")}
    assert "ix_tw_producto_dia_cliente_tienda_fecha" in {i["name"] for i in insp.get_indexes("tw_producto_dia")}
    assert "ix_tw_anuncio_dia_cliente_fecha" in {i["name"] for i in insp.get_indexes("tw_anuncio_dia")}


def test_la_misma_fila_cabe_con_otra_tienda_y_el_pais_es_unico(base):
    from alembic import command
    db = base
    command.upgrade(_config(), "0031")
    with db.engine().begin() as con:
        _sembrar_0031(con)
    command.upgrade(_config(), "0032")
    with db.engine().begin() as con:
        con.execute(sa.text("INSERT INTO tw_tienda (cliente, creado_en, actualizado_en, dominio, pais) "
                            "VALUES ('acme', 'x', 'x', 'happyflops-sverige.myshopify.com', 'SE')"))
        otra = con.execute(sa.text("SELECT id FROM tw_tienda WHERE pais='SE'")).scalar()
        _anuncio(con, "acme", ad_id="a1", tienda=otra)          # (c) mismo (cliente, canal, ad_id, fecha)
        assert con.execute(sa.text("SELECT count(*) FROM tw_anuncio_dia WHERE ad_id='a1'")).scalar() == 2
        # varias tiendas sin país caben; el mismo país dos veces, no
        for d in ("a.myshopify.com", "b.myshopify.com"):
            con.execute(sa.text("INSERT INTO tw_tienda (cliente, creado_en, actualizado_en, dominio) "
                                "VALUES ('acme', 'x', 'x', :d)"), {"d": d})
    with pytest.raises(sa.exc.IntegrityError):
        with db.engine().begin() as con:
            con.execute(sa.text("INSERT INTO tw_tienda (cliente, creado_en, actualizado_en, dominio, pais) "
                                "VALUES ('acme', 'x', 'x', 'c.myshopify.com', 'SE')"))
    with pytest.raises(sa.exc.IntegrityError):               # y la misma fila con la MISMA tienda, tampoco
        with db.engine().begin() as con:
            _anuncio(con, "acme", ad_id="a1", tienda=otra)


def test_baja_deja_una_sola_tienda_por_proyecto_y_el_esquema_viejo(base):
    from alembic import command
    db = base
    command.upgrade(_config(), "0031")
    with db.engine().begin() as con:
        _sembrar_0031(con)
    command.upgrade(_config(), "0032")
    with db.engine().begin() as con:
        con.execute(sa.text("INSERT INTO tw_tienda (cliente, creado_en, actualizado_en, dominio, pais) "
                            "VALUES ('acme', 'x', 'x', 'happyflops-sverige.myshopify.com', 'SE')"))
        otra = con.execute(sa.text("SELECT id FROM tw_tienda WHERE pais='SE'")).scalar()
        _anuncio(con, "acme", ad_id="a1", tienda=otra)
        con.execute(sa.text("INSERT INTO tw_tienda_dia (cliente, tienda_id, fecha, actualizado_en) "
                            "VALUES ('acme', :t, '2026-10-01', 'x')"), {"t": otra})
        con.execute(sa.text("INSERT INTO tw_producto_dia (cliente, tienda_id, fecha, producto_id, actualizado_en) "
                            "VALUES ('acme', :t, '2026-10-01', 'p1', 'x')"), {"t": otra})
    command.downgrade(_config(), "0031")
    insp = sa.inspect(db.engine())
    assert "tw_tienda" not in insp.get_table_names()
    for tabla in ("tw_anuncio_dia", "tw_tienda_dia", "tw_producto_dia"):
        assert "tienda_id" not in {c["name"] for c in insp.get_columns(tabla)}
    assert {u["name"]: tuple(u["column_names"]) for u in insp.get_unique_constraints("tw_anuncio_dia")} == {
        "uq_tw_anuncio_dia": ("cliente", "canal", "ad_id", "fecha")}
    assert tuple(insp.get_unique_constraints("tw_tienda_dia")[0]["column_names"]) == ("cliente", "fecha")
    assert tuple(insp.get_unique_constraints("tw_producto_dia")[0]["column_names"]) == ("cliente", "producto_id", "fecha")
    assert "ix_tw_anuncio_dia_cliente_fecha" in {i["name"] for i in insp.get_indexes("tw_anuncio_dia")}
    assert "ix_tw_anuncio_dia_cliente_tienda_fecha" not in {i["name"] for i in insp.get_indexes("tw_anuncio_dia")}
    with db.engine().begin() as con:
        assert con.execute(sa.text("SELECT count(*) FROM tw_anuncio_dia")).scalar() == 2   # solo la 1.ª tienda
        assert con.execute(sa.text("SELECT count(*) FROM tw_tienda_dia")).scalar() == 1
        assert con.execute(sa.text("SELECT count(*) FROM tw_producto_dia")).scalar() == 1
        assert con.execute(sa.text("SELECT llave FROM triple_whale WHERE cliente='acme'")).scalar() == "cifrada"
    # y sube de nuevo sin romperse
    command.upgrade(_config(), "0032")
    with db.engine().begin() as con:
        assert con.execute(sa.text("SELECT count(*) FROM tw_tienda")).scalar() == 1


def test_base_sin_datos_sube_y_baja(base):
    from alembic import command
    db = base
    command.upgrade(_config(), "head")
    assert "tw_tienda" in sa.inspect(db.engine()).get_table_names()
    command.downgrade(_config(), "0031")
    assert "tw_tienda" not in sa.inspect(db.engine()).get_table_names()
    command.upgrade(_config(), "head")

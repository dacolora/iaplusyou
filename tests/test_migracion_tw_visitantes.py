"""Migración 0036 (spec 2026-10-09-nvp-visitantes-nuevos §3): visitantes para el NVP en las copias de Triple Whale."""
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
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig36.db'}")
    db._reset_para_tests()
    yield db
    db._reset_para_tests()


def test_sube_agrega_visitantes_en_cero_sin_tocar_lo_copiado_y_baja(base):
    from alembic import command
    db = base
    command.upgrade(_config(), "0035")
    with db.engine().begin() as con:
        con.execute(sa.text("INSERT INTO tw_tienda (cliente, pais, dominio, estado, creado_en, actualizado_en) "
                            "VALUES ('acme', 'NO', 'acme.myshopify.com', 'conectada', 'x', 'x')"))
        con.execute(sa.text("INSERT INTO tw_anuncio_dia (cliente, tienda_id, fecha, canal, ad_id, pedidos, "
                            "actualizado_en) VALUES ('acme', 1, '2026-10-01', 'facebook-ads', 'a1', 2, 'x')"))
        con.execute(sa.text("INSERT INTO tw_tienda_dia (cliente, tienda_id, fecha, ingresos, actualizado_en) "
                            "VALUES ('acme', 1, '2026-10-01', 300, 'x')"))
    command.upgrade(_config(), "0036")
    with db.engine().begin() as con:
        a = con.execute(sa.text("SELECT pedidos, visitantes, visitantes_nuevos FROM tw_anuncio_dia")).mappings().one()
        assert dict(a) == {"pedidos": 2, "visitantes": 0, "visitantes_nuevos": 0}
        t = con.execute(sa.text("SELECT ingresos, visitantes, visitantes_nuevos FROM tw_tienda_dia")).mappings().one()
        assert dict(t) == {"ingresos": 300, "visitantes": 0, "visitantes_nuevos": 0}
    insp = sa.inspect(db.engine())
    for tabla in ("tw_anuncio_dia", "tw_tienda_dia"):
        assert {c["name"] for c in insp.get_columns(tabla)} == {c.name for c in db.metadata.tables[tabla].columns}
    command.downgrade(_config(), "0035")
    insp = sa.inspect(db.engine())
    for tabla in ("tw_anuncio_dia", "tw_tienda_dia"):
        assert not {"visitantes", "visitantes_nuevos"} & {c["name"] for c in insp.get_columns(tabla)}
    with db.engine().begin() as con:
        assert con.execute(sa.text("SELECT pedidos FROM tw_anuncio_dia")).scalar() == 2

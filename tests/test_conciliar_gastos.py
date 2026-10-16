"""deploy/conciliar_gastos.py (PND-013): suma la tabla gasto por proveedor y mes, sin escribir nada."""
import importlib.util
import os

import pytest
import sqlalchemy as sa

RUTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "conciliar_gastos.py")


@pytest.fixture()
def conciliar():
    spec = importlib.util.spec_from_file_location("conciliar_gastos", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sembrar():
    import gastos
    gastos.registrar("acme", "video", 1.5, "video:1:t1", proveedor="wavespeed", creado_en="2026-09-10T10:00:00")
    gastos.registrar("acme", "swap", 2.2, "swap:s:t1", proveedor="seedance25_edit", creado_en="2026-09-11T10:00:00")
    gastos.registrar("acme", "swap", 0.5, "swap:k:t1", proveedor="kling_o1", creado_en="2026-09-12T10:00:00")
    gastos.registrar("acme", "swap", 0.039, "swap:g:t1", proveedor="nano_banana", creado_en="2026-09-12T10:00:00")
    gastos.registrar("acme", "final", 0.30, "final:cf__es_CO:t1", proveedor="fal/anthropic",
                     extra={"capas": {"guion": 0.05, "voz": 0.20, "musica": 0.02}}, creado_en="2026-10-01T10:00:00")
    gastos.registrar("acme", "recoleccion", 0.40, "recoleccion:1:t1", proveedor="apify",
                     extra={"estimado": True}, creado_en="2026-10-02T10:00:00")
    gastos.registrar("_creatv", "otro", 0.03, "claude:x", proveedor="anthropic", creado_en="2026-10-03T10:00:00")
    gastos.registrar("otro", "locucion", 0.01, "locucion:x", proveedor="fal/minimax", creado_en="2026-10-04T10:00:00")


def test_suma_por_empresa_y_mes_y_parte_las_finales(base_temporal, conciliar):
    _sembrar()
    r = conciliar.resumen()
    assert r[("2026-09", "wavespeed")]["usd"] == pytest.approx(3.7)
    assert r[("2026-09", "fal")]["usd"] == pytest.approx(0.5)
    assert r[("2026-09", "google")]["usd"] == pytest.approx(0.039)
    assert r[("2026-10", "anthropic")]["usd"] == pytest.approx(0.05 + 0.03)      # el guion de la final + _creatv
    assert r[("2026-10", "fal")]["usd"] == pytest.approx(0.22 + 0.01)
    assert r[("2026-10", "fal/anthropic")]["usd"] == pytest.approx(0.03)         # lo que no cae en una capa
    assert r[("2026-10", "apify")]["estimadas"] == 1


def test_filtra_por_rango_y_proyecto_y_no_escribe(base_temporal, conciliar, capsys):
    import db
    _sembrar()
    with db.conectar() as con:
        antes = con.execute(sa.select(sa.func.count()).select_from(db.gasto)).scalar()
    r = conciliar.resumen(desde="2026-10", hasta="2026-10", proyecto="acme")
    assert {mes for mes, _ in r} == {"2026-10"} and ("2026-10", "fal") in r
    assert r[("2026-10", "fal")]["usd"] == pytest.approx(0.22)                   # sin el de «otro»
    assert conciliar.main(["--desde", "2026-09", "--hasta", "2026-12"]) == 0
    salida = capsys.readouterr().out
    assert "2026-09" in salida and "wavespeed" in salida and "Total" in salida
    assert conciliar.main(["--csv"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "mes;proveedor;usd;filas;estimadas;usd_estimado"
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.gasto)).scalar() == antes


def test_mes_siguiente(conciliar):
    assert conciliar._mes_siguiente("2026-12") == "2027-01" and conciliar._mes_siguiente("2026-09") == "2026-10"

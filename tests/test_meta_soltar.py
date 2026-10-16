"""PND-207 (decisión 2026-10-13): `meta_conexion.borrar` y `meta_agencia.desasignar` borran por sí solas lo copiado de
Meta del proyecto (métricas, análisis de fuente Meta y evaluaciones con IA) y liberan sus cuentas. Antes lo hacía la
ruta (`dashboard._soltar_cuentas_meta`) y un llamador nuevo podía dejar las copias que /privacidad y /eliminar-datos
prometen borrar. Sin red: lo que haya en R2 se borra con un doble."""
import pytest

import meta_conexion as mc
from tests.test_meta_agencia import entorno  # noqa: F401  (fixture: kv y clientes/ temporales, Graph falso)

NORWAY = {"id": "act_5", "name": "HappyFlops Norway", "currency": "SEK"}
SWEDEN = {"id": "act_6", "name": "HappyFlops Sweden", "currency": "SEK"}


@pytest.fixture()
def r2(monkeypatch):
    from meta_rendimiento import analisis, creativo
    borradas = []
    monkeypatch.setattr(analisis, "borrar_claves", lambda claves: borradas.extend(claves) or (len(claves), []))
    monkeypatch.setattr(creativo, "borrar_copias", lambda c, filas: borradas.extend(filas) or (len(filas), []))
    return borradas


def _copias(cliente, cuenta):
    """La cuenta elegida con una fila de métricas, un análisis «Cómo mejorarlo» de fuente Meta y una evaluación."""
    from meta_rendimiento import cuentas, datos
    from triple_whale import datos as tw_datos
    cuentas.elegir(cliente, [cuenta])
    act = cuenta["id"]
    datos.reemplazar_cuenta_dias(cliente, act, "2026-10-01", "2026-10-01", [{"fecha": "2026-10-01", "gasto": 1}])
    tw_datos.crear_analisis(cliente, None, "facebook-ads", "111", "2026-09-01", "2026-09-30", "SEK",
                            {"fuente": "meta", "ad_account_id": act, "nombre": "Video"})
    return datos.crear_evaluacion(cliente, [act], "2026-09-01", "2026-09-30", "SEK", [{"ref": "A1"}], [], "ana")


def _quedan(cliente):
    import sqlalchemy as sa

    import db
    with db.conectar() as con:
        return sum(con.execute(sa.select(sa.func.count()).select_from(t).where(t.c.cliente == cliente)).scalar()
                   for t in (db.meta_cuenta, db.meta_cuenta_dia, db.tw_analisis, db.meta_evaluacion))


def test_borrar_la_conexion_propia_borra_lo_copiado_de_ese_proyecto(entorno, r2):  # noqa: F811
    _copias("acme", NORWAY)
    _copias("otro", SWEDEN)
    mc.guardar("acme", {"token": "TOKEN-PROPIO", "ad_account_id": "act_1", "page_id": "9"})
    r = mc.borrar("acme")
    assert r and r.fallo is None and mc.cargar("acme") is None
    assert _quedan("acme") == 0 and _quedan("otro") == 4
    assert r2                                     # sus copias en R2, después de las filas


def test_desasignar_borra_lo_copiado_de_ese_proyecto(entorno, r2):  # noqa: F811
    ma = entorno["ma"]
    _copias("acme", NORWAY)
    _copias("otro", SWEDEN)
    mc.guardar("acme", {"modo": "agencia", "ad_account_id": "act_1", "page_id": "p1"}, permitir_agencia=True)
    r = ma.desasignar("acme")
    assert r and r.fallo is None and mc.modo("acme") == "propia"
    assert _quedan("acme") == 0 and _quedan("otro") == 4


def test_desasignar_lo_que_no_estaba_asignado_no_borra_nada(entorno, r2):  # noqa: F811
    _copias("acme", NORWAY)
    mc.guardar("acme", {"token": "TOKEN-PROPIO", "ad_account_id": "act_1"})
    r = entorno["ma"].desasignar("acme")
    assert not r and r.fallo is None and _quedan("acme") == 4


def test_desconectar_la_agencia_suelta_cada_proyecto_asignado(entorno, r2):  # noqa: F811
    ma = entorno["ma"]
    _copias("acme", NORWAY)
    _copias("otro", SWEDEN)
    mc.guardar("acme", {"modo": "agencia", "ad_account_id": "act_1", "page_id": "p1"}, permitir_agencia=True)
    assert ma.desconectar() == {"habia": False, "desasignados": 1, "fallos": {}}
    assert _quedan("acme") == 0 and _quedan("otro") == 4


def test_si_no_se_puede_borrar_lo_copiado_la_desconexion_se_queda_y_dice_el_tipo(entorno, r2, monkeypatch):  # noqa: F811
    from meta_rendimiento import cuentas
    _copias("acme", NORWAY)

    def falla(con, cliente, act):
        raise RuntimeError("disco lleno TOKEN-PROPIO")
    monkeypatch.setattr(cuentas, "_borrar_copias", falla)
    mc.guardar("acme", {"token": "TOKEN-PROPIO", "ad_account_id": "act_1"})
    r = mc.borrar("acme")
    assert r and r.fallo == "RuntimeError" and mc.cargar("acme") is None
    assert cuentas.ids("acme") == ["act_5"]            # se reintenta en la próxima desconexión


def test_en_modo_agencia_borrar_rechaza_sin_soltar_nada(entorno, r2):  # noqa: F811
    _copias("acme", NORWAY)
    mc.guardar("acme", {"modo": "agencia", "ad_account_id": "act_1"}, permitir_agencia=True)
    with pytest.raises(mc.ModoAgenciaError):
        mc.borrar("acme")
    assert _quedan("acme") == 4

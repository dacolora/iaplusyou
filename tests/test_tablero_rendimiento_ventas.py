"""Sonda de 60 piezas/180 días y guarda determinista contra recorrer historias sin ventas."""
import pytest
import time
from datetime import datetime, timedelta


def test_centro_trafico_60_piezas_180_dias(base_temporal):
    import db, experimentos as ex, resultados as r, tablero
    from tests.test_experimentos_db import _pieza, PAISES
    ahora = "2026-10-02T12:00:00"
    ini = datetime(2026, 4, 5)
    filas = []
    for e in range(3):
        eid = ex.crear("acme", f"Trafico {e}", PAISES, "OUTCOME_TRAFFIC", 14, 500.0, "https://t.co/p", "USD")
        for k in range(20):
            ep = ex.agregar_pieza("acme", eid, _pieza(base_temporal, tipo="video", estado="listo", pais=None,
                                                      idioma=None, legado=f"cf_{e}_{k}"), "CO")
            for i in range(12 * 180):
                filas.append(dict(experimento_pieza_id=ep, tomado_en=(ini + timedelta(hours=2 * i)).isoformat(),
                                  gasto=float(i), impresiones=10 * i, clics_enlace=i, compras=0, ingresos=0.0,
                                  fuente_ventas="ninguna", extra={}))
    with db.conectar() as con:
        con.execute(db.metrica_snapshot.insert(), filas)
    t = time.perf_counter()
    carga = r.cargar("acme", r.Filtro(dias=0), ahora)
    kpis = {k["clave"]: k for k in r.indicadores(carga)}
    piezas = r.piezas(carga, {})
    paises = r.paises(carga)
    tarjetas = r.experimentos_tarjetas(carga)
    t1 = time.perf_counter() - t
    t = time.perf_counter()
    d = tablero.cargar_datos("acme", ahora)
    tablero.mes_a_mes("acme", ahora, datos=d); tablero.resumen_total("acme", ahora, datos=d); tablero.csv_mes("acme", ahora, datos=d)
    t2 = time.perf_counter() - t
    print(f"\nCENTRO Todo: {t1:.2f}s   TABLERO: {t2:.2f}s")
    assert len(piezas) == 60 and len(tarjetas) == 3 and len(paises) == 1
    assert kpis["gasto"]["valor"] > 0
    assert all(kpis[k]["valor"] is None for k in ("compras", "ingresos", "roas", "cpa"))
    total = tablero.resumen_total("acme", ahora, datos=d)["por_moneda"]["USD"]
    assert total["compras"] == 0 and total["ingresos"] == 0 and total["roas_comparable"]


@pytest.mark.parametrize("primera_venta", [None, "2026-10-01T00:00:00"])
def test_delta_sin_ventas_hasta_cierre_no_recorre_historia(primera_venta):
    import tablero
    from tests.test_tablero import _snap

    class SinRecorrido(list):
        def __iter__(self):
            raise AssertionError("se recorrió la historia sin ventas antes del cierre")

    serie = tablero.Serie([
        _snap("2026-09-01T00:00:00", gasto=10, compras=0, ingresos=0, fuente_ventas="ninguna"),
        _snap("2026-09-03T00:00:00", gasto=30, compras=0, ingresos=0, fuente_ventas="ninguna"),
    ], primera_venta=primera_venta)
    serie.snaps = SinRecorrido(serie.snaps)
    assert tablero._deltas_pieza(serie, "2026-09-02T00:00:00", "2026-09-04T00:00:00") == {
        "gasto": 20, "compras": 0, "ingresos": 0, "clics_enlace": 0, "impresiones": 0,
        "mide": False, "roas_comparable": True, "ventas_cambiaron": False,
    }

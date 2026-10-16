"""PND-066 (decisión 2026-10-13): `metrica_snapshot` guarda la foto solo si cambió algo.

El refresco de cada 2 h guardaba una fila aunque nada cambiara. Ahora una foto igual a la última no agrega fila: la
última anota `extra.confirmado_en`. Estas pruebas demuestran que las cuentas que dependían de tener una fila cada 2 h
dan lo mismo (Tablero, «Mes a mes», serie de 30 días, `snapshots(desde=)`, el decisor y sus horas de evidencia) y que
la frescura («datos viejos», la alerta de 6 h sin métricas) cuenta la confirmación."""
from datetime import datetime, timedelta

import pytest

from tests.test_experimentos_db import PAISES, _pieza

AHORA = "2026-10-10T12:00:00"


def _crear(cliente, atribucion="pixel"):
    import experimentos as ex
    eid = ex.crear(cliente, "Prueba", PAISES, "OUTCOME_SALES", 30, 5_000_000.0, "https://t", "COP", atribucion=atribucion)
    ex.actualizar(cliente, eid, estado="corriendo")
    return eid


def _pieza_en(db, cliente, eid, legado):
    import experimentos as ex
    pid = _pieza(db, cliente=cliente, legado=legado, pais="CO")
    ep = ex.agregar_pieza(cliente, eid, pid, "CO")
    ex.actualizar_pieza(cliente, ep, estado="activo", meta_ad_id="ad_" + legado)
    return ep


def _guardar_siempre(ep_id, metricas, tomado_en):
    """Lo que hacía `experimentos.snapshot` antes de PND-066: una fila por consulta, cambiara o no."""
    import db
    import experimentos as ex
    valores, extra = {}, {}
    for k, v in metricas.items():
        if k in ex._SNAP_COLS:
            valores[k] = (v or "ninguna") if k == "fuente_ventas" else (
                int(float(v or 0)) if k in ex._SNAP_INT else float(v or 0))
        else:
            extra[k] = v
    with db.conectar() as con:
        con.execute(db.metrica_snapshot.insert().values(experimento_pieza_id=ep_id, tomado_en=tomado_en, extra=extra,
                                                        **valores))


def _lecturas():
    """Lo que Meta devuelve cada 2 h del 2026-08-28 al 2026-10-10 (acumulado): mesetas largas (un fin de mes
    entero sin cambios, otra que cruza el arranque de la serie de 30 días y otra que cruza medianoche), ventas
    del Pixel desde el 2026-09-05, una corrección de Meta hacia abajo, cambios sin gasto nuevo (una venta de
    noche, un clic tardío) y el estado del anuncio en `extra`."""
    t = datetime(2026, 8, 28, 0, 0, 0)
    fin = datetime(2026, 10, 10, 10, 0, 0)
    gasto, imp, clics, compras, ingresos = 0.0, 0, 0, 0, 0.0
    out = []
    while t <= fin:
        dia = t.date().isoformat()
        quieto = ("2026-08-30" <= dia <= "2026-09-02"          # fin de mes sin cambios
                  or "2026-09-08" <= dia <= "2026-09-13"       # cruza el arranque de la serie de 30 días
                  or (t.hour >= 20 or t.hour < 6)              # noches: cruza medianoche
                  or dia == "2026-10-01")
        if dia >= "2026-08-29" and not quieto:
            gasto += 1500.0 + (t.hour * 37) % 400
            imp += 900 + (t.hour * 53) % 300
            clics += 11 + t.hour % 5
            if dia >= "2026-09-05" and t.hour in (10, 14):
                compras += 1
                ingresos += 90000.0
        if dia == "2026-09-20" and t.hour == 12:
            gasto -= 2000.0                                    # Meta corrige hacia abajo
        if dia == "2026-09-15" and t.hour == 2:
            compras += 1                                       # una venta atribuida de noche, sin gasto nuevo
            ingresos += 90000.0
        if dia == "2026-09-25" and t.hour == 22:
            clics += 1                                         # un clic tardío, sin gasto ni impresiones
        m = {"impresiones": imp, "clics_enlace": clics, "gasto": round(gasto, 2), "compras": compras,
             "ingresos": ingresos, "ctr": round(clics / imp * 100, 4) if imp else 0.0,
             "cpc": round(gasto / clics, 4) if clics else 0.0, "roas": round(ingresos / gasto, 4) if gasto else 0.0,
             "fuente_ventas": "meta" if compras else "ninguna",
             "estado_meta_texto": "En revisión" if dia < "2026-08-29" else "Activo"}
        out.append((t.isoformat(), m))
        t += timedelta(hours=2)
    return out


@pytest.fixture()
def dos_proyectos(base_temporal):
    """«nuevo» guarda con `experimentos.snapshot` (solo si cambió); «viejo», la misma serie fila por fila."""
    import experimentos as ex
    db = base_temporal
    ep_n = _pieza_en(db, "nuevo", _crear("nuevo"), "cf_n__es_CO")
    ep_v = _pieza_en(db, "viejo", _crear("viejo"), "cf_v__es_CO")
    for tomado, m in _lecturas():
        ex.snapshot(ep_n, m, tomado_en=tomado)
        _guardar_siempre(ep_v, m, tomado)
    return {"db": db, "nuevo": ep_n, "viejo": ep_v}


def _filas(db, ep):
    import sqlalchemy as sa
    with db.conectar() as con:
        return con.execute(sa.select(sa.func.count()).select_from(db.metrica_snapshot)
                           .where(db.metrica_snapshot.c.experimento_pieza_id == ep)).scalar()


def _sin_hora(snap):
    """La foto sin lo que dice CUÁNDO se tomó ni de qué pieza es (en `_cierres_de_mes`, también su mes y su orden)."""
    import experimentos as ex
    fuera = ("tomado_en", ex.CONFIRMADO_EN, "experimento_pieza_id", "mes", "n")
    return {k: v for k, v in (snap or {}).items() if k not in fuera}


# ---------- la foto ----------

def test_una_foto_igual_no_agrega_fila_y_confirma_la_ultima(base_temporal):
    import experimentos as ex
    ep = _pieza_en(base_temporal, "acme", _crear("acme"), "cf_1__es_CO")
    m = {"impresiones": 100, "gasto": 50.0, "estado_meta_texto": "Activo"}
    a = ex.snapshot(ep, m, tomado_en="2026-10-01T08:00:00")
    assert ex.snapshot(ep, dict(m), tomado_en="2026-10-01T10:00:00") == a
    assert ex.snapshot(ep, dict(m), tomado_en="2026-10-01T12:00:00") == a
    assert _filas(base_temporal, ep) == 1
    u = ex.ultima_metrica(ep)
    assert u["tomado_en"] == "2026-10-01T08:00:00" and u[ex.CONFIRMADO_EN] == "2026-10-01T12:00:00"
    assert ex.consultado_en(u) == "2026-10-01T12:00:00"
    # Cambia una columna, o solo el `extra` (el estado del anuncio): fila nueva.
    b = ex.snapshot(ep, {**m, "gasto": 51.0}, tomado_en="2026-10-01T14:00:00")
    c = ex.snapshot(ep, {**m, "gasto": 51.0, "estado_meta_texto": "En pausa"}, tomado_en="2026-10-01T16:00:00")
    assert len({a, b, c}) == 3 and _filas(base_temporal, ep) == 3
    assert ex.CONFIRMADO_EN not in ex.ultima_metrica(ep) and ex.consultado_en(ex.ultima_metrica(ep)) == "2026-10-01T16:00:00"
    # Una foto con hora anterior a la última (un backfill) se guarda como siempre, aunque sea igual.
    ex.snapshot(ep, {**m, "gasto": 51.0, "estado_meta_texto": "En pausa"}, tomado_en="2026-09-30T00:00:00")
    assert _filas(base_temporal, ep) == 4


def test_una_columna_que_falta_vale_su_defecto_al_comparar(base_temporal):
    """Lo que la foto no trae se guarda con el `default` de la tabla: una foto sin `fuente_ventas` es igual a una con
    «ninguna», y una con `compras` 0 igual a una sin compras."""
    import experimentos as ex
    ep = _pieza_en(base_temporal, "acme", _crear("acme"), "cf_1__es_CO")
    ex.snapshot(ep, {"impresiones": 10, "gasto": 5.0}, tomado_en="2026-10-01T08:00:00")
    ex.snapshot(ep, {"impresiones": 10, "gasto": 5.0, "fuente_ventas": "ninguna", "compras": 0},
                tomado_en="2026-10-01T10:00:00")
    assert _filas(base_temporal, ep) == 1


# ---------- las cuentas dan lo mismo ----------

def test_guarda_muchas_menos_filas(dos_proyectos):
    d = dos_proyectos
    n, v = _filas(d["db"], d["nuevo"]), _filas(d["db"], d["viejo"])
    assert v == len(_lecturas()) and n < v / 2


def test_el_valor_en_cada_instante_y_los_deltas_son_los_mismos(dos_proyectos):
    import experimentos as ex
    import tablero
    d = dos_proyectos
    sn, sv = tablero.Serie(ex.snapshots(d["nuevo"])), tablero.Serie(ex.snapshots(d["viejo"]))
    instantes = [t for t, _m in _lecturas()][::3] + ["2026-08-27T00:00:00", "2026-09-01T00:00:00",
                                                       "2026-10-01T00:00:00", AHORA]
    for t in instantes:
        assert _sin_hora(sn.en(t)) == _sin_hora(sv.en(t)), t
    assert sn.primera_venta == sv.primera_venta
    for a, b in zip(instantes, instantes[7:]):
        assert tablero._deltas_pieza(sn, a, b) == tablero._deltas_pieza(sv, a, b), (a, b)
    # Con la base del delta (la última foto antes de la ventana) leída de la base, como el Tablero.
    for desde in ("2026-09-01T00:00:00", "2026-09-10T00:00:00", "2026-09-11T00:00:00", "2026-10-01T00:00:00"):
        vn = tablero.Serie(ex.snapshots(d["nuevo"], desde=desde), tablero._primeras_ventas([d["nuevo"]]).get(d["nuevo"]))
        vv = tablero.Serie(ex.snapshots(d["viejo"], desde=desde), tablero._primeras_ventas([d["viejo"]]).get(d["viejo"]))
        for hasta in ("2026-09-12T00:00:00", "2026-09-20T13:00:00", "2026-10-02T00:00:00", AHORA):
            if hasta > desde:
                assert tablero._deltas_pieza(vn, desde, hasta) == tablero._deltas_pieza(vv, desde, hasta), (desde, hasta)
        de = ex.snapshots_de([d["nuevo"], d["viejo"]], desde)
        assert _sin_hora(de[d["nuevo"]][0]) == _sin_hora(de[d["viejo"]][0])


def test_tablero_mes_a_mes_y_serie_de_30_dias_dan_lo_mismo(dos_proyectos):
    import tablero
    for f in (tablero.resumen_total, tablero.resumen_mes, tablero.mes_a_mes, tablero.serie_diaria):
        assert f("nuevo", ahora_iso=AHORA) == f("viejo", ahora_iso=AHORA), f.__name__
    n = tablero._cierres_de_mes([dos_proyectos["nuevo"]], AHORA)
    v = tablero._cierres_de_mes([dos_proyectos["viejo"]], AHORA)
    assert n[1] == v[1]
    for mes in ("2026-09-01T00:00:00", "2026-10-01T00:00:00", AHORA):
        assert _sin_hora(n[0][dos_proyectos["nuevo"]].en(mes)) == _sin_hora(v[0][dos_proyectos["viejo"]].en(mes))


def test_el_decisor_ve_la_misma_evidencia(dos_proyectos):
    import decisor
    import experimentos as ex
    from tareas import experimentos as tareas_exp
    d = dos_proyectos
    for cuando in ("2026-08-29T08:00:00", "2026-08-31T12:00:00", "2026-09-04T00:00:00", "2026-09-12T12:00:00", AHORA):
        ahora = datetime.fromisoformat(cuando)
        pn = [s for s in ex.snapshots(d["nuevo"]) if s["tomado_en"] <= cuando]
        pv = [s for s in ex.snapshots(d["viejo"]) if s["tomado_en"] <= cuando]
        hn, hv = tareas_exp._horas_activo({}, pn, ahora), tareas_exp._horas_activo({}, pv, ahora)
        assert hn == hv, cuando
        dias = tareas_exp._dias_transcurridos({}, {1: pn}, ahora), tareas_exp._dias_transcurridos({}, {1: pv}, ahora)
        assert dias[0] == dias[1]
        for reglas in ({}, {"ventana_horas": 24, "impresiones_min": 10 ** 9}, {"roas_min": 50.0}):
            ctx = {"horas_activo": hn, "presupuesto_dia": 20000.0, "dias_experimento": 30, "dias_transcurridos": dias[0],
                   "atribucion": "pixel", "compras_pais": None}
            ctx["compras_pais"] = int((pn[-1] if pn else {}).get("compras") or 0)
            assert decisor.decidir(pn, reglas, ctx) == decisor.decidir(pv, reglas, ctx), (cuando, reglas)


# ---------- la frescura cuenta la confirmación ----------

def test_sin_cambios_no_son_datos_viejos_ni_alerta_de_6_horas(base_temporal):
    import experimentos as ex
    import tablero
    eid = _crear("acme")
    ep = _pieza_en(base_temporal, "acme", eid, "cf_1__es_CO")
    m = {"impresiones": 500, "gasto": 9000.0, "estado_meta_texto": "Activo"}
    ex.snapshot(ep, m, tomado_en="2026-10-10T00:00:00")
    ex.snapshot(ep, dict(m), tomado_en="2026-10-10T10:00:00")     # 10 h después, igual: solo confirma
    exp = ex.obtener("acme", eid)
    assert ex.datos_viejos(exp, "2026-10-10T12:00:00") is False
    assert tablero._ultimo_snapshot_experimento(exp) == "2026-10-10T10:00:00"
    sin_metricas = lambda ahora: [a for a in tablero.alertas("acme", ahora_iso=ahora)  # noqa: E731
                                  if a["tipo"] == "sin_metricas" and a["experimento_id"] == eid]
    assert sin_metricas("2026-10-10T12:00:00") == []
    # Sin consultas nuevas en más de 6 h, sí.
    assert ex.datos_viejos(ex.obtener("acme", eid), "2026-10-10T17:00:00") is True
    assert len(sin_metricas("2026-10-10T17:00:00")) == 1

"""tablero.filtrar (spec 2026-10-02 §4.2): el centro de resultados reusa el motor
del Tablero sobre un subconjunto; y la carga de snapshots no crece con las piezas."""
from sqlalchemy import event

from tests.test_experimentos_db import PAISES, _pieza


def _sembrar(db):
    import experimentos as ex
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    img = _pieza(db, tipo="imagen", estado="listo", pais=None, idioma=None, legado="cf_img")
    e1 = ex.crear("acme", "Uno", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t.co/p", "COP")
    e2 = ex.crear("acme", "Dos", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t.co/p", "COP")
    a = ex.agregar_pieza("acme", e1, clon, "CO")
    b = ex.agregar_pieza("acme", e1, img, "MX")
    c = ex.agregar_pieza("acme", e2, clon, "CO")
    for ep, gasto in ((a, 10.0), (b, 20.0), (c, 40.0)):
        ex.snapshot(ep, {"impresiones": 100, "gasto": gasto, "clics_enlace": 5}, tomado_en="2026-10-01T10:00:00")
    return {"e1": e1, "e2": e2, "a": a, "b": b, "c": c}


def test_filtrar_por_experimento_pais_pieza_y_tipo(base_temporal):
    import tablero
    s = _sembrar(base_temporal)
    d = tablero.cargar_datos("acme", "2026-10-02T12:00:00", desde="2026-09-01T00:00:00")
    assert tablero.filtrar(d) is d
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, experimento_id=s["e1"]).filas} == {s["a"], s["b"]}
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, pais="CO").filas} == {s["a"], s["c"]}
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, ep_id=s["b"]).filas} == {s["b"]}
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, tipo="imagen").filas} == {s["b"]}
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, tipo="video").filas} == {s["a"], s["c"]}
    f = tablero.filtrar(d, experimento_id=s["e2"])
    assert [e["id"] for e in f.exps] == [s["e2"]] and f.cliente == "acme" and f.desde == d.desde
    r = tablero.resumen_periodo("acme", "2026-09-01T00:00:00", "2026-10-02T12:00:00", datos=f)
    assert r["por_moneda"]["COP"]["gasto"] == 40.0


def test_snapshots_de_las_piezas_no_se_piden_una_por_una(base_temporal):
    """`_piezas_con_snapshots` hace las mismas consultas con 3 piezas que con 13
    (la carga de experimentos.cargar es aparte: una última métrica por pieza).
    PND-139 requiere una tercera consulta conjunta para detectar ventas previas a la ventana."""
    import db
    import experimentos as ex
    import tablero
    _sembrar(base_temporal)
    cuenta = []

    def contar(*_a, **_k):
        cuenta.append(1)

    def consultas():
        exps = ex.cargar("acme")
        cuenta.clear()
        event.listen(db.engine(), "before_cursor_execute", contar)
        try:
            filas = tablero._piezas_con_snapshots(exps, "2026-09-01T00:00:00")
        finally:
            event.remove(db.engine(), "before_cursor_execute", contar)
        return len(cuenta), filas

    con_tres, filas = consultas()
    assert len(filas) == 3 and con_tres <= 3
    e = ex.cargar("acme")[0]["id"]
    for i in range(10):
        ep = ex.agregar_pieza("acme", e, _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado=f"cf_x{i}"), "CO")
        ex.snapshot(ep, {"impresiones": 1, "gasto": 1.0}, tomado_en="2026-10-01T10:00:00")
    con_trece, filas = consultas()
    assert len(filas) == 13 and con_trece == con_tres
    assert all(len(serie.snaps) == 1 for _e, _pz, serie in filas)


def test_gastos_total_entre(base_temporal):
    import gastos
    gastos.registrar_seguro("acme", "video", 1.5, "video:1:t1")
    gastos.registrar_seguro("acme", "imagen", 0.5, "imagen:1:t2")
    gastos.registrar_seguro("otro", "video", 9.0, "video:9:t9")
    r = gastos.total_entre("acme", "2000-01-01T00:00:00", "2999-01-01T00:00:00")
    assert r == {"usd": 2.0, "n": 2}
    assert gastos.total_entre("acme", "2999-01-01T00:00:00", "2999-02-01T00:00:00") == {"usd": 0.0, "n": 0}

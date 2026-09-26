"""Panel de administrador (admin.py): agrega, para TODOS los proyectos, el
gasto de generación (tabla gasto), la pauta en Meta (snapshots, incluidos los
anuncios sueltos legado, por moneda), piezas del mes, aprobaciones,
experimentos corriendo, conexiones y la salud del worker. Solo lectura y sin
red: el estado de Meta es lo último guardado, no una llamada."""
import pytest
import sqlalchemy as sa

AHORA = "2026-09-19T10:00:00"


@pytest.fixture()
def admin(base_temporal, monkeypatch):
    import admin as mod
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"token": "x"} if c == "acme" else None)
    return mod


def _exp(db, cliente, moneda="COP", legado=False, estado="corriendo"):
    with db.conectar() as con:
        eid = con.execute(sa.insert(db.experimento).values(
            cliente=cliente, creado_en=AHORA, actualizado_en=AHORA, nombre="e", moneda=moneda,
            legado=legado, estado=estado, paises=[], reglas={}, extra={})).inserted_primary_key[0]
        ep = con.execute(sa.insert(db.experimento_pieza).values(
            cliente=cliente, creado_en=AHORA, actualizado_en=AHORA, experimento_id=eid, extra={})).inserted_primary_key[0]
    return eid, ep


def _snap(db, ep, tomado_en, gasto):
    with db.conectar() as con:
        con.execute(sa.insert(db.metrica_snapshot).values(experimento_pieza_id=ep, tomado_en=tomado_en, gasto=gasto, extra={}))


def _pieza(db, cliente, estado="listo", creado_en="2026-09-05T10:00:00"):
    with db.conectar() as con:
        cid = con.execute(sa.insert(db.concepto).values(
            cliente=cliente, creado_en=creado_en, actualizado_en=creado_en, origen="manual", extra={})).inserted_primary_key[0]
        con.execute(sa.insert(db.pieza).values(
            cliente=cliente, creado_en=creado_en, actualizado_en=creado_en, concepto_id=cid,
            tipo="video", estado=estado, capas={}, extra={}))


def test_generacion_del_mes_por_proyecto_y_por_tipo(admin, base_temporal):
    import gastos
    gastos.registrar("acme", "video", 1.3, "video:1", creado_en="2026-09-03T11:00:00")
    gastos.registrar("acme", "swap", 0.5, "swap:1", creado_en="2026-09-10T11:00:00")
    gastos.registrar("acme", "video", 5.0, "video:ago", creado_en="2026-08-20T11:00:00")   # mes anterior
    gastos.registrar("beta", "final", 0.2, "final:1", creado_en="2026-09-15T11:00:00")

    r = admin.resumen(["acme", "beta"], ahora_iso=AHORA)

    acme, beta = r["proyectos"]
    assert acme["id"] == "acme" and acme["generacion_usd"] == 1.8 and acme["cobros"] == 2
    assert acme["por_tipo"] == {"video": 1.3, "swap": 0.5}
    assert beta["generacion_usd"] == 0.2 and beta["por_tipo"] == {"final": 0.2}
    assert r["totales"]["generacion_usd"] == 2.0 and r["totales"]["cobros"] == 3
    assert r["totales"]["por_tipo"] == {"video": 1.3, "swap": 0.5, "final": 0.2}


def test_pauta_del_mes_incluye_anuncios_sueltos_por_moneda(admin, base_temporal):
    _, ep_legado = _exp(base_temporal, "acme", moneda="COP", legado=True)
    _snap(base_temporal, ep_legado, "2026-08-30T00:00:00", 1000)      # acumulado antes del mes: es la base
    _snap(base_temporal, ep_legado, "2026-09-14T02:08:14", 7226)
    _, ep_usd = _exp(base_temporal, "acme", moneda="USD")
    _snap(base_temporal, ep_usd, "2026-09-10T00:00:00", 12.5)
    _, ep_beta = _exp(base_temporal, "beta", moneda="COP")
    _snap(base_temporal, ep_beta, "2026-09-02T00:00:00", 300)

    r = admin.resumen(["acme", "beta"], ahora_iso=AHORA)

    acme, beta = r["proyectos"]
    assert acme["pauta"] == {"COP": 6226.0, "USD": 12.5}
    assert beta["pauta"] == {"COP": 300.0}
    assert r["totales"]["pauta"] == {"COP": 6526.0, "USD": 12.5}


def test_piezas_experimentos_conexiones_y_actividad(admin, base_temporal):
    import cola
    _pieza(base_temporal, "acme", "listo", "2026-09-05T10:00:00")
    _pieza(base_temporal, "acme", "degradada", "2026-09-06T10:00:00")
    _pieza(base_temporal, "acme", "generando", "2026-09-07T10:00:00")   # aún no es una pieza generada
    _pieza(base_temporal, "acme", "listo", "2026-08-07T10:00:00")       # mes anterior
    _exp(base_temporal, "acme", legado=False, estado="corriendo")
    _exp(base_temporal, "acme", legado=True, estado="corriendo")        # anuncios sueltos: no es un experimento
    _exp(base_temporal, "acme", legado=False, estado="cerrado")
    with base_temporal.conectar() as con:
        con.execute(sa.insert(base_temporal.tienda).values(
            cliente="acme", creado_en=AHORA, actualizado_en=AHORA, tipo="shopify", estado="conectada"))
    cola.encolar("flowplus_video", {}, cliente="acme", job_id="acme__x__video")

    r = admin.resumen(["acme", "beta"], ahora_iso=AHORA)

    acme, beta = r["proyectos"]
    assert acme["piezas_mes"] == 2 and beta["piezas_mes"] == 0
    assert acme["experimentos_corriendo"] == 1 and beta["experimentos_corriendo"] == 0
    assert acme["meta"] == "conectado" and beta["meta"] == "sin_conectar"
    assert acme["tiendas"] == 1 and beta["tiendas"] == 0
    assert acme["ultima_actividad"] is not None and beta["ultima_actividad"] is None
    assert r["totales"]["piezas_mes"] == 2 and r["totales"]["experimentos_corriendo"] == 1


def test_aprobaciones_pendientes_desde_estado_videos(admin, monkeypatch):
    import estado
    monkeypatch.setattr(estado, "cargar", lambda c: {
        "b1": {"estado": "pendiente"}, "b2": {"estado": "publicado"}, "b3": {"estado": "publicado"}, "b4": {}}
        if c == "acme" else {})

    r = admin.resumen(["acme", "beta"], ahora_iso=AHORA)

    acme = r["proyectos"][0]
    assert (acme["pendiente"], acme["publicado"], acme["rechazado"]) == (2, 2, 0)   # sin estado cuenta como pendiente
    assert r["totales"]["pendiente"] == 2 and r["totales"]["publicado"] == 2


def test_salud_del_worker_sin_tokens(admin, base_temporal):
    import cola
    cola.encolar("exp_refrescar", {}, cliente="acme", job_id="a1", max_intentos=1)
    cola.encolar("flowplus_video", {}, cliente="beta", job_id="b1", max_intentos=1)
    cola.encolar("sprint_qa_pendientes", {}, job_id="c1")
    primera = cola.reclamar()
    cola.fallar(primera["id"], "Meta dijo 190: access_token=EAAB123 caducó")
    segunda = cola.reclamar()
    cola.terminar(segunda["id"], "Listo.")

    w = admin.salud_worker(ahora_iso=AHORA)

    assert w["pendientes"] == 1 and w["en_curso"] == 0 and w["error"] == 1
    assert w["ultima_hecha"] is not None
    assert len(w["ultimos_errores"]) == 1
    e = w["ultimos_errores"][0]
    assert e["tipo"] == "exp_refrescar" and e["cliente"] == "acme"
    assert "EAAB123" not in e["error"] and "access_token" in e["error"]


def test_historial_de_meses_y_ultimos_cobros(admin, base_temporal):
    import gastos
    gastos.registrar("acme", "video", 1.0, "v1", creado_en="2026-09-03T11:00:00")
    gastos.registrar("acme", "video", 2.0, "v2", creado_en="2026-08-03T11:00:00")
    gastos.registrar("beta", "swap", 0.5, "s1", creado_en="2026-08-04T11:00:00")
    gastos.registrar("beta", "final", 0.25, "f1", creado_en="2026-03-04T11:00:00")   # fuera de los 6 meses

    meses = admin.gasto_meses(["acme", "beta"], meses=6, ahora_iso=AHORA)

    assert [m["mes"] for m in meses] == ["2026-09", "2026-08", "2026-07", "2026-06", "2026-05", "2026-04"]
    assert meses[0]["por_proyecto"] == {"acme": 1.0, "beta": 0.0} and meses[0]["total"] == 1.0
    assert meses[1]["por_proyecto"] == {"acme": 2.0, "beta": 0.5} and meses[1]["total"] == 2.5

    ultimos = admin.ultimos_cobros(limite=2)
    assert [(c["cliente"], c["usd"]) for c in ultimos] == [("acme", 1.0), ("beta", 0.5)]


def test_csv_del_mes_de_todos_los_proyectos(admin, base_temporal):
    import gastos
    gastos.registrar("acme", "video", 1.3, "video:1", detalle="=1+1", proveedor="wavespeed",
                     creado_en="2026-09-03T11:00:00")
    gastos.registrar("beta", "swap", 0.5, "swap:1", creado_en="2026-08-10T11:00:00")   # otro mes

    csv_ = admin.csv_mes(["acme", "beta"], ahora_iso=AHORA)

    assert csv_.startswith("﻿")
    lineas = csv_.lstrip("﻿").splitlines()
    assert lineas[0] == "proyecto;fecha;tipo;proveedor;referencia;detalle;usd"
    assert len(lineas) == 2
    assert lineas[1].startswith("acme;2026-09-03T11:00:00;video;wavespeed;video:1;")
    assert "'=1+1" in lineas[1] and lineas[1].endswith("1,3000")


def test_gasto_de_creatv_aparece_aparte_nunca_mezclado_con_proyectos(admin, base_temporal):
    import gastos
    from referentes.datos import CLIENTE_CREATV
    gastos.registrar("acme", "video", 1.0, "v1", creado_en="2026-09-03T11:00:00")
    gastos.registrar(CLIENTE_CREATV, "otro", 2.5, "copycoders:1", creado_en="2026-09-05T11:00:00")
    gastos.registrar(CLIENTE_CREATV, "otro", 0.3, "copycoders:2", creado_en="2026-08-05T11:00:00")   # mes anterior

    r = admin.resumen(["acme"], ahora_iso=AHORA)

    assert r["totales"]["generacion_usd"] == 1.0   # _creatv nunca se mezcla con el gasto de proyectos
    assert r["totales"]["creatv_usd"] == 2.5 and r["totales"]["creatv_cobros"] == 1
    assert r["totales"]["creatv_por_tipo"] == {"otro": 2.5}
    assert r["meses"][0]["mes"] == "2026-09" and r["meses"][0]["creatv"] == 2.5 and r["meses"][0]["total"] == 1.0
    assert r["meses"][1]["mes"] == "2026-08" and r["meses"][1]["creatv"] == 0.3 and r["meses"][1]["total"] == 0.0

    csv_ = admin.csv_mes(["acme"], ahora_iso=AHORA)
    lineas = csv_.lstrip("﻿").splitlines()
    assert any(l.startswith(f"{CLIENTE_CREATV};2026-09-05T11:00:00;otro;") for l in lineas)


def test_hace_en_espanol(admin):
    assert admin.hace("2026-09-19T09:58:30", AHORA) == "hace 1 min"
    assert admin.hace("2026-09-19T07:00:00", AHORA) == "hace 3 h"
    assert admin.hace("2026-09-16T10:00:00", AHORA) == "hace 3 días"
    assert admin.hace(None, AHORA) is None


def test_pauta_toma_la_moneda_de_la_pieza_o_de_meta_json_cuando_el_experimento_no_la_tiene(admin, base_temporal, monkeypatch):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"token": "x", "moneda": "MXN"} if c == "beta" else None)
    # Anuncios sueltos legado: el experimento no guarda moneda, la pieza sí (extra.moneda).
    _, ep_legado = _exp(base_temporal, "acme", moneda=None, legado=True)
    with base_temporal.conectar() as con:
        con.execute(sa.update(base_temporal.experimento_pieza).where(base_temporal.experimento_pieza.c.id == ep_legado)
                    .values(extra={"nombre": "Lanzamiento", "moneda": "COP"}))
    _snap(base_temporal, ep_legado, "2026-09-14T02:08:14", 37246)
    # Sin moneda en ninguna parte: la de la cuenta publicitaria conectada (meta.json).
    _, ep_beta = _exp(base_temporal, "beta", moneda=None)
    _snap(base_temporal, ep_beta, "2026-09-10T00:00:00", 80)

    r = admin.resumen(["acme", "beta"], ahora_iso=AHORA)

    acme, beta = r["proyectos"]
    assert acme["pauta"] == {"COP": 37246.0}
    assert beta["pauta"] == {"MXN": 80.0}

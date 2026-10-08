"""El cobro se escribe en la misma puerta que el costo (spec §3)."""
import sqlalchemy as sa


def _movs(db):
    with db.conectar() as con:
        return con.execute(sa.select(db.movimiento_saldo).order_by(db.movimiento_saldo.c.id)).all()


def test_registrar_cobra_si_el_proyecto_cobra(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gid = gastos.registrar("acme", "video", 1.0, "video:1:t1")
    (m,) = _movs(base_temporal)
    assert (m.tipo, m.milesimas, m.gasto_id) == ("cobro", -1500, gid)


def test_registrar_no_toca_un_proyecto_que_no_cobra(base_temporal):
    import gastos
    gastos.registrar("acme", "video", 1.0, "video:1:t1")
    assert _movs(base_temporal) == []


def test_corregir_el_monto_recalcula_el_cobro(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "final", 0.2, "final:1:t1")
    gastos.registrar("acme", "final", 0.4, "final:1:t1")
    assert [m.milesimas for m in _movs(base_temporal)] == [-600]


def test_entregado_false_no_cobra_y_avisa(base_temporal, monkeypatch):
    import gastos
    from cobros import avisos, libro
    vistos = []
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda c, m, k: vistos.append((c, m, k)))
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar_seguro("acme", "video", 1.0, "video:1:t1", entregado=False)
    (m,) = _movs(base_temporal)
    assert (m.tipo, m.milesimas) == ("no_cobrado", 0)
    assert vistos == [("acme", 1500, "video")]


def test_si_el_cobro_falla_el_gasto_queda(base_temporal, monkeypatch):
    import gastos
    from cobros import avisos, libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    monkeypatch.setattr(libro, "cobrar_gasto", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    admin = []
    monkeypatch.setattr(avisos, "admin", lambda *a, **k: admin.append(a))
    gid = gastos.registrar("acme", "video", 1.0, "video:1:t1")
    with base_temporal.conectar() as con:
        assert con.execute(sa.select(base_temporal.gasto.c.usd).where(base_temporal.gasto.c.id == gid)).scalar() == 1.0
    assert admin


# ---- más allá del brief: las dos ramas (insertar / actualizar) y los avisos ----

def test_prender_cobrar_no_cobra_la_correccion_de_un_gasto_viejo(base_temporal):
    """§3.2: un gasto anotado con «Cobrar» apagado no se cobra al corregirlo después."""
    import gastos
    from cobros import libro
    gastos.registrar("acme", "video", 1.0, "video:1:t1")
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "video", 2.0, "video:1:t1")
    assert _movs(base_temporal) == []


def test_si_el_cobro_falla_al_corregir_el_gasto_corregido_queda(base_temporal, monkeypatch):
    import gastos
    from cobros import avisos, libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gid = gastos.registrar("acme", "video", 1.0, "video:1:t1")
    monkeypatch.setattr(libro, "cobrar_gasto", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    admin = []
    monkeypatch.setattr(avisos, "admin", lambda *a, **k: admin.append(a))
    gastos.registrar("acme", "video", 3.0, "video:1:t1")
    with base_temporal.conectar() as con:
        assert con.execute(sa.select(base_temporal.gasto.c.usd).where(base_temporal.gasto.c.id == gid)).scalar() == 3.0
    assert [m.milesimas for m in _movs(base_temporal)] == [-1500]   # el cobro previo no se tocó
    assert admin


def test_el_cobro_queda_guardado_en_ambas_ramas(base_temporal):
    """El cobro sobrevive a la conexión (savepoint confirmado), al insertar y al corregir."""
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "video", 1.0, "video:1:t1")
    assert libro.saldo("acme") == -1500
    gastos.registrar("acme", "video", 2.0, "video:1:t1")
    assert libro.saldo("acme") == -3000


def test_conservar_mayor_cobra_sobre_el_monto_guardado(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "video", 1.0, "video:1:t1", conservar_mayor=True)
    gastos.registrar("acme", "video", 0.2, "video:1:t1", conservar_mayor=True)
    assert [m.milesimas for m in _movs(base_temporal)] == [-1500]


def test_no_entregado_despues_de_cobrado_revierte_con_el_margen_del_cobro(base_temporal, monkeypatch):
    import gastos
    from cobros import avisos, libro
    vistos = []
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda c, m, k: vistos.append((c, m, k)))
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "video", 1.0, "video:1:t1")
    libro.configurar("acme", usuario="admin", margen=3.0)
    gastos.registrar("acme", "video", 1.0, "video:1:t1", entregado=False)
    assert [(m.tipo, m.milesimas) for m in _movs(base_temporal)] == [("cobro", -1500), ("reverso", 1500)]
    assert vistos == [("acme", 1500, "video")]
    assert libro.saldo("acme") == 0


def test_cobro_bajo_el_umbral_avisa_saldo_bajo(base_temporal, monkeypatch):
    import gastos
    from cobros import avisos, libro
    bajos = []
    monkeypatch.setattr(avisos, "saldo_bajo", lambda c, s: bajos.append((c, s)))
    libro.configurar("acme", usuario="admin", cobrar=True, umbral=5000)
    with base_temporal.conectar() as con:
        libro.acreditar(con, "acme", "recarga", 6000, "recarga_manual")
    gastos.registrar("acme", "video", 0.1, "video:1:t1")   # 6000 - 150 = 5850: no avisa
    assert bajos == []
    gastos.registrar("acme", "video", 1.0, "video:2:t2")   # 5850 - 1500 = 4350: avisa
    assert bajos == [("acme", 4350)]


def test_un_aviso_que_revienta_no_tumba_el_registro(base_temporal, monkeypatch):
    import gastos
    from cobros import avisos, libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    monkeypatch.setattr(avisos, "saldo_bajo", lambda *a: (_ for _ in ()).throw(RuntimeError("smtp")))
    gid = gastos.registrar("acme", "video", 1.0, "video:1:t1")
    assert gid and libro.saldo("acme") == -1500


# ---- llamadores que anotan «pagado pero no entregado» (Step 4) ----

def _tipos(db):
    return [(m.tipo, m.milesimas) for m in _movs(db)]


def test_final_que_fallo_no_se_cobra_y_la_buena_si(base_temporal, monkeypatch):
    import final_edition
    from cobros import avisos, libro
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda *a: None)
    libro.configurar("acme", usuario="admin", cobrar=True)
    capas = {"voz": {"costo_usd": 0.1, "estado": "ok"}, "render": {"costo_usd": 0.0, "estado": "error"}}
    final_edition._registrar_gasto_final("acme", 7, "es", "CO", 0.1, capas, fallo=True, ref_sufijo=":t1")
    assert _tipos(base_temporal) == [("no_cobrado", 0)]
    final_edition._registrar_gasto_final("acme", 8, "es", "CO", 0.1, capas, fallo=False, ref_sufijo=":t2")
    assert _tipos(base_temporal)[-1] == ("cobro", -150)


def test_guion_de_clips_con_respuesta_invalida_no_se_cobra(base_temporal, monkeypatch):
    from cobros import avisos, libro
    from guiones import claude
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda *a: None)
    libro.configurar("acme", usuario="admin", cobrar=True)
    claude.pedir_json("acme", "armar", 3, "sis", [], "Armar", llamar_fn=lambda *a: ("no es json", 1000, 800))
    assert [t for t, _ in _tipos(base_temporal)] == ["no_cobrado"]
    claude.pedir_json("acme", "leer", 4, "sis", [], "Leer", llamar_fn=lambda *a: ('{"a": 1}', 1000, 800))
    assert [t for t, _ in _tipos(base_temporal)] == ["no_cobrado", "cobro"]


def test_swap_que_fallo_despues_de_generar_no_se_cobra(base_temporal, monkeypatch):
    from cobros import avisos, libro
    from tareas import swap
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda *a: None)
    libro.configurar("acme", usuario="admin", cobrar=True)
    swap._registrar_gasto("acme", "swap:1:t1", "wavespeed", "foto", {"usd": 0.2}, False, entregado=False)
    assert _tipos(base_temporal) == [("no_cobrado", 0)]


def test_video_que_fallo_al_descargar_no_se_cobra(base_temporal, monkeypatch):
    from cobros import avisos, libro
    from tareas import flowplus
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda *a: None)
    libro.configurar("acme", usuario="admin", cobrar=True)
    flowplus._registrar_gasto("acme", "video", {"usd": 1.0}, "video:cf_1:t1", "wan3", "falló", entregado=False)
    assert _tipos(base_temporal) == [("no_cobrado", 0)]

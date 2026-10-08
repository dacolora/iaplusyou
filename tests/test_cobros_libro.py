"""Libro de saldo (spec 2026-10-08 §1-§5)."""
import pytest
import sqlalchemy as sa

AHORA = "2026-10-08T10:00:00"


@pytest.fixture()
def libro(base_temporal):
    from cobros import libro
    return libro


def _tarea(db, job_id, estado="en_curso", cliente="acme", tipo="flowplus_video", creada_en=AHORA, terminada_en=None):
    with db.conectar() as con:
        return con.execute(sa.insert(db.tarea).values(
            cliente=cliente, job_id=job_id, tipo=tipo, payload={}, estado=estado, intentos=0, max_intentos=1,
            prioridad=5, ejecutar_desde=AHORA, creada_en=creada_en, terminada_en=terminada_en, duracion_estimada=60.0, etapas=[])).inserted_primary_key[0]


def _recargar(db, libro, cliente, milesimas):
    with db.conectar() as con:
        libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def test_precio_redondea_hacia_arriba_sin_ruido_de_float(libro):
    assert libro.precio_milesimas(0.01, 1.5) == 15
    assert libro.precio_milesimas(1.0, 1.5) == 1500
    assert libro.precio_milesimas(0.0101, 1.5) == 16
    assert libro.precio_milesimas(0, 1.5) == 0


def test_proyecto_sin_cuenta_no_cobra(libro, base_temporal):
    assert libro.cuenta("acme")["cobrar"] is False
    assert libro.exigir("acme", 99.0, job_id="j") == 0
    with base_temporal.conectar() as con:
        assert libro.cobrar_gasto(con, 1, "acme", 1.0, "video") is None
    assert libro.saldo("acme") == 0


def test_margen_global_y_propio(libro):
    assert libro.margen_global() == 1.5
    libro.guardar_margen_global(1.4, "admin")
    assert libro.cuenta("acme")["margen"] == 1.4
    libro.configurar("acme", usuario="admin", cobrar=True, margen=2.0)
    assert libro.cuenta("acme")["margen"] == 2.0
    libro.configurar("acme", usuario="admin", margen=None)
    assert libro.cuenta("acme")["margen"] == 1.4
    with pytest.raises(ValueError):
        libro.guardar_margen_global(0.5, "admin")


def test_exigir_sin_saldo_lanza_y_no_reserva(libro, base_temporal):
    libro.configurar("acme", usuario="admin", cobrar=True)
    with pytest.raises(libro.SaldoInsuficiente) as e:
        libro.exigir("acme", 1.0, job_id="j1")
    assert e.value.precio == 1500 and e.value.disponible == 0
    with base_temporal.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(base_temporal.reserva_saldo)).scalar() == 0


def test_reserva_viva_descuenta_y_muerta_no(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    _recargar(db, libro, "acme", 2000)
    assert libro.exigir("acme", 1.0, job_id="j1") == 1500
    _tarea(db, "j1", "pendiente")
    assert libro.disponible("acme") == 500
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", 1.0, job_id="j2")
    with db.conectar() as con:
        con.execute(sa.update(db.tarea).where(db.tarea.c.job_id == "j1").values(estado="hecha"))
    assert libro.disponible("acme") == 2000


def test_segundo_clic_del_mismo_job_no_reserva_dos_veces(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    _recargar(db, libro, "acme", 2000)
    libro.exigir("acme", 1.0, job_id="j1")
    _tarea(db, "j1", "pendiente")
    libro.exigir("acme", 1.0, job_id="j1")
    assert libro.reservado("acme") == 1500


def test_sin_precio_basta_saldo_positivo(libro, base_temporal):
    libro.configurar("acme", usuario="admin", cobrar=True)
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", None)
    _recargar(base_temporal, libro, "acme", 1)
    assert libro.exigir("acme", None) == 1


def test_cobro_con_margen_y_contexto(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    with libro.en_trabajo(41, "video:9"), db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 1.0, "video") == "cobro"
    with db.conectar() as con:
        m = con.execute(sa.select(db.movimiento_saldo)).one()
    assert (m.tipo, m.milesimas, m.gasto_id, m.job_id, m.tarea_id, m.concepto) == ("cobro", -1500, 5, "video:9", 41, "video")
    assert m.extra["margen"] == 1.5
    assert libro.saldo("acme") == -1500


def test_gasto_corregido_recalcula_con_el_margen_original(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    with db.conectar() as con:
        libro.cobrar_gasto(con, 5, "acme", 0.20, "final")
    libro.guardar_margen_global(3.0, "admin")
    with db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 0.40, "final", nuevo=False) == "recalculado"
    assert libro.saldo("acme") == -600


def test_gasto_visto_sin_cobrar_y_corregido_despues_no_escribe(libro, base_temporal):
    db = base_temporal
    with db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 0.20, "final") is None      # Cobrar apagado
    libro.configurar("acme", usuario="admin", cobrar=True)
    with db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 0.40, "final", nuevo=False) is None
        assert con.execute(sa.select(sa.func.count()).select_from(db.movimiento_saldo)).scalar() == 0


def test_no_entregado_escribe_cero(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    with db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 1.0, "video", entregado=False) == "no_cobrado"
    with db.conectar() as con:
        m = con.execute(sa.select(db.movimiento_saldo)).one()
    assert (m.tipo, m.milesimas, m.extra["precio"]) == ("no_cobrado", 0, 1500)


def test_revertir_por_job_una_sola_vez(libro, base_temporal, monkeypatch):
    db = base_temporal
    avisos = []
    import cobros.avisos as av
    monkeypatch.setattr(av, "pieza_no_cobrada", lambda cliente, milesimas, concepto: avisos.append(milesimas))
    libro.configurar("acme", usuario="admin", cobrar=True)
    with libro.en_trabajo(1, "video:9"), db.conectar() as con:
        libro.cobrar_gasto(con, 5, "acme", 1.0, "video")
    with libro.en_trabajo(2, "video:9"), db.conectar() as con:
        libro.cobrar_gasto(con, 6, "acme", 0.5, "video")
    assert len(libro.revertir_trabajo("acme", "video:9", "falló")) == 2
    assert libro.revertir_trabajo("acme", "video:9", "falló") == []
    assert libro.saldo("acme") == 0
    assert avisos == [2250]


def test_cobrar_apagado_no_cobra_hacia_atras(libro, base_temporal):
    db = base_temporal
    with db.conectar() as con:
        libro.cobrar_gasto(con, 5, "acme", 1.0, "video")
    libro.configurar("acme", usuario="admin", cobrar=True)
    with db.conectar() as con:
        # gastos.registrar pasa nuevo=False cuando el gasto ya existía (corrección de monto)
        assert libro.cobrar_gasto(con, 5, "acme", 2.0, "video", nuevo=False) is None
    assert libro.saldo("acme") == 0


def test_puede_arrancar(libro, base_temporal):
    db = base_temporal
    tipos = {"flowplus_video"}
    t = {"id": 99, "tipo": "flowplus_video", "cliente": "acme", "job_id": "j"}
    assert libro.puede_arrancar(t, tipos) is True              # no cobra
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert libro.puede_arrancar(t, tipos) is False             # saldo 0
    assert libro.puede_arrancar({**t, "tipo": "exp_decidir"}, tipos) is True
    # el mismo job_id reusado de un día anterior NO es una cadena
    _tarea(db, "j", "hecha", creada_en="2026-10-01T09:00:00", terminada_en="2026-10-01T09:05:00")
    assert libro.puede_arrancar(t, tipos) is False


def test_puede_arrancar_continuacion_de_cadena(libro, base_temporal):
    db = base_temporal
    tipos = {"flowplus_video"}
    libro.configurar("acme", usuario="admin", cobrar=True)
    _tarea(db, "j", "hecha", creada_en="2026-10-08T09:00:00", terminada_en=AHORA)
    siguiente = _tarea(db, "j", "pendiente", creada_en=AHORA)   # se crea al cerrar la anterior
    t = {"id": siguiente, "tipo": "flowplus_video", "cliente": "acme", "job_id": "j"}   # sin creada_en: sale de la base
    assert libro.puede_arrancar(t, tipos) is True
    # una hecha vieja detrás de la reciente no cambia nada; y una tarea sin continuación previa, sí frena
    otra = _tarea(db, "k", "pendiente", creada_en=AHORA)
    assert libro.puede_arrancar({**t, "id": otra, "job_id": "k"}, tipos) is False


def test_acreditar_rechaza_signos_y_ceros_imposibles(libro, base_temporal):
    with base_temporal.conectar() as con:
        for tipo, monto in (("recarga", 0), ("recarga", -5), ("anulacion", 5), ("anulacion", 0), ("ajuste", 0)):
            with pytest.raises(ValueError):
                libro.acreditar(con, "acme", tipo, monto, "ajuste")
        libro.acreditar(con, "acme", "anulacion", -5, "anulacion_bold")
        libro.acreditar(con, "acme", "ajuste", -3, "ajuste")
    assert libro.saldo("acme") == -8


def test_cobra_devuelve_bool(libro):
    assert libro.cobra("acme") is False and libro.cobra("") is False and libro.cobra(None) is False
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert libro.cobra("acme") is True


def test_revertir_con_fallo_a_medias_no_devuelve_ids_fantasma(libro, base_temporal, monkeypatch):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    with libro.en_trabajo(1, "v:1"), db.conectar() as con:
        libro.cobrar_gasto(con, 5, "acme", 1.0, "video")
        libro.cobrar_gasto(con, 6, "acme", 1.0, "video")
    llamadas = []
    original = libro._insertar

    def rota(con, **v):
        llamadas.append(1)
        if len(llamadas) == 2:
            raise RuntimeError("disco lleno")
        return original(con, **v)
    monkeypatch.setattr(libro, "_insertar", rota)
    assert libro.revertir_trabajo("acme", "v:1", "x") == []
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.movimiento_saldo)
                           .where(db.movimiento_saldo.c.tipo == "reverso")).scalar() == 0


def test_limpiar_reservas_muertas(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    _recargar(db, libro, "acme", 5000)
    libro.exigir("acme", 1.0, job_id="viva")
    libro.exigir("acme", 1.0, job_id="muerta")
    _tarea(db, "viva", "en_curso")
    assert libro.limpiar_reservas_muertas() == 1


def test_avisos_arman_el_texto_y_saldo_bajo_avisa_una_vez(base_temporal, monkeypatch):
    from cobros import avisos
    enviados = []
    monkeypatch.setattr(avisos.notificaciones, "avisar", lambda c, t, a, b: enviados.append((c, t, a, b)) or True)
    monkeypatch.setattr(avisos.idiomas, "de_proyecto", lambda c: "es")
    avisos.pieza_no_cobrada("acme", 2250, "video")
    assert enviados[0][1] == "pieza_no_cobrada" and "video" in enviados[0][3] and "2,25" in enviados[0][3]
    avisos.saldo_bajo("acme", 3000)
    avisos.saldo_bajo("acme", 2000)
    assert [e[1] for e in enviados].count("saldo_bajo") == 1
    avisos.limpiar_aviso_bajo("acme")
    avisos.saldo_bajo("acme", 1000)
    assert [e[1] for e in enviados].count("saldo_bajo") == 2


def test_avisos_nunca_lanzan(base_temporal, monkeypatch):
    from cobros import avisos

    def roto(*a, **k):
        raise RuntimeError("smtp caído")
    monkeypatch.setattr(avisos.notificaciones, "avisar", roto)
    monkeypatch.setattr(avisos.notificaciones, "avisar_admin", roto)
    assert avisos.pieza_no_cobrada("acme", 1000, "video") is False
    assert avisos.admin("pago_sin_recarga", "a", "b") == 0


def test_frase_de_saldo_insuficiente(libro, base_temporal):
    import idiomas
    e = libro.SaldoInsuficiente("acme", 1500, 500)
    with idiomas.en_idioma("es"):
        assert "1,50" in e.frase() and "0,50" in e.frase()
        assert "esto cuesta" not in libro.SaldoInsuficiente("acme", 1, 0).frase()


def test_saldo_bajo_con_carrera_en_la_marca_no_lanza_ni_avisa(base_temporal, monkeypatch):
    import sqlalchemy as sa2
    from cobros import avisos
    enviados = []
    monkeypatch.setattr(avisos.notificaciones, "avisar", lambda *a: enviados.append(a) or True)
    real = avisos.sa.select

    class Rival:   # el select no ve la marca, pero el insert choca con la que otro acaba de poner
        def __init__(self):
            with base_temporal.conectar() as con:
                con.execute(base_temporal.kv.insert().values(clave="cobros:aviso_bajo:acme", valor="1",
                                                             actualizado_en=AHORA))
    monkeypatch.setattr(avisos.sa, "select", lambda *a, **k: (Rival(), real(sa2.literal(0)).where(sa2.false()))[1])
    assert avisos.saldo_bajo("acme", 100) is False
    assert enviados == []


# ---- concurrencia: el candado se toma ANTES de leer (fix 1 de la Task 3) ----

def test_exigir_no_deja_que_otra_reserva_entre_en_medio(libro, base_temporal, escritor_en_medio):
    """Sin el candado, otra reserva confirmada entre la lectura del disponible y
    la escritura pasaba: juntas reservaban más que el saldo."""
    libro.configurar("acme", usuario="admin", cobrar=True)
    with base_temporal.conectar() as con:
        libro.acreditar(con, "acme", "recarga", 2000, "recarga_manual")
    _tarea(base_temporal, "j1")
    _tarea(base_temporal, "j2")
    otro = escritor_en_medio("DELETE FROM reserva_saldo",
                             "insert into reserva_saldo(cliente, job_id, milesimas, creada_en) "
                             "values ('acme', 'j2', 1500, 'ahora')")
    assert libro.exigir("acme", 1.0, job_id="j1") == 1500
    assert otro["resultado"].startswith("bloqueado")
    assert libro.reservado("acme") <= libro.saldo("acme")


def test_revertir_no_pierde_reversos_si_otro_revierte_en_medio(libro, base_temporal, monkeypatch, escritor_en_medio):
    """Sin el candado, un reverso ajeno confirmado en medio tumbaba con
    IntegrityError el lote entero: el segundo cobro quedaba sin revertir."""
    import gastos
    from cobros import avisos
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda *a: None)
    libro.configurar("acme", usuario="admin", cobrar=True)
    with libro.en_trabajo(1, "j1"):
        g1 = gastos.registrar("acme", "video", 1.0, "video:1:t1")
        g2 = gastos.registrar("acme", "video", 2.0, "video:1:t1:musica")
    otro = escritor_en_medio("INSERT INTO movimiento_saldo",
                             "insert into movimiento_saldo(cliente, creado_en, tipo, milesimas, gasto_id, job_id, concepto) "
                             f"values ('acme', 'ahora', 'reverso', 1500, {g1}, 'j1', 'video')")
    assert len(libro.revertir_trabajo("acme", "j1", "falló")) == 2
    assert otro["resultado"].startswith("bloqueado")
    m = base_temporal.movimiento_saldo
    with base_temporal.conectar() as con:
        rev = con.execute(sa.select(m.c.gasto_id).where(m.c.tipo == "reverso")).scalars().all()
    assert sorted(rev) == sorted([g1, g2])
    assert libro.saldo("acme") == 0


def test_configurar_no_choca_con_otro_que_crea_la_cuenta_en_medio(libro, base_temporal, escritor_en_medio):
    otro = escritor_en_medio("INSERT INTO cuenta_saldo",
                             "insert into cuenta_saldo(cliente, cobrar, umbral_aviso) values ('acme', 0, 5000)")
    assert libro.configurar("acme", usuario="admin", cobrar=True)["cobrar"] is True
    assert otro["resultado"].startswith("bloqueado")


def test_guardar_margen_global_no_choca_con_otro_en_medio(libro, base_temporal, escritor_en_medio):
    otro = escritor_en_medio("INSERT INTO kv",
                             f"insert into kv(clave, valor, actualizado_en) values ('{libro.CLAVE_MARGEN}', '2.0', 'ahora')")
    libro.guardar_margen_global(1.8, "admin")
    assert libro.margen_global() == 1.8
    assert otro["resultado"].startswith("bloqueado")

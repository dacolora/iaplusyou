"""El libro con plan (spec planes 2026-10-09 §3-§4): la bolsa del plan primero,
el precio de miembro, lo incluido con tope de uso justo y la prioridad.

Las filas de `periodo_plan` se crean a mano (el escritor de verdad, cobros/planes.py,
llega en la Task 5); los movimientos del libro nacen con la hora real, así que los
periodos se arman alrededor de ahora."""
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa


def _iso(dt):
    return dt.isoformat(timespec="seconds")


AHORA = datetime.now()
INICIO = _iso(AHORA - timedelta(days=1))
FIN = _iso(AHORA + timedelta(days=29))


@pytest.fixture()
def libro(base_temporal):
    from cobros import libro
    return libro


@pytest.fixture()
def planes(base_temporal):
    from cobros import planes
    return planes


@pytest.fixture()
def sin_avisos(monkeypatch):
    """Los avisos al proyecto y a los admins, anotados en vez de enviados."""
    from cobros import avisos
    enviados = []
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda *a, **k: enviados.append(("pieza_no_cobrada", a)))
    monkeypatch.setattr(avisos, "saldo_bajo", lambda *a, **k: enviados.append(("saldo_bajo", a)))
    monkeypatch.setattr(avisos, "admin", lambda tipo, *a, **k: enviados.append((tipo, a)))
    return enviados


def _periodo(db, cliente="acme", inicio=INICIO, fin=FIN, margen=1.25, tope=25.0, credito=10_000, cerrado=False,
             suscripcion_id=1):
    with db.conectar() as con:
        return int(con.execute(db.periodo_plan.insert().values(
            cliente=cliente, suscripcion_id=suscripcion_id, inicio=inicio, fin=fin, precio_usd=credito // 1000,
            margen=margen, tope_incluido_usd=tope, credito_milesimas=credito, cerrado=cerrado)).inserted_primary_key[0])


def _movs(db, cliente="acme", tipo=None):
    m = db.movimiento_saldo
    q = sa.select(m).where(m.c.cliente == cliente).order_by(m.c.id)
    if tipo:
        q = q.where(m.c.tipo == tipo)
    with db.conectar() as con:
        return con.execute(q).all()


def _acreditar(db, libro, milesimas, tipo="recarga", cliente="acme"):
    with db.conectar() as con:
        libro.acreditar(con, cliente, tipo, milesimas, "recarga_manual" if tipo == "recarga" else "ajuste",
                        usuario="admin", detalle="prueba")


def _abrir(db, libro, **kw):
    """Periodo abierto ahora y su bolsa acreditada (lo que hará planes en la Task 5)."""
    pid = _periodo(db, **kw)
    with db.conectar() as con:
        libro.acreditar_plan(con, pid)
    return pid


def _tarea_viva(db, job_id, cliente="acme"):
    with db.conectar() as con:
        con.execute(sa.insert(db.tarea).values(
            cliente=cliente, job_id=job_id, tipo="flowplus_video", payload={}, estado="en_curso", intentos=0,
            max_intentos=1, prioridad=5, ejecutar_desde=db.ahora(), creada_en=db.ahora(), duracion_estimada=60.0,
            etapas=[]))


# ------------------------------------------------------------ lecturas ---

def test_tipos_incluidos_son_tipos_de_gasto_y_nada_caro(planes):
    import gastos
    assert planes.TIPOS_INCLUIDOS <= set(gastos.TIPOS)
    assert "revision" in planes.TIPOS_INCLUIDOS            # el diagnóstico de una perdedora se anota como «revision»
    assert {"guion", "transcripcion", "clasificacion", "adaptar_referente"} <= planes.TIPOS_INCLUIDOS
    for caro in ("recoleccion", "video", "imagen", "swap", "final", "musica", "locucion", "voz_propia", "avatares",
                 "investigacion", "otro"):
        assert caro not in planes.TIPOS_INCLUIDOS


def test_tipos_de_tarea_mapean_a_tipos_incluidos(planes):
    import tareas
    for tipo_tarea, tipo_gasto in planes.GASTO_DE_TAREA.items():
        assert tipo_tarea in tareas.TIPOS_QUE_COBRAN
        assert tipo_gasto in planes.TIPOS_INCLUIDOS


def test_periodo_abierto_solo_el_vigente_y_sin_cerrar(base_temporal, planes):
    assert planes.periodo_abierto(None, "acme") is None
    _periodo(base_temporal, inicio=_iso(AHORA - timedelta(days=40)), fin=_iso(AHORA - timedelta(days=10)))  # pasado
    _periodo(base_temporal, inicio=_iso(AHORA + timedelta(days=30)), fin=_iso(AHORA + timedelta(days=60)),
             suscripcion_id=2)                                                                               # futuro
    _periodo(base_temporal, cerrado=True, suscripcion_id=3)                                                  # cerrado
    assert planes.periodo_abierto(None, "acme") is None
    pid = _periodo(base_temporal, suscripcion_id=4)
    p = planes.periodo_abierto(None, "acme")
    assert p == {"id": pid, "inicio": INICIO, "fin": FIN, "margen": 1.25, "tope_incluido_usd": 25.0,
                 "credito_milesimas": 10_000, "suscripcion_id": 4}
    assert planes.periodo_abierto("acme") == p                    # la forma corta, sin conexión
    assert planes.periodo_abierto(None, "acme", ahora=FIN) is None   # el fin no es parte del periodo
    assert planes.periodo_abierto(None, "otro") is None


def test_marcar_cerrado(base_temporal, planes):
    pid = _periodo(base_temporal)
    with base_temporal.conectar() as con:
        assert planes.marcar_cerrado(con, pid) == 1
    assert planes.periodo_abierto(None, "acme") is None


def test_periodo_abierto_se_memoriza_por_peticion_y_no_entre_peticiones(base_temporal, planes):
    import flask
    app = flask.Flask(__name__)
    with app.test_request_context("/"):
        assert planes.periodo_abierto(None, "acme") is None
        _periodo(base_temporal)
        assert planes.periodo_abierto(None, "acme") is None        # misma petición: la lectura de antes
        with base_temporal.conectar() as con:                      # con conexión nunca se memoriza
            assert planes.periodo_abierto(con, "acme") is not None
    with app.test_request_context("/"):
        assert planes.periodo_abierto(None, "acme") is not None    # otra petición: lee de nuevo


# ---------------------------------------------------------- el margen ---

def test_margen_de_miembro_con_periodo_y_a_la_carta_sin_el(base_temporal, libro):
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert libro.cuenta("acme")["margen"] == 2.0 and libro.margen_precio("acme") == 2.0
    _periodo(base_temporal)
    assert libro.cuenta("acme")["margen"] == 1.25
    assert libro.margen_precio("acme") == 1.25
    assert libro.estado("acme")["margen"] == 1.25
    libro.configurar("acme", usuario="admin", margen=1.8)            # el propio no le gana al del plan
    assert libro.cuenta("acme")["margen"] == 1.25
    assert libro.cuenta("acme")["margen_propio"] == 1.8
    assert libro.cuenta("otro")["margen"] == 2.0                     # otro proyecto: a la carta


def test_cobro_en_periodo_a_precio_de_miembro(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    _abrir(base_temporal, libro)
    gastos.registrar("acme", "video", 1.0, "video:1:t1")
    (c,) = _movs(base_temporal, tipo="cobro")
    assert c.milesimas == -1250 and c.extra["margen"] == 1.25


def test_cuenta_sin_plan_no_cambia_de_forma(base_temporal, libro):
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert set(libro.cuenta("acme")) == {"cobrar", "margen", "margen_propio", "umbral"}
    assert set(libro.cuenta("sin_fila")) == {"cobrar", "margen", "margen_propio", "umbral"}


# ------------------------------------------------------------ la bolsa ---

def test_bolsa_primero_el_plan_con_recarga_propia_a_mitad(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert libro.bolsa_plan("acme") is None
    pid = _abrir(base_temporal, libro)
    assert libro.bolsa_plan("acme") == {"periodo_id": pid, "credito": 10_000, "gastado": 0, "restante": 10_000,
                                        "fin": FIN}
    gastos.registrar("acme", "video", 2.4, "video:1:t1")             # 3 000
    _acreditar(base_temporal, libro, 5_000)                          # recarga propia: no es de la bolsa
    gastos.registrar("acme", "video", 3.2, "video:2:t2")             # 4 000
    b = libro.bolsa_plan("acme")
    assert (b["gastado"], b["restante"]) == (7_000, 3_000)
    assert libro.saldo("acme") == 8_000                              # 3 000 de la bolsa + 5 000 propios
    _acreditar(base_temporal, libro, -1_000, tipo="ajuste")          # un ajuste no es gasto del periodo
    assert libro.bolsa_plan("acme")["restante"] == 3_000
    with libro.en_trabajo(9, "j9"):
        gastos.registrar("acme", "video", 4.8, "video:3:t3")         # 6 000: se acaba la bolsa y toma 3 000 propios
    assert libro.bolsa_plan("acme")["restante"] == 0
    assert libro.bolsa_plan("acme")["gastado"] == 13_000
    libro.revertir_trabajo("acme", "j9", "falló")                    # el reverso devuelve a la bolsa
    assert libro.bolsa_plan("acme")["gastado"] == 7_000
    assert libro.bolsa_plan("acme")["restante"] == 3_000


def test_devolver_un_cobro_de_antes_del_periodo_no_infla_la_bolsa(base_temporal, libro, sin_avisos):
    """El reverso de un cobro del mes anterior devuelve saldo propio: la bolsa no pasa de su crédito
    (si no, el vencimiento se llevaría esa plata del cliente)."""
    libro.configurar("acme", usuario="admin", cobrar=True)
    antes = _iso(AHORA - timedelta(days=5))
    with base_temporal.conectar() as con:
        con.execute(base_temporal.movimiento_saldo.insert().values(
            cliente="acme", creado_en=antes, tipo="cobro", milesimas=-3_000, gasto_id=77, job_id="viejo",
            concepto="video", extra={"margen": 2.0}))
    _acreditar(base_temporal, libro, 3_000)
    pid = _abrir(base_temporal, libro)
    libro.revertir_trabajo("acme", "viejo", "falló")                 # reverso de hoy, cobro de antes
    b = libro.bolsa_plan("acme")
    assert (b["gastado"], b["restante"]) == (0, 10_000)
    assert libro.saldo("acme") == 13_000
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 10_000
    assert libro.saldo("acme") == 3_000                              # lo devuelto queda como propio


def test_acreditar_plan_es_idempotente(base_temporal, libro):
    pid = _periodo(base_temporal)
    with base_temporal.conectar() as con:
        mid = libro.acreditar_plan(con, pid)
    with base_temporal.conectar() as con:
        assert libro.acreditar_plan(con, pid) is None
    (p,) = _movs(base_temporal, tipo="plan")
    assert p.id == mid and p.milesimas == 10_000 and p.periodo_id == pid
    assert libro.saldo("acme") == 10_000


def test_acreditar_plan_toma_el_candado_antes_de_leer(base_temporal, libro, escritor_en_medio):
    pid = _periodo(base_temporal)
    otro = escritor_en_medio("FROM movimiento_saldo",
                             "insert into movimiento_saldo(cliente, creado_en, tipo, milesimas, periodo_id, concepto) "
                             f"values ('acme', 'ahora', 'plan', 10000, {pid}, 'plan')")
    with base_temporal.conectar() as con:
        assert libro.acreditar_plan(con, pid) is not None
    assert otro["resultado"].startswith("bloqueado")
    assert len(_movs(base_temporal, tipo="plan")) == 1


# ---------------------------------------------------------- vencimiento ---

def test_vencer_periodo_exacto_e_idempotente_sin_tocar_lo_propio(base_temporal, libro, planes, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    pid = _abrir(base_temporal, libro)
    _acreditar(base_temporal, libro, 5_000)
    gastos.registrar("acme", "video", 2.4, "video:1:t1")             # 3 000
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 7_000
        planes.marcar_cerrado(con, pid)
    assert libro.saldo("acme") == 5_000                              # lo recargado aparte no vence
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 7_000               # segunda vez: el mismo, sin escribir otro
    (v,) = _movs(base_temporal, tipo="vencimiento")
    assert v.milesimas == -7_000 and v.periodo_id == pid
    assert libro.saldo("acme") == 5_000
    assert planes.periodo_abierto(None, "acme") is None


def test_vencer_periodo_gastado_entero_escribe_cero(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    pid = _abrir(base_temporal, libro, credito=1_250)
    gastos.registrar("acme", "video", 1.0, "video:1:t1")             # 1 250: la bolsa entera
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 0
    (v,) = _movs(base_temporal, tipo="vencimiento")
    assert v.milesimas == 0
    assert libro.saldo("acme") == 0


def test_vencer_no_deja_el_saldo_negativo_tras_una_anulacion(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    pid = _abrir(base_temporal, libro)
    gastos.registrar("acme", "video", 1.6, "video:1:t1")             # 2 000: quedan 8 000 en la bolsa
    _acreditar(base_temporal, libro, -5_000, tipo="anulacion")       # el saldo es 3 000
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 3_000
    assert libro.saldo("acme") == 0


def test_vencer_con_saldo_ya_negativo_no_resta_nada(base_temporal, libro):
    pid = _abrir(base_temporal, libro)
    _acreditar(base_temporal, libro, -11_000, tipo="anulacion")
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 0
    assert libro.saldo("acme") == -1_000


def test_vencer_toma_el_candado_antes_de_leer(base_temporal, libro, escritor_en_medio):
    pid = _abrir(base_temporal, libro)
    otro = escritor_en_medio("FROM movimiento_saldo",
                             "insert into movimiento_saldo(cliente, creado_en, tipo, milesimas, concepto) "
                             "values ('acme', 'ahora', 'anulacion', -9000, 'ajuste')")
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 10_000
    assert otro["resultado"].startswith("bloqueado")
    assert libro.saldo("acme") == 0


# ------------------------------------------------------------ incluido ---

def test_incluido_dentro_del_tope_no_descuenta(base_temporal, libro, planes, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    _abrir(base_temporal, libro)
    gid = gastos.registrar("acme", "guion", 0.10, "guion:1:t1")
    (i,) = _movs(base_temporal, tipo="incluido")
    assert i.milesimas == 0 and i.gasto_id == gid and i.concepto == "guion"
    assert i.extra == {"precio": 125, "costo": 0.1, "margen": 1.25, "periodo_id": 1}
    assert not _movs(base_temporal, tipo="cobro")
    assert libro.saldo("acme") == 10_000
    assert planes.incluido_usado("acme", planes.periodo_abierto(None, "acme")) == pytest.approx(0.1)
    assert sin_avisos == []                                          # al cliente no se le avisa nada


def test_incluido_que_cruza_el_tope_se_cobra_a_precio_de_miembro(base_temporal, libro, planes, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    _abrir(base_temporal, libro, tope=0.30)
    gastos.registrar("acme", "guion", 0.10, "guion:1:t1")            # incluido (0,10 de 0,30)
    gastos.registrar("acme", "transcripcion", 0.25, "transcripcion:1")   # 0,35 > 0,30: cobro a precio de miembro
    gastos.registrar("acme", "revision", 0.20, "revision:1")         # 0,1 + 0,2 = 0,30000000000000004: cabe justo
    incl = _movs(base_temporal, tipo="incluido")
    (c,) = _movs(base_temporal, tipo="cobro")
    assert [m.concepto for m in incl] == ["guion", "revision"]
    assert c.concepto == "transcripcion" and c.milesimas == -313 and c.extra["margen"] == 1.25
    assert planes.incluido_usado("acme", planes.periodo_abierto(None, "acme")) == pytest.approx(0.30)


def test_incluido_no_aplica_a_lo_caro_ni_sin_periodo(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    _acreditar(base_temporal, libro, 5_000)
    gastos.registrar("acme", "guion", 0.10, "guion:1:t1")            # sin plan: a la carta ×2
    assert _movs(base_temporal, tipo="cobro")[-1].milesimas == -200
    _abrir(base_temporal, libro)
    gastos.registrar("acme", "video", 0.10, "video:1:t1")            # video: nunca incluido
    gastos.registrar("acme", "recoleccion", 0.10, "recoleccion:1")   # Apify: nunca incluido
    assert [m.milesimas for m in _movs(base_temporal, tipo="cobro")] == [-200, -125, -125]
    assert not _movs(base_temporal, tipo="incluido")


def test_correccion_de_un_incluido_sigue_incluida(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    _abrir(base_temporal, libro)
    gastos.registrar("acme", "guion", 0.10, "guion:1:t1")
    gastos.registrar("acme", "guion", 0.30, "guion:1:t1")            # corrección del monto
    (i,) = _movs(base_temporal, tipo="incluido")
    assert i.extra == {"precio": 375, "costo": 0.3, "margen": 1.25, "periodo_id": 1}
    assert not _movs(base_temporal, tipo="cobro")
    assert libro.saldo("acme") == 10_000


def test_incluido_no_entregado_queda_no_cobrado_como_siempre(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    _abrir(base_temporal, libro)
    gastos.registrar("acme", "guion", 0.10, "guion:1:t1", entregado=False)
    (n,) = _movs(base_temporal, tipo="no_cobrado")
    assert n.milesimas == 0 and n.extra["margen"] == 1.25
    assert not _movs(base_temporal, tipo="incluido")


def test_proyecto_que_no_cobra_no_cambia_aunque_tenga_periodo(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=False)
    _periodo(base_temporal)
    assert libro.margen_precio("acme") == 1.0
    assert libro.exigir("acme", 9.0, job_id="j1", tipo="guion") == 0
    gastos.registrar("acme", "guion", 0.10, "guion:1:t1")
    gastos.registrar("acme", "video", 1.0, "video:1:t1")
    assert _movs(base_temporal) == []
    assert libro.bolsa_plan("sin_fila") is None


# -------------------------------------------------------------- avisos ---

def test_avisa_al_admin_al_80_y_al_100_una_vez_por_periodo(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    _abrir(base_temporal, libro, tope=1.0)
    gastos.registrar("acme", "guion", 0.50, "guion:1")
    assert sin_avisos == []
    gastos.registrar("acme", "guion", 0.35, "guion:2")               # 85 %
    gastos.registrar("acme", "guion", 0.10, "guion:3")               # 95 %: el de 80 ya salió
    assert [t for t, _ in sin_avisos] == ["tope_incluido"]
    gastos.registrar("acme", "guion", 0.05, "guion:4")               # 100 %
    gastos.registrar("acme", "guion", 0.10, "guion:5")               # ya pasado: se cobra, sin otro aviso
    assert [t for t, _ in sin_avisos] == ["tope_incluido", "tope_incluido"]


def test_avisa_el_100_cuando_lo_incluido_ya_no_alcanza(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    _abrir(base_temporal, libro, tope=1.0)
    gastos.registrar("acme", "guion", 0.70, "guion:1")               # 70 %: nada
    gastos.registrar("acme", "guion", 0.50, "guion:2")               # no cabe: cobro y aviso del 100 %
    assert len(_movs(base_temporal, tipo="cobro")) == 1
    assert [t for t, _ in sin_avisos] == ["tope_incluido"]
    gastos.registrar("acme", "guion", 0.20, "guion:3")               # 90 %: el del 80 ya no tiene sentido
    gastos.registrar("acme", "guion", 0.50, "guion:4")               # otro que no cabe: el del 100 ya salió
    assert [t for t, _ in sin_avisos] == ["tope_incluido"]


# --------------------------------------------------------------- freno ---

def test_exigir_tipo_incluido_dentro_del_tope_no_pide_saldo(base_temporal, libro):
    libro.configurar("acme", usuario="admin", cobrar=True)
    pid = _periodo(base_temporal, tope=0.20)                         # sin bolsa acreditada: saldo 0
    _tarea_viva(base_temporal, "j1")
    assert libro.exigir("acme", 0.13, job_id="j1", tipo="guion") == 0
    with base_temporal.conectar() as con:                            # una reserva de 0 que recuerda «incluido»
        r = con.execute(sa.select(base_temporal.reserva_saldo)).one()
    assert (r.milesimas, r.incluido, r.margen, r.periodo_id) == (0, True, 1.25, pid)
    assert libro.reservado("acme") == 0
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", 0.13, job_id="j1")                      # sin tipo: como siempre
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", 0.13, tipo="video")                     # tipo que no es incluido
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", 0.30, tipo="guion")                     # no cabe en el tope
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", None, tipo="guion")                     # sin precio no se sabe si cabe
    with base_temporal.conectar() as con:
        from cobros import planes
        planes.marcar_cerrado(con, pid)
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", 0.13, tipo="guion")                     # sin periodo: como siempre


# ----------------------------------------------------- encolar y prioridad ---

def _prioridad(db, job_id):
    with db.conectar() as con:
        return con.execute(sa.select(db.tarea.c.prioridad).where(db.tarea.c.job_id == job_id)).scalar()


def test_prioridad_6_con_plan_y_5_sin_el(base_temporal, libro):
    import trabajos
    libro.configurar("acme", usuario="admin", cobrar=True)
    trabajos.encolar("acme__a", "cola_limpiar", {}, cliente="acme")
    assert _prioridad(base_temporal, "acme__a") == 5
    _periodo(base_temporal)
    _periodo(base_temporal, cliente="otro", suscripcion_id=2)         # «otro» no cobra: su periodo no le sube nada
    trabajos.encolar("acme__b", "cola_limpiar", {}, cliente="acme")
    trabajos.encolar("acme__lote", "cola_limpiar", {}, cliente="acme", prioridad=3)
    trabajos.encolar("acme__alta", "cola_limpiar", {}, cliente="acme", prioridad=7)
    trabajos.encolar("otro__a", "cola_limpiar", {}, cliente="otro")
    assert _prioridad(base_temporal, "acme__b") == 6
    assert _prioridad(base_temporal, "acme__lote") == 3                # un lote nunca sube ni baja
    assert _prioridad(base_temporal, "acme__alta") == 7
    assert _prioridad(base_temporal, "otro__a") == 5


def test_encolar_tipo_incluido_con_plan_no_pide_saldo(base_temporal, libro):
    import trabajos
    from cobros.libro import SaldoInsuficiente
    libro.configurar("acme", usuario="admin", cobrar=True)
    with pytest.raises(SaldoInsuficiente):
        trabajos.encolar("acme__g1", "final_guion", {}, cliente="acme", costo_estimado=0.13)
    _periodo(base_temporal)                                          # saldo 0, pero el guion está incluido
    assert trabajos.encolar("acme__g1", "final_guion", {}, cliente="acme", costo_estimado=0.13) is True
    assert _prioridad(base_temporal, "acme__g1") == 6
    with pytest.raises(SaldoInsuficiente):                          # un video sigue pidiendo saldo
        trabajos.encolar("acme__v1", "flowplus_video", {}, cliente="acme", costo_estimado=1.0)


def test_encolar_sin_plan_igual_que_antes(base_temporal, libro, monkeypatch):
    """Sin periodo, `exigir` recibe exactamente lo de antes (sin `tipo`) y la prioridad pedida."""
    import trabajos
    llamadas = []
    monkeypatch.setattr(libro, "exigir", lambda *a, **k: llamadas.append((a, k)) or 0)
    trabajos.encolar("acme__v1", "flowplus_video", {}, cliente="acme", costo_estimado=1.0)
    assert llamadas == [(("acme", 1.0), {"job_id": "acme__v1", "excluir_job": None})]
    assert _prioridad(base_temporal, "acme__v1") == 5


def test_una_llamada_sincronica_incluida_no_pide_saldo_con_plan(base_temporal, libro, monkeypatch):
    """Las rutas y funciones que llaman a Claude en la petición pasan su `tipo` a `exigir`
    (aquí la regla de fidelidad del importador): con plan y dentro del tope, saldo 0 no la frena."""
    import importador
    monkeypatch.setattr(importador.generador_prompts, "regla_fidelidad", lambda *a: "regla")
    monkeypatch.setattr(importador.idiomas, "de_proyecto", lambda c: "es")
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert importador._regla_si_hay_saldo("acme", "Chancla", "", "") == ""       # sin plan y sin saldo: sin regla
    _periodo(base_temporal)
    assert importador._regla_si_hay_saldo("acme", "Chancla", "", "") == "regla"


# ----------------------------------------------- respaldo del worker (fix 1) ---

@pytest.fixture()
def worker_guion(base_temporal, libro, monkeypatch):
    """El worker de verdad corriendo una `final_guion` (tipo que cobra, gasto «guion» incluido) con un
    ejecutor falso que anota su gasto como lo haría Claude."""
    import idiomas
    import tareas
    import worker
    import gastos
    monkeypatch.setattr(worker, "PERIODICAS", [])
    monkeypatch.setattr(idiomas, "de_proyecto", lambda cliente: "es")
    llamado = []

    def fn(tarea):
        llamado.append(tarea["id"])
        gastos.registrar_seguro("acme", "guion", 0.13, f"guion:t{tarea['id']}")
        return "listo"
    monkeypatch.setitem(tareas.REGISTRO, "final_guion", fn)
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "final_guion", lambda t, m: None)
    libro.configurar("acme", usuario="admin", cobrar=True)
    return llamado


def _correr_guion(db, job_id):
    import cola
    import trabajos
    import worker
    assert trabajos.encolar(job_id, "final_guion", {}, cliente="acme", costo_estimado=0.13, max_intentos=1)
    tarea = cola.reclamar()
    worker._correr(tarea)
    return cola.consultar_por_id(tarea["id"])


def test_respaldo_deja_correr_lo_incluido_con_plan_y_saldo_cero(base_temporal, libro, worker_guion, sin_avisos):
    import tareas
    _periodo(base_temporal)                                          # plan abierto, saldo 0
    assert libro.puede_arrancar({"tipo": "flowplus_video", "cliente": "acme"}, tareas.TIPOS_QUE_COBRAN) is False
    fila = _correr_guion(base_temporal, "acme__g1")
    assert fila["estado"] == "hecha" and worker_guion
    (i,) = _movs(base_temporal, tipo="incluido")
    assert i.extra["costo"] == 0.13
    assert libro.saldo("acme") == 0


def test_respaldo_frena_lo_incluido_sin_tope_o_sin_plan(base_temporal, libro, worker_guion, sin_avisos):
    import cola
    import tareas
    import worker
    from cobros import planes
    # Sin plan y sin saldo, `encolar` no lo deja pasar; una tarea que llegó a la cola por otro lado la frena el respaldo.
    cola.encolar("final_guion", {}, cliente="acme", job_id="acme__g0", max_intentos=1)
    tarea = cola.reclamar()
    assert libro.puede_arrancar(tarea, tareas.TIPOS_QUE_COBRAN) is False
    worker._correr(tarea)
    assert cola.consultar_por_id(tarea["id"])["mensaje"] == worker.MENSAJE_SIN_SALDO
    # Con plan pero el tope ya gastado: tampoco arranca.
    _periodo(base_temporal, tope=0.13)
    _correr_guion(base_temporal, "acme__g1")                         # usa el tope entero
    assert planes.incluido_usado("acme", planes.periodo_abierto(None, "acme")) == pytest.approx(0.13)
    cola.encolar("final_guion", {}, cliente="acme", job_id="acme__g2", max_intentos=1)
    tarea = cola.reclamar()
    assert libro.puede_arrancar(tarea, tareas.TIPOS_QUE_COBRAN) is False
    # Un video con plan abierto y saldo 0 nunca arranca por el plan.
    assert len(worker_guion) == 1


def test_respaldo_sin_plan_no_lee_periodo_plan(base_temporal, libro):
    """Un proyecto que cobra y tiene saldo arranca sin una sola lectura del plan."""
    import tareas
    from sqlalchemy import event
    libro.configurar("acme", usuario="admin", cobrar=True)
    _acreditar(base_temporal, libro, 5_000)
    vistas = []

    def contar(conn, cursor, statement, *a):
        vistas.append(statement)
    event.listen(base_temporal.engine(), "before_cursor_execute", contar)
    try:
        assert libro.puede_arrancar({"tipo": "final_guion", "cliente": "acme"}, tareas.TIPOS_QUE_COBRAN) is True
        libro.exigir("acme", 0.13)
    finally:
        event.remove(base_temporal.engine(), "before_cursor_execute", contar)
    assert not [q for q in vistas if "periodo_plan" in q][1:]       # exigir: a lo más una (con el candado)
    assert sum("FROM cuenta_saldo" in q for q in vistas) <= 3        # respaldo 1 + exigir (barata 1 + con candado 1)


def test_prioridad_no_lee_el_plan_de_un_proyecto_que_no_cobra(base_temporal, libro, monkeypatch):
    import trabajos
    from cobros import planes
    monkeypatch.setattr(planes, "periodo_abierto", lambda *a, **k: pytest.fail("no debía leer el plan"))
    trabajos.encolar("acme__a", "cola_limpiar", {}, cliente="acme")
    libro.configurar("acme", usuario="admin", cobrar=False)
    trabajos.encolar("acme__b", "cola_limpiar", {}, cliente="acme")
    assert _prioridad(base_temporal, "acme__a") == _prioridad(base_temporal, "acme__b") == 5


def test_exigir_con_plan_ilegible_cobra_como_sin_plan(base_temporal, libro, monkeypatch, caplog):
    """Si leer el plan falla en el freno, nunca un 500: se pide el precio a la carta y queda en el log."""
    from cobros import planes
    libro.configurar("acme", usuario="admin", cobrar=True)
    _periodo(base_temporal)
    _acreditar(base_temporal, libro, 5_000)

    def rota(*a, **k):
        raise RuntimeError("base rota")
    monkeypatch.setattr(planes, "periodo_abierto", rota)
    _tarea_viva(base_temporal, "j1")
    assert libro.exigir("acme", 0.13, job_id="j1", tipo="guion") == 260   # 0,13 × 2,0: a la carta
    assert "no se pudo leer el plan" in caplog.text
    monkeypatch.undo()
    monkeypatch.setattr(planes, "incluido_usado", rota)
    assert libro.exigir("acme", 0.13, tipo="guion") == 163               # periodo leído (×1,25), tope ilegible: cobra


# -------------------------------------- el precio visto al encolar (revisión final 2026-10-10) ---

def _terminar_periodo(db, pid):
    """El periodo llega a su fin (sin cerrarlo todavía): ya no está abierto."""
    with db.conectar() as con:
        con.execute(db.periodo_plan.update().where(db.periodo_plan.c.id == pid)
                    .values(fin=_iso(datetime.now() - timedelta(seconds=1))))


def test_un_video_reservado_antes_del_fin_se_cobra_al_margen_visto_y_de_su_bolsa(base_temporal, libro, sin_avisos):
    """Aprobado a ×1,25 a las 09:50, llega después del fin: se cobra ×1,25 (no ×2) y cuenta en la bolsa que lo
    pagó; al vencer, el saldo propio queda entero."""
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    pid = _abrir(base_temporal, libro)                               # bolsa 10 000
    _acreditar(base_temporal, libro, 5_000)                          # 5 000 propios
    _tarea_viva(base_temporal, "lote")
    assert libro.exigir("acme", 3.2, job_id="lote") == 4_000         # 3,2 × 1,25
    _terminar_periodo(base_temporal, pid)
    assert libro.cuenta("acme")["margen"] == 2.0                     # a la carta desde el fin
    with libro.en_trabajo(1, "lote"):
        gastos.registrar("acme", "video", 3.2, "video:1:t1")
    (c,) = _movs(base_temporal, tipo="cobro")
    assert c.milesimas == -4_000 and c.extra == {"margen": 1.25, "periodo_id": pid}
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 6_000               # 10 000 − 4 000 del lote
    assert libro.saldo("acme") == 5_000                              # lo propio no se tocó
    gastos.registrar("acme", "video", 1.0, "video:2:t2")             # sin reserva (sincrónico): a la carta
    assert _movs(base_temporal, tipo="cobro")[-1].milesimas == -2_000


def test_un_incluido_reservado_que_termina_pasado_el_fin_sigue_incluido(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    pid = _abrir(base_temporal, libro)
    _tarea_viva(base_temporal, "guion1")
    assert libro.exigir("acme", 0.13, job_id="guion1", tipo="guion") == 0
    _terminar_periodo(base_temporal, pid)
    with libro.en_trabajo(1, "guion1"):
        gastos.registrar("acme", "guion", 0.13, "guion:1:t1")
    (i,) = _movs(base_temporal, tipo="incluido")
    assert i.milesimas == 0 and i.extra["periodo_id"] == pid and i.extra["margen"] == 1.25
    assert not _movs(base_temporal, tipo="cobro")


def test_el_cobro_de_un_periodo_viejo_no_cuenta_en_la_bolsa_del_nuevo(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    viejo = _abrir(base_temporal, libro)
    _tarea_viva(base_temporal, "lote")
    libro.exigir("acme", 1.6, job_id="lote")                         # 2 000 a ×1,25
    _terminar_periodo(base_temporal, viejo)
    nuevo = _abrir(base_temporal, libro, inicio=_iso(datetime.now() - timedelta(seconds=1)), suscripcion_id=2)
    with libro.en_trabajo(1, "lote"):
        gastos.registrar("acme", "video", 1.6, "video:1:t1")
    assert libro.bolsa_plan("acme")["periodo_id"] == nuevo
    assert libro.bolsa_plan("acme")["gastado"] == 0                  # es del viejo
    with base_temporal.conectar() as con:
        from cobros import planes
        assert libro._bolsa(con, "acme", planes.periodo(con, viejo))["gastado"] == 2_000


def test_una_reserva_incluida_no_hace_pasar_otra_cosa_del_mismo_trabajo(base_temporal, libro):
    libro.configurar("acme", usuario="admin", cobrar=True)
    _periodo(base_temporal, tope=0.20)                               # sin bolsa: saldo 0
    _tarea_viva(base_temporal, "j1")
    assert libro.exigir("acme", 0.13, job_id="j1", tipo="guion") == 0
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", 0.13, job_id="j1")                      # la reserva de 0 no es «ya reservado»


# ------------------------------------------- la etiqueta «Incluido en tu plan» (spec §4 y §8) ---

def _estimar_en_peticion(tipo, cliente="acme", **params):
    import dashboard
    import gastos
    from flask import g
    with dashboard.app.test_request_context(f"/cliente/{cliente}"):
        g.cliente_precio = cliente
        return gastos.estimar(tipo, **params)


def test_lo_incluido_dice_incluido_en_tu_plan_mientras_quede_tope(base_temporal, libro, sin_avisos):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert _estimar_en_peticion("guion")["texto"] == "US$ 0,26 aprox."             # sin plan: a la carta (×2)
    _abrir(base_temporal, libro, tope=0.20)
    e = _estimar_en_peticion("guion")
    assert e["texto"] == "Incluido en tu plan" and e["incluido"] is True and e["usd"] == 0.13
    assert _estimar_en_peticion("reescribir_idea")["texto"] == "Incluido en tu plan"
    assert _estimar_en_peticion("video", modelo="nada", duracion=5).get("incluido") is None   # lo caro, nunca
    gastos.registrar("acme", "guion", 0.10, "guion:1:t1")                           # quedan 0,10 de tope
    assert _estimar_en_peticion("guion")["texto"] == "US$ 0,16 aprox."             # 0,13 ya no cabe: miembro
    assert _estimar_en_peticion("regla_producto")["texto"] == "Incluido en tu plan"  # 0,01 sí cabe
    assert _estimar_en_peticion("guion", cliente="otro")["texto"] == "US$ 0,13 aprox."   # otro proyecto: costo


def test_la_etiqueta_no_aparece_en_un_proyecto_que_no_cobra(base_temporal, libro):
    libro.configurar("acme", usuario="admin", cobrar=False)
    _abrir(base_temporal, libro)
    assert _estimar_en_peticion("guion")["texto"] == "US$ 0,13 aprox."


def test_incluye_lee_una_vez_por_peticion(base_temporal, libro, planes, monkeypatch):
    import dashboard
    libro.configurar("acme", usuario="admin", cobrar=True)
    _abrir(base_temporal, libro)
    lecturas = []
    original = planes._leer_incluye
    monkeypatch.setattr(planes, "_leer_incluye", lambda c: lecturas.append(c) or original(c))
    with dashboard.app.test_request_context("/cliente/acme"):
        assert planes.incluye("acme", "guion", 0.13) and planes.incluye("acme", "ideas", 0.05)
    assert lecturas == ["acme"]

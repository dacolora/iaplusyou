"""Planes y suscripciones (spec planes 2026-10-09 §5.2, §5.4, §7): alta con una
fuente de Wompi, cobro de cada renovación, lo que dice Wompi de cada pago,
renovación periódica con gracia, cancelar, terminar, cambiar de tarjeta,
activación a mano y avisos. Wompi y la TRM son falsos; la base es real.

Lo que no se negocia: nunca dos cobros aprobados (ni pendientes) de una misma
renovación, ni dos periodos, ni dos movimientos `plan` de un periodo."""
import threading
import time

import pytest
import sqlalchemy as sa

T0 = "2026-10-09T10:00:00"
TRM = 4000.5
CENTAVOS_MES = 400_050_000          # ceil(1 000 × 4 000,5) × 100
ACEPTACION = {"acceptance_token": "eyJ.acepta.prueba", "personal_token": "eyJ.datos.prueba",
              "acepta_terminos": True, "acepta_datos": True, "autoriza_cobro": True}


class WompiFalso:
    """Wompi con la regla que importa: una referencia se usa una sola vez."""

    def __init__(self, wompi):
        self.wompi = wompi
        self.posts, self.usadas, self.txs, self.respuestas = [], set(), {}, {}
        self.defecto, self.error, self.espera, self.fuentes = "APPROVED", None, 0, []

    def crear_fuente(self, tipo, token, correo, acceptance_token, personal_token, tiempo=None):
        self.fuentes.append((tipo, token, correo, acceptance_token, personal_token))
        return {"id": 3891 + len(self.fuentes) - 1, "tipo": tipo, "resumen": "Visa ···4242"}

    def cobrar_fuente(self, fuente_id, centavos, correo, referencia, *, tipo="CARD", acceptance_token=None,
                      tiempo=None):
        self.posts.append({"fuente": fuente_id, "centavos": centavos, "correo": correo, "referencia": referencia,
                           "tipo": tipo, "acceptance_token": acceptance_token})
        if self.espera:
            time.sleep(self.espera)
        if self.error is not None:
            error, llego = self.error
            self.error = None
            if llego:
                self.usadas.add(referencia)
            raise error
        if referencia in self.usadas:
            raise self.wompi.ErrorWompi("usada", codigo=422, referencia_usada=True)
        self.usadas.add(referencia)
        tx = {"id": f"1292-{len(self.txs) + 1}-1", "reference": referencia, "amount_in_cents": centavos,
              "currency": "COP", "status": self.respuestas.get(referencia, self.defecto),
              "status_message": "Fondos insuficientes" if self.respuestas.get(referencia) == "DECLINED" else None,
              "payment_method_type": tipo, "payment_source_id": fuente_id}
        self.txs[tx["id"]] = tx
        return dict(tx)

    def transaccion(self, transaccion_id, tiempo=None):
        return dict(self.txs[transaccion_id])


@pytest.fixture()
def planes(base_temporal):
    from cobros import planes
    return planes


@pytest.fixture()
def falso(base_temporal, monkeypatch):
    from cobros import trm, wompi
    f = WompiFalso(wompi)
    monkeypatch.setattr(wompi, "configurado", lambda: True)
    monkeypatch.setattr(wompi, "crear_fuente", f.crear_fuente)
    monkeypatch.setattr(wompi, "cobrar_fuente", f.cobrar_fuente)
    monkeypatch.setattr(wompi, "transaccion", f.transaccion)
    monkeypatch.setattr(trm, "actual", lambda: TRM)
    return f


@pytest.fixture()
def avisos(monkeypatch):
    import idiomas
    import notificaciones
    enviados = []
    monkeypatch.setattr(idiomas, "de_proyecto", lambda cliente: "es")
    monkeypatch.setattr(notificaciones, "avisar",
                        lambda cliente, tipo, asunto, cuerpo: enviados.append((tipo, cliente, asunto, cuerpo)) or True)

    def admin(tipo, asunto, cuerpo, cliente=""):
        enviados.append(("admin:" + tipo, cliente, asunto() if callable(asunto) else asunto,
                         cuerpo() if callable(cuerpo) else cuerpo))
        return 1
    monkeypatch.setattr(notificaciones, "avisar_admin", admin)
    return enviados


def _tipos(enviados):
    return [e[0] for e in enviados]


@pytest.fixture()
def pro(planes):
    # Los proyectos de estas pruebas cobran: con «Cobrar» apagado la periódica no renueva (revisión final
    # 2026-10-10, test_con_cobrar_apagado_la_periodica_no_cobra_ni_abre_meses).
    from cobros import libro
    for cliente in ("acme", "otro"):
        libro.configurar(cliente, usuario="admin", cobrar=True)
    return planes.crear_plan("Pro", 1000, 1.25, 25, precio_anual_usd=10000, usuario="admin")


def _suscribir(planes, pro, ahora=T0, ciclo="mensual", cliente="acme", precio_visto=None):
    if precio_visto is None:
        precio_visto = 10000 if ciclo == "anual" else 1000
    return planes.suscribir(cliente, pro, ciclo, "CARD", "tok_prueba_4242", "pagos@acme.co", dict(ACEPTACION),
                            "user_acme", precio_visto, ahora=ahora)


def _envejecer(db):
    """El «en vuelo» de un pendiente se mide con el reloj de verdad: aquí lo hacemos viejo (como si el envío se
    hubiera cortado hace rato)."""
    with db.conectar() as con:
        con.execute(db.pago_plan.update().where(db.pago_plan.c.estado == "pendiente")
                    .values(actualizado_en="2000-01-01T00:00:00"))


def _filas(db, tabla, **filtro):
    t = getattr(db, tabla)
    q = sa.select(t).order_by(t.c.id)
    for k, v in filtro.items():
        q = q.where(getattr(t.c, k) == v)
    with db.conectar() as con:
        return con.execute(q).all()


def _sus(db):
    (s,) = _filas(db, "suscripcion")
    return s


def _antes(iso, minutos):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(iso) - timedelta(minutes=minutos)).isoformat(timespec="seconds")


def _despues(iso, minutos=0, horas=0, dias=0):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(iso) + timedelta(minutes=minutos, hours=horas, days=dias)).isoformat(
        timespec="seconds")


# ------------------------------------------------------------- meses ---

@pytest.mark.parametrize("desde,n,esperado", [
    ("2027-01-31T10:00:00", 1, "2027-02-28T10:00:00"),
    ("2028-01-31T10:00:00", 1, "2028-02-29T10:00:00"),
    ("2026-12-15T08:30:00", 1, "2027-01-15T08:30:00"),
    ("2026-10-09T10:00:00", 12, "2027-10-09T10:00:00"),
    ("2027-01-31T10:00:00", 2, "2027-03-31T10:00:00"),
])
def test_sumar_meses_de_calendario(planes, desde, n, esperado):
    assert planes.sumar_meses(desde, n) == esperado


# ------------------------------------------------------------- planes ---

def test_crear_editar_y_archivar_plan(planes):
    pid = planes.crear_plan("Pro", "1000", 1.25, 25, precio_anual_usd=10000, usuario="admin")
    assert planes.leer_plan(pid)["precio_usd"] == 1000
    planes.editar_plan(pid, usuario="admin", margen=1.5)
    assert planes.leer_plan(pid)["margen"] == 1.5 and planes.leer_plan(pid)["nombre"] == "Pro"
    assert [p["id"] for p in planes.listar()] == [pid]
    planes.archivar_plan(pid, "admin")
    assert planes.listar() == [] and len(planes.listar(activos=False)) == 1


@pytest.mark.parametrize("k", [
    {"precio_usd": 0}, {"precio_usd": 10.5}, {"precio_usd": True}, {"precio_usd": "mil"},
    {"margen": 0.9}, {"margen": 5.5}, {"margen": float("nan")}, {"tope_incluido_usd": -1},
    {"nombre": ""}, {"nombre": "x" * 61}, {"precio_anual_usd": 0},
])
def test_crear_plan_valida(planes, k):
    datos = {"nombre": "Pro", "precio_usd": 1000, "margen": 1.25, "tope_incluido_usd": 25, **k}
    with pytest.raises(planes.ErrorPlan):
        planes.crear_plan(datos.pop("nombre"), datos.pop("precio_usd"), datos.pop("margen"),
                          datos.pop("tope_incluido_usd"), usuario="admin", **datos)


# --------------------------------------------------------------- alta ---

def test_alta_aprobada_abre_el_periodo_y_acredita_la_bolsa(base_temporal, planes, pro, falso, avisos):
    from cobros import libro
    r = _suscribir(planes, pro)
    assert r["estado"] == "aprobado"
    (post,) = falso.posts
    assert post["centavos"] == CENTAVOS_MES and post["referencia"] == "pl-1-20261009-1"
    assert post["acceptance_token"] == ACEPTACION["acceptance_token"] and post["fuente"] == 3891
    (pago,) = _filas(base_temporal, "pago_plan")
    assert pago.estado == "aprobado" and pago.usd == 1000 and pago.trm == TRM and pago.transaccion_id
    (per,) = _filas(base_temporal, "periodo_plan")
    assert (per.inicio, per.fin, per.credito_milesimas, per.margen, per.pago_id) == (
        T0, "2026-11-09T10:00:00", 1_000_000, 1.25, pago.id)
    (mov,) = _filas(base_temporal, "movimiento_saldo", tipo="plan")
    assert mov.milesimas == 1_000_000 and mov.periodo_id == per.id
    assert libro.saldo("acme") == 1_000_000
    s = _sus(base_temporal)
    assert (s.estado, s.renovar, s.fuente_resumen, s.cubierto_hasta, s.proximo_cobro) == (
        "activa", True, "Visa ···4242", "2026-11-09T10:00:00", "2026-11-09T09:00:00")
    assert "plan_renovado" in _tipos(avisos)
    import json
    with base_temporal.conectar() as con:
        guardado = con.execute(sa.select(base_temporal.kv.c.valor)
                               .where(base_temporal.kv.c.clave == f"planes:aceptacion:{s.id}")).scalar()
    (acepta,) = json.loads(guardado)
    assert acepta["acceptance_token"] == ACEPTACION["acceptance_token"] and acepta["usuario"] == "user_acme"


def test_alta_rechazada_queda_terminada_sin_periodo_y_se_puede_reintentar(base_temporal, planes, pro, falso, avisos):
    falso.respuestas["pl-1-20261009-1"] = "DECLINED"
    r = _suscribir(planes, pro)
    assert r["estado"] == "rechazado" and r["motivo"] == "Fondos insuficientes"
    assert _sus(base_temporal).estado == "terminada"
    assert _filas(base_temporal, "periodo_plan") == []
    assert _filas(base_temporal, "movimiento_saldo", tipo="plan") == []
    r2 = _suscribir(planes, pro)
    assert r2["estado"] == "aprobado" and r2["suscripcion_id"] != r["suscripcion_id"]


def test_alta_exige_las_aceptaciones_y_un_solo_plan(base_temporal, planes, pro, falso, avisos):
    malas = ({}, {**ACEPTACION, "autoriza_cobro": False}, {**ACEPTACION, "personal_token": ""},
             {**ACEPTACION, "autoriza_cobro": "on"}, {**ACEPTACION, "acepta_terminos": 1},
             {k: v for k, v in ACEPTACION.items() if k != "acepta_datos"})
    for mala in malas:
        with pytest.raises(planes.ErrorPlan):
            planes.suscribir("acme", pro, "mensual", "CARD", "tok_x", "a@b.co", mala, "u", 1000, ahora=T0)
    _suscribir(planes, pro)
    with pytest.raises(planes.ErrorPlan):
        _suscribir(planes, pro)
    assert len(falso.fuentes) == 1   # el segundo intento ni siquiera crea otra fuente


def test_alta_pendiente_y_el_evento_aprobado_la_abre_una_sola_vez(base_temporal, planes, pro, falso, avisos):
    falso.defecto = "PENDING"
    r = _suscribir(planes, pro)
    assert r["estado"] == "pendiente"
    (pago,) = _filas(base_temporal, "pago_plan")
    assert pago.estado == "pendiente" and pago.transaccion_id
    assert _filas(base_temporal, "periodo_plan") == []
    tx = {**falso.txs[pago.transaccion_id], "status": "APPROVED"}
    assert planes.aplicar_transaccion(tx, ahora=_despues(T0, minutos=1)) == "aprobado"
    assert planes.aplicar_transaccion(tx, ahora=_despues(T0, minutos=2)) == "ya_aplicada"
    assert len(_filas(base_temporal, "periodo_plan")) == 1
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="plan")) == 1
    assert _filas(base_temporal, "pago_plan")[0].estado == "aprobado"
    # Un rechazo tardío de la misma transacción no deshace nada.
    assert planes.aplicar_transaccion({**tx, "status": "DECLINED"}) == "ya_aplicada"
    assert _sus(base_temporal).estado == "activa"


@pytest.mark.parametrize("cambio", [{"amount_in_cents": CENTAVOS_MES - 100}, {"currency": "USD"},
                                    {"id": "otra-transaccion"}])
def test_aplicar_una_transaccion_que_no_cuadra_no_toca_nada(base_temporal, planes, pro, falso, avisos, cambio):
    falso.defecto = "PENDING"
    _suscribir(planes, pro)
    (pago,) = _filas(base_temporal, "pago_plan")
    tx = {**falso.txs[pago.transaccion_id], "status": "APPROVED", **cambio}
    assert planes.aplicar_transaccion(tx) == "no_cuadra"
    assert _filas(base_temporal, "pago_plan")[0].estado == "pendiente"
    assert _filas(base_temporal, "periodo_plan") == []
    assert "admin:plan_admin" in _tipos(avisos)


def test_aplicar_una_referencia_ajena(planes, base_temporal):
    assert planes.aplicar_transaccion({"reference": "cv-1-1", "status": "APPROVED"}) == "desconocida"
    assert planes.aplicar_transaccion({"reference": "pl-99-20261009-1", "status": "APPROVED",
                                       "amount_in_cents": 1, "currency": "COP"}) == "desconocida"


# ---------------------------------------------------------- renovación ---

def test_renovacion_se_cobra_antes_y_el_periodo_nuevo_abre_al_cerrar_el_viejo(base_temporal, planes, pro, falso,
                                                                              avisos):
    from cobros import libro
    _suscribir(planes, pro)
    fin = "2026-11-09T10:00:00"
    r = planes.renovar_todo(ahora=_antes(fin, 30))
    assert r["cobros"].get("aprobado") == 1
    assert [p["referencia"] for p in falso.posts] == ["pl-1-20261009-1", "pl-1-20261109-1"]
    assert falso.posts[1]["acceptance_token"] is None
    s = _sus(base_temporal)
    assert s.cubierto_hasta == "2026-12-09T10:00:00" and s.estado == "activa"
    periodos = _filas(base_temporal, "periodo_plan")
    assert [(p.inicio, p.fin) for p in periodos] == [(T0, fin), (fin, "2026-12-09T10:00:00")]
    # Al vencer: cierra el viejo (vence lo que sobró) y el nuevo ya está abierto, sin cobrar de nuevo.
    r = planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert r["cerrados"] == 1 and r["cobros"].get("no_toca") == 1
    (venc,) = _filas(base_temporal, "movimiento_saldo", tipo="vencimiento")
    assert venc.milesimas == -1_000_000 and venc.periodo_id == periodos[0].id
    assert planes.periodo_abierto(None, "acme", ahora=_despues(fin, minutos=1))["id"] == periodos[1].id
    assert libro.saldo("acme") == 1_000_000
    assert len(falso.posts) == 2
    assert len(_filas(base_temporal, "pago_plan", estado="aprobado")) == 2


def test_renovacion_tarde_abre_desde_el_cobro(base_temporal, planes, pro, falso, avisos):
    """El worker estuvo apagado: al volver cierra, cobra y abre desde ese momento."""
    _suscribir(planes, pro)
    tarde = "2026-11-10T15:00:00"
    planes.renovar_todo(ahora=tarde)
    periodos = _filas(base_temporal, "periodo_plan")
    assert periodos[0].cerrado and (periodos[1].inicio, periodos[1].fin) == (tarde, "2026-12-10T15:00:00")
    assert _sus(base_temporal).cubierto_hasta == "2026-12-10T15:00:00"


def test_dos_renovaciones_a_la_vez_cobran_una_sola_vez(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    falso.espera = 0.4
    ahora = _antes("2026-11-09T10:00:00", 30)
    errores = []

    def correr():
        try:
            planes.renovar_todo(ahora=ahora)
        except Exception as e:  # noqa: BLE001
            errores.append(e)
    hilos = [threading.Thread(target=correr) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []
    assert [p["referencia"] for p in falso.posts] == ["pl-1-20261009-1", "pl-1-20261109-1"]
    assert len(_filas(base_temporal, "pago_plan")) == 2
    assert len(_filas(base_temporal, "periodo_plan")) == 2
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="plan")) == 2


def test_evento_y_periodica_a_la_vez_aplican_una_sola_vez(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    falso.defecto = "PENDING"
    ahora = _antes("2026-11-09T10:00:00", 30)
    planes.renovar_todo(ahora=ahora)
    pago = _filas(base_temporal, "pago_plan", estado="pendiente")[0]
    falso.txs[pago.transaccion_id]["status"] = "APPROVED"       # Wompi ya lo aprobó
    tx = dict(falso.txs[pago.transaccion_id])
    salida, barrera = [], threading.Barrier(2)

    def evento():
        barrera.wait()
        salida.append(planes.aplicar_transaccion(tx, ahora=_despues(ahora, minutos=5)))

    def periodica():
        barrera.wait()
        planes.renovar_todo(ahora=_despues(ahora, minutos=5))
    hilos = [threading.Thread(target=evento), threading.Thread(target=periodica)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(_filas(base_temporal, "pago_plan", estado="aprobado")) == 2
    assert len(_filas(base_temporal, "periodo_plan")) == 2
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="plan")) == 2
    assert len(falso.posts) == 2
    assert _sus(base_temporal).cubierto_hasta == "2026-12-09T10:00:00"   # extendido una sola vez


def test_decidir_el_cobro_toma_el_candado_antes_de_leer(base_temporal, planes, pro, falso, avisos, escritor_en_medio):
    _suscribir(planes, pro)
    otro = escritor_en_medio(
        "referencia LIKE",   # la lectura de los pagos de la renovación (la previa sin candado solo evita leer la TRM)
        "insert into pago_plan(cliente, suscripcion_id, ciclo, usd, referencia, estado, medio, monto_cop_centavos) "
        f"values ('acme', 1, 'mensual', 1000, 'pl-1-20261109-9', 'pendiente', 'wompi', {CENTAVOS_MES})")
    planes.cobrar_periodo(1, ahora=_antes("2026-11-09T10:00:00", 30))
    assert otro["resultado"].startswith("bloqueado")
    assert [p.referencia for p in _filas(base_temporal, "pago_plan")] == ["pl-1-20261009-1", "pl-1-20261109-1"]


def test_cobro_incierto_se_reintenta_con_la_misma_referencia(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    ahora = _antes("2026-11-09T10:00:00", 30)
    falso.error = (falso.wompi.ErrorWompi("cortado", caida=True, incierto=True), True)   # llegó y se cortó
    assert planes.cobrar_periodo(1, ahora=ahora) == "caida"
    pendiente = _filas(base_temporal, "pago_plan", estado="pendiente")[0]
    assert pendiente.referencia == "pl-1-20261109-1" and pendiente.transaccion_id is None
    # Al minuto: otro hilo podría estar cobrando todavía; no se reintenta encima.
    assert planes.cobrar_periodo(1, ahora=_despues(ahora, minutos=1)) == "en_curso"
    # Después: se reintenta con la MISMA referencia; Wompi dice que ya se usó → sigue pendiente y el admin lo sabe.
    _envejecer(base_temporal)
    assert planes.cobrar_periodo(1, ahora=_despues(ahora, minutos=5)) == "incierto"
    _envejecer(base_temporal)
    assert planes.cobrar_periodo(1, ahora=_despues(ahora, minutos=10)) == "incierto"
    assert [p["referencia"] for p in falso.posts[1:]] == ["pl-1-20261109-1"] * 3
    assert len(_filas(base_temporal, "pago_plan")) == 2
    assert _tipos(avisos).count("admin:plan_admin") == 1
    # El evento de esa transacción llega y la aplica.
    tx = {"id": "1292-99-1", "reference": "pl-1-20261109-1", "status": "APPROVED",
          "amount_in_cents": CENTAVOS_MES, "currency": "COP"}
    assert planes.aplicar_transaccion(tx, ahora=_despues(ahora, minutos=12)) == "aprobado"
    assert _filas(base_temporal, "pago_plan")[1].transaccion_id == "1292-99-1"
    assert planes.cobrar_periodo(1, ahora=_despues(ahora, minutos=20)) == "no_toca"


def test_cobro_que_no_salio_se_reintenta_con_la_misma_referencia_y_cobra(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    ahora = _antes("2026-11-09T10:00:00", 30)
    falso.error = (falso.wompi.ErrorWompi("sin red", caida=True), False)   # no llegó a conectar
    assert planes.cobrar_periodo(1, ahora=ahora) == "caida"
    assert _filas(base_temporal, "pago_plan")[1].motivo == planes.MOTIVO_NO_SALIO
    assert planes.cobrar_periodo(1, ahora=_despues(ahora, minutos=1)) == "en_curso"
    _envejecer(base_temporal)
    assert planes.cobrar_periodo(1, ahora=_despues(ahora, minutos=5)) == "aprobado"
    assert [p["referencia"] for p in falso.posts[1:]] == ["pl-1-20261109-1"] * 2
    assert len(_filas(base_temporal, "pago_plan", estado="aprobado")) == 2


def test_un_4xx_del_primer_envio_cuenta_como_intento(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    falso.error = (falso.wompi.ErrorWompi("fuente vencida", codigo=422), False)
    assert planes.cobrar_periodo(1, ahora=_antes("2026-11-09T10:00:00", 30)) == "error"
    s = _sus(base_temporal)
    assert s.estado == "morosa" and s.intentos_fallidos == 1


# --------------------------------------------------------------- gracia ---

def test_gracia_tres_intentos_y_termina(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    for i in (1, 2, 3):
        falso.respuestas[f"pl-1-20261109-{i}"] = "DECLINED"
    fin = "2026-11-09T10:00:00"
    planes.renovar_todo(ahora=_antes(fin, 30))
    s = _sus(base_temporal)
    assert (s.estado, s.intentos_fallidos, s.proximo_cobro) == ("morosa", 1, _despues(fin, minutos=-30, horas=24))
    # Al vencer: sin periodo abierto mientras está morosa, y no se cobra antes de las 24 h.
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert planes.periodo_abierto(None, "acme", ahora=_despues(fin, minutos=1)) is None
    assert len(falso.posts) == 2
    planes.renovar_todo(ahora=_despues(fin, horas=24))
    assert _sus(base_temporal).intentos_fallidos == 2 and _sus(base_temporal).estado == "morosa"
    planes.renovar_todo(ahora=_despues(fin, horas=48))
    s = _sus(base_temporal)
    assert s.estado == "terminada" and s.intentos_fallidos == 3
    assert [p["referencia"] for p in falso.posts[1:]] == ["pl-1-20261109-1", "pl-1-20261109-2", "pl-1-20261109-3"]
    planes.renovar_todo(ahora=_despues(fin, horas=96))
    assert len(falso.posts) == 4
    tipos = _tipos(avisos)
    assert tipos.count("plan_rechazado") == 2 and "plan_terminado" in tipos and "admin:plan_terminado" in tipos
    assert "Fondos insuficientes" in [e for e in avisos if e[0] == "plan_rechazado"][0][3]


def test_pago_en_el_segundo_intento_abre_desde_ese_momento(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    falso.respuestas["pl-1-20261109-1"] = "DECLINED"
    fin = "2026-11-09T10:00:00"
    planes.renovar_todo(ahora=_antes(fin, 30))
    segundo = _despues(fin, minutos=-30, horas=24)
    planes.renovar_todo(ahora=segundo)
    s = _sus(base_temporal)
    assert (s.estado, s.intentos_fallidos, s.cubierto_hasta) == ("activa", 0, "2026-12-10T09:30:00")
    nuevo = _filas(base_temporal, "periodo_plan")[-1]
    assert (nuevo.inicio, nuevo.fin) == (segundo, "2026-12-10T09:30:00")


def test_cambiar_tarjeta_en_morosa_cobra_en_el_acto(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    falso.respuestas["pl-1-20261109-1"] = "DECLINED"
    fin = "2026-11-09T10:00:00"
    planes.renovar_todo(ahora=_antes(fin, 30))
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    r = planes.cambiar_fuente("acme", "CARD", "tok_otra", "pagos@acme.co", dict(ACEPTACION), "user_acme",
                              ahora=_despues(fin, horas=2))
    assert r == {"estado": "activa", "cobro": "aprobado"}
    s = _sus(base_temporal)
    assert s.fuente_pago_id == "3892" and s.intentos_fallidos == 0
    assert falso.posts[-1]["fuente"] == 3892 and falso.posts[-1]["referencia"] == "pl-1-20261109-2"
    assert planes.periodo_abierto(None, "acme", ahora=_despues(fin, horas=3)) is not None


def test_cambiar_tarjeta_sin_mora_no_cobra(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    r = planes.cambiar_fuente("acme", "CARD", "tok_otra", "pagos@acme.co", dict(ACEPTACION), "user_acme",
                              ahora=_despues(T0, dias=3))
    assert r["cobro"] is None and len(falso.posts) == 1
    assert _sus(base_temporal).proximo_cobro == "2026-11-09T09:00:00"


# ------------------------------------------------------------- cancelar ---

def test_cancelar_mantiene_hasta_el_fin_y_despues_termina(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    r = planes.cancelar("acme", "user_acme", ahora=_despues(T0, dias=10))
    assert r == {"estado": "cancelada", "termina_el": "2026-11-09T10:00:00"}
    fin = "2026-11-09T10:00:00"
    assert planes.periodo_abierto(None, "acme", ahora=_antes(fin, 30)) is not None
    planes.renovar_todo(ahora=_antes(fin, 30))
    assert len(falso.posts) == 1
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert _sus(base_temporal).estado == "terminada"
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="vencimiento")) == 1
    assert len(falso.posts) == 1


def test_terminar_ya_vence_la_bolsa(base_temporal, planes, pro, falso, avisos):
    from cobros import libro
    _suscribir(planes, pro)
    planes.terminar_ya("acme", "admin", "pidió salir", ahora=_despues(T0, dias=2))
    assert _sus(base_temporal).estado == "terminada"
    assert _filas(base_temporal, "periodo_plan")[0].cerrado
    assert libro.saldo("acme") == 0
    assert "admin:plan_terminado" in _tipos(avisos)


# ------------------------------------------------------------------ anual ---

def test_anual_un_pago_y_doce_periodos_sin_cobrar(base_temporal, planes, pro, falso, avisos):
    inicio = "2027-01-31T10:00:00"
    r = _suscribir(planes, pro, ahora=inicio, ciclo="anual")
    assert r["estado"] == "aprobado"
    assert falso.posts[0]["centavos"] == 40_005_000 * 100
    assert _sus(base_temporal).cubierto_hasta == "2028-01-31T10:00:00"
    for mes in range(1, 12):
        frontera = planes.sumar_meses(inicio, mes)
        planes.renovar_todo(ahora=_antes(frontera, 20))
        planes.renovar_todo(ahora=_despues(frontera, minutos=1))
    periodos = _filas(base_temporal, "periodo_plan")
    assert len(periodos) == 12 and len(falso.posts) == 1
    assert [p.inicio for p in periodos[:4]] == [inicio, "2027-02-28T10:00:00", "2027-03-31T10:00:00",
                                                 "2027-04-30T10:00:00"]
    assert all(a.fin == b.inicio for a, b in zip(periodos, periodos[1:]))
    assert periodos[-1].fin == "2028-01-31T10:00:00"
    assert {p.pago_id for p in periodos} == {_filas(base_temporal, "pago_plan")[0].id}
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="plan")) == 12
    assert all(p.credito_milesimas == 1_000_000 for p in periodos)
    # Al acabar el año: se cobra el anual otra vez.
    planes.renovar_todo(ahora=_antes("2028-01-31T10:00:00", 30))
    assert [p["referencia"] for p in falso.posts] == ["pl-1-20270131-1", "pl-1-20280131-1"]


# ------------------------------------------------------------ a mano ---

def test_activacion_manual_sin_tarjeta(base_temporal, planes, pro, falso, avisos):
    from cobros import libro
    r = planes.activar_manual("acme", pro, "mensual", "admin", "transferencia 123", ahora=T0)
    (pago,) = _filas(base_temporal, "pago_plan")
    assert (pago.medio, pago.estado, pago.usd, pago.motivo) == ("manual", "aprobado", 1000, "transferencia 123")
    assert r["periodo_id"] and libro.saldo("acme") == 1_000_000
    s = _sus(base_temporal)
    assert (s.estado, s.renovar, s.fuente_pago_id, s.proximo_cobro) == ("activa", False, None, None)
    fin = "2026-11-09T10:00:00"
    planes.renovar_todo(ahora=_despues(fin, dias=-2))
    aviso = [e for e in avisos if e[0] == "plan_por_renovar"]
    assert len(aviso) == 1 and "termina" in aviso[0][2]
    planes.renovar_todo(ahora=_antes(fin, 30))
    assert falso.posts == []
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert _sus(base_temporal).estado == "terminada"


def test_activacion_manual_por_adelantado_extiende_desde_el_fin(base_temporal, planes, pro, falso, avisos):
    planes.activar_manual("acme", pro, "mensual", "admin", "mes 1", ahora=T0)
    planes.activar_manual("acme", pro, "mensual", "admin", "mes 2", ahora=_despues(T0, dias=20))
    assert _sus(base_temporal).cubierto_hasta == "2026-12-09T10:00:00"
    assert len(_filas(base_temporal, "periodo_plan")) == 1   # el segundo abre cuando empiece
    fin = "2026-11-09T10:00:00"
    planes.renovar_todo(ahora=_antes(fin, 20))
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    periodos = _filas(base_temporal, "periodo_plan")
    assert [(p.inicio, p.fin) for p in periodos] == [(T0, fin), (fin, "2026-12-09T10:00:00")]
    assert periodos[1].pago_id == _filas(base_temporal, "pago_plan")[1].id
    assert _sus(base_temporal).estado == "activa"


# ------------------------------------------------------------- avisos ---

def test_aviso_tres_dias_antes_una_sola_vez(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    planes.renovar_todo(ahora="2026-11-05T10:00:00")
    assert "plan_por_renovar" not in _tipos(avisos)
    planes.renovar_todo(ahora="2026-11-06T11:00:00")
    planes.renovar_todo(ahora="2026-11-07T11:00:00")
    aviso = [e for e in avisos if e[0] == "plan_por_renovar"]
    assert len(aviso) == 1 and "renueva" in aviso[0][2] and "1.000" in aviso[0][3]
    assert "9 de noviembre de 2026 a las 09:00" in aviso[0][3]      # el momento del cobro, no el fin (10:00)
    assert "antes de esa fecha no se acumula" in aviso[0][3]


def test_aviso_de_la_bolsa_al_80_una_vez_por_periodo(base_temporal, planes, pro, falso, avisos):
    import db as db_
    planes.activar_manual("acme", pro, "mensual", "admin", "")   # periodo alrededor de ahora (los cobros llevan la hora real)
    with db_.conectar() as con:
        con.execute(db_.movimiento_saldo.insert().values(cliente="acme", creado_en=db_.ahora(), tipo="cobro",
                                                         milesimas=-850_000, concepto="video", extra={"margen": 1.25}))
    planes.renovar_todo()
    planes.renovar_todo()
    assert _tipos(avisos).count("plan_bolsa") == 1
    estado = planes.estado_cliente("acme")
    assert estado["bolsa"]["restante"] == 150_000 and estado["bolsa"]["usado_pct"] == 85
    assert estado["incluido_pct"] == 0
    # A la carta (margen global 2,0) habría costado 850 000 × 2 / 1,25 = 1 360 000: ahorró 510 000.
    assert estado["ahorro_milesimas"] == 510_000


# ------------------------------------------------------- la periódica ---

def test_la_periodica_esta_registrada_y_exenta():
    import tareas
    import worker
    from tareas import planes as tareas_planes  # noqa: F401
    assert ("planes_renovar", 1800) in worker.PERIODICAS
    assert "planes_renovar" in tareas.REGISTRO
    assert "Wompi" in tareas.TIPOS_EXENTOS_DE_COBRO["planes_renovar"]
    assert "planes_renovar" not in tareas.TIPOS_QUE_COBRAN


def test_estado_cliente_sin_plan(planes):
    assert planes.estado_cliente("acme")["suscripcion"] is None


# ----------------------------------------------- revisión 1 (dinero) ---

def test_cancelar_tras_una_caida_en_el_alta_no_cobra(base_temporal, planes, pro, falso, avisos):
    """C1: el primer cobro no salió (no conectó); cancelar antes del reintento → nunca se reenvía."""
    falso.error = (falso.wompi.ErrorWompi("sin red", caida=True), False)
    assert _suscribir(planes, pro)["estado"] == "caida"
    planes.cancelar("acme", "user_acme", ahora=_despues(T0, minutos=1))
    assert _sus(base_temporal).estado == "cancelada"
    _envejecer(base_temporal)
    planes.renovar_todo(ahora=_despues(T0, minutos=10))
    planes.renovar_todo(ahora=_despues(T0, minutos=40))
    assert len(falso.posts) == 1
    (pago,) = _filas(base_temporal, "pago_plan")
    assert pago.estado == "error" and pago.motivo != planes.MOTIVO_NO_SALIO
    assert _filas(base_temporal, "pago_plan", estado="aprobado") == []
    assert _sus(base_temporal).estado == "terminada"
    assert _filas(base_temporal, "periodo_plan") == []


def test_renovacion_caida_y_cancelada_no_se_reenvia(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    fin = "2026-11-09T10:00:00"
    falso.error = (falso.wompi.ErrorWompi("sin red", caida=True), False)
    planes.renovar_todo(ahora=_antes(fin, 30))
    planes.cancelar("acme", "user_acme", ahora=_antes(fin, 20))
    _envejecer(base_temporal)
    planes.renovar_todo(ahora=_antes(fin, 10))
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert [p["referencia"] for p in falso.posts] == ["pl-1-20261009-1", "pl-1-20261109-1"]
    assert [p.estado for p in _filas(base_temporal, "pago_plan")] == ["aprobado", "error"]
    assert _sus(base_temporal).estado == "terminada"


def test_un_cobro_incierto_nunca_se_reenvia_tras_cancelar(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    fin = "2026-11-09T10:00:00"
    falso.error = (falso.wompi.ErrorWompi("cortado", caida=True, incierto=True), True)
    planes.renovar_todo(ahora=_antes(fin, 30))
    planes.cancelar("acme", "user_acme", ahora=_antes(fin, 25))
    _envejecer(base_temporal)
    planes.renovar_todo(ahora=_antes(fin, 10))
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert len(falso.posts) == 2                                   # ni un reenvío
    assert _filas(base_temporal, "pago_plan")[1].estado == "pendiente"
    assert _sus(base_temporal).estado == "cancelada"               # espera el evento: no termina con un cobro en el aire
    assert _tipos(avisos).count("admin:plan_admin") == 1
    # Llega el evento: sí se cobró, y lo pagado vale aunque esté cancelada.
    tx = {"id": "1292-77-1", "reference": "pl-1-20261109-1", "status": "APPROVED",
          "amount_in_cents": CENTAVOS_MES, "currency": "COP"}
    assert planes.aplicar_transaccion(tx, ahora=_despues(fin, minutos=5)) == "aprobado"
    s = _sus(base_temporal)
    assert s.estado == "cancelada" and s.cubierto_hasta == "2026-12-09T10:05:00"


def test_la_renovacion_cobra_el_precio_aceptado_no_el_del_plan(base_temporal, planes, pro, falso, avisos):
    """I1: el admin sube el plan; quien ya está suscrito sigue pagando lo que aceptó (y su bolsa es esa)."""
    _suscribir(planes, pro)
    s = _sus(base_temporal)
    assert (s.precio_usd, s.precio_anual_usd) == (1000, 10000)
    planes.editar_plan(pro, usuario="admin", precio_usd=1500, precio_anual_usd=15000)
    planes.renovar_todo(ahora="2026-11-06T10:30:00")
    aviso = [e for e in avisos if e[0] == "plan_por_renovar"]
    assert "1.000" in aviso[0][3] and "1.500" not in aviso[0][3]
    planes.renovar_todo(ahora=_antes("2026-11-09T10:00:00", 30))
    assert falso.posts[-1]["centavos"] == CENTAVOS_MES
    assert _filas(base_temporal, "pago_plan")[-1].usd == 1000
    assert _filas(base_temporal, "periodo_plan")[-1].credito_milesimas == 1_000_000
    assert planes.estado_cliente("acme", ahora=T0)["monto_renovacion_usd"] == 1000


@pytest.mark.parametrize("ciclo,visto", [("mensual", 900), ("mensual", 10000), ("anual", 1000), ("mensual", None),
                                         ("mensual", "mil"), ("mensual", True), ("mensual", "1000"),
                                         ("mensual", " 1000 "), ("mensual", 1000.9), ("mensual", 1000.0)])
def test_alta_con_un_precio_que_ya_no_es_el_del_plan_se_niega(base_temporal, planes, pro, falso, avisos, ciclo, visto):
    with pytest.raises(planes.ErrorPlan) as e:
        planes.suscribir("acme", pro, ciclo, "CARD", "tok_x", "pagos@acme.co", dict(ACEPTACION), "u", visto, ahora=T0)
    assert "cambió" in str(e.value)
    assert falso.fuentes == [] and falso.posts == []
    assert _filas(base_temporal, "suscripcion") == []


def test_alta_guarda_el_precio_y_el_ciclo_aceptados_como_evidencia(base_temporal, planes, pro, falso, avisos):
    import json
    _suscribir(planes, pro, ciclo="anual")
    with base_temporal.conectar() as con:
        (acepta,) = json.loads(con.execute(sa.select(base_temporal.kv.c.valor)
                                           .where(base_temporal.kv.c.clave == "planes:aceptacion:1")).scalar())
    assert (acepta["usd"], acepta["ciclo"]) == (10000, "anual")
    assert acepta["acepta_terminos"] is True and acepta["acepta_datos"] is True and acepta["autoriza_cobro"] is True


def test_un_plan_editado_mientras_se_crea_la_fuente_se_niega(base_temporal, planes, pro, falso, avisos, monkeypatch):
    original = falso.crear_fuente

    def crear_y_editar(*a, **k):
        r = original(*a, **k)
        planes.editar_plan(pro, usuario="admin", precio_usd=1500)
        return r
    monkeypatch.setattr(falso.wompi, "crear_fuente", crear_y_editar)
    with pytest.raises(planes.ErrorPlan):
        _suscribir(planes, pro)
    assert falso.posts == [] and _filas(base_temporal, "suscripcion") == []


def test_activacion_manual_lleva_su_propio_precio(base_temporal, planes, pro, falso, avisos):
    """Revisión 2: el pago a mano guarda el precio de hoy del plan (su foto); sin tarjeta, nada aceptado que guardar."""
    planes.activar_manual("acme", pro, "mensual", "admin", "mes 1", ahora=T0)
    s = _sus(base_temporal)
    assert (s.precio_usd, s.precio_anual_usd, s.renovar) == (None, None, False)
    planes.editar_plan(pro, usuario="admin", precio_usd=1500)
    planes.activar_manual("acme", pro, "mensual", "admin", "mes 2", ahora=_despues(T0, dias=20))
    assert [p.usd for p in _filas(base_temporal, "pago_plan")] == [1000, 1500]


def test_un_anual_anulado_no_abre_mas_meses(base_temporal, planes, pro, falso, avisos):
    """I2: tras anular el pago anual, el mes en curso sigue pero no se abre ni uno más."""
    inicio = "2027-01-31T10:00:00"
    _suscribir(planes, pro, ahora=inicio, ciclo="anual")
    tx = {**falso.txs["1292-1-1"], "status": "VOIDED"}
    assert planes.aplicar_transaccion(tx, ahora=_despues(inicio, dias=1)) == "anulado"
    for mes in range(1, 4):
        frontera = planes.sumar_meses(inicio, mes)
        planes.renovar_todo(ahora=_antes(frontera, 20))
        planes.renovar_todo(ahora=_despues(frontera, minutos=1))
    assert len(_filas(base_temporal, "periodo_plan")) == 1
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="plan")) == 1
    assert _sus(base_temporal).cubierto_hasta == "2028-01-31T10:00:00"   # queda como estaba; el admin decide
    assert any(e[0] == "admin:plan_admin" and "anuló" in e[3] for e in avisos)
    assert len(falso.posts) == 1


def test_un_aprobado_de_un_pago_ya_rechazado_no_acredita(base_temporal, planes, pro, falso, avisos):
    """I3: el 2.º intento ya se cobró y abrió el periodo; un APPROVED tardío del 1.º no vuelve a acreditar."""
    _suscribir(planes, pro)
    falso.respuestas["pl-1-20261109-1"] = "DECLINED"
    planes.cobrar_periodo(1, ahora=_antes("2026-11-09T10:00:00", 30))
    planes.cobrar_periodo(1, ahora=_despues("2026-11-09T10:00:00", horas=24))
    cubierto = _sus(base_temporal).cubierto_hasta
    tx = [t for t in falso.txs.values() if t["reference"] == "pl-1-20261109-1"][0]
    assert planes.aplicar_transaccion({**tx, "status": "APPROVED"}) == "aprobado_tras_final"
    assert [p.estado for p in _filas(base_temporal, "pago_plan")] == ["aprobado", "rechazado", "aprobado"]
    assert _sus(base_temporal).cubierto_hasta == cubierto
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="plan")) == 2
    assert any(e[0] == "admin:plan_admin" and "No se acreditó" in e[3] for e in avisos)


def test_un_rechazo_forzado_no_corre_la_gracia_mas_alla_de_48_horas(base_temporal, planes, pro, falso, avisos):
    """M5: primer rechazo en T; un cambio de tarjeta rechazado en T+40 h deja el último intento en T+48 h."""
    _suscribir(planes, pro)
    for i in (1, 2):
        falso.respuestas[f"pl-1-20261109-{i}"] = "DECLINED"
    t = _antes("2026-11-09T10:00:00", 30)
    planes.renovar_todo(ahora=t)
    planes.cambiar_fuente("acme", "CARD", "tok_otra", "pagos@acme.co", dict(ACEPTACION), "user_acme",
                          ahora=_despues(t, horas=40))
    s = _sus(base_temporal)
    assert (s.estado, s.intentos_fallidos, s.proximo_cobro) == ("morosa", 2, _despues(t, horas=48))
    aviso = [e for e in avisos if e[0] == "plan_rechazado"][-1]
    assert "miércoles 11 de noviembre" in aviso[3]      # el límite sigue siendo T + 48 h


def test_una_suscripcion_que_falla_no_frena_las_demas(base_temporal, planes, pro, falso, avisos, monkeypatch):
    """M3."""
    _suscribir(planes, pro, cliente="otro")
    _suscribir(planes, pro, cliente="acme")
    original = planes.cobrar_periodo

    def falla_para_la_primera(sid, **k):
        if sid == 1:
            raise RuntimeError("base ocupada")
        return original(sid, **k)
    monkeypatch.setattr(planes, "cobrar_periodo", falla_para_la_primera)
    r = planes.renovar_todo(ahora=_antes("2026-11-09T10:00:00", 30))
    assert r["fallos"] == 1 and r["cobros"].get("aprobado") == 1


def test_la_renovacion_normal_no_deja_advertencias(base_temporal, planes, pro, falso, avisos, caplog):
    """M2: la hora antes de cobrar no es una anomalía."""
    import logging
    _suscribir(planes, pro)
    fin = "2026-11-09T10:00:00"
    with caplog.at_level(logging.WARNING, logger="cobros.planes"):
        planes.renovar_todo(ahora=_antes(fin, 59))
        planes.renovar_todo(ahora=_antes(fin, 30))
        planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert [r for r in caplog.records if r.name == "cobros.planes"] == []


def test_un_pendiente_nuevo_lleva_la_hora_real(base_temporal, planes, pro, falso, avisos):
    """M1: la vuelta de la periódica usa un `ahora` fijo; el pendiente y su reclamo, el reloj de verdad."""
    import db as db_
    falso.defecto = "PENDING"
    _suscribir(planes, pro, ahora="2026-01-01T00:00:00")
    (pago,) = _filas(base_temporal, "pago_plan")
    assert pago.creado_en[:10] == db_.ahora()[:10]


def test_un_mensual_anulado_no_se_renueva(base_temporal, planes, pro, falso, avisos):
    """Ruling: tras una anulación (o contracargo) no se vuelve a cobrar la tarjeta sola."""
    _suscribir(planes, pro)
    tx = {**falso.txs["1292-1-1"], "status": "VOIDED"}
    assert planes.aplicar_transaccion(tx, ahora=_despues(T0, dias=3)) == "anulado"
    s = _sus(base_temporal)
    assert (s.renovar, s.proximo_cobro, s.cubierto_hasta) == (False, None, "2026-11-09T10:00:00")
    fin = "2026-11-09T10:00:00"
    planes.renovar_todo(ahora=_antes(fin, 30))
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert len(falso.posts) == 1
    assert _sus(base_temporal).estado == "terminada"
    assert any(e[0] == "admin:plan_admin" and "detenida" in e[3] for e in avisos)


def test_un_anual_anulado_no_se_cobra_al_cumplir_el_año(base_temporal, planes, pro, falso, avisos):
    inicio = "2027-01-31T10:00:00"
    _suscribir(planes, pro, ahora=inicio, ciclo="anual")
    tx = {**falso.txs["1292-1-1"], "status": "VOIDED"}
    planes.aplicar_transaccion(tx, ahora=_despues(inicio, dias=1))
    fin = "2028-01-31T10:00:00"
    planes.renovar_todo(ahora=_antes(fin, 30))
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert len(falso.posts) == 1
    assert len(_filas(base_temporal, "periodo_plan")) == 1
    assert _sus(base_temporal).estado == "terminada"



# ----------------------------------------------- revisión 2 (dinero) ---

def test_activacion_manual_anual_sobre_tarjeta_mensual_no_cobra_la_tarjeta(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    planes.activar_manual("acme", pro, "anual", "admin", "transferencia", ahora=_despues(T0, dias=1))
    s = _sus(base_temporal)
    assert (s.renovar, s.proximo_cobro, s.ciclo, s.precio_usd, s.precio_anual_usd) == (
        False, None, "mensual", 1000, 10000)
    assert s.cubierto_hasta == "2027-11-09T10:00:00"
    assert _filas(base_temporal, "pago_plan")[-1].usd == 10000
    for antes in (30, 0):
        planes.renovar_todo(ahora=_antes(s.cubierto_hasta, antes))
    planes.renovar_todo(ahora=_despues(s.cubierto_hasta, minutos=1))
    assert len(falso.posts) == 1
    assert _sus(base_temporal).estado == "terminada"
    tipos = _tipos(avisos)
    assert any(e[0] == "plan_renovado" and "apagada" in e[2] for e in avisos) and "admin:plan_admin" in tipos


def test_activacion_manual_de_otro_plan_no_cobra_la_tarjeta(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    max_ = planes.crear_plan("Max", 3000, 1.5, 40, usuario="admin")
    planes.activar_manual("acme", max_, "mensual", "admin", "transferencia", ahora=_despues(T0, dias=1))
    s = _sus(base_temporal)
    assert (s.plan_id, s.precio_usd, s.renovar) == (max_, 1000, False)
    planes.renovar_todo(ahora=_antes(s.cubierto_hasta, 30))
    planes.renovar_todo(ahora=_despues("2026-11-09T10:00:00", minutos=1))   # abre el mes pagado a mano
    nuevo = _filas(base_temporal, "periodo_plan")[-1]
    assert (nuevo.credito_milesimas, nuevo.margen, nuevo.tope_incluido_usd) == (3_000_000, 1.5, 40)
    planes.renovar_todo(ahora=_despues(s.cubierto_hasta, minutos=1))
    assert len(falso.posts) == 1


def test_anulado_y_cambio_de_tarjeta_no_vuelve_a_cobrar(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    planes.aplicar_transaccion({**falso.txs["1292-1-1"], "status": "VOIDED"}, ahora=_despues(T0, dias=1))
    assert (_sus(base_temporal).estado, _sus(base_temporal).renovar) == ("cancelada", False)
    r = planes.cambiar_fuente("acme", "CARD", "tok2", "pagos@acme.co", dict(ACEPTACION), "user_acme",
                              ahora=_despues(T0, dias=2))
    assert r == {"estado": "cancelada", "cobro": None}
    s = _sus(base_temporal)
    assert (s.renovar, s.proximo_cobro, s.fuente_pago_id) == (False, None, "3892")
    planes.renovar_todo(ahora=_antes("2026-11-09T10:00:00", 30))
    planes.renovar_todo(ahora=_despues("2026-11-09T10:00:00", minutos=1))
    assert len(falso.posts) == 1 and _sus(base_temporal).estado == "terminada"


def test_morosa_anulada_y_cambio_de_tarjeta_no_cobra_en_el_acto(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    falso.respuestas["pl-1-20261109-1"] = "DECLINED"
    planes.renovar_todo(ahora=_antes("2026-11-09T10:00:00", 60))
    assert _sus(base_temporal).estado == "morosa"
    planes.aplicar_transaccion({**falso.txs["1292-1-1"], "status": "VOIDED"}, ahora=_antes("2026-11-09T10:00:00", 50))
    r = planes.cambiar_fuente("acme", "CARD", "tok2", "pagos@acme.co", dict(ACEPTACION), "user_acme",
                              ahora=_antes("2026-11-09T10:00:00", 40))
    assert r["cobro"] is None
    assert [p["referencia"] for p in falso.posts] == ["pl-1-20261009-1", "pl-1-20261109-1"]
    planes.renovar_todo(ahora=_despues("2026-11-09T10:00:00", horas=24))
    assert len(falso.posts) == 2


def test_cancelada_con_un_cobro_en_vuelo_no_avisa_antes_de_tiempo(base_temporal, planes, pro, falso, avisos):
    """Minor 3: dentro del «en vuelo» el envío puede responder todavía; el aviso de incierto espera."""
    _suscribir(planes, pro)
    falso.error = (falso.wompi.ErrorWompi("read", caida=True, incierto=True), False)
    planes.renovar_todo(ahora=_antes("2026-11-09T10:00:00", 30))
    planes.cancelar("acme", "user_acme", ahora=_antes("2026-11-09T10:00:00", 20))
    assert planes.cobrar_periodo(1, ahora=_antes("2026-11-09T10:00:00", 10)) == "en_curso"
    assert "admin:plan_admin" not in _tipos(avisos)
    _envejecer(base_temporal)
    assert planes.cobrar_periodo(1, ahora=_despues("2026-11-09T10:00:00", horas=1)) == "incierto"
    assert _tipos(avisos).count("admin:plan_admin") == 1
    assert len(falso.posts) == 2


# ----------------------------------------------- revisión 3 (dinero) ---

def test_carrera_cambio_de_tarjeta_en_morosa_y_activacion_manual(base_temporal, planes, pro, falso, avisos,
                                                                monkeypatch):
    """El cliente cambia la tarjeta estando morosa; mientras se lee la TRM (fuera del candado) el admin activa a
    mano el mismo periodo. El cobro forzado relee con el candado: sin renovación, no hay cobro."""
    _suscribir(planes, pro)
    falso.respuestas["pl-1-20261109-1"] = "DECLINED"
    planes.renovar_todo(ahora=_antes("2026-11-09T10:00:00", 60))
    assert _sus(base_temporal).estado == "morosa"
    original = planes._necesita_tasa
    hecho = []

    def entre(sid, ahora, forzar):
        if not hecho:
            hecho.append(1)
            planes.activar_manual("acme", pro, "mensual", "admin", "transferencia", ahora=ahora)
        return original(sid, ahora, forzar)
    monkeypatch.setattr(planes, "_necesita_tasa", entre)
    r = planes.cambiar_fuente("acme", "CARD", "tok2", "pagos@acme.co", dict(ACEPTACION), "user_acme",
                              ahora=_antes("2026-11-09T10:00:00", 40))
    assert r["cobro"] == "no_toca"
    assert [p["referencia"] for p in falso.posts] == ["pl-1-20261009-1", "pl-1-20261109-1"]
    assert [(p.medio, p.estado) for p in _filas(base_temporal, "pago_plan")] == [
        ("wompi", "aprobado"), ("wompi", "rechazado"), ("manual", "aprobado")]
    s = _sus(base_temporal)
    assert (s.estado, s.renovar) == ("activa", False)


def test_un_periodo_a_mano_que_abre_despues_acredita_lo_pagado(base_temporal, planes, pro, falso, avisos):
    """Minor 2: la bolsa de un periodo pagado a mano es su foto del día del pago, aunque abra meses después."""
    planes.activar_manual("acme", pro, "mensual", "admin", "mes 1", ahora=T0)
    planes.activar_manual("acme", pro, "anual", "admin", "año siguiente", ahora=_despues(T0, dias=10))
    planes.editar_plan(pro, usuario="admin", precio_usd=1500, precio_anual_usd=15000)
    fin = "2026-11-09T10:00:00"
    for mes in range(0, 3):
        frontera = planes.sumar_meses(fin, mes)
        planes.renovar_todo(ahora=_antes(frontera, 20))
        planes.renovar_todo(ahora=_despues(frontera, minutos=1))
    periodos = _filas(base_temporal, "periodo_plan")
    assert len(periodos) == 4
    assert [p.credito_milesimas for p in periodos] == [1_000_000] * 4
    assert [p.usd for p in _filas(base_temporal, "pago_plan")] == [1000, 10000]


# ------------------------------------------------ revisión final 2026-10-10 ---

def _tarea_viva(db, job_id, cliente="acme"):
    with db.conectar() as con:
        con.execute(sa.insert(db.tarea).values(
            cliente=cliente, job_id=job_id, tipo="flowplus_video", payload={}, estado="en_curso", intentos=0,
            max_intentos=1, prioridad=5, ejecutar_desde=db.ahora(), creada_en=db.ahora(), duracion_estimada=60.0,
            etapas=[]))


def test_un_periodo_con_un_lote_vivo_no_cierra_hasta_seis_horas_despues(base_temporal, planes, pro, falso, avisos):
    """Un lote reservado durante el periodo todavía se cobra de esa bolsa: el periodo espera para vencer (hasta
    6 h después de su fin); después cierra igual."""
    _suscribir(planes, pro)
    (per,) = _filas(base_temporal, "periodo_plan")
    _tarea_viva(base_temporal, "lote")
    with base_temporal.conectar() as con:                    # reservado dentro del periodo
        con.execute(base_temporal.reserva_saldo.insert().values(
            cliente="acme", job_id="lote", milesimas=40_000, creada_en=_despues(T0, dias=29, horas=23),
            margen=1.25, incluido=False, periodo_id=per.id))
    fin = per.fin
    r = planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert r["cerrados"] == 0 and r["esperando"] == 1
    assert _filas(base_temporal, "movimiento_saldo", tipo="vencimiento") == []
    r = planes.renovar_todo(ahora=_despues(fin, horas=6))  # el tope: cierra igual
    assert r["cerrados"] == 1
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="vencimiento")) == 1


def test_un_periodo_cierra_si_el_lote_ya_termino_o_se_reservo_despues(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    (per,) = _filas(base_temporal, "periodo_plan")
    _tarea_viva(base_temporal, "despues")
    with base_temporal.conectar() as con:                    # reservado después del fin: no es de esta bolsa
        con.execute(base_temporal.reserva_saldo.insert().values(
            cliente="acme", job_id="despues", milesimas=40_000, creada_en=_despues(per.fin, minutos=1), margen=2.0))
        con.execute(base_temporal.reserva_saldo.insert().values(   # durante, pero su tarea ya no vive
            cliente="acme", job_id="muerta", milesimas=40_000, creada_en=T0, margen=1.25, periodo_id=per.id))
    assert planes.renovar_todo(ahora=_despues(per.fin, minutos=5))["cerrados"] == 1


def test_con_cobrar_apagado_la_periodica_no_cobra_ni_abre_meses(base_temporal, planes, pro, falso, avisos):
    from cobros import libro
    _suscribir(planes, pro)                                   # mensual
    _suscribir(planes, pro, ciclo="anual", cliente="otro")
    libro.configurar("acme", usuario="admin", cobrar=False)
    libro.configurar("otro", usuario="admin", cobrar=False)
    fin = "2026-11-09T10:00:00"
    r = planes.renovar_todo(ahora=_antes(fin, 30))
    assert len(falso.posts) == 2                              # solo las dos altas
    assert r["cobros"].get("no_cobra") == 1                   # la mensual (la anual todavía no toca)
    planes.renovar_todo(ahora=_despues(fin, minutos=1))
    assert len(_filas(base_temporal, "periodo_plan", cliente="otro")) == 1   # el mes 2 del anual no abre
    libro.configurar("acme", usuario="admin", cobrar=True)    # se vuelve a prender: la periódica cobra
    libro.configurar("otro", usuario="admin", cobrar=True)
    planes.renovar_todo(ahora=_despues(fin, minutos=31))
    assert len(falso.posts) == 3
    assert len(_filas(base_temporal, "periodo_plan", cliente="otro")) == 2


def test_apagar_renovacion_deja_lo_pagado_y_no_cobra_mas(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    assert planes.apagar_renovacion("acme", "admin") is True
    s = _sus(base_temporal)
    assert (s.estado, s.renovar, s.proximo_cobro, s.cubierto_hasta) == ("activa", False, None, "2026-11-09T10:00:00")
    assert planes.apagar_renovacion("acme", "admin") is False      # ya estaba apagada
    assert planes.apagar_renovacion("otro", "admin") is False      # sin plan


def test_un_cobro_que_cruza_la_medianoche_se_anuncia_el_dia_anterior(base_temporal, planes, pro, falso, avisos):
    """Alta a las 00:30: lo pagado vence el 15 a las 00:30 y la renovación se cobra el 14 a las 23:30. La pantalla
    y el aviso de 3 días dicen el 14 a las 23:30, no «el 15» (revisión final 2026-10-10)."""
    from cobros import vista
    _suscribir(planes, pro, ahora="2026-10-15T00:30:00")
    e = planes.estado_cliente("acme", ahora="2026-10-20T10:00:00")
    assert e["cobro_el"] == "2026-11-14T23:30:00" and e["renueva_el"] == "2026-11-15T00:30:00"
    assert vista.fecha_hora_larga(e["cobro_el"]) == "14 de noviembre de 2026 a las 23:30"
    planes.renovar_todo(ahora="2026-11-12T10:00:00")
    (aviso,) = [e for e in avisos if e[0] == "plan_por_renovar"]
    assert "14 de noviembre de 2026 a las 23:30" in aviso[3]


def test_el_aviso_de_un_anual_no_dice_que_lo_no_usado_antes_de_la_fecha_se_pierde(base_temporal, planes, pro, falso,
                                                                                  avisos):
    _suscribir(planes, pro, ciclo="anual")
    planes.renovar_todo(ahora="2027-10-06T11:00:00")
    (aviso,) = [e for e in avisos if e[0] == "plan_por_renovar"]
    assert "anual" in aviso[3] and "antes de esa fecha" not in aviso[3]
    assert "lo que no uses en un mes no pasa al siguiente" in aviso[3]


def test_un_pago_de_plan_de_otro_comercio_no_cuadra(base_temporal, planes, pro, falso, avisos):
    falso.defecto = "PENDING"
    _suscribir(planes, pro)
    (pago,) = _filas(base_temporal, "pago_plan")
    tx = {**falso.txs[pago.transaccion_id], "status": "APPROVED", "comercio": "pub_test_OTRO"}  # llave-de-prueba
    assert planes.aplicar_transaccion(tx) == "no_cuadra"
    assert _filas(base_temporal, "pago_plan")[0].estado == "pendiente" and _filas(base_temporal, "periodo_plan") == []

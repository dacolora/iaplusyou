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
ACEPTACION = {"acceptance_token": "eyJ.acepta.prueba", "personal_token": "eyJ.datos.prueba", "autoriza_cobro": True}


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
    return planes.crear_plan("Pro", 1000, 1.25, 25, precio_anual_usd=10000, usuario="admin")


def _suscribir(planes, pro, ahora=T0, ciclo="mensual", cliente="acme"):
    return planes.suscribir(cliente, pro, ciclo, "CARD", "tok_prueba_4242", "pagos@acme.co", dict(ACEPTACION),
                            "user_acme", ahora=ahora)


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
    for mala in ({}, {**ACEPTACION, "autoriza_cobro": False}, {**ACEPTACION, "personal_token": ""}):
        with pytest.raises(planes.ErrorPlan):
            planes.suscribir("acme", pro, "mensual", "CARD", "tok_x", "a@b.co", mala, "u", ahora=T0)
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
    assert planes.cobrar_periodo(1, ahora=_despues(ahora, minutos=5)) == "incierto"
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

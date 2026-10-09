"""Recargas a la carta con Wompi (spec planes 2026-10-09 §5.1 y §5.3): crear con
el Web Checkout firmado, la vuelta con `?id=` verificada en Wompi, los eventos
firmados y la periódica. Wompi y la TRM siempre falsos: ninguna prueba sale a
la red. Las llaves son falsas y cada línea que trae una lleva la marca."""
import hashlib
import json
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlsplit

import pytest
import sqlalchemy as sa

PUB = "pub_test_PRUEBA123"  # llave-de-prueba
PRV = "prv_test_PRUEBA456"  # llave-de-prueba
EVE = "test_events_PRUEBA789"  # llave-de-prueba
INT = "test_integrity_PRUEBA000"  # llave-de-prueba
TRM = 3912.41
USD = 50
CENTAVOS = 19562100   # ceil(50 × 3912.41 = 195 620,5) = 195 621 pesos


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import proyectos
    from cobros import avisos, bold, libro, recargas, trm, wompi
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    for nombre, valor in (("WOMPI_LLAVE_PUBLICA", PUB), ("WOMPI_LLAVE_PRIVADA", PRV),
                          ("WOMPI_SECRETO_EVENTOS", EVE), ("WOMPI_SECRETO_INTEGRIDAD", INT)):
        monkeypatch.setenv(nombre, valor)
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD", raising=False)
    monkeypatch.delenv("BOLD_LLAVE_SECRETA", raising=False)
    monkeypatch.delenv("BOLD_PRUEBAS", raising=False)
    monkeypatch.setenv("PLATAFORMA_URL", "http://localhost:5050/")

    def _sin_red(*a, **k):
        raise AssertionError("la prueba no debe llamar a la red")
    for verbo in ("get", "post", "put", "request"):
        monkeypatch.setattr(wompi.requests, verbo, _sin_red)

    estado = {"txs": {}, "consultas": [], "avisos": [], "trm": TRM, "links": []}

    def transaccion(tx_id, tiempo=wompi.TIEMPO):
        estado["consultas"].append((tx_id, tiempo))
        tx = estado["txs"].get(tx_id)
        if isinstance(tx, Exception):
            raise tx
        if tx is None:
            raise wompi.ErrorWompi("Wompi no aceptó el pedido (HTTP 404)", codigo=404)
        return wompi.normalizar(tx)

    def actual():
        if isinstance(estado["trm"], Exception):
            raise estado["trm"]
        return estado["trm"]

    def crear_link(**k):
        estado["links"].append(k)
        return {"link_id": "LNK_PRUEBA1", "url": "https://checkout.bold.co/LNK_PRUEBA1"}

    monkeypatch.setattr(wompi, "transaccion", transaccion)
    monkeypatch.setattr(trm, "actual", actual)
    monkeypatch.setattr(bold, "crear_link", crear_link)
    for nombre in ("recarga_acreditada", "recarga_admin", "limpiar_aviso_bajo"):
        monkeypatch.setattr(avisos, nombre, lambda *a, _n=nombre, **k: estado["avisos"].append((_n, a)))
    monkeypatch.setattr(avisos, "admin", lambda tipo, *a, **k: estado["avisos"].append(("admin", tipo)))
    monkeypatch.setattr(recargas, "_en_segundo_plano", lambda fn: fn())
    monkeypatch.setattr(recargas, "_SIN_FIRMA_WOMPI", {"desde": None, "n": 0, "avisado": False})
    monkeypatch.setattr(recargas, "_AVISADOS_NO_CUADRA", set())
    libro.configurar("acme", usuario="admin", cobrar=True)
    estado.update(db=base_temporal, libro=libro, recargas=recargas, wompi=wompi, trm=TRM, trm_mod=trm, bold=bold)
    return estado


def _recarga(db, rid):
    with db.conectar() as con:
        fila = con.execute(sa.select(db.recarga).where(db.recarga.c.id == rid)).first()
        return dict(fila._mapping) if fila else None


def _recargas(db):
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.recarga).order_by(db.recarga.c.id)).all()]


def _movimientos(db, cliente="acme"):
    m = db.movimiento_saldo
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(m).where(m.c.cliente == cliente).order_by(m.c.id)).all()]


def _eventos(db):
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.pago_evento).order_by(db.pago_evento.c.id)).all()]


def _admin(entorno):
    return [a[1] for a in entorno["avisos"] if a[0] == "admin"]


def _pendiente(entorno, usd=USD, cliente="acme"):
    r = entorno["recargas"].crear(cliente, usd, "user_acme", correo="acme@prueba.local")
    return r["id"], _recarga(entorno["db"], r["id"])["referencia"]


def _tx(ref, status="APPROVED", centavos=CENTAVOS, tx_id="1292-1602113476-10985", moneda="COP"):
    return {"id": tx_id, "reference": ref, "status": status, "amount_in_cents": centavos, "currency": moneda,
            "payment_method_type": "CARD", "customer_email": "paga@ejemplo.com", "payment_source_id": None}


PROPS = ("transaction.id", "transaction.status", "transaction.amount_in_cents")
TODAS = PROPS + ("transaction.reference", "transaction.currency")


def _evento(tx, props=PROPS, ts=1760000000, secreto=EVE, tipo="transaction.updated"):
    cuerpo = {"event": tipo, "data": {"transaction": dict(tx)}, "environment": "test",
              "sent_at": "2026-10-09T16:45:05.000Z", "signature": {"properties": list(props), "timestamp": ts}}
    valores = "".join(str(cuerpo["data"]["transaction"][p.split(".")[1]]) for p in props)
    cuerpo["signature"]["checksum"] = hashlib.sha256(f"{valores}{ts}{secreto}".encode()).hexdigest()
    return json.dumps(cuerpo).encode()


def _ev(entorno, cuerpo, checksum=None):
    return entorno["recargas"].procesar_evento_wompi(cuerpo, checksum)


# --- crear -----------------------------------------------------------------------------------

def test_crear_con_wompi_firma_el_checkout_con_los_centavos_de_la_trm(entorno):
    r = entorno["recargas"].crear("acme", USD, "user_acme", correo="acme@prueba.local")
    fila = _recarga(entorno["db"], r["id"])
    assert (fila["medio"], fila["estado"], fila["milesimas"]) == ("wompi", "pendiente", 50000)
    assert fila["referencia"].startswith(f"cv-{r['id']}-")
    assert (fila["total_pago"], fila["moneda_pago"]) == (CENTAVOS, "COP")
    assert fila["nota"] == f"trm={TRM}" and fila["pasarela_ref"] is None
    assert r["url"].startswith("https://checkout.wompi.co/p/?")
    q = dict(parse_qsl(urlsplit(r["url"]).query))
    assert q["public-key"] == PUB and q["currency"] == "COP" and q["amount-in-cents"] == str(CENTAVOS)
    assert q["reference"] == fila["referencia"]
    esperado = hashlib.sha256(f"{fila['referencia']}{CENTAVOS}COP{INT}".encode()).hexdigest()
    assert q["signature:integrity"] == esperado
    assert q["redirect-url"] == f"http://localhost:5050/cliente/acme/saldo/recarga/{r['id']}"
    assert q["customer-data:email"] == "acme@prueba.local"
    assert PRV not in r["url"] and INT not in r["url"] and EVE not in r["url"]
    assert _movimientos(entorno["db"]) == [] and entorno["consultas"] == []


@pytest.mark.parametrize("usd, tasa, centavos", [
    (10, 4000.0, 4_000_000),          # exacto: no sube un peso
    (3, 3333.34, 1_000_100),          # 10 000,02 → 10 001 pesos
    (50, 3912.41, CENTAVOS),          # 195 620,5 → 195 621
    (1000, 4123.99, 412_399_000),
])
def test_centavos_al_peso_hacia_arriba(entorno, usd, tasa, centavos):
    assert entorno["recargas"].centavos_cop(usd, tasa) == centavos


def test_sin_trm_no_queda_ninguna_recarga(entorno):
    entorno["trm"] = entorno["trm_mod"].SinTasa("sin tasa")
    with pytest.raises(ValueError, match="tasa de cambio"):
        entorno["recargas"].crear("acme", USD, "user_acme")
    assert _recargas(entorno["db"]) == []


def test_sin_llaves_de_wompi_pero_con_bold_sigue_bold(entorno, monkeypatch):
    monkeypatch.delenv("WOMPI_SECRETO_INTEGRIDAD")
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", "identidad-falsa")  # llave-de-prueba
    monkeypatch.setenv("BOLD_LLAVE_SECRETA", "secreta-falsa")  # llave-de-prueba
    r = entorno["recargas"].crear("acme", USD, "user_acme")
    assert r["url"] == "https://checkout.bold.co/LNK_PRUEBA1"
    assert _recarga(entorno["db"], r["id"])["medio"] == "bold" and len(entorno["links"]) == 1


def test_con_las_dos_pasarelas_gana_wompi(entorno, monkeypatch):
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", "identidad-falsa")  # llave-de-prueba
    r = entorno["recargas"].crear("acme", USD, "user_acme")
    assert r["url"].startswith("https://checkout.wompi.co/p/") and entorno["links"] == []


def test_llaves_de_pruebas_en_un_servidor_publico_no_crean_checkouts(entorno, monkeypatch):
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.creatvmachine.com")
    with pytest.raises(entorno["bold"].ErrorBold):   # Wompi apagado y sin Bold: ninguna pasarela
        entorno["recargas"].crear("acme", USD, "user_acme")
    assert _recargas(entorno["db"]) == []


# --- vuelta y verificación -------------------------------------------------------------------

def test_vuelta_aprobada_acredita_los_usd_una_sola_vez(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    assert recargas.verificar(rid, transaccion_id="1292-1602113476-10985") == "aprobada"
    fila = _recarga(db, rid)
    assert fila["pasarela_ref"] == "1292-1602113476-10985" and fila["medio_pago"] == "CARD"
    assert fila["total_pago"] == CENTAVOS   # los pesos quedan de registro
    [mov] = _movimientos(db)
    assert (mov["tipo"], mov["milesimas"], mov["concepto"], mov["recarga_id"]) == ("recarga", 50000, "recarga_wompi", rid)
    assert recargas.verificar(rid, transaccion_id="1292-1602113476-10985") == "aprobada"
    assert entorno["libro"].saldo("acme") == 50000 and len(_movimientos(db)) == 1
    assert {"recarga_acreditada", "recarga_admin"} <= {a[0] for a in entorno["avisos"]}


def test_vuelta_rechazada_no_acredita(entorno):
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref, status="DECLINED")
    assert entorno["recargas"].verificar(rid, transaccion_id="1292-1602113476-10985") == "rechazada"
    assert entorno["libro"].saldo("acme") == 0 and _movimientos(entorno["db"]) == []


@pytest.mark.parametrize("cambio", ["monto", "moneda", "referencia"])
def test_vuelta_que_no_cuadra_no_acredita_y_avisa_al_admin(entorno, cambio):
    rid, ref = _pendiente(entorno)
    tx = _tx(ref)
    if cambio == "monto":
        tx["amount_in_cents"] = CENTAVOS - 100
    elif cambio == "moneda":
        tx["currency"] = "USD"
    else:
        tx["reference"] = "cv-999-1"   # una transacción de otra recarga pegada en el ?id=
    entorno["txs"]["1292-1602113476-10985"] = tx
    assert entorno["recargas"].verificar(rid, transaccion_id="1292-1602113476-10985") == "pendiente"
    fila = _recarga(entorno["db"], rid)
    assert fila["pasarela_ref"] is None and entorno["libro"].saldo("acme") == 0
    assert _admin(entorno) == ["wompi_no_cuadra"]
    entorno["recargas"].verificar(rid, transaccion_id="1292-1602113476-10985")
    assert _admin(entorno) == ["wompi_no_cuadra"]   # el sondeo no manda un correo cada 3 s


def test_vuelta_pendiente_guarda_la_transaccion_y_la_periodica_acredita(entorno):
    recargas = entorno["recargas"]
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref, status="PENDING")
    assert recargas.verificar(rid, transaccion_id="1292-1602113476-10985") == "pendiente"
    assert _recarga(entorno["db"], rid)["pasarela_ref"] == "1292-1602113476-10985"
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    assert recargas.verificar_pendientes() == 1
    assert _recarga(entorno["db"], rid)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000
    assert entorno["consultas"][-1] == ("1292-1602113476-10985", entorno["wompi"].TIEMPO)


def test_la_periodica_vence_una_vieja_sin_transaccion_y_el_evento_tardio_la_acredita(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    viejo = (datetime.now() - timedelta(hours=recargas.HORAS_VIGENTE + 1)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(creada_en=viejo))
    recargas.verificar_pendientes()
    assert _recarga(db, rid)["estado"] == "expirada" and entorno["consultas"] == []
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    assert _ev(entorno, _evento(_tx(ref)))[1] == "acreditada"
    assert _recarga(db, rid)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000


def test_la_periodica_para_con_wompi_caido(entorno):
    for i in range(3):
        rid, ref = _pendiente(entorno)
        tx_id = f"1292-1602113476-1098{i}"
        with entorno["db"].conectar() as con:
            con.execute(entorno["db"].recarga.update().where(entorno["db"].recarga.c.id == rid)
                        .values(pasarela_ref=tx_id))
        entorno["txs"][tx_id] = entorno["wompi"].ErrorWompi("No se pudo hablar con Wompi (Timeout)", caida=True)
    assert entorno["recargas"].verificar_pendientes() == 0
    assert len(entorno["consultas"]) == 1


def test_verificar_toma_el_candado_antes_de_leer(entorno, escritor_en_medio):
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    otro = escritor_en_medio("recarga.pasarela_ref = ", "UPDATE recarga SET estado = 'anulada'")
    assert entorno["recargas"].verificar(rid, transaccion_id="1292-1602113476-10985") == "aprobada"
    assert otro["resultado"].startswith("bloqueado")


# --- eventos ---------------------------------------------------------------------------------

def test_evento_firmado_acredita(entorno):
    db = entorno["db"]
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    cuerpo = _evento(_tx(ref))
    assert _ev(entorno, cuerpo) == (200, "acreditada")
    fila = _recarga(db, rid)
    assert fila["estado"] == "aprobada" and fila["pasarela_ref"] == "1292-1602113476-10985"
    assert entorno["libro"].saldo("acme") == 50000
    [ev] = _eventos(db)
    assert ev["proveedor"] == "wompi" and ev["evento_id"] == hashlib.sha256(cuerpo).hexdigest()
    assert ev["firma_ok"] is True and ev["resultado"] == "acreditada" and ev["referencia"] == ref
    assert ev["tipo"] == "transaction.updated"
    assert "paga@ejemplo.com" not in json.dumps(ev["cuerpo"])   # lista blanca
    assert ev["cuerpo"]["transaction"]["amount_in_cents"] == CENTAVOS
    # La referencia y la moneda no van firmadas: se releyó la transacción antes de acreditar.
    assert [c[0] for c in entorno["consultas"]] == ["1292-1602113476-10985"]
    assert entorno["consultas"][0][1] == entorno["wompi"].TIEMPO_INTERACTIVO


def test_evento_con_todo_firmado_no_relee(entorno):
    rid, ref = _pendiente(entorno)
    assert _ev(entorno, _evento(_tx(ref), props=TODAS)) == (200, "acreditada")
    assert entorno["consultas"] == [] and entorno["libro"].saldo("acme") == 50000


def test_el_mismo_evento_dos_veces_no_acredita_dos_veces(entorno):
    _, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    cuerpo = _evento(_tx(ref))
    assert _ev(entorno, cuerpo) == (200, "acreditada")
    entorno["avisos"].clear()
    assert _ev(entorno, cuerpo) == (200, "duplicada")
    assert entorno["libro"].saldo("acme") == 50000 and len(_eventos(entorno["db"])) == 1 and entorno["avisos"] == []


def test_evento_y_vuelta_no_duplican(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    assert _ev(entorno, _evento(_tx(ref)))[1] == "acreditada"
    assert recargas.verificar(rid, transaccion_id="1292-1602113476-10985") == "aprobada"
    rid2, ref2 = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-20000"] = _tx(ref2, tx_id="1292-1602113476-20000")
    assert recargas.verificar(rid2, transaccion_id="1292-1602113476-20000") == "aprobada"
    assert _ev(entorno, _evento(_tx(ref2, tx_id="1292-1602113476-20000")))[1] == "duplicada"
    assert entorno["libro"].saldo("acme") == 100000 and len(_movimientos(db)) == 2


def test_el_evento_toma_el_candado_antes_de_leer(entorno, escritor_en_medio):
    """El evento y la vuelta a la vez: el otro escritor queda bloqueado entre la
    lectura de la recarga y la acreditación."""
    _, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    otro = escritor_en_medio("recarga.pasarela_ref = ", "UPDATE recarga SET estado = 'anulada'")
    assert _ev(entorno, _evento(_tx(ref)))[1] == "acreditada"
    assert otro["resultado"].startswith("bloqueado")


def test_el_evento_toma_el_candado_antes_de_mirar_si_es_repetido(entorno, escritor_en_medio, monkeypatch):
    """Dos entregas del mismo evento a la vez: la lectura de pago_evento dentro
    de la transacción que acredita ya va con el candado (la mirada previa, sin
    candado, solo evita releer en Wompi un repetido)."""
    _, ref = _pendiente(entorno)
    monkeypatch.setattr(entorno["recargas"], "_es_duplicado", lambda evento_id: False)
    otro = escritor_en_medio("FROM pago_evento", "UPDATE recarga SET estado = 'anulada'")
    assert _ev(entorno, _evento(_tx(ref), props=TODAS))[1] == "acreditada"
    assert otro["resultado"].startswith("bloqueado")


def test_un_evento_con_la_referencia_cambiada_no_acredita_a_otro(entorno):
    """La referencia no va firmada: un evento verdadero con la referencia de
    otra recarga del mismo monto no la acredita; vale lo que dice Wompi."""
    db = entorno["db"]
    rid_a, ref_a = _pendiente(entorno)
    rid_b, ref_b = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref_a)
    assert _ev(entorno, _evento(_tx(ref_b)))[1] == "acreditada"
    assert _recarga(db, rid_a)["estado"] == "aprobada" and _recarga(db, rid_b)["estado"] == "pendiente"
    assert "wompi_no_cuadra" in _admin(entorno)


def test_evento_cuyo_monto_no_cuadra_relee_y_no_acredita(entorno):
    rid, ref = _pendiente(entorno)
    tx = _tx(ref, centavos=CENTAVOS - 100)
    entorno["txs"]["1292-1602113476-10985"] = tx
    assert _ev(entorno, _evento(tx)) == (200, "no_cuadra")
    assert _recarga(entorno["db"], rid)["estado"] == "pendiente" and entorno["libro"].saldo("acme") == 0
    assert _admin(entorno) == ["wompi_no_cuadra"]
    assert _eventos(entorno["db"])[0]["resultado"] == "no_cuadra"


def test_evento_que_no_cuadra_y_wompi_lo_desmiente_vale_wompi(entorno):
    """El evento dice un monto y Wompi otro (el correcto): se acredita lo releído y se avisa."""
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    assert _ev(entorno, _evento(_tx(ref, centavos=999), props=TODAS)) == (200, "acreditada")
    assert entorno["libro"].saldo("acme") == 50000 and "wompi_no_cuadra" in _admin(entorno)


def test_evento_que_no_cuadra_con_wompi_caido_responde_500_sin_escribir(entorno):
    _, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = entorno["wompi"].ErrorWompi("caído", caida=True)
    assert _ev(entorno, _evento(_tx(ref))) == (500, "error")
    assert _eventos(entorno["db"]) == []   # Wompi reintenta y el reintento sí se procesa
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    assert _ev(entorno, _evento(_tx(ref)))[1] == "acreditada"


def test_evento_de_una_referencia_desconocida_avisa_al_admin(entorno):
    entorno["txs"]["1292-1602113476-10985"] = _tx("cv-999-1")
    assert _ev(entorno, _evento(_tx("cv-999-1"))) == (200, "sin_recarga")
    assert _admin(entorno) == ["pago_sin_recarga"]


def test_evento_rechazado_marca_la_recarga_y_un_aprobado_despues_acredita(entorno):
    rid, ref = _pendiente(entorno)
    assert _ev(entorno, _evento(_tx(ref, status="DECLINED")))[1] == "rechazada"
    assert _recarga(entorno["db"], rid)["estado"] == "rechazada" and entorno["consultas"] == []
    entorno["txs"]["1292-1602113476-20000"] = _tx(ref, tx_id="1292-1602113476-20000")
    assert _ev(entorno, _evento(_tx(ref, tx_id="1292-1602113476-20000")))[1] == "acreditada"
    assert entorno["libro"].saldo("acme") == 50000


def test_anulacion_de_una_aprobada_descuenta_y_avisa(entorno):
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    _ev(entorno, _evento(_tx(ref)))
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref, status="VOIDED")
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED")))[1] == "anulada"
    assert _recarga(entorno["db"], rid)["estado"] == "anulada" and entorno["libro"].saldo("acme") == 0
    assert [m["concepto"] for m in _movimientos(entorno["db"])] == ["recarga_wompi", "anulacion_wompi"]
    assert "anulacion_wompi" in _admin(entorno)


def test_evento_sin_firma_401_sin_tocar_nada(entorno):
    rid, ref = _pendiente(entorno)
    assert _ev(entorno, _evento(_tx(ref), secreto="test_events_OTRO")) == (401, "firma_invalida")  # llave-de-prueba
    cuerpo = _evento(_tx(ref))
    assert _ev(entorno, cuerpo, checksum="0" * 64) == (401, "firma_invalida")
    alterado = json.loads(cuerpo)
    alterado["data"]["transaction"]["amount_in_cents"] = CENTAVOS * 10
    assert _ev(entorno, json.dumps(alterado).encode()) == (401, "firma_invalida")
    assert _recarga(entorno["db"], rid)["estado"] == "pendiente" and _movimientos(entorno["db"]) == []
    assert entorno["consultas"] == []
    evs = _eventos(entorno["db"])
    assert len(evs) == 3 and all(e["firma_ok"] is False and e["cuerpo"] is None and e["proveedor"] == "wompi"
                                 for e in evs)


def test_eventos_sin_firma_tienen_cupo_propio(entorno):
    recargas = entorno["recargas"]
    cuerpo = _evento(_tx("cv-1-1"), secreto="test_events_OTRO")  # llave-de-prueba
    for _ in range(recargas.TOPE_SIN_FIRMA_HORA + 5):
        assert _ev(entorno, cuerpo) == (401, "firma_invalida")
    assert len(_eventos(entorno["db"])) == recargas.TOPE_SIN_FIRMA_HORA
    import cuentas
    assert cuentas.limite_ok("bold:sinfirma", recargas.TOPE_SIN_FIRMA_HORA, 3600)   # el cupo de Bold sigue entero


def test_sin_llaves_de_wompi_todo_evento_es_401(entorno, monkeypatch):
    _, ref = _pendiente(entorno)
    monkeypatch.delenv("WOMPI_SECRETO_EVENTOS")
    assert _ev(entorno, _evento(_tx(ref))) == (401, "firma_invalida")
    assert entorno["libro"].saldo("acme") == 0


def test_eventos_firmados_ajenos_responden_200(entorno):
    assert _ev(entorno, _evento(_tx("PEDIDO-TIENDA-1"))) == (200, "ignorada")
    assert _ev(entorno, _evento(_tx("cv-1-1"), tipo="nequi_token.updated")) == (200, "ignorada")
    assert [e["resultado"] for e in _eventos(entorno["db"])] == ["ignorada", "ignorada"]
    assert entorno["consultas"] == []


def test_evento_de_un_plan_sin_planes_se_ignora(entorno, monkeypatch):
    from cobros import planes
    monkeypatch.delattr(planes, "aplicar_transaccion", raising=False)
    assert _ev(entorno, _evento(_tx("pl-3-20261009-1"))) == (200, "ignorada")


def test_evento_de_un_plan_llama_a_planes(entorno, monkeypatch):
    from cobros import planes
    vistos = []
    monkeypatch.setattr(planes, "aplicar_transaccion", lambda tx: vistos.append(tx) or "aprobado", raising=False)
    cuerpo = _evento(_tx("pl-3-20261009-1"))
    assert _ev(entorno, cuerpo) == (200, "aprobado")
    assert vistos[0]["reference"] == "pl-3-20261009-1" and vistos[0]["status"] == "APPROVED"
    assert _ev(entorno, cuerpo) == (200, "duplicada") and len(vistos) == 1
    assert _eventos(entorno["db"])[0]["resultado"] == "aprobado"


def test_evento_de_un_plan_que_falla_responde_500_y_se_reintenta(entorno, monkeypatch):
    from cobros import planes

    def falla(tx):
        raise RuntimeError("base ocupada")
    monkeypatch.setattr(planes, "aplicar_transaccion", falla, raising=False)
    cuerpo = _evento(_tx("pl-3-20261009-1"))
    assert _ev(entorno, cuerpo) == (500, "error") and _eventos(entorno["db"]) == []


@pytest.mark.parametrize("cuerpo", [b"no es json", b"[1, 2]", b"\xff\xfe", b"", b"[" * 60000,
                                    b'{"data": ' + b"[" * 30000 + b"]" * 30000 + b"}"],
                         ids=["texto", "lista", "binario", "vacio", "anidado", "anidado_en_objeto"])
def test_cuerpo_invalido_400(entorno, cuerpo):
    assert _ev(entorno, cuerpo)[0] == 400
    assert _eventos(entorno["db"]) == []


def test_cuerpo_demasiado_grande_413(entorno):
    assert _ev(entorno, b"{" + b" " * 70000 + b"}") == (413, "invalido")


# --- rutas -----------------------------------------------------------------------------------

@pytest.fixture()
def cliente_http(entorno, monkeypatch):
    import dashboard
    from cobros import rutas
    monkeypatch.setattr(rutas, "_ULTIMA_VERIFICACION", {})
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()

    def como(usuario):
        from tests.conftest import USUARIOS_PRUEBA
        with c.session_transaction() as s:
            s.clear()
            if usuario:
                s["usuario"] = usuario
                s["rol"] = USUARIOS_PRUEBA[usuario]["rol"]
                s["cliente"] = USUARIOS_PRUEBA[usuario]["cliente"]
                s["sv"] = 1
        return c
    c.como = como
    return c


MISMO = {"Sec-Fetch-Site": "same-origin"}


def test_las_excepciones_csrf_son_exactamente_los_dos_webhooks():
    import dashboard
    assert dashboard.ENDPOINTS_OTRO_ORIGEN == {"cobros.bold_webhook", "cobros.wompi_eventos"}
    assert "cobros.wompi_eventos" in dashboard.ENDPOINTS_SIN_GUARD_SESION


def test_recargar_redirige_al_checkout_de_wompi(entorno, cliente_http):
    c = cliente_http.como("user_acme")
    r = c.post("/cliente/acme/saldo/recargar", data={"usd": "50"}, headers=MISMO)
    assert r.status_code == 302 and r.headers["Location"].startswith("https://checkout.wompi.co/p/?")
    q = dict(parse_qsl(urlsplit(r.headers["Location"]).query))
    assert q["amount-in-cents"] == str(CENTAVOS) and q["customer-data:email"] == "acme@prueba.local"


def test_recargar_sin_trm_avisa_en_palabras_sin_dejar_recarga(entorno, cliente_http):
    entorno["trm"] = entorno["trm_mod"].SinTasa("sin tasa")
    c = cliente_http.como("user_acme")
    r = c.post("/cliente/acme/saldo/recargar", data={"usd": "50"}, headers=MISMO, follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("#config-ap-saldo")
    with c.session_transaction() as s:
        assert any("tasa de cambio" in m for _, m in s.get("_flashes", []))
    assert _recargas(entorno["db"]) == []


def test_recargar_de_otro_sitio_403(entorno, cliente_http):
    r = cliente_http.como("user_acme").post("/cliente/acme/saldo/recargar", data={"usd": "50"},
                                            headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and _recargas(entorno["db"]) == []


def test_la_vuelta_con_id_verifica_en_wompi_y_acredita(entorno, cliente_http):
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    c = cliente_http.como("user_acme")
    r = c.get(f"/cliente/acme/saldo/recarga/{rid}?id=1292-1602113476-10985&env=test")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Listo" in html and "con Wompi" in html
    assert entorno["libro"].saldo("acme") == 50000
    assert entorno["consultas"] == [("1292-1602113476-10985", entorno["wompi"].TIEMPO_INTERACTIVO)]
    c.get(f"/cliente/acme/saldo/recarga/{rid}?id=1292-1602113476-10985")
    assert entorno["libro"].saldo("acme") == 50000 and len(_movimientos(entorno["db"])) == 1


def test_la_vuelta_sin_id_o_con_un_id_raro_no_consulta(entorno, cliente_http):
    rid, _ = _pendiente(entorno)
    c = cliente_http.como("user_acme")
    for url in (f"/cliente/acme/saldo/recarga/{rid}", f"/cliente/acme/saldo/recarga/{rid}?id=../../x",
                f"/cliente/acme/saldo/recarga/{rid}?id=" + "a" * 70):
        assert c.get(url).status_code == 200
    assert entorno["consultas"] == [] and _recarga(entorno["db"], rid)["estado"] == "pendiente"


def test_la_vuelta_pendiente_sondea_con_el_id(entorno, cliente_http):
    from cobros import rutas
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref, status="PENDING")
    c = cliente_http.como("user_acme")
    html = c.get(f"/cliente/acme/saldo/recarga/{rid}?id=1292-1602113476-10985").get_data(as_text=True)
    assert f"/cliente/acme/saldo/recarga/{rid}/estado?id=1292-1602113476-10985" in html
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    rutas._ULTIMA_VERIFICACION.clear()
    j = c.get(f"/cliente/acme/saldo/recarga/{rid}/estado?id=1292-1602113476-10985").get_json()
    assert j["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000


def test_la_vuelta_de_otro_proyecto_es_404(entorno, cliente_http):
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    r = cliente_http.como("otro").get(f"/cliente/acme/saldo/recarga/{rid}?id=1292-1602113476-10985")
    assert r.status_code in (302, 403, 404)
    assert entorno["consultas"] == [] and entorno["libro"].saldo("acme") == 0


def test_la_vuelta_respeta_la_consulta_en_vuelo(entorno, cliente_http, monkeypatch):
    from cobros import rutas
    rid, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    monkeypatch.setattr(rutas, "_EN_CURSO", {rid})
    cliente_http.como("user_acme").get(f"/cliente/acme/saldo/recarga/{rid}?id=1292-1602113476-10985")
    assert entorno["consultas"] == []


def test_el_panel_ofrece_wompi(entorno, cliente_http):
    html = cliente_http.como("user_acme").get("/cliente/acme/saldo/panel").get_data(as_text=True)
    assert "Pagar con Wompi" in html and "Pagar con Bold" not in html


def test_eventos_de_otro_sitio_y_sin_sesion(entorno, cliente_http):
    c = cliente_http.como(None)
    _, ref = _pendiente(entorno)
    entorno["txs"]["1292-1602113476-10985"] = _tx(ref)
    cuerpo = _evento(_tx(ref))
    cab = {"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"}
    r = c.post("/pagos/wompi/eventos", data=cuerpo, headers={**cab, "X-Event-Checksum": "0" * 64})
    assert r.status_code == 401 and r.data == b""
    r = c.post("/pagos/wompi/eventos", data=cuerpo, headers=cab)
    assert r.status_code == 200 and r.data == b""
    assert entorno["libro"].saldo("acme") == 50000
    r = c.post("/pagos/wompi/eventos", data=_evento(_tx("PEDIDO-AJENO")), headers=cab)
    assert r.status_code == 200 and r.data == b""


def test_eventos_con_una_sesion_vieja_no_redirigen(entorno, cliente_http):
    c = cliente_http.como("user_acme")
    with c.session_transaction() as s:
        s["usuario"] = "fantasma"
    r = c.post("/pagos/wompi/eventos", data=_evento(_tx("PEDIDO-AJENO")))
    assert r.status_code == 200


def test_eventos_400_413_y_405(entorno, cliente_http):
    c = cliente_http.como(None)
    assert c.post("/pagos/wompi/eventos", data=b"no es json").status_code == 400
    assert c.post("/pagos/wompi/eventos", data=b"[" * 60000).status_code == 400
    assert c.post("/pagos/wompi/eventos", data=b"x" * 70000).status_code == 413
    assert c.get("/pagos/wompi/eventos").status_code == 405
    assert _eventos(entorno["db"]) == []

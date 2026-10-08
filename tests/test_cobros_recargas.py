"""Recargas del saldo con Bold (spec 2026-10-08 §9 y §11): crear la recarga,
el webhook firmado, la verificación de respaldo, la recarga manual y sus
rutas. Bold siempre falso: ninguna prueba sale a la red."""
import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

URL_BOLD = "https://checkout.bold.co/LNK_PRUEBA1"


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    """Base nueva, Bold falso (link y estado), firma de pruebas (secreta vacía +
    BOLD_PRUEBAS=1) y avisos anotados en una lista en vez de mandarse."""
    import proyectos
    from cobros import avisos, bold, libro, recargas
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", "identidad-falsa")  # llave-de-prueba
    monkeypatch.setenv("BOLD_LLAVE_SECRETA", "")
    monkeypatch.setenv("BOLD_PRUEBAS", "1")
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.creatvmachine.com/")

    estado = {"links": [], "status": {"status": "ACTIVE", "transaction_id": None, "total": None},
              "avisos": [], "consultas": 0, "error_link": None}

    def crear_link(**k):
        if estado["error_link"]:
            raise bold.ErrorBold(estado["error_link"])
        estado["links"].append(k)
        return {"link_id": f"LNK_PRUEBA{len(estado['links'])}", "url": URL_BOLD}

    def estado_link(link_id):
        estado["consultas"] += 1
        if isinstance(estado["status"], Exception):
            raise estado["status"]
        return dict(estado["status"])

    monkeypatch.setattr(bold, "crear_link", crear_link)
    monkeypatch.setattr(bold, "estado_link", estado_link)
    for nombre in ("recarga_acreditada", "recarga_admin", "limpiar_aviso_bajo"):
        monkeypatch.setattr(avisos, nombre, lambda *a, _n=nombre, **k: estado["avisos"].append((_n, a)))
    monkeypatch.setattr(avisos, "admin", lambda tipo, *a, **k: estado["avisos"].append(("admin", tipo)))
    monkeypatch.setattr(recargas, "_en_segundo_plano", lambda fn: fn())   # avisos en el mismo hilo
    libro.configurar("acme", usuario="admin", cobrar=True)
    estado.update(db=base_temporal, libro=libro, recargas=recargas, bold=bold)
    return estado


def _recarga(db, rid):
    with db.conectar() as con:
        fila = con.execute(sa.select(db.recarga).where(db.recarga.c.id == rid)).first()
        return dict(fila._mapping) if fila else None


def _recargas(db):
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.recarga)).all()]


def _movimientos(db, cliente="acme"):
    m = db.movimiento_saldo
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(m).where(m.c.cliente == cliente).order_by(m.c.id)).all()]


def _eventos(db):
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.pago_evento).order_by(db.pago_evento.c.id)).all()]


def _evento(tipo="SALE_APPROVED", ref=None, evento="ev-1", pago="PAY-1", total=200000):
    return json.dumps({
        "id": evento, "type": tipo, "subject": pago, "source": "/payments", "spec_version": "1.0",
        "time": 1728400000000000000,
        "data": {"payment_id": pago, "merchant_id": "M1", "created_at": "2026-10-08T10:00:00-05:00",
                 "amount": {"currency": "COP", "total": total, "taxes": [], "tip": 0},
                 "metadata": {"reference": ref}, "payment_method": "CARD", "payer_email": "paga@ejemplo.com",
                 "payer": {"name": "Ana Paga", "card_last4": "4242"}},   # un campo que Bold podría agregar
    }).encode()


def _firma(cuerpo, secreta=""):
    return hmac.new(secreta.encode(), base64.b64encode(cuerpo), hashlib.sha256).hexdigest()


def _webhook(recargas, cuerpo, firma=None):
    return recargas.procesar_webhook(cuerpo, _firma(cuerpo) if firma is None else firma)


# --- crear -----------------------------------------------------------------------------------

def test_crear_deja_la_recarga_pendiente_con_su_link(entorno):
    r = entorno["recargas"].crear("acme", 50, "user_acme", correo="acme@prueba.local")
    assert r["url"] == URL_BOLD
    fila = _recarga(entorno["db"], r["id"])
    assert fila["estado"] == "pendiente" and fila["medio"] == "bold" and fila["milesimas"] == 50000
    assert re.fullmatch(r"cv-\d+-\d+", fila["referencia"]) and len(fila["referencia"]) <= 60
    assert fila["referencia"].startswith(f"cv-{r['id']}-")
    assert fila["link_id"] == "LNK_PRUEBA1" and fila["usuario"] == "user_acme"
    link = entorno["links"][0]
    assert link["referencia"] == fila["referencia"] and link["usd"] == 50 and link["correo"] == "acme@prueba.local"
    assert link["callback_url"] == f"https://app.creatvmachine.com/cliente/acme/saldo/recarga/{r['id']}"
    assert link["descripcion"] == "Recarga Creatv · acme"
    assert _movimientos(entorno["db"]) == []   # crear no acredita nada


@pytest.mark.parametrize("usd", [9, 1001, 10.5, "x", "", None, True, -50, "50.0", 0])
def test_crear_rechaza_montos_invalidos_sin_escribir(entorno, usd):
    with pytest.raises(ValueError):
        entorno["recargas"].crear("acme", usd, "user_acme")
    assert _recargas(entorno["db"]) == [] and entorno["links"] == []


@pytest.mark.parametrize("usd", [10, 1000, "25", " 100 "])
def test_crear_acepta_enteros_y_texto_de_digitos(entorno, usd):
    r = entorno["recargas"].crear("acme", usd, "user_acme")
    assert _recarga(entorno["db"], r["id"])["milesimas"] == int(str(usd).strip()) * 1000


def test_crear_sin_plataforma_url_no_escribe(entorno, monkeypatch):
    monkeypatch.setenv("PLATAFORMA_URL", " ")
    with pytest.raises(ValueError):
        entorno["recargas"].crear("acme", 50, "user_acme")
    assert _recargas(entorno["db"]) == []


def test_crear_sin_llaves_de_bold_no_escribe(entorno, monkeypatch):
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD")
    with pytest.raises(entorno["bold"].ErrorBold):
        entorno["recargas"].crear("acme", 50, "user_acme")
    assert _recargas(entorno["db"]) == []


def test_si_bold_falla_la_recarga_queda_rechazada(entorno):
    entorno["error_link"] = "Bold no aceptó el pedido (HTTP 500)"
    with pytest.raises(entorno["bold"].ErrorBold):
        entorno["recargas"].crear("acme", 50, "user_acme")
    [fila] = _recargas(entorno["db"])
    assert fila["estado"] == "rechazada" and "HTTP 500" in fila["nota"] and fila["link_id"] is None


# --- webhook ---------------------------------------------------------------------------------

def _pendiente(entorno, usd=50):
    rid = entorno["recargas"].crear("acme", usd, "user_acme")["id"]
    return rid, _recarga(entorno["db"], rid)["referencia"]


def test_webhook_aprobado_acredita_la_recarga(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    assert _webhook(recargas, _evento(ref=ref)) == (200, "acreditada")
    fila = _recarga(db, rid)
    assert fila["estado"] == "aprobada" and fila["pago_id"] == "PAY-1"
    assert fila["moneda_pago"] == "COP" and fila["total_pago"] == 200000 and fila["medio_pago"] == "CARD"
    assert entorno["libro"].saldo("acme") == 50000
    [mov] = _movimientos(db)
    assert (mov["tipo"], mov["milesimas"], mov["recarga_id"], mov["concepto"]) == ("recarga", 50000, rid, "recarga_bold")
    [ev] = _eventos(db)
    assert ev["proveedor"] == "bold" and ev["evento_id"] == "ev-1" and ev["tipo"] == "SALE_APPROVED"
    assert ev["firma_ok"] is True and ev["resultado"] == "acreditada" and ev["referencia"] == ref
    assert "payer_email" not in ev["cuerpo"] and "paga@ejemplo.com" not in json.dumps(ev["cuerpo"])
    assert "Ana Paga" not in json.dumps(ev["cuerpo"])   # lista blanca: un dato nuevo de quien paga tampoco
    assert ev["cuerpo"]["payment_id"] == "PAY-1" and ev["cuerpo"]["amount"]["total"] == 200000
    nombres = [a[0] for a in entorno["avisos"]]
    assert {"recarga_acreditada", "recarga_admin", "limpiar_aviso_bajo"} <= set(nombres)


def test_el_mismo_evento_dos_veces_no_acredita_dos_veces(entorno):
    recargas = entorno["recargas"]
    _, ref = _pendiente(entorno)
    cuerpo = _evento(ref=ref)
    assert _webhook(recargas, cuerpo) == (200, "acreditada")
    entorno["avisos"].clear()
    assert _webhook(recargas, cuerpo) == (200, "duplicada")
    assert entorno["libro"].saldo("acme") == 50000 and len(_eventos(entorno["db"])) == 1
    assert entorno["avisos"] == []


def test_otro_evento_con_el_mismo_pago_no_acredita_de_nuevo(entorno):
    recargas = entorno["recargas"]
    _, ref = _pendiente(entorno)
    _, ref2 = _pendiente(entorno)
    assert _webhook(recargas, _evento(ref=ref, evento="ev-1")) == (200, "acreditada")
    assert _webhook(recargas, _evento(ref=ref, evento="ev-2")) == (200, "duplicada")
    # el mismo payment_id contado para OTRA recarga pendiente: tampoco
    assert _webhook(recargas, _evento(ref=ref2, evento="ev-3")) == (200, "duplicada")
    assert entorno["libro"].saldo("acme") == 50000
    assert [r["estado"] for r in _recargas(entorno["db"])] == ["aprobada", "pendiente"]


def test_firma_invalida_no_toca_la_recarga(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    assert _webhook(recargas, _evento(ref=ref), firma=_firma(b"otro cuerpo")) == (401, "firma_invalida")
    assert _webhook(recargas, _evento(ref=ref), firma="") == (401, "firma_invalida")
    assert _recarga(db, rid)["estado"] == "pendiente" and entorno["libro"].saldo("acme") == 0
    evs = _eventos(db)
    assert len(evs) == 2 and all(e["firma_ok"] is False and e["resultado"] == "firma_invalida" for e in evs)
    assert all("paga@ejemplo.com" not in json.dumps(e["cuerpo"]) for e in evs)


def test_un_evento_sin_firma_no_bloquea_el_verdadero_con_el_mismo_id(entorno):
    """Quien adivine el id de un evento y lo mande sin firma no puede hacer que
    el verdadero se tome por repetido."""
    recargas = entorno["recargas"]
    _, ref = _pendiente(entorno)
    cuerpo = _evento(ref=ref, evento="ev-real")
    assert _webhook(recargas, cuerpo, firma="0" * 64) == (401, "firma_invalida")
    assert _webhook(recargas, cuerpo, firma="0" * 64) == (401, "firma_invalida")
    assert _webhook(recargas, cuerpo) == (200, "acreditada")
    assert entorno["libro"].saldo("acme") == 50000


def test_firma_invalida_en_produccion_sin_secreta(entorno, monkeypatch):
    monkeypatch.delenv("BOLD_PRUEBAS")
    _, ref = _pendiente(entorno)
    assert _webhook(entorno["recargas"], _evento(ref=ref))[0] == 401


def test_referencia_desconocida_avisa_al_admin(entorno):
    assert _webhook(entorno["recargas"], _evento(ref="cv-999-1")) == (200, "sin_recarga")
    assert ("admin", "pago_sin_recarga") in entorno["avisos"]
    assert _eventos(entorno["db"])[0]["resultado"] == "sin_recarga"
    assert _movimientos(entorno["db"]) == []


def test_venta_rechazada_marca_la_recarga(entorno):
    rid, ref = _pendiente(entorno)
    assert _webhook(entorno["recargas"], _evento("SALE_REJECTED", ref=ref)) == (200, "rechazada")
    assert _recarga(entorno["db"], rid)["estado"] == "rechazada"
    assert _movimientos(entorno["db"]) == [] and entorno["avisos"] == []


def test_un_pago_aprobado_despues_de_un_rechazo_se_acredita(entorno):
    """La persona reintenta con otra tarjeta en el mismo link: Bold manda
    SALE_REJECTED y después SALE_APPROVED. El dinero entró: se acredita."""
    rid, ref = _pendiente(entorno)
    assert _webhook(entorno["recargas"], _evento("SALE_REJECTED", ref=ref, evento="ev-1", pago="PAY-1")) == (200, "rechazada")
    assert _webhook(entorno["recargas"], _evento(ref=ref, evento="ev-2", pago="PAY-2")) == (200, "acreditada")
    assert _recarga(entorno["db"], rid)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000


def test_un_pago_aprobado_de_una_recarga_que_dimos_por_vencida_se_acredita(entorno):
    """El webhook llega tarde (Bold reintenta hasta 24 h) a una recarga que la
    tarea periódica ya marcó expirada: el pago es real, se acredita."""
    rid, ref = _pendiente(entorno)
    db = entorno["db"]
    with db.conectar() as con:
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(estado="expirada"))
    assert _webhook(entorno["recargas"], _evento(ref=ref)) == (200, "acreditada")
    assert entorno["libro"].saldo("acme") == 50000


def test_anulacion_de_una_aprobada_descuenta_y_avisa(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    _webhook(recargas, _evento(ref=ref, evento="ev-1"))
    entorno["avisos"].clear()
    assert _webhook(recargas, _evento("VOID_APPROVED", ref=None, evento="ev-2")) == (200, "anulada")
    assert _recarga(db, rid)["estado"] == "anulada"
    movs = _movimientos(db)
    assert [(m["tipo"], m["milesimas"], m["concepto"]) for m in movs] == [
        ("recarga", 50000, "recarga_bold"), ("anulacion", -50000, "anulacion_bold")]
    assert entorno["libro"].saldo("acme") == 0
    assert ("admin", "anulacion_bold") in entorno["avisos"]
    # la misma anulación con otro id de evento: no descuenta otra vez
    assert _webhook(recargas, _evento("VOID_APPROVED", evento="ev-3"))[1] != "anulada"
    assert entorno["libro"].saldo("acme") == 0


def test_anulacion_de_una_pendiente_se_ignora(entorno):
    rid, ref = _pendiente(entorno)
    assert _webhook(entorno["recargas"], _evento("VOID_APPROVED", ref=ref)) == (200, "ignorada")
    assert _recarga(entorno["db"], rid)["estado"] == "pendiente" and _movimientos(entorno["db"]) == []


def test_otro_tipo_de_evento_se_ignora(entorno):
    _, ref = _pendiente(entorno)
    assert _webhook(entorno["recargas"], _evento("VOID_REJECTED", ref=ref)) == (200, "ignorada")
    assert _webhook(entorno["recargas"], _evento("ALGO_NUEVO", ref=ref, evento="ev-2")) == (200, "ignorada")


@pytest.mark.parametrize("cuerpo", [b"no es json", b"[1, 2]", b"\xff\xfe", b""])
def test_cuerpo_que_no_es_json(entorno, cuerpo):
    assert _webhook(entorno["recargas"], cuerpo) == (400, "invalido")
    assert _eventos(entorno["db"]) == []


def test_evento_sin_id_es_invalido(entorno):
    cuerpo = json.dumps({"type": "SALE_APPROVED", "data": {}}).encode()
    assert _webhook(entorno["recargas"], cuerpo) == (400, "invalido")


def test_cuerpo_demasiado_grande(entorno):
    cuerpo = b"{" + b" " * 70000 + b"}"
    assert _webhook(entorno["recargas"], cuerpo) == (413, "invalido")
    assert _eventos(entorno["db"]) == []


def test_un_error_inesperado_responde_500_para_que_bold_reintente(entorno, monkeypatch):
    _, ref = _pendiente(entorno)

    def revienta(*a, **k):
        raise RuntimeError("la base se cayó")
    monkeypatch.setattr(entorno["libro"], "acreditar", revienta)
    assert _webhook(entorno["recargas"], _evento(ref=ref)) == (500, "error")
    # nada quedó a medias: ni el evento ni la recarga aprobada
    assert _eventos(entorno["db"]) == [] and _recargas(entorno["db"])[0]["estado"] == "pendiente"
    monkeypatch.undo()


def test_el_webhook_toma_el_candado_antes_de_leer(entorno, escritor_en_medio):
    """Dos entregas del mismo evento a la vez (o el webhook y «Verificar»): la
    segunda espera a que la primera confirme; nadie cambia la recarga entre la
    lectura y la escritura."""
    _, ref = _pendiente(entorno)
    otro = escritor_en_medio("FROM pago_evento", "UPDATE recarga SET estado = 'expirada'")
    assert _webhook(entorno["recargas"], _evento(ref=ref)) == (200, "acreditada")
    assert otro["resultado"].startswith("bloqueado")


def test_verificar_toma_el_candado_antes_de_leer(entorno, escritor_en_medio):
    rid, _ = _pendiente(entorno)
    entorno["status"] = {"status": "PAID", "transaction_id": "PAY-1", "total": 50}
    otro = escritor_en_medio("recarga.id !=", "UPDATE recarga SET estado = 'expirada'")
    assert entorno["recargas"].verificar(rid) == "aprobada"
    assert otro["resultado"].startswith("bloqueado")


# --- verificar (respaldo por consulta) --------------------------------------------------------

def test_verificar_pagado_acredita_una_sola_vez_con_el_webhook(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    entorno["status"] = {"status": "PAID", "transaction_id": "PAY-1", "total": 50}
    assert recargas.verificar(rid) == "aprobada"
    assert _recarga(db, rid)["pago_id"] == "PAY-1"
    assert recargas.verificar(rid) == "aprobada"
    assert _webhook(recargas, _evento(ref=ref)) == (200, "duplicada")
    assert entorno["libro"].saldo("acme") == 50000 and len(_movimientos(db)) == 1


def test_webhook_primero_y_verificar_despues_no_acredita_dos_veces(entorno):
    recargas = entorno["recargas"]
    rid, ref = _pendiente(entorno)
    _webhook(recargas, _evento(ref=ref))
    entorno["status"] = {"status": "PAID", "transaction_id": "PAY-1", "total": 50}
    assert recargas.verificar(rid) == "aprobada"
    assert entorno["consultas"] == 0   # ya no estaba pendiente: ni pregunta
    assert entorno["libro"].saldo("acme") == 50000


def test_verificar_pagado_sin_transaccion_usa_el_link(entorno):
    rid, _ = _pendiente(entorno)
    entorno["status"] = {"status": "PAID", "transaction_id": None, "total": 50}
    assert entorno["recargas"].verificar(rid) == "aprobada"
    assert _recarga(entorno["db"], rid)["pago_id"] == "link:LNK_PRUEBA1"


def test_verificar_activo_y_vencido(entorno):
    recargas = entorno["recargas"]
    rid, _ = _pendiente(entorno)
    assert recargas.verificar(rid) == "pendiente"
    entorno["status"] = {"status": "EXPIRED", "transaction_id": None, "total": None}
    assert recargas.verificar(rid) == "expirada"
    assert _recarga(entorno["db"], rid)["estado"] == "expirada" and _movimientos(entorno["db"]) == []


def test_verificar_con_bold_caido_deja_pendiente(entorno):
    rid, _ = _pendiente(entorno)
    entorno["status"] = entorno["bold"].ErrorBold("No se pudo hablar con Bold (Timeout)")
    assert entorno["recargas"].verificar(rid) == "pendiente"


def test_verificar_ignora_manuales_y_desconocidas(entorno):
    recargas = entorno["recargas"]
    recargas.manual("acme", 10, "admin", "transferencia")
    [manual] = _recargas(entorno["db"])
    assert recargas.verificar(manual["id"]) == "aprobada"
    assert recargas.verificar(9999) is None
    assert entorno["consultas"] == 0


def _envejecer(db, rid, horas):
    viejo = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(creada_en=viejo))


def test_verificar_pendientes(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    nueva, _ = _pendiente(entorno)
    vieja, _ = _pendiente(entorno)
    _envejecer(db, vieja, 30)
    assert recargas.verificar_pendientes() == 2
    assert _recarga(db, nueva)["estado"] == "pendiente"
    assert _recarga(db, vieja)["estado"] == "expirada"


def test_una_vieja_pagada_se_acredita_antes_de_darla_por_vencida(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    vieja, _ = _pendiente(entorno)
    _envejecer(db, vieja, 30)
    entorno["status"] = {"status": "PAID", "transaction_id": "PAY-9", "total": 50}
    recargas.verificar_pendientes()
    assert _recarga(db, vieja)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000


def test_la_tarea_periodica(entorno):
    from tareas import REGISTRO, TIPOS_EXENTOS_DE_COBRO
    from tareas import cobros as tareas_cobros  # noqa: F401 — registra el tipo
    _pendiente(entorno)
    assert "1" in REGISTRO["cobros_verificar_recargas"]({"id": 1, "payload": {}})
    assert "cobros_verificar_recargas" in TIPOS_EXENTOS_DE_COBRO
    import worker
    assert ("cobros_verificar_recargas", 600) in worker.PERIODICAS


# --- manual y ajuste --------------------------------------------------------------------------

def test_recarga_manual(entorno):
    db, recargas = entorno["db"], entorno["recargas"]
    mov_id = recargas.manual("acme", 25.5, "admin", "transferencia")
    [mov] = _movimientos(db)
    assert mov["id"] == mov_id and mov["tipo"] == "recarga" and mov["milesimas"] == 25500
    assert mov["concepto"] == "recarga_manual" and mov["usuario"] == "admin"
    [fila] = _recargas(db)
    assert (fila["medio"], fila["estado"], fila["milesimas"], fila["nota"]) == ("manual", "aprobada", 25500, "transferencia")
    assert re.fullmatch(r"mn-\d+-\d+", fila["referencia"]) and mov["recarga_id"] == fila["id"]
    assert ("recarga_acreditada", ("acme", 25500, "manual")) in entorno["avisos"]


@pytest.mark.parametrize("usd", [0, -5, "x", 1.005, float("nan"), float("inf")])
def test_recarga_manual_invalida(entorno, usd):
    with pytest.raises(ValueError):
        entorno["recargas"].manual("acme", usd, "admin", "nota")
    assert _movimientos(entorno["db"]) == [] and _recargas(entorno["db"]) == []


def test_ajuste(entorno):
    recargas = entorno["recargas"]
    with pytest.raises(ValueError):
        recargas.manual("acme", -3, "admin", "  ", tipo="ajuste")
    recargas.manual("acme", -3.25, "admin", "error de cobro", tipo="ajuste")
    [mov] = _movimientos(entorno["db"])
    assert (mov["tipo"], mov["milesimas"], mov["concepto"], mov["detalle"]) == ("ajuste", -3250, "ajuste", "error de cobro")
    assert _recargas(entorno["db"]) == []   # un ajuste no es una recarga
    with pytest.raises(ValueError):
        recargas.manual("acme", 5, "admin", "x", tipo="regalo")


def test_obtener_y_de_proyecto_no_cruzan_proyectos(entorno):
    recargas = entorno["recargas"]
    rid, _ = _pendiente(entorno)
    assert recargas.obtener("acme", rid)["id"] == rid
    assert recargas.obtener("otro", rid) is None
    assert [r["id"] for r in recargas.de_proyecto("acme")] == [rid]
    assert recargas.de_proyecto("otro") == []


# --- rutas -----------------------------------------------------------------------------------

@pytest.fixture()
def cliente_http(entorno, monkeypatch):
    import dashboard
    from cobros import rutas
    monkeypatch.setattr(rutas, "_ULTIMA_VERIFICACION", {})   # los ids de recarga se repiten entre bases
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


def test_webhook_de_otro_sitio_y_sin_sesion_pasa_las_barreras(entorno, cliente_http):
    c = cliente_http.como(None)
    _, ref = _pendiente(entorno)
    cuerpo = _evento(ref=ref)
    cab = {"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"}
    r = c.post("/pagos/bold/webhook", data=cuerpo, headers={**cab, "x-bold-signature": "0" * 64})
    assert r.status_code == 401 and r.data == b""
    r = c.post("/pagos/bold/webhook", data=cuerpo, headers={**cab, "x-bold-signature": _firma(cuerpo)})
    assert r.status_code == 200 and r.data == b""
    assert entorno["libro"].saldo("acme") == 50000


def test_webhook_con_una_sesion_vieja_no_redirige(entorno, cliente_http):
    """Una cookie de sesión de alguien que ya no existe no convierte el webhook en un 302."""
    c = cliente_http.como("user_acme")
    with c.session_transaction() as s:
        s["usuario"] = "fantasma"
    _, ref = _pendiente(entorno)
    cuerpo = _evento(ref=ref)
    r = c.post("/pagos/bold/webhook", data=cuerpo, headers={"x-bold-signature": _firma(cuerpo)})
    assert r.status_code == 200


def test_webhook_cuerpo_grande_413(entorno, cliente_http):
    c = cliente_http.como(None)
    r = c.post("/pagos/bold/webhook", data=b"x" * 70000, headers={"x-bold-signature": "0" * 64})
    assert r.status_code == 413
    assert _eventos(entorno["db"]) == []


def test_webhook_solo_acepta_post(entorno, cliente_http):
    assert cliente_http.como(None).get("/pagos/bold/webhook").status_code == 405


def test_ninguna_otra_ruta_acepta_un_post_de_otro_sitio(entorno, cliente_http):
    c = cliente_http.como("user_acme")
    r = c.post("/cliente/acme/saldo/recargar", data={"usd": "50"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert _recargas(entorno["db"]) == [] and entorno["links"] == []


def test_recargar_redirige_al_checkout_de_bold(entorno, cliente_http):
    c = cliente_http.como("user_acme")
    r = c.post("/cliente/acme/saldo/recargar", data={"usd": "50"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"] == URL_BOLD
    assert entorno["links"][0]["correo"] == "acme@prueba.local"
    assert _recargas(entorno["db"])[0]["usuario"] == "user_acme"


def test_recargar_monto_invalido_vuelve_al_saldo_con_aviso(entorno, cliente_http):
    c = cliente_http.como("user_acme")
    r = c.post("/cliente/acme/saldo/recargar", data={"usd": "5"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#config-ap-saldo")
    with c.session_transaction() as s:
        assert any("US$" in m for _, m in s.get("_flashes", []))
    assert _recargas(entorno["db"]) == []


def test_recargar_con_bold_caido_avisa_en_palabras(entorno, cliente_http):
    entorno["error_link"] = "Bold no aceptó el pedido (HTTP 500)"
    c = cliente_http.como("user_acme")
    r = c.post("/cliente/acme/saldo/recargar", data={"usd": "50"})
    assert r.headers["Location"].endswith("/cliente/acme#config-ap-saldo")
    with c.session_transaction() as s:
        assert any("HTTP 500" in m for _, m in s.get("_flashes", []))


def test_recargar_proyecto_ajeno_lo_frena_el_guard(entorno, cliente_http):
    c = cliente_http.como("otro")
    r = c.post("/cliente/acme/saldo/recargar", data={"usd": "50"})
    assert r.status_code == 302 and "/cliente/otro" in r.headers["Location"]
    assert _recargas(entorno["db"]) == []


def test_recargar_un_proyecto_que_no_cobra(entorno, cliente_http):
    entorno["libro"].configurar("acme", usuario="admin", cobrar=False)
    r = cliente_http.como("user_acme").post("/cliente/acme/saldo/recargar", data={"usd": "50"})
    assert r.headers["Location"].endswith("/cliente/acme#config-ap-saldo") and entorno["links"] == []
    r = cliente_http.como("admin").post("/cliente/acme/saldo/recargar", data={"usd": "50"})
    assert r.headers["Location"] == URL_BOLD   # el admin sí (para dejar saldo antes de prender «Cobrar»)


def test_recargar_tiene_tope_por_hora(entorno, cliente_http):
    c = cliente_http.como("user_acme")
    for _ in range(10):
        assert c.post("/cliente/acme/saldo/recargar", data={"usd": "10"}).headers["Location"] == URL_BOLD
    r = c.post("/cliente/acme/saldo/recargar", data={"usd": "10"})
    assert r.headers["Location"].endswith("#config-ap-saldo") and len(entorno["links"]) == 10


def test_la_vuelta_de_otro_proyecto_es_404(entorno, cliente_http):
    import cobros.recargas as recargas
    rid = recargas.crear("otro", 50, "otro")["id"]
    c = cliente_http.como("user_acme")
    assert c.get(f"/cliente/acme/saldo/recarga/{rid}").status_code == 404
    assert c.get(f"/cliente/acme/saldo/recarga/{rid}/estado").status_code == 404
    assert c.post(f"/cliente/acme/saldo/recarga/{rid}/verificar").status_code == 404


def test_la_vuelta_no_acredita_por_los_parametros_de_la_url(entorno, cliente_http):
    """Ni siquiera pregunta a Bold: la vuelta pinta el estado guardado. Quien
    acredita es el webhook, el sondeo de /estado o «Verificar»."""
    rid, _ = _pendiente(entorno)
    entorno["status"] = {"status": "PAID", "transaction_id": "PAY-1", "total": 50}
    c = cliente_http.como("user_acme")
    r = c.get(f"/cliente/acme/saldo/recarga/{rid}?bold-tx-status=approved&bold-order-id=x")
    assert r.status_code == 200 and "Verificando tu pago" in r.get_data(as_text=True)
    assert _recarga(entorno["db"], rid)["estado"] == "pendiente" and entorno["libro"].saldo("acme") == 0
    assert entorno["consultas"] == 0


def test_estado_json_verifica_como_mucho_cada_3_segundos(entorno, cliente_http):
    rid, _ = _pendiente(entorno)
    c = cliente_http.como("user_acme")
    j = c.get(f"/cliente/acme/saldo/recarga/{rid}/estado").get_json()
    assert j["estado"] == "pendiente" and j["texto"] and "US$" in j["saldo_texto"]
    c.get(f"/cliente/acme/saldo/recarga/{rid}/estado")
    assert entorno["consultas"] == 1
    entorno["status"] = {"status": "PAID", "transaction_id": "PAY-1", "total": 50}
    j = c.get(f"/cliente/acme/saldo/recarga/{rid}/estado").get_json()
    assert j["estado"] == "pendiente" and entorno["consultas"] == 1   # dentro de los 3 s: no pregunta
    import cobros.rutas as rutas
    rutas._ULTIMA_VERIFICACION.clear()   # como si pasaran los 3 s
    j = c.get(f"/cliente/acme/saldo/recarga/{rid}/estado").get_json()
    assert j["estado"] == "aprobada" and "50" in j["texto"] and "50" in j["saldo_texto"]


def test_boton_verificar(entorno, cliente_http):
    rid, _ = _pendiente(entorno)
    entorno["status"] = {"status": "EXPIRED", "transaction_id": None, "total": None}
    c = cliente_http.como("user_acme")
    r = c.post(f"/cliente/acme/saldo/recarga/{rid}/verificar")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#config-ap-saldo")
    assert _recarga(entorno["db"], rid)["estado"] == "expirada"

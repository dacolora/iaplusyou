"""Escenarios de error del módulo de pagos contra el SANDBOX de Wompi (pedido de Daniel, 2026-10-12: «hagamos todo,
los escenarios de error»). Corre el código de verdad (`cobros.recargas`, `cobros.planes`, `cobros.wompi`) contra la API
de pruebas de Wompi, con las tarjetas y celulares de prueba que Wompi publica, sobre una base SQLite temporal. Nada
toca producción ni cuesta plata: si las llaves no son de pruebas, no corre.

    venv/bin/python3 deploy/prueba_wompi_sandbox.py [ruta del archivo con las llaves de pruebas]

Las llaves las pone Daniel en `.env.wompi-sandbox` (git lo ignora); el script nunca las imprime. Sin eventos (el
servidor local no recibe los de Wompi): lo que no responde en el acto se resuelve como en producción sin evento,
consultando la transacción o buscándola por su referencia (PND-296). Sale con 1 si algún escenario falla.

Tarjetas de prueba (wompi-api.md §10): 4242 4242 4242 4242 aprueba, 4111 1111 1111 1111 rechaza. Nequi: 3991111111
aprueba, 3992222222 rechaza.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

APRUEBA, RECHAZA = "4242424242424242", "4111111111111111"
NEQUI_APRUEBA, NEQUI_RECHAZA = "3991111111", "3992222222"
CORREO = "sandbox@creatvmachine.com"
NOMBRES = ("WOMPI_LLAVE_PUBLICA", "WOMPI_LLAVE_PRIVADA", "WOMPI_SECRETO_EVENTOS", "WOMPI_SECRETO_INTEGRIDAD")


def _cargar_llaves(ruta):
    """Lee las cuatro llaves sin imprimirlas y se niega si alguna no es de pruebas."""
    if not os.path.isfile(ruta):
        sys.exit(f"No encuentro {ruta}: pon ahí las llaves de PRUEBAS de Wompi (ver el docstring).")
    valores = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip()
    faltan = [n for n in NOMBRES if not valores.get(n)]
    if faltan:
        sys.exit(f"Faltan en {ruta}: {', '.join(faltan)}")
    prefijos = {"WOMPI_LLAVE_PUBLICA": "pub_test_", "WOMPI_LLAVE_PRIVADA": "prv_test_",
                "WOMPI_SECRETO_EVENTOS": "test_events_", "WOMPI_SECRETO_INTEGRIDAD": "test_integrity_"}
    for nombre, prefijo in prefijos.items():
        if not valores[nombre].startswith(prefijo):
            sys.exit(f"{nombre} no es una llave de PRUEBAS (tiene que empezar por {prefijo}): no corro nada.")
    os.environ.update({n: valores[n] for n in NOMBRES})


def _preparar(carpeta):
    """Base temporal, servidor «local» y avisos a una lista (ni un correo, ni una carpeta en clientes/)."""
    os.environ["CREATV_DB_URL"] = f"sqlite:///{os.path.join(carpeta, 'creatv.db')}"
    os.environ["PLATAFORMA_URL"] = "http://localhost:5050"
    for nombre in ("BOLD_LLAVE_IDENTIDAD", "BOLD_LLAVE_SECRETA", "BOLD_PRUEBAS"):
        os.environ.pop(nombre, None)
    import db
    import notificaciones
    import proyectos
    db.crear_todo()
    avisos = []
    notificaciones.avisar = lambda cliente, tipo, asunto, cuerpo: avisos.append((cliente, tipo)) and False
    notificaciones.avisar_admin = lambda tipo, asunto, cuerpo, cliente="": avisos.append(("admin", tipo)) and 0
    proyectos._path = lambda cliente: os.path.join(carpeta, "clientes", cliente, "proyecto.json")
    from cobros import recargas, wompi
    recargas._en_segundo_plano = lambda fn: fn()   # los avisos en el acto (como en las pruebas): se comprueban enseguida
    if not (wompi.configurado() and wompi.pruebas() and wompi.base_url() == wompi.SANDBOX):
        sys.exit("Wompi no quedó en el sandbox: no corro nada.")
    return db, avisos


# ---------------------------------------------------------------- Wompi de pruebas (lo que hace el navegador) ---

def _api(verbo, ruta, *, llave, cuerpo=None):
    import requests
    from cobros import wompi
    r = getattr(requests, verbo)(wompi.base_url() + ruta, json=cuerpo, timeout=(5, 20), allow_redirects=False,
                                 headers={"Authorization": f"Bearer {llave}", "Accept": "application/json"})
    try:
        j = r.json()
    except ValueError:
        j = {}
    if r.status_code >= 400:
        raise RuntimeError(f"Wompi {verbo.upper()} {ruta} → HTTP {r.status_code}: {str(j)[:300]}")
    return j.get("data") if isinstance(j, dict) else None


def token_tarjeta(numero):
    """Lo que hace el widget: tokenizar una tarjeta de PRUEBAS (`POST /tokens/cards`, llave pública)."""
    from cobros import wompi
    vence = datetime.now() + timedelta(days=400)
    d = _api("post", "/tokens/cards", llave=wompi._publica(), cuerpo={
        "number": numero, "cvc": "123", "exp_month": f"{vence.month:02d}", "exp_year": str(vence.year)[2:],
        "card_holder": "Prueba Sandbox"})
    return d["id"]


def aceptacion():
    from cobros import wompi
    a = wompi.aceptaciones()
    return {"acceptance_token": a["acceptance_token"], "personal_token": a["personal_token"],
            "acepta_terminos": True, "acepta_datos": True, "autoriza_cobro": True}


def pagar_en_checkout(referencia, centavos, numero):
    """Lo que hace la persona en el checkout: una transacción con tarjeta por esa referencia y ese monto."""
    from cobros import wompi
    a = wompi.aceptaciones()
    d = _api("post", "/transactions", llave=wompi._privada(), cuerpo={
        "amount_in_cents": int(centavos), "currency": "COP", "customer_email": CORREO, "reference": referencia,
        "signature": wompi.firma_integridad(referencia, int(centavos)), "acceptance_token": a["acceptance_token"],
        "payment_method": {"type": "CARD", "token": token_tarjeta(numero), "installments": 1}})
    return d["id"]


def esperar_final(tx_id, segundos=60):
    """El sandbox resuelve las tarjetas en unos segundos: espera un estado final."""
    from cobros import wompi
    fin = time.time() + segundos
    while time.time() < fin:
        tx = wompi.transaccion(tx_id)
        if tx.get("status") not in ("PENDING", ""):
            return tx
        time.sleep(2)
    return wompi.transaccion(tx_id)


def anular(tx_id):
    from cobros import wompi
    return _api("post", f"/transactions/{tx_id}/void", llave=wompi._privada())


# --------------------------------------------------------------------------------------------- utilidades ---

def _hace(minutos):
    return (datetime.now() - timedelta(minutes=minutos)).isoformat(timespec="seconds")


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _filas(db, tabla, **filtro):
    import sqlalchemy as sa
    t = getattr(db, tabla)
    q = sa.select(t).order_by(t.c.id)
    for k, v in filtro.items():
        q = q.where(getattr(t.c, k) == v)
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(q).all()]


def _envejecer_recarga(db, rid, minutos):
    with db.conectar() as con:
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(creada_en=_hace(minutos)))


def _movs(db, cliente):
    return [(m["tipo"], m["milesimas"]) for m in _filas(db, "movimiento_saldo", cliente=cliente)]


def _sus(db, cliente):
    filas = _filas(db, "suscripcion", cliente=cliente)
    return filas[-1] if filas else None


class Fallo(AssertionError):
    pass


def esperar(cond, mensaje):
    if not cond:
        raise Fallo(mensaje)


# ------------------------------------------------------------------------------------------------ escenarios ---

def e_recarga_pagada_sin_evento(db, avisos):
    """PND-296 contra Wompi de verdad: la recarga se paga, el evento no llega (local), y la periódica la encuentra
    buscando su referencia, la relee por id y la acredita una vez."""
    from cobros import libro, recargas
    libro.configurar("sb_recarga", usuario="sandbox", cobrar=True)
    r = recargas.crear("sb_recarga", 10, "sandbox", correo=CORREO)
    fila = _filas(db, "recarga", id=r["id"])[0]
    tx_id = pagar_en_checkout(fila["referencia"], fila["total_pago"], APRUEBA)
    tx = esperar_final(tx_id)
    esperar(tx["status"] == "APPROVED", f"el sandbox no aprobó la 4242: {tx['status']}")
    esperar(recargas.verificar_pendientes() >= 0 and _filas(db, "recarga", id=r["id"])[0]["estado"] == "pendiente",
            "una recarga recién creada no se busca (MINUTOS_RESCATE)")
    _envejecer_recarga(db, r["id"], recargas.MINUTOS_RESCATE + 1)
    recargas.verificar_pendientes()
    fila = _filas(db, "recarga", id=r["id"])[0]
    esperar(fila["estado"] == "aprobada" and fila["pasarela_ref"] == tx_id, f"no se rescató: {fila['estado']}")
    esperar(_movs(db, "sb_recarga") == [("recarga", 10000)], f"movimientos: {_movs(db, 'sb_recarga')}")
    esperar(("admin", "wompi_rescatada") in avisos, "falta el aviso wompi_rescatada al admin")
    recargas.verificar_pendientes()
    esperar(_movs(db, "sb_recarga") == [("recarga", 10000)], "la segunda vuelta acreditó otra vez")
    return {"recarga": r["id"], "transaccion": tx_id, "saldo": libro.saldo("sb_recarga")}


def e_recarga_rechazada(db, avisos):
    """Tarjeta rechazada en el checkout: la recarga queda rechazada y no suma nada."""
    from cobros import libro, recargas
    libro.configurar("sb_rechazo", usuario="sandbox", cobrar=True)
    r = recargas.crear("sb_rechazo", 10, "sandbox", correo=CORREO)
    fila = _filas(db, "recarga", id=r["id"])[0]
    tx = esperar_final(pagar_en_checkout(fila["referencia"], fila["total_pago"], RECHAZA))
    esperar(tx["status"] in ("DECLINED", "ERROR"), f"el sandbox no rechazó la 4111: {tx['status']}")
    _envejecer_recarga(db, r["id"], recargas.MINUTOS_RESCATE + 1)
    recargas.verificar_pendientes()
    fila = _filas(db, "recarga", id=r["id"])[0]
    esperar(fila["estado"] == "rechazada", f"estado {fila['estado']}")
    esperar(libro.saldo("sb_rechazo") == 0, "una recarga rechazada sumó saldo")
    return {"recarga": r["id"], "status_wompi": tx["status"]}


def e_recarga_anulada(db, avisos, previo):
    """Wompi anula la recarga aprobada: `verificar` la ve VOIDED, la anula y descuenta el saldo."""
    from cobros import libro, recargas
    tx_id, rid = previo["transaccion"], previo["recarga"]
    anular(tx_id)
    tx = esperar_final(tx_id)
    esperar(tx["status"] == "VOIDED", f"Wompi no la anuló: {tx['status']}")
    recargas.verificar(rid)
    fila = _filas(db, "recarga", id=rid)[0]
    esperar(fila["estado"] == "anulada", f"estado {fila['estado']}")
    esperar(_movs(db, "sb_recarga") == [("recarga", 10000), ("anulacion", -10000)], f"movs {_movs(db, 'sb_recarga')}")
    esperar(("admin", "anulacion_wompi") in avisos, "falta el aviso de anulación al admin")
    return {"saldo": libro.saldo("sb_recarga")}


def _plan(precio=1, anual=None):
    from cobros import planes
    return planes.crear_plan(f"Sandbox {time.time_ns()}", precio, 1.25, tope_incluido_usd=0.5,
                             precio_anual_usd=anual, usuario="sandbox", activo=True)


def _alta(cliente, plan_id, numero, ciclo="mensual", precio_visto=1):
    from cobros import libro, planes
    libro.configurar(cliente, usuario="sandbox", cobrar=True)
    return planes.suscribir(cliente, plan_id, ciclo, "CARD", token_tarjeta(numero), CORREO, aceptacion(), "sandbox",
                            precio_visto)


def _resolver(cliente, alta, segundos=60):
    """Sin evento: la pantalla sondea el pago con `verificar_pago` hasta un estado final."""
    from cobros import planes
    fin = time.time() + segundos
    estado = alta["estado"]
    while estado == "pendiente" and time.time() < fin:
        time.sleep(2)
        estado = planes.verificar_pago(cliente, alta["pago_id"])
    return estado


def e_alta_rechazada(db, avisos):
    """Alta con tarjeta rechazada: la suscripción termina, sin periodo ni bolsa."""
    pid = _plan()
    alta = _alta("sb_alta_mala", pid, RECHAZA)
    estado = _resolver("sb_alta_mala", alta)
    esperar(estado in ("rechazado", "error"), f"pago {estado}")
    s = _sus(db, "sb_alta_mala")
    esperar(s["estado"] == "terminada", f"suscripción {s['estado']}")
    esperar(_filas(db, "periodo_plan", cliente="sb_alta_mala") == [], "abrió un periodo")
    esperar(_movs(db, "sb_alta_mala") == [], f"movimientos {_movs(db, 'sb_alta_mala')}")
    return {"pago": estado, "suscripcion": s["estado"]}


def e_alta_y_renovacion(db, avisos):
    """Alta aprobada y una renovación forzada sin acceptance_token (el cobro mensual)."""
    from cobros import planes
    pid = _plan()
    alta = _alta("sb_ok", pid, APRUEBA)
    esperar(_resolver("sb_ok", alta) == "aprobado", "el alta no se aprobó")
    s = _sus(db, "sb_ok")
    cubierto = s["cubierto_hasta"]
    r = planes.cobrar_periodo(s["id"], forzar=True)
    if r == "pendiente":
        pago = _filas(db, "pago_plan", cliente="sb_ok")[-1]
        r = _resolver("sb_ok", {"estado": "pendiente", "pago_id": pago["id"]})
    esperar(r == "aprobado", f"renovación {r}")
    s = _sus(db, "sb_ok")
    esperar(s["cubierto_hasta"] > cubierto, "la renovación no corrió lo pagado")
    esperar([m for m in _movs(db, "sb_ok") if m[0] == "plan"] == [("plan", 1000)], "más de una bolsa hoy")
    return {"cubierto_hasta": s["cubierto_hasta"], "pagos": len(_filas(db, "pago_plan", cliente="sb_ok"))}


def e_gracia_y_actualizar_tarjeta(db, avisos):
    """La tarjeta guardada empieza a rechazar: morosa con su reintento; «Actualizar tarjeta» cobra en el acto."""
    from cobros import planes
    pid = _plan()
    alta = _alta("sb_morosa", pid, APRUEBA)
    esperar(_resolver("sb_morosa", alta) == "aprobado", "el alta no se aprobó")
    planes.cambiar_fuente("sb_morosa", "CARD", token_tarjeta(RECHAZA), CORREO, aceptacion(), "sandbox")
    s = _sus(db, "sb_morosa")
    r = planes.cobrar_periodo(s["id"], forzar=True)
    if r == "pendiente":
        pago = _filas(db, "pago_plan", cliente="sb_morosa")[-1]
        r = _resolver("sb_morosa", {"estado": "pendiente", "pago_id": pago["id"]})
    s = _sus(db, "sb_morosa")
    esperar(r in ("rechazado", "error") and s["estado"] == "morosa" and s["intentos_fallidos"] == 1,
            f"cobro {r}, suscripción {s['estado']} con {s['intentos_fallidos']} rechazos")
    esperar(("sb_morosa", "plan_rechazado") in avisos, "el cliente no recibió el aviso del rechazo")
    cambio = planes.cambiar_fuente("sb_morosa", "CARD", token_tarjeta(APRUEBA), CORREO, aceptacion(), "sandbox")
    r2 = cambio.get("cobro")
    if r2 == "pendiente":
        pago = _filas(db, "pago_plan", cliente="sb_morosa")[-1]
        r2 = _resolver("sb_morosa", {"estado": "pendiente", "pago_id": pago["id"]})
    s = _sus(db, "sb_morosa")
    esperar(r2 == "aprobado" and s["estado"] == "activa" and s["intentos_fallidos"] == 0,
            f"tras actualizar la tarjeta: cobro {r2}, suscripción {s['estado']}")
    return {"tras_rechazo": "morosa", "tras_actualizar": s["estado"]}


def e_tres_rechazos_terminan(db, avisos):
    """Tres rechazos de la renovación (al momento, a las 24 h y a las 48 h): la suscripción termina."""
    from cobros import planes
    pid = _plan()
    alta = _alta("sb_tres", pid, APRUEBA)
    esperar(_resolver("sb_tres", alta) == "aprobado", "el alta no se aprobó")
    planes.cambiar_fuente("sb_tres", "CARD", token_tarjeta(RECHAZA), CORREO, aceptacion(), "sandbox")
    s = _sus(db, "sb_tres")
    vence = datetime.fromisoformat(s["cubierto_hasta"])
    momentos = [vence - timedelta(minutes=30), vence + timedelta(hours=24), vence + timedelta(hours=48, minutes=5)]
    historial = []
    for ahora in momentos:
        r = planes.cobrar_periodo(s["id"], ahora=_iso(ahora))
        if r == "pendiente":
            pago = _filas(db, "pago_plan", cliente="sb_tres")[-1]
            r = _resolver("sb_tres", {"estado": "pendiente", "pago_id": pago["id"]})
        s = _sus(db, "sb_tres")
        historial.append((r, s["estado"], s["intentos_fallidos"]))
    esperar(historial[-1][1] == "terminada", f"después de tres rechazos: {historial}")
    esperar(("sb_tres", "plan_terminado") in avisos, "el cliente no recibió el aviso de plan terminado")
    aprobados = [p for p in _filas(db, "pago_plan", cliente="sb_tres") if p["estado"] == "aprobado"]
    esperar(len(aprobados) == 1, f"pagos aprobados: {len(aprobados)} (solo el alta)")
    return {"historial": historial}


def e_anual(db, avisos):
    """Un anual: un solo cobro, doce meses; el mes 2 abre su bolsa sin cobrar otra vez."""
    from cobros import planes
    pid = _plan(precio=1, anual=10)
    alta = _alta("sb_anual", pid, APRUEBA, ciclo="anual", precio_visto=10)
    esperar(_resolver("sb_anual", alta) == "aprobado", "el anual no se aprobó")
    periodo = _filas(db, "periodo_plan", cliente="sb_anual")[0]
    s = _sus(db, "sb_anual")
    esperar(datetime.fromisoformat(s["cubierto_hasta"]) >= datetime.fromisoformat(periodo["inicio"]) + timedelta(days=360),
            f"cubre hasta {s['cubierto_hasta']}")
    planes.renovar_todo(ahora=_iso(datetime.fromisoformat(periodo["fin"]) + timedelta(minutes=1)))
    periodos = _filas(db, "periodo_plan", cliente="sb_anual")
    esperar(len(periodos) == 2 and periodos[0]["cerrado"], f"periodos tras el mes 1: {len(periodos)}")
    esperar(len(_filas(db, "pago_plan", cliente="sb_anual")) == 1, "el mes 2 volvió a cobrar")
    tipos = [m[0] for m in _movs(db, "sb_anual")]
    esperar(tipos.count("plan") == 2 and tipos.count("vencimiento") == 1, f"movimientos {tipos}")
    return {"periodos": len(periodos), "credito_mes": periodos[1]["credito_milesimas"]}


def e_anulacion_de_plan(db, avisos):
    """Wompi anula el pago del alta: el pago queda anulado y la suscripción cancelada, sin cobrarse sola otra vez."""
    from cobros import planes, wompi
    pid = _plan()
    alta = _alta("sb_void", pid, APRUEBA)
    esperar(_resolver("sb_void", alta) == "aprobado", "el alta no se aprobó")
    pago = _filas(db, "pago_plan", cliente="sb_void")[-1]
    anular(pago["transaccion_id"])
    tx = esperar_final(pago["transaccion_id"])
    esperar(tx["status"] == "VOIDED", f"Wompi no la anuló: {tx['status']}")
    r = planes.aplicar_transaccion(wompi.transaccion(pago["transaccion_id"]))
    s = _sus(db, "sb_void")
    esperar(r == "anulado" and s["estado"] == "cancelada" and not s["renovar"], f"{r}, suscripción {s['estado']}")
    esperar(("admin", "plan_admin") in avisos, "falta el aviso al admin")
    return {"pago": r, "suscripcion": s["estado"]}


def e_cobro_incierto_se_encuentra(db, avisos):
    """PND-296 en planes: el cobro de la renovación SÍ llega a Wompi pero la respuesta se pierde; al reintentar se
    encuentra por su referencia y se aplica sin reenviar."""
    from cobros import planes, wompi
    pid = _plan()
    alta = _alta("sb_incierto", pid, APRUEBA)
    esperar(_resolver("sb_incierto", alta) == "aprobado", "el alta no se aprobó")
    s = _sus(db, "sb_incierto")
    original, envios = wompi.cobrar_fuente, []

    def se_pierde_la_respuesta(*a, **k):
        envios.append(k.get("acceptance_token"))
        original(*a, **k)                                        # Wompi sí lo recibe y lo cobra
        raise wompi.ErrorWompi("No se pudo hablar con Wompi (ReadTimeout)", caida=True, incierto=True)
    wompi.cobrar_fuente = se_pierde_la_respuesta
    try:
        r = planes.cobrar_periodo(s["id"], forzar=True)
    finally:
        wompi.cobrar_fuente = original
    pago = _filas(db, "pago_plan", cliente="sb_incierto")[-1]
    esperar(pago["estado"] == "pendiente" and pago["transaccion_id"] is None, f"tras perderse: {r}, {pago['estado']}")
    with db.conectar() as con:                                   # pasó el «en vuelo»: toca reintentar
        con.execute(db.pago_plan.update().where(db.pago_plan.c.id == pago["id"])
                    .values(actualizado_en="2000-01-01T00:00:00"))
    time.sleep(3)
    contados = []
    wompi.cobrar_fuente = lambda *a, **k: contados.append(1) or original(*a, **k)
    try:
        r2 = planes.cobrar_periodo(s["id"], forzar=True)
    finally:
        wompi.cobrar_fuente = original
    pago = _filas(db, "pago_plan", id=pago["id"])[0]
    esperar(contados == [], "reenvió el cobro en vez de encontrarlo")
    esperar(pago["estado"] in ("aprobado", "pendiente") and pago["transaccion_id"], f"{r2}: {pago['estado']}")
    if pago["estado"] == "pendiente":
        r2 = _resolver("sb_incierto", {"estado": "pendiente", "pago_id": pago["id"]})
    esperar(_filas(db, "pago_plan", id=pago["id"])[0]["estado"] == "aprobado", f"al final: {r2}")
    return {"resultado": r2}


def e_nequi(db, avisos):
    """Nequi: el celular que aprueba deja suscribirse; el que rechaza no. (El sandbox no dice si el débito de cada
    mes pide aprobar en la app: eso solo se ve con un Nequi real.)"""
    from cobros import libro, planes, wompi
    pid = _plan()
    libro.configurar("sb_nequi", usuario="sandbox", cobrar=True)
    malo = wompi.token_nequi(NEQUI_RECHAZA)
    token = wompi.token_nequi(NEQUI_APRUEBA)
    fin, estado, estado_malo = time.time() + 90, "PENDING", "PENDING"
    while time.time() < fin and "PENDING" in (estado, estado_malo):
        time.sleep(3)
        estado = wompi.estado_token_nequi(token, tiempo=(5, 15)) if estado == "PENDING" else estado
        estado_malo = wompi.estado_token_nequi(malo, tiempo=(5, 15)) if estado_malo == "PENDING" else estado_malo
    esperar(estado == "APPROVED", f"token de Nequi que aprueba: {estado}")
    esperar(estado_malo != "APPROVED", f"token de Nequi que rechaza: {estado_malo}")
    alta = planes.suscribir("sb_nequi", pid, "mensual", "NEQUI", token, CORREO, aceptacion(), "sandbox", 1)
    r = _resolver("sb_nequi", alta, segundos=120)
    esperar(r == "aprobado", f"alta con Nequi: {r}")
    s = _sus(db, "sb_nequi")
    r2 = planes.cobrar_periodo(s["id"], forzar=True)
    if r2 == "pendiente":
        pago = _filas(db, "pago_plan", cliente="sb_nequi")[-1]
        r2 = _resolver("sb_nequi", {"estado": "pendiente", "pago_id": pago["id"]}, segundos=120)
    return {"token_malo": estado_malo, "alta": r, "renovacion": r2}


ESCENARIOS = [
    ("Recarga pagada sin evento → la periódica la encuentra (PND-296)", e_recarga_pagada_sin_evento),
    ("Recarga con tarjeta rechazada", e_recarga_rechazada),
    ("Recarga anulada por Wompi", e_recarga_anulada),
    ("Alta con tarjeta rechazada", e_alta_rechazada),
    ("Alta aprobada + renovación sin contrato", e_alta_y_renovacion),
    ("Renovación rechazada → morosa → actualizar tarjeta", e_gracia_y_actualizar_tarjeta),
    ("Tres rechazos → el plan termina", e_tres_rechazos_terminan),
    ("Plan anual: un cobro, doce meses", e_anual),
    ("Anulación del pago de un plan", e_anulacion_de_plan),
    ("Cobro incierto que sí llegó → se encuentra sin reenviar (PND-296)", e_cobro_incierto_se_encuentra),
    ("Nequi: aprueba y rechaza", e_nequi),
]


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, ".env.wompi-sandbox")
    if not os.path.isfile(ruta):
        ruta = os.path.expanduser("~/Documents/GitHub/iaplusyou/.env.wompi-sandbox")
    _cargar_llaves(ruta)
    carpeta = tempfile.mkdtemp(prefix="creatv_sandbox_wompi_")
    resultados, previo = [], None
    try:
        db, avisos = _preparar(carpeta)
        for nombre, fn in ESCENARIOS:
            inicio = time.time()
            try:
                if fn is e_recarga_anulada:
                    if previo is None:
                        raise Fallo("sin la recarga aprobada del primer escenario")
                    salida = fn(db, avisos, previo)
                else:
                    salida = fn(db, avisos)
                if fn is e_recarga_pagada_sin_evento:
                    previo = salida
                resultados.append({"escenario": nombre, "ok": True, "detalle": salida})
            except Fallo as e:
                resultados.append({"escenario": nombre, "ok": False, "detalle": str(e)})
            except Exception as e:  # noqa: BLE001 — un escenario roto no frena los demás
                resultados.append({"escenario": nombre, "ok": False,
                                   "detalle": f"{type(e).__name__}: {str(e)[:300]}",
                                   "traza": traceback.format_exc(limit=4)})
            r = resultados[-1]
            print(f"{'OK   ' if r['ok'] else 'FALLA'} {nombre} ({time.time() - inicio:.0f} s): "
                  f"{json.dumps(r['detalle'], ensure_ascii=False, default=str)[:400]}", flush=True)
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    salida = os.environ.get("SANDBOX_SALIDA")
    if salida:
        with open(salida, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2, default=str)
    fallidos = [r for r in resultados if not r["ok"]]
    print(f"\n{len(resultados) - len(fallidos)} de {len(resultados)} escenarios bien.")
    sys.exit(1 if fallidos else 0)


if __name__ == "__main__":
    main()

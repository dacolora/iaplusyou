"""Recargas de Wompi anuladas (2026-10-15): PND-328, una aprobación tardía con todo firmado no acredita una recarga
cuya transacción Wompi ya anuló, y PND-304 (b), una recarga APROBADA que Wompi anula después y cuyo aviso se pierde
la encuentra la periódica, que hace el reverso una sola vez y avisa al admin. Wompi falso, base temporal."""
from datetime import datetime, timedelta

import sqlalchemy as sa

from tests.test_recargas_wompi import (TODAS, _admin, _ahora_ts, _ev, _evento, _movimientos, _pendiente, _recarga,
                                       _tx, entorno)  # noqa: F401 — fixture

TX = "1292-1602113476-10985"


def _aprobada(entorno):  # noqa: F811
    """Una recarga acreditada por su evento (relee y cuadra) hace 3 h: pasarela_ref = TX."""
    rid, ref = _aprobada_con_id(entorno, TX)
    entorno["consultas"].clear()
    entorno["avisos"].clear()
    return rid, ref


def _aprobada_con_id(entorno, tx_id, horas=3):  # noqa: F811
    """Acreditada por su evento con todo firmado, creada y aprobada hace `horas` (la revisión cuenta desde la
    aprobación: una recién aprobada no se vuelve a preguntar enseguida)."""
    rid, ref = _pendiente(entorno)
    entorno["txs"][tx_id] = _tx(ref, tx_id=tx_id)
    assert _ev(entorno, _evento(_tx(ref, tx_id=tx_id), props=TODAS))[1] == "acreditada"
    _hace(entorno, rid, hours=horas)
    return rid, ref


def _hace(entorno, rid, **tiempo):  # noqa: F811
    """Creada y aprobada hace `tiempo`."""
    db = entorno["db"]
    cuando = (datetime.now() - timedelta(**tiempo)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(creada_en=cuando, actualizada_en=cuando))


def _kv(entorno, prefijo):  # noqa: F811
    db = entorno["db"]
    with db.conectar() as con:
        return dict(con.execute(sa.select(db.kv.c.clave, db.kv.c.valor).where(db.kv.c.clave.like(f"{prefijo}%"))).all())


# --- PND-328: la aprobación que llega después de la anulación ----------------------------------------------------

def test_una_aprobacion_firmada_que_llega_despues_de_la_anulacion_no_acredita(entorno):  # noqa: F811
    # Los eventos llegan en desorden: primero VOIDED (Wompi aprobó y anuló) y después el APPROVED, con todo firmado
    # (sin releer). Antes el VOIDED de una pendiente se ignoraba y el APPROVED acreditaba un pago anulado.
    db = entorno["db"]
    rid, ref = _pendiente(entorno)
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS)) == (200, "anulada_sin_acreditar")
    fila = _recarga(db, rid)
    assert fila["estado"] == "anulada" and fila["pasarela_ref"] == TX
    assert _movimientos(db) == [] and entorno["libro"].saldo("acme") == 0
    assert _admin(entorno) == ["anulacion_wompi"]
    tarde = _evento(_tx(ref), props=TODAS, ts=_ahora_ts() + 1)
    assert _ev(entorno, tarde) == (200, "ya_anulada")
    assert entorno["libro"].saldo("acme") == 0 and _movimientos(db) == [] and entorno["consultas"] == []
    assert _recarga(db, rid)["estado"] == "anulada"


def test_la_anulacion_sin_firma_completa_se_relee_y_tambien_cuenta(entorno):  # noqa: F811
    db = entorno["db"]
    rid, ref = _pendiente(entorno)
    entorno["txs"][TX] = _tx(ref, status="VOIDED")
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED")))[1] == "anulada_sin_acreditar"
    assert [c[0] for c in entorno["consultas"]] == [TX]
    assert _ev(entorno, _evento(_tx(ref), props=TODAS, ts=_ahora_ts() + 1))[1] == "ya_anulada"
    assert entorno["libro"].saldo("acme") == 0 and _recarga(db, rid)["estado"] == "anulada"


def test_la_anulacion_de_una_rechazada_o_vencida_tambien_la_marca(entorno):  # noqa: F811
    # Una rechazada (la persona reintentó en el mismo checkout) y una vencida siguen siendo acreditables: una
    # anulación de una transacción suya tiene que quedar dicha, igual que en una pendiente.
    db = entorno["db"]
    rid, ref = _pendiente(entorno)
    assert _ev(entorno, _evento(_tx(ref, status="DECLINED", tx_id="1292-1602113476-20000"), props=TODAS))[1] == \
        "rechazada"
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))[1] == "anulada_sin_acreditar"
    fila = _recarga(db, rid)
    assert fila["estado"] == "anulada" and fila["pasarela_ref"] == TX
    assert _ev(entorno, _evento(_tx(ref), props=TODAS, ts=_ahora_ts() + 1))[1] == "ya_anulada"
    assert entorno["libro"].saldo("acme") == 0


def test_otra_aprobada_de_una_recarga_anulada_sin_acreditar_la_acredita_y_avisa(entorno):  # noqa: F811
    # Dos pestañas: una pagó y Wompi la anuló; la otra se aprobó después. La recarga nunca se acreditó: ese pago
    # bueno la acredita solo (una vez: UNIQUE(tipo, recarga_id)) y el admin se entera (revisión de plata 2026-10-15).
    db = entorno["db"]
    rid, ref = _pendiente(entorno)
    _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))
    entorno["avisos"].clear()
    otra = _tx(ref, tx_id="1292-1602113476-30000")
    assert _ev(entorno, _evento(otra, props=TODAS))[1] == "acreditada_otra"
    fila = _recarga(db, rid)
    assert (fila["estado"], fila["pasarela_ref"]) == ("aprobada", "1292-1602113476-30000")
    assert entorno["libro"].saldo("acme") == 50000 and [m["concepto"] for m in _movimientos(db)] == ["recarga_wompi"]
    assert "anulacion_wompi" in _admin(entorno) and ("recarga_acreditada", ("acme", 50000, "Wompi")) in entorno["avisos"]
    assert _ev(entorno, _evento(otra, props=TODAS, ts=_ahora_ts() + 1))[1] == "duplicada"
    assert _ev(entorno, _evento(_tx(ref), props=TODAS, ts=_ahora_ts() + 2))[1] == "ya_anulada"   # la anulada, tarde
    assert entorno["libro"].saldo("acme") == 50000


def test_la_anulacion_de_otra_transaccion_no_cierra_una_recarga_aprobada(entorno):  # noqa: F811
    # La recarga ya está aprobada con TX; un VOIDED de otra transacción de la misma referencia no la anula.
    db = entorno["db"]
    rid, ref = _aprobada(entorno)
    otra = _tx(ref, status="VOIDED", tx_id="1292-1602113476-30000")
    assert _ev(entorno, _evento(otra, props=TODAS))[1] == "ignorada"
    assert _recarga(db, rid)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000


def test_la_vuelta_dice_que_un_pago_anulado_antes_de_acreditar_no_cambia_el_saldo(entorno):  # noqa: F811
    from cobros import rutas
    import dashboard
    rid, ref = _pendiente(entorno)
    _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))
    with dashboard.app.test_request_context():
        texto = rutas.texto_estado(_recarga(entorno["db"], rid))
    assert "antes de que lo sumáramos" in texto and "descontamos" not in texto
    rid2, _ref2 = _aprobada_con_id(entorno, "1292-1602113476-40000")
    entorno["txs"]["1292-1602113476-40000"] = {**entorno["txs"]["1292-1602113476-40000"], "status": "VOIDED"}
    _ev(entorno, _evento(entorno["txs"]["1292-1602113476-40000"], props=TODAS))
    with dashboard.app.test_request_context():
        assert "descontamos" in rutas.texto_estado(_recarga(entorno["db"], rid2))


# --- PND-304 (b): la periódica mira las aprobadas recientes ------------------------------------------------------

def test_la_periodica_encuentra_una_aprobada_que_wompi_anulo_y_hace_el_reverso(entorno):  # noqa: F811
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _aprobada(entorno)
    entorno["txs"][TX] = _tx(ref, status="VOIDED")      # Wompi la anuló y su evento se perdió
    recargas.verificar_pendientes()
    assert _recarga(db, rid)["estado"] == "anulada" and entorno["libro"].saldo("acme") == 0
    assert [m["concepto"] for m in _movimientos(db)] == ["recarga_wompi", "anulacion_wompi"]
    assert [c[0] for c in entorno["consultas"]] == [TX]
    assert _admin(entorno) == ["anulacion_wompi"]


def test_el_reverso_de_la_periodica_nunca_se_aplica_dos_veces(entorno):  # noqa: F811
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _aprobada(entorno)
    entorno["txs"][TX] = _tx(ref, status="VOIDED")
    recargas.verificar_pendientes()
    _kv_borrar(entorno, "wompi:revision:")              # aunque tocara revisarla otra vez
    recargas.verificar_pendientes()
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))[1] == "ignorada"   # el evento tardío
    assert recargas.revisar_aprobadas() == 0
    assert [m["concepto"] for m in _movimientos(db)] == ["recarga_wompi", "anulacion_wompi"]
    assert entorno["libro"].saldo("acme") == 0 and _admin(entorno) == ["anulacion_wompi"]


def test_si_el_evento_de_anulacion_llego_la_periodica_no_hace_nada_mas(entorno):  # noqa: F811
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _aprobada(entorno)
    entorno["txs"][TX] = _tx(ref, status="VOIDED")
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))[1] == "anulada"
    entorno["consultas"].clear()
    recargas.verificar_pendientes()
    assert entorno["consultas"] == [] and len(_movimientos(db)) == 2


def test_una_aprobada_que_sigue_aprobada_no_se_toca_ni_se_avisa(entorno):  # noqa: F811
    db, recargas = entorno["db"], entorno["recargas"]
    rid, _ref = _aprobada(entorno)
    recargas.verificar_pendientes()
    assert [c[0] for c in entorno["consultas"]] == [TX]
    assert _recarga(db, rid)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000
    assert entorno["avisos"] == [] and len(_movimientos(db)) == 1


def test_las_aprobadas_se_revisan_espaciadas_y_solo_las_de_30_dias(entorno):  # noqa: F811
    recargas = entorno["recargas"]
    rid, _ref = _aprobada(entorno)
    recargas.verificar_pendientes()
    recargas.verificar_pendientes()                     # recién revisada: no se vuelve a preguntar
    assert [c[0] for c in entorno["consultas"]] == [TX]
    _marca_vieja(entorno, rid, horas=1)
    recargas.verificar_pendientes()
    assert len(entorno["consultas"]) == 1
    _marca_vieja(entorno, rid, horas=3)                 # los dos primeros días, cada 2 h
    recargas.verificar_pendientes()
    assert len(entorno["consultas"]) == 2
    _hace(entorno, rid, days=10)
    _marca_vieja(entorno, rid, horas=3)                 # después, una vez al día
    recargas.verificar_pendientes()
    assert len(entorno["consultas"]) == 2
    _marca_vieja(entorno, rid, horas=25)
    recargas.verificar_pendientes()
    assert len(entorno["consultas"]) == 3
    _hace(entorno, rid, days=recargas.DIAS_REVISAR_APROBADAS + 1)
    _marca_vieja(entorno, rid, horas=25)
    assert _kv(entorno, "wompi:revision:")
    recargas.verificar_pendientes()
    assert len(entorno["consultas"]) == 3               # más de 30 días: ya no se pregunta
    assert _kv(entorno, "wompi:revision:") == {}        # y su marca se limpia


def test_la_revision_no_acepta_una_anulacion_que_no_cuadra(entorno):  # noqa: F811
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _aprobada(entorno)
    entorno["txs"][TX] = {**_tx(ref, status="VOIDED"), "merchant": {"public_key": "pub_test_OTRO"}}  # llave-de-prueba
    recargas.verificar_pendientes()
    assert _recarga(db, rid)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000
    assert _admin(entorno) == ["wompi_no_cuadra"]


def test_la_revision_para_con_wompi_caido_sin_tocar_nada(entorno):  # noqa: F811
    db, recargas = entorno["db"], entorno["recargas"]
    rid1, _ = _aprobada(entorno)
    rid2, ref2 = _aprobada_con_id(entorno, "1292-1602113476-50000")
    entorno["consultas"].clear()
    entorno["txs"][TX] = entorno["wompi"].ErrorWompi("No se pudo hablar con Wompi (Timeout)", caida=True)
    entorno["txs"]["1292-1602113476-50000"] = entorno["wompi"].ErrorWompi("caído", caida=True)
    recargas.verificar_pendientes()
    assert len(entorno["consultas"]) == 1               # para a la primera caída
    assert _recarga(db, rid1)["estado"] == _recarga(db, rid2)["estado"] == "aprobada"
    assert entorno["libro"].saldo("acme") == 100000


def test_la_revision_respeta_su_cupo_por_vuelta(entorno, monkeypatch):  # noqa: F811
    recargas = entorno["recargas"]
    for i in range(3):
        _aprobada_con_id(entorno, f"1292-1602113476-6000{i}")
    entorno["consultas"].clear()
    monkeypatch.setattr(recargas, "REVISIONES_POR_VUELTA", 2)
    assert recargas.revisar_aprobadas() == 2 and len(entorno["consultas"]) == 2
    assert recargas.revisar_aprobadas() == 1            # la que quedó, en la vuelta siguiente


def test_la_revision_toma_el_candado_antes_de_leer(entorno, escritor_en_medio):  # noqa: F811
    rid, ref = _aprobada(entorno)
    entorno["txs"][TX] = _tx(ref, status="VOIDED")
    otro = escritor_en_medio("recarga.pasarela_ref = ", "UPDATE recarga SET estado = 'expirada'")
    entorno["recargas"].revisar_aprobadas()
    assert otro["resultado"].startswith("bloqueado")
    assert _recarga(entorno["db"], rid)["estado"] == "anulada"


def _marca_vieja(entorno, rid, horas):  # noqa: F811
    db = entorno["db"]
    cuando = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.kv.update().where(db.kv.c.clave == f"wompi:revision:{rid}").values(valor=cuando))


def _kv_borrar(entorno, prefijo):  # noqa: F811
    db = entorno["db"]
    with db.conectar() as con:
        con.execute(db.kv.delete().where(db.kv.c.clave.like(f"{prefijo}%")))


def test_una_recien_aprobada_no_se_vuelve_a_preguntar_en_la_misma_vuelta(entorno):  # noqa: F811
    # La periódica acredita una pendiente (consulta por id) y la revisión de aprobadas no la relee enseguida.
    recargas = entorno["recargas"]
    rid, ref = _pendiente(entorno)
    entorno["txs"][TX] = _tx(ref, status="PENDING")
    _ev(entorno, _evento(_tx(ref, status="PENDING"), props=TODAS))
    entorno["txs"][TX] = _tx(ref)
    recargas.verificar_pendientes()
    assert _recarga(entorno["db"], rid)["estado"] == "aprobada"
    assert [c[0] for c in entorno["consultas"]] == [TX]


# --- revisión de plata (guardian-gasto, 2026-10-15): dos pestañas, una anulada y otra pagada ----------------------

Y = "1292-1602113476-77777"


def test_dos_pestanas_la_anulada_no_esconde_la_otra_pagada_cuyo_evento_se_perdio(entorno):  # noqa: F811
    # Pestaña 1: X se aprueba y Wompi la anula (llega su VOIDED). Pestaña 2: Y se aprueba y su evento se pierde.
    # Antes del cambio el rescate encontraba Y en la pendiente; la anulada tiene que seguir buscándose (26 h) y Y
    # llega al admin como segundo pago (no se acredita sola: lo decide el admin, como cualquier segundo pago).
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))[1] == "anulada_sin_acreditar"
    entorno["avisos"].clear()
    _envejecer_min(entorno, rid, recargas.MINUTOS_RESCATE + 1)
    entorno["por_ref"][ref] = [_tx(ref, status="VOIDED"), _tx(ref, tx_id=Y)]
    entorno["txs"][Y] = _tx(ref, tx_id=Y)
    recargas.verificar_pendientes()
    assert entorno["busquedas"] == [ref]
    assert "anulacion_wompi" in _admin(entorno)                      # se acreditó con Y y el admin lo sabe
    assert entorno["libro"].saldo("acme") == 50000 and _recarga(db, rid)["pasarela_ref"] == Y


def test_la_pendiente_de_nequi_que_se_aprueba_despues_de_la_anulacion_llega_al_admin(entorno):  # noqa: F811
    # Escenario A del guardian: Y (Nequi) PENDING guardada; X (tarjeta) aprobada y anulada pisa la recarga; Y se
    # aprueba y su evento se pierde.
    recargas = entorno["recargas"]
    rid, ref = _pendiente(entorno)
    assert _ev(entorno, _evento(_tx(ref, status="PENDING", tx_id=Y), props=TODAS))[1] == "pendiente"
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))[1] == "anulada_sin_acreditar"
    entorno["avisos"].clear()
    _envejecer_min(entorno, rid, recargas.MINUTOS_RESCATE + 1)
    entorno["por_ref"][ref] = [_tx(ref, status="VOIDED"), _tx(ref, tx_id=Y)]
    entorno["txs"][Y] = _tx(ref, tx_id=Y)
    recargas.verificar_pendientes()
    assert "anulacion_wompi" in _admin(entorno) and entorno["libro"].saldo("acme") == 50000


def test_el_rescate_no_busca_las_anuladas_que_si_se_acreditaron_ni_las_viejas(entorno):  # noqa: F811
    recargas = entorno["recargas"]
    rid, ref = _aprobada(entorno)                              # acreditada y después anulada: ya se descontó
    entorno["txs"][TX] = _tx(ref, status="VOIDED")
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))[1] == "anulada"
    rid2, ref2 = _pendiente(entorno)                           # anulada sin acreditar, pero de hace más de 26 h
    _ev(entorno, _evento(_tx(ref2, status="VOIDED", tx_id="1292-1602113476-88888"), props=TODAS))
    _envejecer_min(entorno, rid2, (recargas.HORAS_VIGENTE + 1) * 60)
    entorno["busquedas"].clear()      # la anulación de la acreditada ya buscó si había otro pago (punto 1)
    recargas.verificar_pendientes()
    assert entorno["busquedas"] == []


def test_el_aviso_de_la_anulada_sin_acreditar_pide_mirar_si_hay_otro_pago(entorno, monkeypatch):  # noqa: F811
    from cobros import avisos
    textos = []
    monkeypatch.setattr(avisos, "admin", lambda tipo, asunto, cuerpo, cliente="": textos.append(cuerpo()))
    _rid, ref = _pendiente(entorno)
    _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))
    (cuerpo,) = textos
    assert "otra transacción aprobada" in cuerpo and "no lo suma" not in cuerpo


def test_lo_visto_aprobado_en_la_vuelta_y_despues_anulado_no_avisa_sin_evento(entorno):  # noqa: F811
    import json
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _pendiente(entorno)
    entorno["txs"][TX] = _tx(ref)
    assert recargas.consultar(rid, TX) == "APPROVED"           # la vuelta lo vio aprobado
    _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))
    hace = (datetime.now() - timedelta(minutes=31)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.kv.update().where(db.kv.c.clave == f"wompi:visto:{rid}")
                    .values(valor=json.dumps({"tx": TX, "visto_en": hace})))
    entorno["avisos"].clear()
    recargas.avisar_vistos_sin_evento()
    assert "wompi_sin_evento" not in _admin(entorno) and _kv(entorno, "wompi:visto:") == {}


def _envejecer_min(entorno, rid, minutos):  # noqa: F811
    db = entorno["db"]
    hace = (datetime.now() - timedelta(minutes=minutos)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(creada_en=hace))



# --- segunda revisión de plata (2026-10-15): la anulación de la acreditada con otro pago aprobado ------------------

T2 = "1292-1602113476-22222"
T3 = "1292-1602113476-33333"


def _textos_admin(entorno, monkeypatch):  # noqa: F811
    from cobros import avisos
    textos = []
    monkeypatch.setattr(avisos, "admin", lambda tipo, asunto, cuerpo, cliente="": (
        textos.append((tipo, cuerpo() if callable(cuerpo) else cuerpo)), entorno["avisos"].append(("admin", tipo))))
    return textos


def _con_segundo_pago(entorno):  # noqa: F811
    """Acreditada con TX (T1); otra pestaña pagó T2 y llegó como segundo pago; después el admin anula T1 en Wompi."""
    rid, ref = _aprobada(entorno)
    assert _ev(entorno, _evento(_tx(ref, tx_id=T2), props=TODAS))[1] == "otro_pago"
    entorno["txs"][TX] = _tx(ref, status="VOIDED")
    entorno["txs"][T2] = _tx(ref, tx_id=T2)
    entorno["por_ref"][ref] = [_tx(ref, status="VOIDED"), _tx(ref, tx_id=T2)]
    entorno["avisos"].clear()
    return rid, ref


def test_anular_la_acreditada_con_otro_pago_aprobado_no_descuenta_y_la_pasa_al_otro(entorno, monkeypatch):  # noqa: F811
    db = entorno["db"]
    rid, ref = _con_segundo_pago(entorno)
    textos = _textos_admin(entorno, monkeypatch)
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))[1] == "reemplazada"
    fila = _recarga(db, rid)
    assert (fila["estado"], fila["pasarela_ref"]) == ("aprobada", T2)
    assert entorno["libro"].saldo("acme") == 50000 and [m["concepto"] for m in _movimientos(db)] == ["recarga_wompi"]
    ((tipo, cuerpo),) = textos
    assert tipo == "anulacion_wompi" and T2 in cuerpo and TX in cuerpo
    # La aprobación tardía de T1 (ya anulada) no la da por «segundo pago» otra vez.
    assert _ev(entorno, _evento(_tx(ref), props=TODAS, ts=_ahora_ts() + 1))[1] == "ya_anulada"
    # Y si después también se anula T2, ahí sí se descuenta (no queda otro pago).
    entorno["txs"][T2] = _tx(ref, tx_id=T2, status="VOIDED")
    entorno["por_ref"][ref] = [_tx(ref, status="VOIDED"), _tx(ref, tx_id=T2, status="VOIDED")]
    assert _ev(entorno, _evento(_tx(ref, tx_id=T2, status="VOIDED"), props=TODAS))[1] == "anulada"
    assert entorno["libro"].saldo("acme") == 0


def test_la_periodica_tampoco_descuenta_si_hay_otro_pago_aprobado(entorno):  # noqa: F811
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _con_segundo_pago(entorno)
    recargas.revisar_aprobadas()
    fila = _recarga(db, rid)
    assert (fila["estado"], fila["pasarela_ref"]) == ("aprobada", T2) and entorno["libro"].saldo("acme") == 50000


def test_si_no_se_puede_saber_si_hay_otro_pago_se_frena_el_reverso_y_se_avisa(entorno, monkeypatch):  # noqa: F811
    db, recargas = entorno["db"], entorno["recargas"]
    rid, ref = _con_segundo_pago(entorno)
    textos = _textos_admin(entorno, monkeypatch)
    entorno["por_ref"][ref] = entorno["wompi"].ErrorWompi("No se pudo hablar con Wompi (Timeout)", caida=True)
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS)) == (500, "error")   # Wompi reintenta
    recargas.revisar_aprobadas()
    assert _recarga(db, rid)["estado"] == "aprobada" and entorno["libro"].saldo("acme") == 50000
    assert [t for t, _c in textos] == ["anulacion_wompi"]            # un solo aviso del freno
    assert "no descontamos" in textos[0][1].lower()
    entorno["por_ref"][ref] = [_tx(ref, status="VOIDED")]             # Wompi responde: no hay otro pago
    entorno["txs"][T2] = _tx(ref, tx_id=T2, status="VOIDED")
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS, ts=_ahora_ts() + 1))[1] == "anulada"
    assert entorno["libro"].saldo("acme") == 0


def test_el_aviso_de_anulacion_nombra_las_otras_aprobadas_que_no_cuadran(entorno, monkeypatch):  # noqa: F811
    textos = _textos_admin(entorno, monkeypatch)
    rid, ref = _aprobada(entorno)
    entorno["txs"][TX] = _tx(ref, status="VOIDED")
    entorno["por_ref"][ref] = [_tx(ref, status="VOIDED"), _tx(ref, tx_id=T3, centavos=999)]
    entorno["txs"][T3] = _tx(ref, tx_id=T3, centavos=999)          # aprobada, pero no es de este monto
    assert _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))[1] == "anulada"
    assert entorno["libro"].saldo("acme") == 0
    (cuerpo,) = [c for t, c in textos if t == "anulacion_wompi"]
    assert T3 in cuerpo


# --- el aviso «acredítala a mano» una sola vez, también tras un reinicio --------------------------------------------

def test_el_aviso_de_segundo_pago_no_se_repite_tras_un_reinicio(entorno, monkeypatch):  # noqa: F811
    recargas = entorno["recargas"]
    _rid, ref = _aprobada(entorno)
    assert _ev(entorno, _evento(_tx(ref, tx_id=T2), props=TODAS))[1] == "otro_pago"
    monkeypatch.setattr(recargas, "_AVISADOS_NO_CUADRA", set())    # el proceso se reinició
    assert _ev(entorno, _evento(_tx(ref, tx_id=T2), props=TODAS, ts=_ahora_ts() + 1))[1] == "otro_pago"
    assert _admin(entorno).count("wompi_no_cuadra") == 1


def test_una_aprobacion_que_wompi_ya_anulo_no_manda_no_cuadra_y_anulacion_a_la_vez(entorno):  # noqa: F811
    # El evento dice APPROVED (sin todo firmado) y al releer Wompi ya la tiene anulada: es el estado que cambió, no
    # un evento que miente. Un solo aviso: la anulación.
    rid, ref = _aprobada(entorno)
    entorno["txs"][TX] = _tx(ref, status="VOIDED")
    assert _ev(entorno, _evento(_tx(ref), ts=_ahora_ts() + 1))[1] == "anulada"
    assert _admin(entorno) == ["anulacion_wompi"]

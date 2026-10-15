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


def test_otra_aprobada_de_una_recarga_anulada_sin_acreditar_va_al_admin(entorno):  # noqa: F811
    # Dos pestañas: una pagó y Wompi la anuló; la otra se aprobó después. No se acredita sola (la recarga ya está
    # cerrada): el admin la ve como segundo pago y decide.
    rid, ref = _pendiente(entorno)
    _ev(entorno, _evento(_tx(ref, status="VOIDED"), props=TODAS))
    entorno["avisos"].clear()
    otra = _tx(ref, tx_id="1292-1602113476-30000")
    assert _ev(entorno, _evento(otra, props=TODAS))[1] == "otro_pago"
    assert entorno["libro"].saldo("acme") == 0 and _admin(entorno) == ["wompi_no_cuadra"]


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

"""Pagos de plan anulados por Wompi (los gemelos de PND-328 y PND-304 b en las recargas).

PND-340: los eventos llegan en desorden. Un VOIDED de un pago de plan todavía pendiente lo deja anulado sin crédito y
la aprobación que llega después no lo acredita. PND-341: la periódica relee los pagos de plan aprobados de los últimos
30 días; si Wompi anuló uno y su evento se perdió, hace lo mismo que el evento y el admin sabe que no llegó."""
from datetime import datetime, timedelta

import pytest

from tests.test_planes import (CENTAVOS_MES, T0, _despues, _filas, _sus, _suscribir, _tipos, avisos, falso,  # noqa: F401
                               planes, pro)


def _avisos_admin(enviados):
    return [e for e in enviados if e[0] == "admin:plan_admin"]


# ------------------------------------------------------------------ PND-340 ---

def test_una_anulacion_antes_de_la_aprobacion_no_deja_acreditar_el_alta(base_temporal, planes, pro, falso, avisos):
    falso.defecto = "PENDING"                                       # el alta queda esperando a Wompi
    _suscribir(planes, pro)
    (pago,) = _filas(base_temporal, "pago_plan")
    assert pago.estado == "pendiente" and pago.transaccion_id
    tx = dict(falso.txs[pago.transaccion_id])

    assert planes.aplicar_transaccion({**tx, "status": "VOIDED"}, ahora=_despues(T0, minutos=5)) == \
        "anulado_sin_acreditar"
    (pago,) = _filas(base_temporal, "pago_plan")
    assert pago.estado == "anulado" and pago.transaccion_id == tx["id"]
    s = _sus(base_temporal)
    assert (s.estado, s.renovar, s.proximo_cobro, s.cubierto_hasta) == ("cancelada", False, None, None)
    (aviso,) = _avisos_admin(avisos)
    assert "antes de que lo aplicáramos" in aviso[3] and pago.referencia in aviso[3]

    # La aprobación tardía de esa misma transacción, aunque venga entera: ni crédito, ni periodo, ni otro aviso.
    assert planes.aplicar_transaccion({**tx, "status": "APPROVED"}, ahora=_despues(T0, minutos=6)) == "ya_anulada"
    assert _filas(base_temporal, "pago_plan")[0].estado == "anulado"
    assert _filas(base_temporal, "movimiento_saldo", tipo="plan") == []
    assert _filas(base_temporal, "periodo_plan") == []
    assert len(_avisos_admin(avisos)) == 1
    # Sin nada pagado y sin renovación, la periódica la termina; la tarjeta no se vuelve a cobrar.
    planes.renovar_todo(ahora=_despues(T0, horas=1))
    assert _sus(base_temporal).estado == "terminada" and len(falso.posts) == 1


def test_una_anulacion_antes_de_la_aprobacion_no_deja_acreditar_una_renovacion(base_temporal, planes, pro, falso,
                                                                              avisos):
    _suscribir(planes, pro)                                         # el alta, aprobada: cubre hasta el 2026-11-09
    falso.defecto = "PENDING"
    assert planes.cobrar_periodo(1, ahora=_despues(T0, minutos=1), forzar=True) == "pendiente"
    renovacion = _filas(base_temporal, "pago_plan")[1]
    tx = dict(falso.txs[renovacion.transaccion_id])
    cubierto = _sus(base_temporal).cubierto_hasta

    assert planes.aplicar_transaccion({**tx, "status": "VOIDED"}) == "anulado_sin_acreditar"
    assert planes.aplicar_transaccion({**tx, "status": "APPROVED"}) == "ya_anulada"
    s = _sus(base_temporal)
    assert s.cubierto_hasta == cubierto and s.estado == "cancelada" and not s.renovar   # lo del alta sigue
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="plan")) == 1             # solo el del alta
    assert [p.estado for p in _filas(base_temporal, "pago_plan")] == ["aprobado", "anulado"]


def test_el_evento_firmado_de_la_aprobacion_tardia_tampoco_acredita(base_temporal, planes, pro, falso, avisos,
                                                                    monkeypatch):
    """De punta a punta por el gancho de los eventos (`recargas._plan_de_evento`): con todo firmado no se relee."""
    from cobros import recargas
    falso.defecto = "PENDING"
    _suscribir(planes, pro)
    (pago,) = _filas(base_temporal, "pago_plan")
    tx = dict(falso.txs[pago.transaccion_id])
    monkeypatch.setattr(recargas, "_todo_firmado", lambda ev: True)
    assert recargas._plan_de_evento({}, {**tx, "status": "VOIDED"}) == "anulado_sin_acreditar"
    assert recargas._plan_de_evento({}, {**tx, "status": "APPROVED"}) == "ya_anulada"
    assert _filas(base_temporal, "movimiento_saldo", tipo="plan") == []


def test_un_aprobado_anulado_que_vuelve_a_llegar_aprobado_no_avisa_de_mas(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    tx = dict(falso.txs["1292-1-1"])
    assert planes.aplicar_transaccion({**tx, "status": "VOIDED"}, ahora=_despues(T0, dias=1)) == "anulado"
    antes = len(_avisos_admin(avisos))
    assert planes.aplicar_transaccion({**tx, "status": "APPROVED"}, ahora=_despues(T0, dias=1)) == "ya_anulada"
    assert len(_avisos_admin(avisos)) == antes
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="plan")) == 1


# ------------------------------------------------------------------ PND-341 ---

def _hace(**tiempo):
    return (datetime.now() - timedelta(**tiempo)).isoformat(timespec="seconds")


def _fechar_pagos(db, creado, aprobado=None):
    with db.conectar() as con:
        con.execute(db.pago_plan.update().values(creado_en=creado, actualizado_en=aprobado or creado))


@pytest.fixture()
def revision(base_temporal):
    from cobros import planes_revision
    return planes_revision


def test_la_periodica_encuentra_la_anulacion_cuyo_evento_no_llego(base_temporal, planes, pro, falso, avisos, revision):
    _suscribir(planes, pro)
    _fechar_pagos(base_temporal, _hace(hours=5))
    (pago,) = _filas(base_temporal, "pago_plan")
    falso.txs[pago.transaccion_id]["status"] = "VOIDED"            # Wompi la anuló; el evento se perdió

    assert revision.revisar_aprobados() == 1
    (pago,) = _filas(base_temporal, "pago_plan")
    assert pago.estado == "anulado"
    s = _sus(base_temporal)
    assert s.estado == "cancelada" and not s.renovar and s.proximo_cobro is None
    assert all(p.cerrado for p in _filas(base_temporal, "periodo_plan"))   # la bolsa de ese pago venció
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="vencimiento")) == 1
    (aviso,) = _avisos_admin(avisos)
    assert "su evento no llegó" in aviso[3] and pago.referencia in aviso[3]
    # Otra vuelta (o el evento tardío) no descuenta dos veces.
    assert revision.revisar_aprobados() == 0
    assert planes.aplicar_transaccion(dict(falso.txs[pago.transaccion_id])) == "ya_aplicada"
    assert len(_filas(base_temporal, "movimiento_saldo", tipo="vencimiento")) == 1 and len(_avisos_admin(avisos)) == 1


def test_un_pago_que_sigue_aprobado_no_cambia_y_se_espacia(base_temporal, planes, pro, falso, avisos, revision,
                                                          monkeypatch):
    from cobros import wompi
    _suscribir(planes, pro)
    _fechar_pagos(base_temporal, _hace(hours=5))
    leidas = []
    original = wompi.transaccion
    monkeypatch.setattr(wompi, "transaccion", lambda i, tiempo=None: leidas.append(i) or original(i))
    assert revision.revisar_aprobados() == 1 and len(leidas) == 1
    assert _filas(base_temporal, "pago_plan")[0].estado == "aprobado" and _avisos_admin(avisos) == []
    assert revision.revisar_aprobados() == 0 and len(leidas) == 1           # recién revisado: espera 2 h
    # Recién aprobado: tampoco se relee en la misma vuelta.
    _fechar_pagos(base_temporal, _hace(minutes=10))
    with base_temporal.conectar() as con:
        con.execute(base_temporal.kv.delete().where(base_temporal.kv.c.clave.like("planes:revision:%")))
    assert revision.revisar_aprobados() == 0


def test_solo_los_ultimos_30_dias_y_solo_con_wompi_configurado(base_temporal, planes, pro, falso, avisos, revision,
                                                              monkeypatch):
    from cobros import wompi
    _suscribir(planes, pro)
    _fechar_pagos(base_temporal, _hace(days=31))
    assert revision.revisar_aprobados() == 0
    _fechar_pagos(base_temporal, _hace(days=3))
    monkeypatch.setattr(wompi, "configurado", lambda: False)
    assert revision.revisar_aprobados() == 0
    monkeypatch.setattr(wompi, "configurado", lambda: True)
    assert revision.revisar_aprobados() == 1


def test_wompi_caido_para_la_pasada(base_temporal, planes, pro, falso, avisos, revision, monkeypatch):
    from cobros import wompi
    _suscribir(planes, pro)
    _suscribir(planes, pro, cliente="otro")
    _fechar_pagos(base_temporal, _hace(hours=5))
    llamadas = []

    def caido(i, tiempo=None):
        llamadas.append(i)
        raise wompi.ErrorWompi("caído", caida=True)
    monkeypatch.setattr(wompi, "transaccion", caido)
    assert revision.revisar_aprobados() == 1 and len(llamadas) == 1
    assert [p.estado for p in _filas(base_temporal, "pago_plan")] == ["aprobado", "aprobado"]


def test_una_transaccion_de_otra_referencia_no_se_aplica(base_temporal, planes, pro, falso, avisos, revision):
    _suscribir(planes, pro)
    _fechar_pagos(base_temporal, _hace(hours=5))
    (pago,) = _filas(base_temporal, "pago_plan")
    falso.txs[pago.transaccion_id].update(status="VOIDED", reference="pl-99-20261109-1")
    assert revision.revisar_aprobados() == 1
    assert _filas(base_temporal, "pago_plan")[0].estado == "aprobado" and _avisos_admin(avisos) == []


def test_la_periodica_de_planes_corre_la_revision_y_un_fallo_no_la_tumba(base_temporal, monkeypatch):
    from cobros import planes, planes_revision
    from tareas import planes as tarea
    monkeypatch.setattr(planes, "renovar_todo", lambda: {"cerrados": 0, "abiertos": 0, "cobros": {}})
    corridas = []
    monkeypatch.setattr(planes_revision, "revisar_aprobados", lambda: corridas.append(1) or 0)
    tarea.renovar({})
    assert corridas == [1]

    def roto():
        raise RuntimeError("base ocupada")
    monkeypatch.setattr(planes_revision, "revisar_aprobados", roto)
    assert "periodos cerrados" in tarea.renovar({})

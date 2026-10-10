"""Alertas del plan mensual (planes 8/8, spec 2026-10-09 §7.6): `cobros:plan_morosa` (bloquea), `plan_renueva`
(info, 3 días antes), `plan_cancelada` (info) y `plan_bolsa_80` (atención), más la recarga pendiente que ahora cubre
Bold y Wompi. Wompi y la TRM son falsos; la base es real.

Lo que no se negocia: un proyecto sin plan no tiene ninguna, las huellas salen de cifras y fechas (nunca del texto
traducido) y las consultas no crecen con lo que haya pasado."""
import pytest
import sqlalchemy as sa

from tests.test_planes import T0, _despues, _suscribir, avisos, falso, planes, pro  # noqa: F401  (fixtures)
from tests.test_cobros_alertas import _consultas, _recarga

CLAVES = ("cobros:plan_morosa", "cobros:plan_renueva", "cobros:plan_cancelada", "cobros:plan_bolsa_80")
HACE_20_MIN = "2026-10-09T09:40:00"


@pytest.fixture()
def cobra(base_temporal, monkeypatch, tmp_path):
    import proyectos
    from cobros import libro
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    libro.configurar("acme", usuario="admin", cobrar=True, margen=2.0)
    return libro


def _plan_de(clave_de_alertas, alertas_):
    return [a for a in alertas_ if a["clave"] in clave_de_alertas]


def _cobro(db, milesimas, cuando=T0, cliente="acme"):
    with db.conectar() as con:
        con.execute(db.movimiento_saldo.insert().values(cliente=cliente, creado_en=cuando, tipo="cobro",
                                                        milesimas=-milesimas, concepto="video", extra={"margen": 1.25}))


def _alertas(cliente, ahora):
    import alertas
    return alertas._fuente_cobros(cliente, ahora)


def test_un_proyecto_sin_plan_no_tiene_alertas_de_plan(cobra, base_temporal):
    import db
    assert _plan_de(CLAVES, _alertas("acme", "2026-10-20T10:00:00")) == []
    import alertas
    _, n = _consultas(db, alertas._alertas_plan, "acme", "2026-10-20T10:00:00", str)
    assert n == 1                                              # solo buscar la suscripción


def test_un_proyecto_que_no_cobra_no_las_tiene_aunque_tenga_plan(base_temporal, planes, pro, falso, avisos):
    _suscribir(planes, pro)                                   # «Cobrar» nunca se prendió
    assert _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=29))) == []


def test_con_el_periodo_a_la_mitad_no_hay_nada_que_avisar(cobra, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    assert _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=10))) == []


def test_renueva_tres_dias_antes_con_la_fecha_y_el_monto_aceptado(cobra, planes, pro, falso, avisos):
    _suscribir(planes, pro)                                   # cubierto hasta 2026-11-09 10:00
    antes = _despues(T0, dias=27, horas=5)                    # 4 días antes: todavía no
    assert _plan_de(CLAVES, _alertas("acme", antes)) == []
    a, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=30)))     # 2026-11-08: a un día
    assert a["clave"] == "cobros:plan_renueva" and a["nivel"] == "info" and a["solo_admin"] is False
    assert a["tab"] == "settings" and a["ancla"] == "config-ap-plan"
    assert "1.000" in a["detalle"] or "1,000" in a["detalle"]
    assert "noviembre" in a["detalle"] or "November" in a["detalle"]
    # La renovación cobra el precio que la persona aceptó, no el del plan de hoy.
    planes.editar_plan(pro, usuario="admin", precio_usd=1500)
    b, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=30)))
    assert b["huella"] == a["huella"] and "1.500" not in b["detalle"] and "1,500" not in b["detalle"]


def test_la_huella_de_renueva_sigue_a_la_fecha_y_al_monto_no_al_texto(cobra, planes, pro, falso, avisos, monkeypatch):
    import alertas
    from flask_babel import gettext as real
    _suscribir(planes, pro)
    a, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=30)))
    monkeypatch.setattr(alertas, "gettext", lambda texto, **k: "otro texto " + real(texto, **k))
    b, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=30)))
    assert a["detalle"] != b["detalle"] and a["huella"] == b["huella"]
    assert alertas.huella("plan_renueva", "2026-11-09T10:00:00", 1000) == a["huella"]


def test_una_activacion_a_mano_avisa_que_termina_y_no_que_se_renueva(cobra, planes, pro, falso, avisos):
    planes.activar_manual("acme", pro, "mensual", "admin", "transferencia", ahora=T0)
    a, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=30)))
    assert a["clave"] == "cobros:plan_cancelada" and a["nivel"] == "info"


def test_cancelada_avisa_hasta_cuando_dura_y_se_calla_al_terminar(cobra, planes, pro, falso, avisos):
    _suscribir(planes, pro)
    planes.cancelar("acme", "user_acme", ahora=_despues(T0, dias=2))
    a, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=3)))
    assert a["clave"] == "cobros:plan_cancelada" and a["nivel"] == "info" and a["ancla"] == "config-ap-plan"
    assert "noviembre" in a["titulo"] or "November" in a["titulo"]
    assert "cobros:plan_renueva" not in [x["clave"] for x in _alertas("acme", _despues(T0, dias=30))]
    assert _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=40))) == []      # ya pasó el fin


def test_morosa_bloquea_y_lleva_a_actualizar_la_tarjeta(cobra, planes, pro, falso, avisos):
    import db
    _suscribir(planes, pro)
    with db.conectar() as con:
        con.execute(db.suscripcion.update().values(estado="morosa", intentos_fallidos=1))
    a, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=30)))        # morosa no avisa renovación ni bolsa
    assert a["clave"] == "cobros:plan_morosa" and a["nivel"] == "bloquea" and a["solo_admin"] is False
    assert a["tab"] == "settings" and a["ancla"] == "config-ap-plan" and a["grupo"] == "puesta_a_punto"
    assert "2 reintentos" in a["detalle"] and "Configuración › Plan" in a["detalle"]
    with db.conectar() as con:
        con.execute(db.suscripcion.update().values(intentos_fallidos=2))
    b, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=30)))
    assert "1 reintento" in b["detalle"] and b["huella"] != a["huella"]       # un descarte no esconde el siguiente intento


def test_la_bolsa_avisa_al_80_por_ciento_una_huella_por_periodo(cobra, planes, pro, falso, avisos):
    import db
    _suscribir(planes, pro)
    _cobro(db, 790_000, cuando=_despues(T0, dias=1))
    assert _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=2))) == []
    _cobro(db, 10_000, cuando=_despues(T0, dias=2))
    a, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=3)))
    assert a["clave"] == "cobros:plan_bolsa_80" and a["nivel"] == "atencion" and a["solo_admin"] is False
    assert a["ancla"] == "config-ap-plan" and "80" in a["titulo"] and "200" in a["detalle"]
    _cobro(db, 50_000, cuando=_despues(T0, dias=4))
    b, = _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=5)))
    assert b["huella"] == a["huella"] and "85" in b["titulo"]                  # el mismo periodo: un solo descarte
    with db.conectar() as con:
        periodo = con.execute(sa.select(db.periodo_plan.c.id)).scalar()
    import alertas
    assert a["huella"] == alertas.huella("plan_bolsa_80", periodo)


def test_las_alertas_del_plan_son_de_su_proyecto_y_las_consultas_no_crecen(cobra, planes, pro, falso, avisos):
    import db
    from cobros import libro
    libro.configurar("otra", usuario="admin", cobrar=True, margen=2.0)
    _suscribir(planes, pro, cliente="otra")
    _suscribir(planes, pro)
    _cobro(db, 900_000, cuando=_despues(T0, dias=1), cliente="otra")
    ahora = _despues(T0, dias=30)
    assert [a["clave"] for a in _plan_de(CLAVES, _alertas("acme", ahora))] == ["cobros:plan_renueva"]
    claves = sorted(a["clave"] for a in _plan_de(CLAVES, _alertas("otra", ahora)))
    assert claves == ["cobros:plan_bolsa_80", "cobros:plan_renueva"]
    _, uno = _consultas(db, _alertas, "otra", ahora)
    for i in range(6):
        _cobro(db, 1_000, cuando=_despues(T0, dias=2, minutos=i), cliente="otra")
    _, muchos = _consultas(db, _alertas, "otra", ahora)
    assert muchos == uno


def test_una_suscripcion_terminada_no_avisa_nada(cobra, planes, pro, falso, avisos):
    import db
    _suscribir(planes, pro)
    with db.conectar() as con:
        con.execute(db.suscripcion.update().values(estado="terminada"))
    assert _plan_de(CLAVES, _alertas("acme", _despues(T0, dias=30))) == []


def test_ninguna_es_solo_admin_y_calcular_las_trae(cobra, planes, pro, falso, avisos):
    import alertas
    import db
    _suscribir(planes, pro)
    with db.conectar() as con:
        con.execute(db.suscripcion.update().values(estado="morosa", intentos_fallidos=1))
    todas = alertas.calcular("acme", _despues(T0, dias=30))
    por = {a["clave"]: a for a in todas}
    assert por["cobros:plan_morosa"]["solo_admin"] is False
    assert not any(a["solo_admin"] for a in todas if a["clave"].startswith("cobros:"))


def test_una_recarga_de_wompi_pendiente_tambien_avisa_y_dice_con_cual(cobra, base_temporal):
    wompi = _recarga(HACE_20_MIN, medio="wompi", ref="rw")
    bold = _recarga(HACE_20_MIN, medio="bold", ref="rb")
    _recarga(HACE_20_MIN, medio="manual", ref="rm")
    por = {a["clave"]: a for a in _alertas("acme", "2026-10-09T10:00:00") if "recarga_pendiente" in a["clave"]}
    assert set(por) == {f"cobros:recarga_pendiente:{wompi}", f"cobros:recarga_pendiente:{bold}"}
    assert "Wompi" in por[f"cobros:recarga_pendiente:{wompi}"]["detalle"]
    assert "Bold" in por[f"cobros:recarga_pendiente:{bold}"]["detalle"]

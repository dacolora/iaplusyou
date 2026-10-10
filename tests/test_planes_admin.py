"""/admin/cobros con planes (spec planes 2026-10-09 §9, planes 7/8): crear,
editar y archivar planes; por proyecto la suscripción con sus acciones
(activar a mano, cancelar, terminar ya con nota, resolver un pago pendiente);
márgenes visibles; ganancia del periodo; eventos de Bold y Wompi; avisos de
configuración de Wompi. Todo solo para el admin, con POST del mismo origen y
un número fijo de consultas por página."""
import re

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from tests.test_planes import ACEPTACION, CENTAVOS_MES, TRM, WompiFalso

MISMO = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import estado
    import idiomas
    import notificaciones
    import proyectos
    from cobros import trm, wompi
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(estado, "listar_clientes", lambda: ["acme", "otro"])
    for nombre in ("WOMPI_LLAVE_PUBLICA", "WOMPI_LLAVE_PRIVADA", "WOMPI_SECRETO_EVENTOS", "WOMPI_SECRETO_INTEGRIDAD",
                   "BOLD_LLAVE_IDENTIDAD", "BOLD_LLAVE_SECRETA", "BOLD_PRUEBAS"):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda cliente: "es")
    enviados = []
    monkeypatch.setattr(notificaciones, "avisar", lambda cliente, tipo, asunto, cuerpo: enviados.append(tipo) or True)
    monkeypatch.setattr(notificaciones, "avisar_admin", lambda tipo, *a, **k: enviados.append("admin:" + tipo) or 1)
    falso = WompiFalso(wompi)
    monkeypatch.setattr(wompi, "crear_fuente", falso.crear_fuente)
    monkeypatch.setattr(wompi, "cobrar_fuente", falso.cobrar_fuente)
    monkeypatch.setattr(wompi, "transaccion", falso.transaccion)
    monkeypatch.setattr(trm, "actual", lambda: TRM)
    falso.enviados = enviados
    return falso


@pytest.fixture()
def http(entorno):
    import dashboard
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


@pytest.fixture()
def pro(entorno):
    from cobros import planes
    return planes.crear_plan("Pro", 1000, 1.25, 25, precio_anual_usd=10000, usuario="admin")


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


def _cobrar(cliente="acme"):
    from cobros import libro
    libro.configurar(cliente, usuario="admin", cobrar=True)


def _filas(tabla, **filtro):
    import db
    t = getattr(db, tabla)
    q = sa.select(t).order_by(t.c.id)
    for k, v in filtro.items():
        q = q.where(getattr(t.c, k) == v)
    with db.conectar() as con:
        return con.execute(q).all()


def _envejecer():
    import db
    with db.conectar() as con:
        con.execute(db.pago_plan.update().where(db.pago_plan.c.estado == "pendiente")
                    .values(actualizado_en="2000-01-01T00:00:00"))


def _suscribir(cliente="acme", plan_id=None):
    """Un alta con tarjeta (Wompi falso). `configurado` solo se finge aquí: los avisos de configuración del panel
    miran las llaves de verdad."""
    from unittest import mock

    from cobros import planes, wompi
    with mock.patch.object(wompi, "configurado", lambda: True):
        return planes.suscribir(cliente, plan_id, "mensual", "CARD", "tok_prueba_4242", "pagos@acme.co",
                                dict(ACEPTACION), "user_acme", 1000)


def _pendiente_incierto(falso, pro, cliente="acme"):
    """Un alta cuyo cobro llegó a Wompi sin respuesta: el pago queda pendiente, sin id de transacción."""
    from cobros import wompi
    _cobrar(cliente)
    falso.error = (wompi.ErrorWompi("se cortó", incierto=True), True)
    _suscribir(cliente, pro)
    (pago,) = _filas("pago_plan", estado="pendiente")
    _envejecer()
    return pago


# --- acceso y mismo origen ---------------------------------------------------------------------

RUTAS_POST = [
    ("/admin/cobros/planes", {"nombre": "Otro", "precio_usd": "500", "margen": "1.5", "tope_incluido_usd": "10"}),
    ("/admin/cobros/planes/{pro}", {"nombre": "Pro", "precio_usd": "9", "margen": "1.5", "tope_incluido_usd": "10"}),
    ("/admin/cobros/planes/{pro}/activo", {"activo": "1"}),
    ("/admin/cobros/acme/plan/activar", {"plan_id": "{pro}", "ciclo": "mensual"}),
    ("/admin/cobros/acme/plan/cancelar", {"confirmo": "1"}),
    ("/admin/cobros/acme/plan/terminar", {"nota": "x", "confirmo": "1"}),
    ("/admin/cobros/acme/plan/pago/1/resolver", {"resultado": "no_cobrado", "nota": "x"}),
]


def _sin_cambios(pro):
    from cobros import planes
    p = planes.leer_plan(pro)
    assert (p["precio_usd"], p["activo"], len(planes.listar(activos=False))) == (1000, True, 1)
    assert _filas("suscripcion") == [] and _filas("pago_plan") == []


def test_quien_no_es_admin_va_al_login_y_nada_cambia(http, pro):
    _cobrar()
    c = http.como("user_acme")
    for ruta, datos in RUTAS_POST:
        datos = {k: v.format(pro=pro) for k, v in datos.items()}
        r = c.post(ruta.format(pro=pro), data=datos, headers=MISMO)
        assert r.status_code == 302 and "/login" in r.headers["Location"], ruta
    _sin_cambios(pro)


def test_un_post_de_otro_sitio_es_403(http, pro):
    _cobrar()
    c = http.como("admin")
    for ruta, datos in RUTAS_POST:
        datos = {k: v.format(pro=pro) for k, v in datos.items()}
        r = c.post(ruta.format(pro=pro), data=datos, headers={"Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403, ruta
    _sin_cambios(pro)


def test_un_proyecto_que_no_existe_es_404(http, pro):
    c = http.como("admin")
    for accion in ("activar", "cancelar", "terminar", "pago/1/resolver"):
        r = c.post(f"/admin/cobros/nadie/plan/{accion}", data={"plan_id": str(pro), "ciclo": "mensual"}, headers=MISMO)
        assert r.status_code == 404
    assert _filas("suscripcion") == []


# --- planes: crear, editar, archivar -----------------------------------------------------------

def test_crear_un_plan_nace_archivado_salvo_que_se_ofrezca(http):
    from cobros import planes
    c = http.como("admin")
    r = c.post("/admin/cobros/planes", data={"nombre": "Básico", "precio_usd": "300", "precio_anual_usd": "",
                                             "margen": "1,5", "tope_incluido_usd": "10,5", "orden": "2"},
               headers=MISMO)
    assert r.status_code == 302 and "#cobros-planes" in r.headers["Location"]
    (p,) = planes.listar(activos=False)
    assert (p["nombre"], p["precio_usd"], p["precio_anual_usd"], p["margen"], p["tope_incluido_usd"], p["orden"],
            p["activo"]) == ("Básico", 300, None, 1.5, 10.5, 2, False)
    assert "Plan creado: Básico." in _flashes(c)
    c.post("/admin/cobros/planes", data={"nombre": "Pro", "precio_usd": "1000", "precio_anual_usd": "10000",
                                         "margen": "1.25", "tope_incluido_usd": "25", "activo": "1"}, headers=MISMO)
    assert [x["nombre"] for x in planes.listar()] == ["Pro"]


@pytest.mark.parametrize("datos, frase", [
    ({"nombre": "", "precio_usd": "300", "margen": "1.5", "tope_incluido_usd": "10"}, "nombre"),
    ({"nombre": "X", "precio_usd": "1.000", "margen": "1.5", "tope_incluido_usd": "10"}, "precio mensual"),
    ({"nombre": "X", "precio_usd": "300", "precio_anual_usd": "99,5", "margen": "1.5", "tope_incluido_usd": "10"},
     "precio anual"),
    ({"nombre": "X", "precio_usd": "300", "margen": "6", "tope_incluido_usd": "10"}, "margen de miembro"),
    ({"nombre": "X", "precio_usd": "300", "margen": "nan", "tope_incluido_usd": "10"}, "margen de miembro"),
    ({"nombre": "X", "precio_usd": "300", "margen": "1.5", "tope_incluido_usd": "-1"}, "tope"),
])
def test_crear_un_plan_invalido_avisa_y_no_escribe(http, datos, frase):
    from cobros import planes
    c = http.como("admin")
    r = c.post("/admin/cobros/planes", data=datos, headers=MISMO)
    assert r.status_code == 302
    assert planes.listar(activos=False) == []
    assert any(frase in m for m in _flashes(c))


def test_editar_un_plan_dice_que_el_precio_solo_vale_para_nuevas(http, pro, entorno):
    from cobros import planes
    _cobrar()
    _suscribir("acme", pro)
    c = http.como("admin")
    r = c.post(f"/admin/cobros/planes/{pro}", data={"nombre": "Pro+", "precio_usd": "1200", "precio_anual_usd": "",
                                                   "margen": "1,30", "tope_incluido_usd": "30", "orden": "1"},
               headers=MISMO)
    assert r.status_code == 302 and f"#plan-{pro}" in r.headers["Location"]
    p = planes.leer_plan(pro)
    assert (p["nombre"], p["precio_usd"], p["precio_anual_usd"], p["margen"], p["tope_incluido_usd"]) == \
        ("Pro+", 1200, None, 1.3, 30.0)
    assert any("sigue con el precio que aceptó" in m for m in _flashes(c))
    assert _filas("suscripcion")[0].precio_usd == 1000     # el precio aceptado no cambia
    r = c.post(f"/admin/cobros/planes/{pro}", data={"nombre": "Pro+", "precio_usd": "0", "margen": "1.3",
                                                   "tope_incluido_usd": "30"}, headers=MISMO)
    assert planes.leer_plan(pro)["precio_usd"] == 1200
    assert any("precio mensual" in m for m in _flashes(c))


def test_archivar_y_volver_a_ofrecer(http, pro):
    from cobros import planes
    c = http.como("admin")
    c.post(f"/admin/cobros/planes/{pro}/activo", data={"activo": "0"}, headers=MISMO)
    assert planes.leer_plan(pro)["activo"] is False
    assert any("Plan archivado" in m for m in _flashes(c))
    c.post(f"/admin/cobros/planes/{pro}/activo", data={"activo": "1"}, headers=MISMO)
    assert planes.leer_plan(pro)["activo"] is True
    r = c.post("/admin/cobros/planes/999/activo", data={"activo": "1"}, headers=MISMO)
    assert r.status_code == 302 and any("no existe" in m for m in _flashes(c))


def test_la_pagina_muestra_los_margenes_de_los_planes_junto_al_global(http, pro):
    from cobros import libro
    assert libro.margen_global() == 2.0
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    fila = re.search(rf'<tr id="plan-{pro}".*?</tr>', html, re.S).group(0)
    assert "1,25" in fila and "a la carta: 2,00 (global)" in fila and "38 % menos" in fila
    assert "US$ 1.000" in fila and "US$ 10.000" in fila and "US$ 25,00" in fila
    assert "Un precio nuevo solo vale para suscripciones nuevas" in fila


# --- por proyecto: activar a mano, cancelar, terminar ya --------------------------------------

def test_activar_a_mano_abre_el_periodo_y_acredita(http, pro):
    from cobros import libro, planes
    _cobrar()
    c = http.como("admin")
    r = c.post("/admin/cobros/acme/plan/activar", data={"plan_id": str(pro), "ciclo": "mensual",
                                                       "nota": "transferencia 123"}, headers=MISMO)
    assert r.status_code == 302 and "#suscripcion-acme" in r.headers["Location"]
    (sus,) = _filas("suscripcion")
    assert (sus.estado, sus.renovar, sus.plan_id) == ("activa", False, pro)
    (pago,) = _filas("pago_plan")
    assert (pago.medio, pago.estado, pago.usd, pago.motivo, pago.usuario) == \
        ("manual", "aprobado", 1000, "transferencia 123", "admin")
    assert planes.periodo_abierto(None, "acme") is not None
    (mov,) = _filas("movimiento_saldo", tipo="plan")
    assert mov.milesimas == 1_000_000 and libro.saldo("acme") == 1_000_000
    assert any("activado a mano" in m for m in _flashes(c))
    html = c.get("/admin/cobros").get_data(as_text=True)
    fila = re.search(r'<tr id="suscripcion-acme".*?</tr>\s*(?=<tr|</tbody>)', html, re.S).group(0)
    assert "Activa a mano" in fila and "US$ 1.000,00" in fila and "Pro" in fila
    proyecto = re.search(r'<tr id="fila-acme".*?</tr>', html, re.S).group(0)
    assert "hoy cobra 1,25 (plan)" in proyecto


def test_activar_a_mano_en_un_proyecto_que_no_cobra_avisa_y_no_escribe(http, pro):
    c = http.como("admin")
    c.post("/admin/cobros/acme/plan/activar", data={"plan_id": str(pro), "ciclo": "mensual"}, headers=MISMO)
    assert _filas("suscripcion") == [] and _filas("movimiento_saldo") == []
    assert any("prende «Cobrar»" in m for m in _flashes(c))


@pytest.mark.parametrize("datos, frase", [({"plan_id": "999", "ciclo": "mensual"}, "no existe"),
                                          ({"plan_id": "{pro}", "ciclo": "semanal"}, "Ciclo")])
def test_activar_a_mano_invalido_avisa(http, pro, datos, frase):
    _cobrar()
    c = http.como("admin")
    c.post("/admin/cobros/acme/plan/activar", data={k: v.format(pro=pro) for k, v in datos.items()}, headers=MISMO)
    assert _filas("suscripcion") == []
    assert any(frase in m for m in _flashes(c))


def test_activar_a_mano_con_tarjeta_que_renueva_avisa_que_la_apaga(http, pro):
    _cobrar()
    _suscribir("acme", pro)
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    assert "Activar a mano APAGA esa renovación automática" in html
    assert "renueva con tarjeta" in html and "por US$ 1.000 (el precio que aceptó)" in html


def test_cancelar_pide_confirmar(http, pro):
    _cobrar()
    _suscribir("acme", pro)
    c = http.como("admin")
    c.post("/admin/cobros/acme/plan/cancelar", data={}, headers=MISMO)
    assert _filas("suscripcion")[0].estado == "activa"
    assert any("Marca la casilla" in m for m in _flashes(c))
    c.post("/admin/cobros/acme/plan/cancelar", data={"confirmo": "1"}, headers=MISMO)
    s = _filas("suscripcion")[0]
    assert (s.estado, s.renovar) == ("cancelada", False)
    assert any("no se renueva y sigue hasta el" in m for m in _flashes(c))


def test_terminar_ya_pide_nota_y_confirmar(http, pro):
    from cobros import libro
    _cobrar()
    _suscribir("acme", pro)
    c = http.como("admin")
    c.post("/admin/cobros/acme/plan/terminar", data={"nota": "  ", "confirmo": "1"}, headers=MISMO)
    assert _filas("suscripcion")[0].estado == "activa"
    assert any("Escribe una nota" in m for m in _flashes(c))
    c.post("/admin/cobros/acme/plan/terminar", data={"nota": "pidió la baja"}, headers=MISMO)
    assert _filas("suscripcion")[0].estado == "activa"
    c.post("/admin/cobros/acme/plan/terminar", data={"nota": "pidió la baja", "confirmo": "1"}, headers=MISMO)
    assert _filas("suscripcion")[0].estado == "terminada"
    (venc,) = _filas("movimiento_saldo", tipo="vencimiento")
    assert venc.milesimas == -1_000_000 and libro.saldo("acme") == 0


def test_cancelar_o_terminar_sin_plan_avisa(http):
    c = http.como("admin")
    c.post("/admin/cobros/acme/plan/cancelar", data={"confirmo": "1"}, headers=MISMO)
    c.post("/admin/cobros/acme/plan/terminar", data={"nota": "x", "confirmo": "1"}, headers=MISMO)
    assert sum("no tiene un plan" in m for m in _flashes(c)) >= 1


# --- resolver un pago pendiente ----------------------------------------------------------------

def test_no_se_cobro_exige_nota_y_lo_da_por_fallido(http, pro, entorno):
    pago = _pendiente_incierto(entorno, pro)
    c = http.como("admin")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert f"Pago pendiente {pago.referencia}" in html and "Resolver el pago" in html
    ruta = f"/admin/cobros/acme/plan/pago/{pago.id}/resolver"
    c.post(ruta, data={"resultado": "no_cobrado", "nota": ""}, headers=MISMO)
    assert _filas("pago_plan")[0].estado == "pendiente"
    assert any("Escribe una nota" in m for m in _flashes(c))
    c.post(ruta, data={"resultado": "no_cobrado", "nota": "no aparece en el panel de Wompi"}, headers=MISMO)
    p = _filas("pago_plan")[0]
    assert (p.estado, p.usuario) == ("error", "admin")
    assert "administrador" in p.motivo
    assert _filas("suscripcion")[0].estado == "terminada"      # el primer cobro falló: el alta no sigue
    assert _filas("movimiento_saldo", tipo="plan") == []
    assert any("no cobrado" in m for m in _flashes(c))


def test_si_se_cobro_relee_la_transaccion_y_abre_el_periodo(http, pro, entorno):
    from cobros import libro
    pago = _pendiente_incierto(entorno, pro)
    entorno.txs["1292-77-1"] = {"id": "1292-77-1", "reference": pago.referencia, "amount_in_cents": CENTAVOS_MES,
                                "currency": "COP", "status": "APPROVED", "status_message": None}
    c = http.como("admin")
    c.post(f"/admin/cobros/acme/plan/pago/{pago.id}/resolver",
           data={"resultado": "cobrado", "transaccion_id": " 1292-77-1 "}, headers=MISMO)
    p = _filas("pago_plan")[0]
    assert (p.estado, p.transaccion_id) == ("aprobado", "1292-77-1")
    assert libro.saldo("acme") == 1_000_000 and len(_filas("periodo_plan")) == 1
    assert any("Wompi confirmó el cobro" in m for m in _flashes(c))


def test_si_se_cobro_con_la_transaccion_de_otro_pago_no_acredita(http, pro, entorno):
    from cobros import libro
    pago = _pendiente_incierto(entorno, pro)
    entorno.txs["1292-78-1"] = {"id": "1292-78-1", "reference": "pl-99-20261010-1", "amount_in_cents": CENTAVOS_MES,
                                "currency": "COP", "status": "APPROVED", "status_message": None}
    c = http.como("admin")
    c.post(f"/admin/cobros/acme/plan/pago/{pago.id}/resolver",
           data={"resultado": "cobrado", "transaccion_id": "1292-78-1"}, headers=MISMO)
    assert _filas("pago_plan")[0].estado == "pendiente" and libro.saldo("acme") == 0
    assert any("es de otro pago" in m for m in _flashes(c))


def test_si_se_cobro_con_un_monto_que_no_cuadra_no_acredita(http, pro, entorno):
    from cobros import libro
    pago = _pendiente_incierto(entorno, pro)
    entorno.txs["1292-79-1"] = {"id": "1292-79-1", "reference": pago.referencia, "amount_in_cents": 100,
                                "currency": "COP", "status": "APPROVED", "status_message": None}
    c = http.como("admin")
    c.post(f"/admin/cobros/acme/plan/pago/{pago.id}/resolver",
           data={"resultado": "cobrado", "transaccion_id": "1292-79-1"}, headers=MISMO)
    assert _filas("pago_plan")[0].estado == "pendiente" and libro.saldo("acme") == 0
    assert any("no cuadran" in m for m in _flashes(c))


def test_si_se_cobro_sin_id_valido_o_con_wompi_caido_no_toca_nada(http, pro, entorno, monkeypatch):
    from cobros import wompi
    pago = _pendiente_incierto(entorno, pro)
    c = http.como("admin")
    ruta = f"/admin/cobros/acme/plan/pago/{pago.id}/resolver"
    c.post(ruta, data={"resultado": "cobrado", "transaccion_id": "../otra cosa"}, headers=MISMO)
    assert any("id de la transacción" in m for m in _flashes(c))

    def caido(*a, **k):
        raise wompi.ErrorWompi("Wompi no responde", caida=True)
    monkeypatch.setattr(wompi, "transaccion", caido)
    c.post(ruta, data={"resultado": "cobrado", "transaccion_id": "1292-80-1"}, headers=MISMO)
    assert any("No pudimos consultar la transacción en Wompi" in m for m in _flashes(c))
    assert _filas("pago_plan")[0].estado == "pendiente"


def test_un_cobro_en_camino_no_se_resuelve_a_mano(http, pro, entorno):
    import db
    pago = _pendiente_incierto(entorno, pro)
    with db.conectar() as con:
        con.execute(db.pago_plan.update().values(actualizado_en=db.ahora()))
    c = http.como("admin")
    assert "va en camino a Wompi" in c.get("/admin/cobros").get_data(as_text=True)
    c.post(f"/admin/cobros/acme/plan/pago/{pago.id}/resolver", data={"resultado": "no_cobrado", "nota": "x"},
           headers=MISMO)
    assert _filas("pago_plan")[0].estado == "pendiente"
    assert any("va en camino" in m for m in _flashes(c))


def test_no_se_cobro_se_niega_si_hay_transaccion(http, pro, entorno):
    import db
    pago = _pendiente_incierto(entorno, pro)
    with db.conectar() as con:
        con.execute(db.pago_plan.update().values(transaccion_id="1292-81-1"))
    c = http.como("admin")
    c.post(f"/admin/cobros/acme/plan/pago/{pago.id}/resolver", data={"resultado": "no_cobrado", "nota": "x"},
           headers=MISMO)
    assert _filas("pago_plan")[0].estado == "pendiente"
    assert any("tiene una transacción en Wompi" in m for m in _flashes(c))


def test_el_pago_de_otro_proyecto_no_se_resuelve_desde_este(http, pro, entorno):
    pago = _pendiente_incierto(entorno, pro, cliente="otro")
    c = http.como("admin")
    c.post(f"/admin/cobros/acme/plan/pago/{pago.id}/resolver", data={"resultado": "no_cobrado", "nota": "x"},
           headers=MISMO)
    assert _filas("pago_plan")[0].estado == "pendiente"
    assert any("no existe" in m for m in _flashes(c))


# --- cifras con plan ---------------------------------------------------------------------------

def test_resumen_admin_con_plan(entorno, pro):
    import gastos
    from cobros import planes, vista
    _cobrar()
    planes.activar_manual("acme", pro, "mensual", "admin")
    gastos.registrar("acme", "video", 10.0, "video:cf1:t1")       # cobro 12 500 a precio de miembro, costo 10 000
    gastos.registrar("acme", "guion", 0.5, "guion:g1:t1")          # incluido: 0 cobrado, costo 500
    a = {f["cliente"]: f for f in vista.resumen_admin()}["acme"]
    assert a["margen"] == 1.25 and a["margen_plan"] == 1.25 and a["margen_propio"] is None
    assert a["recargado_mes"] == 1_000_000                          # el crédito del plan entra como recargado
    assert a["cobrado_mes"] == 12_500 and a["costo_mes"] == 10_500
    assert a["ganancia_mes"] == 12_500 - 10_500
    o = {f["cliente"]: f for f in vista.resumen_admin()}["otro"]
    assert o["margen_plan"] is None and o["margen"] == 2.0


def test_el_saldo_del_plan_vencido_cuenta_como_ganancia(entorno, pro):
    from cobros import planes, vista
    _cobrar()
    planes.activar_manual("acme", pro, "mensual", "admin")
    planes.terminar_ya("acme", "admin", nota="prueba")
    a = {f["cliente"]: f for f in vista.resumen_admin()}["acme"]
    assert a["vencido_mes"] == 1_000_000 and a["ganancia_mes"] == 1_000_000 and a["margen_plan"] is None


def test_planes_admin_bolsa_incluido_y_ganancia_del_periodo(entorno, pro):
    import db
    import gastos
    from cobros import libro, planes, vista
    _cobrar()
    planes.activar_manual("acme", pro, "mensual", "admin")
    gastos.registrar("acme", "video", 10.0, "video:cf1:t1")             # cobro 12 500
    gid = gastos.registrar("acme", "video", 2.0, "video:cf2:t2")        # cobro 2 500, revertido
    m = db.movimiento_saldo
    with db.conectar() as con:
        con.execute(m.update().where(m.c.gasto_id == gid).values(job_id="j-cf2"))
    libro.revertir_trabajo("acme", "j-cf2", motivo="falló")
    gastos.registrar("acme", "guion", 0.5, "guion:g1:t1")               # incluido, costo 0,5
    gastos.registrar("acme", "ideas", 1.25, "ideas:i1:t1")              # incluido, costo 1,25
    d = vista.planes_admin()
    (pl,) = d["planes"]
    assert pl["suscripciones"] == 1
    a = d["por_cliente"]["acme"]
    assert a["suscripcion"]["situacion"] == "manual" and a["suscripcion"]["plan_nombre"] == "Pro"
    assert a["bolsa_credito"] == 1_000_000
    assert a["bolsa_restante"] == libro.bolsa_plan("acme")["restante"] == 1_000_000 - 12_500
    assert a["incluido_usado_usd"] == pytest.approx(1.75)
    assert a["incluido_usado_usd"] == pytest.approx(planes.incluido_usado("acme", planes.periodo_abierto(None, "acme")))
    assert a["cobrado_periodo"] == 12_500
    assert a["costo_periodo"] == 10_000 + 2_000 + 500 + 1_250
    assert a["ganancia_periodo"] == 12_500 - 13_750
    assert "otro" not in d["por_cliente"]


# --- consultas fijas ---------------------------------------------------------------------------

def _sembrar(n, pro):
    import gastos
    from cobros import libro, planes, recargas
    for i in range(n):
        c = f"p{i}"
        if libro.cuenta(c).get("cobrar"):
            continue
        libro.configurar(c, usuario="admin", cobrar=True)
        recargas.manual(c, 50, "admin", "")
        planes.activar_manual(c, pro, "mensual", "admin")
        gastos.registrar(c, "video", 1.0, f"video:{c}:t1")
        gastos.registrar(c, "guion", 0.2, f"guion:{c}:t2")


def _consultas(fn):
    import db
    lista = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        lista.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        fn()
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    return len(lista)


def test_la_pagina_con_planes_no_hace_una_consulta_por_proyecto(http, pro, monkeypatch):
    import estado
    from cobros import vista
    monkeypatch.setattr(estado, "listar_clientes", lambda: [])
    c = http.como("admin")
    _sembrar(3, pro)
    tres_vista = _consultas(vista.planes_admin)
    tres = _consultas(lambda: c.get("/admin/cobros"))
    assert len(vista.planes_admin()["por_cliente"]) == 3
    _sembrar(6, pro)
    assert len(vista.planes_admin()["por_cliente"]) == 6
    assert _consultas(vista.planes_admin) == tres_vista <= 6
    assert _consultas(lambda: c.get("/admin/cobros")) == tres


# --- eventos de Bold y Wompi -------------------------------------------------------------------

def _evento(proveedor, n, referencia, firma_ok=True):
    import db
    with db.conectar() as con:
        con.execute(db.pago_evento.insert().values(
            proveedor=proveedor, evento_id=f"ev-{proveedor}-{n}", tipo="transaction.updated" if proveedor == "wompi"
            else "SALE_APPROVED", referencia=referencia, recibido_en=db.ahora(), firma_ok=firma_ok,
            resultado="acreditada"))


def _recarga(medio, referencia, total, moneda="COP"):
    import db
    with db.conectar() as con:
        con.execute(db.recarga.insert().values(
            cliente="acme", creada_en=db.ahora(), actualizada_en=db.ahora(), medio=medio, estado="aprobada",
            milesimas=1_000_000, referencia=referencia, total_pago=total, moneda_pago=moneda, usuario="user_acme"))


def test_los_eventos_muestran_bold_y_wompi_con_el_monto_en_pesos(http):
    _recarga("wompi", "cv-1-1", 400_050_000)        # Wompi guarda centavos de COP
    _recarga("bold", "cv-2-1", 4_000_500)           # Bold guarda pesos
    _evento("wompi", 1, "cv-1-1")
    _evento("bold", 2, "cv-2-1")
    _evento("wompi", 3, "cv-9-1", firma_ok=False)
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    bloque = re.search(r'id="cobros-eventos".*?</section>', html, re.S).group(0)
    assert "Últimos eventos de Bold y Wompi" in bloque
    filas = re.findall(r"<tr><td>.*?</tr>", bloque, re.S)
    assert len(filas) == 2
    assert "Bold" in filas[0] and "cv-2-1" in filas[0] and "COP 4.000.500" in filas[0]
    assert "Wompi" in filas[1] and "cv-1-1" in filas[1] and "COP 4.000.500" in filas[1]
    assert "US$ 1.000,00" in filas[1]
    assert "cv-9-1" not in bloque


def test_monto_evento_de_un_pago_de_plan(entorno):
    from cobros import vista
    assert vista.monto_evento({"centavos_plan": CENTAVOS_MES}) == "COP 4.000.500"
    assert vista.monto_evento({"total_pago": None}) is None
    assert vista.usd_evento({"usd_plan": 1000}) == "US$ 1.000"


# --- avisos de configuración de Wompi ----------------------------------------------------------

def test_avisos_de_configuracion_de_wompi(http, monkeypatch):
    c = http.como("admin")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-wompi-llaves"' in html and "Faltan las llaves de Wompi" in html
    assert 'id="aviso-wompi-pruebas-servidor"' not in html
    valores = {"WOMPI_LLAVE_PUBLICA": "pub_test_publica123", "WOMPI_LLAVE_PRIVADA": "prv_test_privada456",  # llave-de-prueba
               "WOMPI_SECRETO_EVENTOS": "test_events_secreto789",  # llave-de-prueba
               "WOMPI_SECRETO_INTEGRIDAD": "test_integrity_secreto012"}  # llave-de-prueba
    for k, v in valores.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.creatvmachine.com")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-wompi-pruebas-servidor"' in html and 'id="aviso-wompi-llaves"' not in html
    monkeypatch.setenv("PLATAFORMA_URL", "http://localhost:5050")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-wompi-sandbox"' in html
    assert 'id="aviso-wompi-pruebas-servidor"' not in html and 'id="aviso-wompi-llaves"' not in html
    for v in valores.values():
        assert v not in html

"""Pospago: «Cobrar» sin frenar (pedido de Daniel, 2026-10-12, para happyflops).

Un proyecto que cobra con `pospago` prendido paga cada generación a su margen como siempre (el cobro queda en el
libro), pero nada lo frena por saldo: el saldo puede quedar negativo y eso es lo que debe. Ni `exigir` ni el
respaldo del worker lo detienen, no recibe «sin saldo» ni «saldo bajo», y lo que ve dice «Por pagar»."""
import re
import time

import pytest
import sqlalchemy as sa

AHORA = "2026-10-12T12:00:00"
MISMO = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture()
def libro(base_temporal, monkeypatch, tmp_path):
    import proyectos
    from cobros import libro as mod
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD", raising=False)
    return mod


def _pospago(libro, cliente="acme", margen=3.0, milesimas=0):
    import db
    libro.configurar(cliente, usuario="admin", cobrar=True, margen=margen, pospago=True)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="deuda")


def _tarea_viva(db, job_id, cliente="acme"):
    with db.conectar() as con:
        con.execute(db.tarea.insert().values(tipo="flowplus_video", cliente=cliente, estado="pendiente", job_id=job_id,
                                             ejecutar_desde=AHORA, creada_en=AHORA, payload={}, max_intentos=1))


# --- el libro ------------------------------------------------------------------------------

def test_la_cuenta_dice_si_es_pospago_y_arranca_apagado(libro):
    assert libro.cuenta("sin_fila")["pospago"] is False
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert libro.cuenta("acme")["pospago"] is False
    libro.configurar("acme", usuario="admin", pospago=True)
    assert libro.cuenta("acme")["pospago"] is True and libro.cuenta("acme")["cobrar"] is True
    libro.configurar("acme", usuario="admin", margen=3.0)          # cambiar otra cosa no lo apaga
    assert libro.cuenta("acme")["pospago"] is True
    libro.configurar("acme", usuario="admin", pospago=False)
    assert libro.cuenta("acme")["pospago"] is False


def test_pospago_sin_saldo_no_frena_y_reserva_el_precio_al_margen(libro, base_temporal):
    db = base_temporal
    _pospago(libro)
    assert libro.exigir("acme", 1.0, job_id="j1") == 3000           # 1,00 × 3
    _tarea_viva(db, "j1")
    assert libro.exigir("acme", 2.0, job_id="j2") == 6000           # con disponible −3 000, tampoco frena
    with db.conectar() as con:
        r = con.execute(sa.select(db.reserva_saldo.c.job_id, db.reserva_saldo.c.margen)
                        .order_by(db.reserva_saldo.c.job_id)).all()
    assert [(f.job_id, f.margen) for f in r] == [("j1", 3.0), ("j2", 3.0)]
    assert libro.exigir("acme", None) == 1                          # «precio no disponible» tampoco frena


def test_sin_pospago_el_freno_sigue_igual(libro):
    libro.configurar("acme", usuario="admin", cobrar=True, margen=3.0)
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", 1.0, job_id="j1")


def test_pospago_con_cobrar_apagado_no_cobra_nada(libro, base_temporal):
    import gastos
    libro.configurar("acme", usuario="admin", cobrar=False, pospago=True)
    assert libro.exigir("acme", 1.0, job_id="j1") == 0
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")
    assert libro.saldo("acme") == 0


def test_el_cobro_deja_el_saldo_en_negativo_a_su_margen(libro, base_temporal):
    import gastos
    _pospago(libro, milesimas=-948_630)                             # lo de antes, como un ajuste
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")
    assert libro.saldo("acme") == -948_630 - 3000
    with base_temporal.conectar() as con:
        cobro = con.execute(sa.select(base_temporal.movimiento_saldo)
                            .where(base_temporal.movimiento_saldo.c.tipo == "cobro")).one()
    assert cobro.milesimas == -3000 and cobro.extra["margen"] == 3.0


def test_el_respaldo_del_worker_deja_arrancar_con_saldo_negativo(libro):
    import tareas
    t = {"id": 99, "tipo": "flowplus_video", "cliente": "acme", "job_id": "j"}
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert libro.puede_arrancar(t, tareas.TIPOS_QUE_COBRAN) is False      # prepago: saldo 0 frena
    libro.configurar("acme", usuario="admin", pospago=True)
    assert libro.puede_arrancar(t, tareas.TIPOS_QUE_COBRAN) is True
    _pospago(libro, milesimas=-50_000)
    assert libro.puede_arrancar(t, tareas.TIPOS_QUE_COBRAN) is True


def test_encolar_una_tarea_que_cobra_no_frena_en_pospago(libro, base_temporal):
    import trabajos
    _pospago(libro, milesimas=-10_000)
    trabajos.encolar("acme__video_x", "flowplus_video", {"cliente": "acme"}, cliente="acme", costo_estimado=1.0,
                     max_intentos=1)
    with base_temporal.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(base_temporal.tarea)
                           .where(base_temporal.tarea.c.job_id == "acme__video_x")).scalar() == 1
        reserva = con.execute(sa.select(base_temporal.reserva_saldo.c.milesimas)
                              .where(base_temporal.reserva_saldo.c.job_id == "acme__video_x")).scalar()
    assert reserva == 3000


# --- avisos y alertas ----------------------------------------------------------------------

def test_un_cobro_en_pospago_no_avisa_saldo_bajo(libro, monkeypatch):
    import gastos
    from cobros import avisos
    enviados = []
    monkeypatch.setattr(avisos, "saldo_bajo", lambda *a, **k: enviados.append(a))
    _pospago(libro)
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")
    assert enviados == []
    libro.configurar("otro", usuario="admin", cobrar=True, margen=3.0)    # prepago: sí avisa (control)
    with __import__("db").conectar() as con:
        libro.acreditar(con, "otro", "ajuste", 4_000, "ajuste", usuario="admin", detalle="x")
    gastos.registrar("otro", "video", 1.0, "video:cf2:t2")
    assert len(enviados) == 1


def test_pospago_no_tiene_alertas_de_sin_saldo_ni_saldo_bajo(libro):
    import alertas
    _pospago(libro, milesimas=-948_630)
    assert not [a for a in alertas._fuente_cobros("acme", AHORA)
                if a["clave"] in ("cobros:sin_saldo", "cobros:saldo_bajo")]
    _pospago(libro, cliente="b", milesimas=1_000)                   # positivo bajo el umbral: tampoco
    assert not [a for a in alertas._fuente_cobros("b", AHORA)
                if a["clave"] in ("cobros:sin_saldo", "cobros:saldo_bajo")]


# --- lo que ve el cliente ------------------------------------------------------------------

def test_el_chip_dice_por_pagar_y_no_bloqueo(libro):
    import dashboard
    from cobros import vista
    _pospago(libro, milesimas=-948_630)
    with dashboard.app.test_request_context("/cliente/acme"):
        c = vista.chip("acme", es_admin=False)
    assert c["tono"] == "aviso"
    assert "Por pagar" in c["texto"] and "948.63" in c["texto"].replace(",", ".")
    assert "Recargar" not in c["texto"]


def test_el_chip_con_saldo_a_favor_no_avisa(libro):
    import dashboard
    from cobros import vista
    _pospago(libro, milesimas=1_000)                                # bajo el umbral, pero pospago no avisa
    with dashboard.app.test_request_context("/cliente/acme"):
        c = vista.chip("acme", es_admin=False)
    assert c["tono"] == "normal" and "Saldo:" in c["texto"]


@pytest.fixture()
def pagina(libro, monkeypatch):
    import dashboard
    import referencias_flowplus
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: [])
    dashboard.app.config["TESTING"] = True

    def cliente_como(usuario="user_acme", rol="cliente", proyecto="acme"):
        c = dashboard.app.test_client()
        with c.session_transaction() as s:
            s["usuario"] = usuario; s["rol"] = rol; s["cliente"] = proyecto
        return c
    return cliente_como


def test_el_panel_dice_cuanto_debe_y_que_puede_seguir(libro, pagina):
    _pospago(libro, milesimas=-948_630)
    html = pagina().get("/cliente/acme/saldo/panel").get_data(as_text=True)
    assert "Por pagar" in html
    assert re.search(r"948[.,]63", html)
    assert "Sin saldo" not in html and "Saldo bajo" not in html
    assert "Puedes seguir generando" in html


# --- /admin/cobros -------------------------------------------------------------------------

@pytest.fixture()
def http(libro, monkeypatch, tmp_path):
    import dashboard
    import estado
    monkeypatch.setattr(estado, "listar_clientes", lambda: ["acme", "otro"])
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    from tests.conftest import USUARIOS_PRUEBA
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = USUARIOS_PRUEBA["admin"]["rol"]
        s["cliente"] = USUARIOS_PRUEBA["admin"]["cliente"]; s["sv"] = 1
        s["clave_confirmada_en"] = time.time()   # la clave de los controles de plata, recién escrita (2026-10-15)
    return c


def test_el_admin_prende_y_apaga_el_pospago(http, libro):
    libro.configurar("acme", usuario="admin", cobrar=True)
    r = http.post("/admin/cobros/acme/cuenta", data={"pospago": "1"}, headers=MISMO)
    assert r.status_code == 302 and libro.cuenta("acme")["pospago"] is True
    html = http.get("/admin/cobros").get_data(as_text=True)
    fila = re.search(r'<tr id="fila-acme">.*?</tr>', html, re.S).group(0)
    assert "Pospago" in fila and 'name="pospago" value="0"' in fila
    http.post("/admin/cobros/acme/cuenta", data={"pospago": "0"}, headers=MISMO)
    assert libro.cuenta("acme")["pospago"] is False


def test_prender_el_pospago_desde_otro_sitio_es_403(http, libro):
    libro.configurar("acme", usuario="admin", cobrar=True)
    r = http.post("/admin/cobros/acme/cuenta", data={"pospago": "1"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and libro.cuenta("acme")["pospago"] is False


def test_el_resumen_del_admin_trae_el_pospago(libro):
    from cobros import vista
    _pospago(libro)
    libro.configurar("otro", usuario="admin", cobrar=True)
    filas = {f["cliente"]: f for f in vista.resumen_admin()}
    assert filas["acme"]["pospago"] is True and filas["otro"]["pospago"] is False


# --- con plan mensual (guardian-gasto 2026-10-12: la bolsa que vence no paga la deuda) ------

def _plan_abierto(db, libro, credito=10_000, cliente="acme"):
    from datetime import datetime, timedelta
    ahora = datetime.now()
    with db.conectar() as con:
        pid = int(con.execute(db.periodo_plan.insert().values(
            cliente=cliente, suscripcion_id=1, inicio=(ahora - timedelta(days=1)).isoformat(timespec="seconds"),
            fin=(ahora + timedelta(days=29)).isoformat(timespec="seconds"), precio_usd=credito // 1000,
            margen=1.25, tope_incluido_usd=0.0, credito_milesimas=credito, cerrado=False)).inserted_primary_key[0])
        libro.acreditar_plan(con, pid)
    return pid


def test_pospago_la_bolsa_sin_usar_vence_entera_y_la_deuda_queda(libro, base_temporal):
    import gastos
    _pospago(libro, milesimas=-20_000)
    pid = _plan_abierto(base_temporal, libro)                        # bolsa 10 000: el saldo entero queda en −10 000
    gastos.registrar("acme", "video", 2.4, "video:cf1:t1")           # 2,4 × 1,25 = 3 000 de la bolsa
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 7_000              # vence lo que no se usó, entero
    assert libro.saldo("acme") == -20_000                            # la deuda no se la come la bolsa


def test_pospago_bolsa_mas_grande_que_la_deuda_tampoco_la_borra(libro, base_temporal):
    _pospago(libro, milesimas=-5_000)
    pid = _plan_abierto(base_temporal, libro, credito=10_000)        # saldo entero +5 000
    with base_temporal.conectar() as con:
        assert libro.vencer_periodo(con, pid) == 10_000
    assert libro.saldo("acme") == -5_000


def test_pospago_con_plan_el_chip_y_el_panel_no_esconden_la_deuda(libro, pagina):
    import dashboard
    import db
    from cobros import vista
    _pospago(libro, milesimas=-5_000)
    _plan_abierto(db, libro, credito=10_000)                         # saldo entero +5 000, propio −5 000
    with dashboard.app.test_request_context("/cliente/acme"):
        c = vista.chip("acme", es_admin=False)
    assert "Por pagar" in c["texto"] and "5.00" in c["texto"].replace(",", ".") and c["tono"] == "aviso"
    assert "Plan" in c["texto"]
    html = pagina().get("/cliente/acme/saldo/panel").get_data(as_text=True)
    assert "Por pagar" in html and "Saldo del plan" in html


def test_prender_cobrar_en_un_pospago_sin_saldo_no_dice_que_no_podra_generar(http, libro):
    libro.configurar("acme", usuario="admin", cobrar=False, pospago=True)
    http.post("/admin/cobros/acme/cuenta", data={"cobrar": "1"}, headers=MISMO)
    with http.session_transaction() as s:
        avisos = [m for _c, m in s.get("_flashes", [])]
    assert libro.cuenta("acme")["cobrar"] is True
    assert not [m for m in avisos if "no podrá generar" in m]


# --- aviso al admin cada US$ 200 de deuda nueva (Daniel 2026-10-12) ---------------------------

def test_la_deuda_es_lo_negativo_del_saldo_propio(libro, base_temporal):
    assert libro.deuda("acme") == 0                                  # sin cuenta
    libro.configurar("acme", usuario="admin", cobrar=True)
    with base_temporal.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", -5_000, "ajuste", usuario="admin", detalle="x")
    assert libro.deuda("acme") == 0                                  # prepago: no es deuda de pospago
    libro.configurar("acme", usuario="admin", pospago=True)
    assert libro.deuda("acme") == 5_000
    _plan_abierto(base_temporal, libro, credito=10_000)              # la bolsa no la paga
    assert libro.deuda("acme") == 5_000


@pytest.fixture()
def avisos_admin(monkeypatch):
    from cobros import avisos
    enviados = []
    monkeypatch.setattr(avisos, "admin", lambda tipo, asunto, cuerpo, cliente="": enviados.append(
        (tipo, cliente, asunto() if callable(asunto) else asunto, cuerpo() if callable(cuerpo) else cuerpo)) or 1)
    return enviados


def test_avisa_al_admin_al_entrar_en_cada_tramo_de_200(libro, avisos_admin):
    from cobros import avisos
    assert avisos.deuda_pospago("acme", 948_630) is False            # la primera vez solo anota el tramo (4)
    assert avisos.deuda_pospago("acme", 999_000) is False            # mismo tramo
    assert avisos.deuda_pospago("acme", 1_000_000) is True           # entra al tramo 5: US$ 1 000
    assert avisos.deuda_pospago("acme", 1_150_000) is False
    assert avisos.deuda_pospago("acme", 1_450_000) is True           # salta al 7: un solo aviso
    assert avisos.deuda_pospago("acme", 100_000) is False            # pagó: el tramo baja sin avisar
    assert avisos.deuda_pospago("acme", 250_000) is True             # y vuelve a avisar al subir
    tipos = [a[0] for a in avisos_admin]
    assert tipos == ["deuda_pospago"] * 3 and {a[1] for a in avisos_admin} == {"acme"}
    assert "1.000" in avisos_admin[0][2].replace(",", ".") or "1,000" in avisos_admin[0][2]


def test_un_cobro_en_pospago_dispara_el_aviso_de_deuda(libro, avisos_admin):
    import gastos
    from cobros import avisos
    _pospago(libro, milesimas=-199_000)
    avisos.deuda_pospago("acme", libro.deuda("acme"))                # lo que hace el script al prenderlo
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")           # 199 000 + 3 000 → tramo 1
    assert [a[0] for a in avisos_admin] == ["deuda_pospago"]
    libro.configurar("otro", usuario="admin", cobrar=True, margen=3.0)
    with __import__("db").conectar() as con:
        libro.acreditar(con, "otro", "ajuste", 900_000, "ajuste", usuario="admin", detalle="x")
    gastos.registrar("otro", "video", 1.0, "video:cf2:t2")           # prepago: nunca
    assert len(avisos_admin) == 1


def test_alerta_solo_para_el_admin_con_huella_por_tramo(libro):
    import alertas
    _pospago(libro, milesimas=-150_000)
    assert not [a for a in alertas._fuente_cobros("acme", AHORA) if a["clave"] == "cobros:deuda_pospago"]
    _pospago(libro, milesimas=-100_000)                              # 250 000: tramo 1
    a, = [a for a in alertas._fuente_cobros("acme", AHORA) if a["clave"] == "cobros:deuda_pospago"]
    assert a["solo_admin"] is True and a["ancla"] == "config-ap-saldo" and re.search(r"250[.,]00", a["titulo"])
    _pospago(libro, milesimas=-10_000)                               # 260 000: mismo tramo, misma huella
    b, = [x for x in alertas._fuente_cobros("acme", AHORA) if x["clave"] == "cobros:deuda_pospago"]
    assert b["huella"] == a["huella"]
    _pospago(libro, milesimas=-200_000)                              # 460 000: tramo 2, huella nueva
    c, = [x for x in alertas._fuente_cobros("acme", AHORA) if x["clave"] == "cobros:deuda_pospago"]
    assert c["huella"] != a["huella"]


def test_no_se_pasa_a_prepago_con_deuda_y_un_plan_sin_cerrar(libro, base_temporal):
    # guardian-gasto 2026-10-12 (2.ª ronda): en prepago, la bolsa que vence al cierre borraría la deuda.
    _pospago(libro, milesimas=-948_630)
    pid = _plan_abierto(base_temporal, libro, credito=1_000_000)
    with pytest.raises(ValueError):
        libro.configurar("acme", usuario="admin", pospago=False)
    assert libro.cuenta("acme")["pospago"] is True
    with base_temporal.conectar() as con:
        libro.vencer_periodo(con, pid)
        con.execute(base_temporal.periodo_plan.update().values(cerrado=True))
    libro.configurar("acme", usuario="admin", pospago=False)         # ya cerrado: la deuda quedó, se puede
    assert libro.cuenta("acme")["pospago"] is False and libro.saldo("acme") == -948_630


def test_sin_plan_se_pasa_a_prepago_aunque_deba(libro):
    _pospago(libro, milesimas=-948_630)
    libro.configurar("acme", usuario="admin", pospago=False)
    assert libro.cuenta("acme")["pospago"] is False


def test_el_admin_ve_por_que_no_se_puede_pasar_a_prepago(http, libro, base_temporal):
    _pospago(libro, milesimas=-5_000)
    _plan_abierto(base_temporal, libro)
    http.post("/admin/cobros/acme/cuenta", data={"pospago": "0"}, headers=MISMO)
    with http.session_transaction() as s:
        avisos = [m for c, m in s.get("_flashes", []) if c == "error"]
    assert avisos and libro.cuenta("acme")["pospago"] is True

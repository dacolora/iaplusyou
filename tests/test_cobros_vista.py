"""Lo que ve el cliente de un proyecto que cobra (cobros, spec 2026-10-08 §7 y
§9.4): Configuración › Saldo, la vuelta del pago, el chip de la barra lateral y
el gasto que se le muestra, que es lo COBRADO (cobro + reverso del libro), nunca
el costo del proveedor ni el costo × el margen de hoy."""
import re

import pytest

MARGEN = 1.5


@pytest.fixture()
def libro(base_temporal, monkeypatch, tmp_path):
    import proyectos
    from cobros import libro as mod
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD", raising=False)
    return mod


def _cobra(libro, cliente="acme", milesimas=0, umbral=None):
    import db
    libro.configurar(cliente, usuario="admin", cobrar=True, margen=MARGEN, umbral=umbral)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


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


def _seccion(html, ident):
    m = re.search(r'<section class="config-apartado" id="%s".*?</section>' % re.escape(ident), html, re.S)
    assert m, f"no está la sección {ident}"
    return m.group(0)


# --- movimientos y resúmenes ----------------------------------------------------------------

def test_movimientos_traen_el_saldo_despues_de_cada_fila_y_paginan(libro):
    import db
    import gastos
    from cobros import vista
    libro.configurar("acme", usuario="admin", cobrar=True, margen=MARGEN)
    with db.conectar() as con:
        libro.acreditar(con, "acme", "recarga", 10_000, "recarga_manual", usuario="admin")
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")                  # cobro −1 500
    gid = gastos.registrar("acme", "video", 1.0, "video:cf2:t2")             # cobro −1 500
    # el worker revierte por job_id el segundo (+1 500)
    m = db.movimiento_saldo
    with db.conectar() as con:
        con.execute(m.update().where(m.c.gasto_id == gid).values(job_id="j-cf2"))
    libro.revertir_trabajo("acme", "j-cf2", motivo="falló")
    gastos.registrar("acme", "imagen", 0.4, "imagen:cf3:t3")                # cobro −600
    libro.configurar("otro", usuario="admin", cobrar=True)
    with db.conectar() as con:
        libro.acreditar(con, "otro", "recarga", 99_000, "recarga_manual", usuario="admin")

    r = vista.movimientos("acme")
    saldos = [f["saldo_despues"] for f in r["filas"]]
    tipos = [f["tipo"] for f in r["filas"]]
    # más nuevo primero: recarga 10 000 → cobro −1 500 → cobro −1 500 → reverso +1 500 → cobro −600
    assert tipos == ["cobro", "reverso", "cobro", "cobro", "recarga"]
    assert saldos == [7_900, 8_500, 7_000, 8_500, 10_000]
    assert saldos[0] == libro.saldo("acme")
    for anterior, fila in zip(r["filas"][1:], r["filas"]):
        assert fila["saldo_despues"] == anterior["saldo_despues"] + fila["milesimas"]
    assert r["hay_mas"] is False and all(f["concepto"] for f in r["filas"])
    p1 = vista.movimientos("acme", pagina=1, por_pagina=2)
    p2 = vista.movimientos("acme", pagina=2, por_pagina=2)
    p3 = vista.movimientos("acme", pagina=3, por_pagina=2)
    assert p1["hay_mas"] and p2["hay_mas"] and not p3["hay_mas"]
    assert [f["saldo_despues"] for f in p1["filas"] + p2["filas"] + p3["filas"]] == saldos
    assert vista.movimientos("otro")["filas"][0]["saldo_despues"] == 99_000


def test_resumenes_cobrados_agrupan_por_tipo_y_descuentan_los_reversos(libro):
    import db
    import gastos
    from cobros import vista
    libro.configurar("acme", usuario="admin", cobrar=True, margen=MARGEN)
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")
    gid = gastos.registrar("acme", "video", 2.0, "video:cf2:t2")
    gastos.registrar("acme", "guion", 0.1, "guion:cf1:t3")
    m = db.movimiento_saldo
    with db.conectar() as con:
        con.execute(m.update().where(m.c.gasto_id == gid).values(job_id="j-cf2"))
    libro.revertir_trabajo("acme", "j-cf2")
    r = vista.resumen_mes_cobrado("acme")
    assert set(r) == set(gastos.resumen_mes("acme"))
    assert r["por_tipo"] == {"video": {"usd": 1.5, "n": 1}, "guion": {"usd": 0.15, "n": 1}}
    assert r["total"] == 1.65 and r["n"] == 2
    t = vista.resumen_total_cobrado("acme")
    assert set(t) == set(gastos.resumen_total("acme")) and t["total"] == 1.65 and t["n"] == 2 and t["desde"]
    meses = vista.por_mes_cobrado("acme")
    assert list(meses.values()) == [{"usd": 1.65, "n": 2}]
    h = vista.historial_cobrado("acme")
    assert sorted(f["usd"] for f in h) == [0.15, 1.5]                    # el revertido no aparece
    assert set(gastos.historial("acme")[0]) <= set(h[0])


def test_nombre_concepto_traduce_y_pone_el_prefijo():
    import dashboard
    from cobros import vista
    with dashboard.app.test_request_context("/"):
        assert vista.nombre_concepto("video") == "Videos"
        assert vista.nombre_concepto("recarga_bold") == "Recarga con Bold"
        assert vista.nombre_concepto("anulacion_bold") == "Pago anulado por Bold"
        assert vista.nombre_concepto("video", "reverso") == "Devuelto: Videos"
        assert vista.nombre_concepto("final", "no_cobrado") == "No cobrado: Finales"
        assert vista.nombre_concepto("raro") == "raro"


# --- Configuración › Gasto: lo cobrado, no el costo ----------------------------------------

def test_el_cliente_ve_lo_cobrado_y_el_admin_las_dos_cifras(libro, pagina):
    import gastos
    _cobra(libro, milesimas=50_000)
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1", detalle="wan3 · 5 s")
    gasto = _seccion(pagina().get("/cliente/acme").get_data(as_text=True), "config-ap-gasto")
    assert "US$ 1,50" in gasto and "US$ 1,00" not in gasto
    csv_mes = pagina().get("/cliente/acme/gasto/mes.csv").get_data(as_text=True)
    assert "1,5000" in csv_mes and "1,0000" not in csv_mes
    csv_todo = pagina().get("/cliente/acme/gasto/todo.csv").get_data(as_text=True)
    assert "1,5000" in csv_todo and "1,0000" not in csv_todo
    admin = _seccion(pagina("admin", "admin", None).get("/cliente/acme").get_data(as_text=True), "config-ap-gasto")
    assert "US$ 1,50" in admin and "US$ 1,00" in admin
    csv_admin = pagina("admin", "admin", None).get("/cliente/acme/gasto/mes.csv").get_data(as_text=True)
    assert "1,0000" in csv_admin and "1,5000" in csv_admin


def test_un_proyecto_que_no_cobra_sigue_mostrando_el_costo(libro, pagina):
    import gastos
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    assert "US$ 1,00" in _seccion(html, "config-ap-gasto")
    assert 'id="config-ap-saldo"' not in html and 'data-apartado="saldo"' not in html
    assert "1,0000" in pagina().get("/cliente/acme/gasto/mes.csv").get_data(as_text=True)


def test_la_tarjeta_de_crear_dice_lo_cobrado(libro, pagina):
    import creative_flow as cf
    import gastos
    _cobra(libro, milesimas=50_000)
    cf_id = cf.crear("acme", [], ["Chancla"], [], "camina", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4", enfoque="producto", usd=1.0)
    gastos.registrar("acme", "video", 1.0, f"video:{cf_id}:t1")
    cliente = pagina().get(f"/cliente/acme/creative_flow/{cf_id}/detalle").get_data(as_text=True)
    assert "costó US$ 1,50" in cliente and "costó US$ 1,00" not in cliente
    admin = pagina("admin", "admin", None).get(f"/cliente/acme/creative_flow/{cf_id}/detalle").get_data(as_text=True)
    assert "costó US$ 1,00" in admin


# --- Configuración › Saldo ------------------------------------------------------------------

def test_el_panel_del_saldo_solo_para_quien_entra_al_proyecto(libro, pagina):
    import db
    _cobra(libro, milesimas=12_340)
    libro.configurar("otro", usuario="admin", cobrar=True)
    with db.conectar() as con:
        libro.acreditar(con, "otro", "ajuste", 77_000, "ajuste", usuario="admin", detalle="nota de otro")
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    seccion = _seccion(html, "config-ap-saldo")
    assert 'data-apartado="saldo"' in html and "data-saldo-panel=" in seccion
    assert "US$ 12,34" not in seccion                                    # el libro llega por fetch
    r = pagina().get("/cliente/acme/saldo/panel")
    assert r.status_code == 200
    panel = r.get_data(as_text=True)
    assert "US$ 12,34" in panel and "nota de otro" not in panel
    assert pagina("otro", "cliente", "otro").get("/cliente/acme/saldo/panel").status_code == 302
    csv = pagina().get("/cliente/acme/saldo/movimientos.csv")
    texto = csv.get_data(as_text=True)
    assert csv.status_code == 200 and texto.startswith("﻿") and "12,34" in texto
    assert "nota de otro" not in texto and "77" not in texto
    assert pagina("otro", "cliente", "otro").get("/cliente/acme/saldo/movimientos.csv").status_code == 302


def test_sin_llaves_de_bold_no_hay_boton_de_pago(libro, pagina, monkeypatch):
    _cobra(libro, milesimas=1_000)
    panel = pagina().get("/cliente/acme/saldo/panel").get_data(as_text=True)
    assert "Las recargas en línea todavía no están disponibles; escríbenos para recargar." in panel
    assert "Pagar con Bold" not in panel
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", "identidad-falsa")  # llave-de-prueba
    panel = pagina().get("/cliente/acme/saldo/panel").get_data(as_text=True)
    assert "Pagar con Bold" in panel and 'name="usd"' in panel
    assert 'min="10"' in panel and 'max="1000"' in panel
    assert "Tarjetas de cualquier país; en Colombia también PSE y Nequi." in panel


def test_el_panel_lista_recargas_y_ofrece_verificar_las_pendientes(libro, pagina, monkeypatch):
    import db
    from cobros import recargas
    _cobra(libro)
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(db.recarga.insert().values(cliente="acme", creada_en=ahora, actualizada_en=ahora, medio="bold",
                                               estado="pendiente", milesimas=50_000, referencia="cv-1-1",
                                               usuario="user_acme"))
    rid = recargas.de_proyecto("acme")[0]["id"]
    panel = pagina().get("/cliente/acme/saldo/panel").get_data(as_text=True)
    assert f"/cliente/acme/saldo/recarga/{rid}/verificar" in panel and "US$ 50,00" in panel


def test_ver_mas_trae_la_pagina_siguiente(libro, pagina):
    import db
    _cobra(libro)
    with db.conectar() as con:
        for i in range(60):
            libro.acreditar(con, "acme", "ajuste", 1_000, "ajuste", usuario="admin", detalle=f"fila {i}")
    panel = pagina().get("/cliente/acme/saldo/panel").get_data(as_text=True)
    assert "fila 59" in panel and "fila 9<" not in panel and "/cliente/acme/saldo/movimientos?pagina=2" in panel
    mas = pagina().get("/cliente/acme/saldo/movimientos?pagina=2").get_data(as_text=True)
    assert "fila 9<" in mas and "fila 59" not in mas and "<tr" in mas


def test_el_admin_ve_el_apartado_aunque_el_proyecto_no_cobre(libro, pagina):
    html = pagina("admin", "admin", None).get("/cliente/acme").get_data(as_text=True)
    assert 'id="config-ap-saldo"' in html
    assert pagina("admin", "admin", None).get("/cliente/acme/saldo/panel").status_code == 200
    assert pagina().get("/cliente/acme/saldo/panel").status_code == 404


# --- chip -----------------------------------------------------------------------------------

@pytest.mark.parametrize("saldo,tono", [(3_000, "aviso"), (0, "bloqueo"), (20_000, "normal")])
def test_el_chip_cambia_de_tono_con_el_saldo(libro, saldo, tono):
    import dashboard
    from cobros import vista
    _cobra(libro, milesimas=saldo, umbral=5_000)
    with dashboard.app.test_request_context("/cliente/acme"):
        c = vista.chip("acme", es_admin=False)
    assert c["tono"] == tono and c["url"].endswith("#config-ap-saldo")
    assert "Saldo:" in c["texto"] and "Recargar" in c["texto"]


def test_sin_cobrar_no_hay_chip_de_saldo_y_queda_el_de_hoy(libro, pagina):
    import dashboard
    from cobros import vista
    with dashboard.app.test_request_context("/cliente/acme"):
        assert vista.chip("acme", es_admin=False) is None
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    assert "Este mes:" in html and "sidebar-saldo" not in html


def test_el_chip_de_la_barra_lateral_lleva_al_saldo(libro, pagina):
    _cobra(libro, milesimas=3_000)
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    assert "sidebar-saldo saldo-aviso" in html and "Saldo: US$ 3,00 · Recargar" in html
    admin = pagina("admin", "admin", None).get("/cliente/acme").get_data(as_text=True)
    assert "costo del mes" in admin


# --- la vuelta del pago ---------------------------------------------------------------------

def test_la_pagina_de_vuelta_sondea_por_data_y_sin_script_en_linea(libro, pagina):
    import db
    from cobros import recargas
    _cobra(libro)
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(db.recarga.insert().values(cliente="acme", creada_en=ahora, actualizada_en=ahora, medio="bold",
                                               estado="pendiente", milesimas=20_000, referencia="cv-2-2",
                                               usuario="user_acme"))
    rid = recargas.de_proyecto("acme")[0]["id"]
    html = pagina().get(f"/cliente/acme/saldo/recarga/{rid}").get_data(as_text=True)
    assert f'data-estado-url="/cliente/acme/saldo/recarga/{rid}/estado"' in html
    assert "Verificando tu pago…" in html
    cuerpo = html.split('id="recarga-vuelta"', 1)[1].split("</main>", 1)[0]
    assert "<script>" not in cuerpo and "Bold todavía no confirma el pago" in cuerpo
    assert "cobros.js" in html


def test_cobros_js_esta_en_la_pagina_del_proyecto(libro, pagina):
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    assert re.search(r'<script src="/static/cobros\.js[^"]*" defer data-texto-recargar="Recargar saldo"', html)


# --- revisión 8/11: fallar cerrado y el evento del sprint ------------------------------------

def _pieza_con_gasto(libro):
    import creative_flow as cf
    import gastos
    _cobra(libro, milesimas=50_000)
    cf_id = cf.crear("acme", [], ["Chancla"], [], "camina", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4", enfoque="producto", usd=1.0)
    gastos.registrar("acme", "video", 1.0, f"video:{cf_id}:t1")
    return cf_id


@pytest.mark.parametrize("roto", ["_filas_cobradas", "cobra", "gasto_para"])
def test_si_una_lectura_falla_el_cliente_no_ve_el_costo(libro, pagina, monkeypatch, roto):
    """Spec §11: ante un error, quien no es admin de un proyecto que cobra ve «—» o nada, nunca el costo."""
    from cobros import vista
    cf_id = _pieza_con_gasto(libro)

    def falla(*a, **k):
        raise RuntimeError("base caída")
    monkeypatch.setattr(vista, roto, falla)
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    assert "US$ 1,00" not in _seccion(html, "config-ap-gasto")
    assert "Este mes: US$ 1,00" not in html
    detalle = pagina().get(f"/cliente/acme/creative_flow/{cf_id}/detalle").get_data(as_text=True)
    assert "US$ 1,00" not in detalle
    # el admin puede seguir viendo el costo
    admin = pagina("admin", "admin", None).get(f"/cliente/acme/creative_flow/{cf_id}/detalle").get_data(as_text=True)
    assert "costó US$ 1,00" in admin


def test_ver_cobrado_y_el_filtro_fallan_cerrados(libro, monkeypatch):
    import dashboard
    from cobros import vista
    from flask import g, session
    _cobra(libro)

    def falla(*a, **k):
        raise RuntimeError("base caída")
    monkeypatch.setattr(vista, "cobra", falla)
    for rol, oculta in (("cliente", True), ("admin", False)):
        with dashboard.app.test_request_context("/cliente/acme"):
            session["rol"] = rol
            g.cliente_precio = "acme"
            assert dashboard._ver_cobrado() is oculta                      # swaps e imagen de idea sin créditos ni costo
            assert dashboard._filtro_cobrado(None, 1.0, "video:x") == (None if oculta else 1.0)


def test_el_evento_de_cierre_guarda_lo_cobrado_aunque_cierre_el_admin(libro, monkeypatch, tmp_path):
    import creative_flow
    import dashboard
    import gastos
    from flask import session
    from sprints import datos, estado, revision
    from tests.test_sprints_revision_entrega import _sprint_en_revision
    _cobra(libro)
    sid, _cid, piezas = _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path)
    gastos.registrar("acme", "video", 2.0, f"video:{piezas[0][1]}:t1")     # cobrado 3,00; costo de las piezas 1,50
    assert estado.recalcular("acme", sid)["estado"] == "revision"
    with dashboard.app.test_request_context("/cliente/acme"):
        session["rol"] = "admin"
        r = revision.cerrar("acme", sid)
    assert r["costo_usd"] == 1.5                                            # el admin ve el costo en pantalla
    ev = next(e for e in datos.eventos("acme", sid) if e["tipo"] == "sprint_cerrado")
    assert "USD 3.00" in ev["mensaje"] and ev["datos"]["costo_usd"] == 3.0


def test_los_dos_chips_de_la_barra_fallan_por_separado(libro, pagina, monkeypatch):
    import db
    from cobros import recargas, vista
    _cobra(libro, milesimas=3_000)
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(db.recarga.insert().values(cliente="acme", creada_en=ahora, actualizada_en=ahora, medio="bold",
                                               estado="aprobada", milesimas=3_000, referencia="cv-9-9", usuario="user_acme"))
    ruta = f"/cliente/acme/saldo/recarga/{recargas.de_proyecto('acme')[0]['id']}"   # pasa por _chip_gasto_sidebar

    def falla(*a, **k):
        raise RuntimeError("base caída")
    with monkeypatch.context() as m:
        m.setattr(vista, "chip", falla)
        html = pagina().get(ruta).get_data(as_text=True)
        assert "Este mes:" in html and "sidebar-saldo" not in html
    with monkeypatch.context() as m:
        m.setattr(vista, "gasto_para", falla)
        html = pagina().get(ruta).get_data(as_text=True)
        assert "sidebar-saldo" in html and "Este mes:" not in html


def test_el_historial_de_experimentos_muestra_lo_cobrado_con_texto_neutro(libro, pagina):
    _pieza_con_gasto(libro)
    cliente = pagina().get("/cliente/acme/experimentos/resultados").get_data(as_text=True)
    assert "1 cobro →" in cliente and "a proveedores" not in cliente
    assert "US$ 1,50" in cliente and "US$ 1,00" not in cliente
    admin = pagina("admin", "admin", None).get("/cliente/acme/experimentos/resultados").get_data(as_text=True)
    assert "cobro(s) a proveedores →" in admin

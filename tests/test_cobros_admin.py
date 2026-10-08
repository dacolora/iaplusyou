"""/admin/cobros (spec 2026-10-08 §10 y §11): margen global, «Cobrar» por
proyecto, margen propio, umbral, recarga manual y ajuste, las cifras del mes
(recargado, cobrado, costo de lo cobrado, ganancia) y los eventos de Bold.
Todo solo para el admin y con POST del mismo origen."""
import re
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import event

MISMO = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import estado
    import proyectos
    from cobros import avisos, recargas
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(estado, "listar_clientes", lambda: ["acme", "otro"])
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD", raising=False)
    monkeypatch.delenv("BOLD_LLAVE_SECRETA", raising=False)
    monkeypatch.delenv("BOLD_PRUEBAS", raising=False)
    avisados = []
    for nombre in ("recarga_acreditada", "recarga_admin", "limpiar_aviso_bajo"):
        monkeypatch.setattr(avisos, nombre, lambda *a, _n=nombre, **k: avisados.append((_n, a)))
    monkeypatch.setattr(recargas, "_en_segundo_plano", lambda fn: fn())
    return base_temporal


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


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


def _acreditar(cliente, milesimas):
    import db
    from cobros import libro
    with db.conectar() as con:
        libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


# --- acceso -----------------------------------------------------------------------------------

def test_quien_no_es_admin_va_al_login_con_el_aviso(http):
    c = http.como("user_acme")
    r = c.get("/admin/cobros")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert "Esa página es solo para el administrador." in _flashes(c)
    r = c.post("/admin/cobros/acme/cuenta", data={"cobrar": "1"}, headers=MISMO)
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    from cobros import libro
    assert not libro.cobra("acme")
    for ruta, datos in (("/admin/cobros/margen", {"margen": "2"}),
                        ("/admin/cobros/acme/recarga", {"monto": "25", "nota": "", "tipo": "recarga"})):
        r = c.post(ruta, data=datos, headers=MISMO)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert libro.margen_global() == 1.5 and libro.saldo("acme") == 0


def test_el_admin_ve_los_proyectos(http):
    r = http.como("admin").get("/admin/cobros")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="fila-acme"' in html and 'id="fila-otro"' in html


def test_lista_tambien_un_proyecto_con_cuenta_que_no_esta_en_carpetas(http):
    from cobros import libro, vista
    libro.configurar("viejo", usuario="admin", cobrar=False)
    assert [p["cliente"] for p in vista.resumen_admin()] == ["acme", "otro", "viejo"]
    assert 'id="fila-viejo"' in http.como("admin").get("/admin/cobros").get_data(as_text=True)


def test_el_panel_enlaza_a_cobros(http):
    html = http.como("admin").get("/panel").get_data(as_text=True)
    assert 'href="/admin/cobros"' in html


# --- interruptor, margen propio y umbral ------------------------------------------------------

def test_prender_cobrar(http):
    from cobros import libro
    _acreditar("acme", 10_000)
    c = http.como("admin")
    r = c.post("/admin/cobros/acme/cuenta", data={"cobrar": "1"}, headers=MISMO)
    assert r.status_code == 302 and "/admin/cobros" in r.headers["Location"]
    assert libro.cobra("acme")
    assert not any("no tiene saldo" in m for m in _flashes(c))
    c.post("/admin/cobros/acme/cuenta", data={"cobrar": "0"}, headers=MISMO)
    assert not libro.cobra("acme")


def test_prender_cobrar_sin_saldo_avisa(http):
    from cobros import libro
    c = http.como("admin")
    c.post("/admin/cobros/acme/cuenta", data={"cobrar": "1"}, headers=MISMO)
    assert libro.cobra("acme")
    assert ("Este proyecto no tiene saldo: desde ahora no podrá generar nada que cueste hasta que recargue."
            in _flashes(c))


def test_un_post_de_otro_sitio_es_403(http):
    from cobros import libro
    c = http.como("admin")
    cruzado = {"Sec-Fetch-Site": "cross-site"}
    assert c.post("/admin/cobros/acme/cuenta", data={"cobrar": "1"}, headers=cruzado).status_code == 403
    assert c.post("/admin/cobros/margen", data={"margen": "2"}, headers=cruzado).status_code == 403
    assert c.post("/admin/cobros/acme/recarga", data={"monto": "25", "tipo": "recarga"},
                  headers=cruzado).status_code == 403
    assert not libro.cobra("acme") and libro.margen_global() == 1.5 and libro.saldo("acme") == 0


def test_margen_propio_y_umbral(http):
    from cobros import libro
    c = http.como("admin")
    c.post("/admin/cobros/acme/cuenta", data={"margen": "2,25", "umbral": "12.5"}, headers=MISMO)
    cta = libro.cuenta("acme")
    assert cta["margen"] == 2.25 and cta["margen_propio"] == 2.25 and cta["umbral"] == 12_500
    assert cta["cobrar"] is False   # tocar el margen no prende el interruptor
    c.post("/admin/cobros/acme/cuenta", data={"margen": "", "umbral": "12.5"}, headers=MISMO)
    cta = libro.cuenta("acme")
    assert cta["margen_propio"] is None and cta["margen"] == libro.margen_global()


@pytest.mark.parametrize("datos", [{"margen": "0.5"}, {"margen": "abc"}, {"umbral": "-1"}, {"umbral": "x"},
                                   {"umbral": "1e20"}])
def test_margen_propio_o_umbral_invalido_no_cambia_nada(http, datos):
    from cobros import libro
    libro.configurar("acme", usuario="admin", margen=2.0, umbral=7000)
    c = http.como("admin")
    r = c.post("/admin/cobros/acme/cuenta", data=datos, headers=MISMO)
    assert r.status_code == 302
    cta = libro.cuenta("acme")
    assert cta["margen_propio"] == 2.0 and cta["umbral"] == 7000
    assert _flashes(c)


def test_un_proyecto_que_no_existe_es_404(http):
    c = http.como("admin")
    assert c.post("/admin/cobros/inventado/cuenta", data={"cobrar": "1"}, headers=MISMO).status_code == 404
    assert c.post("/admin/cobros/inventado/recarga", data={"monto": "25", "tipo": "recarga"},
                  headers=MISMO).status_code == 404
    from cobros import libro
    assert libro.cuenta("inventado")["cobrar"] is False and libro.saldo("inventado") == 0


# --- margen global ----------------------------------------------------------------------------

def test_margen_global(http):
    from cobros import libro
    c = http.como("admin")
    c.post("/admin/cobros/margen", data={"margen": "2,5"}, headers=MISMO)
    assert libro.margen_global() == 2.5


@pytest.mark.parametrize("valor", ["0.5", "5.01", "", "abc"])
def test_margen_global_invalido_avisa_y_no_cambia(http, valor):
    from cobros import libro
    c = http.como("admin")
    r = c.post("/admin/cobros/margen", data={"margen": valor}, headers=MISMO)
    assert r.status_code == 302 and libro.margen_global() == 1.5
    assert _flashes(c)


# --- recarga manual y ajuste ------------------------------------------------------------------

def test_recarga_manual(http):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    c = http.como("admin")
    r = c.post("/admin/cobros/acme/recarga", data={"monto": "25", "nota": "transferencia", "tipo": "recarga"},
               headers=MISMO)
    assert r.status_code == 302 and libro.saldo("acme") == 25_000
    assert not any("todavía no cobra" in m for m in _flashes(c))


def test_recarga_manual_a_un_proyecto_que_no_cobra_avisa(http):
    from cobros import libro
    c = http.como("admin")
    c.post("/admin/cobros/otro/recarga", data={"monto": "10", "nota": "", "tipo": "recarga"}, headers=MISMO)
    assert libro.saldo("otro") == 10_000
    assert any("todavía no cobra" in m for m in _flashes(c))


def test_ajuste_sin_nota_avisa_y_no_escribe(http):
    from cobros import libro
    c = http.como("admin")
    c.post("/admin/cobros/acme/recarga", data={"monto": "-5", "nota": "  ", "tipo": "ajuste"}, headers=MISMO)
    assert libro.saldo("acme") == 0
    assert "Un ajuste necesita una nota." in _flashes(c)
    c.post("/admin/cobros/acme/recarga", data={"monto": "-5", "nota": "devolución", "tipo": "ajuste"}, headers=MISMO)
    assert libro.saldo("acme") == -5_000


@pytest.mark.parametrize("monto", ["1e20", "100000.01", "-100000.01", "abc", "0"])
def test_recarga_manual_fuera_de_rango_avisa_sin_500(http, monto):
    from cobros import libro
    c = http.como("admin")
    r = c.post("/admin/cobros/acme/recarga", data={"monto": monto, "nota": "x", "tipo": "ajuste"}, headers=MISMO)
    assert r.status_code == 302 and libro.saldo("acme") == 0 and _flashes(c)


@pytest.mark.parametrize("usd", ["1e20", 100_000.01, -100_000.01, "1e6"])
def test_manual_tiene_tope(entorno, usd):
    from cobros import libro, recargas
    with pytest.raises(ValueError):
        recargas.manual("acme", usd, "admin", "nota", tipo="ajuste")
    assert libro.saldo("acme") == 0


def test_manual_acepta_el_tope_justo(entorno):
    from cobros import libro, recargas
    recargas.manual("acme", "100000", "admin", "nota", tipo="recarga")
    recargas.manual("acme", -100_000, "admin", "nota", tipo="ajuste")
    assert libro.saldo("acme") == 0


# --- cifras del mes ---------------------------------------------------------------------------

def test_resumen_admin_cifras_del_mes(entorno):
    import db
    import gastos
    from cobros import libro, recargas, vista
    libro.configurar("acme", usuario="admin", cobrar=True, margen=1.5, umbral=3000)
    recargas.manual("acme", 20, "admin", "transferencia")                    # recarga 20 000
    hace_dos_meses = (datetime.now() - timedelta(days=62)).isoformat(timespec="seconds")
    gastos.registrar("acme", "video", 4.0, "video:viejo:t1", creado_en=hace_dos_meses)   # otro mes: fuera
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")                   # cobro 1 500, costo 1 000
    gid = gastos.registrar("acme", "video", 2.0, "video:cf2:t2")             # cobro 3 000 revertido, costo 2 000
    m = db.movimiento_saldo
    with db.conectar() as con:
        con.execute(m.update().where(m.c.gasto_id == gid).values(job_id="j-cf2"))
    libro.revertir_trabajo("acme", "j-cf2", motivo="falló")
    gastos.registrar("acme", "imagen", 0.5, "imagen:cf3:t3", entregado=False)   # no cobrado, costo 500
    gastos.registrar("otro", "video", 9.0, "video:o1:t1")                     # «otro» no cobra: sin cobro
    filas = {f["cliente"]: f for f in vista.resumen_admin()}
    a = filas["acme"]
    assert a["cobrar"] is True and a["margen"] == 1.5 and a["margen_propio"] == 1.5 and a["umbral"] == 3000
    assert a["saldo"] == libro.saldo("acme") and a["disponible"] == libro.disponible("acme")
    assert a["recargado_mes"] == 20_000
    assert a["cobrado_mes"] == 1_500                                         # el revertido no cuenta
    assert a["costo_mes"] == 1_000 + 2_000 + 500
    assert a["ganancia_mes"] == 1_500 - 3_500
    o = filas["otro"]
    assert o["cobrar"] is False and o["margen_propio"] is None and o["umbral"] == libro.UMBRAL_DEFECTO
    assert (o["saldo"], o["recargado_mes"], o["cobrado_mes"], o["costo_mes"], o["ganancia_mes"]) == (0, 0, 0, 0, 0)


def test_resumen_admin_recargado_descuenta_anulaciones_y_no_cuenta_ajustes(entorno):
    import db
    from cobros import libro, recargas, vista
    recargas.manual("acme", 30, "admin", "")
    recargas.manual("acme", 5, "admin", "regalo", tipo="ajuste")
    with db.conectar() as con:
        libro.acreditar(con, "acme", "anulacion", -10_000, "anulacion_bold")
    a = {f["cliente"]: f for f in vista.resumen_admin()}["acme"]
    assert a["recargado_mes"] == 20_000 and a["saldo"] == 25_000


def _sembrar(n):
    import gastos
    from cobros import libro, recargas
    nombres = [f"p{i}" for i in range(n)]
    for c in nombres:
        libro.configurar(c, usuario="admin", cobrar=True)
        recargas.manual(c, 50, "admin", "")
        gastos.registrar(c, "video", 1.0, f"video:{c}:t1")
        gastos.registrar(c, "imagen", 0.2, f"imagen:{c}:t2")
    return nombres


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


def test_resumen_admin_no_hace_una_consulta_por_proyecto(entorno, monkeypatch):
    import estado
    from cobros import vista
    monkeypatch.setattr(estado, "listar_clientes", lambda: [])
    _sembrar(3)
    con_tres = _consultas(vista.resumen_admin)
    assert len(vista.resumen_admin()) == 3
    _sembrar(6)   # p0..p5: tres nuevos
    con_seis = _consultas(vista.resumen_admin)
    assert len(vista.resumen_admin()) == 6
    assert con_tres == con_seis <= 10


def test_la_pagina_no_hace_una_consulta_por_proyecto(http, monkeypatch):
    import estado
    monkeypatch.setattr(estado, "listar_clientes", lambda: [])
    c = http.como("admin")
    _sembrar(3)
    con_tres = _consultas(lambda: c.get("/admin/cobros"))
    _sembrar(6)
    con_seis = _consultas(lambda: c.get("/admin/cobros"))
    assert con_tres == con_seis


# --- eventos de Bold --------------------------------------------------------------------------

def _evento(db, n, firma_ok=True, recibido=None, resultado="acreditada", tipo="SALE_APPROVED"):
    with db.conectar() as con:
        con.execute(db.pago_evento.insert().values(
            proveedor="bold", evento_id=f"ev-{n}-{firma_ok}", tipo=tipo, referencia=f"cv-{n}-1",
            recibido_en=recibido or db.ahora(), firma_ok=firma_ok, resultado=resultado))


def _pendiente(db, cliente="acme"):
    with db.conectar() as con:
        con.execute(db.recarga.insert().values(
            cliente=cliente, creada_en=db.ahora(), actualizada_en=db.ahora(), medio="bold", estado="pendiente",
            milesimas=10_000, referencia="cv-99-1", usuario="user_acme"))


def test_ultimos_eventos_solo_los_firmados_y_el_mas_nuevo_primero(entorno):
    from cobros import vista
    db = entorno
    for i in range(25):
        _evento(db, i)
    _evento(db, 100, firma_ok=False, resultado="firma_invalida")
    ev = vista.ultimos_eventos()
    assert len(ev) == 20 and ev[0]["referencia"] == "cv-24-1"
    assert all(e["resultado"] != "firma_invalida" for e in ev)
    assert set(ev[0]) >= {"recibido_en", "tipo", "referencia", "resultado"}


def test_webhook_callado(entorno):
    from cobros import vista
    db = entorno
    assert vista.webhook_callado() is False                         # sin recargas pendientes
    _pendiente(db)
    assert vista.webhook_callado() is True                          # pendiente y ningún evento
    viejo = (datetime.now() - timedelta(days=8)).isoformat(timespec="seconds")
    _evento(db, 1, recibido=viejo)
    assert vista.webhook_callado() is True                          # el único evento es de hace 8 días
    _evento(db, 2, firma_ok=False, resultado="firma_invalida")
    assert vista.webhook_callado() is True                          # uno sin firma no cuenta
    _evento(db, 3)
    assert vista.webhook_callado() is False


def test_la_pagina_muestra_eventos_y_el_aviso_del_webhook(http):
    import db
    _pendiente(db)
    c = http.como("admin")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-webhook"' in html
    _evento(db, 7, resultado="acreditada")
    _evento(db, 8, firma_ok=False, resultado="firma_invalida")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-webhook"' not in html
    assert "cv-7-1" in html and "cv-8-1" not in html


def test_avisos_de_configuracion_de_bold(http, monkeypatch):
    c = http.como("admin")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-bold-llaves"' in html and 'id="aviso-bold-pruebas"' not in html
    monkeypatch.setenv("BOLD_LLAVE_IDENTIDAD", "identidad-falsa")  # llave-de-prueba
    monkeypatch.setenv("BOLD_PRUEBAS", "1")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-bold-llaves"' in html and 'id="aviso-bold-pruebas"' in html   # falta la secreta
    monkeypatch.setenv("BOLD_LLAVE_SECRETA", "secreta-falsa")  # llave-de-prueba
    monkeypatch.delenv("BOLD_PRUEBAS")
    html = c.get("/admin/cobros").get_data(as_text=True)
    assert 'id="aviso-bold-llaves"' not in html and 'id="aviso-bold-pruebas"' not in html
    assert "secreta-falsa" not in html and "identidad-falsa" not in html


def test_la_pagina_muestra_las_cifras_con_formato(http):
    import gastos
    from cobros import libro, recargas
    libro.configurar("acme", usuario="admin", cobrar=True, margen=2.0)
    recargas.manual("acme", 20, "admin", "")
    gastos.registrar("acme", "video", 1.0, "video:cf1:t1")   # cobro 2 000, costo 1 000
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    fila = re.search(r'<tr id="fila-acme".*?</tr>', html, re.S).group(0)
    for cifra in ("US$ 18,00", "US$ 20,00", "US$ 2,00", "US$ 1,00"):
        assert cifra in fila


# --- el valor guardado y el separador de los campos (revisión de la tarea 10) ----------------

def test_el_aviso_del_margen_global_dice_lo_que_quedo_guardado(http):
    """«2,505» se guarda redondeado a 2 decimales: el aviso dice 2,51, no 2,505."""
    from cobros import libro
    c = http.como("admin")
    c.post("/admin/cobros/margen", data={"margen": "2,505"}, headers=MISMO)
    assert libro.margen_global() == 2.51
    assert "Margen global guardado: 2,51." in _flashes(c)


def test_el_margen_se_redondea_antes_de_mirar_el_rango(http):
    """5,004 entra (queda en 5,00); 0,996 también (queda en 1,00); 5,006 no."""
    from cobros import libro
    c = http.como("admin")
    c.post("/admin/cobros/margen", data={"margen": "5,004"}, headers=MISMO)
    assert libro.margen_global() == 5.0
    c.post("/admin/cobros/margen", data={"margen": "0,996"}, headers=MISMO)
    assert libro.margen_global() == 1.0
    c.post("/admin/cobros/margen", data={"margen": "5,006"}, headers=MISMO)
    assert libro.margen_global() == 1.0   # rechazado: no cambió


def test_el_margen_propio_guarda_lo_redondeado(http):
    from cobros import libro
    http.como("admin").post("/admin/cobros/acme/cuenta", data={"margen": "2.255"}, headers=MISMO)
    assert libro.cuenta("acme")["margen_propio"] == 2.26


def _valor_del_campo(html, nombre, fila=None):
    zona = re.search(rf'<tr id="fila-{fila}".*?</tr>', html, re.S).group(0) if fila else html
    return re.search(rf'name="{nombre}"[^>]*?value="([^"]*)"', zona).group(1)


def test_los_campos_llevan_el_separador_de_quien_mira(http):
    from cobros import libro
    libro.guardar_margen_global(1.75, "admin")
    libro.configurar("acme", usuario="admin", margen=2.25, umbral=12_500)
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    assert _valor_del_campo(html, "margen") == "1,75"
    assert _valor_del_campo(html, "margen", fila="acme") == "2,25"
    assert _valor_del_campo(html, "umbral", fila="acme") == "12,50"
    assert _valor_del_campo(html, "margen", fila="otro") == ""


def test_los_campos_en_ingles_llevan_punto_y_sin_miles(http, monkeypatch):
    import idiomas
    from cobros import libro
    monkeypatch.setattr(idiomas, "de_usuario", lambda _usuario: "en")
    libro.configurar("acme", usuario="admin", margen=2.25, umbral=1_500_000)
    html = http.como("admin").get("/admin/cobros").get_data(as_text=True)
    assert _valor_del_campo(html, "margen", fila="acme") == "2.25"
    assert _valor_del_campo(html, "umbral", fila="acme") == "1500.00"   # sin «1,500.00»: el parser no lo leería


def test_lo_que_el_campo_muestra_se_vuelve_a_guardar_igual(http):
    """El ciclo del formulario: mostrar, enviar sin tocar, y no cambia nada."""
    from cobros import libro
    libro.configurar("acme", usuario="admin", margen=2.25, umbral=12_500)
    c = http.como("admin")
    html = c.get("/admin/cobros").get_data(as_text=True)
    c.post("/admin/cobros/acme/cuenta", data={"margen": _valor_del_campo(html, "margen", fila="acme"),
                                              "umbral": _valor_del_campo(html, "umbral", fila="acme")}, headers=MISMO)
    cta = libro.cuenta("acme")
    assert cta["margen_propio"] == 2.25 and cta["umbral"] == 12_500

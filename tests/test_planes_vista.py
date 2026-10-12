"""Lo que ve el cliente de los planes (planes 6/8, spec 2026-10-09 §5.2, §7 y
§8): Configuración › Plan (sin plan, con plan, morosa, cancelada, anulada, a
mano), el alta con un token de Wompi simulado (lo que el widget pone en el
formulario se confirma en sandbox: docs/pagos/wompi-api.md §13.1), Nequi,
cancelar, el chip y el saldo partido. Wompi y la TRM son falsos; la base es real.

Lo que no se negocia: sin las tres casillas no se habla con Wompi; el cliente
nunca ve el costo, ni el margen, ni el tope de lo incluido en dólares."""
import re

import pytest
import sqlalchemy as sa

from tests.test_planes import ACEPTACION, TRM, WompiFalso

LLAVE = "pub_test_widgetdeprueba"  # llave-de-prueba


@pytest.fixture()
def base(base_temporal, monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD", raising=False)
    return base_temporal


@pytest.fixture()
def falso(base, monkeypatch):
    from cobros import trm, wompi
    f = WompiFalso(wompi)
    f.nequi = {}
    monkeypatch.setattr(wompi, "configurado", lambda: True)
    monkeypatch.setattr(wompi, "llave_publica", lambda: LLAVE)
    monkeypatch.setattr(wompi, "crear_fuente", f.crear_fuente)
    monkeypatch.setattr(wompi, "cobrar_fuente", f.cobrar_fuente)
    monkeypatch.setattr(wompi, "transaccion", f.transaccion)
    monkeypatch.setattr(wompi, "aceptaciones", lambda tiempo=None: {
        "acceptance_token": "eyJ.acepta.widget", "acceptance_url": "https://wompi.co/terminos.pdf",
        "personal_token": "eyJ.datos.widget", "personal_url": "https://wompi.com/datos.pdf"})

    def token_nequi(celular, tiempo=None):
        token = f"nequi_test_{len(f.nequi) + 1}"
        f.nequi[token] = "PENDING"
        return token
    monkeypatch.setattr(wompi, "token_nequi", token_nequi)
    monkeypatch.setattr(wompi, "estado_token_nequi", lambda token, tiempo=None: f.nequi[token])
    monkeypatch.setattr(trm, "actual", lambda: TRM)
    return f


@pytest.fixture()
def avisos(monkeypatch):
    import idiomas
    import notificaciones
    enviados = []
    monkeypatch.setattr(idiomas, "de_proyecto", lambda cliente: "es")
    monkeypatch.setattr(notificaciones, "avisar", lambda *a, **k: enviados.append(a) or True)
    monkeypatch.setattr(notificaciones, "avisar_admin", lambda *a, **k: enviados.append(a) or 1)
    return enviados


@pytest.fixture()
def pagina(base, monkeypatch):
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


@pytest.fixture()
def pro(base):
    from cobros import planes
    return planes.crear_plan("Pro", 1000, 1.25, 25, precio_anual_usd=10000, usuario="admin")


def _cobra(cliente="acme"):
    from cobros import libro
    libro.configurar(cliente, usuario="admin", cobrar=True)      # margen a la carta: el global, 2,0


def _suscrito(pro, cliente="acme"):
    import db
    from cobros import planes
    _cobra(cliente)
    r = planes.suscribir(cliente, pro, "mensual", "CARD", "tok_test_1_prueba", "pagos@acme.co", dict(ACEPTACION),
                         "user_acme", 1000, ahora=db.ahora())
    assert r["estado"] == "aprobado"
    return r


def _panel(pagina, **k):
    r = pagina(**k).get("/cliente/acme/plan/panel")
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _texto(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _form_alta(pro, **cambios):
    datos = {"plan_id": str(pro), "ciclo": "mensual", "precio_visto_usd": "1000",
             "acceptance_token": "eyJ.acepta.widget", "personal_token": "eyJ.datos.widget",
             "acepta_terminos": "1", "acepta_datos": "1", "autoriza_cobro": "1",
             "tipo": "CARD", "token": "tok_test_77_ABCdef", "correo": "pagos@acme.co"}
    datos.update(cambios)
    return {k: v for k, v in datos.items() if v is not None}


def _sin_costo(texto):
    """Ni el margen del plan (1,25), ni el tope de lo incluido (US$ 25), ni los costos sembrados."""
    for prohibido in ("1,25", "US$ 25,00", "US$ 25 ", "US$ 100,00", "US$ 5,00", "margen", "costo"):
        assert prohibido not in texto, prohibido


# --- sin plan ------------------------------------------------------------------------------

def test_sin_plan_ofrece_los_planes_con_precio_y_sin_costo(base, pagina, pro, falso):
    _cobra()
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    seccion = re.search(r'<section class="config-apartado" id="config-ap-plan".*?</section>', html, re.S).group(0)
    assert 'data-plan-panel="/cliente/acme/plan/panel"' in seccion and "Pro" not in seccion   # llega por fetch
    assert "checkout.wompi.co" not in html                       # el widget solo en el formulario de alta
    texto = _texto(_panel(pagina))
    assert "Pro" in texto and "US$ 1.000 al mes" in texto and "o US$ 10.000 al año" in texto
    assert "2 meses gratis" in texto
    assert "tus generaciones cuestan 38 % menos que a la carta" in texto        # 1 − 1,25 / 2,0
    assert "Ideas, guiones, análisis y revisiones con IA incluidos." in texto and "Prioridad en la cola." in texto
    assert "El saldo del plan se renueva cada mes y no se acumula." in texto
    assert f"/cliente/acme/plan/alta?plan={pro}" in _panel(pagina)
    _sin_costo(texto)


def test_sin_wompi_no_hay_boton_de_suscribirse(base, pagina, pro, monkeypatch):
    from cobros import wompi
    monkeypatch.setattr(wompi, "configurado", lambda: False)
    _cobra()
    panel = _panel(pagina)
    assert "Suscribirme" not in panel and "escríbenos para activar tu plan" in panel


def test_solo_quien_entra_a_un_proyecto_que_cobra(base, pagina, pro, falso):
    assert pagina().get("/cliente/acme/plan/panel").status_code == 404           # no cobra
    assert 'id="config-ap-plan"' not in pagina().get("/cliente/acme").get_data(as_text=True)
    assert pagina("admin", "admin", None).get("/cliente/acme/plan/panel").status_code == 200
    _cobra()
    assert pagina().get("/cliente/acme/plan/panel").status_code == 200
    assert pagina("otro", "cliente", "otro").get("/cliente/acme/plan/panel").status_code == 302


# --- con plan ------------------------------------------------------------------------------

def test_con_plan_el_medidor_lo_incluido_y_el_ahorro(base, pagina, pro, falso, avisos):
    import gastos
    _suscrito(pro)
    gastos.registrar("acme", "video", 100.0, "video:cf1:t1")      # a precio de miembro: 125 de la bolsa
    gastos.registrar("acme", "guion", 5.0, "guion:cf1:t2")        # incluido: 5 de 25 de tope = 20 %
    texto = _texto(_panel(pagina))
    assert "Plan Pro" in texto and "Activo" in texto
    assert "US$ 875,00 restantes" in texto and "Usaste US$ 125,00 de US$ 1.000,00 (12 %)" in texto
    assert "20 % usado" in texto
    # ahorro: 125 × (2,0 / 1,25 − 1) = 75 del video + 6,25 × 2,0 / 1,25 = 10 del guion incluido
    assert "Este periodo ahorraste US$ 85,00 frente a la carta." in texto
    # El momento real del cobro (una hora antes del fin de lo pagado), con la hora (revisión final 2026-10-10).
    from cobros import planes
    hora = planes.suscripcion("acme")["proximo_cobro"][11:16]
    assert re.search(r"Se renueva el \d{1,2} de \w+ de \d{4} a las " + hora + r": a esa hora cobramos US\$ 1\.000\.",
                     texto)
    assert "Visa ···4242" in texto and "Cambiar tarjeta" in texto and "Aprobado" in texto
    assert re.search(r"Si cancelas antes del \d{1,2} de \w+ de \d{4} a las " + hora + r", no se vuelve a cobrar\. "
                     r"Tu plan sigue hasta el", texto)
    assert "No se devuelve lo ya pagado." in texto
    _sin_costo(texto)


def test_morosa_avisa_arriba_con_actualizar_tarjeta(base, pagina, pro, falso, avisos):
    import db
    _suscrito(pro)
    with db.conectar() as con:
        con.execute(db.suscripcion.update().values(estado="morosa", intentos_fallidos=1,
                                                   proximo_cobro="2099-01-01T10:00:00"))
    html = _panel(pagina)
    texto = _texto(html)
    assert "No pudimos cobrar tu plan." in texto and "quedan 2 intentos antes de perder el plan" in texto
    assert "Mientras tanto generas con tu saldo propio a precio a la carta." in texto
    aviso = html.index("No pudimos cobrar"), html.index("Plan Pro")
    assert aviso[0] < aviso[1]                                   # arriba de todo
    assert 'href="/cliente/acme/plan/tarjeta"' in html and "Actualizar tarjeta" in texto


def test_activado_a_mano_y_anulado_se_explican_en_palabras(base, pagina, pro, falso, avisos):
    from cobros import planes
    _cobra()
    planes.activar_manual("acme", pro, "mensual", "admin", nota="transferencia interna 123")
    texto = _texto(_panel(pagina))
    assert "lo activó Creatv con un pago por transferencia: no se cobra solo" in texto
    assert "transferencia interna 123" not in texto              # la nota del admin no se muestra
    assert "Sin tarjeta registrada" in texto and "Cambiar tarjeta" not in texto
    planes.terminar_ya("acme", "admin")
    _suscrito(pro)
    tx = {**next(iter(falso.txs.values())), "status": "VOIDED"}
    planes.aplicar_transaccion(tx)
    texto = _texto(_panel(pagina))
    assert "Wompi anuló un pago del plan, así que dejamos de cobrarlo solo." in texto and "Anulado" in texto


def test_un_pago_pendiente_se_sondea(base, pagina, pro, falso, avisos):
    import db
    from cobros import planes
    _cobra()
    falso.defecto = "PENDING"
    r = planes.suscribir("acme", pro, "mensual", "CARD", "tok_test_1_prueba", "pagos@acme.co", dict(ACEPTACION),
                         "user_acme", 1000, ahora=db.ahora())
    html = _panel(pagina)
    url = f"/cliente/acme/plan/pago/{r['pago_id']}/estado"
    assert f'data-plan-sondeo="{url}"' in html
    assert pagina().get(url).get_json() == {"estado": "pendiente"}
    falso.txs[next(iter(falso.txs))]["status"] = "APPROVED"
    from cobros import rutas
    rutas._ULTIMA_VERIFICACION.clear()
    assert pagina().get(url).get_json() == {"estado": "aprobado"}
    assert pagina("otro", "cliente", "otro").get(url).status_code == 302


def test_el_panel_no_hace_una_consulta_por_pago(base, pagina, pro, falso, avisos):
    import db
    _suscrito(pro)
    with db.conectar() as con:
        sid = con.execute(sa.select(db.suscripcion.c.id)).scalar()

    def medir():
        n = []

        def uno(*a):
            n.append(1)
        sa.event.listen(db.engine(), "before_cursor_execute", uno)
        try:
            _panel(pagina)
        finally:
            sa.event.remove(db.engine(), "before_cursor_execute", uno)
        return len(n)
    medir()                                                      # la primera petición calienta cachés
    pocos = medir()
    with db.conectar() as con:
        for i in range(15):
            con.execute(db.pago_plan.insert().values(
                cliente="acme", suscripcion_id=sid, ciclo="mensual", usd=1000, referencia=f"pl-{sid}-20200101-{i + 9}",
                estado="rechazado", motivo="Fondos insuficientes", creado_en="2020-01-01T10:00:00",
                actualizado_en="2020-01-01T10:00:00", medio="wompi"))
    assert medir() == pocos


def test_si_falla_la_lectura_no_sale_ninguna_cifra(base, pagina, pro, falso, avisos, monkeypatch):
    from cobros import planes
    _suscrito(pro)
    monkeypatch.setattr(planes, "estado_cliente", lambda cliente, ahora=None: 1 / 0)
    r = pagina().get("/cliente/acme/plan/panel")
    texto = r.get_data(as_text=True)
    assert r.status_code == 500 and "No se pudo cargar el plan" in texto and "US$" not in texto


# --- el alta -------------------------------------------------------------------------------

def test_el_formulario_carga_el_widget_con_la_llave_publica(base, pagina, pro, falso):
    _cobra()
    html = pagina().get(f"/cliente/acme/plan/alta?plan={pro}").get_data(as_text=True)
    assert '<script src="https://checkout.wompi.co/widget.js" data-render="button" ' \
           f'data-widget-operation="tokenize" data-public-key="{LLAVE}"></script>' in html
    # El widget exige ser hijo DIRECTO de un <form method="POST"> (su error de consola, visto el 2026-10-10).
    inicio = html.index('<form method="POST" class="plan-form"')
    form = html[inicio:html.index("</form>", inicio)]
    script = form.index('<script src="https://checkout.wompi.co/widget.js"')
    assert form[:script].count("<div") == form[:script].count("</div>")
    assert form[:script].count("<fieldset") == form[:script].count("</fieldset>")
    for casilla in ("acepta_terminos", "acepta_datos", "autoriza_cobro"):
        assert f'name="{casilla}" value="1" required' in html
    assert 'name="precio_visto_usd" value="1000"' in html and 'value="eyJ.acepta.widget"' in html
    assert "https://wompi.co/terminos.pdf" in html and "https://wompi.com/datos.pdf" in html
    texto = _texto(html)
    assert ("Autorizo el cobro automático de US$ 1.000 cada mes (en pesos colombianos a la TRM del día) hasta que "
            "cancele. El saldo del plan se renueva cada mes y no se acumula.") in texto
    anual = _texto(pagina().get(f"/cliente/acme/plan/alta?plan={pro}&ciclo=anual").get_data(as_text=True))
    assert "Autorizo el cobro automático de US$ 10.000 cada año" in anual
    assert 'value="10000"' in pagina().get(f"/cliente/acme/plan/alta?plan={pro}&ciclo=anual").get_data(as_text=True)
    assert "prv_" not in html and "1,25" not in texto
    assert "Visa, Mastercard o American Express, con código de seguridad." in texto   # Wompi acepta Amex


def test_alta_sin_una_casilla_no_habla_con_wompi(base, pagina, pro, falso, avisos):
    _cobra()
    for falta in ("acepta_terminos", "acepta_datos", "autoriza_cobro"):
        r = pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro, **{falta: None}))
        assert r.status_code == 302 and "/plan/alta" in r.headers["Location"]
    r = pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro, autoriza_cobro="on"))
    assert falso.fuentes == [] and falso.posts == []
    from cobros import planes
    assert planes.suscripcion("acme") is None


def test_alta_con_el_token_simulado_activa_el_plan(base, pagina, pro, falso, avisos):
    from cobros import planes
    _cobra()
    c = pagina()
    r = c.post("/cliente/acme/plan/alta", data=_form_alta(pro))
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#config-ap-plan")
    (fuente,) = falso.fuentes
    assert fuente == ("CARD", "tok_test_77_ABCdef", "pagos@acme.co", "eyJ.acepta.widget", "eyJ.datos.widget")
    sus = planes.suscripcion("acme")
    assert sus["estado"] == "activa" and sus["precio_usd"] == 1000 and sus["usuario"] == "user_acme"
    with c.session_transaction() as s:
        assert any("tu plan está activo" in m for _cat, m in s.get("_flashes", []))


@pytest.mark.parametrize("campo,valor", [
    ("payment_source_token", "tok_test_9_Xyz"),
    ("wompi", '{"id": "tok_test_9_Xyz", "brand": "VISA", "last_four": "4242"}'),
    ("respuesta", '{"data": {"id": "tok_test_9_Xyz"}}'),
])
def test_el_token_del_widget_se_encuentra_aunque_venga_con_otro_nombre(base, pagina, pro, falso, avisos, campo, valor):
    _cobra()
    pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro, token="", **{campo: valor}))
    assert [f[1] for f in falso.fuentes] == ["tok_test_9_Xyz"]


def test_alta_sin_token_o_con_precio_viejo_no_habla_con_wompi(base, pagina, pro, falso, avisos):
    _cobra()
    pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro, token="4242424242424242"))
    pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro, precio_visto_usd="900"))
    pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro, precio_visto_usd="1000.0"))
    assert falso.fuentes == [] and falso.posts == []


def test_un_rechazo_vuelve_al_formulario_con_el_motivo(base, pagina, pro, falso, avisos):
    _cobra()
    falso.defecto = "DECLINED"
    c = pagina()
    r = c.post("/cliente/acme/plan/alta", data=_form_alta(pro))
    assert "/plan/alta" in r.headers["Location"]
    with c.session_transaction() as s:
        assert any("Wompi no aprobó el pago" in m for _cat, m in s.get("_flashes", []))


def test_nequi_solo_con_un_token_que_pidio_esta_sesion(base, pagina, pro, falso, avisos):
    from cobros import planes
    _cobra()
    c = pagina()
    assert c.post("/cliente/acme/plan/nequi", data={"celular": "12345"}).status_code == 400
    d = c.post("/cliente/acme/plan/nequi", data={"celular": "300 123 4567"}).get_json()
    assert d["ok"] and d["token"] == "nequi_test_1"
    assert c.get(d["estado_url"]).get_json() == {"estado": "PENDING"}
    assert pagina().get(d["estado_url"]).status_code == 404               # otra sesión no lo sondea
    pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro, tipo="NEQUI", token="nequi_test_1"))
    assert falso.fuentes == []                                            # token de otra sesión: no
    falso.nequi["nequi_test_1"] = "APPROVED"
    from cobros import rutas
    rutas._ULTIMA_VERIFICACION.clear()
    assert c.get(d["estado_url"]).get_json() == {"estado": "APPROVED"}
    c.post("/cliente/acme/plan/alta", data=_form_alta(pro, tipo="NEQUI", token="nequi_test_1"))
    assert [f[:2] for f in falso.fuentes] == [("NEQUI", "nequi_test_1")]
    assert planes.suscripcion("acme")["medio_fuente"] == "NEQUI"


# --- cancelar, cambiar tarjeta y otro proyecto ---------------------------------------------

def test_cancelar_pide_confirmacion_y_sigue_hasta_el_fin(base, pagina, pro, falso, avisos):
    from cobros import planes
    _suscrito(pro)
    pagina().post("/cliente/acme/plan/cancelar", data={})
    assert planes.suscripcion("acme")["estado"] == "activa"
    pagina().post("/cliente/acme/plan/cancelar", data={"confirmo": "1"})
    sus = planes.suscripcion("acme")
    assert sus["estado"] == "cancelada" and sus["renovar"] is False
    texto = _texto(_panel(pagina))
    assert "Cancelaste el plan: sigue hasta el" in texto and "Cancelar plan" not in texto
    assert "US$ 1.000,00 restantes" in texto                     # lo pagado sigue


def test_otro_proyecto_no_ve_ni_cancela_ni_cambia_la_tarjeta(base, pagina, pro, falso, avisos):
    from cobros import planes
    _suscrito(pro)
    _cobra("otro")
    otro = pagina("otro", "cliente", "otro")
    assert otro.get("/cliente/acme/plan/panel").status_code == 302
    assert otro.post("/cliente/acme/plan/cancelar", data={"confirmo": "1"}).status_code == 302
    assert otro.post("/cliente/acme/plan/tarjeta", data=_form_alta(pro)).status_code == 302
    assert planes.suscripcion("acme")["estado"] == "activa" and len(falso.fuentes) == 1
    assert "Plan Pro" not in _texto(otro.get("/cliente/otro/plan/panel").get_data(as_text=True))


def test_cambiar_tarjeta_guarda_la_nueva_fuente(base, pagina, pro, falso, avisos):
    from cobros import planes
    _suscrito(pro)
    html = pagina().get("/cliente/acme/plan/tarjeta").get_data(as_text=True)
    assert 'data-widget-operation="tokenize"' in html and "precio_visto_usd" not in html
    assert "Autorizo el cobro automático de US$ 1.000 cada mes" in _texto(html)
    r = pagina().post("/cliente/acme/plan/tarjeta", data=_form_alta(pro, token="tok_test_88_Nueva"))
    assert r.headers["Location"].endswith("#config-ap-plan")
    assert [f[1] for f in falso.fuentes] == ["tok_test_1_prueba", "tok_test_88_Nueva"]
    assert planes.suscripcion("acme")["fuente_pago_id"] == "3892"
    pagina().post("/cliente/acme/plan/tarjeta", data=_form_alta(pro, token="tok_test_89_Otra", acepta_datos=None))
    assert len(falso.fuentes) == 2


# --- chip y saldo partido ------------------------------------------------------------------

def test_el_chip_suma_lo_que_queda_del_plan(base, pagina, pro, falso, avisos):
    import gastos
    _suscrito(pro)
    gastos.registrar("acme", "video", 100.0, "video:cf1:t1")
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    assert "Saldo: US$ 0,00 · Plan: US$ 875,00 restantes · Recargar" in html


def test_el_chip_sin_plan_queda_como_antes(base, pagina, pro, falso):
    from cobros import libro
    import db
    _cobra()
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 3_000, "ajuste", usuario="admin", detalle="prueba")
    assert "Saldo: US$ 3,00 · Recargar" in pagina().get("/cliente/acme").get_data(as_text=True)


def test_el_saldo_muestra_aparte_el_propio_y_el_del_plan(base, pagina, pro, falso, avisos):
    import db
    from cobros import libro
    _suscrito(pro)
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 50_000, "ajuste", usuario="admin", detalle="prueba")
    texto = _texto(pagina().get("/cliente/acme/saldo/panel").get_data(as_text=True))
    assert "Saldo propio US$ 50,00" in texto and "Saldo del plan US$ 1.000,00" in texto
    assert "Lo que no uses vence el" in texto and "Saldo del plan del mes" in texto   # el movimiento, con nombre


# --- revisión 1 (2026-10-10) ---------------------------------------------------------------

def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


def test_morosa_el_cambio_de_tarjeta_dice_que_cobra_ahora(base, pagina, pro, falso, avisos):
    import db
    _suscrito(pro)
    normal = _texto(pagina().get("/cliente/acme/plan/tarjeta").get_data(as_text=True))
    assert "cobramos ahora" not in normal and "El nuevo medio se usa desde el próximo cobro" in normal
    with db.conectar() as con:
        con.execute(db.suscripcion.update().values(estado="morosa", intentos_fallidos=1,
                                                   proximo_cobro="2099-01-01T10:00:00"))
    texto = _texto(pagina().get("/cliente/acme/plan/tarjeta").get_data(as_text=True))
    assert "Actualizar tarjeta y pagar el plan" in texto
    assert ("Al guardar, cobramos ahora US$ 1.000 (en pesos a la TRM del día) para recuperar tu plan." in texto)
    assert "El nuevo medio se usa desde el próximo cobro" not in texto
    # el rechazo de ese cobro vuelve con lo que dijo Wompi
    falso.defecto = "DECLINED"
    c = pagina()
    c.post("/cliente/acme/plan/tarjeta", data=_form_alta(pro, token="tok_test_90_Mor"))
    assert any("Wompi no aprobó el pago" in m for m in _flashes(c))


def test_morosa_el_rechazo_trae_el_motivo(base, pagina, pro, falso, avisos, monkeypatch):
    import db
    from cobros import planes
    _suscrito(pro)
    with db.conectar() as con:
        con.execute(db.suscripcion.update().values(estado="morosa", intentos_fallidos=1,
                                                   proximo_cobro="2099-01-01T10:00:00"))
    real = falso.cobrar_fuente

    def rechaza(*a, **k):
        tx = real(*a, **k)
        tx["status"], tx["status_message"] = "DECLINED", "Fondos insuficientes"
        falso.txs[tx["id"]] = dict(tx)
        return tx
    from cobros import wompi
    monkeypatch.setattr(wompi, "cobrar_fuente", rechaza)
    c = pagina()
    c.post("/cliente/acme/plan/tarjeta", data=_form_alta(pro, token="tok_test_91_Mor"))
    assert any("Fondos insuficientes" in m for m in _flashes(c)), _flashes(c)
    assert planes.suscripcion("acme")["estado"] == "morosa"


def test_sin_cobrar_no_se_suscribe_ni_el_admin(base, pagina, pro, falso, avisos):
    from cobros import planes
    admin = pagina("admin", "admin", None)
    panel = admin.get("/cliente/acme/plan/panel").get_data(as_text=True)
    assert "Suscribirme" not in panel and "Este proyecto todavía no cobra" in panel
    r = admin.get(f"/cliente/acme/plan/alta?plan={pro}")
    assert r.status_code == 302 and r.headers["Location"].endswith("#config-ap-plan")
    admin.post("/cliente/acme/plan/alta", data=_form_alta(pro))
    assert falso.fuentes == [] and planes.suscripcion("acme") is None
    assert any("Este proyecto todavía no cobra" in m for m in _flashes(admin))


def test_si_wompi_no_responde_lo_dice_distinto_de_confirmando(base, pagina, pro, falso, avisos):
    from cobros import wompi
    _cobra()
    falso.error = (wompi.ErrorWompi("caída", caida=True), False)
    c = pagina()
    c.post("/cliente/acme/plan/alta", data=_form_alta(pro))
    assert any("Wompi no respondió; lo intentamos de nuevo en unos minutos." in m for m in _flashes(c))
    assert not any("Wompi está confirmando" in m for m in _flashes(c))


def test_el_saldo_propio_nunca_se_pinta_negativo(base, pagina, pro, falso, avisos):
    import db
    from cobros import libro
    _suscrito(pro)
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", -300_000, "ajuste", usuario="admin", detalle="corrección")
    html = pagina().get("/cliente/acme").get_data(as_text=True)
    assert "Saldo: US$ 0,00 · Plan: US$ 1.000,00 restantes" in html
    texto = _texto(pagina().get("/cliente/acme/saldo/panel").get_data(as_text=True))
    assert "Saldo propio US$ 0,00" in texto and "-US$" not in texto


def test_la_bolsa_reusa_el_periodo_memorizado(base, pro, falso, avisos, monkeypatch):
    import dashboard
    from cobros import planes, vista
    _suscrito(pro)
    leidas = []
    real = planes._leer_periodo_nuevo
    monkeypatch.setattr(planes, "_leer_periodo_nuevo", lambda c: leidas.append(c) or real(c))
    with dashboard.app.test_request_context("/cliente/acme"):
        planes.periodo_abierto("acme")
        assert vista.bolsa("acme")["restante"] == 1_000_000
    assert leidas == ["acme"]


def test_las_casillas_son_una_frase_con_el_enlace_adentro(base, pagina, pro, falso):
    import dashboard
    import idiomas
    from flask_babel import gettext
    _cobra()
    html = pagina().get(f"/cliente/acme/plan/alta?plan={pro}").get_data(as_text=True)
    assert ('Autorizo a Wompi el <a href="https://wompi.com/datos.pdf" target="_blank" rel="noopener noreferrer">'
            'tratamiento de mis datos personales</a>.') in html
    assert 'Acepto los <a href="https://wompi.co/terminos.pdf"' in html and "&lt;a" not in html
    with dashboard.app.test_request_context("/"), idiomas.en_idioma("en"):
        assert gettext("Autorizo a Wompi el %(enlace)s.", enlace="X") == "I authorize Wompi's X."
        assert gettext("tratamiento de mis datos personales") == "processing of my personal data"


def test_el_formulario_solo_recibe_id_nombre_y_precios_del_plan(base, pagina, pro, falso):
    import dashboard
    from flask import template_rendered
    _cobra()
    vistos = []

    def anotar(sender, template, context, **extra):
        if template.name == "plan_alta.html":
            vistos.append(context["plan"])
    template_rendered.connect(anotar, dashboard.app)
    try:
        pagina().get(f"/cliente/acme/plan/alta?plan={pro}")
    finally:
        template_rendered.disconnect(anotar, dashboard.app)
    assert vistos and set(vistos[0]) == {"id", "nombre", "precio_usd", "precio_anual_usd"}


def test_los_contratos_de_wompi_se_reusan_10_minutos(base, monkeypatch):
    from cobros import wompi
    pedidos = []
    datos = {"acceptance_token": "eyJ.a", "acceptance_url": "https://wompi.co/t.pdf",
             "personal_token": "eyJ.b", "personal_url": "https://wompi.com/d.pdf"}

    def pedir(tiempo=None):
        pedidos.append(1)
        if len(pedidos) > 1:
            raise wompi.ErrorWompi("caída", caida=True)
        return dict(datos)
    monkeypatch.setattr(wompi, "aceptaciones", pedir)
    assert wompi.aceptaciones_recientes(ahora=1000) == datos
    assert wompi.aceptaciones_recientes(ahora=1000 + 599) == datos and len(pedidos) == 1     # fresco: sin pedir
    assert wompi.aceptaciones_recientes(ahora=1000 + 1200) == datos and len(pedidos) == 2    # Wompi falla: lo guardado
    with pytest.raises(wompi.ErrorWompi):
        wompi.aceptaciones_recientes(ahora=1000 + 46 * 60)                                  # ya no sirve


def test_con_tope_cero_no_se_promete_ia_incluida(base, pagina, falso, avisos):
    from cobros import planes
    sin_ia = planes.crear_plan("Básico", 300, 1.5, 0, usuario="admin")
    _cobra()
    texto = _texto(_panel(pagina))
    assert "Básico" in texto and "con IA incluidos" not in texto
    import db
    planes.suscribir("acme", sin_ia, "mensual", "CARD", "tok_test_1_prueba", "pagos@acme.co", dict(ACEPTACION),
                     "user_acme", 300, ahora=db.ahora())
    texto = _texto(_panel(pagina))
    assert "Plan Básico" in texto and "IA incluida" not in texto


# --- revisión final 2026-10-10: seguridad --------------------------------------------------

def test_un_json_anidado_sin_fin_en_el_formulario_no_es_500(base, pagina, pro, falso, avisos):
    from cobros import rutas
    hondo = '{"a":' + "[" * 4990
    assert rutas._token_en(hondo) is None
    _cobra()
    r = pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro, token="", otro=hondo))
    assert r.status_code == 302 and falso.fuentes == []


def test_la_constancia_guarda_ip_y_navegador_y_nunca_recorta_el_alta(base, pagina, pro, falso, avisos):
    import json
    import db
    from cobros import planes
    _cobra()
    pagina().post("/cliente/acme/plan/alta", data=_form_alta(pro),
                  headers={"User-Agent": "Navegador/1.0 " + "x" * 400}, environ_base={"REMOTE_ADDR": "203.0.113.7"})
    sid = planes.suscripcion("acme")["id"]
    for i in range(12):
        planes.cambiar_fuente("acme", "CARD", f"tok_test_{i}_cambio", "pagos@acme.co", dict(ACEPTACION), "user_acme")

    def constancia():
        with db.conectar() as con:
            return json.loads(con.execute(sa.select(db.kv.c.valor)
                                          .where(db.kv.c.clave == f"planes:aceptacion:{sid}")).scalar())
    lista = constancia()
    assert len(lista) == 10
    assert lista[0]["ip"] == "203.0.113.7" and lista[0]["user_agent"].startswith("Navegador/1.0")
    assert len(lista[0]["user_agent"]) == 300 and lista[0]["acceptance_token"] == "eyJ.acepta.widget"
    assert lista[-1]["aceptada_en"] >= lista[0]["aceptada_en"]


def test_el_pago_de_un_proyecto_no_se_consulta_desde_otro(base, pagina, pro, falso, avisos, monkeypatch):
    """Aislamiento: «otro» no ve ni hace consultar el pago de plan de «acme» (vista.estado_pago_plan y
    planes.verificar_pago comparan el proyecto)."""
    import db
    from cobros import planes
    falso.defecto = "PENDING"
    _cobra("acme")
    _cobra("otro")
    planes.suscribir("acme", pro, "mensual", "CARD", "tok_test_1_prueba", "pagos@acme.co", dict(ACEPTACION),
                     "user_acme", 1000, ahora=db.ahora())
    (pago,) = planes.estado_cliente("acme")["pagos"]
    consultas = []
    from cobros import wompi
    monkeypatch.setattr(wompi, "transaccion",
                        lambda tx_id, tiempo=None: consultas.append(tx_id) or falso.transaccion(tx_id))
    r = pagina("otro", "cliente", "otro").get(f"/cliente/otro/plan/pago/{pago['id']}/estado")
    assert r.status_code == 404
    assert planes.verificar_pago("otro", pago["id"]) is None
    assert consultas == []
    assert pagina().get(f"/cliente/acme/plan/pago/{pago['id']}/estado").get_json()["estado"] == "pendiente"

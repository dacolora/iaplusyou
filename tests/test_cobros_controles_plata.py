"""Los controles de plata del admin (auditoría de seguridad de pagos 2026-10-12, decisiones 2026-10-15).

PND-347: sin segundo factor, una sesión de admin robada creaba saldo a mano. Ahora la recarga manual y el ajuste piden
la clave otra vez (vale 10 minutos), cada uno avisa a TODOS los admins y lo que se suma a mano en un día tiene un tope
que se cambia en /admin/cobros (también con la clave). PND-348: la banda de la TRM se mide contra una tasa de
referencia que fija una persona, no contra la última lectura buena (que se corría de a 8 % por vez)."""
import datetime as dt

import pytest
import sqlalchemy as sa

from tests.conftest import PASSWORD_PRUEBA
from tests.test_trm import T0, _Respuesta, _fila, trm  # noqa: F401 — fixture de la TRM sin red

MISMO = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import estado
    import notificaciones
    import proyectos
    from cobros import avisos, recargas
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(estado, "listar_clientes", lambda: ["acme", "otro"])
    monkeypatch.delenv("BOLD_LLAVE_IDENTIDAD", raising=False)
    for nombre in ("recarga_acreditada", "recarga_admin", "limpiar_aviso_bajo"):
        monkeypatch.setattr(avisos, nombre, lambda *a, **k: None)
    monkeypatch.setattr(recargas, "_en_segundo_plano", lambda fn: fn())
    admins = []

    def avisar_admin(tipo, asunto, cuerpo, cliente=""):
        admins.append((tipo, cliente, asunto() if callable(asunto) else asunto,
                       cuerpo() if callable(cuerpo) else cuerpo))
        return 2
    monkeypatch.setattr(notificaciones, "avisar_admin", avisar_admin)
    base_temporal.admins = admins
    return base_temporal


@pytest.fixture()
def http(entorno):
    import dashboard
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s.update(usuario="admin", rol="admin", cliente=None, sv=1)
    return c


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.pop("_flashes", [])]


def _recargar(c, monto, clave=None, tipo="recarga", nota="transferencia", cliente="acme"):
    datos = {"monto": monto, "nota": nota, "tipo": tipo}
    if clave is not None:
        datos["clave"] = clave
    return c.post(f"/admin/cobros/{cliente}/recarga", data=datos, headers=MISMO)


def _saldo(cliente="acme"):
    from cobros import libro
    return libro.saldo(cliente)


def _intentos_login(db, usuario="admin"):
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == f"limite:login:u:{usuario}")).scalar()
    import json
    return len(json.loads(crudo)) if crudo else 0


# ------------------------------------------------------------------- PND-347: la clave otra vez ---

def test_la_recarga_manual_pide_la_clave_otra_vez(http, entorno):
    r = _recargar(http, "25")
    assert r.status_code == 302 and _saldo() == 0
    assert any("escribe tu clave otra vez" in m for m in _flashes(http))
    assert _intentos_login(entorno) == 0                              # vacía: no cuenta como intento
    _recargar(http, "25", clave="otra-cosa")
    assert _saldo() == 0 and any("Esa no es tu clave" in m for m in _flashes(http))
    assert _intentos_login(entorno) == 1                              # cuenta contra el tope del login
    _recargar(http, "25", clave=PASSWORD_PRUEBA)
    assert _saldo() == 25_000
    _recargar(http, "5", tipo="ajuste", nota="corrección")             # dentro de los 10 minutos: no la vuelve a pedir
    assert _saldo() == 30_000


def test_la_clave_vale_diez_minutos(http, entorno, monkeypatch):
    import cuentas
    _recargar(http, "10", clave=PASSWORD_PRUEBA)
    assert _saldo() == 10_000
    real = cuentas.time.time
    monkeypatch.setattr(cuentas.time, "time", lambda: real() + cuentas.REAUTH_S + 5)
    _recargar(http, "10")
    assert _saldo() == 10_000 and any("escribe tu clave otra vez" in m for m in _flashes(http))


def test_el_ajuste_tambien_pide_la_clave(http, entorno):
    _recargar(http, "-5", tipo="ajuste", nota="devolución")
    assert _saldo() == 0
    _recargar(http, "-5", tipo="ajuste", nota="devolución", clave=PASSWORD_PRUEBA)
    assert _saldo() == -5_000


def test_con_demasiados_fallidos_ni_siquiera_mira_la_clave(http, entorno, monkeypatch):
    import cuentas
    import usuarios
    for _ in range(cuentas.LOGIN_MAX_POR_USUARIO):
        _recargar(http, "1", clave="mala")
    _flashes(http)
    llamadas = []
    original = usuarios.verificar
    monkeypatch.setattr(usuarios, "verificar", lambda u, p: llamadas.append(u) or original(u, p))
    _recargar(http, "1", clave=PASSWORD_PRUEBA)
    assert llamadas == [] and _saldo() == 0
    assert any("Demasiados intentos fallidos" in m for m in _flashes(http))


# --------------------------------------------------------- PND-347: el aviso a todos los admins ---

def test_cada_recarga_y_ajuste_avisa_a_todos_los_admins_con_quien_lo_hizo(http, entorno):
    _recargar(http, "25", clave=PASSWORD_PRUEBA, nota="transferencia de abril")
    _recargar(http, "-3", tipo="ajuste", nota="corrección")
    avisos = [a for a in entorno.admins if a[0] == "saldo_manual"]
    assert len(avisos) == 2 and all(a[1] == "acme" for a in avisos)
    assert "admin" in avisos[0][3] and "recarga manual" in avisos[0][3] and "transferencia de abril" in avisos[0][3]
    assert "ajuste" in avisos[1][3] and "corrección" in avisos[1][3]
    assert "En las últimas 24 horas van US$ 25,00" in avisos[1][3] and "US$ 2.000,00" in avisos[1][3]
    # Sin la clave no se anota nada y no hay aviso de saldo movido.
    _recargar(http, "-3", tipo="ajuste", nota="x", cliente="otro")
    with http.session_transaction() as s:
        s.pop("clave_confirmada_en")
    _recargar(http, "7", cliente="otro")
    assert len([a for a in entorno.admins if a[0] == "saldo_manual"]) == 3


def test_los_avisos_salen_en_avisos_de_plata(entorno):
    from cobros import vista
    assert "saldo_manual" in vista.NOMBRES_AVISO_PLATA and "control_plata" in vista.NOMBRES_AVISO_PLATA
    import notificaciones
    assert "saldo_manual" in notificaciones.TIPOS and "control_plata" in notificaciones.TIPOS


# ------------------------------------------------------------------ PND-347: el tope diario ---

def test_lo_sumado_a_mano_en_un_dia_tiene_tope(entorno):
    from cobros import libro, recargas
    assert recargas.tope_manual() == (0, recargas.TOPE_MANUAL_DIA_DEFECTO * 1000)
    recargas.manual("acme", 1500, "admin", "transferencia")
    with pytest.raises(ValueError, match="el tope"):
        recargas.manual("otro", 600, "admin", "transferencia")         # todos los proyectos juntos
    with pytest.raises(ValueError, match="el tope"):
        recargas.manual("acme", 600, "admin", "regalo", tipo="ajuste")   # un ajuste positivo también suma
    assert libro.saldo("otro") == 0 and libro.saldo("acme") == 1_500_000
    recargas.manual("acme", -600, "admin", "devolución", tipo="ajuste")  # restar no tiene tope
    recargas.manual("acme", 500, "admin", "justo")                       # 1 500 + 500 = el tope exacto
    assert recargas.tope_manual()[0] == 2_000_000
    with db_conectar() as con:                                           # la bienvenida no es «a mano»
        libro.acreditar(con, "otro", "ajuste", 2000, "bienvenida", usuario="sistema")
    assert recargas.tope_manual()[0] == 2_000_000
    with pytest.raises(ValueError):
        recargas.manual("acme", "0.01", "admin", "uno más")


def test_el_tope_toma_el_candado_antes_de_leer(entorno, escritor_en_medio):
    """Dos clics a la vez no pasan juntos el tope: entre leer lo de hoy y escribir, nadie más escribe."""
    from cobros import recargas
    otro = escritor_en_medio("INSERT INTO recarga", "INSERT INTO kv (clave, valor, actualizado_en) "
                                                    "VALUES ('prueba:en_medio', '1', '2026-10-15T00:00:00')")
    recargas.manual("acme", 10, "admin", "transferencia")
    assert otro["hecho"] and otro["resultado"].startswith("bloqueado"), otro


def db_conectar():
    import db
    return db.conectar()


def test_cuentan_las_ultimas_24_horas_corridas(entorno):
    """Revisión de seguridad: con un tope por día de calendario, a las 23:59 y a las 00:01 pasaban dos topes."""
    from cobros import recargas
    recargas.manual("acme", 2000, "admin", "transferencia")
    hace_23h = (dt.datetime.now() - dt.timedelta(hours=23)).isoformat(timespec="seconds")
    with entorno.conectar() as con:
        con.execute(entorno.movimiento_saldo.update().values(creado_en=hace_23h))
    assert recargas.tope_manual()[0] == 2_000_000                      # ayer a esta hora +1: sigue contando
    with pytest.raises(ValueError, match="24 horas"):
        recargas.manual("acme", 1, "admin", "uno más")
    hace_25h = (dt.datetime.now() - dt.timedelta(hours=25)).isoformat(timespec="seconds")
    with entorno.conectar() as con:
        con.execute(entorno.movimiento_saldo.update().values(creado_en=hace_25h))
    assert recargas.tope_manual()[0] == 0
    recargas.manual("acme", 2000, "admin", "otra transferencia")


def test_el_tope_se_cambia_con_la_clave_y_avisa(http, entorno):
    from cobros import recargas
    r = http.post("/admin/cobros/tope-manual", data={"tope": "5000"}, headers=MISMO)
    assert r.status_code == 302 and recargas.tope_manual()[1] == 2_000_000          # sin clave: igual
    http.post("/admin/cobros/tope-manual", data={"tope": "5000,50", "clave": PASSWORD_PRUEBA}, headers=MISMO)
    assert recargas.tope_manual()[1] == 5_000_500
    (aviso,) = [a for a in entorno.admins if a[0] == "control_plata"]
    assert "admin" in aviso[3] and "US$ 5.000,50" in aviso[3]
    for malo in ("-1", "100000.01", "abc", "1.5e3x", "10.001"):
        http.post("/admin/cobros/tope-manual", data={"tope": malo}, headers=MISMO)
        assert recargas.tope_manual()[1] == 5_000_500, malo
    http.post("/admin/cobros/tope-manual", data={"tope": "0"}, headers=MISMO)      # 0: nada a mano
    assert recargas.tope_manual()[1] == 0
    _recargar(http, "1")
    assert _saldo() == 0 and any("el tope es US$ 0,00" in m for m in _flashes(http))


def test_quien_no_es_admin_no_cambia_ningun_control(entorno):
    import dashboard
    from cobros import recargas, trm
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s.update(usuario="user_acme", rol="cliente", cliente="acme", sv=1)
    for ruta, datos in (("/admin/cobros/tope-manual", {"tope": "99999", "clave": PASSWORD_PRUEBA}),
                        ("/admin/cobros/trm/ancla", {"ancla": "4000", "clave": PASSWORD_PRUEBA}),
                        ("/admin/cobros/acme/recarga", {"monto": "10", "tipo": "recarga", "clave": PASSWORD_PRUEBA})):
        r = c.post(ruta, data=datos, headers=MISMO)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert recargas.tope_manual()[1] == 2_000_000 and trm.ancla() is None and _saldo() == 0


def test_la_pagina_muestra_los_controles_y_no_pide_la_clave_si_esta_vigente(http, entorno):
    html = http.get("/admin/cobros").get_data(as_text=True)
    assert 'id="cobros-tope-manual"' in html and 'id="cobros-trm-ancla"' in html
    assert "En las últimas 24 horas van US$ 0,00 de US$ 2.000,00" in html
    assert html.count('name="clave"') >= 3                                         # tope, ancla y la recarga
    _recargar(http, "1", clave=PASSWORD_PRUEBA)
    html = http.get("/admin/cobros").get_data(as_text=True)
    assert 'name="clave"' not in html and "En las últimas 24 horas van US$ 1,00 de US$ 2.000,00" in html


# ---------------------------------------------------------------------- PND-348: el ancla de la TRM ---

def test_la_banda_ya_no_se_corre_con_cada_lectura(trm):  # noqa: F811
    """Antes: 3 218 → 3 470 (+7,8 %) → 3 740 (+7,8 % de la anterior, +16 % del inicio) pasaba de a poco."""
    assert trm.actual() == 3218.75
    assert trm.ancla()["valor"] == 3218.75 and trm.ancla()["usuario"] == "sistema"   # la primera aceptada
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3470.00"))                          # +7,8 % del ancla: sirve
    assert trm.actual() == 3470.0
    assert trm.ancla()["valor"] == 3218.75                                          # el ancla no se movió
    trm.reloj["t"] = T0 + 14 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3740.00"))                          # +16 % del ancla: no
    with pytest.raises(trm.SinTasa):
        trm.actual()
    assert trm.rechazada()["anterior"] == 3218.75


def test_sin_ancla_la_guardada_queda_como_referencia(trm, base_temporal):  # noqa: F811
    assert trm.actual() == 3218.75
    with base_temporal.conectar() as con:                                           # como antes del despliegue
        con.execute(base_temporal.kv.delete().where(base_temporal.kv.c.clave == trm.CLAVE_ANCLA))
    assert trm.ancla() is None
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3300.00"))
    assert trm.actual() == 3300.0
    assert trm.ancla()["valor"] == 3218.75                                          # la aceptada de antes


def test_el_admin_fija_la_referencia_y_la_rechazada_se_vuelve_a_mirar(trm):  # noqa: F811
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3900.00"))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    for malo in ("2400", "7000.01", "abc", "", "nan", "inf"):
        with pytest.raises(ValueError):
            trm.fijar_ancla(malo, "admin")
    assert trm.fijar_ancla("3850,5", "admin") == 3850.5
    assert trm.ancla()["usuario"] == "admin" and trm.rechazada() is None
    assert trm.actual() == 3900.0                                                   # +1,3 % de la nueva


def test_aceptar_la_rechazada_la_vuelve_la_referencia(trm):  # noqa: F811
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3600.00"))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    trm.aceptar("3600.0", "admin")
    assert trm.ancla()["valor"] == 3600.0 and trm.ancla()["usuario"] == "admin"


def test_las_rutas_de_la_trm_piden_la_clave_y_avisan(http, entorno, trm):  # noqa: F811
    assert trm.actual() == 3218.75
    http.post("/admin/cobros/trm/ancla", data={"ancla": "3300"}, headers=MISMO)
    assert trm.ancla()["valor"] == 3218.75                                          # sin clave: igual
    http.post("/admin/cobros/trm/ancla", data={"ancla": "3300", "clave": PASSWORD_PRUEBA}, headers=MISMO)
    assert trm.ancla()["valor"] == 3300.0
    assert any(a[0] == "control_plata" and "3.300,00" in a[1] for a in trm.admin)   # el fixture de la TRM los junta
    html = http.get("/admin/cobros").get_data(as_text=True)
    assert "3.300,00 COP por dólar, fijada por admin" in html
    # «Aceptar la tasa de hoy» también la pide.
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3800.00"))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    with http.session_transaction() as s:
        s.pop("clave_confirmada_en")
    http.post("/admin/cobros/trm/aceptar", data={"valor": "3800.0"}, headers=MISMO)
    assert trm.rechazada() is not None and trm.ancla()["valor"] == 3300.0
    http.post("/admin/cobros/trm/aceptar", data={"valor": "3800.0", "clave": PASSWORD_PRUEBA}, headers=MISMO)
    assert trm.rechazada() is None and trm.ancla()["valor"] == 3800.0


# ------------------------------------------------- revisión de seguridad y de plata (2026-10-15) ---

def test_activar_un_plan_a_mano_pide_la_clave_y_avisa(http, entorno):
    """Activar a mano acredita la bolsa del plan sin cobro de Wompi: como una recarga manual."""
    from cobros import libro, planes
    libro.configurar("acme", usuario="admin", cobrar=True)
    pid = planes.crear_plan("Pro", 1000, 1.25, 25, usuario="admin")
    ruta = "/admin/cobros/acme/plan/activar"
    http.post(ruta, data={"plan_id": pid, "ciclo": "mensual", "nota": "transferencia"}, headers=MISMO)
    assert planes.suscripcion("acme") is None and _saldo() == 0
    assert any("escribe tu clave otra vez" in m for m in _flashes(http))
    http.post(ruta, data={"plan_id": pid, "ciclo": "mensual", "nota": "transferencia", "clave": PASSWORD_PRUEBA},
              headers=MISMO)
    assert planes.suscripcion("acme") is not None and _saldo() == 1_000_000
    (aviso,) = [a for a in entorno.admins if a[0] == "saldo_manual"]
    assert aviso[1] == "acme" and "activó a mano un plan de US$ 1.000" in aviso[3] and "transferencia" in aviso[3]


def test_cambiar_la_clave_o_el_correo_cuenta_contra_el_tope_del_login(http, entorno, monkeypatch):
    """Sin tope, una sesión robada adivinaba la clave en Configuración › Cuenta y con ella pasaba la confirmación."""
    import cuentas
    import usuarios
    for _ in range(cuentas.LOGIN_MAX_POR_USUARIO):
        http.post("/cuenta/password", data={"password_actual": "mala", "password": "otra-clave-9", "confirmacion":
                                            "otra-clave-9"}, headers=MISMO)
    assert _intentos_login(entorno) == cuentas.LOGIN_MAX_POR_USUARIO
    _flashes(http)
    llamadas = []
    original = usuarios.verificar
    monkeypatch.setattr(usuarios, "verificar", lambda u, p: llamadas.append(u) or original(u, p))
    http.post("/cuenta/correo", data={"password": PASSWORD_PRUEBA, "correo": "nuevo@prueba.local"}, headers=MISMO)
    assert llamadas == [] and any("Demasiados intentos fallidos" in m for m in _flashes(http))
    assert usuarios.obtener("admin")["correo"] == "admin@prueba.local"


def test_fijar_el_ancla_invalida_la_tasa_guardada_fuera_de_la_banda(trm):  # noqa: F811
    """Guardian-gasto: el admin fija 4 200 y la guardada es 3 218,75 (−23 %): ya no sirve ni de caché ni de respaldo."""
    import requests as requests_real
    assert trm.actual() == 3218.75
    trm.fijar_ancla("4200", "admin")
    trm.respuesta["r"] = requests_real.ConnectionError("caído")
    with pytest.raises(trm.SinTasa):                      # dentro de las 6 h de caché: no devuelve la vieja
        trm.actual()
    trm.respuesta["r"] = _Respuesta(200, _fila("4180.00"))
    assert trm.actual() == 4180.0


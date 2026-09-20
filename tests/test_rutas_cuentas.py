"""Task 2 de cuentas con correo verificado: las rutas y pantallas. Registro
con correo (y verificación enviada), /verificar/<token>, reenviar con
límite, /recuperar (misma respuesta exista o no el correo), /restablecer
(flujo completo y sesión vieja cerrada), Configuración › Cuenta (cambiar
correo/contraseña), guard de Meta/tienda sin verificar, panel admin y el
banner. Sin red: `notificaciones.enviar` y `cuentas.enviar_*` son fakes y
`cuentas.smtp_configurado` se monkeypatchea."""
import re

import pytest

from tests.conftest import sembrar_usuarios
from tests.test_rutas_productos import _cliente_admin


@pytest.fixture()
def app(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import cuentas
    import estado as estado_mod
    import proyectos
    import usuarios
    import dashboard
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    monkeypatch.delenv("PLATAFORMA_URL", raising=False)
    monkeypatch.delenv("META_REDIRECT_URI", raising=False)
    # usuarios.json propio (solo el admin sembrado): los tests de acá crean sus
    # usuarios y comprueban que el registro no deje nada.
    monkeypatch.setattr(usuarios, "_path", lambda: str(tmp_path / "usuarios.json"))
    sembrar_usuarios(tmp_path / "usuarios.json", nombres=("admin",))
    monkeypatch.setattr(dashboard, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(estado_mod, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    # SMTP "configurado" por defecto; el correo real nunca sale: se captura.
    monkeypatch.setattr(cuentas, "smtp_configurado", lambda: True)
    correos = []
    monkeypatch.setattr(cuentas.notificaciones, "enviar",
                        lambda destinatario, asunto, cuerpo, html=None: correos.append(
                            {"a": destinatario, "asunto": asunto, "cuerpo": cuerpo, "html": html}) or True)
    dashboard.app.config["TESTING"] = True
    return {"dashboard": dashboard, "usuarios": usuarios, "cuentas": cuentas, "correos": correos, "tmp": tmp_path}


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


def _sesion(c):
    with c.session_transaction() as s:
        return dict(s)


def _cliente_con_sesion(app, usuario):
    """Test client con la sesión abierta como ese usuario (leído de usuarios.json)."""
    entry = app["usuarios"].obtener(usuario)
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = entry["rol"]
        s["cliente"] = entry.get("cliente")
        s["sv"] = entry["session_version"]
    return c


def _ana(app, correo="ana@ejemplo.com", verificado=False):
    app["usuarios"].crear("ana", "secreta123", "cliente", cliente="acme", correo=correo)
    if verificado:
        app["usuarios"].actualizar("ana", correo_verificado=True)
    return _cliente_con_sesion(app, "ana")


def _enlace(correo, ruta):
    """Ruta (sin esquema ni host) del enlace del correo: el test client guarda
    la cookie para "localhost" y el enlace lleva la base pública fija."""
    m = re.search(rf"https?://[^/\s]+(/{ruta}/\S+)", correo["cuerpo"])
    assert m, correo["cuerpo"]
    return m.group(1)


def _token(enlace):
    return enlace.rstrip("/").rsplit("/", 1)[1]


REGISTRO = {"nombre": "Acme Store", "usuario": "acme", "correo": "Dueno@Acme.com", "password": "secreta123"}


# --- registro ---------------------------------------------------------------

def test_registro_sin_correo_da_error_y_no_crea_nada(app):
    c = app["dashboard"].app.test_client()
    r = c.post("/proyectos/nuevo", data={**REGISTRO, "correo": ""})
    assert r.status_code == 400
    html = r.get_data(as_text=True)
    assert "Escribe un correo válido" in html
    # Lo escrito se conserva (menos la contraseña) para no llenar todo otra vez.
    assert 'value="Acme Store"' in html and 'value="acme"' in html and "secreta123" not in html
    assert not app["usuarios"].existe("acme")
    assert app["correos"] == []
    assert "usuario" not in _sesion(c)


@pytest.mark.parametrize("cambio, mensaje", [
    ({"correo": "no-es-correo"}, "Escribe un correo válido"),
    ({"password": "corta"}, "al menos 8 caracteres"),
    ({"usuario": "Acme Store"}, "El usuario debe tener"),
])
def test_registro_valida_correo_contrasena_y_usuario(app, cambio, mensaje):
    c = app["dashboard"].app.test_client()
    r = c.post("/proyectos/nuevo", data={**REGISTRO, **cambio})
    assert r.status_code == 400 and mensaje in r.get_data(as_text=True)
    assert list(app["usuarios"].cargar()) == ["admin"]


def test_registro_con_correo_crea_usuario_envia_verificacion_y_abre_sesion(app):
    c = app["dashboard"].app.test_client()
    r = c.post("/proyectos/nuevo", data=REGISTRO)
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme_store")
    entry = app["usuarios"].obtener("acme")
    assert entry["correo"] == "dueno@acme.com" and entry["correo_verificado"] is False and entry["cliente"] == "acme_store"
    s = _sesion(c)
    assert s["usuario"] == "acme" and s["rol"] == "cliente" and s["cliente"] == "acme_store" and s["sv"] == 1
    assert len(app["correos"]) == 1 and app["correos"][0]["a"] == "dueno@acme.com"
    assert "http://127.0.0.1:5050/verificar/" in app["correos"][0]["cuerpo"]   # sin PLATAFORMA_URL: base local
    assert any("Te mandamos un correo a dueno@acme.com" in m for m in _flashes(c))


def test_registro_rechaza_correo_ya_usado(app):
    app["usuarios"].crear("otro", "secreta123", "cliente", cliente="otro", correo="dueno@acme.com")
    c = app["dashboard"].app.test_client()
    r = c.post("/proyectos/nuevo", data=REGISTRO)
    assert r.status_code == 400 and "Ese correo ya tiene una cuenta" in r.get_data(as_text=True)
    assert not app["usuarios"].existe("acme")


def test_registro_sin_smtp_no_falla_y_avisa(app, monkeypatch):
    monkeypatch.setattr(app["cuentas"], "smtp_configurado", lambda: False)
    c = app["dashboard"].app.test_client()
    r = c.post("/proyectos/nuevo", data=REGISTRO)
    assert r.status_code == 302
    assert app["usuarios"].obtener("acme")["correo_verificado"] is False
    assert app["correos"] == []
    assert any("no tiene correo configurado" in m for m in _flashes(c))


# --- verificar ----------------------------------------------------------------

def test_verificar_token_valido_repetido_y_vencido(app, monkeypatch):
    c = app["dashboard"].app.test_client()
    c.post("/proyectos/nuevo", data=REGISTRO)
    enlace = _enlace(app["correos"][0], "verificar")
    r = c.get(enlace)
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme_store#settings")
    assert app["usuarios"].obtener("acme")["correo_verificado"] is True
    assert any("Correo confirmado" in m for m in _flashes(c))
    # Repetido: ya se usó.
    r = c.get(enlace)
    assert any("ya se usó o venció" in m for m in _flashes(c))
    # Vencido: uno nuevo, 25 h después.
    app["usuarios"].actualizar("acme", correo_verificado=False)
    token = app["cuentas"].emitir("verificacion", "acme", "dueno@acme.com")
    from datetime import datetime, timedelta
    monkeypatch.setattr(app["cuentas"], "_ahora", lambda: datetime.now() + timedelta(hours=25))
    c.get(f"/verificar/{token}")
    assert app["usuarios"].obtener("acme")["correo_verificado"] is False
    assert any("ya se usó o venció" in m for m in _flashes(c))


def test_verificar_sin_sesion_redirige_al_login_y_actualiza_el_correo_del_token(app):
    _ana(app, correo="vieja@ejemplo.com")
    token = app["cuentas"].emitir("verificacion", "ana", "nueva@ejemplo.com")
    c = app["dashboard"].app.test_client()
    r = c.get(f"/verificar/{token}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    entry = app["usuarios"].obtener("ana")
    assert entry["correo"] == "nueva@ejemplo.com" and entry["correo_verificado"] is True


# --- reenviar -----------------------------------------------------------------

def test_reenviar_exige_sesion(app):
    r = app["dashboard"].app.test_client().post("/reenviar-verificacion")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_reenviar_envia_y_respeta_el_limite(app, monkeypatch):
    c = _ana(app)
    r = c.post("/reenviar-verificacion")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#settings")
    assert len(app["correos"]) == 1 and app["correos"][0]["a"] == "ana@ejemplo.com"
    # Límite alcanzado: no se envía y se pide esperar.
    monkeypatch.setattr(app["cuentas"], "limite_ok", lambda clave, maximo=5, ventana_s=3600: False)
    c.post("/reenviar-verificacion")
    assert len(app["correos"]) == 1
    assert any("Espera un momento" in m for m in _flashes(c))


def test_reenviar_con_correo_verificado_no_envia(app):
    c = _ana(app, verificado=True)
    c.post("/reenviar-verificacion")
    assert app["correos"] == [] and any("ya está confirmado" in m for m in _flashes(c))


def test_reenviar_sin_smtp_avisa_y_no_emite_token(app, monkeypatch):
    monkeypatch.setattr(app["cuentas"], "smtp_configurado", lambda: False)
    c = _ana(app)
    c.post("/reenviar-verificacion")
    assert app["correos"] == [] and any("no tiene correo configurado" in m for m in _flashes(c))


# --- recuperar ----------------------------------------------------------------

def test_recuperar_get_muestra_el_formulario_y_login_lo_enlaza(app):
    c = app["dashboard"].app.test_client()
    html = c.get("/recuperar").get_data(as_text=True)
    assert 'action="/recuperar"' in html and 'name="correo"' in html
    assert 'href="/recuperar"' in c.get("/login").get_data(as_text=True)


def test_recuperar_misma_respuesta_exista_o_no_el_correo(app):
    _ana(app)
    c = app["dashboard"].app.test_client()
    r1 = c.post("/recuperar", data={"correo": "nadie@ejemplo.com"})
    f1 = _flashes(c)
    assert r1.status_code == 302 and r1.headers["Location"].endswith("/login")
    assert app["correos"] == []                       # desconocido: ningún envío
    c.get("/login")                                    # consume el flash
    r2 = c.post("/recuperar", data={"correo": "ANA@ejemplo.com"})
    f2 = _flashes(c)
    assert r2.status_code == r1.status_code and r2.headers["Location"] == r1.headers["Location"]
    assert f1 == f2 and any("Si ese correo está registrado" in m for m in f2)
    assert len(app["correos"]) == 1 and "/restablecer/" in app["correos"][0]["cuerpo"]


def test_recuperar_respeta_el_limite(app, monkeypatch):
    _ana(app)
    monkeypatch.setattr(app["cuentas"], "limite_ok", lambda clave, maximo=5, ventana_s=3600: False)
    c = app["dashboard"].app.test_client()
    c.post("/recuperar", data={"correo": "ana@ejemplo.com"})
    assert app["correos"] == [] and any("Si ese correo está registrado" in m for m in _flashes(c))


# --- restablecer --------------------------------------------------------------

def test_restablecer_flujo_completo_y_sesion_vieja_invalidada(app):
    vieja = _ana(app)                                   # navegador A, sesión abierta con la contraseña vieja
    assert vieja.get("/cliente/acme").status_code == 200
    app["dashboard"].app.test_client().post("/recuperar", data={"correo": "ana@ejemplo.com"})
    enlace = _enlace(app["correos"][0], "restablecer")
    b = app["dashboard"].app.test_client()             # navegador B, desde el correo
    html = b.get(enlace).get_data(as_text=True)
    assert 'name="confirmacion"' in html and "Enlace vencido" not in html
    # Contraseñas distintas: error sin gastar el token.
    r = b.post(enlace, data={"password": "nueva12345", "confirmacion": "otra12345"})
    assert r.status_code == 400 and "no coinciden" in r.get_data(as_text=True)
    r = b.post(enlace, data={"password": "nueva12345", "confirmacion": "nueva12345"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert any("Contraseña cambiada" in m for m in _flashes(b))
    assert app["usuarios"].verificar("ana", "nueva12345") and not app["usuarios"].verificar("ana", "secreta123")
    entry = app["usuarios"].obtener("ana")
    assert entry["session_version"] == 2 and entry["correo_verificado"] is True   # abrió el enlace de SU correo
    # El enlace ya no sirve.
    assert b.get(enlace).status_code == 400 and "Enlace vencido" in b.get(enlace).get_data(as_text=True)
    # La sesión vieja (sv=1) queda fuera en la siguiente petición.
    r = vieja.get("/cliente/acme")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert "usuario" not in _sesion(vieja)
    assert any("Tu sesión se cerró" in m for m in _flashes(vieja))


def test_restablecer_token_invalido_muestra_vencido(app):
    c = app["dashboard"].app.test_client()
    r = c.get("/restablecer/no-existe")
    assert r.status_code == 400 and "Enlace vencido" in r.get_data(as_text=True)
    r = c.post("/restablecer/no-existe", data={"password": "nueva12345", "confirmacion": "nueva12345"})
    assert r.status_code == 400 and "Enlace vencido" in r.get_data(as_text=True)


# --- cuenta: correo y contraseña ---------------------------------------------

def test_cuenta_correo_pide_la_contrasena_actual(app):
    c = _ana(app, verificado=True)
    c.post("/cuenta/correo", data={"correo": "nueva@ejemplo.com", "password": "malísima"})
    assert app["usuarios"].obtener("ana")["correo"] == "ana@ejemplo.com"
    assert app["correos"] == [] and any("contraseña actual no es correcta" in m for m in _flashes(c))


def test_cuenta_correo_cambia_desverifica_y_envia(app):
    c = _ana(app, verificado=True)
    r = c.post("/cuenta/correo", data={"correo": "Nueva@Ejemplo.com", "password": "secreta123"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#settings")
    entry = app["usuarios"].obtener("ana")
    assert entry["correo"] == "nueva@ejemplo.com" and entry["correo_verificado"] is False
    assert len(app["correos"]) == 1 and app["correos"][0]["a"] == "nueva@ejemplo.com"
    # El enlace del correo nuevo lo confirma.
    c.get(_enlace(app["correos"][0], "verificar"))
    assert app["usuarios"].obtener("ana")["correo_verificado"] is True


def test_cuenta_correo_rechaza_el_de_otro_usuario(app):
    app["usuarios"].crear("bob", "secreta123", "cliente", cliente="bob", correo="bob@ejemplo.com")
    c = _ana(app)
    c.post("/cuenta/correo", data={"correo": "bob@ejemplo.com", "password": "secreta123"})
    assert app["usuarios"].obtener("ana")["correo"] == "ana@ejemplo.com"
    assert any("ya está en uso" in m for m in _flashes(c))


def test_cuenta_password_cambia_y_la_sesion_actual_sigue(app):
    c = _ana(app, verificado=True)
    c.post("/cuenta/password", data={"password_actual": "mala", "password": "nueva12345", "confirmacion": "nueva12345"})
    assert app["usuarios"].verificar("ana", "secreta123") and any("actual no es correcta" in m for m in _flashes(c))
    c.post("/cuenta/password", data={"password_actual": "secreta123", "password": "nueva12345", "confirmacion": "distinta1"})
    assert app["usuarios"].verificar("ana", "secreta123") and any("no coinciden" in m for m in _flashes(c))
    r = c.post("/cuenta/password", data={"password_actual": "secreta123", "password": "nueva12345", "confirmacion": "nueva12345"})
    assert r.status_code == 302
    assert app["usuarios"].verificar("ana", "nueva12345")
    assert _sesion(c)["sv"] == 2
    assert c.get("/cliente/acme").status_code == 200          # esta sesión sigue viva


def test_cuenta_rutas_exigen_sesion(app):
    c = app["dashboard"].app.test_client()
    for ruta in ("/cuenta/correo", "/cuenta/password"):
        r = c.post(ruta, data={})
        assert r.status_code == 302 and r.headers["Location"].endswith("/login"), ruta


# --- sesión / guard -------------------------------------------------------------

def test_login_guarda_sv_y_una_sesion_sin_sv_se_sella(app):
    _ana(app)
    c = app["dashboard"].app.test_client()
    r = c.post("/login", data={"usuario": "ana", "password": "secreta123"})
    assert r.status_code == 302 and _sesion(c)["sv"] == 1
    # Cookie anterior a esta versión (sin sv): se sella con la versión actual.
    c2 = app["dashboard"].app.test_client()
    with c2.session_transaction() as s:
        s["usuario"] = "ana"; s["rol"] = "cliente"; s["cliente"] = "acme"
    assert c2.get("/cliente/acme").status_code == 200
    assert _sesion(c2)["sv"] == 1


def test_sesion_de_usuario_borrado_se_cierra(app):
    c = _ana(app)
    app["usuarios"].guardar({})
    r = c.get("/cliente/acme")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login") and "usuario" not in _sesion(c)


@pytest.mark.parametrize("ruta, metodo", [
    ("/cliente/acme/meta/conectar", "get"),
    ("/cliente/acme/meta/app", "post"),
    ("/cliente/acme/config/tienda/conectar", "post"),
    ("/cliente/acme/config/tienda/meli/iniciar", "get"),
])
def test_guard_sin_correo_verificado_bloquea_meta_y_tiendas(app, monkeypatch, ruta, metodo):
    llamadas = []
    monkeypatch.setattr(app["dashboard"].meta_conexion, "guardar_app", lambda c, d: llamadas.append(("app", c)))
    monkeypatch.setattr(app["dashboard"].meta_conexion, "url_dialogo", lambda c, s: llamadas.append(("dialogo", c)) or "https://meta.test/dialogo")
    monkeypatch.setattr(app["dashboard"].cifrado, "disponible", lambda: False)   # tienda: primer paso tras el guard
    c = _ana(app)
    r = getattr(c, metodo)(ruta, data={})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#settings")
    assert any("Confirma tu correo primero" in m for m in _flashes(c))
    assert llamadas == []
    # Verificado: pasa el guard (y llega al siguiente paso de la ruta).
    app["usuarios"].actualizar("ana", correo_verificado=True)
    c = _ana_relogin(app)
    r = getattr(c, metodo)(ruta, data={})
    assert not any("Confirma tu correo primero" in m for m in _flashes(c))
    if ruta.endswith("/meta/conectar"):
        assert r.headers["Location"] == "https://meta.test/dialogo" and llamadas == [("dialogo", "acme")]


def _ana_relogin(app):
    return _cliente_con_sesion(app, "ana")


def test_guard_no_aplica_al_admin(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].meta_conexion, "url_dialogo", lambda c, s: "https://meta.test/dialogo")
    r = _cliente_admin(app["dashboard"]).get("/cliente/acme/meta/conectar")
    assert r.status_code == 302 and r.headers["Location"] == "https://meta.test/dialogo"


# --- panel admin ------------------------------------------------------------------

def test_panel_lista_usuarios_y_el_admin_marca_verificado(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].estado_mod, "listar_clientes", lambda: [])
    app["usuarios"].crear("ana", "secreta123", "cliente", cliente="acme", correo="ana@ejemplo.com")
    app["usuarios"].crear("sin", "secreta123", "cliente", cliente="otro")
    admin = _cliente_admin(app["dashboard"])
    html = admin.get("/panel").get_data(as_text=True)
    assert 'id="panel-usuarios"' in html and "ana@ejemplo.com" in html
    assert html.count('action="/admin/usuarios/') == 2                 # las dos sin verificar
    assert "pbkdf2" not in html and 'id="aviso-smtp"' not in html
    r = admin.post("/admin/usuarios/ana/verificar")
    assert r.status_code == 302 and r.headers["Location"].endswith("/panel")
    assert app["usuarios"].obtener("ana")["correo_verificado"] is True
    html = admin.get("/panel").get_data(as_text=True)
    assert html.count('action="/admin/usuarios/') == 1
    # Usuario inexistente: error sin excepción.
    admin.post("/admin/usuarios/nadie/verificar")
    assert any("No existe el usuario" in m for m in _flashes(admin))


def test_panel_avisa_smtp_sin_configurar(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].estado_mod, "listar_clientes", lambda: [])
    monkeypatch.setattr(app["cuentas"], "smtp_configurado", lambda: False)
    html = _cliente_admin(app["dashboard"]).get("/panel").get_data(as_text=True)
    assert 'id="aviso-smtp"' in html and "SMTP sin configurar" in html


def test_marcar_verificado_es_solo_del_admin(app):
    c = _ana(app)
    r = c.post("/admin/usuarios/ana/verificar")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert app["usuarios"].obtener("ana")["correo_verificado"] is False


# --- banner y Configuración › Cuenta -------------------------------------------------

def test_banner_presente_sin_verificar_y_ausente_verificado(app):
    c = _ana(app)
    html = c.get("/cliente/acme").get_data(as_text=True)
    assert 'id="cuenta-banner"' in html and "Confirma tu correo ana@ejemplo.com" in html
    assert 'action="/reenviar-verificacion"' in html and "no tiene correo configurado" not in html
    app["usuarios"].actualizar("ana", correo_verificado=True)
    html = c.get("/cliente/acme").get_data(as_text=True)
    assert 'id="cuenta-banner"' not in html


def test_banner_sin_correo_pide_el_correo_y_sin_smtp_avisa(app, monkeypatch):
    app["usuarios"].crear("viejo", "secreta123", "cliente", cliente="acme")
    c = _cliente_con_sesion(app, "viejo")
    html = c.get("/cliente/acme").get_data(as_text=True)
    assert 'id="cuenta-banner"' in html and 'action="/cuenta/correo"' in html and "Tu cuenta no tiene correo" in html
    c.post("/cuenta/correo", data={"correo": "viejo@ejemplo.com", "password": "secreta123"})
    monkeypatch.setattr(app["cuentas"], "smtp_configurado", lambda: False)
    html = c.get("/cliente/acme").get_data(as_text=True)
    assert "Confirma tu correo viejo@ejemplo.com" in html
    assert "el servidor no tiene correo configurado; avisa al administrador" in html
    assert 'action="/reenviar-verificacion"' in html and "Reenviar</button>" not in html


def test_admin_no_ve_el_banner(app):
    html = _cliente_admin(app["dashboard"]).get("/cliente/acme").get_data(as_text=True)
    assert 'id="cuenta-banner"' not in html


def test_configuracion_tiene_seccion_cuenta_y_tarjeta_smtp_renombrada(app):
    c = _ana(app, verificado=True)
    html = c.get("/cliente/acme").get_data(as_text=True)
    cfg = html[html.index('<section id="tab-settings"'):]
    assert cfg.index("Puesta a punto") < cfg.index('id="config-cuenta"') < cfg.index('id="config-gasto"')
    assert 'action="/cuenta/correo"' in cfg and 'action="/cuenta/password"' in cfg
    assert "ana@ejemplo.com" in cfg and ">confirmado<" in cfg
    assert "Correo de la plataforma (cuentas y avisos)" in cfg
    tarjeta = cfg[cfg.index('id="llave-smtp"'):cfg.index("</article>", cfg.index('id="llave-smtp"'))]
    assert "confirmar el correo de cada cuenta" in tarjeta and "Contraseñas de aplicación" in tarjeta
    assert "PLATAFORMA_URL" in tarjeta


# --- C1: la base de los enlaces nunca sale de la cabecera Host ---------------------------

def test_enlace_por_correo_usa_plataforma_url_y_no_la_cabecera_host(app, monkeypatch):
    _ana(app)
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.creatv.test/")
    c = app["dashboard"].app.test_client()
    r = c.post("/recuperar", data={"correo": "ana@ejemplo.com"}, headers={"Host": "evil.example"})
    assert r.status_code == 302
    cuerpo = app["correos"][0]["cuerpo"]
    assert "https://app.creatv.test/restablecer/" in cuerpo and "evil.example" not in cuerpo
    assert "evil.example" not in (app["correos"][0]["html"] or "")


def test_url_base_sin_plataforma_url_cae_a_meta_redirect_uri_o_local(app, monkeypatch, caplog):
    d = app["dashboard"]
    monkeypatch.setattr(d, "_aviso_url_base_dado", False)
    with d.app.test_request_context("/recuperar", base_url="http://evil.example",
                                    headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "evil.example"}):
        with caplog.at_level("WARNING", logger="dashboard"):
            assert d._url_base() == "http://127.0.0.1:5050"
            assert d._url_base() == "http://127.0.0.1:5050"
        assert sum("PLATAFORMA_URL" in rec.getMessage() for rec in caplog.records) == 1   # avisa una sola vez
        monkeypatch.setenv("META_REDIRECT_URI", "https://app.creatv.test/meta/callback")
        assert d._url_base() == "https://app.creatv.test"
        monkeypatch.setenv("PLATAFORMA_URL", "https://fija.test/")
        assert d._url_base() == "https://fija.test"


def test_host_distinto_a_plataforma_url_es_404_salvo_localhost(app, monkeypatch):
    d = app["dashboard"]
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.creatv.test")
    c = d.app.test_client()
    # Con app.testing el chequeo no corre (los demás tests usan "localhost").
    assert c.get("/login", headers={"Host": "evil.example"}).status_code == 200
    monkeypatch.setitem(d.app.config, "TESTING", False)
    assert c.get("/login", headers={"Host": "evil.example"}).status_code == 404
    assert c.get("/login", headers={"Host": "app.creatv.test"}).status_code == 200
    assert c.get("/login", headers={"Host": "APP.creatv.test:443"}).status_code == 200
    assert c.get("/login", headers={"Host": "localhost:5050"}).status_code == 200
    assert c.get("/login", headers={"Host": "127.0.0.1:5050"}).status_code == 200
    monkeypatch.delenv("PLATAFORMA_URL")
    assert c.get("/login", headers={"Host": "evil.example"}).status_code == 200   # sin la variable no se filtra


# --- I1: toda sesión tiene que ser de un usuario que exista -------------------------------

def test_sesion_de_usuario_inexistente_sin_sv_tambien_se_cierra(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "fantasma"; s["rol"] = "cliente"; s["cliente"] = "acme"      # cookie vieja, sin sv
    r = c.get("/cliente/acme")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert "usuario" not in _sesion(c)
    # Y también al pedir un proyecto ajeno: la sesión muerta se cierra antes del guard por cliente.
    with c.session_transaction() as s:
        s["usuario"] = "fantasma"; s["rol"] = "cliente"; s["cliente"] = "acme"
    r = c.get("/cliente/otro")
    assert r.headers["Location"].endswith("/login") and "usuario" not in _sesion(c)


# --- I2: la IP sale de remote_addr; X-Forwarded-For solo con ProxyFix ----------------------

def test_ip_cliente_ignora_x_forwarded_for_salvo_detras_de_proxy(app, monkeypatch):
    from werkzeug.middleware.proxy_fix import ProxyFix
    d = app["dashboard"]
    xff = {"X-Forwarded-For": "1.2.3.4, 9.9.9.9", "X-Forwarded-Proto": "https"}
    with d.app.test_request_context("/recuperar", headers=xff, environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        assert d._ip_cliente() == "127.0.0.1"
    monkeypatch.delenv("DETRAS_DE_PROXY", raising=False)
    assert d._detras_de_proxy() is False
    monkeypatch.setenv("DETRAS_DE_PROXY", "1")
    assert d._detras_de_proxy() is True
    # Con ProxyFix (x_for=1) vale el ÚLTIMO valor, el que añade nginx; el primero lo inventa el cliente.
    monkeypatch.setattr(d.app, "wsgi_app", ProxyFix(d.app.wsgi_app, x_for=1, x_proto=1, x_host=0))
    vistas = []
    monkeypatch.setattr(d, "_limite_correo", lambda prefijo, correo: vistas.append(d._ip_cliente()) or False)
    _ana(app)
    d.app.test_client().post("/recuperar", data={"correo": "ana@ejemplo.com"}, headers=xff,
                             environ_base={"REMOTE_ADDR": "127.0.0.1"})
    assert vistas == ["9.9.9.9"]


# --- I3: cookie de sesión y POST sin contraseña solo desde la propia página ----------------

def test_flags_de_la_cookie_de_sesion(app):
    d = app["dashboard"]
    assert d.app.config["SESSION_COOKIE_HTTPONLY"] is True and d.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert d._config_sesion("https://app.creatv.test")["SESSION_COOKIE_SECURE"] is True
    assert d._config_sesion("http://localhost:5050")["SESSION_COOKIE_SECURE"] is False
    assert d._config_sesion("")["SESSION_COOKIE_SECURE"] is False
    c = d.app.test_client()
    _ana(app)
    r = c.post("/login", data={"usuario": "ana", "password": "secreta123"})
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


@pytest.mark.parametrize("sitio, esperado", [
    (None, 302), ("same-origin", 302), ("none", 302), ("cross-site", 403), ("same-site", 403),
])
def test_reenviar_y_marcar_verificado_rechazan_post_de_otro_sitio(app, sitio, esperado):
    headers = {} if sitio is None else {"Sec-Fetch-Site": sitio}
    c = _ana(app)
    r = c.post("/reenviar-verificacion", headers=headers)
    assert r.status_code == esperado
    assert len(app["correos"]) == (1 if esperado == 302 else 0)
    admin = _cliente_admin(app["dashboard"])
    r = admin.post("/admin/usuarios/ana/verificar", headers=headers)
    assert r.status_code == esperado
    assert app["usuarios"].obtener("ana")["correo_verificado"] is (esperado == 302)


# --- I4: el registro tiene tope por IP y el correo de verificación pasa por el límite -------

def test_registro_limita_por_ip_y_el_correo_por_limite(app, monkeypatch):
    d = app["dashboard"]
    claves = []
    real = app["cuentas"].limite_ok

    def espiar(clave, maximo=5, ventana_s=3600):
        claves.append(clave)
        return real(clave, maximo, ventana_s)
    monkeypatch.setattr(app["cuentas"], "limite_ok", espiar)
    c = d.app.test_client()
    r = c.post("/proyectos/nuevo", data=REGISTRO, environ_base={"REMOTE_ADDR": "5.6.7.8"})
    assert r.status_code == 302 and len(app["correos"]) == 1
    assert claves == ["alta:ip:5.6.7.8", "verif:dueno@acme.com", "verif:ip:5.6.7.8"]
    # Sexto registro desde la misma IP en la hora: 429 y no se crea nada.
    for i in range(4):
        real(f"alta:ip:5.6.7.8")
    r = d.app.test_client().post("/proyectos/nuevo", data={**REGISTRO, "nombre": "Otra", "usuario": "otra",
                                                            "correo": "otra@acme.com"},
                                 environ_base={"REMOTE_ADDR": "5.6.7.8"})
    assert r.status_code == 429 and not app["usuarios"].existe("otra") and len(app["correos"]) == 1
    assert "Demasiados registros" in r.get_data(as_text=True)
    # Otra IP sigue pudiendo, pero si el límite de correos ya está lleno se crea la cuenta sin enviar.
    monkeypatch.setattr(app["cuentas"], "limite_ok", lambda clave, maximo=5, ventana_s=3600: not clave.startswith("verif"))
    r = d.app.test_client().post("/proyectos/nuevo", data={**REGISTRO, "nombre": "Otra", "usuario": "otra",
                                                            "correo": "otra@acme.com"},
                                 environ_base={"REMOTE_ADDR": "5.6.7.9"})
    assert r.status_code == 302 and app["usuarios"].existe("otra") and len(app["correos"]) == 1


# --- menores: confirm del panel, token viejo al cambiar correo, Referrer-Policy ------------

def test_panel_confirm_no_se_rompe_con_un_usuario_raro(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].estado_mod, "listar_clientes", lambda: [])
    raro = "x') ;alert(1);//"
    app["usuarios"].guardar({**app["usuarios"].cargar(),
                             raro: {"password_hash": "x", "rol": "cliente", "cliente": "acme", "correo": "r@x.com"}})
    html = _cliente_admin(app["dashboard"]).get("/panel").get_data(as_text=True)
    onsubmit = re.search(r"onsubmit='([^']*)'", html).group(1)
    # Ni la comilla cruda ni su entidad (&#39;, que el parser HTML decodifica
    # antes de que JS vea el atributo) llegan al confirm: va como '.
    assert "'" not in onsubmit and "&#39;" not in onsubmit
    assert "confirm(\"\\u00bfMarcar a x\\u0027) ;alert(1);//" in onsubmit


def test_cambiar_correo_invalida_el_token_del_correo_anterior_aunque_no_se_envie(app, monkeypatch):
    c = _ana(app, correo="vieja@ejemplo.com")
    token_viejo = app["cuentas"].emitir("verificacion", "ana", "vieja@ejemplo.com")
    monkeypatch.setattr(app["cuentas"], "smtp_configurado", lambda: False)   # no se emite uno nuevo
    c.post("/cuenta/correo", data={"correo": "nueva@ejemplo.com", "password": "secreta123"})
    assert app["usuarios"].obtener("ana")["correo"] == "nueva@ejemplo.com"
    assert app["cuentas"].validar("verificacion", token_viejo) is None
    c.get(f"/verificar/{token_viejo}")
    entry = app["usuarios"].obtener("ana")
    assert entry["correo"] == "nueva@ejemplo.com" and entry["correo_verificado"] is False


def test_referrer_policy_en_paginas_con_token(app):
    _ana(app)
    token = app["cuentas"].emitir("restablecer", "ana", "ana@ejemplo.com")
    c = app["dashboard"].app.test_client()
    assert c.get(f"/restablecer/{token}").headers["Referrer-Policy"] == "no-referrer"
    assert c.get("/login").headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

import smtplib

import pytest


class SMTPFalso:
    instancias = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.llamadas = []
        SMTPFalso.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.llamadas.append("starttls")

    def login(self, usuario, clave):
        self.llamadas.append(("login", usuario, clave))

    def send_message(self, msg):
        self.llamadas.append(("send", msg["To"], msg["From"], msg["Subject"], msg.get_content()))


@pytest.fixture()
def smtp_falso(monkeypatch):
    SMTPFalso.instancias = []
    monkeypatch.setattr(smtplib, "SMTP", SMTPFalso)
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)
    return SMTPFalso


def test_sin_smtp_host_devuelve_false_sin_enviar(smtp_falso):
    import notificaciones
    assert notificaciones.enviar("a@b.co", "Hola", "cuerpo") is False
    assert smtp_falso.instancias == []


def test_sin_destinatario_devuelve_false(smtp_falso, monkeypatch):
    import notificaciones
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    assert notificaciones.enviar("", "Hola", "cuerpo") is False
    assert notificaciones.enviar(None, "Hola", "cuerpo") is False
    assert smtp_falso.instancias == []


def test_envia_con_starttls_login_y_send(smtp_falso, monkeypatch):
    import notificaciones
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    monkeypatch.setenv("SMTP_FROM", "motor@ejemplo.com")
    assert notificaciones.enviar("a@b.co", "Asunto", "Cuerpo") is True
    s = smtp_falso.instancias[0]
    assert (s.host, s.port) == ("smtp.ejemplo.com", 2525)
    assert s.llamadas[0] == "starttls" and s.llamadas[1] == ("login", "u", "p")
    assert s.llamadas[2][:4] == ("send", "a@b.co", "motor@ejemplo.com", "Asunto")
    assert s.llamadas[2][4].strip() == "Cuerpo"


def test_sin_usuario_no_hace_login(smtp_falso, monkeypatch):
    import notificaciones
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    assert notificaciones.enviar("a@b.co", "Asunto", "Cuerpo") is True
    assert not any(isinstance(l, tuple) and l[0] == "login" for l in smtp_falso.instancias[0].llamadas)


def test_excepcion_devuelve_false(smtp_falso, monkeypatch):
    import notificaciones

    class Rompe(SMTPFalso):
        def send_message(self, msg):
            raise smtplib.SMTPException("se cayó")

    monkeypatch.setattr(smtplib, "SMTP", Rompe)
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    assert notificaciones.enviar("a@b.co", "Asunto", "Cuerpo") is False


def test_avisar_usa_correo_del_proyecto_y_registra_bitacora(smtp_falso, monkeypatch, tmp_path):
    import bitacora
    import notificaciones
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    monkeypatch.setattr(bitacora, "LOG_FILE", str(tmp_path / "bitacora.csv"))
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    # Sin correo configurado: no envía pero tampoco lanza, y queda en bitácora.
    assert proyectos.correo_notificaciones("acme") is None
    assert notificaciones.avisar("acme", "propuesta", "Asunto", "Cuerpo") is False
    assert smtp_falso.instancias == []
    proyectos.guardar_correo_notificaciones("acme", "  dueño@acme.co ")
    assert proyectos.correo_notificaciones("acme") == "dueño@acme.co"
    assert notificaciones.avisar("acme", "ganador", "Asunto", "Cuerpo") is True
    assert smtp_falso.instancias[0].llamadas[-1][1] == "dueño@acme.co"
    filas = bitacora.leer("acme")
    assert [f["etapa"] for f in filas] == ["ganador", "propuesta"]
    assert filas[0]["estado"] == "enviado" and filas[1]["estado"] == "sin_correo"


def test_avisar_nunca_lanza(smtp_falso, monkeypatch):
    import notificaciones
    monkeypatch.setattr(notificaciones.proyectos, "correo_notificaciones", lambda c: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(notificaciones.bitacora, "registrar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("y")))
    assert notificaciones.avisar("acme", "rechazo_meta", "A", "B") is False


# ---- avisos a los administradores (spec §2.5) ----

USUARIOS_PRUEBA = {
    "daniel": {"rol": "admin", "correo": "daniel@creatv.co", "correo_verificado": True},
    "otro_admin": {"rol": "admin", "correo": "otro@creatv.co", "correo_verificado": False},
    "repetido": {"rol": "admin", "correo": "daniel@creatv.co", "correo_verificado": True},
    "acme": {"rol": "cliente", "correo": "acme@cliente.co", "correo_verificado": True},
}


@pytest.fixture()
def admins_falsos(monkeypatch):
    import bitacora
    import notificaciones
    import usuarios
    monkeypatch.setattr(usuarios, "cargar", lambda: {k: dict(v) for k, v in USUARIOS_PRUEBA.items()})
    registros = []
    monkeypatch.setattr(bitacora, "registrar", lambda *a, **k: registros.append(a))
    enviados = []
    monkeypatch.setattr(notificaciones, "enviar", lambda destinatario, asunto, cuerpo, html=None: enviados.append((destinatario, asunto)) or True)
    return {"registros": registros, "enviados": enviados}


def test_correos_admin_solo_verificados_sin_repetir(admins_falsos):
    import notificaciones
    assert notificaciones.correos_admin() == ["daniel@creatv.co"]


def test_avisar_admin_manda_a_cada_admin_y_deja_bitacora(admins_falsos):
    import notificaciones
    n = notificaciones.avisar_admin("meta_solicitud", "Acme pide conectar Meta", "portafolio 777", cliente="acme")
    assert n == 1 and admins_falsos["enviados"] == [("daniel@creatv.co", "Acme pide conectar Meta")]
    assert admins_falsos["registros"][-1][:4] == ("acme", "admin", "meta_solicitud", "enviado:1")


def test_avisar_admin_sin_admins_ni_smtp_no_lanza(admins_falsos, monkeypatch):
    import notificaciones
    import usuarios
    monkeypatch.setattr(usuarios, "cargar", lambda: {})
    assert notificaciones.avisar_admin("meta_cambio_forma", "x", "y") == 0
    assert admins_falsos["registros"][-1][:4] == ("_admin", "admin", "meta_cambio_forma", "sin_correo")
    # usuarios.json ilegible tampoco tumba nada.
    def _rompe():
        raise OSError("disco")
    monkeypatch.setattr(usuarios, "cargar", _rompe)
    assert notificaciones.avisar_admin("meta_conectado", "x", "y") == 0


def test_tipos_nuevos_registrados():
    import notificaciones
    for tipo in ("meta_solicitud", "meta_conexion_cliente", "meta_cambio_forma", "meta_conectado"):
        assert tipo in notificaciones.TIPOS

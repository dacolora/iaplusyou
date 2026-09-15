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

"""Task 1 de cuentas con correo verificado: usuarios con correo, tokens de
un solo uso (token_cuenta), límite por hora y correos de verificación /
restablecimiento con notificaciones.enviar falso (sin red)."""
import json
import logging
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa


@pytest.fixture()
def usuarios_tmp(tmp_path, monkeypatch):
    import usuarios
    ruta = tmp_path / "usuarios.json"
    monkeypatch.setattr(usuarios, "_path", lambda: str(ruta))
    return usuarios


@pytest.fixture()
def envios(monkeypatch):
    """notificaciones.enviar falso: captura (destinatario, asunto, cuerpo, html)."""
    import notificaciones
    capturados = []

    def falso(destinatario, asunto, cuerpo, html=None):
        capturados.append({"para": destinatario, "asunto": asunto, "cuerpo": cuerpo, "html": html})
        return True

    monkeypatch.setattr(notificaciones, "enviar", falso)
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    return capturados


# --- usuarios -------------------------------------------------------------

def test_crear_guarda_correo_normalizado_y_defaults(usuarios_tmp):
    u = usuarios_tmp
    u.crear("ana", "secreta123", "cliente", cliente="acme", correo="  Ana@Ejemplo.COM ")
    entry = u.obtener("ana")
    assert entry["correo"] == "ana@ejemplo.com"
    assert entry["correo_verificado"] is False
    assert entry["session_version"] == 1
    assert entry["creado_en"] and datetime.fromisoformat(entry["creado_en"])
    assert u.verificar("ana", "secreta123")["correo"] == "ana@ejemplo.com"


def test_crear_sin_correo_deja_none_y_correo_invalido_falla(usuarios_tmp):
    u = usuarios_tmp
    u.crear("sin", "secreta123", "cliente", cliente="acme")
    assert u.obtener("sin")["correo"] is None
    with pytest.raises(ValueError):
        u.crear("mal", "secreta123", "cliente", cliente="acme", correo="no-es-correo")


def test_registro_viejo_sin_llaves_se_completa_al_leer(usuarios_tmp):
    u = usuarios_tmp
    u.guardar({"viejo": {"password_hash": u._hash("secreta123"), "rol": "cliente", "cliente": "acme"}})
    entry = u.verificar("viejo", "secreta123")
    assert entry["correo"] is None
    assert entry["correo_verificado"] is False
    assert entry["session_version"] == 1
    assert u.obtener("viejo")["session_version"] == 1
    assert u.verificar("viejo", "otra") is None
    assert u.obtener("nadie") is None


@pytest.mark.parametrize("entrada,esperado", [
    ("Ana@Ejemplo.com", "ana@ejemplo.com"),
    ("  ana@ejemplo.com  ", "ana@ejemplo.com"),
    ("ana.perez+x@sub.dominio.co", "ana.perez+x@sub.dominio.co"),
    ("", None),
    (None, None),
    ("sinarroba.com", None),
    ("dos@@ejemplo.com", None),
    ("ana@sinpunto", None),
    ("ana @ejemplo.com", None),
    ("@ejemplo.com", None),
    ("ana@", None),
    ("ana@.ejemplo.com", None),
    ("a" * 250 + "@x.co", None),
])
def test_validar_correo(entrada, esperado):
    import usuarios
    assert usuarios.validar_correo(entrada) == esperado


def test_validar_password():
    import usuarios
    assert usuarios.validar_password("12345678") is None
    msg = usuarios.validar_password("corta")
    assert msg and "8" in msg
    assert usuarios.validar_password(None)


def test_por_correo_compara_en_minusculas(usuarios_tmp):
    u = usuarios_tmp
    u.crear("ana", "secreta123", "cliente", cliente="acme", correo="Ana@Ejemplo.com")
    u.crear("sin", "secreta123", "cliente", cliente="acme")
    assert u.por_correo("ANA@ejemplo.COM ")[0] == "ana"
    assert u.por_correo("ana@ejemplo.com")[1]["cliente"] == "acme"
    assert u.por_correo("otro@ejemplo.com") is None
    assert u.por_correo("") is None
    assert u.por_correo(None) is None


def test_actualizar_correo_y_verificado(usuarios_tmp):
    u = usuarios_tmp
    u.crear("ana", "secreta123", "cliente", cliente="acme", correo="ana@ejemplo.com")
    u.actualizar("ana", correo_verificado=True)
    assert u.obtener("ana")["correo_verificado"] is True
    entry = u.actualizar("ana", correo="  Nueva@Ejemplo.com", correo_verificado=False)
    assert entry["correo"] == "nueva@ejemplo.com" and entry["correo_verificado"] is False
    assert u.obtener("ana")["correo"] == "nueva@ejemplo.com"
    assert u.obtener("ana")["rol"] == "cliente" and u.obtener("ana")["cliente"] == "acme"
    with pytest.raises(ValueError):
        u.actualizar("ana", correo="mal")
    with pytest.raises(ValueError):
        u.actualizar("ana", rol="admin")
    with pytest.raises(ValueError):
        u.actualizar("nadie", correo_verificado=True)


def test_cambiar_password_sube_session_version(usuarios_tmp):
    u = usuarios_tmp
    u.crear("ana", "secreta123", "cliente", cliente="acme", correo="ana@ejemplo.com")
    assert u.cambiar_password("ana", "nueva-clave-9") == 2
    assert u.obtener("ana")["session_version"] == 2
    assert u.verificar("ana", "secreta123") is None
    assert u.verificar("ana", "nueva-clave-9")["session_version"] == 2
    with pytest.raises(ValueError):
        u.cambiar_password("ana", "corta")
    assert u.obtener("ana")["session_version"] == 2
    # Un registro viejo sin session_version pasa de 1 (implícito) a 2.
    u.guardar({"viejo": {"password_hash": u._hash("secreta123"), "rol": "admin", "cliente": None}})
    assert u.cambiar_password("viejo", "otra-clave-9") == 2


# --- tokens ---------------------------------------------------------------

def _filas(db):
    with db.conectar() as con:
        return con.execute(sa.select(db.token_cuenta).order_by(db.token_cuenta.c.id)).mappings().all()


def test_emitir_guarda_hash_no_el_token(base_temporal):
    import cuentas
    token = cuentas.emitir("verificacion", "ana", "Ana@Ejemplo.com", ip="10.0.0.1")
    assert isinstance(token, str) and len(token) >= 40
    filas = _filas(base_temporal)
    assert len(filas) == 1
    f = filas[0]
    assert f["token_hash"] == cuentas._hash(token) and f["token_hash"] != token
    assert f["usuario"] == "ana" and f["correo"] == "ana@ejemplo.com" and f["ip"] == "10.0.0.1"
    assert f["usado_en"] is None
    creado = datetime.fromisoformat(f["creado_en"])
    vence = datetime.fromisoformat(f["vence_en"])
    assert vence - creado == timedelta(hours=24)


def test_restablecer_vence_a_una_hora(base_temporal):
    import cuentas
    cuentas.emitir("restablecer", "ana", "ana@ejemplo.com")
    f = _filas(base_temporal)[0]
    assert datetime.fromisoformat(f["vence_en"]) - datetime.fromisoformat(f["creado_en"]) == timedelta(hours=1)


def test_consumir_es_de_un_solo_uso(base_temporal):
    import cuentas
    token = cuentas.emitir("verificacion", "ana", "ana@ejemplo.com")
    assert cuentas.validar("verificacion", token) == {"usuario": "ana", "correo": "ana@ejemplo.com"}
    assert cuentas.validar("verificacion", token) is not None  # validar no consume
    assert cuentas.consumir("verificacion", token) == {"usuario": "ana", "correo": "ana@ejemplo.com"}
    assert cuentas.consumir("verificacion", token) is None
    assert cuentas.validar("verificacion", token) is None
    assert _filas(base_temporal)[0]["usado_en"] is not None


def test_consumir_rechaza_tipo_equivocado_e_inventado(base_temporal):
    import cuentas
    token = cuentas.emitir("restablecer", "ana", "ana@ejemplo.com")
    assert cuentas.consumir("verificacion", token) is None
    assert cuentas.consumir("restablecer", "inventado") is None
    assert cuentas.consumir("restablecer", "") is None
    assert cuentas.consumir("restablecer", None) is None
    # El de tipo equivocado no lo quemó: sigue vivo para su tipo.
    assert cuentas.consumir("restablecer", token) is not None
    with pytest.raises(ValueError):
        cuentas.emitir("otro", "ana", "ana@ejemplo.com")
    with pytest.raises(ValueError):
        cuentas.consumir("otro", token)


def test_token_vencido_no_sirve(base_temporal, monkeypatch):
    import cuentas
    token = cuentas.emitir("restablecer", "ana", "ana@ejemplo.com")
    real = cuentas._ahora()
    monkeypatch.setattr(cuentas, "_ahora", lambda: real + timedelta(hours=1, seconds=1))
    assert cuentas.validar("restablecer", token) is None
    assert cuentas.consumir("restablecer", token) is None
    assert _filas(base_temporal)[0]["usado_en"] is None


def test_emitir_invalida_los_anteriores_del_mismo_tipo(base_temporal):
    import cuentas
    t1 = cuentas.emitir("verificacion", "ana", "ana@ejemplo.com")
    r1 = cuentas.emitir("restablecer", "ana", "ana@ejemplo.com")
    otro = cuentas.emitir("verificacion", "beto", "beto@ejemplo.com")
    t2 = cuentas.emitir("verificacion", "ana", "ana@ejemplo.com")
    assert cuentas.consumir("verificacion", t1) is None
    assert cuentas.consumir("verificacion", t2) is not None
    # Ni el de otro tipo ni el de otro usuario se tocaron.
    assert cuentas.consumir("restablecer", r1) is not None
    assert cuentas.consumir("verificacion", otro) is not None


def test_consumir_invalida_los_demas_del_mismo_tipo(base_temporal):
    import cuentas
    import db
    a = cuentas.emitir("restablecer", "ana", "ana@ejemplo.com")
    b = cuentas.emitir("restablecer", "ana", "ana@ejemplo.com")
    # Revivimos `a` a mano para simular dos tokens vivos a la vez.
    with db.conectar() as con:
        con.execute(sa.update(db.token_cuenta).values(usado_en=None))
    assert cuentas.consumir("restablecer", b) is not None
    assert cuentas.consumir("restablecer", a) is None
    assert all(f["usado_en"] for f in _filas(base_temporal))


# --- límite ---------------------------------------------------------------

def test_limite_ok_por_ventana(base_temporal):
    import cuentas
    import db
    for _ in range(5):
        assert cuentas.limite_ok("correo:ana@ejemplo.com") is True
    assert cuentas.limite_ok("correo:ana@ejemplo.com") is False
    assert cuentas.limite_ok("correo:ana@ejemplo.com") is False
    # El sexto rechazado no se anotó: siguen 5 marcas.
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == "limite:correo:ana@ejemplo.com")).scalar()
    assert len(json.loads(crudo)) == 5
    # Otra clave no se ve afectada.
    assert cuentas.limite_ok("ip:1.2.3.4") is True
    assert cuentas.limite_ok("x", maximo=1) is True
    assert cuentas.limite_ok("x", maximo=1) is False


def test_limite_ok_olvida_marcas_viejas(base_temporal, monkeypatch):
    import cuentas
    import time as time_mod
    base = 1_000_000.0
    monkeypatch.setattr(cuentas.time, "time", lambda: base)
    for _ in range(5):
        assert cuentas.limite_ok("c", maximo=5, ventana_s=3600) is True
    assert cuentas.limite_ok("c", maximo=5, ventana_s=3600) is False
    monkeypatch.setattr(cuentas.time, "time", lambda: base + 3601)
    assert cuentas.limite_ok("c", maximo=5, ventana_s=3600) is True
    assert isinstance(time_mod.time(), float)


def test_limite_ok_tolera_valor_corrupto(base_temporal):
    import cuentas
    import db
    with db.conectar() as con:
        con.execute(db.kv.insert().values(clave="limite:raro", valor="no es json", actualizado_en=db.ahora()))
    assert cuentas.limite_ok("raro") is True


# --- correos --------------------------------------------------------------

def test_smtp_configurado(monkeypatch):
    import cuentas
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert cuentas.smtp_configurado() is False
    monkeypatch.setenv("SMTP_HOST", "  ")
    assert cuentas.smtp_configurado() is False
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    assert cuentas.smtp_configurado() is True


def test_enviar_verificacion_manda_enlace_con_token_valido(base_temporal, envios, caplog):
    import cuentas
    caplog.set_level(logging.DEBUG)
    assert cuentas.enviar_verificacion("ana", "Ana@Ejemplo.com", "https://app.ejemplo.com/", ip="1.2.3.4") is True
    assert len(envios) == 1
    e = envios[0]
    assert e["para"] == "ana@ejemplo.com"
    assert "Creatv Machine" in e["asunto"] and "correo" in e["asunto"].lower()
    filas = _filas(base_temporal)
    assert len(filas) == 1 and filas[0]["tipo"] == "verificacion" and filas[0]["ip"] == "1.2.3.4"
    # El enlace del cuerpo lleva el token crudo (sin doble barra) y ese token sirve.
    prefijo = "https://app.ejemplo.com/verificar/"
    linea = next(l for l in e["cuerpo"].splitlines() if l.startswith(prefijo))
    token = linea[len(prefijo):]
    assert token and cuentas._hash(token) == filas[0]["token_hash"]
    assert linea in e["html"] and "Creatv Machine" in e["html"] and "24 horas" in e["cuerpo"]
    assert "ana" in e["cuerpo"]
    assert cuentas.consumir("verificacion", token) == {"usuario": "ana", "correo": "ana@ejemplo.com"}
    # El token nunca pasa por los logs.
    assert caplog.records, "se esperaba al menos un log de emisión/envío"
    assert all(token not in r.getMessage() for r in caplog.records)
    assert all(filas[0]["token_hash"] not in r.getMessage() for r in caplog.records)


def test_enviar_restablecer_manda_enlace_y_vence_en_una_hora(base_temporal, envios):
    import cuentas
    assert cuentas.enviar_restablecer("ana", "ana@ejemplo.com", "https://app.ejemplo.com") is True
    e = envios[0]
    assert "contraseña" in e["asunto"].lower() and "Creatv Machine" in e["asunto"]
    prefijo = "https://app.ejemplo.com/restablecer/"
    token = next(l for l in e["cuerpo"].splitlines() if l.startswith(prefijo))[len(prefijo):]
    assert "1 hora" in e["cuerpo"] and prefijo + token in e["html"]
    assert cuentas.validar("restablecer", token) == {"usuario": "ana", "correo": "ana@ejemplo.com"}
    assert _filas(base_temporal)[0]["tipo"] == "restablecer"


def test_sin_smtp_devuelve_false_sin_excepcion_ni_token(base_temporal, monkeypatch):
    import cuentas
    import notificaciones
    monkeypatch.delenv("SMTP_HOST", raising=False)
    llamadas = []
    monkeypatch.setattr(notificaciones, "enviar", lambda *a, **k: llamadas.append(a) or True)
    assert cuentas.enviar_verificacion("ana", "ana@ejemplo.com", "https://app.ejemplo.com") is False
    assert cuentas.enviar_restablecer("ana", "ana@ejemplo.com", "https://app.ejemplo.com") is False
    assert llamadas == []
    assert _filas(base_temporal) == []


def test_envio_fallido_devuelve_false(base_temporal, monkeypatch):
    import cuentas
    import notificaciones
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setattr(notificaciones, "enviar", lambda *a, **k: False)
    assert cuentas.enviar_verificacion("ana", "ana@ejemplo.com", "https://app.ejemplo.com") is False
    monkeypatch.setattr(notificaciones, "enviar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert cuentas.enviar_restablecer("ana", "ana@ejemplo.com", "https://app.ejemplo.com") is False
    assert cuentas.enviar_verificacion("ana", "", "https://app.ejemplo.com") is False


def test_notificaciones_enviar_con_html_manda_multipart(monkeypatch):
    import smtplib
    import notificaciones
    enviados = []

    class SMTPFalso:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            enviados.append(msg)

    monkeypatch.setattr(smtplib, "SMTP", SMTPFalso)
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    assert notificaciones.enviar("a@b.co", "Asunto", "Texto plano", html="<p>Hola</p>") is True
    msg = enviados[0]
    assert msg.is_multipart() and msg.get_content_type() == "multipart/alternative"
    partes = [p.get_content_type() for p in msg.iter_parts()]
    assert partes == ["text/plain", "text/html"]
    assert msg.get_body(("plain",)).get_content().strip() == "Texto plano"
    assert "<p>Hola</p>" in msg.get_body(("html",)).get_content()
    # Sin html sigue siendo texto plano simple (firma vieja intacta).
    assert notificaciones.enviar("a@b.co", "Asunto", "Solo texto") is True
    assert not enviados[1].is_multipart()

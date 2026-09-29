"""
Avisos por correo del motor (Bloque 4): propuestas pendientes, ganadores,
rechazos de Meta, errores de lanzamiento, tiendas que dejaron de sincronizar
(Bloque 5, tipo "tienda") y publicaciones orgánicas terminadas (Bloque 7,
tipo "publicado": qué salió, con sus URLs, y qué falló). SMTP con STARTTLS leído del entorno
(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM); el destinatario es el
correo de notificaciones del proyecto (proyectos.correo_notificaciones).

Regla de oro: nada de acá tumba una tarea. Sin SMTP configurado o sin
destinatario se devuelve False y el aviso queda solo en la bitácora; un error
de red o de autenticación se registra y también devuelve False. Los cuerpos
nunca llevan tokens ni credenciales: quien arma el texto pasa mensajes ya
limpios (cola.sin_token) y este módulo no agrega nada del entorno.
"""
import logging
import os
import smtplib
from email.message import EmailMessage

import bitacora
import idiomas
import proyectos

log = logging.getLogger("creatv.notificaciones")

TIPOS = ("propuesta", "ganador", "rechazo_meta", "error_lanzamiento", "tope", "tienda", "sprint_lote", "publicado",
         "meta_solicitud", "meta_conexion_cliente", "meta_cambio_forma", "meta_conectado", "tw_evaluacion")


def _config():
    host = (os.environ.get("SMTP_HOST") or "").strip()
    try:
        puerto = int(os.environ.get("SMTP_PORT") or 587)
    except (TypeError, ValueError):
        puerto = 587
    usuario = os.environ.get("SMTP_USER") or ""
    clave = os.environ.get("SMTP_PASS") or ""
    remitente = (os.environ.get("SMTP_FROM") or usuario or "").strip()
    return host, puerto, usuario, clave, remitente


def enviar(destinatario, asunto, cuerpo, html=None):
    """True si el correo salió; False (sin excepción) si falta configuración,
    falta destinatario o el envío falló. Con `html` se manda multipart
    (texto plano + alternativa HTML); sin él, texto plano como siempre."""
    host, puerto, usuario, clave, remitente = _config()
    destinatario = (destinatario or "").strip()
    if not host or not destinatario:
        log.info("correo no enviado (sin SMTP_HOST o sin destinatario): %s", asunto)
        return False
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = remitente or usuario or f"creatv@{host}"
    msg["To"] = destinatario
    msg.set_content(cuerpo or "")
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(host, puerto, timeout=30) as smtp:
            smtp.starttls()
            if usuario:
                smtp.login(usuario, clave)
            smtp.send_message(msg)
        return True
    except Exception as error:  # noqa: BLE001 — un correo nunca tumba una tarea
        log.error("no se pudo enviar el correo '%s': %s", asunto, type(error).__name__)
        return False


def avisar(cliente, tipo, asunto, cuerpo):
    """Aviso de motor para un proyecto: siempre queda en la bitácora; se manda
    por correo al destinatario del proyecto si hay uno y SMTP está
    configurado. Devuelve True solo si el correo salió. Nunca lanza."""
    if tipo not in TIPOS:
        log.warning("tipo de aviso desconocido: %r", tipo)
    try:
        destinatario = proyectos.correo_notificaciones(cliente)
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo leer el correo de notificaciones de %s: %s", cliente, type(error).__name__)
        destinatario = None
    enviado = False
    try:
        enviado = enviar(destinatario, asunto, cuerpo)
    except Exception as error:  # noqa: BLE001 — defensa extra; enviar ya no lanza
        log.error("aviso %s falló: %s", tipo, type(error).__name__)
    try:
        bitacora.registrar(cliente, "motor", tipo, "enviado" if enviado else "sin_correo", asunto)
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo registrar el aviso en la bitácora: %s", type(error).__name__)
    return enviado


def admins_con_correo():
    """(usuario, correo) de los admins con correo verificado (usuarios.json),
    sin correos repetidos, ordenados por correo. [] si no hay o el archivo no
    se puede leer."""
    import usuarios  # noqa: PLC0415 — import tardío: usuarios no depende de este módulo, pero así no se acoplan al cargar
    try:
        data = usuarios.cargar()
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo leer usuarios.json para avisar a los admins: %s", type(error).__name__)
        return []
    por_correo = {}
    for usuario, entry in (data or {}).items():
        correo = (entry.get("correo") or "").strip()
        if entry.get("rol") == "admin" and entry.get("correo_verificado") and correo:
            por_correo.setdefault(correo, usuario)
    return sorted(((u, c) for c, u in por_correo.items()), key=lambda uc: uc[1])


def correos_admin():
    """Correos verificados de los usuarios con rol admin, ordenados y sin repetir."""
    return [c for _u, c in admins_con_correo()]


def _textos(idioma, *valores):
    """Cada valor tal cual si es texto; si es una función, su resultado
    armado en `idioma`. Sin funciones no se toca el idioma (texto = como antes)."""
    if not any(callable(v) for v in valores):
        return valores
    with idiomas.en_idioma(idioma):
        return tuple(v() if callable(v) else v for v in valores)


def avisar_admin(tipo, asunto, cuerpo, cliente=""):
    """Aviso para los administradores de la plataforma (spec §2.5): una
    solicitud de un cliente, una conexión hecha por un cliente, un cambio de
    forma. Un correo por admin con correo verificado; siempre queda en la
    bitácora (del proyecto que lo originó, o "_admin"). Devuelve cuántos
    correos salieron. Nunca lanza.

    `asunto` y `cuerpo` pueden ser texto o una función sin argumentos: si son
    funciones se llaman una vez por admin, en el idioma de ese admin (spec
    2026-09-26 §B8), y la bitácora guarda el asunto en el idioma por defecto."""
    if tipo not in TIPOS:
        log.warning("tipo de aviso desconocido: %r", tipo)
    enviados = 0
    for usuario, correo in admins_con_correo():
        try:
            a, c = (_textos(idiomas.de_usuario(usuario), asunto, cuerpo)
                    if callable(asunto) or callable(cuerpo) else (asunto, cuerpo))
            if enviar(correo, a, c):
                enviados += 1
        except Exception as error:  # noqa: BLE001 — defensa extra; enviar ya no lanza
            log.error("aviso admin %s falló: %s", tipo, type(error).__name__)
    try:
        (a0,) = _textos(idiomas.DEFECTO, asunto)
        bitacora.registrar(cliente or "_admin", "admin", tipo, f"enviado:{enviados}" if enviados else "sin_correo", a0)
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo registrar el aviso admin en la bitácora: %s", type(error).__name__)
    return enviados

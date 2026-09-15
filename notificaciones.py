"""
Avisos por correo del motor (Bloque 4): propuestas pendientes, ganadores,
rechazos de Meta y errores de lanzamiento. SMTP con STARTTLS leído del entorno
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
import proyectos

log = logging.getLogger("creatv.notificaciones")

TIPOS = ("propuesta", "ganador", "rechazo_meta", "error_lanzamiento")


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


def enviar(destinatario, asunto, cuerpo):
    """True si el correo salió; False (sin excepción) si falta configuración,
    falta destinatario o el envío falló."""
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

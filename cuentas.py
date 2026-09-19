"""
Cuentas: tokens de un solo uso (verificar correo, restablecer contraseña),
límites por hora y los correos que los llevan. Plan:
docs/superpowers/plans/2026-09-19-cuentas-correo-verificado.md.

El usuario sigue en usuarios.json (usuarios.py); acá solo se toca la tabla
`token_cuenta` (db.py, migración 0011) y `kv` para los límites. El token
crudo (32 bytes de secrets.token_urlsafe) viaja únicamente en el enlace del
correo: en la base queda su sha256, y este módulo nunca lo escribe en logs.

Reglas:
  - `verificacion` vence a 24 h, `restablecer` a 1 h.
  - Un solo uso: `consumir` marca `usado_en` y, de paso, invalida los demás
    del mismo tipo para ese usuario. `emitir` también invalida los anteriores.
  - `limite_ok` es una ventana deslizante simple (timestamps en JSON dentro
    de kv `limite:<clave>`): la llamada que supera el máximo no cuenta.
  - Sin SMTP configurado nada falla: `enviar_*` devuelven False y quien llama
    decide qué decirle al usuario.
"""
import hashlib
import html as html_mod
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
import notificaciones

log = logging.getLogger("creatv.cuentas")

NOMBRE_PLATAFORMA = "Creatv Machine"
TIPOS = ("verificacion", "restablecer")
VENCIMIENTO_S = {"verificacion": 24 * 3600, "restablecer": 3600}
TOKEN_BYTES = 32
LIMITE_MAXIMO = 5
LIMITE_VENTANA_S = 3600


def _ahora():
    return datetime.now()


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def _hash(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _validar_tipo(tipo):
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de token desconocido: {tipo!r}. Opciones: {TIPOS}")


def smtp_configurado():
    """True si el servidor tiene correo (SMTP_HOST). Solo mira si está, nunca
    el valor."""
    return bool((os.environ.get("SMTP_HOST") or "").strip())


# --- tokens ---------------------------------------------------------------

def _invalidar_anteriores(con, tipo, usuario, ahora_iso):
    con.execute(
        sa.update(db.token_cuenta)
        .where(db.token_cuenta.c.usuario == usuario,
               db.token_cuenta.c.tipo == tipo,
               db.token_cuenta.c.usado_en.is_(None))
        .values(usado_en=ahora_iso)
    )


def emitir(tipo, usuario, correo, ip=None):
    """Crea un token nuevo de ese tipo para el usuario y devuelve el token
    crudo (lo único que va en el enlace). Los tokens anteriores del mismo
    tipo que no se hayan usado quedan invalidados."""
    _validar_tipo(tipo)
    if not usuario:
        raise ValueError("Falta el usuario.")
    correo = (correo or "").strip().lower()
    if not correo:
        raise ValueError("Falta el correo.")
    token = secrets.token_urlsafe(TOKEN_BYTES)
    ahora = _ahora()
    ahora_iso = _iso(ahora)
    vence = _iso(ahora + timedelta(seconds=VENCIMIENTO_S[tipo]))
    with db.conectar() as con:
        _invalidar_anteriores(con, tipo, usuario, ahora_iso)
        con.execute(db.token_cuenta.insert().values(
            usuario=usuario, tipo=tipo, correo=correo, token_hash=_hash(token),
            creado_en=ahora_iso, vence_en=vence, usado_en=None,
            ip=str(ip)[:45] if ip else None,
        ))
    log.info("token de %s emitido para %s", tipo, usuario)
    return token


def _buscar_vivo(con, tipo, token, ahora_iso):
    """La fila del token si existe, es de ese tipo, no se usó y no venció."""
    if not token or not isinstance(token, str):
        return None
    fila = con.execute(
        sa.select(db.token_cuenta).where(db.token_cuenta.c.token_hash == _hash(token))
    ).mappings().first()
    if fila is None or fila["tipo"] != tipo or fila["usado_en"] is not None:
        return None
    if not fila["vence_en"] or fila["vence_en"] <= ahora_iso:
        return None
    return fila


def _resultado(fila):
    return {"usuario": fila["usuario"], "correo": fila["correo"]}


def validar(tipo, token):
    """{"usuario","correo"} si el token sirve (tipo correcto, sin usar, sin
    vencer), sin consumirlo — para el GET de /restablecer que solo muestra el
    formulario. None en cualquier otro caso."""
    _validar_tipo(tipo)
    with db.conectar() as con:
        fila = _buscar_vivo(con, tipo, token, _iso(_ahora()))
    return _resultado(fila) if fila is not None else None


def consumir(tipo, token):
    """Igual que validar, pero marca el token como usado (y con él los demás
    del mismo tipo para ese usuario). Un segundo consumir del mismo token
    devuelve None."""
    _validar_tipo(tipo)
    ahora_iso = _iso(_ahora())
    with db.conectar() as con:
        fila = _buscar_vivo(con, tipo, token, ahora_iso)
        if fila is None:
            return None
        # UPDATE condicionado a usado_en IS NULL: si dos peticiones llegan a
        # la vez con el mismo enlace, solo una lo consume.
        marcado = con.execute(
            sa.update(db.token_cuenta)
            .where(db.token_cuenta.c.id == fila["id"], db.token_cuenta.c.usado_en.is_(None))
            .values(usado_en=ahora_iso)
        ).rowcount
        if not marcado:
            return None
        _invalidar_anteriores(con, tipo, fila["usuario"], ahora_iso)
    log.info("token de %s consumido por %s", tipo, fila["usuario"])
    return _resultado(fila)


# --- límites --------------------------------------------------------------

def limite_ok(clave, maximo=LIMITE_MAXIMO, ventana_s=LIMITE_VENTANA_S):
    """Ventana deslizante en kv (`limite:<clave>` = JSON con timestamps).
    True si todavía cabe otro intento (y lo anota); False si en la ventana ya
    hubo `maximo` (y no anota nada, así el bloqueo no se alarga solo)."""
    clave_kv = f"limite:{clave}"
    ahora = time.time()
    desde = ahora - ventana_s
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == clave_kv)).scalar()
        try:
            marcas = [float(t) for t in (json.loads(crudo) if crudo else [])]
        except (TypeError, ValueError):
            marcas = []
        marcas = [t for t in marcas if t > desde]
        if len(marcas) >= maximo:
            return False
        marcas.append(ahora)
        valor = json.dumps(marcas)
        con.execute(insert_sqlite(db.kv).values(
            clave=clave_kv, valor=valor, actualizado_en=db.ahora()
        ).on_conflict_do_update(index_elements=["clave"], set_={"valor": valor, "actualizado_en": db.ahora()}))
    return True


# --- correos --------------------------------------------------------------

def _horas_texto(segundos):
    horas = segundos // 3600
    if horas == 1:
        return "1 hora"
    return f"{horas} horas"


def _armar_correo(tipo, usuario, enlace):
    """(asunto, texto plano, html) del correo de ese tipo."""
    vence = _horas_texto(VENCIMIENTO_S[tipo])
    if tipo == "verificacion":
        asunto = f"Confirma tu correo en {NOMBRE_PLATAFORMA}"
        intro = (f"Hola {usuario},\n\nPara terminar de crear tu cuenta en {NOMBRE_PLATAFORMA} "
                 f"confirma que este correo es tuyo abriendo este enlace:")
        cierre = (f"El enlace vence en {vence}. Si no creaste una cuenta en {NOMBRE_PLATAFORMA}, "
                  f"ignora este correo.")
        boton = "Confirmar mi correo"
    else:
        asunto = f"Restablece tu contraseña de {NOMBRE_PLATAFORMA}"
        intro = (f"Hola {usuario},\n\nAlguien pidió restablecer la contraseña de tu cuenta en "
                 f"{NOMBRE_PLATAFORMA}. Si fuiste tú, abre este enlace para elegir una nueva:")
        cierre = (f"El enlace vence en {vence} y sirve una sola vez. Si no pediste cambiar tu "
                  f"contraseña, ignora este correo: tu cuenta sigue igual.")
        boton = "Elegir nueva contraseña"
    cuerpo = f"{intro}\n\n{enlace}\n\n{cierre}\n\n— {NOMBRE_PLATAFORMA}\n"
    e = html_mod.escape
    parrafos = "".join(f"<p>{e(p)}</p>" for p in intro.split("\n\n"))
    html = (
        "<!DOCTYPE html><html lang=\"es\"><body style=\"font-family:Arial,Helvetica,sans-serif;"
        "color:#222;line-height:1.5\">"
        f"{parrafos}"
        f"<p><a href=\"{e(enlace)}\" style=\"display:inline-block;padding:10px 18px;background:#1f6feb;"
        f"color:#fff;text-decoration:none;border-radius:6px\">{e(boton)}</a></p>"
        f"<p style=\"font-size:13px;color:#555\">Si el botón no funciona, copia este enlace en tu navegador:<br>"
        f"<a href=\"{e(enlace)}\">{e(enlace)}</a></p>"
        f"<p style=\"font-size:13px;color:#555\">{e(cierre)}</p>"
        f"<p>— {e(NOMBRE_PLATAFORMA)}</p>"
        "</body></html>"
    )
    return asunto, cuerpo, html


def _enviar(tipo, ruta, usuario, correo, url_base, ip=None):
    correo = (correo or "").strip().lower()
    if not usuario or not correo:
        return False
    if not smtp_configurado():
        log.info("correo de %s para %s no enviado: sin SMTP configurado", tipo, usuario)
        return False
    token = emitir(tipo, usuario, correo, ip=ip)
    enlace = f"{(url_base or '').rstrip('/')}/{ruta}/{token}"
    asunto, cuerpo, html = _armar_correo(tipo, usuario, enlace)
    try:
        enviado = bool(notificaciones.enviar(correo, asunto, cuerpo, html=html))
    except Exception as error:  # noqa: BLE001 — un correo nunca tumba una petición
        log.error("correo de %s para %s falló: %s", tipo, usuario, type(error).__name__)
        enviado = False
    log.info("correo de %s para %s: %s", tipo, usuario, "enviado" if enviado else "no enviado")
    return enviado


def enviar_verificacion(usuario, correo, url_base, ip=None):
    """Emite un token de verificación y manda el enlace
    `{url_base}/verificar/<token>`. True solo si el correo salió; False sin
    excepción cuando no hay SMTP o el envío falla."""
    return _enviar("verificacion", "verificar", usuario, correo, url_base, ip=ip)


def enviar_restablecer(usuario, correo, url_base, ip=None):
    """Emite un token de restablecimiento y manda el enlace
    `{url_base}/restablecer/<token>`. Misma semántica que enviar_verificacion."""
    return _enviar("restablecer", "restablecer", usuario, correo, url_base, ip=ip)

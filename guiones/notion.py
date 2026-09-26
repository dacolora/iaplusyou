"""
Leer un guion desde una página de Notion (spec 2026-09-25 §9). Cada
proyecto guarda la llave de su integración interna cifrada en `kv`
(`notion:<cliente>`, misma clave derivada que las tiendas). Del link solo se
saca el id: la URL nunca se usa como destino, siempre se consulta
api.notion.com. La llave nunca va a un mensaje de error ni a un log.
"""
import re
from urllib.parse import urlparse

import requests
import sqlalchemy as sa

import cifrado
import db

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
MAX_BLOQUES, MAX_PROFUNDIDAD = 3000, 4
_RE_ID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}", re.I)
_LISTAS = ("bulleted_list_item", "numbered_list_item", "to_do")


class ErrorNotion(Exception):
    """Mensaje en español que se muestra tal cual."""


def extraer_id(url):
    texto = str(url or "").strip()
    if not texto:
        return None
    camino = urlparse(texto).path if "://" in texto else texto
    encontrados = _RE_ID.findall(camino)
    return encontrados[-1].replace("-", "").lower() if encontrados else None


def _clave(cliente):
    return f"notion:{cliente}"


def guardar_llave(cliente, llave):
    valor, ahora = cifrado.cifrar(llave.strip()), db.ahora()
    with db.conectar() as con:
        r = con.execute(db.kv.update().where(db.kv.c.clave == _clave(cliente)).values(valor=valor, actualizado_en=ahora))
        if r.rowcount == 0:
            con.execute(sa.insert(db.kv).values(clave=_clave(cliente), valor=valor, actualizado_en=ahora))


def _valor(cliente):
    with db.conectar() as con:
        return con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == _clave(cliente))).scalar()


def conectado(cliente):
    return bool(_valor(cliente))


def llave(cliente):
    valor = _valor(cliente)
    if not valor:
        return None
    try:
        return cifrado.descifrar(valor)
    except cifrado.ErrorCifrado:
        return None


def borrar(cliente):
    with db.conectar() as con:
        con.execute(db.kv.delete().where(db.kv.c.clave == _clave(cliente)))


def _get(llave_, ruta, http, params=None):
    try:
        r = http.get(f"{API}{ruta}", headers={"Authorization": f"Bearer {llave_}", "Notion-Version": VERSION},
                     params=params, timeout=30)
    except requests.RequestException:
        raise ErrorNotion("No se pudo hablar con Notion; intenta de nuevo en un momento.") from None
    if r.status_code == 401:
        raise ErrorNotion("La llave de Notion no sirve; vuelve a conectarla.")
    if r.status_code in (403, 404):
        raise ErrorNotion("Esa página no está compartida con tu integración de Notion "
                          "(en la página: ··· › Conexiones › tu integración).")
    if r.status_code == 429:
        raise ErrorNotion("Notion pidió esperar; intenta en un minuto.")
    if not r.ok:
        raise ErrorNotion(f"Notion respondió con un error {r.status_code}; intenta de nuevo.")
    return r.json()


def probar(llave_, http=requests):
    _get(llave_, "/users/me", http)


def _texto_bloque(b):
    tipo = b.get("type")
    texto = "".join(rt.get("plain_text", "") for rt in ((b.get(tipo) or {}).get("rich_text") or []))
    return f"- {texto}" if tipo in _LISTAS and texto else texto


def _hijos(llave_, bloque_id, http, profundidad, cuenta, lineas):
    cursor = None
    while True:
        params = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
        d = _get(llave_, f"/blocks/{bloque_id}/children", http, params=params)
        for b in d.get("results", []):
            cuenta[0] += 1
            if cuenta[0] > MAX_BLOQUES:
                raise ErrorNotion("La página es demasiado larga (más de 3000 bloques).")
            lineas.append(_texto_bloque(b))
            if b.get("has_children") and profundidad < MAX_PROFUNDIDAD and b.get("type") != "child_page":
                _hijos(llave_, b["id"], http, profundidad + 1, cuenta, lineas)
        if not d.get("has_more"):
            return
        cursor = d.get("next_cursor")


def leer_pagina(llave_, page_id, http=requests):
    p = _get(llave_, f"/pages/{page_id}", http)
    titulo = ""
    for prop in (p.get("properties") or {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            titulo = "".join(rt.get("plain_text", "") for rt in prop.get("title") or [])
    lineas = []
    _hijos(llave_, page_id, http, 1, [0], lineas)
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    if not texto:
        raise ErrorNotion("La página de Notion está vacía.")
    return titulo, texto

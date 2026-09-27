"""Materiales del editor (spec §1, §2.3, §5): cada archivo que entra o se
produce, en R2 y en la tabla `material`, con hash como clave de caché.
UNIQUE(cliente, hash) garantiza que nada se pague dos veces."""
import hashlib
import os
import shutil
from datetime import datetime, timedelta
from urllib.parse import unquote, urlparse

import sqlalchemy as sa

import db
from storage import r2_uploader

LIMITES = {"video": (200 * 1024 * 1024, 120000), "imagen": (20 * 1024 * 1024, None), "audio": (20 * 1024 * 1024, None)}
CUOTA_BYTES = 2 * 1024 ** 3
EFIMEROS = ("png_texto", "proxy", "tira", "forma_onda")


class MaterialEnUso(RuntimeError):
    pass


class SubidaInvalida(ValueError):
    pass


def hash_archivo(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def hash_clave(*partes):
    return hashlib.sha256("\x1f".join(str(p) for p in partes).encode("utf-8")).hexdigest()


def _fila_a_dict(f):
    return dict(f._mapping) if f is not None else None


def buscar_hash(cliente, hash_):
    with db.conectar() as con:
        return _fila_a_dict(con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.hash == hash_)).first())


def obtener(cliente, material_id):
    with db.conectar() as con:
        return _fila_a_dict(con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.id == int(material_id))).first())


def registrar(cliente, *, tipo, origen, url, hash, bytes, duracion_ms=None, ancho=None, alto=None,
              costo_usd=0.0, padre_id=None, url_proxy=None, extra=None):
    ahora = db.ahora()
    with db.conectar() as con:
        r = con.execute(db.material.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, tipo=tipo, origen=origen, url=url,
            url_proxy=url_proxy, hash=hash, duracion_ms=duracion_ms, ancho=ancho, alto=alto, bytes=int(bytes),
            costo_usd=float(costo_usd or 0.0), padre_id=padre_id, extra=extra or {}, usado_en=ahora))
        return _fila_a_dict(con.execute(sa.select(db.material).where(db.material.c.id == r.inserted_primary_key[0])).first())


def obtener_o_crear(cliente, hash_, producir):
    """(material, creado). `producir()` solo corre si no existe; devuelve los
    kwargs de `registrar` sin `hash`. Si dos procesos producen a la vez, el
    segundo pierde el INSERT y relee (UNIQUE)."""
    existente = buscar_hash(cliente, hash_)
    if existente:
        marcar_uso([existente["id"]])
        return existente, False
    campos = producir()
    try:
        return registrar(cliente, hash=hash_, **campos), True
    except sa.exc.IntegrityError:
        return buscar_hash(cliente, hash_), False


def subir(cliente, local_path, key, content_type, **campos):
    h = hash_archivo(local_path)
    tam = os.path.getsize(local_path)

    def _producir():
        url = r2_uploader.upload_file(local_path, key, content_type)
        return {**campos, "url": url, "bytes": tam}
    mat, _ = obtener_o_crear(cliente, h, _producir)
    return mat


def descargar(mat, destino):
    """Copia `extra.local` si el archivo sigue en disco (el clon de Crear y
    las voces recién sintetizadas viven en salidas/); si no, baja `url`."""
    import requests
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    local = (mat.get("extra") or {}).get("local")
    if local and os.path.isfile(local):
        shutil.copyfile(local, destino)
        return destino
    with requests.get(mat["url"], stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return destino


def marcar_uso(ids):
    if not ids:
        return
    with db.conectar() as con:
        con.execute(db.material.update().where(db.material.c.id.in_([int(i) for i in ids]))
                    .values(usado_en=db.ahora()))


def actualizar_extra(cliente, material_id, **campos):
    """Mezcla `campos` en `extra` (RMW bajo el lock de escritura: el UPDATE
    sin efecto toma el lock RESERVED antes del SELECT, como
    ediciones.versionar) y devuelve la fila actualizada; None si no es de
    este cliente."""
    mid = int(material_id)
    with db.conectar() as con:
        r = con.execute(db.material.update().where(db.material.c.id == mid, db.material.c.cliente == cliente)
                        .values(actualizado_en=db.material.c.actualizado_en))
        if r.rowcount != 1:
            return None
        actual = con.execute(sa.select(db.material.c.extra).where(db.material.c.id == mid)).scalar() or {}
        con.execute(db.material.update().where(db.material.c.id == mid)
                    .values(extra={**actual, **campos}, actualizado_en=db.ahora()))
    return obtener(cliente, mid)


def en_uso(cliente, material_id):
    """True si algún documento vivo (`edicion`) o congelado (`edicion_version`,
    que se puede restaurar o volver a producir) de ese cliente lo lista en
    `materiales` (lista que `documento.validar` deriva de los clips)."""
    mid = int(material_id)

    def _lo_lista(doc):
        return mid in [int(x) for x in (doc or {}).get("materiales") or []]
    with db.conectar() as con:
        for (doc,) in con.execute(sa.select(db.edicion.c.documento).where(db.edicion.c.cliente == cliente)):
            if _lo_lista(doc):
                return True
        for (doc,) in con.execute(sa.select(db.edicion_version.c.documento)
                                  .join(db.edicion, db.edicion.c.id == db.edicion_version.c.edicion_id)
                                  .where(db.edicion.c.cliente == cliente)):
            if _lo_lista(doc):
                return True
    return False


def _key_de_url(url):
    ruta = unquote(urlparse(url).path).lstrip("/")
    return ruta


def _clave_propia(cliente, key):
    """Solo los objetos que el editor subió para este cliente viven bajo
    `clientes/<cliente>/materiales/`; cualquier otra clave (el video de una
    pieza de Crear con origen `crear`, una final, otro cliente) la enlaza
    otra cosa y borrarla en R2 rompería eso."""
    return key.startswith(f"clientes/{cliente}/materiales/")


def borrar(cliente, material_id):
    mat = obtener(cliente, material_id)
    if not mat:
        return False
    if en_uso(cliente, material_id):
        raise MaterialEnUso("Ese material está en una edición; quítalo de ahí primero.")
    # La fila es el único handle al objeto en R2: si el borrado ahí falla,
    # propaga y no toca la base — mejor un material huérfano en la base
    # (reintentable) que uno huérfano en R2 (sin ninguna fila que lo recuerde).
    for url in (mat["url"], mat.get("url_proxy")):
        if url and url.startswith("http"):
            key = _key_de_url(url)
            if _clave_propia(cliente, key):
                r2_uploader.delete_file(key)
    with db.conectar() as con:
        con.execute(db.material.delete().where(db.material.c.id == mat["id"]))
    return True


def limpiar_sin_uso(cliente=None, dias=30):
    limite = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    cond = [db.material.c.tipo.in_(EFIMEROS), sa.func.coalesce(db.material.c.usado_en, db.material.c.creado_en) < limite]
    if cliente:
        cond.append(db.material.c.cliente == cliente)
    with db.conectar() as con:
        filas = [dict(f._mapping) for f in con.execute(sa.select(db.material).where(*cond))]
    n = 0
    for f in filas:
        try:
            if borrar(f["cliente"], f["id"]):
                n += 1
        except MaterialEnUso:
            marcar_uso([f["id"]])
        except Exception:
            # Un R2 caído en esta fila no debe cortar el barrido de las demás;
            # la fila sigue existiendo (borrar no la tocó) y se reintenta la
            # próxima vez que corra limpiar_sin_uso.
            continue
    return n


def validar_subida(tipo, bytes_, duracion_ms=None):
    if tipo not in LIMITES:
        raise SubidaInvalida(f"tipo de archivo no permitido: {tipo}. Acepto video, imagen y audio.")
    max_bytes, max_ms = LIMITES[tipo]
    if int(bytes_) > max_bytes:
        raise SubidaInvalida(f"El {tipo} pesa más de {max_bytes // (1024 * 1024)} MB.")
    if max_ms and duracion_ms and int(duracion_ms) > max_ms:
        raise SubidaInvalida("El video dura más de 2 min.")


def bytes_usados(cliente):
    with db.conectar() as con:
        return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(db.material.c.bytes), 0))
                               .where(db.material.c.cliente == cliente)).scalar() or 0)

"""Conexión de Triple Whale por proyecto (tabla `triple_whale`).

Una fila por proyecto: llave cifrada (Fernet, `cifrado.py`), dominio de la
tienda (el shop-id de Triple Whale), moneda en que se piden las cifras,
modelo y ventana de atribución, estado de la sincronización y `extra`
(backfill_desde, ultimo_resumen, gasto_7d). La llave nunca sale de aquí más
que descifrada para `triple_whale.sql_query`; `obtener` no la devuelve.
"""
import sqlalchemy as sa

import cifrado
import db
import triple_whale


def conectar(cliente: str, llave_descifrada: str, dominio_tienda: str, moneda: str = "USD",
             modelo_atribucion: str = triple_whale.MODELO_DEFECTO,
             ventana_atribucion: str = triple_whale.VENTANA_DEFECTO, zona_horaria: str = "") -> int:
    """Crea o reemplaza la conexión del proyecto. Modelo y ventana se
    normalizan al vocabulario de Triple Whale; si cambian respecto de la
    conexión anterior (o cambia la tienda o la moneda), las métricas copiadas
    se borran: fueron calculadas con otra atribución. Devuelve el id."""
    ahora = db.ahora()
    dominio = triple_whale.normalizar_dominio(dominio_tienda) or (dominio_tienda or "").strip()
    valores = {
        "actualizado_en": ahora,
        "llave": cifrado.cifrar(llave_descifrada),
        "dominio_tienda": dominio,
        "moneda": triple_whale.normalizar_moneda(moneda),
        "modelo_atribucion": triple_whale.normalizar_modelo(modelo_atribucion),
        "ventana_atribucion": triple_whale.normalizar_ventana(ventana_atribucion),
        "zona_horaria": zona_horaria,
        "estado": "conectada",
        "error": None,
    }
    t = db.triple_whale
    with db.conectar() as con:
        fila = con.execute(sa.select(t).where(t.c.cliente == cliente)).first()
        if fila:
            cambio = any(getattr(fila, k) != valores[k]
                         for k in ("dominio_tienda", "moneda", "modelo_atribucion", "ventana_atribucion"))
            if cambio:
                valores.update(extra={}, ultima_sincronizacion=None)
                _borrar_copias(con, cliente)
            con.execute(t.update().where(t.c.id == fila.id).values(**valores))
            return fila.id
        return con.execute(t.insert().values(cliente=cliente, creado_en=ahora, extra={}, **valores)
                           ).inserted_primary_key[0]


def cambiar_ajustes(cliente, moneda=None, modelo_atribucion=None, ventana_atribucion=None):
    """Cambia moneda / modelo / ventana sin volver a pedir la llave. Si algo
    cambió borra las copias (hay que volver a traerlas) y devuelve True."""
    actual = obtener(cliente)
    if not actual:
        return False
    nuevos = {
        "moneda": triple_whale.normalizar_moneda(moneda or actual["moneda"]),
        "modelo_atribucion": triple_whale.normalizar_modelo(modelo_atribucion or actual["modelo_atribucion"]),
        "ventana_atribucion": triple_whale.normalizar_ventana(ventana_atribucion or actual["ventana_atribucion"]),
    }
    if all(actual.get(k) == v for k, v in nuevos.items()):
        return False
    t = db.triple_whale
    with db.conectar() as con:
        _borrar_copias(con, cliente)
        con.execute(t.update().where(t.c.cliente == cliente).values(
            actualizado_en=db.ahora(), extra={}, ultima_sincronizacion=None, **nuevos))
    return True


def obtener_llave(cliente: str):
    """La llave descifrada, o None si no hay conexión."""
    t = db.triple_whale
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.llave).where(t.c.cliente == cliente)).first()
    if not fila or not fila[0]:
        return None
    return cifrado.descifrar(fila[0])


def obtener(cliente: str):
    """La configuración del proyecto SIN la llave, o None. Modelo y ventana
    pasan por el vocabulario de Triple Whale (una fila de antes de la 0022
    puede traer «First Touch» o «7»)."""
    t = db.triple_whale
    with db.conectar() as con:
        fila = con.execute(sa.select(
            t.c.id, t.c.dominio_tienda, t.c.moneda, t.c.modelo_atribucion, t.c.ventana_atribucion,
            t.c.zona_horaria, t.c.estado, t.c.error, t.c.ultima_sincronizacion, t.c.extra, t.c.creado_en,
        ).where(t.c.cliente == cliente)).first()
    if not fila:
        return None
    return {
        "id": fila.id,
        "dominio_tienda": fila.dominio_tienda,
        "moneda": triple_whale.normalizar_moneda(fila.moneda),
        "modelo_atribucion": triple_whale.normalizar_modelo(fila.modelo_atribucion),
        "ventana_atribucion": triple_whale.normalizar_ventana(fila.ventana_atribucion),
        "zona_horaria": fila.zona_horaria,
        "estado": fila.estado,
        "error": fila.error,
        "ultima_sincronizacion": fila.ultima_sincronizacion,
        "extra": dict(fila.extra or {}),
        "creado_en": fila.creado_en,
    }


def url_tags(cliente):
    """Los Parámetros de URL de Triple Whale para los anuncios que Creatv
    crea en Meta, o None si el proyecto no tiene Triple Whale conectado (sin
    él, tw_source/tw_adid solo ensucian el link)."""
    return triple_whale.URL_TAGS if obtener(cliente) else None


def conectados():
    """Proyectos con Triple Whale conectado (para la sincronización periódica)."""
    t = db.triple_whale
    with db.conectar() as con:
        return [r[0] for r in con.execute(sa.select(t.c.cliente).where(t.c.llave.isnot(None)).order_by(t.c.cliente))]


def actualizar(cliente: str, **campos):
    """Actualiza columnas de la conexión (estado, error, ultima_sincronizacion…)."""
    campos["actualizado_en"] = db.ahora()
    t = db.triple_whale
    with db.conectar() as con:
        con.execute(t.update().where(t.c.cliente == cliente).values(**campos))


def actualizar_extra(cliente, cambios):
    """Mezcla `cambios` en `extra` (lectura y escritura en la misma transacción)."""
    t = db.triple_whale
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.extra).where(t.c.cliente == cliente)).first()
        if not fila:
            return
        extra = dict(fila.extra or {})
        extra.update(cambios)
        con.execute(t.update().where(t.c.cliente == cliente).values(extra=extra, actualizado_en=db.ahora()))


def _borrar_copias(con, cliente):
    con.execute(db.tw_anuncio_dia.delete().where(db.tw_anuncio_dia.c.cliente == cliente))
    con.execute(db.tw_tienda_dia.delete().where(db.tw_tienda_dia.c.cliente == cliente))


def desconectar(cliente: str):
    """Quita la conexión y las métricas copiadas de Triple Whale. Las
    evaluaciones con IA (ya pagadas) se conservan."""
    with db.conectar() as con:
        _borrar_copias(con, cliente)
        con.execute(db.triple_whale.delete().where(db.triple_whale.c.cliente == cliente))

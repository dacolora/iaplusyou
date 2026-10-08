"""Conexión de Triple Whale por proyecto, con una tienda por país (spec 2026-10-08 §3 y §4).

Dos tablas, un solo escritor (este archivo, regla 5 de CLAUDE.md):

* `tw_tienda`: una fila por tienda conectada. Lleva la llave cifrada (Fernet,
  `cifrado.py`), el dominio (el shop-id de Triple Whale), el país, el estado de
  su sincronización y su `extra` (backfill_desde, ultimo_resumen, gasto_7d).
* `triple_whale`: los AJUSTES del proyecto, una fila mientras haya al menos una
  tienda: moneda, modelo y ventana de atribución (valen para todas) y su `extra`
  (avisados, aviso_sin_ventas). Sus columnas viejas de conexión ya no se tocan.

La llave nunca sale de aquí más que descifrada por `obtener_llave`, para
`triple_whale.sql_query`; ninguna lectura de este módulo la devuelve.
Cada escritura es UNA transacción (`db.conectar()`) y toda lectura-modificación-
escritura lee dentro de ella.
"""
import sqlalchemy as sa

import cifrado
import db
import triple_whale
from triple_whale.paises import adivinar_pais


class PaisOcupado(ValueError):
    """Otra tienda del mismo proyecto ya usa ese país. `str()` es el código; la
    ruta lo dice en palabras (el texto que ve la persona no se arma aquí)."""

    def __init__(self, pais):
        super().__init__(pais)
        self.pais = pais


# Lo único que `actualizar_tienda` deja escribir: el estado de la sincronización. La llave y el
# dominio entran por `agregar`; el país, por `cambiar_pais` (que controla el país ocupado).
_CAMPOS_TIENDA = frozenset({"estado", "error", "ultima_sincronizacion", "zona_horaria"})


def _pais(codigo):
    """«no» -> «NO»; vacío -> None."""
    return (codigo or "").strip().upper() or None


def _ajustes_de(fila):
    return {
        "id": fila.id,
        "moneda": triple_whale.normalizar_moneda(fila.moneda),
        "modelo_atribucion": triple_whale.normalizar_modelo(fila.modelo_atribucion),
        "ventana_atribucion": triple_whale.normalizar_ventana(fila.ventana_atribucion),
        "extra": dict(fila.extra or {}),
        "actualizado_en": fila.actualizado_en,
    }


def _tienda_de(fila):
    return {
        "id": fila.id, "cliente": fila.cliente, "pais": fila.pais, "dominio": fila.dominio,
        "zona_horaria": fila.zona_horaria, "estado": fila.estado, "error": fila.error,
        "ultima_sincronizacion": fila.ultima_sincronizacion, "extra": dict(fila.extra or {}),
        "creado_en": fila.creado_en, "actualizado_en": fila.actualizado_en,
    }


_COLUMNAS_TIENDA = ("id", "cliente", "pais", "dominio", "zona_horaria", "estado", "error",
                    "ultima_sincronizacion", "extra", "creado_en", "actualizado_en")


def _select_tienda():
    return sa.select(*(getattr(db.tw_tienda.c, c) for c in _COLUMNAS_TIENDA))   # sin la llave


# ---------------------------------------------------------------- lectura ---

def ajustes(cliente):
    """Moneda, modelo, ventana y extra del proyecto, o None si no hay ninguna
    tienda conectada. Modelo y ventana pasan por el vocabulario de Triple Whale
    (una fila de antes de la 0022 puede traer «First Touch» o «7»)."""
    t = db.triple_whale
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.id, t.c.moneda, t.c.modelo_atribucion, t.c.ventana_atribucion,
                                     t.c.extra, t.c.actualizado_en).where(t.c.cliente == cliente)).first()
    return _ajustes_de(fila) if fila else None


def tiendas(cliente):
    """Las tiendas del proyecto SIN llave, por país (las que no tienen, al final) y luego por id."""
    with db.conectar() as con:
        filas = con.execute(_select_tienda().where(db.tw_tienda.c.cliente == cliente)).all()
    return sorted((_tienda_de(f) for f in filas), key=lambda t: (t["pais"] is None, t["pais"] or "", t["id"]))


def tienda(cliente, tienda_id):
    """Una tienda del proyecto, o None. Verifica el cliente: es el aislamiento entre proyectos."""
    with db.conectar() as con:
        fila = con.execute(_select_tienda().where(db.tw_tienda.c.cliente == cliente,
                                                  db.tw_tienda.c.id == tienda_id)).first()
    return _tienda_de(fila) if fila else None


def tienda_de_pais(cliente, pais):
    """La tienda de ese país en el proyecto, o None."""
    pais = _pais(pais)
    if not pais:
        return None
    with db.conectar() as con:
        fila = con.execute(_select_tienda().where(db.tw_tienda.c.cliente == cliente,
                                                  db.tw_tienda.c.pais == pais)).first()
    return _tienda_de(fila) if fila else None


def obtener(cliente):
    """Los ajustes del proyecto más sus `tiendas`, o None si no hay ninguna tienda
    (para quien solo pregunta «¿hay Triple Whale?»). Sin llaves."""
    lista = tiendas(cliente)
    if not lista:
        return None
    base = ajustes(cliente) or {
        "id": None, "moneda": triple_whale.normalizar_moneda(None),
        "modelo_atribucion": triple_whale.MODELO_DEFECTO, "ventana_atribucion": triple_whale.VENTANA_DEFECTO,
        "extra": {}, "actualizado_en": None}
    return {**base, "tiendas": lista}


def obtener_llave(cliente, tienda_id):
    """La llave descifrada de esa tienda, o None si no existe (o no es de ese proyecto)."""
    t = db.tw_tienda
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.llave).where(t.c.cliente == cliente, t.c.id == tienda_id)).first()
    if not fila or not fila[0]:
        return None
    return cifrado.descifrar(fila[0])


def conectadas():
    """`[(cliente, tienda_id)]` de las tiendas con llave, para la sincronización periódica."""
    t = db.tw_tienda
    with db.conectar() as con:
        return [(r[0], r[1]) for r in con.execute(
            sa.select(t.c.cliente, t.c.id).where(t.c.llave.isnot(None)).order_by(t.c.cliente, t.c.id))]


def firma(cliente):
    """`(n tiendas, última modificación de las tiendas y de los ajustes)`: cambia con cualquier
    escritura de aquí, para la clave de caché del Tablero."""
    t, a = db.tw_tienda, db.triple_whale
    with db.conectar() as con:
        n, mt = con.execute(sa.select(sa.func.count(), sa.func.max(t.c.actualizado_en))
                            .where(t.c.cliente == cliente)).one()
        ma = con.execute(sa.select(sa.func.max(a.c.actualizado_en)).where(a.c.cliente == cliente)).scalar()
    return n, max((v for v in (mt, ma) if v), default=None)


def url_tags(cliente):
    """Los Parámetros de URL de Triple Whale para los anuncios que Creatv
    crea en Meta, o None si el proyecto no tiene ninguna tienda conectada (sin
    Triple Whale, tw_source/tw_adid solo ensucian el link)."""
    return triple_whale.URL_TAGS if tiendas(cliente) else None


def kw_url_tags(cliente):
    """`{"url_tags": …}` para pasar como `**kwargs` a `meta_ads.creative`, o `{}`
    sin Triple Whale: el argumento solo viaja cuando hay parámetros, así un
    servidor con el submódulo `meta_ads` sin actualizar sigue creando anuncios
    mientras ningún proyecto los necesite, en vez de fallar en todos."""
    tags = url_tags(cliente)
    return {"url_tags": tags} if tags else {}


# -------------------------------------------------------------- escritura ---

def _borrar_copias(con, cliente, tienda_id=None):
    """Borra las TRES copias (anuncios, tienda y productos) del proyecto, o solo las de una tienda."""
    for tabla in (db.tw_anuncio_dia, db.tw_tienda_dia, db.tw_producto_dia):
        q = tabla.delete().where(tabla.c.cliente == cliente)
        if tienda_id is not None:
            q = q.where(tabla.c.tienda_id == tienda_id)
        con.execute(q)


def _pais_libre(con, cliente, pais, salvo_id=None):
    """Lanza `PaisOcupado` si OTRA tienda del proyecto ya usa ese país."""
    if not pais:
        return
    t = db.tw_tienda
    q = sa.select(t.c.id).where(t.c.cliente == cliente, t.c.pais == pais)
    if salvo_id is not None:
        q = q.where(t.c.id != salvo_id)
    if con.execute(q).first():
        raise PaisOcupado(pais)


def agregar(cliente, llave, dominio, pais=None, moneda="USD", modelo_atribucion=triple_whale.MODELO_DEFECTO,
            ventana_atribucion=triple_whale.VENTANA_DEFECTO, zona_horaria=""):
    """Conecta una tienda al proyecto y devuelve su id.

    * Sin `pais` (None o vacío) se adivina por el dominio; si no hay pista y la tienda ya existía, conserva el suyo.
    * Si el proyecto no tenía ajustes los crea con `moneda`/`modelo_atribucion`/`ventana_atribucion`; si ya
      los tenía, los IGNORA (son del proyecto y se cambian con `cambiar_ajustes`).
    * Si ya hay una tienda con ese dominio la reconecta: llave nueva, estado `conectada`, sin tocar sus cifras.
    * Si OTRA tienda del proyecto usa el país, lanza `PaisOcupado` y no escribe nada."""
    ahora = db.ahora()
    dom = triple_whale.normalizar_dominio(dominio) or (dominio or "").strip()
    t, a = db.tw_tienda, db.triple_whale
    with db.conectar() as con:
        existente = con.execute(sa.select(t.c.id, t.c.pais).where(t.c.cliente == cliente, t.c.dominio == dom)).first()
        elegido = _pais(pais) or adivinar_pais(dom) or (existente.pais if existente else None)
        _pais_libre(con, cliente, elegido, existente.id if existente else None)
        if not con.execute(sa.select(a.c.id).where(a.c.cliente == cliente)).first():
            con.execute(a.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, extra={},
                moneda=triple_whale.normalizar_moneda(moneda),
                modelo_atribucion=triple_whale.normalizar_modelo(modelo_atribucion),
                ventana_atribucion=triple_whale.normalizar_ventana(ventana_atribucion)))
        valores = {"actualizado_en": ahora, "llave": cifrado.cifrar(llave), "dominio": dom, "pais": elegido,
                   "estado": "conectada", "error": None}
        if existente:
            if zona_horaria:
                valores["zona_horaria"] = zona_horaria
            con.execute(t.update().where(t.c.id == existente.id).values(**valores))
            return existente.id
        return con.execute(t.insert().values(cliente=cliente, creado_en=ahora, extra={},
                                             zona_horaria=zona_horaria, **valores)).inserted_primary_key[0]


def conectar(cliente, llave_descifrada, dominio_tienda, moneda="USD", modelo_atribucion=triple_whale.MODELO_DEFECTO,
             ventana_atribucion=triple_whale.VENTANA_DEFECTO, zona_horaria=""):
    """`agregar` con la firma de cuando el proyecto tenía una sola conexión."""
    return agregar(cliente, llave_descifrada, dominio_tienda, None, moneda, modelo_atribucion,
                   ventana_atribucion, zona_horaria)


def cambiar_pais(cliente, tienda_id, pais):
    """Cambia el país de una tienda sin tocar sus cifras (las copias van por `tienda_id`). `pais` vacío = sin
    país. Lanza `PaisOcupado` si OTRA tienda del proyecto lo usa. No hace nada si la tienda no es del proyecto."""
    pais = _pais(pais)
    t = db.tw_tienda
    with db.conectar() as con:
        if not con.execute(sa.select(t.c.id).where(t.c.cliente == cliente, t.c.id == tienda_id)).first():
            return
        _pais_libre(con, cliente, pais, tienda_id)
        con.execute(t.update().where(t.c.id == tienda_id).values(pais=pais, actualizado_en=db.ahora()))


def actualizar_tienda(cliente, tienda_id, **campos):
    """Escribe el estado de la sincronización de una tienda (estado, error, ultima_sincronizacion, zona_horaria)."""
    sobran = set(campos) - _CAMPOS_TIENDA
    if sobran:
        raise ValueError(f"campos no permitidos: {sorted(sobran)}")
    t = db.tw_tienda
    with db.conectar() as con:
        con.execute(t.update().where(t.c.cliente == cliente, t.c.id == tienda_id)
                    .values(actualizado_en=db.ahora(), **campos))


def actualizar_extra_tienda(cliente, tienda_id, cambios):
    """Mezcla `cambios` en el `extra` de una tienda (lee y escribe en la misma transacción)."""
    t = db.tw_tienda
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.extra).where(t.c.cliente == cliente, t.c.id == tienda_id)).first()
        if not fila:
            return
        extra = dict(fila.extra or {})
        extra.update(cambios)
        con.execute(t.update().where(t.c.id == tienda_id).values(extra=extra, actualizado_en=db.ahora()))


def actualizar_extra(cliente, cambios):
    """Mezcla `cambios` en el `extra` del PROYECTO (avisados, aviso_sin_ventas)."""
    a = db.triple_whale
    with db.conectar() as con:
        fila = con.execute(sa.select(a.c.extra).where(a.c.cliente == cliente)).first()
        if not fila:
            return
        extra = dict(fila.extra or {})
        extra.update(cambios)
        con.execute(a.update().where(a.c.cliente == cliente).values(extra=extra, actualizado_en=db.ahora()))


def cambiar_ajustes(cliente, moneda=None, modelo_atribucion=None, ventana_atribucion=None):
    """Cambia moneda / modelo / ventana del proyecto sin volver a pedir llaves. Si algo cambió borra las copias
    de TODAS las tiendas (se calcularon con otra atribución), les vacía el `extra` (backfill_desde…) y la
    última sincronización, y devuelve True. Sin cambios, o sin ajustes, devuelve False."""
    a, t = db.triple_whale, db.tw_tienda
    with db.conectar() as con:
        fila = con.execute(sa.select(a.c.id, a.c.moneda, a.c.modelo_atribucion, a.c.ventana_atribucion,
                                     a.c.extra, a.c.actualizado_en).where(a.c.cliente == cliente)).first()
        if not fila:
            return False
        actual = _ajustes_de(fila)
        nuevos = {
            "moneda": triple_whale.normalizar_moneda(moneda or actual["moneda"]),
            "modelo_atribucion": triple_whale.normalizar_modelo(modelo_atribucion or actual["modelo_atribucion"]),
            "ventana_atribucion": triple_whale.normalizar_ventana(ventana_atribucion or actual["ventana_atribucion"]),
        }
        if all(actual[k] == v for k, v in nuevos.items()):
            return False
        ahora = db.ahora()
        _borrar_copias(con, cliente)
        con.execute(t.update().where(t.c.cliente == cliente).values(
            actualizado_en=ahora, extra={}, ultima_sincronizacion=None))
        con.execute(a.update().where(a.c.id == fila.id).values(actualizado_en=ahora, **nuevos))
    return True


def quitar(cliente, tienda_id):
    """Quita una tienda y sus copias; si era la última, quita también los ajustes del proyecto. Las
    evaluaciones con IA (ya pagadas) se conservan. Devuelve si había tienda que quitar."""
    t = db.tw_tienda
    with db.conectar() as con:
        if not con.execute(sa.select(t.c.id).where(t.c.cliente == cliente, t.c.id == tienda_id)).first():
            return False
        _borrar_copias(con, cliente, tienda_id)
        con.execute(t.delete().where(t.c.id == tienda_id))
        if not con.execute(sa.select(t.c.id).where(t.c.cliente == cliente)).first():
            con.execute(db.triple_whale.delete().where(db.triple_whale.c.cliente == cliente))
    return True


def desconectar(cliente):
    """Quita todas las tiendas del proyecto, sus copias y los ajustes (solo la usan las pruebas).
    Las evaluaciones con IA se conservan."""
    with db.conectar() as con:
        _borrar_copias(con, cliente)
        con.execute(db.tw_tienda.delete().where(db.tw_tienda.c.cliente == cliente))
        con.execute(db.triple_whale.delete().where(db.triple_whale.c.cliente == cliente))

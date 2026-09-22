"""Gestión de conexiones Triple Whale por proyecto.

Tabla `triple_whale`: llave cifrada, dominio de tienda, modelo/ventana, zona horaria.
Espejo de tiendas.py pero para TW como atribución alternativa.
"""
import json
import db
import cifrado
import sqlalchemy as sa
from datetime import datetime


def conectar(cliente: str, llave_descifrada: str, dominio_tienda: str, moneda: str = "USD",
             modelo_atribucion: str = "Triple Attribution", ventana_atribucion: str = "lifetime",
             zona_horaria: str = "") -> int:
    """Crea o reemplaza la conexión de Triple Whale de un proyecto.
    
    Args:
        cliente: proyecto.
        llave_descifrada: API key del usuario (se cifra con Fernet).
        dominio_tienda: Shopify domain (ej: example.myshopify.com).
        moneda: ISO 4217 (ej: USD, COP).
        modelo_atribucion: atribución en Triple Whale (ej: "Triple Attribution").
        ventana_atribucion: ventana (ej: "lifetime", "7d").
        zona_horaria: de la tienda (ej: "America/Bogota").
    
    Returns: id de la fila triple_whale.
    """
    ahora = db.ahora()
    llave_cifrada = cifrado.cifrar(llave_descifrada)
    
    t = db.triple_whale
    with db.conectar() as con:
        # Un registro por proyecto: si existe, reemplaza.
        fila = con.execute(sa.select(t.c.id).where(t.c.cliente == cliente)).first()
        valores = {
            "actualizado_en": ahora,
            "llave": llave_cifrada,
            "dominio_tienda": dominio_tienda,
            "moneda": moneda.upper(),
            "modelo_atribucion": modelo_atribucion,
            "ventana_atribucion": ventana_atribucion,
            "zona_horaria": zona_horaria,
            "estado": "conectada",
            "error": None,
        }
        if fila:
            tw_id = fila[0]
            con.execute(t.update().where(t.c.id == tw_id).values(**valores))
            return tw_id
        return con.execute(t.insert().values(
            cliente=cliente, creado_en=ahora, **valores
        )).inserted_primary_key[0]


def obtener_llave(cliente: str) -> str:
    """Retorna la llave descifrada. None si no existe / no tiene acceso."""
    t = db.triple_whale
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.llave).where(t.c.cliente == cliente)).first()
    if not fila or not fila[0]:
        return None
    return cifrado.descifrar(fila[0])


def obtener(cliente: str) -> dict:
    """Retorna la configuración Triple Whale del proyecto (sin llave)."""
    t = db.triple_whale
    with db.conectar() as con:
        fila = con.execute(sa.select(
            t.c.id, t.c.dominio_tienda, t.c.moneda, t.c.modelo_atribucion,
            t.c.ventana_atribucion, t.c.zona_horaria, t.c.estado, t.c.error,
            t.c.ultima_sincronizacion
        ).where(t.c.cliente == cliente)).first()
    if not fila:
        return None
    return {
        "id": fila[0],
        "dominio_tienda": fila[1],
        "moneda": fila[2],
        "modelo_atribucion": fila[3],
        "ventana_atribucion": fila[4],
        "zona_horaria": fila[5],
        "estado": fila[6],
        "error": fila[7],
        "ultima_sincronizacion": fila[8],
    }


def actualizar(cliente: str, **campos):
    """Actualiza la configuración de Triple Whale del proyecto."""
    ahora = db.ahora()
    t = db.triple_whale
    campos["actualizado_en"] = ahora
    with db.conectar() as con:
        con.execute(t.update().where(t.c.cliente == cliente).values(**campos))


def desconectar(cliente: str):
    """Elimina la conexión Triple Whale del proyecto."""
    t = db.triple_whale
    with db.conectar() as con:
        con.execute(t.delete().where(t.c.cliente == cliente))

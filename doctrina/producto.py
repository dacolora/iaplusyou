"""Pruebas y pedidos de un producto (doctrina, bloque 2, §5).

Viven en `producto.extra` (claves `pruebas` y `pedidos`, protegidas de la
sync de tienda por `tiendas.EXTRA_INTERNO`) y solo se escriben por acá, con
`tiendas.modificar_extra_interno`: toma el lock de escritura antes de leer,
porque la web (responder, borrar) y el worker (resumir pedidos) escriben el
mismo producto."""
from uuid import uuid4

import db
import tiendas

FUENTES_PRUEBA_PRODUCTO = ("ficha", "comentarios")
NOMBRE_FUENTE = {"ficha": "dato del producto", "comentarios": "comentario real de un comprador"}
MAX_PRUEBAS_PRODUCTO = 20
MAX_TEXTO = 400


class ErrorPrueba(ValueError):
    """Algo que no se puede guardar; el mensaje es para la persona."""


def _texto(valor):
    return " ".join(str(valor or "").split())[:MAX_TEXTO]


def pruebas(fila):
    """Las pruebas guardadas de una fila `producto` (dict de `tiendas`)."""
    lista = ((fila or {}).get("extra") or {}).get("pruebas") or []
    return [p for p in lista if isinstance(p, dict) and p.get("texto")]


def pruebas_texto(lista):
    """Líneas para los DATOS de un prompt; "" sin pruebas."""
    return "\n".join(f"- {p['texto']} ({NOMBRE_FUENTE.get(p.get('fuente'), p.get('fuente') or '')})"
                     for p in lista or [] if isinstance(p, dict) and p.get("texto"))


def agregar_prueba(cliente, producto_id, texto, fuente, pedido_id=None):
    """Agrega una prueba y la devuelve. ErrorPrueba si falta el texto, la
    fuente no es de las del producto, ya hay MAX_PRUEBAS_PRODUCTO o el
    producto no existe."""
    texto = _texto(texto)
    if not texto:
        raise ErrorPrueba("Escribe la prueba: un dato real del producto o un comentario de un comprador.")
    if fuente not in FUENTES_PRUEBA_PRODUCTO:
        raise ErrorPrueba("Elige si es un dato del producto o un comentario real de un comprador.")
    nueva = {"id": uuid4().hex[:8], "texto": texto, "fuente": fuente, "creada_en": db.ahora(), "pedido_id": pedido_id}

    def agregar(extra):
        actuales = [p for p in extra.get("pruebas") or [] if isinstance(p, dict)]
        if len(actuales) >= MAX_PRUEBAS_PRODUCTO:
            raise ErrorPrueba(f"Este producto ya tiene {MAX_PRUEBAS_PRODUCTO} pruebas: borra alguna antes.")
        extra["pruebas"] = actuales + [nueva]
        return extra
    if tiendas.modificar_extra_interno(cliente, producto_id, agregar) is None:
        raise ErrorPrueba("No encontré ese producto.")
    return nueva


def borrar_prueba(cliente, producto_id, prueba_id):
    """True si el producto existe (la prueba se borra si estaba)."""
    def borrar(extra):
        restantes = [p for p in extra.get("pruebas") or [] if isinstance(p, dict) and p.get("id") != prueba_id]
        if restantes:
            extra["pruebas"] = restantes
        else:
            extra.pop("pruebas", None)
        return extra
    return tiendas.modificar_extra_interno(cliente, producto_id, borrar) is not None

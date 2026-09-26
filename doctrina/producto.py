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


# --------------------------------------------------------------- pedidos ---

ESTADOS_PEDIDO = ("abierto", "respondido", "descartado")
MAX_PEDIDOS = 5


def pedidos(fila, estado=None):
    """Los pedidos guardados de una fila `producto`; con `estado`, solo esos."""
    lista = ((fila or {}).get("extra") or {}).get("pedidos") or []
    return [p for p in lista if isinstance(p, dict) and p.get("texto") and (estado is None or p.get("estado") == estado)]


def reemplazar_abiertos(cliente, producto_id, nuevos):
    """Deja los pedidos `respondido`/`descartado` como estaban y reemplaza los
    abiertos por `nuevos` ([{texto, para_que}], máximo MAX_PEDIDOS). Devuelve
    la lista escrita, o None si el producto no existe."""
    ahora = db.ahora()
    frescos = [{"id": uuid4().hex[:8], "texto": _texto(n.get("texto")), "para_que": _texto(n.get("para_que")),
                "estado": "abierto", "creado_en": ahora, "respondido_en": None}
               for n in (nuevos or [])[:MAX_PEDIDOS] if _texto(n.get("texto"))]

    def reemplazar(extra):
        cerrados = [p for p in extra.get("pedidos") or [] if isinstance(p, dict) and p.get("estado") != "abierto"]
        extra["pedidos"] = cerrados + frescos
        return extra
    escrito = tiendas.modificar_extra_interno(cliente, producto_id, reemplazar)
    return None if escrito is None else escrito["pedidos"]


def _cerrar(cliente, producto_id, pedido_id, estado):
    encontrado = {}

    def cerrar(extra):
        lista = []
        for p in extra.get("pedidos") or []:
            if isinstance(p, dict) and p.get("id") == pedido_id and p.get("estado") == "abierto":
                p = dict(p, estado=estado, respondido_en=db.ahora())
                encontrado["ok"] = True
            lista.append(p)
        extra["pedidos"] = lista
        return extra
    tiendas.modificar_extra_interno(cliente, producto_id, cerrar)
    return bool(encontrado)


def responder(cliente, producto_id, pedido_id, texto, fuente):
    """La respuesta a un pedido abierto queda como prueba del producto y el
    pedido se cierra como `respondido`. ErrorPrueba si el pedido no está
    abierto o la prueba no se puede guardar."""
    fila = tiendas.producto(cliente, producto_id)
    if not any(p.get("id") == pedido_id for p in pedidos(fila, "abierto")):
        raise ErrorPrueba("Ese pedido ya no está abierto.")
    prueba = agregar_prueba(cliente, producto_id, texto, fuente, pedido_id=pedido_id)
    _cerrar(cliente, producto_id, pedido_id, "respondido")
    return prueba


def descartar(cliente, producto_id, pedido_id):
    """«No aplica»: True si había un pedido abierto con ese id."""
    return _cerrar(cliente, producto_id, pedido_id, "descartado")

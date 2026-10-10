"""Desgloses de una cuenta de Meta dentro de su copia (spec E2 §5): cómo rinde por edad y género, por ubicación, por
país y por dispositivo, en los últimos 7 y 30 días. Son 8 consultas por cuenta (2 ventanas × 4 dimensiones) y
`sync.sincronizar` las hace como mucho una vez cada 20 horas: el límite de uso de Meta es de TODOS los proyectos que
comparten usuario y app, y 8 al día por cuenta es el presupuesto.

Leer no cobra. Un límite de uso de Meta (`ErrorGraph.limite`) sube tal cual para que la tarea ponga la pausa
compartida; cualquier otro fallo de UNA combinación se anota con el nombre del error (su texto puede traer la URL con
el token) y se sigue con la siguiente, sin tocar lo que esa combinación ya tenía guardado."""
import logging

from meta_rendimiento import datos, graph

log = logging.getLogger("creatv.meta_rendimiento.desgloses")

# dimensión -> los `breakdowns` que se piden a Meta, en el orden en que se unen para formar la clave.
DIMENSIONES = {"edad_genero": "age,gender", "ubicacion": "publisher_platform,platform_position",
               "pais": "country", "dispositivo": "impression_device"}
VENTANAS = (7, 30)
CAMPOS = "spend,impressions,clicks,outbound_clicks,inline_link_clicks,actions,action_values"
LIMITE_PAGINA = 500   # un país por fila: hay a lo sumo unos 200, y el resto de las dimensiones son decenas
SIN_VALOR = "unknown"   # como Meta llama al segmento que no sabe clasificar; también lo que falta en una fila


def fila(f, dimension):
    """Una fila de insights de Meta con breakdowns -> fila de `datos.reemplazar_desgloses`: `clave` (los valores
    del desglose unidos con «|», en el orden de la dimensión; «unknown» para el que falte) y las métricas igual que
    la cuenta por día (`sync.fila_cuenta`: compras = el primer tipo presente de `graph.TIPOS_COMPRA`). Una fila sin
    NINGÚN valor del desglose no es un segmento: su clave es None y `datos` la ignora."""
    from meta_rendimiento import sync   # tardío: sync importa este módulo
    valores = [str(f.get(b) or "").strip() for b in DIMENSIONES[dimension].split(",")]
    clave = "|".join(v or SIN_VALOR for v in valores) if any(valores) else None
    base = sync.fila_cuenta(f)
    return {"clave": clave, **{m: base[m] for m in datos.METRICAS_DESGLOSE}}


def copiar(cliente, act, token):
    """Pide a Meta los 8 desgloses de la cuenta `act` y reemplaza cada uno en la base. Devuelve cuántas filas escribió.
    Un `ErrorGraph` de límite sube; cualquier otro error de una combinación se anota y sigue con la siguiente (esa
    combinación conserva lo que tenía hasta la próxima copia diaria)."""
    n = 0
    for ventana in VENTANAS:
        for dimension, breakdowns in DIMENSIONES.items():
            try:
                filas = graph.paginar(f"{act}/insights", token, {
                    "level": "account", "date_preset": f"last_{ventana}d", "breakdowns": breakdowns,
                    "fields": CAMPOS, "limit": LIMITE_PAGINA})
                n += datos.reemplazar_desgloses(cliente, act, ventana, dimension,
                                                [fila(f, dimension) for f in filas])
            except Exception as e:  # noqa: BLE001 — una combinación que falla no tumba las demás ni la copia
                if isinstance(e, graph.ErrorGraph) and e.limite:
                    raise
                log.warning("meta desgloses %s: %s de %s días saltado (%s)", act, dimension, ventana,
                            type(e).__name__)
    return n

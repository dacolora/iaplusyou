"""
Tareas del worker de la doctrina de venta (bloques 2 y 3).

  producto_pedidos -> f"{cliente}__producto{producto_id}__pedidos"  (max_intentos=1, pagada)
  pieza_revisar    -> f"{cliente}__{cf_id}__revisar"                 (max_intentos=1, pagada)

«Actualizar lo que Claude necesita» en Catálogo: junta los faltantes de las
piezas de un producto y le pide a Claude máximo cinco pedidos concretos para
el cliente (`doctrina.pedidos.resumir`). Una llamada pagada: el precio va en
el botón, nunca se reintenta sola y el gasto real queda como tipo «pedidos»,
también si la respuesta no sirvió.

«Revisar con la doctrina» en Crear (bloque 3): Claude con visión contesta los
12 puntos de `textos/revisar.md` sobre la pieza terminada
(`doctrina.revisor.revisar`). Mismas reglas de pago; gasto tipo «revision».
"""
import gastos
import trabajos
from doctrina import pedidos, revisor
from nicho.avatares import costo_real, modelo_actual
from tareas import ref_sufijo, registrar

TIPO_PEDIDOS = "producto_pedidos"
TIPO_REVISAR = "pieza_revisar"


def job_id_pedidos(cliente, producto_id):
    return f"{cliente}__producto{producto_id}__pedidos"


def encolar_pedidos(cliente, producto_id):
    return trabajos.encolar(job_id_pedidos(cliente, producto_id), TIPO_PEDIDOS,
                            {"cliente": cliente, "producto_id": producto_id},
                            cliente=cliente, duracion_estimada=40, max_intentos=1)


def _gasto(cliente, referencia, ent, sal, detalle, tipo="pedidos"):
    if ent or sal:
        gastos.registrar_seguro(cliente, tipo, costo_real(ent, sal), referencia, proveedor="anthropic",
                                detalle=detalle, extra={"tokens_entrada": ent, "tokens_salida": sal,
                                                        "modelo": modelo_actual()})


@registrar(TIPO_PEDIDOS)
def ejecutar_pedidos(tarea):
    p = tarea["payload"]
    cliente, producto_id = p["cliente"], int(p["producto_id"])
    referencia = f"producto:pedidos:{producto_id}{ref_sufijo(tarea)}"
    try:
        n, ent, sal = pedidos.resumir(cliente, producto_id)
    except pedidos.ErrorPedidos as e:
        _gasto(cliente, referencia, getattr(e, "tokens_entrada", 0) or 0, getattr(e, "tokens_salida", 0) or 0,
               "pedidos al cliente · respuesta inválida")
        raise
    _gasto(cliente, referencia, ent, sal, "pedidos al cliente")
    return f"{n} pedido(s) listos para el cliente." if n else "Claude no ha pedido nada para este producto."


def job_id_revisar(cliente, cf_id):
    return f"{cliente}__{cf_id}__revisar"


def encolar_revisar(cliente, cf_id):
    return trabajos.encolar(job_id_revisar(cliente, cf_id), TIPO_REVISAR, {"cliente": cliente, "cf_id": cf_id},
                            cliente=cliente, duracion_estimada=60, max_intentos=1)


@registrar(TIPO_REVISAR)
def ejecutar_revisar(tarea):
    p = tarea["payload"]
    cliente, cf_id = p["cliente"], p["cf_id"]
    referencia = f"revision:{cf_id}{ref_sufijo(tarea)}"
    try:
        rev, ent, sal = revisor.revisar(cliente, cf_id)
    except revisor.ErrorRevision as e:
        _gasto(cliente, referencia, e.tokens_entrada, e.tokens_salida, "revisión de la doctrina · respuesta inválida",
               tipo="revision")
        raise
    _gasto(cliente, referencia, ent, sal, "revisión de la doctrina", tipo="revision")
    n = revisor.contar(rev)
    return f"Revisión lista: {n} punto(s) para mejorar." if n else "Revisión lista: la pieza pasa todo."

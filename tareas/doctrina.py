"""
Tareas del worker de la doctrina de venta (bloque 2).

  producto_pedidos -> f"{cliente}__producto{producto_id}__pedidos"  (max_intentos=1, pagada)

«Actualizar lo que Claude necesita» en Catálogo: junta los faltantes de las
piezas de un producto y le pide a Claude máximo cinco pedidos concretos para
el cliente (`doctrina.pedidos.resumir`). Una llamada pagada: el precio va en
el botón, nunca se reintenta sola y el gasto real queda como tipo «pedidos»,
también si la respuesta no sirvió.
"""
import gastos
import trabajos
from doctrina import pedidos
from nicho.avatares import costo_real, modelo_actual
from tareas import ref_sufijo, registrar

TIPO_PEDIDOS = "producto_pedidos"


def job_id_pedidos(cliente, producto_id):
    return f"{cliente}__producto{producto_id}__pedidos"


def encolar_pedidos(cliente, producto_id):
    return trabajos.encolar(job_id_pedidos(cliente, producto_id), TIPO_PEDIDOS,
                            {"cliente": cliente, "producto_id": producto_id},
                            cliente=cliente, duracion_estimada=40, max_intentos=1)


def _gasto(cliente, referencia, ent, sal, detalle):
    if ent or sal:
        gastos.registrar_seguro(cliente, "pedidos", costo_real(ent, sal), referencia, proveedor="anthropic",
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

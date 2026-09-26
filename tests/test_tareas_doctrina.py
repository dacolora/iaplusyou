"""Tarea `producto_pedidos` (doctrina, bloque 2, §5.3)."""
import pytest


def test_pedidos_registra_el_gasto_real_tambien_si_falla(base_temporal, monkeypatch):
    import gastos
    import tareas
    from doctrina import pedidos
    tareas.cargar_todas()
    from tareas import doctrina as td
    assert td.job_id_pedidos("acme", 4) == "acme__producto4__pedidos"
    monkeypatch.setattr(pedidos, "resumir", lambda cliente, pid: (3, 800, 1200))
    assert tareas.REGISTRO["producto_pedidos"]({"id": 9, "payload": {"cliente": "acme", "producto_id": 4}}).startswith("3 pedido")
    g = gastos.historial("acme", limite=1)[0]
    assert g["tipo"] == "pedidos" and g["referencia"] == "producto:pedidos:4:t9" and g["usd"] > 0

    def falla(cliente, pid):
        e = pedidos.ErrorPedidos("Claude no devolvió pedidos.")
        e.tokens_entrada, e.tokens_salida = 300, 20
        raise e
    monkeypatch.setattr(pedidos, "resumir", falla)
    with pytest.raises(pedidos.ErrorPedidos):
        tareas.REGISTRO["producto_pedidos"]({"id": 10, "payload": {"cliente": "acme", "producto_id": 4}})
    assert gastos.historial("acme", limite=1)[0]["referencia"] == "producto:pedidos:4:t10"

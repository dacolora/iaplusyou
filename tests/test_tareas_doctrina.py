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


def test_revisar_encola_una_vez_y_registra_el_gasto_real_tambien_si_falla(base_temporal, monkeypatch):
    """Doctrina, bloque 3: «Revisar con la doctrina» es pagada: una sola vez,
    gasto tipo «revision» con referencia por tarea, también si Claude no
    respondió algo usable."""
    import gastos
    import tareas
    import trabajos
    from doctrina import revisor
    tareas.cargar_todas()
    from tareas import doctrina as td
    assert td.job_id_revisar("acme", "cf_1") == "acme__cf_1__revisar"
    visto = {}
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **k: visto.update(job_id=job_id, tipo=tipo,
                                                                                            payload=payload, **k))
    td.encolar_revisar("acme", "cf_1")
    assert visto["tipo"] == "pieza_revisar" and visto["payload"] == {"cliente": "acme", "cf_id": "cf_1"}
    assert visto["max_intentos"] == 1 and visto["job_id"] == "acme__cf_1__revisar"
    rev = {"puntos": [{"n": 6, "estado": "mejorar", "detalle": "x"}], "reglas": []}
    monkeypatch.setattr(revisor, "revisar", lambda cliente, cf_id: (rev, 3000, 900))
    assert tareas.REGISTRO["pieza_revisar"]({"id": 5, "payload": {"cliente": "acme", "cf_id": "cf_1"}}) == \
        "Revisión lista: 1 punto(s) para mejorar."
    g = gastos.historial("acme", limite=1)[0]
    assert g["tipo"] == "revision" and g["referencia"] == "revision:cf_1:t5" and g["usd"] > 0

    def falla(cliente, cf_id):
        raise revisor.ErrorRevision("Claude no devolvió JSON.", 2000, 300)
    monkeypatch.setattr(revisor, "revisar", falla)
    with pytest.raises(revisor.ErrorRevision):
        tareas.REGISTRO["pieza_revisar"]({"id": 6, "payload": {"cliente": "acme", "cf_id": "cf_1"}})
    g = gastos.historial("acme", limite=1)[0]
    assert g["referencia"] == "revision:cf_1:t6" and "respuesta inválida" in g["detalle"]

    def sin_llamar(cliente, cf_id):
        raise revisor.ErrorRevision("No se pudo sacar ningún fotograma del video.")
    monkeypatch.setattr(revisor, "revisar", sin_llamar)
    with pytest.raises(revisor.ErrorRevision):
        tareas.REGISTRO["pieza_revisar"]({"id": 7, "payload": {"cliente": "acme", "cf_id": "cf_1"}})
    assert gastos.historial("acme", limite=1)[0]["referencia"] == "revision:cf_1:t6"   # sin tokens, sin gasto


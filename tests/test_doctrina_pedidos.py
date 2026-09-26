"""«Lo que Claude necesita» (doctrina, bloque 2, §5.2–5.3)."""
import json

import pytest


def _producto_con_piezas(monkeypatch):
    """Un producto (activo `espejo_led`) con una idea de sprint y dos sesiones
    de Crear (una lo nombra por id, otra por nombre) y una sesión ajena."""
    import catalogo_productos
    import creative_flow
    import tiendas
    from sprints import datos
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None:
                        {"id": "espejo_led", "nombre": "Espejo LED"} if pid == "espejo_led" else None)
    fila = tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED", "redondo")
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    datos.crear_idea("acme", cid, "video", "Idea", "escena", extra={"angulo": {"faltantes": [
        "error: cifra_no_verificada:47", "faltan comentarios reales sobre la luz",
        "arranque fuera de lo recomendado: x", "nivel de consciencia confirmado por investigación"]}})
    a = creative_flow.crear("acme", [], ["espejo_led"], [], "x", 8, "", "A")
    b = creative_flow.crear("acme", [], ["Espejo LED"], [], "x", 8, "", "A")
    otro = creative_flow.crear("acme", [], ["Otra cosa"], [], "x", 8, "", "A")
    creative_flow.actualizar("acme", a, angulo={"faltantes": ["faltan comentarios reales sobre la luz", "precio"]})
    creative_flow.actualizar("acme", b, angulo={"faltantes": ["garantía del producto"]})
    creative_flow.actualizar("acme", otro, angulo={"faltantes": ["no es de este producto"]})
    return fila


def test_faltantes_del_producto_junta_ideas_y_sesiones_sin_ruido(base_temporal, monkeypatch):
    import tiendas
    from doctrina import pedidos
    fila = _producto_con_piezas(monkeypatch)
    faltantes = pedidos.faltantes_del_producto("acme", tiendas.producto("acme", fila))
    assert faltantes == ["faltan comentarios reales sobre la luz", "precio", "garantía del producto"]


def test_resumir_escribe_los_pedidos_y_cuida_lo_ya_cerrado(base_temporal, monkeypatch):
    import tiendas
    from doctrina import pedidos, producto as dp
    fila = _producto_con_piezas(monkeypatch)
    dp.agregar_prueba("acme", fila, "Luz regulable en 3 tonos", "ficha")
    viejo = dp.reemplazar_abiertos("acme", fila, [{"texto": "Dinos la garantía", "para_que": "x"}])[0]
    dp.descartar("acme", fila, viejo["id"])
    vistos = []

    def falso(mensaje, system):
        vistos.append((mensaje, system))
        return json.dumps({"pedidos": [{"texto": "Pega un comentario real sobre la luz", "para_que": "prueba"}]}), 700, 900
    monkeypatch.setattr(pedidos, "_llamar", falso)
    assert pedidos.resumir("acme", fila) == (1, 700, 900)
    mensaje, system = vistos[0]
    assert "Luz regulable en 3 tonos" in mensaje and "Dinos la garantía" in mensaje and "garantía del producto" in mensaje
    assert "DOCTRINA DE VENTA" in system[0]["text"] and "máximo 5 pedidos" in system[1]["text"]
    estados = [(p["texto"], p["estado"]) for p in dp.pedidos(tiendas.producto("acme", fila))]
    assert estados == [("Dinos la garantía", "descartado"), ("Pega un comentario real sobre la luz", "abierto")]


def test_resumir_con_respuesta_invalida_no_toca_nada_y_trae_los_tokens(base_temporal, monkeypatch):
    import tiendas
    from doctrina import pedidos, producto as dp
    fila = _producto_con_piezas(monkeypatch)
    dp.reemplazar_abiertos("acme", fila, [{"texto": "Viejo", "para_que": "x"}])
    monkeypatch.setattr(pedidos, "_llamar", lambda mensaje, system: ("sin json", 300, 20))
    with pytest.raises(pedidos.ErrorPedidos) as e:
        pedidos.resumir("acme", fila)
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (300, 20)
    assert [p["texto"] for p in dp.pedidos(tiendas.producto("acme", fila))] == ["Viejo"]


def test_resumir_sin_faltantes_no_llama_a_claude(base_temporal, monkeypatch):
    import tiendas
    from doctrina import pedidos
    fila = tiendas.asegurar_manual("acme", "solo", "Solo")
    monkeypatch.setattr(pedidos, "_llamar", lambda *a: pytest.fail("no debía llamar"))
    assert pedidos.resumir("acme", fila) == (0, 0, 0)

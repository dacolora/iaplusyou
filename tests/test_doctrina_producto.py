"""Pruebas del producto (doctrina, bloque 2, §5)."""
import pytest


def _fila():
    import tiendas
    return tiendas.upsert_producto("acme", "shopify", "a", {"nombre": "Pantufla", "extra": {"handle": "a"}})


def test_agregar_listar_y_borrar_pruebas(base_temporal):
    import tiendas
    from doctrina import producto as dp
    pid = _fila()
    p = dp.agregar_prueba("acme", pid, "  El 95 %   repite la compra ", "comentarios")
    assert p["texto"] == "El 95 % repite la compra" and p["fuente"] == "comentarios" and len(p["id"]) == 8
    fila = tiendas.producto("acme", pid)
    assert [x["texto"] for x in dp.pruebas(fila)] == ["El 95 % repite la compra"]
    assert fila["extra"]["handle"] == "a"                                  # lo de la tienda no se toca
    assert dp.pruebas_texto(dp.pruebas(fila)) == "- El 95 % repite la compra (comentario real de un comprador)"
    assert dp.borrar_prueba("acme", pid, p["id"]) is True
    assert "pruebas" not in tiendas.producto("acme", pid)["extra"]
    assert dp.borrar_prueba("acme", 999, "x") is False


def test_agregar_prueba_valida_y_tiene_tope(base_temporal):
    from doctrina import producto as dp
    pid = _fila()
    with pytest.raises(dp.ErrorPrueba):
        dp.agregar_prueba("acme", pid, "   ", "ficha")
    with pytest.raises(dp.ErrorPrueba):
        dp.agregar_prueba("acme", pid, "algo", "demostracion")      # eso es del video, no del producto
    with pytest.raises(dp.ErrorPrueba):
        dp.agregar_prueba("acme", 999, "algo", "ficha")
    for n in range(dp.MAX_PRUEBAS_PRODUCTO):
        dp.agregar_prueba("acme", pid, f"dato {n}", "ficha")
    with pytest.raises(dp.ErrorPrueba):
        dp.agregar_prueba("acme", pid, "uno más", "ficha")
    assert dp.pruebas_texto([]) == ""


def test_pedidos_reemplazar_responder_y_descartar(base_temporal):
    import tiendas
    from doctrina import producto as dp
    pid = _fila()
    escritos = dp.reemplazar_abiertos("acme", pid, [{"texto": "Pega un comentario real", "para_que": "prueba"},
                                                    {"texto": "  ", "para_que": "vacío no entra"},
                                                    {"texto": "Dinos cuánto dura", "para_que": "cifra"}])
    assert [p["texto"] for p in escritos] == ["Pega un comentario real", "Dinos cuánto dura"]
    k1, k2 = escritos[0]["id"], escritos[1]["id"]
    prueba = dp.responder("acme", pid, k1, "Me encantan, son muy calientitas", "comentarios")
    assert prueba["pedido_id"] == k1
    assert dp.descartar("acme", pid, k2) is True and dp.descartar("acme", pid, k2) is False
    fila = tiendas.producto("acme", pid)
    assert [p["estado"] for p in dp.pedidos(fila)] == ["respondido", "descartado"]
    with pytest.raises(dp.ErrorPrueba):
        dp.responder("acme", pid, k1, "otra vez", "ficha")             # ya no está abierto
    # una actualización nueva conserva los cerrados y reemplaza solo los abiertos
    dp.reemplazar_abiertos("acme", pid, [{"texto": "Nuevo", "para_que": "x"}])
    assert [p["estado"] for p in dp.pedidos(tiendas.producto("acme", pid))] == ["respondido", "descartado", "abierto"]
    assert dp.reemplazar_abiertos("acme", 999, []) is None

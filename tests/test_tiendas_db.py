import pytest


@pytest.fixture(autouse=True)
def clave(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")


def test_conectar_listar_credenciales_desconectar(base_temporal):
    import tiendas
    tid = tiendas.conectar("acme", "shopify", {"token": "shpat_1", "dominio": "acme.myshopify.com"}, nombre="Acme", dominio="acme.myshopify.com")
    lista = tiendas.listar("acme")
    assert len(lista) == 1 and lista[0]["tipo"] == "shopify" and lista[0]["estado"] == "conectada" and "credenciales" not in lista[0]
    assert tiendas.credenciales("acme", tid)["token"] == "shpat_1"
    assert tiendas.credenciales("otro", tid) is None
    tid2 = tiendas.conectar("acme", "shopify", {"token": "shpat_2"})   # reemplaza
    assert tid2 == tid and tiendas.credenciales("acme", tid)["token"] == "shpat_2"
    tiendas.actualizar("acme", tid, estado="rota", error="401")
    assert tiendas.obtener("acme", tid)["error"] == "401"
    tiendas.upsert_producto("acme", "shopify", "p1", {"nombre": "Cojín", "precio": 10, "moneda": "USD", "url_compra": "https://a/p1", "fotos": []})
    assert tiendas.desconectar("acme", tid) is True
    assert tiendas.listar("acme") == []
    assert tiendas.productos("acme") == [] and tiendas.productos("acme", incluir_archivados=True)[0]["archivado"] is True


def test_upsert_producto_conserva_marcas(base_temporal):
    import tiendas
    pid = tiendas.upsert_producto("acme", "csv", "sku-1", {"nombre": "Cojín", "descripcion": "suave", "precio": 89900, "moneda": "COP", "url_compra": "https://t/p", "fotos": ["https://i/1.jpg"], "categoria": "hogar"})
    tiendas.marcar_producto("acme", pid, en_prueba=True, prioridad=5, activo_catalogo_id="cojin")
    assert tiendas.upsert_producto("acme", "csv", "sku-1", {"nombre": "Cojín XL", "precio": 99900, "moneda": "COP"}) == pid
    p = tiendas.producto("acme", pid)
    assert p["nombre"] == "Cojín XL" and p["precio"] == 99900 and p["en_prueba"] is True and p["prioridad"] == 5
    assert p["activo_catalogo_id"] == "cojin" and p["fotos"] == ["https://i/1.jpg"] and p["archivado"] is False
    assert tiendas.producto("otro", pid) is None
    tiendas.upsert_producto("acme", "csv", "sku-2", {"nombre": "Otro", "precio": 1, "moneda": "COP"})
    assert tiendas.archivar_faltantes("acme", "csv", {"sku-1"}) == 1
    assert [x["fuente_id"] for x in tiendas.productos("acme")] == ["sku-1"]
    tiendas.upsert_producto("acme", "csv", "sku-2", {"nombre": "Otro", "precio": 1, "moneda": "COP"})
    assert [x["fuente_id"] for x in tiendas.productos("acme")] == ["sku-1", "sku-2"]   # reaparece → desarchiva


def test_pedidos(base_temporal):
    import tiendas
    tid = tiendas.conectar("acme", "woo", {"ck": "a", "cs": "b"})
    n = tiendas.guardar_pedidos("acme", tid, [
        {"fuente_id": "1001", "fecha": "2026-09-16T10:00:00", "total": 50.0, "moneda": "USD", "items": [{"sku": "x", "cantidad": 1}], "utm_content": "42"},
        {"fuente_id": "1002", "fecha": "2026-09-16T11:00:00", "total": 20.0, "moneda": "USD", "items": [], "utm_content": None},
    ])
    assert n == 2
    assert tiendas.guardar_pedidos("acme", tid, [{"fuente_id": "1001", "fecha": "2026-09-16T10:00:00", "total": 55.0, "moneda": "USD", "items": [], "utm_content": "42"}]) == 0
    sin = tiendas.pedidos_sin_resolver("acme")
    assert [p["fuente_id"] for p in sin] == ["1001"] and sin[0]["total"] == 55.0
    tiendas.resolver_pedido("acme", sin[0]["id"], 7)
    assert tiendas.pedidos_sin_resolver("acme") == []
    assert tiendas.ventas_por_pieza("acme", 7, "2026-09-16T00:00:00") == {"compras": 1, "ingresos": 55.0}
    assert tiendas.ventas_por_pieza("acme", 7, "2026-09-17T00:00:00") == {"compras": 0, "ingresos": 0.0}

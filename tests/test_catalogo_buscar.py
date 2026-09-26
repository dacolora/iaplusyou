def test_encontrar_por_id_o_nombre(monkeypatch):
    import catalogo_productos as cp
    productos = [{"id": "espejo_led", "nombre": "Espejo LED"}]
    monkeypatch.setattr(cp, "encontrar", lambda c, pid, categoria=None: next((p for p in productos if p["id"] == pid), None))
    monkeypatch.setattr(cp, "listar", lambda c, categoria="producto": productos)
    assert cp.encontrar_por_id_o_nombre("acme", "espejo_led")["nombre"] == "Espejo LED"
    assert cp.encontrar_por_id_o_nombre("acme", "Espejo LED")["id"] == "espejo_led"
    assert cp.encontrar_por_id_o_nombre("acme", "Otro") is None
    assert cp.encontrar_por_id_o_nombre("acme", "") is None

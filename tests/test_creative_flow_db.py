def test_crear_actualizar_cargar_eliminar(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], ["Chancla Rose"], [], "la persona camina", 10, "", "A",
                   referencias_urls=["https://x/1.png"], platforms=[])
    assert cid.startswith("cf_")
    data = cf.cargar("acme")
    e = data[cid]
    assert e["accion_central"] == "la persona camina" and e["estado"] == "prompt_pendiente"
    assert e["referencias_urls"] == ["https://x/1.png"] and e["productos_ids"] == ["Chancla Rose"]
    assert e["duracion_objetivo"] == 10 and e["video_url"] is None and e["creado_en"]

    assert cf.actualizar("acme", cid, estado="video_listo", video_url="https://r2/v.mp4", usd=1.2,
                         prompt_relleno="PROMPT", tipo="video", modelo="wan3", enfoque="producto",
                         enfoque_nombre="Solo producto", con_persona=False, aspect_ratio="9:16",
                         referencias=[{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}])
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["video_url"] == "https://r2/v.mp4" and e["usd"] == 1.2
    assert e["prompt_relleno"] == "PROMPT" and e["modelo"] == "wan3" and e["enfoque_nombre"] == "Solo producto"
    assert e["referencias"][0]["etiqueta"] == "@Imagen 1" and e["aspect_ratio"] == "9:16"

    assert cf.eliminar("acme", cid) is True
    assert cid not in cf.cargar("acme")
    assert cf.actualizar("acme", cid, estado="x") is False


def test_cargar_ordena_por_creado_y_aisla_clientes(base_temporal):
    import creative_flow as cf
    a = cf.crear("acme", [], [], [], "uno", 5, "", "A")
    b = cf.crear("acme", [], [], [], "dos", 5, "", "A")
    cf.crear("otro", [], [], [], "ajeno", 5, "", "A")
    data = cf.cargar("acme")
    assert list(data.keys()) == [a, b] and "ajeno" not in [v["accion_central"] for v in data.values()]


def test_guardar_dict_completo(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "uno", 5, "", "A")
    data = cf.cargar("acme")
    data[cid]["estado"] = "error"; data[cid]["error"] = "boom"
    cf.guardar("acme", data)
    assert cf.cargar("acme")[cid]["error"] == "boom"


def test_campos_extra_redondean(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "uno", 5, "", "A")
    cf.actualizar("acme", cid, con_persona=True, enfoque_nombre="Con persona", credits=3,
                 platforms=["youtube", "tiktok"], productos_ids=["P1", "P2"])
    e = cf.cargar("acme")[cid]
    assert e["con_persona"] is True
    assert e["enfoque_nombre"] == "Con persona"
    assert e["credits"] == 3
    assert e["platforms"] == ["youtube", "tiktok"]
    assert e["productos_ids"] == ["P1", "P2"]

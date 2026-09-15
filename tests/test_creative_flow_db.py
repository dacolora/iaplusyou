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

    assert cf.actualizar("acme", cid, tipo="imagen")
    e = cf.cargar("acme")[cid]
    assert e["tipo"] == "imagen"

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
    e = cf.cargar("acme")[cid]
    assert e["error"] == "boom"
    assert e["estado"] == "error"


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


def test_actualizar_y_eliminar_ignoran_piezas_final(base_temporal):
    import creative_flow as cf
    import db

    cid = cf.crear("acme", [], [], [], "uno", 5, "", "A")
    ahora = db.ahora()
    with db.conectar() as con:
        concepto_id = con.execute(
            db.concepto.select().where(db.concepto.c.legado_id == cid)
        ).first().id
        con.execute(db.pieza.insert().values(
            cliente="acme", creado_en=ahora, actualizado_en=ahora,
            concepto_id=concepto_id, tipo="final", estado="pendiente"))

    assert cf.actualizar("acme", cid, video_url="https://r2/v.mp4")

    with db.conectar() as con:
        piezas = con.execute(
            db.pieza.select().where(db.pieza.c.concepto_id == concepto_id)
        ).fetchall()
    final = next(p for p in piezas if p.tipo == "final")
    legado = next(p for p in piezas if p.tipo != "final")
    assert final.url_video is None
    assert legado.url_video == "https://r2/v.mp4"

    assert cf.eliminar("acme", cid) is True
    with db.conectar() as con:
        piezas = con.execute(
            db.pieza.select().where(db.pieza.c.concepto_id == concepto_id)
        ).fetchall()
    assert len(piezas) == 1 and piezas[0].tipo == "final"
    assert cid not in cf.cargar("acme")


def test_crear_con_legado_id_y_creado_en(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "uno", 5, "", "A",
                   legado_id="cf_x", creado_en="2026-01-02T03:04:05.123456")
    assert cid == "cf_x"
    data = cf.cargar("acme")
    assert "cf_x" in data
    assert data["cf_x"]["creado_en"] == "2026-01-02T03:04:05"


def test_piezas_finales(base_temporal):
    import pytest
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "uno", 8, "", "A")
    fid = cf.crear_final("acme", cid, "es", "CO")
    assert fid == f"{cid}__es_CO"
    assert cf.finales("acme", cid)[0]["estado"] == "generando"
    assert cf.actualizar_final("acme", fid, estado="listo", url_video="https://r2/f.mp4",
                               capas={"voz": {"estado": "ok"}}, costo_usd=0.5)
    f = cf.final_por_legado("acme", fid)
    assert f["estado"] == "listo" and f["video_url"] == "https://r2/f.mp4" and f["capas"]["voz"]["estado"] == "ok"
    # volver a crear la misma final la reinicia (misma fila, resultado limpio)
    assert cf.crear_final("acme", cid, "es", "CO") == fid
    assert len(cf.finales("acme", cid)) == 1 and cf.finales("acme", cid)[0]["video_url"] is None
    # Crear no la ve como sesión
    assert fid not in cf.cargar("acme") and cid in cf.cargar("acme")
    with pytest.raises(ValueError):
        cf.actualizar_final("acme", fid, otra_cosa=1)
    assert cf.actualizar_final("acme", "no_existe", estado="x") is False
    assert cf.finales("acme", "no_existe") == []
    with pytest.raises(ValueError):
        cf.crear_final("acme", "no_existe", "es", "CO")
    # borrar la sesión borra también sus finales (FK padre_pieza_id)
    assert cf.eliminar("acme", cid) is True
    assert cf.final_por_legado("acme", fid) is None
    assert cf.eliminar_final("acme", fid) is False

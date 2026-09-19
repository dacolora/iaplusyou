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
    # volver a crear la misma final la reinicia a "generando" (misma fila),
    # pero NO borra el video/miniatura anteriores (I4): la cuadrícula sigue
    # mostrando la final anterior hasta que la nueva termine (bien o mal).
    assert cf.crear_final("acme", cid, "es", "CO") == fid
    finales = cf.finales("acme", cid)
    assert len(finales) == 1
    assert finales[0]["estado"] == "generando"
    assert finales[0]["video_url"] == "https://r2/f.mp4"  # conservado, no nulled
    assert finales[0]["error"] is None and finales[0]["capas"] == {} and finales[0]["costo_usd"] is None
    # si el reintento falla, actualizar_final(estado="error") deja intacto el video anterior
    assert cf.actualizar_final("acme", fid, estado="error", error="fal caído")
    f_err = cf.final_por_legado("acme", fid)
    assert f_err["estado"] == "error" and f_err["video_url"] == "https://r2/f.mp4"
    # si el reintento tiene éxito, actualizar_final SÍ sobrescribe con lo nuevo
    assert cf.actualizar_final("acme", fid, estado="listo", url_video="https://r2/nueva.mp4")
    assert cf.final_por_legado("acme", fid)["video_url"] == "https://r2/nueva.mp4"
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


def test_crear_guarda_extra_sprint(base_temporal):
    import creative_flow as cf
    cf_id = cf.crear("acme", [], ["P"], [], "acción", 8, "", "A", extra_sprint={"sprint_id": 1, "campana_id": 2, "cp_id": 3})
    e = cf.cargar("acme")[cf_id]
    assert e["sprint"] == {"sprint_id": 1, "campana_id": 2, "cp_id": 3}
    otro = cf.crear("acme", [], ["P"], [], "acción", 8, "", "A")
    assert "sprint" not in cf.cargar("acme")[otro]
    copia = cf.duplicar("acme", cf_id)
    assert cf.cargar("acme")[copia]["sprint"]["cp_id"] == 3    # la regeneración conserva el vínculo


def test_duplicar_rearma_el_prompt_con_sonido_solo_para_videos(base_temporal, monkeypatch):
    """Al cambiar el enfoque, la copia vuelve a armar el prompt como Crear:
    un video pide el sonido de la escena; una imagen no lleva línea SONIDO."""
    import creative_flow as cf
    import marca as marca_mod
    monkeypatch.setattr(marca_mod, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(marca_mod, "negative_prompt_efectivo", lambda c: None)
    refs = [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}]
    vid = cf.crear("acme", [], ["P"], [], "gira despacio", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", vid, prompt_relleno="viejo", referencias=refs, enfoque="producto", tipo="video")
    img = cf.crear("acme", [], ["P"], [], "gira despacio", 0, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", img, prompt_relleno="viejo", referencias=refs, enfoque="producto", tipo="imagen")
    copia_v = cf.duplicar("acme", vid, enfoque="unboxing")
    copia_i = cf.duplicar("acme", img, enfoque="unboxing")
    todo = cf.cargar("acme")
    assert "SONIDO: ambiente natural de la escena." in todo[copia_v]["prompt_relleno"]
    assert "SONIDO" not in todo[copia_i]["prompt_relleno"] and "ESCENA: gira despacio" in todo[copia_i]["prompt_relleno"]


def test_duplicar_respeta_el_sonido_de_la_sesion_original(base_temporal, monkeypatch):
    """La copia rearma el prompt con el sonido que guardó la sesión (spec
    estudio S1, check «Sonido de la escena»): una sesión muda sigue muda y sin
    línea SONIDO aunque tenga texto guardado; una con sonido conserva su texto
    en la línea SONIDO. Los tres campos viajan tal cual a la copia."""
    import creative_flow as cf
    import marca as marca_mod
    monkeypatch.setattr(marca_mod, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(marca_mod, "negative_prompt_efectivo", lambda c: None)
    refs = [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}]
    muda = cf.crear("acme", [], ["P"], [], "gira despacio", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", muda, prompt_relleno="viejo", referencias=refs, enfoque="producto", tipo="video",
                  con_sonido=False, sonido_texto="risas", musica_estilo="")
    sonora = cf.crear("acme", [], ["P"], [], "gira despacio", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", sonora, prompt_relleno="viejo", referencias=refs, enfoque="producto", tipo="video",
                  con_sonido=True, sonido_texto="risas de niños", musica_estilo="calmado")
    copia_m = cf.duplicar("acme", muda, enfoque="unboxing")
    copia_s = cf.duplicar("acme", sonora, enfoque="unboxing")
    todo = cf.cargar("acme")
    assert todo[copia_m]["con_sonido"] is False and todo[copia_m]["sonido_texto"] == "risas"
    assert "SONIDO" not in todo[copia_m]["prompt_relleno"] and "ESCENA: gira despacio" in todo[copia_m]["prompt_relleno"]
    assert todo[copia_s]["con_sonido"] is True and todo[copia_s]["musica_estilo"] == "calmado"
    assert "SONIDO: risas de niños. Sin diálogo hablado ni música de fondo." in todo[copia_s]["prompt_relleno"]
    assert "ambiente natural" not in todo[copia_s]["prompt_relleno"]


def test_armar_prompt_sesion_toma_el_sonido_del_extra(base_temporal, monkeypatch):
    """Sin `con_sonido` explícito: manda `extra["con_sonido"]`; si la sesión es
    anterior a ese campo, el tipo (video sí, imagen no). El texto solo entra
    con sonido; un `con_sonido` explícito manda sobre el extra."""
    import creative_flow as cf
    import marca as marca_mod
    monkeypatch.setattr(marca_mod, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(marca_mod, "negative_prompt_efectivo", lambda c: None)
    base = {"accion_central": "gira", "referencias": []}
    assert "SONIDO" not in cf.armar_prompt_sesion("acme", {**base, "con_sonido": False, "sonido_texto": "risas"}, "producto")[0]
    p, _ = cf.armar_prompt_sesion("acme", {**base, "con_sonido": True, "sonido_texto": "risas"}, "producto")
    assert "SONIDO: risas. Sin diálogo hablado ni música de fondo." in p
    assert "SONIDO: ambiente natural de la escena." in cf.armar_prompt_sesion("acme", {**base, "con_sonido": True}, "producto")[0]
    assert "SONIDO: ambiente natural" in cf.armar_prompt_sesion("acme", {**base, "tipo": "video"}, "producto")[0]
    assert "SONIDO" not in cf.armar_prompt_sesion("acme", {**base, "tipo": "imagen"}, "producto")[0]
    assert "SONIDO" not in cf.armar_prompt_sesion("acme", {**base, "con_sonido": True, "sonido_texto": "risas"}, "producto", con_sonido=False)[0]


def test_capas_del_clon_y_duplicar_no_arrastra_lo_generado(base_temporal, monkeypatch):
    """`capas` es columna de la pieza (como en las finales) y sale en cargar();
    el video crudo vive en extra. Una copia empieza sin nada del video generado."""
    import creative_flow as cf
    import marca as marca_mod
    monkeypatch.setattr(marca_mod, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(marca_mod, "negative_prompt_efectivo", lambda c: None)
    cf_id = cf.crear("acme", [], ["P"], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    assert cf.cargar("acme")[cf_id]["capas"] == {}
    capas = {"sonido": {"proveedor": "wan3", "estado": "ok", "parametros": {"con_sonido": True, "sonido": ""}, "costo_usd": 0.0}}
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4", video_url_crudo="https://r2/v_crudo.mp4",
                  video_local_crudo="/tmp/v_crudo.mp4", capas=capas, sonido={"viejo": True}, prompt_relleno="P",
                  referencias=[], enfoque="producto", tipo="video")
    e = cf.cargar("acme")[cf_id]
    assert e["capas"] == capas and e["video_url_crudo"] == "https://r2/v_crudo.mp4" and e["video_local_crudo"] == "/tmp/v_crudo.mp4"
    nuevo_id = cf.duplicar("acme", cf_id)
    copia = cf.cargar("acme")[nuevo_id]
    assert copia["capas"] == {} and copia["video_url"] is None
    for k in ("video_url_crudo", "video_local_crudo", "sonido", "credits"):
        assert k not in copia, k


def test_duplicar_con_prompt_y_variante_b(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], ["P"], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="prompt_listo", tipo="video", modelo="wan3", prompt_relleno="A", con_sonido=True,
                  musica_estilo="calmado", calidad="borrador", director={"estado": "ok", "prompt_b": "B", "diferencia_b": "otro"})
    hijo = cf.duplicar("acme", cid, prompt_relleno="B", variante="B")
    e = cf.cargar("acme")[hijo]
    assert e["prompt_relleno"] == "B" and e["variante"] == "B" and e["derivado_de"] == cid and e["estado"] == "prompt_listo"
    assert e["musica_estilo"] == "calmado" and e["calidad"] == "borrador" and e["con_sonido"] is True
    assert "director" not in e     # los planos/B del padre no viajan al hijo

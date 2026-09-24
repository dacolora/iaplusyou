import pytest


def test_persona_crear_listar_editar_archivar(base_temporal):
    from sprints import datos
    pid = datos.crear_persona("acme", "Cliente Premium", resumen="Busca calidad", tono="cercano y experto",
                              senales_visuales=["cocina moderna", "luz natural"], palabras_clave=["premium"])
    p = datos.persona("acme", pid)
    assert p["nombre"] == "Cliente Premium" and p["senales_visuales"] == ["cocina moderna", "luz natural"]
    assert p["origen"] == "manual" and p["archivada"] is False
    assert datos.actualizar_persona("acme", pid, tono="directo") and datos.persona("acme", pid)["tono"] == "directo"
    assert datos.personas("otro") == []            # aislamiento por cliente
    assert datos.persona("otro", pid) is None
    datos.archivar_persona("acme", pid)
    assert datos.personas("acme") == [] and len(datos.personas("acme", incluir_archivadas=True)) == 1


def test_persona_valida_nombre_y_origen(base_temporal):
    from sprints import datos
    with pytest.raises(datos.ErrorDatos):
        datos.crear_persona("acme", "   ")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_persona("acme", "X", origen="magia")
    pid = datos.crear_persona("acme", "X")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_persona("acme", pid, nombre="")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_persona("acme", pid, cliente="otro")   # campo no editable


def test_temporada_valida_fechas(base_temporal):
    from sprints import datos
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos", tipo="comercial",
                                mood_visual={"paleta": ["#B3001B"]})
    t = datos.temporada("acme", tid)
    assert t["inicio"] == "2026-11-15" and t["mood_visual"] == {"paleta": ["#B3001B"]}
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "2026-12-31", "2026-11-15")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "ayer", "2026-11-15")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "2026-01-01", "2026-02-01", tipo="rara")
    assert [x["nombre"] for x in datos.temporadas("acme")] == ["Navidad"]
    datos.archivar_temporada("acme", tid)
    assert datos.temporadas("acme") == []


def _base(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", destinos=["es_CO"])
    return pid, tid, sid


def test_sprint_crear_y_validar(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    s = datos.sprint("acme", sid)
    assert s["estado"] == "planeando" and s["destinos"] == ["es_CO"] and s["campanas"] == []
    assert [e["tipo"] for e in s["eventos"]] == ["sprint_creado"]
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "", "2026-10-01", "2026-10-31")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "X", "2026-10-31", "2026-10-01")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "X", "2026-10-01", "2026-10-31", referencias_objetivo_defecto=0)
    assert datos.sprint("otro", sid) is None and datos.sprints("otro") == []


def test_campana_unicidad_y_cantidades(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 10, 25)
    c = datos.campana("acme", cid)
    assert c["persona_nombre"] == "Premium" and c["temporada_nombre"] == "Verano" and c["estado"] == "planeada"
    assert c["referencias_objetivo"] == 5 and c["referencias_total"] == 0 and c["sprint_id"] == sid
    with pytest.raises(datos.CampanaDuplicada) as e:
        datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    assert "campaña 1" in str(e.value)
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 0, 3, referencias_objetivo=8)
    assert datos.campana("acme", cid2)["orden"] == 1 and datos.campana("acme", cid2)["referencias_objetivo"] == 8
    assert datos.combinaciones("acme", sid) == {(pid, "espejo_led", tid), (pid, "espejo_led", tid2)}
    for malo in [dict(n_videos=0, n_imagenes=0), dict(n_videos=-1, n_imagenes=2), dict(n_videos="x", n_imagenes=1)]:
        with pytest.raises(datos.ErrorDatos):
            datos.agregar_campana("acme", sid, pid, "otro", tid, **malo)
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, 999, "otro", tid, 1, 1)        # persona ajena
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, pid, "", tid, 1, 1)           # sin producto
    assert [c["id"] for c in datos.campanas("acme", sid)] == [cid, cid2]
    assert datos.actualizar_campana("acme", cid, n_videos=12)
    assert datos.eliminar_campana("acme", cid2) and len(datos.campanas("acme", sid)) == 1
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert tipos[0] == "campana_eliminada" and "campana_agregada" in tipos


def test_sprints_lista_con_totales(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 10, 25)
    lista = datos.sprints("acme")
    assert len(lista) == 1 and lista[0]["piezas_planeadas"] == 35 and lista[0]["campanas_total"] == 1
    datos.archivar_sprint("acme", sid)
    assert datos.sprints("acme") == [] and len(datos.sprints("acme", incluir_archivados=True)) == 1


def test_referencias_borrador_y_lista(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", titulo="a.jpg",
                                  intencion=["paleta", "composicion"])
    r2 = datos.agregar_referencia("acme", cid, "video", "https://r2/b.mp4", frame_url="https://r2/b.frame.jpg",
                                  origen="link", descripcion="El movimiento de cámara lento")
    a, b = datos.referencia("acme", r1), datos.referencia("acme", r2)
    assert a["estado"] == "borrador" and b["estado"] == "lista" and a["sprint_id"] == sid
    assert a["analisis_estado"] == "pendiente" and a["intencion"] == ["paleta", "composicion"]
    c = datos.campana("acme", cid)
    assert c["referencias_total"] == 2 and c["referencias_listas"] == 1
    datos.actualizar_referencia("acme", r1, descripcion="Quiero esta paleta", intencion=["paleta", "otro"],
                                intencion_otro="textura del vidrio")
    assert datos.referencia("acme", r1)["estado"] == "lista"
    datos.actualizar_referencia("acme", r1, descripcion="   ")
    assert datos.referencia("acme", r1)["estado"] == "borrador"
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia("acme", cid, "audio", "https://x")
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia("acme", cid, "imagen", "https://x", intencion=["magia"])
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia("acme", cid, "imagen", "https://x", origen="marte")
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia("acme", 999, "imagen", "https://x")
    assert [r["id"] for r in datos.referencias("acme", cid)] == [r1, r2]
    assert datos.quitar_referencia("acme", r2) and len(datos.referencias("acme", cid)) == 1
    assert not datos.quitar_referencia("otro", r1)


def test_reutilizar_referencia_copia_con_analisis(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 1, 1)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz", intencion=["iluminacion"])
    datos.actualizar_referencia("acme", r1, analisis={"resumen": "x"}, analisis_estado="listo")
    r2 = datos.reutilizar_referencia("acme", r1, cid2)
    b = datos.referencia("acme", r2)
    assert b["campana_id"] == cid2 and b["origen"] == "reutilizada" and b["analisis"] == {"resumen": "x"}
    assert b["estado"] == "lista" and b["analisis_estado"] == "listo"
    with pytest.raises(datos.ErrorDatos):
        datos.reutilizar_referencia("acme", r1, cid)      # ya está en esa campaña


def test_actualizar_referencia_ignora_estado_directo(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg")
    datos.actualizar_referencia("acme", r1, estado="lista")
    assert datos.referencia("acme", r1)["estado"] == "borrador"   # estado se deriva, no se fija a mano


def test_reutilizar_referencia_sin_analisis_conserva_intencion_otro_y_estado(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 1, 1)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", intencion=["otro"])
    datos.actualizar_referencia("acme", r1, intencion_otro="textura", analisis_estado="error")
    r2 = datos.reutilizar_referencia("acme", r1, cid2)
    b = datos.referencia("acme", r2)
    assert b["intencion_otro"] == "textura" and b["analisis_estado"] == "error" and b["analisis"] is None


def test_agregar_referencia_biblioteca_crea_fila_lista(base_temporal, monkeypatch):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    import referentes.datos as referentes_datos
    monkeypatch.setattr(referentes_datos, "referente", lambda cliente_, rid: {
        "id": rid, "estado_imagen": "ok", "imagen_url": "https://cdn/ref.jpg", "titular": "Titular del anuncio",
        "firma": "Antes/después con el mismo encuadre", "familia": "ugc_testimonial", "etapa": "TOF",
        "consciencia": "unaware", "dolor": "no confía en la marca",
    })
    monkeypatch.setattr(referentes_datos, "familias", lambda cliente_: [
        {"nombre": "ugc_testimonial", "descripcion": "Testimonio grabado con el celular"},
    ])
    rid = datos.agregar_referencia_biblioteca("acme", cid, 42)
    r = datos.referencia("acme", rid)
    assert r["origen"] == "biblioteca"
    assert r["url"] == "https://cdn/ref.jpg" and r["frame_url"] == "https://cdn/ref.jpg"
    assert r["titulo"] == "Titular del anuncio"
    assert r["descripcion"] == "Antes/después con el mismo encuadre"
    assert r["intencion"] == ["formato"]
    assert r["estado"] == "lista"
    assert r["analisis_estado"] == "listo"
    assert r["analisis"]["familia"] == "ugc_testimonial"
    assert r["analisis"]["descripcion_familia"] == "Testimonio grabado con el celular"
    assert r["analisis"]["resumen"] == "Antes/después con el mismo encuadre"
    assert r["extra"]["referente_id"] == 42


def test_agregar_referencia_biblioteca_no_duplica(base_temporal, monkeypatch):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    import referentes.datos as referentes_datos
    monkeypatch.setattr(referentes_datos, "referente", lambda cliente_, rid: {
        "id": rid, "estado_imagen": "ok", "imagen_url": "https://cdn/ref.jpg", "titular": "T",
        "firma": "F", "familia": None, "etapa": "TOF", "consciencia": None, "dolor": None,
    })
    monkeypatch.setattr(referentes_datos, "familias", lambda cliente_: [])
    rid1 = datos.agregar_referencia_biblioteca("acme", cid, 42)
    rid2 = datos.agregar_referencia_biblioteca("acme", cid, 42)
    assert rid1 == rid2
    assert len(datos.referencias("acme", cid)) == 1


def test_agregar_referencia_biblioteca_referente_inexistente(base_temporal, monkeypatch):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    import referentes.datos as referentes_datos
    monkeypatch.setattr(referentes_datos, "referente", lambda cliente_, rid: None)
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia_biblioteca("acme", cid, 999)


def test_orden_de_campana_no_se_repite_tras_borrar_una_intermedia(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    t2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    t3 = datos.crear_temporada("acme", "Padre", "2026-06-05", "2026-06-20")
    c1 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    c2 = datos.agregar_campana("acme", sid, pid, "espejo_led", t2, 1, 0)
    c3 = datos.agregar_campana("acme", sid, pid, "espejo_led", t3, 1, 0)
    assert [datos.campana("acme", c)["orden"] for c in (c1, c2, c3)] == [0, 1, 2]
    datos.eliminar_campana("acme", c2)
    c4 = datos.agregar_campana("acme", sid, pid, "division_bano", tid, 1, 0)
    assert datos.campana("acme", c4)["orden"] == 3
    ordenes = [c["orden"] for c in datos.campanas("acme", sid)]
    assert len(ordenes) == len(set(ordenes))


def test_persona_color_hexadecimal_o_nada(base_temporal):
    from sprints import datos
    with pytest.raises(datos.ErrorDatos) as e:
        datos.crear_persona("acme", "X", color="rojo")
    assert "hexadecimal" in str(e.value)
    pid = datos.crear_persona("acme", "X", color="#4d8dff")
    assert datos.persona("acme", pid)["color"] == "#4d8dff"
    assert datos.crear_persona("acme", "Y", color="") and datos.personas("acme")[1]["color"] is None
    assert datos.crear_persona("acme", "Z", color=None) and datos.personas("acme")[2]["color"] is None
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_persona("acme", pid, color="4d8dff")      # sin #
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_persona("acme", pid, color="#zz")         # empieza por # pero no es hex
    assert datos.actualizar_persona("acme", pid, color="#000") and datos.persona("acme", pid)["color"] == "#000"
    assert datos.actualizar_persona("acme", pid, color="") and datos.persona("acme", pid)["color"] is None


def test_temporada_paleta_descarta_lo_que_no_es_hex(base_temporal):
    from sprints import datos
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31",
                                mood_visual={"paleta": ["#000", "rojo"], "luz": "cálida"})
    assert datos.temporada("acme", tid)["mood_visual"] == {"paleta": ["#000"], "luz": "cálida"}
    datos.actualizar_temporada("acme", tid, mood_visual={"paleta": ["#FFFFFF", "blanco", "#zz1122", 7]})
    assert datos.temporada("acme", tid)["mood_visual"]["paleta"] == ["#FFFFFF"]
    tid2 = datos.crear_temporada("acme", "Sin", "2026-01-01", "2026-02-01", mood_visual={"luz": "x"})
    assert datos.temporada("acme", tid2)["mood_visual"] == {"luz": "x"}


def _campana(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    return sid, datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)


def test_ideas_crud_y_validaciones(base_temporal):
    from sprints import datos
    sid, cid = _campana(datos)
    i1 = datos.crear_idea("acme", cid, "video", "Espejo al amanecer", "La cámara rodea el espejo...", sonido="pájaros",
                          enfoque="producto", gancho="Luz que despierta", referencias_ids=[], duracion_s=8,
                          plataformas=["instagram", "tiktok"])
    i2 = datos.crear_idea("acme", cid, "imagen", "Detalle del marco", "Primer plano del marco...")
    a = datos.idea("acme", i1)
    assert a["estado_idea"] == "propuesta" and a["revision"] == "pendiente" and a["estado"] is None
    assert a["sprint_id"] == sid and a["campana_orden"] == 0 and a["plataformas"] == ["instagram", "tiktok"]
    assert [i["id"] for i in datos.ideas("acme", cid)] == [i1, i2]
    assert datos.actualizar_idea("acme", i1, estado_idea="aprobada", escena="Nueva escena")
    assert datos.idea("acme", i1)["escena"] == "Nueva escena"
    with pytest.raises(datos.ErrorDatos):
        datos.crear_idea("acme", cid, "audio", "x", "y")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_idea("acme", cid, "video", "", "y")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_idea("acme", i1, estado_idea="rara")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_idea("acme", i1, revision="quizas")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_idea("acme", 999, "video", "x", "y")
    assert datos.idea("otro", i1) is None
    datos.actualizar_idea("acme", i2, estado_idea="descartada")
    assert [i["id"] for i in datos.ideas("acme", cid, incluir_descartadas=False)] == [i1]
    assert datos.eliminar_idea("acme", i2) and datos.idea("acme", i2) is None
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert "idea_creada" in tipos and "idea_eliminada" in tipos


def test_ideas_se_unen_con_la_sesion_de_crear(base_temporal):
    import creative_flow
    from sprints import datos
    sid, cid = _campana(datos)
    i1 = datos.crear_idea("acme", cid, "video", "A", "a", estado_idea="aprobada")
    i2 = datos.crear_idea("acme", cid, "imagen", "B", "b", estado_idea="aprobada")
    i3 = datos.crear_idea("acme", cid, "video", "C", "c", estado_idea="descartada")
    cf1 = creative_flow.crear("acme", [], ["Espejo"], [], "a", 8, "", "A")
    cf2 = creative_flow.crear("acme", [], ["Espejo"], [], "b", 0, "", "A")
    creative_flow.actualizar("acme", cf2, tipo="imagen")
    datos.actualizar_idea("acme", i1, cf_id=cf1)
    datos.actualizar_idea("acme", i2, cf_id=cf2)
    datos.actualizar_idea("acme", i3, cf_id=cf1)
    creative_flow.actualizar("acme", cf1, estado="video_listo", video_url="https://r2/v.mp4", usd=0.8)
    creative_flow.actualizar("acme", cf2, estado="video_generando")
    c = datos.campana("acme", cid)
    assert len(c["ideas"]) == 3 and [p["id"] for p in c["piezas"]] == [i1, i2]
    assert c["piezas_listas"] == 1 and c["piezas_aprobadas"] == 0
    p1 = next(p for p in c["piezas"] if p["id"] == i1)
    assert p1["estado"] == "listo" and p1["url_video"] == "https://r2/v.mp4" and p1["costo_usd"] == 0.8
    assert next(p for p in c["piezas"] if p["id"] == i2)["estado"] == "generando"
    datos.actualizar_idea("acme", i1, revision="aprobada")
    assert datos.campana("acme", cid)["piezas_aprobadas"] == 1
    # Una final de la misma sesión (legado_id cf__es_CO) NO se confunde con el clon.
    creative_flow.crear_final("acme", cf1, "es", "CO")
    assert datos.idea("acme", i1)["estado"] == "listo"
    with pytest.raises(datos.ErrorDatos):
        datos.eliminar_idea("acme", i1)     # ya tiene sesión


def test_reclamar_cf_es_compare_and_swap(base_temporal):
    """El primer `reclamar_cf` gana el `cf_id`; el segundo, sobre la misma
    idea todavía sin sesión (`cf_id IS NULL`), ya no puede ganar (evita que
    dos lotes concurrentes generen dos sesiones para la misma idea)."""
    from sprints import datos
    sid, cid = _campana(datos)
    i1 = datos.crear_idea("acme", cid, "video", "A", "a", estado_idea="aprobada")
    assert datos.reclamar_cf("acme", i1, "reservando_1") is True
    assert datos.idea("acme", i1)["cf_id"] == "reservando_1"
    assert datos.reclamar_cf("acme", i1, "reservando_2") is False        # ya no está en None
    assert datos.idea("acme", i1)["cf_id"] == "reservando_1"             # no se pisó


def test_reclamar_cf_con_esperado_solo_cambia_si_coincide(base_temporal):
    """Con `esperado`, el swap solo ocurre si el valor actual es exactamente
    ese (el caso de `regenerar`: reemplazar una sesión conocida por otra)."""
    from sprints import datos
    sid, cid = _campana(datos)
    i1 = datos.crear_idea("acme", cid, "video", "A", "a", estado_idea="aprobada")
    datos.actualizar_idea("acme", i1, cf_id="cf_viejo")
    assert datos.reclamar_cf("acme", i1, "cf_nuevo", esperado="cf_otro") is False
    assert datos.idea("acme", i1)["cf_id"] == "cf_viejo"
    assert datos.reclamar_cf("acme", i1, "cf_nuevo", esperado="cf_viejo") is True
    assert datos.idea("acme", i1)["cf_id"] == "cf_nuevo"
    assert datos.reclamar_cf("acme", i1, "cf_nuevo_2", esperado="cf_viejo") is False   # ya cambió, no coincide más


def test_actualizar_extra_sprint_hace_rmw_atomico(base_temporal):
    """`fn` recibe el `extra` actual y lo que agrega convive con lo que ya
    había (no reemplaza el dict completo como `actualizar_sprint(extra=...)`)."""
    from sprints import datos
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    datos.actualizar_extra_sprint("acme", sid, lambda extra: {**extra, "costo_estimado_usd": 1.5})
    assert datos.sprint("acme", sid)["extra"] == {"costo_estimado_usd": 1.5}
    nuevo = datos.actualizar_extra_sprint("acme", sid, lambda extra: {**extra, "lote_en_curso": True})
    assert nuevo == {"costo_estimado_usd": 1.5, "lote_en_curso": True}
    assert datos.sprint("acme", sid)["extra"] == {"costo_estimado_usd": 1.5, "lote_en_curso": True}
    assert datos.actualizar_extra_sprint("acme", 999, lambda extra: extra) is None


def test_guardar_qa_solo_si_la_sesion_sigue_siendo_la_evaluada(base_temporal):
    """F2: `guardar_qa` escribe `qa` únicamente cuando `cf_id` es el que se
    evaluó (compare-and-swap por sesión); si la idea ya apunta a otra
    sesión, no toca nada y devuelve False."""
    from sprints import datos
    sid, cid = _campana(datos)
    i1 = datos.crear_idea("acme", cid, "video", "A", "a", estado_idea="aprobada")
    datos.actualizar_idea("acme", i1, cf_id="cf_1")
    assert datos.guardar_qa("acme", i1, "cf_0", {"veredicto": "pasa"}) is False
    assert datos.idea("acme", i1)["qa"] is None
    assert datos.guardar_qa("otro", i1, "cf_1", {"veredicto": "pasa"}) is False       # otro cliente
    assert datos.guardar_qa("acme", i1, "cf_1", {"veredicto": "pasa", "cf_id": "cf_1"}) is True
    assert datos.idea("acme", i1)["qa"] == {"veredicto": "pasa", "cf_id": "cf_1"}


def test_persona_investigada_con_extra(base_temporal):
    from sprints import datos
    pid = datos.crear_persona("acme", "Melissa / La que regala", origen="investigada", extra={"avatar_id": 7})
    p = datos.persona("acme", pid)
    assert p["origen"] == "investigada" and p["extra"] == {"avatar_id": 7}
    assert datos.crear_persona("acme", "Sin extra") and datos.persona("acme", pid + 1)["extra"] == {}


def test_campana_guarda_y_actualiza_el_funnel(base_temporal):
    """Regresión del 2026-09-23: la migración 0014 creó `campana.funnel` pero la
    Table de db.py no lo declaraba, y cada inserción reventaba con
    CompileError («Unconsumed column names: funnel»)."""
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0, funnel="bof")
    assert datos.campana("acme", cid)["funnel"] == "bof"
    assert datos.actualizar_campana("acme", cid, funnel="mof")
    assert datos.campana("acme", cid)["funnel"] == "mof"
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, pid, "division_bano", tid, 1, 0, funnel="xxx")

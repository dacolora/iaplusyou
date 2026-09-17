def _c(**k):
    base = {"estado": "planeada", "n_videos": 10, "n_imagenes": 5, "referencias_listas": 0, "referencias_objetivo": 5,
            "referencias_total": 0, "piezas_listas": 0, "piezas_aprobadas": 0, "ideas": [], "piezas": []}
    base.update(k)
    return base


def test_progreso_campana_por_etapa():
    from sprints import progreso
    p = progreso.progreso_campana(_c(estado="referencias", referencias_listas=3))
    assert p == {"etapa": "referencias", "fraccion": 0.6, "porcentaje": 60, "texto": "3 / 5 referencias", "planeadas": 15}
    assert progreso.progreso_campana(_c(estado="referencias", referencias_listas=9))["fraccion"] == 1.0
    p = progreso.progreso_campana(_c(estado="generando", piezas_listas=6))
    assert p["etapa"] == "produccion" and p["porcentaje"] == 40 and p["texto"] == "6 de 15 piezas listas"
    p = progreso.progreso_campana(_c(estado="revision", piezas_aprobadas=15))
    assert p["etapa"] == "revision" and p["fraccion"] == 1.0
    assert progreso.progreso_campana(_c(n_videos=0, n_imagenes=0, estado="revision"))["fraccion"] == 0.0


def test_progreso_sprint_pondera_por_piezas():
    from sprints import progreso
    grande = _c(estado="referencias", referencias_listas=5, n_videos=20, n_imagenes=5)   # 25 piezas, 100 %
    chica = _c(estado="referencias", referencias_listas=0, n_videos=3, n_imagenes=2)     # 5 piezas, 0 %
    s = progreso.progreso_sprint([grande, chica])
    assert s["planeadas"] == 30 and s["porcentaje"] == 83 and s["texto"] == "0 de 30 piezas"
    assert progreso.progreso_sprint([]) == {"fraccion": 0.0, "porcentaje": 0, "planeadas": 0, "listas": 0, "aprobadas": 0,
                                            "texto": "sin piezas planeadas"}


def test_cobertura_sugiere_por_tipo_de_pieza():
    from sprints import progreso
    refs = [{"intencion": ["paleta"]}, {"intencion": ["composicion"]}]
    avisos = progreso.cobertura(_c(n_videos=10, n_imagenes=5), refs)
    assert len(avisos) == 1 and "movimiento de cámara" in avisos[0] and "10 videos" in avisos[0]
    assert progreso.cobertura(_c(n_videos=0, n_imagenes=5), refs) == []
    assert len(progreso.cobertura(_c(n_videos=1, n_imagenes=1), [])) == 2


def test_estado_campana_reglas():
    from sprints import estado
    assert estado.estado_campana(0, 15) == "planeada"
    assert estado.estado_campana(1, 15) == "referencias"
    ideas = [{"estado_idea": "propuesta"}] * 15
    assert estado.estado_campana(3, 15, ideas=ideas) == "ideas_propuestas"
    assert estado.estado_campana(3, 15, ideas=[{"estado_idea": "aprobada"}] * 15) == "ideas_aprobadas"
    assert estado.estado_campana(3, 15, ideas=ideas, piezas=[{"estado": "generando"}]) == "generando"
    assert estado.estado_campana(3, 2, piezas=[{"estado": "listo", "revision": "pendiente"}, {"estado": "error"}]) == "revision"
    assert estado.estado_campana(3, 2, piezas=[{"estado": "listo", "revision": "aprobada"}] * 2) == "completada"


def test_estado_sprint_reglas():
    from sprints import estado
    assert estado.estado_sprint([]) == "planeando"
    assert estado.estado_sprint([_c()]) == "planeando"
    assert estado.estado_sprint([_c(estado="referencias", referencias_listas=1)]) == "referencias"
    # Caso mixto: basta con que UNA campaña salga de planeada para que el sprint esté en referencias.
    assert estado.estado_sprint([_c(estado="planeada"), _c(estado="referencias", referencias_listas=1)]) == "referencias"
    listas = [_c(estado="referencias", referencias_listas=5), _c(estado="referencias", referencias_listas=6)]
    assert estado.estado_sprint(listas) == "listo_para_generar"
    assert estado.estado_sprint([_c(estado="referencias", referencias_listas=1)], listo_manual=True) == "listo_para_generar"
    assert estado.estado_sprint([_c(estado="generando"), _c(estado="revision")]) == "generando"
    assert estado.estado_sprint([_c(estado="revision"), _c(estado="completada")]) == "revision"
    assert estado.estado_sprint([_c(estado="completada")], cerrado=True) == "completado"


def test_recalcular_escribe_estados(base_temporal):
    from sprints import datos, estado
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", referencias_objetivo_defecto=1)
    cid = datos.agregar_campana("acme", sid, pid, "espejo", tid, 1, 0)
    assert estado.recalcular("acme", sid)["estado"] == "planeando"
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg")
    sp = estado.recalcular("acme", sid)
    assert sp["estado"] == "referencias" and sp["campanas"][0]["estado"] == "referencias"
    datos.actualizar_referencia("acme", rid, descripcion="luz")
    assert estado.recalcular("acme", sid)["estado"] == "listo_para_generar"
    assert datos.sprint("acme", sid)["estado"] == "listo_para_generar"
    assert estado.recalcular("acme", 999) is None


def test_recalcular_con_ideas_y_piezas_reales(base_temporal):
    import creative_flow
    from sprints import datos, estado
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", referencias_objetivo_defecto=1)
    cid = datos.agregar_campana("acme", sid, pid, "espejo", tid, 1, 0)
    datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz")
    i_desc = datos.crear_idea("acme", cid, "video", "X", "x", estado_idea="descartada")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "referencias"   # descartadas no cuentan
    i1 = datos.crear_idea("acme", cid, "video", "A", "a")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "ideas_propuestas"
    datos.actualizar_idea("acme", i1, estado_idea="aprobada")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "ideas_aprobadas"
    cf = creative_flow.crear("acme", [], ["Espejo"], [], "a", 8, "", "A")
    datos.actualizar_idea("acme", i1, cf_id=cf)
    creative_flow.actualizar("acme", cf, estado="video_generando")
    sp = estado.recalcular("acme", sid)
    assert sp["campanas"][0]["estado"] == "generando" and sp["estado"] == "generando"
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4")
    sp = estado.recalcular("acme", sid)
    assert sp["campanas"][0]["estado"] == "revision" and sp["estado"] == "revision"
    datos.actualizar_idea("acme", i1, revision="aprobada")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "completada"


def test_recalcular_reserva_viva_genera_y_vencida_vuelve_a_ideas_aprobadas(base_temporal):
    """F1: una idea con reserva viva (placeholder fresco, sin sesión de Crear
    aún) deja la campaña en `generando`; una reserva vencida cuenta como
    idea aprobada sin sesión (campaña `ideas_aprobadas`, sprint
    `listo_para_generar`) para que «Generar lote» vuelva a ofrecerse."""
    from sprints import datos, estado
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", referencias_objetivo_defecto=1)
    cid = datos.agregar_campana("acme", sid, pid, "espejo", tid, 1, 0)
    datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz")
    i1 = datos.crear_idea("acme", cid, "video", "A", "a", estado_idea="aprobada")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "ideas_aprobadas"
    datos.actualizar_idea("acme", i1, cf_id=datos.reserva_placeholder(i1))
    sp = estado.recalcular("acme", sid)
    assert sp["campanas"][0]["estado"] == "generando" and sp["estado"] == "generando"
    datos.actualizar_idea("acme", i1, cf_id=datos.reserva_placeholder(i1, ahora=1))
    sp = estado.recalcular("acme", sid)
    assert sp["campanas"][0]["estado"] == "ideas_aprobadas" and sp["estado"] == "listo_para_generar"
    assert sp["campanas"][0]["piezas"] == [] and sp["campanas"][0]["ideas"][0]["sin_sesion"] is True

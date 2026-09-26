import pytest


@pytest.fixture()
def escenario(base_temporal, monkeypatch, tmp_path):
    import catalogo_productos, marca, proyectos
    from sprints import datos
    from storage import r2_uploader
    # proyecto.json en un archivo temporal: estimar / crear_sesion leen las
    # preferencias de sonido de ahí y nunca el clientes/acme/ real del equipo.
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural.")
    monkeypatch.setattr(marca, "negative_prompt_efectivo", lambda c: None)
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: {
        "id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo", "regla": "Idéntico.", "categoria": "producto",
        "referencias": ["/tmp/espejo/1.jpg", "/tmp/espejo/2.jpg"], "imagenes": ["1.jpg", "2.jpg"]})
    monkeypatch.setattr(r2_uploader, "upload_image", lambda ruta, key: f"https://r2/{key}")
    monkeypatch.setattr(proyectos, "preferencias_flowplus", lambda c: {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro"})
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    pid = datos.crear_persona("acme", "Premium", resumen="Busca calidad", tono="cercano", senales_visuales=["cocina"])
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos")
    sid = datos.crear_sprint("acme", "Sprint octubre", "2026-10-01", "2026-10-31", destinos=["es_CO", "en_US"])
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/ref1.jpg", descripcion="luz")
    r2 = datos.agregar_referencia("acme", cid, "video", "https://r2/ref2.mp4", frame_url="https://r2/ref2.frame.jpg", descripcion="mov")
    iv = datos.crear_idea("acme", cid, "video", "Amanecer", "Rodea el espejo", sonido="pájaros", enfoque="producto",
                          gancho="Luz", referencias_ids=[r2], duracion_s=8, plataformas=["instagram"], estado_idea="aprobada")
    ii = datos.crear_idea("acme", cid, "imagen", "Marco", "Primer plano", enfoque="producto", estado_idea="aprobada")
    ip = datos.crear_idea("acme", cid, "video", "Sin aprobar", "x", estado_idea="propuesta")
    return {"sid": sid, "cid": cid, "iv": iv, "ii": ii, "ip": ip, "r1": r1, "r2": r2}


def test_estimar_cuenta_aprobadas_sin_sesion(escenario):
    from sprints import produccion
    from providers import flowplus_modelos
    e = produccion.estimar("acme", escenario["sid"])
    assert e["videos"] == 1 and e["imagenes"] == 1 and e["segundos"] == 180 + 60
    esperado = flowplus_modelos.estimate_video("wan3", 8)["usd"] + flowplus_modelos.estimate_imagen("seedream_v5_pro", 3)["usd"]
    assert abs(e["usd"] - esperado) < 1e-6 and e["modelo_video"] == "wan3" and "USD" in e["texto"]
    e2 = produccion.estimar("acme", escenario["sid"], modelo_video="kling_o3_pro")
    assert e2["modelo_video"] == "kling_o3_pro" and e2["usd"] > e["usd"]
    assert produccion.estimar("acme", escenario["sid"], modelo_video="inventado")["modelo_video"] == "wan3"


def test_crear_sesion_arma_referencias_prompt_y_vinculo(escenario):
    import creative_flow
    from sprints import datos, produccion
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    idea = datos.idea("acme", escenario["iv"])
    refs, urls, productos = produccion.referencias_sesion("acme", c, idea)
    assert productos == ["Espejo LED"]
    assert refs[0]["etiqueta"] == "@Producto 1" and refs[0]["producto"] == "Espejo LED" and refs[0]["regla"] == "Idéntico."
    # la referencia de la idea (r2, video) va antes que la otra (r1)
    assert [r["url"] for r in refs[1:3]] == ["https://r2/ref2.mp4", "https://r2/ref1.jpg"]
    assert refs[1]["tipo"] == "video" and refs[1]["frame_url"] == "https://r2/ref2.frame.jpg" and refs[1]["etiqueta"] == "@Video 1"
    assert refs[2]["etiqueta"] == "@Imagen 1" and urls[1] == "https://r2/ref2.frame.jpg"
    cf_id = produccion.crear_sesion("acme", sp, c, idea, "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["sprint"] == {"sprint_id": sp["id"], "sprint_nombre": "Sprint octubre", "campana_id": c["id"], "campana_n": 1, "cp_id": idea["id"]}
    assert e["tipo"] == "video" and e["modelo"] == "wan3" and e["duracion_objetivo"] == 8 and e["tono"] == "cercano"
    assert e["platforms"] == ["instagram"] and e["aspect_ratio"] == "9:16" and e["enfoque"] == "producto"
    assert "AUDIENCIA: Busca calidad" in e["prompt_relleno"] and "TEMPORADA: Navidad" in e["prompt_relleno"]
    assert "SONIDO: pájaros" in e["prompt_relleno"] and "ESCENA: Rodea el espejo" in e["prompt_relleno"]
    assert e["con_sonido"] is True and e["sonido_texto"] == "pájaros" and e["musica_estilo"] == ""
    assert datos.idea("acme", escenario["iv"])["cf_id"] == cf_id
    idea_img = datos.idea("acme", escenario["ii"])
    cf2 = produccion.crear_sesion("acme", sp, c, idea_img, "wan3", "seedream_v5_pro")
    e2 = creative_flow.cargar("acme")[cf2]
    assert e2["tipo"] == "imagen" and e2["modelo"] == "seedream_v5_pro" and "SONIDO" not in e2["prompt_relleno"]


def test_crear_sesion_sigue_la_preferencia_de_sonido_del_proyecto(escenario):
    import creative_flow
    import proyectos
    from sprints import datos, produccion
    proyectos.guardar_preferencias_sonido("acme", False, "urbano")
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    cf_id = produccion.crear_sesion("acme", sp, c, datos.idea("acme", escenario["iv"]), "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["con_sonido"] is False and e["musica_estilo"] == "urbano" and "SONIDO" not in e["prompt_relleno"]


def test_crear_sesion_normaliza_y_recorta_el_sonido_de_la_idea(escenario):
    """El sonido de la idea entra a la sesión como en Crear: espacios
    colapsados y máximo 200 caracteres, tanto en `sonido_texto` como en la
    línea SONIDO del prompt."""
    import creative_flow
    from sprints import datos, produccion
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    largo = "  risas   de\nniños " + "x" * 300
    idea = datos.crear_idea("acme", c["id"], "video", "Ruido", "Gira el espejo", sonido=largo, enfoque="producto",
                            duracion_s=5, plataformas=["instagram"], estado_idea="aprobada")
    cf_id = produccion.crear_sesion("acme", sp, c, datos.idea("acme", idea), "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["sonido_texto"].startswith("risas de niños x") and len(e["sonido_texto"]) == 200
    assert "SONIDO: " + e["sonido_texto"] + ". Sin diálogo" in e["prompt_relleno"]
    assert "\n" not in e["sonido_texto"] and "  " not in e["sonido_texto"]


def test_lanzar_lote_encola_con_prioridad_y_registra(escenario, monkeypatch):
    import flowplus_lanzar
    import trabajos
    from sprints import datos, produccion
    lanzados, encolados = [], []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append((cf, e["tipo"], prioridad)) or True)
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((tipo, payload, kw.get("prioridad"))) or True)
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["encoladas"] == 2 and r["omitidas"] == 0 and len(r["cf_ids"]) == 2 and r["usd"] > 0
    # el video ahora pasa por el director (trabajos.encolar); solo la imagen usa flowplus_lanzar.lanzar directo
    assert sorted(t for _, t, _ in lanzados) == ["imagen"] and all(p == 3 for _, _, p in lanzados)
    assert len(encolados) == 1 and encolados[0][0] == "flowplus_director" and encolados[0][2] == 3
    sp = datos.sprint("acme", escenario["sid"])
    assert sp["extra"]["lote_en_curso"] is True and abs(sp["extra"]["costo_estimado_usd"] - r["usd"]) < 1e-6
    assert sp["eventos"][0]["tipo"] == "lote_encolado" and sp["eventos"][0]["datos"]["encoladas"] == 2
    assert datos.idea("acme", escenario["ip"])["cf_id"] is None      # la propuesta no se genera
    r2 = produccion.lanzar_lote("acme", escenario["sid"])
    assert r2["encoladas"] == 0                                        # idempotente: ya tienen sesión
    with pytest.raises(datos.ErrorDatos):
        produccion.lanzar_lote("acme", 999)


def test_lanzar_lote_encola_el_director_para_videos_y_genera_directo_las_imagenes(escenario, monkeypatch):
    import flowplus_lanzar
    import trabajos
    from sprints import datos, produccion
    lanzados, encolados = [], []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append((cf, e["tipo"], prioridad)) or True)
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((tipo, payload, kw.get("prioridad"))) or True)
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["encoladas"] == 2
    assert [t for _, t, _ in lanzados] == ["imagen"]
    assert len(encolados) == 1 and encolados[0][0] == "flowplus_director"
    assert encolados[0][1]["auto_lanzar"] is True and encolados[0][1]["prioridad"] == 3 and encolados[0][2] == 3
    cf_video = encolados[0][1]["cf_id"]
    import creative_flow
    e = creative_flow.cargar("acme")[cf_video]
    assert e["estado"] == "prompt_pendiente" and e["referencias"][0]["token"] == "Image 1" and e["prompt_relleno"]   # determinista de respaldo


def test_regenerar_pasa_por_el_director(escenario, monkeypatch):
    import creative_flow
    import flowplus_lanzar
    import trabajos
    from sprints import datos, produccion
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: True)
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((tipo, payload)) or True)
    produccion.lanzar_lote("acme", escenario["sid"], campana_id=escenario["cid"])
    cf = datos.idea("acme", escenario["iv"])["cf_id"]
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4")
    encolados.clear()
    nuevo = produccion.regenerar("acme", escenario["iv"])
    assert encolados == [("flowplus_director", {"cliente": "acme", "cf_id": nuevo, "auto_lanzar": True, "prioridad": 3})]
    assert creative_flow.cargar("acme")[nuevo]["estado"] == "prompt_pendiente"


def test_encolar_director_deja_la_sesion_en_error_si_la_cola_rechaza(escenario, monkeypatch):
    """Si `trabajos.encolar` rechaza la tarea (job_id duplicado, lo que no
    debería pasar con uno recién armado, pero por si acaso), la sesión no se
    queda colgada en `prompt_pendiente` sin tarea viva ni forma de
    recuperarse: `encolar_director` la deja en `error` con motivo, así
    `reintentar` (que exige `estado == "error"`) la puede relanzar con el
    prompt determinista que ya tiene guardado."""
    import creative_flow
    import trabajos
    from sprints import datos, produccion
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: True)
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["encoladas"] == 2
    cf_video = datos.idea("acme", escenario["iv"])["cf_id"]
    prompt_previo = creative_flow.cargar("acme")[cf_video]["prompt_relleno"]
    assert creative_flow.cargar("acme")[cf_video]["estado"] == "prompt_pendiente"   # ya cubierto arriba: reuso de una línea
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: False)
    assert produccion.encolar_director("acme", cf_video) is False
    e = creative_flow.cargar("acme")[cf_video]
    assert e["estado"] == "error" and "encolar" in e["error"] and e["prompt_relleno"] == prompt_previo and prompt_previo


def test_reintentar_y_regenerar(escenario, monkeypatch):
    import creative_flow
    import flowplus_lanzar
    import trabajos
    from sprints import datos, produccion
    lanzados, encolados = [], []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append(cf) or True)
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append(payload["cf_id"]) or True)
    produccion.lanzar_lote("acme", escenario["sid"], campana_id=escenario["cid"])
    cf = datos.idea("acme", escenario["iv"])["cf_id"]
    assert encolados[-1] == cf                                           # video: el lote lo mandó al director
    assert produccion.reintentar("acme", escenario["iv"]) is False       # no está en error
    creative_flow.actualizar("acme", cf, estado="error", error="timeout")
    datos.actualizar_extra_sprint("acme", escenario["sid"], lambda e: {**e, "lote_en_curso": False})   # el lote ya "terminó"
    assert produccion.reintentar("acme", escenario["iv"]) is True and lanzados[-1] == cf
    # E1: reintentar vuelve a encender el lote, como regenerar, para que la periódica avise al terminar
    assert datos.sprint("acme", escenario["sid"])["extra"]["lote_en_curso"] is True
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4")
    datos.actualizar_idea("acme", escenario["iv"], qa={"score": 40}, revision="rechazada", revision_motivo="feo")
    nuevo = produccion.regenerar("acme", escenario["iv"])
    assert nuevo != cf and encolados[-1] == nuevo                        # regenerar: también video, también director
    i = datos.idea("acme", escenario["iv"])
    assert i["cf_id"] == nuevo and i["qa"] is None and i["revision"] == "pendiente" and i["revision_motivo"] is None
    assert creative_flow.cargar("acme")[nuevo]["sprint"]["cp_id"] == escenario["iv"]
    assert i["extra"]["cf_anteriores"] == [cf]


def test_lanzar_lote_no_duplica_una_idea_ya_reservada(escenario, monkeypatch):
    """Simula la carrera: dos llamadas a `lanzar_lote` leyeron la misma lista
    de `pendientes` (una idea sin `cf_id` todavía), pero para cuando esta
    llamada procesa esa idea, otra ya se le adelantó y la reservó. El
    compare-and-swap de `reclamar_cf` dentro del lote debe verla omitida y no
    generar una segunda sesión (double spend) ni pisar la reserva ajena."""
    import flowplus_lanzar
    from sprints import datos, produccion
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append(cf) or True)
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    idea_iv = datos.idea("acme", escenario["iv"])
    idea_ii = datos.idea("acme", escenario["ii"])
    datos.actualizar_idea("acme", escenario["iv"], cf_id="reservando_99")   # "otra llamada" ya se adelantó
    monkeypatch.setattr(produccion, "pendientes",
                        lambda cliente, sprint_id, campana_id=None: [(c, idea_iv), (c, idea_ii)])
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["omitidas"] == 1 and r["encoladas"] == 1 and len(r["cf_ids"]) == 1
    assert datos.idea("acme", escenario["iv"])["cf_id"] == "reservando_99"   # sin tocar, sin sesión nueva
    assert datos.idea("acme", escenario["ii"])["cf_id"] is not None


def test_regenerar_falla_si_la_reserva_ya_no_es_valida(escenario, monkeypatch):
    """Cuando `reclamar_cf` no puede ganar el swap (otra regeneración se
    adelantó entre el `duplicar` y este punto), `regenerar` archiva la sesión
    duplicada de más y nunca la encola."""
    import creative_flow
    import flowplus_lanzar
    from sprints import datos, produccion
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: True)
    produccion.lanzar_lote("acme", escenario["sid"], campana_id=escenario["cid"])
    archivados = []
    monkeypatch.setattr(creative_flow, "archivar_concepto",
                        lambda c, cf, motivo: archivados.append((c, cf, motivo)) or True)
    monkeypatch.setattr(datos, "reclamar_cf", lambda cliente, cp_id, cf_id, esperado=None: False)
    with pytest.raises(datos.ErrorDatos):
        produccion.regenerar("acme", escenario["iv"])
    assert len(archivados) == 1 and archivados[0][2] == "regeneración duplicada"


def test_referencias_sesion_exige_foto_de_producto(escenario, monkeypatch):
    import catalogo_productos
    from sprints import datos, produccion
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    idea = datos.idea("acme", escenario["iv"])
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda cl, pid, categoria=None: None)
    with pytest.raises(datos.ErrorDatos):
        produccion.referencias_sesion("acme", c, idea)


def test_lanzar_lote_omite_y_libera_reserva_si_falla_la_subida_del_producto(escenario, monkeypatch):
    """`referencias_sesion` ahora exige la foto del producto: si subirla
    falla, la idea no se queda a medio reservar ni gasta un lanzamiento —
    `lanzar_lote` la cuenta como omitida, no crea sesión y deja `cf_id` en
    None otra vez para un reintento posterior."""
    import flowplus_lanzar
    from sprints import datos, produccion
    from storage import r2_uploader
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append(cf) or True)
    def _falla(ruta, key):
        raise RuntimeError("R2 no responde")
    monkeypatch.setattr(r2_uploader, "upload_image", _falla)
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["omitidas"] == 2 and r["encoladas"] == 0 and r["cf_ids"] == [] and lanzados == []
    assert datos.idea("acme", escenario["iv"])["cf_id"] is None
    assert datos.idea("acme", escenario["ii"])["cf_id"] is None
    sp = datos.sprint("acme", escenario["sid"])
    tipos = [e["tipo"] for e in sp["eventos"]]
    assert tipos.count("pieza_omitida") == 2 and "lote_encolado" not in tipos


def test_estimar_cuenta_los_logos_en_n_referencias_de_imagen(escenario, monkeypatch):
    """`_n_referencias` debe sumar los logos que `referencias_sesion` agrega
    (tope 2) a lo que le llega al modelo de imagen, si no el estimado del
    lote sale corto frente a lo que realmente se manda a generar."""
    from sprints import produccion
    from providers import flowplus_modelos
    monkeypatch.setattr(produccion, "_logos",
                        lambda cliente: [{"url": "https://r2/l1.png"}, {"url": "https://r2/l2.png"}])
    vistos = []
    original = flowplus_modelos.estimate_imagen
    def _espia(modelo, n_referencias=1):
        vistos.append(n_referencias)
        return original(modelo, n_referencias=n_referencias)
    monkeypatch.setattr(flowplus_modelos, "estimate_imagen", _espia)
    produccion.estimar("acme", escenario["sid"])
    assert vistos == [1 + 2 + 2]      # 1 producto + 2 referencias de campaña (fixture) + 2 logos (tope)


def test_progreso_agregado(escenario, monkeypatch):
    import cola
    import creative_flow
    import flowplus_lanzar
    from sprints import datos, produccion
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: True)
    produccion.lanzar_lote("acme", escenario["sid"])
    cfv, cfi = datos.idea("acme", escenario["iv"])["cf_id"], datos.idea("acme", escenario["ii"])["cf_id"]
    monkeypatch.setattr(cola, "consultar_por_job", lambda job_id: {"estado": "pendiente"} if cfv in job_id else {"estado": "en_curso"})
    p = produccion.progreso("acme", escenario["sid"])
    s = p["sprint"]
    assert s["planeadas"] == 3 and s["encoladas"] == 1 and s["generando"] == 1 and s["listas"] == 0 and s["error"] == 0
    assert s["segundos_restantes"] == 180 + 60 and p["campanas"][0]["id"] == escenario["cid"]
    creative_flow.actualizar("acme", cfv, estado="video_listo", video_url="https://r2/v.mp4", usd=0.8)
    creative_flow.actualizar("acme", cfi, estado="error", error="x")
    datos.actualizar_idea("acme", escenario["iv"], revision="aprobada")
    s = produccion.progreso("acme", escenario["sid"])["sprint"]
    assert s["listas"] == 1 and s["error"] == 1 and s["aprobadas"] == 1 and abs(s["costo_usd"] - 0.8) < 1e-6 and s["segundos_restantes"] == 0


def test_reserva_placeholder_es_reserva_y_vence(base_temporal):
    """F1: el placeholder lleva la hora (`reservando_<cp>_<epoch>`); vence a
    los RESERVA_TTL_S. Un placeholder viejo sin hora (`reservando_<cp>`) cuenta
    como vencido; un cf_id real nunca es reserva ni está vencido."""
    from sprints import datos, produccion
    r = produccion.reserva_placeholder(7, ahora=1000)
    assert r == "reservando_7_1000" and produccion.es_reserva(r) and datos.es_reserva(r)
    assert produccion.RESERVA_TTL_S == 600
    assert produccion.reserva_vencida(r, ahora=1000 + 599) is False
    assert produccion.reserva_vencida(r, ahora=1000 + 601) is True
    assert produccion.reserva_vencida("reservando_7") is True          # formato viejo, sin hora
    assert produccion.reserva_vencida("reservando_7_abc") is True      # hora ilegible
    assert produccion.es_reserva("cf_abc") is False and produccion.es_reserva(None) is False
    assert produccion.reserva_vencida("cf_abc") is False and produccion.reserva_vencida(None) is False


def test_lanzar_lote_recupera_una_reserva_vencida(escenario, monkeypatch):
    """F1 (a): una idea que quedó con un placeholder vencido (se cayó el
    proceso entre reservar y crear la sesión) vuelve a `pendientes()` y
    `lanzar_lote` la reclama atómicamente y le crea la sesión."""
    import flowplus_lanzar
    import trabajos
    from sprints import datos, produccion
    lanzados, encolados = [], []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append(cf) or True)
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append(payload["cf_id"]) or True)
    vieja = produccion.reserva_placeholder(escenario["iv"], ahora=1)      # hace mucho: vencida
    datos.actualizar_idea("acme", escenario["iv"], cf_id=vieja)
    ids = [i["id"] for _, i in produccion.pendientes("acme", escenario["sid"])]
    assert escenario["iv"] in ids and escenario["ii"] in ids
    assert datos.idea("acme", escenario["iv"])["sin_sesion"] is True
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["encoladas"] == 2 and r["omitidas"] == 0
    cf = datos.idea("acme", escenario["iv"])["cf_id"]      # es un video: pasó por el director, no por flowplus_lanzar
    assert cf in encolados and not produccion.es_reserva(cf)


def test_lanzar_lote_no_roba_una_reserva_viva(escenario, monkeypatch):
    """F1 (b): una reserva fresca (otro lote la tomó hace segundos) no está
    en `pendientes()` y `lanzar_lote` no la toca."""
    import flowplus_lanzar
    from sprints import datos, produccion
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append(cf) or True)
    fresca = produccion.reserva_placeholder(escenario["iv"])
    datos.actualizar_idea("acme", escenario["iv"], cf_id=fresca)
    assert [i["id"] for _, i in produccion.pendientes("acme", escenario["sid"])] == [escenario["ii"]]
    assert datos.idea("acme", escenario["iv"])["sin_sesion"] is False
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["encoladas"] == 1 and len(lanzados) == 1
    assert datos.idea("acme", escenario["iv"])["cf_id"] == fresca


def test_progreso_con_reserva_vencida_no_cuenta_el_lote_en_curso(escenario, monkeypatch):
    """F1 (c): una reserva vencida no es una pieza viva (ni encolada ni
    generando): el lote no está en curso. Una viva sí cuenta como encolada."""
    import cola
    from sprints import datos, produccion
    monkeypatch.setattr(cola, "consultar_por_job", lambda job_id: None)
    datos.actualizar_idea("acme", escenario["iv"], cf_id=produccion.reserva_placeholder(escenario["iv"], ahora=1))
    s = produccion.progreso("acme", escenario["sid"])["sprint"]
    assert s["encoladas"] == 0 and s["generando"] == 0 and s["en_curso"] is False
    assert datos.sprint("acme", escenario["sid"])["campanas"][0]["piezas"] == []
    datos.actualizar_idea("acme", escenario["iv"], cf_id=produccion.reserva_placeholder(escenario["iv"]))
    s = produccion.progreso("acme", escenario["sid"])["sprint"]
    assert s["encoladas"] == 1 and s["en_curso"] is True and s["segundos_restantes"] == produccion.SEGUNDOS_VIDEO


def test_crear_sesion_no_pisa_una_reserva_que_ya_no_es_suya(escenario, monkeypatch):
    """F1: si la reserva con la que se llamó a `crear_sesion` ya no es el
    cf_id de la idea (venció y otro lote la reclamó), el vínculo no se
    escribe encima: se avisa con ErrorDatos y `lanzar_lote` la cuenta omitida
    sin soltar la reserva ajena."""
    import flowplus_lanzar
    from sprints import datos, produccion
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append(cf) or True)
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    idea = datos.idea("acme", escenario["iv"])
    ajena = produccion.reserva_placeholder(escenario["iv"])
    datos.actualizar_idea("acme", escenario["iv"], cf_id=ajena)
    with pytest.raises(datos.ErrorDatos):
        produccion.crear_sesion("acme", sp, c, idea, "wan3", "seedream_v5_pro", reserva="reservando_%d_1" % escenario["iv"])
    assert datos.idea("acme", escenario["iv"])["cf_id"] == ajena
    # y en el lote: la reserva vencida se reclama, pero si alguien la pisa antes del vínculo, se libera solo la propia
    monkeypatch.setattr(produccion, "reserva_vencida", lambda cf_id, ahora=None: True)
    vieja = datos.idea("acme", escenario["iv"])
    original = produccion.crear_sesion
    def _pisa(cliente, sprint, campana, idea, mv, mi, reserva=None):
        datos.actualizar_idea(cliente, idea["id"], cf_id="reservando_%d_%d" % (idea["id"], 2 ** 40))   # otro lote se adelantó
        return original(cliente, sprint, campana, idea, mv, mi, reserva=reserva)
    monkeypatch.setattr(produccion, "crear_sesion", _pisa)
    r = produccion.lanzar_lote("acme", escenario["sid"], campana_id=escenario["cid"])
    assert r["omitidas"] >= 1 and datos.idea("acme", escenario["iv"])["cf_id"].startswith("reservando_")


def test_crear_sesion_recorta_la_duracion_de_la_idea_al_modelo(escenario):
    """Una idea de 30 s cabe en Wan pero Kling llega a 15: el estimado y la
    sesión usan la duración recortada (nunca se pide algo que el modelo rechaza)."""
    import creative_flow
    from providers import flowplus_modelos
    from sprints import datos, produccion
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    datos.actualizar_idea("acme", escenario["iv"], duracion_s=30)
    e_wan = produccion.estimar("acme", escenario["sid"], modelo_video="wan3")
    e_kling = produccion.estimar("acme", escenario["sid"], modelo_video="kling_o3_pro")
    imagen = flowplus_modelos.estimate_imagen("seedream_v5_pro", 3)["usd"]
    assert abs(e_wan["usd"] - (flowplus_modelos.estimate_video("wan3", 30)["usd"] + imagen)) < 1e-6
    assert abs(e_kling["usd"] - (flowplus_modelos.estimate_video("kling_o3_pro", 15)["usd"] + imagen)) < 1e-6
    cf_id = produccion.crear_sesion("acme", sp, c, datos.idea("acme", escenario["iv"]), "kling_o3_pro", "seedream_v5_pro")
    assert creative_flow.cargar("acme")[cf_id]["duracion_objetivo"] == 15


def test_crear_sesion_propaga_referente_id_de_biblioteca(escenario, monkeypatch):
    """Una idea que cita una referencia traída de la biblioteca (Bloque 2,
    `agregar_referencia_biblioteca`) debe dejar `referente_id` en la sesión
    de Crear, para que `referentes.recrear.usos()` cuente también las piezas
    que salieron de Sprints."""
    import creative_flow
    import referentes.datos as referentes_datos
    from sprints import datos, produccion
    monkeypatch.setattr(referentes_datos, "referente", lambda cliente_, rid: {
        "id": rid, "estado_imagen": "ok", "imagen_url": "https://cdn/ref.jpg", "titular": "T",
        "firma": "F", "familia": None, "etapa": "TOF", "consciencia": None, "dolor": None,
    })
    monkeypatch.setattr(referentes_datos, "familias", lambda cliente_: [])
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    rid = datos.agregar_referencia_biblioteca("acme", c["id"], 42)
    cp_id = datos.crear_idea("acme", c["id"], "imagen", "Con referente", "Plano cercano", enfoque="producto",
                             referencias_ids=[rid], estado_idea="aprobada")
    idea = datos.idea("acme", cp_id)
    cf_id = produccion.crear_sesion("acme", sp, c, idea, "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["referente_id"] == 42


def test_crear_sesion_sin_referencia_de_biblioteca_no_manda_referente_id(escenario):
    """Sin ninguna referencia de biblioteca en la campaña, `crear_sesion` no
    debe escribir `referente_id` en absoluto (ni siquiera en None) para no
    ensuciar `concepto.extra` de toda sesión que no viene de un referente."""
    import creative_flow
    from sprints import datos, produccion
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    idea = datos.idea("acme", escenario["ii"])
    cf_id = produccion.crear_sesion("acme", sp, c, idea, "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert "referente_id" not in e


def test_crear_sesion_lleva_angulo_y_contexto_a_la_sesion(escenario):
    import creative_flow
    import db
    from sprints import datos, produccion
    angulo = {"version": 1, "audiencia": "a", "consciencia": "consciente_del_problema", "sofisticacion": 2, "deseo": "d",
              "promesa": "p", "mecanismo": None, "pruebas": [], "lead": "problema_solucion", "gancho": "g",
              "faltantes": [], "origen": "ideas"}
    with db.conectar() as con:
        con.execute(db.campana_pieza.update().where(db.campana_pieza.c.id == escenario["iv"]).values(extra={"angulo": angulo}))
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    cf_id = produccion.crear_sesion("acme", sp, c, datos.idea("acme", escenario["iv"]), "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["angulo"]["promesa"] == "p"
    assert e["contexto"]["persona"]["resumen"] == "Busca calidad" and e["contexto"]["temporada"]["nombre"] == "Navidad"
    d = creative_flow.datos_para_director("acme", e)
    assert d["angulo"]["gancho"] == "g" and d["contexto"]["temporada"]["nombre"] == "Navidad"
    copia = creative_flow.duplicar("acme", cf_id)
    assert creative_flow.cargar("acme")[copia]["angulo"]["promesa"] == "p"      # regenerar/derivar conserva el ángulo


def test_crear_sesion_sin_angulo_no_inventa_uno(escenario):
    import creative_flow
    from sprints import datos, produccion
    sp = datos.sprint("acme", escenario["sid"])
    cf_id = produccion.crear_sesion("acme", sp, sp["campanas"][0], datos.idea("acme", escenario["iv"]), "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert "angulo" not in e and e["contexto"]["persona"]["tono"] == "cercano"

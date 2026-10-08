import pytest


def _referencia(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo", tid, 1, 1)
    return sid, cid, datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg")


def test_job_ids():
    from tareas import sprints as ts
    assert ts.job_id_analizar("acme", 7) == "acme__ref7__analizar"
    assert ts.job_id_sugerir("acme") == "acme__sprints__sugerir_personas"
    assert ts.job_id_link("acme", 3) == "acme__campana3__link"


def test_analizar_referencia_guarda_analisis(base_temporal, monkeypatch):
    import tareas
    from sprints import analisis, datos
    from tareas import sprints as ts
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(analisis, "analizar", lambda ref, marca="", idioma="es": {"resumen": "ok", "paleta": ["#000"]})
    tareas.cargar_todas()
    assert "sprint_analizar_referencia" in tareas.REGISTRO
    msg = tareas.REGISTRO["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": rid},
                                                         "job_id": ts.job_id_analizar("acme", rid)})
    r = datos.referencia("acme", rid)
    assert r["analisis_estado"] == "listo" and r["analisis"]["resumen"] == "ok" and "analizada" in msg.lower()
    assert tareas.REGISTRO["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": 999}}) == "La referencia ya no existe."


def test_analizar_referencia_error_deja_rastro(base_temporal, monkeypatch):
    import tareas
    from sprints import analisis, datos
    sid, cid, rid = _referencia(datos)
    def rompe(ref, marca="", idioma="es"):
        raise RuntimeError("Claude caído")
    monkeypatch.setattr(analisis, "analizar", rompe)
    tareas.cargar_todas()
    with pytest.raises(RuntimeError):
        tareas.REGISTRO["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": rid}})
    r = datos.referencia("acme", rid)
    assert r["analisis_estado"] == "error" and "Claude caído" in r["analisis"]["error"]
    datos.actualizar_referencia("acme", rid, analisis_estado="pendiente")
    tareas.AL_INTERRUMPIR["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": rid}}, "reinicio")
    assert datos.referencia("acme", rid)["analisis_estado"] == "error"


def test_encolar_analisis_usa_el_worker(base_temporal, monkeypatch):
    import trabajos
    from tareas import sprints as ts
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_analisis("acme", 5) is True
    job_id, tipo, payload, kw = encolados[0]
    assert job_id == "acme__ref5__analizar" and tipo == "sprint_analizar_referencia"
    assert payload == {"cliente": "acme", "referencia_id": 5} and kw["max_intentos"] == 3 and kw["cliente"] == "acme"


def test_sugerir_personas_crea_filas(base_temporal, monkeypatch):
    import tareas
    from sprints import datos, sugerencias
    monkeypatch.setattr(sugerencias, "sugerir_personas", lambda c, cuantas=3: [
        {"nombre": "Cliente Premium", "resumen": "r", "descripcion": "d", "edad_rango": "35-50", "tono": "t",
         "senales_visuales": ["cocina"], "palabras_clave": ["lujo"], "color": "#4d8dff"}])
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_sugerir_personas"]({"payload": {"cliente": "acme", "cuantas": 1}})
    p = datos.personas("acme")
    assert len(p) == 1 and p[0]["origen"] == "sugerida_ia" and p[0]["color"] == "#4d8dff" and "1 personas" in msg


def test_sugerir_personas_guarda_la_consciencia_en_extra(base_temporal, monkeypatch):
    import tareas
    from sprints import datos, sugerencias
    monkeypatch.setattr(sugerencias, "sugerir_personas", lambda c, cuantas=3: [
        {"nombre": "Con nivel", "resumen": "", "descripcion": "", "edad_rango": "", "tono": "", "senales_visuales": [],
         "palabras_clave": [], "color": "#4d8dff", "conciencia": {"nivel": "muy_consciente", "detalle": "ya compró"}},
        {"nombre": "Sin nivel", "resumen": "", "descripcion": "", "edad_rango": "", "tono": "", "senales_visuales": [],
         "palabras_clave": [], "color": "#7c5cff"}])
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_sugerir_personas"]({"payload": {"cliente": "acme", "cuantas": 2}})
    por_nombre = {p["nombre"]: p for p in datos.personas("acme")}
    assert por_nombre["Con nivel"]["extra"]["conciencia"] == {"nivel": "muy_consciente", "detalle": "ya compró"}
    assert por_nombre["Sin nivel"]["extra"] == {}


def test_referencia_desde_link_descarga_registra_y_encola(base_temporal, monkeypatch, tmp_path):
    import tareas
    import referencias_link
    from sprints import archivos, datos
    from tareas import sprints as ts
    sid, cid, _ = _referencia(datos)
    def descargar_falso(url, carpeta, nombre_base):
        ruta = tmp_path / f"{nombre_base}.mp4"; ruta.write_bytes(b"mp4")
        return str(ruta), {"fuente": "tiktok", "titulo": "Baile", "url_origen": url}
    monkeypatch.setattr(referencias_link, "descargar", descargar_falso)
    monkeypatch.setattr(archivos, "registrar_local", lambda c, ruta, titulo: {
        "tipo": "video", "url": "https://r2/l.mp4", "frame_url": "https://r2/l.frame.jpg", "ruta_local": ruta, "titulo": titulo})
    encolados = []
    monkeypatch.setattr(ts, "encolar_analisis", lambda c, rid: encolados.append((c, rid)) or True)
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_referencia_link"]({"payload": {"cliente": "acme", "campana_id": cid, "url": "https://t.t/v"}})
    refs = datos.referencias("acme", cid)
    nueva = refs[-1]
    assert nueva["origen"] == "link" and nueva["titulo"] == "Baile" and nueva["frame_url"] == "https://r2/l.frame.jpg"
    assert encolados == [("acme", nueva["id"])] and "link" in msg


def test_proponer_ideas_tarea_y_encolar(base_temporal, monkeypatch):
    import tareas
    import trabajos
    from sprints import datos, ideas
    from tareas import sprints as ts
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(ideas, "proponer",
                        lambda c, cid_, n_videos=None, n_imagenes=None, reemplaza=None, uso=None: [1, 2])
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_proponer_ideas"]({"payload": {"cliente": "acme", "campana_id": cid, "n_videos": 2, "n_imagenes": 0}})
    assert "2 ideas" in msg
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_ideas("acme", cid, n_videos=3, reemplaza=7) is True
    job_id, tipo, payload, kw = encolados[0]
    assert job_id == f"acme__campana{cid}__ideas" and tipo == "sprint_proponer_ideas"
    assert payload == {"cliente": "acme", "campana_id": cid, "n_videos": 3, "n_imagenes": None, "reemplaza": 7} and kw["max_intentos"] == 1


def _pieza_lista(datos, creative_flow, cliente="acme", estado_pieza="video_listo"):
    pid = datos.crear_persona(cliente, "P")
    tid = datos.crear_temporada(cliente, "T", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint(cliente, "S", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana(cliente, sid, pid, "espejo", tid, 1, 0)
    cp = datos.crear_idea(cliente, cid, "video", "A", "a", estado_idea="aprobada")
    cf = creative_flow.crear(cliente, [], ["E"], [], "a", 8, "", "A")
    datos.actualizar_idea(cliente, cp, cf_id=cf)
    creative_flow.actualizar(cliente, cf, estado=estado_pieza, video_url="https://r2/v.mp4")
    return sid, cid, cp, cf


def test_qa_pieza_guarda_resultado_y_error(base_temporal, monkeypatch):
    import creative_flow
    import tareas
    from sprints import datos, qa
    from tareas import sprints as ts
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {"score": 80, "checks": {}, "veredicto": "pasa", "modelo": "m", "costo_usd": 0.02, "evaluado_en": "x"})
    tareas.cargar_todas()
    assert ts.job_id_qa("acme", cp) == f"acme__cp{cp}__qa"
    msg = tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    assert datos.idea("acme", cp)["qa"]["veredicto"] == "pasa" and "pasa" in msg
    assert any(e["tipo"] == "qa_evaluada" for e in datos.eventos("acme", sid))
    def rompe(*a, **k):
        raise RuntimeError("visión caída")
    monkeypatch.setattr(qa, "evaluar", rompe)
    datos.actualizar_idea("acme", cp, qa=None)
    with pytest.raises(RuntimeError):
        tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    # F5: queda un marcador terminal (la periódica no vuelve a encolar) y la
    # excepción sigue subiendo para que la cola agote sus propios intentos.
    marca = datos.idea("acme", cp)["qa"]
    assert marca == {"veredicto": "error", "score": None, "checks": {}, "nota": "visión caída", "cf_id": cf}
    assert tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": 999}}) == "La pieza ya no existe."


def test_qa_pieza_registra_el_gasto_y_guarda_la_doctrina_en_la_sesion(base_temporal, monkeypatch):
    """Doctrina, bloque 3: el QA por fin registra su gasto real (una fila por
    intento, también si falla después de pagar) y la revisión de los 12
    puntos queda en la sesión de Crear."""
    import creative_flow
    import gastos
    import tareas
    from sprints import datos, qa
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    rev = {"video_url": "https://r2/v.mp4", "puntos": [], "resumen": "ok", "reglas": [], "origen": "sprint"}
    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {
        "score": 80, "checks": {}, "veredicto": "pasa", "modelo": "m", "costo_usd": 0.02, "evaluado_en": "x",
        "tokens_entrada": 1500, "tokens_salida": 400, "doctrina": dict(rev)})
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_qa_pieza"]({"id": 31, "intentos": 1, "payload": {"cliente": "acme", "cp_id": cp}})
    g = gastos.historial("acme", limite=1)[0]
    assert g["tipo"] == "revision" and g["referencia"] == f"qa:{cp}:t31:i1" and "doctrina" in g["detalle"]
    assert creative_flow.cargar("acme")[cf]["revision_doctrina"] == rev
    qa_guardado = datos.idea("acme", cp)["qa"]
    assert "doctrina" not in qa_guardado and "tokens_entrada" not in qa_guardado

    def falla(*a, **k):
        e = qa.AnalisisInvalido("Claude no devolvió JSON.")
        e.tokens_entrada, e.tokens_salida = 1400, 100
        raise e
    monkeypatch.setattr(qa, "evaluar", falla)
    with pytest.raises(qa.AnalisisInvalido):
        tareas.REGISTRO["sprint_qa_pieza"]({"id": 31, "intentos": 2, "payload": {"cliente": "acme", "cp_id": cp}})
    g = gastos.historial("acme", limite=1)[0]
    assert g["referencia"] == f"qa:{cp}:t31:i2" and "respuesta inválida" in g["detalle"]


def test_qa_pieza_no_revienta_si_falla_guardar_la_doctrina(base_temporal, monkeypatch):
    """Bloque 3, revisión final (I4): si guardar `revision_doctrina` en la
    sesión revienta, el QA (ya pagado y guardado) no debe reintentarse por
    eso — solo queda rastro en la bitácora."""
    import bitacora
    import creative_flow
    import gastos
    import tareas
    from sprints import datos, qa
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    rev = {"video_url": "https://r2/v.mp4", "puntos": [], "resumen": "ok", "reglas": [], "origen": "sprint"}
    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {
        "score": 80, "checks": {}, "veredicto": "pasa", "modelo": "m", "costo_usd": 0.02, "evaluado_en": "x",
        "tokens_entrada": 1500, "tokens_salida": 400, "doctrina": dict(rev)})
    original = creative_flow.actualizar

    def falla_solo_doctrina(cliente, cf_id, **campos):
        if "revision_doctrina" in campos:
            raise RuntimeError("db caída")
        return original(cliente, cf_id, **campos)
    monkeypatch.setattr(creative_flow, "actualizar", falla_solo_doctrina)
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_qa_pieza"]({"id": 31, "intentos": 1, "payload": {"cliente": "acme", "cp_id": cp}})
    assert "pasa" in msg
    assert datos.idea("acme", cp)["qa"]["veredicto"] == "pasa"          # el QA sí se guardó
    g = gastos.historial("acme", limite=1)[0]
    assert g["tipo"] == "revision"                                      # el gasto sí se registró
    filas = bitacora.leer(cliente="acme", brief_id=cf)
    assert any(f["etapa"] == "sprint_qa" and f["estado"] == "doctrina_no_guardada" for f in filas)


def test_qa_sin_doctrina_no_toca_una_revision_existente(base_temporal, monkeypatch):
    """Bloque 3, revisión final (I9): con `doctrina=None` (el QA solo, sin
    revisión útil) la sesión conserva la revisión que ya tenía — por ejemplo,
    una hecha con el botón de Crear."""
    import creative_flow
    import tareas
    from sprints import datos, qa
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    previa = {"video_url": "https://r2/v.mp4", "puntos": [], "resumen": "de antes", "reglas": [], "origen": "boton"}
    creative_flow.actualizar("acme", cf, revision_doctrina=previa)
    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {
        "score": 80, "checks": {}, "veredicto": "pasa", "modelo": "m", "costo_usd": 0.02, "evaluado_en": "x",
        "tokens_entrada": 0, "tokens_salida": 0, "doctrina": None})
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    assert creative_flow.cargar("acme")[cf]["revision_doctrina"] == previa


def test_qa_pieza_error_no_se_reencola_y_un_intento_bueno_pisa_el_marcador(base_temporal, monkeypatch):
    """F5: con el marcador `veredicto=error` la periódica ya no encola otro
    QA para esa pieza (antes lo hacía cada 5 min, descargando el video otra
    vez); un intento posterior que sí funciona sobrescribe el marcador."""
    import cola
    import creative_flow
    import tareas
    from sprints import datos, qa
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    def rompe(*a, **k):
        raise RuntimeError("x" * 500)
    monkeypatch.setattr(qa, "evaluar", rompe)
    tareas.cargar_todas()
    with pytest.raises(RuntimeError):
        tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    assert len(datos.idea("acme", cp)["qa"]["nota"]) == 300
    encolados = []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append(tipo) or 1)
    tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert encolados == []
    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {"score": 85, "checks": {}, "veredicto": "pasa"})
    tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    assert datos.idea("acme", cp)["qa"]["veredicto"] == "pasa"


def test_encolar_qa_usa_el_worker(base_temporal, monkeypatch):
    import trabajos
    from tareas import sprints as ts
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_qa("acme", 5) is True
    job_id, tipo, payload, kw = encolados[0]
    assert job_id == "acme__cp5__qa" and tipo == "sprint_qa_pieza" and payload == {"cliente": "acme", "cp_id": 5}
    assert kw["max_intentos"] == 3 and kw["cliente"] == "acme"


def test_qa_pieza_descarta_el_resultado_si_la_pieza_se_regenero(base_temporal, monkeypatch):
    """F2: el QA evalúa la sesión con la que se encoló; si mientras tanto la
    idea apunta a una sesión nueva (Regenerar), el veredicto viejo no se le
    pega a la pieza nueva — `qa` sigue en None para que la periódica evalúe la
    nueva, y queda rastro en la bitácora."""
    import bitacora
    import creative_flow
    import tareas
    from sprints import datos, qa
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    nuevo = creative_flow.crear("acme", [], ["E"], [], "b", 8, "", "A")
    def evaluar_y_regenerar(c, i, e, ca, umbral=None):
        datos.actualizar_idea("acme", cp, cf_id=nuevo, qa=None)      # el usuario pulsó Regenerar en medio
        return {"score": 80, "checks": {}, "veredicto": "pasa", "modelo": "m", "costo_usd": 0.02, "evaluado_en": "x"}
    monkeypatch.setattr(qa, "evaluar", evaluar_y_regenerar)
    filas = []
    monkeypatch.setattr(bitacora, "registrar", lambda *a, **k: filas.append(a))
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    assert datos.idea("acme", cp)["qa"] is None and datos.idea("acme", cp)["cf_id"] == nuevo
    assert "regener" in msg.lower() and any("regenerada" in str(f) for f in filas)
    assert not any(e["tipo"] == "qa_evaluada" for e in datos.eventos("acme", sid))
    # sin regeneración en medio, el resultado se guarda con la sesión evaluada adentro
    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {"score": 80, "checks": {}, "veredicto": "pasa"})
    tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    assert datos.idea("acme", cp)["qa"]["cf_id"] == nuevo


def test_qa_pendientes_encola_y_avisa_fin_de_lote(base_temporal, monkeypatch):
    import cola
    import creative_flow
    import notificaciones
    import tareas
    from sprints import datos
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    datos.actualizar_sprint("acme", sid, extra={"lote_en_curso": True})
    sid2, cid2, cp2, cf2 = _pieza_lista(datos, creative_flow, cliente="otro", estado_pieza="video_generando")
    datos.actualizar_sprint("otro", sid2, extra={"lote_en_curso": True})
    encolados, avisos = [], []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append((tipo, payload, kw.get("job_id"))) or 1)
    monkeypatch.setattr(notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: avisos.append((c, tipo, asunto)) or False)
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert [(t, p["cp_id"]) for t, p, _ in encolados] == [("sprint_qa_pieza", cp)]
    assert avisos == [("acme", "sprint_lote", "Lote terminado: S")] and "1 pieza" in msg
    assert datos.sprint("acme", sid)["extra"]["lote_en_curso"] is False
    assert datos.sprint("otro", sid2)["extra"]["lote_en_curso"] is True
    assert datos.sprint("acme", sid)["eventos"][0]["tipo"] == "lote_terminado"
    datos.actualizar_idea("acme", cp, qa={"veredicto": "pasa"})
    encolados.clear()
    tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert encolados == []


def test_qa_pendientes_no_encola_qa_en_un_proyecto_que_cobra_sin_saldo(base_temporal, monkeypatch):
    """Cobros (2026-10-08): el QA cobra; sin saldo el respaldo del worker la
    dejaría en error y la periódica la volvería a encolar cada 5 min."""
    import cola
    import creative_flow
    import db
    import tareas
    from cobros import libro
    from sprints import datos
    _, _, cp, _ = _pieza_lista(datos, creative_flow)
    _, _, cp_otro, _ = _pieza_lista(datos, creative_flow, cliente="otro")
    encolados = []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append((payload["cliente"], payload["cp_id"])) or 1)
    tareas.cargar_todas()
    libro.configurar("acme", usuario="admin", cobrar=True)
    tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert encolados == [("otro", cp_otro)]   # «otro» no cobra: como siempre

    encolados.clear()
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 1000, "ajuste", usuario="admin", detalle="prueba")
    tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert sorted(encolados) == [("acme", cp), ("otro", cp_otro)]


def test_qa_pendientes_no_avisa_con_idea_reservando(base_temporal, monkeypatch):
    """Fix round 1, hallazgo 2: una idea con una reserva VIVA (cf_id
    "reservando_<cp>_<epoch>", otro lote está armando su sesión de Crear) no
    tiene fila en `pieza` — queda con estado None. Cuenta como viva: el lote
    no se reporta terminado (bandera encendida, sin aviso)."""
    import creative_flow
    import notificaciones
    import tareas
    from sprints import datos, produccion
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)  # una pieza "listo"
    cp2 = datos.crear_idea("acme", cid, "video", "B", "b", estado_idea="aprobada")
    datos.actualizar_idea("acme", cp2, cf_id=produccion.reserva_placeholder(cp2))  # reserva fresca
    datos.actualizar_sprint("acme", sid, extra={"lote_en_curso": True})
    avisos = []
    monkeypatch.setattr(notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: avisos.append((c, tipo, asunto)) or False)
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert avisos == []
    assert datos.sprint("acme", sid)["extra"]["lote_en_curso"] is True


def test_qa_pendientes_cierra_el_lote_con_una_reserva_vencida(base_temporal, monkeypatch):
    """F1: una reserva vencida (el proceso murió entre reservar y crear la
    sesión; formato viejo sin hora incluido) ya no es una pieza viva: el lote
    termina (bandera apagada + aviso) en vez de quedar colgado para siempre."""
    import creative_flow
    import notificaciones
    import tareas
    from sprints import datos
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    cp2 = datos.crear_idea("acme", cid, "video", "B", "b", estado_idea="aprobada")
    datos.actualizar_idea("acme", cp2, cf_id="reservando_9")      # formato viejo: vencida
    datos.actualizar_sprint("acme", sid, extra={"lote_en_curso": True})
    avisos = []
    monkeypatch.setattr(notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: avisos.append((c, tipo, asunto)) or False)
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert avisos == [("acme", "sprint_lote", "Lote terminado: S")]
    assert datos.sprint("acme", sid)["extra"]["lote_en_curso"] is False
    assert datos.idea("acme", cp2)["sin_sesion"] is True


def test_periodica_qa_registrada():
    import worker
    assert ("sprint_qa_pendientes", 300) in worker.PERIODICAS


def test_empaquetar_tarea(base_temporal, monkeypatch):
    import tareas
    import trabajos
    from sprints import entrega
    from tareas import sprints as ts
    monkeypatch.setattr(entrega, "empaquetar", lambda c, sid, descargar=None: {"url": "https://r2/z.zip", "n": 3, "creado_en": "x"})
    tareas.cargar_todas()
    assert "3 pieza" in tareas.REGISTRO["sprint_empaquetar"]({"payload": {"cliente": "acme", "sprint_id": 1}})
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_zip("acme", 4) is True and encolados[0][0] == "acme__sprint4__zip" and encolados[0][3]["max_intentos"] == 2


def test_job_id_y_encolar_sugerir_biblioteca(base_temporal, monkeypatch):
    import trabajos
    from tareas import sprints as ts
    assert ts.job_id_sugerir_biblioteca("acme", 9) == "acme__campana9__sugerir_biblioteca"
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_sugerir_biblioteca("acme", 9) is True
    job_id, tipo, payload, kw = encolados[0]
    assert job_id == "acme__campana9__sugerir_biblioteca" and tipo == "referentes_sugerir_ia"
    assert payload == {"cliente": "acme", "campana_id": 9} and kw["max_intentos"] == 1 and kw["cliente"] == "acme"


def test_ejecutar_sugerir_biblioteca_guarda_sugerencias(base_temporal, monkeypatch):
    import gastos
    import tareas
    import referentes.sugerir as referentes_sugerir
    from sprints import datos
    sid, cid, rid = _referencia(datos)
    enfoques = []
    monkeypatch.setattr(referentes_sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: (
        enfoques.append(enfoque) or [{"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2}], []))
    textos = []
    monkeypatch.setattr(referentes_sugerir, "sugerir_ia", lambda cands, p, pr, t, objetivo, enfoque_texto="", idioma="es": (
        textos.append((p, t, enfoque_texto)) or ([{"referente_id": 5, "razon": "encaja"}], 100, 20)))
    tareas.cargar_todas()
    tarea = {"id": 1, "payload": {"cliente": "acme", "campana_id": cid}}
    resultado = tareas.REGISTRO["referentes_sugerir_ia"](tarea)
    assert "1" in resultado
    c = datos.campana("acme", cid)
    assert c["extra"]["sugerencias_ia"] == [{"referente_id": 5, "razon": "encaja"}]
    filas = [f for f in gastos.historial("acme") if f["tipo"] == "sugerir_ia"]
    assert len(filas) == 1 and filas[0]["usd"] > 0
    # Sprint nuevo: para todos los países, en inglés (2026-09-27).
    assert enfoques[0]["etapa"] == "TOF" and enfoques[0]["idioma"] == "en"
    assert "idioma de la audiencia: inglés" in textos[0][2]


def test_ejecutar_sugerir_biblioteca_sin_candidatos(base_temporal, monkeypatch):
    import tareas
    import referentes.sugerir as referentes_sugerir
    from sprints import datos
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(referentes_sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: ([], []))
    tareas.cargar_todas()
    tarea = {"id": 1, "payload": {"cliente": "acme", "campana_id": cid}}
    resultado = tareas.REGISTRO["referentes_sugerir_ia"](tarea)
    assert "biblioteca" in resultado.lower() or "candidatos" in resultado.lower()
    c = datos.campana("acme", cid)
    assert not (c.get("extra") or {}).get("sugerencias_ia")


def test_ejecutar_sugerir_biblioteca_respuesta_invalida_registra_gasto_y_relanza(base_temporal, monkeypatch):
    """Autorrevisión: una respuesta de Claude que no parsea (`SugerenciaInvalida`)
    igual cobra los tokens ya gastados, y la excepción sigue subiendo para que
    la cola marque la tarea en error en vez de darla por buena en silencio."""
    import gastos
    import tareas
    import referentes.sugerir as referentes_sugerir
    from sprints import datos
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(referentes_sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: (
        [{"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2}], []))
    def rompe(cands, p, pr, t, objetivo, enfoque_texto="", idioma="es"):
        e = referentes_sugerir.SugerenciaInvalida("no parsea")
        e.tokens_entrada, e.tokens_salida = 90, 15
        raise e
    monkeypatch.setattr(referentes_sugerir, "sugerir_ia", rompe)
    tareas.cargar_todas()
    tarea = {"id": 2, "payload": {"cliente": "acme", "campana_id": cid}}
    with pytest.raises(referentes_sugerir.SugerenciaInvalida):
        tareas.REGISTRO["referentes_sugerir_ia"](tarea)
    c = datos.campana("acme", cid)
    assert not (c.get("extra") or {}).get("sugerencias_ia")
    filas = [f for f in gastos.historial("acme") if f["tipo"] == "sugerir_ia"]
    assert len(filas) == 1 and filas[0]["usd"] > 0 and filas[0]["detalle"] == "respuesta inválida"


def test_sugerir_biblioteca_le_pasa_la_consciencia_de_la_persona(base_temporal, monkeypatch):
    import tareas
    import referentes.sugerir as referentes_sugerir
    from sprints import datos
    sid, cid, rid = _referencia(datos)
    datos.actualizar_persona("acme", datos.campana("acme", cid)["persona_id"],
                             extra={"conciencia": {"nivel": "consciente_del_problema", "detalle": "x"}})
    monkeypatch.setattr(referentes_sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: (
        [{"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2}], []))
    visto = {}

    def falso(cands, persona_texto, producto_texto, temporada_texto, objetivo, enfoque_texto="", idioma="es"):
        visto["persona"] = persona_texto
        return [], 10, 5
    monkeypatch.setattr(referentes_sugerir, "sugerir_ia", falso)
    tareas.cargar_todas()
    tareas.REGISTRO["referentes_sugerir_ia"]({"id": 2, "payload": {"cliente": "acme", "campana_id": cid}})
    assert "consciente del problema" in visto["persona"]


def test_reescribir_idea_registra_el_gasto_real(base_temporal, monkeypatch):
    """Doctrina, bloque 2 (§3.5): pagada, gasto tipo «ideas» con los tokens
    reales — también cuando la respuesta no sirvió."""
    import gastos
    import tareas
    from sprints import datos, ideas
    tareas.cargar_todas()
    monkeypatch.setattr(ideas, "reescribir", lambda cliente, cp_id: (1000, 2000))
    tareas.REGISTRO["sprint_reescribir_idea"]({"id": 7, "payload": {"cliente": "acme", "cp_id": 3}})
    g = gastos.historial("acme", limite=1)[0]
    assert g["tipo"] == "ideas" and g["referencia"] == "idea:reescribir:3:t7" and g["usd"] > 0

    def falla(cliente, cp_id):
        e = ideas.AnalisisInvalido("Claude no devolvió JSON.")
        e.tokens_entrada, e.tokens_salida = 400, 50
        raise e
    monkeypatch.setattr(ideas, "reescribir", falla)
    with pytest.raises(ideas.AnalisisInvalido):
        tareas.REGISTRO["sprint_reescribir_idea"]({"id": 8, "payload": {"cliente": "acme", "cp_id": 3}})
    g = gastos.historial("acme", limite=1)[0]
    assert g["referencia"] == "idea:reescribir:3:t8" and "inválida" in g["detalle"]


def test_reescribir_idea_con_pieza_registra_su_propio_detalle(base_temporal, monkeypatch):
    """Doctrina, bloque 2 (revisión final #3): cuando «Generar lote» se
    adelanta, el gasto queda con su propio detalle, distinto del de una
    respuesta inválida cualquiera."""
    import gastos
    import tareas
    from sprints import ideas
    tareas.cargar_todas()

    def con_pieza(cliente, cp_id):
        e = ideas.IdeaConPieza("La idea ya tiene una pieza generada; no se reescribió.")
        e.tokens_entrada, e.tokens_salida = 400, 50
        raise e
    monkeypatch.setattr(ideas, "reescribir", con_pieza)
    with pytest.raises(ideas.IdeaConPieza):
        tareas.REGISTRO["sprint_reescribir_idea"]({"id": 9, "payload": {"cliente": "acme", "cp_id": 3}})
    g = gastos.historial("acme", limite=1)[0]
    assert g["referencia"] == "idea:reescribir:3:t9" and g["detalle"] == "reescribir idea · la idea ya tenía pieza"


def test_sugerir_biblioteca_usa_el_enfoque_de_la_campana(base_temporal, monkeypatch):
    import tareas
    import referentes.sugerir as referentes_sugerir
    from referentes import datos as rdatos
    from sprints import datos
    sid, cid, rid = _referencia(datos)
    rdatos.familia_asegurar("UGC", "")
    datos.actualizar_sprint("acme", sid, idioma="en", marcas="Crocs", momento="Hot Sale")
    datos.actualizar_campana("acme", cid, consciencia="consciente_del_problema", dolor="pies fríos", familias=["UGC"])
    vistos = {}
    monkeypatch.setattr(referentes_sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: (
        vistos.update(enfoque=enfoque) or [{"id": 5, "familia": "UGC"}], []))
    monkeypatch.setattr(referentes_sugerir, "sugerir_ia", lambda cands, p, pr, t, objetivo, enfoque_texto="", idioma="es": (
        vistos.update(persona=p, temporada=t, enfoque_texto=enfoque_texto) or ([], 10, 5)))
    tareas.cargar_todas()
    tareas.REGISTRO["referentes_sugerir_ia"]({"id": 1, "payload": {"cliente": "acme", "campana_id": cid}})
    e = vistos["enfoque"]
    assert (e["consciencia"], e["familias"], e["idioma"], e["marcas"]) == ("consciente_del_problema", ["UGC"], "en", [{"nombre": "Crocs"}])
    assert "pies fríos" in vistos["persona"] and "consciente del problema" in vistos["persona"]
    assert vistos["temporada"] == "Hot Sale"
    assert "UGC" in vistos["enfoque_texto"] and "Crocs" in vistos["enfoque_texto"] and "inglés" in vistos["enfoque_texto"]


def test_proponer_ideas_registra_el_gasto_real(base_temporal, monkeypatch):
    import gastos
    import tareas
    from sprints import datos, ideas
    sid, cid, rid = _referencia(datos)

    def proponer(c, cid_, n_videos=None, n_imagenes=None, reemplaza=None, uso=None):
        uso["entrada"] += 5000
        uso["salida"] += 2000
        return [11, 12]
    monkeypatch.setattr(ideas, "proponer", proponer)
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_proponer_ideas"]({"id": 7, "payload": {"cliente": "acme", "campana_id": cid}})
    filas = [f for f in gastos.historial("acme") if f["tipo"] == "ideas"]
    assert len(filas) == 1 and filas[0]["usd"] > 0 and filas[0]["referencia"] == f"idea:proponer:{cid}:t7"


def test_proponer_ideas_registra_lo_pagado_si_falla(base_temporal, monkeypatch):
    import pytest
    import gastos
    import tareas
    from sprints import datos, ideas
    sid, cid, rid = _referencia(datos)

    def proponer(c, cid_, n_videos=None, n_imagenes=None, reemplaza=None, uso=None):
        uso["entrada"] += 3000
        raise ideas.AnalisisInvalido("Claude no devolvió JSON.")
    monkeypatch.setattr(ideas, "proponer", proponer)
    tareas.cargar_todas()
    with pytest.raises(ideas.AnalisisInvalido):
        tareas.REGISTRO["sprint_proponer_ideas"]({"id": 8, "payload": {"cliente": "acme", "campana_id": cid}})
    filas = [f for f in gastos.historial("acme") if f["tipo"] == "ideas"]
    assert len(filas) == 1 and "no sirvió" in filas[0]["detalle"]


def test_proponer_ideas_sin_llamadas_no_registra_gasto(base_temporal, monkeypatch):
    import gastos
    import tareas
    from sprints import datos, ideas
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(ideas, "proponer", lambda c, cid_, n_videos=None, n_imagenes=None, reemplaza=None, uso=None: [])
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_proponer_ideas"]({"id": 9, "payload": {"cliente": "acme", "campana_id": cid}})
    assert not [f for f in gastos.historial("acme") if f["tipo"] == "ideas"]


def test_encolar_ideas_no_se_reintenta_sola(base_temporal, monkeypatch):
    from tareas import sprints as ts
    vistos = []
    monkeypatch.setattr(ts.trabajos, "encolar", lambda job_id, tipo, payload, **kw: vistos.append(kw) or True)
    ts.encolar_ideas("acme", 5)
    assert vistos[0]["max_intentos"] == 1

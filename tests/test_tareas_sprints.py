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
    monkeypatch.setattr(analisis, "analizar", lambda ref, marca="": {"resumen": "ok", "paleta": ["#000"]})
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
    def rompe(ref, marca=""):
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
    monkeypatch.setattr(ideas, "proponer", lambda c, cid_, n_videos=None, n_imagenes=None, reemplaza=None: [1, 2])
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_proponer_ideas"]({"payload": {"cliente": "acme", "campana_id": cid, "n_videos": 2, "n_imagenes": 0}})
    assert "2 ideas" in msg
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_ideas("acme", cid, n_videos=3, reemplaza=7) is True
    job_id, tipo, payload, kw = encolados[0]
    assert job_id == f"acme__campana{cid}__ideas" and tipo == "sprint_proponer_ideas"
    assert payload == {"cliente": "acme", "campana_id": cid, "n_videos": 3, "n_imagenes": None, "reemplaza": 7} and kw["max_intentos"] == 2


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
    monkeypatch.setattr(referentes_sugerir, "candidatos", lambda cliente_, etapa, excluir, limite=60: [
        {"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2},
    ])
    monkeypatch.setattr(referentes_sugerir, "sugerir_ia", lambda cands, p, pr, t, objetivo: (
        [{"referente_id": 5, "razon": "encaja"}], 100, 20))
    tareas.cargar_todas()
    tarea = {"id": 1, "payload": {"cliente": "acme", "campana_id": cid}}
    resultado = tareas.REGISTRO["referentes_sugerir_ia"](tarea)
    assert "1" in resultado
    c = datos.campana("acme", cid)
    assert c["extra"]["sugerencias_ia"] == [{"referente_id": 5, "razon": "encaja"}]
    filas = [f for f in gastos.historial("acme") if f["tipo"] == "sugerir_ia"]
    assert len(filas) == 1 and filas[0]["usd"] > 0


def test_ejecutar_sugerir_biblioteca_sin_candidatos(base_temporal, monkeypatch):
    import tareas
    import referentes.sugerir as referentes_sugerir
    from sprints import datos
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(referentes_sugerir, "candidatos", lambda cliente_, etapa, excluir, limite=60: [])
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
    monkeypatch.setattr(referentes_sugerir, "candidatos", lambda cliente_, etapa, excluir, limite=60: [
        {"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2},
    ])
    def rompe(cands, p, pr, t, objetivo):
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
    monkeypatch.setattr(referentes_sugerir, "candidatos", lambda cliente_, etapa, excluir, limite=60: [
        {"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2}])
    visto = {}

    def falso(cands, persona_texto, producto_texto, temporada_texto, objetivo):
        visto["persona"] = persona_texto
        return [], 10, 5
    monkeypatch.setattr(referentes_sugerir, "sugerir_ia", falso)
    tareas.cargar_todas()
    tareas.REGISTRO["referentes_sugerir_ia"]({"id": 2, "payload": {"cliente": "acme", "campana_id": cid}})
    assert "consciente del problema" in visto["persona"]

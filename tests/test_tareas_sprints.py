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

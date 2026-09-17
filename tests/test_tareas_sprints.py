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

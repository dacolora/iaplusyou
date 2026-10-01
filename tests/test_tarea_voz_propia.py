"""Tarea voz_propia_crear (spec 2026-09-30 §3)."""


def test_tarea_registrada_y_job_por_proyecto():
    import tareas
    tareas.cargar_todas()
    assert "voz_propia_crear" in tareas.REGISTRO
    import tareas.voces_propias as tv
    assert tv.job_id("acme") == "acme__voz_propia"
    assert [e[0] for e in tv.ETAPAS] == ["Creando la voz", "Estrenando la voz", "Guardando"]


def test_tarea_crea_la_voz_con_mensajes_fijos(monkeypatch):
    import tareas.voces_propias as tv
    vistos, etapas = [], []
    monkeypatch.setattr(tv.trabajos, "reportar", lambda jid, etapa=None, **k: etapas.append(etapa))

    def _crear(cliente, payload, ref_sufijo="", reportar=None):
        vistos.append((cliente, payload, ref_sufijo))
        reportar(1)
        reportar(2)
        return ({"forma": "clonada", "nombre": "Daniel secreto"}, True)
    monkeypatch.setattr(tv.voces_propias, "crear", _crear)
    payload = {"cliente": "acme", "forma": "clonar", "nombre": "Daniel secreto"}
    msg = tv.ejecutar({"id": 7, "job_id": "acme__voz_propia", "payload": payload})
    assert msg == tv.MENSAJES["clonada"] and "secreto" not in msg
    assert vistos == [("acme", payload, ":t7")]
    assert etapas == ["Creando la voz", "Estrenando la voz", "Guardando"]
    monkeypatch.setattr(tv.voces_propias, "crear", lambda *a, **k: ({"forma": "disenada"}, True))
    assert tv.ejecutar({"id": 8, "payload": {"cliente": "acme"}}) == tv.MENSAJES["disenada"]
    monkeypatch.setattr(tv.voces_propias, "crear", lambda *a, **k: ({"forma": "disenada"}, False))
    assert tv.ejecutar({"id": 9, "payload": {"cliente": "acme"}}) == tv.MENSAJES["sin_estrenar"]

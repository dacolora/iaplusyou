import json

import pytest

IDEA_V = {"titulo": "Espejo al amanecer", "tipo": "video", "escena": "La cámara rodea el espejo redondo mientras la luz del amanecer entra por la ventana.",
          "sonido": "pájaros lejanos, brisa", "enfoque": "producto", "gancho": "Luz que despierta", "referencias_ids": [1, 999],
          "duracion_s": 9, "plataformas": ["instagram", "tiktok", "otra"]}
IDEA_I = {"titulo": "Detalle del marco", "tipo": "imagen", "escena": "Primer plano del marco metálico con reflejo cálido.",
          "sonido": "", "enfoque": "rarísimo", "gancho": "Detalle que enamora", "referencias_ids": [], "duracion_s": None,
          "plataformas": ["instagram"]}


def test_parsear_valida_y_normaliza():
    from sprints import ideas
    salida = ideas.parsear(json.dumps({"ideas": [IDEA_V, IDEA_I, {"titulo": "sin escena", "tipo": "video"}]}),
                           referencias_ids_validos={1, 2}, duraciones=(5, 8, 10, 12))
    assert len(salida) == 2
    v, i = salida
    assert v["referencias_ids"] == [1] and v["duracion_s"] == 8 and v["plataformas"] == ["instagram", "tiktok"]
    assert i["enfoque"] == "producto" and i["duracion_s"] is None and i["sonido"] == ""
    with pytest.raises(ideas.AnalisisInvalido):
        ideas.parsear("nada", set(), (8,))
    with pytest.raises(ideas.AnalisisInvalido):
        ideas.parsear(json.dumps({"ideas": []}), set(), (8,))


def test_faltantes_descuenta_vivas():
    from sprints import ideas
    c = {"n_videos": 3, "n_imagenes": 2, "ideas": [
        {"tipo": "video", "estado_idea": "aprobada"}, {"tipo": "video", "estado_idea": "propuesta"},
        {"tipo": "video", "estado_idea": "descartada"}, {"tipo": "imagen", "estado_idea": "aprobada"}]}
    assert ideas.faltantes(c) == (1, 1)
    assert ideas.faltantes({"n_videos": 0, "n_imagenes": 1, "ideas": [{"tipo": "imagen", "estado_idea": "aprobada"}] * 3}) == (0, 0)


def _ctx(monkeypatch, datos, con_ref=True):
    import catalogo_productos, marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural, sin saturar.")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo con luz", "regla": "Idéntico."})
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    pid = datos.crear_persona("acme", "Cliente Premium", resumen="Busca calidad", descripcion="Renueva su casa", tono="cercano",
                              senales_visuales=["cocina moderna"])
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos", mood_visual={"paleta": ["#B3001B"], "luz": "cálida"})
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    rid = None
    if con_ref:
        rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz lateral", intencion=["iluminacion"])
        datos.actualizar_referencia("acme", rid, analisis={"resumen": "Espejo con luz lateral cálida", "paleta": ["#F2E9E4"], "movimiento": "sin movimiento"}, analisis_estado="listo")
    return sid, cid, rid


def test_armar_prompt_incluye_todo_el_contexto(base_temporal, monkeypatch):
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    datos.crear_idea("acme", cid, "video", "Ya existe", "x")
    datos.crear_idea("acme", cid, "video", "Descartada fea", "y", estado_idea="descartada")
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    p = ideas.armar_prompt(ctx, 1, 1)
    for frag in ("Vidrios Sol", "Cliente Premium", "Busca calidad", "cocina moderna", "Espejo LED", "redondo con luz", "Navidad",
                 "regalos", "#B3001B", "Luz natural", f"ref {rid}", "Espejo con luz lateral cálida", "Ya existe", "Descartada fea",
                 "1 ideas de VIDEO", "1 ideas de IMAGEN"):
        assert frag in p, frag
    assert "Producto en primer plano" in p     # banco de prompts como ejemplos de estilo


def test_proponer_crea_ideas_y_reemplaza(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    respuestas = [json.dumps({"ideas": [dict(IDEA_V, referencias_ids=[rid]), IDEA_I]})]
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: respuestas.pop(0))
    creadas = ideas.proponer("acme", cid)          # faltantes: 2 videos, 1 imagen → pide 2 y 1; Claude devuelve 1 y 1
    assert len(creadas) == 2
    lista = datos.ideas("acme", cid)
    assert lista[0]["titulo"] == "Espejo al amanecer" and lista[0]["referencias_ids"] == [rid] and lista[0]["duracion_s"] == 8.0
    assert lista[1]["tipo"] == "imagen" and lista[1]["enfoque"] == "producto"
    respuestas.append(json.dumps({"ideas": [dict(IDEA_V, titulo="Otra versión")]}))
    nuevas = ideas.proponer("acme", cid, reemplaza=lista[0]["id"])
    assert len(nuevas) == 1
    assert datos.idea("acme", lista[0]["id"])["estado_idea"] == "descartada"
    assert datos.idea("acme", nuevas[0])["titulo"] == "Otra versión" and datos.idea("acme", nuevas[0])["tipo"] == "video"
    assert any(e["tipo"] == "ideas_propuestas" for e in datos.eventos("acme", sid))


def test_proponer_sin_faltantes_no_llama(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    for _ in range(2):
        datos.crear_idea("acme", cid, "video", "V", "v", estado_idea="aprobada")
    datos.crear_idea("acme", cid, "imagen", "I", "i", estado_idea="aprobada")
    monkeypatch.setattr(analisis, "_llamar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía llamar")))
    assert ideas.proponer("acme", cid) == []
    with pytest.raises(datos.ErrorDatos):
        ideas.proponer("acme", 999)

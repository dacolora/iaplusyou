import json

import pytest

CHECKS_OK = {"consistencia_visual": {"ok": True, "nota": "coherente"}, "presencia_marca": {"ok": True, "nota": "logo visible"},
             "compatibilidad_campana": {"ok": True, "nota": "espejo en escena"}, "calidad_minima": {"ok": True, "nota": "limpio"}}


def test_veredicto_puro():
    from sprints import qa
    todos = {k: {"ok": True, "nota": ""} for k in qa.CHECKS}
    assert qa.veredicto(85, todos, 70) == "pasa"
    assert qa.veredicto(60, todos, 70) == "revisar"
    assert qa.veredicto(90, dict(todos, presencia_marca={"ok": False, "nota": "sin logo"}), 70) == "revisar"
    assert qa.veredicto(95, dict(todos, calidad_minima={"ok": False, "nota": "manos"}), 70) == "falla"
    assert qa.veredicto(95, dict(todos, formato={"ok": False, "nota": "16:9"}), 70) == "falla"


def test_parsear_exige_score_y_cuatro_checks():
    from sprints import qa
    r = qa.parsear(json.dumps({"score": 82, "checks": CHECKS_OK}))
    assert r["score"] == 82 and set(r["checks"]) == set(qa.CHECKS) - {"formato"}
    r = qa.parsear(json.dumps({"score": 150, "checks": dict(CHECKS_OK, calidad_minima={"ok": "sí", "nota": 5})}))
    assert r["score"] == 100 and r["checks"]["calidad_minima"] == {"ok": True, "nota": "5"}
    with pytest.raises(qa.AnalisisInvalido):
        qa.parsear(json.dumps({"score": 80, "checks": {"consistencia_visual": {"ok": True}}}))
    with pytest.raises(qa.AnalisisInvalido):
        qa.parsear("nada")


def test_formato_con_ffprobe_falso(monkeypatch, tmp_path):
    from final_edition import cortes
    from sprints import qa
    v = tmp_path / "v.mp4"; v.write_bytes(b"x")
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {"duration": "8.2"}, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
    assert qa.formato(str(v), "video", 8, "9:16") == (True, "9:16, 8.2 s")
    ok, nota = qa.formato(str(v), "video", 12, "9:16")
    assert ok is False and "duración" in nota
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {}, "streams": [{"codec_type": "video", "width": 1280, "height": 720}]})
    ok, nota = qa.formato(str(v), "imagen", None, "9:16")
    assert ok is False and "16:9" in nota
    assert qa.formato(None, "video", 8, "9:16") == (True, "sin archivo local; formato no verificado")


def test_evaluar_arma_prompt_y_mezcla_formato(base_temporal, monkeypatch, tmp_path):
    import marca
    from final_edition import cortes
    from sprints import analisis, datos, qa
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural.")
    pid = datos.crear_persona("acme", "Premium", resumen="Busca calidad")
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos")
    sid = datos.crear_sprint("acme", "S", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz")
    datos.actualizar_referencia("acme", rid, analisis={"resumen": "luz lateral cálida", "paleta": ["#FFF"]}, analisis_estado="listo")
    cp = datos.crear_idea("acme", cid, "video", "Amanecer", "rodea", estado_idea="aprobada", duracion_s=8)
    v = tmp_path / "v.mp4"; v.write_bytes(b"x")
    from doctrina import revisor
    monkeypatch.setattr(revisor, "duracion", lambda ruta: 8.0)
    monkeypatch.setattr(revisor, "fotogramas", lambda ruta, ts: [(t, b"f") for t in ts])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {"duration": "8.0"}, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
    capturado = {}
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: capturado.update(
        c=content, m=max_tokens, s=system) or (json.dumps({"score": 88, "checks": CHECKS_OK}), 1000, 200))
    entry = {"tipo": "video", "video_local": str(v), "video_url": "https://r2/v.mp4", "aspect_ratio": "9:16", "duracion_objetivo": 8, "modelo": "wan3"}
    r = qa.evaluar("acme", datos.idea("acme", cp), entry, datos.campana("acme", cid), umbral=70)
    assert r["veredicto"] == "pasa" and r["score"] == 88 and r["checks"]["formato"] == {"ok": True, "nota": "9:16, 8.0 s"}
    assert r["modelo"] and r["evaluado_en"] and r["costo_usd"] > 0
    assert (r["tokens_entrada"], r["tokens_salida"]) == (1000, 200) and r["doctrina"] is None   # sin «doctrina» en la respuesta
    texto = capturado["c"][0]["text"]
    for frag in ("Premium", "Busca calidad", "Navidad", "Luz natural", "luz lateral cálida", "Amanecer", "rodea",
                 "DATOS de la pieza", '"doctrina"'):
        assert frag in texto, frag
    assert capturado["m"] == qa.MAX_TOKENS and "Revisar" in capturado["s"][0]["text"]
    assert len([b for b in capturado["c"] if b["type"] == "image"]) == 4                       # 0,3 · 3 · 6 · 7,7 s
    assert "Segundo 0,3:" in [b.get("text") for b in capturado["c"]]
    # Imagen sin archivo local: usa la URL y formato no verificado.
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: capturado.update(
        c=content) or (json.dumps({"score": 50, "checks": CHECKS_OK}), 800, 100))
    r2 = qa.evaluar("acme", datos.idea("acme", cp), {"tipo": "imagen", "video_url": "https://r2/i.png", "video_local": "/no/existe.png"}, datos.campana("acme", cid))
    assert r2["veredicto"] == "revisar" and r2["checks"]["formato"]["ok"] is True
    assert [b for b in capturado["c"] if b["type"] == "image"][0]["source"] == {"type": "url", "url": "https://r2/i.png"}


def test_evaluar_borra_el_temporal_aunque_falle_la_vision(base_temporal, monkeypatch, tmp_path):
    """Fix round 1, hallazgo 1: si `analisis._llamar` (los dos intentos)
    falla, el archivo temporal que bajó `archivo_local` no debe quedar
    huérfano en el temp dir — sprint_qa_pieza reintenta hasta 3 veces."""
    from sprints import analisis, datos, qa
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    sid = datos.crear_sprint("acme", "S", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    v = tmp_path / "qa_temp.mp4"; v.write_bytes(b"x")
    monkeypatch.setattr(qa, "archivo_local", lambda entry: str(v))
    def rompe(content, max_tokens=700, system=None):
        raise analisis.AnalisisInvalido("Claude no devolvió JSON.")
    monkeypatch.setattr(analisis, "_llamar_contando", rompe)
    entry = {"tipo": "imagen", "video_url": "https://r2/i.png"}
    idea = {"titulo": "Amanecer", "escena": "rodea"}
    with pytest.raises(qa.AnalisisInvalido):
        qa.evaluar("acme", idea, entry, datos.campana("acme", cid))
    assert not v.exists()


def _doctrina_ok():
    puntos = [{"n": n, "estado": "pasa", "detalle": "", "donde": ""} for n in range(1, 13)]
    puntos[0] = {"n": 1, "estado": "mejorar", "detalle": "El gancho tarda en aparecer.", "donde": "segundo 3"}
    return {"puntos": puntos, "resumen": "Adelanta el gancho."}


def _campana_qa(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    sid = datos.crear_sprint("acme", "S", "2026-10-01", "2026-10-31")
    return datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)


def test_evaluar_trae_la_revision_de_la_doctrina(base_temporal, monkeypatch):
    """Doctrina, bloque 3: la misma llamada del QA contesta los 12 puntos."""
    from sprints import analisis, datos, qa
    cid = _campana_qa(datos)
    respuesta = json.dumps({"score": 80, "checks": CHECKS_OK, "doctrina": _doctrina_ok()})
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: (respuesta, 900, 300))
    entry = {"tipo": "imagen", "video_url": "https://r2/i.png"}
    r = qa.evaluar("acme", {"titulo": "A", "escena": "a"}, entry, datos.campana("acme", cid))
    rev = r["doctrina"]
    assert rev["origen"] == "sprint" and rev["video_url"] == "https://r2/i.png" and len(rev["puntos"]) == 12
    assert rev["resumen"] == "Adelanta el gancho." and rev["usd"] == r["costo_usd"] > 0 and rev["reglas"] == []
    # Una «doctrina» que no sirve no tumba el QA: se guarda sin ella.
    mala = json.dumps({"score": 80, "checks": CHECKS_OK, "doctrina": {"puntos": [{"n": 1, "estado": "quizas"}]}})
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: (mala, 900, 300))
    r = qa.evaluar("acme", {"titulo": "A", "escena": "a"}, entry, datos.campana("acme", cid))
    assert r["score"] == 80 and r["doctrina"] is None


def test_evaluar_dos_respuestas_malas_traen_los_tokens(base_temporal, monkeypatch):
    from sprints import analisis, datos, qa
    cid = _campana_qa(datos)
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: ("nada", 700, 50))
    with pytest.raises(qa.AnalisisInvalido) as e:
        qa.evaluar("acme", {"titulo": "A", "escena": "a"}, {"tipo": "imagen", "video_url": "https://r2/i.png"},
                   datos.campana("acme", cid))
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (1400, 100)


def test_evaluar_falla_la_correccion_preserva_tokens_del_primer_intento(base_temporal, monkeypatch):
    """Si la llamada de corrección falla por un error de red o similar, los
    tokens de la primera llamada no se pierden: entran en la excepción."""
    from sprints import analisis, datos, qa
    cid = _campana_qa(datos)
    llamada_n = {"n": 0}

    def dos_intentos(content, max_tokens=700, system=None):
        llamada_n["n"] += 1
        if llamada_n["n"] == 1:
            return ("nada", 700, 50)  # Primera: bad JSON
        # Segunda (corrección): network error
        raise RuntimeError("red caída")

    monkeypatch.setattr(analisis, "_llamar_contando", dos_intentos)
    with pytest.raises(qa.AnalisisInvalido) as e:
        qa.evaluar("acme", {"titulo": "A", "escena": "a"}, {"tipo": "imagen", "video_url": "https://r2/i.png"},
                   datos.campana("acme", cid))
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (700, 50)

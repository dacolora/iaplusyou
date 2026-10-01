"""«Editar este video»: el documento que sale del clon crudo y la edición
que se crea con él (sin pagar nada)."""
import pytest

from final_edition import documento, edicion_clon


def _clon(audio=True):
    return {"id": 7, "duracion_ms": 8250, "extra": {"tiene_audio": audio}}


def test_documento_del_clon_con_sonido():
    doc = edicion_clon.documento(_clon(), "9:16")
    principal = doc["pistas"][0]
    assert principal["tipo"] == "video" and [c["id"] for c in principal["clips"]] == ["v0"]
    v0 = principal["clips"][0]
    assert (v0["inicio_ms"], v0["duracion_ms"], v0["recorte"], v0["material_id"]) == (0, 8250, {"desde_ms": 0, "hasta_ms": 8250}, 7)
    sonido = [p for p in doc["pistas"] if p["id"] == "p_sonido"][0]
    assert sonido["clips"][0]["rol_audio"] == "sonido" and sonido["clips"][0]["duracion_ms"] == 8250
    assert doc["miniatura_ms"] == 1000 and doc["origen"] == {"tipo": "clon"}
    assert documento.validar(doc) == doc


def test_documento_del_clon_mudo_no_tiene_pista_de_sonido():
    doc = edicion_clon.documento(_clon(audio=False), "16:9")
    assert [p["id"] for p in doc["pistas"]] == ["p_video"] and doc["formato"] == "16:9"


def test_crear_arma_la_edicion_de_la_pieza(base_temporal, tmp_path, monkeypatch):
    import creative_flow
    import ediciones
    from final_edition import insumos
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira sobre la mesa", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    bajadas = []
    monkeypatch.setattr(insumos, "_descargar", lambda url, destino: bajadas.append((url, destino)) or destino)
    monkeypatch.setattr(insumos, "clon", lambda cliente, cf_id, entry, ruta: (_clon(), True))
    eid = edicion_clon.crear("acme", cf, str(tmp_path))
    ed = ediciones.cargar("acme", eid)
    assert ed["cf_id"] == cf and ed["nombre"].startswith("Edición de gira sobre la mesa")
    assert ed["documento"]["pistas"][0]["clips"][0]["material_id"] == 7
    assert bajadas == [("https://r2.test/v.mp4", str(tmp_path / "clon.mp4"))]
    assert ed["creada_por"] == "editor"


def test_el_destino_del_clon_es_el_pais_del_proyecto():
    from final_edition import vista_previa
    doc = edicion_clon.documento(_clon(), "9:16", pais="MX")
    assert doc["origen"] == {"tipo": "clon", "pais": "MX"} and doc["idioma_base"] == "es"
    assert vista_previa.destinos(doc) == ["es_MX"]
    assert vista_previa.destinos(edicion_clon.documento(_clon(), "9:16")) == ["es_CO"]   # sin país: como antes


def test_crear_usa_el_pais_del_proyecto(base_temporal, tmp_path, monkeypatch):
    import creative_flow
    import ediciones
    import proyectos
    from final_edition import insumos, vista_previa
    monkeypatch.setattr(proyectos, "pais", lambda cliente: {"acme": "MX"}[cliente])
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira sobre la mesa", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    monkeypatch.setattr(insumos, "_descargar", lambda url, destino: destino)
    monkeypatch.setattr(insumos, "clon", lambda cliente, cf_id, entry, ruta: (_clon(), True))
    ed = ediciones.cargar("acme", edicion_clon.crear("acme", cf, str(tmp_path)))
    assert vista_previa.destinos(ed["documento"]) == ["es_MX"]


def test_crear_rechaza_una_pieza_sin_video(base_temporal, tmp_path):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    with pytest.raises(ValueError, match="video listo"):
        edicion_clon.crear("acme", cf, str(tmp_path))


def test_la_edicion_desde_el_clon_usa_el_idioma_del_pais():
    """Decisión B (2026-09-28): una final sale en el idioma de su país; la
    edición «Editar este video» de un proyecto en EE. UU. produce en_US (la
    misma clave que usa fe_producir), una de México es_MX."""
    from final_edition import edicion_clon
    clon = {"id": 7, "duracion_ms": 4000, "extra": {}}
    assert edicion_clon.documento(clon, "9:16", pais="US")["idioma_base"] == "en"
    assert edicion_clon.documento(clon, "9:16", pais="MX")["idioma_base"] == "es"
    assert edicion_clon.documento(clon, "9:16")["idioma_base"] == "es"

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


def test_crear_rechaza_una_pieza_sin_video(base_temporal, tmp_path):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    with pytest.raises(ValueError, match="video listo"):
        edicion_clon.crear("acme", cf, str(tmp_path))

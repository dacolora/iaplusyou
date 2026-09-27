"""La edición de demostración de la vista previa: medios sintéticos locales,
documento del borrador de producción, reutiliza materiales por hash."""
import pytest

from final_edition import documento


@pytest.mark.slow
def test_sembrar_crea_una_edicion_valida_con_medios_locales(base_temporal, tmp_path):
    import ediciones
    import materiales
    import sembrar_edicion_demo as s
    from tareas import edicion
    eid = s.sembrar("acme", carpeta=str(tmp_path), url_base="/demo")
    doc = ediciones.cargar("acme", eid)["documento"]
    assert doc["pistas"][0]["clips"][0]["transicion"] == {"tipo": "fundido", "duracion_ms": 500}
    assert any(p["tipo"] == "imagen" for p in doc["pistas"])                    # el logo
    res = documento.resolver(doc, "es", "CO")
    textos = [c["texto"]["literal"] for p in res["pistas"] if p["tipo"] == "texto" for c in p["clips"]]
    assert "$ 89.900" in textos and "¿Tu piel se ve apagada?" in textos
    assert res["subtitulos"]["palabras"]
    mats = [materiales.obtener("acme", m) for m in doc["materiales"]]
    assert all(m["url"].startswith("/demo/") for m in mats)
    assert all((m.get("extra") or {}).get("local", "").startswith(str(tmp_path)) for m in mats)
    clon = next(m for m in mats if m["tipo"] == "video")
    assert clon["url_proxy"] == "/demo/clon_proxy.mp4"
    assert clon["extra"]["proxy_version"] == edicion.PROXY_VERSION
    voz = next(m for m in mats if m["origen"] == "voz")
    assert voz["extra"]["picos"] and max(voz["extra"]["picos"]) > 0.5
    eid2 = s.sembrar("acme", carpeta=str(tmp_path), url_base="/demo", cf_id="cf_demo")
    assert eid2 != eid and ediciones.cargar("acme", eid2)["cf_id"] == "cf_demo"
    assert ediciones.cargar("acme", eid2)["documento"]["materiales"] == doc["materiales"]   # mismos materiales

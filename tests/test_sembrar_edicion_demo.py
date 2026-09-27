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


@pytest.mark.parametrize("url", ["https://app.creatvmachine.com", "app.creatvmachine.com", "http://10.0.0.5:5050"])
def test_la_linea_de_comandos_se_niega_fuera_de_local(monkeypatch, capsys, url):
    """Nunca escribe una edición de demostración en producción: con
    PLATAFORMA_URL de otra máquina sale con 1 y un mensaje claro, sin sembrar."""
    import sembrar_edicion_demo as s
    monkeypatch.setattr(s, "_cargar_env", lambda: None)      # no leer el .env de verdad
    monkeypatch.setenv("PLATAFORMA_URL", url)
    monkeypatch.setattr(s, "sembrar", lambda *a, **k: pytest.fail("no debía sembrar"))
    assert s.main(["--cliente", "acme"]) == 1
    err = capsys.readouterr().err
    assert "No se crea la edición de demostración" in err and "nunca se escribe en producción" in err


@pytest.mark.parametrize("url", [None, "", "http://127.0.0.1:5050", "http://localhost:5050/"])
def test_la_linea_de_comandos_siembra_en_local(monkeypatch, capsys, url):
    import sembrar_edicion_demo as s
    monkeypatch.setattr(s, "_cargar_env", lambda: None)
    if url is None:
        monkeypatch.delenv("PLATAFORMA_URL", raising=False)
    else:
        monkeypatch.setenv("PLATAFORMA_URL", url)
    llamadas = []
    monkeypatch.setattr(s, "sembrar", lambda cliente, cf_id=None: llamadas.append((cliente, cf_id)) or 7)
    assert s.main(["--cliente", "acme", "--cf", "cf_1"]) == 0
    assert llamadas == [("acme", "cf_1")]
    assert "/cliente/acme/ediciones/7" in capsys.readouterr().out


def test_la_linea_de_comandos_lee_el_env_raiz(monkeypatch, tmp_path):
    """En el servidor PLATAFORMA_URL vive en el .env raíz, no en la terminal."""
    import sembrar_edicion_demo as s
    (tmp_path / ".env").write_text("PLATAFORMA_URL=https://app.creatvmachine.com\n")
    monkeypatch.setattr(s, "BASE", str(tmp_path))
    monkeypatch.delenv("PLATAFORMA_URL", raising=False)
    monkeypatch.setattr(s, "sembrar", lambda *a, **k: pytest.fail("no debía sembrar"))
    assert s.main(["--cliente", "acme"]) == 1

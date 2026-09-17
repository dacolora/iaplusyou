import pytest


def test_presets_por_pais_con_fechas_del_anio():
    from sprints import calendario
    co = calendario.presets("CO", anio=2026)
    claves = [p["clave"] for p in co]
    assert "navidad" in claves and "amor_y_amistad" in claves and "black_friday" in claves
    navidad = next(p for p in co if p["clave"] == "navidad")
    assert navidad["inicio"] == "2026-11-15" and navidad["fin"] == "2026-12-31" and navidad["tipo"] == "comercial"
    assert all(p["inicio"] < p["fin"] for p in co)
    mx = calendario.presets("MX", anio=2026)
    assert "san_valentin" in [p["clave"] for p in mx]
    assert calendario.presets("ZZ", anio=2026) == calendario.presets("CO", anio=2026)   # país sin calendario: el de Colombia


def test_adoptar_crea_temporada_una_sola_vez(base_temporal):
    from sprints import calendario, datos
    tid = calendario.adoptar("acme", "black_friday", pais="CO", anio=2026)
    t = datos.temporada("acme", tid)
    assert t["nombre"] == "Black Friday" and t["tipo"] == "comercial" and t["inicio"] == "2026-11-20"
    assert calendario.adoptar("acme", "black_friday", pais="CO", anio=2026) == tid
    assert len(datos.temporadas("acme")) == 1
    with pytest.raises(datos.ErrorDatos):
        calendario.adoptar("acme", "no_existe", pais="CO", anio=2026)


def test_pais_del_proyecto(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    assert proyectos.pais("acme") == "CO"
    proyectos.guardar_pais("acme", "MX")
    assert proyectos.pais("acme") == "MX"
    with pytest.raises(ValueError):
        proyectos.guardar_pais("acme", "XX")

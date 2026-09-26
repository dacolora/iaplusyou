"""Página «Cómo escribe Creatv» (doctrina, bloque 2, §6)."""


def test_a_html_convierte_lo_que_usan_los_textos():
    from doctrina import pagina
    html = str(pagina.a_html("# Título\n\nUn **principio** con *énfasis* y `faltantes`.\n\n"
                             "- uno\n- dos\n  sigue dos\n\n1. primero\n2. segundo"))
    assert "<h2>Título</h2>" in html
    assert "<p>Un <strong>principio</strong> con <em>énfasis</em> y <code>faltantes</code>.</p>" in html
    assert "<ul><li>uno</li><li>dos sigue dos</li></ul>" in html
    assert "<ol><li>primero</li><li>segundo</li></ol>" in html


def test_a_html_escapa_antes_de_convertir():
    from doctrina import pagina
    html = str(pagina.a_html('Hola <script>alert(1)</script> **<b>x</b>** "comillas"'))
    assert "<script>" not in html and "&lt;script&gt;" in html and "<strong>&lt;b&gt;x&lt;/b&gt;</strong>" in html


def test_secciones_trae_las_nueve_rebanadas_en_orden():
    import doctrina
    from doctrina import pagina
    secciones = pagina.secciones()
    assert [s[0] for s in secciones] == list(doctrina.REBANADAS)
    assert all(str(s[2]).strip() for s in secciones)


def test_ruta_de_la_doctrina_exige_acceso_al_proyecto(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    assert c.get("/cliente/acme/doctrina").status_code == 302          # sin sesión: al login
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    html = c.get("/cliente/acme/doctrina").data.decode()
    assert "Cómo escribe Creatv" in html and 'id="angulo"' in html and 'id="gancho"' in html
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    assert c.get("/cliente/acme/doctrina").status_code in (302, 403, 404)
    # Configuración › Generación enlaza la página
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    assert 'href="/cliente/acme/doctrina"' in c.get("/cliente/acme").data.decode()

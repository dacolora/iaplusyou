"""Rutas de «Cómo mejorarlo» (spec tarjetas §6.2, §6.4, §6.5, §7)."""
import pytest
import sqlalchemy as sa

import db
import proyectos
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_triple_whale import _conectar, _hace, _sembrar, _tareas
from tests.test_tw_mejorar import respuesta
from triple_whale import datos, mejorar


@pytest.fixture(autouse=True)
def _proyecto_aislado(tmp_path, monkeypatch):
    """El aprendizaje y las preferencias viven en clientes/<c>/proyecto.json: que las pruebas no escriban en el repo."""
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


def _analizar(app, ad_id="p1", json=False, **headers):  # noqa: F811
    h = dict(headers)
    if json:
        h["Accept"] = "application/json"
    return app["c"].post(f"/cliente/acme/triple-whale/anuncio/facebook-ads/{ad_id}/analizar",
                         data={"dias": "30", "canal": "", "tienda": ""}, headers=h)


def test_analizar_crea_la_fila_con_la_foto_y_encola_una_vez(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = _analizar(app)
    assert r.status_code == 302 and r.headers["Location"].endswith("#triplewhale")
    [fila] = datos.ultimos_analisis("acme", [("facebook-ads", "p1")]).values()
    assert fila["estado"] == "en_cola" and fila["pedido_por"] == "admin" and fila["moneda"] == "USD"
    assert fila["foto"]["nombre"] == "Anuncio p1" and fila["foto"]["veredicto"] and "anillos" in fila["foto"]
    assert "cpa_canal" in fila["foto"]["cuenta"] and isinstance(fila["foto"]["ganadores"], list)
    [t] = _tareas("tw_analizar_anuncio")
    assert t["job_id"] == "acme__tw_anuncio__facebook-ads__p1" and t["max_intentos"] == 1
    assert t["payload"] == {"cliente": "acme", "analisis_id": fila["id"]}
    _analizar(app)                                                   # segundo clic: nada nuevo
    assert len(_tareas("tw_analizar_anuncio")) == 1
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.tw_analisis)).scalar() == 1


def test_analizar_por_fetch_devuelve_la_tarjeta_con_la_barra(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = _analizar(app, json=True)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and 'data-poll-al-terminar="evento"' in d["html"]
    assert 'data-poll-job="acme__tw_anuncio__facebook-ads__p1"' in d["html"]


def test_analizar_rechaza_otro_origen_ajenos_invalidos_y_sin_datos(app):  # noqa: F811
    _conectar()
    _sembrar()
    assert _analizar(app, **{"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert _analizar(app, ad_id="no-existe").status_code == 404
    assert app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/a%2Fb/analizar").status_code == 404
    r = _analizar(app, ad_id="n1")                                   # sin datos: no cobra
    assert r.status_code == 302 and _tareas("tw_analizar_anuncio") == []


def test_sin_triple_whale_no_cobra_y_el_fetch_recibe_json(app):  # noqa: F811
    r = _analizar(app, json=True)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] is False and d["html"] == "" and "no está conectado" in d["mensaje"]
    r = _analizar(app)
    assert r.status_code == 302 and _tareas("tw_analizar_anuncio") == []
    assert app["c"].post("/cliente/acme/triple-whale/analizar-lote").status_code == 302
    assert app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/g1/referente").status_code == 404


def test_un_anuncio_sin_datos_por_fetch_no_cobra_y_dice_por_que(app):  # noqa: F811
    _conectar()
    _sembrar()
    d = _analizar(app, ad_id="n1", json=True).get_json()
    assert d["ok"] is False and "muy pocos datos" in d["mensaje"] and "tw-tarjeta" in d["html"]
    assert _tareas("tw_analizar_anuncio") == []


def test_lote_encola_los_que_mas_gastaron_sin_repetir(app):  # noqa: F811
    _conectar()
    _sembrar()
    _analizar(app, ad_id="p1")
    r = app["c"].post("/cliente/acme/triple-whale/analizar-lote", data={"dias": "30", "canal": "", "tienda": ""})
    assert r.status_code == 302
    jobs = {t["job_id"] for t in _tareas("tw_analizar_anuncio")}
    assert "acme__tw_anuncio__facebook-ads__p1" in jobs and len(jobs) >= 3
    assert all(t["max_intentos"] == 1 for t in _tareas("tw_analizar_anuncio"))
    assert not any(j.endswith("__n1") for j in jobs)


def _lista(app, ad_id="p1"):  # noqa: F811
    _analizar(app, ad_id=ad_id)
    fila = datos.ultimos_analisis("acme", [("facebook-ads", ad_id)])[("facebook-ads", ad_id)]
    datos.actualizar_analisis(fila["id"], estado="lista", usd=0.08,
                              resultado=mejorar.parsear(respuesta(), "datos"),
                              medios={"visual": "fotogramas", "fotogramas": 6, "transcripcion": "Det er", "copy": True})
    return fila["id"]


def _el_worker_termino():
    """`_lista` deja la fila lista a mano: la tarea del worker se da por hecha, como cuando termina de verdad."""
    with db.conectar() as con:
        con.execute(db.tarea.update().values(estado="hecha"))


def test_detalle_muestra_razones_cambios_y_version(app):  # noqa: F811
    _conectar()
    _sembrar()
    aid = _lista(app)
    html = app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()
    assert "Pierde porque arranca con el logo." in html and "Arranque lento" in html and "Segundo 0" in html
    assert "Otro arranque" in html and "Pies cansados al final del día" in html and "Close-up" in html
    assert f"/cliente/acme/triple-whale/analisis/{aid}/crear" in html
    assert f"/cliente/acme/triple-whale/analisis/{aid}/aprendizaje" in html
    assert "6 fotogramas" in html
    assert app["c"].get("/cliente/acme/triple-whale/analisis/99999").status_code == 404


def test_detalle_de_otro_proyecto_es_404(app):  # noqa: F811
    _conectar()
    aid = datos.crear_analisis("otro", None, "facebook-ads", "1", "2026-09-01", "2026-09-30", "USD", {})
    datos.actualizar_analisis(aid, estado="lista", resultado={"frase": "x"})
    assert app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").status_code == 404


def test_llevar_a_crear_y_el_origen(app):  # noqa: F811
    from triple_whale import puente
    _conectar()
    _sembrar()
    aid = _lista(app)
    r = app["c"].post(f"/cliente/acme/triple-whale/analisis/{aid}/crear")
    assert r.status_code == 302 and r.headers["Location"].endswith("#creativeflowplus")
    with app["c"].session_transaction() as s:
        assert s["fp_prefill"]["texto"].startswith("Close-up") and s["fp_prefill"]["origen_tw"] == f"a{aid}"
    assert puente.origen_desde_formulario("acme", f"a{aid}") == {"analisis_id": aid, "titulo": "Pies cansados al final del día"}
    assert puente.origen_desde_formulario("otro", f"a{aid}") is None
    assert puente.origen_desde_formulario("acme", "a99999") is None
    assert puente.origen_desde_formulario("acme", "axx") is None


def test_guardar_como_aprendizaje(app):  # noqa: F811
    _conectar()
    _sembrar()
    aid = _lista(app)
    assert proyectos.aprendizajes("acme") == []                     # analizar no agrega ninguno
    app["c"].post(f"/cliente/acme/triple-whale/analisis/{aid}/aprendizaje")
    [item] = proyectos.aprendizajes("acme")
    assert item["origen"] == "triple_whale" and "logo" in item["texto"]


def test_anuncio_a_referentes_desde_la_tarjeta(app, monkeypatch):  # noqa: F811
    from referentes import datos as ref_datos
    from referentes import imagenes
    tid = _conectar()
    _sembrar()
    datos.reemplazar_creativos("acme", tid, [{"canal": "facebook-ads", "ad_id": "g1", "tipo": "video",
                                              "imagen_url": "https://files.triplewhale.com/t/g1.jpg", "titulo": "T", "copy": "C"}])
    monkeypatch.setattr(imagenes, "guardar_en_r2", lambda aid, url, carpeta: f"https://r2/{aid}.jpg")
    r = app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/g1/referente", data={"dias": "30"},
                      follow_redirects=True)
    assert "Guardado en Referentes" in r.data.decode()
    [ref] = ref_datos.listar("acme", {"fuente": "triple_whale"})["items"]
    assert ref["anuncio_id"] == "tw:g1" and ref["titular"] == "T"


def test_detalle_dice_lo_que_claude_vio_y_no_inventa_el_texto(app):  # noqa: F811
    """`m.copy` en Jinja sería el método de dict (siempre verdadero): «el texto» solo sale si de verdad lo vio."""
    _conectar()
    _sembrar()
    aid = _lista(app)
    datos.actualizar_analisis(aid, medios={"visual": None, "transcripcion": None, "copy": False})
    html = app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()
    assert "Claude no vio el anuncio" in html and "· el texto" not in html and "· la voz" not in html
    datos.actualizar_analisis(aid, medios={"visual": "imagen", "copy": True})
    html = app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()
    assert "Claude vio la imagen" in html and "· el texto" in html and "· la voz" not in html


def test_lo_que_escribio_claude_va_escapado(app):  # noqa: F811
    _conectar()
    _sembrar()
    aid = _lista(app)
    datos.actualizar_analisis(aid, resultado=mejorar.parsear(
        respuesta(frase="<script>alert(1)</script>", aprendizaje="<img src=x onerror=alert(2)>"), "datos"))
    html = app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)" in html
    assert "<img src=x" not in html


def test_el_detalle_ya_guardado_no_ofrece_guardar_otra_vez(app):  # noqa: F811
    _conectar()
    _sembrar()
    aid = _lista(app)
    url = f"/cliente/acme/triple-whale/analisis/{aid}"
    assert "Guardar como aprendizaje" in app["c"].get(url).data.decode()
    app["c"].post(f"{url}/aprendizaje")
    app["c"].post(f"{url}/aprendizaje")                                # segundo clic: no duplica
    [item] = proyectos.aprendizajes("acme")
    assert item["analisis_id"] == aid
    html = app["c"].get(url).data.decode()
    assert "Guardar como aprendizaje" not in html and "Guardado" in html


def test_el_aprendizaje_se_guarda_en_el_idioma_del_proyecto(app):  # noqa: F811
    """Regla 3: lo que se guarda va en el idioma del proyecto, no en el de quien hace el clic."""
    import idiomas
    _conectar()
    _sembrar()
    aid = _lista(app)
    idiomas.guardar_de_proyecto("acme", "en")
    app["c"].post(f"/cliente/acme/triple-whale/analisis/{aid}/aprendizaje", headers={"Accept-Language": "es"})
    [item] = proyectos.aprendizajes("acme")
    assert item["texto"].startswith("Lost in Triple Whale") and "Diagnóstico" not in item["texto"]


def test_llevar_a_crear_sin_version_o_de_otro_proyecto_es_404(app):  # noqa: F811
    _conectar()
    _sembrar()
    aid = _lista(app)
    datos.actualizar_analisis(aid, resultado={"frase": "x"})
    assert app["c"].post(f"/cliente/acme/triple-whale/analisis/{aid}/crear").status_code == 404
    ajeno = datos.crear_analisis("otro", None, "facebook-ads", "1", "2026-09-01", "2026-09-30", "USD", {})
    datos.actualizar_analisis(ajeno, estado="lista", resultado={"version": {"titulo": "x", "prompt": "y"}})
    assert app["c"].post(f"/cliente/acme/triple-whale/analisis/{ajeno}/crear").status_code == 404
    assert app["c"].post(f"/cliente/acme/triple-whale/analisis/{ajeno}/aprendizaje").status_code == 404


def test_la_pieza_hecha_con_el_origen_del_analisis_se_cuenta_en_la_tarjeta(app, monkeypatch, tmp_path):  # noqa: F811
    """Punta a punta: «Llevar a Crear» deja `a<id>`, el formulario de Crear lo devuelve, `cf_crear_video` lo guarda
    en `concepto.extra.tw_idea` y la tarjeta dice «Ya se hizo 1 pieza con esta mejora» (spec §7.1). No genera nada."""
    import creative_flow as cf
    import referencias_flowplus
    dashboard = app["dashboard"]
    _conectar()
    _sembrar()
    aid = _lista(app)
    _el_worker_termino()
    monkeypatch.setattr(referencias_flowplus, "_path", lambda cliente: str(tmp_path / f"bandeja_{cliente}.json"))
    lanzadas = []
    monkeypatch.setattr(dashboard, "_lanzar_video_cf", lambda c, cf_id, entry: lanzadas.append(cf_id) or True)
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda job_id, tipo, payload, **kw: True)
    html = app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/p1?dias=30").data.decode()
    assert "Ya se hizo" not in html
    app["c"].post(f"/cliente/acme/triple-whale/analisis/{aid}/crear")
    r = app["c"].post("/cliente/acme/creative_flow/crear", data={
        "accion_central": "Close-up of a tired foot", "duracion_objetivo": "8", "aspect_ratio": "9:16", "tipo": "video",
        "modelo": "wan3", "musica_estilo": "", "bandeja_vista": "1", "origen_tw": f"a{aid}"})
    assert r.status_code == 302
    [(cf_id, entry)] = cf.cargar("acme").items()
    assert entry["tw_idea"] == {"analisis_id": aid, "titulo": "Pies cansados al final del día"} and lanzadas == [cf_id]
    html = app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/p1?dias=30").data.decode()
    assert "Ya se hizo 1 pieza con esta mejora" in html


def test_el_lote_no_repite_lo_analizado_en_otro_periodo_pero_la_tarjeta_si_lo_ofrece(app):  # noqa: F811
    """El lote respeta el alcance: lo ya analizado en otro periodo no se ofrece ni se cobra otra vez."""
    _conectar()
    _sembrar()
    for ad in ("g1", "g2", "p1", "p2"):
        _analizar(app, ad_id=ad)
        fila = datos.ultimos_analisis("acme", [("facebook-ads", ad)])[("facebook-ads", ad)]
        datos.actualizar_analisis(fila["id"], estado="lista", resultado={"frase": "x"},
                                  desde=_hace(6), hasta=_hace(0))     # 7 días: otro alcance que los 30 pedidos
    cuatro = {f"acme__tw_anuncio__facebook-ads__{ad}" for ad in ("g1", "g2", "p1", "p2")}

    def de_los_cuatro():
        return sorted(t["job_id"] for t in _tareas("tw_analizar_anuncio") if t["job_id"] in cuatro)
    antes = de_los_cuatro()
    assert len(antes) == 4
    r = app["c"].post("/cliente/acme/triple-whale/analizar-lote", data={"dias": "30", "canal": "", "tienda": ""},
                      follow_redirects=True)
    assert de_los_cuatro() == antes                                       # ya tenían análisis: el lote no los repite
    assert "Analizando 1 anuncio con IA" in r.data.decode() or "No quedó ningún anuncio por analizar" in r.data.decode()
    _el_worker_termino()
    antes_todas = len(_tareas("tw_analizar_anuncio"))
    # Y la tarjeta ofrece, a propósito, uno nuevo con los datos de ahora; ese sí cobra otro análisis.
    r = app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/p1/analizar",
                      data={"dias": "30", "canal": "", "tienda": ""}, headers={"Accept": "application/json"})
    assert r.get_json()["ok"] and len(_tareas("tw_analizar_anuncio")) == antes_todas + 1


def test_referente_sin_miniatura_dice_por_que_y_el_anuncio_ajeno_es_404(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/g2/referente", data={"dias": "30"},
                      follow_redirects=True)
    assert "no tiene miniatura" in r.data.decode()
    assert app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/no-existe/referente").status_code == 404
    assert app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/g1/referente",
                         headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403

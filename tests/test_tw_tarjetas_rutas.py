"""Rutas de «Cómo mejorarlo» (spec tarjetas §6.2, §6.4, §6.5, §7)."""
import re

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


def _form_del_lote(app, **extra):  # noqa: F811
    """Lo que manda el formulario del lote tal como la pestaña lo pinta: el alcance y una `clave` por anuncio mostrado."""
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    claves = re.findall(r'<input type="hidden" name="clave" value="([^"]+)">', html)
    return dict({"dias": "30", "canal": "", "tienda": "", "veredicto": "", "clave": claves}, **extra), claves, html


def _lote(app, data):  # noqa: F811
    return app["c"].post("/cliente/acme/triple-whale/analizar-lote", data=data, follow_redirects=True)


def _jobs():
    return sorted(t["job_id"] for t in _tareas("tw_analizar_anuncio"))


def _filas_analisis():
    with db.conectar() as con:
        return con.execute(sa.select(sa.func.count()).select_from(db.tw_analisis)).scalar()


def test_lote_encola_los_que_mas_gastaron_sin_repetir(app):  # noqa: F811
    _conectar()
    _sembrar()
    _analizar(app, ad_id="p1")
    data, claves, html = _form_del_lote(app)
    assert claves and "facebook-ads:p1" not in claves and "facebook-ads:n1" not in claves   # ni lo vivo ni sin datos
    assert f"Analizar los {len(claves)} que más gastaron" in html
    r = app["c"].post("/cliente/acme/triple-whale/analizar-lote", data=data)
    assert r.status_code == 302
    jobs = {t["job_id"] for t in _tareas("tw_analizar_anuncio")}
    assert "acme__tw_anuncio__facebook-ads__p1" in jobs and len(jobs) == 1 + len(claves) and len(jobs) >= 3
    assert all(t["max_intentos"] == 1 for t in _tareas("tw_analizar_anuncio"))
    assert not any(j.endswith("__n1") for j in jobs)


def test_el_segundo_envio_del_mismo_lote_no_cobra_los_siguientes(app):  # noqa: F811
    """Pestaña vieja, «atrás» o doble clic: el formulario confirmó ESTOS anuncios, no «los próximos N»."""
    _conectar()
    _sembrar()
    data, claves, _ = _form_del_lote(app)
    assert len(claves) == 5
    _lote(app, data)
    assert len(_jobs()) == 5 and _filas_analisis() == 5
    _lote(app, data)                                         # el mismo formulario otra vez: ya están en cola
    assert len(_jobs()) == 5 and _filas_analisis() == 5
    _el_worker_termino()
    for fila in datos.ultimos_analisis("acme", [tuple(c.split(":")) for c in claves]).values():
        datos.actualizar_analisis(fila["id"], estado="lista", resultado={"frase": "x"})
    r = _lote(app, data)                                      # y ya terminados (frescos) tampoco se vuelven a pedir
    assert len(_jobs()) == 5 and _filas_analisis() == 5
    assert "No quedó ningún anuncio por analizar" in r.data.decode()


def test_el_lote_cobra_a_lo_sumo_lo_que_se_confirmo(app):  # noqa: F811
    """Una página que mostraba «los 3» no puede cobrar 10: se analizan solo las claves enviadas."""
    _conectar()
    _sembrar()
    _, claves, _ = _form_del_lote(app)
    assert len(claves) == 5
    r = _lote(app, {"dias": "30", "canal": "", "tienda": "", "veredicto": "", "clave": claves[:3]})
    esperados = sorted(f"acme__tw_anuncio__{c.replace(':', '__')}" for c in claves[:3])
    assert _jobs() == esperados and _filas_analisis() == 3
    assert "Analizando 3 anuncios con IA" in r.data.decode()


def test_un_lote_sin_claves_no_analiza_nada(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = _lote(app, {"dias": "30", "canal": "", "tienda": "", "veredicto": ""})
    assert _jobs() == [] and _filas_analisis() == 0 and "No quedó ningún anuncio por analizar" in r.data.decode()


def test_el_lote_ignora_claves_inventadas_o_que_no_son_elegibles(app):  # noqa: F811
    _conectar()
    _sembrar()
    datos.crear_analisis("otro", None, "facebook-ads", "g1", "2026-09-01", "2026-09-30", "USD", {})
    falsas = ["facebook-ads:n1",                    # sin datos: nunca se cobra
              "facebook-ads:no-existe", "tiktok-ads:g1",         # no existe en el proyecto
              "otro:g1", "x", ":", "a:b:c", "facebook-ads:", ":p1", "facebook-ads:p1\n", "facebook-ads:a/b", "", "facebook-ads: p1"]
    r = _lote(app, {"dias": "30", "canal": "", "tienda": "", "veredicto": "", "clave": falsas})
    assert _jobs() == [] and _filas_analisis() == 1                    # solo la fila ajena que sembré
    assert "No quedó ningún anuncio por analizar" in r.data.decode()
    # Y una buena mezclada con las falsas sí pasa, una sola vez aunque venga repetida.
    _lote(app, {"dias": "30", "canal": "", "tienda": "", "veredicto": "",
                "clave": falsas + ["facebook-ads:p1", "facebook-ads:p1"]})
    assert _jobs() == ["acme__tw_anuncio__facebook-ads__p1"]


def test_el_lote_nunca_pasa_de_diez_aunque_manden_mas(app):  # noqa: F811
    from tests.test_tw_tarjetas_galeria import _sembrar_muchos
    _conectar()
    _sembrar_muchos(15)
    data, claves, _ = _form_del_lote(app)
    assert len(claves) == 10                                           # el botón ofrece 10
    todas = [f"facebook-ads:m{i:02d}" for i in range(15)]              # y un POST a mano manda las 15
    _lote(app, {"dias": "30", "canal": "", "tienda": "", "veredicto": "", "clave": todas})
    assert len(_jobs()) == 10 and _filas_analisis() == 10


def test_si_encolar_falla_no_queda_una_fila_colgada(app, monkeypatch):  # noqa: F811
    """Una fila `en_cola` sin tarea bloquearía el anuncio para siempre: se borra y el error sigue su camino."""
    from tareas import triple_whale as tareas_tw
    _conectar()
    _sembrar()
    def revienta(*a, **k):  # noqa: E306
        raise RuntimeError("redis token=abc")
    monkeypatch.setattr(tareas_tw, "encolar_analisis", revienta)
    with pytest.raises(RuntimeError):
        _analizar(app)
    assert _filas_analisis() == 0 and _jobs() == []
    assert not datos.analisis_en_curso("acme", "facebook-ads", "p1")


def test_en_el_lote_una_que_falla_no_tumba_las_demas(app, monkeypatch, caplog):  # noqa: F811
    from tareas import triple_whale as tareas_tw
    _conectar()
    _sembrar()
    real = tareas_tw.encolar_analisis

    def a_veces(cliente, aid, canal, ad_id):
        if ad_id == "p1":
            raise RuntimeError("boom token=abc")
        return real(cliente, aid, canal, ad_id)
    monkeypatch.setattr(tareas_tw, "encolar_analisis", a_veces)
    _, claves, _ = _form_del_lote(app)
    assert "facebook-ads:p1" in claves and len(claves) == 5
    with caplog.at_level("WARNING", logger="creatv.triple_whale.rutas"):
        r = _lote(app, {"dias": "30", "canal": "", "tienda": "", "veredicto": "", "clave": claves})
    html = r.data.decode()
    assert len(_jobs()) == 4 and "acme__tw_anuncio__facebook-ads__p1" not in _jobs() and _filas_analisis() == 4
    assert "Analizando 4 anuncios con IA" in html and "No se pudo encolar 1 anuncio" in html
    assert "RuntimeError" in caplog.text and "token=abc" not in caplog.text    # la clase, nunca el mensaje


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
    assert "Claude no vio el anuncio: juzgó por los números" in html
    assert "el texto" not in html and "la voz" not in html                      # ni repetido ni inventado
    datos.actualizar_analisis(aid, medios={"visual": "imagen", "copy": True})
    html = app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()
    assert "Claude vio la imagen" in html and "· el texto" in html and "· la voz" not in html
    datos.actualizar_analisis(aid, medios={"visual": None, "transcripcion": "Det er", "copy": True})
    html = app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()
    assert "juzgó por los números · la voz · el texto" in " ".join(html.split())
    assert html.count("el texto") == 1


def test_el_detalle_dice_cuando_se_analizo_y_con_que_alcance(app):  # noqa: F811
    _conectar()
    _sembrar()
    aid = _lista(app)
    fila = datos.analisis_anuncio("acme", aid)
    html = app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()
    assert f"analizado el {fila['creado_en'][:10]}" in html
    assert f"datos del {fila['desde']} al {fila['hasta']} · acme.myshopify.com ·" in " ".join(html.split())
    todas = datos.crear_analisis("acme", None, "facebook-ads", "g1", "2026-09-01", "2026-09-30", "USD", {})
    datos.actualizar_analisis(todas, estado="lista", resultado={"frase": "x"})
    html = app["c"].get(f"/cliente/acme/triple-whale/analisis/{todas}").data.decode()
    assert "Todas las tiendas" in html and "acme.myshopify.com" not in html


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


def test_dos_guardados_del_mismo_aprendizaje_dejan_uno(app):  # noqa: F811
    """El `id` sale del análisis y `agregar_aprendizaje` descarta por `id` bajo su candado: sin comprobar antes."""
    from doctrina import aprendizajes
    _conectar()
    _sembrar()
    aid = _lista(app)
    fila = datos.analisis_anuncio("acme", aid)
    primero, segundo = aprendizajes.desde_analisis_tw(fila), aprendizajes.desde_analisis_tw(fila)
    assert primero["id"] == segundo["id"] == f"tw{aid}"
    proyectos.agregar_aprendizaje("acme", primero)
    proyectos.agregar_aprendizaje("acme", segundo)
    [item] = proyectos.aprendizajes("acme")
    assert item["analisis_id"] == aid
    otro = _lista(app, "p2")                                              # otro análisis, otro aprendizaje
    proyectos.agregar_aprendizaje("acme", aprendizajes.desde_analisis_tw(datos.analisis_anuncio("acme", otro)))
    assert len(proyectos.aprendizajes("acme")) == 2


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
    _el_worker_termino()                                                  # sin tarea viva: solo el alcance los frena
    data, claves, _ = _form_del_lote(app)
    assert not {f"facebook-ads:{ad}" for ad in ("g1", "g2", "p1", "p2")} & set(claves)    # el botón no los ofrece
    forzado = dict(data, clave=claves + [f"facebook-ads:{ad}" for ad in ("g1", "g2", "p1", "p2")])
    r = _lote(app, forzado)                                               # ni aunque alguien los mande a mano
    assert de_los_cuatro() == antes                                       # ya tenían análisis: el lote no los repite
    assert "Analizando 1 anuncio con IA" in r.data.decode()               # solo t1 (TikTok), que no tenía ninguno
    antes_todas = len(_tareas("tw_analizar_anuncio"))
    # Y la tarjeta ofrece, a propósito, uno nuevo con los datos de ahora; ese sí cobra otro análisis.
    r = app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/p1/analizar",
                      data={"dias": "30", "canal": "", "tienda": ""}, headers={"Accept": "application/json"})
    assert r.get_json()["ok"] and len(_tareas("tw_analizar_anuncio")) == antes_todas + 1


def test_el_boton_de_referentes_sale_solo_si_la_ruta_puede_guardarlo(app, base_temporal, monkeypatch):  # noqa: F811
    """La miniatura es la misma que pinta la tarjeta: la del anuncio de Triple Whale o, en uno hecho en Creatv, la de R2."""
    import experimentos as ex
    from referentes import datos as ref_datos
    from referentes import imagenes
    from tests.test_experimentos_db import PAISES, _pieza
    _conectar()
    _sembrar()
    guardadas = []
    monkeypatch.setattr(imagenes, "guardar_en_r2", lambda aid, url, carpeta: guardadas.append(url) or f"https://r2/{aid}.jpg")

    def boton(ad):
        html = app["c"].get(f"/cliente/acme/triple-whale/tarjeta/facebook-ads/{ad}?dias=30").data.decode()
        return f"/anuncio/facebook-ads/{ad}/referente" in html
    assert not boton("g1") and not boton("g2")                            # ganadores, pero sin ninguna miniatura
    eid = ex.crear("acme", "Cojín otoño", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "USD")
    pieza = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_tw")
    ep = ex.agregar_pieza("acme", eid, pieza, "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id="g1")                      # g1 lo lanzó Creatv; Triple Whale no trae miniatura
    with db.conectar() as con:
        con.execute(db.pieza.update().where(db.pieza.c.id == pieza).values(url_miniatura="https://r2/mini.jpg"))
    assert boton("g1") and not boton("g2")
    r = app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/g1/referente", data={"dias": "30"},
                      follow_redirects=True)
    assert "Guardado en Referentes" in r.data.decode() and guardadas == ["https://r2/mini.jpg"]
    [ref] = ref_datos.listar("acme", {"fuente": "triple_whale"})["items"]
    assert ref["anuncio_id"] == "tw:g1"
    r = app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/g2/referente", data={"dias": "30"},
                      follow_redirects=True)
    assert "no tiene miniatura" in r.data.decode() and guardadas == ["https://r2/mini.jpg"]


def test_referente_sin_miniatura_dice_por_que_y_el_anuncio_ajeno_es_404(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/g2/referente", data={"dias": "30"},
                      follow_redirects=True)
    assert "no tiene miniatura" in r.data.decode()
    assert app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/no-existe/referente").status_code == 404
    assert app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/g1/referente",
                         headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403

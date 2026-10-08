"""Pestaña Triple Whale (spec 2026-09-28 §8): la página solo pinta el
contenedor, el panel llega por fetch, y los cuatro POST (sincronizar,
evaluar con IA, llevar una idea a Crear, guardar un anuncio en Referentes)."""
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

import db
import triple_whale_tiendas
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_experimentos import _resultados
from tests.test_triple_whale_analisis import respuesta
from triple_whale import analisis, datos


def _hace(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _conectar():
    triple_whale_tiendas.conectar("acme", "tw_secreto_123", "acme.myshopify.com", moneda="USD")
    triple_whale_tiendas.actualizar("acme", ultima_sincronizacion=db.ahora())


def _tienda(cliente="acme"):
    """El id de la (única) tienda conectada en la prueba."""
    return triple_whale_tiendas.tiendas(cliente)[0]["id"]


def _sembrar():
    """Seis anuncios de Meta con 10 días de datos: dos ganadores, dos
    perdedores, uno sin datos y uno de TikTok; y la tienda."""
    canal, pixel, tienda = [], [], []
    for dia in range(10):
        f = _hace(dia)
        for ad, gasto, imp, pedidos, ingresos, canal_ in (("g1", 20, 2000, 1, 120, "facebook-ads"),
                                                          ("g2", 15, 1500, 1, 90, "facebook-ads"),
                                                          ("p1", 40, 3000, 0, 0, "facebook-ads"),
                                                          ("p2", 30, 2500, 0, 0, "facebook-ads"),
                                                          ("n1", 1, 20, 0, 0, "facebook-ads"),
                                                          ("t1", 10, 1000, 0.5, 20, "tiktok-ads")):
            canal.append({"canal": canal_, "ad_id": ad, "fecha": f, "anuncio": f"Anuncio {ad}", "campana": "Otoño",
                          "gasto": gasto, "impresiones": imp, "clics": imp // 50, "vistas_3s": imp // 3,
                          "thruplays": imp // 10, "utm_ok": ad != "p2"})
            pixel.append({"canal": canal_, "ad_id": ad, "fecha": f, "pedidos": pedidos, "ingresos": ingresos})
        tienda.append({"fecha": f, "gasto": 120, "ingresos": 400, "pedidos": 5, "nc_pedidos": 2})
    datos.reemplazar_anuncios_canal("acme", _tienda(), _hace(9), _hace(0), canal)
    datos.reemplazar_anuncios_pixel("acme", _tienda(), _hace(9), _hace(0), pixel)
    datos.reemplazar_tienda("acme", _tienda(), _hace(9), _hace(0), tienda)


def _tareas(tipo):
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(
            sa.select(db.tarea.c.job_id, db.tarea.c.payload, db.tarea.c.max_intentos).where(db.tarea.c.tipo == tipo))]


def test_sin_conectar_la_pestana_invita_a_conectar(app):  # noqa: F811
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-tab="triplewhale"' in html and 'id="tab-triplewhale"' in html
    ini = html.index('id="tab-triplewhale"')
    pestana = html[ini:html.index('id="tab-nicho"')]
    # Desde 2026-09-28 el formulario de conexión vive aquí mismo, no en Configuración.
    assert "Conecta Triple Whale para evaluar tu contenido" in pestana and 'id="tw-conexion"' in pestana
    assert "/cliente/acme/cfg_triple_whale/conectar" in pestana and "config-triple-whale" not in pestana
    assert "/triple-whale/panel" not in pestana
    assert "Triple Whale ya no está conectado" in app["c"].get("/cliente/acme/triple-whale/panel").data.decode()


def test_la_pagina_no_calcula_el_panel_al_cargar(app, monkeypatch):  # noqa: F811
    from triple_whale import panel
    _conectar()
    monkeypatch.setattr(panel, "contexto", lambda *a, **k: pytest.fail("el panel va por fetch"))
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-url="/cliente/acme/triple-whale/panel"' in html


def test_panel_con_datos_muestra_tienda_veredictos_diagnostico_e_ia(app):  # noqa: F811
    _conectar()
    _sembrar()
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "Tu tienda" in html and "MER" in html and "Tus anuncios" in html
    assert "Anuncio g1" in html and "Anuncio p1" in html
    assert "Ganador" in html and "Perdedor" in html and "Sin datos suficientes" in html
    assert 'class="tb-grafico"' in html
    assert "Sin rastreo de Triple Whale" in html            # p2 no lleva los parámetros
    assert "TikTok" in html and 'data-tw-param="canal"' in html
    assert "/cliente/acme/triple-whale/evaluar" in html and "aprox." in html
    assert "tw_secreto_123" not in html
    # Filtro por canal: solo TikTok.
    solo_tt = app["c"].get("/cliente/acme/triple-whale/panel?canal=tiktok-ads&dias=7").data.decode()
    assert "Anuncio t1" in solo_tt and "Anuncio g1" not in solo_tt and "Tu tienda" not in solo_tt
    assert '<option value="7" selected>' in solo_tt


def test_el_anuncio_hecho_en_creatv_enlaza_a_su_experimento_por_el_hash(app, base_temporal):  # noqa: F811
    """«Hecho en Creatv · …» lleva a `#experimentos?exp=<id>` (el filtro va en el hash y no recarga la página, E2);
    la forma vieja `?exp=<id>#experimentos` ya no se pinta."""
    import experimentos as ex
    from tests.test_experimentos_db import PAISES, _pieza
    _conectar()
    _sembrar()
    eid = ex.crear("acme", "Cojín otoño", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "USD")
    ep = ex.agregar_pieza("acme", eid, _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None,
                                              legado="cf_tw"), "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id="g1")                    # el anuncio g1 de Triple Whale lo lanzó Creatv
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert f'<a href="#experimentos?exp={eid}">Hecho en Creatv · Cojín otoño</a>' in html
    assert f"?exp={eid}#experimentos" not in html


def test_panel_recien_conectado_sin_copia(app, monkeypatch):  # noqa: F811
    _conectar()
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "Todavía no hay métricas copiadas" in html and "Sincronizar ahora" in html


def test_sincronizar_encola(app):  # noqa: F811
    _conectar()
    r = app["c"].post("/cliente/acme/triple-whale/sincronizar")
    assert r.status_code == 302 and r.headers["Location"].endswith("#triplewhale")
    assert _tareas("tw_sincronizar") == [{"job_id": "acme__tw_sync", "payload": {"cliente": "acme"}, "max_intentos": 2}]


def test_evaluar_crea_la_evaluacion_con_la_muestra_y_encola_una_sola_vez(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = app["c"].post("/cliente/acme/triple-whale/evaluar", data={"dias": "30", "canal": ""})
    assert r.status_code == 302
    [fila] = datos.evaluaciones("acme")
    assert fila["estado"] == "en_cola" and fila["moneda"] == "USD" and fila["pedido_por"] == "admin"
    assert {a["ad_id"] for a in fila["anuncios"]} >= {"g1", "g2", "p1", "p2"}
    assert fila["extra"]["modelo"] == "Triple Attribution" and fila["extra"]["meta_roas"] == 2.0
    [tarea] = _tareas("tw_evaluar")
    assert tarea["max_intentos"] == 1 and tarea["payload"] == {"cliente": "acme", "evaluacion_id": fila["id"]}
    # Un segundo clic mientras la primera sigue viva no crea otra ni paga dos veces.
    app["c"].post("/cliente/acme/triple-whale/evaluar", data={"dias": "30"})
    assert len(datos.evaluaciones("acme")) == 1 and len(_tareas("tw_evaluar")) == 1


def test_evaluar_sin_datos_no_encola(app):  # noqa: F811
    _conectar()
    r = app["c"].post("/cliente/acme/triple-whale/evaluar", data={"dias": "30"}, follow_redirects=True)
    assert "datos suficientes" in r.data.decode()
    assert datos.evaluaciones("acme") == [] and _tareas("tw_evaluar") == []


def _evaluacion_lista():
    m = [{"ref": "A1", "canal": "facebook-ads", "ad_id": "g1", "nombre": "Anuncio g1", "veredicto": "ganador",
          "motivo": "ROAS 6", "problemas": [], "fortalezas": [], "m": {"roas": 6.0},
          "medio": {"imagen": "https://x/g1.jpg", "titulo": "T", "texto": "B", "tipo": "imagen"}},
         {"ref": "A2", "canal": "facebook-ads", "ad_id": "p1", "nombre": "Anuncio p1", "veredicto": "perdedor",
          "motivo": "ROAS 0", "problemas": [], "fortalezas": [], "m": {"roas": 0.0}},
         {"ref": "A3", "canal": "facebook-ads", "ad_id": "p2", "nombre": "Anuncio p2", "veredicto": "perdedor",
          "motivo": "ROAS 0", "problemas": [], "fortalezas": [], "m": {"roas": 0.0}}]
    eid = datos.crear_evaluacion("acme", _hace(29), _hace(0), "USD", m)
    datos.actualizar_evaluacion(eid, estado="lista", usd=0.12,
                                resultado=analisis.parsear(respuesta(), {"A1", "A2", "A3"}, ""))
    return eid


def test_panel_muestra_la_ultima_evaluacion_lista(app):  # noqa: F811
    _conectar()
    _sembrar()
    eid = _evaluacion_lista()
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "Ganan las demostraciones cortas." in html and "Demostración en los primeros 2 s" in html
    assert "Caja que se abre sola" in html and "Basada en: Anuncio g1" in html
    assert f"/cliente/acme/triple-whale/evaluacion/{eid}/idea/0/crear" in html
    assert f"/cliente/acme/triple-whale/evaluacion/{eid}/anuncio/A1/referente" in html
    assert f"/evaluacion/{eid}/anuncio/A2/referente" not in html      # perdedor y sin miniatura


def test_idea_a_crear_deja_el_formulario_precargado(app):  # noqa: F811
    _conectar()
    eid = _evaluacion_lista()
    r = app["c"].post(f"/cliente/acme/triple-whale/evaluacion/{eid}/idea/0/crear")
    assert r.status_code == 302 and r.headers["Location"].endswith("#creativeflowplus")
    with app["c"].session_transaction() as s:
        assert s["fp_prefill"]["texto"].startswith("Top-down shot") and s["fp_prefill"]["tipo"] == "video"
        assert s["fp_prefill"]["origen_tw"] == f"{eid}:0"
    assert app["c"].post(f"/cliente/acme/triple-whale/evaluacion/{eid}/idea/9/crear").status_code == 404
    otra = datos.crear_evaluacion("acme", _hace(1), _hace(0), "USD", [])
    assert app["c"].post(f"/cliente/acme/triple-whale/evaluacion/{otra}/idea/0/crear").status_code == 404


def test_ganador_a_referentes(app, monkeypatch):  # noqa: F811
    from referentes import datos as ref_datos
    from referentes import imagenes
    _conectar()
    eid = _evaluacion_lista()
    monkeypatch.setattr(imagenes, "guardar_en_r2", lambda aid, url, carpeta: f"https://r2/{aid}.jpg")
    r = app["c"].post(f"/cliente/acme/triple-whale/evaluacion/{eid}/anuncio/A1/referente", follow_redirects=True)
    assert "Guardado en Referentes" in r.data.decode()
    [ref] = ref_datos.listar("acme", {"fuente": "triple_whale"})["items"]
    assert ref["anuncio_id"] == "tw:g1" and ref["etapa"] == "TOF"
    r = app["c"].post(f"/cliente/acme/triple-whale/evaluacion/{eid}/anuncio/A2/referente", follow_redirects=True)
    assert "no tiene miniatura" in r.data.decode()
    assert app["c"].post(f"/cliente/acme/triple-whale/evaluacion/{eid}/anuncio/A9/referente").status_code == 404


def test_post_de_otro_sitio_se_rechaza(app):  # noqa: F811
    _conectar()
    r = app["c"].post("/cliente/acme/triple-whale/sincronizar", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and _tareas("tw_sincronizar") == []


def test_otro_proyecto_no_ve_el_panel(app):  # noqa: F811
    from tests.test_rutas_productos import _cliente_admin  # noqa: F401
    import dashboard
    _conectar()
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s.update({"usuario": "otro", "rol": "cliente", "cliente": "otro"})
    r = c.get("/cliente/acme/triple-whale/panel")
    assert r.status_code in (302, 403, 404)


# ---- lo que más se vende, pausar/activar, la tienda en el Tablero (spec §11-§13) ----

def _sembrar_productos():
    import sqlalchemy as sa
    datos.reemplazar_productos("acme", _tienda(), _hace(9), _hace(0), [
        {"fecha": _hace(1), "producto_id": "8891", "nombre": "Cojín lumbar", "sku": "C-1", "unidades": 12, "ingresos": 480, "pedidos": 10},
        {"fecha": _hace(1), "producto_id": "7770", "nombre": "Lámpara", "sku": "L-1", "unidades": 2, "ingresos": 120, "pedidos": 2}])
    datos.reemplazar_productos("acme", _tienda(), _hace(39), _hace(30), [
        {"fecha": _hace(35), "producto_id": "8891", "nombre": "Cojín lumbar", "unidades": 6, "ingresos": 240, "pedidos": 5}])
    with db.conectar() as con:
        con.execute(db.producto.insert().values(
            cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(), fuente="shopify", fuente_id="8891",
            nombre="Cojín lumbar Pro", archivado=False, extra={}, fotos=[], prioridad=0, en_prueba=False))


def test_panel_muestra_lo_que_mas_se_vende_con_su_variacion_y_el_catalogo(app):  # noqa: F811
    _conectar()
    _sembrar()
    _sembrar_productos()
    html = app["c"].get("/cliente/acme/triple-whale/panel?dias=30").data.decode()
    assert "Lo que más se vende" in html and "Cojín lumbar" in html and "Lámpara" in html
    assert "+100 %" in html                                   # 480 vs 240 el periodo anterior
    assert "En tu catálogo: Cojín lumbar Pro" in html and 'data-ir-tab="catalogo"' in html
    # Con filtro de canal no aplica (la tienda no se parte por canal).
    assert "Lo que más se vende" not in app["c"].get("/cliente/acme/triple-whale/panel?canal=tiktok-ads").data.decode()


def test_tabla_ofrece_pausar_o_activar_solo_las_piezas_de_creatv(app, monkeypatch):  # noqa: F811
    from tests.test_triple_whale_analisis import _experimento_con_anuncio
    _conectar()
    _sembrar()
    _, ep_activa = _experimento_con_anuncio("g1", estado="activo")
    _, ep_pausada = _experimento_con_anuncio("p1", estado="pausado")
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert f"/cliente/acme/triple-whale/pieza/{ep_activa}/pausar" in html
    assert f"/cliente/acme/triple-whale/pieza/{ep_pausada}/activar" in html
    assert f"/pieza/{ep_activa}/activar" not in html and "/pieza/0/" not in html
    assert html.count("triple-whale/pieza/") == 2          # g2, p2, n1, t1 no son de Creatv


def test_pausar_y_activar_van_por_el_lanzador(app, monkeypatch):  # noqa: F811
    import lanzador
    _conectar()
    llamadas = []
    monkeypatch.setattr(lanzador, "pausar_pieza", lambda cliente, ep_id: llamadas.append(("pausar", cliente, ep_id)))
    monkeypatch.setattr(lanzador, "activar_pieza", lambda cliente, ep_id: llamadas.append(("activar", cliente, ep_id)))
    r = app["c"].post("/cliente/acme/triple-whale/pieza/7/pausar")
    assert r.status_code == 302 and r.headers["Location"].endswith("#triplewhale")
    app["c"].post("/cliente/acme/triple-whale/pieza/7/activar")
    assert llamadas == [("pausar", "acme", 7), ("activar", "acme", 7)]
    assert app["c"].post("/cliente/acme/triple-whale/pieza/7/borrar").status_code == 404

    def _no_existe(cliente, ep_id):
        raise ValueError("Esa pieza no existe.")
    monkeypatch.setattr(lanzador, "pausar_pieza", _no_existe)
    r = app["c"].post("/cliente/acme/triple-whale/pieza/7/pausar", follow_redirects=True)
    assert "Esa pieza no existe" in r.data.decode()

    def _meta(cliente, ep_id):
        raise RuntimeError("Meta Ads (x) respondió 400: access_token=EAAB-secreto")
    monkeypatch.setattr(lanzador, "activar_pieza", _meta)
    html = app["c"].post("/cliente/acme/triple-whale/pieza/7/activar", follow_redirects=True).data.decode()
    assert "Meta no aceptó el cambio" in html and "EAAB-secreto" not in html
    assert app["c"].post("/cliente/acme/triple-whale/pieza/7/pausar", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_tablero_muestra_la_tienda_segun_triple_whale(app):  # noqa: F811
    # El Tablero se fundió en Experimentos (E2): la tienda según Triple Whale sale en el historial (sección 09) del
    # fragmento de resultados, y en la nota de «Resumen del periodo» (01) con ingresos y MER.
    assert "Tu tienda según Triple Whale" not in _resultados(app["c"])
    _conectar()
    _sembrar()
    html = _resultados(app["c"])
    historial = html[html.index("Historial mes a mes"):]
    assert "Tu tienda según Triple Whale" in historial and "MER" in historial and 'data-ir-tab="triplewhale"' in historial
    resumen = html[html.index('aria-labelledby="cr-s01"'):html.index('aria-labelledby="cr-s02"')]
    assert "Tu tienda según Triple Whale" in resumen and "MER" in resumen
    # Y la página no trae ni panel ni botón «tablero»: abre en Experimentos.
    pagina = app["c"].get("/cliente/acme").data.decode()
    assert 'id="tab-tablero"' not in pagina and "Tu tienda según Triple Whale" not in pagina

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


def _conectar(cliente="acme", dominio="acme.myshopify.com", pais=None, llave="tw_secreto_123"):
    """Conecta una tienda (con su copia hecha) y devuelve su id."""
    tid = triple_whale_tiendas.agregar(cliente, llave, dominio, pais, moneda="USD")
    triple_whale_tiendas.actualizar_tienda(cliente, tid, ultima_sincronizacion=db.ahora())
    return tid


def _tienda(cliente="acme"):
    """El id de la (única) tienda conectada en la prueba."""
    return triple_whale_tiendas.tiendas(cliente)[0]["id"]


def _sembrar(tienda_id=None, dias=10):
    """Seis anuncios de Meta con 10 días de datos: dos ganadores, dos
    perdedores, uno sin datos y uno de TikTok; y la tienda. En la primera
    tienda del proyecto si no se dice cuál."""
    tienda_id = tienda_id or _tienda()
    canal, pixel, tienda = [], [], []
    for dia in range(dias):
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
    datos.reemplazar_anuncios_canal("acme", tienda_id, _hace(dias - 1), _hace(0), canal)
    datos.reemplazar_anuncios_pixel("acme", tienda_id, _hace(dias - 1), _hace(0), pixel)
    datos.reemplazar_tienda("acme", tienda_id, _hace(dias - 1), _hace(0), tienda)


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
    assert "Resultados de tu tienda" in html and "Retorno (MER)" in html and "Tus anuncios" in html
    assert "Anuncio g1" in html and "Anuncio p1" in html
    assert "Ganador" in html and "Perdedor" in html and "Sin datos suficientes" in html
    assert 'id="tw-resultados-datos"' in html and 'class="tb-grafico"' not in html
    assert "Sin rastreo de Triple Whale" in html            # p2 no lleva los parámetros
    assert "TikTok" in html and 'data-tw-param="canal"' in html
    assert "/cliente/acme/triple-whale/evaluar" in html and "aprox." in html
    assert "tw_secreto_123" not in html
    # Filtro por canal: solo TikTok.
    solo_tt = app["c"].get("/cliente/acme/triple-whale/panel?canal=tiktok-ads&dias=7").data.decode()
    assert "Anuncio t1" in solo_tt and "Anuncio g1" not in solo_tt and "Resultados de tu tienda" not in solo_tt
    assert "Resultados de TikTok" in solo_tt and "Ventas atribuidas" in solo_tt
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
    tid = _conectar()
    r = app["c"].post("/cliente/acme/triple-whale/sincronizar")
    assert r.status_code == 302 and r.headers["Location"].endswith("#triplewhale")
    assert _tareas("tw_sincronizar") == [{"job_id": f"acme__tw_sync__{tid}", "payload": {"cliente": "acme", "tienda_id": tid},
                                          "max_intentos": 2}]


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
    historial = html[html.index("Totales desde el inicio"):]
    assert "Tu tienda según Triple Whale" in historial and "MER" in historial and 'data-ir-tab="triplewhale"' in historial
    resumen = html[html.index('aria-labelledby="cr-s01"'):html.index('aria-labelledby="cr-s02"')]
    assert "Tu tienda según Triple Whale" in resumen and "MER" in resumen
    # Y la página no trae ni panel ni botón «tablero»: abre en Experimentos.
    pagina = app["c"].get("/cliente/acme").data.decode()
    assert 'id="tab-tablero"' not in pagina and "Tu tienda según Triple Whale" not in pagina


# ---- varias tiendas (spec 2026-10-08 §6.2 y §8) ----

def _dos_tiendas(compartida=True):
    """Noruega con los seis anuncios de `_sembrar`; Suecia con dos anuncios propios (s1 vende, s2 no) y, si
    `compartida`, el mismo g1 de Noruega (la cuenta de Meta es una sola: su gasto llega por las dos tiendas)."""
    no = _conectar(dominio="happyflops-norge.myshopify.com", pais="NO", llave="tw_llave_no_1")
    se = _conectar(dominio="happyflops-sverige.myshopify.com", pais="SE", llave="tw_llave_se_2")
    _sembrar(no)
    canal, pixel, tienda = [], [], []
    for dia in range(10):
        f = _hace(dia)
        filas = [("s1", 25, 2500, 2, 300), ("s2", 35, 2800, 0, 0)] + ([("g1", 20, 2000, 1, 80)] if compartida else [])
        for ad, gasto, imp, pedidos, ingresos in filas:
            canal.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "anuncio": f"Anuncio {ad}", "gasto": gasto,
                          "impresiones": imp, "clics": imp // 50, "vistas_3s": imp // 3, "thruplays": imp // 10,
                          "utm_ok": True})
            pixel.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "pedidos": pedidos, "ingresos": ingresos})
        tienda.append({"fecha": f, "gasto": 80, "ingresos": 700, "pedidos": 6, "nc_pedidos": 3})
    datos.reemplazar_anuncios_canal("acme", se, _hace(9), _hace(0), canal)
    datos.reemplazar_anuncios_pixel("acme", se, _hace(9), _hace(0), pixel)
    datos.reemplazar_tienda("acme", se, _hace(9), _hace(0), tienda)
    return no, se


NOTA_COMPARTIDA = "Estas tiendas comparten cuenta publicitaria"


def test_panel_con_dos_tiendas_selector_por_tienda_y_nota_de_cuenta_compartida(app):  # noqa: F811
    no, se = _dos_tiendas()
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert 'data-tw-param="tienda"' in html and "Todas las tiendas (2)" in html
    assert "🇳🇴 Noruega" in html and "🇸🇪 Suecia" in html
    assert f'<option value="{no}"' in html and f'<option value="{se}"' in html
    assert "Por tienda" in html and NOTA_COMPARTIDA in html
    por_tienda = html[html.index("Por tienda"):html.index("Tus anuncios")]
    assert "Noruega" in por_tienda and "Suecia" in por_tienda and "tw-tabla-scroll" in por_tienda
    # «Todas» suma los anuncios de las dos tiendas.
    assert "Anuncio g1" in html and "Anuncio s1" in html
    assert "tw_llave_no_1" not in html and "tw_llave_se_2" not in html


def test_panel_de_una_tienda_sin_por_tienda_y_con_el_aviso_del_roas(app):  # noqa: F811
    no, se = _dos_tiendas()
    html = app["c"].get(f"/cliente/acme/triple-whale/panel?tienda={se}").data.decode()
    assert f'<option value="{se}" selected>' in html and "Por tienda" not in html
    assert "Anuncio s1" in html and "Anuncio p1" not in html          # p1 solo corre en Noruega
    assert NOTA_COMPARTIDA in html and "solo cuenta las ventas de esta tienda" in html
    # El formulario de «Evaluar con IA» manda la tienda que se está viendo.
    assert f'name="tienda" value="{se}"' in html


def test_panel_sin_cuenta_compartida_no_pone_la_nota(app):  # noqa: F811
    _dos_tiendas(compartida=False)
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "Por tienda" in html and NOTA_COMPARTIDA not in html


NOTA_EVALUAR = "Esta tienda comparte cuenta publicitaria: para evaluar anuncios conviene"


def test_nota_de_cuenta_compartida_segun_la_tienda_que_se_mira(app):  # noqa: F811
    """Revisión del guardián del gasto (2026-10-08): la nota sale del gasto duplicado del alcance que se
    mira. Una tercera tienda con cuenta propia no la muestra; una que comparte la repite junto a «Evaluar
    con IA» (evaluarla sola lee el gasto de los anuncios de los otros países); «Todas» no repite."""
    no, se = _dos_tiendas()
    dk = _conectar(dominio="happyflops-danmark.myshopify.com", pais="DK", llave="tw_llave_dk_3")
    canal, pixel = [], []
    for dia in range(10):
        f = _hace(dia)
        for ad, gasto, pedidos in (("d1", 30, 2), ("d2", 25, 0)):
            canal.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "anuncio": f"Anuncio {ad}",
                          "gasto": gasto, "impresiones": 2000, "clics": 40, "utm_ok": True})
            pixel.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "pedidos": pedidos, "ingresos": pedidos * 90})
    datos.reemplazar_anuncios_canal("acme", dk, _hace(9), _hace(0), canal)
    datos.reemplazar_anuncios_pixel("acme", dk, _hace(9), _hace(0), pixel)

    propia = app["c"].get(f"/cliente/acme/triple-whale/panel?tienda={dk}").data.decode()
    assert "Anuncio d1" in propia and NOTA_COMPARTIDA not in propia and NOTA_EVALUAR not in propia
    compartida = app["c"].get(f"/cliente/acme/triple-whale/panel?tienda={se}").data.decode()
    assert NOTA_COMPARTIDA in compartida and NOTA_EVALUAR in compartida
    ia = compartida[compartida.index('id="tw-ia"'):]
    assert NOTA_EVALUAR in ia and "Todas las tiendas" in ia
    todas = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert NOTA_COMPARTIDA in todas and NOTA_EVALUAR not in todas


def test_por_tienda_va_en_el_orden_de_las_tiendas_no_por_id(app):  # noqa: F811
    """Revisión del spec (2026-10-08): «Por tienda» sigue el orden de `triple_whale_tiendas.tiendas` (por
    país, las sin país al final, luego id), el mismo del selector; antes salía por id de la tienda."""
    sin_pais = _conectar(dominio="acme.myshopify.com")                                   # id menor, sin país
    se = _conectar(dominio="happyflops-sverige.myshopify.com", pais="SE", llave="tw_llave_se_2")
    no = _conectar(dominio="happyflops-norge.myshopify.com", pais="NO", llave="tw_llave_no_1")
    assert sin_pais < se < no
    for tid in (sin_pais, se, no):
        datos.reemplazar_tienda("acme", tid, _hace(1), _hace(1), [{"fecha": _hace(1), "ingresos": 100, "gasto": 10}])
        datos.reemplazar_anuncios_canal("acme", tid, _hace(1), _hace(1), [
            {"canal": "facebook-ads", "ad_id": f"a{tid}", "fecha": _hace(1), "gasto": 10, "impresiones": 1000}])
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    por_tienda = html[html.index("tw-por-tienda"):]
    por_tienda = por_tienda[:por_tienda.index("</table>")]
    posiciones = [por_tienda.index(t) for t in ("Noruega", "Suecia", "acme.myshopify.com")]
    assert posiciones == sorted(posiciones)


def test_tienda_de_otro_proyecto_o_invalida_es_todas(app):  # noqa: F811
    _dos_tiendas()
    ajena = _conectar(cliente="otro", dominio="otro-norge.myshopify.com")
    for valor in (ajena, "abc", "", 99999):
        html = app["c"].get(f"/cliente/acme/triple-whale/panel?tienda={valor}").data.decode()
        assert "Por tienda" in html and "Anuncio s1" in html and "Anuncio p1" in html, valor
        assert "otro-norge" not in html


def test_con_una_sola_tienda_no_hay_selector(app):  # noqa: F811
    _conectar()
    _sembrar()
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert 'data-tw-param="tienda"' not in html and "Por tienda" not in html and "Todas las tiendas" not in html
    assert "Resultados de tu tienda" in html and "acme.myshopify.com" in html


def test_evaluar_una_tienda_guarda_su_alcance_y_su_muestra(app):  # noqa: F811
    no, se = _dos_tiendas()
    app["c"].post("/cliente/acme/triple-whale/evaluar", data={"dias": "30", "tienda": str(se)})
    [fila] = datos.evaluaciones("acme")
    assert fila["extra"]["tienda_id"] == se and fila["extra"]["pais"] == "SE"
    ids = {a["ad_id"] for a in fila["anuncios"]}
    assert "s1" in ids and not ids & {"p1", "p2", "g2"}                # solo lo que corre en Suecia
    # La lista de evaluaciones dice el alcance.
    datos.actualizar_evaluacion(fila["id"], estado="lista", usd=0.1,
                                resultado=analisis.parsear(respuesta(), {a["ref"] for a in fila["anuncios"]}, ""))
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    cab = html[html.index('class="tw-eval-cab"'):]
    assert "Suecia" in cab[:400]


def test_evaluar_todas_y_tienda_ajena(app):  # noqa: F811
    _dos_tiendas()
    ajena = _conectar(cliente="otro", dominio="otro-norge.myshopify.com")
    app["c"].post("/cliente/acme/triple-whale/evaluar", data={"dias": "30", "tienda": str(ajena)})
    [fila] = datos.evaluaciones("acme")
    assert fila["extra"]["tienda_id"] is None and fila["extra"]["pais"] is None
    assert {"s1", "p1"} <= {a["ad_id"] for a in fila["anuncios"]}
    datos.actualizar_evaluacion(fila["id"], estado="lista", usd=0.1,
                                resultado=analisis.parsear(respuesta(), {a["ref"] for a in fila["anuncios"]}, ""))
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "Todas las tiendas" in html[html.index('class="tw-eval-cab"'):][:400]


def test_sincronizar_sin_tienda_encola_todas_y_con_tienda_solo_esa(app):  # noqa: F811
    no, se = _dos_tiendas()
    app["c"].post("/cliente/acme/triple-whale/sincronizar")
    assert sorted(t["job_id"] for t in _tareas("tw_sincronizar")) == sorted([f"acme__tw_sync__{no}", f"acme__tw_sync__{se}"])
    with db.conectar() as con:
        con.execute(db.tarea.delete())
    r = app["c"].post("/cliente/acme/triple-whale/sincronizar", data={"tienda_id": str(se)})
    assert r.status_code == 302
    assert [t["payload"] for t in _tareas("tw_sincronizar")] == [{"cliente": "acme", "tienda_id": se}]
    ajena = _conectar(cliente="otro", dominio="otro-norge.myshopify.com")
    assert app["c"].post("/cliente/acme/triple-whale/sincronizar", data={"tienda_id": str(ajena)}).status_code == 404
    assert app["c"].post("/cliente/acme/triple-whale/sincronizar", data={"tienda_id": "abc"}).status_code == 404
    assert len(_tareas("tw_sincronizar")) == 1


def test_una_barra_por_copia_en_curso_con_el_pais(app):  # noqa: F811
    from tareas import triple_whale as tareas_tw
    no, se = _dos_tiendas()
    assert tareas_tw.encolar_sync("acme") == 2
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert html.count("data-poll-job=") == 2
    assert f'data-poll-job="acme__tw_sync__{no}"' in html and f'data-poll-job="acme__tw_sync__{se}"' in html
    assert f'id="tw-sync-acme-{no}"' in html and f'id="tw-sync-acme-{se}"' in html
    assert "Trayendo métricas de Noruega" in html and "Trayendo métricas de Suecia" in html
    # Ningún <script> que corra (rule 8): el único es el JSON inerte que lee static/tw_resultados.js.
    assert "<script" not in html.replace('<script type="application/json" id="tw-resultados-datos">', "")


def test_panel_con_una_tienda_en_error_dice_cual(app):  # noqa: F811
    no, se = _dos_tiendas()
    triple_whale_tiendas.actualizar_tienda("acme", se, estado="error", error="La llave fue revocada")
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "La última copia de Suecia falló: La llave fue revocada" in html
    solo_no = app["c"].get(f"/cliente/acme/triple-whale/panel?tienda={no}").data.decode()
    assert "La llave fue revocada" not in solo_no


def test_el_panel_no_hace_una_consulta_por_anuncio(app):  # noqa: F811
    from tests.test_escala import _Consultas
    _dos_tiendas()
    with _Consultas() as pocas:
        assert app["c"].get("/cliente/acme/triple-whale/panel").status_code == 200
    filas = [{"canal": "facebook-ads", "ad_id": f"x{i}", "fecha": _hace(1), "anuncio": f"X {i}", "gasto": 5 + i,
              "impresiones": 500, "clics": 10, "vistas_3s": 100, "thruplays": 40, "utm_ok": True} for i in range(40)]
    datos.reemplazar_anuncios_canal("acme", _tienda(), _hace(1), _hace(1), filas)
    with _Consultas() as muchas:
        assert app["c"].get("/cliente/acme/triple-whale/panel").status_code == 200
    assert muchas.n - pocas.n <= 2, (pocas.n, muchas.n)


def test_resumen_mes_tienda_suma_todas_las_tiendas(app):  # noqa: F811
    from triple_whale import panel
    no, se = _dos_tiendas(compartida=False)
    hoy = date.today()
    r = panel.resumen_mes_tienda("acme", hoy=hoy)
    dias = min(10, hoy.day)                                    # días sembrados dentro del mes en curso
    assert r["moneda"] == "USD" and r["ingresos"] == pytest.approx((400 + 700) * dias)
    assert r["pedidos"] == pytest.approx((5 + 6) * dias)


def test_panel_abre_desde_el_inicio_y_resumen_total_de_la_tienda(app):  # noqa: F811
    """Daniel, 2026-10-08: las métricas en su totalidad, no por periodos cortos. La pestaña abre en «Desde el
    inicio» (todo lo copiado, sin comparación) y los tiles de Experimentos suman la tienda desde el primer día."""
    from triple_whale import panel
    _dos_tiendas(compartida=False)
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert '<option value="0" selected>Desde el inicio</option>' in html
    assert "todo lo copiado de Triple Whale" in html and "días anteriores" not in html
    assert "Cada país desde el inicio" in html
    assert "vs. periodo anterior" not in html         # sin comparación, sin columna vacía
    assert '<input type="hidden" name="dias" value="0">' in html
    # Un periodo corto se puede seguir eligiendo y vuelve a comparar.
    corto = app["c"].get("/cliente/acme/triple-whale/panel?dias=7").data.decode()
    assert '<option value="7" selected>' in corto
    assert "vs. periodo anterior" in corto
    # Los tiles de la tienda en Experimentos: los 10 días sembrados de las dos tiendas, sin variación.
    r = panel.resumen_total_tienda("acme", hoy=date.today())
    assert r["moneda"] == "USD" and r["ingresos"] == pytest.approx((400 + 700) * 10) and r["variacion"] == {}
    assert r["desde"] == _hace(9)


# ---- Resultados de tu tienda (spec 2026-10-08-tw-resultados) ----

def test_detalle_del_dia(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(1)}")
    html = r.data.decode()
    assert r.status_code == 200 and "Qué pasó el" in html and "Anuncio g1" in html
    assert "Meta" in html and "TikTok" in html and "según el Pixel" in html
    assert "el mismo día de la semana anterior" in html
    assert f'data-twr-dia="{_hace(2)}"' in html and 'data-twr-dia=""' in html     # ‹ va al día anterior; › no llega a hoy


def test_detalle_del_dia_valida_la_fecha(app):  # noqa: F811
    _conectar()
    _sembrar()
    assert app["c"].get("/cliente/acme/triple-whale/dia?fecha=ayer").status_code == 400
    assert app["c"].get("/cliente/acme/triple-whale/dia").status_code == 400
    assert app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(0)}").status_code == 400      # hoy, a medias
    assert app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(30)}").status_code == 400     # antes de la copia
    assert app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(9)}").status_code == 200      # el primer día


def test_detalle_del_dia_de_otro_proyecto_no(app):  # noqa: F811
    import dashboard
    _conectar()
    _sembrar()
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s.update({"usuario": "otro", "rol": "cliente", "cliente": "otro"})
    r = c.get(f"/cliente/acme/triple-whale/dia?fecha={_hace(1)}")
    assert r.status_code in (302, 403, 404) and b"Anuncio g1" not in r.data


def test_detalle_del_dia_por_canal_y_canal_raro(app):  # noqa: F811
    _conectar()
    _sembrar()
    html = app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(1)}&canal=tiktok-ads").data.decode()
    assert "Anuncio t1" in html and "Anuncio g1" not in html and "Por canal" not in html
    raro = app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(1)}&canal=<script>").data.decode()
    assert "Anuncio g1" in raro and "<script>" not in raro                      # canal desconocido = todos


def test_detalle_del_dia_dice_hecho_en_creatv(app, base_temporal):  # noqa: F811
    import experimentos as ex
    from tests.test_experimentos_db import PAISES, _pieza
    _conectar()
    _sembrar()
    eid = ex.crear("acme", "Cojín otoño", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "USD")
    ep = ex.agregar_pieza("acme", eid, _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None,
                                              legado="cf_tw2"), "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id="g1")
    html = app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(1)}").data.decode()
    assert f'<a href="#experimentos?exp={eid}">Hecho en Creatv · Cojín otoño</a>' in html


def test_resultados_pinta_tarjetas_lectura_creativos_y_tabla(app):  # noqa: F811
    _conectar()
    _sembrar(dias=20)                                                      # 7 días + sus 6 anteriores dentro de la copia
    html = app["c"].get("/cliente/acme/triple-whale/panel?dias=7").data.decode()
    for texto in ("Ventas", "Pedidos", "Gasto en anuncios", "Retorno (MER)", "Ticket promedio", "Costo por pedido",
                  "Clientes nuevos", "Tu mejor día fue el", "Ver los datos en tabla", 'data-twr-metrica="ventas"',
                  "Comparar", "Tendencia", "Por antigüedad", "Por canal", "Lo que dicen los números",
                  'data-twr-dia="', 'id="tw-cada-anuncio"', "Hoy va en"):
        assert texto in html, texto
    assert html.count('role="tab"') == 7                                   # 6 + clientes nuevos (nc_pedidos > 0)
    assert '"comparar": true' in html and "Vendiste" in html and "las variaciones comparan 6 días completos" in html
    corto = app["c"].get("/cliente/acme/triple-whale/panel?dias=30").data.decode()
    assert '"comparar": false' in corto                                    # el periodo anterior cae antes de la copia
    inicio = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert '"comparar": false' in inicio and "data-twr-comparar" not in inicio and "▲" not in inicio


def test_resultados_no_hace_una_consulta_por_dia(app):  # noqa: F811
    from tests.test_escala import _Consultas
    _conectar()
    _sembrar()
    assert app["c"].get("/cliente/acme/triple-whale/panel?dias=7").status_code == 200   # calienta caché y sesión
    with _Consultas() as corto:
        assert app["c"].get("/cliente/acme/triple-whale/panel?dias=7").status_code == 200
    with _Consultas() as largo:
        assert app["c"].get("/cliente/acme/triple-whale/panel?dias=90").status_code == 200
    assert largo.n == corto.n, (corto.n, largo.n)

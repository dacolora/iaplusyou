"""Tarjetas ligeras y detalle bajo demanda (spec 2026-09-28): la página pinta
24 tarjetas por lista sin el <template> del detalle; el detalle y «Ver más»
llegan por fetch."""
import os

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _plantilla(nombre):
    return open(os.path.join(RAIZ, "templates", nombre), encoding="utf-8").read()


def _admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    (tmp_path / "clientes" / "otro").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _admin(dashboard)}


def _sembrar(n, cliente="acme", desde=0, tipo="video", estado="video_listo", con_final=False, guion=False):
    """n sesiones con `creado_en` creciente (la lista va de la más nueva a la más vieja)."""
    import creative_flow
    ids = []
    for i in range(desde, desde + n):
        cf_id = creative_flow.crear(cliente, [], ["prod"], [], f"acción {i}", 8, "tono", "A",
                                    legado_id=f"cf_20260901_000000_{i:06d}",
                                    creado_en=f"2026-09-01T{i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}")
        campos = {"estado": estado, "tipo": tipo}
        if estado == "video_listo":
            campos["video_url"] = f"https://r2/videos/{cf_id}.mp4"
        creative_flow.actualizar(cliente, cf_id, **campos)
        if guion:
            creative_flow.guardar_guion_base(cliente, cf_id, {
                "idioma": "es", "pais": "CO", "precio_base": None,
                "bloques": [{"rol": "gancho", "inicio_s": 0, "fin_s": 3, "texto_pantalla": "Hola", "texto_voz": "Hola"}]})
        if con_final:
            fid = creative_flow.crear_final(cliente, cf_id, "es", "CO")
            creative_flow.actualizar_final(cliente, fid, estado="listo", url_video=f"https://r2/finales/{fid}.mp4",
                                           capas={"voz": {"proveedor": "fal", "estado": "ok"}})
        ids.append(cf_id)
    return ids


# ------------------------------------------------------------ Task 1: servidor

def test_creative_flow_item_devuelve_lo_mismo_que_la_lista(app):
    dashboard = app["dashboard"]
    ids = _sembrar(3, con_final=True, guion=True)
    lista = {i["id"]: i for i in dashboard._creative_flow_items("acme")}
    for cf in ids:
        assert dashboard._creative_flow_item("acme", cf) == lista[cf]
    assert dashboard._creative_flow_item("acme", "cf_no_existe") is None
    assert dashboard._creative_flow_item("otro", ids[0]) is None


def test_pagina_desde_y_listas(app):
    dashboard = app["dashboard"]
    assert dashboard._pagina_desde("24") == 24 and dashboard._pagina_desde("abc") == 0
    assert dashboard._pagina_desde("-5") == 0 and dashboard._pagina_desde(None) == 0
    _sembrar(30, con_final=True)
    _sembrar(2, desde=30, tipo="imagen")
    items = dashboard._creative_flow_items("acme")
    listas = dashboard._listas_crear(items)
    assert len(listas["crear"]) == 24 and listas["crear_total"] == 32
    assert listas["crear"][0]["id"] == "cf_20260901_000000_000031"          # la más nueva primero
    assert len(dashboard._listas_crear(items, n=None)["crear"]) == 32
    # Tablero de Final edition (2026-10-02): 30 videos con su final lista y
    # nada pendiente van todos a Finalizados; las imágenes no se pueden elegir.
    t = dashboard._tablero_final(items, {})
    assert t["fe_en_edicion"] == [] and t["fe_en_edicion_total"] == 0
    assert len(t["fe_finalizados"]) == 24 and t["fe_finalizados_total"] == 30
    assert t["fe_finalizados"][0][1]["idioma"] == "es"
    assert t["fe_cifras"]["elegibles"] == 30 and t["fe_cifras"]["finalizados"] == 30


def test_contexto_final_edition_tiene_lo_que_usan_los_detalles(app):
    ctx = app["dashboard"]._contexto_final_edition("acme")
    for clave in ("paises_fe", "voces_fe", "estilos_fe", "presets_mezcla", "precios", "ediciones_por_cf", "mi_musica",
                  "mis_voces_fe"):
        assert clave in ctx
    assert "guion" in ctx["precios"] and "final_por_pais" in ctx["precios"]


def test_contexto_final_edition_trae_mis_voces_sin_voice_id(app):
    import materiales
    import voces_propias
    v = materiales.registrar("acme", tipo="audio", origen=voces_propias.ORIGEN, url="https://r2/vp.mp3",
                             hash=materiales.hash_clave("voz_propia", "minimax", "mmx_1"), bytes=1, duracion_ms=1000,
                             costo_usd=3.0, extra={"nombre": "Astrid", "forma": "disenada", "voice_id": "mmx_1",
                                                   "idioma_muestra": "sv", "estrenada": True})
    assert app["dashboard"]._contexto_final_edition("acme")["mis_voces_fe"] == [{"valor": f"vp:{v['id']}", "nombre": "Astrid"}]


# ------------------------------------------------------------ Task 2: base.html

def test_base_trae_sondeos_por_atributo_ritmo_y_modal_remoto():
    base = _plantilla("base.html")
    assert "function arrancarSondeos(raiz)" in base
    assert "function intervaloSondeo(" in base and "document.hidden" in base and "visibilitychange" in base
    assert "function abrirDetalleRemoto(modal, cuerpo, url, alInsertar)" in base
    assert "'X-Requested-With': 'fetch'" in base
    # El observador de nodos insertados arranca sondeos además de videos.
    assert "arrancarSondeos(n)" in base
    assert "setTimeout(tick, intervaloSondeo(inicio))" in base and "setTimeout(tick, 1500)" not in base


# ------------------------------------------------------------ Task 3: Crear

def _pestana(html, id_, siguiente):
    return html.split(f'id="{id_}"')[1].split(f'id="{siguiente}"')[0]


def test_crear_pinta_24_tarjetas_sin_detalle_embebido(app):
    _sembrar(30)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    crear = _pestana(html, "tab-creativeflowplus", "tab-final")
    assert '<template class="generado-detalle">' not in crear
    assert "<script>iniciarPolling" not in crear
    assert crear.count('class="generado"') == 24
    assert 'data-siguiente="24"' in crear and "Generados (30)" in crear
    assert crear.count('data-detalle="/cliente/acme/creative_flow/') == 24


def test_crear_ver_mas_y_desde_raro(app):
    _sembrar(30)
    c = app["c"]
    r = c.get("/cliente/acme/crear/tarjetas?desde=24")
    assert r.status_code == 200 and r.mimetype == "text/html"
    html = r.get_data(as_text=True)
    assert html.count('class="generado"') == 6 and "data-siguiente" not in html
    assert c.get("/cliente/acme/crear/tarjetas?desde=abc").get_data(as_text=True).count('class="generado"') == 24


def test_detalle_de_crear(app):
    (cf,) = _sembrar(1)
    c = app["c"]
    r = c.get(f"/cliente/acme/creative_flow/{cf}/detalle")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Descargar" in html and f"/flowplus/reusar/{cf}" in html
    assert "detalle-acciones" in html and "<template" not in html
    assert c.get("/cliente/acme/creative_flow/cf_nada/detalle").status_code == 404
    assert c.get(f"/cliente/otro/creative_flow/{cf}/detalle").status_code == 404


def test_tarjeta_con_trabajo_vivo_usa_data_poll_job(app):
    import cola
    (cf,) = _sembrar(1, estado="video_generando")
    dashboard = app["dashboard"]
    jid = dashboard._job_id_creative_flow("acme", cf)
    cola.encolar("flowplus_video", {"cliente": "acme", "cf_id": cf}, job_id=jid, cliente="acme")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    crear = _pestana(html, "tab-creativeflowplus", "tab-final")
    assert f'data-poll-job="{jid}"' in crear and f'id="trabajo-{jid}"' in crear
    assert "<script>iniciarPolling" not in crear


# ------------------------------------------------------------ Task 4: Final edition

def test_final_pinta_el_tablero_sin_repetir_la_lista_de_crear(app):
    """Tablero (2026-10-02): «En edición» (videos empezados) y «Finalizados»
    (finales listas), 24 por columna; los videos listos de Crear no se pintan:
    el selector «+ Nueva» los pide por fetch al abrirse."""
    _sembrar(30, con_final=True, guion=True)          # terminados: a Finalizados
    _sembrar(26, desde=30, guion=True)                 # con guion y sin finales: en edición
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    final = _pestana(html, "tab-final", "tab-experimentos")
    assert "<template" not in final and "<script>iniciarPolling" not in final
    assert 'id="fe-videos"' not in final and "Videos listos" not in final
    en_edicion = final.split('id="fe-editando"')[1].split("</section>")[0]
    finalizados = final.split('id="fe-finalizados"')[1].split("</section>")[0]
    assert en_edicion.count('class="generado"') == 24 and 'data-siguiente="24"' in en_edicion
    assert finalizados.count('class="generado generado-final"') == 24 and 'data-siguiente="24"' in finalizados
    assert 'fe-contador">26<' in final and 'fe-contador">30<' in final
    assert en_edicion.count('/final/detalle"') == 24 and finalizados.count('__es_CO/detalle"') == 24
    assert "data-fe-elegir" in en_edicion and "56 videos listos en Crear" in en_edicion
    selector = final.split('id="fe-elegibles"')[1].split("</dialog>")[0]
    assert 'class="generado' not in selector          # vacío hasta que se abre


def test_final_ver_mas_selector_y_lista_invalida(app):
    _sembrar(26, con_final=True)
    _sembrar(27, desde=26, guion=True)
    c = app["c"]
    assert c.get("/cliente/acme/final/tarjetas?lista=finalizados&desde=24").get_data(as_text=True).count("generado-final") == 2
    assert c.get("/cliente/acme/final/tarjetas?lista=en_edicion&desde=24").get_data(as_text=True).count('class="generado"') == 3
    elegir = c.get("/cliente/acme/final/tarjetas?lista=elegir").get_data(as_text=True)
    assert elegir.count('class="generado fe-elegible"') == 24 and 'data-siguiente="24"' in elegir
    assert "data-poll-job" not in elegir             # las barras van solo en «En edición»
    assert c.get("/cliente/acme/final/tarjetas?lista=elegir&desde=48").get_data(as_text=True).count('class="generado fe-elegible"') == 5
    assert "Todavía no hay videos listos" in c.get("/cliente/otro/final/tarjetas?lista=elegir").get_data(as_text=True)
    for invalida in ("videos", "finales", "x"):
        assert c.get(f"/cliente/acme/final/tarjetas?lista={invalida}").status_code == 400


def test_detalle_de_video_y_de_final(app):
    (con_guion,) = _sembrar(1, con_final=True, guion=True)
    (sin_guion,) = _sembrar(1, desde=1)
    (imagen,) = _sembrar(1, desde=2, tipo="imagen")
    c = app["c"]
    html = c.get(f"/cliente/acme/creative_flow/{con_guion}/final/detalle").get_data(as_text=True)
    assert "Producir finales" in html and "Guardar guion" in html and "angulo-editor" in html
    html = c.get(f"/cliente/acme/creative_flow/{sin_guion}/final/detalle").get_data(as_text=True)
    assert "Preparar guion" in html and "Producir finales" not in html
    assert c.get(f"/cliente/acme/creative_flow/{imagen}/final/detalle").status_code == 404
    assert c.get(f"/cliente/otro/creative_flow/{con_guion}/final/detalle").status_code == 404
    fid = f"{con_guion}__es_CO"
    html = c.get(f"/cliente/acme/creative_flow/{con_guion}/final/{fid}/detalle").get_data(as_text=True)
    assert "Capas" in html and "Descartar" in html
    assert c.get(f"/cliente/acme/creative_flow/{sin_guion}/final/{fid}/detalle").status_code == 404


def test_final_js_abre_por_enlace_aunque_la_tarjeta_no_este():
    js = _plantilla("_tab_final.html")
    assert "template.generado-detalle" not in js and "data-detalle" in _plantilla("_final_tarjetas.html")
    assert "fe_detalle_video" in js and "URL_DETALLE" in js and "abrirDetalleRemoto(" in js and "iniciarEditoresAngulo" in js


def test_detalle_muestra_el_estado_en_palabras(app):
    """Antes el detalle de una pieza mostraba el valor interno («video_listo»)."""
    c, dashboard = app["c"], app["dashboard"]
    cf = _sembrar(1)[0]
    html = c.get(f"/cliente/acme/creative_flow/{cf}/detalle").get_data(as_text=True)
    assert '<span class="tag-estado">Lista</span>' in html and ">video_listo<" not in html

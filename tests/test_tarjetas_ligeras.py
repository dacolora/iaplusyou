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
    # Tablero (2026-10-02): «&abrir=editor» busca la tarjeta en «En edición»,
    # y elegir un video del selector lo cierra antes de abrir el detalle.
    assert "panel.querySelector('#fe-editando .generado[data-cf=\"' + CSS.escape(cf)" in js
    assert "if (e.target.closest('[data-fe-elegir]')) { abrirElegir(); return; }" in js
    # Elegir en «+ Nueva» va directo al editor (2026-10-02): la edición que
    # ya tiene, la preparación gratis por POST, o esperar la que va en curso;
    # mientras se prepara, el tablero resalta la tarjeta en vez de abrir el
    # detalle encima.
    assert "if (elegir.contains(card)) { irAlEditor(card); return; }" in js
    assert "if (card.dataset.editorUrl) { location.href = card.dataset.editorUrl; return; }" in js
    assert "form.method = 'post';" in js and "form.action = card.dataset.desdeClon;" in js
    assert "if (card.dataset.abriendo) return;" in js
    assert "card.classList.add('fe-resaltada');" in js


def test_detalle_muestra_el_estado_en_palabras(app):
    """Antes el detalle de una pieza mostraba el valor interno («video_listo»)."""
    c, dashboard = app["c"], app["dashboard"]
    cf = _sembrar(1)[0]
    html = c.get(f"/cliente/acme/creative_flow/{cf}/detalle").get_data(as_text=True)
    assert '<span class="tag-estado">Lista</span>' in html and ">video_listo<" not in html


# ------------------------------------------------- Tablero de Final edition (2026-10-02)

def _vivo(tipo, job_id):
    import cola
    cola.encolar(tipo, {"cliente": "acme"}, cliente="acme", job_id=job_id)
    return job_id


def test_final_tablero_cada_barra_una_sola_vez_y_el_selector_sin_barras(app):
    """Con guion, editor y una final vivos a la vez, cada `trabajo-<job>` sale
    una sola vez en la página (una tapa visible y las demás ocultas), y el
    selector «+ Nueva» no pinta barras: un id repetido confunde al sondeo."""
    import creative_flow
    from tareas import edicion as tareas_edicion
    from tareas import final_edition as tareas_fe
    (cf,) = _sembrar(1, guion=True)
    _sembrar(2, desde=1)
    creative_flow.crear_final("acme", cf, "en", "US")
    jobs = [_vivo("final_guion", tareas_fe.job_id_guion("acme", cf)),
            _vivo("edicion_desde_clon", tareas_edicion.job_id_desde_clon("acme", cf)),
            _vivo("final_producir", tareas_fe.job_id_final("acme", cf, "en", "US"))]
    c = app["c"]
    html = c.get("/cliente/acme").get_data(as_text=True)
    for jid in jobs:
        assert html.count(f'id="trabajo-{jid}"') == 1, jid
        assert html.count(f'data-poll-job="{jid}"') == 1, jid
    elegir = c.get("/cliente/acme/final/tarjetas?lista=elegir").get_data(as_text=True)
    assert elegir.count('class="generado fe-elegible"') == 3 and "data-poll-job" not in elegir


def test_final_elegir_un_video_lleva_directo_al_editor(app):
    """«+ Nueva final edition» (pedido de Daniel, 2026-10-02): cada video del
    selector sabe cómo llegar al editor sin pasar por el detalle, por el
    mismo camino que «Editar»: su edición (la que abre «Editar»), la
    preparación gratis (POST a editor.desde_clon) o esperar la que va."""
    import ediciones
    from final_edition import documento
    from tareas import edicion as tareas_edicion
    sin_edicion, con_edicion, preparando = _sembrar(3)
    ed = ediciones.crear("acme", "video", "Mi corte", documento.nuevo_video("9:16"), cf_id=con_edicion,
                         creada_por="editor")
    _vivo("edicion_desde_clon", tareas_edicion.job_id_desde_clon("acme", preparando))
    html = app["c"].get("/cliente/acme/final/tarjetas?lista=elegir").get_data(as_text=True)

    def tarjeta(cf):
        return html.split(f'data-cf="{cf}"')[1].split("</video>")[0]

    assert f'data-desde-clon="/cliente/acme/ediciones/desde/{sin_edicion}"' in tarjeta(sin_edicion)
    assert "data-editor-url" not in tarjeta(sin_edicion)
    assert f'data-editor-url="/cliente/acme/ediciones/{ed["id"]}"' in tarjeta(con_edicion)
    assert "data-desde-clon" not in tarjeta(con_edicion)
    assert 'data-preparando="1"' in tarjeta(preparando)
    assert "data-editor-url" not in tarjeta(preparando) and "data-desde-clon" not in tarjeta(preparando)
    # El POST es el mismo de «Editar»: prepara gratis y vuelve con «&abrir=editor».
    r = app["c"].post(f"/cliente/acme/ediciones/desde/{sin_edicion}", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"#final?cf={sin_edicion}&abrir=editor")


def test_final_producida_desde_el_editor_cuenta_como_produciendose(app):
    """«Producir» del editor encola `edicion_producir` con su propio job_id
    (uno por edición): la final no es «con error» mientras se produce, lleva
    su barra y suma en «Produciéndose» (revisión del tablero, 2026-10-02)."""
    import creative_flow
    import ediciones
    from final_edition import documento
    from final_edition import tablero
    from tareas import edicion as tareas_edicion
    (cf,) = _sembrar(1)
    ed = ediciones.crear("acme", "video", "Mi corte", documento.nuevo_video("9:16"), cf_id=cf, creada_por="editor")
    creative_flow.crear_final("acme", cf, "es", "CO")
    jid = _vivo("edicion_producir", tareas_edicion.job_id_producir("acme", ed["id"], "es", "CO"))
    dashboard = app["dashboard"]
    t = tablero.armar(dashboard._creative_flow_items("acme"), dashboard._ediciones_por_cf("acme"))
    (_item, r), = t["en_edicion"]
    assert r["produciendo"] == 1 and r["con_error"] == 0 and r["siguiente"] == "produciendo"
    assert t["cifras"]["produciendo"] == 1
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert html.count(f'data-poll-job="{jid}"') == 1
    # Sin el trabajo vivo sí es una final interrumpida.
    (cf2,) = _sembrar(1, desde=1)
    creative_flow.crear_final("acme", cf2, "es", "CO")
    t = tablero.armar(dashboard._creative_flow_items("acme"), dashboard._ediciones_por_cf("acme"))
    assert {i["id"]: r["con_error"] for i, r in t["en_edicion"]} == {cf: 0, cf2: 1}


def test_final_editar_despues_y_volver_a_producir_lo_saca_de_en_edicion(app, monkeypatch):
    """Una edición guardada después de la última final devuelve el video a
    «En edición»; volver a producir ese destino lo saca (la final lleva su
    `actualizado_en`: `crear_final` conserva el `creado_en`)."""
    import creative_flow
    import db
    import ediciones
    from final_edition import documento
    from final_edition import tablero
    reloj = iter(f"2026-10-02T10:{m:02d}:00" for m in range(60))
    monkeypatch.setattr(db, "ahora", lambda: next(reloj))
    dashboard = app["dashboard"]

    def en_edicion():
        t = tablero.armar(dashboard._creative_flow_items("acme"), dashboard._ediciones_por_cf("acme"))
        return [i["id"] for i, _ in t["en_edicion"]]

    (cf,) = _sembrar(1)
    fid = creative_flow.crear_final("acme", cf, "es", "CO")
    creative_flow.actualizar_final("acme", fid, estado="listo", url_video="https://r2/f1.mp4")
    assert en_edicion() == []
    ed = ediciones.crear("acme", "video", "Mi corte", documento.nuevo_video("9:16"), cf_id=cf, creada_por="editor")
    ediciones.guardar("acme", ed["id"], documento.nuevo_video("9:16"), ed["version_n"])
    assert en_edicion() == [cf]
    creative_flow.crear_final("acme", cf, "es", "CO")
    creative_flow.actualizar_final("acme", fid, estado="listo", url_video="https://r2/f2.mp4")
    assert en_edicion() == []


def test_pnd133_detalle_remoto_rechaza_login_redirigido_en_node(app):
    import re
    import subprocess
    html = app['c'].get('/cliente/acme').get_data(as_text=True)
    textos = re.search(r'var T_BASE = \{.*?\n    \};', html, re.S).group()
    funciones = html[html.index('function avisoVacio('):html.index('window.abrirDetalleRemoto =')]
    codigo = textos + funciones + '''
    const assert = require('node:assert/strict');
    const document = {createElement:()=>({})};
    let sondeos=0, insertados=0, leidos=0;
    const arrancarSondeos=()=>sondeos++;
    const modal = {open:false,showModal(){this.open=true;}};
    const cuerpo = {innerHTML:'', appendChild(p){this.innerHTML=p.textContent;}};
    async function comprobar(respuesta) {
      global.fetch=async()=>respuesta;
      abrirDetalleRemoto(modal,cuerpo,'/detalle',()=>insertados++);
      await new Promise(resolve=>setImmediate(resolve));
    }
    (async()=>{
      await comprobar({ok:true,redirected:true,status:200,text:async()=>{leidos++;return '<form>login</form>';}});
      assert.equal(cuerpo.innerHTML,T_BASE.detalleNoCargo);
      assert.equal(leidos,0); assert.equal(sondeos,0); assert.equal(insertados,0);
      await comprobar({ok:false,redirected:false,status:404});
      assert.equal(cuerpo.innerHTML,T_BASE.detalleNoExiste);
      await comprobar({ok:true,redirected:false,status:200,text:async()=>'<article>detalle</article>'});
      assert.equal(cuerpo.innerHTML,'<article>detalle</article>');
      assert.equal(insertados,1); assert.equal(sondeos,1);
    })().catch(e=>{console.error(e);process.exitCode=1;});
    '''
    r = subprocess.run(['node','-e',codigo],capture_output=True,text=True)
    assert r.returncode == 0, r.stderr


def test_pnd120_alerta_abre_detalle_fuera_de_las_24_en_node(app):
    import json
    import re
    import subprocess
    import alertas
    import creative_flow
    ids = _sembrar(30)
    creative_flow.actualizar('acme', ids[0], estado='error', error='fallo')
    html = app['c'].get('/cliente/acme').get_data(as_text=True)
    crear = _pestana(html, 'tab-creativeflowplus', 'tab-final')
    assert f'id="cf-{ids[0]}"' not in crear
    a = next(a for a in alertas._fuente_crear('acme', '2026-09-02T00:00:00') if a['entidad'] == ids[0])
    assert a['url'] == '#creativeflowplus?cf=' + ids[0]
    script = next(s for s in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S) if "var modal = document.getElementById('generado-modal')" in s)
    codigo = """
    const assert = require('node:assert/strict');
    const pedidos = [], listeners = {};
    const el = {addEventListener(){}, dataset:{}, close(){}};
    global.document = {getElementById(){return el}, addEventListener(n, f){listeners[n]=f}};
    global.window = {addEventListener(n,f){listeners[n]=f}};
    global.location = {hash: HASH};
    global.abrirDetalleRemoto = (m,c,u) => pedidos.push(u);
    global.setTimeout = f => f();
    SCRIPT
    listeners.DOMContentLoaded && listeners.DOMContentLoaded();
    assert.deepEqual(pedidos, [URL]);
    location.hash = '#settings'; listeners.hashchange && listeners.hashchange();
    assert.equal(pedidos.length, 1);
    location.hash = '#creativeflowplus?cf=cf_otro'; listeners.hashchange && listeners.hashchange();
    assert.equal(pedidos[1], '/cliente/acme/creative_flow/cf_otro/detalle');
    location.hash = '#creativeflowplus?cf=../../otro'; listeners.hashchange && listeners.hashchange();
    assert.equal(pedidos.length, 2);
    """.replace('HASH', json.dumps(a['url'])).replace('URL', json.dumps(f'/cliente/acme/creative_flow/{ids[0]}/detalle')).replace('SCRIPT', script)
    r = subprocess.run(['node', '-e', codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert app['c'].get(f'/cliente/acme/creative_flow/{ids[0]}/detalle').status_code == 200
    assert app['c'].get('/cliente/otro/creative_flow/' + ids[0] + '/detalle').status_code == 404

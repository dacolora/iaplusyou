"""PND-037 (2026-10-16, spec docs/superpowers/specs/2026-10-16-organico-desde-crear-design.md): publicar en
redes desde cualquier video de Crear, no solo desde la ganadora de un experimento o una final.

El detalle de una pieza de Crear (llega por fetch, `cf_detalle`) trae el mismo bloque «Publicar orgánico» que
Experimentos y Final edition cuando la pieza es un video listo; nunca para una imagen ni para un video sin
terminar. Publicar crea filas `publicacion` con la `pieza` de esa sesión (origen manual, sin experimento) y encola
la tarea con max_intentos=1; una pieza de otro proyecto es un 404 sin crear, reservar ni encolar nada. Nunca se
publica de verdad: `publicador._publicar_una` revienta si alguien lo llama. Sin red: canales por meta.json falso y
tokens en un BASE_DIR temporal (fixture `app` de test_rutas_organico)."""
import contextlib
import json
import os
import re
import subprocess

import pytest

from tests.test_rutas_organico import FORM_OK, app  # noqa: F401 — `app` es la fixture
from tests.test_rutas_final_edition import _sesion_video_listo


@pytest.fixture(autouse=True)
def _nunca_publica(monkeypatch):
    import publicador
    monkeypatch.setattr(publicador, "_publicar_una",
                        lambda *a, **k: pytest.fail("una prueba nunca publica en una red de verdad"))


def _pieza_de(cf_id, cliente="acme"):
    import creative_flow as cf
    return cf.pieza_id_por_legado(cliente, cf_id)


def _detalle(app, cf_id):
    r = app["c"].get(f"/cliente/acme/creative_flow/{cf_id}/detalle", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _bloque(html):
    assert 'class="org-bloque"' in html
    return html[html.index('class="org-bloque"'):]


def _node(code):
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


# ---- el bloque en el detalle -------------------------------------------------------

def test_el_detalle_de_un_video_listo_trae_el_bloque_de_publicar(app, base_temporal):
    cf_id = _sesion_video_listo()
    pid = _pieza_de(cf_id)
    html = _detalle(app, cf_id)
    bloque = _bloque(html)
    assert "Publicación orgánica" in html
    assert f'name="pieza_id" value="{pid}"' in bloque and 'name="ep_id"' not in bloque
    assert 'name="volver" value="creativeflowplus"' in bloque and f'name="cf" value="{cf_id}"' in bloque
    # Precio a la vista antes de gastar (regla 1) y el aviso de confirmación con el video que se publica.
    assert "Escribir texto con IA ≈ US$ 0,06</button>" in bloque
    assert 'onsubmit="return window.orgConfirmar(this);"' in bloque and 'data-que="la persona camina"' in bloque
    # Los canales del proyecto: Instagram, Facebook y YouTube conectados; TikTok sin token, con su motivo.
    for p in ("instagram", "facebook", "youtube"):
        assert f'name="caption_{p}"' in bloque
    assert 'name="caption_tiktok"' not in bloque and "Falta token_tiktok.json" in bloque
    # Llega por fetch: sin <script> propio (el JS vive una vez en la página, org_scripts).
    assert "<script" not in html


def test_el_aviso_de_confirmar_recorta_lo_que_pidio_la_persona(app, base_temporal):
    import creative_flow as cf
    cf_id = _sesion_video_listo()
    cf.actualizar("acme", cf_id, accion_central="Una mujer abre la caja <b>y</b> sonríe " + "x" * 200)
    bloque = _bloque(_detalle(app, cf_id))
    que = re.search(r'data-que="([^"]*)"', bloque).group(1)
    assert que.startswith("Una mujer abre la caja &lt;b&gt;y&lt;/b&gt; sonríe") and que.endswith("…")
    assert len(que.replace("&lt;", "<").replace("&gt;", ">")) <= 80


@pytest.mark.parametrize("estado", ["video_generando", "error", "prompt_listo", "prompt_pendiente"])
def test_un_video_sin_terminar_no_trae_el_bloque(app, base_temporal, estado):
    import creative_flow as cf
    cf_id = cf.crear("acme", [], [], [], "la persona camina", 8, "", "A")
    # Con la URL de un video anterior (otro intento): lo que manda es que ESTE esté listo.
    cf.actualizar("acme", cf_id, estado=estado, video_url="https://r2/anterior.mp4")
    html = _detalle(app, cf_id)
    assert 'class="org-bloque"' not in html and "Publicación orgánica" not in html


def test_una_imagen_no_trae_el_bloque(app, base_temporal):
    import creative_flow as cf
    cf_id = cf.crear("acme", [], [], [], "producto sobre la mesa", 0, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", tipo="imagen", video_url="https://r2/i.png")
    html = _detalle(app, cf_id)
    assert 'class="org-bloque"' not in html and "Publicación orgánica" not in html


def test_sin_conexiones_dice_que_falta_por_red_y_lleva_a_canales_organicos(app, base_temporal):
    app["meta"].clear()
    os.remove(app["tmp"] / "clientes" / "acme" / "token_youtube.json")
    bloque = _bloque(_detalle(app, _sesion_video_listo()))
    for motivo in ("Conecta Meta con una Página", "Falta token_tiktok.json", "Falta token_youtube.json"):
        assert motivo in bloque
    assert 'name="caption_' not in bloque and ">Publicar</button>" not in bloque
    enlace = re.search(r'<a href="#config-canales-organicos"[^>]*onclick="([^"]+)"[^>]*>([^<]+)</a>', bloque)
    assert enlace and enlace.group(2) == "Configuración › Canales orgánicos"
    # Dentro del <dialog> del detalle: lo cierra, abre Configuración y baja a «Canales orgánicos» (apartado Conexiones).
    salida = _node(
        "const orden=[]; const document={querySelector:s=>({click:()=>orden.push('tab:'+s)})};"
        "const window={irAConfig:id=>orden.push('config:'+id)};"
        "const enlace={closest:s=>s==='dialog'?{open:true,close:()=>orden.push('cerrar')}:null};"
        "const r=(function(){" + enlace.group(1).replace("&#39;", "'") + "}).call(enlace);"
        "console.log(JSON.stringify([orden, r]));")
    orden, devuelto = json.loads(salida)
    assert orden == ["cerrar", "tab:.sidebar-item[data-tab=settings]", "config:config-canales-organicos"]
    assert devuelto is False


def test_la_seccion_de_canales_organicos_esta_donde_apunta_el_enlace(app):
    """El enlace del bloque lleva a `config-canales-organicos`, dentro del apartado Conexiones (irAConfig lo abre)."""
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    i = html.index('id="config-ap-conexiones"')
    assert i < html.index('id="config-canales-organicos"') < html.index('id="config-ap-marca"')


# ---- publicar ----------------------------------------------------------------------

def test_publicar_desde_crear_crea_filas_de_su_pieza_y_vuelve_al_detalle(app, base_temporal, monkeypatch):
    cf_id = _sesion_video_listo()
    pid = _pieza_de(cf_id)
    r = app["c"].post("/cliente/acme/organico/publicar",
                      data=dict(FORM_OK, pieza_id=str(pid), volver="creativeflowplus", cf=cf_id))
    assert r.status_code == 302 and r.headers["Location"].endswith(f"#creativeflowplus?cf={cf_id}")
    pubs = app["organico"].listar("acme", pieza_id=pid)
    assert [(p["plataforma"], p["estado"], p["origen"], p["experimento_pieza_id"]) for p in pubs] == \
        [("instagram", "en_cola", "manual", None), ("facebook", "en_cola", "manual", None)]
    (t,) = app["encolados"]
    assert t["tipo"] == "organico_publicar" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "pub_ids": [p["id"] for p in pubs]}
    # El detalle que reabre la vuelta: la barra de la publicación (data-poll-job, sin <script>) y sin formulario.
    monkeypatch.setattr(app["dashboard"].cola, "job_ids_vivos", lambda cliente, tipo: {t["job_id"]})
    html = _detalle(app, cf_id)
    assert f'data-poll-job="{t["job_id"]}"' in html and 'name="caption_instagram"' not in html
    assert "<script" not in html


def test_reintentar_desde_crear_vuelve_al_detalle(app, base_temporal):
    cf_id = _sesion_video_listo()
    pid = _pieza_de(cf_id)
    org = app["organico"]
    pub = org.crear("acme", pid, "instagram", "x #a #b #c")
    org.actualizar("acme", pub, estado="error", error="IG dijo que no")
    bloque = _bloque(_detalle(app, cf_id))
    reintentar = bloque[bloque.index("/reintentar"):]
    assert f'name="cf" value="{cf_id}"' in reintentar[:600]
    r = app["c"].post(f"/cliente/acme/organico/{pub}/reintentar", data={"volver": "creativeflowplus", "cf": cf_id})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"#creativeflowplus?cf={cf_id}")
    assert org.obtener("acme", pub)["estado"] == "en_cola" and len(app["encolados"]) == 1


@pytest.mark.parametrize("cf", ["javascript:alert(1)", "cf_1&exp=2", "", "x" * 10, "cf_" + "a" * 200])
def test_la_vuelta_solo_lleva_un_id_de_sesion_valido(app, base_temporal, cf):
    pid = _pieza_de(_sesion_video_listo())
    r = app["c"].post("/cliente/acme/organico/publicar",
                      data=dict(FORM_OK, pieza_id=str(pid), volver="creativeflowplus", cf=cf))
    assert r.status_code == 302 and r.headers["Location"].endswith("#creativeflowplus")


def test_una_pieza_de_otro_proyecto_es_404_y_no_crea_reserva_ni_encola(app, base_temporal, monkeypatch):
    ajena_cf = _sesion_video_listo(cliente="otro")
    ajena = _pieza_de(ajena_cf, "otro")
    reservas = []

    def _pedido(*a, **k):
        reservas.append(a)
        return contextlib.nullcontext()
    monkeypatch.setattr(app["dashboard"].libro_cobros, "pedido", _pedido)
    monkeypatch.setattr(app["dashboard"].organico, "redactar", lambda *a: pytest.fail("no se redacta una pieza ajena"))
    r = app["c"].post("/cliente/acme/organico/publicar",
                      data=dict(FORM_OK, pieza_id=str(ajena), volver="creativeflowplus", cf=ajena_cf))
    assert r.status_code == 404
    r = app["c"].post("/cliente/acme/organico/redactar", data={"pieza_id": str(ajena), "plataformas": ["instagram"]})
    assert r.status_code == 404 and r.get_json()["error"]
    # Una que no existe en ningún lado, igual.
    assert app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id="999999")).status_code == 404
    assert reservas == [] and app["encolados"] == []
    assert app["organico"].listar("otro") == [] and app["organico"].listar("acme") == []
    # Y el detalle de esa sesión no se abre desde acme.
    assert app["c"].get(f"/cliente/acme/creative_flow/{ajena_cf}/detalle").status_code == 404


def test_un_post_a_mano_de_una_imagen_o_un_video_sin_terminar_no_publica(app, base_temporal):
    import creative_flow as cf
    imagen = cf.crear("acme", [], [], [], "producto", 0, "", "A")
    cf.actualizar("acme", imagen, estado="video_listo", tipo="imagen", video_url="https://r2/i.png")
    a_medias = cf.crear("acme", [], [], [], "la persona camina", 8, "", "A")
    cf.actualizar("acme", a_medias, estado="video_generando")
    for cf_id in (imagen, a_medias):
        pid = _pieza_de(cf_id)
        r = app["c"].post("/cliente/acme/organico/publicar",
                          data=dict(FORM_OK, pieza_id=str(pid), volver="creativeflowplus", cf=cf_id))
        assert r.status_code == 302 and r.headers["Location"].endswith(f"#creativeflowplus?cf={cf_id}")
        assert app["organico"].listar("acme", pieza_id=pid) == []
    assert app["encolados"] == []


# ---- la confirmación (JS de la página, en Node) --------------------------------------

def _org_scripts(app):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    return re.search(r"<script>\s*var ORG_AVISO_MARCA_PLATAFORMA.*?</script>", html, re.S).group(0)[len("<script>"):-len("</script>")]


def _confirmar(app, que):
    codigo = _org_scripts(app)
    salida = _node(
        "const window={}; let visto=null; const alert=m=>{visto='alert:'+m;}; const confirm=m=>{visto=m; return true;};"
        + codigo +
        ";const casilla=(v,n)=>({value:v,dataset:{nombre:n}});"
        "const marcadas=[casilla('instagram','Instagram Reels'),casilla('facebook','Facebook (Página)')];"
        "marcadas.forEach=Array.prototype.forEach;"
        "const form={dataset:" + json.dumps({"que": que} if que is not None else {}) + ","
        "querySelectorAll:()=>marcadas, querySelector:()=>({value:'texto #a #b #c'})};"
        "const r=window.orgConfirmar(form); console.log(JSON.stringify([visto, r]));")
    return json.loads(salida)


def test_publicar_confirma_que_video_y_en_que_redes(app):
    visto, ok = _confirmar(app, "la persona $& camina")
    assert ok is True
    assert visto == ("Se publica el video «la persona $& camina» en Instagram Reels, Facebook (Página). "
                     "Es público y no se puede deshacer desde aquí. ¿Publicar?")
    # Sin `que` (Experimentos, Final edition) el aviso de siempre.
    visto, _ = _confirmar(app, None)
    assert visto == ("Se publica el video en Instagram Reels, Facebook (Página). "
                     "Es público y no se puede deshacer desde aquí. ¿Publicar?")


def test_cerrar_el_detalle_quita_el_cf_del_hash(app):
    """La vuelta de publicar deja `#creativeflowplus?cf=<id>` para reabrir el detalle; al cerrarlo el hash vuelve a
    `#creativeflowplus` (como Final edition), así la recarga de otra pieza que termina no lo reabre sola. Un hash que
    ya cambió (el enlace a Canales orgánicos cierra el diálogo antes de ir) no se toca."""
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    script = next(s for s in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
                  if "var modal = document.getElementById('generado-modal')" in s)
    salida = _node("""
    const oyentes = {}, cambios = [];
    const nodo = id => ({id, dataset:{}, innerHTML:'x', close(){}, addEventListener(n, f){ oyentes[id + ':' + n] = f; }});
    const nodos = {};
    global.document = {getElementById(id){ return nodos[id] || (nodos[id] = nodo(id)); }, addEventListener(){}};
    global.window = {addEventListener(){}};
    global.location = {hash: '#creativeflowplus?cf=cf_20261016_101010_1'};
    global.history = {replaceState(a, b, url){ cambios.push(url); location.hash = url; }};
    global.abrirDetalleRemoto = () => {};
    SCRIPT
    oyentes['generado-modal:close']();
    const vacio = nodos['generado-modal-cuerpo'].innerHTML;
    location.hash = '#config-canales-organicos';
    oyentes['generado-modal:close']();
    console.log(JSON.stringify([cambios, vacio]));
    """.replace("SCRIPT", script))
    assert json.loads(salida) == [["#creativeflowplus"], ""]

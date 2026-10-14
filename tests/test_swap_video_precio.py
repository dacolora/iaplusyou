"""Swaps de video por lo que dura el video (PND-312, pedido de Daniel 2026-10-13): antes todos se cobraban como
5 s y solo la salida (happyflops: 12 swaps de Seedance anotados en US$ 12,80 que costaron ≈ US$ 38). Las reglas
salen de la página de cada modelo, leídas el 2026-10-13 (ver providers/swap_video_precio.py)."""
import io
import json
import re
import shutil
import subprocess

import pytest

from tests.test_rutas_cuentas import _ana, _flashes, app  # noqa: F401 (fixture)


# --- la regla de cada modelo -----------------------------------------------------------------

@pytest.mark.parametrize("proveedor, duracion, fps, esperado", [
    ("seedance25_edit", 5, None, 2.20),      # «5 s de entrada + 5 s de salida a 720p: US$ 2,20»
    ("seedance25_edit", 4.74, None, 2.0856),
    ("seedance25_edit", 2, None, 1.76),      # la entrada se cuenta desde 4 s
    ("seedance25_edit", 40, None, 13.2),     # y hasta 30 s
    ("wan27_edit", 5, None, 1.00),           # «5 s: US$ 1,00 en 720p» (entrada + salida)
    ("wan27_edit", 4.2, None, 1.00),         # redondea al segundo
    ("wan27_edit", 1, None, 0.40),           # mínimo 2 s
    ("wan27_edit", 14.7, None, 2.00),        # máximo 10 s
    ("kling_o3_pro_edit", 5, None, 0.84),    # «5 s: US$ 0,840»
    ("kling_o3_pro_edit", 2, None, 0.504),   # «mínimo 3 s: US$ 0,504»
    ("kling_o3_pro_edit", 12, None, 1.68),   # «máximo 10 s: US$ 1,680»
    ("kling_o1", 5, None, 0.63),             # fal: US$ 0,126/s de salida
    ("luma_modify", 5, None, 1.75),          # fal: US$ 0,35/s
    ("wan_animate_replace", 5, 60, 0.75),    # «5 s a 60 fps = 300 cuadros / 16 × tarifa» (480p, 0,04)
    ("wan_animate_replace", 5, None, 0.375),  # sin fps medidos, 30
    ("luma_ray32_edit", 12, None, 0.72),     # fijo: 540p, 5 s
])
def test_cada_modelo_cobra_por_la_duracion_real(proveedor, duracion, fps, esperado):
    from providers import swap_video_precio
    assert swap_video_precio.costo(proveedor, duracion, fps) == pytest.approx(esperado)


def test_sin_tarifa_o_sin_duracion_no_hay_precio():
    from providers import swap_video_precio
    assert swap_video_precio.costo("modelo_nuevo", 5) is None
    assert swap_video_precio.costo("seedance25_edit", None) is None
    assert swap_video_precio.costo("luma_ray32_edit", None) == 0.72


def test_los_estimadores_de_cada_proveedor_usan_la_misma_tabla():
    import gastos
    from providers import comparador_modelos, kling_o1_client, wavespeed_client, wavespeed_video_edit
    assert wavespeed_video_edit.estimate_video("seedance25_edit", 9.73)["usd"] == pytest.approx(4.2812)
    assert wavespeed_client.estimate_video(5)["usd"] == pytest.approx(1.0)
    assert kling_o1_client.estimate_video(10)["usd"] == pytest.approx(1.26)
    assert comparador_modelos.estimate_video("wan_animate_replace", 4, fps=24)["usd"] == pytest.approx(0.24)
    est = gastos.estimar("swap", proveedor="seedance25_edit", formato="video", duracion=14.72)
    assert est["usd"] == pytest.approx(6.4768) and "14.72 s" in est["detalle"]


def _video(tmp_path, segundos=2, fps=25, nombre="clip.mp4"):
    if not shutil.which("ffmpeg"):
        pytest.skip("sin ffmpeg")
    ruta = tmp_path / nombre
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=160x120:rate={fps}",
                    "-t", str(segundos), "-pix_fmt", "yuv420p", str(ruta)], check=True)
    return ruta


@pytest.mark.slow
def test_medir_lee_duracion_y_cuadros_de_un_video_real(tmp_path):
    from providers import swap_video_precio
    duracion, fps = swap_video_precio.medir(str(_video(tmp_path, 2, 25)))
    assert duracion == pytest.approx(2.0, abs=0.05) and fps == pytest.approx(25)
    roto = tmp_path / "roto.mp4"
    roto.write_bytes(b"no soy un video")
    assert swap_video_precio.medir(str(roto)) == (None, None)
    assert swap_video_precio.medir(str(tmp_path / "no-existe.mp4")) == (None, None)


# --- la tarea anota lo real -------------------------------------------------------------------

def _swap_video(sw, monkeypatch, tmp_path, entrada):
    monkeypatch.setattr(sw, "BASE_DIR", str(tmp_path))
    original = tmp_path / "orig.mp4"
    original.write_bytes(b"mp4")
    monkeypatch.setattr(sw.swaps_mod, "cargar", lambda c: {"swap_v": {"foto_original_local": str(original),
                                                                     "tipo": "video", **entrada}})
    monkeypatch.setattr(sw.swaps_mod, "actualizar", lambda c, sid, **k: None)
    monkeypatch.setattr(sw.catalogo_productos, "encontrar",
                        lambda c, pid: {"id": pid, "tipo": "calzado", "mapa_texto": None, "referencias": [],
                                        "descripcion": "zapato"})
    monkeypatch.setattr(sw.marca_mod, "negative_prompt_efectivo", lambda c: "")
    monkeypatch.setattr(sw.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(sw.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(sw.wavespeed_video_edit, "editar_video", lambda *a, **k: "https://ws/salida.mp4")
    monkeypatch.setattr(sw, "_extraer_frame", lambda *a, **k: None)
    monkeypatch.setattr(sw, "_evaluar_swap_contra_matriz", lambda *a, **k: None)
    monkeypatch.setattr(sw.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(sw.trabajos, "reportar", lambda job_id, **k: None)

    class _Resp:
        content = b"mp4-salida"

        def raise_for_status(self):
            return None
    monkeypatch.setattr(sw.requests, "get", lambda *a, **k: _Resp())
    return {"cliente": "acme", "swap_id": "swap_v", "producto_id": "p1", "proveedor": "seedance25_edit",
            "tipo": "video", "mejorar_calidad": False}


def test_la_tarea_anota_el_swap_de_video_por_su_duracion(base_temporal, monkeypatch, tmp_path):
    import gastos
    import tareas.swap as sw
    payload = _swap_video(sw, monkeypatch, tmp_path, {"duracion_s": 9.73, "fps": 30})
    monkeypatch.setattr(sw.swap_video_precio, "medir", lambda ruta: pytest.fail("ya estaba medido"))
    sw.ejecutar({"id": 7, "job_id": "acme__swap_v__swap", "payload": payload})
    g = gastos.historial("acme")[0]
    assert g["referencia"] == "swap:swap_v:t7" and g["usd"] == pytest.approx(4.2812)   # (9,73 + 9,73) × 0,22


def test_un_swap_encolado_sin_medida_se_mide_en_la_tarea(base_temporal, monkeypatch, tmp_path):
    import gastos
    import tareas.swap as sw
    payload = _swap_video(sw, monkeypatch, tmp_path, {})
    monkeypatch.setattr(sw.swap_video_precio, "medir", lambda ruta: (14.72, 30.0))
    sw.ejecutar({"id": 8, "job_id": "acme__swap_v__swap", "payload": payload})
    assert gastos.historial("acme")[0]["usd"] == pytest.approx(6.4768)


# --- la ruta mide antes de reservar ------------------------------------------------------------

@pytest.mark.slow
def test_subir_un_video_lo_mide_reserva_por_su_duracion_y_lo_guarda(app, monkeypatch, tmp_path):  # noqa: F811
    d = app["dashboard"]
    monkeypatch.setattr(d.swaps_mod, "BASE_DIR", str(app["tmp"]))
    monkeypatch.setattr(d.catalogo_productos, "encontrar", lambda cliente, pid: {"id": pid})
    encolados, exigido = [], []
    monkeypatch.setattr(d.trabajos, "encolar", lambda *a, **k: encolados.append((a, k)) or True)
    monkeypatch.setattr(d.libro_cobros, "exigir", lambda cliente, usd, **k: exigido.append(usd))
    c = _ana(app)
    video = _video(tmp_path, 3, 25).read_bytes()
    c.post("/cliente/acme/swap/generar", data={"foto": (io.BytesIO(video), "clip.mp4"), "producto_id": "p1",
                                               "proveedor_video": "seedance25_edit", "precio_visto": "1.76"},
           content_type="multipart/form-data")
    assert exigido == [pytest.approx(1.76)]                 # 3 s → se cuenta desde 4 s: (4 + 4) × 0,22
    (args, kw), = encolados
    assert kw["costo_estimado"] == pytest.approx(1.76)
    swap = d.swaps_mod.cargar("acme")[args[2]["swap_id"]]
    assert swap["duracion_s"] == pytest.approx(3.0, abs=0.05) and swap["fps"] == pytest.approx(25)
    assert open(swap["foto_original_local"], "rb").read() == video     # el archivo se guardó entero


def test_un_video_que_no_se_puede_leer_no_se_sube(app, monkeypatch):  # noqa: F811
    d = app["dashboard"]
    monkeypatch.setattr(d.swaps_mod, "BASE_DIR", str(app["tmp"]))
    encolados = []
    monkeypatch.setattr(d.catalogo_productos, "encontrar", lambda cliente, pid: {"id": pid})
    monkeypatch.setattr(d.trabajos, "encolar", lambda *a, **k: encolados.append(a) or True)
    c = _ana(app)
    c.post("/cliente/acme/swap/generar", data={"foto": (io.BytesIO(b"no soy un video"), "clip.mp4"),
                                               "producto_id": "p1", "precio_visto": "999"}, content_type="multipart/form-data")
    assert encolados == []
    assert any("No pude leer la duración de ese video" in m for m in _flashes(c))


# --- lo que ve la persona antes de generar -----------------------------------------------------

def _datos_precio(html):
    m = re.search(r'<script type="application/json" id="swap-precio-datos">(.*?)</script>', html, re.S)
    assert m, "falta #swap-precio-datos"
    return json.loads(m.group(1))


def test_cambiar_producto_muestra_el_precio_con_el_margen_y_nunca_el_costo(app, monkeypatch):  # noqa: F811
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True, margen=3.0)
    html = _ana(app).get("/cliente/acme").get_data(as_text=True)
    assert 'id="swap-precio"' in html and "swap-precio.js" in html
    datos = _datos_precio(html)
    seedance = datos["precios"]["video"]["seedance25_edit"]
    assert seedance["usd_s"] == pytest.approx(0.66) and seedance["factor"] == 2 and seedance["min_s"] == 4
    assert datos["precios"]["video"]["luma_ray32_edit"] == {"fijo": pytest.approx(2.16)}
    assert datos["precios"]["foto"]["nano_banana"] == {"usd": pytest.approx(0.237)}   # (0,039 + 0,04 de la mejora) × 3
    assert "0.22" not in json.dumps(datos["precios"])                     # el costo no llega al navegador


def test_si_el_margen_no_se_puede_leer_dice_precio_no_disponible(app, monkeypatch):  # noqa: F811
    import gastos
    monkeypatch.setattr(gastos, "_margen_fallido", lambda: True)
    datos = _datos_precio(_ana(app).get("/cliente/acme").get_data(as_text=True))
    assert datos["precios"] is None and datos["textos"]["sinPrecio"]


# --- nunca más de lo que se vio (revisión de guardian-gasto, 2026-10-13) --------------------------

@pytest.mark.slow
@pytest.mark.parametrize("visto", [None, "1.20", "abc"])
def test_sin_precio_visto_o_con_uno_menor_no_se_guarda_ni_se_cobra(app, monkeypatch, tmp_path, visto):  # noqa: F811
    d = app["dashboard"]
    monkeypatch.setattr(d.swaps_mod, "BASE_DIR", str(app["tmp"]))
    monkeypatch.setattr(d.catalogo_productos, "encontrar", lambda cliente, pid: {"id": pid})
    encolados, exigido = [], []
    monkeypatch.setattr(d.trabajos, "encolar", lambda *a, **k: encolados.append(a) or True)
    monkeypatch.setattr(d.libro_cobros, "exigir", lambda cliente, usd, **k: exigido.append(usd))
    c = _ana(app)
    datos = {"foto": (io.BytesIO(_video(tmp_path, 3, 25).read_bytes()), "clip.mp4"), "producto_id": "p1",
             "proveedor_video": "seedance25_edit"}
    if visto is not None:
        datos["precio_visto"] = visto
    c.post("/cliente/acme/swap/generar", data=datos, content_type="multipart/form-data")
    assert encolados == [] and exigido == [] and d.swaps_mod.cargar("acme") == {}
    assert any("Este envío cuesta US$ 1,76" in m for m in _flashes(c))


@pytest.mark.slow
def test_medir_devuelve_duracion_y_cuadros_sin_guardar_nada(app, monkeypatch, tmp_path):  # noqa: F811
    d = app["dashboard"]
    monkeypatch.setattr(d.swaps_mod, "BASE_DIR", str(app["tmp"]))
    c = _ana(app)
    r = c.post("/cliente/acme/swap/medir", data={"video": (io.BytesIO(_video(tmp_path, 2, 50).read_bytes()), "c.mov")},
               content_type="multipart/form-data")
    j = r.get_json()
    assert r.status_code == 200 and j["duracion_s"] == pytest.approx(2.0, abs=0.05) and j["fps"] == pytest.approx(50)
    assert d.swaps_mod.cargar("acme") == {}
    malo = c.post("/cliente/acme/swap/medir", data={"video": (io.BytesIO(b"<html>"), "c.mp4")},
                  content_type="multipart/form-data")
    assert malo.status_code == 400 and not malo.get_json()["ok"]
    foto = c.post("/cliente/acme/swap/medir", data={"video": (io.BytesIO(b"x"), "c.png")},
                  content_type="multipart/form-data")
    assert foto.status_code == 400


def test_seedream_reserva_con_las_referencias_del_producto(base_temporal, monkeypatch, tmp_path):
    from tests.test_tareas_swap import _Archivo
    import dashboard
    monkeypatch.setattr(dashboard, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.aspect_ratio_mod, "detectar_gemini", lambda p: "9:16")
    monkeypatch.setattr(dashboard.swaps_mod, "crear", lambda *a, **k: "swap_s")
    capturado = {}
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda job_id, tipo, payload, **kw: capturado.update(kw) or True)
    producto = {"id": "p1", "referencias": [f"/r/{i}.jpg" for i in range(12)], "descripcion": "zapato"}
    dashboard._lanzar_swap("acme", _Archivo("foto.jpg"), producto, "p1", "seedream_v5_pro", "seedance25_edit", False)
    assert capturado["costo_estimado"] == pytest.approx(0.09 + 9 * 0.003)   # como cobra la tarea: hasta 9


def test_el_precio_del_navegador_es_el_de_python(base_temporal):
    """Mismo precio en la pantalla (static/swap-precio.js) y en el servidor, para cada modelo, duraciones de borde
    y cuadros por segundo; también las fotos de Seedream con sus referencias."""
    if not shutil.which("node"):
        pytest.skip("sin node")
    from providers import swap_video_precio, wavespeed_imagen
    casos = []
    for pid, t in swap_video_precio.TARIFAS.items():
        for d in (0.5, 1.2, 2, 3.4, 4.74, 5, 9.73, 10.2, 14.72, 31, 45):
            for fps in (None, 24, 60):
                casos.append({"t": t, "d": d, "fps": fps, "esperado": swap_video_precio.costo(pid, d, fps)})
    foto = {"usd": 0.09, "por_referencia": wavespeed_imagen.COSTO_USD_SEEDREAM_IMAGEN_EXTRA, "max_referencias": 9}
    fotos = [{"n": n, "esperado": wavespeed_imagen.estimate_seedream(n_imagenes=max(1, min(n, 9)) + 1)["usd"]}
             for n in (0, 1, 3, 9, 14)]
    programa = """
    const fs=require('fs'),assert=require('assert');globalThis.window=globalThis;
    globalThis.document={getElementById:()=>null};
    eval(fs.readFileSync('static/swap-precio.js','utf8'));
    const casos=%s, fotos=%s, foto=%s;
    for (const c of casos) {
      const v=SwapPrecio.precioVideo(c.t,c.d,c.fps,30);
      assert.ok(Math.abs(v-c.esperado)<1e-4, JSON.stringify(c)+' -> '+v);
    }
    for (const f of fotos) assert.ok(Math.abs(SwapPrecio.precioFoto(foto,f.n)-f.esperado)<1e-4, JSON.stringify(f));
    assert.equal(SwapPrecio.precioVideo(casos[0].t,null,null,30),null);
    assert.equal(SwapPrecio.precioFoto(foto,null),null);
    """ % (json.dumps(casos), json.dumps(fotos), json.dumps(foto))
    r = subprocess.run(["node", "-e", programa], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_la_pantalla_bloquea_generar_sin_precio_y_cuenta_las_referencias(app, monkeypatch):  # noqa: F811
    c = _ana(app)
    html = c.get("/cliente/acme").get_data(as_text=True)
    assert re.search(r'<button[^>]*id="swap-generar"[^>]*disabled', html)
    assert 'name="precio_visto" id="swap-precio-visto"' in html
    datos = _datos_precio(html)
    assert datos["precios"]["foto"]["seedream_v5_pro"]["por_referencia"] and datos["urlMedir"].endswith("/swap/medir")
    assert datos["precios"]["necesita_fps"] == ["wan_animate_replace"]
    d = app["dashboard"]
    html_sel = d.app.jinja_env.from_string(
        '{% from "_selector_productos.html" import grilla_selector %}'
        '{{ grilla_selector("acme", {"producto": [p]}, "radio", "producto_id", {}, []) }}')
    with d.app.test_request_context("/"):
        salida = html_sel.render(p={"id": "p1", "nombre": "Chancla", "nombre_producto": "Chancla", "variante": None,
                                    "referencias": ["a.jpg", "b.jpg", "c.jpg"]})
    assert 'data-n-referencias="3"' in salida


def test_wan_animate_se_anota_con_los_cuadros_reales(base_temporal, monkeypatch, tmp_path):
    import gastos
    import tareas.swap as sw
    payload = _swap_video(sw, monkeypatch, tmp_path, {"duracion_s": 10, "fps": 60})
    payload["proveedor"] = "wan_animate_replace"
    monkeypatch.setattr(sw.comparador_modelos, "editar_video", lambda *a, **k: "https://fal/salida.mp4")
    sw.ejecutar({"id": 9, "job_id": "acme__swap_v__swap", "payload": payload})
    assert gastos.historial("acme")[0]["usd"] == pytest.approx(1.5)      # 600 cuadros / 16 × 0,04


def test_estimar_pasa_los_cuadros_por_segundo():
    import gastos
    assert gastos.estimar("swap", proveedor="wan_animate_replace", formato="video", duracion=4,
                          fps=24)["usd"] == pytest.approx(0.24)


def test_generar_se_activa_solo_con_un_precio_a_la_vista():
    """Con la página de verdad en miniatura: sin archivos el botón queda bloqueado y sin precio visto; con una
    foto y su modelo, se activa y `precio_visto` lleva el precio mostrado."""
    if not shutil.which("node"):
        pytest.skip("sin node")
    programa = r"""
    const fs=require('fs'),assert=require('assert');const g=globalThis;g.window=g;
    function nodo(extra){return Object.assign({dataset:{},textContent:'',value:'',disabled:true,
      addEventListener(t,f){this['on'+t]=f}},extra||{});}
    const input=nodo({files:[]}), visto=nodo(), boton=nodo(), salida=nodo();
    const radioFoto={value:'nano_banana',dataset:{}};
    const form=nodo({querySelector(s){
      if(s.indexOf('type="file"')>=0)return input;
      if(s.indexOf('proveedor_foto')>=0)return radioFoto;
      return null;}});
    const datos={textContent:JSON.stringify({usdEjemplo:'US$ 0,50',urlMedir:'/m',
      precios:{video:{},foto:{nano_banana:{usd:0.117}},fps:30,necesita_fps:[]},
      textos:{aprox:'≈',elegir:'Elige',sinPrecio:'—',midiendo:'…',sinDuracion:'?',detalleVideos:'{segundos}',
              elegirProducto:'P',recorte:'{max}',salidaFija:'{segundos}'}})};
    g.document={getElementById:id=>({'swap-form':form,'swap-precio':salida,'swap-precio-datos':datos,
      'swap-precio-visto':visto,'swap-generar':boton}[id]||null)};
    eval(fs.readFileSync('static/swap-precio.js','utf8'));
    assert.equal(boton.disabled,true,'sin archivos el botón se activó');
    assert.equal(visto.value,'');
    input.files=[{name:'foto.jpg'},{name:'otra.png'}];
    input.onchange();
    setTimeout(()=>{
      assert.equal(boton.disabled,false,'con precio no se activó');
      assert.equal(visto.value,'0.2340');
      assert.ok(salida.textContent.indexOf('0,23')>=0, salida.textContent);
      input.files=[]; input.onchange();
      assert.equal(boton.disabled,true,'al quitar los archivos sigue activo');
    },0);
    """
    r = subprocess.run(["node", "-e", programa], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


# --- segunda revisión de guardian-gasto: medio centavo, Kling O1 y el aviso de recorte ------------

@pytest.mark.slow
@pytest.mark.parametrize("visto, pasa", [("1.76", True), ("1.7551", True), ("1.75", False)])
def test_no_se_cobra_mas_de_medio_centavo_sobre_lo_visto(app, monkeypatch, tmp_path, visto, pasa):  # noqa: F811
    d = app["dashboard"]
    monkeypatch.setattr(d.swaps_mod, "BASE_DIR", str(app["tmp"]))
    monkeypatch.setattr(d.catalogo_productos, "encontrar", lambda cliente, pid: {"id": pid})
    encolados = []
    monkeypatch.setattr(d.trabajos, "encolar", lambda *a, **k: encolados.append(a) or True)
    monkeypatch.setattr(d.libro_cobros, "exigir", lambda cliente, usd, **k: None)
    _ana(app).post("/cliente/acme/swap/generar", data={
        "foto": (io.BytesIO(_video(tmp_path, 3, 25).read_bytes()), "clip.mp4"), "producto_id": "p1",
        "proveedor_video": "seedance25_edit", "precio_visto": visto}, content_type="multipart/form-data")
    assert bool(encolados) is pasa


@pytest.mark.slow
def test_kling_o1_no_deja_subir_un_video_de_mas_de_10_s(app, monkeypatch, tmp_path):  # noqa: F811
    d = app["dashboard"]
    monkeypatch.setattr(d.swaps_mod, "BASE_DIR", str(app["tmp"]))
    monkeypatch.setattr(d.catalogo_productos, "encontrar", lambda cliente, pid: {"id": pid})
    encolados = []
    monkeypatch.setattr(d.trabajos, "encolar", lambda *a, **k: encolados.append(a) or True)
    c = _ana(app)
    c.post("/cliente/acme/swap/generar", data={"foto": (io.BytesIO(_video(tmp_path, 11, 10).read_bytes()), "c.mp4"),
                                               "producto_id": "p1", "proveedor_video": "kling_o1",
                                               "precio_visto": "999"}, content_type="multipart/form-data")
    assert encolados == [] and any("hasta 10 s" in m for m in _flashes(c))


def _dom_video(proveedor, duracion, tarifa):
    """El JS de la pantalla con un video que el servidor (fetch doble) mide en `duracion` s."""
    return r"""
    const fs=require('fs'),assert=require('assert');const g=globalThis;g.window=g;
    function nodo(extra){return Object.assign({dataset:{},textContent:'',value:'',disabled:true,
      addEventListener(t,f){this['on'+t]=f}},extra||{});}
    const input=nodo({files:[]}), visto=nodo(), boton=nodo(), salida=nodo();
    const radioVideo={value:'%(proveedor)s',dataset:{}};
    const form=nodo({querySelector(s){
      if(s.indexOf('type="file"')>=0)return input;
      if(s.indexOf('proveedor_video')>=0)return radioVideo;
      return null;}});
    const datos={textContent:JSON.stringify({usdEjemplo:'US$ 0,50',urlMedir:'/m',
      precios:{video:{'%(proveedor)s':%(tarifa)s},foto:{},fps:30,necesita_fps:[]},
      textos:{aprox:'≈',elegir:'Elige',sinPrecio:'—',midiendo:'…',sinDuracion:'?',detalleVideos:'{segundos}',
              elegirProducto:'P',recorte:'corta en {max}',salidaFija:'{segundos}',muyLargo:'acepta {max}'}})};
    g.FormData=function(){this.append=function(){}};
    g.fetch=()=>Promise.resolve({ok:true,json:()=>Promise.resolve({ok:true,duracion_s:%(duracion)s,fps:30})});
    g.document={getElementById:id=>({'swap-form':form,'swap-precio':salida,'swap-precio-datos':datos,
      'swap-precio-visto':visto,'swap-generar':boton}[id]||null)};
    eval(fs.readFileSync('static/swap-precio.js','utf8'));
    input.files=[{name:'clip.mov'}]; input.onchange();
    setTimeout(()=>{ console.log(JSON.stringify({texto:salida.textContent,visto:visto.value,bloqueado:boton.disabled})); },20);
    """ % {"proveedor": proveedor, "duracion": duracion, "tarifa": json.dumps(tarifa)}


@pytest.mark.parametrize("proveedor, duracion, visto, bloqueado, trozo", [
    ("wan27_edit", 14.7, "2.0000", False, "corta en 10"),      # avisa el recorte; el precio ya va recortado
    ("kling_o1", 14.7, "", True, "acepta 10"),                # Kling O1 lo rechaza: no se deja generar
    ("seedance25_edit", 9.73, "4.2812", False, "9,7"),
])
def test_la_pantalla_usa_la_medida_del_servidor_y_avisa(proveedor, duracion, visto, bloqueado, trozo):
    if not shutil.which("node"):
        pytest.skip("sin node")
    from providers import swap_video_precio
    r = subprocess.run(["node", "-e", _dom_video(proveedor, duracion, swap_video_precio.TARIFAS[proveedor])],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida["visto"] == visto and salida["bloqueado"] is bloqueado and trozo in salida["texto"], salida



# --- auditoría de seguridad (2026-10-13): la cabecera no manda, ffprobe solo lee el disco y la ruta tiene topes ---

def _mentir_duracion(ruta, segundos):
    """Cambia la duración que declaran mvhd, tkhd y mdhd (versión 0) sin tocar los cuadros."""
    datos = bytearray(ruta.read_bytes())
    i = datos.find(b"mvhd")
    escala_peli = int.from_bytes(datos[i + 16:i + 20], "big")
    datos[i + 20:i + 24] = (escala_peli * segundos).to_bytes(4, "big")
    i = datos.find(b"tkhd")
    datos[i + 24:i + 28] = (escala_peli * segundos).to_bytes(4, "big")
    i = datos.find(b"mdhd")
    escala = int.from_bytes(datos[i + 16:i + 20], "big")
    datos[i + 20:i + 24] = (escala * segundos).to_bytes(4, "big")
    ruta.write_bytes(bytes(datos))


@pytest.mark.slow
def test_una_cabecera_que_miente_no_baja_el_precio(tmp_path):
    from providers import swap_video_precio
    video = _video(tmp_path, 12, 30)
    _mentir_duracion(video, 2)
    cabecera = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                               str(video)], capture_output=True, text=True).stdout.strip()
    assert float(cabecera) == pytest.approx(2.0, abs=0.1)           # el archivo dice 2 s…
    duracion, fps = swap_video_precio.medir(str(video))
    assert duracion == pytest.approx(12.0, abs=0.1)                  # …y se cobra por los 12 s que trae
    assert duracion * fps == pytest.approx(360, abs=2)               # los cuadros, contados


def test_ffprobe_solo_lee_archivos_del_disco(monkeypatch):
    from providers import swap_video_precio
    llamadas = []

    class _R:
        stdout = ""
    monkeypatch.setattr(swap_video_precio.subprocess, "run", lambda args, **k: llamadas.append(args) or _R())
    swap_video_precio.medir("/tmp/x.mp4")
    assert llamadas and all(a[a.index("-protocol_whitelist") + 1] == "file" for a in llamadas)


def _post_medir(c, contenido=b"x"):
    return c.post("/cliente/acme/swap/medir", data={"video": (io.BytesIO(contenido), "c.mp4")},
                  content_type="multipart/form-data")


def test_medir_tiene_tope_de_tamano_de_tasa_y_de_turnos(app, monkeypatch):  # noqa: F811
    d = app["dashboard"]
    c = _ana(app)
    monkeypatch.setattr(d, "MAX_BYTES_VIDEO_SWAP", 3)
    assert _post_medir(c, b"cuatro").status_code == 413
    monkeypatch.setattr(d, "MAX_BYTES_VIDEO_SWAP", 200 * 1024 * 1024)
    monkeypatch.setattr(d.cuentas, "limite_ok", lambda *a, **k: False)
    assert _post_medir(c).status_code == 429
    monkeypatch.setattr(d.cuentas, "limite_ok", lambda *a, **k: True)
    turnos = d.threading.BoundedSemaphore(1)
    turnos.acquire()                                   # el único turno está ocupado
    monkeypatch.setattr(d, "_MEDIR_VIDEO_TURNOS", turnos)
    monkeypatch.setattr(d, "ESPERA_TURNO_MEDIR_S", 0)
    assert _post_medir(c).status_code == 503


def test_medir_de_otro_proyecto_da_403_y_no_mide(app, monkeypatch):  # noqa: F811
    d = app["dashboard"]
    monkeypatch.setattr(d, "_medir_video_subido", lambda *a, **k: pytest.fail("midió un video ajeno"))
    r = _ana(app).post("/cliente/otro/swap/medir", data={"video": (io.BytesIO(b"x"), "c.mp4")},
                       content_type="multipart/form-data")
    assert r.status_code == 403


@pytest.mark.parametrize("estado, clave", [(403, "sesion"), (413, "grande"), (503, "ocupado")])
def test_la_pantalla_dice_por_que_no_hay_precio(estado, clave):
    if not shutil.which("node"):
        pytest.skip("sin node")
    from providers import swap_video_precio
    programa = _dom_video("seedance25_edit", 5, swap_video_precio.TARIFAS["seedance25_edit"]).replace(
        "g.fetch=()=>Promise.resolve({ok:true,", "g.fetch=()=>Promise.resolve({ok:false,status:%d,redirected:false," % estado)
    programa = programa.replace("muyLargo:'acepta {max}'", "muyLargo:'acepta {max}',sesion:'S',grande:'G',ocupado:'O'")
    r = subprocess.run(["node", "-e", programa], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida["texto"] == {"sesion": "S", "grande": "G", "ocupado": "O"}[clave] and salida["bloqueado"] is True

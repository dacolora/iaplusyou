"""Rutas de Audios en Crear (spec 2026-09-28 §4): JSON con la lista ya pintada."""
import re

import pytest

import audios
import materiales
from tests.test_rutas_experimentos import _cliente_admin

FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    monkeypatch.setattr(dashboard, "_client_dir", lambda c: str(tmp_path / "clientes" / c))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    vivos = set()
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: job_id in vivos)
    encolados, subidos, borrados = [], [], []

    def _encolar(job_id, tipo, payload, **kw):
        if job_id in vivos:
            return False
        vivos.add(job_id)
        encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw})
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados, "vivos": vivos,
            "subidos": subidos, "borrados": borrados}


def _audio(cliente="acme", n=1):
    return materiales.registrar(cliente, tipo="audio", origen=audios.ORIGEN, url=f"https://r2/clientes/{cliente}/materiales/locucion_{n}.mp3",
                                hash=materiales.hash_clave("locucion", cliente, n), bytes=10, duracion_ms=4100,
                                extra={"nombre": f"Audio {n}", "texto": f"texto {n}", "voz": "Rachel", "idioma": "es",
                                       "velocidad": "normal", "volumen": "media", "musica": None})


def _cancion(cliente="acme"):
    return materiales.registrar(cliente, tipo="audio", origen="subida", url="https://r2/j.mp3",
                                hash=materiales.hash_clave("cancion", cliente), bytes=10, duracion_ms=30000,
                                extra={"nombre": "Jingle", "fuente": "subida"})


def _datos(**k):
    d = {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal", "musica": "", "inicio_s": "0", "volumen": "media"}
    d.update(k)
    return d


def test_la_pagina_trae_el_modo_audios(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-modo="audios"' in html and 'id="crear-modo-audios"' in html
    assert 'id="au-texto"' in html and 'id="au-lista"' in html and "Todavía no tienes audios" in html
    # Galería de voces (2026-09-29): una tarjeta por voz con su ▶, filtros por
    # género y el campo oculto `au-voz` que sigue alimentando el POST.
    assert 'id="au-voces"' in html and html.count('class="au-voz"') == len(audios.voces())
    assert 'data-voz="Rachel"' in html and 'data-genero="mujer"' in html and 'data-genero="hombre"' in html
    assert '<input type="hidden" id="au-voz" value="Rachel">' in html and '<select id="au-voz"' not in html
    assert 'data-filtro-genero="mujer"' in html


def test_lista_devuelve_el_fragmento_y_los_audios(app):
    _audio(n=1)
    d = app["c"].get("/cliente/acme/audios/lista", headers=FETCH).get_json()
    assert d["ok"] and [a["nombre"] for a in d["audios"]] == ["Audio 1"]
    assert 'class="au-item"' in d["html"] and "au-borrar" in d["html"] and "/audios/" in d["html"] and d["trabajo"] is None


def test_crear_encola_una_sola_tarea_sin_reintentos(app):
    c = _cancion()
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(musica=f"mat:{c['id']}", inicio_s="4", volumen="alta"), headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["job_id"] == "acme__audio_generar" and d["trabajo"]["job_id"] == "acme__audio_generar"
    assert 'data-job="acme__audio_generar"' in d["html"] and "data-poll-job" not in d["html"]
    (t,) = app["encolados"]
    assert t["tipo"] == "audio_generar" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal",
                            "musica_id": c["id"], "inicio_s": 4, "volumen": "alta"}
    assert [e[0] for e in t["etapas"]] == ["Sintetizando la voz", "Mezclando con la música", "Guardando"]
    r2 = app["c"].post("/cliente/acme/audios/crear", data=_datos(), headers=FETCH)
    assert r2.status_code == 400 and "espera" in r2.get_json()["error"] and len(app["encolados"]) == 1


def test_crear_invalido_responde_400_sin_encolar(app):
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(texto="   "), headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == "Escribe el texto que quieres que lea la voz."
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(voz="Nadie"), headers=FETCH)
    assert r.status_code == 400 and "voz" in r.get_json()["error"]
    assert app["encolados"] == []


def test_los_post_de_otro_sitio_dan_403(app):
    ajeno = {**FETCH, "Sec-Fetch-Site": "cross-site"}
    assert app["c"].post("/cliente/acme/audios/crear", data=_datos(), headers=ajeno).status_code == 403
    assert app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "es"}, headers=ajeno).status_code == 403
    assert app["c"].post("/cliente/acme/audios/1/borrar", headers=ajeno).status_code == 403
    assert app["encolados"] == []


def test_borrar_quita_el_audio(app):
    a = _audio(n=1)
    d = app["c"].post(f"/cliente/acme/audios/{a['id']}/borrar", headers=FETCH).get_json()
    assert d["ok"] and d["audios"] == [] and app["borrados"] == ["clientes/acme/materiales/locucion_1.mp3"]
    ajeno = _audio(cliente="otro", n=2)
    d = app["c"].post(f"/cliente/acme/audios/{ajeno['id']}/borrar", headers=FETCH).get_json()
    assert d["ok"] and len(app["borrados"]) == 1


def test_muestra_cacheada_no_llama_a_fal(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(audios, "muestra", lambda voz, idioma: llamadas.append((voz, idioma)) or "https://r2/m.mp3")
    d = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "en"}, headers=FETCH).get_json()
    assert d == {"ok": True, "url": "https://r2/m.mp3"} and llamadas == [("Rachel", "en")]
    r = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Nadie", "idioma": "en"}, headers=FETCH)
    assert r.status_code == 400 and len(llamadas) == 1

    def _revienta(voz, idioma):
        raise RuntimeError("fal caído sk-secreto")
    monkeypatch.setattr(audios, "muestra", _revienta)
    r = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "es"}, headers=FETCH)
    assert r.status_code == 502 and "RuntimeError" in r.get_json()["error"] and "secreto" not in r.get_json()["error"]


def test_descargar_entrega_el_mp3_como_adjunto(app, monkeypatch):
    a = _audio(n=1)

    class _Resp:
        status_code = 200
        headers = {"Content-Length": "3"}

        def iter_content(self, n):
            yield b"MP3"
    monkeypatch.setattr(app["dashboard"].requests, "get", lambda url, stream=True, timeout=120: _Resp())
    r = app["c"].get(f"/cliente/acme/audios/{a['id']}/descargar")
    assert r.status_code == 200 and r.data == b"MP3" and r.mimetype == "audio/mpeg"
    assert r.headers["Content-Disposition"] == 'attachment; filename="Audio 1.mp3"'
    assert app["c"].get("/cliente/acme/audios/999/descargar").status_code == 404


def _voz_propia(cliente="acme", voice_id="mmx_1", nombre="Ana"):
    return materiales.registrar(cliente, tipo="audio", origen="voz_propia",
                                url=f"https://r2/clientes/{cliente}/materiales/voz_propia_{voice_id}.mp3",
                                hash=materiales.hash_clave("voz_propia", "minimax", voice_id), bytes=1, duracion_ms=3000,
                                extra={"nombre": nombre, "forma": "disenada", "proveedor": "minimax", "voice_id": voice_id,
                                       "idioma_muestra": "es", "estrenada": True})


def test_mis_voces_devuelve_el_fragmento(app):
    v = _voz_propia()
    d = app["c"].get("/cliente/acme/audios/voces", headers=FETCH).get_json()
    assert d["ok"] and [x["nombre"] for x in d["voces"]] == ["Ana"] and d["trabajo"] is None
    assert f'data-voz="vp:{v["id"]}"' in d["html"] and "au-vp-borrar" in d["html"] and 'id="au-vp-crear"' in d["html"]


def test_disenar_encola_una_sola_creacion_sin_reintentos(app):
    r = app["c"].post("/cliente/acme/audios/voces/disenar",
                      data={"nombre": "Ana", "descripcion": "Mujer cálida de 30", "idioma": "sv"}, headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["job_id"] == "acme__voz_propia"
    assert 'data-job="acme__voz_propia"' in d["html"] and "data-poll-job" not in d["html"]
    (t,) = app["encolados"]
    assert t["tipo"] == "voz_propia_crear" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "forma": "disenar", "nombre": "Ana",
                            "descripcion": "Mujer cálida de 30", "idioma": "sv"}
    r2 = app["c"].post("/cliente/acme/audios/voces/disenar",
                       data={"nombre": "Eva", "descripcion": "Hombre de voz grave", "idioma": "es"}, headers=FETCH)
    assert r2.status_code == 400 and "espera" in r2.get_json()["error"] and len(app["encolados"]) == 1
    r3 = app["c"].post("/cliente/acme/audios/voces/disenar", data={"nombre": "", "descripcion": "x", "idioma": "es"}, headers=FETCH)
    assert r3.status_code == 400


def test_clonar_exige_permiso_y_guarda_la_grabacion(app, monkeypatch):
    import io

    import voces_propias
    monkeypatch.setattr(voces_propias, "_duracion_ms", lambda path: 15000)
    sin_permiso = {"nombre": "Daniel", "idioma": "cs", "grabacion": (io.BytesIO(b"audio falso"), "voz.wav")}
    r = app["c"].post("/cliente/acme/audios/voces/clonar", data=sin_permiso, content_type="multipart/form-data", headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == voces_propias.MENSAJES["permiso"]
    assert app["subidos"] == [] and app["encolados"] == []
    sin_archivo = {"nombre": "Daniel", "idioma": "cs", "consentimiento": "si"}
    r = app["c"].post("/cliente/acme/audios/voces/clonar", data=sin_archivo, content_type="multipart/form-data", headers=FETCH)
    assert r.status_code == 400 and app["encolados"] == []
    bien = {"nombre": "Daniel", "idioma": "cs", "consentimiento": "si", "grabacion": (io.BytesIO(b"audio falso"), "voz.wav")}
    r = app["c"].post("/cliente/acme/audios/voces/clonar", data=bien, content_type="multipart/form-data", headers=FETCH)
    assert r.status_code == 200 and r.get_json()["job_id"] == "acme__voz_propia"
    (t,) = app["encolados"]
    p = t["payload"]
    assert (p["forma"], p["nombre"], p["idioma"]) == ("clonar", "Daniel", "cs") and p["consentimiento"]["usuario"] == "admin"
    assert materiales.obtener("acme", p["grabacion_id"])["origen"] == "grabacion"
    assert app["subidos"][0].startswith("clientes/acme/materiales/grabacion_")


def _clonar_con_cola_ocupada(app, monkeypatch):
    """Otra creación se encoló entre el chequeo de la ruta y su encolar (la
    carrera): `trabajos.encolar` se niega después de subir la grabación."""
    import io

    import voces_propias
    monkeypatch.setattr(voces_propias, "_duracion_ms", lambda path: 15000)
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar", lambda *a, **k: False)
    datos = {"nombre": "Daniel", "idioma": "cs", "consentimiento": "si", "grabacion": (io.BytesIO(b"audio falso"), "voz.wav")}
    r = app["c"].post("/cliente/acme/audios/voces/clonar", data=datos, content_type="multipart/form-data", headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == voces_propias.MENSAJES["en_curso"]


def _hash_grabacion(datos):
    import hashlib
    return materiales.hash_clave("grabacion", hashlib.sha256(datos).hexdigest())


def test_clonar_sin_poder_encolar_borra_la_grabacion(app, monkeypatch):
    """Revisión final F2: la grabación recién subida no se queda en R2 sin voz."""
    _clonar_con_cola_ocupada(app, monkeypatch)
    (key,) = app["subidos"]
    assert key.startswith("clientes/acme/materiales/grabacion_") and app["borrados"] == [key]
    assert materiales.buscar_hash("acme", _hash_grabacion(b"audio falso")) is None


def test_clonar_sin_poder_encolar_no_borra_la_grabacion_de_la_creacion_viva(app, monkeypatch):
    """La creación que ganó la carrera clona el mismo archivo (una sola fila
    por hash): esa grabación sigue ahí para ella."""
    import cola
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_v.wav",
                             hash=_hash_grabacion(b"audio falso"), bytes=11, duracion_ms=15000, extra={"nombre": "voz"})
    cola.encolar("voz_propia_crear", {"cliente": "acme", "forma": "clonar", "grabacion_id": g["id"]},
                 cliente="acme", job_id="acme__voz_propia", max_intentos=1)
    _clonar_con_cola_ocupada(app, monkeypatch)
    assert materiales.obtener("acme", g["id"]) is not None
    assert app["subidos"] == [] and app["borrados"] == []


def test_borrar_voz_propia(app):
    v = _voz_propia()
    d = app["c"].post(f"/cliente/acme/audios/voces/{v['id']}/borrar", headers=FETCH).get_json()
    assert d["ok"] and d["voces"] == [] and app["borrados"] == ["clientes/acme/materiales/voz_propia_mmx_1.mp3"]


def test_muestra_de_voz_propia(app, monkeypatch):
    import voces_propias
    v = _voz_propia()
    llamadas = []
    monkeypatch.setattr(voces_propias, "muestra", lambda cliente, voz, idioma:
                        llamadas.append((cliente, voz, idioma)) or "https://r2/mp.mp3")
    d = app["c"].post("/cliente/acme/audios/muestra", data={"voz": f"vp:{v['id']}", "idioma": "fi"}, headers=FETCH).get_json()
    assert d == {"ok": True, "url": "https://r2/mp.mp3"} and llamadas == [("acme", f"vp:{v['id']}", "fi")]
    ajena = _voz_propia(cliente="otro", voice_id="mmx_2")
    r = app["c"].post("/cliente/acme/audios/muestra", data={"voz": f"vp:{ajena['id']}", "idioma": "fi"}, headers=FETCH)
    assert r.status_code == 400 and len(llamadas) == 1


def test_crear_audio_con_voz_propia(app):
    v = _voz_propia()
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(voz=f"vp:{v['id']}", idioma="no"), headers=FETCH)
    assert r.status_code == 200 and app["encolados"][0]["payload"]["voz"] == f"vp:{v['id']}"


def test_los_post_de_mis_voces_de_otro_sitio_dan_403(app):
    ajeno = {**FETCH, "Sec-Fetch-Site": "cross-site"}
    for url in ("/cliente/acme/audios/voces/disenar", "/cliente/acme/audios/voces/clonar", "/cliente/acme/audios/voces/1/borrar"):
        assert app["c"].post(url, data={}, headers=ajeno).status_code == 403
    assert app["encolados"] == []


def test_el_gasto_de_voces_propias_tiene_nombre(app):
    assert app["dashboard"].NOMBRES_TIPO_GASTO["voz_propia"] == "Voces propias"


def test_la_pagina_trae_mis_voces_el_panel_y_diez_idiomas(app):
    v = _voz_propia()
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'id="au-vp-wrap"' in html and f'data-voz="vp:{v["id"]}"' in html and 'id="au-vp-panel"' in html
    assert 'data-vp-pestana="clonar"' in html and 'data-vp-pestana="disenar"' in html
    assert 'id="au-vp-permiso"' in html and "tengo permiso escrito de la persona" in html
    assert 'id="au-vp-descripcion"' in html and "US$ 1,52" in html and "US$ 3,01" in html
    assert "data-url-vp-clonar=" in html and "data-url-vp-lista=" in html
    sel = html.split('id="au-idioma"')[1].split("</select>")[0]
    assert sel.count("<option") == 11 and "Nederlands" in sel and "Norsk" in sel and "Čeština" in sel and "Suomi" in sel
    assert "Idioma del texto" in html
    # Pestañas del panel accesibles (revisión Task 6): cada una dice si está
    # elegida y qué formulario controla; los formularios son sus tabpanel.
    clonar = re.search(r'<button[^>]*data-vp-pestana="clonar"[^>]*>', html).group(0)
    disenar = re.search(r'<button[^>]*data-vp-pestana="disenar"[^>]*>', html).group(0)
    assert 'aria-selected="true"' in clonar and 'aria-controls="au-vp-form-clonar"' in clonar
    assert 'aria-selected="false"' in disenar and 'aria-controls="au-vp-form-disenar"' in disenar
    for forma in ("clonar", "disenar"):
        panel = re.search(rf'<div[^>]*data-vp-form="{forma}"[^>]*>', html).group(0)
        assert 'role="tabpanel"' in panel and f'id="au-vp-form-{forma}"' in panel
    # No hay arnés de JS: como en test_base_visual/test_movil, se mira el
    # script de la página. Un clon que salió desmarca la casilla de permiso
    # (cada clon pide su propio permiso) y elegir otro archivo también la
    # desmarca: el permiso es por archivo (revisión final F4).
    assert "document.getElementById('au-vp-permiso').checked = false" in html
    assert re.search(r"getElementById\('au-vp-archivo'\)\.addEventListener\('change', function \(\) \{\s*"
                     r"document\.getElementById\('au-vp-permiso'\)\.checked = false;", html)
    # Un sondeo se calla solo si el re-pintado trajo su propia barra del mismo
    # trabajo (uno solo por trabajo); si la barra se fue sin reemplazo sigue y
    # muestra el aviso o el error del final (revisión final F7).
    assert "if (!barra.isConnected) { clearInterval(t); return; }" not in html
    assert ("if (!barra.isConnected && vpWrap.querySelector('.barra-progreso[data-job=\"' + barra.dataset.job"
            " + '\"]')) { clearInterval(t); return; }") in html
    assert ("if (!barra.isConnected && document.querySelector('#au-lista .barra-progreso[data-job=\"' + barra.dataset.job"
            " + '\"]')) { clearInterval(t); return; }") in html
    css = open("static/style.css", encoding="utf-8").read()
    assert ".au-voz-propia .au-voz-nombre" in css


def test_tabla_clon_coincide_con_estimador_y_se_calcula_una_vez(app, monkeypatch):
    import gastos
    import voces_propias
    d = app['dashboard']
    limpiar = getattr(getattr(d, '_precios_clon', None), 'cache_clear', lambda: None)
    limpiar()
    original = gastos.estimar
    calculos = []
    def contar(tipo, **kw):
        if tipo == 'voz_clonada' and 'nombre' in kw: calculos.append(kw)
        return original(tipo, **kw)
    monkeypatch.setattr(gastos, 'estimar', contar)
    try:
        contexto = d._contexto_mis_voces('acme')
        cantidad = len(calculos)
        for nombre, idioma in [('Ana', 'es'), ('Dániel Pérez', 'en'), ('李雷', 'de')]:
            assert contexto['precios_clon'][idioma][len(nombre)] == original('voz_clonada', nombre=nombre, idioma=idioma)['usd']
        html = app['c'].get('/cliente/acme').get_data(as_text=True)
        d._contexto_mis_voces('acme')
        assert cantidad == len(audios.IDIOMAS) * (voces_propias.MAX_NOMBRE + 1)
        assert len(calculos) == cantidad
        assert re.search(r"getElementById\('au-vp-nombre-c'\)\.addEventListener\('input', refrescarPrecioClon\)", html)
        assert re.search(r"getElementById\('au-idioma'\)\.addEventListener\('change', refrescarPrecioClon\)", html)
    finally:
        limpiar()


def test_clonar_refresca_precio_al_vaciar_nombre(app):
    import json
    import subprocess
    html = app['c'].get('/cliente/acme').get_data(as_text=True)
    funcion = re.search(r'function refrescarPrecioClon\(\) \{.*?\n  \}', html, re.S).group()
    accion = html.split('enviarVoz(raiz.dataset.urlVpClonar, fd).then(function (ok) {', 1)[1].split('    });', 1)[0]
    tabla = app['dashboard']._contexto_mis_voces('acme')['precios_clon']
    codigo = 'var preciosClon=' + json.dumps(tabla) + ''';
    const elementos={'au-vp-nombre-c':{value:'x'.repeat(40)},'au-idioma':{value:'es'},
      'au-vp-clonar-precio':{textContent:''},'au-vp-permiso':{checked:true}};
    const document={getElementById:id=>elementos[id]}, T={aprox:'≈'};
    const fmtUsd=v=>'US$ '+v.toFixed(2), archivo={value:'a.mp3'}, botonClonar={disabled:true};
    ''' + funcion + '''
    refrescarPrecioClon(); const antes=elementos['au-vp-clonar-precio'].textContent;
    function terminar(ok){''' + accion + '''}
    terminar(true);
    console.log(JSON.stringify({antes,despues:elementos['au-vp-clonar-precio'].textContent,nombre:elementos['au-vp-nombre-c'].value}));
    '''
    r = subprocess.run(['node', '-e', codigo], text=True, capture_output=True, check=True)
    resultado = json.loads(r.stdout)
    assert resultado['nombre'] == ''
    assert resultado['despues'] != resultado['antes']
    assert resultado['despues'] == f"≈ US$ {tabla['es'][0]:.2f}"


def test_diseno_refresca_precio_por_nombre_e_idioma_en_node(app):
    import json
    import subprocess
    html = app['c'].get('/cliente/acme').get_data(as_text=True)
    assert 'id="au-vp-disenar-precio"' in html
    tabla = app['dashboard']._contexto_mis_voces('acme')['precios_disenar']
    funcion = html[html.index('function refrescarPrecioDisenar('):html.index('function refrescarPrecioClon(')]
    codigo = 'var preciosDisenar=' + json.dumps(tabla) + ''';
    var nombre={value:'Ana',addEventListener(e,f){this[e]=f;}}, idioma={value:'en',addEventListener(e,f){this[e]=f;}}, precio={textContent:''};
    var document={getElementById:id=>({'au-vp-nombre-d':nombre,'au-idioma':idioma,'au-vp-disenar-precio':precio}[id])};
    var T={aprox:'≈'}, sep='.', fmtUsd=v=>'US$ '+v.toFixed(2);
    ''' + funcion + '''
    refrescarPrecioDisenar();
    if (precio.textContent !== '≈ ' + fmtUsd(preciosDisenar.en[3])) throw Error(precio.textContent);
    nombre.value='x'.repeat(40); nombre.input();
    if (precio.textContent !== '≈ ' + fmtUsd(preciosDisenar.en[40])) throw Error(precio.textContent);
    idioma.value='sv'; idioma.change();
    if (precio.textContent !== '≈ ' + fmtUsd(preciosDisenar.sv[40])) throw Error(precio.textContent);
    '''
    subprocess.run(['node', '-e', codigo], check=True, capture_output=True, text=True)


def test_tabla_diseno_por_nombre_e_idioma_contra_cobro(app, monkeypatch):
    from providers import fal_audio
    import voces_propias
    d = app['dashboard']
    monkeypatch.setattr(fal_audio.fal_client, 'llamar', lambda *a, **kw: {
        'custom_voice_id': 'voz', 'audio': {'url': 'https://r2/a.mp3'}})
    d._precios_disenar.cache_clear()
    try:
        tabla = d._precios_disenar()
        precios = []
        for idioma, n in [('es', 3), ('es', 40), ('sv', 40), ('en', 3)]:
            frase = voces_propias.frase_muestra('x' * n, idioma)
            pagado = round(fal_audio.disenar_voz_minimax('Descripción', frase)['costo_usd']
                           + fal_audio.tts_minimax(frase, 'voz', idioma)['costo_usd'], 4)
            assert tabla[idioma][n] == pagado
            precios.append(pagado)
        assert precios[0] != precios[1]  # largo
        assert precios[1] != precios[2]  # idioma
    finally:
        d._precios_disenar.cache_clear()


def test_pnd095_botones_de_muestra_y_borrar_fuera_del_radio(app):
    from flask import render_template_string
    from html.parser import HTMLParser
    with app["dashboard"].app.test_request_context():
        html = render_template_string("{% from '_voces_galeria.html' import fichas_galeria, voz_propia_item %}{{ fichas_galeria(fichas) }}{{ voz_propia_item(v,'/borrar') }}",\
            fichas=[{"nombre": "Rachel", "genero": "mujer", "genero_nombre": "Mujer"}],\
            v={"valor": "vp:7", "nombre": "Mi voz", "forma_nombre": "Clonada", "estrenada": True})
    class Lector(HTMLParser):
        def __init__(self):
            super().__init__(); self.pila = []; self.radios = 0; self.botones = 0
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "button":
                assert "radio" not in self.pila, "botón dentro de role=radio"
                self.botones += 1
            if a.get("role") == "radio":
                assert a.get("tabindex") == "0" and "data-voz" in a
                self.radios += 1
            self.pila.append(a.get("role"))
        def handle_endtag(self, tag):
            self.pila.pop()
    lector = Lector(); lector.feed(html)
    assert lector.radios == 2 and lector.botones == 3

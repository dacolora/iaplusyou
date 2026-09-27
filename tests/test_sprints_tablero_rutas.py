"""Rutas del tablero de Sprints (spec 2026-09-26). Fixture `app` de
test_rutas_sprints: sesión admin, catálogo falso con espejo_led y
division_bano, encolar monkeypatcheado."""
import json

import pytest

from tests.test_rutas_sprints import app  # noqa: F401


def _sprint(datos, **kw):
    return datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", **kw)


# ------------------------------------------------------ «+ Nuevo sprint» ---

def test_contexto_de_la_pestana(app):
    from datetime import date
    from sprints import datos, rutas, tablero
    ctx = rutas.contexto("acme")
    assert ctx["pais_calendario"] == "CO" and any(p["clave"] == "navidad" for p in ctx["presets_temporadas"])
    assert "CO" in [p["codigo"] for p in ctx["paises_sprint"]] and ctx["idiomas_sprint"]["en"] == "inglés"
    assert (ctx["inicio_defecto"], ctx["fin_defecto"]) == tablero.mes_siguiente(date.today())
    assert datos.personas("acme") == []                     # ya no se crean personas genéricas


def test_pestana_muestra_el_formulario_corto(app):
    html = app["c"].get("/cliente/acme").data.decode()
    tab = html[html.index('id="tab-sprints"'):]
    for frag in ('name="nombre"', 'name="inicio"', 'name="pais"', 'name="idioma"', 'name="momento"',
                 'name="marcas"', "Crear y armar campañas"):
        assert frag in tab, frag
    for viejo in ("campanas_json", "modal-agregar-campana", "sprint-paso", "Siguiente: la matriz"):
        assert viejo not in html, viejo


def test_crear_sprint_corto_abre_su_tablero(app):
    from sprints import calendario, datos
    clave = calendario.presets("MX", 2026)[0]["clave"]
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={
        "nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31", "pais": "MX", "idioma": "es",
        "momento": clave, "marcas": "Crocs\nSkechers 1234567"})
    s = datos.sprints("acme")[0]
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{s['id']}")
    assert s["pais"] == "MX" and s["campanas_total"] == 0 and s["momento"]["clave"] == clave
    assert s["marcas"] == [{"nombre": "Crocs"}, {"nombre": "Skechers", "pagina_id": "1234567"}]


def test_crear_sprint_con_momento_propio(app):
    from sprints import datos
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31",
                                                        "momento": "propio", "momento_texto": "Lanzamiento"})
    s = datos.sprints("acme")[0]
    assert s["momento"] == {"nombre": "Lanzamiento"} and s["pais"] == "CO" and s["idioma"] == "es"


@pytest.mark.parametrize("malo", [{"pais": "Colombia"}, {"momento": "no_existe"}, {"fin": "2026-09-01"}])
def test_crear_sprint_invalido_no_crea_nada(app, malo):
    from sprints import datos
    datos_form = {"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31", **malo}
    r = app["c"].post("/cliente/acme/sprints/nuevo", data=datos_form)
    assert r.status_code == 302 and r.headers["Location"].endswith("#sprints")
    assert datos.sprints("acme", incluir_archivados=True) == []


def test_momento_del_mes_sigue_al_pais_elegido(app):
    """El «Momento del mes» no puede quedarse anclado al país por defecto: si
    la persona cambia a MX y elige uno de sus presets, crear no debe fallar
    con «Ese momento del calendario no existe» (fix round 1)."""
    from final_edition import tipos as fe_tipos
    from sprints import datos, rutas
    ctx = rutas.contexto("acme")
    assert set(ctx["presets_por_pais"].keys()) == set(fe_tipos.PAISES.keys())
    html = app["c"].get("/cliente/acme").data.decode()
    tab = html[html.index('id="tab-sprints"'):]
    assert 'data-pais="MX"' in tab and 'value="buen_fin"' in tab
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={
        "nombre": "Noviembre", "inicio": "2026-11-01", "fin": "2026-11-30", "pais": "MX", "momento": "buen_fin"})
    s = datos.sprints("acme")[0]
    assert r.status_code == 302 and s["momento"]["clave"] == "buen_fin"


# ------------------------------------------------------------- tablero ---

def _campana(datos, sid, **kw):
    pid = kw.pop("persona_id", None) or datos.crear_persona("acme", "Premium", resumen="Busca calidad")
    return datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1, **kw)


def test_tablero_muestra_tarjetas_resumen_y_siguiente_paso(app):
    from sprints import datos
    sid = _sprint(datos, pais="CO", marcas="Crocs", momento="Hot Sale")
    cid = _campana(datos, sid, consciencia="consciente_del_problema", dolor="pies fríos")
    html = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    for frag in (f'id="campana-{cid}"', "Campaña 1", "Premium", "Espejo LED", "consciente del problema",
                 "«pies fríos»", "Siguiente: elegir 5 referentes", "1 campaña · 3 piezas planeadas · 0/5 referentes elegidos",
                 "1–31 oct · 🇨🇴 español · Hot Sale · imita: Crocs", 'id="tablero-panel"', 'id="tablero-nueva"'):
        assert frag in html, frag
    assert "-ajax" not in html and 'name="temporada_id"' not in html
    assert 'id="sprint-lote-resumen"' not in html    # F4: nada en cola/generando/listo -- no hay resumen que mostrar


def test_tablero_de_un_sprint_viejo_abre(app):
    from sprints import datos
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = _sprint(datos)
    datos.agregar_campana("acme", sid, datos.crear_persona("acme", "Premium"), "espejo_led", tid, 2, 1)
    r = app["c"].get(f"/cliente/acme/sprints/{sid}")
    assert r.status_code == 200 and ">None<" not in r.data.decode()


def test_tablero_sin_campanas_invita_a_crear_una(app):
    from sprints import datos
    html = app["c"].get(f"/cliente/acme/sprints/{_sprint(datos)}").data.decode()
    assert "Este sprint todavía no tiene campañas" in html and "data-nueva-campana" in html


def test_tablero_abre_el_panel_pedido(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}?panel={cid}").data.decode()
    assert f'data-panel-inicial="{cid}"' in html


def _json(c, url, cuerpo):
    return c.post(url, data=json.dumps(cuerpo), content_type="application/json",
                  headers={"X-Requested-With": "fetch"})


def test_campo_del_sprint_guarda_y_valida(app):
    from sprints import datos
    sid = _sprint(datos)
    url = f"/cliente/acme/sprints/{sid}/campo"
    j = _json(app["c"], url, {"campo": "pais", "valor": "MX"}).get_json()
    assert j["ok"] and "🇲🇽" in j["linea"] and datos.sprint("acme", sid)["pais"] == "MX"
    assert _json(app["c"], url, {"campo": "momento", "valor": "propio:Hot Sale"}).get_json()["ok"]
    assert datos.sprint("acme", sid)["momento"] == {"nombre": "Hot Sale"}
    assert _json(app["c"], url, {"campo": "momento", "valor": "navidad"}).get_json()["ok"]
    assert datos.sprint("acme", sid)["momento"]["clave"] == "navidad"
    assert _json(app["c"], url, {"campo": "marcas", "valor": "Crocs"}).get_json()["ok"]
    for malo in ({"campo": "idioma", "valor": "xx"}, {"campo": "nombre", "valor": ""}, {"campo": "estado", "valor": "x"},
                 {"campo": "pais", "valor": {"x": 1}}, {"campo": "fin", "valor": "2026-09-01"}):
        r = _json(app["c"], url, malo)
        assert r.status_code == 400 and r.get_json()["error"], malo
    assert _json(app["c"], "/cliente/acme/sprints/999/campo", {"campo": "pais", "valor": "CO"}).status_code == 404


def test_agregar_campana_json_crea_con_valores_por_defecto_y_avisa_repetida(app):
    from sprints import datos
    sid = _sprint(datos)
    pid = datos.crear_persona("acme", "Premium")
    url = f"/cliente/acme/sprints/{sid}/campanas"
    j = _json(app["c"], url, {"persona_id": pid, "catalogo_id": "espejo_led"}).get_json()
    c = datos.campana("acme", j["cid"])
    assert j["ok"] and j["aviso"] is None and j["url"].endswith(f"/sprints/{sid}?panel={j['cid']}")
    assert (c["n_videos"], c["n_imagenes"], c["funnel"]) == (5, 5, "tof")
    j2 = _json(app["c"], url, {"persona_id": pid, "catalogo_id": "espejo_led"}).get_json()
    assert j2["ok"] and "campaña 1" in j2["aviso"]


@pytest.mark.parametrize("cuerpo,error", [({"catalogo_id": "espejo_led"}, "Elige una persona"),
                                          ({"persona_id": "PID", "catalogo_id": "no_existe"}, "Elige un producto")])
def test_agregar_campana_json_valida(app, cuerpo, error):
    from sprints import datos
    sid = _sprint(datos)
    pid = datos.crear_persona("acme", "Premium")
    cuerpo = {k: (pid if v == "PID" else v) for k, v in cuerpo.items()}
    r = _json(app["c"], f"/cliente/acme/sprints/{sid}/campanas", cuerpo)
    assert r.status_code == 400 and error in r.get_json()["error"] and datos.campanas("acme", sid) == []


def test_persona_rapida_responde_json(app):
    from sprints import datos
    r = app["c"].post("/cliente/acme/sprints/personas", data={"nombre": "Mamá práctica", "resumen": "Quiere ahorrar tiempo"},
                      headers={"X-Requested-With": "fetch"})
    j = r.get_json()
    p = datos.persona("acme", j["id"])
    assert j["ok"] and j["nombre"] == "Mamá práctica" and p["origen"] == "manual" and p["resumen"] == "Quiere ahorrar tiempo"
    r = app["c"].post("/cliente/acme/sprints/personas", data={"nombre": ""}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400 and not r.get_json()["ok"]


def test_tarjeta_de_una_campana(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/tarjeta").data.decode()
    assert html.lstrip().startswith("<article") and f'id="campana-{cid}"' in html
    otro = _sprint(datos)
    assert app["c"].get(f"/cliente/acme/sprints/{otro}/campanas/{cid}/tarjeta").status_code == 404


# --------------------------------------------------------------- panel ---

def _referente(n, familia, etapa="TOF", consciencia="problem-aware", marca="", idioma="en"):
    from referentes import datos as rdatos
    rdatos.familia_asegurar(familia, "")
    rid, _ = rdatos.guardar_referente({"anuncio_id": f"p{n}", "fuente": "atria", "imagen_origen": "https://o/x.jpg",
                                       "marca": marca, "idioma": idioma})
    rdatos.marcar_imagen(rid, "ok", f"https://r2/ref{n}.jpg")
    rdatos.actualizar_referente(rid, etapa=etapa, consciencia=consciencia, familia=familia, clasificacion="claude")
    return rid


def test_panel_muestra_las_siete_secciones(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    r = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel")
    html = r.data.decode()
    assert r.status_code == 200
    for frag in ("Audiencia y producto", "Enfoque", "Formato de los anuncios", "Mercado y marcas", "Piezas",
                 "Referentes · 0 de 5 elegidos", 'data-campo="persona_id"', 'data-campo="catalogo_id"',
                 'data-campo="funnel"', 'data-campo="consciencia"', 'data-campo="dolor"', 'data-campo="familias"',
                 'data-campo="pais"', 'data-campo="idioma"', 'data-campo="marcas"', 'data-campo="n_videos"',
                 'data-campo="n_imagenes"', 'data-campo="referencias_objetivo"', "Sugerir con IA",
                 "Buscar en la biblioteca", "Traer nuevos de Meta", 'name="volver" value="tablero"',
                 "Eliminar campaña", f"/sprints/{sid}/campanas/{cid}/ideas", "Crear persona rápida", "data-sugeridos"):
        assert frag in html, frag
    assert "<script" not in html                      # el JS vive en sprint_detalle.html


def test_panel_de_otra_campana_o_sprint_da_404(app):
    from sprints import datos
    sid, otro = _sprint(datos), _sprint(datos)
    cid = _campana(datos, sid)
    assert app["c"].get(f"/cliente/acme/sprints/{otro}/campanas/{cid}/panel").status_code == 404
    assert app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/999/panel").status_code == 404


def test_panel_trae_lo_de_nicho_y_lo_heredado(app):
    from sprints import datos
    pid = datos.crear_persona("acme", "Melissa", resumen="Comodidad al llegar", origen="investigada",
                              extra={"conciencia": {"nivel": "consciente del problema"},
                                     "encaje_producto": "Abriga sin sudar"})
    sid = _sprint(datos, pais="MX", marcas="Crocs")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel").data.decode()
    assert 'value="consciente_del_problema" checked' in html
    assert 'data-valor="Abriga sin sudar"' in html and "Melissa · del Nicho" in html
    assert "Del sprint (🇲🇽 México)" in html and "Del sprint: Crocs" in html
    assert "#referentes?" in html and "etapa=TOF" in html and "consciencia=problem-aware" in html
    assert "pais=MX" in html and "palabra=Espejo+LED" in html


def test_panel_muestra_referencias_viejas_sin_frame(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    datos.agregar_referencia("acme", cid, "imagen", "https://r2/vieja.png", frame_url=None, titulo="vieja.png")
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel").data.decode()
    assert 'src="https://r2/vieja.png"' in html and "falta describir" in html


def test_guardar_un_campo_de_la_campana(app):
    from referentes import datos as rdatos
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    rdatos.familia_asegurar("UGC", "")
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/campo"
    j = _json(app["c"], url, {"campo": "dolor", "valor": "pies fríos"}).get_json()
    assert j["ok"] and "«pies fríos»" in j["tarjeta"] and j["recargar_panel"] is False
    j = _json(app["c"], url, {"campo": "familias", "valor": ["UGC"]}).get_json()
    assert j["ok"] and j["recargar_panel"] is True and datos.campana("acme", cid)["familias"] == ["UGC"]
    j = _json(app["c"], url, {"campo": "n_videos", "valor": "7"}).get_json()
    assert j["ok"] and "7 videos" in j["tarjeta"] and "8 piezas planeadas" in j["resumen"]
    for malo in ({"campo": "consciencia", "valor": "x"}, {"campo": "familias", "valor": ["No existe"]},
                 {"campo": "n_videos", "valor": -1}, {"campo": "catalogo_id", "valor": "no_existe"},
                 {"campo": "estado", "valor": "x"}, {"campo": "dolor", "valor": {"a": 1}},
                 {"campo": "funnel", "valor": True}):
        r = _json(app["c"], url, malo)
        assert r.status_code == 400 and r.get_json()["error"], malo
    assert datos.campana("acme", cid)["n_videos"] == 7


def test_guardar_un_campo_rechaza_el_tipo_equivocado(app):
    """F5 (ronda final): antes, `_valor_simple` aceptaba una lista para
    CUALQUIER campo -- `catalogo_id` con `[]` tiraba un TypeError sin atrapar
    (unhashable type: 'list' al comparar contra el set de ids, 500), y
    `dolor`/`nombre` con una lista se guardaban stringificados
    ("['a', 'b']", `sprints.datos._texto`). Ahora solo familias/marcas
    aceptan lista; el resto de texto, numéricos+persona_id texto o número."""
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/campo"
    for malo in ({"campo": "catalogo_id", "valor": []}, {"campo": "dolor", "valor": ["a", "b"]},
                 {"campo": "persona_id", "valor": [1]}, {"campo": "funnel", "valor": []},
                 {"campo": "consciencia", "valor": []}, {"campo": "n_videos", "valor": []}):
        r = _json(app["c"], url, malo)
        assert r.status_code == 400 and r.get_json()["error"], malo
    original = datos.campana("acme", cid)
    assert original["catalogo_id"] == "espejo_led" and original["dolor"] == ""
    # las listas siguen andando donde sí las manda el panel: familias y marcas.
    from referentes import datos as rdatos
    rdatos.familia_asegurar("UGC", "")
    assert _json(app["c"], url, {"campo": "familias", "valor": ["UGC"]}).get_json()["ok"]
    assert _json(app["c"], url, {"campo": "marcas", "valor": ["Crocs"]}).get_json()["ok"]
    assert datos.campana("acme", cid)["marcas"] == [{"nombre": "Crocs"}]


def test_guardar_campo_del_sprint_rechaza_el_tipo_equivocado(app):
    """Mismo tipo de bug a nivel de sprint: `nombre`/`momento` con una lista."""
    from sprints import datos
    sid = _sprint(datos)
    url = f"/cliente/acme/sprints/{sid}/campo"
    original = datos.sprint("acme", sid)
    for malo in ({"campo": "nombre", "valor": ["a", "b"]}, {"campo": "momento", "valor": ["a", "b"]},
                 {"campo": "pais", "valor": []}):
        r = _json(app["c"], url, malo)
        assert r.status_code == 400 and r.get_json()["error"], malo
    assert datos.sprint("acme", sid)["nombre"] == original["nombre"]
    assert datos.sprint("acme", sid)["momento"] == original["momento"]
    assert _json(app["c"], url, {"campo": "marcas", "valor": ["Crocs"]}).get_json()["ok"]


def test_guardar_repetida_devuelve_el_aviso(app):
    from sprints import datos
    sid = _sprint(datos)
    pid = datos.crear_persona("acme", "Premium")
    datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0, funnel="mof")
    j = _json(app["c"], f"/cliente/acme/sprints/{sid}/campanas/{cid}/campo", {"campo": "funnel", "valor": "tof"}).get_json()
    assert j["ok"] and "campaña 1" in j["aviso"]


def test_autoguardado_limpia_data_sucio(app):
    """F2 (ronda final): sin borrar `data-sucio` del campo que ya se guardó,
    `haySinGuardar()` (base.html) seguía viéndolo sucio y `recargarOAvisar`
    mostraba «cambios sin guardar» en falso cuando, por ejemplo, terminaba
    «Sugerir con IA» -- guardarSprint y guardar (panel) deben limpiarlo tanto
    al guardar como al restaurar el valor por error; la búsqueda de familia,
    al vaciarse; persona-rápida/nueva-campaña, al terminar (`f.reset()` no
    toca los `data-*`)."""
    from sprints import datos
    sid = _sprint(datos)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    cabecera = html[html.index("function guardarSprint"):html.index("campos.addEventListener")]
    assert cabecera.count("delete el.dataset.sucio;") == 2
    panel_js = html[html.index("function guardar(el, valor)"):html.index("function cajaFamilias")]
    assert panel_js.count("delete el.dataset.sucio;") == 2
    assert "delete t.dataset.sucio;" in html
    assert "function limpiarSucio(" in html and html.count("limpiarSucio(f)") == 2


def test_json_del_tablero_avisa_amigable_si_el_servidor_no_responde_json(app):
    """F7 (ronda final): `json(r)` llamaba `r.json()` directo -- un 404/500 en
    HTML o un login redirect tiraban un SyntaxError crudo del navegador
    («Unexpected token '<'…») en vez de un aviso legible."""
    from sprints import datos
    sid = _sprint(datos)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    assert "el servidor respondió con un error" in html
    funcion = html[html.index("function json(r)"):html.index("function mensaje(e)")]
    assert ".catch(" in funcion    # r.json() puede rechazar (no es JSON): hay que atraparlo, no dejarlo subir crudo


def test_sugeridos_siguen_el_enfoque_y_avisan_lo_aflojado(app):
    from sprints import datos
    uno = _referente(1, "UGC")
    dos = _referente(2, "Antes y después")
    _referente(3, "Lista", consciencia="unaware")
    _referente(4, "Otra etapa", etapa="MOF")
    sid = _sprint(datos)
    cid = _campana(datos, sid, consciencia="consciente_del_problema", familias=["UGC"])
    datos.actualizar_campana("acme", cid, referencias_objetivo=1)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos").data.decode()
    assert f'data-sumar-ref="{uno}"' in html and "ya no filtran por" not in html
    datos.actualizar_campana("acme", cid, referencias_objetivo=5)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos").data.decode()
    assert f'data-sumar-ref="{dos}"' in html and "ya no filtran por" in html and "las familias de formato" in html
    assert "Otra etapa" not in html


def test_sugeridos_vacios_ofrecen_tres_salidas(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos").data.decode()
    for frag in ("No hay referentes para sugerir", "data-aflojar", "data-sugerir-ia", "Traer nuevos de Meta"):
        assert frag in html, frag
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos?todas=1").data.decode()
    assert "data-aflojar" not in html


def test_agregar_de_la_biblioteca_por_fetch_y_por_formulario(app):
    from sprints import datos
    uno, dos = _referente(1, "UGC"), _referente(2, "Lista")
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    url = f"/cliente/acme/sprints/campanas/{cid}/referencias_biblioteca"
    r = app["c"].post(url, data={"referente_ids": [str(uno)]}, headers={"X-Requested-With": "fetch"})
    assert r.get_json() == {"ok": True, "agregados": 1, "error": None}
    r = app["c"].post(url, data={"referente_ids": [str(dos)]})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}")
    assert len(datos.referencias("acme", cid)) == 2
    j = app["c"].post(url, data={"referente_ids": ["999"]}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] is False and j["error"]


def test_sugerir_ia_por_fetch(app, monkeypatch):
    from sprints import datos, rutas
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    url = f"/cliente/acme/sprints/campanas/{cid}/sugerir_ia"
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_sugerir_biblioteca", lambda cliente_, cid_: True)
    j = app["c"].post(url, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] and j["job_id"] == f"acme__campana{cid}__sugerir_biblioteca"
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_sugerir_biblioteca", lambda cliente_, cid_: False)
    j = app["c"].post(url, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] is False and "en curso" in j["error"]


def test_fotos_del_producto_vuelven_al_panel(app, monkeypatch):
    import catalogo_productos
    from sprints import datos, rutas
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda c, pid, cat=None: {"id": "espejo_led", "nombre": "Espejo LED", "imagenes": ["a.jpg"]})
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_analisis", lambda cliente_, rid: True)
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias/catalogo"
    r = app["c"].post(url, data={"volver": "tablero"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}")
    r = app["c"].post(url)
    assert r.headers["Location"].endswith(f"/sprints/{sid}/campanas/{cid}")


def test_las_mini_pantallas_viejas_ya_no_existen(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    for tipo in ("referencias", "ideas", "revision"):
        assert app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/{tipo}-ajax").status_code == 404

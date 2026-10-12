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
    assert "paises_sprint" not in ctx and "presets_por_pais" not in ctx   # el sprint es para todos los países
    assert (ctx["inicio_defecto"], ctx["fin_defecto"]) == tablero.mes_siguiente(date.today())
    assert datos.personas("acme") == []                     # ya no se crean personas genéricas


def test_pestana_muestra_el_formulario_corto(app):
    html = app["c"].get("/cliente/acme").data.decode()
    tab = html[html.index('id="tab-sprints"'):]
    for frag in ('name="nombre"', 'name="inicio"', 'name="momento"', 'name="marcas"', "Crear y armar campañas"):
        assert frag in tab, frag
    for viejo in ("campanas_json", "modal-agregar-campana", "sprint-paso", "Siguiente: la matriz"):
        assert viejo not in html, viejo


def test_crear_sprint_corto_abre_su_tablero(app):
    from sprints import calendario, datos
    clave = calendario.presets("CO", 2026)[0]["clave"]          # calendario del proyecto
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={
        "nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31",
        "momento": clave, "marcas": "Crocs\nSkechers 1234567"})
    s = datos.sprints("acme")[0]
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{s['id']}")
    assert s["pais"] is None and s["idioma"] == "en" and s["campanas_total"] == 0 and s["momento"]["clave"] == clave
    assert s["marcas"] == [{"nombre": "Crocs"}, {"nombre": "Skechers", "pagina_id": "1234567"}]


def test_crear_sprint_con_momento_propio(app):
    from sprints import datos
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31",
                                                        "momento": "propio", "momento_texto": "Lanzamiento"})
    s = datos.sprints("acme")[0]
    assert s["momento"] == {"nombre": "Lanzamiento"} and s["pais"] is None and s["idioma"] == "en"


@pytest.mark.parametrize("malo", [{"nombre": ""}, {"momento": "no_existe"}, {"fin": "2026-09-01"}])
def test_crear_sprint_invalido_no_crea_nada(app, malo):
    from sprints import datos
    datos_form = {"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31", **malo}
    r = app["c"].post("/cliente/acme/sprints/nuevo", data=datos_form)
    assert r.status_code == 302 and r.headers["Location"].endswith("#sprints")
    assert datos.sprints("acme", incluir_archivados=True) == []


def test_momento_del_mes_sigue_al_calendario_del_proyecto(app):
    """El sprint ya no lleva país (2026-09-27): «Momento del mes» ofrece el
    calendario del país del proyecto (el de Temporadas), y un preset de ese
    calendario se guarda sin «Ese momento del calendario no existe»."""
    import proyectos
    from sprints import datos
    proyectos.guardar_pais("acme", "MX")
    html = app["c"].get("/cliente/acme").data.decode()
    tab = html[html.index('id="tab-sprints"'):]
    assert 'value="buen_fin"' in tab and 'data-pais=' not in tab
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={
        "nombre": "Noviembre", "inicio": "2026-11-01", "fin": "2026-11-30", "momento": "buen_fin"})
    s = datos.sprints("acme")[0]
    assert r.status_code == 302 and s["momento"]["clave"] == "buen_fin" and s["pais"] is None


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
                 "1–31 oct · Hot Sale · imita: Crocs", 'id="tablero-panel"', 'id="tablero-alta"'):
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
    assert "Este sprint todavía no tiene campañas" in html and "data-alta-campana" in html


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
    j = _json(app["c"], url, {"campo": "momento", "valor": "propio:Hot Sale"}).get_json()
    assert j["ok"] and "Hot Sale" in j["linea"]
    assert datos.sprint("acme", sid)["momento"] == {"nombre": "Hot Sale"}
    assert _json(app["c"], url, {"campo": "momento", "valor": "navidad"}).get_json()["ok"]
    assert datos.sprint("acme", sid)["momento"]["clave"] == "navidad"
    assert _json(app["c"], url, {"campo": "marcas", "valor": "Crocs"}).get_json()["ok"]
    for malo in ({"campo": "idioma", "valor": "es"}, {"campo": "nombre", "valor": ""}, {"campo": "estado", "valor": "x"},
                 {"campo": "pais", "valor": "MX"}, {"campo": "fin", "valor": "2026-09-01"}):
        r = _json(app["c"], url, malo)
        assert r.status_code == 400 and r.get_json()["error"], malo
    assert _json(app["c"], "/cliente/acme/sprints/999/campo", {"campo": "nombre", "valor": "X"}).status_code == 404


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
    for frag in ("Audiencia y producto", "Enfoque", "Formato de los anuncios", "Marcas a imitar", "Piezas",
                 "Referentes · <span data-ref-listas>0</span> de <span data-ref-objetivo>5</span> elegidos", 'data-campo="persona_id"', 'data-campo="catalogo_id"',
                 'data-campo="funnel"', 'data-campo="consciencia"', 'data-campo="dolor"', 'data-campo="familias"',
                 'data-campo="marcas"', 'data-campo="n_videos"',
                 'data-campo="n_imagenes"', 'data-campo="referencias_objetivo"', "Sugerir con IA",
                 "Buscar en la biblioteca", "Traer nuevos de Meta", 'name="volver" value="tablero"',
                 "Eliminar campaña", "Crear persona rápida", "data-sugeridos"):
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
    assert "Del sprint: Crocs" in html
    assert "#referentes?" in html and "etapa=TOF" in html and "consciencia=problem-aware" in html
    assert "pais=MX" in html and "palabra=Espejo+LED" in html


def test_panel_muestra_referencias_viejas_sin_frame(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    datos.agregar_referencia("acme", cid, "imagen", "https://r2/vieja.png", frame_url=None, titulo="vieja.png")
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel").data.decode()
    assert 'src="https://r2/vieja.png"' in html and "Falta describir" in html


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
    # Idioma (Task 4): el texto ahora sale de TEXTO_TABLERO.errorServidor, un
    # `_('...')|tojson` como el resto de la app — igual que test_rutas_experimentos_galeria,
    # tojson escapa los acentos a \\uXXXX (JSON válido; el navegador lo decodifica igual).
    assert "el servidor respondi\\u00f3 con un error" in html
    funcion = html[html.index("function json(r)"):html.index("function mensaje(e)")]
    assert ".catch(" in funcion    # r.json() puede rechazar (no es JSON): hay que atraparlo, no dejarlo subir crudo


def test_panel_no_se_blanquea_ni_pierde_el_scroll_al_reabrir_la_misma_campana(app):
    """F8 (ronda final): `abrir(cid)` blanqueaba a «Cargando…» y perdía el
    scroll aun cuando la campaña que reabría era la MISMA que ya estaba
    mostrando -- pasa después de guardar un campo que recarga el panel, o de
    agregar/quitar un referente. Dos `abrir` rápidas también podían dejar que
    una respuesta vieja pisara a la más nueva."""
    from sprints import datos
    sid = _sprint(datos)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    js = html[html.index("function mostrar()"):html.index("window.tablero = {")]
    assert "panelActualCid" in js and "peticionPanel" in js
    assert "if (!mismo)" in js or "if (mismo)" in js
    assert "panel.scrollTop" in js
    assert js.count("panelActualCid = null") >= 2    # cerrar() y noExiste() sueltan el cid actual


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


def test_sugeridos_gratis_heredan_la_consciencia_de_nicho_si_la_campana_no_tiene(app, monkeypatch):
    """F9 (ronda final): la tarea de «Sugerir con IA» (tareas/sprints.py) ya
    caía a `datos.consciencia_de_persona` cuando la campaña no tenía
    consciencia propia; la ruta gratis (`campana_sugeridos`) no lo hacía --
    una campaña creada ANTES de que Nicho investigara a su persona se quedaba
    sin ese filtro para siempre."""
    from sprints import datos, rutas
    pid = datos.crear_persona("acme", "Melissa", resumen="x")   # sin nivel de Nicho al crear la campaña
    sid = _sprint(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    assert datos.campana("acme", cid)["consciencia"] is None
    datos.actualizar_persona("acme", pid, extra={"conciencia": {"nivel": "consciente_del_problema"}})

    vistos = []

    def _falso(cliente, enfoque, excluir, objetivo, **kw):
        vistos.append(enfoque)
        return {"items": [], "aflojado": []}
    monkeypatch.setattr(rutas.referentes_sugerir, "sugerir_campana", _falso)

    app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos")
    assert vistos and vistos[0]["consciencia"] == "consciente_del_problema"


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
    r = app["c"].post(url, data={"volver": "tablero", "n_visto": 1})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}")
    r = app["c"].post(url, data={"n_visto": 0})
    assert r.headers["Location"].endswith(f"/sprints/{sid}/campanas/{cid}")


def test_las_mini_pantallas_viejas_ya_no_existen(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    for tipo in ("referencias", "ideas", "revision"):
        assert app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/{tipo}-ajax").status_code == 404


def test_buscadores_y_campos_vacios_no_quedan_sin_guardar(app):
    """Tres marcas `data-sucio` que nada limpiaba y hacían que `recargarOAvisar`
    (base.html) pidiera «Recargar ahora» en falso al terminar un trabajo:
    un buscador (familias del panel, o cualquier type="search") nunca guarda
    nada; «Otro (escríbelo)…» del momento sin texto no tiene qué guardar; y el
    «otro: ¿qué?» de la página de referencias se guarda con su tarjeta."""
    from sprints import datos
    base = open("templates/base.html", encoding="utf-8").read()
    marcar = base[base.index("function marcarSucio"):base.index("document.addEventListener('input', marcarSucio)")]
    assert "el.type === 'search'" in marcar and "data-busqueda" in marcar
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    panel = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel?paso=armar",
                         headers={"X-Requested-With": "fetch"}).data.decode()
    buscador = panel[panel.index('class="panel-familia-buscar"'):]
    assert "data-busqueda" in buscador[:buscador.index(">")]
    html = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    cambio = html[html.index("campos.addEventListener('change'"):html.index("function puedeRecargar")]
    assert "function sinTextoPropio()" in html and cambio.count("sinTextoPropio()") == 2
    refs = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}").data.decode()
    assert "if (enviado === cambios)" in refs and "input[name=intencion_otro], textarea[name=descripcion]" in refs
    assert "ta.addEventListener('blur'" not in refs

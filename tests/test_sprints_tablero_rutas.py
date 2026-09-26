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

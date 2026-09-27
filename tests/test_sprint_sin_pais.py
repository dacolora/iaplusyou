"""El sprint es para todos los países (pedido de Daniel, 2026-09-27): no lleva
país ni idioma. Se trabaja en inglés como base y cada país/idioma se resuelve
después en la edición final. Los sprints viejos conservan lo que tenían."""
from tests.test_sprints_tablero_rutas import app  # noqa: F401  (fixture: admin en /cliente/acme)


def _sprint(datos, **kw):
    return datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", **kw)


def _campana(datos, sid):
    pid = datos.crear_persona("acme", "Premium", resumen="Busca calidad")
    return datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)


def test_formulario_nuevo_sprint_sin_pais_ni_idioma(app):
    html = app["c"].get("/cliente/acme").data.decode()
    tab = html[html.index('id="tab-sprints"'):]
    form = tab[tab.index('id="nuevo-sprint"'):tab.index("</form>", tab.index('id="nuevo-sprint"'))]
    assert 'name="pais"' not in form and 'name="idioma"' not in form
    assert 'data-pais="' not in form                  # el momento sale del calendario del proyecto
    assert 'name="momento"' in form and 'name="marcas"' in form


def test_crear_sprint_queda_para_todos_los_paises_en_ingles(app):
    from sprints import calendario, datos
    clave = calendario.presets("CO", 2026)[0]["clave"]       # calendario del proyecto (CO por defecto)
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={
        "nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31",
        "pais": "MX", "idioma": "es",                        # un formulario viejo: se ignora
        "momento": clave})
    assert r.status_code == 302
    s = datos.sprints("acme")[0]
    assert s["pais"] is None and s["idioma"] == "en" and s["momento"]["clave"] == clave


def test_cabecera_y_panel_sin_pais_ni_idioma(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    pagina = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    assert 'data-campo="pais"' not in pagina and 'data-campo="idioma"' not in pagina
    panel = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel").data.decode()
    assert 'data-campo="pais"' not in panel and 'data-campo="idioma"' not in panel
    assert "pais=" not in panel                             # «Traer nuevos de Meta» busca en todos los países


def test_pais_e_idioma_ya_no_se_editan_por_json(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    r = app["c"].post(f"/cliente/acme/sprints/{sid}/campo", json={"campo": "pais", "valor": "MX"})
    assert r.status_code == 400
    r = app["c"].post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/campo", json={"campo": "idioma", "valor": "es"})
    assert r.status_code == 400
    assert datos.sprint("acme", sid)["pais"] is None


def test_ideas_de_un_sprint_global(base_temporal):
    from sprints import ideas
    ctx = {"mercado": {"pais": None, "idioma": "en"}}
    texto = ideas._mercado_texto(ctx)
    assert "todos los países" in texto and "inglés" in texto and "edición final" in texto
    assert "inglés" in ideas.instrucciones(ctx) and "Todo en español." not in ideas.instrucciones(ctx)

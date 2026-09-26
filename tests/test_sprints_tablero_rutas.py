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

"""sprints.tablero: funciones puras de las tarjetas y la cabecera del tablero."""
from datetime import date

from sprints import tablero

# La única prueba de ruta de este archivo (abajo, catálogo agrupado por color)
# reusa el catálogo real de tests/test_rutas_catalogo.py: su `app` monkeypatchea
# catalogo_productos.BASE_DIR a un tmp_path (a diferencia del `app` de
# tests/test_rutas_sprints.py, que reemplaza catalogo_productos.listar por una
# lista fija sin producto_id/variante) y sigue siendo el mismo dashboard.app
# donde vive el Blueprint de sprints.
from tests.test_rutas_catalogo import _con_colores, app  # noqa: F401


def _c(**kw):
    base = {"referencias_objetivo": 5, "referencias_listas": 5, "n_videos": 1, "n_imagenes": 1, "ideas": [], "piezas": []}
    base.update(kw)
    return base


def _idea(estado_idea="aprobada", sin_sesion=False, estado=None, revision="pendiente"):
    return {"estado_idea": estado_idea, "sin_sesion": sin_sesion, "estado": estado, "revision": revision}


def test_siguiente_paso_sigue_el_orden_del_trabajo():
    assert tablero.siguiente_paso(_c(referencias_listas=3)) == {"clave": "referentes", "texto": "elegir 2 referentes"}
    assert tablero.siguiente_paso(_c(referencias_listas=4))["texto"] == "elegir 1 referente"
    assert tablero.siguiente_paso(_c())["clave"] == "ideas"
    propuestas = [_idea("propuesta", True), _idea("propuesta", True)]
    assert tablero.siguiente_paso(_c(ideas=propuestas))["texto"] == "aprobar 2 ideas"
    aprobadas = [_idea(sin_sesion=True), _idea(sin_sesion=True)]
    assert tablero.siguiente_paso(_c(ideas=aprobadas))["texto"] == "generar 2 piezas"
    en_curso = [_idea(estado="generando"), _idea(estado="listo")]
    assert tablero.siguiente_paso(_c(ideas=en_curso, piezas=en_curso))["clave"] == "generando"
    con_error = [_idea(estado="error"), _idea(estado="listo", revision="aprobada")]
    assert tablero.siguiente_paso(_c(ideas=con_error, piezas=con_error))["clave"] == "errores"
    listas = [_idea(estado="listo"), _idea(estado="degradada", revision="aprobada")]
    assert tablero.siguiente_paso(_c(ideas=listas, piezas=listas))["texto"] == "revisar 1 pieza"
    hechas = [_idea(estado="listo", revision="aprobada"), _idea(estado="listo", revision="rechazada")]
    assert tablero.siguiente_paso(_c(ideas=hechas, piezas=hechas)) == {"clave": "lista", "texto": "campaña lista"}


def test_las_descartadas_no_cuentan():
    ideas = [_idea("descartada", True), _idea("aprobada", True)]
    assert tablero.siguiente_paso(_c(n_videos=1, n_imagenes=0, ideas=ideas))["texto"] == "generar 1 pieza"


def test_sugerencias_dolor_salen_de_la_persona():
    p = {"resumen": "Comodidad al llegar", "senales_visuales": ["pisos helados", "sofá", "tercera"],
         "extra": {"encaje_producto": "Abriga sin sudar", "evidencia": [{"cita": "mis pies son hielo"}, {"cita": "x"}]}}
    assert tablero.sugerencias_dolor(p) == ["Comodidad al llegar", "Abriga sin sudar", "pisos helados", "sofá"]
    assert tablero.sugerencias_dolor(None) == [] and tablero.sugerencias_dolor({"nombre": "X"}) == []


def test_mes_siguiente():
    assert tablero.mes_siguiente(date(2026, 9, 26)) == ("2026-10-01", "2026-10-31")
    assert tablero.mes_siguiente(date(2026, 12, 3)) == ("2027-01-01", "2027-01-31")
    assert tablero.mes_siguiente(date(2027, 1, 30)) == ("2027-02-01", "2027-02-28")


def test_resumen_y_linea_del_sprint():
    sp = {"inicio": "2026-10-01", "fin": "2026-10-31", "pais": "CO", "idioma": "es",
          "momento": {"nombre": "Hot Sale"}, "marcas": [{"nombre": "Crocs"}, {"nombre": "Hoka", "pagina_id": "555555"}],
          "campanas": [_c(referencias_listas=3, n_videos=5, n_imagenes=5), _c(referencias_listas=7, n_videos=3, n_imagenes=0)]}
    assert tablero.resumen(sp) == "2 campañas · 13 piezas planeadas · 8/10 referentes elegidos"
    assert tablero.resumen({"campanas": []}) == "0 campañas · 0 piezas planeadas · 0/0 referentes elegidos"
    assert tablero.linea_sprint(sp) == "1–31 oct · Hot Sale · imita: Crocs, Hoka"   # sin país ni idioma
    otro = {"inicio": "2026-10-20", "fin": "2026-11-10", "pais": None, "idioma": "en", "momento": None, "marcas": []}
    assert tablero.linea_sprint(otro) == "20 oct – 10 nov"


def test_marcas_texto():
    assert tablero.marcas_texto([{"nombre": "Crocs"}, {"nombre": "Hoka", "pagina_id": "555555"}]) == "Crocs\nHoka 555555"
    assert tablero.marcas_texto(None) == ""


def test_paso_por_defecto_sigue_el_siguiente_paso():
    assert tablero.paso_por_defecto(_c(referencias_listas=3)) == "armar"
    assert tablero.paso_por_defecto(_c()) == "ideas"                                   # proponer ideas
    assert tablero.paso_por_defecto(_c(ideas=[_idea("propuesta", True)])) == "ideas"  # aprobar
    assert tablero.paso_por_defecto(_c(ideas=[_idea(sin_sesion=True), _idea(sin_sesion=True)])) == "ideas"  # generar
    en_curso = [_idea(estado="generando"), _idea(estado="listo")]
    assert tablero.paso_por_defecto(_c(ideas=en_curso, piezas=en_curso)) == "piezas"
    listas = [_idea(estado="listo"), _idea(estado="listo", revision="aprobada")]
    assert tablero.paso_por_defecto(_c(ideas=listas, piezas=listas)) == "piezas"


def test_resolver_paso():
    assert tablero.resolver_paso("piezas", _c(referencias_listas=0)) == "piezas"
    assert tablero.resolver_paso("otra", _c(referencias_listas=0)) == "armar"
    assert tablero.resolver_paso(None, _c()) == "ideas"
    assert tablero.PASOS == ("armar", "ideas", "piezas")


def test_pestanas_cuentan_lo_de_cada_paso():
    ideas = [_idea("aprobada", estado="listo"), _idea("propuesta", True), _idea("descartada", True)]
    piezas = [ideas[0]]
    assert tablero.pestanas(_c(referencias_listas=3, ideas=ideas, piezas=piezas)) == \
        {"armar": "3/5", "ideas": "1/2", "piezas": "1/2"}
    assert tablero.pestanas(_c())["armar"] == "✓"


# --------------------------------------------------------- panel (ruta) ---

def test_panel_agrupa_los_colores_del_producto(app):
    """El <select> de producto del panel «Armar» agrupa los colores de un
    mismo producto en un <optgroup> (spec 2026-09-28 §10.5), igual que el
    selector de Crear."""
    from sprints import datos
    _con_colores(app)                          # Original: pink + beige, en el catálogo temporal
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    pid = datos.crear_persona("acme", "Premium", resumen="Busca calidad")
    cid = datos.agregar_campana("acme", sid, pid, "original/pink", None, 2, 1)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel",
                        headers={"X-Requested-With": "fetch"}).data.decode()
    assert '<optgroup label="Original">' in html and '<option value="original/pink"' in html and ">Pink<" in html

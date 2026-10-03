"""Sistema de estilos (spec docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md):
static/estilos/ es la fuente y static/style.css se genera con «python3 estilos.py construir»."""
import os

import estilos

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _carpeta(tmp_path, archivos, orden):
    for ruta, texto in archivos.items():
        p = tmp_path / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    (tmp_path / "ORDEN").write_text(orden, encoding="utf-8")
    return str(tmp_path)


def test_unir_respeta_el_orden_y_los_separadores(tmp_path):
    c = _carpeta(tmp_path, {"tokens.css": ":root { --a: #000; }\n", "legado/01-x.css": ".x { color: var(--a); }\n"},
                 "# comentario\ntokens.css\n\nlegado/01-x.css  # al final\n")
    assert estilos.leer_orden(c) == ["tokens.css", "legado/01-x.css"]
    assert estilos.unir(c, separadores=False) == ":root { --a: #000; }\n.x { color: var(--a); }\n"
    con = estilos.unir(c)
    assert con.startswith(estilos.CABECERA)
    assert "/* ── estilos/legado/01-x.css ── */\n.x" in con


def test_archivos_css_lista_todo(tmp_path):
    c = _carpeta(tmp_path, {"tokens.css": "", "componentes/boton.css": "", "nota.txt": ""}, "tokens.css\n")
    assert estilos.archivos_css(c) == ["componentes/boton.css", "tokens.css"]


def test_tokens_y_contraste(tmp_path):
    c = _carpeta(tmp_path, {"tokens.css": "/* x */\n:root {\n  color-scheme: dark;\n  --panel: #0b1a33;\n  --text: #eef4ff;\n"
                                          "  --borde: rgba(80, 150, 255, 0.16);\n  --esp-1: 4px;\n}\n"}, "tokens.css\n")
    assert estilos.tokens(c) == [("--panel", "#0b1a33"), ("--text", "#eef4ff"), ("--borde", "rgba(80, 150, 255, 0.16)"),
                                 ("--esp-1", "4px")]
    assert estilos.es_color("#0b1a33") and estilos.es_color("rgba(80, 150, 255, 0.16)") and not estilos.es_color("4px")
    assert estilos.contraste("#eef4ff", "#0b1a33") == 15.72
    assert estilos.contraste("#ffffff", "#1d6ae0") == 5.01
    assert estilos.contraste("4px", "#0b1a33") is None

def test_construir_con_orden_roto_no_toca_la_hoja(tmp_path):
    """Revisión de la entrega 1: `construir` abría la hoja antes de unir y un ORDEN con un archivo que no existe la dejaba en
    0 bytes. Ahora une primero, escribe a un temporal y reemplaza; con ORDEN roto, la hoja de antes queda intacta."""
    import pytest
    c = _carpeta(tmp_path / "estilos", {"tokens.css": ":root { --a: #000; }\n"}, "tokens.css\nlegado/99-no-existe.css\n")
    hoja = tmp_path / "style.css"
    hoja.write_text("la de antes", encoding="utf-8")
    with pytest.raises(estilos.OrdenInvalido, match="99-no-existe.css"):
        estilos.construir(c, str(hoja))
    assert hoja.read_text(encoding="utf-8") == "la de antes"
    assert not [p for p in os.listdir(tmp_path) if p.startswith("style.css.")], "quedó un temporal suelto"


def test_orden_con_repetido_o_archivo_fuera_es_invalido(tmp_path):
    import pytest
    repetido = _carpeta(tmp_path / "a", {"tokens.css": ""}, "tokens.css\ntokens.css\n")
    with pytest.raises(estilos.OrdenInvalido, match="repite"):
        estilos.unir(repetido)
    fuera = _carpeta(tmp_path / "b", {"tokens.css": "", "componentes/boton.css": ""}, "tokens.css\n")
    with pytest.raises(estilos.OrdenInvalido, match="componentes/boton.css"):
        estilos.unir(fuera)


def test_comprobar_ve_una_hoja_vieja(tmp_path):
    c = _carpeta(tmp_path / "estilos", {"tokens.css": ":root { --a: #000; }\n"}, "tokens.css\n")
    hoja = tmp_path / "style.css"
    estilos.construir(c, str(hoja))
    assert estilos.comprobar(c, str(hoja))
    hoja.write_text(hoja.read_text(encoding="utf-8") + ".x {}\n", encoding="utf-8")
    assert not estilos.comprobar(c, str(hoja))


CAPAS = {"tokens.css": 0, "legado": 1, "base.css": 2, "componentes": 3, "pantallas": 4}


def _capa(ruta):
    return CAPAS[ruta if ruta in CAPAS else ruta.split("/", 1)[0]]


def test_la_hoja_es_la_generada():
    with open(estilos.HOJA, encoding="utf-8") as f:
        assert f.read() == estilos.unir(), "static/style.css no es la hoja generada: corre «python3 estilos.py construir»"


def test_orden_nombra_cada_archivo_una_vez_y_por_capas():
    orden = estilos.leer_orden()
    assert len(orden) == len(set(orden)), "ORDEN repite un archivo"
    assert sorted(orden) == estilos.archivos_css(), "ORDEN y static/estilos/ no coinciden (falta o sobra un archivo)"
    assert orden[0] == "tokens.css"
    capas = [_capa(r) for r in orden]
    assert capas == sorted(capas), "ORDEN va por capas: tokens.css, legado/, base.css, componentes/, pantallas/"

import glob
import re

# Los morados e índigos de la paleta vieja (los dos últimos los encontró el barrido por tono de la revisión de la
# entrega 1). El violeta de la insignia de WooCommerce (#b48be0 / 127,84,179) se queda a propósito: es el color de su
# marca, como el verde de Shopify y el amarillo de Mercado Libre.
MORADOS = re.compile(r"7c3aed|a855f7|a78bfa|8b5cf6|8b6cf0|6d28d9|c4b5fd|9333ea|124,\s*58,\s*237|168,\s*85,\s*247|"
                     r"124,\s*92,\s*255|124,\s*108,\s*255|108,\s*92,\s*231", re.I)


def _archivos_estilo_y_plantillas():
    css = [os.path.join(estilos.CARPETA, r) for r in estilos.archivos_css()]
    plantillas = [p for p in glob.glob(os.path.join(RAIZ, "templates", "*.html")) if not p.endswith("mapa_codigo.html")]
    return css + plantillas


def test_sin_morados():
    fallas = []
    for ruta in _archivos_estilo_y_plantillas():
        with open(ruta, encoding="utf-8") as f:
            if MORADOS.search(f.read()):
                fallas.append(os.path.relpath(ruta, RAIZ))
    assert not fallas, "el morado se fue de la app (spec §3): " + ", ".join(fallas)

_RE_COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:white|black)\b(?!-)")
_RE_VALOR = re.compile(r":\s*([^;{}]+)")
ANIMACIONES_PERMITIDAS = {"pulso", "aparece-card", "exp-pulso", "fe-pulso", "flash-in", "girar", "gp-latido",
                          "gp-recien", "rayas-progreso", "shimmer"}
TECHO_COLORES_LEGADO = 199     # medido el 2026-10-02 al cerrar la paleta azul; solo baja
TECHO_ESTILOS_EN_LINEA = 414   # medido el 2026-10-02 con la Guía; solo baja


def _sin_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _leer_estilo(ruta):
    with open(os.path.join(estilos.CARPETA, ruta), encoding="utf-8") as f:
        return _sin_comentarios(f.read())


def _colores_en(css):
    return sum(len(_RE_COLOR_LITERAL.findall(v)) for v in _RE_VALOR.findall(css))


def _colores_en_legado():
    return sum(_colores_en(_leer_estilo(r)) for r in estilos.leer_orden() if r.startswith("legado/"))


def _plantillas():
    return sorted(glob.glob(os.path.join(RAIZ, "templates", "*.html")))


def _estilos_en_linea():
    total = 0
    for p in _plantillas():
        with open(p, encoding="utf-8") as f:
            total += f.read().count('style="')
    return total


def test_colores_solo_en_tokens():
    fallas = [r for r in estilos.leer_orden()
              if r != "tokens.css" and not r.startswith("legado/") and _colores_en(_leer_estilo(r))]
    assert not fallas, "colores escritos a mano fuera de tokens.css (usa var(--…)): " + ", ".join(fallas)


def test_legado_solo_baja():
    n = _colores_en_legado()
    assert n <= TECHO_COLORES_LEGADO, f"legado/ tiene {n} colores literales y el techo es {TECHO_COLORES_LEGADO}: muda, no agregues"


def test_estilos_en_linea_sin_colores_y_sin_crecer():
    fallas = []
    for p in _plantillas():
        if p.endswith("mapa_codigo.html"):
            continue
        with open(p, encoding="utf-8") as f:
            for estilo in re.findall(r'style="([^"]*)"', f.read()):
                if _RE_COLOR_LITERAL.search(estilo):
                    fallas.append(f"{os.path.basename(p)}: {estilo[:60]}")
    assert not fallas, "colores en style=\"…\" (usa una clase o var(--…)): " + "; ".join(fallas)
    n = _estilos_en_linea()
    assert n <= TECHO_ESTILOS_EN_LINEA, f"{n} style=\"…\" en templates/ y el techo es {TECHO_ESTILOS_EN_LINEA}: usa una clase"


def _reglas(css):
    """(selectores, cuerpo) de cada regla sin anidar: los de un @media salen sueltos, sin el @media."""
    return [([s.strip() for s in sel.split(",")], cuerpo) for sel, cuerpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def test_enlaces_sin_clase_en_el_azul_del_sistema():
    """Sin una regla para `a`, Chrome pinta los enlaces con su lila (#9e9eff) y los visitados de morado (#d0adf0) en
    tema oscuro: «¿Olvidaste tu contraseña?» del login, «Volver al panel»… (spec §3: el morado se va). Va en base.css
    con :where(), que no suma especificidad: cualquier clase con su propio color le gana."""
    cuerpos = [c for sel, c in _reglas(_leer_estilo("base.css")) if ":where(a)" in sel]
    assert cuerpos and re.search(r"color:\s*var\(--accent-texto\)", cuerpos[0])


def test_botones_con_clase_sin_fondo_propio_son_secundarios():
    """Un <button> con clase que no pinta su fondo queda con el gris del navegador (#6b6b6b en tema oscuro): el «☰ Menú»
    del celular y los filtros de voces de Audios lo tenían. Entran a la regla del botón secundario de la base visual."""
    with open(estilos.HOJA, encoding="utf-8") as f:
        hoja = _sin_comentarios(f.read())
    secundario = [(sel, c) for sel, c in _reglas(hoja) if "button:not([class])" in sel]
    assert secundario and "var(--panel)" in secundario[0][1]
    for clase in (".menu-movil", ".au-filtro"):
        assert clase in secundario[0][0], f"{clase} queda con el gris del navegador"


def test_editor_sobrio_detras_del_video():
    """Decisión de Daniel (2026-10-02): el editor va azul, pero detrás del reproductor un gris neutro y el lienzo negro,
    sin brillo: un marco azul fuerte engaña el ojo al juzgar los colores del video."""
    with open(os.path.join(RAIZ, "templates", "editor.html"), encoding="utf-8") as f:
        html = f.read()
    assert re.search(r"\.ed-centro\s*\{[^}]*background:\s*var\(--fondo-video\)", html)
    assert re.search(r"#lienzo\s*\{[^}]*background:\s*var\(--fondo-lienzo\)", html)
    valores = dict(estilos.tokens())
    assert valores["--fondo-video"] == "#121417" and valores["--fondo-lienzo"] == "#000000"


def test_base_reduce_movimiento_y_animaciones_permitidas():
    assert "prefers-reduced-motion: reduce" in _leer_estilo("base.css")
    for r in estilos.leer_orden():
        if r == "tokens.css" or r.startswith("legado/"):
            continue
        css = _leer_estilo(r)
        usadas = set(re.findall(r"@keyframes\s+([\w-]+)", css)) | set(re.findall(r"animation(?:-name)?\s*:\s*([\w-]+)", css))
        extra = usadas - ANIMACIONES_PERMITIDAS - {"none"}
        assert not extra, f"{r}: animaciones fuera de ANIMACIONES_PERMITIDAS (spec §9 regla 7): {sorted(extra)}"

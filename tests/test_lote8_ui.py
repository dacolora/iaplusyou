"""Guardias del CSS y del marcado que limitan el ancho; capturas a cargo de Claude."""
from pathlib import Path
import re


def _bloques(css):
    """Bloques con llaves balanceadas: conserva el ámbito de los @media."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    inicio = 0
    while (abre := css.find('{', inicio)) != -1:
        profundidad, fin = 1, abre + 1
        while profundidad:
            profundidad += (css[fin] == '{') - (css[fin] == '}')
            fin += 1
        yield css[inicio:abre].strip(), css[abre + 1:fin - 1]
        inicio = fin


def regla(selector, media=False):
    css = Path('static/estilos/pantallas/sprints.css').read_text()
    bloques = list(_bloques(css))
    if media:
        bloques = [regla for cabecera, cuerpo in bloques
                   if re.fullmatch(r'@media\s*\(max-width:\s*\d+px\)', cabecera)
                   for regla in _bloques(cuerpo)]
    matches = [cuerpo for cabecera, cuerpo in bloques if cabecera == selector]
    assert matches, f'Falta la regla {selector} en ' + ('media max-width' if media else 'escritorio')
    return matches[-1]


def test_pnd209_link_limitado_y_avisos_envuelven():
    html = Path('templates/campana_referencias.html').read_text()
    assert 'class="sprint-link-campo"' in html
    assert 'style="width: 22rem;"' not in html
    assert 'max-width: 100%' in regla('.sprint-link-campo')
    assert 'white-space: normal' in regla('.sprint-aviso')
    assert 'overflow-wrap: anywhere' in regla('.sprint-aviso')


def test_pnd210_aviso_detenido_no_impone_ancho():
    html = Path('templates/_nicho_investigacion.html').read_text()
    detenida = re.search(r'{% if inv\.detenida_por %}(.*?){% endif %}', html, re.S).group(1)
    parrafo = re.search(r'<p\b[^>]*class="([^"]*)"', detenida).group(1)
    assert 'sprint-aviso' in parrafo.split()
    bloque = regla('.sprint-aviso')
    assert 'max-width: 100%' in bloque
    assert 'white-space: normal' in bloque
    assert 'overflow-wrap: anywhere' in bloque


def test_pnd032_filtros_en_filas_con_campana_a_todo_el_ancho():
    html = Path('templates/sprint_revision.html').read_text()
    assert 'class="sprint-filtros"' in html
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr))' in regla('.sprint-filtros', media=True)
    assert 'grid-column: 1 / -1' in regla('.sprint-filtros > label:first-child', media=True)
    assert 'grid-template-columns: minmax(0, 2fr) repeat(2, minmax(0, 1fr))' in regla('.sprint-filtros')
    assert 'min-width: 0' in regla('.sprint-filtros > label')
    assert 'max-width: 100%' in regla('.sprint-filtros select')


def test_filtros_separados_de_las_acciones():
    bloque = regla('.sprint-filtros')
    margen = re.search(r'margin-top:\s*([\d.]+)(rem|em|px)\s*;', bloque)
    assert margen is not None, 'Falta margen superior en sprint-filtros'
    assert float(margen.group(1)) > 0

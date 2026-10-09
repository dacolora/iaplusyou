"""Guardias del CSS y del marcado que limitan el ancho; capturas a cargo de Claude."""
from pathlib import Path
import re
import pytest
import estilos


def regla(selector, media=False):
    css = estilos.unir()
    if media:
        css = css[css.index('/* Lote 8: filtros de revisión en celular. */'):]
    matches = re.findall(re.escape(selector) + r'\s*\{([^}]+)\}', css)
    assert matches, f'Falta la regla {selector}'
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
    assert 'class="tag-estado sprint-aviso"' in html
    bloque = regla('.sprint-aviso')
    assert 'max-width: 100%' in bloque
    assert 'white-space: normal' in bloque
    assert 'overflow-wrap: anywhere' in bloque


def test_pnd032_filtros_en_filas_con_campana_a_todo_el_ancho():
    html = Path('templates/sprint_revision.html').read_text()
    assert 'class="sprint-filtros"' in html
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr))' in regla('.sprint-filtros', media=True)
    assert 'grid-column: 1 / -1' in regla('.sprint-filtros > label:first-child', media=True)
    assert 'min-width: 0' in regla('.sprint-filtros > label')
    assert 'max-width: 100%' in regla('.sprint-filtros select')

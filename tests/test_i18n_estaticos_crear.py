"""Los scripts extraídos reciben el texto visible traducido desde la página."""
from pathlib import Path
import pytest
from tests.i18n_util import _SCRIPT_TOKEN, _con_marca


@pytest.mark.parametrize('archivo', ['crear-compositor', 'crear-flowplus', 'crear-audios', 'crear-guiones'])
def test_scripts_de_crear_sin_espanol_visible_suelto(archivo):
    js = (Path(__file__).parents[1] / 'static' / (archivo + '.js')).read_text()
    literales = [t for t in _SCRIPT_TOKEN.findall(js) if t[0] in ("'", '"', '`') and _con_marca(t)]
    assert not literales, f'{archivo}: {literales}'

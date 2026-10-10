"""PND-155: precio local y selectores con listas centrales de producción."""
from pathlib import Path
import re
import pytest
from flask import render_template_string
from tests.test_rutas_experimentos import app  # noqa: F401


@pytest.mark.parametrize('pais,moneda', [('NO','NOK'),('SE','SEK')])
@pytest.mark.parametrize('precio', ['299 Kr','299 kr','299 KR','NOK 299','SEK 299','$299','€299','299,50 kr','1.299,50 kr'])
def test_pnd155_precio_coronas(pais, moneda, precio):
    from nicho.fuentes.plataformas import _precio_moneda
    numero, divisa = _precio_moneda({'price':precio, 'loadedCountryCode':pais})
    esperado = 1299.50 if precio.startswith('1.') else 299.50 if ',' in precio else 299
    assert numero == esperado
    assert divisa == ('NOK' if precio.startswith('NOK') else 'SEK' if precio.startswith('SEK') else
                       'EUR' if precio.startswith('€') else 'USD' if precio.startswith('$') else moneda)


def _selector(plantilla, nombre):
    s = Path('templates',plantilla).read_text()
    return re.search(r'<select name="'+nombre+r'">.*?</select>', s, re.S).group()


def test_pnd155_idiomas_final_salen_de_lista_central(app, monkeypatch):
    import idiomas
    monkeypatch.setattr(idiomas, 'NOMBRES_PUBLICACION', {'no':'central-no', 'sv':'central-sv'}, raising=False)
    with app['dashboard'].app.test_request_context('/cliente/acme'):
        html = render_template_string(_selector('_final_detalle.html','idioma_base'), idiomas_fe=['no','sv'])
    assert 'central-no' in html and 'central-sv' in html
    assert idiomas.IDIOMAS == ('en', 'es')


def test_pnd155_referentes_paises_centrales(app, monkeypatch):
    from final_edition import tipos
    monkeypatch.setitem(tipos.PAISES,'NO', {**tipos.PAISES['NO'], 'nombre':'central-no'})
    monkeypatch.setitem(tipos.PAISES,'SE', {**tipos.PAISES['SE'], 'nombre':'central-se'})
    with app['dashboard'].app.test_request_context('/cliente/acme'):
        html = render_template_string(_selector('_referentes_traer.html','pais'), consulta={'pais':'NO'})
    assert 'value="NO" selected' in html and 'value="SE"' in html
    assert 'central-no' in html and 'central-se' in html


@pytest.mark.parametrize('codigo', ['no', 'sv'])
def test_pnd155_nombres_reales_sin_monkeypatch(app, codigo):
    import idiomas
    from babel import Locale
    nombre = idiomas.NOMBRES_PUBLICACION[codigo]
    assert nombre.casefold() != codigo
    assert len(nombre.strip()) > len(codigo)
    assert nombre.casefold().startswith(Locale.parse(codigo).get_language_name().casefold())
    with app['dashboard'].app.test_request_context('/cliente/acme'):
        html = render_template_string(_selector('_final_detalle.html', 'idioma_base'), idiomas_fe=[codigo])
    assert re.search(r'<option[^>]*value="' + codigo + r'"[^>]*>(.*?)</option>', html, re.S).group(1).strip() == nombre


@pytest.mark.parametrize('pais', ['ALL', 'EC', 'NO', 'SE', 'BR'])
def test_pnd155_paises_solo_lista_decidida(app, pais):
    with app['dashboard'].app.test_request_context('/cliente/acme'):
        html = render_template_string(_selector('_referentes_traer.html', 'pais'), consulta={'pais': pais})
    codigos = re.findall(r'<option[^>]*value="([A-Z]+)"', html)
    assert codigos == ['ALL', 'CO', 'MX', 'AR', 'CL', 'PE', 'EC', 'US', 'ES', 'NO', 'SE']

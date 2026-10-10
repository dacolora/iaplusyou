"""Leer el JS enlazado por el HTML real, sin red ni alterar expectativas."""
from pathlib import Path
from urllib.parse import urlparse
from tests.html_lote7 import HTML


def con_script_estatico(html, archivo):
    ruta = '/static/' + archivo
    enlaces = [n for n in HTML(html).raiz.todos('script')
               if urlparse(n.attrs.get('src', '')).path == ruta]
    assert len(enlaces) == 1, f'Falta el enlace a {ruta}'
    js = (Path(__file__).parents[1] / 'static' / archivo).read_text()
    return html + '\n<script>\n' + js + '\n</script>'


def config_script(html, archivo):
    """Los mismos datos que JSON.parse recibe en el módulo externo."""
    import json
    ident = Path(archivo).stem + '-datos'
    nodo, = [n for n in HTML(html).raiz.todos('script') if n.attrs.get('id') == ident]
    assert nodo.attrs.get('type') == 'application/json'
    return json.loads(nodo.texto())

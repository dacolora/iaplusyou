"""Plantillas ya traducidas (spec 2026-09-26 §Pruebas): en su FUENTE no queda
texto visible en español fuera de _() — en ninguna rama de un {% if %} — ni
literales en español dentro de <script>. Cada tarea que traduce una plantilla
la agrega a PLANTILLAS_TRADUCIDAS."""
import os

import pytest

from tests.i18n_util import espanol_en_plantilla

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLAS_TRADUCIDAS = [
]


def test_la_deteccion_funciona(tmp_path):
    ruta = tmp_path / "x.html"
    ruta.write_text("<p>{{ _('Guardar') }}</p><p>Guardar cambios</p>"
                    "<script>var a = {{ _('Sí')|tojson }}; var b = '¿Seguro?'; // comentario en español</script>",
                    encoding="utf-8")
    assert espanol_en_plantilla(str(ruta)) == ["Guardar cambios", "'¿Seguro?'"]


@pytest.mark.parametrize("nombre", PLANTILLAS_TRADUCIDAS)
def test_plantilla_sin_espanol_suelto(nombre):
    hallazgos = espanol_en_plantilla(os.path.join(RAIZ, "templates", nombre))
    assert not hallazgos, f"{nombre}: texto en español fuera de _():\n" + "\n".join(hallazgos[:30])

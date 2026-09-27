"""Pruebas de los módulos del editor en el navegador (static/editor/*.js).
Corren con el runner que trae Node (`node --test`), sin npm ni node_modules;
donde no hay Node (el VPS) se saltan. Además se comparan con Python las
constantes que el navegador no puede recibir de la página (las que usan
las pruebas de Node)."""
import glob
import json
import os
import re
import shutil
import subprocess

import pytest

from final_edition import documento

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="sin Node no corren las pruebas de JS (el VPS no lo tiene)")
def test_modulos_del_editor_pasan_sus_pruebas():
    archivos = sorted(glob.glob(os.path.join(RAIZ, "tests", "js", "*.test.mjs")))
    assert archivos, "no hay pruebas en tests/js"
    r = subprocess.run([NODE, "--test", *archivos], cwd=RAIZ, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, (r.stdout[-6000:] + "\n" + r.stderr[-3000:])


def _constante_js(archivo, nombre):
    with open(os.path.join(RAIZ, "static", "editor", archivo), encoding="utf-8") as f:
        texto = f.read()
    m = re.search(rf"export const {nombre} = (.*?);\n", texto, re.S)
    assert m, f"{archivo} no exporta {nombre}"
    return json.loads(m.group(1))


def test_formatos_js_iguales_a_python():
    assert _constante_js("formatos.js", "FORMATOS") == {k: list(v) for k, v in documento.FORMATOS.items()}

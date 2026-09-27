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


def _generador():
    import importlib.util
    ruta = os.path.join(RAIZ, "tests", "fixtures", "generar_casos_editor.py")
    spec = importlib.util.spec_from_file_location("generar_casos_editor", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_casos_del_editor_al_dia():
    gen = _generador()
    for nombre, funcion in gen.ARCHIVOS.items():
        with open(os.path.join(RAIZ, "tests", "fixtures", nombre), encoding="utf-8") as f:
            assert f.read() == gen.texto(funcion), (
                f"{nombre} quedó viejo: correr `venv/bin/python3 tests/fixtures/generar_casos_editor.py`")


def test_ducking_de_mezcla_es_legible_por_el_navegador():
    # audio.js::parsearDucking lee "clave=valor:clave=valor" con estas cuatro claves.
    from final_edition import mezcla
    for cadena in (mezcla.DUCKING_VOZ_SOBRE_MUSICA, mezcla.DUCKING_VOZ_SOBRE_SONIDO):
        partes = dict(p.split("=") for p in cadena.split(":"))
        assert set(partes) == {"threshold", "ratio", "attack", "release"}
        assert all(float(v) > 0 for v in partes.values())

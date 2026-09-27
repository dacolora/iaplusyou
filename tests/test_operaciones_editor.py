"""Las operaciones de edición del navegador (static/editor/operaciones.js)
tienen que dejar documentos que Python acepta: se corren en Node y cada
resultado pasa por documento.validar y compilador.verificar_recortes."""
import copy
import json
import os
import shutil
import subprocess

import pytest

from final_edition import documento
from final_edition.motor import compilador

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
DURACIONES = {1: 8000, 2: 3000}


@pytest.mark.skipif(not NODE, reason="sin Node no corren las pruebas de JS (el VPS no lo tiene)")
def test_las_operaciones_del_navegador_dejan_documentos_validos():
    r = subprocess.run([NODE, "tests/js/salida_operaciones.mjs"], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-3000:]
    casos = json.loads(r.stdout)
    assert len(casos) >= 12
    for caso in casos:
        doc = documento.validar(caso["doc"])
        ids = [c["id"] for p in doc["pistas"] for c in p["clips"]]
        assert len(ids) == len(set(ids)), caso["nombre"]
        antes = json.dumps(doc["pistas"][0]["clips"], sort_keys=True)
        compilador.verificar_recortes(copy.deepcopy(doc), DURACIONES)          # nada pide material de más
        normal = compilador.verificar_recortes(copy.deepcopy(doc), DURACIONES)
        assert json.dumps(normal["pistas"][0]["clips"], sort_keys=True) == antes, (
            f"{caso['nombre']}: el navegador no normalizó las transiciones como el compilador")

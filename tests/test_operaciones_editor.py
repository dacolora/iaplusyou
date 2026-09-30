"""Las operaciones de edición del navegador (static/editor/operaciones.js)
tienen que dejar documentos que Python acepta: se corren en Node y cada
resultado pasa por documento.validar y compilador.verificar_recortes."""
import copy
import json
import os
import shutil
import subprocess

import pytest

from final_edition import documento, mezcla
from final_edition.motor import compilador

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
DURACIONES = {1: 8000, 2: 3000}


@pytest.mark.skipif(not NODE, reason="sin Node no corren las pruebas de JS (el VPS no lo tiene)")
def test_las_operaciones_del_navegador_dejan_documentos_validos():
    r = subprocess.run([NODE, "tests/js/salida_operaciones.mjs"], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-3000:]
    casos = json.loads(r.stdout)
    assert len(casos) >= 30   # capa 4a (13) + capa 4b: agregar/cortar/transición/editar/cambiar (21) + al_final_*
    assert sum(c["nombre"].startswith("al_final_") for c in casos) == 6 * 16   # cada velocidad, al final del archivo
    for caso in casos:
        doc = documento.validar(caso["doc"])
        ids = [c["id"] for p in doc["pistas"] for c in p["clips"]]
        assert len(ids) == len(set(ids)), caso["nombre"]
        duraciones = {int(k): v for k, v in (caso.get("duraciones") or DURACIONES).items()}
        antes = json.dumps(doc["pistas"][0]["clips"], sort_keys=True)
        try:
            normal = compilador.verificar_recortes(copy.deepcopy(doc), duraciones)   # nada pide material de más
        except ValueError as e:
            pytest.fail(f"{caso['nombre']}: {e}")
        assert json.dumps(normal["pistas"][0]["clips"], sort_keys=True) == antes, (
            f"{caso['nombre']}: el navegador no normalizó las transiciones como el compilador")
        # lo que se agrega (y, capa 4c, lo que se mueve, alarga o duplica)
        # nunca alarga el video: termina con la principal
        if caso["nombre"].startswith(("agregar_", "no_alarga_")):
            fin_principal = sum(c["duracion_ms"] for c in doc["pistas"][0]["clips"])
            assert documento.duracion_ms(doc) == fin_principal, f"{caso['nombre']}: el video quedó más largo"
        # capa 4c: los fundidos de cada audio caben en su clip (si no, el
        # render pide `afade ... st=<negativo>` y ffmpeg falla)
        for p in doc["pistas"]:
            if p["tipo"] != "audio":
                continue
            for c in p["clips"]:
                au = c.get("audio") or {}
                assert au.get("fundido_entrada_ms", 0) + au.get("fundido_salida_ms", 0) <= c["duracion_ms"], (
                    f"{caso['nombre']}: los fundidos de {c['id']} no caben en sus {c['duracion_ms']} ms")
        # arreglo 4: una entrada animada siempre lleva su duración (sin ella ni
        # la vista previa ni el render la aplican)
        for p in doc["pistas"]:
            for c in p["clips"]:
                an = c.get("animacion") or {}
                if an.get("entrada") not in (None, "ninguna"):
                    assert an.get("duracion_ms", 0) > 0, f"{caso['nombre']}: {c['id']} anima sin duración"
        # la mezcla que deja el panel de propiedades es una que el render conoce
        mz = doc.get("mezcla") or {}
        mezcla.volumenes_para(mz.get("preset"), mz.get("volumenes"))

"""Las operaciones de edición del navegador (static/editor/operaciones.js)
tienen que dejar documentos que Python acepta: se corren en Node y cada
resultado pasa por documento.validar y compilador.verificar_recortes."""
import copy
import json
import os
import shutil
import subprocess

import pytest

from final_edition import documento, mezcla, subtitulos_fuente
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
        # lo que se agrega (y, capa 4c, lo que se mueve, alarga o duplica;
        # capa 5b, lo que sigue a su clip o se recorta por D10.5) nunca
        # alarga el video: termina con la principal
        if caso["nombre"].startswith(("agregar_", "no_alarga_", "vinculado_")):
            fin_principal = sum(c["duracion_ms"] for c in doc["pistas"][0]["clips"])
            assert documento.duracion_ms(doc) == fin_principal, f"{caso['nombre']}: el video quedó más largo"
        # capa 5b (D10.6): una capa movida que pisaba a otra de su misma fila
        # se reparte a una fila libre — ningún clip de una pista de texto
        # pisa a otro de su misma pista.
        if caso["nombre"].startswith("vinculado_"):
            for p in doc["pistas"]:
                if p["tipo"] != "texto":
                    continue
                ordenados = sorted(p["clips"], key=lambda c: c["inicio_ms"])
                for a, b in zip(ordenados, ordenados[1:]):
                    assert a["inicio_ms"] + a["duracion_ms"] <= b["inicio_ms"], (
                        f"{caso['nombre']}: {a['id']} pisa a {b['id']} en la pista {p['id']}")
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
        # capa 5b (D1): una foto no tiene tiempo de fuente ni velocidad, y
        # nunca suena — ningún clip de p_sonido usa su material.
        fotos_material = set()
        for p in doc["pistas"]:
            for c in p["clips"]:
                if not c.get("foto"):
                    continue
                fotos_material.add(c["material_id"])
                assert c["recorte"] == {"desde_ms": 0, "hasta_ms": c["duracion_ms"]}, (
                    f"{caso['nombre']}: {c['id']} es una foto con recorte {c['recorte']}")
                assert c["velocidad"] == 1, f"{caso['nombre']}: {c['id']} es una foto a velocidad {c['velocidad']}"
        if fotos_material:
            sonido = next((p for p in doc["pistas"] if p["id"] == "p_sonido"), None)
            for c in (sonido or {}).get("clips", []):
                assert c["material_id"] not in fotos_material, (
                    f"{caso['nombre']}: {c['id']} en p_sonido usa el material de una foto")
        # capa 5b (D9): en los casos solape_*, la duración total queda en la
        # de antes menos lo que la transición tiene cedido ahora mismo (o
        # igual si se quitó — nada queda cedido).
        if caso["nombre"].startswith("solape_") and "duracion_antes" in caso:
            principal = documento.pista_principal(doc)
            cedido = sum(
                c["transicion"]["duracion_ms"] for c in principal["clips"]
                if c.get("transicion") and c["transicion"].get("modo") == "solape")
            assert documento.duracion_ms(doc) == caso["duracion_antes"] - cedido, (
                f"{caso['nombre']}: duración total {documento.duracion_ms(doc)}, "
                f"esperada {caso['duracion_antes']} - {cedido} cedidos")
        # la mezcla que deja el panel de propiedades es una que el render conoce
        mz = doc.get("mezcla") or {}
        mezcla.volumenes_para(mz.get("preset"), mz.get("volumenes"))


@pytest.mark.skipif(not NODE, reason="sin Node no corren las pruebas de JS (el VPS no lo tiene)")
def test_adoptar_voz_al_resolver_da_las_mismas_palabras_que_guardaba():
    """D14: el documento `adoptar_voz` (docConVozYPalabras adoptado por
    operaciones.adoptarVozComoFuente) no tocó `subtitulos.palabras` — ese
    respaldo de legado sigue como estaba, para `es_CO` —; lo que cambia es
    que ahora hay una fuente «voz» para "es". Al resolver ese destino y
    derivar con subtitulos_fuente.aplicar (las mismas palabras que trae el
    material, en Python con claves enteras) el resultado es ESE MISMO
    respaldo: adoptar no cambia lo que se ve."""
    r = subprocess.run([NODE, "tests/js/salida_operaciones.mjs"], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-3000:]
    casos = {c["nombre"]: c["doc"] for c in json.loads(r.stdout)}
    crudo = casos["adoptar_voz"]
    esperado = crudo["subtitulos"]["palabras"]["es_CO"]
    doc = documento.validar(crudo)
    assert doc["subtitulos"]["fuentes"] == {"es": [{"tipo": "voz"}]}
    resuelto = documento.resolver(doc, "es", "CO")
    final = subtitulos_fuente.aplicar(resuelto, {2: esperado})
    assert final["subtitulos"]["palabras"] == esperado

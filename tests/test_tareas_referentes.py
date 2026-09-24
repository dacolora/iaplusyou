"""tareas.referentes: importación de copycoders por fases, sin red (costuras monkeypatcheadas)."""
import os

import pytest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "copycoders_swipe.html")


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    from referentes import copycoders, imagenes
    from tareas import referentes as tr
    encolados = []
    with open(FIXTURE, encoding="utf-8") as f:
        html = f.read()
    monkeypatch.setattr(copycoders, "descargar_html", lambda url: html)

    def guardar_falso(aid, url, carpeta):
        if aid == "555":
            raise imagenes.ImagenInvalida("no es imagen")
        return f"https://r2/referentes/{aid}.jpg"
    monkeypatch.setattr(imagenes, "guardar_en_r2", guardar_falso)
    monkeypatch.setattr(copycoders, "traducir_firmas", lambda pares: ({rid: f"ES {firma}" for rid, firma in pares}, 100, 40))
    monkeypatch.setattr(copycoders, "describir_familias", lambda fams: ({n: f"Desc {n}" for n, _ in fams}, 30, 10))
    monkeypatch.setattr(tr, "CARPETA", str(tmp_path))
    monkeypatch.setattr(tr.cola, "encolar", lambda tipo, payload, **kw: encolados.append({"tipo": tipo, "payload": payload, **kw}) or 1)
    monkeypatch.setattr(tr.cola, "reportar", lambda *a, **k: None)
    gastos = []
    monkeypatch.setattr(tr.gastos, "registrar_seguro", lambda *a, **k: gastos.append((a, k)))
    return {"tr": tr, "encolados": encolados, "gastos": gastos}


def _tarea(payload, tid=5):
    return {"id": tid, "job_id": "referentes:importar:copycoders", "payload": payload}


def test_encolar_crea_barrido(entorno, monkeypatch):
    from referentes import datos
    tr = entorno["tr"]
    llamadas = []
    monkeypatch.setattr(tr.trabajos, "encolar", lambda job_id, tipo, payload, **kw: llamadas.append((job_id, tipo, payload, kw)) or True)
    assert tr.encolar_importar_copycoders(pedido_por="admin") is True
    job_id, tipo, payload, kw = llamadas[0]
    assert job_id == tr.JOB_IMPORTAR and tipo == "referentes_importar_copycoders" and payload["fase"] == "anuncios"
    assert kw["max_intentos"] == 1 and payload["barrido_id"] == datos.barridos(None, "copycoders")[0]["id"]


def test_fase_anuncios(entorno):
    from referentes import datos
    tr = entorno["tr"]
    bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
    msg = tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "anuncios"}))
    b = datos.barrido(bid)
    assert b["traidos"] == 3 and b["nuevos"] == 3 and b["estado"] == "guardando" and b["tarea_id"] == 5
    assert datos.contar_imagenes("copycoders") == {"ok": 0, "pendiente": 3, "error": 0}
    assert {f["nombre"] for f in datos.familias()} == {"Price Slash Hero", "Self-Diagnosis Chart", "Content Camouflage"}
    assert entorno["encolados"][-1]["payload"]["fase"] == "imagenes" and entorno["encolados"][-1]["job_id"].endswith("__cont")
    assert "3" in msg


def test_fases_imagenes_y_traducir(entorno):
    from referentes import datos
    tr = entorno["tr"]
    bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "anuncios"}))
    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "imagenes"}, tid=6))
    assert datos.contar_imagenes("copycoders") == {"ok": 2, "pendiente": 0, "error": 1}
    assert entorno["encolados"][-1]["payload"]["fase"] == "traducir"
    antes = len(entorno["encolados"])
    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "traducir"}, tid=7))
    b = datos.barrido(bid)
    assert b["estado"] == "parcial" and "1" in b["aviso"] and b["con_imagen"] == 2
    lista = datos.listar("acme")
    assert lista["total"] == 2 and all(r["firma"].startswith("ES ") for r in lista["items"])
    assert datos.familias()[0]["descripcion"].startswith("Desc ")
    (args, kw), = [g for g in entorno["gastos"] if "traduccion" in g[0][3]][:1]
    assert args[0] == "_creatv" and args[1] == "otro" and kw["proveedor"] == "anthropic"
    assert datos.sin_traducir() == [] and len(entorno["encolados"]) == antes     # todo traducido: no se re-encola


def test_fase_anuncios_falla_deja_error(entorno, monkeypatch):
    from referentes import copycoders, datos
    tr = entorno["tr"]
    monkeypatch.setattr(copycoders, "descargar_html", lambda url: "<html>nada</html>")
    bid = datos.crear_barrido(None, "copycoders", {"url": "https://x"}, 0)
    with pytest.raises(copycoders.FormatoInvalido):
        tr.ejecutar_importar(_tarea({"url": "https://x", "barrido_id": bid, "fase": "anuncios"}))
    b = datos.barrido(bid)
    assert b["estado"] == "error" and "const DATA" in b["aviso"] and entorno["encolados"] == []


def test_reimportar_actualiza_sin_duplicar(entorno):
    from referentes import datos
    tr = entorno["tr"]
    for _ in range(2):
        bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
        tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "anuncios"}))
    b = datos.barrido(bid)
    assert b["traidos"] == 3 and b["nuevos"] == 0 and datos.contar_imagenes("copycoders")["pendiente"] == 3

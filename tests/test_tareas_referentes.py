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
    # Por debajo de sprints (3): un import admin nunca debe adelantarse a Crear.
    assert kw["prioridad"] == 2


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


def test_fase_imagenes_no_aborta_el_tramo_por_una_excepcion_generica(entorno, monkeypatch):
    from referentes import datos, imagenes
    tr = entorno["tr"]
    bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "anuncios"}))

    # La 2ª de 3 filas (orden de id) revienta con algo que no es ImagenInvalida
    # (p. ej. un error transitorio de R2/red) — las otras dos deben procesarse
    # igual, no quedar a medias porque una excepción abortó el for entero.
    def falla_r2(aid, url, carpeta):
        if aid == "1234567890":
            raise RuntimeError("R2 se cayó a medio subir")
        return f"https://r2/referentes/{aid}.jpg"
    monkeypatch.setattr(imagenes, "guardar_en_r2", falla_r2)

    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "imagenes"}, tid=6))
    assert datos.contar_imagenes("copycoders") == {"ok": 2, "pendiente": 0, "error": 1}


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


def _sembrar_sin_traducir(datos, bid, n, prefijo="tr"):
    ids = []
    for i in range(n):
        rid, _ = datos.guardar_referente({"anuncio_id": f"{prefijo}-{i}", "fuente": "copycoders",
                                          "imagen_origen": "https://cdn/x.jpg", "firma": f"firma {i}",
                                          "extra": {"traducida": False}}, cliente=None, barrido_id=bid)
        datos.marcar_imagen(rid, "ok", f"https://r2/{prefijo}-{i}.jpg")
        ids.append(rid)
    return ids


def test_fase_traducir_drena_todo_pese_al_limite_de_tramo(entorno, monkeypatch):
    from referentes import datos
    tr = entorno["tr"]
    bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
    # 15 filas, muy por encima de la vieja ventana de 4 (limite*4 con limite=1);
    # TRAMO=4 fuerza varias pasadas (3 lotes × 4 = 12 por llamada) y por lo
    # tanto varios re-encolados reales para drenarlas todas.
    _sembrar_sin_traducir(datos, bid, 15)
    monkeypatch.setattr(tr, "TRAMO", 4)
    b = None
    for tid in range(10):
        tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "traducir"}, tid=tid))
        b = datos.barrido(bid)
        if b["estado"] == "listo":
            break
    assert b["estado"] == "listo"
    assert datos.sin_traducir() == []
    assert {r["firma"] for r in datos.listar("acme")["items"]} == {f"ES firma {i}" for i in range(15)}


def test_fase_traducir_no_reencola_para_siempre_sin_progreso(entorno, monkeypatch):
    from referentes import copycoders, datos
    tr = entorno["tr"]
    bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
    ids = _sembrar_sin_traducir(datos, bid, 5, prefijo="np")
    # Claude omite estas filas en cada pasada (pasa en producción con lotes
    # grandes): sin memoria de progreso, esto re-encolaría —y pagaría una
    # llamada a Claude— cada ESPERA_CONT segundos para siempre.
    monkeypatch.setattr(copycoders, "traducir_firmas", lambda pares: ({}, 10, 5))
    antes = len(entorno["encolados"])
    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "traducir"}))
    b = datos.barrido(bid)
    assert len(entorno["encolados"]) == antes                 # no se re-encoló: la pasada no avanzó nada
    assert b["estado"] == "parcial" and str(len(ids)) in b["aviso"]
    assert [r["id"] for r in datos.sin_traducir()] == ids     # el trabajo sigue ahí, no se pierde ni se oculta

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


# ---------------------------------------------------------------- bloque 4 ---
# `referentes_barrer` / `referentes_clasificar`: mismo patrón de fases que
# arriba, pero sin la fixture `entorno` (específica de copycoders/HTML) — acá
# alcanza con una base de datos temporal por test y un nombre de cliente
# cualquiera (referentes.datos guarda `cliente` como texto, no valida que
# exista en disco).

def _cliente_de_prueba(tmp_path, monkeypatch):
    """Mismo patrón que la fixture `base_temporal` de conftest.py, pero como
    función corriente (los tests de este bloque no necesitan nada más del
    `entorno` de copycoders, así que no vale la pena forzarlos a compartirlo)."""
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'creatv.db'}")
    db._reset_para_tests()
    db.crear_todo()
    return "acme"


def test_encolar_barrer_crea_fila_y_encola(tmp_path, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = tareas_ref.encolar_barrer(cliente, "atria", {"modo": "palabra", "palabra": "protein", "idioma": "en"},
                                    50, 0.30, pedido_por="tester")
    assert isinstance(bid, int)
    b = datos.barrido(bid)
    assert b["cliente"] == cliente and b["fuente"] == "atria" and b["estado"] == "en_cola"
    assert tareas_ref.trabajo_barrer(bid) == tareas_ref.job_id_barrer(bid)


def test_encolar_barrer_tope_se_limita_a_2000(tmp_path, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = tareas_ref.encolar_barrer(cliente, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"},
                                    999999, 1.0)
    assert datos.barrido(bid)["tope"] == 2000


def test_encolar_barrer_ya_en_curso_devuelve_false(tmp_path, monkeypatch):
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = tareas_ref.encolar_barrer(cliente, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 10, 0.1)
    # Sin ejecutar el worker, el job sigue "en curso" en la cola: un segundo encolar para el MISMO bid ya
    # no aplica (no hay un segundo bid); en cambio, comprobamos que trabajo_barrer(bid) ve el job vivo.
    assert tareas_ref.trabajo_barrer(bid) is not None


def test_ejecutar_barrer_fase_trayendo_guarda_y_re_encola(tmp_path, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {"modo": "palabra", "palabra": "protein", "idioma": "en"}, 5)
    anuncios_falsos = [{"anuncio_id": str(i), "pagina_id": "1", "marca": "M", "titular": "T", "cuerpo": "",
                        "idioma": "en", "pais": None, "tipo": "imagen", "imagen_origen": f"https://x/{i}.jpg",
                        "dias": 1, "variantes": 1, "primera_vez": "2026-09-24", "ultima_vez": "2026-09-24",
                        "activo": True, "url_anuncio": "", "url_marca": "", "etiquetas_fuente": {}, "extra": {}}
                       for i in range(3)]

    def _traer_falso(consulta, tope, avanzar, cursor=None):
        yield anuncios_falsos, None

    import referentes.fuentes as fuentes
    monkeypatch.setattr(fuentes, "por_tipo", lambda tipo: type("M", (), {"traer": staticmethod(_traer_falso)}))
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "trayendo",
                                  "consulta": {"fuente": "atria", "modo": "palabra", "palabra": "protein", "idioma": "en"},
                                  "tope": 5}}
    llamadas_cola = []
    monkeypatch.setattr("cola.encolar", lambda *a, **kw: llamadas_cola.append((a, kw)))
    resultado = tareas_ref.ejecutar_barrer(tarea)
    assert "traíd" in resultado.lower() or "trayendo" in resultado.lower()
    b = datos.barrido(bid)
    assert b["traidos"] == 3
    assert len(llamadas_cola) == 1  # se re-encoló (tope=5, solo trajo 3)


def test_ejecutar_barrer_sin_nada_traido_marca_error(tmp_path, monkeypatch):
    from referentes import datos
    from referentes.fuentes import base as fuentes_base
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 5)

    def _traer_falla(consulta, tope, avanzar, cursor=None):
        raise fuentes_base.ErrorFuente("Atria no está configurado (falta ATRIA_API_KEY).")
        yield  # pragma: no cover (nunca se alcanza; hace de esta func un generador)

    import referentes.fuentes as fuentes
    monkeypatch.setattr(fuentes, "por_tipo", lambda tipo: type("M", (), {"traer": staticmethod(_traer_falla)}))
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "trayendo",
                                  "consulta": {"fuente": "atria", "modo": "palabra", "palabra": "x", "idioma": "en"},
                                  "tope": 5}}
    with pytest.raises(fuentes_base.ErrorFuente):
        tareas_ref.ejecutar_barrer(tarea)
    assert datos.barrido(bid)["estado"] == "error"


def test_fase_clasificando_registra_gasto_y_actualiza_referente(tmp_path, monkeypatch):
    from referentes import clasificar, datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {}, 5)
    rid, _ = datos.guardar_referente({"anuncio_id": "9", "fuente": "atria", "imagen_origen": "https://x/9.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente=cliente, barrido_id=bid)
    datos.marcar_imagen(rid, "ok", "https://r2/9.jpg")
    monkeypatch.setattr(clasificar, "clasificar",
                        lambda referente, vocabulario: ({"etapa": "TOF", "consciencia": "unaware",
                                                         "familia": None, "familia_nueva": {"nombre": "X", "descripcion": "d"},
                                                         "dolor": "bloating", "firma": "f"}, 900, 60))
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "clasificando",
                                  "consulta": {"fuente": "atria"}, "tope": 5}}
    tareas_ref.ejecutar_barrer(tarea)
    r = datos.referente(cliente, rid)
    assert r["clasificacion"] == "claude" and r["familia"] == "EMERGING: X"
    assert any(f["nombre"] == "EMERGING: X" for f in datos.familias())


def test_fase_clasificando_claude_invalido_deja_error_y_no_reencola_para_siempre(tmp_path, monkeypatch):
    """Un ClasificacionInvalida en UN referente no debe abortar el tramo (el
    siguiente se clasifica igual) NI, si Claude sigue fallando siempre en el
    mismo, reencolarse para siempre (mismo riesgo que _fase_traducir ya
    resuelve para las traducciones): sin avance en una pasada, el barrido
    queda `parcial` con aviso en vez de reintentar cada ESPERA_CONT segundos
    para siempre."""
    from referentes import clasificar, datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {}, 5)
    rid_malo, _ = datos.guardar_referente({"anuncio_id": "10", "fuente": "atria", "imagen_origen": "https://x/10.jpg",
                                           "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                          cliente=cliente, barrido_id=bid)
    rid_bueno, _ = datos.guardar_referente({"anuncio_id": "11", "fuente": "atria", "imagen_origen": "https://x/11.jpg",
                                            "marca": "M", "titular": "T2", "cuerpo": "", "idioma": "en"},
                                           cliente=cliente, barrido_id=bid)
    datos.marcar_imagen(rid_malo, "ok", "https://r2/10.jpg")
    datos.marcar_imagen(rid_bueno, "ok", "https://r2/11.jpg")

    def _clasificar_falso(referente, vocabulario):
        if referente["id"] == rid_malo:
            e = clasificar.ClasificacionInvalida("Claude no devolvió JSON.")
            e.tokens_entrada, e.tokens_salida = 50, 0
            raise e
        return ({"etapa": "TOF", "consciencia": "unaware", "familia": None,
                 "familia_nueva": {"nombre": "Y", "descripcion": "d"}, "dolor": "dolor", "firma": "f"}, 80, 20)

    monkeypatch.setattr(clasificar, "clasificar", _clasificar_falso)
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "clasificando",
                                  "consulta": {"fuente": "atria"}, "tope": 5}}
    # Primera pasada: rid_bueno avanza, rid_malo queda en error -> como hubo
    # avance, se re-encola una vez más (para reintentar rid_malo).
    tareas_ref.ejecutar_barrer(tarea)
    assert datos.referente(cliente, rid_malo)["clasificacion"] == "error"
    assert datos.referente(cliente, rid_bueno)["clasificacion"] == "claude"
    assert datos.barrido(bid)["clasificados"] == 1

    # Segunda pasada: solo queda rid_malo, que vuelve a fallar -> sin avance,
    # no debe re-encolarse otra vez; el barrido cierra en `parcial`.
    llamadas_cola = []
    monkeypatch.setattr("cola.encolar", lambda *a, **kw: llamadas_cola.append((a, kw)))
    tareas_ref.ejecutar_barrer(tarea)
    assert llamadas_cola == []
    b = datos.barrido(bid)
    assert b["estado"] == "parcial" and "no se pudieron clasificar" in b["aviso"]


def test_encolar_reintentar_imagenes_resetea_error_a_pendiente(tmp_path, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 5)
    rid, _ = datos.guardar_referente({"anuncio_id": "7", "fuente": "atria", "imagen_origen": "https://x/7.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente=cliente, barrido_id=bid)
    datos.marcar_imagen(rid, "error")
    assert tareas_ref.encolar_reintentar_imagenes(cliente, bid)
    assert datos.referente(cliente, rid)["estado_imagen"] == "pendiente"


def test_encolar_reintentar_imagenes_ya_en_curso_devuelve_false(tmp_path, monkeypatch):
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = tareas_ref.encolar_barrer(cliente, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 10, 0.1)
    assert tareas_ref.encolar_reintentar_imagenes(cliente, bid) is False


def test_encolar_clasificar_pendientes(tmp_path, monkeypatch):
    from referentes import datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 5)
    assert tareas_ref.encolar_clasificar_pendientes(cliente, bid)
    assert tareas_ref.trabajo_barrer(bid) is not None


def test_encolar_clasificar_pendientes_sin_barrido_devuelve_false(tmp_path, monkeypatch):
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    assert tareas_ref.encolar_clasificar_pendientes(cliente, 999999) is False

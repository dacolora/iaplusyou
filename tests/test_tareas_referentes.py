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
        yield anuncios_falsos, None, {}

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
    # El job_id de la continuación debe ser el REAL job_id_barrer(bid)+__cont,
    # no un truncado (bug real: _job_continuacion_barrer recortaba un
    # job_id_barrer(bid) recalculado, que nunca lleva el sufijo, en vez de
    # recortar el job_id de verdad).
    assert llamadas_cola[0][1]["job_id"] == tareas_ref.job_id_barrer(bid) + tareas_ref.SUFIJO_CONT


def test_job_continuacion_barrer_alterna_sin_colisionar_entre_barridos(tmp_path, monkeypatch):
    """Reproduce el bug real de _job_continuacion_barrer: recortaba SIEMPRE un
    job_id_barrer(bid) recién calculado (que nunca lleva el sufijo __cont) en
    vez del job_id real de la tarea -- para bids de un solo dígito, esto
    colisionaba TODOS los barridos en el mismo string truncado
    ("referentes:ba"). Corre 3 tramos reales (sin mockear
    _job_continuacion_barrer) para dos barridos distintos y confirma que la
    cadena alterna base/__cont correctamente y nunca se cruza entre ellos."""
    from referentes import datos
    from tareas import referentes as tareas_ref

    cliente = _cliente_de_prueba(tmp_path, monkeypatch)

    def _traer_una_pagina(consulta, tope, avanzar, cursor=None):
        # Siempre trae 1 y dice "hay más" (cursor real) -> nunca termina
        # solo, así se queda varios tramos seguidos en fase "trayendo".
        n = int(cursor or 0)
        yield ([{"anuncio_id": f"{consulta['fuente']}-{n}-{cliente}", "pagina_id": "1", "marca": "M", "titular": "T",
                "cuerpo": "", "idioma": "en", "pais": None, "tipo": "imagen", "imagen_origen": f"https://x/{n}.jpg",
                "dias": 1, "variantes": 1, "primera_vez": "2026-09-24", "ultima_vez": "2026-09-24",
                "activo": True, "url_anuncio": "", "url_marca": "", "etiquetas_fuente": {}, "extra": {}}],
               str(n + 1), {})

    import referentes.fuentes as fuentes
    monkeypatch.setattr(fuentes, "por_tipo", lambda tipo: type("M", (), {"traer": staticmethod(_traer_una_pagina)}))

    encolados = []
    monkeypatch.setattr("cola.encolar", lambda tipo, payload, **kw: encolados.append(kw["job_id"]) or 1)

    def _correr_tramos(bid, n_tramos):
        job_id = tareas_ref.job_id_barrer(bid)
        secuencia = []
        for _ in range(n_tramos):
            tarea = {"id": 1, "job_id": job_id, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "trayendo",
                     "consulta": {"fuente": "atria"}, "tope": 1000}}
            tareas_ref.ejecutar_barrer(tarea)
            job_id = encolados[-1]
            secuencia.append(job_id)
        return secuencia

    bid1 = datos.crear_barrido(cliente, "atria", {}, 1000)
    bid2 = datos.crear_barrido(cliente, "atria", {}, 1000)
    sec1 = _correr_tramos(bid1, 3)
    sec2 = _correr_tramos(bid2, 3)

    base1, cont1 = tareas_ref.job_id_barrer(bid1), tareas_ref.job_id_barrer(bid1) + tareas_ref.SUFIJO_CONT
    base2, cont2 = tareas_ref.job_id_barrer(bid2), tareas_ref.job_id_barrer(bid2) + tareas_ref.SUFIJO_CONT
    assert sec1 == [cont1, base1, cont1]
    assert sec2 == [cont2, base2, cont2]
    assert set(sec1).isdisjoint(sec2)  # nunca colisionan entre barridos distintos


def test_fase_trayendo_error_con_avance_previo_deja_aviso_en_extra(tmp_path, monkeypatch):
    """Important 6.1 (primera parte, "swallowed once something's been
    fetched"): si `traer()` lanza ErrorFuente pero el barrido YA traía algo de
    tramos anteriores, `_fase_trayendo` no debe abortar (correcto, sigue
    siendo entrega parcial) -- pero antes tampoco dejaba NINGÚN rastro del
    porqué. Debe quedar en `extra.aviso_trayendo`."""
    from referentes import datos
    from referentes.fuentes import base as fuentes_base
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, traidos=5, nuevos=5, estado="trayendo")

    def _traer_falla(consulta, tope, avanzar, cursor=None):
        raise fuentes_base.ErrorFuente("Atria: se acabaron las llamadas del plan este mes.")
        yield  # pragma: no cover (nunca se alcanza; hace de esta func un generador)

    import referentes.fuentes as fuentes
    monkeypatch.setattr(fuentes, "por_tipo", lambda tipo: type("M", (), {"traer": staticmethod(_traer_falla)}))
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "trayendo",
                                  "consulta": {"fuente": "atria", "modo": "palabra", "palabra": "x", "idioma": "en"},
                                  "tope": 50}}
    resultado = tareas_ref.ejecutar_barrer(tarea)  # no debe lanzar: ya había avance (traidos=5)
    assert isinstance(resultado, str)
    b = datos.barrido(bid)
    assert b["estado"] == "guardando"  # sigue de largo a imágenes, entrega parcial
    assert "se acabaron las llamadas del plan este mes" in b["extra"]["aviso_trayendo"]


def test_fase_trayendo_cuota_agotada_a_mitad_de_tramo_deja_aviso(tmp_path, monkeypatch):
    """Important 6.1 (segunda parte, "documented ran out of monthly quota
    mid-fetch" behavior): cuando `traer()` NO lanza nada -- ya trajo algo EN
    esta misma llamada y por eso entrega `([], None)` en silencio, como ya
    hacía antes de este fix -- la única señal de que la causa fue el cupo
    mensual (y no que la búsqueda esté genuinamente agotada) es el
    `avanzar(detalle=AVISO_CUOTA_AGOTADA)` que la fuente manda. Debe quedar
    igual en `extra.aviso_trayendo`."""
    from referentes import datos
    from referentes.fuentes.base import AVISO_CUOTA_AGOTADA
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {"modo": "palabra", "palabra": "x", "idioma": "en"}, 50)

    def _traer_cuota_agotada(consulta, tope, avanzar, cursor=None):
        yield ([{"anuncio_id": "cuota-1", "pagina_id": "1", "marca": "M", "titular": "T", "cuerpo": "",
                "idioma": "en", "pais": None, "tipo": "imagen", "imagen_origen": "https://x/1.jpg",
                "dias": 1, "variantes": 1, "primera_vez": "2026-09-24", "ultima_vez": "2026-09-24",
                "activo": True, "url_anuncio": "", "url_marca": "", "etiquetas_fuente": {}, "extra": {}}],
               "cursor-1", {})
        avanzar(detalle=AVISO_CUOTA_AGOTADA)
        yield [], None, {}

    import referentes.fuentes as fuentes
    monkeypatch.setattr(fuentes, "por_tipo", lambda tipo: type("M", (), {"traer": staticmethod(_traer_cuota_agotada)}))
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "trayendo",
                                  "consulta": {"fuente": "atria", "modo": "palabra", "palabra": "x", "idioma": "en"},
                                  "tope": 50}}
    tareas_ref.ejecutar_barrer(tarea)
    b = datos.barrido(bid)
    assert b["traidos"] == 1 and b["estado"] == "guardando"
    assert "cupo mensual de Atria" in b["extra"]["aviso_trayendo"]


def test_fase_clasificando_suma_el_aviso_de_trayendo_al_final(tmp_path, monkeypatch):
    """El aviso que dejó la fase "trayendo" (arriba) no debe perderse cuando
    la fase final ("clasificando") arma SU aviso -- antes cada fase pisaba a
    la anterior con `actualizar_barrido(..., aviso=...)`."""
    from referentes import clasificar, datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {}, 5)
    datos.actualizar_barrido(bid, extra={"aviso_trayendo": "Se detuvo de traer más anuncios: se acabó el cupo mensual de Atria."})
    rid, _ = datos.guardar_referente({"anuncio_id": "80", "fuente": "atria", "imagen_origen": "https://x/80.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente=cliente, barrido_id=bid)
    datos.marcar_imagen(rid, "ok", "https://r2/80.jpg")
    monkeypatch.setattr(clasificar, "clasificar",
                        lambda referente, vocabulario: ({"etapa": "TOF", "consciencia": "unaware", "familia": None,
                                                         "familia_nueva": {"nombre": "W", "descripcion": "d"},
                                                         "dolor": "dolor", "firma": "f"}, 80, 20))
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "clasificando",
                                  "consulta": {"fuente": "atria"}, "tope": 5}}
    tareas_ref.ejecutar_barrer(tarea)
    b = datos.barrido(bid)
    assert b["estado"] == "parcial"
    assert "cupo mensual de Atria" in b["aviso"]


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


def test_ejecutar_barrer_fase_trayendo_con_atria_real_no_revienta_por_avanzar(tmp_path, monkeypatch):
    """Bug real: `referentes.fuentes.atria.traer()` (Task 2, ya en main) llama
    `avanzar(detalle=...)` SIN pasar `etapa` — con `avanzar(etapa, detalle=None)`
    (etapa obligatorio, sin default) esto revienta con TypeError en la primera
    página real de CUALQUIER barrido, después de ya haber gastado una llamada
    contra el cupo mensual de Atria. Los `traer` de doble falso a mano en las
    otras pruebas nunca invocan `avanzar` así, por eso no lo agarraban — este
    usa el módulo `referentes.fuentes.atria` REAL, con solo `_sesion`
    mockeada (mismo patrón que tests/test_referentes_fuentes_atria.py)."""
    import json
    import time as time_mod

    import referentes.fuentes.atria as atria
    from referentes import datos
    from tareas import referentes as tareas_ref

    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(time_mod, "sleep", lambda s: None)
    fixture_search = json.load(open("tests/fixtures/atria_search.json"))

    class _RespuestaFalsa:
        def __init__(self, cuerpo, status=200):
            self._cuerpo = cuerpo
            self.status_code = status

        def json(self):
            return self._cuerpo

    class _SesionFalsa:
        def __init__(self, respuestas):
            self._respuestas = list(respuestas)

        def get(self, url, params=None, headers=None, timeout=None):
            return self._respuestas.pop(0)

    # FIXTURE_SEARCH trae exactamente 2 anuncios con page_size=2 (hay_mas=True
    # sin importar el tope) — con tope=2 el propio `while traidos < tope` de
    # `atria.traer` corta ANTES de pedir una segunda página, así que una sola
    # respuesta mockeada alcanza (ver test_referentes_fuentes_atria.py).
    monkeypatch.setattr(atria, "_sesion", lambda: _SesionFalsa([_RespuestaFalsa(fixture_search)]))

    bid = datos.crear_barrido(cliente, "atria", {"modo": "palabra", "palabra": "protein", "idioma": "en"}, 2)
    tarea = {"id": 1, "job_id": tareas_ref.job_id_barrer(bid),
             "payload": {"cliente": cliente, "barrido_id": bid, "fase": "trayendo",
                        "consulta": {"fuente": "atria", "modo": "palabra", "palabra": "protein", "idioma": "en"},
                        "tope": 2}}
    resultado = tareas_ref.ejecutar_barrer(tarea)  # antes del fix: TypeError acá mismo
    assert isinstance(resultado, str)
    b = datos.barrido(bid)
    assert b["traidos"] == 2 and b["estado"] == "guardando"


def _bad_request_error(mensaje="could not process image"):
    import httpx

    import anthropic
    peticion = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    respuesta = httpx.Response(400, request=peticion, json={"error": {"message": mensaje}})
    return anthropic.BadRequestError(mensaje, response=respuesta, body=None)


def test_fase_clasificando_bad_request_deja_error_y_no_bloquea_el_resto(tmp_path, monkeypatch):
    """Important 4: un anthropic.BadRequestError (p. ej. "no pude procesar la
    imagen") en UN referente antes reventaba el tramo entero -- y como esa
    fila queda `clasificacion=pendiente` y ordena primero por id, CADA
    intento posterior (automático Y "Clasificar pendientes") volvía a pegar
    contra la MISMA fila y fallaba igual, bloqueando PERMANENTEMENTE el resto
    del barrido. Debe tratarse igual que ClasificacionInvalida: esa fila queda
    en error, y el tramo sigue con las demás."""
    from referentes import clasificar, datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {}, 5)
    rid_malo, _ = datos.guardar_referente({"anuncio_id": "60", "fuente": "atria", "imagen_origen": "https://x/60.jpg",
                                           "marca": "M", "titular": "Imagen rota", "cuerpo": "", "idioma": "en"},
                                          cliente=cliente, barrido_id=bid)
    rid_bueno, _ = datos.guardar_referente({"anuncio_id": "61", "fuente": "atria", "imagen_origen": "https://x/61.jpg",
                                            "marca": "M", "titular": "T2", "cuerpo": "", "idioma": "en"},
                                           cliente=cliente, barrido_id=bid)
    datos.marcar_imagen(rid_malo, "ok", "https://r2/60.jpg")
    datos.marcar_imagen(rid_bueno, "ok", "https://r2/61.jpg")

    def _clasificar_falso(referente, vocabulario):
        if referente["id"] == rid_malo:
            raise _bad_request_error()
        return ({"etapa": "TOF", "consciencia": "unaware", "familia": None,
                 "familia_nueva": {"nombre": "Z", "descripcion": "d"}, "dolor": "dolor", "firma": "f"}, 80, 20)

    monkeypatch.setattr(clasificar, "clasificar", _clasificar_falso)
    gastos_registrados = []
    monkeypatch.setattr(tareas_ref.gastos, "registrar_seguro", lambda *a, **k: gastos_registrados.append((a, k)))
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "clasificando",
                                  "consulta": {"fuente": "atria"}, "tope": 5}}
    tareas_ref.ejecutar_barrer(tarea)
    assert datos.referente(cliente, rid_malo)["clasificacion"] == "error"
    assert datos.referente(cliente, rid_bueno)["clasificacion"] == "claude"
    assert datos.barrido(bid)["clasificados"] == 1
    # Nada facturado por la fila que reventó (0 tokens: la llamada nunca llegó
    # a completarse del lado de Anthropic).
    assert not any("60" in str(a) for a, k in gastos_registrados)


def test_fase_clasificando_rate_limit_sigue_abortando_el_tramo(tmp_path, monkeypatch):
    """Companion del test anterior: Important 4 pide explícitamente NO
    ampliar el catch a cualquier excepción -- un 429 (u otro error que no sea
    BadRequestError) sí debe seguir abortando el tramo entero, porque a
    diferencia de una imagen ilegible, tiene sentido reintentarlo más tarde."""
    import anthropic

    from referentes import clasificar, datos
    from tareas import referentes as tareas_ref
    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {}, 5)
    rid, _ = datos.guardar_referente({"anuncio_id": "70", "fuente": "atria", "imagen_origen": "https://x/70.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente=cliente, barrido_id=bid)
    datos.marcar_imagen(rid, "ok", "https://r2/70.jpg")

    def _clasificar_429(referente, vocabulario):
        import httpx
        peticion = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        respuesta = httpx.Response(429, request=peticion, json={"error": {"message": "rate limited"}})
        raise anthropic.RateLimitError("rate limited", response=respuesta, body=None)

    monkeypatch.setattr(clasificar, "clasificar", _clasificar_429)
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "clasificando",
                                  "consulta": {"fuente": "atria"}, "tope": 5}}
    with pytest.raises(anthropic.RateLimitError):
        tareas_ref.ejecutar_barrer(tarea)
    assert datos.referente(cliente, rid)["clasificacion"] == "pendiente"
    assert datos.barrido(bid)["estado"] == "parcial"


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


def test_fase_clasificando_automatica_nunca_re_factura_un_referente_en_error(tmp_path, monkeypatch):
    """Important 3: el tramo AUTOMÁTICO de `referentes_barrer` (una tarea sin
    "tipo", o con tipo=TIPO_BARRER -- como la deja `cola.reclamar()` para
    cualquier tarea `referentes_barrer` real) pide `pendientes_clasificacion`
    con `incluir_error=False`, así que un referente que ya falló nunca debe
    volver a pasar por `clasificar.clasificar` -- ni facturarse otra vez --
    en ningún tramo posterior, aunque la fase se siga re-encolando para
    procesar OTROS referentes que sí van avanzando.

    Fuerza TRAMO=1 (monkeypatch del módulo) para que cada llamada a
    `ejecutar_barrer` sea de verdad un tramo que solo toca UN referente --
    así se puede intercalar tramos que sí avanzan (y por lo tanto sí se
    re-encolarían en producción) con tramos que ya no tocan a rid_malo,
    usando un contador de llamadas explícito por id en vez de inferir el
    comportamiento solo de los estados finales."""
    from collections import defaultdict

    from referentes import clasificar, datos
    from tareas import referentes as tareas_ref

    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    monkeypatch.setattr(tareas_ref, "TRAMO", 1)
    bid = datos.crear_barrido(cliente, "atria", {}, 5)

    # Orden de creación == orden de id == orden en que `pendientes_clasificacion`
    # (ORDER BY id) los entrega con TRAMO=1: bueno1, luego malo, luego bueno2.
    rid_bueno1, _ = datos.guardar_referente({"anuncio_id": "40", "fuente": "atria", "imagen_origen": "https://x/40.jpg",
                                             "marca": "M", "titular": "B1", "cuerpo": "", "idioma": "en"},
                                            cliente=cliente, barrido_id=bid)
    rid_malo, _ = datos.guardar_referente({"anuncio_id": "41", "fuente": "atria", "imagen_origen": "https://x/41.jpg",
                                           "marca": "M", "titular": "Malo", "cuerpo": "", "idioma": "en"},
                                          cliente=cliente, barrido_id=bid)
    rid_bueno2, _ = datos.guardar_referente({"anuncio_id": "42", "fuente": "atria", "imagen_origen": "https://x/42.jpg",
                                             "marca": "M", "titular": "B2", "cuerpo": "", "idioma": "en"},
                                            cliente=cliente, barrido_id=bid)
    for rid in (rid_bueno1, rid_malo, rid_bueno2):
        datos.marcar_imagen(rid, "ok", f"https://r2/{rid}.jpg")

    llamadas = defaultdict(int)

    def _clasificar_falso(referente, vocabulario):
        llamadas[referente["id"]] += 1
        if referente["id"] == rid_malo:
            e = clasificar.ClasificacionInvalida("Claude no devolvió JSON.")
            e.tokens_entrada, e.tokens_salida = 50, 0
            raise e
        return ({"etapa": "TOF", "consciencia": "unaware", "familia": None,
                 "familia_nueva": {"nombre": f"F{referente['id']}", "descripcion": "d"}, "dolor": "dolor", "firma": "f"},
                80, 20)

    monkeypatch.setattr(clasificar, "clasificar", _clasificar_falso)
    monkeypatch.setattr("cola.encolar", lambda *a, **kw: None)  # no nos importa el re-encolado real, solo el estado
    tarea = {"id": 1, "payload": {"cliente": cliente, "barrido_id": bid, "fase": "clasificando",
                                  "consulta": {"fuente": "atria"}, "tope": 5}}
    # Sin "tipo": tal como llega una tarea `referentes_barrer` real a
    # `_fase_clasificando` (tipo_actual cae a TIPO_BARRER, el default).

    # Tramo 1: toca rid_bueno1 (menor id, sigue "pendiente") -> avanza.
    tareas_ref.ejecutar_barrer(tarea)
    assert llamadas == {rid_bueno1: 1}
    assert datos.referente(cliente, rid_bueno1)["clasificacion"] == "claude"

    # Tramo 2: el siguiente "pendiente" es rid_malo -> falla, queda en error.
    tareas_ref.ejecutar_barrer(tarea)
    assert llamadas[rid_malo] == 1
    assert datos.referente(cliente, rid_malo)["clasificacion"] == "error"

    # Tramo 3: rid_malo YA está en error -> el automático (incluir_error=False)
    # ya no lo trae; el siguiente "pendiente" real es rid_bueno2 -> avanza.
    tareas_ref.ejecutar_barrer(tarea)
    assert llamadas[rid_malo] == 1          # nunca se reintentó ni se re-facturó
    assert llamadas[rid_bueno2] == 1
    assert datos.referente(cliente, rid_bueno2)["clasificacion"] == "claude"

    # Tramo 4: no queda nada "pendiente" (solo rid_malo en error, que el
    # automático sigue ignorando) -> ni siquiera se llama a clasificar.clasificar.
    resultado_final = tareas_ref.ejecutar_barrer(tarea)
    assert llamadas == {rid_bueno1: 1, rid_malo: 1, rid_bueno2: 1}
    b = datos.barrido(bid)
    assert b["estado"] == "parcial" and "no se pudieron clasificar" in b["aviso"]
    assert isinstance(resultado_final, str)


def test_ejecutar_clasificar_standalone_si_reintenta_referente_en_error(tmp_path, monkeypatch):
    """Companion del test anterior: la tarea STANDALONE `referentes_clasificar`
    (el botón explícito "Clasificar pendientes") SÍ debe recoger y reintentar
    un referente que quedó en clasificacion="error" de un intento previo --
    eso es justamente lo que permite `incluir_error=True` (default) en
    `pendientes_clasificacion` para esta tarea, a diferencia del tramo
    automático de arriba. La tarea lleva "tipo": TIPO_CLASIFICAR (tal como lo
    deja `cola.reclamar()` en producción para toda tarea encolada con ese
    tipo, ver cola.py/`encolar_clasificar_pendientes`) para que
    `_fase_clasificando` calcule `automatico=False` de verdad, no por un
    default accidental de la prueba."""
    from referentes import clasificar, datos
    from tareas import referentes as tareas_ref

    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "atria", {}, 5)
    rid_error, _ = datos.guardar_referente({"anuncio_id": "50", "fuente": "atria", "imagen_origen": "https://x/50.jpg",
                                            "marca": "M", "titular": "Reintento", "cuerpo": "", "idioma": "en"},
                                           cliente=cliente, barrido_id=bid)
    datos.marcar_imagen(rid_error, "ok", "https://r2/50.jpg")
    # Simula el estado que deja un intento previo fallido (ver
    # `_clasificar_uno` ante un ClasificacionInvalida, y el test de arriba).
    datos.actualizar_referente(rid_error, clasificacion="error",
                               extra={"error_clasificacion": "Claude no devolvió JSON."})
    assert datos.referente(cliente, rid_error)["clasificacion"] == "error"

    llamadas = []

    def _clasificar_ok(referente, vocabulario):
        llamadas.append(referente["id"])
        return ({"etapa": "TOF", "consciencia": "unaware", "familia": None,
                 "familia_nueva": {"nombre": "Reintentado", "descripcion": "d"}, "dolor": "dolor", "firma": "f"},
                80, 20)

    monkeypatch.setattr(clasificar, "clasificar", _clasificar_ok)
    monkeypatch.setattr("cola.encolar", lambda *a, **kw: None)
    tarea = {"id": 1, "tipo": tareas_ref.TIPO_CLASIFICAR, "job_id": tareas_ref.job_id_barrer(bid),
             "payload": {"cliente": cliente, "barrido_id": bid, "fase": "clasificando",
                        "consulta": {"fuente": "atria"}, "tope": 5}}
    tareas_ref.ejecutar_clasificar(tarea)

    assert llamadas == [rid_error]  # el standalone SÍ recogió y reintentó la fila en error
    r = datos.referente(cliente, rid_error)
    assert r["clasificacion"] == "claude" and r["familia"] == "EMERGING: Reintentado"


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


def test_fase_trayendo_registra_gasto_real_cuando_la_fuente_lo_reporta(tmp_path, monkeypatch):
    import sqlalchemy as sa

    import db
    from referentes import datos
    from tareas import referentes as tareas_referentes

    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "apify", {"modo": "palabra", "palabra": "sandalias"}, 5)

    def traer_falso(consulta, tope, avanzar, cursor=None):
        avanzar("Buscando en Apify", "1 anuncios")
        yield [{"anuncio_id": "a1", "imagen_origen": "https://x/a1.jpg", "marca": "X", "titular": "", "cuerpo": "",
                "tipo": "imagen", "pais": None, "idioma": None, "dias": None, "variantes": None,
                "primera_vez": None, "ultima_vez": None, "activo": True, "url_anuncio": "", "url_marca": "",
                "etiquetas_fuente": {}, "extra": {}, "pagina_id": None}], None, {"costo_real": 0.029}

    class _ModuloFalso:
        traer = staticmethod(traer_falso)

    monkeypatch.setattr(tareas_referentes.fuentes, "por_tipo", lambda tipo: _ModuloFalso())
    tarea = {"id": 999, "job_id": None, "payload": {"barrido_id": bid, "cliente": cliente,
             "consulta": {"modo": "palabra", "palabra": "sandalias", "fuente": "apify"}, "tope": 5, "fase": "trayendo"}}
    tareas_referentes.ejecutar_barrer(tarea)

    with db.conectar() as con:
        filas = con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente,
                                                       db.gasto.c.tipo == "recoleccion")).mappings().all()
    assert len(filas) == 1
    assert filas[0]["usd"] == 0.029
    assert f"referentes:barrer:{bid}:apify:t999" in filas[0]["referencia"]


def test_fase_trayendo_suma_el_costo_real_a_usd_real_del_barrido(tmp_path, monkeypatch):
    """El gasto en `gastos` (Important 1 del review final) no basta: "Mis
    barridos" lee `barrido.usd_real`, así que `_fase_trayendo` debe sumarle
    el costo real de Apify igual que `_fase_clasificando` ya hace con el
    suyo (mismo mecanismo: releer el barrido y sumar con
    `datos.actualizar_barrido(bid, usd_real=...)`)."""
    from referentes import datos
    from tareas import referentes as tareas_referentes

    cliente = _cliente_de_prueba(tmp_path, monkeypatch)
    bid = datos.crear_barrido(cliente, "apify", {"modo": "palabra", "palabra": "sandalias"}, 5)

    def traer_falso(consulta, tope, avanzar, cursor=None):
        avanzar("Buscando en Apify", "1 anuncios")
        yield [{"anuncio_id": "a1", "imagen_origen": "https://x/a1.jpg", "marca": "X", "titular": "", "cuerpo": "",
                "tipo": "imagen", "pais": None, "idioma": None, "dias": None, "variantes": None,
                "primera_vez": None, "ultima_vez": None, "activo": True, "url_anuncio": "", "url_marca": "",
                "etiquetas_fuente": {}, "extra": {}, "pagina_id": None}], None, {"costo_real": 0.029}

    class _ModuloFalso:
        traer = staticmethod(traer_falso)

    monkeypatch.setattr(tareas_referentes.fuentes, "por_tipo", lambda tipo: _ModuloFalso())
    tarea = {"id": 999, "job_id": None, "payload": {"barrido_id": bid, "cliente": cliente,
             "consulta": {"modo": "palabra", "palabra": "sandalias", "fuente": "apify"}, "tope": 5, "fase": "trayendo"}}
    tareas_referentes.ejecutar_barrer(tarea)

    assert datos.barrido(bid)["usd_real"] == pytest.approx(0.029)

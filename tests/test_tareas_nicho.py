import pytest

SUB = {"base": "emocion", "nombre": "Ana / La que carga", "deseo": "Quiero lavar sin cargar", "demografia": "", "edad_rango": "",
       "emocion": "Cansancio", "identidad": {"quiere_que_vean": "a", "cree_de_si": "b", "quiere_lograr": "c"},
       "soluciones_previas": [], "situaciones": ["Cargando garrafas"], "comportamiento": "Sigue igual",
       "conciencia": {"nivel": "consciente_del_problema", "detalle": "d"}, "encaje_producto": "Cápsulas", "tono": "Directo",
       "palabras_clave": ["garrafa"], "evidencia": [{"comentario_id": 1, "cita": "la garrafa pesa demasiado"}], "sin_evidencia": False}


def _estudio(datos):
    eid = datos.crear_estudio("acme", "Detergente")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: la garrafa pesa demasiado."} for i in range(25)])
    return eid


def test_encolar_generar(base_temporal, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    encolados = []
    monkeypatch.setattr(tareas_nicho.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    eid = _estudio(datos)
    assert tareas_nicho.encolar_generar("acme", eid) is True
    t = encolados[0]
    assert t["job_id"] == datos.job_id_generar("acme", eid) and t["tipo"] == "nicho_generar_avatares"
    assert t["payload"] == {"cliente": "acme", "estudio_id": eid} and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert [e[0] for e in t["etapas"]] == ["Agrupando deseos", "Armando sub-avatares", "Guardando"]


def test_ejecutar_generar_guarda_registra_gasto_y_recalcula(base_temporal, monkeypatch):
    from nicho import avatares, datos
    from tareas import nicho as tareas_nicho
    import gastos
    eid = _estudio(datos)
    resultado = {"nucleos": [{"nombre": "Sin peso", "deseo": "Quiero lavar sin cargar", "resumen": "r", "comentarios": [1], "sub_avatares": [SUB]}],
                 "resumen": {"comentarios": 25, "nucleos": 1, "subs": 1, "con_evidencia": 1, "sin_evidencia": 0, "errores": 0,
                             "tokens_entrada": 3000, "tokens_salida": 900, "usd": 0.015, "modelo": "claude-sonnet-5"}}
    llamadas = []
    monkeypatch.setattr(avatares, "generar", lambda cliente, estudio_id, avanzar=None: llamadas.append((cliente, estudio_id)) or resultado)
    msg = tareas_nicho.ejecutar_generar({"payload": {"cliente": "acme", "estudio_id": eid}, "job_id": datos.job_id_generar("acme", eid)})
    assert "1 núcleo" in msg and "1 sub-avatar" in msg and llamadas == [("acme", eid)]
    e = datos.estudio("acme", eid)
    assert e["estado"] == "revisando" and e["generacion"] == 1 and e["avatares_total"] == 1
    assert e["extra"]["ultima_generacion"]["usd"] == 0.015 and "ultimo_error" not in e["extra"]
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "avatares" and g["usd"] == 0.015 and g["referencia"] == f"avatares:{eid}:1" and g["proveedor"] == "anthropic"
    assert g["extra"]["tokens_entrada"] == 3000
    assert len(gastos.historial("acme")) == 1                             # nada de "fallido" cuando sale bien


def test_ejecutar_generar_falla_deja_error_y_estado(base_temporal, monkeypatch):
    from nicho import avatares, datos
    from tareas import nicho as tareas_nicho
    import gastos
    eid = _estudio(datos)

    def _falla(*a, **k):
        e = avatares.AnalisisInvalido("Claude no devolvió JSON.")
        e.tokens_entrada, e.tokens_salida = 3000, 100
        raise e
    monkeypatch.setattr(avatares, "generar", _falla)
    with pytest.raises(avatares.AnalisisInvalido):
        tareas_nicho.ejecutar_generar({"payload": {"cliente": "acme", "estudio_id": eid}, "job_id": datos.job_id_generar("acme", eid)})
    e = datos.estudio("acme", eid)
    assert e["estado"] == "armando" and "Claude no devolvió JSON" in e["extra"]["ultimo_error"] and "cobró" in e["extra"]["ultimo_error"]
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "avatares" and g["referencia"].startswith(f"avatares:{eid}:fallido")
    assert g["usd"] == avatares.costo_real(3000, 100) and g["detalle"].startswith("intento fallido")
    assert tareas_nicho.ejecutar_generar({"payload": {"cliente": "acme", "estudio_id": 999}, "job_id": "x"}) == "El estudio ya no existe."


def test_ejecutar_generar_falla_al_guardar_deja_error_y_estado(base_temporal, monkeypatch):
    from nicho import avatares, datos
    from tareas import nicho as tareas_nicho
    import gastos
    eid = _estudio(datos)
    resultado = {"nucleos": [{"nombre": "N", "deseo": "Quiero", "resumen": "", "comentarios": [1], "sub_avatares": [SUB]}],
                 "resumen": {"comentarios": 25, "nucleos": 1, "subs": 1, "con_evidencia": 1, "sin_evidencia": 0, "errores": 0,
                             "tokens_entrada": 10, "tokens_salida": 5, "usd": 0.001, "modelo": "claude-sonnet-5"}}
    monkeypatch.setattr(avatares, "generar", lambda *a, **k: resultado)
    monkeypatch.setattr(datos, "guardar_generacion", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disco lleno")))
    with pytest.raises(RuntimeError):
        tareas_nicho.ejecutar_generar({"payload": {"cliente": "acme", "estudio_id": eid}, "job_id": datos.job_id_generar("acme", eid)})
    e = datos.estudio("acme", eid)
    assert e["estado"] == "armando" and "disco lleno" in e["extra"]["ultimo_error"]
    g = gastos.historial("acme")[0]
    assert g["referencia"].startswith(f"avatares:{eid}:fallido") and g["usd"] == 0.001


def test_interrumpida_generar(base_temporal):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = _estudio(datos)
    datos.actualizar_estudio("acme", eid, estado="generando")
    tareas_nicho.interrumpida_generar({"payload": {"cliente": "acme", "estudio_id": eid}}, "Se interrumpió por un reinicio.")
    e = datos.estudio("acme", eid)
    assert e["estado"] == "armando" and e["extra"]["ultimo_error"] == "Se interrumpió por un reinicio."


def test_worker_registra_la_tarea():
    import tareas
    from tareas import nicho  # noqa: F401 — el import corre los @registrar
    assert "nicho_generar_avatares" in tareas.REGISTRO and "nicho_generar_avatares" in tareas.AL_INTERRUMPIR
    import inspect
    assert "nicho" in inspect.getsource(tareas.cargar_todas)      # el worker real también lo importa


def test_cadena_completa_generar_guardar_y_gasto(base_temporal, monkeypatch):
    """I3: generar -> ejecutar_generar -> guardar_generacion -> avatares, de
    punta a punta, con solo `avatares._llamar` reemplazado (nada más)."""
    import json
    from nicho import avatares, datos
    from tareas import nicho as tareas_nicho
    import gastos
    eid = _estudio(datos)
    ids = [c["id"] for c in datos.comentarios_para_generar("acme", eid)]
    nucleos = {"nucleos": [{"nombre": "Sin peso", "deseo": "Quiero lavar sin cargar", "resumen": "r", "comentarios": ids[:10]},
                           {"nombre": "Sin goteo", "deseo": "Quiero que no gotee", "resumen": "r2", "comentarios": ids[10:20]}]}
    sub = dict(SUB, nombre="Ana / La que carga",
              evidencia=[{"comentario_id": ids[0], "cita": "la garrafa pesa demasiado"},
                         {"comentario_id": ids[0], "cita": "esto no lo dijo nadie en este comentario"}])
    respuestas = [(json.dumps(nucleos), 1000, 200), (json.dumps({"sub_avatares": [sub]}), 700, 300), ("no es json", 500, 10)]
    monkeypatch.setattr(avatares, "_llamar", lambda texto, max_tokens: respuestas.pop(0))
    tarea = {"payload": {"cliente": "acme", "estudio_id": eid}, "job_id": datos.job_id_generar("acme", eid)}
    tareas_nicho.ejecutar_generar(tarea)

    nucleos_bd = datos.avatares("acme", eid)
    assert len(nucleos_bd) == 2
    n1, n2 = nucleos_bd
    assert len(n1["subs"]) == 1
    s = n1["subs"][0]
    assert len(s["evidencia"]) == 1 and s["evidencia"][0]["cita"] == "la garrafa pesa demasiado"
    assert s["sin_evidencia"] is False and s["estado"] == "propuesto"
    assert n2["subs"] == [] and "JSON" in n2["extra"]["error"]

    est = datos.estudio("acme", eid)
    assert est["estado"] == "revisando" and est["generacion"] == 1
    assert est["extra"]["ultima_generacion"]["errores"] == 1

    g = gastos.historial("acme")[0]
    assert g["referencia"] == f"avatares:{eid}:1"
    assert g["usd"] == avatares.costo_real(1000 + 700 + 500, 200 + 300 + 10)


# ------------------------------------------------------- nicho_recolectar ---

class _FuenteFalsa:
    """Fuente programable: entrega `programa`, deja `aviso_final`, y si `fallo_en`
    no es None lanza `fallo_exc` después de entregar esa cantidad."""
    tipo = "reddit"
    de_pago = False
    programa = ()
    aviso_final = ""
    fallo_en = None
    fallo_exc = None

    def __init__(self):
        self.aviso = ""
        self.resultados = 0

    def recolectar(self, params, avanzar=None):
        avanzar("Buscando")
        for i, c in enumerate(self.programa):
            if self.fallo_en is not None and i == self.fallo_en:
                raise self.fallo_exc
            avanzar("Leyendo comentarios", f"{i + 1}")
            self.resultados += 1
            yield c
        self.aviso = self.aviso_final


def _comentarios_falsos(n):
    return [{"fuente_id": f"r{i}", "texto": f"Comentario {i}: la garrafa pesa demasiado y gotea.", "url": None, "contexto": None,
             "puntuacion": i, "fecha": None, "extra": {}} for i in range(n)]


def _fuente_falsa(monkeypatch, tipo="reddit", programa=(), aviso_final="", fallo_en=None, fallo_exc=None, de_pago=False):
    from tareas import nicho as tareas_nicho

    class F(_FuenteFalsa):
        pass
    F.tipo, F.de_pago, F.programa, F.aviso_final, F.fallo_en, F.fallo_exc = tipo, de_pago, list(programa), aviso_final, fallo_en, fallo_exc
    monkeypatch.setattr(tareas_nicho.fuentes_registro, "por_tipo", lambda t: F)
    return F


def _tarea(cliente, eid, fuente, params=None, tid=7):
    from nicho import datos
    return {"id": tid, "payload": {"cliente": cliente, "estudio_id": eid, "fuente": fuente, "params": params or {}},
            "job_id": datos.job_id_recolectar(cliente, eid, fuente)}


def test_job_id_y_encolar_recolectar(base_temporal, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    encolados = []
    monkeypatch.setattr(tareas_nicho.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    eid = datos.crear_estudio("acme", "X")
    assert datos.job_id_recolectar("acme", eid, "reddit") == f"nicho:acme:{eid}:recolectar:reddit"
    assert tareas_nicho.encolar_recolectar("acme", eid, "reddit", {"palabras_clave": "x"}) is True
    t = encolados[0]
    assert t["job_id"] == f"nicho:acme:{eid}:recolectar:reddit" and t["tipo"] == "nicho_recolectar"
    assert t["payload"] == {"cliente": "acme", "estudio_id": eid, "fuente": "reddit", "params": {"palabras_clave": "x"}}
    assert t["max_intentos"] == 2 and t["duracion_estimada"] == 120 and [e[0] for e in t["etapas"]] == ["Buscando", "Leyendo comentarios", "Guardando"]
    tareas_nicho.encolar_recolectar("acme", eid, "apify", {"actor": "tiktok_comentarios"})
    assert encolados[1]["max_intentos"] == 1 and encolados[1]["duracion_estimada"] == 300
    with pytest.raises(datos.ErrorDatos):
        tareas_nicho.encolar_recolectar("acme", eid, "texto", {})


def test_ejecutar_recolectar_guarda_por_lotes_y_registra(base_temporal, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, programa=_comentarios_falsos(250))
    lotes = []
    original = datos.agregar_comentarios
    monkeypatch.setattr(tareas_nicho.datos, "agregar_comentarios", lambda c, e, f, lista: lotes.append(len(lista)) or original(c, e, f, lista))
    msg = tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "reddit", {"palabras_clave": "x"}))
    assert lotes == [100, 100, 50] and "250 comentario(s) nuevo(s) de Reddit" in msg and "Aviso" not in msg
    e = datos.estudio("acme", eid)
    assert e["comentarios_total"] == 250 and e["fuentes"]["reddit"]["total"] == 250 and e["estado"] == "armando"
    r = e["extra"]["recolecciones"][-1]
    assert r["fuente"] == "reddit" and r["nuevos"] == 250 and r["repetidos"] == 0 and r["aviso"] == "" and r["fecha"]
    msg = tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "reddit"))
    assert "0 comentario(s) nuevo(s)" in msg and "250 repetido(s)" in msg
    assert datos.estudio("acme", eid)["extra"]["recolecciones"][-1]["repetidos"] == 250
    assert tareas_nicho.ejecutar_recolectar(_tarea("acme", 999, "reddit")) == "El estudio ya no existe."


def test_ejecutar_recolectar_parcial_deja_aviso(base_temporal, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, tipo="youtube", programa=_comentarios_falsos(3), aviso_final="YouTube agotó la cuota diaria.")
    msg = tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "youtube"))
    assert "3 comentario(s) nuevo(s) de YouTube" in msg and "Aviso: YouTube agotó la cuota" in msg
    assert datos.estudio("acme", eid)["extra"]["recolecciones"][-1]["aviso"] == "YouTube agotó la cuota diaria."


def test_ejecutar_recolectar_fallo_guarda_lo_leido_y_relanza(base_temporal, monkeypatch):
    from nicho import datos
    from nicho.fuentes.base import ErrorFuente
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, programa=_comentarios_falsos(5), fallo_en=3, fallo_exc=ErrorFuente("Reddit rechazó la llamada (access_token=abc)."))
    with pytest.raises(ErrorFuente):
        tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "reddit"))
    e = datos.estudio("acme", eid)
    assert e["comentarios_total"] == 3
    r = e["extra"]["recolecciones"][-1]
    assert r["nuevos"] == 3 and r["aviso"].startswith("falló: Reddit rechazó") and "abc" not in r["aviso"]


def test_ejecutar_recolectar_apify_registra_gasto(base_temporal, monkeypatch):
    import gastos
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, tipo="apify", programa=_comentarios_falsos(30), de_pago=True)
    tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "apify", {"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 50}, tid=11))
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "recoleccion" and g["usd"] == 0.09 and g["proveedor"] == "apify" and g["referencia"] == f"recoleccion:{eid}:t11"
    assert "30 resultado(s) aprox." in g["detalle"] and g["extra"]["actor"] == "junglee~amazon-reviews-scraper"
    _fuente_falsa(monkeypatch, tipo="reddit", programa=_comentarios_falsos(3))
    tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "reddit", tid=12))
    assert len(gastos.historial("acme")) == 1                                   # las gratis no registran gasto


def test_ejecutar_recolectar_apify_fallido_registra_lo_cobrado(base_temporal, monkeypatch):
    import gastos
    from nicho import datos
    from nicho.fuentes.base import ErrorFuente
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, tipo="apify", programa=_comentarios_falsos(10), de_pago=True, fallo_en=4, fallo_exc=ErrorFuente("La corrida de Apify terminó en ABORTED."))
    with pytest.raises(ErrorFuente):
        tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "apify", {"actor": "tiktok_comentarios"}, tid=13))
    g = gastos.historial("acme")[0]
    assert g["usd"] == 0.01 and "intento fallido" in g["detalle"] and g["extra"]["resultados"] == 4
    assert datos.estudio("acme", eid)["comentarios_total"] == 4


def test_interrumpida_recolectar(base_temporal):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    tareas_nicho.interrumpida_recolectar(_tarea("acme", eid, "reddit"), "Se interrumpió por un reinicio.")
    r = datos.estudio("acme", eid)["extra"]["recolecciones"][-1]
    assert r["fuente"] == "reddit" and r["aviso"] == "interrumpida: Se interrumpió por un reinicio." and r["nuevos"] == 0


def test_worker_registra_recolectar():
    import tareas
    from tareas import nicho  # noqa: F401
    assert "nicho_recolectar" in tareas.REGISTRO and "nicho_recolectar" in tareas.AL_INTERRUMPIR

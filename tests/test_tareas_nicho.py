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

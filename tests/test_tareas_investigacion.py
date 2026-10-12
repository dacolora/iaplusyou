"""Cadena de la investigación: consultas, buscar, seleccionar, avanzar y los pasos de recolectar/generar (sin red, SQLite real)."""
import pytest


def _estudio(datos, pais="SE", tema="pantuflas para dolor de pies", n_comentarios=0):
    eid = datos.crear_estudio("acme", "Tofflor", producto="HappyFlops", tema=tema, pais=pais)
    if n_comentarios:
        datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: me duelen los talones."} for i in range(n_comentarios)])
    return eid


def _iniciar(datos, eid, plataformas=("amazon", "meli"), redes=("reddit",)):
    from nicho import investigacion as inv
    return datos.iniciar_investigacion("acme", eid, inv.crear_inicial("pantuflas", "SE" if "meli" not in plataformas else "MX", list(plataformas), list(redes),
                                                                    inv.TOPES_DEFECTO, estimado={"total_usd": 9.0}))


@pytest.fixture()
def cola_falsa(monkeypatch):
    from tareas import investigacion as ti, nicho as tn
    encolados = []

    def _encolar(job_id, tipo, payload, **kw):
        encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw})
        return True
    monkeypatch.setattr(ti.trabajos, "encolar", _encolar)
    monkeypatch.setattr(tn.trabajos, "encolar", _encolar)
    monkeypatch.setattr(ti.trabajos, "en_curso", lambda job: False, raising=False)
    return encolados


def _tarea(cliente, eid, tipo, extra=None, tid=7, intentos=1, max_intentos=2):
    return {"id": tid, "tipo": tipo, "payload": {"cliente": cliente, "estudio_id": eid, **(extra or {})}, "job_id": f"x:{tipo}",
            "intentos": intentos, "max_intentos": max_intentos}


class _Plat:
    """Fuente de plataforma falsa: `buscar` entrega lo programado, cobra `resultados`."""
    de_pago = True
    programa = []
    fallo = None
    aviso_final = ""
    resultados_crudos = 0

    def __init__(self, clave):
        self.tipo = self.clave = clave
        self.resultados, self.aviso, self.run_id, self.corridas, self.conteo_por_producto = 0, "", None, [], {}

    def tarifa_busqueda(self):
        return {"actor": "x~buscar", "nombre": f"Búsqueda en {self.clave}", "usd_por_resultado": 0.003}

    def tarifa(self, params=None):
        return {"actor": "x~resenas", "nombre": f"Reseñas de {self.clave}", "usd_por_resultado": 0.001}

    def buscar(self, consultas, pais, n, avanzar=None):
        self.run_id, self.corridas = "run_b", [{"run_id": "run_b"}]
        for k, p in enumerate(self.programa):
            if self.fallo is not None and k == self.fallo:
                self.resultados = self.resultados_crudos
                raise self.fallo_exc
            self.resultados += 1
            yield dict(p)
        self.aviso = self.aviso_final


def _productos(n, plataforma="amazon"):
    return [{"fuente_id": f"P{i}", "titulo": f"Producto {i}", "marca": "M", "precio": 9.9, "moneda": "USD", "estrellas": 4.0, "n_resenas": 10 * (i + 1),
             "url": f"https://x/{plataforma}/{i}", "imagen": None, "consulta": "q", "extra": {}} for i in range(n)]


def _claude(monkeypatch, respuestas):
    from nicho import avatares
    it = iter(respuestas)
    monkeypatch.setattr(avatares, "_llamar", lambda texto, max_tokens: next(it))


def test_consultas_hecho_gasto_y_avanza(base_temporal, cola_falsa, monkeypatch):
    import gastos
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))
    _claude(monkeypatch, [('{"consultas": ["tofflor mot fotsmärta", "ortopediska tofflor"]}', 700, 40)])
    msg = ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas"))
    i = datos.investigacion("acme", eid)
    assert "tofflor" in msg and i["consultas"] == ["tofflor mot fotsmärta", "ortopediska tofflor"]
    assert i["pasos"]["consultas"]["estado"] == "hecho" and i["pasos"]["consultas"]["usd"] > 0 and i["gastado_usd"] == i["pasos"]["consultas"]["usd"]
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "investigacion" and g["referencia"] == f"investigacion:{eid}:consultas:t7" and g["extra"]["tokens_entrada"] == 700
    assert cola_falsa[-1]["tipo"] == "nicho_inv_buscar" and cola_falsa[-1]["payload"]["plataforma"] == "amazon" and cola_falsa[-1]["max_intentos"] == 1
    assert cola_falsa[-1]["job_id"] == datos.job_id_inv("acme", eid, "buscar:amazon") and i["estado"] == "buscando"


def test_consultas_falla_dos_veces_detiene_y_registra(base_temporal, cola_falsa, monkeypatch):
    import gastos
    from nicho import avatares, datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid)
    _claude(monkeypatch, [("no es json", 10, 5)])
    with pytest.raises(avatares.AnalisisInvalido):
        ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas", intentos=1, max_intentos=2))
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "consultas" and i["pasos"]["consultas"]["estado"] == "pendiente" and cola_falsa == []
    assert gastos.historial("acme")[0]["detalle"].startswith("intento fallido")
    _claude(monkeypatch, [("tampoco", 10, 5)])
    with pytest.raises(avatares.AnalisisInvalido):
        ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas", intentos=2, max_intentos=2))
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and "consultas" in i["detenida_por"] and i["pasos"]["consultas"]["estado"] == "error"
    assert ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas")) and cola_falsa == []      # detenida: no hace nada
    eid2 = _estudio(datos, tema="")
    _iniciar(datos, eid2)
    ti.ejecutar_consultas(_tarea("acme", eid2, "nicho_inv_consultas"))
    assert datos.investigacion("acme", eid2)["detenida_por"] == "sin tema"


def test_buscar_guarda_productos_gasto_y_sigue(base_temporal, cola_falsa, monkeypatch):
    import gastos
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("amazon", "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a", "b"], "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}}})
    F = type("F", (_Plat,), {"programa": _productos(3), "aviso_final": "una corrida FAILED"})
    monkeypatch.setattr(ti.fuentes_registro, "por_tipo", lambda t: (lambda: F(t)))
    msg = ti.ejecutar_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "amazon"}, intentos=1, max_intentos=1))
    assert "3" in msg
    assert [p["fuente_id"] for p in datos.productos_nicho("acme", eid, plataforma="amazon")] == ["P2", "P1", "P0"]
    i = datos.investigacion("acme", eid)
    paso = i["pasos"]["buscar:amazon"]
    assert paso["estado"] == "hecho" and paso["productos"] == 3 and paso["nuevos"] == 3 and paso["usd"] == 0.01 and paso["aviso"] == "una corrida FAILED"
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "recoleccion" and g["referencia"] == f"recoleccion:{eid}:buscar:amazon:t7" and g["extra"]["corridas"] == ["run_b"]
    assert cola_falsa[-1]["tipo"] == "nicho_inv_buscar" and cola_falsa[-1]["payload"]["plataforma"] == "meli"
    F2 = type("F2", (_Plat,), {"programa": []})
    monkeypatch.setattr(ti.fuentes_registro, "por_tipo", lambda t: (lambda: F2(t)))
    ti.ejecutar_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "meli"}))
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["buscar:meli"]["estado"] == "vacio" and cola_falsa[-1]["tipo"] == "nicho_inv_seleccionar" and i["estado"] == "seleccionando"


def test_buscar_falla_guarda_lo_leido_y_la_cadena_sigue(base_temporal, cola_falsa, monkeypatch):
    import gastos
    from nicho import datos
    from nicho.fuentes.base import ErrorFuente
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("amazon", "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a"], "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}}})
    F = type("F", (_Plat,), {"programa": _productos(2), "fallo": 1, "fallo_exc": ErrorFuente("Apify se cayó (corrida run_b)"), "resultados_crudos": 5})
    monkeypatch.setattr(ti.fuentes_registro, "por_tipo", lambda t: (lambda: F(t)))
    with pytest.raises(ErrorFuente):
        ti.ejecutar_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "amazon"}, intentos=1, max_intentos=1))
    assert [p["fuente_id"] for p in datos.productos_nicho("acme", eid)] == ["P0"]          # lo leído antes del fallo se guardó
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["buscar:amazon"]["estado"] == "error" and "run_b" in i["pasos"]["buscar:amazon"]["aviso"] and i["pasos"]["buscar:amazon"]["usd"] == 0.02
    assert gastos.historial("acme")[0]["detalle"].endswith("intento fallido") and cola_falsa[-1]["payload"]["plataforma"] == "meli"


def test_seleccionar_marca_elige_y_encola_resenas(base_temporal, cola_falsa, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("amazon", "meli"), redes=())
    datos.guardar_productos_nicho("acme", eid, "amazon", _productos(3))
    datos.guardar_productos_nicho("acme", eid, "meli", _productos(1, "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "topes": {**x["topes"], "productos_elegidos": 2},
                                                          "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:amazon": {"estado": "hecho"}, "buscar:meli": {"estado": "hecho"}}})
    ids = {(p["plataforma"], p["fuente_id"]): p["id"] for p in datos.productos_nicho("acme", eid)}
    respuesta = {"productos": [{"id": ids[("amazon", "P0")], "relevante": True, "motivo": "sí"}, {"id": ids[("amazon", "P1")], "relevante": True, "motivo": "sí"},
                               {"id": ids[("amazon", "P2")], "relevante": True, "motivo": "sí"}, {"id": ids[("meli", "P0")], "relevante": False, "motivo": "otra cosa"}]}
    import json
    _claude(monkeypatch, [(json.dumps(respuesta), 900, 60)])
    msg = ti.ejecutar_seleccionar(_tarea("acme", eid, "nicho_inv_seleccionar"))
    assert "3" in msg
    i = datos.investigacion("acme", eid)
    assert i["elegidos"] == {"amazon": ["P2", "P1"]} and i["pasos"]["seleccionar"]["relevantes"] == 3 and i["pasos"]["seleccionar"]["estado"] == "hecho"
    assert datos.productos_nicho("acme", eid, solo_sin_juzgar=True) == []
    t = cola_falsa[-1]
    assert t["tipo"] == "nicho_recolectar" and t["payload"]["fuente"] == "amazon" and t["payload"]["investigacion"] is True and t["max_intentos"] == 1
    assert [p["fuente_id"] for p in t["payload"]["params"]["productos"]] == ["P2", "P1"] and t["payload"]["params"]["resenas_por_producto"] == 100
    assert t["payload"]["params"]["pais"] == "MX" and t["payload"]["params"]["productos"][0]["titulo"] == "Producto 2"
    assert i["estado"] == "resenas"


def test_seleccionar_con_dos_variantes_ya_traidas_no_se_detiene(base_temporal, cola_falsa, monkeypatch):
    """Dos variantes del mismo anuncio, ya traídas en una investigación anterior, son lo único del nicho: la
    selección elige una (no se detiene con «no se encontraron productos del nicho») y el paso de reseñas queda
    vacío, sin encolar ninguna recolección ni pagar de nuevo."""
    import json
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="MX", n_comentarios=5)
    _iniciar(datos, eid, plataformas=("amazon",), redes=())
    datos.guardar_productos_nicho("acme", eid, "amazon", [{**p, "n_resenas": 106, "extra": {"variantes": ["P0", "P1"]}} for p in _productos(2)])
    datos.sumar_resenas_traidas("acme", eid, "amazon", {"P0": 10, "P1": 10})
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:amazon": {"estado": "hecho"}}})
    ids = {p["fuente_id"]: p["id"] for p in datos.productos_nicho("acme", eid)}
    _claude(monkeypatch, [(json.dumps({"productos": [{"id": ids["P0"], "relevante": True, "motivo": "sí"},
                                                     {"id": ids["P1"], "relevante": True, "motivo": "sí"}]}), 900, 60)])
    ti.ejecutar_seleccionar(_tarea("acme", eid, "nicho_inv_seleccionar"))
    i = datos.investigacion("acme", eid)
    assert i["elegidos"] == {"amazon": ["P0"]} and "productos del nicho" not in (i.get("detenida_por") or "")
    assert i["pasos"]["resenas:amazon"]["estado"] == "vacio"
    assert not [t for t in cola_falsa if t["tipo"] == "nicho_recolectar"]


def test_seleccionar_sin_relevantes_detiene(base_temporal, cola_falsa, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",), redes=())
    datos.guardar_productos_nicho("acme", eid, "amazon", _productos(1))
    pid = datos.productos_nicho("acme", eid)[0]["id"]
    _claude(monkeypatch, [('{"productos": [{"id": %d, "relevante": false, "motivo": "no"}]}' % pid, 100, 10)])
    ti.ejecutar_seleccionar(_tarea("acme", eid, "nicho_inv_seleccionar"))
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and "nicho" in i["detenida_por"] and cola_falsa == []


def test_avanzar_salta_resenas_sin_productos_y_redes_sin_llave_y_para_sin_comentarios(base_temporal, cola_falsa, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("meli",), redes=("reddit", "youtube"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a", "b"], "elegidos": {},
                                                         "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:meli": {"estado": "vacio"}, "seleccionar": {"estado": "hecho"}}})
    assert ti.avanzar("acme", eid) is None
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["resenas:meli"]["estado"] == "vacio" and i["pasos"]["redes:reddit"]["estado"] == "saltado" and i["pasos"]["redes:youtube"]["estado"] == "saltado"
    assert i["estado"] == "detenida" and "20" in i["detenida_por"] and cola_falsa == []
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    eid2 = _estudio(datos, pais="MX", n_comentarios=25)
    _iniciar(datos, eid2, plataformas=(), redes=("youtube",))
    datos.actualizar_investigacion("acme", eid2, lambda x: {**x, "consultas": ["a", "b"], "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "seleccionar": {"estado": "hecho"}}})
    assert ti.avanzar("acme", eid2) == "redes:youtube"
    t = cola_falsa[-1]
    assert t["tipo"] == "nicho_recolectar" and t["payload"]["fuente"] == "youtube" and t["payload"]["params"]["palabras_clave"] == "a | b" and t["payload"]["params"]["region"] == "SE"
    datos.actualizar_investigacion("acme", eid2, lambda x: {**x, "pasos": {**x["pasos"], "redes:youtube": {"estado": "hecho", "nuevos": 30}}})
    assert ti.avanzar("acme", eid2) == "generar"
    t = cola_falsa[-1]
    assert t["tipo"] == "nicho_generar_avatares" and t["payload"]["auto"] is True and t["payload"]["tope_usd"] == 9.0
    datos.archivar_estudio("acme", eid2)
    datos.actualizar_investigacion("acme", eid2, lambda x: {**x, "estado": "generando", "pasos": {**x["pasos"], "generar": {"estado": "pendiente"}}})
    assert ti.avanzar("acme", eid2) is None and datos.investigacion("acme", eid2)["detenida_por"] == "estudio archivado"


def test_recolectar_como_paso_anota_reseñas_traidas_y_avanza(base_temporal, cola_falsa, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti, nicho as tn
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("meli",), redes=())
    datos.guardar_productos_nicho("acme", eid, "meli", _productos(2, "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a"], "elegidos": {"meli": ["P0", "P1"]},
                                                         "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:meli": {"estado": "hecho"}, "seleccionar": {"estado": "hecho"}}})

    class F(_Plat):
        def recolectar(self, params, avanzar=None):
            self.run_id, self.corridas = "run_r", [{"run_id": "run_r"}]
            for k in range(3):
                self.resultados += 1
                self.conteo_por_producto["P0"] = self.conteo_por_producto.get("P0", 0) + 1
                yield {"fuente_id": f"r{k}", "texto": f"Reseña {k}: se me quitó el dolor.", "url": None, "contexto": "Producto 0", "puntuacion": 5, "fecha": None,
                       "extra": {"producto": "P0", "plataforma": "meli"}}
    monkeypatch.setattr(tn.fuentes_registro, "por_tipo", lambda t: (lambda: F(t)))
    assert ti.avanzar("acme", eid) == "resenas:meli"
    t = cola_falsa[-1]
    assert t["payload"]["params"]["productos"][0]["fuente_id"] == "P1"                    # más reseñas primero
    msg = tn.ejecutar_recolectar({"id": 9, "payload": t["payload"], "job_id": t["job_id"], "intentos": 1, "max_intentos": 1})
    assert "3" in msg
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["resenas:meli"] == {"estado": "hecho", "usd": 0.01, "nuevos": 3, "repetidos": 0, "aviso": ""}
    assert {p["fuente_id"]: p["resenas_traidas"] for p in datos.productos_nicho("acme", eid)} == {"P0": 3, "P1": 0}
    assert datos.contar_por_fuente("acme", eid)["meli"]["total"] == 3
    assert i["estado"] == "detenida" and "20" in i["detenida_por"]                        # 3 comentarios no alcanzan para avatares
    import gastos
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "recoleccion" and g["extra"]["actor"] == "x~resenas" and g["extra"]["corridas"] == ["run_r"]


def test_generar_auto_respeta_el_tope_y_cierra(base_temporal, cola_falsa, monkeypatch):
    from nicho import avatares, datos
    from tareas import nicho as tn
    from tests.test_tareas_nicho import SUB
    eid = _estudio(datos, n_comentarios=25)
    _iniciar(datos, eid, plataformas=(), redes=())
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "estado": "generando", "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "seleccionar": {"estado": "hecho"}, "generar": {"estado": "en_curso"}}})
    monkeypatch.setattr(avatares, "estimar_costo", lambda lista, modelo=None: {"usd": 5.0, "comentarios": 25, "suficientes": True, "referencia": False, "modelo": "m"})
    msg = tn.ejecutar_generar({"id": 3, "payload": {"cliente": "acme", "estudio_id": eid, "auto": True, "tope_usd": 1.0}, "job_id": datos.job_id_generar("acme", eid), "intentos": 1, "max_intentos": 1})
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and "1" in i["detenida_por"] and "5" in i["detenida_por"] and "US$" in msg
    assert datos.estudio("acme", eid)["generacion"] == 0
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "estado": "generando", "detenida_por": None, "pasos": {**x["pasos"], "generar": {"estado": "en_curso"}}})
    monkeypatch.setattr(avatares, "estimar_costo", lambda lista, modelo=None: {"usd": 0.5, "comentarios": 25, "suficientes": True, "referencia": False, "modelo": "m"})
    resultado = {"nucleos": [{"nombre": "Sin dolor", "deseo": "Quiero caminar sin dolor", "resumen": "r", "comentarios": [1], "sub_avatares": [SUB]}],
                 "resumen": {"comentarios": 25, "nucleos": 1, "subs": 1, "con_evidencia": 1, "sin_evidencia": 0, "errores": 0,
                             "tokens_entrada": 3000, "tokens_salida": 900, "usd": 0.015, "modelo": "claude-sonnet-5"}}
    monkeypatch.setattr(avatares, "generar", lambda cliente, estudio_id, avanzar=None: resultado)
    tn.ejecutar_generar({"id": 4, "payload": {"cliente": "acme", "estudio_id": eid, "auto": True, "tope_usd": 1.0}, "job_id": datos.job_id_generar("acme", eid), "intentos": 1, "max_intentos": 1})
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["generar"] == {"estado": "hecho", "usd": 0.015, "nucleos": 1, "subs": 1} and i["estado"] == "lista" and i["terminada_en"]
    assert datos.estudio("acme", eid)["estado"] == "revisando"


def test_hooks_de_interrupcion(base_temporal):
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "pasos": {**x["pasos"], "buscar:amazon": {"estado": "en_curso"}}})
    ti.interrumpida_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "amazon"}), "reinicio del worker (access_token=abc)")
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "interrumpida" and i["pasos"]["buscar:amazon"]["estado"] == "pendiente" and "abc" not in i["ultimo_error"]


# ------------------------------------------------------- fix round 1 (I2) ---

def test_avanzar_se_interrumpe_si_un_manual_choca_con_la_cadena(base_temporal):
    """Ruling 13: el job_id de una recolección se comparte con el botón manual
    "recolectar esta fuente". Si ya hay uno vivo SIN la bandera de la cadena,
    avanzar() no puede seguir por encima de él: se interrumpe con un aviso."""
    import cola as cola_mod
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("meli",), redes=())
    datos.guardar_productos_nicho("acme", eid, "meli", _productos(1, "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a"], "elegidos": {"meli": ["P0"]},
                                                          "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:meli": {"estado": "hecho"},
                                                                    "seleccionar": {"estado": "hecho"}}})
    job_id = datos.job_id_recolectar("acme", eid, "meli")
    cola_mod.encolar("nicho_recolectar", {"cliente": "acme", "estudio_id": eid, "fuente": "meli", "params": {}}, cliente="acme", job_id=job_id)
    assert ti.avanzar("acme", eid) is None
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "interrumpida" and "reanuda" in i["ultimo_error"]


def test_avanzar_no_choca_con_su_propio_job_vivo(base_temporal):
    """El mismo job_id, pero con la bandera `investigacion`: es la cadena
    misma (encolar_recolectar ya lo puso vivo en otra vuelta) -- idempotente,
    la investigación sigue viva y avanzar() devuelve el paso tal cual."""
    import cola as cola_mod
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("meli",), redes=())
    datos.guardar_productos_nicho("acme", eid, "meli", _productos(1, "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a"], "elegidos": {"meli": ["P0"]},
                                                          "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:meli": {"estado": "hecho"},
                                                                    "seleccionar": {"estado": "hecho"}}})
    job_id = datos.job_id_recolectar("acme", eid, "meli")
    cola_mod.encolar("nicho_recolectar", {"cliente": "acme", "estudio_id": eid, "fuente": "meli", "params": {}, "investigacion": True},
                     cliente="acme", job_id=job_id)
    assert ti.avanzar("acme", eid) == "resenas:meli"
    i = datos.investigacion("acme", eid)
    assert i["estado"] not in ("interrumpida", "detenida")


# ------------------------------------------------------- fix round 1 (I3) ---

def test_consultas_falla_y_luego_paga_con_referencia_de_intento(base_temporal, cola_falsa, monkeypatch):
    """Ruling 14: dos intentos de la MISMA tarea -- el primero falla (se
    cobra igual, con su propia referencia), el segundo paga y avanza; las dos
    referencias son distintas y el `usd` del paso es la suma de ambas."""
    import gastos
    from nicho import avatares, datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))
    _claude(monkeypatch, [("no es json", 10, 5)])
    with pytest.raises(avatares.AnalisisInvalido):
        ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas", intentos=1, max_intentos=2))
    _claude(monkeypatch, [('{"consultas": ["a b", "c d"]}', 200, 20)])
    ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas", intentos=2, max_intentos=2))
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["consultas"]["estado"] == "hecho"
    refs = {g["referencia"]: g["usd"] for g in gastos.historial("acme")}
    ref_fallido, ref_ok = f"investigacion:{eid}:consultas:fallido1:t7", f"investigacion:{eid}:consultas:i2:t7"
    assert ref_fallido in refs and ref_ok in refs
    suma = round(refs[ref_fallido] + refs[ref_ok], 4)
    assert i["pasos"]["consultas"]["usd"] == suma == i["gastado_usd"]
    assert cola_falsa[-1]["tipo"] == "nicho_inv_buscar"


def test_consultas_ya_hecho_no_llama_a_claude_de_nuevo(base_temporal, cola_falsa, monkeypatch):
    """Un reintento de la tarea (p. ej. avanzar() reventó DESPUÉS de guardar
    las consultas) con el paso ya `hecho`: no se paga otra vez, solo sigue."""
    import gastos
    from nicho import avatares, datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a b", "c d"],
                                                          "pasos": {**x["pasos"], "consultas": {"estado": "hecho", "usd": 0.01}}})
    llamado = []
    monkeypatch.setattr(avatares, "_llamar", lambda *a, **k: llamado.append(1))
    msg = ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas", intentos=2, max_intentos=2))
    assert llamado == [] and gastos.historial("acme") == [] and "a b" in msg
    assert cola_falsa[-1]["tipo"] == "nicho_inv_buscar"


# --------------------------------------------------- fix round 1 (Ruling 16) ---

def test_avanzar_sin_plataformas_salta_seleccionar(base_temporal, cola_falsa, monkeypatch):
    """Sin ninguna plataforma buscada no hay productos que juzgar: seleccionar
    queda `vacio` sin llamar a Claude, y la cadena sigue con las redes."""
    from nicho import datos
    from tareas import investigacion as ti
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=(), redes=("youtube",))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a", "b"], "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}}})
    assert ti.avanzar("acme", eid) == "redes:youtube"
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["seleccionar"]["estado"] == "vacio" and i["pasos"]["seleccionar"]["aviso"] == "sin plataformas"
    assert cola_falsa[-1]["tipo"] == "nicho_recolectar" and cola_falsa[-1]["payload"]["fuente"] == "youtube"


# --------------------------------------------------- fix round 1 (Ruling 17) ---

def test_buscar_fuente_no_construye_deja_error_y_sigue(base_temporal, cola_falsa, monkeypatch):
    """Si ni siquiera se puede construir la fuente (adentro del try, R17), el
    paso igual cierra `error` -- nada que cobrar -- y la cadena sigue con la
    siguiente plataforma."""
    import gastos
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("amazon", "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a"], "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}}})

    def _fabrica(t):
        def _revienta():
            raise RuntimeError("no se pudo crear la fuente")
        return _revienta
    monkeypatch.setattr(ti.fuentes_registro, "por_tipo", _fabrica)
    with pytest.raises(RuntimeError):
        ti.ejecutar_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "amazon"}, intentos=1, max_intentos=1))
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["buscar:amazon"]["estado"] == "error"
    assert gastos.historial("acme") == []
    assert cola_falsa[-1]["tipo"] == "nicho_inv_buscar" and cola_falsa[-1]["payload"]["plataforma"] == "meli"
    import tareas
    from tareas import investigacion  # noqa: F401
    for t in ("nicho_inv_consultas", "nicho_inv_buscar", "nicho_inv_seleccionar"):
        assert t in tareas.REGISTRO and t in tareas.AL_INTERRUMPIR


# ---------------------------------------------------------------- ola final ---

def test_si_avanzar_revienta_la_cadena_queda_interrumpida(base_temporal, cola_falsa, monkeypatch):
    """F2: el paso ya se cerró pero no se pudo encolar el siguiente -> interrumpida
    (con Reanudar) y la tarea que hizo su parte termina bien."""
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))
    _claude(monkeypatch, [('{"consultas": ["tofflor", "mjuka tofflor"]}', 700, 40)])

    def _revienta(cliente, estudio_id):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(ti, "avanzar", _revienta)
    assert ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas"))                  # no lanza
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["consultas"]["estado"] == "hecho" and i["estado"] == "interrumpida" and "locked" in i["ultimo_error"]
    assert inv.puede_reanudar(i["estado"])


def test_seleccion_revienta_despues_de_pagar(base_temporal, cola_falsa, monkeypatch):
    """F2: una escritura que revienta después de pagar Claude en el último intento
    deja la cadena interrumpida; con intentos por delante, el reintento la retoma."""
    import gastos
    from nicho import datos
    from tareas import investigacion as ti
    for ultimo in (False, True):
        eid = _estudio(datos)
        _iniciar(datos, eid, plataformas=("amazon",), redes=())
        datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a", "b"],
                                                                "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:amazon": {"estado": "hecho"}}})
        datos.guardar_productos_nicho("acme", eid, "amazon", _productos(2))
        ids = [p["id"] for p in datos.productos_nicho("acme", eid)]
        _claude(monkeypatch, [('{"productos": [' + ", ".join(f'{{"id": {x}, "relevante": true, "motivo": "m"}}' for x in ids) + ']}', 900, 60)])

        def _revienta(*a, **k):
            raise RuntimeError("database is locked")
        monkeypatch.setattr(ti.datos, "marcar_relevancia", _revienta)
        antes = len(gastos.historial("acme"))
        with pytest.raises(RuntimeError):
            ti.ejecutar_seleccionar(_tarea("acme", eid, "nicho_inv_seleccionar", intentos=2 if ultimo else 1, max_intentos=2))
        monkeypatch.undo()
        i = datos.investigacion("acme", eid)
        assert len(gastos.historial("acme")) == antes + 1                                          # lo pagado quedó anotado una vez
        assert (i["estado"] == "interrumpida") is ultimo and i["pasos"]["seleccionar"]["estado"] == "en_curso"


def test_red_de_la_cadena_solo_si_el_paso_quedo_abierto(base_temporal):
    """F2: si la tarea sale con error en su último intento sin cerrar su paso, la
    investigación queda interrumpida; si el paso ya se cerró (tienda caída que
    siguió la cadena), no se toca."""
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))

    @ti.red_de_la_cadena(lambda p: "consultas")
    def _falla(tarea):
        raise RuntimeError("se cayó al empezar")
    with pytest.raises(RuntimeError):
        _falla(_tarea("acme", eid, "x", intentos=1, max_intentos=2))                             # con intentos por delante: nada
    assert datos.investigacion("acme", eid)["estado"] == "consultas"
    with pytest.raises(RuntimeError):
        _falla(_tarea("acme", eid, "x", intentos=2, max_intentos=2))
    assert datos.investigacion("acme", eid)["estado"] == "interrumpida"
    eid2 = _estudio(datos)
    _iniciar(datos, eid2, plataformas=("amazon",))
    datos.actualizar_investigacion("acme", eid2, lambda x: inv.marcar_paso(inv.marcar_paso(x, "consultas", "hecho"), "buscar:amazon", "error"))

    @ti.red_de_la_cadena(lambda p: "buscar:amazon")
    def _tienda_caida(tarea):
        raise RuntimeError("actor caído")
    with pytest.raises(RuntimeError):
        _tienda_caida(_tarea("acme", eid2, "x", intentos=1, max_intentos=1))
    assert datos.investigacion("acme", eid2)["estado"] != "interrumpida"


def test_consultas_y_busqueda_dentro_del_tope_aprobado(base_temporal, cola_falsa, monkeypatch):
    """F3: Claude recibe el tope aprobado y la búsqueda nunca usa más consultas."""
    from nicho import avatares, datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "topes": {**x["topes"], "consultas": 1}})
    prompts = []

    def _llamar(texto, max_tokens):
        prompts.append(texto)
        return '{"consultas": ["uno", "dos", "tres"]}', 100, 10
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas"))
    assert datos.investigacion("acme", eid)["consultas"] == ["uno"] and "de 1 a 1" in prompts[-1]
    eid2 = _estudio(datos, pais="MX")
    _iniciar(datos, eid2, plataformas=("amazon",))
    datos.actualizar_investigacion("acme", eid2, lambda x: {**x, "consultas": ["a", "b", "c", "d"], "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}}})
    vistas = []

    class F(_Plat):
        def buscar(self, consultas, pais, n, avanzar=None):
            vistas.append(list(consultas))
            return iter(())
    monkeypatch.setattr(ti.fuentes_registro, "por_tipo", lambda t: (lambda: F(t)))
    ti.ejecutar_buscar(_tarea("acme", eid2, "nicho_inv_buscar", {"plataforma": "amazon"}, intentos=1, max_intentos=1))
    assert vistas == [["a", "b", "c"]]                                                            # tope por defecto: 3


def test_seleccion_sin_nada_por_juzgar_no_paga(base_temporal, cola_falsa, monkeypatch):
    """Reintento con todo ya juzgado: no se llama a Claude ni se anota gasto."""
    import gastos
    from nicho import avatares, datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",), redes=())
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a", "b"],
                                                            "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:amazon": {"estado": "hecho"}}})
    datos.guardar_productos_nicho("acme", eid, "amazon", _productos(2))
    datos.marcar_relevancia("acme", eid, {p["id"]: {"relevante": True, "motivo": "m"} for p in datos.productos_nicho("acme", eid)})
    monkeypatch.setattr(avatares, "_llamar", lambda *a, **k: pytest.fail("no debía llamar a Claude"))
    antes = len(gastos.historial("acme"))
    ti.ejecutar_seleccionar(_tarea("acme", eid, "nicho_inv_seleccionar"))
    i = datos.investigacion("acme", eid)
    assert len(gastos.historial("acme")) == antes and i["pasos"]["seleccionar"]["estado"] == "hecho" and i["elegidos"]["amazon"]


@pytest.mark.parametrize('paso,tipo', [('consultas', 'nicho_inv_consultas'), ('seleccionar', 'nicho_inv_seleccionar')])
def test_pnd190_fallo_unico_y_reintento_manual(base_temporal, monkeypatch, paso, tipo):
    import cola
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=('amazon',), redes=())
    if paso == 'seleccionar':
        datos.guardar_productos_nicho('acme', eid, 'amazon', _productos(1))
        datos.actualizar_investigacion('acme', eid, lambda x: inv.marcar_paso(inv.marcar_paso(x, 'consultas', 'hecho'), 'buscar:amazon', 'hecho'))
    llamadas = []
    def fallo(*a):
        llamadas.append(1)
        raise RuntimeError('fallo simulado')
    nombre = 'consultas_por_idioma_con_claude' if paso == 'consultas' else 'seleccion_con_claude'
    monkeypatch.setattr(inv, nombre, fallo)
    assert ti.avanzar('acme', eid) == paso
    job = datos.job_id_inv('acme', eid, paso)
    t = cola.reclamar()
    assert t['max_intentos'] == 1
    with pytest.raises(RuntimeError, match='fallo simulado'):
        getattr(ti, 'ejecutar_' + paso)(t)
    assert cola.fallar(t['id'], 'fallo simulado') == 'error'
    assert cola.reclamar() is None
    i = datos.investigacion('acme', eid)
    assert i['estado'] == 'detenida' and 'fallo simulado' in i['detenida_por']
    datos.actualizar_investigacion('acme', eid, inv.reanudar)
    assert ti.avanzar('acme', eid) == paso
    assert cola.consultar_por_job(job)['id'] != t['id']
    assert llamadas == [1]


@pytest.mark.parametrize('paso', ['consultas', 'seleccionar'])
def test_pnd190_reanudar_con_datos_pagados_no_llama_claude(base_temporal, cola_falsa, monkeypatch, paso):
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=('amazon',), redes=())
    def prohibido(*a):
        pytest.fail('Claude se pagó otra vez')
    monkeypatch.setattr(inv, 'consultas_por_idioma_con_claude', prohibido)
    monkeypatch.setattr(inv, 'seleccion_con_claude', prohibido)
    if paso == 'consultas':
        datos.actualizar_investigacion('acme', eid, lambda x: {**inv.marcar_paso(x, paso, 'hecho'), 'consultas': ['ya pagada'], 'estado': 'interrumpida'})
    else:
        datos.guardar_productos_nicho('acme', eid, 'amazon', _productos(1))
        prod = datos.productos_nicho('acme', eid)[0]
        datos.marcar_relevancia('acme', eid, {prod['id']: {'relevante': True, 'motivo': 'pagado'}})
        datos.actualizar_investigacion('acme', eid, lambda x: {**inv.marcar_paso(inv.marcar_paso(inv.marcar_paso(x, 'consultas', 'hecho'), 'buscar:amazon', 'hecho'), paso, 'en_curso'), 'estado': 'interrumpida'})
    datos.actualizar_investigacion('acme', eid, inv.reanudar)
    getattr(ti, 'ejecutar_' + paso)(_tarea('acme', eid, 'nicho_inv_' + paso, max_intentos=1))
    assert cola_falsa[-1]['tipo'] == ('nicho_inv_buscar' if paso == 'consultas' else 'nicho_recolectar')

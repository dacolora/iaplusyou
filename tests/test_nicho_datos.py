import pytest


def _c(i, texto=None, **extra):
    """Comentario normalizado mínimo (lo que produce nicho.fuentes.base.normalizar_comentario)."""
    return {"fuente_id": f"c{i}", "texto": texto or f"Comentario número {i}: la garrafa pesa demasiado y gotea.",
            "url": None, "contexto": None, "puntuacion": None, "fecha": None, "extra": {}, **extra}


def test_estudio_crear_listar_editar_archivar(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "Detergente Suecia", producto="Cápsulas sin plástico", tema="lavar sin cargar",
                              idioma="sv", catalogo_id="capsulas")
    e = datos.estudio("acme", eid)
    assert e["nombre"] == "Detergente Suecia" and e["idioma"] == "sv" and e["estado"] == "armando"
    assert e["generacion"] == 0 and e["archivado"] is False and e["catalogo_id"] == "capsulas"
    assert e["comentarios_total"] == 0 and e["fuentes"] == {} and e["avatares_aprobados"] == 0
    assert datos.actualizar_estudio("acme", eid, tema="otro tema") and datos.estudio("acme", eid)["tema"] == "otro tema"
    assert datos.estudio("otro", eid) is None and datos.estudios("otro") == []
    datos.archivar_estudio("acme", eid)
    assert datos.estudios("acme") == [] and len(datos.estudios("acme", incluir_archivados=True)) == 1


def test_estudio_valida(base_temporal):
    from nicho import datos
    with pytest.raises(datos.ErrorDatos):
        datos.crear_estudio("acme", "   ")
    eid = datos.crear_estudio("acme", "X", idioma="ZZZZZZZ")
    assert datos.estudio("acme", eid)["idioma"] == "es"          # idioma raro -> español
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_estudio("acme", eid, cliente="otro")     # campo no editable
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_estudio("acme", eid, estado="volando")


def test_comentarios_agregar_dedup_paginar_excluir_borrar(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    r = datos.agregar_comentarios("acme", eid, "texto", [_c(1), _c(2), _c(1)])
    assert r == {"nuevos": 2, "repetidos": 1}
    assert datos.agregar_comentarios("acme", eid, "texto", [_c(2)]) == {"nuevos": 0, "repetidos": 1}
    assert datos.agregar_comentarios("acme", eid, "csv", [_c(2), _c(3, puntuacion=5, url="https://x/y")]) == {"nuevos": 2, "repetidos": 0}
    e = datos.estudio("acme", eid)
    assert e["comentarios_total"] == 4 and e["fuentes"] == {"texto": {"total": 2, "excluidos": 0}, "csv": {"total": 2, "excluidos": 0}}
    pagina = datos.comentarios("acme", eid, por_pagina=3)
    assert pagina["total"] == 4 and pagina["paginas"] == 2 and len(pagina["items"]) == 3
    assert pagina["items"][0]["fuente"] == "csv" and pagina["items"][0]["puntuacion"] == 5    # más nuevo primero
    assert datos.comentarios("acme", eid, fuente="texto")["total"] == 2
    cid = pagina["items"][0]["id"]
    assert datos.excluir_comentario("acme", cid) and datos.comentario("acme", cid)["excluido"] is True
    assert datos.contar_por_fuente("acme", eid)["csv"] == {"total": 2, "excluidos": 1}
    assert [c["id"] for c in datos.comentarios_para_generar("acme", eid)] == sorted(c["id"] for c in datos.comentarios("acme", eid)["items"] if c["id"] != cid)
    assert datos.estudio("acme", eid)["comentarios_activos"] == 3
    assert datos.excluir_comentario("acme", cid, excluido=False) and datos.comentario("acme", cid)["excluido"] is False
    assert datos.borrar_fuente("acme", eid, "csv") == 2 and datos.estudio("acme", eid)["comentarios_total"] == 2
    assert datos.comentario("otro", cid) is None and datos.excluir_comentario("otro", cid) is False


def test_comentarios_valida_fuente_y_estudio(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_comentarios("acme", eid, "magia", [_c(1)])
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_comentarios("acme", 999, "texto", [_c(1)])
    assert datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": "", "texto": "x"}, {"fuente_id": "a", "texto": "  "}]) == {"nuevos": 0, "repetidos": 0}


def test_extra_y_recolecciones(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    assert datos.actualizar_extra_estudio("acme", eid, lambda x: {**x, "ultimo_error": "falló"})["ultimo_error"] == "falló"
    assert datos.actualizar_extra_estudio("acme", 999, lambda x: x) is None
    for i in range(datos.MAX_RECOLECCIONES + 3):
        datos.registrar_recoleccion("acme", eid, {"fuente": "texto", "nuevos": i, "repetidos": 0})
    rec = datos.estudio("acme", eid)["extra"]["recolecciones"]
    assert len(rec) == datos.MAX_RECOLECCIONES and rec[-1]["nuevos"] == datos.MAX_RECOLECCIONES + 2 and rec[-1]["fecha"]


def test_recalcular(base_temporal, monkeypatch):
    from nicho import datos
    import cola
    eid = datos.crear_estudio("acme", "X")
    assert datos.recalcular("acme", eid) == "armando"
    monkeypatch.setattr(cola, "consultar_por_job", lambda job_id: {"estado": "en_curso"} if job_id == datos.job_id_generar("acme", eid) else None)
    assert datos.recalcular("acme", eid) == "generando" and datos.estudio("acme", eid)["estado"] == "generando"
    assert datos.recalcular("acme", eid, tarea_viva=False) == "armando"
    assert datos.recalcular("acme", 999) is None
    assert datos.job_id_generar("acme", eid) == f"nicho:acme:{eid}:generar"


SUB = {
    "base": "emocion", "nombre": "Melissa / La que regala con cabeza", "deseo": "Quiero regalar algo útil y personal",
    "demografia": "Mujer de 30 a 50, ciudad", "edad_rango": "30-50", "emocion": "Presión por no quedar mal",
    "identidad": {"quiere_que_vean": "detallista", "cree_de_si": "generosa", "quiere_lograr": "ser la que acierta"},
    "soluciones_previas": [{"que": "Tarjetas de regalo", "por_que_fallo": ["impersonales", "sin valor duradero"]}],
    "situaciones": ["Comprando a última hora", "Buscando en el centro comercial"],
    "comportamiento": "Compra lo seguro aunque no emocione",
    "conciencia": {"nivel": "inconsciente", "detalle": "No sabe que existe algo mejor"},
    "encaje_producto": "Pantuflas con soporte: útil y personal", "tono": "Cálido, con culpa leve",
    "palabras_clave": ["regalo", "detalle"], "evidencia": [{"comentario_id": 1, "cita": "la garrafa pesa demasiado"}],
    "sin_evidencia": False,
}


def _estudio_con_generacion(datos, n_subs=2):
    eid = datos.crear_estudio("acme", "X", producto="Pantuflas")
    datos.agregar_comentarios("acme", eid, "texto", [_c(i) for i in range(1, 4)])
    nucleos = [{"nombre": "Regalo con cabeza", "deseo": "Quiero regalar bien", "resumen": "Quienes regalan",
                "sub_avatares": [dict(SUB, nombre=f"Sub {i}") for i in range(n_subs)]},
               {"nombre": "Pies cansados", "deseo": "Quiero descansar los pies", "resumen": "", "sub_avatares": [], "error": "JSON inválido"}]
    return eid, datos.guardar_generacion("acme", eid, nucleos, {"comentarios": 3, "usd": 0.04})


def test_guardar_generacion_y_listar(base_temporal):
    from nicho import datos
    eid, r = _estudio_con_generacion(datos)
    assert r == {"generacion": 1, "nucleos": 2, "subs": 2}
    e = datos.estudio("acme", eid)
    assert e["estado"] == "revisando" and e["generacion"] == 1 and e["extra"]["ultima_generacion"]["usd"] == 0.04
    assert e["extra"]["ultima_generacion"]["generacion"] == 1 and e["avatares_total"] == 2 and e["avatares_aprobados"] == 0
    nucleos = datos.avatares("acme", eid)
    assert [n["nombre"] for n in nucleos] == ["Regalo con cabeza", "Pies cansados"]
    assert nucleos[1]["extra"] == {"error": "JSON inválido"} and nucleos[1]["subs"] == []
    s = nucleos[0]["subs"][0]
    assert s["tipo"] == "sub" and s["padre_id"] == nucleos[0]["id"] and s["estado"] == "propuesto" and s["generacion"] == 1
    assert s["identidad"]["cree_de_si"] == "generosa" and s["soluciones_previas"][0]["por_que_fallo"] == ["impersonales", "sin valor duradero"]
    assert s["conciencia"] == {"nivel": "inconsciente", "detalle": "No sabe que existe algo mejor"} and s["sin_evidencia"] is False
    assert datos.avatar("acme", s["id"])["nombre"] == "Sub 0" and datos.avatar("otro", s["id"]) is None
    assert datos.avatares("otro", eid) == []


def test_regenerar_conserva_aprobados(base_temporal):
    from nicho import datos
    eid, _ = _estudio_con_generacion(datos)
    nucleos = datos.avatares("acme", eid)
    aprobado = nucleos[0]["subs"][0]
    pid = datos.aprobar_avatar("acme", aprobado["id"])
    datos.descartar_avatar("acme", nucleos[0]["subs"][1]["id"])
    r = datos.guardar_generacion("acme", eid, [{"nombre": "Nuevo", "deseo": "Quiero lo nuevo", "resumen": "", "sub_avatares": [SUB]}])
    assert r["generacion"] == 2
    lista = datos.avatares("acme", eid)
    assert [n["nombre"] for n in lista] == ["Regalo con cabeza", "Nuevo"]            # "Pies cansados" (sin aprobados) se fue
    assert [s["estado"] for s in lista[0]["subs"]] == ["aprobado"] and lista[0]["subs"][0]["persona_id"] == pid
    assert lista[1]["subs"][0]["generacion"] == 2 and lista[1]["generacion"] == 2
    assert datos.estudio("acme", eid)["generacion"] == 2


def test_aprobar_crea_actualiza_y_descartar_archiva(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    eid, _ = _estudio_con_generacion(datos)
    sub = datos.avatares("acme", eid)[0]["subs"][0]
    pid = datos.aprobar_avatar("acme", sub["id"])
    p = sd.persona("acme", pid)
    assert p["origen"] == "investigada" and p["nombre"] == "Sub 0" and p["resumen"] == "Quiero regalar algo útil y personal"
    assert p["edad_rango"] == "30-50" and p["tono"] == "Cálido, con culpa leve" and p["senales_visuales"] == SUB["situaciones"]
    assert p["palabras_clave"] == ["regalo", "detalle"] and p["color"] in datos.COLORES
    assert "Mujer de 30 a 50" in p["descripcion"] and "Usó Tarjetas de regalo: impersonales, sin valor duradero" in p["descripcion"]
    assert p["extra"]["avatar_id"] == sub["id"] and p["extra"]["conciencia"]["nivel"] == "inconsciente" and p["extra"]["identidad"]["quiere_lograr"] == "ser la que acierta"
    a = datos.avatar("acme", sub["id"])
    assert a["estado"] == "aprobado" and a["persona_id"] == pid
    datos.actualizar_avatar("acme", sub["id"], nombre="Melissa", tono="Directo")
    assert sd.persona("acme", pid)["nombre"] == "Sub 0"                 # editar no toca la persona...
    assert datos.aprobar_avatar("acme", sub["id"]) == pid               # ...hasta volver a aprobar: misma persona
    assert sd.persona("acme", pid)["nombre"] == "Melissa" and sd.persona("acme", pid)["tono"] == "Directo"
    assert len(sd.personas("acme", incluir_archivadas=True)) == 1
    assert datos.descartar_avatar("acme", sub["id"]) and datos.avatar("acme", sub["id"])["estado"] == "descartado"
    assert sd.persona("acme", pid)["archivada"] is True
    assert datos.aprobar_avatar("acme", sub["id"]) == pid and sd.persona("acme", pid)["archivada"] is False
    nucleo = datos.avatares("acme", eid)[0]
    with pytest.raises(datos.ErrorDatos):
        datos.aprobar_avatar("acme", nucleo["id"])                      # el núcleo no se aprueba
    with pytest.raises(datos.ErrorDatos):
        datos.aprobar_avatar("acme", 999)


def test_actualizar_avatar_valida(base_temporal):
    from nicho import datos
    eid, _ = _estudio_con_generacion(datos)
    sid = datos.avatares("acme", eid)[0]["subs"][0]["id"]
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_avatar("acme", sid, estado="aprobado")          # no editable por acá
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_avatar("acme", sid, nombre="  ")
    assert datos.actualizar_avatar("acme", sid, base="rara", conciencia={"nivel": "x", "detalle": "d"},
                                   soluciones_previas=[{"que": "", "por_que_fallo": ["a"]}, {"que": "Pods", "por_que_fallo": "no lista"}],
                                   identidad={"cree_de_si": "fuerte", "otra": "x"}, palabras_clave="no lista")
    a = datos.avatar("acme", sid)
    assert a["base"] == "emocion" and a["conciencia"] == {"nivel": "", "detalle": "d"}
    assert a["soluciones_previas"] == [{"que": "Pods", "por_que_fallo": []}]
    assert a["identidad"] == {"quiere_que_vean": "", "cree_de_si": "fuerte", "quiere_lograr": ""} and a["palabras_clave"] == []
    assert datos.actualizar_avatar("otro", sid, nombre="X") is False

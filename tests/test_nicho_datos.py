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

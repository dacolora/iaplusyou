"""Avatares del proyecto (spec 2026-09-29 §1): estudio oculto, avatares escritos a mano, personas sin avatar y la lista única."""
import pytest

FICHA = {"nombre": "Carla / La que camina todo el día", "deseo": "Quiero llegar a la noche sin dolor", "demografia": "Mujer 40-50, enfermera",
         "edad_rango": "40-50", "emocion": "Agotamiento", "identidad": {"quiere_que_vean": "fuerte", "cree_de_si": "aguanta todo", "quiere_lograr": "cuidar sin romperse"},
         "encaje_producto": "Pantuflas que alivian el talón", "soluciones_previas": [{"que": "Plantillas", "por_que_fallo": ["duras"]}],
         "situaciones": ["Turno de 12 horas", "Al llegar a casa"], "comportamiento": "Se quita los zapatos en el carro",
         "conciencia": {"nivel": "consciente_de_la_solucion", "detalle": "busca pantuflas"}, "tono": "Práctico", "palabras_clave": ["talón", "turno", "alivio"]}


def _estudio_con_subs(datos):
    eid = datos.crear_estudio("acme", "Tofflor", tema="t")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: me duele el talón al final del turno."} for i in range(25)])
    ids = [c["id"] for c in datos.comentarios_para_generar("acme", eid)]
    sub = dict(FICHA, base="emocion", evidencia=[{"comentario_id": ids[0], "cita": "me duele el talón"}, {"comentario_id": ids[1], "cita": "al final del turno"}])
    datos.guardar_generacion("acme", eid, [{"nombre": "Sin dolor", "deseo": "Quiero caminar sin dolor", "resumen": "r",
                                            "sub_avatares": [sub, dict(sub, nombre="Incompleta", tono="", situaciones=["una"])]}])
    return eid, datos.avatares("acme", eid)[0]["subs"]


def test_estudio_oculto_y_avatar_escrito_a_mano(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    eid, nid = datos.estudio_manual("acme")
    assert datos.estudio_manual("acme") == (eid, nid) and datos.es_manual(datos.estudio("acme", eid))
    assert datos.estudios("acme") == []                                                  # el oculto no se lista
    aid = datos.crear_avatar_manual("acme", FICHA)
    a = datos.avatar("acme", aid)
    assert a["estado"] == "aprobado" and a["estudio_id"] == eid and a["padre_id"] == nid and a["persona_id"]
    p = sd.persona("acme", a["persona_id"])
    assert p["origen"] == "manual" and p["nombre"] == FICHA["nombre"] and p["extra"]["avatar_id"] == aid
    with pytest.raises(datos.ErrorDatos):
        datos.crear_avatar_manual("acme", {"nombre": " "})
    assert len(datos.estudios("acme", incluir_archivados=True)) == 0


def test_aprobar_funde_el_extra_de_la_persona(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    eid, subs = _estudio_con_subs(datos)
    pid = datos.aprobar_avatar("acme", subs[0]["id"])
    assert sd.persona("acme", pid)["origen"] == "investigada"
    sd.actualizar_persona("acme", pid, extra={**sd.persona("acme", pid)["extra"], "otra_cosa": 1})
    datos.actualizar_avatar("acme", subs[0]["id"], tono="Muy práctico")
    datos.aprobar_avatar("acme", subs[0]["id"])
    p = sd.persona("acme", pid)
    assert p["tono"] == "Muy práctico" and p["extra"]["otra_cosa"] == 1 and p["extra"]["avatar_id"] == subs[0]["id"]


def test_avatar_desde_persona_sin_avatar(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    pid = sd.crear_persona("acme", "Premium", resumen="Quiere lo mejor", descripcion="Hombre 30-40, ciudad", tono="Seguro",
                           senales_visuales=["En la oficina"], palabras_clave=["calidad"], origen="sugerida_ia",
                           extra={"conciencia": {"nivel": "consciente_del_producto", "detalle": "x"}})
    aid = datos.avatar_desde_persona("acme", pid)
    a = datos.avatar("acme", aid)
    assert a["persona_id"] == pid and a["estado"] == "aprobado" and a["deseo"] == "Quiere lo mejor" and a["demografia"] == "Hombre 30-40, ciudad"
    assert a["situaciones"] == ["En la oficina"] and a["conciencia"]["nivel"] == "consciente_del_producto"
    assert datos.avatar_desde_persona("acme", pid) == aid                               # una sola vez
    datos.actualizar_avatar("acme", aid, tono="Muy seguro")
    datos.aprobar_avatar("acme", aid)
    assert sd.persona("acme", pid)["origen"] == "sugerida_ia" and sd.persona("acme", pid)["tono"] == "Muy seguro"   # conserva su origen
    with pytest.raises(datos.ErrorDatos):
        datos.avatar_desde_persona("acme", 999)


def test_lista_y_resumen_de_avatares(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    eid, subs = _estudio_con_subs(datos)
    manual = datos.crear_avatar_manual("acme", dict(FICHA, nombre="Marta / La escrita a mano"))
    suelta = sd.crear_persona("acme", "Sprint suelta", resumen="r")
    archivada = sd.crear_persona("acme", "Vieja", resumen="r")
    sd.archivar_persona("acme", archivada)
    datos.aprobar_avatar("acme", subs[0]["id"])
    l = datos.lista_avatares("acme")
    assert [x["avatar"]["id"] for x in l["nuevos"]] == [subs[1]["id"]]
    assert l["nuevos"][0]["faltantes"] == ["situaciones", "tono"] and l["nuevos"][0]["estudio"]["nombre"] == "Tofflor" and l["nuevos"][0]["nucleo"] == "Sin dolor"
    nombres = [(x["persona"] or {}).get("nombre") for x in l["aprobados"]]
    assert nombres == sorted(nombres, key=str.lower) and set(nombres) == {"Marta / La escrita a mano", FICHA["nombre"], "Sprint suelta"}
    por_nombre = {x["persona"]["nombre"]: x for x in l["aprobados"]}
    assert por_nombre["Marta / La escrita a mano"]["avatar"]["id"] == manual and por_nombre["Marta / La escrita a mano"]["faltantes"] == []   # sin exigir citas
    assert por_nombre[FICHA["nombre"]]["avatar"]["id"] == subs[0]["id"] and por_nombre[FICHA["nombre"]]["faltantes"] == []
    assert por_nombre["Sprint suelta"]["avatar"] is None and "demografia" in por_nombre["Sprint suelta"]["faltantes"]
    assert [x["persona"]["nombre"] for x in l["otros"]] == ["Vieja"]
    datos.descartar_avatar("acme", subs[1]["id"])
    l = datos.lista_avatares("acme")
    assert l["nuevos"] == [] and {x["clave"] for x in l["otros"]} == {f"a{subs[1]['id']}", f"p{archivada}"}
    r = datos.resumen_avatares("acme")
    assert r["aprobados"] == 3 and r["nuevos"] == 0 and r["incompletos"] == 1
    assert {m["nombre"] for m in r["muestra"]} == {"Marta / La escrita a mano", FICHA["nombre"], "Sprint suelta"}
    assert datos.urls_de_comentarios("acme", [subs[0]["evidencia"][0]["comentario_id"]]) == {subs[0]["evidencia"][0]["comentario_id"]: None}

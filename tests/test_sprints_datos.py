import pytest


def test_persona_crear_listar_editar_archivar(base_temporal):
    from sprints import datos
    pid = datos.crear_persona("acme", "Cliente Premium", resumen="Busca calidad", tono="cercano y experto",
                              senales_visuales=["cocina moderna", "luz natural"], palabras_clave=["premium"])
    p = datos.persona("acme", pid)
    assert p["nombre"] == "Cliente Premium" and p["senales_visuales"] == ["cocina moderna", "luz natural"]
    assert p["origen"] == "manual" and p["archivada"] is False
    assert datos.actualizar_persona("acme", pid, tono="directo") and datos.persona("acme", pid)["tono"] == "directo"
    assert datos.personas("otro") == []            # aislamiento por cliente
    assert datos.persona("otro", pid) is None
    datos.archivar_persona("acme", pid)
    assert datos.personas("acme") == [] and len(datos.personas("acme", incluir_archivadas=True)) == 1


def test_persona_valida_nombre_y_origen(base_temporal):
    from sprints import datos
    with pytest.raises(datos.ErrorDatos):
        datos.crear_persona("acme", "   ")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_persona("acme", "X", origen="magia")
    pid = datos.crear_persona("acme", "X")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_persona("acme", pid, nombre="")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_persona("acme", pid, cliente="otro")   # campo no editable


def test_temporada_valida_fechas(base_temporal):
    from sprints import datos
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos", tipo="comercial",
                                mood_visual={"paleta": ["#B3001B"]})
    t = datos.temporada("acme", tid)
    assert t["inicio"] == "2026-11-15" and t["mood_visual"] == {"paleta": ["#B3001B"]}
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "2026-12-31", "2026-11-15")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "ayer", "2026-11-15")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "2026-01-01", "2026-02-01", tipo="rara")
    assert [x["nombre"] for x in datos.temporadas("acme")] == ["Navidad"]
    datos.archivar_temporada("acme", tid)
    assert datos.temporadas("acme") == []


def _base(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", destinos=["es_CO"])
    return pid, tid, sid


def test_sprint_crear_y_validar(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    s = datos.sprint("acme", sid)
    assert s["estado"] == "planeando" and s["destinos"] == ["es_CO"] and s["campanas"] == []
    assert [e["tipo"] for e in s["eventos"]] == ["sprint_creado"]
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "", "2026-10-01", "2026-10-31")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "X", "2026-10-31", "2026-10-01")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "X", "2026-10-01", "2026-10-31", referencias_objetivo_defecto=0)
    assert datos.sprint("otro", sid) is None and datos.sprints("otro") == []


def test_campana_unicidad_y_cantidades(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 10, 25)
    c = datos.campana("acme", cid)
    assert c["persona_nombre"] == "Premium" and c["temporada_nombre"] == "Verano" and c["estado"] == "planeada"
    assert c["referencias_objetivo"] == 5 and c["referencias_total"] == 0 and c["sprint_id"] == sid
    with pytest.raises(datos.CampanaDuplicada) as e:
        datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    assert "campaña 1" in str(e.value)
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 0, 3, referencias_objetivo=8)
    assert datos.campana("acme", cid2)["orden"] == 1 and datos.campana("acme", cid2)["referencias_objetivo"] == 8
    assert datos.combinaciones("acme", sid) == {(pid, "espejo_led", tid), (pid, "espejo_led", tid2)}
    for malo in [dict(n_videos=0, n_imagenes=0), dict(n_videos=-1, n_imagenes=2), dict(n_videos="x", n_imagenes=1)]:
        with pytest.raises(datos.ErrorDatos):
            datos.agregar_campana("acme", sid, pid, "otro", tid, **malo)
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, 999, "otro", tid, 1, 1)        # persona ajena
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, pid, "", tid, 1, 1)           # sin producto
    assert [c["id"] for c in datos.campanas("acme", sid)] == [cid, cid2]
    assert datos.actualizar_campana("acme", cid, n_videos=12)
    assert datos.eliminar_campana("acme", cid2) and len(datos.campanas("acme", sid)) == 1
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert tipos[0] == "campana_eliminada" and "campana_agregada" in tipos


def test_sprints_lista_con_totales(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 10, 25)
    lista = datos.sprints("acme")
    assert len(lista) == 1 and lista[0]["piezas_planeadas"] == 35 and lista[0]["campanas_total"] == 1
    datos.archivar_sprint("acme", sid)
    assert datos.sprints("acme") == [] and len(datos.sprints("acme", incluir_archivados=True)) == 1

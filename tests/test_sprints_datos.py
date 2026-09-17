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

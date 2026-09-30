"""datos de la Parte 3: país del estudio, producto_nicho (tabla de la migración 0016) y extra.investigacion."""
import pytest


def _productos(n=2, consulta="tofflor"):
    return [{"fuente_id": f"B0TEST{i:04d}", "titulo": f"Producto {i}", "marca": "Acme", "precio": 10.0 + i, "moneda": "SEK",
             "estrellas": 4.5, "n_resenas": 100 * (i + 1), "url": f"https://www.amazon.se/dp/B0TEST{i:04d}", "imagen": None,
             "consulta": consulta, "extra": {"vendidos": i}} for i in range(n)]


def test_pais_del_estudio_y_constantes(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", pais="se")
    assert datos.estudio("acme", eid)["pais"] == "SE"
    assert datos.estudio("acme", datos.crear_estudio("acme", "Y", pais="zz"))["pais"] is None
    datos.actualizar_estudio("acme", eid, pais="co")
    assert datos.estudio("acme", eid)["pais"] == "CO"
    datos.actualizar_estudio("acme", eid, pais="")
    assert datos.estudio("acme", eid)["pais"] is None
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_estudio("acme", eid, pais="ZZ")
    assert "SE" in datos.PAISES_ESTUDIO and "CO" in datos.PAISES_ESTUDIO
    assert datos.job_id_inv("acme", eid, "buscar:amazon") == f"nicho:acme:{eid}:inv:buscar:amazon"
    assert set(datos.FUENTES_PLATAFORMA) <= set(datos.FUENTES) and datos.FUENTES_PLATAFORMA == ("amazon", "meli", "tiktok_shop")


def test_productos_nicho_upsert_y_lectura(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", pais="SE")
    r = datos.guardar_productos_nicho("acme", eid, "amazon", _productos(2) + [{"fuente_id": "", "titulo": "sin id"}, {"fuente_id": "B0SINTIT", "titulo": ""}])
    assert r == {"nuevos": 2, "actualizados": 0}
    lista = datos.productos_nicho("acme", eid)
    assert [p["fuente_id"] for p in lista] == ["B0TEST0001", "B0TEST0000"]           # más reseñas primero
    assert lista[0]["relevante"] is None and lista[0]["resenas_traidas"] == 0 and lista[0]["plataforma"] == "amazon"
    assert lista[0]["extra"] == {"vendidos": 1} and lista[0]["consulta"] == "tofflor" and lista[0]["precio"] == 11.0
    datos.marcar_relevancia("acme", eid, {lista[0]["id"]: {"relevante": True, "motivo": "es del nicho"}})
    cambiados = _productos(2)
    cambiados[1]["precio"] = 99.0
    assert datos.guardar_productos_nicho("acme", eid, "amazon", cambiados) == {"nuevos": 0, "actualizados": 2}
    p = datos.productos_nicho("acme", eid)[0]
    assert p["precio"] == 99.0 and p["relevante"] is True and p["motivo"] == "es del nicho"    # el upsert no pisa el juicio
    assert datos.productos_nicho("acme", eid, plataforma="meli") == [] and datos.productos_nicho("otro", eid) == []
    assert [x["fuente_id"] for x in datos.productos_nicho("acme", eid, fuente_ids=["B0TEST0000"])] == ["B0TEST0000"]
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_productos_nicho("acme", eid, "magia", _productos(1))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_productos_nicho("acme", 999, "amazon", _productos(1))


def test_relevancia_y_resenas_traidas(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", pais="CO")
    datos.guardar_productos_nicho("acme", eid, "meli", _productos(3))
    ids = {p["fuente_id"]: p["id"] for p in datos.productos_nicho("acme", eid)}
    n = datos.marcar_relevancia("acme", eid, {ids["B0TEST0000"]: {"relevante": True, "motivo": "sí"},
                                              ids["B0TEST0001"]: {"relevante": False, "motivo": "es otra cosa"}, 999: {"relevante": True, "motivo": "x"}})
    assert n == 2
    assert [p["fuente_id"] for p in datos.productos_nicho("acme", eid, solo_sin_juzgar=True)] == ["B0TEST0002"]
    assert [p["fuente_id"] for p in datos.productos_nicho("acme", eid, solo_relevantes=True)] == ["B0TEST0000"]
    assert datos.sumar_resenas_traidas("acme", eid, "meli", {"B0TEST0001": 40, "B0TEST0002": 5, "NOEXISTE": 1, "B0TEST0000": 0}) == 2
    por_id = {p["fuente_id"]: p["resenas_traidas"] for p in datos.productos_nicho("acme", eid)}
    assert por_id == {"B0TEST0000": 0, "B0TEST0001": 40, "B0TEST0002": 5}
    datos.sumar_resenas_traidas("acme", eid, "meli", {"B0TEST0001": 10})
    assert {p["fuente_id"]: p["resenas_traidas"] for p in datos.productos_nicho("acme", eid)}["B0TEST0001"] == 50


def test_investigacion_en_extra(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", pais="SE")
    assert datos.investigacion("acme", eid) == {} and datos.investigacion("acme", 999) == {}
    inv = datos.iniciar_investigacion("acme", eid, {"version": 1, "estado": "consultas", "aprobado_usd": 5.0, "pasos": {}})
    assert inv["estado"] == "consultas" and datos.investigacion("acme", eid)["aprobado_usd"] == 5.0
    nuevo = datos.actualizar_investigacion("acme", eid, lambda i: {**i, "estado": "buscando", "gastado_usd": 0.02})
    assert nuevo["estado"] == "buscando" and datos.investigacion("acme", eid)["gastado_usd"] == 0.02
    assert datos.actualizar_investigacion("acme", 999, lambda i: i) is None
    inv2 = datos.iniciar_investigacion("acme", eid, {"version": 1, "estado": "consultas", "aprobado_usd": 7.0, "pasos": {}})
    e = datos.estudio("acme", eid)
    assert inv2["aprobado_usd"] == 7.0 and e["extra"]["investigacion"]["aprobado_usd"] == 7.0
    assert [i["aprobado_usd"] for i in e["extra"]["investigaciones_previas"]] == [5.0]
    for k in range(4):
        datos.iniciar_investigacion("acme", eid, {"version": 1, "estado": "consultas", "aprobado_usd": 10.0 + k, "pasos": {}})
    assert len(datos.estudio("acme", eid)["extra"]["investigaciones_previas"]) == 3      # se conservan las últimas 3

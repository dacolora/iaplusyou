"""referentes.datos: único escritor de referente / referente_familia / barrido."""
import pytest
import sqlalchemy as sa


def _anuncio(**extra):
    base = {"anuncio_id": "1931355470987046", "pagina_id": "110920097280290", "fuente": "copycoders",
            "marca": "Lulutox Tea", "url_anuncio": "https://www.facebook.com/ads/library/?id=1931355470987046",
            "url_marca": "https://www.facebook.com/ads/library/?view_all_page_id=110920097280290",
            "titular": "WE'RE SAYING GOODBYE", "idioma": "en", "tipo": "imagen",
            "imagen_origen": "https://cdn.tryatria.com/adfiles/m1931355470987046_x.jpeg",
            "dias": 366, "variantes": 15, "activo": True,
            "etapa": "BOF", "consciencia": "most-aware", "familia": "Price Slash Hero", "dolor": "ninguno-oferta",
            "firma": "Titular gigante estilo ruptura que fabrica urgencia.", "clasificacion": "fuente",
            "extra": {"sweep": "AUG"}}
    base.update(extra)
    return base


def test_tablas_existen_y_anuncio_id_unico(base_temporal):
    import db
    with db.conectar() as con:
        con.execute(db.barrido.insert().values(cliente=None, creado_en=db.ahora(), actualizado_en=db.ahora(),
                                               fuente="copycoders", consulta={}, tope=0, estado="en_cola", extra={}))
        con.execute(db.referente.insert().values(cliente=None, creado_en=db.ahora(), actualizado_en=db.ahora(),
                                                 anuncio_id="1", fuente="copycoders", tipo="imagen",
                                                 estado_imagen="pendiente", clasificacion="fuente", extra={}))
        with pytest.raises(sa.exc.IntegrityError):
            con.execute(db.referente.insert().values(cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(),
                                                     anuncio_id="1", fuente="atria", tipo="imagen",
                                                     estado_imagen="pendiente", clasificacion="pendiente", extra={}))


def test_familia_asegurar_no_duplica_ni_pisa_descripcion(base_temporal):
    from referentes import datos
    a = datos.familia_asegurar("Blame Transplant", "Culpa a otra cosa, no a la persona.")
    b = datos.familia_asegurar("Blame Transplant", "")
    assert a == b
    f = [x for x in datos.familias() if x["nombre"] == "Blame Transplant"][0]
    assert f["descripcion"] == "Culpa a otra cosa, no a la persona." and f["origen"] == "copycoders" and f["n"] == 0
    assert datos.familia_actualizar(a, "Nueva descripción") and datos.familias()[0]["descripcion"] == "Nueva descripción"
    with pytest.raises(datos.ErrorDatos):
        datos.familia_asegurar("   ")


def test_guardar_referente_crea_y_actualiza_sin_reasignar(base_temporal):
    from referentes import datos
    rid, creado = datos.guardar_referente(_anuncio())
    assert creado is True
    r = datos.referente("acme", rid)
    assert r["cliente"] is None and r["estado_imagen"] == "pendiente" and r["clasificacion"] == "fuente"
    assert r["familia"] == "Price Slash Hero" and r["extra"]["sweep"] == "AUG"
    # Un barrido de cliente encuentra el mismo anuncio: actualiza días/variantes, conserva cliente y clasificación.
    rid2, creado2 = datos.guardar_referente(_anuncio(dias=400, variantes=20, cuerpo="Copy nuevo", clasificacion="pendiente",
                                                     familia=None, etapa=None), cliente="acme", barrido_id=None)
    assert rid2 == rid and creado2 is False
    r = datos.referente("acme", rid)
    assert r["dias"] == 400 and r["variantes"] == 20 and r["cuerpo"] == "Copy nuevo"
    assert r["cliente"] is None and r["clasificacion"] == "fuente" and r["familia"] == "Price Slash Hero"


def test_guardar_referente_valida(base_temporal):
    from referentes import datos
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(anuncio_id=""))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(fuente="otra"))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(imagen_origen=""))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(etapa="XXX"))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(consciencia="dormido"))


def test_referente_privado_solo_lo_ve_su_cliente(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="777"), cliente="acme")
    assert datos.referente("acme", rid)["cliente"] == "acme"
    assert datos.referente("otro", rid) is None

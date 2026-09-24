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

"""referentes.recrear: prompt determinista, adaptación con Claude, subida de
fotos del producto y conteo de usos. Sin red: _llamar y r2_uploader se
reemplazan con monkeypatch."""
import pytest


def _referente(**extra):
    base = {"id": 7, "titular": "WE'RE SAYING GOODBYE", "familia": "Price Slash Hero",
            "firma": "Titular gigante estilo ruptura que fabrica urgencia.", "dolor": "ninguno-oferta",
            "imagen_url": "https://r2/referentes/1.jpg"}
    base.update(extra)
    return base


def _familia(**extra):
    base = {"nombre": "Price Slash Hero", "descripcion": "Precio tachado en grande con oferta que cierra."}
    base.update(extra)
    return base


def _producto(**extra):
    base = {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "Espejo redondo con luz regulable.",
            "regla": "Reprodúcelo idéntico: marco negro mate, luz cálida.", "referencias": ["/x/a.jpg", "/x/b.jpg"]}
    base.update(extra)
    return base


def test_armar_prompt_imagen_basico():
    from referentes import recrear
    p = recrear.armar_prompt(_referente(), _familia(), _producto(), "Fotografía de producto, fondo neutro.",
                             "SE ACABA HOY", "1:1")
    assert "Image 1" in p and "Image 2 y 3" in p and "Price Slash Hero" in p
    assert "Precio tachado en grande con oferta que cierra." in p
    assert "Titular gigante estilo ruptura que fabrica urgencia." in p
    assert "Espejo LED" in p and "Espejo redondo con luz regulable." in p and "marco negro mate" in p
    assert "titular «SE ACABA HOY»" in p and "Fotografía de producto, fondo neutro." in p
    assert "Sin logos ni nombres de otras marcas" in p and "Sin marcas de agua" in p
    assert "Sustituye por completo el producto y la marca de la referencia" in p
    assert "SONIDO" not in p and "Cámara fija" not in p


def test_armar_prompt_una_sola_foto_de_producto():
    from referentes import recrear
    p = recrear.armar_prompt(_referente(), _familia(), _producto(referencias=["/x/a.jpg"]), "", "X", "1:1")
    assert "Image 2 y 3" not in p and "el de Image 2" in p


def test_armar_prompt_omite_dolor_ninguno_y_campos_vacios():
    from referentes import recrear
    p = recrear.armar_prompt(_referente(dolor="ninguno-oferta"), None, _producto(), "", "", "9:16")
    assert "ninguno-oferta" not in p and "Dolor que ataca" not in p
    p2 = recrear.armar_prompt(_referente(dolor="bloating"), None, _producto(), "", "", "9:16")
    assert "Dolor que ataca: bloating." in p2


def test_armar_prompt_video_agrega_camara_y_sonido():
    from referentes import recrear
    p = recrear.armar_prompt(_referente(), _familia(), _producto(), "", "X", "9:16", tipo="video",
                             sonido_texto="", con_sonido=True)
    assert "Cámara fija con leve acercamiento al producto" in p
    assert "SONIDO: ambiente natural de la escena. Sin diálogo hablado ni música de fondo." in p
    p2 = recrear.armar_prompt(_referente(), _familia(), _producto(), "", "X", "9:16", tipo="video",
                              sonido_texto="el clic del espejo al encenderse", con_sonido=True)
    assert "SONIDO: el clic del espejo al encenderse. Sin diálogo hablado ni música de fondo." in p2
    p3 = recrear.armar_prompt(_referente(), _familia(), _producto(), "", "X", "9:16", tipo="video",
                              sonido_texto="", con_sonido=False)
    assert "SONIDO" not in p3

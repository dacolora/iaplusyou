"""Incidente 2026-09-28 («mira lo que sacó»): Seedance 2.5 recibe UNA imagen de
arranque y las otras tres referencias de la bandeja se descartaban en
silencio, mientras la tarjeta las mostraba como usadas y se cobraba el modelo
más caro. `referencias_de_mas` dice qué referencias no llegarían al modelo
elegido, con la misma cuenta que hacen `_preparar` y `generar_video`."""
from providers import flowplus_modelos as fm


def _img(n):
    return {"tipo": "imagen", "etiqueta": f"@Imagen {n}"}


def _vid(n):
    return {"tipo": "video", "etiqueta": f"@Video {n}"}


def test_seedance_solo_usa_la_primera():
    refs = [_img(1), _img(2), _img(3), _img(4)]
    assert fm.referencias_de_mas("seedance25", refs) == ["@Imagen 2", "@Imagen 3", "@Imagen 4"]
    assert fm.referencias_de_mas("seedance25", [_img(1)]) == []
    assert fm.referencias_de_mas("seedance25", []) == []


def test_kling_cuenta_el_fotograma_del_video_como_imagen():
    refs = [_img(n) for n in range(1, 8)] + [_vid(1)]
    assert fm.referencias_de_mas("kling_o3_pro", refs) == ["@Video 1"]
    assert fm.referencias_de_mas("kling_o3_pro", refs[:7]) == []


def test_wan_cuenta_imagenes_y_videos_aparte():
    refs = [_img(n) for n in range(1, 12)] + [_vid(n) for n in range(1, 7)]
    assert fm.referencias_de_mas("wan3", refs) == ["@Imagen 11", "@Video 6"]
    assert fm.referencias_de_mas("wan3", refs[:10] + refs[11:16]) == []


def test_los_activos_del_catalogo_cuentan_como_imagenes():
    refs = [{"tipo": "imagen", "etiqueta": "Personaje 1", "categoria": "personaje", "activo": "Ana"},
            {"tipo": "imagen", "etiqueta": "Personaje 1 (vista 2)", "categoria": "personaje", "activo": "Ana"},
            _img(1)]
    assert fm.referencias_de_mas("seedance25", refs) == ["Personaje 1 (vista 2)", "@Imagen 1"]


def test_la_imagen_tiene_su_propio_tope():
    refs = [_img(n) for n in range(1, 12)]
    assert fm.referencias_de_mas("seedream_v5_pro", refs, tipo="imagen") == ["@Imagen 11"]
    assert fm.referencias_de_mas("seedream_v5_pro", refs[:10], tipo="imagen") == []

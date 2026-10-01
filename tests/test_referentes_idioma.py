"""Referentes: «Sugerir con IA», «Adaptar con IA» y el prompt determinista de
«Recrear con mi producto» en el idioma del proyecto (spec 2026-09-26 §B4-§B5).
Sin red."""
import idiomas
from referentes import recrear, sugerir
from tests.i18n_util import _con_marca
from tests.test_referentes_recrear import _familia, _producto, _referente
from tests.test_referentes_sugerir import _RespuestaFalsa, _cand, _cliente_que_responde
from tests.test_rutas_referentes import _sembrar, app  # noqa: F401  (fixture)

ORDEN_EN = idiomas.orden_idioma("en")

# El prompt de hoy, byte a byte (antes de esta tarea), para los datos de tests/test_referentes_recrear.py.
ES_IMAGEN = ("Anuncio estático para redes, formato 1:1. Sigue la ESTRUCTURA y la COMPOSICIÓN de Image 1 (referencia "
             "de formato «Price Slash Hero»: Precio tachado en grande con oferta que cierra.). Funciona porque: Titular "
             "gigante estilo ruptura que fabrica urgencia.. Producto: el de Image 2 y 3: Espejo LED. Espejo redondo con "
             "luz regulable. Reprodúcelo idéntico: marco negro mate, luz cálida. Sustituye por completo el producto y la "
             "marca de la referencia. Texto en la imagen: titular «SE ACABA HOY» con el mismo peso y ubicación que en la "
             "referencia; ningún otro texto. Guía de estilo de la marca: Fotografía de producto, fondo neutro.. Sin logos "
             "ni nombres de otras marcas. Sin marcas de agua.")
ES_VIDEO = ("Anuncio estático para redes, formato 9:16. Sigue la ESTRUCTURA y la COMPOSICIÓN de Image 1 (referencia de "
            "formato «Price Slash Hero»: ). Funciona porque: Titular gigante estilo ruptura que fabrica urgencia.. Dolor "
            "que ataca: bloating. Producto: el de Image 2: Espejo LED. Espejo redondo con luz regulable. Reprodúcelo "
            "idéntico: marco negro mate, luz cálida. Sustituye por completo el producto y la marca de la referencia. "
            "Texto en la imagen: titular «X» con el mismo peso y ubicación que en la referencia; ningún otro texto. Sin "
            "logos ni nombres de otras marcas. Sin marcas de agua. Cámara fija con leve acercamiento al producto; el "
            "titular aparece en los primeros 2 segundos. SONIDO: ambiente natural de la escena. Sin diálogo hablado ni "
            "música de fondo.")


def test_sugerir_ia_pide_la_razon_en_ingles(monkeypatch):
    pedidos = []
    _cliente_que_responde(monkeypatch, _RespuestaFalsa('{"elegidos": [{"referente_id": 1, "razon": "Fits."}]}'), pedidos)
    elegidos, _, _ = sugerir.sugerir_ia([_cand(1, "ugc")], "moms", "sandal", "summer", 1, idioma="en")
    s = pedidos[0]["system"][1]["text"]
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "una razón de una frase, en inglés" in pedidos[0]["messages"][0]["content"]
    assert elegidos == [{"referente_id": 1, "razon": "Fits."}]


def test_la_tarea_de_sugerir_pasa_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import tareas
    from sprints import datos
    from tests.test_tareas_sprints import _referencia
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: (
        [{"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2}], []))
    visto = {}
    monkeypatch.setattr(sugerir, "sugerir_ia", lambda cands, p, pr, t, objetivo, enfoque_texto="", idioma="es": (
        visto.update(idioma=idioma) or ([], 10, 5)))
    tareas.cargar_todas()
    tareas.REGISTRO["referentes_sugerir_ia"]({"id": 1, "payload": {"cliente": "acme", "campana_id": cid}})
    assert visto["idioma"] == "en"


def test_adaptar_con_la_orden_al_principio_y_al_final(monkeypatch):
    textos = []
    respuesta = '{"titular": "ENDS TODAY", "prompt": "Ad with Image 1 and Image 2.", "angulo": {}}'
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: textos.append(texto) or (respuesta, 50, 10))
    recrear.adaptar(_referente(firma="Giant break-up headline that creates urgency."),
                    _familia(descripcion="Big struck-through price."), _producto(), "ENDS TODAY", idioma="en")
    assert len(textos) == 2                    # el ángulo vacío pide una corrección: también lleva la orden
    for t in textos:
        assert t.startswith(ORDEN_EN) and t.endswith(ORDEN_EN)
    assert "Escribe en inglés," in textos[0] and "Escribe en español" not in textos[0]


def test_armar_prompt_en_espanol_identico():
    assert recrear.armar_prompt(_referente(), _familia(), _producto(), "Fotografía de producto, fondo neutro.",
                                "SE ACABA HOY", "1:1") == ES_IMAGEN
    assert recrear.armar_prompt(_referente(dolor="bloating"), None, _producto(referencias=["/x/a.jpg"]), "", "X", "9:16",
                                tipo="video", sonido_texto="", con_sonido=True) == ES_VIDEO


def test_armar_prompt_en_ingles_sin_espanol_fijo():
    ref = _referente(firma="Giant break-up headline that creates urgency.")
    fam = _familia(descripcion="Big struck-through price with a closing offer.")
    prod = _producto(nombre="LED mirror", descripcion="Round mirror with dimmable light.",
                     regla="Reproduce it identically: matte black frame, warm light.")
    p = recrear.armar_prompt(ref, fam, prod, "Product photo, neutral background.", "ENDS TODAY", "1:1", idioma="en")
    assert not _con_marca(p), p
    assert "Image 2 and 3" in p and "headline “ENDS TODAY”" in p
    v = recrear.armar_prompt(ref, fam, prod, "", "ENDS TODAY", "9:16", tipo="video", con_sonido=True, idioma="en")
    assert not _con_marca(v), v
    assert v.endswith("SOUND: natural ambient sound of the scene. No spoken dialogue and no background music.")


def test_recrear_arma_el_prompt_en_el_idioma_del_proyecto(app):
    ids = _sembrar()
    idiomas.guardar_de_proyecto("acme", "en")
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear").data.decode()
    assert "Static social media ad" in html and "Anuncio estático para redes" not in html


def test_adaptar_recibe_el_idioma_del_proyecto(app, monkeypatch):
    ids = _sembrar()
    idiomas.guardar_de_proyecto("acme", "en")
    visto = {}
    monkeypatch.setattr(recrear, "adaptar", lambda referente, familia, producto, titular_actual, guia="", idioma="es", **kw: (
        visto.update(idioma=idioma) or ({"titular": "T", "prompt": "P", "angulo": {}}, 10, 5)))
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "espejo_led"})
    assert r.status_code == 200 and visto["idioma"] == "en"

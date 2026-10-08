"""Tarjetas de análisis (spec 2026-10-08 §3): tw_creativo y tw_analisis."""
import pytest

import db
import triple_whale_tiendas
from triple_whale import datos


@pytest.fixture()
def tienda(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    return triple_whale_tiendas.agregar("acme", "tw_x", "acme.myshopify.com", None, moneda="USD")


def _creativo(ad_id, **kw):
    r = {"canal": "facebook-ads", "ad_id": ad_id, "tipo": "video", "imagen_url": f"https://files.triplewhale.com/t/{ad_id}.jpg",
         "video_url": f"https://files.triplewhale.com/v/{ad_id}.mp4", "titulo": "Título", "copy": "Copy largo",
         "cta": None, "duracion_s": 23.0}
    r.update(kw)
    return r


def test_creativos_upsert_y_un_vacio_no_pisa_lo_guardado(tienda):
    datos.reemplazar_creativos("acme", tienda, [_creativo("1"), _creativo("2", tipo="image", video_url=None)])
    datos.reemplazar_creativos("acme", tienda, [_creativo("1", copy=None, titulo="Nuevo")])
    c = datos.creativos("acme", [("facebook-ads", "1"), ("facebook-ads", "2"), ("facebook-ads", "9")])
    assert set(c) == {("facebook-ads", "1"), ("facebook-ads", "2")}
    assert c[("facebook-ads", "1")]["titulo"] == "Nuevo" and c[("facebook-ads", "1")]["copy"] == "Copy largo"
    assert c[("facebook-ads", "2")]["video_url"] is None and c[("facebook-ads", "2")]["tipo"] == "image"
    assert datos.creativos("acme", []) == {} and datos.creativos("otro", [("facebook-ads", "1")]) == {}


def test_creativos_de_una_tienda_quitada_no_se_escriben(tienda):
    triple_whale_tiendas.quitar("acme", tienda)
    datos.reemplazar_creativos("acme", tienda, [_creativo("1")])
    assert datos.creativos("acme", [("facebook-ads", "1")]) == {}


def test_quitar_la_ultima_tienda_borra_los_creativos_y_otra_no(tienda):
    otra = triple_whale_tiendas.agregar("acme", "tw_y", "acme-no.myshopify.com", "NO", moneda="USD")
    datos.reemplazar_creativos("acme", tienda, [_creativo("1")])
    triple_whale_tiendas.quitar("acme", otra)
    assert datos.creativos("acme", [("facebook-ads", "1")])          # queda una tienda: se conservan
    triple_whale_tiendas.quitar("acme", tienda)
    assert datos.creativos("acme", [("facebook-ads", "1")]) == {}    # sin tiendas: se borran


def test_cambiar_ajustes_no_borra_los_creativos(tienda):
    datos.reemplazar_creativos("acme", tienda, [_creativo("1")])
    assert triple_whale_tiendas.cambiar_ajustes("acme", moneda="EUR")
    assert datos.creativos("acme", [("facebook-ads", "1")])


def test_analisis_crear_actualizar_leer_y_ultimo_por_anuncio(tienda):
    a1 = datos.crear_analisis("acme", None, "facebook-ads", "1", "2026-09-01", "2026-09-30", "USD",
                              {"veredicto": "perdedor"}, pedido_por="admin")
    a2 = datos.crear_analisis("acme", tienda, "facebook-ads", "1", "2026-09-01", "2026-09-30", "USD", {})
    a3 = datos.crear_analisis("acme", None, "facebook-ads", "2", "2026-09-01", "2026-09-30", "USD", {})
    assert datos.actualizar_analisis(a2, estado="lista", resultado={"frase": "x"}, usd=0.05)
    with pytest.raises(ValueError):
        datos.actualizar_analisis(a2, estado="raro")
    fila = datos.analisis_anuncio("acme", a2)
    assert fila["estado"] == "lista" and fila["resultado"] == {"frase": "x"} and fila["tienda_id"] == tienda
    assert datos.analisis_anuncio("otro", a2) is None
    ultimos = datos.ultimos_analisis("acme", [("facebook-ads", "1"), ("facebook-ads", "2")])
    assert ultimos[("facebook-ads", "1")]["id"] == a2 and ultimos[("facebook-ads", "2")]["id"] == a3
    assert datos.analisis_anuncio("acme", a1)["foto"] == {"veredicto": "perdedor"}
    assert datos.analisis_en_curso("acme", "facebook-ads", "1")      # a1 sigue en cola: ese anuncio sigue en curso
    assert datos.actualizar_analisis(a1, estado="error")
    assert datos.analisis_en_curso("acme", "facebook-ads", "2") and not datos.analisis_en_curso("acme", "facebook-ads", "1")
    assert datos.borrar_analisis("acme", a3) and not datos.borrar_analisis("otro", a1)
    assert datos.ultimos_analisis("acme", []) == {}


def test_un_analisis_no_se_borra_al_quitar_la_tienda(tienda):
    aid = datos.crear_analisis("acme", tienda, "facebook-ads", "1", "2026-09-01", "2026-09-30", "USD", {})
    triple_whale_tiendas.quitar("acme", tienda)
    assert datos.analisis_anuncio("acme", aid) is not None


def test_ultimos_analisis_es_una_sola_consulta(tienda):
    import sqlalchemy as sa
    from sqlalchemy import event
    for i in range(5):
        datos.crear_analisis("acme", None, "facebook-ads", str(i), "2026-09-01", "2026-09-30", "USD", {})
    n = []
    f = lambda *a, **k: n.append(1)  # noqa: E731
    event.listen(sa.engine.Engine, "before_cursor_execute", f)
    try:
        datos.ultimos_analisis("acme", [("facebook-ads", str(i)) for i in range(5)])
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", f)
    assert len(n) == 1


def test_tres_mil_claves_no_pasan_los_topes_de_sqlite(tienda):
    """happyflops tiene ~2 500 anuncios de Meta en 90 días y el lote mira todos los candidatos: una cadena de OR por
    clave pasaba el tope de profundidad de expresiones de SQLite (revisión de la tarea 7). Sin error, sin mezclar
    proyectos y con el análisis más nuevo de cada anuncio."""
    n = 3000
    datos.reemplazar_creativos("acme", tienda, [_creativo(str(i), titulo=f"T{i}") for i in range(n)])
    ahora = db.ahora()
    filas = []
    for i in range(n):
        for estado in ("lista", "error"):                     # el segundo (id mayor) es el último
            filas.append(dict(cliente="acme", creado_en=ahora, actualizado_en=ahora, canal="facebook-ads",
                              ad_id=str(i), estado=estado, foto={}, resultado={}, medios={}, usd=0.0))
    filas.append(dict(cliente="otro", creado_en=ahora, actualizado_en=ahora, canal="facebook-ads", ad_id="7",
                      estado="en_cola", foto={}, resultado={}, medios={}, usd=0.0))
    with db.conectar() as con:
        con.execute(db.tw_analisis.insert(), filas)
    claves = [("facebook-ads", str(i)) for i in range(n)] + [("tiktok-ads", "nada")]
    cr = datos.creativos("acme", claves)
    assert len(cr) == n and cr[("facebook-ads", "2999")]["titulo"] == "T2999"
    ul = datos.ultimos_analisis("acme", claves)
    assert len(ul) == n and all(f["estado"] == "error" and f["cliente"] == "acme" for f in ul.values())

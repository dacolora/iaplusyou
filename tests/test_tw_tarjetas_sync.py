"""La sincronización trae el anuncio tal cual (spec tarjetas §3.3)."""
import triple_whale
import triple_whale_tiendas
from tests.test_triple_whale_sync import HOY, TripleWhaleFalso, _ad, _tienda, conectado  # noqa: F401
from triple_whale import datos, sync


def _cre(ad_id, **kw):
    f = {"channel": "facebook-ads", "ad_id": ad_id, "ad_type": "VIDEO",
         "ad_image_url": f"https://files.triplewhale.com/thumbnails/{ad_id}.jpg",
         "video_url": f"https://files.triplewhale.com/videos/{ad_id}.mp4", "ad_title": "Varme skritt",
         "ad_copy": "Det er offisielt", "creative_cta_type": None, "video_duration": "23"}
    f.update(kw)
    return f


def test_normalizar_creativo():
    r = sync.normalizar_creativo(_cre("123"))
    assert r == {"canal": "facebook-ads", "ad_id": "123", "tipo": "video",
                 "imagen_url": "https://files.triplewhale.com/thumbnails/123.jpg",
                 "video_url": "https://files.triplewhale.com/videos/123.mp4", "titulo": "Varme skritt",
                 "copy": "Det er offisielt", "cta": None, "duracion_s": 23.0}
    assert sync.normalizar_creativo({"channel": "x", "ad_id": ""}) is None
    assert sync.normalizar_creativo({"ad_id": "null"}) is None
    assert sync.normalizar_creativo(_cre("1", video_duration=None))["duracion_s"] is None
    assert len(sync.normalizar_creativo(_cre("1", ad_copy="x" * 5000))["copy"]) == 3000


def test_consultas_creativos_completa_y_minima():
    completa, minima = triple_whale.consultas_creativos()
    assert "ad_copy" in completa and "ad_title" in completa and "ad_image_url" in completa
    assert "ad_image_url" in minima and "ad_copy" not in minima and "ad_title" not in minima


def test_sincronizar_guarda_los_creativos(conectado, monkeypatch):
    falso = TripleWhaleFalso(ads=[_ad("1", "2026-09-28")], creativos=[_cre("1"), _cre("2", ad_type="image", video_url=None)])
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    r = sync.sincronizar("acme", _tienda(), "2026-09-22", "2026-09-28", hoy=HOY)
    assert r["creativos"] == 2 and r["consultas"]["creativos"] == "completa" and "creativos" not in r["fallos"]
    c = datos.creativos("acme", [("facebook-ads", "1"), ("facebook-ads", "2")])
    assert c[("facebook-ads", "1")]["copy"] == "Det er offisielt" and c[("facebook-ads", "2")]["tipo"] == "image"


def test_si_la_consulta_de_creativos_falla_la_copia_sigue(conectado, monkeypatch):
    falso = TripleWhaleFalso(ads=[_ad("1", "2026-09-28")], fallar_todo={"creativos"})
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    # 14 días = dos tramos (DIAS_TRAMO = 7): el segundo no vuelve a probar los creativos.
    r = sync.sincronizar("acme", _tienda(), "2026-09-15", "2026-09-28", hoy=HOY)
    assert r["tramos"] == 2
    assert "creativos" in r["fallos"] and r["anuncios"] == 1 and r["consultas"]["creativos"] == "sin_datos"
    assert triple_whale_tiendas.tienda("acme", _tienda())["estado"] == "conectada"
    # Un fallo no se reintenta en cada tramo: una sola llamada completa y una mínima.
    assert len([l for l in falso.llamadas if l[0] == "creativos"]) == 2


def test_el_fallo_de_creativos_queda_sin_la_llave(conectado, monkeypatch):
    """El texto del fallo se guarda en `ultimo_resumen` y se pinta en la pestaña: sin la llave."""
    def responde(llave, shop, consulta, desde, hasta, moneda=None):
        if "ad_image_url" in consulta:
            raise triple_whale.ErrorConsulta(f"consulta rechazada para {llave}")
        return []
    monkeypatch.setattr(triple_whale, "sql_query", responde)
    r = sync.sincronizar("acme", _tienda(), "2026-09-22", "2026-09-28", hoy=HOY)
    guardado = triple_whale_tiendas.tienda("acme", _tienda())["extra"]["ultimo_resumen"]["fallos"]
    for texto in (r["fallos"]["creativos"], guardado["creativos"]):
        assert "tw_secreto" not in texto and "***" in texto


def test_la_minima_de_creativos_sirve_si_la_completa_no(conectado, monkeypatch):
    falso = TripleWhaleFalso(ads=[_ad("1", "2026-09-28")], creativos=[_cre("1")], fallar={"creativos": 1})
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    r = sync.sincronizar("acme", _tienda(), "2026-09-22", "2026-09-28", hoy=HOY)
    assert r["consultas"]["creativos"] == "minima"

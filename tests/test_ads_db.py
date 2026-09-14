import pytest


def test_crear_y_cargar(base_temporal):
    import ads
    aid = ads.crear("acme", "flowplus", "cf_1", "https://r2/v.mp4", "video", "Lanzamiento — Video")
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "en_cola" and e["nombre"] == "Lanzamiento — Video" and e["fuente"] == "flowplus"
    assert e["meta_ids"] == {"campaign_id": None, "adset_id": None, "ad_id": None, "creative_id": None}
    assert e["metricas"]["impresiones"] == 0 and e["metricas"]["actualizado_en"] is None
    assert e["creado_en"]


def test_actualizar_meta_ids_metricas_y_estado(base_temporal):
    import ads
    aid = ads.crear("acme", "flowplus", "cf_1", "https://r2/v.mp4", "video", "N")
    ads.actualizar("acme", aid, estado="publicando", objetivo="OUTCOME_TRAFFIC", presupuesto_diario_usd=20000, dias=3,
                   audiencia={"pais": "CO"}, meta_ids={"campaign_id": "1", "adset_id": "2", "ad_id": "3", "creative_id": "4"})
    ads.actualizar("acme", aid, estado="pausado", metricas={"impresiones": 10, "clics": 2, "gasto_usd": 5.5, "ctr": 20.0,
                   "reach": 8, "resultado": 2, "resultado_nombre": "Clics al enlace", "estado_meta": "PAUSED",
                   "estado_meta_texto": "Pausado", "actualizado_en": "2026-09-14T10:00:00"})
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "pausado" and e["meta_ids"]["ad_id"] == "3" and e["objetivo"] == "OUTCOME_TRAFFIC"
    assert e["metricas"]["impresiones"] == 10 and e["metricas"]["gasto_usd"] == 5.5 and e["metricas"]["estado_meta_texto"] == "Pausado"
    assert e["presupuesto_diario_usd"] == 20000 and e["audiencia"] == {"pais": "CO"}


def test_error_y_eliminar(base_temporal):
    import ads
    aid = ads.crear("acme", "swap", "s1", "https://r2/i.png", "imagen", "N")
    ads.actualizar("acme", aid, estado="error", error="Meta dijo no")
    assert ads.cargar("acme")[aid]["error"] == "Meta dijo no"
    ads.actualizar("acme", aid, estado="en_cola", error=None)
    assert ads.cargar("acme")[aid]["error"] is None
    ads.eliminar("acme", aid)
    assert aid not in ads.cargar("acme")
    with pytest.raises(KeyError):
        ads.actualizar("acme", aid, estado="x")


def test_orden_y_aislamiento(base_temporal):
    import ads
    a = ads.crear("acme", "f", "1", "u", "video", "a"); b = ads.crear("acme", "f", "2", "u", "video", "b")
    ads.crear("otro", "f", "3", "u", "video", "c")
    assert list(ads.cargar("acme").keys()) == [a, b]


def test_metricas_historial(base_temporal):
    import db
    import ads
    aid = ads.crear("acme", "flowplus", "cf_1", "https://r2/v.mp4", "video", "N")
    ads.actualizar("acme", aid, metricas={"impresiones": 5, "actualizado_en": "2026-09-14T09:00:00"})
    ads.actualizar("acme", aid, metricas={"impresiones": 10, "actualizado_en": "2026-09-14T10:00:00"})
    e = ads.cargar("acme")[aid]
    assert e["metricas"]["impresiones"] == 10
    assert e["metricas"]["actualizado_en"] == "2026-09-14T10:00:00"
    with db.conectar() as con:
        import sqlalchemy as sa
        n = con.execute(sa.select(sa.func.count()).select_from(db.metrica_snapshot)).scalar()
    assert n == 2

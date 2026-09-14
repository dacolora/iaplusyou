import json
import os
import tempfile


def _cliente_con_json():
    base = tempfile.mkdtemp(prefix="creatv_mig_")
    c = os.path.join(base, "clientes", "acme"); os.makedirs(c)
    cf = {"cf_20260912_160550_108303": {
        "personajes_ids": [], "productos_ids": ["Rose"], "escenas_ids": [], "accion_central": "camina",
        "duracion_objetivo": 10, "tono": "", "modo": "A", "platforms": [], "estado": "video_listo",
        "prompt_relleno": "PROMPT", "referencias_urls": ["https://x/1.png"], "video_url": "https://r2/v.mp4",
        "video_local": "/tmp/v.mp4", "credits": None, "usd": 1.0, "error": None, "creado_en": "2026-09-12T16:05:50",
        "tipo": "video", "modelo": "wan3", "enfoque": "producto", "enfoque_nombre": "Solo producto", "aspect_ratio": "9:16",
        "referencias": [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}]}}
    ads = {"ad_20260913_193256_500057": {
        "fuente": "flowplus", "fuente_id": "cf_20260912_160550_108303", "contenido_url": "https://r2/v.mp4",
        "contenido_tipo": "video", "nombre": "Lanzamiento — Video", "estado": "activo", "objetivo": "OUTCOME_TRAFFIC",
        "presupuesto_diario_usd": 20000, "dias": 3, "audiencia": {"pais": "CO"},
        "meta_ids": {"campaign_id": "1", "adset_id": "2", "ad_id": "3", "creative_id": "4"},
        "metricas": {"impresiones": 5, "clics": 1, "gasto_usd": 100.0, "ctr": 20.0, "reach": 4, "estado_meta": "ACTIVE",
                     "estado_meta_texto": "Activo", "actualizado_en": "2026-09-13T19:36:00"},
        "error": None, "creado_en": "2026-09-13T19:32:56"}}
    json.dump(cf, open(os.path.join(c, "creative_flow_pendientes.json"), "w"))
    json.dump(ads, open(os.path.join(c, "ads.json"), "w"))
    return base


def test_migra_y_es_idempotente(base_temporal):
    import ads, creative_flow as cf, migrar_json_a_db as mig
    base = _cliente_con_json()
    r1 = mig.migrar_cliente("acme", base)
    assert r1 == {"conceptos": 1, "anuncios": 1, "saltados": 0}
    e = cf.cargar("acme")["cf_20260912_160550_108303"]
    assert e["estado"] == "video_listo" and e["video_url"] == "https://r2/v.mp4" and e["creado_en"] == "2026-09-12T16:05:50"
    assert e["referencias"][0]["etiqueta"] == "@Imagen 1" and e["prompt_relleno"] == "PROMPT"
    a = ads.cargar("acme")["ad_20260913_193256_500057"]
    assert a["estado"] == "activo" and a["meta_ids"]["ad_id"] == "3" and a["metricas"]["impresiones"] == 5
    assert a["metricas"]["estado_meta_texto"] == "Activo" and a["creado_en"] == "2026-09-13T19:32:56"
    r2 = mig.migrar_cliente("acme", base)
    assert r2 == {"conceptos": 0, "anuncios": 0, "saltados": 2}
    assert len(cf.cargar("acme")) == 1 and len(ads.cargar("acme")) == 1


def test_cliente_sin_json(base_temporal):
    import migrar_json_a_db as mig
    base = tempfile.mkdtemp(); os.makedirs(os.path.join(base, "clientes", "vacio"))
    assert mig.migrar_cliente("vacio", base) == {"conceptos": 0, "anuncios": 0, "saltados": 0}

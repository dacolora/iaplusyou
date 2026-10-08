"""meta_detalle (spec 2026-10-02 §3): traducir filas de Meta, pedir con
paginación, guardar sin cruzar proyectos y refrescar sin tumbar nada."""
import json
import pytest
from datetime import date
import sqlalchemy as sa

FILA_DIA = {
    "ad_id": "ad_1", "date_start": "2026-09-30", "date_stop": "2026-09-30",
    "impressions": "1000", "reach": "800", "frequency": "1.25", "clicks": "40", "inline_link_clicks": "25",
    "spend": "12.5", "cpm": "12.5",
    "actions": [{"action_type": "video_view", "value": "300"}, {"action_type": "landing_page_view", "value": "18"},
                {"action_type": "omni_add_to_cart", "value": "4"}, {"action_type": "add_to_cart", "value": "4"},
                {"action_type": "omni_initiated_checkout", "value": "2"}, {"action_type": "purchase", "value": "1"}],
    "action_values": [{"action_type": "purchase", "value": "59.9"}],
    "video_play_actions": [{"action_type": "video_view", "value": "900"}],
    "video_p25_watched_actions": [{"action_type": "video_view", "value": "220"}],
    "video_p50_watched_actions": [{"action_type": "video_view", "value": "150"}],
    "video_p75_watched_actions": [{"action_type": "video_view", "value": "90"}],
    "video_p95_watched_actions": [{"action_type": "video_view", "value": "60"}],
    "video_p100_watched_actions": [{"action_type": "video_view", "value": "50"}],
    "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "70"}],
    "video_avg_time_watched_actions": [{"action_type": "video_view", "value": "4.2"}],
}


def test_fila_diaria_traduce_campos_y_acciones():
    import meta_detalle as md
    f = md.fila_diaria(FILA_DIA)
    assert f["fecha"] == "2026-09-30"
    assert (f["impresiones"], f["alcance"], f["clics"], f["clics_enlace"]) == (1000, 800, 40, 25)
    assert f["frecuencia"] == 1.25 and f["gasto"] == 12.5 and f["cpm"] == 12.5
    assert f["vistas_3s"] == 300 and f["reproducciones"] == 900
    assert (f["p25"], f["p50"], f["p75"], f["p95"], f["p100"]) == (220, 150, 90, 60, 50)
    assert f["thruplay"] == 70 and f["tiempo_medio_s"] == 4.2
    # carrito: omni_ primero y sin sumar el duplicado add_to_cart
    assert f["visitas_pagina"] == 18 and f["carrito"] == 4 and f["pago_iniciado"] == 2
    assert f["compras_meta"] == 1 and f["ingresos_meta"] == 59.9


def test_fila_diaria_sin_video_ni_acciones_da_ceros():
    import meta_detalle as md
    f = md.fila_diaria({"date_start": "2026-10-01", "impressions": "10", "spend": "1"})
    assert f["impresiones"] == 10 and f["gasto"] == 1.0
    assert f["vistas_3s"] == f["p25"] == f["carrito"] == f["compras_meta"] == 0 and f["ingresos_meta"] == 0.0


@pytest.mark.parametrize("dimension, extra, clave", [
    ("ubicacion", {"publisher_platform": "instagram", "platform_position": "instagram_reels"}, "instagram|instagram_reels"),
    ("edad_genero", {"age": "25-34", "gender": "female"}, "25-34|female"),
    ("dispositivo", {"device_platform": "mobile_app"}, "mobile_app"),
    ("region", {"region": "Antioquia"}, "Antioquia"),
])
def test_fila_desglose_arma_la_clave(dimension, extra, clave):
    import meta_detalle as md
    fila = {**FILA_DIA, **extra}
    k, v = md.fila_desglose(fila, dimension)
    assert k == clave
    assert v == {"impresiones": 1000, "clics_enlace": 25, "gasto": 12.5, "vistas_3s": 300, "thruplay": 70,
                 "compras_meta": 1, "ingresos_meta": 59.9}


def test_rankings_de():
    import meta_detalle as md
    r = md.rankings_de({"quality_ranking": "ABOVE_AVERAGE", "engagement_rate_ranking": "AVERAGE",
                        "conversion_rate_ranking": "UNKNOWN"})
    assert r == {"calidad": "ABOVE_AVERAGE", "interaccion": "AVERAGE", "conversion": None}


class LlamarFalso:
    """Reemplaza meta_ads.auth.llamar: responde por edge/params y anota las llamadas."""
    def __init__(self, paginas):
        self.paginas = list(paginas)   # cada una: {"data": [...], "paging": {...}}
        self.llamadas = []

    def __call__(self, metodo, edge, payload=None, params=None, dry_run=False):
        self.llamadas.append((metodo, edge, dict(params or {})))
        return self.paginas.pop(0)


def _con_llamar(monkeypatch, paginas):
    import meta_detalle as md
    falso = LlamarFalso(paginas)
    monkeypatch.setattr(md.auth, "llamar", falso)
    monkeypatch.setattr(md.auth, "ad_account_id", lambda: "123")
    return md, falso


def test_pedir_diario_arma_la_consulta_y_sigue_paginas(monkeypatch):
    md, falso = _con_llamar(monkeypatch, [
        {"data": [{"ad_id": "a"}], "paging": {"cursors": {"after": "C1"}, "next": "https://graph/next"}},
        {"data": [{"ad_id": "b"}], "paging": {"cursors": {"after": "C2"}}},
    ])
    filas = md.pedir_diario("cmp_9", "2026-09-01", "2026-09-30")
    assert [f["ad_id"] for f in filas] == ["a", "b"]
    metodo, edge, params = falso.llamadas[0]
    assert metodo == "GET" and edge == "act_123/insights"
    assert params["level"] == "ad" and params["time_increment"] == 1
    assert json.loads(params["time_range"]) == {"since": "2026-09-01", "until": "2026-09-30"}
    assert json.loads(params["filtering"]) == [{"field": "campaign.id", "operator": "EQUAL", "value": "cmp_9"}]
    assert "video_p25_watched_actions" in params["fields"] and "ad_id" in params["fields"]
    assert "after" not in params and falso.llamadas[1][2]["after"] == "C1"


def test_pedir_para_en_max_paginas(monkeypatch):
    import meta_detalle as md
    pagina = {"data": [{"ad_id": "x"}], "paging": {"cursors": {"after": "C"}, "next": "https://graph/next"}}
    md2, falso = _con_llamar(monkeypatch, [dict(pagina) for _ in range(md.MAX_PAGINAS + 5)])
    assert len(md2.pedir_rankings("cmp", "2026-09-01", "2026-09-30")) == md.MAX_PAGINAS
    assert len(falso.llamadas) == md.MAX_PAGINAS


def test_pedir_desglose_y_rankings(monkeypatch):
    md, falso = _con_llamar(monkeypatch, [{"data": [{"ad_id": "a", "age": "25-34", "gender": "female"}]},
                                          {"data": [{"ad_id": "a", "quality_ranking": "AVERAGE"}]}])
    assert md.pedir_desglose("cmp", "edad_genero", "2026-09-10", "2026-10-02")[0]["age"] == "25-34"
    _, _, p1 = falso.llamadas[0]
    assert p1["breakdowns"] == "age,gender" and "time_increment" not in p1
    # desde la creación del experimento hasta hoy, no «maximum» (Meta restringe lo de por vida con desgloses)
    assert json.loads(p1["time_range"]) == {"since": "2026-09-10", "until": "2026-10-02"} and "date_preset" not in p1
    assert "video_p25_watched_actions" not in p1["fields"]   # sin campos de video en desgloses
    md.pedir_rankings("cmp", "2026-09-10", "2026-10-02")
    _, _, p2 = falso.llamadas[1]
    assert "quality_ranking" in p2["fields"] and "date_preset" not in p2
    assert json.loads(p2["time_range"]) == {"since": "2026-09-10", "until": "2026-10-02"}


def test_campos_desglose_son_solo_lo_que_se_guarda():
    """reach/frequency/cpm/clicks no se guardan en metrica_desglose y reach con desgloses es caro."""
    import meta_detalle as md
    assert md.CAMPOS_DESGLOSE.split(",") == ["ad_id", "impressions", "inline_link_clicks", "spend", "actions",
                                              "action_values", "video_thruplay_watched_actions"]


@pytest.fixture()
def dos_piezas(base_temporal):
    """Experimento de acme con dos anuncios (ad_1 en CO, ad_2 en MX)."""
    import experimentos as ex
    from tests.test_experimentos_db import PAISES, _pieza
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t.co/p", "COP")
    ep1 = ex.agregar_pieza("acme", eid, clon, "CO")
    ep2 = ex.agregar_pieza("acme", eid, clon, "MX")
    ex.actualizar_pieza("acme", ep1, meta_ad_id="ad_1")
    ex.actualizar_pieza("acme", ep2, meta_ad_id="ad_2")
    ex.actualizar("acme", eid, meta_campaign_id="cmp_1")
    return {"db": base_temporal, "ex": ex, "eid": eid, "ep1": ep1, "ep2": ep2}


def _filas(db, tabla):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(tabla).order_by(tabla.c.id))]


def test_guardar_dias_reemplaza_el_dia_e_ignora_anuncios_ajenos(dos_piezas):
    import meta_detalle as md
    db, ep1 = dos_piezas["db"], dos_piezas["ep1"]
    mapa = {"ad_1": ep1, "ad_2": dos_piezas["ep2"]}
    n = md.guardar_dias(mapa, [{**FILA_DIA, "ad_id": "ad_1"}, {**FILA_DIA, "ad_id": "ad_de_otro_proyecto"}])
    assert n == 1
    md.guardar_dias(mapa, [{**FILA_DIA, "ad_id": "ad_1", "impressions": "1500"}])   # Meta corrigió el día
    filas = _filas(db, db.metrica_dia)
    assert len(filas) == 1 and filas[0]["experimento_pieza_id"] == ep1 and filas[0]["impresiones"] == 1500
    assert filas[0]["fecha"] == "2026-09-30" and filas[0]["actualizado_en"]


def test_guardar_desglose_reemplaza_el_juego_completo(dos_piezas):
    import meta_detalle as md
    db, ep1 = dos_piezas["db"], dos_piezas["ep1"]
    mapa = {"ad_1": ep1}
    md.guardar_desglose(mapa, "edad_genero", [{**FILA_DIA, "ad_id": "ad_1", "age": "18-24", "gender": "male"},
                                             {**FILA_DIA, "ad_id": "ad_1", "age": "25-34", "gender": "female"}])
    md.guardar_desglose(mapa, "dispositivo", [{**FILA_DIA, "ad_id": "ad_1", "device_platform": "mobile_app"}])
    md.guardar_desglose(mapa, "edad_genero", [{**FILA_DIA, "ad_id": "ad_1", "age": "25-34", "gender": "female"}])
    claves = sorted((f["dimension"], f["clave"]) for f in _filas(db, db.metrica_desglose))
    assert claves == [("dispositivo", "mobile_app"), ("edad_genero", "25-34|female")]


def test_guardar_rankings_en_extra_de_la_pieza(dos_piezas):
    import meta_detalle as md
    ex, ep1 = dos_piezas["ex"], dos_piezas["ep1"]
    ex.marcar_pieza("acme", ep1, archivado=False)   # lo que ya había en extra se conserva
    md.guardar_rankings("acme", {"ad_1": ep1}, [{"ad_id": "ad_1", "quality_ranking": "ABOVE_AVERAGE"},
                                                {"ad_id": "ajeno", "quality_ranking": "BELOW_AVERAGE_10"}])
    extra = [p for p in ex.obtener("acme", dos_piezas["eid"])["piezas"] if p["id"] == ep1][0]["extra"]
    assert extra["rankings_meta"]["calidad"] == "ABOVE_AVERAGE" and extra["archivado"] is False


def test_desde_para_sin_datos_y_con_datos(dos_piezas):
    import meta_detalle as md
    ep1 = dos_piezas["ep1"]
    assert md.desde_para([ep1], "2026-09-10T08:00:00", date(2026, 10, 2)) == "2026-09-10"
    md.guardar_dias({"ad_1": ep1}, [{**FILA_DIA, "ad_id": "ad_1"}])   # último día guardado: 30 sep
    assert md.desde_para([ep1], "2026-09-10T08:00:00", date(2026, 10, 2)) == "2026-09-28"
    # nunca después de hoy
    assert md.desde_para([ep1], "2026-12-01T00:00:00", date(2026, 10, 2)) == "2026-09-28"


def test_ads_eliminar_limpia_metrica_dia_y_desglose(base_temporal):
    """Verifica que ads.eliminar borra metrica_dia y metrica_desglose además de
    metrica_snapshot y experimento_pieza."""
    import ads
    import meta_detalle as md
    import db

    # Crear un ad en la base (crea una fila experimento_pieza con legado_id)
    ad_id = ads.crear("test", "flowplus", "cf_1", "https://r2/v.mp4", "video", "Test Ad")

    # Obtener el experimento_pieza id del ad
    with db.conectar() as con:
        ep_row = con.execute(sa.select(db.experimento_pieza).where(
            db.experimento_pieza.c.cliente == "test", db.experimento_pieza.c.legado_id == ad_id)).first()
        ep_id = ep_row._mapping[db.experimento_pieza.c.id]

    # Insertar metrica_dia y metrica_desglose para este ad
    md.guardar_dias({"ad_" + ad_id: ep_id}, [{**FILA_DIA, "ad_id": "ad_" + ad_id}])
    md.guardar_desglose({"ad_" + ad_id: ep_id}, "edad_genero",
                        [{**FILA_DIA, "ad_id": "ad_" + ad_id, "age": "25-34", "gender": "female"}])

    # Verificar que hay datos antes del delete
    with db.conectar() as con:
        n_dias = con.execute(sa.select(sa.func.count()).select_from(db.metrica_dia)
                            .where(db.metrica_dia.c.experimento_pieza_id == ep_id)).scalar()
        n_desgloses = con.execute(sa.select(sa.func.count()).select_from(db.metrica_desglose)
                                 .where(db.metrica_desglose.c.experimento_pieza_id == ep_id)).scalar()
        assert n_dias == 1 and n_desgloses == 1

    # Eliminar el ad (debe limpiar metrica_dia, metrica_desglose, metrica_snapshot y experimento_pieza)
    ads.eliminar("test", ad_id)

    # Verificar que no quedan filas de metrica_dia ni metrica_desglose para este ep
    with db.conectar() as con:
        n_dias = con.execute(sa.select(sa.func.count()).select_from(db.metrica_dia)
                            .where(db.metrica_dia.c.experimento_pieza_id == ep_id)).scalar()
        n_desgloses = con.execute(sa.select(sa.func.count()).select_from(db.metrica_desglose)
                                 .where(db.metrica_desglose.c.experimento_pieza_id == ep_id)).scalar()
        n_pieza = con.execute(sa.select(sa.func.count()).select_from(db.experimento_pieza)
                             .where(db.experimento_pieza.c.id == ep_id)).scalar()
        assert n_dias == 0 and n_desgloses == 0 and n_pieza == 0


def test_fk_impide_borrar_pieza_con_metrica_dia_huerfana(base_temporal):
    """Verifica que la FK de metrica_dia a experimento_pieza está activa:
    intentar borrar experimento_pieza mientras tiene metrica_dia hijos levanta
    IntegrityError. Esto documenta por qué ads.eliminar y rendimiento.sembrar.limpiar
    deben borrar metrica_dia/metrica_desglose antes de borrar experimento_pieza."""
    import db

    # Crear pieza y detalles
    db_mod = base_temporal
    with db_mod.conectar() as con:
        eid = con.execute(db_mod.experimento.insert().values(
            cliente="fk_test", creado_en=db_mod.ahora(), actualizado_en=db_mod.ahora(),
            nombre="Test", modo="manual", estado="corriendo")).inserted_primary_key[0]
        ep_id = con.execute(db_mod.experimento_pieza.insert().values(
            cliente="fk_test", creado_en=db_mod.ahora(), actualizado_en=db_mod.ahora(),
            experimento_id=eid, estado="en_cola")).inserted_primary_key[0]
        # Insertar metrica_dia manualmente
        con.execute(db_mod.metrica_dia.insert().values(
            experimento_pieza_id=ep_id, fecha="2026-10-01", impresiones=100,
            actualizado_en=db_mod.ahora()))

    # Intentar borrar solo experimento_pieza sin borrar metrica_dia primero
    import pytest
    with pytest.raises(sa.exc.IntegrityError):
        with db_mod.conectar() as con:
            con.execute(db_mod.experimento_pieza.delete().where(db_mod.experimento_pieza.c.id == ep_id))


@pytest.fixture()
def con_meta(dos_piezas, monkeypatch):
    """Credenciales de mentira y un auth.llamar que responde por tipo de consulta."""
    import lanzador
    import meta_detalle as md
    monkeypatch.setattr(lanzador.meta_conexion, "credenciales_ads",
                        lambda c: {"token": "TOKEN-SECRETO", "ad_account_id": "123", "page_id": "2"})
    respuestas = {"diario": {"data": [{**FILA_DIA, "ad_id": "ad_1"}, {**FILA_DIA, "ad_id": "ad_2"}]},
                  "rankings": {"data": [{"ad_id": "ad_1", "quality_ranking": "AVERAGE"}]}}
    fallar = {}
    llamadas = []
    params_por_parte = {}

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        params = params or {}
        parte = (params.get("breakdowns") and [k for k, v in md.DIMENSIONES.items() if v == params["breakdowns"]][0]
                 or ("diario" if "time_increment" in params else "rankings"))
        llamadas.append(parte)
        params_por_parte[parte] = dict(params)
        if parte in fallar:
            raise RuntimeError(fallar[parte])
        if parte in md.DIMENSIONES:
            return {"data": [{**FILA_DIA, "ad_id": "ad_1", "age": "25-34", "gender": "female",
                              "publisher_platform": "instagram", "platform_position": "feed",
                              "device_platform": "mobile_app", "region": "Antioquia"}]}
        return respuestas[parte]

    monkeypatch.setattr(md.auth, "llamar", llamar)
    return {**dos_piezas, "md": md, "fallar": fallar, "llamadas": llamadas, "params": params_por_parte}


def test_refrescar_detalle_guarda_todo_y_anota_en_extra(con_meta):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert r["dias"] == 2 and r["desgloses"] == 4 and r["rankings"] == 1 and r["errores"] == {} and not r["limite"]
    assert con_meta["llamadas"] == ["diario", "ubicacion", "edad_genero", "dispositivo", "region", "rankings"]
    det = ex.obtener("acme", eid)["extra"]["detalle_meta"]
    assert det["errores"] == {} and det["limite"] is False and det["actualizado_en"]


def test_refrescar_detalle_pide_desgloses_y_rankings_desde_la_creacion_hasta_hoy(con_meta):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    creado = ex.obtener("acme", eid)["creado_en"][:10]
    hoy = date(2026, 10, 2)
    md.refrescar_detalle("acme", eid, hoy=hoy)
    esperado = {"since": min(creado, hoy.isoformat()), "until": "2026-10-02"}
    for parte in ("ubicacion", "edad_genero", "dispositivo", "region", "rankings"):
        p = con_meta["params"][parte]
        assert json.loads(p["time_range"]) == esperado and "date_preset" not in p, parte
    # un experimento «creado en el futuro» (reloj distinto) nunca pide desde después de hoy
    con_meta["params"].clear()
    md.refrescar_detalle("acme", eid, hoy=date(2000, 1, 1))
    assert json.loads(con_meta["params"]["region"]["time_range"]) == {"since": "2000-01-01", "until": "2000-01-01"}


def test_un_desglose_que_falla_no_tumba_los_otros_ni_filtra_el_token(con_meta):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    con_meta["fallar"]["region"] = 'Meta Ads (act_123/insights) respondió 400: {"error":{"code":100,"message":"bad access_token=TOKEN-SECRETO"}}'
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert r["desgloses"] == 3 and r["rankings"] == 1 and "region" in r["errores"]
    det = ex.obtener("acme", eid)["extra"]["detalle_meta"]
    assert "TOKEN-SECRETO" not in json.dumps(det) and "region" in det["errores"]


def test_limite_de_meta_para_la_pasada(con_meta):
    md, eid = con_meta["md"], con_meta["eid"]
    con_meta["fallar"]["ubicacion"] = 'Meta Ads (act_123/insights) respondió 400: {"error":{"code":17,"message":"User request limit reached"}}'
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert r["limite"] is True and r["dias"] == 2
    assert con_meta["llamadas"] == ["diario", "ubicacion"]   # no sigue golpeando a Meta


def test_falla_el_diario_no_lanza(con_meta):
    md, eid = con_meta["md"], con_meta["eid"]
    con_meta["fallar"]["diario"] = "Meta Ads (act_123/insights) falló en red: ConnectionError"
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert "diario" in r["errores"] and r["dias"] == 0


def test_red_caida_corta_la_pasada_sin_marcar_limite(con_meta):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    con_meta["fallar"]["diario"] = "Meta Ads (act_123/insights) falló en red: ConnectionError"
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert con_meta["llamadas"] == ["diario"]   # no sigue golpeando a Meta
    assert r["cortado"] is True and r["limite"] is False and "diario" in r["errores"]
    det = ex.obtener("acme", eid)["extra"]["detalle_meta"]
    assert det["cortado"] is True and det["limite"] is False and "diario" in det["errores"]


def test_http_5xx_corta_la_pasada_pero_un_4xx_no(con_meta):
    md, eid = con_meta["md"], con_meta["eid"]
    con_meta["fallar"]["ubicacion"] = 'Meta Ads (act_123/insights) respondió 503: {"error":{"message":"Service Unavailable"}}'
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert con_meta["llamadas"] == ["diario", "ubicacion"] and r["cortado"] is True and r["limite"] is False
    # un 400 (código 100) sigue su camino: las otras partes se piden
    con_meta["llamadas"].clear()
    con_meta["fallar"]["ubicacion"] = 'Meta Ads (act_123/insights) respondió 400: {"error":{"code":100,"message":"x"}}'
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert len(con_meta["llamadas"]) == 6 and r["cortado"] is False and "ubicacion" in r["errores"]


def test_sin_campana_o_de_otro_proyecto_no_llama(con_meta):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    assert md.refrescar_detalle("otro", eid)["dias"] == 0
    ex.actualizar("acme", eid, meta_campaign_id=None)
    assert md.refrescar_detalle("acme", eid)["dias"] == 0
    assert con_meta["llamadas"] == []


def test_es_limite():
    import meta_detalle as md
    assert md.es_limite('respondió 400: {"error":{"code":613}}')
    assert md.es_limite('respondió 400: {"error":{"code":80000,"message":"There have been too many calls"}}')
    assert not md.es_limite('respondió 400: {"error":{"code":100}}') and not md.es_limite("")


def test_es_limite_cubre_la_familia_de_limites_por_caso_de_uso():
    import meta_detalle as md
    import meta_errores
    for codigo in (4, 17, 32, 613, 80000, 80001, 80002, 80003, 80004, 80005, 80006, 80008, 80009, 80014):
        texto = 'respondió 400: {"error":{"code":%d}}' % codigo
        assert meta_errores.es_limite(texto) and md.es_limite(texto), codigo
    assert not meta_errores.es_limite('respondió 400: {"error":{"code":80007}}')   # no es de la familia
    assert not meta_errores.es_limite(None)


def test_actualizar_extra_que_falla_no_lanza(con_meta, monkeypatch):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    def actualizar_falla(*args, **kwargs):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(md.experimentos, "actualizar_extra", actualizar_falla)
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert r["dias"] == 2 and r["desgloses"] == 4 and r["rankings"] == 1
    # no exception raised, result still returned normally


def test_desde_para_que_falla_anota_interno_no_llama_meta(con_meta, monkeypatch):
    md, eid = con_meta["md"], con_meta["eid"]
    def desde_para_falla(*args, **kwargs):
        raise ValueError("invalid date format")
    monkeypatch.setattr(md, "desde_para", desde_para_falla)
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert "interno" in r["errores"] and r["dias"] == 0 and r["desgloses"] == 0
    assert con_meta["llamadas"] == []  # no Meta calls made


def test_tarea_exp_detalle_y_encolar_todos(con_meta, monkeypatch):
    import cola
    import tareas
    from tareas import experimentos as t_exp
    md, eid = con_meta["md"], con_meta["eid"]
    encoladas = []
    monkeypatch.setattr(md.cola, "encolar", lambda tipo, payload, **kw: encoladas.append((tipo, payload, kw)) or 1)
    assert md.encolar_todos() == 1
    tipo, payload, kw = encoladas[0]
    assert tipo == "exp_detalle" and payload == {"cliente": "acme", "experimento_id": eid}
    assert kw["job_id"] == t_exp.job_id_detalle("acme", eid) and kw["max_intentos"] == 2 and kw["cliente"] == "acme"
    texto = tareas.REGISTRO["exp_detalle"]({"payload": payload, "job_id": kw["job_id"]})
    assert "2" in texto   # «Detalle de Meta al día (2 días de anuncios…)»


# --- exp_detalle: honesto y con reintento real --------------------------------

def _resultado(**kw):
    return {"dias": 2, "desgloses": 4, "rankings": 1, "limite": False, "errores": {}, "cortado": False, **kw}


def _correr_exp_detalle(monkeypatch, resultado, **payload):
    import tareas
    from tareas import experimentos as t_exp  # noqa: F401 — registra exp_detalle
    import meta_detalle as md
    monkeypatch.setattr(md, "refrescar_detalle", lambda cliente, experimento_id, hoy=None: resultado)
    return tareas.REGISTRO["exp_detalle"]({"payload": {"cliente": "acme", "experimento_id": 7, **payload}, "job_id": "j"})


def test_exp_detalle_con_limite_sigue_con_continuar_en_media_hora(monkeypatch):
    from datetime import datetime, timedelta
    import tareas
    antes = datetime.now()
    r = _correr_exp_detalle(monkeypatch, _resultado(limite=True, errores={"ubicacion": "code 17"}))
    assert isinstance(r, tareas.Continuar) and r.tipo == "exp_detalle"
    assert r.payload == {"cliente": "acme", "experimento_id": 7, "vuelta": 1} and r.mensaje
    assert isinstance(r.ejecutar_desde, datetime) and r.ejecutar_desde >= antes + timedelta(minutes=29)
    # la vuelta crece de una en una
    r2 = _correr_exp_detalle(monkeypatch, _resultado(limite=True), vuelta=2)
    assert isinstance(r2, tareas.Continuar) and r2.payload["vuelta"] == 3


def test_exp_detalle_a_la_tercera_vuelta_con_limite_termina_y_lo_dice(monkeypatch):
    import tareas
    r = _correr_exp_detalle(monkeypatch, _resultado(limite=True, errores={"region": "code 17"}), vuelta=3)
    assert isinstance(r, str) and not isinstance(r, tareas.Continuar)
    assert "siguió pidiendo esperar" in r and "al día" not in r


def test_exp_detalle_con_errores_nombra_las_partes_y_no_dice_al_dia(monkeypatch):
    r = _correr_exp_detalle(monkeypatch, _resultado(errores={"region": "x", "rankings": "y"}))
    assert isinstance(r, str) and "incompleto" in r and "region" in r and "rankings" in r and "al día" not in r


def test_exp_detalle_sin_errores_dice_al_dia(monkeypatch):
    r = _correr_exp_detalle(monkeypatch, _resultado())
    assert "al día" in r and "2" in r and "4" in r


# --- aislamiento de guardar_desglose entre experimentos -----------------------

def test_guardar_desglose_ignora_un_ad_ajeno_y_no_toca_el_juego_de_otra_pieza(dos_piezas):
    import meta_detalle as md
    db, ep1, ep2 = dos_piezas["db"], dos_piezas["ep1"], dos_piezas["ep2"]
    fila = lambda ad, edad: {**FILA_DIA, "ad_id": ad, "age": edad, "gender": "female"}  # noqa: E731
    md.guardar_desglose({"ad_1": ep1, "ad_2": ep2}, "edad_genero", [fila("ad_1", "18-24"), fila("ad_2", "25-34")])
    # reemplazar el juego de ep1, con una fila de un anuncio que no es de este mapa: se ignora
    n = md.guardar_desglose({"ad_1": ep1}, "edad_genero", [fila("ad_1", "35-44"), fila("ad_2", "55-64"), fila("ad_ajeno", "65+")])
    assert n == 1
    por_ep = {}
    for f in _filas(db, db.metrica_desglose):
        por_ep.setdefault(f["experimento_pieza_id"], []).append(f["clave"])
    assert por_ep == {ep1: ["35-44|female"], ep2: ["25-34|female"]}   # ep2 intacto, ep1 reemplazado


@pytest.mark.parametrize('valor', ['inf', 'nan', '1e999', '1e30'])
def test_num_rechaza_valores_no_persistibles(valor):
    import meta_detalle as md
    assert md.fila_diaria({'impressions': valor})['impresiones'] == 0


def test_ranking_rechaza_valor_ajeno():
    import meta_detalle as md
    assert md._ranking('inventado') is None


def test_no_guarda_fecha_invalida(dos_piezas):
    import meta_detalle as md
    assert md.guardar_dias({'ad_1': dos_piezas['ep1']},
                           [{**FILA_DIA, 'date_start': '2026-99-99'}]) == 0


def test_desglose_deduplica_clave_ya_acotada(dos_piezas):
    import meta_detalle as md
    filas = [{**FILA_DIA, 'region': 'x' * 120 + sufijo} for sufijo in ('a', 'b')]
    assert md.guardar_desglose({'ad_1': dos_piezas['ep1']}, 'region', filas) == 1


def test_paginas_marca_resultado_incompleto(monkeypatch):
    md, falso = _con_llamar(monkeypatch, [{'data': [], 'paging': {'next': 'x', 'cursors': {'after': 'a'}}}])
    monkeypatch.setattr(md, 'MAX_PAGINAS', 1)
    filas = md.pedir_rankings('cmp', '2026-09-01', '2026-10-01')
    assert filas.incompleto


def test_plazo_vencido_corta_la_pasada_sin_llamar_a_meta(con_meta, monkeypatch):
    """PND-117: con el plazo de la pasada vencido, no se hace ninguna llamada,
    la pasada queda «cortada» y el motivo se anota sin lanzar."""
    md, eid = con_meta["md"], con_meta["eid"]
    monkeypatch.setattr(md, "PLAZO_S", -1)
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert con_meta["llamadas"] == [] and r["cortado"] is True and r["dias"] == 0
    assert "límite de tiempo" in r["errores"]["diario"]

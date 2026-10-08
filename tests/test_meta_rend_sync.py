"""Copia de una cuenta de Meta (spec §6): un doble de `graph` que responde según el edge y los params, sin red."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

import db
from meta_rendimiento import cuentas, datos, graph, sync

CLI, ACT = "hf", "act_1"
HOY = date(2026, 10, 8)
FILA_META = {
    "spend": "100.5", "impressions": "1000", "reach": "800", "clicks": "30",
    "outbound_clicks": [{"action_type": "outbound_click", "value": "12"}],
    "actions": [{"action_type": "omni_purchase", "value": "3"}, {"action_type": "purchase", "value": "2"},
                {"action_type": "video_view", "value": "400"}],
    "action_values": [{"action_type": "purchase", "value": "250.5"}],
    "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "90"}],
    "date_start": "2026-10-01"}


def _dias(rango):
    a, b = date.fromisoformat(rango["since"]), date.fromisoformat(rango["until"])
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


class FakeGraph:
    """Responde según el edge y los params; guarda cada llamada para mirar los tramos que se pidieron."""

    def __init__(self, monkeypatch, info=None, campanas=None, conjuntos=None, anuncios=None, filas_anuncio=None,
                 falla_informe=None, falla_ventana=None, falla_anuncios=None):
        self.info = info if info is not None else {
            "name": "HappyFlops SE", "currency": "SEK", "timezone_name": "Europe/Stockholm",
            "account_status": 1, "disable_reason": 0, "amount_spent": "12345", "spend_cap": "0"}
        self.campanas = campanas if campanas is not None else [
            {"id": "c1", "name": "Otoño", "objective": "OUTCOME_SALES", "effective_status": "ACTIVE",
             "daily_budget": "50000", "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "created_time": "2026-09-01T10:00:00+0200"}]
        self.conjuntos = conjuntos if conjuntos is not None else [
            {"id": "s1", "name": "Mujeres", "campaign_id": "c1", "effective_status": "ACTIVE",
             "daily_budget": "50000", "lifetime_budget": "0", "optimization_goal": "OFFSITE_CONVERSIONS",
             "learning_stage_info": {"status": "FAIL"}}]
        self.anuncios = anuncios if anuncios is not None else [
            {"id": "a1", "name": "Video 1", "adset_id": "s1", "campaign_id": "c1", "effective_status": "ACTIVE",
             "creative": {"id": "cr1", "thumbnail_url": "https://x/1.jpg", "video_id": "v1"}}]
        self.filas_anuncio = filas_anuncio
        self.falla_informe, self.falla_ventana, self.falla_anuncios = falla_informe, falla_ventana, falla_anuncios
        self.llamadas = []
        self.asegurar = []
        monkeypatch.setattr(sync.graph, "get", self.get)
        monkeypatch.setattr(sync.graph, "paginar", self.paginar)
        monkeypatch.setattr(sync.graph, "informe", self.informe)
        monkeypatch.setattr(sync.tasas, "asegurar", lambda *a, **k: self.asegurar.append((a, k)))

    def _marca(self, tipo, edge, params):
        self.llamadas.append((tipo, edge, dict(params or {})))

    def de(self, tipo, termina=None):
        return [(e, p) for t, e, p in self.llamadas if t == tipo and (termina is None or e.endswith(termina))]

    def get(self, edge, token, params=None, timeout=60):
        self._marca("get", edge, params)
        assert token == "tok"
        if edge == ACT:
            return self.info
        assert edge == f"{ACT}/insights" and params["level"] == "account"
        if self.falla_ventana and params["date_preset"] == self.falla_ventana[0]:
            raise self.falla_ventana[1]
        w = int(params["date_preset"][5:-1])
        return {"data": [{"reach": str(w * 100), "frequency": "1.5"}]}

    def paginar(self, edge, token, params=None, max_paginas=200, timeout=60):
        self._marca("paginar", edge, params)
        if edge == f"{ACT}/campaigns":
            return self.campanas
        if edge == f"{ACT}/adsets":
            return self.conjuntos
        if edge == f"{ACT}/ads":
            if self.falla_anuncios:
                raise self.falla_anuncios
            return self.anuncios
        assert edge == f"{ACT}/insights"
        if params["level"] == "campaign":
            return [{"campaign_id": "c1", "reach": str(int(params["date_preset"][5:-1]) * 10), "frequency": "2.0"}]
        assert params["level"] == "account" and params["time_increment"] == 1
        return [dict(FILA_META, date_start=d) for d in _dias(json.loads(params["time_range"]))]

    def informe(self, ad_account_id, token, params, espera_max_s=600, intervalo_s=5, dormir=None):
        self._marca("informe", ad_account_id, params)
        if self.falla_informe:
            raise self.falla_informe
        assert params["level"] == "ad" and params["time_increment"] == 1
        if self.filas_anuncio is not None:
            return self.filas_anuncio
        return [dict(FILA_META, date_start=d, ad_id="a1", ad_name="Video 1", adset_id="s1", adset_name="Mujeres",
                     campaign_id="c1", campaign_name="Otoño") for d in _dias(json.loads(params["time_range"]))]


@pytest.fixture()
def cuenta(base_temporal):
    cuentas.elegir(CLI, [{"id": ACT, "name": "HF", "currency": "SEK"}])
    return ACT


def _objeto(nivel, objeto_id):
    t = db.meta_objeto
    with db.conectar() as con:
        return con.execute(sa.select(t).where(t.c.cliente == CLI, t.c.nivel == nivel,
                                                  t.c.objeto_id == objeto_id)).mappings().first()


# ------------------------------------------------------------ filas puras ---

def test_fila_cuenta_y_fila_anuncio():
    c = sync.fila_cuenta(FILA_META)
    assert c == {"fecha": "2026-10-01", "gasto": 100.5, "impresiones": 1000, "alcance": 800, "clics": 30,
                 "clics_salida": 12, "compras": 2.0, "valor": 250.5, "vistas_3s": 400, "thruplays": 90}
    a = sync.fila_anuncio(dict(FILA_META, ad_id=123, adset_id="s1", campaign_id="c1",
                               video_p25_watched_actions=[{"action_type": "video_view", "value": "70"}],
                               video_p100_watched_actions=[{"action_type": "video_view", "value": "20"}]))
    assert "alcance" not in a
    assert a["ad_id"] == "123" and a["adset_id"] == "s1" and a["campaign_id"] == "c1"
    assert (a["compras"], a["valor"], a["clics_salida"], a["vistas_3s"], a["thruplays"]) == (2.0, 250.5, 12, 400, 90)
    assert (a["p25"], a["p50"], a["p75"], a["p100"]) == (70, 0, 0, 20)


def test_fila_sin_clics_de_salida_usa_clics_de_enlace_y_sin_datos_da_ceros():
    f = sync.fila_cuenta({"date_start": "2026-10-02", "inline_link_clicks": "7", "spend": None, "clicks": "x"})
    assert f["clics_salida"] == 7 and f["gasto"] == 0.0 and f["clics"] == 0 and f["compras"] == 0.0
    # Sin ad_id no existe un "None" como anuncio: datos.reemplazar_anuncio_dias ignora la fila.
    assert sync.fila_anuncio({"date_start": "2026-10-02"})["ad_id"] is None


def test_objetos_de_presupuestos_aprendizaje_y_miniatura():
    campanas = [{"id": "c1", "name": "Otoño", "objective": "OUTCOME_SALES", "effective_status": "ACTIVE",
                 "daily_budget": "50000", "lifetime_budget": "0", "bid_strategy": "COST_CAP",
                 "created_time": "2026-09-01T10:00:00+0200"}]
    conjuntos = [{"id": "s1", "name": "Mujeres", "campaign_id": "c1", "effective_status": "PAUSED",
                  "lifetime_budget": "1250000", "optimization_goal": "OFFSITE_CONVERSIONS",
                  "learning_stage_info": {"status": "FAIL"}}]
    anuncios = [{"id": "a1", "name": "Video 1", "adset_id": "s1", "campaign_id": "c1", "effective_status": "ACTIVE",
                 "creative": {"id": "cr1", "thumbnail_url": "https://x/1.jpg", "video_id": "v1"}}]
    por_id = {o["objeto_id"]: o for o in sync.objetos_de(campanas, conjuntos, anuncios, moneda="SEK")}
    c, s, a = por_id["c1"], por_id["s1"], por_id["a1"]
    assert c["nivel"] == "campana" and c["presupuesto_diario"] == 500.0 and c["presupuesto_total"] is None
    assert c["objetivo"] == "OUTCOME_SALES" and c["estrategia_puja"] == "COST_CAP" and c["estado"] == "ACTIVE"
    assert s["nivel"] == "conjunto" and s["padre_id"] == "c1" and s["campaign_id"] == "c1"
    assert s["aprendizaje"] == "FAIL" and s["presupuesto_total"] == 12500.0 and s["optimizacion"] == "OFFSITE_CONVERSIONS"
    assert a["nivel"] == "anuncio" and a["padre_id"] == "s1" and a["miniatura_url"] == "https://x/1.jpg"
    assert a["creative_id"] == "cr1" and a["video_id"] == "v1"
    # Monedas sin decimales: el monto de Meta ya está en la unidad.
    clp = sync.objetos_de([{"id": "c9", "daily_budget": "50000"}], [], [], moneda="CLP")
    assert clp[0]["presupuesto_diario"] == 50000.0
    # Un presupuesto ausente, vacío o ilegible queda en None, nunca en 0.
    nada = sync.objetos_de([{"id": "c8", "daily_budget": "abc", "lifetime_budget": None}], [], [])
    assert nada[0]["presupuesto_diario"] is None and nada[0]["presupuesto_total"] is None


def test_hoy_local_usa_la_zona_de_la_cuenta():
    ahora = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    assert sync._hoy_local("Pacific/Kiritimati", ahora) == date(2026, 10, 9)
    assert sync._hoy_local("Pacific/Pago_Pago", ahora) == date(2026, 10, 8)
    assert sync._hoy_local("No/Existe", ahora) == date.today()
    assert sync._hoy_local(None, ahora) == date.today()


# ------------------------------------------------------------- la copia ---

def test_primera_copia_pide_395_dias_de_cuenta_y_90_de_anuncio(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch)
    r = sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    desde_c, desde_a = HOY - timedelta(days=395), HOY - timedelta(days=89)
    # Cuenta: 5 tramos de 90 días seguidos hasta hoy.
    tramos_c = [json.loads(p["time_range"]) for e, p in g.de("paginar", "/insights") if p["level"] == "account"]
    assert len(tramos_c) == 5
    assert tramos_c[0]["since"] == desde_c.isoformat() and tramos_c[-1]["until"] == HOY.isoformat()
    for ant, sig in zip(tramos_c, tramos_c[1:]):
        assert date.fromisoformat(sig["since"]) == date.fromisoformat(ant["until"]) + timedelta(days=1)
    assert all((date.fromisoformat(t["until"]) - date.fromisoformat(t["since"])).days <= 89 for t in tramos_c)
    # Anuncio: informes asíncronos de 30 días.
    tramos_a = [json.loads(p["time_range"]) for e, p in g.de("informe")]
    assert len(tramos_a) == 3
    assert tramos_a[0]["since"] == desde_a.isoformat() and tramos_a[-1]["until"] == HOY.isoformat()
    assert all(p["fields"] == sync.CAMPOS_ANUNCIO_DIA for e, p in g.de("informe"))
    assert all(p["fields"] == sync.CAMPOS_CUENTA_DIA for e, p in g.de("paginar", "/insights") if p["level"] == "account")
    # Lo escrito.
    assert r == {"dias_cuenta": 396, "filas_anuncio": 90, "objetos": 3,
                 "desde": desde_c.isoformat(), "hasta": HOY.isoformat()}
    assert datos.rango(CLI, [ACT]) == {"filas": 396, "desde": desde_c.isoformat(), "hasta": HOY.isoformat()}
    ads = datos.totales_por_anuncio(CLI, [ACT], desde_a.isoformat(), HOY.isoformat())
    assert len(ads) == 1 and ads[0]["ad_id"] == "a1" and ads[0]["dias_con_gasto"] == 90
    assert ads[0]["anuncio"] == "Video 1" and ads[0]["conjunto"] == "Mujeres" and ads[0]["campana"] == "Otoño"
    # La cuenta queda ok, con su moneda, su zona y el backfill hecho.
    c = cuentas.cuenta(CLI, ACT)
    assert c["estado"] == "ok" and c["error"] is None and c["moneda"] == "SEK" and c["ultima_copia"]
    assert c["zona_horaria"] == "Europe/Stockholm" and c["nombre"] == "HappyFlops SE"
    assert c["extra"]["backfill_hecho"] is True
    assert c["extra"]["cuenta"] == {"account_status": 1, "disable_reason": 0, "amount_spent": "12345", "spend_cap": "0"}
    # Las tasas piden la moneda de la cuenta para todo el rango de cuenta.
    (a, k), = g.asegurar
    assert a[0] == ["SEK"] and a[1] == desde_c.isoformat() and a[2] == HOY.isoformat()


def test_segunda_copia_solo_repasa_los_ultimos_7_dias(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    g.llamadas.clear()
    r = sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    tramos_c = [json.loads(p["time_range"]) for e, p in g.de("paginar", "/insights") if p["level"] == "account"]
    tramos_a = [json.loads(p["time_range"]) for e, p in g.de("informe")]
    seis = (HOY - timedelta(days=6)).isoformat()
    assert tramos_c == [{"since": seis, "until": HOY.isoformat()}]
    assert tramos_a == [{"since": seis, "until": HOY.isoformat()}]
    assert r["dias_cuenta"] == 7 and r["filas_anuncio"] == 7 and r["desde"] == seis
    # Repasar no duplica ni borra lo de antes de la ventana.
    assert datos.rango(CLI, [ACT])["filas"] == 396
    assert datos.totales_por_cuenta(CLI, [ACT], seis, HOY.isoformat())[ACT]["dias"] == 7


def test_objetos_guardados_con_presupuesto_aprendizaje_y_miniatura(cuenta, monkeypatch):
    FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    s, a, c = _objeto("conjunto", "s1"), _objeto("anuncio", "a1"), _objeto("campana", "c1")
    assert c["presupuesto_diario"] == 500.0 and c["objetivo"] == "OUTCOME_SALES" and c["estado"] == "ACTIVE"
    assert s["presupuesto_diario"] == 500.0 and s["aprendizaje"] == "FAIL" and s["padre_id"] == "c1"
    assert s["presupuesto_total"] is None   # «0» de Meta = sin presupuesto total
    assert a["miniatura_url"] == "https://x/1.jpg" and a["creative_id"] == "cr1" and a["video_id"] == "v1"
    assert datos.activos(CLI, [ACT])[ACT] == {"campana": 1, "conjunto": 1, "anuncio": 1, "aprendizaje_limitado": 1}


def test_los_listados_piden_sus_estados_y_el_de_anuncios_solo_los_activos(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    por_edge = {e.split("/")[-1]: p for e, p in g.de("paginar") if not e.endswith("/insights")}
    assert set(por_edge) == {"campaigns", "adsets", "ads"}
    assert all(p["limit"] == 500 for p in por_edge.values())
    estados = {k: json.loads(p["filtering"])[0]["value"] for k, p in por_edge.items()}
    assert set(estados["campaigns"]) == set(sync.ESTADOS) and "PAUSED" in estados["adsets"]
    assert sorted(estados["ads"]) == sorted(["ACTIVE", "WITH_ISSUES", "PENDING_REVIEW", "DISAPPROVED", "IN_PROCESS"])
    assert "creative{id,thumbnail_url,video_id}" in por_edge["ads"]["fields"]
    assert "learning_stage_info" in por_edge["adsets"]["fields"]


def test_un_anuncio_que_ya_no_vino_pierde_el_estado_pero_el_pausado_lo_conserva(cuenta, monkeypatch):
    datos.guardar_objetos(CLI, ACT, [
        {"nivel": "anuncio", "objeto_id": "viejo", "nombre": "Viejo", "estado": "ACTIVE"},
        {"nivel": "anuncio", "objeto_id": "pausado", "nombre": "Pausado", "estado": "PAUSED"},
        {"nivel": "campana", "objeto_id": "c_vieja", "nombre": "Campaña vieja", "estado": "PAUSED"},
        {"nivel": "conjunto", "objeto_id": "s_viejo", "nombre": "Conjunto viejo", "estado": "ACTIVE"}])
    FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert _objeto("anuncio", "viejo")["estado"] is None
    assert _objeto("anuncio", "pausado")["estado"] == "PAUSED"   # los pausados no se listan: no se les toca
    # Campañas y conjuntos sí se listan con todos sus estados: lo que no vino ya no existe.
    assert _objeto("campana", "c_vieja")["estado"] is None and _objeto("conjunto", "s_viejo")["estado"] is None
    assert _objeto("anuncio", "a1")["estado"] == "ACTIVE"


def test_los_nombres_de_los_insights_no_pisan_el_estado_ni_lo_guardado(cuenta, monkeypatch):
    # «pausado» no sale en el listado de anuncios (solo activos) pero sí en los insights de su gasto.
    datos.guardar_objetos(CLI, ACT, [
        {"nivel": "anuncio", "objeto_id": "pausado", "nombre": "Pausado", "estado": "PAUSED",
         "miniatura_url": "https://x/p.jpg"}])
    filas = [dict(FILA_META, date_start=HOY.isoformat(), ad_id="pausado", ad_name="Pausado (renombrado)",
                  adset_id="s1", adset_name="Mujeres", campaign_id="c1", campaign_name="Otoño"),
             dict(FILA_META, date_start=HOY.isoformat(), ad_id="solo_insights", ad_name="Solo insights",
                  adset_id="s1", adset_name="Mujeres", campaign_id="c1", campaign_name="Otoño"),
             dict(FILA_META, date_start=HOY.isoformat(), ad_id="sin_nombre", ad_name=None,
                  adset_id="s1", campaign_id="c1")]
    FakeGraph(monkeypatch, filas_anuncio=filas)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    p, n, sn = _objeto("anuncio", "pausado"), _objeto("anuncio", "solo_insights"), _objeto("anuncio", "sin_nombre")
    assert p["estado"] == "PAUSED" and p["miniatura_url"] == "https://x/p.jpg" and p["nombre"] == "Pausado (renombrado)"
    assert n["nombre"] == "Solo insights" and n["estado"] is None and n["padre_id"] == "s1"
    assert sn is None   # un anuncio sin nombre en los insights no crea un objeto vacío
    assert _objeto("conjunto", "s1")["estado"] == "ACTIVE" and _objeto("conjunto", "s1")["aprendizaje"] == "FAIL"
    assert _objeto("campana", "c1")["presupuesto_diario"] == 500.0


def test_alcance_por_ventana_a_nivel_de_cuenta_y_de_campana(cuenta, monkeypatch):
    FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    for w in (7, 14, 30, 90):
        assert datos.alcance(CLI, [ACT], w, "cuenta")[ACT] == {"alcance": w * 100, "frecuencia": 1.5}
        assert datos.alcance(CLI, [ACT], w, "campana")["c1"] == {"alcance": w * 10, "frecuencia": 2.0}


def test_una_ventana_con_parametro_invalido_se_salta_y_las_demas_siguen(cuenta, monkeypatch):
    FakeGraph(monkeypatch, falla_ventana=("last_14d", graph.ErrorGraph("parámetro inválido", codigo=100)))
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert datos.alcance(CLI, [ACT], 14, "cuenta") == {}
    assert datos.alcance(CLI, [ACT], 90, "cuenta")[ACT]["alcance"] == 9000
    c = cuentas.cuenta(CLI, ACT)
    assert c["estado"] == "ok" and c["extra"]["backfill_hecho"] is True


def test_otro_error_en_el_alcance_sube_y_la_cuenta_no_queda_ok(cuenta, monkeypatch):
    FakeGraph(monkeypatch, falla_ventana=("last_30d", graph.ErrorGraph("límite", codigo=17)))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    c = cuentas.cuenta(CLI, ACT)
    assert c["estado"] != "ok" and not c["extra"].get("backfill_hecho")


def test_un_limite_de_meta_en_el_informe_sube_y_la_cuenta_no_queda_ok(cuenta, monkeypatch):
    limite = graph.ErrorGraph("Meta pidió esperar", codigo=17)
    assert limite.limite
    FakeGraph(monkeypatch, falla_informe=limite)
    with pytest.raises(graph.ErrorGraph) as e:
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert e.value is limite
    c = cuentas.cuenta(CLI, ACT)
    assert c["estado"] != "ok" and not c["extra"].get("backfill_hecho") and c["ultima_copia"] is None


def test_un_listado_que_falla_no_deja_sin_estado_a_nadie(cuenta, monkeypatch):
    datos.guardar_objetos(CLI, ACT, [{"nivel": "anuncio", "objeto_id": "viejo", "nombre": "V", "estado": "ACTIVE"}])
    FakeGraph(monkeypatch, falla_anuncios=graph.ErrorGraph("página caída", codigo=1))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert _objeto("anuncio", "viejo")["estado"] == "ACTIVE"


def test_etapas_en_orden_con_progreso_creciente(cuenta, monkeypatch):
    FakeGraph(monkeypatch)
    vistas = []
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY, on_etapa=lambda nombre, p: vistas.append((nombre, p)))
    nombres = []
    for n, _ in vistas:
        if not nombres or nombres[-1] != n:
            nombres.append(n)
    assert nombres == ["Leyendo la cuenta", "Campañas, conjuntos y anuncios", "Métricas por día", "Alcance"]
    progresos = [p for _, p in vistas]
    assert progresos == sorted(progresos) and 0 <= progresos[0] and progresos[-1] <= 100


def test_la_fecha_de_hoy_sale_de_la_zona_de_la_cuenta(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch, info={"name": "N", "currency": "SEK", "timezone_name": "Europe/Stockholm"})
    sync.sincronizar(CLI, ACT, "tok")
    hasta = max(json.loads(p["time_range"])["until"] for e, p in g.de("informe"))
    assert abs((date.fromisoformat(hasta) - date.today()).days) <= 1
    c = cuentas.cuenta(CLI, ACT)
    assert c["extra"]["cuenta"] == {"account_status": None, "disable_reason": None, "amount_spent": None,
                                    "spend_cap": None}


def test_si_meta_no_trae_nombre_ni_moneda_se_conserva_lo_guardado(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch, info={"timezone_name": "Europe/Stockholm"})
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    c = cuentas.cuenta(CLI, ACT)
    assert c["nombre"] == "HF" and c["moneda"] == "SEK" and c["estado"] == "ok"
    assert g.asegurar[0][0][0] == ["SEK"]

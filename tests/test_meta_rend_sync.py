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
                 falla_informe=None, falla_ventana=None, falla_anuncios=None, anuncios_pausados=None,
                 falla_pausados=None, falla_informe_n=None, falla_cuenta_n=None, filas_cuenta=None,
                 miniaturas=None, falla_miniaturas=None, falla_informe_tras_pagina=None,
                 falla_cuenta_tras_pagina=None):
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
             "creative": {"id": "cr1", "thumbnail_url": "https://scontent.xx.fbcdn.net/1.jpg", "video_id": "v1"}}]
        self.anuncios_pausados = anuncios_pausados if anuncios_pausados is not None else []
        self.filas_anuncio = filas_anuncio
        self.falla_informe, self.falla_ventana, self.falla_anuncios = falla_informe, falla_ventana, falla_anuncios
        self.falla_pausados = falla_pausados
        self.falla_informe_n = falla_informe_n   # solo falla_informe en el informe número N (1 = el primero)
        self.filas_cuenta = filas_cuenta         # si se da, lo único que devuelve la consulta de cuenta por día
        self.falla_cuenta_n = falla_cuenta_n     # un límite de Meta (17) en la consulta de cuenta por día número N
        self.miniaturas = miniaturas or {}       # {ad_id: creative} que devuelve `?ids=` (los demás vienen sin creativo)
        self.falla_miniaturas = falla_miniaturas  # una excepción, o una lista con una por llamada a `?ids=` (None = bien)
        self.falla_informe_tras_pagina = falla_informe_tras_pagina   # el informe entrega UNA página y la siguiente falla
        self.falla_cuenta_tras_pagina = falla_cuenta_tras_pagina     # el listado de la cuenta falla en su 2.ª página
        self.paginas_entregadas = 0   # cuántas páginas llegaron al callback de un informe que luego falló
        self.paginas_informe = []   # cuántas páginas entregó cada informe al callback (None = devolvió la lista)
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
        if edge == "":     # la raíz de Graph: `?ids=` para pedir varios objetos de una vez
            n = len([1 for t, e, _ in self.llamadas if t == "get" and e == ""]) - 1
            falla = self.falla_miniaturas
            if isinstance(falla, list):
                falla = falla[n] if n < len(falla) else None
            if falla:
                raise falla
            return {i: ({"id": i, "creative": self.miniaturas[i]} if i in self.miniaturas else {"id": i})
                    for i in params["ids"].split(",")}
        assert edge == f"{ACT}/insights" and params["level"] == "account"
        if self.falla_ventana and params["date_preset"] == self.falla_ventana[0]:
            raise self.falla_ventana[1]
        w = int(params["date_preset"][5:-1])
        return {"data": [{"reach": str(w * 100), "frequency": "1.5"}]}

    def paginar(self, edge, token, params=None, max_paginas=200, timeout=60, por_pagina=None):
        self._marca("paginar", edge, params)
        assert max_paginas >= 200   # los listados no se cortan por el tope de páginas
        filas = self._filas(edge, params)
        if por_pagina is not None:
            for i in range(0, len(filas), 3):
                por_pagina(filas[i:i + 3])
            return len(filas)
        return filas

    def _filas(self, edge, params):
        if edge == f"{ACT}/campaigns":
            return self.campanas
        if edge == f"{ACT}/adsets":
            return self.conjuntos
        if edge == f"{ACT}/ads":
            if "PAUSED" in json.loads(params["filtering"])[0]["value"]:
                if self.falla_pausados:
                    raise self.falla_pausados
                return self.anuncios_pausados
            if self.falla_anuncios:
                raise self.falla_anuncios
            return self.anuncios
        assert edge == f"{ACT}/insights"
        if params["level"] == "campaign":
            return [{"campaign_id": "c1", "reach": str(int(params["date_preset"][5:-1]) * 10), "frequency": "2.0"}]
        assert params["level"] == "account" and params["time_increment"] == 1
        if self.falla_cuenta_n and len(self.de("paginar", "/insights")) - self._de_campana() == self.falla_cuenta_n:
            raise graph.ErrorGraph("Meta pidió esperar", codigo=17)
        if self.falla_cuenta_tras_pagina:
            raise self.falla_cuenta_tras_pagina    # `paginar` descarta lo que ya había leído al fallar
        if self.filas_cuenta is not None:
            return self.filas_cuenta
        return [dict(FILA_META, date_start=d) for d in _dias(json.loads(params["time_range"]))]

    def _de_campana(self):
        return len([1 for e, p in self.de("paginar", "/insights") if p["level"] == "campaign"])

    def informe(self, ad_account_id, token, params, espera_max_s=600, intervalo_s=5, dormir=None, por_pagina=None):
        self._marca("informe", ad_account_id, params)
        if self.falla_informe and (self.falla_informe_n is None or len(self.de("informe")) == self.falla_informe_n):
            raise self.falla_informe
        assert params["level"] == "ad" and params["time_increment"] == 1
        if self.filas_anuncio is not None:
            filas = self.filas_anuncio
        else:
            filas = [dict(FILA_META, date_start=d, ad_id="a1", ad_name="Video 1", adset_id="s1",
                          adset_name="Mujeres", campaign_id="c1", campaign_name="Otoño")
                     for d in _dias(json.loads(params["time_range"]))]
        if por_pagina is None:
            self.paginas_informe.append(None)
            return filas
        paginas = [filas[i:i + 3] for i in range(0, len(filas), 3)]
        if self.falla_informe_tras_pagina:
            por_pagina(paginas[0])
            self.paginas_entregadas += 1
            raise self.falla_informe_tras_pagina
        for pagina in paginas:   # como Meta: página a página; el llamador no recibe la lista
            por_pagina(pagina)
        self.paginas_informe.append(len(paginas))
        return len(filas)


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
                 "creative": {"id": "cr1", "thumbnail_url": "https://scontent.xx.fbcdn.net/1.jpg", "video_id": "v1"}}]
    por_id = {o["objeto_id"]: o for o in sync.objetos_de(campanas, conjuntos, anuncios, moneda="SEK")}
    c, s, a = por_id["c1"], por_id["s1"], por_id["a1"]
    assert c["nivel"] == "campana" and c["presupuesto_diario"] == 500.0 and c["presupuesto_total"] is None
    assert c["objetivo"] == "OUTCOME_SALES" and c["estrategia_puja"] == "COST_CAP" and c["estado"] == "ACTIVE"
    assert s["nivel"] == "conjunto" and s["padre_id"] == "c1" and s["campaign_id"] == "c1"
    assert s["aprendizaje"] == "FAIL" and s["presupuesto_total"] == 12500.0 and s["optimizacion"] == "OFFSITE_CONVERSIONS"
    assert a["nivel"] == "anuncio" and a["padre_id"] == "s1" and a["miniatura_url"] == "https://scontent.xx.fbcdn.net/1.jpg"
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
    # Cuenta: 5 tramos de 90 días seguidos hasta hoy, del más NUEVO al más viejo (el último queda corto).
    tramos_c = [json.loads(p["time_range"]) for e, p in g.de("paginar", "/insights") if p["level"] == "account"]
    assert len(tramos_c) == 5
    assert tramos_c[0]["until"] == HOY.isoformat() and tramos_c[-1]["since"] == desde_c.isoformat()
    for nuevo, viejo in zip(tramos_c, tramos_c[1:]):
        assert date.fromisoformat(nuevo["since"]) == date.fromisoformat(viejo["until"]) + timedelta(days=1)
    assert all((date.fromisoformat(t["until"]) - date.fromisoformat(t["since"])).days <= 89 for t in tramos_c)
    # Anuncio: informes asíncronos de 10 días (nueve), cuyas páginas se procesan una a una: sync nunca recibe la
    # lista cruda de un tramo (graph.informe devuelve solo la cuenta cuando hay callback).
    tramos_a = [json.loads(p["time_range"]) for e, p in g.de("informe")]
    assert len(tramos_a) == 9 and sync.TRAMO_ANUNCIO == 10
    assert tramos_a[0]["until"] == HOY.isoformat() and tramos_a[-1]["since"] == desde_a.isoformat()   # nuevo -> viejo
    for nuevo, viejo in zip(tramos_a, tramos_a[1:]):
        assert date.fromisoformat(nuevo["since"]) == date.fromisoformat(viejo["until"]) + timedelta(days=1)
    assert all((date.fromisoformat(t["until"]) - date.fromisoformat(t["since"])).days <= 9 for t in tramos_a)
    assert len(g.paginas_informe) == 9 and None not in g.paginas_informe
    assert all(p["fields"] == sync.CAMPOS_ANUNCIO_DIA for e, p in g.de("informe"))
    assert all(p["fields"] == sync.CAMPOS_CUENTA_DIA for e, p in g.de("paginar", "/insights") if p["level"] == "account")
    # Lo escrito.
    assert r == {"omitida": False, "dias_cuenta": 396, "filas_anuncio": 90, "objetos": 3,
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
    assert c["extra"]["backfill_cuenta"] is True and c["extra"]["backfill_anuncios"] is True
    assert c["extra"]["cuenta_desde"] == desde_c.isoformat() and c["extra"]["anuncios_desde"] == desde_a.isoformat()
    assert c["extra"]["listado_completo_en"]
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
    assert a["miniatura_url"] == "https://scontent.xx.fbcdn.net/1.jpg" and a["creative_id"] == "cr1" and a["video_id"] == "v1"
    assert datos.activos(CLI, [ACT])[ACT] == {"campana": 1, "conjunto": 1, "anuncio": 1, "aprendizaje_limitado": 1}


def test_los_listados_piden_sus_estados_y_los_anuncios_en_dos_tandas(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    listados = [(e.split("/")[-1], p) for e, p in g.de("paginar") if not e.endswith("/insights")]
    assert [k for k, _ in listados] == ["campaigns", "adsets", "ads", "ads"]
    campanas, conjuntos, activos, pausados = (p for _, p in listados)
    assert campanas["limit"] == 500 and conjuntos["limit"] == 500
    assert set(json.loads(campanas["filtering"])[0]["value"]) == set(sync.ESTADOS)
    assert "PAUSED" in json.loads(conjuntos["filtering"])[0]["value"]
    assert "learning_stage_info" in conjuntos["fields"]
    # Anuncios activos: con creativo (pesado) y de 100 en 100; pausados: solo campos ligeros y de 500 en 500.
    assert sorted(json.loads(activos["filtering"])[0]["value"]) == sorted(
        ["ACTIVE", "WITH_ISSUES", "PENDING_REVIEW", "DISAPPROVED", "IN_PROCESS"])
    assert "creative{id,thumbnail_url,video_id}" in activos["fields"] and activos["limit"] == 100
    assert sorted(json.loads(pausados["filtering"])[0]["value"]) == ["ADSET_PAUSED", "CAMPAIGN_PAUSED", "PAUSED"]
    assert pausados["fields"] == "id,name,adset_id,campaign_id,effective_status" and pausados["limit"] == 500


def test_un_anuncio_pausado_muestra_su_estado_real_y_solo_el_archivado_queda_sin_estado(cuenta, monkeypatch):
    datos.guardar_objetos(CLI, ACT, [
        {"nivel": "anuncio", "objeto_id": "viejo", "nombre": "Viejo", "estado": "ACTIVE"},
        {"nivel": "anuncio", "objeto_id": "archivado", "nombre": "Archivado", "estado": "PAUSED"},
        {"nivel": "anuncio", "objeto_id": "pausado", "nombre": "Pausado", "estado": None,
         "miniatura_url": "https://scontent.xx.fbcdn.net/p.jpg"},
        {"nivel": "campana", "objeto_id": "c_vieja", "nombre": "Campaña vieja", "estado": "PAUSED"},
        {"nivel": "conjunto", "objeto_id": "s_viejo", "nombre": "Conjunto viejo", "estado": "ACTIVE"}])
    FakeGraph(monkeypatch, anuncios_pausados=[
        {"id": "pausado", "name": "Pausado", "adset_id": "s1", "campaign_id": "c1", "effective_status": "ADSET_PAUSED"},
        {"id": "pausado2", "name": "Otro", "adset_id": "s1", "campaign_id": "c1", "effective_status": "PAUSED"}])
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    pausado = _objeto("anuncio", "pausado")
    # Un pausado se ve con su estado real (no «sin estado»); la miniatura que ya tenía se conserva.
    assert pausado["estado"] == "ADSET_PAUSED" and pausado["miniatura_url"] == "https://scontent.xx.fbcdn.net/p.jpg"
    assert _objeto("anuncio", "pausado2")["estado"] == "PAUSED"
    assert _objeto("anuncio", "a1")["estado"] == "ACTIVE"
    # Lo que no salió en NINGUNA de las dos listas ya no existe (archivado o borrado).
    assert _objeto("anuncio", "viejo")["estado"] is None and _objeto("anuncio", "archivado")["estado"] is None
    # Campañas y conjuntos sí se listan con todos sus estados: lo que no vino ya no existe.
    assert _objeto("campana", "c_vieja")["estado"] is None and _objeto("conjunto", "s_viejo")["estado"] is None


def test_los_nombres_de_los_insights_no_pisan_el_estado_ni_lo_guardado(cuenta, monkeypatch):
    # «pausado» sale en el listado de pausados y además trae un nombre nuevo en los insights de su gasto.
    datos.guardar_objetos(CLI, ACT, [
        {"nivel": "anuncio", "objeto_id": "pausado", "nombre": "Pausado", "estado": "PAUSED",
         "miniatura_url": "https://scontent.xx.fbcdn.net/p.jpg"}])
    filas = [dict(FILA_META, date_start=HOY.isoformat(), ad_id="pausado", ad_name="Pausado (renombrado)",
                  adset_id="s1", adset_name="Mujeres", campaign_id="c1", campaign_name="Otoño"),
             dict(FILA_META, date_start=HOY.isoformat(), ad_id="solo_insights", ad_name="Solo insights",
                  adset_id="s1", adset_name="Mujeres", campaign_id="c1", campaign_name="Otoño"),
             dict(FILA_META, date_start=HOY.isoformat(), ad_id="sin_nombre", ad_name=None,
                  adset_id="s1", campaign_id="c1")]
    FakeGraph(monkeypatch, filas_anuncio=filas, anuncios_pausados=[
        {"id": "pausado", "name": "Pausado", "adset_id": "s1", "campaign_id": "c1", "effective_status": "PAUSED"}])
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    p, n, sn = _objeto("anuncio", "pausado"), _objeto("anuncio", "solo_insights"), _objeto("anuncio", "sin_nombre")
    assert p["estado"] == "PAUSED" and p["miniatura_url"] == "https://scontent.xx.fbcdn.net/p.jpg" and p["nombre"] == "Pausado (renombrado)"
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


@pytest.mark.parametrize("falla", ["activos", "pausados"])
def test_un_listado_de_anuncios_que_falla_no_deja_sin_estado_a_nadie(cuenta, monkeypatch, falla):
    datos.guardar_objetos(CLI, ACT, [{"nivel": "anuncio", "objeto_id": "viejo", "nombre": "V", "estado": "ACTIVE"},
                                     {"nivel": "anuncio", "objeto_id": "pau", "nombre": "P", "estado": "PAUSED"}])
    error = graph.ErrorGraph("página caída", codigo=1)
    FakeGraph(monkeypatch, **({"falla_anuncios": error} if falla == "activos" else {"falla_pausados": error}))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    # Se marca solo cuando las DOS listas terminaron: con una caída a medias nadie pierde su estado.
    assert _objeto("anuncio", "viejo")["estado"] == "ACTIVE" and _objeto("anuncio", "pau")["estado"] == "PAUSED"
    assert cuentas.cuenta(CLI, ACT)["estado"] != "ok"


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
    class Reloj(datetime):   # 23:30 UTC del 15 de enero de 2030
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 15, 23, 30, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(sync, "datetime", Reloj)
    # En Kiritimati (UTC+14) ya es el 16; el 15 de enero de 2030 tampoco es el «hoy» del servidor.
    g = FakeGraph(monkeypatch, info={"name": "N", "currency": "SEK", "timezone_name": "Pacific/Kiritimati"})
    r = sync.sincronizar(CLI, ACT, "tok")
    assert r["hasta"] == "2030-01-16"
    assert max(json.loads(p["time_range"])["until"] for e, p in g.de("informe")) == "2030-01-16"
    assert max(json.loads(p["time_range"])["until"] for e, p in g.de("paginar", "/insights")
               if p["level"] == "account") == "2030-01-16"
    assert sync._hoy_local("Pacific/Pago_Pago") == date(2030, 1, 15)   # en Samoa Americana (UTC-11) aún es el 15
    c = cuentas.cuenta(CLI, ACT)
    assert c["extra"]["cuenta"] == {"account_status": None, "disable_reason": None, "amount_spent": None,
                                    "spend_cap": None}


def test_si_meta_no_trae_nombre_ni_moneda_se_conserva_lo_guardado(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch, info={"timezone_name": "Europe/Stockholm"})
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    c = cuentas.cuenta(CLI, ACT)
    assert c["nombre"] == "HF" and c["moneda"] == "SEK" and c["estado"] == "ok"
    assert g.asegurar[0][0][0] == ["SEK"]


def test_objetos_de_un_anuncio_ligero_no_trae_miniatura_ni_video():
    o, = sync.objetos_de([], [], [], anuncios_ligeros=[
        {"id": "p1", "name": "Pausado", "adset_id": "s1", "campaign_id": "c1", "effective_status": "PAUSED"}])
    assert o == {"nivel": "anuncio", "objeto_id": "p1", "padre_id": "s1", "campaign_id": "c1", "nombre": "Pausado",
                 "estado": "PAUSED"}   # sin miniatura_url / creative_id / video_id: no pisan los guardados


# ------------------------------------------- cuenta quitada, banderas y huecos ---

def test_una_cuenta_que_ya_no_esta_en_el_proyecto_se_omite_sin_llamar_a_meta(base_temporal, monkeypatch):
    g = FakeGraph(monkeypatch)
    etapas = []
    r = sync.sincronizar(CLI, ACT, "tok", hoy=HOY, on_etapa=lambda n, p: etapas.append(n))
    assert r == {"omitida": True, "dias_cuenta": 0, "filas_anuncio": 0, "objetos": 0, "desde": None, "hasta": None}
    assert g.llamadas == [] and g.asegurar == [] and etapas == []
    assert cuentas.cuenta(CLI, ACT) is None
    assert datos.rango(CLI, [ACT])["filas"] == 0 and datos.ultima_fecha(CLI, ACT, "anuncio") is None
    # La cuenta de OTRO proyecto tampoco cuenta como «en el proyecto».
    cuentas.elegir("otro", [{"id": ACT, "name": "HF", "currency": "SEK"}])
    assert sync.sincronizar(CLI, ACT, "tok", hoy=HOY)["omitida"] is True and g.llamadas == []


def test_si_falla_el_alcance_la_siguiente_copia_no_repite_los_13_meses(cuenta, monkeypatch):
    FakeGraph(monkeypatch, falla_ventana=("last_30d", graph.ErrorGraph("límite", codigo=17)))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    extra = cuentas.cuenta(CLI, ACT)["extra"]
    # Las dos mitades ya quedaron hechas aunque la copia no terminó; la bandera de «todo» aún no.
    assert extra["backfill_cuenta"] is True and extra["backfill_anuncios"] is True
    assert not extra.get("backfill_hecho")
    g = FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    seis = (HOY - timedelta(days=6)).isoformat()
    assert [json.loads(p["time_range"]) for e, p in g.de("paginar", "/insights") if p["level"] == "account"] == [
        {"since": seis, "until": HOY.isoformat()}]
    assert [json.loads(p["time_range"]) for e, p in g.de("informe")] == [{"since": seis, "until": HOY.isoformat()}]
    assert cuentas.cuenta(CLI, ACT)["extra"]["backfill_hecho"] is True


def test_si_falla_el_informe_de_anuncios_solo_se_repite_esa_mitad(cuenta, monkeypatch):
    FakeGraph(monkeypatch, falla_informe=graph.ErrorGraph("Meta pidió esperar", codigo=17))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    extra = cuentas.cuenta(CLI, ACT)["extra"]
    assert extra["backfill_cuenta"] is True and not extra.get("backfill_anuncios")
    g = FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert len(g.de("informe")) == 9                                                    # los 90 días de anuncio otra vez
    assert len([1 for e, p in g.de("paginar", "/insights") if p["level"] == "account"]) == 1   # la cuenta, solo 7 días


def test_la_bandera_antigua_backfill_hecho_vale_por_las_dos(cuenta, monkeypatch):
    cuentas.actualizar_extra(CLI, ACT, {"backfill_hecho": True})
    g = FakeGraph(monkeypatch)
    r = sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert len(g.de("informe")) == 1 and r["dias_cuenta"] == 7


def test_pasada_mas_de_una_semana_la_recopia_cubre_el_hueco(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    g.llamadas.clear()
    despues = HOY + timedelta(days=12)    # el último día copiado quedó 12 días atrás
    r = sync.sincronizar(CLI, ACT, "tok", hoy=despues)
    # Se repite el último día copiado (pudo copiarse con el día a medias) y se sigue hasta hoy, sin huecos.
    assert [json.loads(p["time_range"]) for e, p in g.de("paginar", "/insights") if p["level"] == "account"] == [
        {"since": HOY.isoformat(), "until": despues.isoformat()}]
    assert [json.loads(p["time_range"]) for e, p in g.de("informe")] == [
        {"since": HOY.isoformat(), "until": (HOY + timedelta(days=9)).isoformat()},
        {"since": (HOY + timedelta(days=10)).isoformat(), "until": despues.isoformat()}]
    assert r["desde"] == HOY.isoformat() and r["dias_cuenta"] == 13
    assert datos.rango(CLI, [ACT]) == {"filas": 396 + 12, "desde": (HOY - timedelta(days=395)).isoformat(),
                                       "hasta": despues.isoformat()}
    assert datos.ultima_fecha(CLI, ACT, "anuncio") == despues.isoformat()


def test_plan_primera_vez_hueco_y_relleno_a_medias():
    hoy = date(2026, 10, 8)

    def plan(*a):
        return [(x, y) for x, y, _ in sync._plan(hoy, *a)]

    def rellenos(*a):
        return [r for _, _, r in sync._plan(hoy, *a)]

    # Primera vez: toda la ventana inicial, del tramo más nuevo al más viejo, todo relleno (aunque ya haya datos
    # de una copia que no apuntó hasta dónde llegó).
    p = plan(89, 10, False, None, "2026-10-07")
    assert len(p) == 9 and p[0] == ("2026-09-29", "2026-10-08") and p[-1] == ("2026-07-11", "2026-07-20")
    assert all(rellenos(89, 10, False, None, None))
    # Ya hecha: los últimos 7 días (hoy - 6) ...
    for ultima in ("2026-10-08", "2026-10-04", None):
        assert plan(395, 90, True, None, ultima) == [("2026-10-02", "2026-10-08")]
    assert not any(rellenos(395, 90, True, None, None))
    # ... o desde el último día copiado si pasó más tiempo (se repite ese día) ...
    assert plan(89, 10, True, None, "2026-09-26") == [("2026-09-26", "2026-10-05"), ("2026-10-06", "2026-10-08")]
    # ... pero nunca más atrás de la ventana inicial (cuenta 395 días, anuncio 89).
    assert plan(395, 90, True, None, "2024-01-01")[0][0] == str(hoy - timedelta(days=395))
    assert plan(89, 10, True, None, "2026-01-01")[0][0] == str(hoy - timedelta(days=89))
    # Relleno a medias (marcador = el día más viejo ya copiado): lo reciente y, después, hacia atrás desde el día
    # anterior al marcador hasta el fondo de la ventana.
    p = sync._plan(hoy, 89, 10, False, "2026-09-09", "2026-10-08")
    assert p[0] == ("2026-10-02", "2026-10-08", False)
    assert p[1:] == [("2026-08-30", "2026-09-08", True), ("2026-08-20", "2026-08-29", True),
                     ("2026-08-10", "2026-08-19", True), ("2026-07-31", "2026-08-09", True),
                     ("2026-07-21", "2026-07-30", True), ("2026-07-11", "2026-07-20", True)]
    # Marcador ya en el fondo de la ventana (o un marcador ilegible): no queda relleno / se empieza de nuevo.
    assert sync._plan(hoy, 89, 10, False, "2026-07-11", "2026-10-08") == [("2026-10-02", "2026-10-08", False)]
    assert len(sync._plan(hoy, 89, 10, False, "basura", "2026-10-08")) == 9
    # Con la copia hecha el marcador sobra.
    assert sync._plan(hoy, 89, 10, True, "2026-09-09", "2026-10-08") == [("2026-10-02", "2026-10-08", False)]


# --------------------------------- R13: menos llamadas a Meta y relleno que se reanuda ---

def _listados_de_anuncios(g):
    return [p for e, p in g.de("paginar") if e.endswith("/ads")]


def _hace(horas):
    return (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")


def test_el_listado_completo_de_anuncios_se_hace_como_mucho_cada_20_horas(cuenta, monkeypatch):
    datos.guardar_objetos(CLI, ACT, [{"nivel": "anuncio", "objeto_id": "viejo", "nombre": "V", "estado": "ACTIVE"}])
    pausado = {"id": "pau", "name": "P", "adset_id": "s1", "campaign_id": "c1", "effective_status": "PAUSED"}
    g = FakeGraph(monkeypatch, anuncios_pausados=[pausado])
    # Corrida 1: sin marca, listado completo (activos + pausados), limpieza de archivados y marca nueva.
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert len(_listados_de_anuncios(g)) == 2
    assert _objeto("anuncio", "viejo")["estado"] is None and _objeto("anuncio", "pau")["estado"] == "PAUSED"
    marca = cuentas.cuenta(CLI, ACT)["extra"]["listado_completo_en"]
    assert marca

    # Corrida 2 enseguida: solo los activos; ni los pausados ni la limpieza de anuncios. Campañas y conjuntos sí
    # se vuelven a listar completos y se limpian.
    datos.guardar_objetos(CLI, ACT, [{"nivel": "anuncio", "objeto_id": "otro", "nombre": "O", "estado": "ACTIVE"},
                                     {"nivel": "campana", "objeto_id": "c2", "nombre": "C2", "estado": "ACTIVE"},
                                     {"nivel": "conjunto", "objeto_id": "s2", "nombre": "S2", "estado": "ACTIVE"}])
    g.llamadas.clear()
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    listados = _listados_de_anuncios(g)
    assert len(listados) == 1 and "creative{" in listados[0]["fields"]
    assert _objeto("anuncio", "otro")["estado"] == "ACTIVE"              # no se llamó a marcar_sin_estado de anuncios
    assert _objeto("anuncio", "pau")["estado"] == "PAUSED"
    assert _objeto("campana", "c2")["estado"] is None and _objeto("conjunto", "s2")["estado"] is None
    assert cuentas.cuenta(CLI, ACT)["extra"]["listado_completo_en"] == marca   # la marca no se toca

    # Corrida con la marca de hace 19 horas: todavía no.
    cuentas.actualizar_extra(CLI, ACT, {"listado_completo_en": _hace(19)})
    g.llamadas.clear()
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert len(_listados_de_anuncios(g)) == 1 and _objeto("anuncio", "otro")["estado"] == "ACTIVE"

    # Corrida 3 con la marca de hace 21 horas: otra vez completo, limpia lo que ya no existe y renueva la marca.
    vieja = _hace(21)
    cuentas.actualizar_extra(CLI, ACT, {"listado_completo_en": vieja})
    g.llamadas.clear()
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert len(_listados_de_anuncios(g)) == 2
    assert _objeto("anuncio", "otro")["estado"] is None and _objeto("anuncio", "pau")["estado"] == "PAUSED"
    assert cuentas.cuenta(CLI, ACT)["extra"]["listado_completo_en"] > vieja


def test_si_el_listado_de_pausados_falla_no_se_apunta_el_listado_completo(cuenta, monkeypatch):
    FakeGraph(monkeypatch, falla_pausados=graph.ErrorGraph("Meta pidió esperar", codigo=17))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert not cuentas.cuenta(CLI, ACT)["extra"].get("listado_completo_en")   # la próxima corrida lo reintenta
    g = FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert len(_listados_de_anuncios(g)) == 2


def _fechas(tabla):
    with db.conectar() as con:
        return [r[0] for r in con.execute(sa.select(tabla.c.fecha).where(tabla.c.cliente == CLI)).all()]


def test_el_relleno_de_anuncios_se_reanuda_desde_el_tramo_que_falto(cuenta, monkeypatch):
    # Meta pide esperar (17) al pedir el informe del tramo 4 de 9: los tramos 1 a 3 (los más nuevos) ya quedaron.
    FakeGraph(monkeypatch, falla_informe=graph.ErrorGraph("Meta pidió esperar", codigo=17), falla_informe_n=4)
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    extra = cuentas.cuenta(CLI, ACT)["extra"]
    assert extra["backfill_cuenta"] is True and not extra.get("backfill_anuncios") and not extra.get("backfill_hecho")
    assert extra["anuncios_desde"] == (HOY - timedelta(days=29)).isoformat()
    assert sorted(_fechas(db.meta_anuncio_dia)) == [(HOY - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]

    # Siguiente corrida: lo reciente (hoy - 6) y los tramos que faltaron, del más nuevo al más viejo.
    g = FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    pedidos = [(json.loads(p["time_range"])["since"], json.loads(p["time_range"])["until"]) for e, p in g.de("informe")]
    d = lambda n: (HOY - timedelta(days=n)).isoformat()   # noqa: E731
    assert pedidos == [(d(6), d(0))] + [(d(10 * k + 9), d(10 * k)) for k in range(3, 9)]
    assert len([1 for e, p in g.de("paginar", "/insights") if p["level"] == "account"]) == 1   # la cuenta, solo lo reciente
    extra = cuentas.cuenta(CLI, ACT)["extra"]
    assert extra["backfill_anuncios"] is True and extra["backfill_hecho"] is True
    # Ni faltan ni se repiten días: 90 días distintos, uno por fila (el anuncio a1 tiene gasto cada día).
    fechas = _fechas(db.meta_anuncio_dia)
    assert len(fechas) == 90 and sorted(set(fechas)) == sorted(d(i) for i in range(90))
    # Y la siguiente ya solo repasa lo reciente.
    g.llamadas.clear()
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert [(json.loads(p["time_range"])["since"]) for e, p in g.de("informe")] == [d(6)]


def test_el_relleno_de_la_cuenta_tambien_se_reanuda(cuenta, monkeypatch):
    # Meta pide esperar al pedir el tramo 3 de 5 de la cuenta (90 días cada uno): quedan los dos más nuevos.
    FakeGraph(monkeypatch, falla_cuenta_n=3)
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    d = lambda n: (HOY - timedelta(days=n)).isoformat()   # noqa: E731
    extra = cuentas.cuenta(CLI, ACT)["extra"]
    assert extra["cuenta_desde"] == d(179) and not extra.get("backfill_cuenta")
    assert len(_fechas(db.meta_cuenta_dia)) == 180
    g = FakeGraph(monkeypatch)
    r = sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    pedidos = [(json.loads(p["time_range"])["since"], json.loads(p["time_range"])["until"])
               for e, p in g.de("paginar", "/insights") if p["level"] == "account"]
    assert pedidos == [(d(6), d(0)), (d(269), d(180)), (d(359), d(270)), (d(395), d(360))]
    fechas = _fechas(db.meta_cuenta_dia)
    assert len(fechas) == 396 and sorted(set(fechas)) == sorted(d(i) for i in range(396))
    assert r["desde"] == d(395) and g.asegurar[0][0][1] == d(395)
    extra = cuentas.cuenta(CLI, ACT)["extra"]
    assert extra["backfill_cuenta"] is True and extra["backfill_anuncios"] is True
    assert len(g.de("informe")) == 9    # los anuncios no habían empezado: sus 90 días enteros, nuevo -> viejo


# ------------------------------------------------ R14: tasas de todos los días guardados ---

def test_las_tasas_se_piden_desde_el_dia_mas_viejo_guardado_aunque_esta_corrida_copie_solo_siete(cuenta, monkeypatch):
    # Corrida 1: la cuenta se rellena entera (396 días) pero el informe de anuncios falla antes de llegar a las tasas.
    FakeGraph(monkeypatch, falla_informe=graph.ErrorGraph("Meta pidió esperar", codigo=17))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert cuentas.cuenta(CLI, ACT)["extra"]["backfill_cuenta"] is True
    # Corrida 2: la cuenta ya está hecha, solo copia 7 días; las tasas igual cubren los 396 días guardados.
    g = FakeGraph(monkeypatch)
    r = sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert r["dias_cuenta"] == 7 and r["desde"] == (HOY - timedelta(days=6)).isoformat()
    (a, k), = g.asegurar
    assert a == (["SEK"], (HOY - timedelta(days=395)).isoformat(), HOY.isoformat()) and k == {"hoy": HOY}
    # Y una corrida más, con todo hecho, también.
    g.asegurar.clear()
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert g.asegurar[0][0][1] == (HOY - timedelta(days=395)).isoformat()


def test_sin_dias_de_cuenta_guardados_las_tasas_usan_el_desde_de_esta_corrida(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch, filas_cuenta=[])   # una cuenta sin gasto: Meta no devuelve ningún día
    r = sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert r["dias_cuenta"] == 0 and datos.primera_fecha(CLI, ACT, "cuenta") is None
    (a, _k), = g.asegurar
    assert a == (["SEK"], (HOY - timedelta(days=395)).isoformat(), HOY.isoformat())


# ---------------------------------------- R25: miniaturas de los anuncios con gasto reciente (`?ids=`) ---

def _fila_ad(ad_id, dia=None, **cambios):
    dia = dia or (HOY - timedelta(days=1))
    return dict(FILA_META, date_start=dia.isoformat(), ad_id=ad_id, ad_name=f"Anuncio {ad_id}", adset_id="s1",
                adset_name="Mujeres", campaign_id="c1", campaign_name="Otoño", **cambios)


def _creative(ad_id, url=None):
    return {"id": f"cr_{ad_id}", "thumbnail_url": url or f"https://scontent.xx.fbcdn.net/{ad_id}.jpg",
            "video_id": f"v_{ad_id}"}


def _pedidos_ids(g):
    """Los params de cada llamada a la raíz de Graph (`?ids=`) de una copia."""
    return [p for t, e, p in g.llamadas if t == "get" and e == ""]


def _pausado(ad_id):
    return {"id": ad_id, "name": f"Anuncio {ad_id}", "adset_id": "s1", "campaign_id": "c1",
            "effective_status": "PAUSED"}


def test_un_anuncio_pausado_con_gasto_reciente_trae_su_miniatura_en_la_corrida_del_listado_completo(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch, anuncios_pausados=[_pausado("p1")], filas_anuncio=[_fila_ad("p1"), _fila_ad("a1")],
                  miniaturas={"p1": _creative("p1")})
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    (pedido,) = _pedidos_ids(g)
    # a1 (activo) ya trajo su miniatura en el listado de esa misma corrida: solo se pide la del pausado.
    assert pedido["ids"] == "p1" and pedido["fields"] == "creative{id,thumbnail_url,video_id}"
    assert pedido["fields"] == sync.CAMPOS_MINIATURA
    p = _objeto("anuncio", "p1")
    assert p["miniatura_url"] == "https://scontent.xx.fbcdn.net/p1.jpg" and p["creative_id"] == "cr_p1"
    assert p["video_id"] == "v_p1" and p["extra"]["miniatura_en"]
    assert p["estado"] == "PAUSED" and p["nombre"] == "Anuncio p1"      # lo demás del objeto no se toca
    assert cuentas.cuenta(CLI, ACT)["estado"] == "ok"
    # Una corrida enseguida (listado liviano de cada 3 horas) no vuelve a pedir nada.
    g.llamadas.clear()
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert _pedidos_ids(g) == []


def test_las_miniaturas_se_piden_de_50_en_50(cuenta, monkeypatch):
    ids = [f"p{i:03d}" for i in range(120)]
    g = FakeGraph(monkeypatch, filas_anuncio=[_fila_ad(i) for i in ids], miniaturas={i: _creative(i) for i in ids})
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    pedidos = [p["ids"].split(",") for p in _pedidos_ids(g)]
    assert [len(x) for x in pedidos] == [50, 50, 20] and sorted(i for x in pedidos for i in x) == ids
    assert _objeto("anuncio", "p000")["miniatura_url"] and _objeto("anuncio", "p119")["miniatura_url"]


def test_solo_se_piden_los_anuncios_con_gasto_en_30_dias_y_sin_miniatura_al_dia(cuenta, monkeypatch):
    miniatura = "https://scontent.xx.fbcdn.net/{}.jpg"
    datos.guardar_objetos(CLI, ACT, [
        {"nivel": "anuncio", "objeto_id": "fresca", "nombre": "F", "miniatura_url": miniatura.format("fresca"),
         "extra": {"miniatura_en": _hace(5)}},
        {"nivel": "anuncio", "objeto_id": "vieja", "nombre": "V", "miniatura_url": miniatura.format("vieja"),
         "extra": {"miniatura_en": _hace(21)}},
        {"nivel": "anuncio", "objeto_id": "sin_marca", "nombre": "S", "miniatura_url": miniatura.format("sin_marca")}])
    filas = [_fila_ad(i) for i in ("fresca", "vieja", "sin_marca", "nueva")]
    filas.append(_fila_ad("hace_mucho", HOY - timedelta(days=45)))             # gastó, pero hace más de 30 días
    filas.append(_fila_ad("sin_gasto", spend="0"))
    g = FakeGraph(monkeypatch, filas_anuncio=filas, miniaturas={"vieja": _creative("vieja", miniatura.format("nueva_v"))})
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    (pedido,) = _pedidos_ids(g)
    assert pedido["ids"].split(",") == ["nueva", "sin_marca", "vieja"]
    assert _objeto("anuncio", "vieja")["miniatura_url"] == miniatura.format("nueva_v")
    assert _objeto("anuncio", "fresca")["miniatura_url"] == miniatura.format("fresca")
    assert _objeto("anuncio", "nueva")["miniatura_url"] is None      # Meta no trajo creativo: queda sin miniatura


def test_solo_se_guardan_miniaturas_de_hosts_de_meta_y_sin_token(cuenta, monkeypatch):
    malas = {"p1": "http://scontent.xx.fbcdn.net/p1.jpg", "p2": "https://evil.example/p2.jpg",
             "p3": "https://scontent.xx.fbcdn.net/p3.jpg?access_token=EAAsecreto"}
    ids = ["p1", "p2", "p3", "p4", "p5"]
    g = FakeGraph(monkeypatch, filas_anuncio=[_fila_ad(i) for i in ids],
                  miniaturas={**{i: _creative(i, u) for i, u in malas.items()},
                              "p4": {"id": "cr_p4", "video_id": "v_p4"},      # creativo sin thumbnail_url
                              "p5": _creative("p5")})
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert len(_pedidos_ids(g)) == 1
    for i in ("p1", "p2", "p3", "p4"):
        o = _objeto("anuncio", i)
        assert o["miniatura_url"] is None and not (o["extra"] or {}).get("miniatura_en")
    assert _objeto("anuncio", "p5")["miniatura_url"] == "https://scontent.xx.fbcdn.net/p5.jpg"


def test_un_anuncio_activo_con_miniatura_rara_no_la_guarda_ni_marca_la_fecha(cuenta, monkeypatch):
    activos = [{"id": "a1", "name": "A", "adset_id": "s1", "campaign_id": "c1", "effective_status": "ACTIVE",
                "creative": {"id": "cr1", "thumbnail_url": "https://evil.example/1.jpg?access_token=EAAx"}},
               {"id": "a2", "name": "B", "adset_id": "s1", "campaign_id": "c1", "effective_status": "ACTIVE",
                "creative": {"id": "cr2", "thumbnail_url": "https://scontent.xx.fbcdn.net/2.jpg"}}]
    g = FakeGraph(monkeypatch, anuncios=activos, filas_anuncio=[_fila_ad("a1"), _fila_ad("a2")])
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    a1, a2 = _objeto("anuncio", "a1"), _objeto("anuncio", "a2")
    assert a1["miniatura_url"] is None and not (a1["extra"] or {}).get("miniatura_en") and a1["creative_id"] == "cr1"
    assert a2["miniatura_url"] == "https://scontent.xx.fbcdn.net/2.jpg" and a2["extra"]["miniatura_en"]
    assert [p["ids"] for p in _pedidos_ids(g)] == ["a1"]       # el de la miniatura rara se vuelve a pedir; el otro no


def test_sin_el_listado_completo_no_se_piden_miniaturas(cuenta, monkeypatch):
    g = FakeGraph(monkeypatch, anuncios_pausados=[_pausado("p1")], filas_anuncio=[_fila_ad("p1")],
                  miniaturas={"p1": _creative("p1")})
    cuentas.actualizar_extra(CLI, ACT, {"listado_completo_en": _hace(5)})
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert _pedidos_ids(g) == [] and _objeto("anuncio", "p1")["miniatura_url"] is None


@pytest.mark.parametrize("falla", [
    graph.ErrorGraph("Meta rechazó la consulta", codigo=100),
    graph.ErrorGraph("Meta pidió esperar", codigo=17),
    RuntimeError("boom access_token=EAAsecreto"),
    ValueError("respuesta rara")])
def test_si_las_miniaturas_fallan_la_copia_termina_bien_y_el_registro_solo_dice_el_tipo(cuenta, monkeypatch, caplog, falla):
    ids = [f"p{i:03d}" for i in range(120)]
    g = FakeGraph(monkeypatch, filas_anuncio=[_fila_ad(i) for i in ids], miniaturas={i: _creative(i) for i in ids},
                  falla_miniaturas=[falla, None, None])
    with caplog.at_level("WARNING", logger="creatv.meta_rendimiento.sync"):
        r = sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    c = cuentas.cuenta(CLI, ACT)
    assert c["estado"] == "ok" and not c["error"] and c["extra"]["backfill_hecho"] is True and r["omitida"] is False
    assert type(falla).__name__ in caplog.text and "EAAsecreto" not in caplog.text and "boom" not in caplog.text
    # Un límite de uso deja de pedir; cualquier otro fallo salta ese lote y sigue con los demás.
    if isinstance(falla, graph.ErrorGraph) and falla.limite:
        assert len(_pedidos_ids(g)) == 1 and _objeto("anuncio", "p119")["miniatura_url"] is None
    else:
        assert len(_pedidos_ids(g)) == 3
        assert _objeto("anuncio", "p000")["miniatura_url"] is None and _objeto("anuncio", "p119")["miniatura_url"]


def test_si_no_se_puede_calcular_que_pedir_la_copia_termina_bien(cuenta, monkeypatch, caplog):
    def mal(*a, **k):
        raise sa.exc.OperationalError("SELECT", {}, Exception("access_token=EAAsecreto"))
    monkeypatch.setattr(sync.datos, "anuncios_sin_miniatura_al_dia", mal)
    g = FakeGraph(monkeypatch)
    with caplog.at_level("WARNING", logger="creatv.meta_rendimiento.sync"):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert cuentas.cuenta(CLI, ACT)["estado"] == "ok" and _pedidos_ids(g) == []
    assert "OperationalError" in caplog.text and "EAAsecreto" not in caplog.text


# ------------------------------ un tramo que falla a medias no deja filas a medias (revisión final, H1) ---

def _foto(tabla):
    """Todas las filas de la tabla (con id y marca de tiempo): lo que NO debe cambiar si un tramo falla."""
    with db.conectar() as con:
        return [dict(r) for r in con.execute(sa.select(tabla).where(tabla.c.cliente == CLI)
                                              .order_by(tabla.c.id)).mappings()]


def _siete_dias(**cambios):
    seis = HOY - timedelta(days=6)
    return [dict(FILA_META, date_start=d, **cambios) for d in _dias({"since": seis.isoformat(), "until": HOY.isoformat()})]


def test_un_informe_de_anuncios_que_falla_despues_de_entregar_una_pagina_deja_intacto_el_tramo(cuenta, monkeypatch):
    FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)               # copia buena que deja el tramo sembrado
    antes, extra_antes = _foto(db.meta_anuncio_dia), cuentas.cuenta(CLI, ACT)["extra"]
    assert len(antes) >= 7
    nuevas = [dict(f, ad_id="a1", ad_name="Video 1", adset_id="s1", adset_name="Mujeres", campaign_id="c1",
                   campaign_name="Otoño") for f in _siete_dias(spend="999")]
    g = FakeGraph(monkeypatch, filas_anuncio=nuevas,
                  falla_informe_tras_pagina=graph.ErrorGraph("Meta pidió esperar", codigo=17))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert g.paginas_entregadas == 1                          # sí llegó una página (3 filas) antes del error
    assert _foto(db.meta_anuncio_dia) == antes                # ni filas nuevas, ni borradas, ni cambiadas
    assert cuentas.cuenta(CLI, ACT)["extra"]["anuncios_desde"] == extra_antes["anuncios_desde"]
    assert cuentas.cuenta(CLI, ACT)["estado"] != "ok"


def test_un_listado_de_cuenta_que_falla_a_medias_deja_intacto_el_tramo(cuenta, monkeypatch):
    FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    antes_cuenta, antes_anuncio = _foto(db.meta_cuenta_dia), _foto(db.meta_anuncio_dia)
    assert len(antes_cuenta) >= 7
    FakeGraph(monkeypatch, filas_cuenta=_siete_dias(spend="999"),
              falla_cuenta_tras_pagina=graph.ErrorGraph("Meta pidió esperar", codigo=17))
    with pytest.raises(graph.ErrorGraph):
        sync.sincronizar(CLI, ACT, "tok", hoy=HOY)
    assert _foto(db.meta_cuenta_dia) == antes_cuenta
    assert _foto(db.meta_anuncio_dia) == antes_anuncio        # los anuncios ni se alcanzaron a pedir
    assert cuentas.cuenta(CLI, ACT)["estado"] != "ok"

"""Lanzar crea y activa (pedido de Daniel, 2026-10-08): «si la persona ya lo había configurado es porque ya le había
dado aprobar». La tarea `exp_lanzar` con `activar=True` lanza y, SOLO si todo salió bien, activa el experimento entero
por el mismo camino que «Activar todo» (`lanzador.cambiar_estado`). Si el lanzamiento falla o una pieza queda sin
anuncio, nada se activa; si la activación falla, queda en pausa con su motivo y sin reintento."""
import pytest

from tests.test_lanzador import entorno, entorno_app  # noqa: F401 — fixtures
from tests.test_rutas_experimentos import app  # noqa: F401 — fixture


@pytest.fixture()
def tarea_lanzar(monkeypatch):
    import tareas
    import trabajos
    monkeypatch.setattr(trabajos, "reportar", lambda job_id, **kw: None)
    tareas.cargar_todas()
    fn = tareas.REGISTRO["exp_lanzar"]

    def correr(eid, activar=True):
        payload = {"cliente": "acme", "experimento_id": eid}
        if activar:
            payload["activar"] = True
        return fn({"payload": payload, "job_id": f"acme__exp{eid}__lanzar"})
    return correr


def _activados(meta):
    return {kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "ACTIVE"}


def test_activar_tras_lanzar_activa_campana_conjuntos_y_anuncios(entorno, tarea_lanzar):
    ex, meta, eid = entorno["ex"], entorno["meta"], entorno["eid"]
    mensaje = tarea_lanzar(eid)
    e = ex.obtener("acme", eid)
    activos = _activados(meta)
    assert e["meta_campaign_id"] in activos
    assert {p["meta_adset_id"] for p in e["paises"]} <= activos
    assert {p["meta_ad_id"] for p in e["piezas"]} <= activos
    assert e["estado"] == "corriendo" and (e.get("extra") or {}).get("activado_en")
    assert (e.get("extra") or {}).get("fin_primera_activacion")   # PND-113: el plazo se fija en la primera activación
    assert all(p["estado"] == "activo" for p in e["piezas"]) and not e["error"]
    ev = next(ev for ev in e["eventos"] if ev["mensaje"].startswith("Activado al lanzar"))
    assert ev["datos"] == {"diario": 20150.0, "moneda": "COP"}   # 20.000 CO + 150 MX
    assert "20.150 COP" in ev["mensaje"] and "activo" in mensaje


def test_sin_activar_el_lanzamiento_queda_en_pausa(entorno, tarea_lanzar):
    """Los demás llamadores (sin `activar`) siguen como antes: todo en pausa."""
    ex, meta, eid = entorno["ex"], entorno["meta"], entorno["eid"]
    tarea_lanzar(eid, activar=False)
    assert not _activados(meta) and ex.obtener("acme", eid)["estado"] == "pausado"


def test_lanzamiento_que_falla_no_activa_nada(entorno, tarea_lanzar):
    ex, meta, eid = entorno["ex"], entorno["meta"], entorno["eid"]
    meta.fallar_en = "ad"
    with pytest.raises(RuntimeError):
        tarea_lanzar(eid)
    assert not _activados(meta)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and not (e.get("extra") or {}).get("activado_en")


def test_pieza_en_error_tras_lanzar_no_activa_nada(entorno, tarea_lanzar):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lanzar_real = lz.lanzar

    def lanzar_con_una_pieza_en_error(cliente, experimento_id, on_etapa=None, soltar=True):
        r = lanzar_real(cliente, experimento_id, on_etapa=on_etapa, soltar=soltar)
        pz = ex.obtener(cliente, experimento_id)["piezas"][0]
        ex.actualizar_pieza(cliente, pz["id"], estado="error", error="Meta rechazó el anuncio")
        return r
    entorno["monkeypatch"].setattr(lz, "lanzar", lanzar_con_una_pieza_en_error)
    mensaje = tarea_lanzar(eid)
    assert not _activados(meta)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and "No se activó" in mensaje and "1 pieza" in mensaje
    assert e["error"] == mensaje   # la tarjeta muestra el motivo
    assert any(ev["tipo"] == "error" and ev["mensaje"] == mensaje for ev in e["eventos"])


def test_activacion_que_falla_queda_en_pausa_con_su_motivo_y_sin_reintento(entorno, tarea_lanzar):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    adset_real = lz.meta_adset.actualizar_estado

    def adset_que_no_activa(oid, status, dry_run=False):
        if status == "ACTIVE" and oid.endswith("_3"):   # el segundo conjunto (MX): la campaña y CO ya activaron
            raise RuntimeError("Meta falló al activar")
        return adset_real(oid, status)
    entorno["monkeypatch"].setattr(lz.meta_adset, "actualizar_estado", adset_que_no_activa)
    avisos = []
    entorno["monkeypatch"].setattr(lz.notificaciones, "avisar", lambda c, tipo, asunto, cuerpo, **k: avisos.append((tipo, asunto, cuerpo)))
    mensaje = tarea_lanzar(eid)   # no lanza excepción: la tarea termina con el motivo, sin reintento automático
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and not (e.get("extra") or {}).get("activado_en")
    assert "no se pudo activar" in mensaje and "Quedó en pausa" in mensaje and e["error"] == mensaje
    # Lo que alcanzó a activarse se vuelve a pausar: nada gasta en Meta con el experimento «en pausa» aquí.
    pausados = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"]
    assert e["meta_campaign_id"] in pausados and "adset_2" in pausados
    assert any(ev["tipo"] == "error" and ev["mensaje"] == mensaje for ev in e["eventos"])
    assert all(p["estado"] == "pausado" for p in e["piezas"])
    assert [a[0] for a in avisos] == ["error_lanzamiento"] and mensaje in avisos[0][2]
    # Activar a mano después borra el motivo viejo.
    entorno["monkeypatch"].setattr(lz.meta_adset, "actualizar_estado", adset_real)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo" and not e["error"]


def test_app_activa_los_dos_conjuntos_de_cada_pais(entorno_app, tarea_lanzar):
    e = entorno_app
    tarea_lanzar(e["eid"])
    ex = e["ex"].obtener("acme", e["eid"])
    conjuntos = {i for p in ex["paises"] for i in (p.get("meta_adsets") or {}).values()}
    assert len(conjuntos) == 4 and conjuntos <= _activados(e["meta"])
    assert ex["meta_campaign_id"] in _activados(e["meta"])
    assert ex["estado"] == "corriendo" and all(p["estado"] == "activo" for p in ex["paises"])


# ---------- R1: mientras activa, sigue en «lanzando» y nada lo toca ----------

def _durante_la_activacion(entorno, fn):
    """Corre `fn(estado_visto)` justo antes de que `activar_tras_lanzar` active: el momento en que antes el
    experimento ya figuraba «pausado» y la tarjeta ofrecía Cerrar y «Activar todo»."""
    lz = entorno["lanzador"]
    activar_real = lz.activar_tras_lanzar

    def con_espia(cliente, experimento_id):
        fn(entorno["ex"].obtener(cliente, experimento_id)["estado"])
        return activar_real(cliente, experimento_id)
    entorno["monkeypatch"].setattr(lz, "activar_tras_lanzar", con_espia)


def test_entre_lanzar_y_activar_sigue_lanzando_y_cerrar_o_activar_a_mano_se_rechazan(entorno, tarea_lanzar):
    import dashboard
    from tests.test_rutas_experimentos import _cliente_admin
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    mp = entorno["monkeypatch"]
    mp.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado"})
    c = _cliente_admin(dashboard)
    vistos = []

    def intentar(estado):
        vistos.append(estado)
        c.post(f"/cliente/acme/experimentos/{eid}/cerrar")
        c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "ACTIVE"})
        c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "PAUSED"})
        vistos.append(ex.obtener("acme", eid)["estado"])
        with pytest.raises(ValueError, match="Espera a que termine"):
            lz.cambiar_estado("acme", eid, "ACTIVE")
    _durante_la_activacion(entorno, intentar)
    tarea_lanzar(eid)
    assert vistos == ["lanzando", "lanzando"]   # ni Cerrar ni Activar/Pausar lo movieron
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


def test_lanzar_sin_soltar_deja_lanzando(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    assert lz.lanzar("acme", eid, soltar=False) is None
    assert ex.obtener("acme", eid)["estado"] == "lanzando"


def test_interrupcion_a_mitad_de_activar_repausa_en_meta_y_queda_en_error(entorno):
    """El worker muere con la campaña y un conjunto ya ACTIVE: el hook de interrupción repausa todo en Meta antes de
    marcar el error, así nada queda gastando."""
    import tareas
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid, soltar=False)
    e = ex.obtener("acme", eid)
    lz.meta_campaign.actualizar_estado(e["meta_campaign_id"], "ACTIVE")       # lo que alcanzó a activarse
    lz.meta_adset.actualizar_estado(e["paises"][0]["meta_adset_id"], "ACTIVE")
    meta.llamadas.clear()
    tareas.cargar_todas()
    tareas.AL_INTERRUMPIR["exp_lanzar"]({"payload": {"cliente": "acme", "experimento_id": eid, "activar": True}}, "se cayó")
    pausados = {kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"}
    assert e["meta_campaign_id"] in pausados and {p["meta_adset_id"] for p in e["paises"]} <= pausados
    assert {p["meta_ad_id"] for p in e["piezas"]} <= pausados
    assert not _activados(meta)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and "se cayó" in e["error"]


def test_reconciliacion_al_arrancar_repausa_un_lanzando_huerfano(entorno, monkeypatch, tmp_path):
    """El servidor arranca y encuentra un «lanzando» sin tarea viva (murió a mitad de activar): repausa en Meta y
    lo deja en error, nunca activo."""
    import dashboard
    from tests.test_i18n_guardado import _huerfanos_en_carpeta_temporal
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid, soltar=False)
    e = ex.obtener("acme", eid)
    lz.meta_campaign.actualizar_estado(e["meta_campaign_id"], "ACTIVE")
    meta.llamadas.clear()
    _huerfanos_en_carpeta_temporal(dashboard, monkeypatch, tmp_path)
    dashboard._reconciliar_huerfanos()
    pausados = {kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"}
    assert e["meta_campaign_id"] in pausados and {p["meta_ad_id"] for p in e["piezas"]} <= pausados
    assert ex.obtener("acme", eid)["estado"] == "error"


def test_activar_nunca_pisa_cerrado(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    ex.actualizar("acme", eid, estado="cerrado")
    lz._a_corriendo("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "cerrado"
    # Si algo lo sacara de «lanzando» antes de activar, activar_tras_lanzar no activa nada encima.
    ex.actualizar("acme", eid, estado="cerrado")
    entorno["meta"].llamadas.clear()
    mensaje = lz.activar_tras_lanzar("acme", eid)
    assert "No se activó" in mensaje and not _activados(entorno["meta"])
    assert ex.obtener("acme", eid)["estado"] == "cerrado"


# ---------- R2: reenviar «Nuevo experimento» no crea (ni activa) otro ----------

@pytest.fixture()
def rutas(base_temporal, monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))


def _form(base_temporal, **extra):
    from tests.test_experimentos_db import _pieza
    from tests.test_rutas_experimentos import FORM_PROBAR
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_rep")
    return dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO", f"{clon}:MX"], **extra)


@pytest.mark.parametrize("con_token", [True, False])
def test_dos_post_identicos_crean_un_solo_experimento_y_una_sola_tarea(app, base_temporal, rutas, con_token):
    import experimentos as ex
    from tests.test_rutas_bloque4 import _flashes
    datos = _form(base_temporal, **({"token_form": "abc123_token-x"} if con_token else {}))
    r1 = app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    _flashes(app["c"])
    r2 = app["c"].post("/cliente/acme/experimentos/probar", data=datos)
    (e,) = ex.cargar("acme")
    assert len(app["encolados"]) == 1 and app["encolados"][0]["payload"]["experimento_id"] == e["id"]
    assert r1.status_code == r2.status_code == 302 and f"exp={e['id']}" in r2.headers["Location"]
    assert "ya creó un experimento" in " ".join(_flashes(app["c"]))


def test_otro_formulario_con_otro_token_si_crea_otro(app, base_temporal, rutas):
    import experimentos as ex
    app["c"].post("/cliente/acme/experimentos/probar", data=_form(base_temporal, token_form="uno"))
    app["c"].post("/cliente/acme/experimentos/probar", data=_form(base_temporal, token_form="dos"))
    assert len(ex.cargar("acme")) == 2 and len(app["encolados"]) == 2


def test_la_pagina_trae_un_token_de_un_solo_uso_distinto_cada_vez(app, base_temporal, rutas):
    import re
    tokens = [re.search(r'name="token_form" value="([^"]+)"', app["c"].get("/cliente/acme/experimentos/nuevo").get_data(as_text=True)).group(1)
              for _ in range(2)]
    assert tokens[0] and tokens[0] != tokens[1]

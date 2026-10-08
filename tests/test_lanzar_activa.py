"""Lanzar crea y activa (pedido de Daniel, 2026-10-08): «si la persona ya lo había configurado es porque ya le había
dado aprobar». La tarea `exp_lanzar` con `activar=True` lanza y, SOLO si todo salió bien, activa el experimento entero
por el mismo camino que «Activar todo» (`lanzador.cambiar_estado`). Si el lanzamiento falla o una pieza queda sin
anuncio, nada se activa; si la activación falla, queda en pausa con su motivo y sin reintento."""
import pytest

from tests.test_lanzador import entorno, entorno_app  # noqa: F401 — fixtures


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

    def lanzar_con_una_pieza_en_error(cliente, experimento_id, on_etapa=None):
        r = lanzar_real(cliente, experimento_id, on_etapa=on_etapa)
        pz = ex.obtener(cliente, experimento_id)["piezas"][0]
        ex.actualizar_pieza(cliente, pz["id"], estado="error", error="Meta rechazó el anuncio")
        return r
    entorno["monkeypatch"].setattr(lz, "lanzar", lanzar_con_una_pieza_en_error)
    mensaje = tarea_lanzar(eid)
    assert not _activados(meta)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and "No se activó" in mensaje
    assert any(ev["tipo"] == "error" and ev["mensaje"] == mensaje for ev in e["eventos"])


def test_activacion_que_falla_queda_en_pausa_con_su_motivo_y_sin_reintento(entorno, tarea_lanzar):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    adset_real = lz.meta_adset.actualizar_estado

    def adset_que_no_activa(oid, status, dry_run=False):
        if status == "ACTIVE" and oid.endswith("_3"):   # el segundo conjunto (MX): la campaña y CO ya activaron
            raise RuntimeError("Meta falló al activar")
        return adset_real(oid, status)
    entorno["monkeypatch"].setattr(lz.meta_adset, "actualizar_estado", adset_que_no_activa)
    mensaje = tarea_lanzar(eid)   # no lanza excepción: la tarea termina con el motivo, sin reintento automático
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and not (e.get("extra") or {}).get("activado_en")
    assert "no se pudo activar" in mensaje and "Quedó en pausa" in mensaje and e["error"] == mensaje
    # Lo que alcanzó a activarse se vuelve a pausar: nada gasta en Meta con el experimento «en pausa» aquí.
    pausados = [kw["oid"] for t, kw in meta.llamadas if t == "estado" and kw["status"] == "PAUSED"]
    assert e["meta_campaign_id"] in pausados and "adset_2" in pausados
    assert any(ev["tipo"] == "error" and ev["mensaje"] == mensaje for ev in e["eventos"])
    assert all(p["estado"] == "pausado" for p in e["piezas"])
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

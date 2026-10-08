"""PND-114: la ruta legado usa el mismo candado que el worker de Meta."""
from threading import Event, Thread


def test_estado_ad_espera_el_candado_compartido(base_temporal, monkeypatch):
    import dashboard
    from tareas.meta import _LOCK
    from tests.test_rutas_experimentos import _cliente_admin
    c = _cliente_admin(dashboard)
    entro = Event()
    monkeypatch.setattr(dashboard.ads_mod, "cargar", lambda _: {"a": {"meta_ids": {"campaign_id": "camp", "adset_id": "set", "ad_id": "ad"}}})
    monkeypatch.setattr(dashboard.ads_mod, "actualizar", lambda *a, **k: None)
    monkeypatch.setattr(dashboard.meta_conexion, "credenciales_ads", lambda _: {"token": "llave-de-prueba", "ad_account_id": "cuenta", "page_id": "pagina"})
    monkeypatch.setattr(dashboard.meta_auth, "configurar", lambda *a: entro.set())
    monkeypatch.setattr(dashboard.meta_auth, "limpiar", lambda: None)
    llamadas = []
    monkeypatch.setattr(dashboard.meta_campaign, "actualizar_estado", lambda *a: llamadas.append(a))
    resultado = []
    with _LOCK:
        hilo = Thread(target=lambda: resultado.append(c.post("/cliente/acme/ads/a/estado", data={"estado": "ACTIVE"})))
        hilo.start()
        prematuro = entro.wait(0.3)
    hilo.join(timeout=5)
    assert not prematuro, "la ruta mezcló credenciales mientras el worker tenía el lock"
    assert not hilo.is_alive() and resultado[0].status_code == 302
    assert llamadas == [("camp", "ACTIVE"), ("set", "ACTIVE"), ("ad", "ACTIVE")]

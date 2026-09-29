"""Lo que se GUARDA (un error de una publicación o de un experimento, el
detalle de un gasto, un evento, el mensaje de una tarea) va en el idioma del
proyecto aunque lo arme una ruta mirada por alguien en otro idioma (spec
2026-09-26 §B8; fase 6). Lo que se RESPONDE sigue a quien mira."""
import idiomas
from tests.test_rutas_referentes import app  # noqa: F401 (fixture: proyecto y catálogo de prueba)


def test_error_guardado_de_una_publicacion_va_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import dashboard
    import organico
    guardados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda *a, **k: None)
    monkeypatch.setattr(organico, "actualizar", lambda c, pub_id, **kw: guardados.append(kw["error"]))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    with idiomas.en_idioma("es"):                     # quien mira, en español
        assert not dashboard._encolar_organico("acme", 1, [7])
    assert guardados == ["This piece already had a publication in progress; retry when it finishes."]


def _huerfanos_en_carpeta_temporal(dashboard, monkeypatch, tmp_path, clientes=()):
    """_reconciliar_huerfanos recorre BASE_DIR/clientes: una carpeta temporal
    para no tocar nunca los proyectos reales del repo."""
    for cliente in clientes:
        (tmp_path / "clientes" / cliente).mkdir(parents=True)
    (tmp_path / "clientes").mkdir(exist_ok=True)
    monkeypatch.setattr(dashboard, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)


def test_generacion_interrumpida_se_guarda_en_el_idioma_de_cada_proyecto(base_temporal, monkeypatch, tmp_path):
    import dashboard
    _huerfanos_en_carpeta_temporal(dashboard, monkeypatch, tmp_path, clientes=("acme", "otro"))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: {"acme": "en", "otro": "es"}[c])
    monkeypatch.setattr(dashboard.swaps_mod, "cargar", lambda c: {"s1": {"estado": "generando"}})
    guardados = {}
    monkeypatch.setattr(dashboard.swaps_mod, "guardar", lambda c, data: guardados.__setitem__(c, data["s1"]["error"]))
    monkeypatch.setattr(dashboard.creative_flow, "cargar", lambda c: {})
    monkeypatch.setattr(dashboard.conceptos_imagen, "cargar", lambda c: {})
    dashboard._reconciliar_huerfanos()
    assert guardados == {
        "acme": "The generation was interrupted because the server restarted — try again.",
        "otro": "La generación se interrumpió porque el servidor se reinició — vuelve a intentarlo.",
    }


def test_detalle_del_gasto_de_adaptar_invalido_va_en_el_idioma_del_proyecto(app, monkeypatch):
    """La respuesta (el JSON de error) sigue a quien mira; el `detalle` del
    gasto que queda en Configuración › Gasto, al proyecto."""
    import gastos
    import proyectos
    from referentes import recrear
    from tests.test_rutas_referentes import _sembrar
    monkeypatch.setattr(proyectos, "referentes_copycoders", lambda cliente: True)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: ("no es json", 80, 20))
    ids = _sembrar()
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "espejo_led"})
    assert r.status_code == 502
    assert gastos.historial("acme", limite=1)[0]["detalle"] == "Espejo LED · Price Slash Hero · invalid response"


def test_lanzamiento_interrumpido_se_guarda_en_el_idioma_del_proyecto(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import experimentos as ex
    from tests.test_experimentos_db import PAISES
    _huerfanos_en_carpeta_temporal(dashboard, monkeypatch, tmp_path)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="lanzando")
    dashboard._reconciliar_huerfanos()
    exp = ex.obtener("acme", eid)
    assert exp["estado"] == "error"
    assert exp["error"] == "The launch was interrupted; check Ads Manager and try again."

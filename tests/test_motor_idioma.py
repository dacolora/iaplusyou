"""El motor de ecommerce escribe en el idioma del proyecto (spec 2026-09-26
§B8): motivo del decisor, eventos y avisos por correo. El worker ya corre cada
tarea dentro de idiomas.en_idioma (tests/test_worker_idioma.py); aquí se
comprueba que los textos pasan por el catálogo. Sin red ni base: se
reemplazan notificaciones.avisar y las escrituras."""
import idiomas
from tests.i18n_util import _con_marca

EX = {"id": 7, "nombre": "Summer test"}
PZ = {"id": 3, "nombre": "Blue sandal", "pais": "CO"}


def _capturar_avisos(monkeypatch, modulo):
    enviados = []
    monkeypatch.setattr(modulo.notificaciones, "avisar",
                        lambda cliente, tipo, asunto, cuerpo: enviados.append((tipo, asunto, cuerpo)) or False)
    return enviados


def test_motivo_del_decisor_en_ingles_y_en_espanol():
    import decisor
    snaps = [{"impresiones": 10, "gasto": 1}]
    ctx = {"horas_activo": 3, "presupuesto_dia": 10}
    assert decisor.decidir(snaps, {}, ctx)["motivo"] == \
        "Sin evidencia todavía: 10 impresiones (mínimo 1000), gasto 1.00 (mínimo 20.00), 3 h de 48."
    with idiomas.en_idioma("en"):
        assert decisor.decidir([], {}, {})["motivo"] == "No metrics yet."
        assert decisor.decidir(snaps, {}, ctx)["motivo"] == \
            "No evidence yet: 10 impressions (minimum 1000), spend 1.00 (minimum 20.00), 3 h of 48."


def test_avisos_de_ganador_y_propuestas(monkeypatch):
    from tareas import experimentos as te
    enviados = _capturar_avisos(monkeypatch, te)
    resultado = {"ganadores": [PZ], "veredictos": [(PZ, {"motivo": "Winner: CTR 2.00%."})],
                 "organico_propuesto": set(), "propuestas": ["Scale CO +20%"]}
    with idiomas.en_idioma("en"):
        te._avisar_resultado("acme", EX, resultado)
    (t1, a1, c1), (t2, a2, c2) = enviados
    assert (t1, a1) == ("ganador", "Winner in “Summer test”: Blue sandal (CO)")
    assert (t2, a2) == ("propuesta", "1 proposal(s) awaiting your approval in “Summer test”")
    assert not any(_con_marca(x) for x in (c1, c2)), (c1, c2)


def test_aviso_de_rechazo_de_meta(monkeypatch):
    import lanzador
    enviados = _capturar_avisos(monkeypatch, lanzador)
    eventos = []
    monkeypatch.setattr(lanzador.experimentos, "registrar_evento",
                        lambda cliente, eid, tipo, texto, datos=None, ep_id=None: eventos.append(texto))
    with idiomas.en_idioma("en"):
        lanzador._avisar_rechazo_meta("acme", EX, PZ, "DISAPPROVED", "policy 4.2")
    ((tipo, asunto, cuerpo),) = enviados
    assert (tipo, asunto) == ("rechazo_meta", "Meta rejected an ad in “Summer test”")
    assert not _con_marca(cuerpo) and not _con_marca(eventos[0]), (cuerpo, eventos)


def test_aviso_de_error_de_lanzamiento(monkeypatch):
    import lanzador
    enviados = _capturar_avisos(monkeypatch, lanzador)
    with idiomas.en_idioma("en"):
        lanzador._avisar_error_lanzamiento("acme", EX, 7, "Invalid budget")
    ((tipo, asunto, cuerpo),) = enviados
    assert (tipo, asunto) == ("error_lanzamiento", "Launch of “Summer test” failed")
    assert "Invalid budget" in cuerpo and not _con_marca(cuerpo), cuerpo


def test_evento_de_cierre(monkeypatch):
    import lanzador
    eventos = []
    monkeypatch.setattr(lanzador.experimentos, "obtener", lambda c, eid: {"meta_campaign_id": None, "estado": "armando"})
    monkeypatch.setattr(lanzador.experimentos, "actualizar", lambda c, eid, **kw: None)
    monkeypatch.setattr(lanzador.experimentos, "registrar_evento",
                        lambda cliente, eid, tipo, texto, datos=None, ep_id=None: eventos.append(texto))
    with idiomas.en_idioma("en"):
        lanzador.cerrar("acme", 7)
    assert eventos == ["Experiment closed"]


def test_lote_terminado_en_el_idioma_del_proyecto(tmp_path, monkeypatch):
    import proyectos
    from tareas import sprints as ts
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    enviados = _capturar_avisos(monkeypatch, ts)
    eventos = []
    monkeypatch.setattr(ts.datos, "registrar_evento", lambda cliente, sid, tipo, texto, datos=None: eventos.append(texto))
    ts._avisar_lote_terminado("acme", 4, "October", 3, 1)      # la periódica no tiene contexto propio
    ((tipo, asunto, cuerpo),) = enviados
    assert (tipo, asunto) == ("sprint_lote", "Batch finished: October")
    assert eventos == ["Batch finished: 3 ready, 1 with errors"]
    assert not _con_marca(cuerpo), cuerpo


def test_tienda_rota_en_ingles(monkeypatch):
    from tareas import tiendas as tt
    enviados = _capturar_avisos(monkeypatch, tt)
    monkeypatch.setattr(tt.tiendas, "actualizar", lambda cliente, tid, **kw: None)
    tienda = {"id": 1, "nombre": "Glow Shop", "tipo": "shopify"}
    with idiomas.en_idioma("en"):
        tt._marcar_rota("acme", tienda, {"intentos": 1, "max_intentos": 1}, "productos", RuntimeError("token expired"))
    ((tipo, asunto, cuerpo),) = enviados
    assert (tipo, asunto) == ("tienda", "The store “Glow Shop” stopped syncing")
    assert "products" in cuerpo and not _con_marca(cuerpo), cuerpo

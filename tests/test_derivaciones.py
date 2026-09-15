"""Bloque 4 — derivaciones: re-ediciones y regeneraciones asíncronas que
terminan como piezas nuevas del experimento (hijo para `derivar`, el mismo
para `rescatar`). `trabajos.encolar` se captura (nada llega al worker),
`creative_flow` es real sobre la base temporal, y `lanzador`/`acciones.pedir`
son falsos."""
import pytest

from tests.test_experimentos_db import PAISES


def _sesion_con_video(cf, cliente="acme", modelo="wan3"):
    cf_id = cf.crear(cliente, [], ["p1"], [], "sandalia sobre arena", 10, "", "A", referencias_urls=["https://r"])
    cf.actualizar(cliente, cf_id, estado="video_listo", video_url="https://r2/v.mp4", modelo=modelo,
                  referencias=[{"tipo": "imagen", "etiqueta": "@Imagen 1", "url": "https://r", "frame_url": "https://r"}])
    return cf_id


@pytest.fixture()
def ent(base_temporal, monkeypatch):
    import acciones
    import creative_flow as cf
    import derivaciones as dv
    import experimentos as ex
    import trabajos
    encolados = []
    llamadas = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: (encolados.append(
        {"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])

    def _lanzar(cliente, eid, on_etapa=None):
        llamadas.append(("lanzar", eid))
        ex.actualizar(cliente, eid, estado="pausado", meta_campaign_id="camp")

    monkeypatch.setattr(dv.lanzador, "lanzar", _lanzar)
    monkeypatch.setattr(dv.lanzador, "lanzar_piezas_nuevas", lambda c, e: llamadas.append(("piezas_nuevas", e)))
    monkeypatch.setattr(acciones, "pedir", lambda c, e, accion, payload, motivo: (
        llamadas.append((accion, e, sorted(payload["ep_ids"]), motivo)), ("ejecutada", "ok"))[1])
    cf_id = _sesion_con_video(cf)
    final_id = cf.crear_final("acme", cf_id, "es", "CO")
    cf.actualizar_final("acme", final_id, estado="listo", url_video="https://r2/f.mp4")
    eid = ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", modo="auto")
    ep = ex.agregar_pieza("acme", eid, cf.pieza_id_por_legado("acme", final_id), "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id="ad1", estado="activo")
    ex.actualizar("acme", eid, estado="corriendo", meta_campaign_id="c1")
    return {"dv": dv, "ex": ex, "cf": cf, "eid": eid, "ep": ep, "cf_id": cf_id, "final_id": final_id,
            "encolados": encolados, "llamadas": llamadas}


def _derivacion(ex, eid, cliente="acme"):
    ds = ex.obtener(cliente, eid)["extra"]["derivaciones"]
    assert len(ds) == 1
    return ds[0]


def test_planificar_derivar_crea_hijo_con_reediciones_y_regeneraciones(ent):
    dv, ex, cf, eid, ep, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"], ent["cf_id"]
    hijo = dv.planificar("acme", eid, "derivar", {"ep_id": ep, "motivo": "ganadora en CO"})
    assert hijo != eid
    h = ex.obtener("acme", hijo)
    assert h["estado"] == "armando" and h["padre_experimento_id"] == eid
    assert h["nombre"] == "Cojín · derivado de Final es_CO"
    d = _derivacion(ex, hijo)
    assert d["tipo"] == "derivar" and d["estado"] == "produciendo" and d["origen_ep_id"] == ep and d["cf_id"] == cf_id
    reed = [i for i in d["items"] if i["clase"] == "reedicion"]
    regen = [i for i in d["items"] if i["clase"] == "regeneracion"]
    assert [(i["variante"], i["variante_tipo"]) for i in reed] == [(1, "hook"), (2, "estructura"), (3, "hook")]
    assert all(i["cf_id"] == cf_id and i["paises"] == ["CO", "MX"] and i["estado"] == "produciendo_finales" for i in reed)
    assert len(regen) == 2 and all(i["estado"] == "produciendo_clon" for i in regen)
    sesiones = cf.cargar("acme")
    nuevos = [sesiones[i["cf_id"]] for i in regen]
    assert all(s["derivado_de"] == cf_id for s in nuevos)
    assert {s["modelo"] for s in nuevos} == {"kling_o3_pro", "seedance25"}   # distintos del original (wan3) y entre sí
    assert {s["enfoque"] for s in nuevos} == {"persona", "unboxing"}
    assert all(s["estado"] == "video_generando" for s in nuevos)              # marcado antes de encolar
    # 3 re-ediciones × 2 países como finales, 2 clones.
    finales = [e for e in ent["encolados"] if e["tipo"] == "final_producir"]
    clones = [e for e in ent["encolados"] if e["tipo"] == "flowplus_video"]
    assert len(finales) == 6 and len(clones) == 2
    assert all(e["max_intentos"] == 1 for e in ent["encolados"])
    assert {(e["payload"]["idioma"], e["payload"]["pais"]) for e in finales} == {("es", "CO"), ("es", "MX")}
    assert sorted((e["payload"]["opciones"]["variante"], e["payload"]["opciones"]["variante_tipo"]) for e in finales
                  if e["payload"]["pais"] == "CO") == [(1, "hook"), (2, "estructura"), (3, "hook")]
    assert all(e["job_id"].endswith(f"__v{e['payload']['opciones']['variante']}__final") for e in finales)
    assert {e["job_id"] for e in clones} == {f"acme__{i['cf_id']}__creative_flow" for i in regen}
    assert all(f["estado"] == "generando" for f in cf.finales("acme", cf_id) if f["variante"])
    assert {i["finales"][k] for i in reed for k in i["finales"]} == {
        f"{cf_id}__es_{p}__v{n}" for p in ("CO", "MX") for n in (1, 2, 3)}
    tipos_padre = [e["tipo"] for e in ex.eventos("acme", eid)]
    tipos_hijo = [e["tipo"] for e in ex.eventos("acme", hijo)]
    assert "derivacion" in tipos_padre and "derivacion" in tipos_hijo
    # Repetir avanzar no vuelve a encolar nada (todo está generando).
    n = len(ent["encolados"])
    dv.avanzar("acme", hijo)
    assert len(ent["encolados"]) == n and ent["llamadas"] == []


def test_variantes_siguen_la_numeracion_existente(ent):
    dv, ex, cf, eid, ep, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"], ent["cf_id"]
    cf.crear_final("acme", cf_id, "es", "MX", variante=2)
    ex.actualizar("acme", eid, reglas={"n_reediciones": 2, "n_regeneraciones": 0})
    hijo = dv.planificar("acme", eid, "derivar", {"ep_id": ep, "motivo": "x"})
    d = _derivacion(ex, hijo)
    assert [(i["clase"], i["variante"], i["variante_tipo"]) for i in d["items"]] == [
        ("reedicion", 3, "hook"), ("reedicion", 4, "estructura")]


def test_avanzar_regeneracion_y_cierre_lanza_y_pide_activar(ent):
    dv, ex, cf, eid, ep, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"], ent["cf_id"]
    ex.actualizar("acme", eid, reglas={"n_reediciones": 1, "n_regeneraciones": 1})
    hijo = dv.planificar("acme", eid, "derivar", {"ep_id": ep, "motivo": "ganadora"})
    d = _derivacion(ex, hijo)
    regen = [i for i in d["items"] if i["clase"] == "regeneracion"][0]
    nuevo = regen["cf_id"]
    # La sesión regenerada termina: sus finales normales (sin variante) se encolan por país.
    cf.actualizar("acme", nuevo, estado="video_listo", video_url="https://r2/nuevo.mp4")
    resumen = dv.avanzar("acme", hijo)
    assert resumen["estado"] == "produciendo"
    regen = [i for i in _derivacion(ex, hijo)["items"] if i["clase"] == "regeneracion"][0]
    assert regen["estado"] == "produciendo_finales"
    assert regen["finales"] == {"es_CO": f"{nuevo}__es_CO", "es_MX": f"{nuevo}__es_MX"}
    nuevas = [e for e in ent["encolados"] if e["tipo"] == "final_producir" and e["payload"]["cf_id"] == nuevo]
    assert len(nuevas) == 2 and all(e["payload"]["opciones"] == {"variante": None} for e in nuevas)
    assert all(f["estado"] == "generando" for f in cf.finales("acme", nuevo))
    # Nada listo todavía: no se agregan piezas ni se lanza.
    assert ex.obtener("acme", hijo)["piezas"] == [] and ent["llamadas"] == []
    # Todas las finales terminan → piezas nuevas, lanzar (hijo armando) y pedir activar.
    for i in _derivacion(ex, hijo)["items"]:
        for legado in i["finales"].values():
            cf.actualizar_final("acme", legado, estado="listo", url_video=f"https://r2/{legado}.mp4")
    resumen = dv.avanzar("acme", hijo)
    h = ex.obtener("acme", hijo)
    d = h["extra"]["derivaciones"][0]
    assert resumen["estado"] == "listo" and d["estado"] == "listo"
    assert all(i["estado"] == "listo" for i in d["items"])
    ep_ids = sorted(p["id"] for p in h["piezas"])
    assert len(ep_ids) == 4 and sorted(sum((i["ep_ids"] for i in d["items"]), [])) == ep_ids
    assert {(p["pais"], p["tipo"]) for p in h["piezas"]} == {("CO", "final"), ("MX", "final")}
    assert ent["llamadas"] == [("lanzar", hijo), ("activar", hijo, ep_ids, resumen["motivo"])]
    assert "derivación" in resumen["motivo"].lower() or "derivacion" in resumen["motivo"].lower()
    # Idempotente: otra pasada no relanza ni vuelve a pedir nada.
    dv.avanzar("acme", hijo)
    assert len(ent["llamadas"]) == 2
    assert any(e["tipo"] == "derivacion" and "lista" in e["mensaje"] for e in ex.eventos("acme", hijo))


@pytest.mark.parametrize("escalon,esperado", [
    (0, ("reedicion", "hook")), (1, ("reedicion", "estructura")), (2, ("regeneracion", None))])
def test_planificar_rescatar_por_escalon(ent, escalon, esperado):
    dv, ex, cf, eid, ep, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"], ent["cf_id"]
    ex.actualizar_pieza("acme", ep, escalon_rescate=escalon)
    assert dv.planificar("acme", eid, "rescatar", {"ep_id": ep, "motivo": "perdedora"}) == eid
    pz = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert pz["escalon_rescate"] == escalon + 1
    d = _derivacion(ex, eid)
    assert d["tipo"] == "rescatar" and d["origen_ep_id"] == ep and len(d["items"]) == 1
    item = d["items"][0]
    assert (item["clase"], item["variante_tipo"]) == esperado and item["paises"] == ["CO"]
    if item["clase"] == "reedicion":
        assert item["variante"] == 1 and item["cf_id"] == cf_id
        assert [e["tipo"] for e in ent["encolados"]] == ["final_producir"]
    else:
        assert item["cf_id"] != cf_id and cf.cargar("acme")[item["cf_id"]]["derivado_de"] == cf_id
        assert [e["tipo"] for e in ent["encolados"]] == ["flowplus_video"]
    assert any(e["tipo"] == "derivacion" and e["ep_id"] == ep for e in ex.eventos("acme", eid))


def test_rescatar_sin_escalones_falla(ent):
    dv, ex, eid, ep = ent["dv"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar_pieza("acme", ep, escalon_rescate=3)
    with pytest.raises(ValueError, match="escal"):
        dv.planificar("acme", eid, "rescatar", {"ep_id": ep})
    assert ent["encolados"] == []


def test_rescatar_cierra_con_piezas_nuevas_en_experimento_corriendo(ent):
    dv, ex, cf, eid, ep = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"]
    dv.planificar("acme", eid, "rescatar", {"ep_id": ep, "motivo": "perdedora"})
    legado = _derivacion(ex, eid)["items"][0]["finales"]["es_CO"]
    cf.actualizar_final("acme", legado, estado="degradada", url_video="https://r2/v1.mp4")
    resumen = dv.avanzar("acme", eid)
    nuevas = [p["id"] for p in ex.obtener("acme", eid)["piezas"] if p["id"] != ep]
    assert resumen["estado"] == "listo" and len(nuevas) == 1
    assert ent["llamadas"] == [("piezas_nuevas", eid), ("activar", eid, nuevas, resumen["motivo"])]


def test_rescatar_de_clon_usa_idioma_del_pais(ent):
    dv, ex, cf, eid = ent["dv"], ent["ex"], ent["cf"], ent["eid"]
    cf_clon = _sesion_con_video(cf)
    ex.actualizar("acme", eid, paises=PAISES + [{"pais": "US", "idioma": "en", "presupuesto_dia": 5.0}])
    ep_clon = ex.agregar_pieza("acme", eid, cf.pieza_id_por_legado("acme", cf_clon), "US")
    dv.planificar("acme", eid, "rescatar", {"ep_id": ep_clon})
    item = _derivacion(ex, eid)["items"][0]
    assert item["cf_id"] == cf_clon and item["finales"] == {"en_US": f"{cf_clon}__en_US__v1"}
    assert ent["encolados"][0]["payload"]["idioma"] == "en"


def test_final_en_error_marca_item_y_derivacion_sin_bloquear_a_las_otras(ent):
    dv, ex, cf, eid, ep = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, reglas={"n_reediciones": 2, "n_regeneraciones": 0})
    hijo = dv.planificar("acme", eid, "derivar", {"ep_id": ep, "motivo": "x"})
    i1, i2 = _derivacion(ex, hijo)["items"]
    cf.actualizar_final("acme", i1["finales"]["es_CO"], estado="error", error="sin voz")
    resumen = dv.avanzar("acme", hijo)
    d = _derivacion(ex, hijo)
    assert d["items"][0]["estado"] == "error" and d["items"][1]["estado"] == "produciendo_finales"
    assert resumen["estado"] == "produciendo" and ent["llamadas"] == []
    assert any(e["tipo"] == "error" for e in ex.eventos("acme", hijo))
    for legado in i2["finales"].values():
        cf.actualizar_final("acme", legado, estado="listo", url_video="https://r2/ok.mp4")
    resumen = dv.avanzar("acme", hijo)
    d = _derivacion(ex, hijo)
    # Sin pendientes y con un item en error: la derivación queda en error,
    # pero lo que sí se produjo entra al experimento.
    assert d["estado"] == "error" and resumen["estado"] == "error"
    assert len(ex.obtener("acme", hijo)["piezas"]) == 2
    assert [l[0] for l in ent["llamadas"]] == ["lanzar", "activar"]
    dv.avanzar("acme", hijo)
    assert len(ent["llamadas"]) == 2


def test_clon_en_error_marca_item(ent):
    dv, ex, cf, eid, ep = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, reglas={"n_reediciones": 0, "n_regeneraciones": 1})
    hijo = dv.planificar("acme", eid, "derivar", {"ep_id": ep})
    nuevo = _derivacion(ex, hijo)["items"][0]["cf_id"]
    cf.actualizar("acme", nuevo, estado="error", error="el modelo falló")
    resumen = dv.avanzar("acme", hijo)
    d = _derivacion(ex, hijo)
    assert d["items"][0]["estado"] == "error" and d["estado"] == "error" and resumen["estado"] == "error"
    assert ent["llamadas"] == []


def test_avanzar_no_encola_si_el_trabajo_sigue_vivo(ent, monkeypatch):
    import trabajos
    dv, ex, cf, eid, ep = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, reglas={"n_reediciones": 0, "n_regeneraciones": 1})
    hijo = dv.planificar("acme", eid, "derivar", {"ep_id": ep})
    nuevo = _derivacion(ex, hijo)["items"][0]["cf_id"]
    # El worker se reinició: la sesión volvió a prompt_listo pero la tarea sigue viva en la cola.
    cf.actualizar("acme", nuevo, estado="prompt_listo")
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: True)
    n = len(ent["encolados"])
    dv.avanzar("acme", hijo)
    assert len(ent["encolados"]) == n


def test_exp_avanzar_todos_solo_toca_derivaciones_produciendo(base_temporal, monkeypatch):
    import ads
    import derivaciones as dv
    import experimentos as ex
    import tareas
    tareas.cargar_todas()
    e1 = ex.crear("acme", "A", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e2 = ex.crear("acme", "B", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e3 = ex.crear("otro", "C", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e4 = ex.crear("otro", "D", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ads.crear("acme", "creative_flow", "cf_9", "https://r2/v.mp4", "video", "suelto")   # legado: no entra
    ex.actualizar("acme", e1, extra={"derivaciones": [{"id": "d1", "estado": "listo"}, {"id": "d2", "estado": "produciendo"}]})
    ex.actualizar("acme", e2, extra={"derivaciones": [{"id": "d1", "estado": "listo"}]})
    ex.actualizar("otro", e3, extra={"derivaciones": [{"id": "d1", "estado": "produciendo"}]})
    ex.actualizar("otro", e4, extra={})
    tocados = []
    monkeypatch.setattr(dv, "avanzar", lambda c, e: tocados.append((c, e)) or {"estado": "produciendo"})
    msg = tareas.REGISTRO["exp_avanzar_todos"]({"payload": {}})
    assert sorted(tocados) == sorted([("acme", e1), ("otro", e3)]) and "2" in msg


def test_exp_avanzar_todos_no_se_cae_por_un_experimento(base_temporal, monkeypatch):
    import derivaciones as dv
    import experimentos as ex
    import tareas
    tareas.cargar_todas()
    e1 = ex.crear("acme", "A", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e2 = ex.crear("acme", "B", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    for e in (e1, e2):
        ex.actualizar("acme", e, extra={"derivaciones": [{"id": "d1", "estado": "produciendo"}]})
    tocados = []

    def _avanzar(c, e):
        tocados.append(e)
        if e == e1:
            raise RuntimeError("meta caída")
        return {"estado": "produciendo"}
    monkeypatch.setattr(dv, "avanzar", _avanzar)
    tareas.REGISTRO["exp_avanzar_todos"]({"payload": {}})
    assert sorted(tocados) == sorted([e1, e2])
    assert any(e["tipo"] == "error" and "meta caída" in e["mensaje"] for e in ex.eventos("acme", e1))


def test_periodica_avanzar_registrada():
    import worker
    assert ("exp_avanzar_todos", 600) in worker.PERIODICAS
    assert ("exp_refrescar_todos", 7200) in worker.PERIODICAS


# ------------------------------------------------ fix round 1 (I-1..I-3) ---

def test_otro_rota_sobre_los_distintos_del_actual(ent):
    dv = ent["dv"]
    assert dv._otro(("a", "b", "c"), "a", 0) == "b"
    assert dv._otro(("a", "b", "c"), "a", 1) == "c"
    assert dv._otro(("a", "b", "c"), "a", 2) == "b"      # cíclico, nunca "a"
    assert dv._otro(("a", "b", "c"), "zzz", 0) == "a"    # actual fuera de la lista
    assert dv._otro(("a",), "a", 5) == "a"               # único: no hay otro


def test_rescate_escalon_3_regenera_con_otro_modelo_y_otro_enfoque(ent):
    """I-1: el escalón 3 (regeneración) debe cambiar modelo y enfoque, no
    repetir los del original (antes `_otro(..., 3)` con 3 opciones devolvía
    el mismo)."""
    dv, ex, cf, eid, ep, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"], ent["cf_id"]
    ex.actualizar_pieza("acme", ep, escalon_rescate=2)
    dv.planificar("acme", eid, "rescatar", {"ep_id": ep})
    item = _derivacion(ex, eid)["items"][0]
    origen, nueva = cf.cargar("acme")[cf_id], cf.cargar("acme")[item["cf_id"]]
    assert item["clase"] == "regeneracion"
    assert nueva["modelo"] != origen["modelo"] and nueva["modelo"] in dv.flowplus_modelos.VIDEO
    assert nueva["enfoque"] != (origen["enfoque"] or dv.ENFOQUES[0]) and nueva["enfoque"] in dv.ENFOQUES


def test_derivar_tres_regeneraciones_ninguna_repite_el_original(ent):
    dv, ex, cf, eid, ep, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"], ent["cf_id"]
    ex.actualizar("acme", eid, reglas={"n_reediciones": 0, "n_regeneraciones": 3})
    hijo = dv.planificar("acme", eid, "derivar", {"ep_id": ep})
    sesiones = cf.cargar("acme")
    nuevas = [sesiones[i["cf_id"]] for i in _derivacion(ex, hijo)["items"]]
    assert len(nuevas) == 3
    assert all(s["modelo"] != "wan3" and s["enfoque"] != "producto" for s in nuevas)
    assert len({s["modelo"] for s in nuevas[:2]}) == 2 and len({s["enfoque"] for s in nuevas[:2]}) == 2


def test_derivar_sin_reediciones_ni_regeneraciones_falla_sin_crear_hijo(ent):
    dv, ex, eid, ep = ent["dv"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, reglas={"n_reediciones": 0, "n_regeneraciones": 0})
    with pytest.raises(ValueError, match="nada que derivar"):
        dv.planificar("acme", eid, "derivar", {"ep_id": ep})
    assert ex.obtener("acme", eid)["hijos"] == [] and ent["encolados"] == []


def test_encolar_final_no_reproduce_una_final_que_ya_existe(ent):
    """I-2: si el estado en memoria se perdió antes de guardarse, la pasada
    siguiente encuentra la final ya creada: si terminó (`listo`/`degradada`)
    se registra sin volver a producirla; si está `generando` se espera. Solo
    se crea y encola cuando no existe o falló."""
    dv, ex, cf, eid, ep, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"], ent["cf_id"]
    dv.planificar("acme", eid, "rescatar", {"ep_id": ep})
    d = _derivacion(ex, eid)
    legado = d["items"][0]["finales"]["es_CO"]
    assert legado == f"{cf_id}__es_CO__v1" and len(ent["encolados"]) == 1
    cf.actualizar_final("acme", legado, estado="listo", url_video="https://r2/v1.mp4", costo_usd=0.7)
    # Se pierde el estado en memoria: la derivación vuelve a no saber de esa final.
    d["items"][0]["finales"] = {}
    dv._guardar("acme", eid, d)
    resumen = dv.avanzar("acme", eid)
    item = _derivacion(ex, eid)["items"][0]
    f = cf.final_por_legado("acme", legado)
    assert item["finales"] == {"es_CO": legado} and len(ent["encolados"]) == 1      # ni re-crea ni re-encola
    assert f["estado"] == "listo" and f["costo_usd"] == 0.7                            # no se reinició
    # La pasada siguiente la ve lista y cierra.
    resumen = dv.avanzar("acme", eid)
    assert resumen["estado"] == "listo" and len(ent["encolados"]) == 1
    # `generando` sin tarea viva: también se espera, sin reiniciar.
    cf.crear_final("acme", cf_id, "es", "MX", variante=7)
    assert dv._encolar_final("acme", cf_id, "es", "MX", {"variante": 7, "variante_tipo": "hook"}) == f"{cf_id}__es_MX__v7"
    assert len(ent["encolados"]) == 1
    # `error`: sí se reproduce.
    cf.actualizar_final("acme", f"{cf_id}__es_MX__v7", estado="error", error="x")
    dv._encolar_final("acme", cf_id, "es", "MX", {"variante": 7, "variante_tipo": "hook"})
    assert len(ent["encolados"]) == 2 and cf.final_por_legado("acme", f"{cf_id}__es_MX__v7")["estado"] == "generando"


def test_actualizar_extra_no_pierde_escrituras_intercaladas(ent):
    """I-3: dos escritores con fotos viejas de `extra`: cada `fn` recibe el
    `extra` actual de la base (SELECT+UPDATE en la misma transacción), así
    que las dos claves sobreviven aunque el segundo llamador haya leído antes
    de que el primero escribiera."""
    ex, eid = ent["ex"], ent["eid"]
    foto_vieja = dict(ex.obtener("acme", eid)["extra"])       # ambos leyeron acá
    ex.actualizar_extra("acme", eid, lambda e: {**e, "derivaciones": [{"id": "d1"}]})

    def _activar(e):
        assert e.get("derivaciones") == [{"id": "d1"}]        # ve lo del primero, no la foto vieja
        return {**e, "activado_en": "2026-09-15T10:00:00"}
    ex.actualizar_extra("acme", eid, _activar, estado="corriendo")
    assert "derivaciones" not in foto_vieja
    e = ex.obtener("acme", eid)
    assert e["extra"] == {"derivaciones": [{"id": "d1"}], "activado_en": "2026-09-15T10:00:00"}
    assert e["estado"] == "corriendo"
    with pytest.raises(ValueError):
        ex.actualizar_extra("acme", eid, lambda e: e, extra={})
    assert ex.actualizar_extra("acme", 999999, lambda e: e) is None


def test_guardar_derivacion_conserva_activado_en(ent):
    dv, ex, eid, ep = ent["dv"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar_extra("acme", eid, lambda e: {**e, "activado_en": "2026-09-15T09:00:00"})
    dv.planificar("acme", eid, "rescatar", {"ep_id": ep})
    e = ex.obtener("acme", eid)["extra"]
    assert e["activado_en"] == "2026-09-15T09:00:00" and len(e["derivaciones"]) == 1


def test_lanzador_activar_pieza_conserva_derivaciones_escritas_entre_medio(ent, monkeypatch):
    """I-3 del lado del dashboard: `activar_pieza` leyó el experimento, habló
    con Meta y recién ahí escribe `activado_en`; si el worker guardó
    `derivaciones` en el intervalo, no deben perderse."""
    import lanzador
    dv, ex, eid, ep = ent["dv"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, estado="pausado")
    ex.actualizar_pieza("acme", ep, estado="pausado")

    def _meta(cliente, fn):
        dv.planificar("acme", eid, "rescatar", {"ep_id": ep})   # el worker escribe mientras "Meta" responde
        fn({})
    monkeypatch.setattr(lanzador, "_con_credenciales", _meta)
    monkeypatch.setattr(lanzador.meta_campaign, "actualizar_estado", lambda *a, **k: None)
    monkeypatch.setattr(lanzador.meta_adset, "actualizar_estado", lambda *a, **k: None)
    monkeypatch.setattr(lanzador.meta_ad, "actualizar_estado", lambda *a, **k: None)
    lanzador.activar_pieza("acme", ep)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo" and e["extra"]["activado_en"]
    assert len(e["extra"]["derivaciones"]) == 1


def test_rescate_fallido_deja_propuesta_y_evento_sobre_la_pieza(ent):
    """M-2: la pieza origen quedó pausada; si el rescate falla, evento `error`
    con `ep_id` y una propuesta `rescatar` para que la persona decida."""
    import propuestas
    dv, ex, cf, eid, ep = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"]
    dv.planificar("acme", eid, "rescatar", {"ep_id": ep, "motivo": "perdedora"})
    legado = _derivacion(ex, eid)["items"][0]["finales"]["es_CO"]
    cf.actualizar_final("acme", legado, estado="error", error="sin voz")
    assert dv.avanzar("acme", eid)["estado"] == "error"
    errores = [e for e in ex.eventos("acme", eid) if e["tipo"] == "error"]
    assert errores and all(e["ep_id"] == ep for e in errores)
    assert any("sin voz" in e["mensaje"] for e in errores)
    pend = propuestas.pendientes("acme", eid)
    assert len(pend) == 1 and pend[0]["accion"] == "rescatar" and pend[0]["payload"]["ep_id"] == ep
    assert "reintentar rescate" in pend[0]["payload"]["motivo"]
    dv.avanzar("acme", eid)
    assert len(propuestas.pendientes("acme", eid)) == 1


def test_regeneracion_de_sesion_de_imagen_encola_flowplus_imagen(ent):
    dv, ex, cf, eid, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["cf_id"]
    cf_img = _sesion_con_video(cf)
    cf.actualizar("acme", cf_img, tipo="imagen")
    ep_img = ex.agregar_pieza("acme", eid, cf.pieza_id_por_legado("acme", cf_img), "MX")
    ex.actualizar_pieza("acme", ep_img, escalon_rescate=2)
    dv.planificar("acme", eid, "rescatar", {"ep_id": ep_img})
    assert [e["tipo"] for e in ent["encolados"]] == ["flowplus_imagen"]

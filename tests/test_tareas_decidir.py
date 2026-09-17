"""exp_decidir (Bloque 4): veredictos por país, acciones vía acciones.pedir,
tope, periódica y paso a `decidido`."""
from datetime import datetime, timedelta

import pytest

from tests.test_experimentos_db import PAISES, _pieza

GANADOR = {"impresiones": 5000, "clics_enlace": 100, "ctr": 2.0, "cpc": 0.3, "thruplay_rate": 0.3, "gasto": 10.0}
PERDEDOR = {"impresiones": 5000, "clics_enlace": 5, "ctr": 0.2, "cpc": 3.0, "thruplay_rate": 0.05, "gasto": 10.0}


def _hace(horas):
    return (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")


@pytest.fixture()
def ent(base_temporal, monkeypatch):
    import experimentos as ex
    import tareas
    from tareas import experimentos as te
    tareas.cargar_todas()
    llamadas, avisos = [], []
    pedir_real = te.acciones.pedir

    def pedir(cliente, eid, accion, payload, motivo):
        llamadas.append((accion, payload))
        return ("propuesta" if accion in ("escalar", "derivar") else "ejecutada"), f"{accion} ok"

    monkeypatch.setattr(te.acciones, "pedir", pedir)
    monkeypatch.setattr(te.lanzador, "cambiar_estado", lambda c, e, s, pais=None: llamadas.append(("estado", e, s)))
    monkeypatch.setattr(te.notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: (avisos.append((tipo, asunto, cuerpo)), True)[1])
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", modo="semi")
    ex.actualizar("acme", eid, estado="corriendo", meta_campaign_id="c1")
    ex.actualizar_extra("acme", eid, lambda extra: {**extra, "activado_en": _hace(72)})

    def pieza(pais="CO", legado="cf_1__es_CO", horas=72, metricas=None):
        pid = _pieza(base_temporal, pais=pais, legado=legado)
        ep = ex.agregar_pieza("acme", eid, pid, pais)
        ex.actualizar_pieza("acme", ep, meta_ad_id=f"ad{ep}", estado="activo", extra={"activado_en": _hace(horas)})
        if metricas is not None:
            ex.snapshot(ep, metricas)
        return ep

    return {"ex": ex, "te": te, "eid": eid, "pieza": pieza, "llamadas": llamadas, "avisos": avisos, "pedir_real": pedir_real,
            "decidir": lambda: te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})}


def _pz(ent, ep):
    return next(p for p in ent["ex"].obtener("acme", ent["eid"])["piezas"] if p["id"] == ep)


def test_tope_alcanzado_pausa_y_no_evalua(ent):
    ex, eid = ent["ex"], ent["eid"]
    ep = ent["pieza"](metricas=GANADOR)
    ex.actualizar("acme", eid, gasto_acumulado=100.0)
    msg = ent["decidir"]()
    assert "tope" in msg.lower()
    assert ent["llamadas"] == [("estado", eid, "PAUSED")]
    assert _pz(ent, ep)["veredicto"] == "pendiente"
    assert any(e["tipo"] == "tope" for e in ex.eventos("acme", eid))
    assert ent["avisos"] and "Tope" in ent["avisos"][0][1]


def test_ganador_escala_deriva_y_avisa(ent):
    ex, eid = ent["ex"], ent["eid"]
    ep = ent["pieza"](metricas=GANADOR)
    msg = ent["decidir"]()
    pz = _pz(ent, ep)
    assert pz["veredicto"] == "ganador" and pz["veredicto_motivo"].startswith("Ganador")
    assert ent["llamadas"] == [("escalar", {"pais": "CO", "ep_id": ep}), ("derivar", {"ep_id": ep})]
    ev = [e for e in ex.eventos("acme", eid) if e["tipo"] == "veredicto"]
    assert len(ev) == 1 and ev[0]["ep_id"] == ep and ev[0]["datos"]["numeros"]["impresiones"] == 5000
    tipos = [a[0] for a in ent["avisos"]]
    assert tipos == ["ganador", "propuesta"]  # escalar/derivar quedaron como propuesta (modo semi): un solo correo
    assert "2 propuesta" in ent["avisos"][1][1]
    assert "1 ganador" in msg and "2 propuesta" in msg


def test_perdedora_pide_pausar_y_luego_rescate(ent):
    """I-2 (review final, spec §7): la pausa del perdedor es una acción
    aparte y sin gasto que se pide ANTES del rescate — así en semi el
    anuncio deja de gastar aunque el rescate espere aprobación."""
    ep = ent["pieza"](metricas=PERDEDOR)
    ent["decidir"]()
    assert _pz(ent, ep)["veredicto"] == "perdedor"
    assert ent["llamadas"] == [("pausar", {"ep_id": ep}), ("rescatar", {"ep_id": ep})]
    assert [a[0] for a in ent["avisos"]] == []


def test_perdedora_en_escalon_3_archiva_con_cf_id(ent):
    ex = ent["ex"]
    ep = ent["pieza"](metricas=PERDEDOR)
    ex.actualizar_pieza("acme", ep, escalon_rescate=3)
    ent["decidir"]()
    assert [l[0] for l in ent["llamadas"]] == ["pausar", "archivar"]
    assert ent["llamadas"][1][1]["ep_id"] == ep and ent["llamadas"][1][1]["cf_id"] == "cf_1"
    assert ent["llamadas"][1][1]["motivo"]


def test_sin_evidencia_sigue_pendiente_y_no_pide_nada(ent):
    ep = ent["pieza"](horas=1, metricas={"impresiones": 10, "ctr": 2.0, "cpc": 0.3, "thruplay_rate": 0.3, "gasto": 1.0})
    msg = ent["decidir"]()
    assert _pz(ent, ep)["veredicto"] == "pendiente"
    assert ent["llamadas"] == [] and ent["avisos"] == []
    assert msg.startswith("0 veredicto")


def test_solo_evalua_piezas_activas_con_anuncio(ent):
    ex = ent["ex"]
    ep_pausada = ent["pieza"](metricas=GANADOR)
    ex.actualizar_pieza("acme", ep_pausada, estado="pausado")
    ep_sin_ad = ent["pieza"](legado="cf_2__es_CO", metricas=GANADOR)
    ex.actualizar_pieza("acme", ep_sin_ad, meta_ad_id=None)
    ent["decidir"]()
    assert _pz(ent, ep_pausada)["veredicto"] == "pendiente"
    assert _pz(ent, ep_sin_ad)["veredicto"] == "pendiente"
    assert ent["llamadas"] == []


def test_ranking_dos_piezas_ambas_ganan_con_tres_solo_la_mejor(ent):
    ex = ent["ex"]
    a = ent["pieza"](legado="cf_a__es_CO", metricas={**GANADOR, "cpc": 0.5})
    b = ent["pieza"](legado="cf_b__es_CO", metricas={**GANADOR, "cpc": 0.4})
    ent["decidir"]()
    assert _pz(ent, a)["veredicto"] == "ganador" and _pz(ent, b)["veredicto"] == "ganador"
    # Tercera pieza en el país: ahora solo el tercio superior (1 de 3) gana.
    # (La pasada anterior dejó el experimento `decidido`: se vuelve a abrir.)
    ex.actualizar("acme", ent["eid"], estado="corriendo")
    for ep in (a, b):
        ex.actualizar_pieza("acme", ep, veredicto="pendiente")
    c = ent["pieza"](legado="cf_c__es_CO", metricas={**GANADOR, "cpc": 0.2})
    ent["llamadas"].clear()
    ent["decidir"]()
    assert _pz(ent, c)["veredicto"] == "ganador"
    assert _pz(ent, a)["veredicto"] == "pendiente" and _pz(ent, b)["veredicto"] == "pendiente"
    assert [l[0] for l in ent["llamadas"]] == ["escalar", "derivar"] and ent["llamadas"][0][1]["ep_id"] == c


def test_ranking_por_roas_con_atribucion_y_compras(ent):
    ex, eid = ent["ex"], ent["eid"]
    ex.actualizar("acme", eid, atribucion="pixel", reglas={"roas_min": None, "cpa_max": None})
    a = ent["pieza"](legado="cf_a__es_CO", metricas={**GANADOR, "cpc": 0.2, "compras": 1, "roas": 1.0})
    b = ent["pieza"](legado="cf_b__es_CO", metricas={**GANADOR, "cpc": 0.9, "compras": 3, "roas": 4.0})
    c = ent["pieza"](legado="cf_c__es_CO", metricas={**GANADOR, "cpc": 0.5, "compras": 0, "roas": 0.0})
    ent["decidir"]()
    assert _pz(ent, b)["veredicto"] == "ganador"
    assert _pz(ent, a)["veredicto"] == "pendiente" and _pz(ent, c)["veredicto"] == "pendiente"


def test_horas_activo_desde_primer_snapshot_con_impresiones(ent):
    ex = ent["ex"]
    ep = ent["pieza"](metricas=None)
    ex.actualizar_pieza("acme", ep, extra={})  # sin activado_en
    with ex.db.conectar() as con:
        con.execute(ex.db.metrica_snapshot.insert().values(experimento_pieza_id=ep, tomado_en=_hace(80), extra={}, **GANADOR))
    ex.snapshot(ep, GANADOR)
    ent["decidir"]()
    assert _pz(ent, ep)["veredicto"] == "ganador"


def test_pasa_a_decidido_cuando_todo_tiene_veredicto(ent):
    ex, eid = ent["ex"], ent["eid"]
    a = ent["pieza"](metricas=GANADOR)
    b = ent["pieza"](pais="MX", legado="cf_b__es_MX", horas=1, metricas={"impresiones": 5})
    msg = ent["decidir"]()
    assert ex.obtener("acme", eid)["estado"] == "corriendo"  # b sigue pendiente
    ex.actualizar_pieza("acme", b, veredicto="perdedor")
    msg = ent["decidir"]()
    assert ex.obtener("acme", eid)["estado"] == "decidido" and "decidido" in msg
    assert any("decidido" in e["mensaje"].lower() for e in ex.eventos("acme", eid))
    # Ya decidido: otra pasada no hace nada.
    assert "no se decide" in ent["decidir"]()


def test_no_pasa_a_decidido_con_derivacion_produciendo(ent):
    ex, eid = ent["ex"], ent["eid"]
    ent["pieza"](metricas=GANADOR)
    ex.actualizar_extra("acme", eid, lambda extra: {**extra, "derivaciones": [{"estado": "produciendo"}]})
    ent["decidir"]()
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


def test_no_pasa_a_decidido_con_propuestas_pendientes(ent):
    """I-1 del review: en modo semi/manual, una propuesta (p.ej. el rescate
    de la perdedora) que todavía no se aprobó no puede dejar que el
    experimento pase a 'decidido' — si no, cuando se apruebe, lanzar la
    pieza rescatada chocaría con el guard de lanzador (solo pausado|corriendo,
    antes de este fix)."""
    ex, eid = ent["ex"], ent["eid"]
    import propuestas as pr
    ent["pieza"](metricas=GANADOR)  # única pieza con anuncio: queda con veredicto final
    pr.crear("acme", eid, "rescatar", {"ep_id": 999999}, "motivo de prueba, sin relación con esta pieza")
    ent["decidir"]()
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


def test_no_pasa_a_decidido_con_pieza_en_cola(ent):
    """I-1: una pieza agregada al experimento que todavía no tiene anuncio en
    Meta ('en_cola', la crea lanzador.lanzar_piezas_nuevas de forma asíncrona)
    no debe contar como 'ya decidido' solo porque no tiene meta_ad_id."""
    ex, eid = ent["ex"], ent["eid"]
    from tests.test_experimentos_db import _pieza as _crear_pieza
    ent["pieza"](metricas=GANADOR)
    pid_nueva = _crear_pieza(ex.db, legado="cf_2__es_CO")
    ex.agregar_pieza("acme", eid, pid_nueva, "CO")  # queda 'en_cola'
    ent["decidir"]()
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


def test_dos_ganadores_del_mismo_pais_escalan_una_sola_vez(ent):
    """I-2 del review: 'escalar' sube el presupuesto del país, no de la
    pieza — con dos ganadores del mismo país en una sola pasada, solo el
    primero debe pedir escalar; el segundo solo deriva."""
    ex, eid = ent["ex"], ent["eid"]
    a = ent["pieza"](legado="cf_a__es_CO", metricas={**GANADOR, "cpc": 0.5})
    b = ent["pieza"](legado="cf_b__es_CO", metricas={**GANADOR, "cpc": 0.4})
    ent["decidir"]()
    assert _pz(ent, a)["veredicto"] == "ganador" and _pz(ent, b)["veredicto"] == "ganador"
    escalar = [l for l in ent["llamadas"] if l[0] == "escalar"]
    derivar = [l for l in ent["llamadas"] if l[0] == "derivar"]
    assert len(escalar) == 1 and len(derivar) == 2
    assert any(e["tipo"] == "escalado" and "ya pedido en esta pasada" in e["mensaje"] for e in ex.eventos("acme", eid))


def test_error_en_una_accion_no_frena_las_demas(ent, monkeypatch):
    ex, eid = ent["ex"], ent["eid"]

    def pedir(cliente, e, accion, payload, motivo):
        if accion == "escalar":
            raise RuntimeError("Meta dijo no")
        ent["llamadas"].append((accion, payload))
        return "ejecutada", "ok"

    monkeypatch.setattr(ent["te"].acciones, "pedir", pedir)
    a = ent["pieza"](legado="cf_a__es_CO", metricas=GANADOR)
    b = ent["pieza"](legado="cf_b__es_CO", metricas=PERDEDOR)
    msg = ent["decidir"]()
    assert _pz(ent, a)["veredicto"] == "ganador" and _pz(ent, b)["veredicto"] == "perdedor"
    assert [l[0] for l in ent["llamadas"]] == ["derivar", "pausar", "rescatar"]
    assert "1 acción(es) con error" in msg


def test_accion_que_falla_queda_como_propuesta(ent, monkeypatch):
    """I-3 del review: el veredicto ya quedó persistido y la pieza no se
    vuelve a evaluar, así que una acción que falló al ejecutarse no puede
    perderse solo con el evento de error — tiene que quedar como propuesta
    para que el humano la reintente desde el panel."""
    import propuestas as pr
    ex, eid = ent["ex"], ent["eid"]

    def pedir(cliente, e, accion, payload, motivo):
        if accion == "escalar":
            raise RuntimeError("Meta dijo no")
        ent["llamadas"].append((accion, payload))
        return "ejecutada", "ok"

    monkeypatch.setattr(ent["te"].acciones, "pedir", pedir)
    ent["pieza"](metricas=GANADOR)
    ent["decidir"]()
    pendientes = pr.pendientes("acme", eid)
    assert [p["accion"] for p in pendientes] == ["escalar"]
    assert "falló al ejecutar" in pendientes[0]["payload"]["motivo"] and "Meta dijo no" in pendientes[0]["payload"]["motivo"]


def test_snapshots_cronologicos(base_temporal):
    import experimentos as ex
    pid = _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    assert ex.snapshots(ep) == []
    ex.snapshot(ep, {"impresiones": 1, "extra_x": "a"})
    ex.snapshot(ep, {"impresiones": 2})
    s = ex.snapshots(ep)
    assert [x["impresiones"] for x in s] == [1, 2] and s[0]["extra_x"] == "a" and all(x["tomado_en"] for x in s)
    assert s[-1] == ex.ultima_metrica(ep)


def test_exp_decidir_todos_encola_solo_corriendo(base_temporal, monkeypatch):
    import cola
    import experimentos as ex
    import tareas
    tareas.cargar_todas()
    e1 = ex.crear("acme", "A", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e2 = ex.crear("acme", "B", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e3 = ex.crear("otro", "C", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", e1, estado="corriendo")
    ex.actualizar("acme", e2, estado="decidido")
    ex.actualizar("otro", e3, estado="pausado")
    encolados = []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append((tipo, payload, kw)))
    tareas.REGISTRO["exp_decidir_todos"]({"payload": {}})
    assert [(t, p["experimento_id"]) for t, p, _ in encolados] == [("exp_decidir", e1)]
    assert encolados[0][2]["job_id"] == "acme__exp%s__decidir" % e1 and encolados[0][2]["max_intentos"] == 2
    # refrescar_todos sí incluye los decididos (sus anuncios siguen entregando).
    encolados.clear()
    tareas.REGISTRO["exp_refrescar_todos"]({"payload": {}})
    assert sorted(p["experimento_id"] for _, p, _ in encolados) == sorted([e1, e2])


def test_periodica_decidir_registrada():
    import worker
    # F4 (Bloque 5): los pedidos se sincronizan/atribuyen antes de refrescar
    # experimentos en el mismo tick, para que el snapshot por tienda no vea
    # ventas de hace un ciclo.
    assert worker.PERIODICAS == [("tienda_sync_pedidos_todas", 7200), ("exp_refrescar_todos", 7200),
                                 ("exp_decidir_todos", 3600), ("exp_avanzar_todos", 600),
                                 ("tienda_sync_productos_todas", 21600)]


def test_semi_perdedora_se_pausa_ya_y_el_rescate_queda_propuesto(ent, monkeypatch):
    """I-2 con `acciones.pedir` real (modo semi): pausar se ejecuta en Meta
    (sin gasto) y el rescate queda como propuesta pendiente; el experimento
    no pasa a decidido mientras la propuesta espere."""
    import acciones
    import propuestas as pr
    ex, eid = ent["ex"], ent["eid"]
    monkeypatch.setattr(ent["te"].acciones, "pedir", ent["pedir_real"])
    pausadas = []

    def _pausar(c, ep_):
        pausadas.append(ep_)
        ex.actualizar_pieza(c, ep_, estado="pausado")
    monkeypatch.setattr(acciones.lanzador, "pausar_pieza", _pausar)
    monkeypatch.setattr(acciones.derivaciones, "planificar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe planificar en semi")))
    ep = ent["pieza"](metricas=PERDEDOR)
    msg = ent["decidir"]()
    assert pausadas == [ep] and _pz(ent, ep)["estado"] == "pausado"
    pend = pr.pendientes("acme", eid)
    assert [(p["accion"], p["payload"]["ep_id"]) for p in pend] == [("rescatar", ep)]
    assert "1 propuesta" in msg and ex.obtener("acme", eid)["estado"] == "corriendo"
    tipos = [e["tipo"] for e in ex.eventos("acme", eid)]
    assert "accion" in tipos and "propuesta" in tipos
    assert [a[0] for a in ent["avisos"]] == ["propuesta"]


def test_pieza_rechazada_por_meta_no_se_evalua_y_avisa_una_vez(ent):
    """I-8: un anuncio DISAPPROVED/WITH_ISSUES no entrega; el decisor lo
    salta (no hay veredicto ni acción) y deja UN evento `rechazo_meta`
    (bandera `extra.rechazo_avisado`), no uno por pasada."""
    ex, eid = ent["ex"], ent["eid"]
    import lanzador
    assert lanzador.ESTADOS_META_RECHAZO == ("DISAPPROVED", "WITH_ISSUES")
    ep = ent["pieza"](metricas=PERDEDOR)
    ex.actualizar_pieza("acme", ep, estado_meta="DISAPPROVED")
    ok = ent["pieza"](legado="cf_2__es_CO", metricas=GANADOR)
    ex.actualizar_pieza("acme", ok, estado_meta="WITH_ISSUES")
    ent["decidir"]()
    ent["decidir"]()
    assert _pz(ent, ep)["veredicto"] == "pendiente" and _pz(ent, ok)["veredicto"] == "pendiente"
    assert ent["llamadas"] == []
    avisos = [e for e in ex.eventos("acme", eid) if e["tipo"] == "rechazo_meta"]
    assert sorted(e["ep_id"] for e in avisos) == sorted([ep, ok])
    assert _pz(ent, ep)["extra"]["rechazo_avisado"] is True
    # Corregido en Meta: vuelve a evaluarse.
    ex.actualizar_pieza("acme", ok, estado_meta="ACTIVE")
    ent["decidir"]()
    assert _pz(ent, ok)["veredicto"] == "ganador"


def test_pieza_pausada_a_mano_sin_veredicto_no_bloquea_decidido(ent):
    """Menor (review final): `decidido` = todas las piezas ACTIVAS tienen
    veredicto; una pausada a mano y sin veredicto no lo bloquea para siempre."""
    ex, eid = ent["ex"], ent["eid"]
    a = ent["pieza"](metricas=GANADOR)
    b = ent["pieza"](legado="cf_b__es_CO", metricas=None)
    ex.actualizar_pieza("acme", b, estado="pausado")
    ent["decidir"]()
    assert _pz(ent, a)["veredicto"] == "ganador" and _pz(ent, b)["veredicto"] == "pendiente"
    assert ex.obtener("acme", eid)["estado"] == "decidido"


def test_todas_pausadas_sin_veredicto_no_es_decidido(ent):
    ex, eid = ent["ex"], ent["eid"]
    b = ent["pieza"](metricas=None)
    ex.actualizar_pieza("acme", b, estado="pausado")
    ent["decidir"]()
    assert ex.obtener("acme", eid)["estado"] == "corriendo"


def test_dias_transcurridos_sin_activado_en_usa_el_primer_snapshot_con_impresiones(ent):
    """Menor (review final): experimentos activados antes de que existiera
    `extra.activado_en` cuentan los días desde el primer snapshot con
    impresiones (de cualquier pieza); si no, `inconcluso` nunca dispararía."""
    ex, eid = ent["ex"], ent["eid"]
    ex.actualizar("acme", eid, extra={})       # sin activado_en
    pocas = {"impresiones": 10, "ctr": 2.0, "cpc": 0.3, "thruplay_rate": 0.3, "gasto": 0.5}
    ep = ent["pieza"](horas=1, metricas=None)
    with ex.db.conectar() as con:
        con.execute(ex.db.metrica_snapshot.insert().values(experimento_pieza_id=ep, tomado_en=_hace(24 * 8), extra={}, **pocas))
    ex.snapshot(ep, pocas)
    ent["decidir"]()
    pz = _pz(ent, ep)
    assert pz["veredicto"] == "inconcluso" and ent["llamadas"] == [("pausar", {"ep_id": ep})]
    # Con `activado_en` reciente, la ventana de 7 días sigue abierta: pendiente.
    from tareas import experimentos as te
    from datetime import datetime
    assert te._dias_transcurridos({"extra": {"activado_en": _hace(2)}}, {}, datetime.now()) < 1
    assert te._dias_transcurridos({"extra": {}}, {ep: []}, datetime.now()) == 0.0

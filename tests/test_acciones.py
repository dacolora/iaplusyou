import pytest

from tests.test_experimentos_db import PAISES, _pieza


@pytest.fixture()
def ent(base_temporal, monkeypatch):
    import acciones
    import experimentos as ex
    llamadas = []
    monkeypatch.setattr(acciones.lanzador, "pausar_pieza", lambda c, ep: llamadas.append(("pausar", ep)))
    monkeypatch.setattr(acciones.lanzador, "activar_pieza", lambda c, ep: llamadas.append(("activar", ep)))
    monkeypatch.setattr(acciones.lanzador, "cambiar_estado", lambda c, e, s, pais=None: llamadas.append(("estado", e, s)))
    monkeypatch.setattr(acciones.lanzador, "escalar_pais", lambda c, e, p, pct, tope_dia=None: (llamadas.append(("escalar", p, pct, tope_dia)), 24.0)[1])
    monkeypatch.setattr(acciones.derivaciones, "planificar", lambda c, e, tipo, payload: (llamadas.append(("planificar", tipo, payload.get("ep_id"))), 99)[1])
    pid = _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", modo="semi")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id="ad1", estado="activo")
    ex.actualizar("acme", eid, estado="corriendo", meta_campaign_id="c1")
    return {"ac": acciones, "ex": ex, "eid": eid, "ep": ep, "pid": pid, "llamadas": llamadas}


def test_pedir_respeta_modo(ent):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    import propuestas as pr
    assert ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "perdedor")[0] == "ejecutada"
    assert ent["llamadas"][-1] == ("pausar", ep)
    assert ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")[0] == "propuesta"
    assert [p["accion"] for p in pr.pendientes("acme", eid)] == ["escalar"]
    ex.actualizar("acme", eid, modo="auto")
    assert ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")[0] == "ejecutada"
    assert ent["llamadas"][-1][0] == "escalar"
    tipos = [e["tipo"] for e in ex.eventos("acme", eid)]
    assert "accion" in tipos and "propuesta" in tipos


def test_pedir_con_tope_alcanzado_propone_aunque_sea_auto(ent):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, modo="auto", gasto_acumulado=100.0)
    estado, msg = ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")
    assert estado == "propuesta" and "tope" in msg.lower()
    assert ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "x")[0] == "ejecutada"   # pausar no gasta


def test_ejecutar_derivar_rescatar_archivar_idempotentes(ent, monkeypatch):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    import creative_flow as cf
    ac.ejecutar("acme", eid, "derivar", {"ep_id": ep})
    ac.ejecutar("acme", eid, "derivar", {"ep_id": ep})
    assert [l for l in ent["llamadas"] if l[0] == "planificar"] == [("planificar", "derivar", ep)]
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert [l for l in ent["llamadas"] if l == ("planificar", "rescatar", ep)] == [("planificar", "rescatar", ep)]
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["extra"]["derivado"] is True and p["extra"]["rescatado_en_escalon"] == 1
    archivados = []
    monkeypatch.setattr(cf, "archivar_concepto", lambda c, cf_id, motivo: archivados.append((cf_id, motivo)))
    ac.ejecutar("acme", eid, "archivar", {"ep_id": ep, "cf_id": "cf_1", "motivo": "perdió 3 escalones"})
    assert archivados == [("cf_1", "perdió 3 escalones")] and ("pausar", ep) in ent["llamadas"]


def test_ejecutar_activar(ent):
    """I-1 (review final): activar piezas NUNCA pasa por
    `cambiar_estado(ACTIVE)` del experimento entero, ni siquiera con el
    experimento `pausado` — eso reactivaría en Meta las perdedoras que el
    decisor pausó. `activar_pieza` ya reactiva campaña y conjunto."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, estado="pausado")
    ac.ejecutar("acme", eid, "activar", {"ep_ids": [ep]})
    assert ("activar", ep) in ent["llamadas"]
    assert not any(l[0] == "estado" for l in ent["llamadas"])


def test_ejecutar_activar_acepta_experimento_decidido(ent):
    """I-1 del review de decidir: un rescate aprobado después de que el
    experimento pasó a 'decidido' tiene que poder activarse en Meta — si no,
    la propuesta aprobada queda inejecutable."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, estado="decidido")
    ac.ejecutar("acme", eid, "activar", {"ep_ids": [ep]})
    assert ("activar", ep) in ent["llamadas"]
    assert not any(l[0] == "estado" for l in ent["llamadas"])  # no toca la campaña: no estaba 'pausado'


@pytest.mark.parametrize("estado", ["armando", "lanzando", "error"])
def test_ejecutar_activar_arroja_si_no_esta_en_meta(ent, estado):
    """M/brief: activar sobre un experimento que todavía no llegó a Meta
    (armando/lanzando/error) no es un no-op silencioso: lanza ValueError con
    el mensaje que la UI puede mostrar tal cual."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, estado=estado)
    with pytest.raises(ValueError, match="El experimento todavía no está en Meta."):
        ac.ejecutar("acme", eid, "activar", {"ep_ids": [ep]})
    assert not any(l[0] == "activar" for l in ent["llamadas"])


def test_rescatar_idempotente_aunque_planificar_avance_el_escalon(ent, monkeypatch):
    """I1: cada pieza engendra a lo sumo un rescate por escalón. planificar
    sube `escalon_rescate` de la pieza; la marca de idempotencia es ese mismo
    escalón, y una segunda llamada sobre él no vuelve a planificar ni a
    gastar (solo asegura la pausa)."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]

    def _planificar_y_subir_escalon(c, e, tipo, payload):
        ent["llamadas"].append(("planificar", tipo, payload.get("ep_id")))
        pz = [p for p in ex.piezas(c, e) if p["id"] == payload["ep_id"]][0]
        ex.actualizar_pieza(c, payload["ep_id"], escalon_rescate=pz["escalon_rescate"] + 1)
        return 99

    monkeypatch.setattr(ac.derivaciones, "planificar", _planificar_y_subir_escalon)
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["escalon_rescate"] == 1 and p["extra"]["rescatado_en_escalon"] == 1

    # Segunda llamada: el decisor vuelve a pedir el rescate sin que la pieza
    # haya avanzado más allá del escalón ya marcado -> no repite.
    msg = ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert "ya rescatada" in msg
    assert [l for l in ent["llamadas"] if l[0] == "planificar" and l[1] == "rescatar"] == \
        [("planificar", "rescatar", ep)]

    # Si la pieza avanza de escalón por otra vía, un nuevo rescate sí procede
    # y la marca sube con ella.
    ex.actualizar_pieza("acme", ep, escalon_rescate=2)
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert len([l for l in ent["llamadas"] if l[0] == "planificar" and l[1] == "rescatar"]) == 2
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["escalon_rescate"] == 3 and p["extra"]["rescatado_en_escalon"] == 3


def test_rescatar_marca_antes_de_pausar_y_no_replanifica_si_pausar_fallo(ent, monkeypatch):
    """Fix escalera (2): si planificar salió bien pero Meta falla al pausar,
    la marca ya quedó escrita; la excepción sube (la propuesta se reabre) y
    al reintentar NO se vuelve a planificar (no hay doble producción): solo
    se reintenta la pausa."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    intentos = []

    def _pausar(c, ep_):
        intentos.append(ep_)
        if len(intentos) == 1:
            raise RuntimeError("Meta caída")

    monkeypatch.setattr(ac.lanzador, "pausar_pieza", _pausar)
    with pytest.raises(RuntimeError, match="Meta caída"):
        ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["extra"]["rescatado_en_escalon"] == 1
    assert [l for l in ent["llamadas"] if l[0] == "planificar"] == [("planificar", "rescatar", ep)]

    msg = ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert "ya rescatada" in msg and "pausada" in msg
    assert intentos == [ep, ep]
    assert [l for l in ent["llamadas"] if l[0] == "planificar"] == [("planificar", "rescatar", ep)]


def test_archivar_recorre_la_cadena_de_sesiones_regeneradas(ent, monkeypatch):
    """Fix escalera (1): archivar el concepto de una pieza que salió de una
    regeneración archiva también la sesión original (y su cadena
    `derivado_de`), no solo la última."""
    ac, eid, ep = ent["ac"], ent["eid"], ent["ep"]
    import creative_flow as cf
    a = cf.crear("acme", [], ["p1"], [], "sandalia", 10, "", "A", referencias_urls=["https://r"])
    b = cf.duplicar("acme", a)
    c = cf.duplicar("acme", b)
    ac.ejecutar("acme", eid, "archivar", {"ep_id": ep, "cf_id": c, "motivo": "agotó la escalera"})
    assert all(cf.concepto_archivado("acme", x) for x in (a, b, c))
    assert ac._cadena_conceptos("acme", c) == [c, b, a]
    assert ("pausar", ep) in ent["llamadas"]
    # Un ciclo en los datos no cuelga: tope de 5 saltos.
    assert ac._cadena_conceptos("acme", "cf_no_existe") == ["cf_no_existe"]
    assert ac._cadena_conceptos("acme", None) == []


def test_rescatar_llama_planificar_antes_de_pausar(ent, monkeypatch):
    """I3: si planificar falla, la pieza no debe quedar pausada — pausar solo
    ocurre después de que el rescate exista."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]

    def _falla(c, e, tipo, payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(ac.derivaciones, "planificar", _falla)
    with pytest.raises(RuntimeError):
        ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert not any(l[0] == "pausar" for l in ent["llamadas"])


def test_marcar_pieza_no_pisa_extra_escrito_despues_del_read_inicial(ent):
    """I2: acciones.ejecutar lee `pz` al principio; si algo más escribe en
    `extra` de la misma pieza entre ese read y el marcado (p. ej.
    lanzador.activar_pieza guardando `activado_en`), marcar_pieza no debe
    perder ese dato."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    pz_vieja = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert pz_vieja["extra"] == {}
    # Algo más (fuera de este ejecutar) escribe en extra después del read.
    ex.actualizar_pieza("acme", ep, extra={"activado_en": "2026-09-15T00:00:00"})
    ex.marcar_pieza("acme", ep, derivado=True)
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["extra"] == {"activado_en": "2026-09-15T00:00:00", "derivado": True}


def test_pedir_registra_evento_error_y_relanza(ent, monkeypatch):
    """I3: pedir() no traga la excepción de ejecutar(); antes de relanzarla
    deja un evento tipo error, en español, con el token de Meta redactado."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]

    def _falla(c, ep_):
        raise RuntimeError("Meta dijo: access_token=SECRETO123 inválido")

    monkeypatch.setattr(ac.lanzador, "pausar_pieza", _falla)
    with pytest.raises(RuntimeError):
        ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "perdedor")
    eventos = ex.eventos("acme", eid)
    errores = [e for e in eventos if e["tipo"] == "error"]
    assert len(errores) == 1
    assert "access_token=***" in errores[0]["mensaje"]
    assert "SECRETO123" not in errores[0]["mensaje"]
    assert errores[0]["datos"]["accion"] == "pausar"


def test_pedir_derivar_en_profundidad_maxima_propone_aunque_sea_auto(ent):
    """I-9: a partir de `PROFUNDIDAD_MAXIMA` generaciones (extra.profundidad
    del experimento) un ganador ya no deriva solo ni en `auto`: queda como
    propuesta con motivo "profundidad máxima". Por debajo sigue igual."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    import propuestas as pr
    ex.actualizar("acme", eid, modo="auto")
    ex.actualizar_extra("acme", eid, lambda e: {**e, "profundidad": ac.PROFUNDIDAD_MAXIMA - 1})
    assert ac.pedir("acme", eid, "derivar", {"ep_id": ep}, "ganador")[0] == "ejecutada"
    assert ("planificar", "derivar", ep) in ent["llamadas"]
    ex.marcar_pieza("acme", ep, derivado=False)
    ex.actualizar_extra("acme", eid, lambda e: {**e, "profundidad": ac.PROFUNDIDAD_MAXIMA})
    estado, msg = ac.pedir("acme", eid, "derivar", {"ep_id": ep}, "ganador")
    assert estado == "propuesta" and "profundidad máxima" in msg
    pend = pr.pendientes("acme", eid)
    assert [p["accion"] for p in pend] == ["derivar"] and "profundidad máxima" in pend[0]["payload"]["motivo"]
    assert len([l for l in ent["llamadas"] if l[0] == "planificar"]) == 1
    # Las demás acciones no se ven afectadas por la profundidad.
    assert ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "x")[0] == "ejecutada"


def test_rescatar_tolera_la_marca_que_planificar_ya_dejo(ent, monkeypatch):
    """I-5: `derivaciones.planificar` marca `rescatado_en_escalon` por su
    cuenta (antes de encolar). `ejecutar("rescatar")` no debe bajarla ni
    volver a planificar cuando ya está puesta."""
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]

    def _planificar_marcando(c, e, tipo, payload):
        ent["llamadas"].append(("planificar", tipo, payload.get("ep_id")))
        ex.actualizar_pieza(c, payload["ep_id"], escalon_rescate=1)
        ex.marcar_pieza(c, payload["ep_id"], rescatado_en_escalon=1)
        return e

    monkeypatch.setattr(ac.derivaciones, "planificar", _planificar_marcando)
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["extra"]["rescatado_en_escalon"] == 1 and p["escalon_rescate"] == 1
    msg = ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert "ya rescatada" in msg
    assert [l for l in ent["llamadas"] if l[0] == "planificar"] == [("planificar", "rescatar", ep)]


# --- Bloque 7: publicar_organico ---------------------------------------------

@pytest.fixture()
def org(ent, monkeypatch):
    """Canales y redacción falsos: `disponibles` devuelve lo que el test ponga
    en `canales`; `redactar` no llama a Claude y anota qué plataformas le
    pidieron."""
    import acciones
    import organico
    canales = ["instagram", "facebook"]
    redactadas = []

    def redactar(cliente, pieza_id, plataformas):
        redactadas.append(list(plataformas))
        return {p: {"titulo": f"T {p}", "caption": f"Texto {p}\n\n#a #b #c", "extra": {"fallback": False}}
                for p in plataformas}

    monkeypatch.setattr(acciones.organico, "disponibles", lambda cliente: list(canales))
    monkeypatch.setattr(acciones.organico, "redactar", redactar)
    return {**ent, "organico": organico, "canales": canales, "redactadas": redactadas}


def _pieza_ep(ent):
    return [p for p in ent["ex"].piezas("acme", ent["eid"]) if p["id"] == ent["ep"]][0]


def test_ejecutar_publicar_organico_crea_publicaciones_y_encola(org):
    import cola
    ac, eid, ep, pid = org["ac"], org["eid"], org["ep"], org["pid"]
    msg = ac.ejecutar("acme", eid, "publicar_organico", {"ep_id": ep})
    assert "Instagram Reels" in msg and "Facebook" in msg
    pubs = org["organico"].listar("acme", pieza_id=pid)
    assert [(p["plataforma"], p["estado"], p["origen"], p["experimento_pieza_id"]) for p in pubs] == \
        [("instagram", "en_cola", "ganador", ep), ("facebook", "en_cola", "ganador", ep)]
    assert pubs[0]["caption"].startswith("Texto instagram") and pubs[0]["titulo"] == "T instagram"
    assert org["redactadas"] == [["instagram", "facebook"]]
    tarea = cola.consultar_por_job(f"acme__pieza{pid}__organico")
    assert tarea["tipo"] == "organico_publicar" and tarea["estado"] == "pendiente" and tarea["max_intentos"] == 1
    assert tarea["payload"] == {"cliente": "acme", "pub_ids": [p["id"] for p in pubs]}
    assert tarea["etapas"] == [["Descargando", 15], ["Publicando", 85]] and tarea["cliente"] == "acme"
    assert _pieza_ep(org)["extra"]["publicado_organico"] is True


def test_ejecutar_publicar_organico_si_encolar_falla_filas_quedan_en_error_y_no_marca_publicado(org, monkeypatch):
    """M-3: la carrera entre `trabajos.en_curso()` y `trabajos.encolar()`
    (alguien encoló la misma pieza justo en el medio) deja las filas recién
    creadas en `error` con mensaje en español, sin encolar tarea y sin
    marcar `extra.publicado_organico` (M-1: la bandera es solo para lo que
    de verdad quedó en cola)."""
    import cola
    ac, eid, ep, pid = org["ac"], org["eid"], org["ep"], org["pid"]
    monkeypatch.setattr(ac.trabajos, "encolar", lambda *a, **k: False)
    msg = ac.ejecutar("acme", eid, "publicar_organico", {"ep_id": ep})
    assert "Ya hay una publicación orgánica" in msg and "en curso" in msg and "reintentar" in msg
    pubs = org["organico"].listar("acme", pieza_id=pid)
    assert [(p["plataforma"], p["estado"]) for p in pubs] == [("instagram", "error"), ("facebook", "error")]
    assert all("Ya había una publicación de esta pieza en curso; reintenta cuando termine." == p["error"]
               for p in pubs)
    assert cola.consultar_por_job(f"acme__pieza{pid}__organico") is None
    assert "publicado_organico" not in _pieza_ep(org)["extra"]


def test_ejecutar_publicar_organico_creacion_parcial_deja_lo_creado_en_error(org, monkeypatch):
    """Minor #5: si `organico.crear` falla en la 2.ª plataforma con algo que
    no sea «ya está publicada», la 1.ª no queda `en_cola` sin tarea
    (bloquearía la plataforma por unicidad): pasa a `error` y la excepción sube."""
    import cola
    ac, eid, ep, pid = org["ac"], org["eid"], org["ep"], org["pid"]
    real = org["organico"].crear

    def crear_fragil(cliente, pieza_id, plataforma, *a, **kw):
        if plataforma == "facebook":
            raise ValueError("El texto de la publicación no puede estar vacío.")
        return real(cliente, pieza_id, plataforma, *a, **kw)
    monkeypatch.setattr(ac.organico, "crear", crear_fragil)
    with pytest.raises(ValueError, match="no puede estar vacío"):
        ac.ejecutar("acme", eid, "publicar_organico", {"ep_id": ep})
    pubs = org["organico"].listar("acme", pieza_id=pid)
    assert [(p["plataforma"], p["estado"]) for p in pubs] == [("instagram", "error")]
    assert "No se creó la publicación en Facebook (Página)" in pubs[0]["error"]
    assert cola.consultar_por_job(f"acme__pieza{pid}__organico") is None
    assert "publicado_organico" not in _pieza_ep(org)["extra"]


def test_ejecutar_publicar_organico_respeta_captions_y_plataformas_del_payload(org):
    """Lo que la persona editó en la propuesta se publica (normalizado por
    organico.ajustar: hashtags aparte, «Link en bio.» en IG porque el
    experimento tiene destino_url); redactar solo se llama para las
    plataformas sin texto. Una plataforma pedida sin canal conectado se
    avisa y no se crea."""
    ac, eid, ep, pid = org["ac"], org["eid"], org["ep"], org["pid"]
    msg = ac.ejecutar("acme", eid, "publicar_organico", {
        "ep_id": ep, "plataformas": ["facebook", "instagram", "tiktok"],
        "captions": {"instagram": {"titulo": "Mío", "caption": "Mi texto editado #x #y #z"}}})
    pubs = {p["plataforma"]: p for p in org["organico"].listar("acme", pieza_id=pid)}
    assert set(pubs) == {"instagram", "facebook"}
    assert pubs["instagram"]["caption"] == "Mi texto editado\n\nLink en bio.\n\n#x #y #z"
    assert pubs["instagram"]["titulo"] == "Mío"
    assert org["redactadas"] == [["facebook"]]
    assert "Sin canal conectado: TikTok" in msg


def test_ejecutar_publicar_organico_normaliza_el_caption_editado(org):
    """Important #1: un caption editado a mano de 3 000 chars con URL en
    Instagram se guarda recortado y sin enlace — no se manda crudo a Graph."""
    import organico
    ac, eid, ep, pid = org["ac"], org["eid"], org["ep"], org["pid"]
    largo = ("palabra " * 375).strip() + " https://tienda.com/p " + ("otra " * 220).strip() + " #a #b #c"
    assert len(largo) > 2900
    ac.ejecutar("acme", eid, "publicar_organico", {
        "ep_id": ep, "plataformas": ["instagram"], "captions": {"instagram": {"titulo": "T", "caption": largo}}})
    ig = org["organico"].listar("acme", pieza_id=pid)[0]
    assert ig["estado"] == "en_cola" and len(ig["caption"]) <= organico.PLATAFORMAS["instagram"]["max_caption"]
    assert "https://" not in ig["caption"] and "Link en bio." in ig["caption"] and ig["caption"].endswith("#a #b #c")
    assert org["redactadas"] == []


def test_ejecutar_publicar_organico_salta_vivas_y_no_encola_dos_veces(org):
    import cola
    ac, eid, ep, pid, organico = org["ac"], org["eid"], org["ep"], org["pid"], org["organico"]
    ya = organico.crear("acme", pid, "instagram", "ya publicada #a #b #c", origen="manual")
    organico.actualizar("acme", ya, estado="publicada", url="https://www.instagram.com/p/abc")
    msg = ac.ejecutar("acme", eid, "publicar_organico", {"ep_id": ep})
    assert "Ya estaba publicada (o en cola) en Instagram Reels" in msg and "Facebook" in msg
    pubs = organico.listar("acme", pieza_id=pid)
    assert [(p["plataforma"], p["estado"]) for p in pubs] == [("instagram", "publicada"), ("facebook", "en_cola")]
    assert org["redactadas"] == [["facebook"]]
    tarea = cola.consultar_por_job(f"acme__pieza{pid}__organico")
    assert tarea["payload"]["pub_ids"] == [pubs[1]["id"]]
    # Segunda vez con la tarea viva: no crea nada ni encola otra.
    msg2 = ac.ejecutar("acme", eid, "publicar_organico", {"ep_id": ep})
    assert "en curso" in msg2
    assert len(organico.listar("acme", pieza_id=pid)) == 2 and len(org["redactadas"]) == 1
    # Con la tarea terminada y todo vivo: nada nuevo, sin error.
    cola.terminar(tarea["id"], "ok")
    msg3 = ac.ejecutar("acme", eid, "publicar_organico", {"ep_id": ep})
    assert "no tiene nada nuevo que publicar" in msg3
    assert len(organico.listar("acme", pieza_id=pid)) == 2


def test_ejecutar_publicar_organico_sin_canales_no_es_error(org):
    import cola
    ac, eid, ep, pid = org["ac"], org["eid"], org["ep"], org["pid"]
    org["canales"].clear()
    msg = ac.ejecutar("acme", eid, "publicar_organico", {"ep_id": ep})
    assert msg.startswith("No hay canales orgánicos disponibles")
    assert org["organico"].listar("acme", pieza_id=pid) == [] and org["redactadas"] == []
    assert cola.consultar_por_job(f"acme__pieza{pid}__organico") is None
    assert "publicado_organico" not in _pieza_ep(org)["extra"]


def test_pedir_publicar_organico_en_semi_propone_con_textos_y_en_auto_publica(org):
    import cola
    import propuestas as pr
    ac, ex, eid, ep, pid = org["ac"], org["ex"], org["eid"], org["ep"], org["pid"]
    estado, msg = ac.pedir("acme", eid, "publicar_organico", {"ep_id": ep, "plataformas": ["instagram", "facebook"]},
                           "ganador")
    assert estado == "propuesta" and "publicar_organico" in msg
    pend = pr.pendientes("acme", eid)
    assert len(pend) == 1 and pend[0]["accion"] == "publicar_organico"
    payload = pend[0]["payload"]
    assert payload["ep_id"] == ep and payload["plataformas"] == ["instagram", "facebook"]
    assert payload["captions"]["instagram"]["caption"].startswith("Texto instagram")
    assert payload["captions"]["facebook"]["titulo"] == "T facebook"
    assert org["organico"].listar("acme", pieza_id=pid) == []          # nada publicado sin aprobar
    assert cola.consultar_por_job(f"acme__pieza{pid}__organico") is None
    # Misma propuesta otra vez: no duplica y (M-2) no vuelve a redactar —
    # sería una llamada a Claude cuyo texto propuestas.crear descartaría igual.
    ac.pedir("acme", eid, "publicar_organico", {"ep_id": ep, "plataformas": ["instagram", "facebook"]}, "ganador")
    assert len(pr.pendientes("acme", eid)) == 1
    assert org["redactadas"] == [["instagram", "facebook"]]
    # Manual también propone; auto ejecuta.
    ex.actualizar("acme", eid, modo="manual")
    assert ac.pedir("acme", eid, "publicar_organico", {"ep_id": ep}, "ganador")[0] == "propuesta"
    assert org["redactadas"] == [["instagram", "facebook"]]   # sigue sin redactar de nuevo
    ex.actualizar("acme", eid, modo="auto")
    estado, msg = ac.pedir("acme", eid, "publicar_organico", {"ep_id": ep}, "ganador")
    assert estado == "ejecutada" and "en cola" in msg
    assert [p["plataforma"] for p in org["organico"].listar("acme", pieza_id=pid)] == ["instagram", "facebook"]
    assert cola.consultar_por_job(f"acme__pieza{pid}__organico")["max_intentos"] == 1
    tipos = [e["tipo"] for e in ex.eventos("acme", eid)]
    assert "propuesta" in tipos and "accion" in tipos


def test_pedir_publicar_organico_propone_aunque_redactar_falle(org, monkeypatch):
    """Sin texto previo la propuesta igual existe (con `captions_error`); al
    aprobarla, ejecutar vuelve a redactar."""
    import propuestas as pr
    ac, eid, ep = org["ac"], org["eid"], org["ep"]
    monkeypatch.setattr(ac.organico, "redactar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin base")))
    estado, _ = ac.pedir("acme", eid, "publicar_organico", {"ep_id": ep}, "ganador")
    assert estado == "propuesta"
    payload = pr.pendientes("acme", eid)[0]["payload"]
    assert "captions" not in payload and payload["captions_error"] == "sin base"
    assert payload["plataformas"] == ["instagram", "facebook"]


# ---- Task 3: precio a la vista en las propuestas de derivar / rescatar ----

def test_pedir_derivar_y_rescatar_llevan_precio_estimado(ent):
    """`pedir` deja en payload["precio_estimado"] {"usd", "texto"} con
    gastos.estimar: derivar = n_reediciones × final (n_paises × el precio de
    un país, sin descuento por país extra — I2) + n_regeneraciones × (video
    + final), valorando CADA regeneración k con el modelo que esa
    regeneración de verdad usa (`derivaciones.modelo_regeneracion`: nunca el
    modelo de la sesión original, que las reglas por defecto ni siquiera
    repiten — I1); rescatar escalón 1 = una re-edición = final de un país."""
    import creative_flow as cf
    import derivaciones as dv
    import gastos
    import propuestas as pr
    ac, eid, ep = ent["ac"], ent["eid"], ent["ep"]
    # La pieza del fixture viene de la sesión cf_1 (legado "cf_1__es_CO").
    cf.crear("acme", [], ["Chancla"], [], "camina", 8, "", "A", legado_id="cf_1")
    cf.actualizar("acme", "cf_1", modelo="wan3", estado="video_listo")

    assert ac.pedir("acme", eid, "derivar", {"ep_id": ep}, "ganador")[0] == "propuesta"
    prop = [p for p in pr.pendientes("acme", eid) if p["accion"] == "derivar"][0]
    precio = prop["payload"]["precio_estimado"]
    final_2 = 2 * gastos.estimar("final", paises=1)["usd"]      # el experimento tiene CO y MX
    # Reglas por defecto: 2 regeneraciones desde "wan3" — la 1.ª va a
    # "kling_o3_pro" y la 2.ª a "seedance25" (nunca "wan3", el original).
    modelos_regen = [dv.modelo_regeneracion({"modelo": "wan3"}, k) for k in range(2)]
    assert modelos_regen == ["kling_o3_pro", "seedance25"]
    videos = [gastos.estimar("video", modelo=m, duracion=8)["usd"] for m in modelos_regen]
    esperado = round(3 * final_2 + sum(v + final_2 for v in videos), 4)   # reglas por defecto: 3 re-ediciones, 2 regeneraciones
    assert precio["usd"] == esperado and precio["usd"] > 0
    assert precio["texto"] == f"{gastos.formatear(esperado)} aprox."

    assert ac.pedir("acme", eid, "rescatar", {"ep_id": ep}, "perdedor")[0] == "propuesta"
    prop = [p for p in pr.pendientes("acme", eid) if p["accion"] == "rescatar"][0]
    precio = prop["payload"]["precio_estimado"]
    assert precio["usd"] == gastos.TARIFAS["final"] and precio["texto"] == "US$ 0,10 aprox."


def test_pedir_precio_no_disponible_no_bloquea(ent):
    """Sin sesión de Crear detrás de la pieza (o sin modelo con tarifa) el
    precio es «precio no disponible» y la propuesta se crea igual. Las
    acciones que no producen no llevan precio."""
    import propuestas as pr
    ac, eid, ep = ent["ac"], ent["eid"], ent["ep"]
    assert ac.pedir("acme", eid, "derivar", {"ep_id": ep}, "ganador")[0] == "propuesta"
    prop = [p for p in pr.pendientes("acme", eid) if p["accion"] == "derivar"][0]
    assert prop["payload"]["precio_estimado"] == {"usd": None, "texto": "precio no disponible"}
    assert ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")[0] == "propuesta"
    prop = [p for p in pr.pendientes("acme", eid) if p["accion"] == "escalar"][0]
    assert "precio_estimado" not in prop["payload"]

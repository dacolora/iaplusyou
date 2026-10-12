"""Tablero de Final edition (pedido de Daniel, 2026-10-02): la pestaña ya no
repite la lista de Crear. «En edición» tiene una tarjeta por video empezado,
«Finalizados» una por final lista y «+ Nueva final edition» elige entre los
videos listos. `final_edition.tablero` decide qué va en cada columna."""
from final_edition import tablero


def _video(cf_id="cf_1", creado_en="2026-09-01T10:00:00", **extra):
    item = {"id": cf_id, "estado": "video_listo", "tipo": "video", "creado_en": creado_en,
            "guion_base": None, "finales": [], "trabajo_guion": None, "trabajo_editor": None}
    item.update(extra)
    return item


def _final(pais="CO", estado="listo", fecha="2026-09-02T10:00:00", trabajo=None, costo=None, idioma="es"):
    return {"id": f"cf_1__{idioma}_{pais}", "idioma": idioma, "pais": pais, "estado": estado, "creado_en": fecha,
            "actualizado_en": fecha, "trabajo": trabajo, "costo_usd": costo}


def _edicion(fecha="2026-09-03T10:00:00", creada_por="editor"):
    return {"id": 1, "actualizado_en": fecha, "creada_por": creada_por}


def _columna(items, eds=None):
    t = tablero.armar(items, eds or {})
    return [i["id"] for i, _ in t["en_edicion"]], [f["id"] for _, f in t["finalizados"]], t


def test_un_video_sin_empezar_solo_se_puede_elegir():
    en, fin, t = _columna([_video()])
    assert en == [] and fin == []
    assert [i["id"] for i, _ in t["elegibles"]] == ["cf_1"]


def test_imagenes_y_videos_sin_terminar_no_entran():
    items = [_video("cf_img", tipo="imagen"), _video("cf_gen", estado="video_generando")]
    en, fin, t = _columna(items)
    assert en == [] and fin == [] and t["elegibles"] == []


def test_guion_escrito_o_escribiendose_esta_en_edicion():
    en, _, t = _columna([_video(guion_base={"bloques": []})])
    assert en == ["cf_1"] and t["en_edicion"][0][1]["guion"] == "listo"
    assert t["en_edicion"][0][1]["siguiente"] == "producir"
    en, _, t = _columna([_video(trabajo_guion={"job_id": "j_guion"})])
    r = t["en_edicion"][0][1]
    assert en == ["cf_1"] and r["guion"] == "escribiendo" and r["trabajos"][0] == {"job_id": "j_guion", "tipo": "guion"}


def test_editor_preparandose_o_edicion_propia_esta_en_edicion():
    en, _, t = _columna([_video(trabajo_editor={"job_id": "j_ed"})])
    assert en == ["cf_1"] and t["en_edicion"][0][1]["trabajos"] == [{"job_id": "j_ed", "tipo": "editor"}]
    en, _, t = _columna([_video()], {"cf_1": [_edicion()]})
    assert en == ["cf_1"] and t["en_edicion"][0][1]["ediciones"] == 1


def test_final_lista_sin_nada_pendiente_sale_de_en_edicion():
    item = _video(guion_base={"bloques": []}, finales=[_final()])
    en, fin, t = _columna([item], {"cf_1": [_edicion("2026-09-01T12:00:00"),
                                            _edicion("2026-09-02T11:00:00", creada_por="final_edition")]})
    assert en == [] and fin == ["cf_1__es_CO"]
    assert t["elegibles"][0][1]["listas"] == 1      # el selector dice que ya tiene una final


def test_degradada_cuenta_como_finalizada():
    _, fin, _ = _columna([_video(finales=[_final(estado="degradada")])])
    assert fin == ["cf_1__es_CO"]


def test_final_con_error_o_interrumpida_deja_el_video_en_edicion():
    finales = [_final("CO"), _final("US", estado="error", idioma="en"), _final("BR", estado="generando", idioma="pt")]
    en, fin, t = _columna([_video(finales=finales)])
    r = t["en_edicion"][0][1]
    assert en == ["cf_1"] and fin == ["cf_1__es_CO"]
    assert r["con_error"] == 2 and r["produciendo"] == 0 and r["listas"] == 1 and r["siguiente"] == "error"


def test_final_produciendose_va_en_edicion_con_su_barra():
    f = _final(estado="generando", trabajo={"job_id": "j_final"})
    en, fin, t = _columna([_video(finales=[f], trabajo_guion={"job_id": "j_guion"})])
    r = t["en_edicion"][0][1]
    assert en == ["cf_1"] and fin == [] and r["produciendo"] == 1 and r["siguiente"] == "produciendo"
    assert [x["job_id"] for x in r["trabajos"]] == ["j_guion", "j_final"]


def test_editar_despues_de_la_ultima_final_lo_vuelve_a_poner_en_edicion():
    item = _video(finales=[_final(fecha="2026-09-02T10:00:00")])
    en, fin, t = _columna([item], {"cf_1": [_edicion("2026-09-05T09:00:00")]})
    assert en == ["cf_1"] and fin == ["cf_1__es_CO"]
    assert t["en_edicion"][0][1]["siguiente"] == "producir_otra_vez"
    # El borrador automático se vuelve a guardar al producir: no cuenta.
    en, _, _ = _columna([item], {"cf_1": [_edicion("2026-09-05T09:00:00", creada_por="final_edition")]})
    assert en == []


def test_orden_por_lo_ultimo_que_se_movio():
    viejo = _video("cf_viejo", creado_en="2026-08-01T10:00:00", guion_base={"bloques": []})
    nuevo = _video("cf_nuevo", creado_en="2026-09-20T10:00:00", guion_base={"bloques": []})
    # cf_viejo es más viejo, pero su edición es de hoy: va primero.
    en, _, _ = _columna([nuevo, viejo], {"cf_viejo": [_edicion("2026-10-01T08:00:00")]})
    assert en == ["cf_viejo", "cf_nuevo"]
    a = _video("cf_a", finales=[_final("CO", fecha="2026-09-10T10:00:00")])
    b = _video("cf_b", finales=[dict(_final("US", fecha="2026-09-12T10:00:00", idioma="en"), id="cf_b__en_US")])
    _, fin, _ = _columna([a, b])
    assert fin == ["cf_b__en_US", "cf_1__es_CO"]


def test_cifras_del_tablero():
    a = _video("cf_a", finales=[_final("CO", costo=0.5), _final("MX", costo=0.25),
                                _final("US", estado="generando", trabajo={"job_id": "j"}, idioma="en")])
    b = _video("cf_b", finales=[dict(_final("CO", costo=None), id="cf_b__es_CO")])
    c = _video("cf_c")
    t = tablero.armar([a, b, c], {}, costo_finales=0.75)
    assert t["cifras"] == {"en_edicion": 1, "produciendo": 1, "finalizados": 3, "paises": 2, "costo_usd": 0.75,
                           "elegibles": 3}
    assert tablero.armar([c], {})["cifras"]["costo_usd"] is None


def test_lo_que_tiene_un_trabajo_vivo_va_primero():
    """Su barra tiene que quedar entre las tarjetas pintadas (24) para que la
    página se recargue sola, aunque el video sea viejo (revisión, 2026-10-02)."""
    viejo = _video("cf_viejo", creado_en="2026-08-01T10:00:00", trabajo_editor={"job_id": "j_ed"})
    nuevo = _video("cf_nuevo", creado_en="2026-09-20T10:00:00", guion_base={"bloques": []})
    en, _, _ = _columna([nuevo, viejo], {"cf_nuevo": [_edicion("2026-10-01T08:00:00")]})
    assert en == ["cf_viejo", "cf_nuevo"]


def test_pnd112_cambiar_guion_devuelve_a_edicion(base_temporal, monkeypatch):
    import creative_flow as cf
    import db
    cid = cf.crear('acme', [], [], [], 'video', 8, '', 'A')
    cf.actualizar('acme', cid, estado='video_listo')
    monkeypatch.setattr(db, 'ahora', lambda: '2026-10-01T10:00:00')
    cf.guardar_guion_base('acme', cid, {'bloques': [{'texto': 'antes'}]})
    fid = cf.crear_final('acme', cid, 'es', 'CO')
    cf.actualizar_final('acme', fid, estado='listo')
    def resumen():
        item = cf.cargar('acme')[cid]
        item.update(guion_base=cf.guion_base('acme', cid), finales=cf.finales('acme', cid))
        return tablero.resumen(item, [_edicion('2026-10-03T00:00:00', 'final_edition')])
    assert not resumen()['en_edicion']
    monkeypatch.setattr(db, 'ahora', lambda: '2026-10-02T10:00:00')
    cf.guardar_guion_base('acme', cid, {'bloques': [{'texto': 'antes'}]})
    assert not resumen()['en_edicion']
    cf.guardar_guion_base('acme', cid, {'bloques': [{'texto': 'después'}]})
    assert resumen()['en_edicion']
    assert resumen()['siguiente'] == 'producir_otra_vez'
    assert cf.finales('acme', cid)[0]['estado'] == 'listo'

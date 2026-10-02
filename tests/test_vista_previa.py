"""Datos de la página de vista previa del editor: destinos, materiales,
proxies pendientes y la configuración compartida con el motor de ffmpeg."""
import json

import audios
from final_edition import documento, vista_previa


def test_destinos_base_primero_y_sin_claves_de_solo_idioma():
    doc = documento.nuevo_video("9:16")
    doc["guion"] = {"idioma": "es", "pais": "MX"}
    doc["variables"] = {"textos": {"hook": {"es": "a", "es_MX": "b", "en_US": "c"}}, "voz": {}, "precios": {"es_CO": 1}}
    assert vista_previa.destinos(doc) == ["es_MX", "en_US", "es_CO"]


def test_destinos_sin_claves_usa_el_idioma_base_y_el_pais_del_guion():
    doc = documento.nuevo_video("9:16")
    assert vista_previa.destinos(doc) == ["es_CO"]
    doc["idioma_base"] = "pt"
    doc["guion"] = {"pais": "BR"}
    assert vista_previa.destinos(doc) == ["pt_BR"]


def test_destinos_incluye_voces_y_subtitulos_por_destino():
    doc = documento.nuevo_video("9:16")
    doc["subtitulos"] = {"palabras": {"en_US": [], "es": []}}
    doc["pistas"].append({"id": "a", "tipo": "audio", "clips": [{"id": "x", "por_destino": {"pt_BR": None, "es": None}}]})
    assert vista_previa.destinos(doc) == ["en_US", "pt_BR"]


def test_pendientes_video_sin_proxy_o_viejo_y_audio_sin_picos():
    mats = {1: {"tipo": "video", "url_proxy": None}, 2: {"tipo": "video", "url_proxy": "u", "proxy_version": None},
            3: {"tipo": "video", "url_proxy": "u", "proxy_version": 2}, 4: {"tipo": "audio", "picos": None},
            5: {"tipo": "audio", "picos": []}, 6: {"tipo": "imagen"}, 7: {"tipo": "imagen", "url_proxy": "u"}}
    # Tarea 6 (D13): una imagen sin su copia liviana también está pendiente.
    assert vista_previa.pendientes(mats) == [1, 2, 4, 6]


def test_config_navegador_sale_de_los_modulos():
    from final_edition import mezcla
    from final_edition.motor import subtitulos
    cfg = vista_previa.config_navegador()
    assert cfg["formatos"]["9:16"] == [1080, 1920] and cfg["fps"] == 30 and cfg["ventana_picos_ms"] == 50
    assert cfg["mezcla"]["presets"] == mezcla.PRESETS
    assert cfg["mezcla"]["preset_defecto"] == mezcla.PRESET_DEFECTO
    assert cfg["mezcla"]["ducking_musica"] == mezcla.DUCKING_VOZ_SOBRE_MUSICA
    assert cfg["mezcla"]["ducking_sonido"] == mezcla.DUCKING_VOZ_SOBRE_SONIDO
    assert (cfg["mezcla"]["vol_musica_sola"], cfg["mezcla"]["vol_musica_con_sonido"]) == (mezcla.VOL_MUSICA_SOLA, mezcla.VOL_MUSICA_CON_SONIDO)
    assert cfg["subtitulos"]["estilos"] == subtitulos.ESTILOS_ASS
    assert cfg["subtitulos"]["estilos"]["palabra_grande"]["max_palabras"] == 1
    assert cfg["subtitulos"]["em_por_tam"] == subtitulos.escala_libass()
    assert {"Inter-Bold", "Inter-SemiBold", "SpaceGrotesk-Bold"} <= set(cfg["fuentes"])
    json.dumps(cfg)


def test_materiales_para_y_faltantes(base_temporal):
    import materiales
    m = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2.test/v.wav", hash="h1", bytes=1,
                             duracion_ms=100, extra={"picos": [0.5], "tira_url": "https://r2.test/t.jpg"})
    doc = {"materiales": [m["id"], 999]}
    mats = vista_previa.materiales_para("acme", doc)
    assert list(mats) == [m["id"]]
    assert mats[m["id"]]["picos"] == [0.5] and mats[m["id"]]["url"] == "https://r2.test/v.wav"
    assert mats[m["id"]]["tira_url"] == "https://r2.test/t.jpg"
    assert vista_previa.faltantes(doc, mats) == [999]
    assert vista_previa.materiales_para("otro", doc) == {}


def test_la_vista_previa_usa_los_recortes_del_render(base_temporal):
    # Revisión de la Task 5: sin cola en el material, el render hace corte seco
    # (compilador.verificar_recortes); la vista previa no debe mostrar un fundido.
    import materiales
    clon = materiales.registrar("acme", tipo="video", origen="crear", url="u", hash="h", bytes=1, duracion_ms=4000)
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [
        {"id": "a", "inicio_ms": 0, "duracion_ms": 2000, "material_id": clon["id"], "recorte": {"desde_ms": 2000, "hasta_ms": 4000},
         "transicion": {"tipo": "fundido", "duracion_ms": 500}},
        {"id": "b", "inicio_ms": 2000, "duracion_ms": 2000, "material_id": clon["id"], "recorte": {"desde_ms": 0, "hasta_ms": 2000}}]
    doc = documento.validar(doc)
    mats = vista_previa.materiales_para("acme", doc)
    vista, aviso = vista_previa.documento_para_vista(doc, mats)
    assert aviso is None and vista["pistas"][0]["clips"][0]["transicion"] is None
    assert doc["pistas"][0]["clips"][0]["transicion"]["tipo"] == "fundido"      # el original no se toca
    doc["pistas"][0]["clips"][1]["recorte"]["desde_ms"] = 3000                  # b pide 3000–5000 de un clon de 4000
    vista2, aviso2 = vista_previa.documento_para_vista(doc, mats)
    assert "'b'" in aviso2 and vista2 is doc


def test_encolar_proxies_uno_por_material_gratis_y_con_reintentos(monkeypatch):
    import trabajos
    llamadas = []
    monkeypatch.setattr(trabajos, "encolar", lambda *a, **k: llamadas.append((a, k)) or True)
    assert vista_previa.encolar_proxies("acme", [3, 7]) == 2
    args, kw = llamadas[0]
    assert args[:3] == ("acme__mat3__proxy", "edicion_proxy", {"cliente": "acme", "material_id": 3})
    assert kw["max_intentos"] == 3 and kw["cliente"] == "acme"


def test_material_para_siempre_tiene_palabras_solo_con_con_palabras_trae_la_lista(base_temporal):
    """Capa 5a (Task 5): `tiene_palabras` va siempre; `palabras` solo si se
    pide (la biblioteca general no las manda — pesarían demasiado)."""
    import materiales
    m = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2.test/v.wav", hash="hp1", bytes=1,
                             extra={"palabras": [{"t_ms": 0, "dur_ms": 100, "texto": "hola"}]})
    sin = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2.test/v2.wav", hash="hp2", bytes=1)
    d = vista_previa.material_para(m)
    assert d["tiene_palabras"] is True and "palabras" not in d
    d2 = vista_previa.material_para(m, con_palabras=True)
    assert d2["palabras"] == [{"t_ms": 0, "dur_ms": 100, "texto": "hola"}]
    assert vista_previa.material_para(sin)["tiene_palabras"] is False
    assert vista_previa.material_para(sin, con_palabras=True)["palabras"] is None


def test_materiales_para_manda_las_palabras(base_temporal):
    """`materiales_para` (la que alimenta `datos_pagina`) siempre las pide:
    la página deriva los subtítulos sin otra vuelta al servidor."""
    import materiales
    m = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2.test/v.wav", hash="hp3", bytes=1,
                             extra={"palabras": [{"t_ms": 0, "dur_ms": 100, "texto": "hola"}]})
    mats = vista_previa.materiales_para("acme", {"materiales": [m["id"]]})
    assert mats[m["id"]]["palabras"] == [{"t_ms": 0, "dur_ms": 100, "texto": "hola"}]


def test_datos_pagina_trae_idiomas_y_trabajos_vivos_de_subtitulos(base_temporal, monkeypatch):
    import ediciones
    import trabajos
    from final_edition import documento
    from tareas import edicion as tareas_edicion
    doc = documento.nuevo_video("9:16")
    ed = ediciones.crear("acme", "video", "Demo", doc)
    datos = vista_previa.datos_pagina("acme", ed, {})
    assert datos["subtitulos"]["idiomas"] == list(audios.IDIOMAS)
    assert datos["trabajos_vivos"]["subtitulos"] is None
    job_id = tareas_edicion.job_id_transcribir("acme", ed["id"])
    monkeypatch.setattr(trabajos, "en_curso", lambda jid: jid == job_id)
    datos2 = vista_previa.datos_pagina("acme", ed, {})
    assert datos2["trabajos_vivos"]["subtitulos"] == job_id


def test_datos_pagina_trae_voz_y_grabacion(base_temporal, monkeypatch):
    """Editor capa 5a, Task 6 (D9/D12): la galería de voces (con género y tono
    ya traducidos — el editor no es Jinja), las velocidades traducidas, y los
    topes de la grabación del micrófono; `trabajos_vivos.voz` sigue la
    edición igual que `subtitulos`."""
    import ediciones
    import materiales
    import trabajos
    from final_edition import biblioteca, documento
    from tareas import edicion as tareas_edicion
    doc = documento.nuevo_video("9:16")
    ed = ediciones.crear("acme", "video", "Demo", doc)
    datos = vista_previa.datos_pagina("acme", ed, {})
    assert len(datos["voces"]) == len(audios.fichas_voces())
    assert {"nombre", "genero", "genero_nombre", "tono"} <= set(datos["voces"][0])
    assert datos["voz"] == {"idiomas": list(audios.IDIOMAS), "nombres_idioma": audios.NOMBRES_IDIOMA,
                            "velocidades": dict(audios.NOMBRES_VELOCIDAD), "max_caracteres": audios.MAX_CARACTERES,
                            "idioma_defecto": audios.idioma_defecto("acme")}
    assert datos["grabacion"] == {"max_ms": biblioteca.MAX_GRABACION_MS, "max_bytes": materiales.LIMITES["audio"][0]}
    assert datos["trabajos_vivos"]["voz"] is None
    job_id = tareas_edicion.job_id_voz("acme", ed["id"])
    monkeypatch.setattr(trabajos, "en_curso", lambda jid: jid == job_id)
    datos2 = vista_previa.datos_pagina("acme", ed, {})
    assert datos2["trabajos_vivos"]["voz"] == job_id


def test_datos_pagina_traduce_las_voces_al_idioma_de_quien_mira(base_temporal):
    """`voces` sale en el idioma activo (D13): un proyecto en inglés ve
    `genero_nombre`/`tono` en inglés, no en español."""
    import ediciones
    import idiomas
    from final_edition import documento
    doc = documento.nuevo_video("9:16")
    ed = ediciones.crear("acme", "video", "Demo", doc)
    with idiomas.en_idioma("en"):
        datos = vista_previa.datos_pagina("acme", ed, {})
    por_nombre = {v["nombre"]: v for v in datos["voces"]}
    assert por_nombre["Rachel"]["genero_nombre"] == "Female" and por_nombre["Rachel"]["tono"] == "calm"


def test_material_para_dice_el_idioma_que_habla_una_voz(base_temporal):
    """Capa 5a (Task 8, fix round 1): la biblioteca decide con qué idioma entra
    una voz con IA o una locución por el que habla (`extra.idioma`); lo que no
    es un idioma de dos letras no se manda."""
    import materiales
    voz = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2.test/i1.mp3", hash="hi1", bytes=1,
                               extra={"nombre": "Hola", "idioma": "en"})
    raro = materiales.registrar("acme", tipo="audio", origen="locucion", url="https://r2.test/i2.mp3", hash="hi2", bytes=1,
                                extra={"idioma": "english"})
    grab = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2.test/i3.mp3", hash="hi3", bytes=1)
    assert vista_previa.material_para(voz)["idioma"] == "en"
    assert vista_previa.material_para(raro)["idioma"] is None
    assert vista_previa.material_para(grab)["idioma"] is None


# --- fuentes, tipografía y emojis (capa 5c, Task 1) --------------------------

def test_fuentes_son_los_ids_del_catalogo_y_nunca_la_de_emojis():
    from final_edition import fuentes
    ids = [f["id"] for f in fuentes.catalogo()]
    assert vista_previa.fuentes() == ids and ids[0] == "Inter-Bold" and len(ids) == 11
    assert fuentes.EMOJI_ID not in vista_previa.fuentes()
    assert vista_previa.config_navegador()["fuentes"] == ids


def test_config_navegador_trae_catalogo_tipografia_y_emoji():
    from final_edition import fuentes
    cfg = vista_previa.config_navegador()
    assert cfg["catalogo_fuentes"] == fuentes.catalogo()
    assert all({"id", "nombre", "categoria"} <= set(f) for f in cfg["catalogo_fuentes"])
    assert cfg["tipografia"] == fuentes.cargar_tabla()
    assert cfg["tipografia"]["fuentes"]["Inter-Bold"]["upem"] == 2048
    assert cfg["emoji"] == {"familia": "CreatvEmoji", "archivo": "fonts/emoji/TwemojiMozilla.ttf"}
    json.dumps(cfg)


def test_config_navegador_sin_fuente_de_emojis_manda_emoji_none(monkeypatch):
    from final_edition import fuentes
    monkeypatch.setenv("EDITOR_SIN_EMOJI", "1")
    fuentes.cargar_tabla.cache_clear()
    try:
        cfg = vista_previa.config_navegador()
        assert cfg["emoji"] is None and cfg["tipografia"]["emoji"] is None
        assert cfg["tipografia"]["fuentes"] == fuentes.generar_tabla()["fuentes"]
    finally:
        monkeypatch.delenv("EDITOR_SIN_EMOJI")
        fuentes.cargar_tabla.cache_clear()
    assert vista_previa.config_navegador()["emoji"] is not None


def test_config_navegador_sin_el_archivo_de_emojis_manda_emoji_none(monkeypatch, tmp_path):
    # el despliegue perdió la TTF: la tabla (`cargar_tabla`) ya sale sin emoji y la página no declara nada
    from final_edition import fuentes
    fuentes.cargar_tabla.cache_clear()
    try:
        with monkeypatch.context() as m:
            m.setattr(fuentes, "RUTA_EMOJI", str(tmp_path / "no_existe.ttf"))
            fuentes.cargar_tabla.cache_clear()
            cfg = vista_previa.config_navegador()
            assert cfg["emoji"] is None and cfg["tipografia"]["emoji"] is None
            assert cfg["tipografia"]["fuentes"] == fuentes.generar_tabla()["fuentes"]
    finally:
        fuentes.cargar_tabla.cache_clear()
    assert vista_previa.config_navegador()["emoji"] is not None


def test_material_para_dice_si_se_puede_tenir(base_temporal):
    import materiales
    con = materiales.registrar("acme", tipo="imagen", origen="sticker", url="https://r2.test/s1.png", hash="hs1", bytes=1,
                               extra={"tenible": True})
    sin = materiales.registrar("acme", tipo="imagen", origen="subida", url="https://r2.test/s2.png", hash="hs2", bytes=1)
    assert vista_previa.material_para(con)["tenible"] is True
    assert vista_previa.material_para(sin)["tenible"] is False

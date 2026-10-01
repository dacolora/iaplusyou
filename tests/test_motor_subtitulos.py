from final_edition.motor import subtitulos as s

PAL = [{"t_ms": 0, "dur_ms": 400, "texto": "Hola"}, {"t_ms": 400, "dur_ms": 500, "texto": "mundo"},
       {"t_ms": 900, "dur_ms": 300, "texto": "esto"}, {"t_ms": 1200, "dur_ms": 300, "texto": "es"},
       {"t_ms": 1500, "dur_ms": 400, "texto": "una"}, {"t_ms": 3000, "dur_ms": 400, "texto": "prueba"}]


def test_tiempo_ass_formato_centesimas():
    assert s._tiempo_ass(0) == "0:00:00.00"
    assert s._tiempo_ass(61234) == "0:01:01.23"
    assert s._tiempo_ass(3600000) == "1:00:00.00"


def test_ventanas_cierran_por_cantidad_y_por_hueco():
    v = s.ventanas(PAL, max_palabras=4, max_ms=5000)
    assert [len(x["palabras"]) for x in v] == [4, 1, 1]
    assert v[0]["t_ms"] == 0 and v[0]["dur_ms"] == 1500
    assert v[2]["t_ms"] == 3000


def test_ventanas_cierran_por_duracion_maxima():
    v = s.ventanas(PAL[:5], max_palabras=10, max_ms=1000)
    assert [len(x["palabras"]) for x in v] == [2, 2, 1]


def test_ventanas_cierra_antes_de_pasar_max_caracteres():
    # "Hola mundo" (10) + " extraordinario" (15) = 25 > 22: cierra antes.
    palabras = [{"t_ms": 0, "dur_ms": 300, "texto": "Hola"}, {"t_ms": 300, "dur_ms": 300, "texto": "mundo"},
                {"t_ms": 600, "dur_ms": 300, "texto": "extraordinario"}]
    v = s.ventanas(palabras, max_palabras=4, max_ms=1800, max_caracteres=22)
    assert [len(x["palabras"]) for x in v] == [2, 1]
    assert [p["texto"] for p in v[0]["palabras"]] == ["Hola", "mundo"]
    assert v[1]["palabras"][0]["texto"] == "extraordinario"


def test_ventanas_sin_max_caracteres_se_comporta_como_hoy():
    v = s.ventanas(PAL, max_palabras=4, max_ms=5000, max_caracteres=None)
    assert [len(x["palabras"]) for x in v] == [4, 1, 1]


def test_ventanas_palabra_larga_sola_siempre_entra():
    larga = "a" * 30
    v = s.ventanas([{"t_ms": 0, "dur_ms": 300, "texto": larga}], max_palabras=4, max_ms=1800, max_caracteres=22)
    assert len(v) == 1 and v[0]["palabras"][0]["texto"] == larga


def test_sin_palabras_devuelve_vacio():
    assert s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "palabras": []}, "9:16") == s.SIN_SUBTITULOS
    assert s.eventos({"estilo_id": "karaoke", "palabras": []}) == []


def test_estilo_desconocido_cae_a_karaoke():
    ass = s.generar_ass({"estilo_id": "inventado", "posicion": 0.78, "palabras": PAL[:1]}, "9:16")
    assert "Style: karaoke," in ass


def test_escapa_llaves_barras_y_saltos_en_el_texto(tmp_path):
    ass = s.generar_ass({"estilo_id": "minimal", "posicion": 0.8,
                         "palabras": [{"t_ms": 0, "dur_ms": 300, "texto": "a{b}\nc"}]}, "9:16")
    assert "a(b) c" in ass
    ruta = tmp_path / "s.ass"
    s.escribir_ass(ass, str(ruta))
    assert ruta.read_text(encoding="utf-8").startswith("[Script Info]")


def test_generar_ass_escapa_backslash():
    ass = s.generar_ass({"estilo_id": "minimal", "posicion": 0.78,
                         "palabras": [{"t_ms": 0, "dur_ms": 300, "texto": "a\\Nb"}]}, "9:16")
    assert "a/Nb" in ass


def test_generar_ass_posicion_en_pixeles_del_formato():
    ass = s.generar_ass({"estilo_id": "caja", "posicion": 0.5, "palabras": PAL[:2]}, "1:1")
    assert "\\pos(540,540)" in ass


def test_estilos_ass_es_el_mismo_dict():
    assert s.ESTILOS_ASS is s._ESTILOS
    assert set(s.ESTILOS_ASS) == set(s.ESTILOS)


def test_estilos_ass_trae_los_campos_de_la_tabla_d7_sin_secundario():
    campos = {"tam", "negrita", "primario", "contorno", "fondo", "borde", "grosor", "sombra",
              "max_palabras", "max_caracteres", "resalta", "mayusculas", "resaltado"}
    for estilo_id, e in s.ESTILOS_ASS.items():
        assert set(e) == campos, estilo_id
        assert "secundario" not in e
    assert s.ESTILOS_ASS["karaoke"]["tam"] == 64 and s.ESTILOS_ASS["karaoke"]["resalta"] is True
    assert s.ESTILOS_ASS["karaoke"]["max_palabras"] == 4 and s.ESTILOS_ASS["karaoke"]["max_caracteres"] == 22
    assert s.ESTILOS_ASS["karaoke"]["resaltado"] == "#FFD400"
    assert s.ESTILOS_ASS["caja"]["tam"] == 60 and s.ESTILOS_ASS["caja"]["resalta"] is False
    assert s.ESTILOS_ASS["caja"]["resaltado"] is None
    assert s.ESTILOS_ASS["palabra_grande"]["tam"] == 110 and s.ESTILOS_ASS["palabra_grande"]["resalta"] is True
    assert s.ESTILOS_ASS["palabra_grande"]["max_palabras"] == 1 and s.ESTILOS_ASS["palabra_grande"]["max_caracteres"] == 10
    assert s.ESTILOS_ASS["palabra_grande"]["mayusculas"] is True
    assert s.ESTILOS_ASS["minimal"]["tam"] == 52 and s.ESTILOS_ASS["minimal"]["resalta"] is False
    assert s.ESTILOS_ASS["minimal"]["max_palabras"] == 5 and s.ESTILOS_ASS["minimal"]["max_caracteres"] == 28
    assert s.ESTILOS_ASS["minimal"]["negrita"] == 0


def test_estilo_efectivo_resaltado_del_documento_o_del_estilo():
    ef = s.estilo_efectivo({"estilo_id": "karaoke"})
    assert ef["resaltado"] == "#FFD400" and ef["tam_base_px"] == 64
    ef2 = s.estilo_efectivo({"estilo_id": "karaoke", "resaltado": "#3DDC84", "escala": 1.5})
    assert ef2["resaltado"] == "#3DDC84" and ef2["tam_base_px"] == 96
    ef3 = s.estilo_efectivo({"estilo_id": "caja", "resaltado": "#3DDC84"})
    assert ef3["resaltado"] is None  # caja no resalta: nunca lleva color


def test_eventos_karaoke_una_palabra_resaltada_a_la_vez():
    evs = s.eventos({"estilo_id": "karaoke", "palabras": PAL})
    assert [(e["t_ms"], e["dur_ms"]) for e in evs] == [
        (0, 400), (400, 500), (900, 300), (1200, 300), (1500, 400), (3000, 400)]
    assert [e["tam_px"] for e in evs] == [64] * 6
    textos = [[p["texto"] for p in e["palabras"] if p["resaltada"]][0] for e in evs]
    assert textos == ["Hola", "mundo", "esto", "es", "una", "prueba"]
    # la primera línea (Hola mundo esto es) trae las 4 palabras en cada evento
    assert [p["texto"] for p in evs[1]["palabras"]] == ["Hola", "mundo", "esto", "es"]


def test_eventos_caja_una_linea_por_ventana_sin_resaltar():
    evs = s.eventos({"estilo_id": "caja", "palabras": PAL})
    assert len(evs) == 3
    assert all(not p["resaltada"] for e in evs for p in e["palabras"])
    assert [p["texto"] for p in evs[0]["palabras"]] == ["Hola", "mundo", "esto", "es"]


def test_eventos_minimal_tope_de_cinco_palabras():
    palabras = [{"t_ms": i * 100, "dur_ms": 50, "texto": c} for i, c in enumerate("abcdef")]
    evs = s.eventos({"estilo_id": "minimal", "palabras": palabras})
    assert [len(e["palabras"]) for e in evs] == [5, 1]


def test_eventos_palabra_grande_mayusculas_y_estiramiento():
    evs = s.eventos({"estilo_id": "palabra_grande", "palabras": PAL})
    assert len(evs) == 6
    assert all(len(e["palabras"]) == 1 and e["palabras"][0]["resaltada"] for e in evs)
    assert [e["palabras"][0]["texto"] for e in evs] == ["HOLA", "MUNDO", "ESTO", "ES", "UNA", "PRUEBA"]
    # cada evento (salvo el último) se estira hasta el inicio del siguiente
    for i in range(len(evs) - 1):
        assert evs[i]["t_ms"] + evs[i]["dur_ms"] == evs[i + 1]["t_ms"] or evs[i + 1]["t_ms"] - (evs[i]["t_ms"] + evs[i]["dur_ms"]) > s.HUECO_MAX_MS
    # una -> prueba: hueco de 1100 ms, no se estira
    una = evs[4]
    assert una["t_ms"] == 1500 and una["dur_ms"] == 400


def test_eventos_palabra_grande_palabra_larga_achica_tam_px():
    evs = s.eventos({"estilo_id": "palabra_grande",
                     "palabras": [{"t_ms": 0, "dur_ms": 500, "texto": "extraordinariamente"}]})
    assert len(evs) == 1 and evs[0]["tam_px"] == 58


def test_eventos_escala_agranda_tam_px():
    evs = s.eventos({"estilo_id": "karaoke", "escala": 1.5, "palabras": PAL[:2]})
    assert all(e["tam_px"] == 96 for e in evs)


def test_eventos_hueco_600_estira_601_no():
    estirado = s.eventos({"estilo_id": "palabra_grande", "palabras": [
        {"t_ms": 0, "dur_ms": 300, "texto": "Hola"}, {"t_ms": 900, "dur_ms": 200, "texto": "mundo"}]})
    assert estirado[0]["t_ms"] == 0 and estirado[0]["dur_ms"] == 900  # se estiró hasta 900

    sin_estirar = s.eventos({"estilo_id": "palabra_grande", "palabras": [
        {"t_ms": 0, "dur_ms": 300, "texto": "Hola"}, {"t_ms": 901, "dur_ms": 200, "texto": "mundo"}]})
    assert sin_estirar[0]["t_ms"] == 0 and sin_estirar[0]["dur_ms"] == 300  # queda natural


def test_eventos_lineas_que_se_solapan_la_primera_termina_donde_empieza_la_segunda():
    evs = s.eventos({"estilo_id": "palabra_grande", "palabras": [
        {"t_ms": 0, "dur_ms": 1000, "texto": "Hola"}, {"t_ms": 800, "dur_ms": 200, "texto": "mundo"}]})
    assert evs[0]["t_ms"] == 0 and evs[0]["dur_ms"] == 800
    assert evs[1]["t_ms"] == 800 and evs[1]["dur_ms"] == 200


def test_generar_ass_karaoke_fontsize_y_tantos_dialogue_como_eventos():
    ass = s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "palabras": PAL}, "9:16")
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: karaoke," in ass
    linea_style = next(l for l in ass.splitlines() if l.startswith("Style:"))
    assert linea_style.split(",")[2] == "64"
    dialogos = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogos) == 6
    assert "{\\1c&H00D4FF&}mundo{\\1c&HFFFFFF&}" in dialogos[1]
    assert "\\pos(540,1498)" in dialogos[0]


def test_generar_ass_escala_1_5_sale_96_en_el_style():
    ass = s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "escala": 1.5, "palabras": PAL[:2]}, "9:16")
    linea_style = next(l for l in ass.splitlines() if l.startswith("Style:"))
    assert linea_style.split(",")[2] == "96"


def test_generar_ass_palabra_larga_lleva_fs_override():
    ass = s.generar_ass({"estilo_id": "palabra_grande", "posicion": 0.78,
                         "palabras": [{"t_ms": 0, "dur_ms": 500, "texto": "extraordinariamente"}]}, "9:16")
    dialogos = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert "{\\fs58}" in dialogos[0]


def test_generar_ass_resaltado_personalizado_en_bgr():
    ass = s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "resaltado": "#3DDC84",
                         "palabras": PAL[:1]}, "9:16")
    assert "&H84DC3D&" in ass


def test_generar_ass_ventana_recorta_y_desplaza_eventos():
    ass = s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "palabras": PAL}, "9:16", ventana=(1000, 3200))
    # "mundo" termina en 900 <= 1000 (el inicio de la ventana): su evento (el
    # que la resalta a ELLA) no toca la ventana y no aparece como ninguna
    # línea resaltada, aunque siga siendo contexto de la línea compartida.
    assert "{\\1c&H00D4FF&}mundo{\\1c&HFFFFFF&}" not in ass
    dialogos = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    esto = next(d for d in dialogos if "{\\1c&H00D4FF&}esto{\\1c&HFFFFFF&}" in d)
    assert esto.split(",")[1] == "0:00:00.00" and esto.split(",")[2] == "0:00:00.20"
    prueba = next(d for d in dialogos if "prueba" in d)
    assert prueba.split(",")[1] == "0:00:02.00"


def test_generar_ass_sin_eventos_en_la_ventana_devuelve_vacio():
    ass = s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "palabras": PAL}, "9:16", ventana=(10000, 20000))
    assert ass == s.SIN_SUBTITULOS


def test_escala_libass_sale_de_la_tabla_os2_de_inter():
    k = s.escala_libass()
    assert 0.6 < k < 1.0          # em más chico que Fontsize: libass mide asc+desc
    assert s.escala_libass() == k  # determinista (con caché)

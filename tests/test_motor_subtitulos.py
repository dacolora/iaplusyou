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


def test_generar_ass_karaoke_lleva_playres_y_k_por_palabra():
    ass = s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "palabras": PAL}, "9:16")
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: karaoke," in ass
    lineas = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(lineas) == 3
    assert "\\k40" in lineas[0] and "\\k50" in lineas[0]
    assert "Hola mundo esto es" in lineas[0].replace("{\\k40}", "").replace("{\\k50}", "").replace("{\\k30}", "")


def test_generar_ass_posicion_en_pixeles_del_formato():
    ass = s.generar_ass({"estilo_id": "caja", "posicion": 0.5, "palabras": PAL[:2]}, "1:1")
    assert "\\pos(540,540)" in ass


def test_sin_palabras_devuelve_vacio():
    assert s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "palabras": []}, "9:16") == s.SIN_SUBTITULOS


def test_estilo_desconocido_cae_a_karaoke():
    ass = s.generar_ass({"estilo_id": "inventado", "posicion": 0.78, "palabras": PAL[:1]}, "9:16")
    assert "Style: karaoke," in ass


def test_escapa_llaves_y_saltos_en_el_texto(tmp_path):
    ass = s.generar_ass({"estilo_id": "minimal", "posicion": 0.8,
                         "palabras": [{"t_ms": 0, "dur_ms": 300, "texto": "a{b}\nc"}]}, "9:16")
    assert "a(b) c" in ass
    ruta = tmp_path / "s.ass"
    s.escribir_ass(ass, str(ruta))
    assert ruta.read_text(encoding="utf-8").startswith("[Script Info]")

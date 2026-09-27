import json
import os

import pytest

from final_edition import documento as d, mezcla
from final_edition.motor import compilador as c

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos")


def _doc(idioma="es", pais="CO"):
    with open(os.path.join(FIX, "video_basico.json"), encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), idioma, pais)


RUTAS = {1: "/m/clon.mp4", 2: "/m/voz.wav", 3: "/m/musica.wav", "png:t1": "/m/t1.png", "ass": "/m/sub.ass"}


def _esperado():
    with open(os.path.join(FIX, "esperado_basico.filtergraph.txt"), encoding="utf-8") as f:
        lineas = [l for l in f.read().splitlines() if l.strip()]
    mezcla_txt = mezcla.filtro_mezcla(voz="[au_voz]", sonido=None, musica="[au_musica]",
                                      volumenes=mezcla.volumenes_para("equilibrada"))
    return lineas + mezcla_txt.split(";")


def test_filtergraph_del_fixture_basico_sin_ass():
    plan = c.compilar(_doc(), RUTAS, con_ass=False)
    assert plan.filtergraph.split(";") == _esperado()
    assert [e["ruta"] for e in plan.entradas] == ["/m/clon.mp4", "/m/t1.png", "/m/voz.wav", "/m/musica.wav"]
    assert plan.entradas[3]["opciones"] == ["-stream_loop", "-1"]
    assert plan.salida_audio and plan.duracion_ms == 7000 and (plan.ancho, plan.alto) == (1080, 1920)
    assert plan.overlays == 1


def test_con_ass_agrega_un_solo_filtro_subtitles_y_el_texto():
    plan = c.compilar(_doc(), RUTAS, con_ass=True)
    assert plan.filtergraph.count("subtitles=") == 1
    assert "subtitles='/m/sub.ass'" in plan.filtergraph
    assert plan.ass_texto.startswith("[Script Info]")
    # los textos libres siguen siendo PNG aunque haya ASS (escalados a su
    # caja y luego superpuestos)
    assert "[1:v]scale=400:200[l1]" in plan.filtergraph and "[l1]overlay" in plan.filtergraph


def test_sin_subtitulos_en_el_idioma_no_hay_filtro():
    plan = c.compilar(_doc("en", "US"), RUTAS, con_ass=True)
    assert "subtitles=" not in plan.filtergraph and plan.ass_texto == ""


def test_ventana_desplaza_tiempos_a_cero():
    plan = c.compilar(_doc(), RUTAS, ventana=(3500, 7000), con_ass=False)
    assert "trim=start=3.500:end=7.000" in plan.filtergraph
    assert "xfade" not in plan.filtergraph
    assert plan.duracion_ms == 3500
    assert "overlay" not in plan.filtergraph  # el texto t1 termina en 2700 < 3500


def test_imagen_estatica_sin_audio_ni_tiempo():
    doc = d.nuevo_imagen("1:1")
    doc["pistas"][0]["clips"] = [{"id": "i1", "inicio_ms": 0, "duracion_ms": 0, "material_id": 9,
                                  "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}}]
    doc = d.resolver(d.validar(doc), "es", "CO")
    plan = c.compilar(doc, {9: "/m/foto.png"})
    assert plan.salida_video and not plan.salida_audio and plan.duracion_ms == 0
    assert "scale=1080:1080" in plan.filtergraph and "overlay" not in plan.filtergraph


def test_velocidad_aplica_setpts():
    doc = _doc()
    doc["pistas"][0]["clips"][0]["velocidad"] = 2.0
    doc["pistas"][0]["clips"][0]["transicion"] = None
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "setpts=(PTS-STARTPTS)/2.0" in plan.filtergraph


def test_transicion_con_velocidad_escala_la_cola():
    doc = _doc()
    doc["pistas"][0]["clips"][0]["velocidad"] = 2.0
    plan = c.compilar(doc, RUTAS, con_ass=False)
    # 3500 ms de salida a 2x = 7000 ms de fuente, más la cola de transición
    # (500 ms de salida) también a 2x = 1000 ms de fuente -> 8000.
    assert "trim=start=0.000:end=8.000" in plan.filtergraph
    # el offset del xfade es tiempo de SALIDA: no lo toca la velocidad.
    assert "xfade=transition=fade:duration=0.500:offset=3.500" in plan.filtergraph


def test_tres_clips_corte_y_fundido():
    # corte seco 0-2000, fundido 500 ms 2000-5000, corte seco 5000-7000.
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [
        {"id": "c1", "inicio_ms": 0, "duracion_ms": 2000, "material_id": 1,
         "recorte": {"desde_ms": 0, "hasta_ms": 2000}},
        {"id": "c2", "inicio_ms": 2000, "duracion_ms": 3000, "material_id": 1,
         "recorte": {"desde_ms": 2000, "hasta_ms": 5000},
         "transicion": {"tipo": "fundido", "duracion_ms": 500}},
        {"id": "c3", "inicio_ms": 5000, "duracion_ms": 2000, "material_id": 1,
         "recorte": {"desde_ms": 5000, "hasta_ms": 7000}},
    ]
    doc = d.resolver(d.validar(doc), "es", "CO")
    plan = c.compilar(doc, {1: "/m/clon.mp4"}, con_ass=False)
    # el corte seco entre c1 y c2 necesita su propio timebase antes del xfade
    # que sigue (concat sale a 1/1000000; xfade exige 1/fps en ambas patas).
    assert "concat=n=2:v=1:a=0,settb=1/30[vx1]" in plan.filtergraph
    assert "xfade=transition=fade:duration=0.500:offset=5.000[vc]" in plan.filtergraph
    assert plan.duracion_ms == 7000


def test_dos_voces_en_una_pista_se_suman():
    doc = _doc()
    doc["pistas"][2]["clips"] = [
        {"id": "v1", "inicio_ms": 0, "duracion_ms": 3000, "material_id": 2, "rol_audio": "voz",
         "recorte": {"desde_ms": 0, "hasta_ms": 3000}, "audio": {"volumen": 1.0}},
        {"id": "v2", "inicio_ms": 3500, "duracion_ms": 3500, "material_id": 2, "rol_audio": "voz",
         "recorte": {"desde_ms": 0, "hasta_ms": 3500}, "audio": {"volumen": 1.0}},
    ]
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "adelay=3500|3500" in plan.filtergraph
    assert "amix=inputs=2:normalize=0[au_voz]" in plan.filtergraph
    # una vez como salida del amix, otra vez como entrada de la mezcla final.
    assert plan.filtergraph.count("[au_voz]") == 2


def test_voz_que_empieza_tarde_lleva_adelay():
    doc = _doc()
    doc["pistas"][2]["clips"][0]["inicio_ms"] = 1500
    doc["pistas"][2]["clips"][0]["duracion_ms"] = 5500
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "adelay=1500|1500" in plan.filtergraph


def test_keyframes_de_posicion_generan_expresion_en_t():
    doc = _doc()
    # t1 ya tiene x=0.5 de base; con >= 2 keyframes de posición la expresión
    # deja de ser la constante de _expr_animacion y pasa a ser lineal por
    # tramos en t. x=0.2 -> px=216, caja 400 px centrada -> 216-200=16;
    # x=0.8 -> px=864 -> 864-200=664 (formato 9:16, lienzo 1080 de ancho).
    doc["pistas"][1]["clips"][0]["keyframes"] = [
        {"t_ms": 0, "transform": {"x": 0.2}},
        {"t_ms": 2000, "transform": {"x": 0.8}},
    ]
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "if(lt(t," in plan.filtergraph
    assert "16.000" in plan.filtergraph
    assert "664.000" in plan.filtergraph


def test_fundidos_de_audio_solo_en_bordes_reales():
    # ventana=(0,3500) corta la voz y la música (que duran 7000) a mitad de
    # camino: ese corte no es su fin real, así que no debe sonar el fundido
    # de salida (sonaría a mitad de frase, y el tramo siguiente entraría
    # sin la mitad que ya se "gastó" en este fundido).
    plan = c.compilar(_doc(), RUTAS, ventana=(0, 3500), con_ass=False)
    assert "afade=t=out" not in plan.filtergraph


def test_ventana_sin_clips_de_audio_emite_silencio_si_el_documento_tiene_audio():
    # La voz y la música terminan con el primer tramo (3500): la ventana
    # (3500, 7000) no tiene ningún clip de audio activo, pero el documento sí
    # tiene audio en general — sin relleno, ese tramo saldría sin stream de
    # audio y `concat -c copy` cortaría el audio del video entero ahí.
    doc = _doc()
    doc["pistas"][2]["clips"][0]["duracion_ms"] = 3500
    doc["pistas"][2]["clips"][0]["recorte"]["hasta_ms"] = 3500
    doc["pistas"][3]["clips"][0]["duracion_ms"] = 3500
    doc["pistas"][3]["clips"][0]["recorte"]["hasta_ms"] = 3500
    plan = c.compilar(doc, RUTAS, ventana=(3500, 7000), con_ass=False)
    assert "anullsrc=r=48000:cl=stereo[aout]" in plan.filtergraph
    assert plan.salida_audio is True


def test_documento_sin_audio_no_inventa_silencio():
    doc = _doc()
    doc["pistas"] = doc["pistas"][:2]  # solo video y texto, sin pistas de audio
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "anullsrc" not in plan.filtergraph
    assert plan.salida_audio is False


def test_dos_fuentes_en_la_principal_es_error():
    doc = _doc()
    doc["pistas"][0]["clips"][1]["material_id"] = 99
    with pytest.raises(ValueError, match="más de una fuente"):
        c.compilar(doc, {**RUTAS, 99: "/m/otro.mp4"}, con_ass=False)


def test_ruta_faltante_es_error_con_el_clip():
    rutas_incompletas = {k: v for k, v in RUTAS.items() if k != "png:t1"}
    with pytest.raises(ValueError, match="t1"):
        c.compilar(_doc(), rutas_incompletas, con_ass=False)


def test_pista_oculta_y_silenciada_se_ignoran():
    doc = _doc()
    doc["pistas"][1]["oculta"] = True
    doc["pistas"][3]["silenciada"] = True
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "overlay" not in plan.filtergraph and "[au_musica]" not in plan.filtergraph


def test_transiciones_mapean_a_xfade():
    assert c._transicion_xfade("fundido") == "fade"
    assert c._transicion_xfade("deslizar") == "slideleft"
    assert c._transicion_xfade("zoom") == "zoomin"
    assert c._transicion_xfade("desenfoque") == "fadeblack"


# ---- final review, grupo B --------------------------------------------------

_TRANSFORM = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}


def test_roles_de_sonido_se_suman_en_au_sonido():
    # C1: un clip `sonido` + un clip `efecto` → un solo amix hacia [au_sonido]
    # (antes "el último gana" dejaba una etiqueta suelta y ffmpeg rechazaba
    # el grafo).
    doc = _doc()
    doc["pistas"][3]["clips"] = [
        {"id": "s1", "inicio_ms": 0, "duracion_ms": 7000, "material_id": 3, "rol_audio": "sonido",
         "recorte": {"desde_ms": 0, "hasta_ms": 7000}, "audio": {"volumen": 1.0}},
        {"id": "e1", "inicio_ms": 1000, "duracion_ms": 500, "material_id": 3, "rol_audio": "efecto",
         "recorte": {"desde_ms": 0, "hasta_ms": 500}, "audio": {"volumen": 1.0}},
    ]
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert plan.filtergraph.count("amix=inputs=2:normalize=0[au_sonido]") == 1
    assert "[au_efecto]" not in plan.filtergraph
    # ninguna etiqueta suelta: cada una se produce una vez y se consume una vez
    assert plan.filtergraph.count("[au_sonido]") == 2
    assert plan.filtergraph.count("[au_sonido_0]") == 2 and plan.filtergraph.count("[au_sonido_1]") == 2
    # el efecto empieza en 1000: lleva su adelay
    assert "adelay=1000|1000" in plan.filtergraph


def test_un_solo_clip_de_efecto_entra_como_au_sonido():
    doc = _doc()
    doc["pistas"][3]["clips"][0]["rol_audio"] = "efecto"
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "[au_efecto]" not in plan.filtergraph and plan.filtergraph.count("[au_sonido]") == 2
    assert "amix=inputs=2:normalize=0[au_sonido]" not in plan.filtergraph


def test_superpuesto_con_clips_es_error_explicito():
    # I1: el PIP no se renderiza en la capa 1; mejor un error claro que un
    # video con la capa ignorada en silencio.
    doc = _doc()
    doc["pistas"].append({"id": "p_pip", "tipo": "superpuesto", "bloqueada": False, "silenciada": False, "oculta": False,
                          "clips": [{"id": "pip1", "inicio_ms": 0, "duracion_ms": 1000, "material_id": 1,
                                     "recorte": {"desde_ms": 0, "hasta_ms": 1000}, "transform": dict(_TRANSFORM), "keyframes": []}]})
    with pytest.raises(ValueError, match="PIP"):
        c.compilar(doc, RUTAS, con_ass=False)
    doc["pistas"][-1]["clips"] = []
    c.compilar(doc, RUTAS, con_ass=False)  # una pista superpuesta vacía no molesta


def test_capa_png_se_escala_a_su_caja():
    # I2: la caja de geometria.caja manda el tamaño del PNG en el lienzo;
    # sin el scale, `escala` solo movía la capa sin agrandarla.
    doc = _doc()
    doc["pistas"][1]["clips"][0]["transform"]["escala"] = 1.5
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "[1:v]scale=600:300[l1]" in plan.filtergraph
    assert "[vc][l1]overlay=" in plan.filtergraph
    assert "[vc][1:v]overlay" not in plan.filtergraph


def test_capa_con_opacidad_aplica_colorchannelmixer():
    doc = _doc()
    doc["pistas"][1]["clips"][0]["transform"]["opacidad"] = 0.5
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "[1:v]scale=400:200,format=rgba,colorchannelmixer=aa=0.5[l1]" in plan.filtergraph


def test_imagen_con_capa_de_texto_sale_overlay_sin_enable():
    # I3: un documento imagen (duración 0) no tiene ventana de tiempo: todas
    # las capas entran, sin `enable=`.
    doc = d.nuevo_imagen("1:1")
    doc["pistas"][0]["clips"] = [{"id": "i1", "inicio_ms": 0, "duracion_ms": 0, "material_id": 9}]
    doc["pistas"].append({"id": "p_texto", "tipo": "texto", "clips": [
        {"id": "t1", "inicio_ms": 0, "duracion_ms": 0, "texto": {"literal": "Hola"},
         "estilo": {"fuente": "Inter"}, "ancho_px": 400, "alto_px": 200}]})
    doc = d.resolver(d.validar(doc), "es", "CO")
    plan = c.compilar(doc, {9: "/m/foto.png", "png:t1": "/m/t1.png"})
    assert "overlay=" in plan.filtergraph and "enable=" not in plan.filtergraph
    assert plan.duracion_ms == 0 and plan.overlays == 1
    assert [e["ruta"] for e in plan.entradas] == ["/m/foto.png", "/m/t1.png"]


def test_verificar_recortes_rechaza_recorte_mas_alla_del_material():
    # I5: c2 pide 3500..7000 de un material de 6000 ms.
    with pytest.raises(ValueError, match="c2"):
        c.verificar_recortes(_doc(), {1: 6000})
    # la voz de 7000 sobre un material de 6999 tampoco cabe
    with pytest.raises(ValueError, match="a1"):
        c.verificar_recortes(_doc(), {2: 6999})


def test_verificar_recortes_acorta_la_cola_de_la_transicion():
    # c1 necesita 3500 + 500 de cola = 4000; con 3800 de material la cola
    # se queda en 300. c2 lee desde 0 para que él sí quepa.
    doc = _doc()
    doc["pistas"][0]["clips"][1]["recorte"] = {"desde_ms": 0, "hasta_ms": 3500}
    out = c.verificar_recortes(doc, {1: 3800})
    assert out["pistas"][0]["clips"][0]["transicion"] == {"tipo": "fundido", "duracion_ms": 300}
    # y con velocidad 2x la cola de salida vale la mitad de la fuente sobrante
    doc = _doc()
    doc["pistas"][0]["clips"][0]["velocidad"] = 2.0
    doc["pistas"][0]["clips"][1]["recorte"] = {"desde_ms": 0, "hasta_ms": 3500}
    out = c.verificar_recortes(doc, {1: 7700})  # c1 a 2x consume 7000; sobran 700 → 350 de salida
    assert out["pistas"][0]["clips"][0]["transicion"]["duracion_ms"] == 350


def test_verificar_recortes_sin_cola_quita_la_transicion():
    doc = _doc()
    doc["pistas"][0]["clips"][1]["recorte"] = {"desde_ms": 0, "hasta_ms": 3500}
    out = c.verificar_recortes(doc, {1: 3500})
    assert out["pistas"][0]["clips"][0]["transicion"] is None


def test_verificar_recortes_ignora_materiales_sin_duracion_y_musica_en_bucle():
    doc = _doc()
    # el material 1 no está en `duraciones` (sin ffprobe todavía): no se juzga;
    # la música va con -stream_loop -1, así que un clip de 7000 sobre 4000 vale.
    out = c.verificar_recortes(doc, {2: 7000, 3: 4000})
    assert out["pistas"][0]["clips"][0]["transicion"] == {"tipo": "fundido", "duracion_ms": 500}


def test_ruta_filtro_escapa_dos_puntos_comillas_y_barras():
    # I7: ffmpeg parsea la ruta dos veces (grafo y opciones del filtro). `:`
    # y `\` se escapan con `\` para el segundo nivel (dentro de '...' el
    # primero los deja pasar); la comilla no se puede escapar dentro de una
    # cita, así que se cierra, va escapada y se reabre: `\'\''`. Verificado
    # con ffmpeg 9 real (`movie='...'`) sobre una ruta con los tres.
    assert c._ruta_filtro("/m/a:b'c\\d.ass") == "/m/a\\:b\\'\\''c\\\\d.ass"
    assert c._ruta_filtro("/m/normal.ass") == "/m/normal.ass"


def test_subtitles_lleva_fontsdir_escapado():
    plan = c.compilar(_doc(), {**RUTAS, "ass": "/m/su b:1.ass"}, con_ass=True)
    assert "subtitles='/m/su b\\:1.ass':fontsdir='" in plan.filtergraph
    assert c.FONTSDIR.endswith(os.path.join("static", "fonts")) and os.path.isdir(c.FONTSDIR)
    assert f":fontsdir='{c._ruta_filtro(c.FONTSDIR)}'[os]" in plan.filtergraph


def test_pista_principal_corta_se_rellena_con_tpad():
    # I6: la principal termina en 6000 pero la voz sigue hasta 7000 — el
    # último cuadro se clona hasta el fin del tramo en vez de cortar el video
    # antes que el audio.
    doc = _doc()
    doc["pistas"][0]["clips"][1]["duracion_ms"] = 2500
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "[vp]tpad=stop_mode=clone:stop_duration=1.000[vc]" in plan.filtergraph
    assert plan.duracion_ms == 7000
    # un solo clip corto: el tpad reemplaza al `null`
    doc["pistas"][0]["clips"] = doc["pistas"][0]["clips"][:1]
    doc["pistas"][0]["clips"][0]["transicion"] = None
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "[v0]tpad=stop_mode=clone:stop_duration=3.500[vc]" in plan.filtergraph
    # el fixture completo (la principal dura todo el documento) no lleva tpad
    assert "tpad" not in c.compilar(_doc(), RUTAS, con_ass=False).filtergraph


def test_pista_imagen_antes_de_la_de_video_no_es_la_principal():
    # _pista_principal: manda la pista `video`; una `imagen` listada antes es
    # una capa (logo) y no el fondo.
    doc = _doc()
    doc["pistas"].insert(0, {"id": "p_img", "tipo": "imagen", "bloqueada": False, "silenciada": False, "oculta": False,
                             "clips": [{"id": "img1", "inicio_ms": 0, "duracion_ms": 7000, "material_id": 5,
                                        "transform": dict(_TRANSFORM), "ancho_px": 200, "alto_px": 100, "keyframes": []}]})
    plan = c.compilar(doc, {**RUTAS, 5: "/m/logo.png"}, con_ass=False)
    assert plan.entradas[0]["ruta"] == "/m/clon.mp4"
    assert "[0:v]trim=start=0.000:end=4.000" in plan.filtergraph
    assert "[1:v]scale=200:100[l1]" in plan.filtergraph
    assert plan.overlays == 2


def test_ken_burns_agrega_zoompan_y_sigue_donde_iba_en_cada_tramo():
    doc = _doc()
    doc["pistas"][0]["clips"][0]["ken_burns"] = "in"
    doc["pistas"][0]["clips"][1]["ken_burns"] = "out"
    fg = c.compilar(doc, RUTAS, con_ass=False).filtergraph
    assert ("fps=30,zoompan=z='min(1+0.08*(on+0)/105,1.08)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            ":s=1080x1920:fps=30,format=yuv420p[v0]") in fg
    assert "zoompan=z='max(1.08-0.08*(on+0)/105,1)'" in fg
    # ventana que arranca a mitad del primer clip (tramos): el zoom continúa,
    # no reinicia — 1000 ms = 30 cuadros ya consumidos
    fg2 = c.compilar(doc, RUTAS, ventana=(1000, 7000), con_ass=False).filtergraph
    assert "min(1+0.08*(on+30)/105,1.08)" in fg2
    # sin ken_burns no aparece (el fixture esperado sigue intacto)
    assert "zoompan" not in c.compilar(_doc(), RUTAS, con_ass=False).filtergraph

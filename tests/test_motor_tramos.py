import copy
import json
import os

import pytest

from final_edition import documento as d
from final_edition.motor import tramos as tr

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), "es", "CO")


def _con_textos(n, inicio_ms=0, dur_ms=7000):
    doc = _doc()
    pista = doc["pistas"][1]
    base = pista["clips"][0]
    pista["clips"] = []
    for i in range(n):
        c = copy.deepcopy(base); c["id"] = f"t{i}"; c["inicio_ms"] = inicio_ms; c["duracion_ms"] = dur_ms
        c["texto"] = {"literal": f"texto {i}"}
        pista["clips"].append(c)
    return doc


def test_capas_cuenta_textos_imagenes_superpuestos_no_subtitulos():
    doc = _doc()
    capas = tr.capas_overlay(doc)
    assert [c["clip_id"] for c in capas] == ["t1"]


def test_un_tramo_si_cabe():
    assert tr.partir(_doc()) == [(0, 7000)]


def test_parte_en_fronteras_de_clips_cuando_se_pasa():
    # 40 textos en los primeros 3,5 s y 40 en los últimos: 80 > 60 en total,
    # pero cada mitad cabe → 2 tramos en la frontera del clip principal.
    doc = _con_textos(40, 0, 3500)
    extra = _con_textos(40, 3500, 3500)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    doc["pistas"][0]["clips"][0]["transicion"] = None
    assert tr.partir(doc) == [(0, 3500), (3500, 7000)]


def test_no_corta_dentro_de_una_transicion():
    doc = _con_textos(40, 0, 3500)
    extra = _con_textos(40, 3500, 3500)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    # transición de 500 ms en el clip 1: ocupa [3500, 4000); ningún corte cae ahí
    cortes = tr.partir(doc)
    fines = [b for _a, b in cortes]
    assert not any(3500 <= c < 4000 for c in fines)
    assert 4000 in fines
    assert cortes[-1][1] == 7000


def test_punto_medio_dentro_de_transicion_se_empuja_y_acepta_el_tramo():
    # clip 1: 0–1500 con transición de 1500 ms → ocupa [1500, 3000); clip 2: 1500–7000.
    # 40 textos en [0,1500) y 40 en [1500,7000): el tramo (0,3000) toca 80 capas (> 60),
    # su punto medio 0 + max(2000, 1500) = 2000 cae dentro de la transición y se empuja
    # a 3000 = fin del tramo, así que el tramo se acepta entero en vez de cortarse en 2000.
    doc = _con_textos(40, 0, 1500)
    extra = _con_textos(40, 1500, 5500)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    principal = doc["pistas"][0]
    principal["clips"][0]["duracion_ms"] = 1500
    principal["clips"][0]["recorte"] = {"desde_ms": 0, "hasta_ms": 1500}
    principal["clips"][0]["transicion"] = {"tipo": "fundido", "duracion_ms": 1500}
    principal["clips"][1]["inicio_ms"] = 1500
    principal["clips"][1]["duracion_ms"] = 5500
    principal["clips"][1]["recorte"] = {"desde_ms": 1500, "hasta_ms": 7000}
    cortes = tr.partir(doc)
    assert cortes == [(0, 3000), (3000, 7000)]
    assert tr.contar(doc, 0, 3000) == 80  # aceptado por encima del presupuesto a propósito


def test_clip_largo_se_parte_por_tiempo():
    doc = _con_textos(50, 0, 2000)
    extra = _con_textos(50, 2000, 5000)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    doc["pistas"][0]["clips"] = [doc["pistas"][0]["clips"][0]]
    doc["pistas"][0]["clips"][0]["duracion_ms"] = 7000
    doc["pistas"][0]["clips"][0]["recorte"]["hasta_ms"] = 7000
    doc["pistas"][0]["clips"][0]["transicion"] = None
    cortes = tr.partir(doc)
    assert cortes[0] == (0, 2000) and cortes[-1][1] == 7000
    for a, b in cortes:
        assert tr.contar(doc, a, b) <= tr.PRESUPUESTO_OVERLAYS


def test_instante_imposible_lanza_error():
    with pytest.raises(ValueError, match="mismo instante"):
        tr.partir(_con_textos(61, 0, 7000))


def test_instante_imposible_en_el_idioma_del_proyecto():
    """El mensaje llega al `error` de la final y la persona puede actuar
    (quitar capas): en su idioma; en español, el de siempre."""
    import idiomas
    with idiomas.en_idioma("en"), pytest.raises(ValueError) as e:
        tr.partir(_con_textos(61, 0, 7000))
    assert str(e.value) == "There are more than 60 layers at the same moment; remove some."
    with idiomas.en_idioma("es"), pytest.raises(ValueError) as e:
        tr.partir(_con_textos(61, 0, 7000))
    assert str(e.value) == "Hay más de 60 capas en el mismo instante; quita algunas."


def test_fronteras_usan_la_misma_pista_principal_que_el_compilador():
    # documento.pista_principal: la primera pista `video` NO oculta (una
    # imagen listada antes es una capa). Una pista de video oculta que va
    # primero no debe aportar fronteras.
    doc = _doc()
    doc["pistas"].insert(0, {"id": "p_img", "tipo": "imagen", "oculta": False, "clips": []})
    doc["pistas"].insert(0, {"id": "p_vieja", "tipo": "video", "oculta": True, "clips": [
        {"id": "x1", "inicio_ms": 0, "duracion_ms": 1000, "material_id": 1, "transicion": None}]})
    assert tr._fronteras_seguras(doc, 7000) == [4000]
    assert tr._intervalos_transicion(doc) == [(3500, 4000)]


# ---- presupuesto de cortes de video (incidente 2026-09-30) ----------------
# Cada clip de la principal es su propia entrada de ffmpeg y cada una cuesta
# ~85 MB con ffmpeg 8 en el VPS (1 CPU): 32 cortes pidieron ~3 GB y el
# kernel mató el render. Por encima de PRESUPUESTO_VIDEOS se parte en tramos.

def _con_cortes(n, dur_ms=1000, d_tr=0):
    """Solo la principal, partida en `n` clips seguidos de `dur_ms`; con
    `d_tr` > 0 cada clip (menos el último) lleva un fundido de `d_tr`."""
    doc = _doc()
    base = doc["pistas"][0]["clips"][0]
    clips = []
    for i in range(n):
        c = copy.deepcopy(base)
        c.update(id=f"v{i}", inicio_ms=i * dur_ms, duracion_ms=dur_ms, recorte={"desde_ms": 0, "hasta_ms": dur_ms},
                 transicion={"tipo": "fundido", "duracion_ms": d_tr} if d_tr and i < n - 1 else None)
        clips.append(c)
    doc["pistas"] = [{**doc["pistas"][0], "clips": clips}]
    return doc


def _cubre_todo_seguido(cortes, total):
    assert cortes[0][0] == 0 and cortes[-1][1] == total
    assert all(b == c for (_a, b), (c, _d) in zip(cortes, cortes[1:]))


def test_pocos_cortes_van_en_un_solo_tramo():
    n = tr.PRESUPUESTO_VIDEOS
    assert tr.partir(_con_cortes(n)) == [(0, n * 1000)]


def test_muchos_cortes_se_parten_sin_pasar_el_presupuesto_de_videos():
    doc = _con_cortes(20)
    cortes = tr.partir(doc)
    assert len(cortes) > 1
    _cubre_todo_seguido(cortes, 20000)
    for a, b in cortes:
        assert tr.videos(doc, a, b) <= tr.PRESUPUESTO_VIDEOS


def test_agrupa_cortes_seguidos_hasta_llenar_el_presupuesto():
    # Pocos tramos: cada frontera de más es un proceso de ffmpeg y una unión
    # más; se llena cada tramo antes de abrir el siguiente.
    assert tr.partir(_con_cortes(12), presupuesto_videos=6) == [(0, 6000), (6000, 12000)]


def test_con_transiciones_no_corta_dentro_y_respeta_el_presupuesto():
    doc = _con_cortes(20, d_tr=300)
    cortes = tr.partir(doc)
    _cubre_todo_seguido(cortes, 20000)
    for a, b in cortes:
        assert tr.videos(doc, a, b) <= tr.PRESUPUESTO_VIDEOS
    for ini, fin in tr._intervalos_transicion(doc):
        assert not any(ini <= b < fin for _a, b in cortes[:-1])


# Inicio, duración y fundido (ms) de los 32 cortes de la edición de happyflops
# que el kernel mató tres veces el 2026-09-30 (la música seguía hasta 225 383).
_EDICION_HAPPYFLOPS = [
    (0, 5100, 500), (5100, 3896, 264), (8996, 3792, 500), (12788, 7902, 162), (20690, 990, 500),
    (21680, 7433, 0), (29113, 2721, 0), (31834, 2615, 0), (34449, 3719, 500), (38168, 4001, 118),
    (42169, 3477, 300), (45646, 3133, 500), (48779, 5089, 0), (53868, 1341, 500), (55209, 5787, 500),
    (60996, 3942, 0), (64938, 2076, 0), (67014, 1937, 0), (68951, 13314, 140), (82265, 7474, 218),
    (89739, 4899, 0), (94638, 6000, 500), (100638, 3355, 309), (103993, 7666, 0), (111659, 1950, 500),
    (113609, 2243, 500), (115852, 4204, 0), (120056, 8141, 0), (128197, 4211, 358), (132408, 12667, 500),
    (145075, 9805, 200), (154880, 13214, 0)]


def test_la_edicion_de_32_cortes_que_se_quedo_sin_memoria():
    doc = _con_cortes(1)
    base = doc["pistas"][0]["clips"][0]
    clips = []
    for i, (ini, dur, d_tr) in enumerate(_EDICION_HAPPYFLOPS):
        c = copy.deepcopy(base)
        c.update(id=f"v{i}", inicio_ms=ini, duracion_ms=dur, recorte={"desde_ms": 0, "hasta_ms": dur},
                 transicion={"tipo": "fundido", "duracion_ms": d_tr} if d_tr else None)
        clips.append(c)
    doc["pistas"][0]["clips"] = clips
    doc["pistas"].append({"id": "p_audio", "tipo": "audio", "oculta": False, "silenciada": False, "clips": [
        {"id": "m", "inicio_ms": 0, "duracion_ms": 225383, "material_id": 15, "rol_audio": "musica",
         "recorte": {"desde_ms": 0, "hasta_ms": 225383}, "velocidad": 1.0}]})
    cortes = tr.partir(doc)
    _cubre_todo_seguido(cortes, 225383)
    assert len(cortes) <= 8
    for a, b in cortes:
        assert tr.videos(doc, a, b) <= tr.PRESUPUESTO_VIDEOS
    for ini, fin in tr._intervalos_transicion(doc):
        assert not any(ini <= b < fin for _a, b in cortes[:-1])


def test_cada_foto_de_la_principal_cuenta_como_una_entrada():
    # Capa 5b (D2): una foto es una entrada más del render (sin -ss/-t, pero
    # decodificada y escalada): cuenta 1 en PRESUPUESTO_VIDEOS como un video.
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": f"f{i}", "inicio_ms": i * 1000, "duracion_ms": 1000, "material_id": 4, "foto": True}
                                 for i in range(8)]
    doc = d.resolver(d.validar(doc), "es", "CO")
    assert tr.videos(doc, 0, 8000) == 8
    assert tr.partir(doc) == [(0, 6000), (6000, 8000)]


# ---- encuadre con acercamiento (revisión final de la capa 5b, R7) ----------
# «llenar»/«ajustar» con zoom z escalan el cuadro ENTERO antes del crop: un
# 1080p horizontal en 9:16 pasa por 3414·z × 1920·z en cada cuadro. Medido
# (Mac, -threads 1): seis de esos clips en un tramo, zoom 2 = 1,5 GB y zoom 4
# = 2,9 GB. Cada VIDEO con zoom > 1 pesa ceil(zoom²) entradas (tope
# PRESUPUESTO_VIDEOS); una foto sigue en 1 (se escala una vez antes del loop).

def _con_zoom(zooms, d_tr=0, modo="llenar"):
    doc = _con_cortes(len(zooms), d_tr=d_tr)
    for c, z in zip(doc["pistas"][0]["clips"], zooms):
        c.update(encuadre={"modo": modo, "zoom": z, "x": 0.5, "y": 0.5}, ancho_px=1920, alto_px=1080)
    return doc


@pytest.mark.parametrize("zoom, peso", [(1.0, 1), (1.01, 2), (1.5, 3), (2.0, 4), (2.5, 6), (4.0, 6)])
def test_un_video_acercado_pesa_ceil_de_zoom_al_cuadrado(zoom, peso):
    assert tr.videos(_con_zoom([zoom]), 0, 1000) == peso


def test_ajustar_con_zoom_pesa_igual_y_sin_zoom_pesa_uno():
    assert tr.videos(_con_zoom([2.0], modo="ajustar"), 0, 1000) == 4
    doc = _con_cortes(1)
    doc["pistas"][0]["clips"][0].update(encuadre={"modo": "ajustar"}, ancho_px=1920, alto_px=1080)
    assert tr.videos(doc, 0, 1000) == 1
    doc["pistas"][0]["clips"][0]["encuadre"] = None
    assert tr.videos(doc, 0, 1000) == 1


def test_una_foto_acercada_sigue_pesando_uno():
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "f0", "inicio_ms": 0, "duracion_ms": 1000, "material_id": 4, "foto": True,
                                  "encuadre": {"modo": "llenar", "zoom": 3.0}, "ancho_px": 4000, "alto_px": 3000}]
    doc = d.resolver(d.validar(doc), "es", "CO")
    assert tr.videos(doc, 0, 1000) == 1


def test_seis_videos_con_zoom_2_van_cada_uno_en_su_tramo():
    doc = _con_zoom([2.0] * 6)
    cortes = tr.partir(doc)
    assert cortes == [(i * 1000, (i + 1) * 1000) for i in range(6)]
    for a, b in cortes:
        assert tr.videos(doc, a, b) <= tr.PRESUPUESTO_VIDEOS


def test_los_tramos_se_siguen_llenando_con_los_pesos():
    # 4 + 1 + 1 = 6 caben juntos; el cuarto (4) abre otro tramo
    assert tr.partir(_con_zoom([2.0, 1.0, 1.0, 2.0])) == [(0, 3000), (3000, 4000)]


def test_con_zoom_y_transiciones_nunca_corta_dentro_de_una():
    doc = _con_zoom([2.0, 1.0, 1.5, 2.0, 1.0, 4.0], d_tr=300)
    cortes = tr.partir(doc)
    _cubre_todo_seguido(cortes, 6000)
    assert len(cortes) > 1
    for ini, fin in tr._intervalos_transicion(doc):
        assert not any(ini <= b < fin for _a, b in cortes[:-1])

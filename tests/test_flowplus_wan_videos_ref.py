"""Wan 3.0 con videos de referencia (incidente 2026-09-30 en Forja: un video de
14,9 s y 20 s pedidos → WaveSpeed 1405 «exceeds 30s limit»). Reglas del
esquema publicado: los videos de referencia suman como máximo 15 s y, con
ellos, entrada + salida no pasan de 30 s. Y el precio: WaveSpeed factura los
segundos de entrada normalizados (cada video entre 1 y 15 s, el total hasta
15 s, redondeado hacia arriba) más los de salida — el estimado ya no lo
ignora. Kling y Seedance reciben solo el fotograma: no aplica."""
from providers import flowplus_modelos as fm


def _video(n, s=None):
    r = {"tipo": "video", "etiqueta": f"@Video {n}"}
    if s is not None:
        r["duracion_s"] = s
    return r


IMG = {"tipo": "imagen", "etiqueta": "@Imagen 1"}


def test_el_total_con_videos_no_pasa_de_30():
    assert fm.problema_duracion("wan3", [IMG, _video(1, 14.9)], 20) == {"motivo": "total", "videos_s": 14.9, "maxima": 15}
    assert fm.problema_duracion("wan3", [IMG, _video(1, 14.9)], 15) is None
    assert fm.problema_duracion("wan3", [_video(1, 5)], 25) is None


def test_los_videos_juntos_no_pasan_de_15():
    assert fm.problema_duracion("wan3", [_video(1, 10), _video(2, 8)], 5) == {
        "motivo": "videos_largos", "videos_s": 18, "maxima_videos": 15}


def test_solo_wan_recibe_videos_y_una_duracion_desconocida_no_se_juzga():
    assert fm.problema_duracion("kling_o3_pro", [_video(1, 14.9)], 15) is None
    assert fm.problema_duracion("seedance25", [_video(1, 14.9)], 30) is None
    assert fm.problema_duracion("wan3", [_video(1)], 30) is None
    assert fm.problema_duracion("wan3", [IMG], 30) is None


def test_segundos_de_videos_que_recibe_el_modelo():
    assert fm.segundos_videos("wan3", [IMG, _video(1, 3.5), _video(2)]) == [3.5]
    assert fm.segundos_videos("kling_o3_pro", [_video(1, 3.5)]) == []


def test_segundos_facturables_de_la_entrada():
    assert fm.segundos_facturables_referencia([]) == 0
    assert fm.segundos_facturables_referencia([14.9]) == 15
    assert fm.segundos_facturables_referencia([0.4]) == 1
    assert fm.segundos_facturables_referencia([3.2, 4.1]) == 8
    assert fm.segundos_facturables_referencia([10, 10]) == 15


def test_el_estimado_de_wan_suma_la_entrada():
    assert fm.estimate_video("wan3", 15) == {"credits": None, "usd": 1.5}
    assert fm.estimate_video("wan3", 15, videos_ref_s=[14.9]) == {"credits": None, "usd": 3.0}
    assert fm.estimate_video("wan3", 5, calidad="borrador", videos_ref_s=[5]) == {"credits": None, "usd": 0.5}
    assert fm.estimate_video("kling_o3_pro", 5, videos_ref_s=[10]) == fm.estimate_video("kling_o3_pro", 5)


def test_la_duracion_que_de_verdad_se_pide_con_videos():
    """Última barrera (worker y precio para reintentar): con videos de duración
    conocida Wan recorta la salida para no pasar de 30 s; sin videos, o con
    otros modelos, la duración no cambia."""
    assert fm.duracion_con_videos("wan3", [_video(1, 14.9)], 20) == 15
    assert fm.duracion_con_videos("wan3", [_video(1, 14.9)], 10) == 10
    assert fm.duracion_con_videos("wan3", [_video(1, 29.5)], 10) == fm.VIDEO["wan3"]["min_duracion"]
    assert fm.duracion_con_videos("wan3", [IMG], 20) == 20
    assert fm.duracion_con_videos("kling_o3_pro", [_video(1, 14.9)], 15) == 15

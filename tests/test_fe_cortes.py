import os
import shutil
import subprocess

import pytest

from final_edition import cortes

pytestmark = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None,
    reason="ffmpeg/ffprobe no instalados",
)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    """Dos clips 540x960: `continuo` (testsrc2, 8 s, sin cortes) y `corte`
    (4 s rojo + 4 s azul concatenados → un corte duro en 4.0 s)."""
    carpeta = tmp_path_factory.mktemp("clips")
    continuo = str(carpeta / "continuo.mp4")
    corte = str(carpeta / "corte.mp4")
    base = [cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(base + [
        "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=25",
        "-t", "8", "-pix_fmt", "yuv420p", continuo,
    ], check=True)
    subprocess.run(base + [
        "-f", "lavfi", "-i", "color=red:s=540x960:d=4",
        "-f", "lavfi", "-i", "color=blue:s=540x960:d=4",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
        "-pix_fmt", "yuv420p", corte,
    ], check=True)
    return {"continuo": continuo, "corte": corte}


# --- helpers ffmpeg/ffprobe -------------------------------------------------

def test_ffprobe_json_devuelve_streams_y_format(clips):
    info = cortes.ffprobe_json(clips["continuo"])
    assert "streams" in info and "format" in info
    video = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    assert video["width"] == 540 and video["height"] == 960


def test_duracion(clips):
    assert cortes.duracion(clips["continuo"]) == pytest.approx(8.0, abs=0.1)
    assert cortes.duracion(clips["corte"]) == pytest.approx(8.0, abs=0.1)


def test_ffmpeg_lanza_runtime_error_con_stderr(tmp_path):
    with pytest.raises(RuntimeError) as exc:
        cortes.ffmpeg(["-i", str(tmp_path / "no_existe.mp4"), "-f", "null", "-"])
    assert "no_existe.mp4" in str(exc.value)


def test_ffmpeg_respeta_variable_de_entorno(monkeypatch, tmp_path):
    falso = tmp_path / "ffmpeg_falso.sh"
    falso.write_text("#!/bin/sh\necho hola\n")
    os.chmod(str(falso), 0o755)
    monkeypatch.setattr(cortes, "FFMPEG", str(falso))
    salida = cortes.ffmpeg(["x"])
    assert salida.stdout.strip() == "hola"


# --- detección de cortes -----------------------------------------------------

def test_detectar_cortes_clip_con_corte_duro(clips):
    encontrados = cortes.detectar_cortes(clips["corte"])
    assert len(encontrados) == 1
    assert encontrados[0] == pytest.approx(4.0, abs=0.2)


def test_detectar_cortes_clip_continuo_no_tiene(clips):
    assert cortes.detectar_cortes(clips["continuo"]) == []


def test_parsear_scdet_ignora_bordes_y_ordena():
    stderr = (
        "[Parsed_scdet_0 @ 0x1] lavfi.scd.score: 15.625, lavfi.scd.time: 4\n"
        "[Parsed_scdet_0 @ 0x1] lavfi.scd.score: 12.1, lavfi.scd.time: 2.04\n"
        "[Parsed_scdet_0 @ 0x1] lavfi.scd.score: 40, lavfi.scd.time: 0.12\n"
        "[Parsed_scdet_0 @ 0x1] lavfi.scd.score: 40, lavfi.scd.time: 7.9\n"
        "[Parsed_scdet_0 @ 0x1] lavfi.scd.score: 11, lavfi.scd.time: 4.001\n"
        "otra linea sin nada\n"
    )
    assert cortes._parsear_scdet(stderr, 8.0) == [2.04, 4.0]


# --- plan de segmentos -------------------------------------------------------

def _suma(segmentos):
    return sum(s["fin"] - s["inicio"] for s in segmentos)


def _contiguos(segmentos):
    return all(a["fin"] == pytest.approx(b["inicio"]) for a, b in zip(segmentos, segmentos[1:]))


def test_planificar_sin_cortes_fabrica_ken_burns():
    plan = cortes.planificar_segmentos(8.0, [], 8.0)
    assert 3 <= len(plan) <= 4
    assert _suma(plan) == pytest.approx(8.0, abs=0.05)
    assert plan[0]["inicio"] == 0.0 and _contiguos(plan)
    assert [s["zoom"] for s in plan] == ["in", "out", "in", "out"][:len(plan)]
    duraciones = [s["fin"] - s["inicio"] for s in plan]
    assert max(duraciones) - min(duraciones) < 0.05


def test_planificar_con_corte_respeta_y_recorta_a_objetivo():
    plan = cortes.planificar_segmentos(8.0, [4.0], 6.0)
    assert _suma(plan) == pytest.approx(6.0, abs=0.05)
    assert plan[0]["inicio"] == 0.0 and _contiguos(plan)
    assert any(s["fin"] == pytest.approx(4.0) for s in plan)
    assert plan[-1]["fin"] == pytest.approx(6.0)
    assert [s["zoom"] for s in plan] == ["in", "out"]
    for s in plan:
        assert 1.5 - 0.01 <= s["fin"] - s["inicio"] <= 4.0 + 0.01


def test_planificar_parte_piezas_largas():
    plan = cortes.planificar_segmentos(10.0, [8.0], 10.0)
    assert _suma(plan) == pytest.approx(10.0, abs=0.05)
    assert any(s["fin"] == pytest.approx(8.0) for s in plan)
    for s in plan:
        assert s["fin"] - s["inicio"] <= 4.0 + 0.01
    assert [s["zoom"] for s in plan] == ["in", "out"] * (len(plan) // 2) + ["in"] * (len(plan) % 2)


def test_planificar_cortes_muy_pegados_cae_a_ken_burns():
    plan = cortes.planificar_segmentos(8.0, [0.5, 4.0], 8.0)
    assert 3 <= len(plan) <= 4
    assert _suma(plan) == pytest.approx(8.0, abs=0.05)


def test_planificar_clip_corto_reduce_a_dos_segmentos():
    plan = cortes.planificar_segmentos(3.0, [], 3.0)
    assert _suma(plan) == pytest.approx(3.0, abs=0.05)
    assert len(plan) in (1, 2)
    for s in plan:
        assert s["fin"] - s["inicio"] >= 1.5 - 0.01


def test_planificar_clip_muy_corto_da_un_solo_segmento():
    plan = cortes.planificar_segmentos(2.0, [], 2.0)
    assert len(plan) == 1
    assert _suma(plan) == pytest.approx(2.0, abs=0.05)


def test_planificar_objetivo_mayor_que_duracion():
    plan = cortes.planificar_segmentos(5.0, [], 12.0)
    assert _suma(plan) == pytest.approx(5.0, abs=0.05)
    assert plan[-1]["fin"] == pytest.approx(5.0)


def test_planificar_cola_corta_se_funde_con_el_trozo_anterior():
    # Recortado a 6 s, el trozo [5, 6] mide menos de min_seg: se funde con el
    # anterior en vez de descartar el corte real.
    plan = cortes.planificar_segmentos(8.0, [2.0, 5.0], 6.0)
    assert _suma(plan) == pytest.approx(6.0, abs=0.05)
    assert any(s["fin"] == pytest.approx(2.0) for s in plan)
    assert plan[-1]["fin"] == pytest.approx(6.0)
    for s in plan:
        assert 1.5 - 0.01 <= s["fin"] - s["inicio"] <= 4.0 + 0.01

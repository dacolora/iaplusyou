"""cortes.ultimo_fotograma: el último cuadro de un video (cadena de escenas de Flow Plus)."""
import os
import subprocess

import pytest

from final_edition import cortes


@pytest.mark.slow
def test_ultimo_fotograma_es_del_final(tmp_path):
    video = tmp_path / "v.mp4"
    # 2 s rojos y 1 s azul: el último cuadro tiene que ser azul.
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:s=64x112:d=2", "-f", "lavfi",
                    "-i", "color=blue:s=64x112:d=1", "-filter_complex", "[0][1]concat=n=2:v=1:a=0",
                    "-r", "25", "-pix_fmt", "yuv420p", str(video)], check=True)
    jpg = cortes.ultimo_fotograma(str(video), str(tmp_path / "f.jpg"))
    from PIL import Image
    r, g, b = Image.open(jpg).convert("RGB").getpixel((32, 56))
    assert b > 150 and r < 80 and os.path.getsize(jpg) > 0


def test_ultimo_fotograma_sin_video(tmp_path):
    with pytest.raises(RuntimeError):
        cortes.ultimo_fotograma(str(tmp_path / "no.mp4"), str(tmp_path / "f.jpg"))

"""`final_edition.fotos.preparar` (editor capa 5b, D2): la copia de una foto
que entra al render como clip de la pista principal — derecha (EXIF), lo
transparente sobre negro, RGB, lado largo ≤ 4096 y JPEG."""
import pytest
from PIL import Image

from final_edition import fotos


def _abrir(ruta):
    im = Image.open(ruta)
    im.load()
    return im


def test_lo_transparente_queda_sobre_negro(tmp_path):
    origen, destino = str(tmp_path / "alfa.png"), str(tmp_path / "foto_1.jpg")
    im = Image.new("RGBA", (10, 10), (0, 0, 255, 255))
    for x in range(5):
        for y in range(10):
            im.putpixel((x, y), (255, 0, 0, 0))
    assert im.getpixel((0, 0)) == (255, 0, 0, 0)
    im.save(origen)
    assert fotos.preparar(origen, destino) == (10, 10)
    out = _abrir(destino)
    assert out.format == "JPEG" and out.mode == "RGB" and out.size == (10, 10)
    # sin alfa el rojo saldría rojo; sobre negro, negro
    assert all(v < 40 for v in out.getpixel((0, 0)))
    assert out.getpixel((9, 9))[2] > 200


@pytest.mark.parametrize("modo", ["LA", "P"])
def test_tambien_gris_con_alfa_y_paleta_con_transparencia(tmp_path, modo):
    origen, destino = str(tmp_path / f"{modo}.png"), str(tmp_path / "f.jpg")
    if modo == "LA":
        im = Image.new("LA", (10, 10), (255, 0))
        im.save(origen)
    else:
        im = Image.new("P", (10, 10), 1)
        im.putpalette([0, 0, 0, 255, 255, 255] + [0] * 762)
        im.save(origen, transparency=1)
    assert fotos.preparar(origen, destino) == (10, 10)
    out = _abrir(destino)
    assert out.mode == "RGB" and all(v < 40 for v in out.getpixel((5, 5)))


def test_la_orientacion_exif_la_endereza(tmp_path):
    origen, destino = str(tmp_path / "celular.jpg"), str(tmp_path / "f.jpg")
    exif = Image.Exif()
    exif[0x0112] = 6   # girar 90° a la derecha al mostrar
    Image.new("RGB", (40, 20), (200, 10, 10)).save(origen, exif=exif.tobytes())
    assert fotos.preparar(origen, destino) == (20, 40)
    assert _abrir(destino).size == (20, 40)


def test_una_foto_enorme_baja_a_4096_de_lado_largo(tmp_path):
    origen, destino = str(tmp_path / "grande.png"), str(tmp_path / "f.jpg")
    Image.new("RGB", (5000, 3000), (10, 120, 10)).save(origen)
    ancho, alto = fotos.preparar(origen, destino)
    assert max(ancho, alto) == fotos.LADO_MAX == 4096
    assert abs(ancho / alto - 5000 / 3000) <= 0.01
    assert _abrir(destino).size == (ancho, alto)


def test_una_foto_chica_no_se_agranda(tmp_path):
    origen, destino = str(tmp_path / "chica.png"), str(tmp_path / "f.jpg")
    Image.new("RGB", (400, 200), (10, 120, 10)).save(origen)
    assert fotos.preparar(origen, destino) == (400, 200)


def test_un_archivo_que_no_es_imagen_dice_cual(tmp_path):
    origen = tmp_path / "notas.png"
    origen.write_text("esto no es una foto", encoding="utf-8")
    with pytest.raises(RuntimeError, match="No pude leer la foto notas.png"):
        fotos.preparar(str(origen), str(tmp_path / "f.jpg"))

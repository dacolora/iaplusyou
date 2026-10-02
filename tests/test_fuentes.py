"""La tabla tipográfica de las fuentes del editor (capa 5c, D4): se lee de las
TTF con `struct`, sin dependencias, y la comparten el navegador (que mide
con ella) y Pillow (que dibuja con las mismas TTF). También: el catálogo de
fuentes y las capas de color (COLR/CPAL) de la fuente de emojis."""
import io
import json
import os
import struct

import pytest
from PIL import Image, ImageDraw, ImageFont

from final_edition import fuentes


def _ttf(nombre):
    return os.path.join(fuentes.FONTS_DIR, nombre + ".ttf")


def _expandir(tramos):
    """{código: avance} desde la forma compacta de `tramos`."""
    out = {}
    for inicio, avances in tramos:
        for i, a in enumerate(avances):
            out[inicio + i] = a
    return out


def _en_repertorio(cp):
    return any(a <= cp <= b for a, b in fuentes.REPERTORIO)


# --- leer_ttf ---------------------------------------------------------------

def test_leer_ttf_inter_bold_da_las_medidas_conocidas():
    t = fuentes.leer_ttf(_ttf("Inter-Bold"))
    assert (t["upem"], t["asc"], t["desc"]) == (2048, 1984, 494)
    av = t["avances"]
    assert av[ord("H")] == 1530 and av[ord("o")] == 1256 and av[ord("l")] == 555 and av[ord("a")] == 1189
    assert av[0x20] == 485 and av[0xA0] == 485
    assert av[ord("€")] == 1402
    assert av[0x2713] == 1807                      # ✓


def test_leer_ttf_space_grotesk_bold_y_sin_glifo():
    t = fuentes.leer_ttf(_ttf("SpaceGrotesk-Bold"))
    assert (t["upem"], t["asc"], t["desc"]) == (1000, 984, 292)
    assert t["avances"][ord("H")] == 656
    assert 0x2713 not in t["avances"]              # sin glifo: glifo 0 no cuenta


def test_leer_ttf_un_archivo_de_texto_es_value_error_con_su_nombre(tmp_path):
    ruta = tmp_path / "no_es_una_fuente.ttf"
    ruta.write_text("esto no es una TTF, ni de lejos, solo texto plano para probar", encoding="utf-8")
    with pytest.raises(ValueError, match="no_es_una_fuente.ttf"):
        fuentes.leer_ttf(str(ruta))


def test_leer_ttf_truncada_es_value_error(tmp_path):
    with open(_ttf("Inter-Bold"), "rb") as f:
        mitad = f.read(4096)
    ruta = tmp_path / "cortada.ttf"
    ruta.write_bytes(mitad)
    with pytest.raises(ValueError, match="cortada.ttf"):
        fuentes.leer_ttf(str(ruta))


def test_leer_ttf_avances_coinciden_con_pillow():
    """Contra una lectura independiente (FreeType vía Pillow): el avance de
    cada carácter latino a un tamaño igual a la unidad de la fuente."""
    t = fuentes.leer_ttf(_ttf("Inter-Bold"))
    f = ImageFont.truetype(_ttf("Inter-Bold"), t["upem"])
    for ch in "Hola mundo, ¿qué tal? 0123456789":
        assert t["avances"][ord(ch)] == pytest.approx(f.getlength(ch), abs=1)


# --- tramos -----------------------------------------------------------------

def test_tramos_junta_los_codigos_consecutivos():
    assert fuentes.tramos({32: 5, 33: 6, 35: 7}) == [[32, [5, 6]], [35, [7]]]
    assert fuentes.tramos({35: 7, 32: 5, 33: 6}) == [[32, [5, 6]], [35, [7]]]      # ordena
    assert fuentes.tramos({}) == []


# --- catálogo ---------------------------------------------------------------

def test_catalogo_del_repo_sigue_el_orden_y_cada_id_tiene_su_archivo():
    cat = fuentes.catalogo()
    assert [f["id"] for f in cat] == [i for i, _n, _c in fuentes.CATALOGO]
    assert all(os.path.isfile(_ttf(f["id"])) for f in cat)
    assert {f["categoria"] for f in cat} <= set(fuentes.CATEGORIAS)
    assert cat[0] == {"id": "Inter-Bold", "nombre": "Inter Bold", "categoria": "clasicas"}
    assert len(fuentes.CATALOGO) == 11


def test_catalogo_con_una_sola_fuente_en_la_carpeta(tmp_path, monkeypatch):
    with open(_ttf("Inter-Bold"), "rb") as f:
        (tmp_path / "Inter-Bold.ttf").write_bytes(f.read())
    (tmp_path / "Otra-Fuente.ttf").write_bytes(b"x")          # fuera del CATALOGO: no aparece
    monkeypatch.setattr(fuentes, "FONTS_DIR", str(tmp_path))
    assert fuentes.catalogo() == [{"id": "Inter-Bold", "nombre": "Inter Bold", "categoria": "clasicas"}]


def test_la_fuente_de_emojis_no_esta_en_el_catalogo():
    assert fuentes.EMOJI_ID not in [f["id"] for f in fuentes.catalogo()]


def test_hay_emoji_sigue_al_archivo(monkeypatch, tmp_path):
    assert fuentes.hay_emoji() is True
    monkeypatch.setattr(fuentes, "RUTA_EMOJI", str(tmp_path / "no_existe.ttf"))
    assert fuentes.hay_emoji() is False


# --- la tabla ---------------------------------------------------------------

def test_generar_tabla_de_inter_bold():
    tabla = fuentes.generar_tabla()
    assert tabla["version"] == 1
    assert tabla["repertorio"] == [list(r) for r in fuentes.REPERTORIO]
    inter = tabla["fuentes"]["Inter-Bold"]
    assert (inter["upem"], inter["asc"], inter["desc"]) == (2048, 1984, 494)
    assert inter["avances"][0][0] == 32 and inter["avances"][0][1][0] == 485
    assert set(tabla["fuentes"]) == {f["id"] for f in fuentes.catalogo()}


def test_ningun_codigo_de_la_tabla_cae_fuera_del_repertorio():
    tabla = fuentes.generar_tabla()
    for fid, datos in tabla["fuentes"].items():
        cps = _expandir(datos["avances"])
        assert cps, fid
        assert all(_en_repertorio(cp) for cp in cps), fid
    assert 0x410 not in _expandir(tabla["fuentes"]["Inter-Bold"]["avances"])      # cirílico: Inter lo trae, el repertorio no


def test_generar_tabla_sin_el_archivo_de_emojis_deja_emoji_en_none(monkeypatch, tmp_path):
    monkeypatch.setattr(fuentes, "RUTA_EMOJI", str(tmp_path / "no_existe.ttf"))
    assert fuentes.generar_tabla()["emoji"] is None


def test_generar_tabla_con_la_fuente_de_emojis():
    emoji = fuentes.generar_tabla()["emoji"]
    assert emoji["id"] == fuentes.EMOJI_ID and emoji["upem"] > 0
    assert 0x1F525 in _expandir(emoji["avances"])           # 🔥
    assert all(_en_repertorio(cp) for cp in _expandir(emoji["avances"]))


def test_tabla_al_dia():
    """`static/editor/tipografia.json` es lo que dan las TTF de hoy; si una
    fuente cambia, se regenera con `venv/bin/python3 -m final_edition.fuentes`."""
    with open(fuentes.RUTA_TABLA, encoding="utf-8") as f:
        guardada = json.load(f)
    assert guardada == fuentes.generar_tabla(), \
        "static/editor/tipografia.json quedó viejo: correr `venv/bin/python3 -m final_edition.fuentes`"


def test_la_tabla_se_escribe_compacta_y_estable(tmp_path, monkeypatch):
    monkeypatch.setattr(fuentes, "RUTA_TABLA", str(tmp_path / "t.json"))
    fuentes.escribir_tabla()
    crudo = (tmp_path / "t.json").read_text(encoding="utf-8")
    assert crudo.endswith("\n") and "\n" not in crudo[:-1] and ": " not in crudo[:200]
    assert json.loads(crudo) == fuentes.generar_tabla()
    fuentes.escribir_tabla()
    assert (tmp_path / "t.json").read_text(encoding="utf-8") == crudo      # dos corridas, mismo archivo


@pytest.fixture
def tabla_limpia():
    fuentes.cargar_tabla.cache_clear()
    yield
    fuentes.cargar_tabla.cache_clear()


def test_cargar_tabla_lee_el_archivo_una_vez(tabla_limpia):
    a = fuentes.cargar_tabla()
    assert a is fuentes.cargar_tabla()
    with open(fuentes.RUTA_TABLA, encoding="utf-8") as f:
        assert a == json.load(f)


def test_cargar_tabla_con_editor_sin_emoji_quita_solo_la_fuente_de_emojis(tabla_limpia, monkeypatch):
    normal = fuentes.cargar_tabla()
    assert normal["emoji"] is not None
    fuentes.cargar_tabla.cache_clear()
    monkeypatch.setenv("EDITOR_SIN_EMOJI", "1")
    sin = fuentes.cargar_tabla()
    assert sin["emoji"] is None
    assert sin["fuentes"] == normal["fuentes"] and sin["repertorio"] == normal["repertorio"]


# --- emojis por capas (R1) --------------------------------------------------

def test_emoji_capas_de_la_llama_tiene_dos_capas_con_color_rgba():
    capas = fuentes.emoji_capas(0x1F525)
    assert len(capas) == 2
    for gid, color in capas:
        assert isinstance(gid, int) and gid > 0
        assert len(color) == 4 and all(isinstance(c, int) and 0 <= c <= 255 for c in color)


def test_emoji_capas_del_corazon_rojo_tiene_una_capa_de_color_conocido():
    capas = fuentes.emoji_capas(0x2764)
    assert len(capas) == 1
    assert capas[0][1] == (221, 46, 68, 255)               # CPAL guarda BGRA; sale RGBA


def test_emoji_capas_de_una_letra_o_sin_archivo_es_none(monkeypatch, tmp_path):
    assert fuentes.emoji_capas(ord("A")) is None
    monkeypatch.setattr(fuentes, "RUTA_EMOJI", str(tmp_path / "no_existe.ttf"))
    assert fuentes.emoji_capas(0x1F525) is None


def test_la_fuente_derivada_no_trae_color_y_dibuja_las_capas():
    datos = fuentes.fuente_emoji_capas()
    assert isinstance(datos, bytes) and datos is fuentes.fuente_emoji_capas()          # una sola vez
    assert datos[:4] in (b"\x00\x01\x00\x00", b"true")
    f = ImageFont.truetype(io.BytesIO(datos), 160)
    lienzo = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
    dib = ImageDraw.Draw(lienzo)
    for gid, color in fuentes.emoji_capas(0x1F525):
        dib.text((80, 240), chr(fuentes.PUA_CAPAS + gid), font=f, fill=color or (255, 255, 255, 255), anchor="ls")
    caja = lienzo.getchannel("A").getbbox()
    assert caja is not None and caja[3] - caja[1] > 100
    r, g, b, a = lienzo.getpixel((160, 160))
    assert a == 255 and r > 180 and b < 90


def test_la_fuente_derivada_conserva_las_demas_tablas():
    """Todas las tablas menos COLR, CPAL y cmap pasan tal cual, y el cmap
    nuevo es de formato 12 con un solo grupo U+F0000 + glifo."""
    original = open(fuentes.RUTA_EMOJI, "rb").read()
    datos = fuentes.fuente_emoji_capas()
    t0, t1 = fuentes._directorio(original), fuentes._directorio(datos)
    assert set(t0) - set(t1) == {"COLR", "CPAL"}
    assert set(t1) == (set(t0) - {"COLR", "CPAL"})
    for tag in t1:
        if tag == "cmap":
            continue
        o0, l0 = t0[tag]
        o1, l1 = t1[tag]
        assert original[o0:o0 + l0] == datos[o1:o1 + l1], tag
        assert o1 % 4 == 0
    ocmap, lcmap = t1["cmap"]
    assert lcmap == 4 + 8 + 28
    assert list(t1) == sorted(t1)                          # directorio en orden de etiqueta


def test_ninguna_capa_sin_area_llega_al_render():
    """Tres glifos de capa de Twemoji son astillas sin área (una caja de ancho
    o alto 0): no se ven, pero Pillow lanza «Bitmap missing for glyph» al
    dibujar dos de ellas en ciertos tamaños (la capa 3276 de 🌯 a 16, 32… y
    160 px). `emoji_capas` no las devuelve."""
    capas_burrito = [g for g, _c in fuentes.emoji_capas(0x1F32F)]
    assert 3276 not in capas_burrito and len(capas_burrito) == 24
    _cmap, bases = fuentes._indice_capas(fuentes.RUTA_EMOJI)
    gids = sorted({g for capas in bases.values() for g, _c in capas})
    assert not {3276, 7886, 8180} & set(gids)
    for tam in (16, 128, 160, 256):
        f = ImageFont.truetype(io.BytesIO(fuentes.fuente_emoji_capas()), tam)
        for g in gids:
            f.getmask(chr(fuentes.PUA_CAPAS + g))          # no lanza OSError


def test_el_indice_de_paleta_0xFFFF_es_el_color_del_texto():
    """El archivo real no trae capas «del color del texto»: se le pone una a
    mano (en memoria) a la capa del corazón y sale `None`, no un color."""
    datos = bytearray(open(fuentes.RUTA_EMOJI, "rb").read())
    colr = fuentes._directorio(bytes(datos))["COLR"][0]
    _v, n_bases, desde_bases, desde_capas, _n = struct.unpack_from(">HHIIH", datos, colr)
    cmap, _bases = fuentes._indice_capas(fuentes.RUTA_EMOJI)
    glifo = cmap[0x2764]
    for i in range(n_bases):
        g, primera, _cuantas = struct.unpack_from(">HHH", datos, colr + desde_bases + 6 * i)
        if g == glifo:
            break
    struct.pack_into(">H", datos, colr + desde_capas + 4 * primera + 2, 0xFFFF)
    _cmap, bases = fuentes._leer_indice(bytes(datos))
    assert bases[glifo][0][1] is None and bases[glifo][0][0] == fuentes.emoji_capas(0x2764)[0][0]

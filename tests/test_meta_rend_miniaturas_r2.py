"""PND-194 (decisión 2026-10-13): las miniaturas de los anuncios de Meta sin análisis se copian a R2, como las de
Triple Whale: la URL firmada de Meta caduca y la tarjeta se rompía. La copia diaria las sube una vez por anuncio y
creativo (las de más gasto primero, con tope por corrida) y la tarjeta muestra la copia; soltar la cuenta las borra de
R2 después de las filas. Sin red: Meta, el conector y R2 son dobles."""
import pytest
from PIL import Image

from conectores import url as conector_url
from meta_rendimiento import cuentas, datos, miniaturas, sync
from storage import r2_uploader

CLI, ACT = "hf", "act_1"
HOY = "2026-10-08"
MINI = "https://scontent.xx.fbcdn.net/{}.jpg"


@pytest.fixture()
def r2(base_temporal, monkeypatch):
    """Una cuenta elegida con anuncios con gasto y su miniatura de Meta; el conector y R2 falsos."""
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://media.creatv.test")
    cuentas.elegir(CLI, [{"id": ACT, "name": "HF", "currency": "SEK"}])
    estado = {"bajadas": [], "subidas": [], "borradas": [], "falla": set()}

    def _descargar(url, ruta, max_bytes=None, tipos=("video/",), **_):
        assert tipos == ("image/",) and max_bytes == miniaturas.MAX_BYTES
        estado["bajadas"].append(url)
        if any(f in url for f in estado["falla"]):
            raise conector_url.ErrorConector("no responde")
        Image.new("RGB", (64, 64), (200, 30, 30)).save(ruta, format="PNG")
        return 1

    def _subir(local, key, content_type):
        with Image.open(local) as im:
            assert im.format == "JPEG" and content_type == "image/jpeg"
        estado["subidas"].append(key)
        return f"https://media.creatv.test/{key}"

    monkeypatch.setattr(conector_url, "descargar_archivo", _descargar)
    monkeypatch.setattr(r2_uploader, "upload_file", _subir)
    from meta_rendimiento import analisis
    monkeypatch.setattr(analisis, "borrar_claves", lambda claves: estado["borradas"].extend(claves) or (len(claves), []))
    return estado


def _anuncio(ad_id, gasto, creative="cr", miniatura=True):
    datos.reemplazar_anuncio_dias(CLI, ACT, "2026-10-01", "2026-10-01", [
        {"fecha": "2026-10-01", "ad_id": a, "gasto": g} for a, g in _anuncio.dias.items()] + [
        {"fecha": "2026-10-01", "ad_id": ad_id, "gasto": gasto}])
    _anuncio.dias[ad_id] = gasto
    datos.guardar_objetos(CLI, ACT, [{"nivel": "anuncio", "objeto_id": ad_id, "nombre": f"Ad {ad_id}",
                                      "creative_id": f"{creative}_{ad_id}",
                                      **({"miniatura_url": MINI.format(ad_id)} if miniatura else {})}])


@pytest.fixture(autouse=True)
def _dias():
    _anuncio.dias = {}


def _extra(ad_id):
    return {o["ad_id"]: o for o in datos.totales_por_anuncio(CLI, [ACT], "2026-09-01", HOY)}[ad_id]


def test_copia_las_de_mas_gasto_una_vez_por_creativo(r2, monkeypatch):
    for ad_id, gasto in (("11", 5.0), ("22", 50.0), ("33", 20.0)):
        _anuncio(ad_id, gasto)
    _anuncio("44", 99.0, miniatura=False)                       # sin miniatura de Meta: nada que copiar
    monkeypatch.setattr(miniaturas, "TOPE_POR_CORRIDA", 2)
    assert miniaturas.copiar(CLI, ACT, "2026-09-09") == 2
    assert r2["subidas"] == [miniaturas.clave(CLI, "22"), miniaturas.clave(CLI, "33")]      # las de más gasto
    assert _extra("22")["miniatura_r2"] == f"https://media.creatv.test/clientes/{CLI}/meta_rendimiento/miniaturas/22.jpg"
    assert miniaturas.copiar(CLI, ACT, "2026-09-09") == 1 and r2["subidas"][-1] == miniaturas.clave(CLI, "11")
    assert miniaturas.copiar(CLI, ACT, "2026-09-09") == 0      # ya copiadas: nada (la URL de Meta cambia, la imagen no)
    _anuncio("22", 50.0, creative="nuevo")                      # cambió el creativo: se vuelve a copiar
    assert miniaturas.copiar(CLI, ACT, "2026-09-09") == 1 and r2["subidas"][-1] == miniaturas.clave(CLI, "22")
    assert _extra("22")["miniatura_r2"] and _extra("44")["miniatura_r2"] is None


def test_una_que_falla_no_frena_a_las_demas_ni_la_copia(r2):
    _anuncio("11", 5.0)
    _anuncio("22", 50.0)
    r2["falla"].add("22.jpg")
    assert miniaturas.copiar(CLI, ACT, "2026-09-09") == 1
    assert _extra("22")["miniatura_r2"] is None and _extra("11")["miniatura_r2"]


def test_no_pisa_lo_demas_de_extra(r2):
    _anuncio("11", 5.0)
    datos.guardar_objetos(CLI, ACT, [{"nivel": "anuncio", "objeto_id": "11", "extra": {
        "miniatura_en": "2026-10-08T01:00:00", "problemas": [{"resumen": "Ad Rejected", "mensaje": None}]}}])
    miniaturas.copiar(CLI, ACT, "2026-09-09")
    fila = _extra("11")
    assert fila["miniatura_r2"] and fila["problemas_meta"] == [{"resumen": "Ad Rejected", "mensaje": None}]


def test_si_la_cuenta_se_suelta_mientras_copia_lo_subido_se_borra(r2, monkeypatch):
    _anuncio("11", 5.0)
    subir = r2_uploader.upload_file

    def _y_se_suelta(local, key, content_type):
        url = subir(local, key, content_type)
        cuentas.elegir(CLI, [])
        return url
    monkeypatch.setattr(r2_uploader, "upload_file", _y_se_suelta)
    with pytest.raises(datos.CuentaSoltada):
        miniaturas.copiar(CLI, ACT, "2026-09-09")
    assert r2["borradas"] == [miniaturas.clave(CLI, "11")]


def test_soltar_la_cuenta_borra_sus_copias_de_r2_despues_de_las_filas(r2):
    _anuncio("11", 5.0)
    _anuncio("22", 50.0)
    miniaturas.copiar(CLI, ACT, "2026-09-09")
    filas_al_borrar = []
    from meta_rendimiento import analisis
    analisis_borrar = analisis.borrar_claves

    def _borrar(claves):
        import sqlalchemy as sa

        import db
        with db.conectar() as con:
            filas_al_borrar.append(con.execute(sa.select(sa.func.count()).select_from(db.meta_objeto)).scalar())
        return analisis_borrar(claves)
    analisis.borrar_claves = _borrar
    try:
        r = cuentas.elegir(CLI, [])
        assert r["quitadas"] == [ACT] and r["fallos_r2"] == [] and r2["borradas"] == []   # la limpieza las borra
        from meta_rendimiento import soltar
        filas, fallos = soltar.barrer(CLI)                    # lo que corre `meta_rend_limpiar` del proyecto
    finally:
        analisis.borrar_claves = analisis_borrar
    assert filas > 0 and fallos == []
    assert sorted(r2["borradas"]) == sorted([miniaturas.clave(CLI, "11"), miniaturas.clave(CLI, "22")])
    assert filas_al_borrar == [0]                             # R2 después de las filas


def test_la_copia_diaria_las_sube_y_la_tarjeta_muestra_la_de_r2(r2, monkeypatch):
    from tests.test_meta_rend_sync import FakeGraph
    FakeGraph(monkeypatch)
    sync.sincronizar(CLI, ACT, "tok", hoy=__import__("datetime").date(2026, 10, 8))
    assert miniaturas.clave(CLI, "a1") not in r2["subidas"]      # «a1» no son dígitos: nunca va en una clave
    _anuncio("123", 10.0)
    datos.guardar_objetos(CLI, ACT, [{"nivel": "anuncio", "objeto_id": "123", "extra": {"miniatura_en": "x"}}])
    cuentas.actualizar_extra(CLI, ACT, {"listado_completo_en": None})
    sync.sincronizar(CLI, ACT, "tok", hoy=__import__("datetime").date(2026, 10, 8))
    assert miniaturas.clave(CLI, "123") in r2["subidas"]
    from pestana_rendimiento import galeria
    a = _extra("123")
    assert galeria.medio_meta(a) == {"imagen": a["miniatura_r2"], "miniatura": True}
    assert galeria.medio_meta(dict(a, miniatura_r2="https://otro.example/x.jpg")) == {
        "imagen": MINI.format("123"), "miniatura": True}         # una URL que no es de R2 no se pinta

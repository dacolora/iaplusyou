"""Las funciones puras de los ganchos (spec 2026-10-09 §4.6 y §4.7): código, formato, destino, el documento del
editor y por qué no se ofrece el botón. Sin base, sin red y sin ffmpeg."""
import pytest

from final_edition import borrador, vista_previa
from final_edition import documento as documento_mod
from final_edition.motor import compilador
from triple_whale import ganchos

URL = "https://files.triplewhale.com/v/p1.mp4"
GEN = [{"n": 1, "texto": "Uno", "prompt": "Push in", "fotograma_s": 2.0}]
CLIP = {"id": 7, "duracion_ms": 3040, "extra": {"tiene_audio": False}}
ORIGINAL = {"id": 9, "duracion_ms": 20000, "ancho": 1080, "alto": 1920, "extra": {"tiene_audio": True}}


def test_codigo_y_codigo_en():
    assert ganchos.codigo(12) == "CV12" and ganchos.codigo("7") == "CV7"
    assert ganchos.codigo_en("Chanclas · gancho 2 · CV12") == 12
    assert ganchos.codigo_en("cv7 prueba") == 7 and ganchos.codigo_en("[CV31]") == 31
    for nombre in ("ACV12", "CV12a", "CV", "", None, "Sin código"):
        assert ganchos.codigo_en(nombre) is None, nombre


def test_formato_y_aspecto_mas_cercanos():
    assert ganchos.formato_cercano(1080, 1920) == "9:16" and ganchos.formato_cercano(1920, 1080) == "16:9"
    assert ganchos.formato_cercano(1080, 1350) == "4:5" and ganchos.formato_cercano(1000, 1000) == "1:1"
    assert ganchos.formato_cercano(720, 1280) == "9:16" and ganchos.formato_cercano(None, 0) == "9:16"
    assert ganchos.aspecto_kling(1080, 1920) == "9:16" and ganchos.aspecto_kling(1920, 1080) == "16:9"
    assert ganchos.aspecto_kling(1080, 1350) == "1:1" and ganchos.aspecto_kling(None, None) == "9:16"


def test_destino_tienda_proyecto_y_colombia():
    assert ganchos.destino("NO", "CO") == ("no", "NO")
    assert ganchos.destino(None, "US") == ("en", "US")
    assert ganchos.destino("DE", "SE") == ("sv", "SE")          # Alemania no está en tipos.PAISES
    assert ganchos.destino(None, "ZZ") == ("es", "CO")


def test_ganchos_generables_deja_fuera_los_que_citan_cifras_y_numera_por_posicion():
    r = {"ganchos": [{"texto": "Uno", "prompt": "a", "fotograma_s": 1.0, "cifras_sin_dato": []},
                     {"texto": "50 % menos", "prompt": "b", "fotograma_s": 2.0, "cifras_sin_dato": ["50 %"]},
                     {"texto": "Tres", "prompt": "c", "fotograma_s": None, "cifras_sin_dato": []}]}
    assert ganchos.ganchos_generables(r) == [{"n": 1, "texto": "Uno", "prompt": "a", "fotograma_s": 1.0},
                                             {"n": 3, "texto": "Tres", "prompt": "c", "fotograma_s": None}]
    assert ganchos.ganchos_generables({}) == [] and ganchos.ganchos_generables(None) == []


def _fila(resultado=None, estado="lista", duracion=20.0):
    return {"estado": estado, "resultado": {"ganchos": [{"texto": "Uno"}]} if resultado is None else resultado,
            "foto": {"creativo": {"duracion_s": duracion}}}


def test_puede_probar_dice_por_que_no():
    assert ganchos.puede_probar(_fila(), GEN, [], 0.336, URL) is None
    assert ganchos.puede_probar(_fila(estado="analizando"), GEN, [], 0.336, URL) == ganchos.MOTIVO_NO_LISTO
    assert ganchos.puede_probar(_fila({"frase": "x"}), [], [], None, URL) == ganchos.MOTIVO_VIEJO
    assert ganchos.puede_probar(_fila(), [], [], None, URL) == ganchos.MOTIVO_SIN_GANCHOS
    assert ganchos.puede_probar(_fila(), GEN, [], 0.336, None) == ganchos.MOTIVO_SIN_VIDEO
    assert ganchos.puede_probar(_fila(duracion=4.9), GEN, [], 0.336, URL) == ganchos.MOTIVO_CORTO
    assert ganchos.puede_probar(_fila(duracion=None), GEN, [], 0.336, URL) is None      # sin duración: se mide al bajar
    assert ganchos.puede_probar(_fila(), GEN, [{"estado": "armando"}], 0.336, URL) == ganchos.MOTIVO_TANDA_VIVA
    assert ganchos.puede_probar(_fila(), GEN, [{"estado": "lista"}, {"estado": "error"}], 0.336, URL) is None
    assert ganchos.puede_probar(_fila(), GEN, [], None, URL) == ganchos.MOTIVO_SIN_PRECIO


def test_tandas_agrupa_la_mas_nueva_primero_con_su_codigo():
    filas = [{"id": 4, "tanda": 1, "n": 2}, {"id": 9, "tanda": 2, "n": 1}, {"id": 3, "tanda": 1, "n": 1}]
    t = ganchos.tandas(filas)
    assert [x["tanda"] for x in t] == [2, 1]
    assert [(f["id"], f["codigo"]) for f in t[1]["filas"]] == [(3, "CV3"), (4, "CV4")]
    assert ganchos.tandas([]) == []


def test_documento_gancho_clip_original_audio_entero_y_texto():
    doc = ganchos.documento_gancho(CLIP, ORIGINAL, "¿Te duelen los pies?", "9:16", "no", "NO",
                                   analisis_id=5, gancho_id=12)
    v0, v1 = doc["pistas"][0]["clips"]
    assert (v0["material_id"], v0["inicio_ms"], v0["duracion_ms"]) == (7, 0, 3000)
    assert v0["recorte"] == {"desde_ms": 0, "hasta_ms": 3000} and v0["audio"]["volumen"] == 0.0
    assert (v1["material_id"], v1["inicio_ms"], v1["duracion_ms"]) == (9, 3000, 17000)
    assert v1["recorte"] == {"desde_ms": 3000, "hasta_ms": 20000} and v1["audio"]["volumen"] == 0.0
    pistas = {p["id"]: p for p in doc["pistas"]}
    assert "p_sonido" not in pistas                                   # ruling 1: el editor rehace p_sonido
    [audio] = pistas[ganchos.PISTA_ORIGINAL]["clips"]
    assert (audio["material_id"], audio["inicio_ms"], audio["duracion_ms"]) == (9, 0, 20000)
    assert audio["recorte"] == {"desde_ms": 0, "hasta_ms": 20000} and audio["audio"]["volumen"] == 1.0
    assert audio["rol_audio"] == "sonido" and pistas[ganchos.PISTA_ORIGINAL]["tipo"] == "audio"
    [texto] = pistas["p_texto"]["clips"]
    assert texto["texto"] == {"literal": "¿Te duelen los pies?"} and (texto["inicio_ms"], texto["duracion_ms"]) == (0, 3000)
    assert texto["estilo"]["fuente"] == borrador.ESTILO_HOOK["fuente"] and texto["transform"]["y"] == borrador.POS_HOOK["y"]
    assert doc["origen"] == {"tipo": "triple_whale", "pais": "NO", "analisis_id": 5, "gancho_id": 12}
    assert doc["idioma_base"] == "no" and doc["formato"] == "9:16" and set(doc["materiales"]) == {7, 9}
    assert vista_previa.destinos(doc) == ["no_NO"]
    resuelto = documento_mod.resolver(doc, "no", "NO")
    compilador.verificar_recortes(resuelto, {7: 3040, 9: 20000})      # nada pide más material del que hay


def test_documento_gancho_clip_corto_sin_audio_y_original_muy_corto():
    corto = dict(CLIP, duracion_ms=2500)
    doc = ganchos.documento_gancho(corto, dict(ORIGINAL, extra={"tiene_audio": False}), "Hola", "16:9", "es", "CO")
    v0, v1 = doc["pistas"][0]["clips"]
    assert v0["duracion_ms"] == 2500 and v1["inicio_ms"] == 2500 and v1["recorte"]["desde_ms"] == 2500
    assert ganchos.PISTA_ORIGINAL not in {p["id"] for p in doc["pistas"]}      # sin audio no hay pista de audio
    with pytest.raises(ganchos.GanchoError) as e:
        ganchos.documento_gancho(CLIP, dict(ORIGINAL, duracion_ms=3500), "Hola", "9:16", "es", "CO")
    assert str(e.value) == ganchos.MOTIVO_CORTO


def test_el_documento_compila_con_el_audio_entero_del_original_en_su_pista():
    """Compila a ffmpeg (sin correrlo): el video es clip + original desde el segundo 3 y el audio entra una sola vez,
    entero, desde el original (la voz sigue en sincronía con lo que se ve después del gancho)."""
    doc = ganchos.documento_gancho(CLIP, ORIGINAL, "Hola", "9:16", "es", "CO")
    plan = compilador.compilar(documento_mod.resolver(doc, "es", "CO"),
                               {7: "a.mp4", 9: "b.mp4", "png:t_gancho": "t.png"}, con_ass=False)
    assert plan.duracion_ms == 20000
    assert "atrim=start=0.000:end=20.000" in plan.filtergraph
    assert "concat=n=2:v=1:a=0" in plan.filtergraph

"""Orquestador de Final Edition (`final_edition.producir` / `preparar_guion`)
con TODAS las capas falsas: solo se prueba el cableado, la degradación y el
estado que queda en la base (`creative_flow.finales`)."""
import os
import shutil
import subprocess
import wave

import pytest

import final_edition
from final_edition import cortes, guion as guion_mod, musica, render, texto, voz

pytestmark = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None,
    reason="ffmpeg/ffprobe no instalados",
)

GUION_BASE = {
    "idioma": "es", "pais": "CO", "moneda": None, "precio_texto": None,
    "bloques": [
        {"rol": "hook", "texto_pantalla": "Hola", "texto_voz": "Hola a todos", "inicio_s": 0, "fin_s": 1.5},
        {"rol": "problema", "texto_pantalla": "Duele", "texto_voz": "Te duelen los pies", "inicio_s": 1.5, "fin_s": 3},
        {"rol": "producto", "texto_pantalla": "Chanclas", "texto_voz": "Estas chanclas", "inicio_s": 3, "fin_s": 5},
        {"rol": "prueba", "texto_pantalla": "Miles", "texto_voz": "Miles las usan", "inicio_s": 5, "fin_s": 6.5},
        {"rol": "cta", "texto_pantalla": "Pide hoy", "texto_voz": "Pide las tuyas", "inicio_s": 6.5, "fin_s": 8},
    ],
}


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    ruta = str(tmp_path_factory.mktemp("clip") / "clon.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=25",
                    "-t", "8", "-pix_fmt", "yuv420p", ruta], check=True)
    return ruta


def _wav(ruta, segundos=1.0):
    with wave.open(ruta, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"\x00\x00" * 2 * int(44100 * segundos))
    return ruta


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch, clip):
    """Sesión con video listo + todas las capas y R2 monkeypatched. Devuelve
    un dict con cf_id y las llamadas registradas."""
    import creative_flow as cf
    import catalogo_productos

    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    cf_id = cf.crear("acme", [], ["chancla_rose"], [], "la persona camina con las chanclas", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", video_local=clip,
                  enfoque="producto", aspect_ratio="9:16",
                  referencias=[{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1f.png"},
                               {"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/vf.png"},
                               {"tipo": "logo", "url": "https://x/logo.png", "frame_url": "https://x/logo.png"}])

    llamadas = {"cf_id": cf_id}
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda cliente, pid, categoria=None: {"id": pid, "nombre": "Chancla Rose",
                                                              "descripcion": "Chancla cómoda", "tipo": "calzado"})

    def fake_generar(producto, referencia, enfoque, duracion_s, idioma_base, marca, cliente_hint):
        llamadas["generar"] = dict(producto=producto, referencia=referencia, enfoque=enfoque,
                                   duracion_s=duracion_s, idioma_base=idioma_base, marca=marca)
        return dict(GUION_BASE), 0.01
    monkeypatch.setattr(guion_mod, "generar_guion_base", fake_generar)

    def fake_localizar(guion_base, idioma, pais, precio):
        llamadas["localizar"] = (idioma, pais, precio)
        g = dict(guion_base); g["idioma"] = idioma; g["pais"] = pais
        return g, 0.02
    monkeypatch.setattr(guion_mod, "localizar_guion", fake_localizar)

    monkeypatch.setattr(cortes, "detectar_cortes", lambda path, umbral=10.0: [])

    def fake_voz(guion, voz_nombre, carpeta, on_progreso=None, cliente=None):
        llamadas["voz"] = dict(voz=voz_nombre, cliente=cliente, idioma=guion["idioma"])
        os.makedirs(carpeta, exist_ok=True)
        return {"pistas": [], "palabras": [{"inicio": 0.1, "fin": 0.5, "texto": "Hola"}],
                "archivo_voz": _wav(os.path.join(carpeta, "voz.wav"))}, 0.3
    monkeypatch.setattr(voz, "sintetizar", fake_voz)

    def fake_musica(estilo, segundos, carpeta_cache=None, on_progreso=None):
        llamadas["musica"] = dict(estilo=estilo, segundos=segundos)
        os.makedirs(carpeta_cache or str(tmp_path / "musica"), exist_ok=True)
        return {"archivo": _wav(str(tmp_path / "pista.wav")), "url": "https://r2/m.wav",
                "estilo": estilo, "generada": False}, 0.0
    monkeypatch.setattr(musica, "obtener_pista", fake_musica)

    def fake_overlays(guion, palabras, marca, carpeta, ancho=1080, alto=1920):
        llamadas["texto"] = dict(palabras=palabras, marca=marca, ancho=ancho, alto=alto)
        return {"hook": None, "subtitulos": [], "badge": None, "cta": None}
    monkeypatch.setattr(texto, "generar_overlays", fake_overlays)

    def fake_componer(clon_path, segmentos, overlays, archivo_voz, pista_musica, salida_mp4, duracion_s,
                      ancho=1080, alto=1920, preset="veryfast"):
        llamadas["render"] = dict(clon=clon_path, segmentos=segmentos, voz=archivo_voz, musica=pista_musica,
                                  duracion_s=duracion_s)
        os.makedirs(os.path.dirname(salida_mp4), exist_ok=True)
        shutil.copy(clon_path, salida_mp4)
        mini = os.path.splitext(salida_mp4)[0] + "_miniatura.png"
        with open(mini, "wb") as f:
            f.write(b"png")
        return {"archivo": salida_mp4, "miniatura": mini, "duracion_s": duracion_s}
    monkeypatch.setattr(render, "componer", fake_componer)

    from storage import r2_uploader
    monkeypatch.setattr(r2_uploader, "upload_video", lambda p, k: f"https://r2/{k}")
    monkeypatch.setattr(r2_uploader, "upload_image", lambda p, k: f"https://r2/{k}")

    from providers import fal_audio
    monkeypatch.setattr(fal_audio, "transcribir_palabras",
                        lambda url, idioma, on_progreso=None: {"texto": "hola mundo", "palabras": [], "costo_usd": 0.001})
    return llamadas


def test_preparar_guion_guarda_guion_base(entorno):
    import creative_flow as cf
    g, costo = final_edition.preparar_guion("acme", entorno["cf_id"], {"precio": 89900})
    assert g["bloques"][0]["rol"] == "hook"
    assert costo == pytest.approx(0.011)
    assert cf.guion_base("acme", entorno["cf_id"])["bloques"][4]["rol"] == "cta"
    args = entorno["generar"]
    assert args["producto"]["nombre"] == "Chancla Rose" and args["producto"]["precio"] == 89900
    assert args["referencia"]["frames"] == ["https://x/1f.png", "https://x/vf.png"]
    assert args["referencia"]["transcripcion"] == "hola mundo"
    assert args["enfoque"] == "producto" and args["duracion_s"] == pytest.approx(8.0, abs=0.1)
    assert args["idioma_base"] == "es"


def test_preparar_guion_sin_producto_ni_transcripcion(entorno, monkeypatch):
    import creative_flow as cf
    import catalogo_productos
    from providers import fal_audio
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda *a, **k: None)

    def falla(*a, **k):
        raise RuntimeError("whisper caído")
    monkeypatch.setattr(fal_audio, "transcribir_palabras", falla)
    final_edition.preparar_guion("acme", entorno["cf_id"])
    args = entorno["generar"]
    assert args["producto"]["nombre"] == "la persona camina con las chanclas"
    assert args["referencia"]["transcripcion"] is None
    assert cf.guion_base("acme", entorno["cf_id"]) is not None


def test_producir_ok(entorno):
    import creative_flow as cf
    cf_id = entorno["cf_id"]
    etapas = []
    final_id, resumen = final_edition.producir("acme", cf_id, "en", "US", {"precio": 19.9, "voz": "Josh"},
                                               on_etapa=etapas.append)
    assert final_id == f"{cf_id}__en_US"
    assert etapas == [nombre for nombre, _ in final_edition.ETAPAS_FINAL]
    assert entorno["localizar"] == ("en", "US", 19.9)
    assert entorno["voz"] == {"voz": "Josh", "cliente": "acme", "idioma": "en"}
    assert entorno["musica"]["estilo"] == "urbano"
    assert entorno["texto"]["palabras"][0]["texto"] == "Hola"
    assert entorno["texto"]["marca"]["color_acento"] == "#7c3aed"
    assert entorno["render"]["clon"].endswith("clon.mp4") and entorno["render"]["voz"] and entorno["render"]["musica"]
    assert entorno["render"]["duracion_s"] == pytest.approx(8.0, abs=0.1)

    finales = cf.finales("acme", cf_id)
    assert len(finales) == 1
    f = finales[0]
    assert f["id"] == final_id and f["idioma"] == "en" and f["pais"] == "US"
    assert f["estado"] == "listo"
    assert f["video_url"] == f"https://r2/clientes/acme/finales/{final_id}.mp4"
    assert f["url_miniatura"].endswith(f"{final_id}.png")
    assert f["duracion_s"] == pytest.approx(8.0, abs=0.1)
    assert sorted(f["capas"]) == ["cortes", "guion", "musica", "render", "texto", "voz"]
    assert all(c["estado"] == "ok" for c in f["capas"].values())
    assert f["costo_usd"] == pytest.approx(0.011 + 0.02 + 0.3)
    assert f["guion"]["idioma"] == "en" and f["error"] is None
    assert resumen["estado"] == "listo" and resumen["video_url"] == f["video_url"]
    # la final no aparece como sesión de Crear
    assert final_id not in cf.cargar("acme") and cf_id in cf.cargar("acme")
    assert os.path.exists(f["url_local"])


def test_producir_reusa_fila_y_omite_capas(entorno):
    import creative_flow as cf
    cf_id = entorno["cf_id"]
    final_edition.producir("acme", cf_id, "es", "CO")
    final_id, _ = final_edition.producir("acme", cf_id, "es", "CO", {"con_voz": False, "con_musica": False})
    finales = cf.finales("acme", cf_id)
    assert len(finales) == 1 and finales[0]["id"] == final_id
    f = finales[0]
    assert f["capas"]["voz"]["estado"] == "omitida" and f["capas"]["musica"]["estado"] == "omitida"
    assert f["estado"] == "listo"
    assert entorno["render"]["voz"] is None and entorno["render"]["musica"] is None
    assert cf.final_por_legado("acme", final_id)["estado"] == "listo"
    assert cf.eliminar_final("acme", final_id) is True
    assert cf.finales("acme", cf_id) == []


def test_producir_degradada_si_falla_voz(entorno, monkeypatch):
    import creative_flow as cf

    def falla(*a, **k):
        raise RuntimeError("elevenlabs caído")
    monkeypatch.setattr(voz, "sintetizar", falla)
    final_id, resumen = final_edition.producir("acme", entorno["cf_id"], "es", "CO")
    f = cf.finales("acme", entorno["cf_id"])[0]
    assert f["estado"] == "degradada" and resumen["estado"] == "degradada"
    assert f["capas"]["voz"]["estado"] == "error" and "elevenlabs" in f["capas"]["voz"]["error"]
    assert f["capas"]["musica"]["estado"] == "ok" and f["capas"]["render"]["estado"] == "ok"
    assert entorno["render"]["voz"] is None and entorno["texto"]["palabras"] == []
    assert f["video_url"]


def test_producir_error_si_falla_render(entorno, monkeypatch):
    import creative_flow as cf

    def falla(*a, **k):
        raise RuntimeError("ffmpeg explotó")
    monkeypatch.setattr(render, "componer", falla)
    with pytest.raises(RuntimeError, match="ffmpeg explotó"):
        final_edition.producir("acme", entorno["cf_id"], "es", "CO")
    f = cf.finales("acme", entorno["cf_id"])[0]
    assert f["estado"] == "error" and "ffmpeg explotó" in f["error"]
    assert f["capas"]["render"]["estado"] == "error" and f["capas"]["voz"]["estado"] == "ok"
    assert f["video_url"] is None


def test_producir_sin_sesion(entorno):
    with pytest.raises(ValueError):
        final_edition.producir("acme", "cf_nada", "es", "CO")

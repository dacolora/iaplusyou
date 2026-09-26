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


@pytest.fixture(scope="module")
def clip_con_audio(tmp_path_factory):
    """Igual que `clip` pero con una pista de audio (tono de 440 Hz)."""
    ruta = str(tmp_path_factory.mktemp("clip") / "clon_audio.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                    "-t", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", ruta], check=True)
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
    cf_id = cf.crear("acme", [], ["Chancla Rose"], [], "la persona camina con las chanclas", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", video_local=clip,
                  enfoque="producto", aspect_ratio="9:16",
                  referencias=[{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1f.png",
                                "categoria": "producto", "activo": "Chancla Rose"},
                               {"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/vf.png"},
                               {"tipo": "imagen", "url": "https://x/logo.png", "frame_url": "https://x/logo.png",
                                "logo": True}])

    llamadas = {"cf_id": cf_id}
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda cliente, pid, categoria=None: None)
    monkeypatch.setattr(catalogo_productos, "listar",
                        lambda cliente, categoria="producto": [{"id": "chancla_rose", "nombre": "Chancla Rose",
                                                                "descripcion": "Chancla cómoda", "tipo": "calzado"}])

    def fake_generar(producto, referencia, enfoque, duracion_s, idioma_base, marca, cliente_hint, canal_optimo=None,
                     angulo=None):
        llamadas["generar"] = dict(producto=producto, referencia=referencia, enfoque=enfoque,
                                   duracion_s=duracion_s, idioma_base=idioma_base, marca=marca)
        return dict(GUION_BASE), 0.01
    monkeypatch.setattr(guion_mod, "generar_guion_base", fake_generar)

    def fake_localizar(guion_base, idioma, pais, precio, angulo=None):
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
                      ancho=1080, alto=1920, preset="veryfast", con_sonido=False, volumenes=None):
        llamadas["render"] = dict(clon=clon_path, segmentos=segmentos, voz=archivo_voz, musica=pista_musica,
                                  duracion_s=duracion_s, con_sonido=con_sonido, volumenes=volumenes)
        os.makedirs(os.path.dirname(salida_mp4), exist_ok=True)
        shutil.copy(clon_path, salida_mp4)
        mini = os.path.splitext(salida_mp4)[0] + "_miniatura.png"
        with open(mini, "wb") as f:
            f.write(b"png")
        return {"archivo": salida_mp4, "miniatura": mini, "duracion_s": duracion_s,
                "con_sonido": con_sonido and llamadas.get("clon_con_audio", False)}
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
    assert args["producto"]["descripcion"] == "Chancla cómoda"
    assert args["referencia"]["frames"] == ["https://x/1f.png", "https://x/vf.png"]
    assert args["referencia"]["transcripcion"] == "hola mundo"
    assert args["enfoque"] == "producto" and args["duracion_s"] == pytest.approx(8.0, abs=0.1)
    assert args["idioma_base"] == "es"


def test_guia_marca_corrupta_no_tumba_el_guion(entorno, monkeypatch):
    """M6/Task 8: un root.json de marca corrupto (JSON inválido) es un extra
    que se degrada a "" en vez de reventar `preparar_guion`."""
    import marca

    def root_corrupto(cliente):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")
    monkeypatch.setattr(marca, "cargar_root", root_corrupto)

    g, _ = final_edition.preparar_guion("acme", entorno["cf_id"], {"precio": 89900})
    assert g["bloques"][0]["rol"] == "hook"  # no revienta
    assert entorno["generar"]["marca"] == ""


def test_preparar_guion_sin_producto_ni_transcripcion(entorno, monkeypatch):
    import creative_flow as cf
    import catalogo_productos
    from providers import fal_audio
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda *a, **k: None)
    monkeypatch.setattr(catalogo_productos, "listar", lambda cliente, categoria="producto": [])
    cf.actualizar("acme", entorno["cf_id"], productos_ids=[],
                  referencias=[{"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/vf.png"}])

    def falla(*a, **k):
        raise RuntimeError("whisper caído")
    monkeypatch.setattr(fal_audio, "transcribir_palabras", falla)
    final_edition.preparar_guion("acme", entorno["cf_id"])
    args = entorno["generar"]
    assert args["producto"]["nombre"] == "la persona camina con las chanclas"
    assert args["referencia"]["transcripcion"] is None
    assert cf.guion_base("acme", entorno["cf_id"]) is not None


def test_preparar_guion_guarda_el_angulo_nuevo_y_no_pisa_uno_existente(entorno, monkeypatch):
    import creative_flow as cf
    nuevo = {"audiencia": "a", "consciencia": "consciente_del_problema", "sofisticacion": 2, "deseo": "d",
             "promesa": "p", "mecanismo": None, "pruebas": [], "lead": "problema_solucion", "gancho": "g", "faltantes": []}

    def generar_con_angulo(producto, referencia, enfoque, duracion_s, idioma_base, marca, cliente_hint,
                           canal_optimo=None, angulo=None):
        entorno["angulo_recibido"] = angulo
        return dict(GUION_BASE, angulo=nuevo), 0.01
    monkeypatch.setattr(guion_mod, "generar_guion_base", generar_con_angulo)
    g, _ = final_edition.preparar_guion("acme", entorno["cf_id"], {"precio": 89900})
    assert "angulo" not in g and "angulo" not in cf.guion_base("acme", entorno["cf_id"])
    guardado = cf.cargar("acme")[entorno["cf_id"]]["angulo"]
    assert guardado["promesa"] == "p" and guardado["origen"] == "guion" and entorno["angulo_recibido"] is None
    monkeypatch.setattr(guion_mod, "generar_guion_base",
                        lambda *a, **k: (dict(GUION_BASE, angulo=dict(nuevo, promesa="otra")), 0.01))
    final_edition.preparar_guion("acme", entorno["cf_id"], {"precio": 89900})
    assert cf.cargar("acme")[entorno["cf_id"]]["angulo"]["promesa"] == "p"      # el ángulo de la sesión manda


def test_preparar_guion_lleva_regla_y_precio_de_la_tienda(entorno, monkeypatch):
    import catalogo_productos
    import tiendas
    monkeypatch.setattr(catalogo_productos, "listar", lambda cliente, categoria="producto": [
        {"id": "chancla_rose", "nombre": "Chancla Rose", "descripcion": "Chancla cómoda", "tipo": "calzado",
         "regla": "Suela rosa idéntica."}])
    pid = tiendas.asegurar_manual("acme", "chancla_rose", "Chancla Rose", "Chancla cómoda")
    tiendas.marcar_producto("acme", pid, precio=89900, moneda="COP", url_compra="https://tienda.co/rose")
    final_edition.preparar_guion("acme", entorno["cf_id"])                    # sin precio escrito: el de la tienda
    p = entorno["generar"]["producto"]
    assert p["regla"] == "Suela rosa idéntica." and p["precio"] == 89900 and p["moneda"] == "COP"
    assert p["url_compra"] == "https://tienda.co/rose" and "beneficios" not in p
    final_edition.preparar_guion("acme", entorno["cf_id"], {"precio": 99000})  # el escrito manda; no se le pone moneda
    p = entorno["generar"]["producto"]
    assert p["precio"] == 99000 and p["moneda"] is None


def test_producir_ok(entorno):
    import creative_flow as cf
    cf_id = entorno["cf_id"]
    etapas = []
    final_id, resumen = final_edition.producir(
        "acme", cf_id, "en", "US", {"precios": {"en_US": 19.9}, "voz": "Daniel"}, on_etapa=etapas.append)
    assert final_id == f"{cf_id}__en_US"
    assert etapas == [nombre for nombre, _ in final_edition.ETAPAS_FINAL]
    assert entorno["localizar"] == ("en", "US", 19.9)
    assert entorno["voz"] == {"voz": "Daniel", "cliente": "acme", "idioma": "en"}
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
    assert sorted(f["capas"]) == ["cortes", "guion", "musica", "render", "sonido", "texto", "voz"]
    # El clon de la fixture no trae pista: la capa sonido queda "ausente" (gratis, no degrada).
    assert all(c["estado"] == "ok" for n, c in f["capas"].items() if n != "sonido")
    assert f["capas"]["sonido"]["estado"] == "ausente" and f["capas"]["sonido"]["costo_usd"] == 0.0
    assert f["capas"]["render"]["parametros"]["con_sonido"] is False
    assert f["capas"]["render"]["parametros"]["mezcla"] == "equilibrada"
    assert f["costo_usd"] == pytest.approx(0.011 + 0.02 + 0.3)
    assert f["guion"]["idioma"] == "en" and f["error"] is None
    assert resumen["estado"] == "listo" and resumen["video_url"] == f["video_url"]
    # la final no aparece como sesión de Crear
    assert final_id not in cf.cargar("acme") and cf_id in cf.cargar("acme")
    assert os.path.exists(f["url_local"])


def test_producir_precio_base_solo_aplica_al_pais_base(entorno):
    """I1: `opciones["precio"]` (sin `precios`) solo se usa como precio para
    el destino cuyo país coincide con el país del guion base (es/CO en
    GUION_BASE); a un destino de otro país no le llega ese número sin
    convertir."""
    import creative_flow as cf
    cf_id = entorno["cf_id"]
    cf.guardar_guion_base("acme", cf_id, dict(GUION_BASE))  # pais base = CO
    final_edition.producir("acme", cf_id, "es", "CO", {"precio": 89900})
    assert entorno["localizar"] == ("es", "CO", 89900)
    final_edition.producir("acme", cf_id, "en", "US", {"precio": 89900})
    assert entorno["localizar"] == ("en", "US", None)  # NO se le aplica el precio del país base


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


def test_producir_error_si_falla_primer_bloque_de_voz_y_no_paga_musica(entorno, monkeypatch):
    """I3: una voz inválida (fal 422 en el primer bloque) es fatal —
    estado='error' en español, y música NUNCA se llega a generar/pagar."""
    import creative_flow as cf

    def falla(*a, **k):
        raise voz.ErrorPrimerBloque("Voice not found: NoExiste")
    monkeypatch.setattr(voz, "sintetizar", falla)

    def musica_no_debe_llamarse(*a, **k):
        raise AssertionError("música no debía generarse: la voz falló en el primer bloque")
    monkeypatch.setattr(musica, "obtener_pista", musica_no_debe_llamarse)

    with pytest.raises(ValueError, match="No se pudo generar la voz"):
        final_edition.producir("acme", entorno["cf_id"], "es", "CO", {"voz": "NoExiste"})

    f = cf.finales("acme", entorno["cf_id"])[0]
    assert f["estado"] == "error"
    assert "no se pudo generar la voz" in f["error"].lower()
    assert f["capas"]["voz"]["estado"] == "error"
    assert "musica" not in f["capas"]
    assert f["video_url"] is None
    assert "musica" not in entorno


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


def test_producir_usa_precio_base_guardado_al_preparar(entorno):
    """El precio escrito al preparar el guion viaja en `guion_base.precio_base`
    y aplica al país base cuando al producir no se escribe uno (el campo vacío
    no lo tapa); los demás países siguen sin precio."""
    import creative_flow as cf
    cf_id = entorno["cf_id"]
    g = dict(GUION_BASE)
    g["precio_base"] = 129900
    cf.guardar_guion_base("acme", cf_id, g)
    final_edition.producir("acme", cf_id, "es", "CO", {"precios": {}})
    assert entorno["localizar"] == ("es", "CO", 129900)
    final_edition.producir("acme", cf_id, "en", "US", {"precios": {}})
    assert entorno["localizar"] == ("en", "US", None)
    final_edition.producir("acme", cf_id, "es", "CO", {"precios": {"es_CO": 99900}})
    assert entorno["localizar"] == ("es", "CO", 99900)


def test_producir_conserva_el_sonido_del_clon_desde_el_crudo(entorno, clip_con_audio, monkeypatch):
    import creative_flow as cf
    cf.actualizar("acme", entorno["cf_id"], video_local_crudo=clip_con_audio, video_url_crudo="https://r2/crudo.mp4",
                  capas={"sonido": {"proveedor": "wan3", "estado": "ok"}})
    entorno["clon_con_audio"] = True
    final_id, resumen = final_edition.producir("acme", entorno["cf_id"], "es", "CO", {"mezcla": "voz_protagonista"})
    r = entorno["render"]
    assert r["clon"] == clip_con_audio and r["con_sonido"] is True
    assert r["volumenes"] == {"voz": 1.0, "sonido": 0.6, "musica": 0.25}
    assert resumen["capas"]["sonido"] == {"proveedor": "nativo", "parametros": {"sonido": "nativo", "mezcla": "voz_protagonista",
                                          "volumenes": {"voz": 1.0, "sonido": 0.6, "musica": 0.25}}, "costo_usd": 0.0,
                                          "estado": "ok", "error": None}
    assert resumen["capas"]["render"]["parametros"]["con_sonido"] is True


def test_producir_sin_sonido_o_clon_mudo(entorno):
    # el clon de la fixture no tiene pista: pedido pero ausente
    _, resumen = final_edition.producir("acme", entorno["cf_id"], "es", "CO")
    assert resumen["capas"]["sonido"]["estado"] == "ausente" and entorno["render"]["con_sonido"] is False
    assert resumen["estado"] == "listo"   # un clon mudo no degrada la pieza
    _, resumen2 = final_edition.producir("acme", entorno["cf_id"], "en", "US", {"con_sonido": False})
    assert resumen2["capas"]["sonido"]["estado"] == "omitida" and entorno["render"]["con_sonido"] is False
    _, resumen3 = final_edition.producir("acme", entorno["cf_id"], "pt", "BR", {"sonido": "ninguno"})
    assert resumen3["capas"]["sonido"]["estado"] == "omitida"


def test_producir_rechaza_preset_desconocido(entorno):
    with pytest.raises(ValueError):
        final_edition.producir("acme", entorno["cf_id"], "es", "CO", {"mezcla": "reguetón"})


# ---------- gasto real (guion:<cf_id> / final:<final_id>) ----------

def test_preparar_guion_registra_el_gasto(entorno):
    import gastos
    final_edition.preparar_guion("acme", entorno["cf_id"], {"precio": 89900})
    g = gastos.historial("acme")[0]
    assert g["referencia"] == f"guion:{entorno['cf_id']}" and g["tipo"] == "guion"
    assert g["usd"] == pytest.approx(0.011) and g["proveedor"] == "anthropic"
    assert g["extra"] == {"usd_guion": 0.01, "usd_whisper": 0.001}
    assert "transcripción" in g["detalle"]
    # volver a preparar (misma llamada directa, sin tarea): misma fila
    final_edition.preparar_guion("acme", entorno["cf_id"], {"precio": 89900})
    assert len(gastos.historial("acme")) == 1


def test_preparar_guion_de_dos_tareas_distintas_deja_dos_filas(entorno):
    """I2: `ref_sufijo` es el id de la tarea que paga — "Volver a escribir
    con IA" encola una tarea nueva (un cobro real nuevo) y no puede pisar el
    guion (y su gasto) de la escritura anterior."""
    import gastos
    cf_id = entorno["cf_id"]
    final_edition.preparar_guion("acme", cf_id, {"precio": 89900}, ref_sufijo=":t1")
    # reintento de la MISMA tarea: misma fila
    final_edition.preparar_guion("acme", cf_id, {"precio": 89900}, ref_sufijo=":t1")
    assert len(gastos.historial("acme")) == 1
    # tarea NUEVA: fila propia
    final_edition.preparar_guion("acme", cf_id, {"precio": 89900}, ref_sufijo=":t2")
    assert {f["referencia"] for f in gastos.historial("acme")} == {f"guion:{cf_id}:t1", f"guion:{cf_id}:t2"}


def test_producir_registra_el_gasto_de_la_final_sin_contar_el_guion_base_dos_veces(entorno):
    """El guion base preparado dentro de `producir` queda como
    `guion:<cf_id><ref_sufijo>`; la final registra solo sus capas (guion
    localizado + voz + música), con el desglose por capa en `extra`.
    `ref_sufijo` es el id de la tarea que paga (I1): reintentar LA MISMA
    tarea actualiza su fila, pero una tarea nueva del mismo destino
    (reproducir la final) deja la suya, sin pisar el cobro anterior."""
    import gastos
    cf_id = entorno["cf_id"]
    final_id, _ = final_edition.producir("acme", cf_id, "en", "US", {"precios": {"en_US": 19.9}}, ref_sufijo=":t1")
    filas = {f["referencia"]: f for f in gastos.historial("acme")}
    assert set(filas) == {f"guion:{cf_id}:t1", f"final:{final_id}:t1"}
    assert filas[f"guion:{cf_id}:t1"]["usd"] == pytest.approx(0.011)
    g = filas[f"final:{final_id}:t1"]
    assert g["tipo"] == "final" and g["usd"] == pytest.approx(0.02 + 0.3)
    assert g["extra"]["capas"]["guion"] == 0.02 and g["extra"]["capas"]["voz"] == 0.3
    assert g["extra"]["capas"]["musica"] == 0.0 and g["extra"]["fallo"] is False
    assert g["detalle"] == "en_US · guion, voz"
    assert gastos.resumen_mes("acme")["total"] == pytest.approx(0.011 + 0.02 + 0.3)

    # reintento de LA MISMA tarea (mismo ref_sufijo): misma fila, no duplica
    final_edition.producir("acme", cf_id, "en", "US", {"precios": {"en_US": 19.9}}, ref_sufijo=":t1")
    assert len(gastos.historial("acme")) == 2

    # una tarea NUEVA del MISMO destino (otro clic en "Producir" tras un
    # intento anterior, id distinto): deja su PROPIA fila de final — no pisa
    # el cobro del intento anterior (I1, antes se perdía).
    final_id_v2, _ = final_edition.producir("acme", cf_id, "en", "US", {"precios": {"en_US": 19.9}}, ref_sufijo=":t2")
    assert final_id_v2 == final_id  # mismo destino, mismo legado_id
    filas = {f["referencia"]: f for f in gastos.historial("acme")}
    assert set(filas) == {f"guion:{cf_id}:t1", f"final:{final_id}:t1", f"final:{final_id}:t2"}

    # otro destino: otra final, el guion base ya existía (no se vuelve a cobrar)
    final_es, _ = final_edition.producir("acme", cf_id, "es", "CO", ref_sufijo=":t3")
    assert {f["referencia"] for f in gastos.historial("acme")} == {
        f"guion:{cf_id}:t1", f"final:{final_id}:t1", f"final:{final_id}:t2", f"final:{final_es}:t3"}


def test_producir_registra_lo_cobrado_si_falla_el_render(entorno, monkeypatch):
    """Voz (y música) ya se pagaron cuando ffmpeg revienta: el gasto queda
    con el detalle de qué falló y qué se cobró."""
    import gastos

    def falla(*a, **k):
        raise RuntimeError("ffmpeg explotó")
    monkeypatch.setattr(render, "componer", falla)
    with pytest.raises(RuntimeError, match="ffmpeg explotó"):
        final_edition.producir("acme", entorno["cf_id"], "es", "CO")
    g = [f for f in gastos.historial("acme") if f["tipo"] == "final"][0]
    assert g["referencia"] == f"final:{entorno['cf_id']}__es_CO"
    assert g["usd"] == pytest.approx(0.02 + 0.3) and g["extra"]["fallo"] is True
    assert g["detalle"] == "es_CO · falló en render; guion y voz cobradas"


def test_producir_no_registra_gasto_si_falla_antes_de_cobrar(entorno, monkeypatch):
    import gastos
    monkeypatch.setattr(guion_mod, "localizar_guion", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("claude caído")))
    with pytest.raises(RuntimeError, match="claude caído"):
        final_edition.producir("acme", entorno["cf_id"], "es", "CO")
    assert [f["tipo"] for f in gastos.historial("acme")] == ["guion"]


def test_producir_con_cancion_propia_usa_su_tramo_sin_costo(entorno, monkeypatch, tmp_path):
    import creative_flow as cf
    vistos = []

    def fake_propia(cliente, valor, inicio_s=0, carpeta_cache=None):
        vistos.append((cliente, valor, inicio_s))
        return {"archivo": _wav(str(tmp_path / "propia.wav")), "url": "https://r2/clientes/acme/materiales/h.mp3",
                "estilo": "Jingle", "generada": False, "material_id": 3, "inicio_s": 12, "fuente": "elevenlabs"}, 0
    monkeypatch.setattr(musica, "pista_propia", fake_propia)
    final_edition.producir("acme", entorno["cf_id"], "es", "CO", {"estilo_musica": "mat:3", "musica_inicio_s": 12})
    assert vistos == [("acme", "mat:3", 12)]
    assert "musica" not in entorno                    # obtener_pista (fake_musica) no se llamó
    f = cf.finales("acme", entorno["cf_id"])[0]
    assert f["capas"]["musica"]["proveedor"] == "elevenlabs" and f["capas"]["musica"]["costo_usd"] == 0.0
    assert f["capas"]["musica"]["parametros"] == {"estilo": "Jingle", "url": "https://r2/clientes/acme/materiales/h.mp3",
                                                  "material_id": 3, "inicio_s": 12}
    assert entorno["render"]["musica"].endswith("propia.wav")

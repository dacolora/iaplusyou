"""Noruega (NO, noruego bokmål, NOK) y Suecia (SE, sueco, SEK): países, monedas y nombres de idioma.
Spec docs/superpowers/specs/2026-10-08-noruega-y-suecia-design.md §3 y §4."""
import pytest

import idiomas_publicacion
import lanzador
import presupuesto_experimentos
import proyectos
import triple_whale
from final_edition import tipos
from nicho import datos as nicho_datos


def test_paises_no_y_se_con_su_idioma_y_moneda():
    assert tipos.PAISES["NO"]["idioma"] == "no"
    assert tipos.PAISES["NO"]["moneda"] == "NOK"
    assert tipos.PAISES["NO"]["simbolo"] == "kr"
    assert tipos.PAISES["SE"]["idioma"] == "sv"
    assert tipos.PAISES["SE"]["moneda"] == "SEK"
    assert tipos.PAISES["SE"]["simbolo"] == "kr"
    assert tipos.PAISES["NO"]["bandera"] == "🇳🇴"
    assert tipos.PAISES["SE"]["bandera"] == "🇸🇪"


@pytest.mark.parametrize("valor,pais,esperado", [
    (299, "NO", "299 kr"),
    (1299, "SE", "1 299 kr"),
    (149.5, "NO", "149,50 kr"),
    (1299.5, "SE", "1 299,50 kr"),
    (299, "SE", "299 kr"),
    (1299, "NO", "1 299 kr"),
])
def test_formatear_precio_en_coronas(valor, pais, esperado):
    assert tipos.formatear_precio(valor, pais) == esperado


def test_formatear_precio_de_los_demas_paises_no_cambia():
    assert tipos.formatear_precio(89900, "CO") == "$ 89.900"
    assert tipos.formatear_precio(89.9, "US") == "$89.90"
    assert tipos.formatear_precio(89.9, "ES") == "89,90 €"
    assert tipos.formatear_precio(89.9, "BR") == "R$ 89,90"


def test_presupuesto_minimo_diario_y_tope_de_campana_en_coronas():
    assert presupuesto_experimentos.PRESUPUESTO_MINIMO_DIARIO["NOK"] == 10
    assert presupuesto_experimentos.PRESUPUESTO_MINIMO_DIARIO["SEK"] == 10
    assert lanzador.minimo_tope_campana("NOK") == 1000.0
    assert lanzador.minimo_tope_campana("SEK") == 1000.0


def test_triple_whale_acepta_coronas():
    assert "NOK" in triple_whale.MONEDAS
    assert "SEK" in triple_whale.MONEDAS


def test_calendario_sale_de_los_paises_de_final_edition(tmp_path, monkeypatch):
    assert proyectos.PAISES_CALENDARIO == tuple(tipos.PAISES)
    monkeypatch.setattr(proyectos, "_path", lambda c: str(tmp_path / f"{c}.json"))
    for pais in ("NO", "SE"):
        proyectos.guardar_pais("acme", pais)
        assert proyectos.pais("acme") == pais
    with pytest.raises(ValueError):
        proyectos.guardar_pais("acme", "XX")


def test_nicho_acepta_noruega_y_suecia():
    assert "NO" in nicho_datos.PAISES_ESTUDIO
    assert "SE" in nicho_datos.PAISES_ESTUDIO
    assert nicho_datos.NOMBRES_PAIS["NO"] == "Noruega"
    assert nicho_datos.NOMBRES_PAIS["SE"] == "Suecia"


def test_idiomas_de_publicacion_tienen_nombre_propio():
    assert idiomas_publicacion.nombre("no") == "noruego (bokmål)"
    assert idiomas_publicacion.nombre("sv") == "sueco"
    assert idiomas_publicacion.nombre("es") == "español"
    assert idiomas_publicacion.nombre("no", en_ingles=True) == "Norwegian (Bokmål)"
    assert idiomas_publicacion.nombre("sv", en_ingles=True) == "Swedish"
    assert idiomas_publicacion.NOMBRES["pt"] == "portugués"
    assert idiomas_publicacion.NOMBRES_EN["en"] == "English"


def test_idioma_desconocido_devuelve_el_codigo():
    assert idiomas_publicacion.nombre("xx") == "xx"
    assert idiomas_publicacion.nombre("xx", en_ingles=True) == "xx"


# --- Task 2: finales en noruego y sueco (spec §4 y §7) ---------------------------------

GUION_NO = {
    "idioma": "no", "pais": "NO", "moneda": None, "precio_texto": None,
    "bloques": [
        {"rol": "hook", "texto_pantalla": "Hei", "texto_voz": "Hei alle sammen", "inicio_s": 0, "fin_s": 1.5},
        {"rol": "problema", "texto_pantalla": "Vondt", "texto_voz": "Føttene gjør vondt", "inicio_s": 1.5, "fin_s": 3},
        {"rol": "producto", "texto_pantalla": "Tøfler", "texto_voz": "Disse tøflene", "inicio_s": 3, "fin_s": 5},
        {"rol": "prueba", "texto_pantalla": "Tusenvis", "texto_voz": "Tusenvis bruker dem", "inicio_s": 5, "fin_s": 6.5},
        {"rol": "cta", "texto_pantalla": "Kjøp nå", "texto_voz": "Kjøp dine i dag", "inicio_s": 6.5, "fin_s": 8},
    ],
}


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"
        s["rol"] = "admin"
        s["cliente"] = None
    return c


def _sesion_video_listo(cliente="acme"):
    import creative_flow as cf
    cf_id = cf.crear(cliente, [], ["Chancla Rose"], [], "la persona camina", 8, "", "A")
    cf.actualizar(cliente, cf_id, estado="video_listo", video_url="https://r2/clon.mp4", enfoque="producto")
    return cf_id


def _capturar_encolar(monkeypatch, dashboard):
    llamadas = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: llamadas.append(dict(job_id=job_id, payload=payload)) or True)
    return llamadas


def test_destinos_de_final_edition_aceptan_noruega_y_suecia():
    import dashboard
    assert "no" in dashboard.IDIOMAS_FE and "sv" in dashboard.IDIOMAS_FE
    assert dashboard._destinos_form(["no_NO", "sv_SE"]) == [("no", "NO"), ("sv", "SE")]
    assert dashboard._destinos_form(["sv_NO"]) == [("sv", "NO")]      # idioma y país válidos, combinación libre
    assert dashboard._destinos_form(["xx_NO"]) is None
    assert dashboard._destinos_form(["no_XX"]) is None


def test_producir_encola_las_finales_de_noruega_y_suecia_con_voz_noruega(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    from providers import fal_audio
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_NO)
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    r = _cliente_admin(dashboard).post(f"/cliente/acme/creative_flow/{cf_id}/final/producir", data={
        "destinos": ["no_NO", "sv_SE"], "voz": "NoExiste", "estilo_musica": "energetico",
        "precio_no_NO": "299", "precio_sv_SE": "1299",
    })
    assert r.status_code == 302
    assert [(t["payload"]["idioma"], t["payload"]["pais"]) for t in llamadas] == [("no", "NO"), ("sv", "SE")]
    o = llamadas[0]["payload"]["opciones"]
    assert o["idioma_base"] == "no"                       # el guion base en noruego no cae al español
    assert o["voz"] == fal_audio.VOCES["no"][0]
    assert o["precios"] == {"no_NO": 299.0, "sv_SE": 1299.0}


@pytest.mark.parametrize("idioma", ["no", "sv"])
def test_preparar_acepta_guion_base_en_noruego_o_sueco(base_temporal, monkeypatch, idioma):
    import dashboard
    cf_id = _sesion_video_listo()
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    _cliente_admin(dashboard).post(f"/cliente/acme/creative_flow/{cf_id}/final/preparar", data={"idioma_base": idioma})
    assert llamadas[0]["payload"]["opciones"]["idioma_base"] == idioma


def test_prompts_de_localizacion_llevan_el_nombre_del_idioma():
    """Con el código solo, 'no' se lee como la palabra «no» (spec §4)."""
    from final_edition import guion
    s_no = guion._system_localizar("no", "NO")
    assert "noruego (bokmål)" in s_no and "NOK" in s_no and "'no'" in s_no
    s_sv = guion._system_localizar("sv", "SE", precio_texto="1 299 kr")
    assert "sueco" in s_sv and "SEK" in s_sv
    m = guion._mensaje_localizar(GUION_NO, "sv", "SE", "SEK", "1 299 kr")
    assert "sueco" in m and "SEK" in m and "1 299 kr" in m
    assert "noruego (bokmål)" in guion._mensaje_localizar(GUION_NO, "no", "NO", "NOK", None)
    assert "noruego (bokmål)" in guion._reglas_generar(8, "no")       # guion base y variantes en noruego
    # Los demás idiomas siguen con su código y ganan su nombre.
    assert "español ('es')" in guion._system_localizar("es", "CO")


def test_guion_base_en_noruego_cae_en_noruega():
    from final_edition import guion
    assert guion._pais_por_idioma("no") == "NO"
    assert guion._pais_por_idioma("sv") == "SE"


def test_voces_de_las_finales_en_noruego_y_sueco():
    from providers import fal_audio
    assert fal_audio.VOCES["no"] == fal_audio.VOCES["pt"]
    assert fal_audio.VOCES["sv"] == fal_audio.VOCES["pt"]


def _fal_falso(monkeypatch):
    from providers import fal_client
    llamadas = []

    def llamar(modelo, payload, timeout=None, on_progreso=None):
        llamadas.append((modelo, dict(payload)))
        if "whisper" in modelo:
            return {"text": "hei", "chunks": [{"timestamp": [0.0, 0.4], "text": "hei"}]}
        return {"audio": {"url": "https://fal/voz.mp3"}}
    monkeypatch.setattr(fal_client, "llamar", llamar)
    return llamadas


def test_voz_de_galeria_en_noruego_pide_turbo_con_language_code(monkeypatch):
    from providers import fal_audio
    llamadas = _fal_falso(monkeypatch)
    r = fal_audio.tts_galeria("Kjøp nå", "Rachel", "no")
    assert r["url"] == "https://fal/voz.mp3"
    modelo, payload = llamadas[0]
    assert modelo == fal_audio.MODELO_TTS_TURBO and payload["language_code"] == "no"
    fal_audio.tts_galeria("Köp nu", "Rachel", "sv")               # el sueco lo habla Multilingual v2
    modelo, payload = llamadas[1]
    assert modelo == fal_audio.MODELO_TTS and "language_code" not in payload


def test_whisper_recibe_sv_y_no_tal_cual(monkeypatch):
    from providers import fal_audio
    llamadas = _fal_falso(monkeypatch)
    fal_audio.transcribir_palabras("https://r2/a.mp3", "no")
    fal_audio.transcribir_palabras("https://r2/a.mp3", "sv")
    assert [p["language"] for _m, p in llamadas] == ["no", "sv"]


@pytest.fixture()
def voz_final_falsa(base_temporal, tmp_path, monkeypatch):
    """Lo que usa la voz de las finales (insumos.voz_bloque) con fal, R2 y ffmpeg falsos."""
    import final_edition
    from final_edition import cortes, insumos
    from providers import fal_audio
    from storage import r2_uploader
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(r2_uploader, "upload_file", lambda p, k, ct: f"https://r2/{k}")
    llamadas = []
    monkeypatch.setattr(fal_audio, "tts", lambda texto, voz="Rachel", idioma="es", **kw:
                        llamadas.append((idioma, kw)) or {"url": "https://fal/x.mp3", "costo_usd": 0.01})
    monkeypatch.setattr(fal_audio, "transcribir_palabras", lambda url, idioma, on_progreso=None:
                        {"texto": "", "costo_usd": 0.0, "palabras": []})
    monkeypatch.setattr(insumos, "_descargar", lambda url, destino: (open(destino, "wb").write(b"mp3"), destino)[1])
    monkeypatch.setattr(cortes, "duracion", lambda path: 1.0)
    return insumos, llamadas, str(tmp_path / "w")


def test_la_voz_de_las_finales_en_noruego_va_por_turbo(voz_final_falsa):
    from providers import fal_audio
    insumos, llamadas, carpeta = voz_final_falsa
    insumos.voz_bloque("acme", "Kjøp dine i dag", "Rachel", "no", 1500, carpeta)
    insumos.voz_bloque("acme", "Köp dina i dag", "Rachel", "sv", 1500, carpeta)
    insumos.voz_bloque("acme", "Pide las tuyas", "Rachel", "es", 1500, carpeta)
    assert llamadas[0] == ("no", {"modelo": fal_audio.MODELO_TTS_TURBO, "language_code": "no"})
    assert llamadas[1] == ("sv", {}) and llamadas[2] == ("es", {})


def test_la_voz_del_camino_legado_en_noruego_tambien_va_por_turbo(monkeypatch):
    from final_edition import voz
    from providers import fal_audio
    llamadas = []
    monkeypatch.setattr(fal_audio, "tts", lambda texto, voz="Rachel", idioma="es", **kw:
                        llamadas.append((idioma, kw)) or {"url": "https://fal/x.mp3", "costo_usd": 0.01})
    voz._tts("Kjøp nå", "Rachel", "no", "acme")
    assert llamadas == [("no", {"modelo": fal_audio.MODELO_TTS_TURBO, "language_code": "no"})]


@pytest.mark.parametrize("texto", ["Kjøp nå – spar 20 %", "Köp nu – Åre", "Æ Ø Å æ ø å Ä Ö ä ö"])
def test_tipografia_v1_no_quita_las_letras_nordicas(texto):
    from final_edition import fuentes, tipografia
    tabla = {**fuentes.cargar_tabla(), "emoji": None}
    for fuente in tabla["fuentes"]:
        assert tipografia.sin_glifos_v1(texto, fuente, tabla) == texto, fuente


def test_organico_tiene_su_copy_en_noruego_y_sueco():
    import organico
    assert organico._copy("no")["link_bio"] == "Lenke i bio."
    assert organico._copy("sv")["link_bio"] == "Länk i bion."
    for idioma in ("no", "sv"):
        copy = organico._copy(idioma)
        assert set(copy) == {"link_bio", "cta", "escribenos"} and copy != organico._copy("es")
    fb = organico.fallback({"nombre_producto": "Tøfler", "idioma": "no", "url_compra": "https://x.no/p"}, "facebook")
    assert organico._copy("no")["cta"] in fb["caption"]


def test_caption_organico_en_noruego_pide_lenke_i_bio_y_nombra_el_idioma(monkeypatch):
    import generador_prompts as gp
    assert gp.LINK_EN_BIO["no"] == "Lenke i bio" and gp.LINK_EN_BIO["sv"] == "Länk i bion"
    capturado = {}

    class _Resp:
        content = [type("B", (), {"type": "text", "text": '{"instagram": {"titulo": "T", "caption": "C"}}'})()]
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 5})()
        stop_reason = "end_turn"

    class _Cliente:
        def __init__(self, api_key=None):
            pass

        class messages:
            @staticmethod
            def create(**kw):
                capturado.update(kw)
                return _Resp()
    monkeypatch.setattr(gp.anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr(gp, "_api_key", lambda: "sk-test")
    gp.caption_organico({"nombre_producto": "Tøfler", "idioma": "no"}, ["instagram"])
    system = capturado["system"] if isinstance(capturado["system"], str) else "\n".join(b["text"] for b in capturado["system"])
    assert "Lenke i bio" in system
    assert "noruego (bokmål)" in capturado["messages"][0]["content"]


def test_pantalla_de_destinos_ofrece_noruega_y_suecia(base_temporal, monkeypatch):
    """Lo que ve la persona en «Producir finales» (fe_detalle_video, por el test client)."""
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_NO)
    html = _cliente_admin(dashboard).get(f"/cliente/acme/creative_flow/{cf_id}/final/detalle").get_data(as_text=True)
    assert 'name="destinos" value="no_NO"' in html and 'name="destinos" value="sv_SE"' in html
    assert 'name="precio_no_NO"' in html and 'data-moneda="NOK"' in html and 'data-moneda="SEK"' in html
    assert "Noruega" in html and "Suecia" in html
    # «Volver a escribir con IA» conserva el guion base en noruego.
    assert 'name="idioma_base" value="no"' in html


def test_selector_de_idioma_base_ofrece_noruego_y_sueco(base_temporal):
    import dashboard
    cf_id = _sesion_video_listo()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/creative_flow/{cf_id}/final/detalle").get_data(as_text=True)
    assert '<option value="sv">Svenska</option>' in html and '<option value="no">Norsk (bokmål)</option>' in html

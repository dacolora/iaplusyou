"""Producción por la vía del editor (`final_edition/produccion.py`) con los
insumos, Claude y el render falsos: cableado, reutilización por receta,
traducción por destino, degradación, estados y gasto."""
import copy

import pytest

import final_edition
from final_edition import borrador, documento as d
from tests.test_fe_producir import GUION_BASE

NOMBRES = [n for n, _ in final_edition.ETAPAS_FINAL]


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import creative_flow as cf
    import materiales
    import tareas.edicion as te
    from final_edition import guion as guion_mod, insumos
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "salidas"))
    clip = str(tmp_path / "clon.mp4")
    open(clip, "wb").write(b"video")
    cf_id = cf.crear("acme", [], ["Chancla Rose"], [], "la persona camina con las chanclas", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", video_local=clip,
                  enfoque="producto", aspect_ratio="9:16")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda cliente, pid, categoria=None: None)
    monkeypatch.setattr(catalogo_productos, "listar", lambda cliente, categoria="producto": [
        {"id": "chancla_rose", "nombre": "Chancla Rose", "descripcion": "Chancla cómoda", "tipo": "calzado"}])
    ll = {"cf_id": cf_id, "generar": 0, "localizar": [], "variar": 0, "voz": [], "musica": [], "clon": 0, "render": [],
          "fallar_voz_en": None}

    def fake_generar(producto, referencia, enfoque, duracion_s, idioma_base, marca, cliente_hint):
        ll["generar"] += 1
        return copy.deepcopy(GUION_BASE), 0.01
    monkeypatch.setattr(guion_mod, "generar_guion_base", fake_generar)

    def fake_localizar(guion_base, idioma, pais, precio):
        ll["localizar"].append((idioma, pais, precio))
        g = copy.deepcopy(guion_base)
        if idioma == guion_base.get("idioma") and pais == guion_base.get("pais"):
            return g, 0.0
        g["idioma"], g["pais"] = idioma, pais
        for bl in g["bloques"]:
            bl["texto_pantalla"] += f" {idioma}"
            bl["texto_voz"] += f" {idioma}"
        return g, 0.02
    monkeypatch.setattr(guion_mod, "localizar_guion", fake_localizar)

    def fake_variar(guion_base, tipo, marca):
        ll["variar"] += 1
        g = copy.deepcopy(guion_base)
        g["bloques"][0]["texto_pantalla"], g["bloques"][0]["texto_voz"] = "HOOK2", "Hook dos"
        return g, 0.02
    monkeypatch.setattr(guion_mod, "variar_guion", fake_variar)

    def fake_clon(cliente, cf_id_, entry, ruta_local):
        ll["clon"] += 1
        return materiales.obtener_o_crear(cliente, "hclon", lambda: {
            "tipo": "video", "origen": "crear", "url": "https://r2/clon.mp4", "bytes": 5, "duracion_ms": 8000,
            "ancho": 540, "alto": 960, "extra": {"local": ruta_local, "tiene_audio": True, "cortes_ms": []}})
    monkeypatch.setattr(insumos, "clon", fake_clon)

    def fake_voz(cliente, texto, voz, idioma, ventana_ms, carpeta):
        ll["voz"].append((texto, voz, idioma, ventana_ms))
        if ll["fallar_voz_en"] is not None and len(ll["voz"]) == ll["fallar_voz_en"]:
            raise RuntimeError("fal caído")
        h = materiales.hash_clave("voz", texto, voz, idioma)
        mat, creado = materiales.obtener_o_crear(cliente, h, lambda: {
            "tipo": "audio", "origen": "voz", "url": f"https://r2/{h[:8]}.mp3", "bytes": 1, "duracion_ms": 1200, "costo_usd": 0.05,
            "extra": {"palabras": [{"t_ms": 100, "dur_ms": 300, "texto": texto.split()[0]}]}})
        return mat, (0.05 if creado else 0.0)
    monkeypatch.setattr(insumos, "voz_bloque", fake_voz)

    def fake_musica(cliente, estilo, segundos):
        ll["musica"].append((estilo, segundos))
        mat, creado = materiales.obtener_o_crear(cliente, f"hm_{estilo}", lambda: {
            "tipo": "audio", "origen": "musica", "url": f"https://r2/musica/{estilo}_15.wav", "bytes": 1, "duracion_ms": 15000,
            "costo_usd": 0.02, "extra": {"estilo": estilo}})
        return mat, (0.02 if creado else 0.0)
    monkeypatch.setattr(insumos, "musica", fake_musica)
    monkeypatch.setattr(insumos, "logo", lambda cliente: None)

    def fake_render(cliente, final_id, version_id, idioma, pais, avisar=None):
        ll["render"].append((final_id, version_id, idioma, pais))
        if avisar:
            avisar("Renderizando")
        return {"url_video": f"https://r2/finales/{final_id}__v{version_id}.mp4", "duracion_s": 8.0, "tramos": 1,
                "url_miniatura": f"https://r2/finales/{final_id}__v{version_id}.png", "con_ass": True,
                "version_id": version_id, "es_imagen": False}
    monkeypatch.setattr(te, "renderizar_final", fake_render)
    return ll


def _opciones(**cambios):
    o = dict(final_edition._OPCIONES_DEFECTO)
    o.update({"voz": "Rachel", "estilo_musica": "energetico"})
    o.update(cambios)
    return o


def _entry(entorno):
    import creative_flow as cf
    return cf.cargar("acme")[entorno["cf_id"]]


def test_asegurar_borrador_crea_la_edicion_y_la_reutiliza_por_receta(entorno):
    import ediciones
    from final_edition import produccion
    cf_id, entry = entorno["cf_id"], _entry(entorno)
    etapas = []
    ed, capas, costo, creada = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(), etapas.append)
    assert creada and costo == pytest.approx(5 * 0.05 + 0.02) and etapas == ["Cortes", "Voz", "Música"]
    assert ed["cf_id"] == cf_id and ed["nombre"].startswith("Borrador · la persona camina")
    doc = ed["documento"]
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_texto", "p_voz", "p_musica", "p_sonido"]
    assert doc["origen"]["receta"] == borrador.receta(GUION_BASE, _opciones(), "9:16") and doc["origen"]["degradada"] is False
    assert set(capas) == {"cortes", "sonido", "voz", "musica", "texto"}
    assert capas["voz"]["parametros"] == {"voz": "Rachel"} and capas["voz"]["costo_usd"] == pytest.approx(0.25)
    assert capas["musica"]["parametros"]["estilo"] == "energetico" and capas["musica"]["costo_usd"] == 0.02
    assert capas["sonido"]["estado"] == "ok" and capas["cortes"]["parametros"]["segmentos"] >= 1
    assert [v[3] for v in entorno["voz"]] == [1500, 1500, 2000, 1500, 1500]      # la ventana de cada bloque
    assert entorno["musica"] == [("energetico", 8.0)]
    ed2, capas2, costo2, creada2 = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(), etapas.append)
    assert not creada2 and ed2["id"] == ed["id"] and costo2 == 0.0 and len(entorno["voz"]) == 5 and len(etapas) == 3
    assert capas2["voz"]["costo_usd"] == 0.0 and capas2["voz"]["parametros"] == {"voz": "Rachel"}
    ed3, _, _, creada3 = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(voz="Adam"), etapas.append)
    assert creada3 and ed3["id"] != ed["id"] and len(ediciones.listar("acme", cf_id=cf_id)) == 2


def test_asegurar_borrador_sin_voz_ni_musica_ni_sonido_por_opciones(entorno):
    from final_edition import produccion
    ed, capas, costo, _ = produccion.asegurar_borrador(
        "acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE,
        _opciones(con_voz=False, con_musica=False, con_sonido=False), lambda n: None)
    assert costo == 0 and entorno["voz"] == [] and entorno["musica"] == []
    assert [p["id"] for p in ed["documento"]["pistas"]] == ["p_video", "p_texto"]
    assert capas["voz"]["estado"] == "omitida" and capas["musica"]["estado"] == "omitida" and capas["sonido"]["estado"] == "omitida"


def test_primer_bloque_de_voz_fatal_no_paga_musica_ni_crea_edicion(entorno):
    import ediciones
    from final_edition import produccion
    entorno["fallar_voz_en"] = 1
    with pytest.raises(ValueError, match="No se pudo generar la voz"):
        produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert entorno["musica"] == [] and ediciones.listar("acme", cf_id=entorno["cf_id"]) == []


def test_voz_incompleta_degrada_y_ese_borrador_no_se_reutiliza(entorno):
    from final_edition import produccion
    cf_id, entry = entorno["cf_id"], _entry(entorno)
    entorno["fallar_voz_en"] = 3
    ed, capas, costo, _ = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert capas["voz"]["estado"] == "error" and "fal caído" in capas["voz"]["error"] and capas["musica"]["estado"] == "ok"
    assert "p_voz" not in {p["id"] for p in ed["documento"]["pistas"]} and ed["documento"]["origen"]["degradada"] is True
    assert costo == pytest.approx(2 * 0.05 + 0.02)               # lo pagado antes del fallo cuenta
    entorno["fallar_voz_en"] = None
    ed2, capas2, costo2, creada2 = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert creada2 and ed2["id"] != ed["id"] and capas2["voz"]["estado"] == "ok"
    assert costo2 == pytest.approx(3 * 0.05)                     # los dos bloques ya pagados vienen de la caché


def test_traducir_agrega_el_destino_una_vez_y_fija_el_precio(entorno):
    from final_edition import produccion
    ed, *_ = produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    ed2, capas, costo = produccion.traducir("acme", ed, "en", "US", 24.99, "Rachel", True)
    assert costo == pytest.approx(0.02 + 5 * 0.05) and capas["guion"]["costo_usd"] == 0.02 and capas["voz"]["costo_usd"] == 0.25
    assert entorno["localizar"] == [("en", "US", 24.99)] and ed2["version_n"] == ed["version_n"] + 1
    assert [v[2] for v in entorno["voz"][5:]] == ["en"] * 5
    doc = ed2["documento"]
    assert borrador.tiene_destino(doc, "en", "US") and doc["variables"]["precios"] == {"en_US": 24.99}
    assert doc["variables"]["textos"]["hook"]["en_US"] == "Hola en" and doc["subtitulos"]["palabras"]["en_US"][0]["texto"] == "Hola"
    ed3, capas3, costo3 = produccion.traducir("acme", ed2, "en", "US", None, "Rachel", True)
    assert costo3 == 0.0 and "voz" not in capas3 and len(entorno["localizar"]) == 1
    assert ed3["documento"]["variables"]["precios"] == {}
    ed4, capas4, costo4 = produccion.traducir("acme", ed3, "es", "CO", 89900, "Rachel", True)   # destino base: solo el precio
    assert costo4 == 0.0 and len(entorno["localizar"]) == 1 and ed4["documento"]["variables"]["precios"] == {"es_CO": 89900.0}
    assert d.resolver(ed4["documento"], "es", "CO")["pistas"][1]["clips"][1]["texto"] == {"literal": "$ 89.900"}


def test_traducir_voz_fatal_lleva_lo_pagado_en_la_excepcion(entorno):
    import ediciones
    from final_edition import produccion
    ed, *_ = produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    entorno["fallar_voz_en"] = len(entorno["voz"]) + 1
    with pytest.raises(produccion.VozFatal) as exc:
        produccion.traducir("acme", ed, "en", "US", None, "Rachel", True)
    assert exc.value.costo == pytest.approx(0.02)
    assert exc.value.capas["guion"]["costo_usd"] == 0.02
    assert exc.value.capas["voz"]["estado"] == "error"
    assert "No se pudo generar la voz" in str(exc.value)
    assert ediciones.cargar("acme", ed["id"])["version_n"] == ed["version_n"]


def test_asegurar_borrador_voz_fatal_lleva_las_capas(entorno):
    from final_edition import produccion
    entorno["fallar_voz_en"] = 1
    with pytest.raises(produccion.VozFatal) as exc:
        produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert exc.value.costo == 0.0
    assert set(exc.value.capas) == {"cortes", "sonido", "voz"}
    assert exc.value.capas["voz"]["estado"] == "error"


def test_traducir_voz_incompleta_degrada_el_destino_y_la_retraduccion_no_paga_claude(entorno):
    from final_edition import produccion
    ed, *_ = produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    entorno["fallar_voz_en"] = len(entorno["voz"]) + 3
    ed2, capas, costo = produccion.traducir("acme", ed, "en", "US", 24.99, "Rachel", True)
    assert capas["voz"]["estado"] == "error"
    assert costo == pytest.approx(0.02 + 2 * 0.05)
    assert ed2["documento"]["variables"]["textos"]["hook"]["en_US"] == "Hola en"
    assert borrador.tiene_textos(ed2["documento"], "en", "US") is True
    assert borrador.tiene_destino(ed2["documento"], "en", "US") is False
    entorno["fallar_voz_en"] = None
    ed3, capas3, costo3 = produccion.traducir("acme", ed2, "en", "US", 24.99, "Rachel", True)
    assert len(entorno["localizar"]) == 1                        # Claude no se vuelve a llamar
    assert costo3 == pytest.approx(3 * 0.05)                     # los dos bloques ya pagados vienen de la caché
    assert borrador.tiene_destino(ed3["documento"], "en", "US") is True
    assert "voz" in capas3 and capas3["voz"]["estado"] == "ok"


def test_musica_que_falla_degrada_el_borrador(entorno, monkeypatch):
    from final_edition import insumos, produccion

    def fallar(*a, **k):
        raise RuntimeError("stable audio caído")
    monkeypatch.setattr(insumos, "musica", fallar)
    ed, capas, costo, creada = produccion.asegurar_borrador(
        "acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert capas["musica"]["estado"] == "error" and "stable audio" in capas["musica"]["error"]
    assert "p_musica" not in {p["id"] for p in ed["documento"]["pistas"]}
    assert ed["documento"]["origen"]["degradada"] is True
    ed2, capas2, costo2, creada2 = produccion.asegurar_borrador(
        "acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert creada2 and ed2["id"] != ed["id"]

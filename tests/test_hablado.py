"""Anuncio hablado (spec 2026-10-01 §1, §3, §4): la voz con las reglas de
Audios y el precio de su video, las fotos del proyecto por ficha (nunca una
URL) y la sesión de Crear que se lanza. Sin red: R2 y el catálogo son falsos."""
import pytest

import audios
import creative_flow
import hablado
import materiales


@pytest.fixture()
def entorno(base_temporal, monkeypatch):
    import catalogo_productos
    personajes = [{"id": "ana", "nombre": "Ana", "referencias": ["/catalogo/ana/frente.jpg"]}]
    monkeypatch.setattr(catalogo_productos, "listar",
                        lambda c, cat="producto": personajes if (c == "acme" and cat == "personaje") else [])
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda c, pid, categoria=None: next((p for p in personajes if p["id"] == pid), None)
                        if (c == "acme" and categoria == "personaje") else None)
    subidas = []
    monkeypatch.setattr(hablado.r2_uploader, "upload_image", lambda local, key: subidas.append(key) or f"https://r2/{key}")
    return {"subidas": subidas}


def _imagen_crear(cliente="acme", estado="video_listo", tipo="imagen"):
    cid = creative_flow.crear(cliente, [], [], [], "mujer sonriendo con la chancla", 0, "", "A", referencias_urls=[])
    creative_flow.actualizar(cliente, cid, tipo=tipo, estado=estado, modelo="seedream_v5_pro",
                             video_url=f"https://r2/clientes/{cliente}/flowplus/{cid}.png")
    return cid


def _foto_subida(cliente="acme", n=1):
    return materiales.registrar(cliente, tipo="imagen", origen="subida",
                                url=f"https://r2/clientes/{cliente}/materiales/f{n}.jpg",
                                hash=materiales.hash_clave("foto", cliente, n), bytes=10, ancho=704, alto=1280,
                                extra={"nombre": f"foto {n}"})


def _voz(cliente="acme", texto="Estas chanclas son una nube.", voz="Rachel", idioma="es", velocidad="normal", ms=7050):
    h = audios.hash_voz(texto, voz, idioma, velocidad)
    return materiales.registrar(cliente, tipo="audio", origen="voz",
                                url=f"https://r2/clientes/{cliente}/materiales/voz_{h[:16]}.mp3",
                                hash=h, bytes=10, duracion_ms=ms, costo_usd=0.0028,
                                extra={"texto": texto, "voz": voz, "voz_ref": voz, "idioma": idioma,
                                       "velocidad": velocidad})


def test_validar_voz_con_las_reglas_de_audios_y_el_tope_del_guion(entorno):
    assert hablado.validar_voz("acme", {"texto": "  Hola   mundo ", "voz": "Rachel", "idioma": "es",
                                        "velocidad": "rapida"}) == \
        {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "rapida"}
    assert hablado.validar_voz("acme", {"texto": "x" * 500, "voz": "Rachel", "idioma": "es"})["velocidad"] == "normal"
    casos = (({"texto": " ", "voz": "Rachel", "idioma": "es"}, "Escribe el texto que quieres que lea la voz."),
             ({"texto": "x" * 501, "voz": "Rachel", "idioma": "es"}, "El guion pasa de 500 caracteres."),
             ({"texto": "Hola", "voz": "Nadie", "idioma": "es"}, "Elige una voz de la lista."),
             ({"texto": "Hola", "voz": "Rachel", "idioma": "xx"}, "Elige un idioma de la lista."),
             ({"texto": "Hola", "voz": "Rachel", "idioma": "es", "velocidad": "turbo"}, "Elige una velocidad de la lista."))
    for form, texto in casos:
        with pytest.raises(hablado.EntradaInvalida) as e:
            hablado.validar_voz("acme", form)
        assert e.value.texto() == texto


def test_voz_existente_solo_voces_de_este_proyecto(entorno):
    v = _voz()
    assert hablado.voz_existente("acme", v["hash"])["id"] == v["id"]
    assert hablado.voz_existente("otro", v["hash"]) is None
    assert hablado.voz_existente("acme", "nada") is None and hablado.voz_existente("acme", None) is None
    locucion = materiales.registrar("acme", tipo="audio", origen="locucion", url="https://r2/l.mp3", hash="a" * 64,
                                    bytes=1, duracion_ms=4000)
    assert hablado.voz_existente("acme", locucion["hash"]) is None      # un audio final de Audios no es una voz


def test_voz_info_trae_el_precio_del_video_redondeado_al_segundo(entorno):
    corta = _voz()
    assert hablado.voz_info(corta) == {"material_id": corta["id"], "url": corta["url"], "duracion_s": 7.05,
                                       "hash": corta["hash"], "precio_video": 0.2, "aviso": None}
    assert hablado.voz_info(_voz(texto="otra", ms=10760))["precio_video"] == 0.275
    tope = hablado.voz_info(_voz(texto="justo", ms=30000))
    assert tope["precio_video"] == 0.75 and tope["aviso"] is None
    larga = hablado.voz_info(_voz(texto="larga", ms=31000))
    assert larga["precio_video"] is None
    assert larga["aviso"].startswith("Esta voz dura 31 s; el anuncio hablado llega a 30 s.")


def test_fotos_lista_imagenes_de_crear_personajes_y_subidas_de_este_proyecto(entorno):
    cid = _imagen_crear()
    _imagen_crear(estado="error")              # sin imagen lista: no entra
    _imagen_crear(tipo="video")                # un video no es una foto
    _imagen_crear(cliente="otro")              # de otro proyecto: no entra
    m = _foto_subida()
    _foto_subida(cliente="otro", n=2)
    lista = hablado.fotos("acme")
    assert [f["ficha"] for f in lista] == [f"cf:{cid}", "cat:ana", f"mat:{m['id']}"]
    assert [f["origen"] for f in lista] == ["crear", "catalogo", "subida"]
    assert lista[0]["miniatura"] == f"https://r2/clientes/acme/flowplus/{cid}.png" and lista[1]["miniatura"] is None
    assert lista[1]["activo_id"] == "ana" and lista[2]["nombre"] == "foto 1" and lista[2]["origen_nombre"] == "Subida"


def test_resolver_foto_solo_acepta_fichas_de_este_proyecto(entorno):
    cid, m = _imagen_crear(), _foto_subida()
    assert hablado.resolver_foto("acme", f"cf:{cid}") == f"https://r2/clientes/acme/flowplus/{cid}.png"
    assert hablado.resolver_foto("acme", f"mat:{m['id']}") == m["url"]
    assert hablado.resolver_foto("acme", "cat:ana") == "https://r2/clientes/acme/personajes_catalogo/ana/frente.jpg"
    assert entorno["subidas"] == ["clientes/acme/personajes_catalogo/ana/frente.jpg"]
    ajena = _foto_subida(cliente="otro", n=2)
    fichas = (f"cf:{_imagen_crear(cliente='otro')}", f"mat:{ajena['id']}", "cat:nadie", "https://otro.sitio/cara.jpg",
              "mat:abc", "mat:99999999999999999999999", "", None, f"cf:{_imagen_crear(estado='error')}")
    for ficha in fichas:
        with pytest.raises(hablado.EntradaInvalida) as e:
            hablado.resolver_foto("acme", ficha)
        assert e.value.texto() == "Elige una foto de este proyecto.", ficha


def test_resolver_foto_acepta_cualquier_origen_del_proyecto(entorno):
    # biblioteca.subir dedupea por hash (materiales.obtener_o_crear): si la
    # misma imagen ya existía como material con otro origen (p. ej. "crear",
    # de una pieza previa de Crear), esa fila vuelve tal cual — la tarjeta la
    # muestra como «Subida» pero resolver_foto no debe rechazarla.
    propia = materiales.registrar("acme", tipo="imagen", origen="crear",
                                  url="https://r2/clientes/acme/flowplus/otra-pieza.png",
                                  hash=materiales.hash_clave("foto-crear", "acme"), bytes=10, ancho=704, alto=1280)
    assert hablado.resolver_foto("acme", f"mat:{propia['id']}") == propia["url"]
    ajena = materiales.registrar("otro", tipo="imagen", origen="crear",
                                 url="https://r2/clientes/otro/flowplus/otra-pieza.png",
                                 hash=materiales.hash_clave("foto-crear", "otro"), bytes=10, ancho=704, alto=1280)
    with pytest.raises(hablado.EntradaInvalida) as e:
        hablado.resolver_foto("acme", f"mat:{ajena['id']}")
    assert e.value.texto() == "Elige una foto de este proyecto."


def test_crear_pieza_deja_la_sesion_lista_para_el_worker(entorno):
    m, v = _foto_subida(), _voz()
    cf_id = hablado.crear_pieza("acme", f"mat:{m['id']}", v["hash"], "  Sonríe y señala la chancla.  ", "0.2")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["tipo"] == "video" and e["modelo"] == "p_video_avatar" and e["modo_crear"] == "hablado"
    assert e["duracion_objetivo"] == 8 and e["accion_central"] == "Estas chanclas son una nube."
    assert e["referencias_urls"] == [m["url"]] and e["con_sonido"] is True and e["musica_estilo"] == ""
    assert e["enfoque"] == "persona" and e["enfoque_nombre"] == "Anuncio hablado" and e["con_persona"] is True
    assert e["prompt_fuente"] == "Estas chanclas son una nube." and e["aspect_ratio"] is None
    assert e["hablado"] == {"foto_url": m["url"], "foto_ficha": f"mat:{m['id']}", "voz_material_id": v["id"],
                            "voz_url": v["url"], "voz_duracion_s": 7.05, "voz": "Rachel", "idioma": "es",
                            "velocidad": "normal", "movimiento": "Sonríe y señala la chancla.", "resolucion": "720p"}
    assert e["estado"] == "prompt_pendiente"          # la lanza la ruta (flowplus_lanzar), no esto


def test_crear_pieza_valida_todo_antes_de_crear_nada(entorno):
    m, v = _foto_subida(), _voz()
    larga = _voz(texto="Un guion larguísimo.", ms=31000)
    ajena = _voz(cliente="otro", texto="Otra cosa.")
    casos = [
        (dict(foto_ficha="https://otro.sitio/cara.jpg"), hablado.EntradaInvalida, "Elige una foto de este proyecto."),
        (dict(voz_hash="f" * 64), hablado.EntradaInvalida, "Escucha la voz otra vez."),
        (dict(voz_hash="no-es-un-hash"), hablado.EntradaInvalida, "Escucha la voz otra vez."),
        (dict(voz_hash=ajena["hash"]), hablado.EntradaInvalida, "Escucha la voz otra vez."),
        (dict(voz_hash=larga["hash"], precio_visto="0.775"), hablado.EntradaInvalida, "Esta voz dura 31 s"),
        (dict(movimiento="x" * 501), hablado.EntradaInvalida, "500 caracteres"),
        (dict(precio_visto="0.15"), hablado.PrecioCambio, "El precio cambió"),
        (dict(precio_visto="gratis"), hablado.PrecioCambio, "El precio cambió"),
    ]
    base = dict(foto_ficha=f"mat:{m['id']}", voz_hash=v["hash"], movimiento="", precio_visto="0.2")
    for cambio, error, texto in casos:
        with pytest.raises(error) as e:
            hablado.crear_pieza("acme", **{**base, **cambio})
        assert texto in e.value.texto(), cambio
    assert creative_flow.cargar("acme") == {}


def test_crear_pieza_no_sube_la_foto_si_la_voz_o_el_precio_fallan_antes(entorno):
    # La voz y el precio se validan ANTES de resolver la foto: un "cat:" sube
    # la imagen a R2 al resolverse (como en Crear), así que un precio o una
    # voz inválidos no deben gastar esa subida (spec: nada se crea si algo no
    # cuadra, y aquí tampoco se sube nada de más).
    v = _voz()
    with pytest.raises(hablado.PrecioCambio):
        hablado.crear_pieza("acme", "cat:ana", v["hash"], "", "0.15")
    assert entorno["subidas"] == []
    with pytest.raises(hablado.EntradaInvalida) as e:
        hablado.crear_pieza("acme", "cat:ana", "f" * 64, "", "0.2")
    assert e.value.texto() == "Escucha la voz otra vez."
    assert entorno["subidas"] == []

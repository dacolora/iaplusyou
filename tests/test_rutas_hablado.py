"""Rutas del anuncio hablado (spec 2026-10-01 §1, §3, §4): el panel por fetch,
subir una foto, la voz (cacheada o una tarea que paga una vez) y crear el
video con el precio visto. Nada se crea ni se cobra con algo inválido."""
import io

import pytest

import audios
import materiales
from tests.test_hablado import _foto_subida, _imagen_crear, _voz
from tests.test_rutas_experimentos import _cliente_admin

FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import catalogo_productos
    import dashboard
    import hablado
    import proyectos
    from final_edition import biblioteca
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    monkeypatch.setattr(dashboard, "_client_dir", lambda c: str(tmp_path / "clientes" / c))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado",
                        lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    personajes = [{"id": "ana", "nombre": "Ana", "referencias": [str(tmp_path / "ana.jpg")]}]
    monkeypatch.setattr(catalogo_productos, "listar",
                        lambda c, cat="producto": personajes if (c == "acme" and cat == "personaje") else [])
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda c, pid, categoria=None: next((p for p in personajes if p["id"] == pid), None)
                        if (c == "acme" and categoria == "personaje") else None)
    vivos, encolados, subidos = set(), [], []
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: job_id in vivos)

    def _encolar(job_id, tipo, payload, **kw):
        if job_id in vivos:
            return False
        vivos.add(job_id)
        encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw})
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(hablado.r2_uploader, "upload_image", lambda local, key: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(biblioteca, "_carpeta_tmp", lambda c: str(tmp_path))
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados, "vivos": vivos,
            "subidos": subidos}


def _datos_voz(**k):
    d = {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal"}
    d.update(k)
    return d


def _jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (90, 160), (200, 120, 80)).save(buf, "JPEG")
    return buf.getvalue()


def test_panel_trae_las_fotos_y_la_galeria_de_voces(app):
    cid, m = _imagen_crear(), _foto_subida()
    r = app["c"].get("/cliente/acme/hablado/panel", headers=FETCH)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert f'value="cf:{cid}"' in html and 'value="cat:ana"' in html and f'value="mat:{m["id"]}"' in html
    assert "/cliente/acme/productos/ana/imagen?categoria=personaje&amp;w=320" in html
    assert html.count('class="au-voz"') == len(audios.voces()) and 'id="hb-voces"' in html
    assert 'id="hb-texto"' in html and 'maxlength="500"' in html and 'id="hb-generar"' in html
    assert "<script" not in html and "data-poll-job" not in html and "<form" not in html
    assert html.count("<div") == html.count("</div>")


def test_voz_ya_hecha_responde_lista_sin_encolar(app):
    _voz(texto="Hola mundo")
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(texto="  Hola   mundo "), headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["listo"]
    assert d["voz"]["precio_video"] == 0.2 and d["voz"]["duracion_s"] == 7.05 and d["voz"]["aviso"] is None
    assert app["encolados"] == []


def test_voz_nueva_encola_una_sola_tarea_que_paga(app):
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(), headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and not d["listo"] and d["job_id"] == "acme__hablado_voz"
    assert d["estado_url"] == "/trabajo/acme__hablado_voz/estado"
    (t,) = app["encolados"]
    assert t["tipo"] == "hablado_voz" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "texto": "Hola mundo", "voz": "Rachel", "idioma": "es",
                            "velocidad": "normal"}
    assert [e[0] for e in t["etapas"]] == ["Sintetizando la voz"]
    r2 = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(texto="Otra cosa"), headers=FETCH)
    d2 = r2.get_json()
    assert r2.status_code == 409 and "espera" in d2["error"] and d2["job_id"] == "acme__hablado_voz"
    assert len(app["encolados"]) == 1


def test_solo_cache_nunca_encola(app):
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(solo_cache="1"), headers=FETCH)
    assert r.status_code == 404 and not r.get_json()["ok"] and app["encolados"] == []


def test_voz_invalida_responde_400_sin_encolar(app):
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(texto="   "), headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == "Escribe el texto que quieres que lea la voz."
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(texto="a" * 501), headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == "El guion pasa de 500 caracteres."
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(voz="Nadie"), headers=FETCH)
    assert r.status_code == 400 and app["encolados"] == []


def test_crear_lanza_la_pieza_con_el_precio_visto(app):
    import creative_flow
    m, v = _foto_subida(), _voz()
    r = app["c"].post("/cliente/acme/hablado/crear", headers=FETCH,
                      data={"foto": f"mat:{m['id']}", "voz_hash": v["hash"], "movimiento": "Sonríe.", "precio_visto": "0.2"})
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["ir"] == "#referencias"
    e = creative_flow.cargar("acme")[d["cf_id"]]
    assert e["modelo"] == "p_video_avatar" and e["modo_crear"] == "hablado" and e["estado"] == "video_generando"
    assert e["hablado"]["voz_url"] == v["url"] and e["hablado"]["foto_url"] == m["url"]
    assert e["hablado"]["movimiento"] == "Sonríe."
    (t,) = app["encolados"]
    assert t["tipo"] == "flowplus_video" and t["max_intentos"] == 1 and t["prioridad"] == 5
    assert t["job_id"] == f"acme__{d['cf_id']}__creative_flow"


def test_crear_rechaza_y_no_crea_nada(app):
    import creative_flow
    m, v = _foto_subida(), _voz()
    larga = _voz(texto="largo", ms=31000)
    ajena = _foto_subida(cliente="otro", n=2)
    de_otro = _imagen_crear(cliente="otro")
    casos = [
        ({"foto": f"mat:{ajena['id']}"}, 400, "Elige una foto de este proyecto."),
        ({"foto": f"cf:{de_otro}"}, 400, "Elige una foto de este proyecto."),
        ({"foto": "https://otro.sitio/cara.jpg"}, 400, "Elige una foto de este proyecto."),
        ({"voz_hash": "0" * 64}, 400, "Escucha la voz otra vez."),
        ({"voz_hash": larga["hash"], "precio_visto": "0.775"}, 400, "Esta voz dura 31 s"),
        ({"precio_visto": "0.15"}, 409, "El precio cambió"),
        ({"precio_visto": ""}, 409, "El precio cambió"),
    ]
    base = {"foto": f"mat:{m['id']}", "voz_hash": v["hash"], "movimiento": "", "precio_visto": "0.2"}
    for cambio, codigo, texto in casos:
        r = app["c"].post("/cliente/acme/hablado/crear", data={**base, **cambio}, headers=FETCH)
        assert r.status_code == codigo, cambio
        assert texto in r.get_json()["error"], cambio
    assert creative_flow.cargar("acme") == {} and app["encolados"] == []


def test_subir_foto_la_guarda_y_devuelve_su_tarjeta(app):
    r = app["c"].post("/cliente/acme/hablado/foto", data={"foto": (io.BytesIO(_jpeg()), "cara.jpg")},
                      headers=FETCH, content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["foto"]["ficha"].startswith("mat:") and d["foto"]["origen"] == "subida"
    assert 'class="hb-foto"' in d["html"] and f'value="{d["foto"]["ficha"]}"' in d["html"]
    assert any(k.startswith("clientes/acme/materiales/") and k.endswith(".jpg") for k in app["subidos"])
    r = app["c"].post("/cliente/acme/hablado/foto", data={"foto": (io.BytesIO(b"hola"), "notas.txt")},
                      headers=FETCH, content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json()["error"] == "Sube una foto jpg, png o webp."


def test_los_post_de_otro_sitio_dan_403(app):
    ajeno = {**FETCH, "Sec-Fetch-Site": "cross-site"}
    for ruta in ("voz", "crear", "foto"):
        r = app["c"].post(f"/cliente/acme/hablado/{ruta}", data=_datos_voz(), headers=ajeno)
        assert r.status_code == 403 and r.get_json()["ok"] is False, ruta
    assert app["encolados"] == []

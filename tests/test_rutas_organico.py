"""Rutas y UI de la publicación orgánica (Bloque 7, Task 3): Configuración ›
Canales orgánicos, `org_redactar` (JSON), `org_publicar` (crea filas + encola
organico_publicar con max_intentos=1, duplicados con aviso), `org_reintentar`,
la propuesta `publicar_organico` con el texto editable y `prop_aprobar` con
overrides, el bloque «Publicar orgánico» en Experimentos y Crear, el tile y
la alerta del Tablero, y el guard por cliente. Sin red: canales por meta.json
fake + tokens en un BASE_DIR temporal, Claude y acciones.ejecutar fakes,
trabajos.encolar capturado."""
import json
import os

import pytest

from tests.test_experimentos_db import PAISES, _pieza
from tests.test_rutas_bloque4 import _flashes, _seccion
from tests.test_rutas_experimentos import _cliente_admin

META_OK = {"moneda": "COP", "page_access_token": "T-PAG", "page_id": "123", "ig_user_id": "999"}


@pytest.fixture()
def app(base_temporal, tmp_path, monkeypatch):
    """Facebook + Instagram por meta.json, YouTube por token; TikTok sin
    token (canal no disponible, con motivo)."""
    import dashboard
    import organico
    import proyectos
    import tiendas
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(organico, "BASE_DIR", str(tmp_path))
    os.makedirs(tmp_path / "clientes" / "acme")
    with open(tmp_path / "clientes" / "acme" / "token_youtube.json", "w") as f:
        json.dump({"access_token": "SECRETO-YT"}, f)
    meta = dict(META_OK)
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: dict(meta) if c == "acme" and meta else None)
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(tiendas, "listar", lambda c: [])
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    ejecutadas = []

    def _ejecutar(cliente, eid, accion, payload):
        ejecutadas.append((cliente, eid, accion, dict(payload)))
        return f"{accion} hecho."
    monkeypatch.setattr(dashboard.acciones, "ejecutar", _ejecutar)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados,
            "ejecutadas": ejecutadas, "meta": meta, "tmp": tmp_path, "organico": organico}


def _experimento(cliente="acme", modo="manual"):
    import experimentos as ex
    return ex.crear(cliente, "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", modo=modo)


def _pieza_en(base_temporal, eid, **kw):
    import experimentos as ex
    pid = _pieza(base_temporal, **kw)
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    return pid, ep


def _html(app):
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    return r.get_data(as_text=True)


FORM_OK = {"plataformas": ["instagram", "facebook"], "caption_instagram": "Hola IG #a #b #c",
           "caption_facebook": "Hola FB https://t #a #b #c", "titulo_facebook": "Título FB"}


# ---- Configuración › Canales orgánicos ----------------------------------------

def test_configuracion_muestra_canales_con_estado_y_pasos(app):
    html = _seccion(_html(app), "settings")
    i = html.index('id="config-canales-organicos"')
    assert html.index('id="config-pixel"') < i < html.index('id="config-correo"')
    sec = html[i:]
    assert 'id="canal-facebook"' in sec and 'id="canal-tiktok"' in sec
    # Orden de organico.ORDEN: instagram, facebook, tiktok, youtube.
    fb = sec[sec.index('id="canal-facebook"'):sec.index('id="canal-tiktok"')]
    assert "conectado" in fb and "falta" not in fb
    tk = sec[sec.index('id="canal-tiktok"'):sec.index('id="canal-youtube"')]
    assert "falta" in tk and "Falta token_tiktok.json" in tk and "auth/auth_tiktok.py" in tk
    assert "clientes/acme/" in tk
    assert "instagram_content_publish" in sec and "auth/auth_youtube.py" in sec
    assert "SECRETO-YT" not in html


def test_configuracion_canales_sin_meta(app):
    app["meta"].clear()
    html = _seccion(_html(app), "settings")
    sec = html[html.index("Canales orgánicos"):]
    fb = sec[sec.index('id="canal-facebook"'):sec.index('id="canal-tiktok"')]
    assert "falta" in fb and "Conecta Meta con una Página" in fb


# ---- org_redactar ------------------------------------------------------------

def test_org_redactar_devuelve_json_por_plataforma(app, base_temporal, monkeypatch):
    pid = _pieza(base_temporal)
    pedidas = []

    def fake(cliente, pieza_id, plataformas):
        pedidas.append((cliente, pieza_id, list(plataformas)))
        return {p: {"titulo": f"T {p}", "caption": f"C {p} #a #b #c", "extra": {"fallback": p == "facebook"}}
                for p in plataformas}
    monkeypatch.setattr(app["dashboard"].organico, "redactar", fake)
    r = app["c"].post("/cliente/acme/organico/redactar", data={"pieza_id": str(pid), "plataformas": ["instagram", "facebook"]})
    assert r.status_code == 200
    assert r.get_json() == {"instagram": {"titulo": "T instagram", "caption": "C instagram #a #b #c", "fallback": False},
                            "facebook": {"titulo": "T facebook", "caption": "C facebook #a #b #c", "fallback": True}}
    assert pedidas == [("acme", pid, ["instagram", "facebook"])]


def test_org_redactar_valida_y_no_filtra_tokens(app, base_temporal, monkeypatch):
    r = app["c"].post("/cliente/acme/organico/redactar", data={"pieza_id": "", "plataformas": ["instagram"]})
    assert r.status_code == 400 and "plataforma" in r.get_json()["error"]
    r = app["c"].post("/cliente/acme/organico/redactar", data={"pieza_id": "5", "plataformas": ["twitter"]})
    assert r.status_code == 400
    pid = _pieza(base_temporal)
    monkeypatch.setattr(app["dashboard"].organico, "redactar",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("Graph 400 access_token=EAABsecret")))
    r = app["c"].post("/cliente/acme/organico/redactar", data={"pieza_id": str(pid), "plataformas": ["instagram"]})
    assert r.status_code == 500 and "EAABsecret" not in r.get_json()["error"]


# ---- org_publicar ------------------------------------------------------------

def test_org_publicar_crea_publicaciones_y_encola_con_max_intentos_1(app, base_temporal):
    pid = _pieza(base_temporal)
    r = app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id=str(pid)))
    assert r.status_code == 302 and r.headers["Location"].endswith("#experimentos")
    pubs = app["organico"].listar("acme", pieza_id=pid)
    # Todo pasa por organico.ajustar en servidor: el título vacío se rellena
    # con el gancho/nombre y el bloque de hashtags va aparte.
    assert [(p["plataforma"], p["estado"], p["origen"], p["experimento_pieza_id"], p["titulo"]) for p in pubs] == \
        [("instagram", "en_cola", "manual", None, f"Pieza {pid}"), ("facebook", "en_cola", "manual", None, "Título FB")]
    assert pubs[0]["caption"] == "Hola IG\n\n#a #b #c"
    assert len(app["encolados"]) == 1
    t = app["encolados"][0]
    assert t["tipo"] == "organico_publicar" and t["job_id"] == f"acme__pieza{pid}__organico"
    assert t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["etapas"] == [("Descargando", 15), ("Publicando", 85)]
    assert t["payload"] == {"cliente": "acme", "pub_ids": [p["id"] for p in pubs]}
    assert any("en cola: Instagram Reels, Facebook (Página)" in m for m in _flashes(app["c"]))


def test_org_publicar_vuelve_a_crear_y_guarda_ep_id(app, base_temporal):
    import experimentos as ex
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    r = app["c"].post("/cliente/acme/organico/publicar",
                      data=dict(FORM_OK, ep_id=str(ep), plataformas=["instagram"], volver="creativeflowplus"))
    assert r.headers["Location"].endswith("#creativeflowplus")
    pubs = app["organico"].listar("acme", pieza_id=pid)
    assert [(p["plataforma"], p["experimento_pieza_id"]) for p in pubs] == [("instagram", ep)]
    e = ex.obtener("acme", eid)
    assert e["piezas"][0]["extra"]["publicado_organico"] is True
    assert any(ev["tipo"] == "accion" and "orgánica en cola" in ev["mensaje"] for ev in e["eventos"])


def test_org_publicar_duplicado_avisa_y_no_repite(app, base_temporal):
    pid = _pieza(base_temporal)
    org = app["organico"]
    ya = org.crear("acme", pid, "instagram", "ya salió #a #b #c")
    org.actualizar("acme", ya, estado="publicada", url="https://www.instagram.com/p/abc")
    app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id=str(pid)))
    pubs = org.listar("acme", pieza_id=pid)
    assert [(p["plataforma"], p["estado"]) for p in pubs] == [("instagram", "publicada"), ("facebook", "en_cola")]
    assert any("Ya estaba publicada (o en cola) en Instagram Reels" in m for m in _flashes(app["c"]))
    assert app["encolados"][0]["payload"]["pub_ids"] == [pubs[1]["id"]]
    # Todo duplicado: ni fila nueva ni tarea.
    app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id=str(pid)))
    assert len(org.listar("acme", pieza_id=pid)) == 2 and len(app["encolados"]) == 1


def test_org_publicar_rechaza_canal_no_disponible_y_texto_vacio(app, base_temporal):
    pid = _pieza(base_temporal)
    org = app["organico"]
    app["c"].post("/cliente/acme/organico/publicar",
                  data={"pieza_id": str(pid), "plataformas": ["instagram", "tiktok"], "caption_instagram": "x #a #b #c", "caption_tiktok": "y"})
    assert org.listar("acme", pieza_id=pid) == [] and app["encolados"] == []
    assert any("Sin canal conectado: TikTok" in m and "No se publicó nada" in m for m in _flashes(app["c"]))
    app["c"].post("/cliente/acme/organico/publicar",
                  data={"pieza_id": str(pid), "plataformas": ["instagram", "facebook"], "caption_instagram": "x #a #b #c", "caption_facebook": "  "})
    assert org.listar("acme", pieza_id=pid) == [] and app["encolados"] == []
    assert any("Falta el texto para Facebook (Página)" in m for m in _flashes(app["c"]))
    app["c"].post("/cliente/acme/organico/publicar", data={"pieza_id": str(pid)})
    assert any("Marca al menos una plataforma" in m for m in _flashes(app["c"]))
    app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id="9999"))
    assert any("no existe en este proyecto" in m for m in _flashes(app["c"]))
    assert org.listar("acme") == [] and app["encolados"] == []


def test_org_publicar_no_encola_si_ya_hay_trabajo_en_curso(app, base_temporal, monkeypatch):
    pid = _pieza(base_temporal)
    monkeypatch.setattr(app["dashboard"].trabajos, "en_curso", lambda job_id: True)
    app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id=str(pid)))
    assert app["organico"].listar("acme", pieza_id=pid) == [] and app["encolados"] == []
    assert any("en curso" in m for m in _flashes(app["c"]))


def test_org_publicar_si_encolar_falla_filas_quedan_en_error(app, base_temporal, monkeypatch):
    pid = _pieza(base_temporal)
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar", lambda *a, **k: False)
    app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id=str(pid)))
    pubs = app["organico"].listar("acme", pieza_id=pid)
    assert [p["estado"] for p in pubs] == ["error", "error"]
    assert all("reintenta" in p["error"] for p in pubs)


def test_org_publicar_normaliza_el_texto_en_servidor(app, base_temporal):
    """Important #1: `maxlength` del textarea es solo cliente. Un caption de
    3 000 chars con URL en Instagram queda guardado recortado (≤ 2200), sin
    enlace y con «Link en bio.»; en Facebook el enlace se conserva."""
    import organico
    pid = _pieza(base_temporal)
    largo = ("palabra " * 375).strip() + " https://tienda.com/p " + ("otra " * 220).strip()
    assert len(largo) > 2900
    app["c"].post("/cliente/acme/organico/publicar", data={
        "pieza_id": str(pid), "plataformas": ["instagram", "facebook"],
        "caption_instagram": largo + " #a #b #c", "caption_facebook": "Corto https://tienda.com/p #a #b #c"})
    pubs = {p["plataforma"]: p for p in app["organico"].listar("acme", pieza_id=pid)}
    ig = pubs["instagram"]["caption"]
    assert len(ig) <= organico.PLATAFORMAS["instagram"]["max_caption"]
    assert "https://" not in ig and "tienda.com" not in ig and "Link en bio." in ig
    assert ig.endswith("#a #b #c") and pubs["instagram"]["estado"] == "en_cola"
    assert "https://tienda.com/p" in pubs["facebook"]["caption"]
    assert len(app["encolados"]) == 1


def test_org_publicar_creacion_parcial_deja_lo_creado_en_error(app, base_temporal, monkeypatch):
    """Minor #5: si `crear` falla en la 2.ª plataforma con un error que no es
    «ya está publicada», la fila creada en la 1.ª no queda `en_cola` sin tarea
    (bloquearía la plataforma por unicidad): pasa a `error` y no se encola."""
    import organico
    pid = _pieza(base_temporal)
    crear_real = organico.crear
    llamadas = []

    def crear(cliente, pieza_id, plataforma, *a, **kw):
        llamadas.append(plataforma)
        if len(llamadas) == 2:
            raise ValueError("Se cayó la base.")
        return crear_real(cliente, pieza_id, plataforma, *a, **kw)
    monkeypatch.setattr(app["dashboard"].organico, "crear", crear)
    app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id=str(pid)))
    pubs = app["organico"].listar("acme", pieza_id=pid)
    assert [(p["plataforma"], p["estado"]) for p in pubs] == [("instagram", "error")]
    assert "Se cayó la base." in pubs[0]["error"] and "Facebook" in pubs[0]["error"]
    assert app["encolados"] == []
    assert any("Se cayó la base." in m and "No se publicó nada" in m for m in _flashes(app["c"]))
    # La plataforma no quedó bloqueada: se puede volver a crear.
    monkeypatch.setattr(app["dashboard"].organico, "crear", crear_real)
    app["c"].post("/cliente/acme/organico/publicar", data=dict(FORM_OK, pieza_id=str(pid)))
    assert [(p["plataforma"], p["estado"]) for p in app["organico"].listar("acme", pieza_id=pid)] == \
        [("instagram", "error"), ("instagram", "en_cola"), ("facebook", "en_cola")]


# ---- org_reintentar ----------------------------------------------------------

def test_org_reintentar_solo_en_error(app, base_temporal):
    pid = _pieza(base_temporal)
    org = app["organico"]
    pub = org.crear("acme", pid, "facebook", "texto #a #b #c")
    org.actualizar("acme", pub, estado="error", error="Graph dijo que no")
    r = app["c"].post(f"/cliente/acme/organico/{pub}/reintentar", data={"volver": "creativeflowplus"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#creativeflowplus")
    fila = org.obtener("acme", pub)
    assert fila["estado"] == "en_cola" and fila["error"] is None
    assert app["encolados"][-1]["payload"] == {"cliente": "acme", "pub_ids": [pub]} and app["encolados"][-1]["max_intentos"] == 1
    # Publicada: no se toca.
    org.actualizar("acme", pub, estado="publicada")
    app["c"].post(f"/cliente/acme/organico/{pub}/reintentar")
    assert org.obtener("acme", pub)["estado"] == "publicada" and len(app["encolados"]) == 1
    assert any("Solo se reintenta" in m for m in _flashes(app["c"]))
    app["c"].post("/cliente/acme/organico/9999/reintentar")
    assert any("no existe" in m for m in _flashes(app["c"]))


def test_org_reintentar_con_otra_viva_avisa_y_no_da_500(app, base_temporal):
    """I2: IG falló (fila A `error`), la persona publicó de nuevo (fila B
    viva) y pulsa «Reintentar» en A → flash, A sigue `error`, nada encolado,
    y el bloque ya no ofrece «Reintentar» para A."""
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    org = app["organico"]
    a = org.crear("acme", pid, "instagram", "falló #a #b #c")
    org.actualizar("acme", a, estado="error", error="IG dijo que no")
    b = org.crear("acme", pid, "instagram", "salió #a #b #c")
    org.actualizar("acme", b, estado="publicada", id_externo="17900")
    r = app["c"].post(f"/cliente/acme/organico/{a}/reintentar", data={"volver": "experimentos"})
    assert r.status_code == 302
    assert any("Ya hay una publicación en curso o publicada" in m for m in _flashes(app["c"]))
    assert org.obtener("acme", a)["estado"] == "error" and app["encolados"] == []
    html = _seccion(_html(app), "experimentos")
    assert f"/organico/{a}/reintentar" not in html and "IG dijo que no" in html
    # Carrera: la viva aparece entre el chequeo y el UPDATE → ValueError de
    # organico.actualizar, no IntegrityError/500.
    org.actualizar("acme", b, estado="error")
    real = org.listar
    app["dashboard"].organico.listar = lambda cliente, **kw: [p for p in real(cliente, **kw) if p["id"] != b]
    try:
        org.actualizar("acme", b, estado="publicada")
        r = app["c"].post(f"/cliente/acme/organico/{a}/reintentar")
        assert r.status_code == 302 and org.obtener("acme", a)["estado"] == "error" and app["encolados"] == []
        assert any("en curso o publicada" in m for m in _flashes(app["c"]))
    finally:
        app["dashboard"].organico.listar = real


def test_org_reintentar_rechaza_fila_que_ya_subio(app, base_temporal):
    """I1: una fila `error` con id_externo ya está en la plataforma: no se
    reintenta (sería un segundo upload) y el bloque no ofrece «Reintentar»."""
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    org = app["organico"]
    a = org.crear("acme", pid, "facebook", "x #a #b #c")
    org.actualizar("acme", a, estado="error", error="se cortó", id_externo="555")
    r = app["c"].post(f"/cliente/acme/organico/{a}/reintentar")
    assert r.status_code == 302 and org.obtener("acme", a)["estado"] == "error" and app["encolados"] == []
    assert any("ya se subió" in m and "revisa la plataforma" in m for m in _flashes(app["c"]))
    html = _seccion(_html(app), "experimentos")
    assert f"/organico/{a}/reintentar" not in html and "se cortó" in html
    # Y una `publicando` con id se pinta como subida en confirmación.
    b = org.crear("acme", pid, "tiktok", "x #a #b #c")
    org.actualizar("acme", b, estado="publicando", id_externo="v_pub.7")
    html = _seccion(_html(app), "experimentos")
    assert "subida, confirmando (id v_pub.7)" in html


def test_propuesta_escapa_el_caption_en_el_textarea(app, base_temporal):
    """Un caption con </textarea><script> no rompe el HTML ni ejecuta nada:
    la macro va bajo autoescape."""
    malo = "Hola </textarea><script>alert(1)</script> #a #b #c"
    _propuesta_organica(base_temporal, captions={"instagram": {"titulo": "T", "caption": malo},
                                                 "facebook": {"titulo": 'x" onfocus="alert(1)', "caption": malo}})
    html = _seccion(_html(app), "experimentos")
    assert "</textarea><script>" not in html and "&lt;/textarea&gt;&lt;script&gt;" in html
    assert 'onfocus="alert' not in html and "onfocus=&#34;alert" in html


# ---- propuesta publicar_organico --------------------------------------------

def _propuesta_organica(base_temporal, captions=None):
    import propuestas
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    payload = {"ep_id": ep, "plataformas": ["instagram", "facebook"],
               "captions": captions or {"instagram": {"titulo": "T", "caption": "Texto IG del motor #a #b #c"},
                                        "facebook": {"titulo": "Título FB", "caption": "Texto FB del motor #a #b #c"}}}
    prid = propuestas.crear("acme", eid, "publicar_organico", payload, "ganador")
    return eid, pid, ep, prid


def test_propuesta_organica_renderiza_textos_editables(app, base_temporal):
    eid, pid, ep, prid = _propuesta_organica(base_temporal)
    html = _seccion(_html(app), "experimentos")
    assert "Texto IG del motor #a #b #c" in html and "Texto FB del motor" in html
    assert 'name="caption_instagram"' in html and 'name="titulo_facebook"' in html and 'value="Título FB"' in html
    assert 'name="org_form"' in html and "Aprobar y publicar" in html
    assert f"/propuestas/{prid}/aprobar" in html and f"/propuestas/{prid}/rechazar" in html


def test_prop_aprobar_manda_el_texto_editado(app, base_temporal):
    import propuestas
    eid, pid, ep, prid = _propuesta_organica(base_temporal)
    r = app["c"].post(f"/cliente/acme/propuestas/{prid}/aprobar", data={
        "org_form": "1", "plataformas": ["instagram", "facebook"],
        "caption_instagram": "Mi texto editado #x #y #z", "titulo_instagram": "",
        "caption_facebook": "Texto FB del motor #a #b #c", "titulo_facebook": "Mi título"})
    assert r.status_code == 302
    assert len(app["ejecutadas"]) == 1
    cliente, e, accion, payload = app["ejecutadas"][0]
    assert (cliente, e, accion) == ("acme", eid, "publicar_organico")
    assert payload["plataformas"] == ["instagram", "facebook"]
    # El texto editado va normalizado (organico.ajustar): «Link en bio.» en
    # IG porque el experimento tiene destino_url, título vacío → gancho/nombre;
    # en FB entra la url de compra.
    assert payload["captions"]["instagram"] == {"titulo": f"Pieza {pid}",
                                                "caption": "Mi texto editado\n\nLink en bio.\n\n#x #y #z"}
    assert payload["captions"]["facebook"] == {"titulo": "Mi título",
                                               "caption": "Texto FB del motor\n\nhttps://t\n\n#a #b #c"}
    assert propuestas.obtener("acme", prid)["estado"] == "ejecutada"


def test_prop_aprobar_normaliza_caption_largo_con_url(app, base_temporal):
    """Important #1 en la propuesta: 3 000 chars + URL en Instagram llegan a
    acciones recortados y sin enlace."""
    import organico
    eid, pid, ep, prid = _propuesta_organica(base_temporal)
    largo = ("palabra " * 375).strip() + " https://tienda.com/p " + ("otra " * 220).strip() + " #a #b #c"
    app["c"].post(f"/cliente/acme/propuestas/{prid}/aprobar", data={
        "org_form": "1", "plataformas": ["instagram"], "caption_instagram": largo})
    ig = app["ejecutadas"][0][3]["captions"]["instagram"]["caption"]
    assert len(ig) <= organico.PLATAFORMAS["instagram"]["max_caption"]
    assert "https://" not in ig and "Link en bio." in ig and ig.endswith("#a #b #c")


def test_prop_aprobar_respeta_plataformas_desmarcadas_y_exige_una(app, base_temporal):
    import propuestas
    eid, pid, ep, prid = _propuesta_organica(base_temporal)
    # Ninguna marcada: no se aprueba (lista vacía = todas las disponibles en acciones).
    app["c"].post(f"/cliente/acme/propuestas/{prid}/aprobar", data={"org_form": "1"})
    assert app["ejecutadas"] == [] and propuestas.obtener("acme", prid)["estado"] == "pendiente"
    assert any("Marca al menos una plataforma" in m for m in _flashes(app["c"]))
    # Solo Facebook: Instagram sale del payload.
    app["c"].post(f"/cliente/acme/propuestas/{prid}/aprobar",
                  data={"org_form": "1", "plataformas": ["facebook"], "caption_facebook": "Solo FB #a #b #c"})
    payload = app["ejecutadas"][0][3]
    assert payload["plataformas"] == ["facebook"] and set(payload["captions"]) == {"facebook"}
    assert payload["captions"]["facebook"]["caption"] == "Solo FB\n\nhttps://t\n\n#a #b #c"
    assert payload["captions"]["facebook"]["titulo"] == "Título FB"   # sin campo titulo en el form: se conserva


def test_propuesta_sin_plataformas_ofrece_los_canales_disponibles(app, base_temporal):
    """Minor #3: una propuesta que el motor creó sin canales pinta los que
    hoy están disponibles (sin marcar, texto oculto) y aprobar manda los que
    la persona marcó; sin caption, acciones redacta al aprobar."""
    import propuestas
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    prid = propuestas.crear("acme", eid, "publicar_organico", {"ep_id": ep, "plataformas": [], "captions": {}}, "ganador")
    html = _seccion(_html(app), "experimentos")
    form = html[html.index(f"/propuestas/{prid}/aprobar"):html.index("Aprobar y publicar")]
    assert 'value="instagram"' in form and 'value="facebook"' in form and 'value="youtube"' in form
    assert 'value="tiktok"' not in form   # sin token: no disponible
    assert "checked" not in form and form.count("canal nuevo") == 3
    assert 'data-redacta-al-aprobar="1"' in form
    assert "al aprobar no se publica nada" not in form
    r = app["c"].post(f"/cliente/acme/propuestas/{prid}/aprobar",
                      data={"org_form": "1", "plataformas": ["youtube"], "caption_youtube": "", "titulo_youtube": ""})
    assert r.status_code == 302
    payload = app["ejecutadas"][0][3]
    assert payload["plataformas"] == ["youtube"] and payload["captions"] == {"youtube": {"titulo": ""}}


def test_propuesta_con_plataformas_suma_los_canales_nuevos_sin_marcar(app, base_temporal):
    eid, pid, ep, prid = _propuesta_organica(base_temporal)   # instagram + facebook
    html = _seccion(_html(app), "experimentos")
    form = html[html.index(f"/propuestas/{prid}/aprobar"):html.index("Aprobar y publicar")]
    ig = form[form.index('value="instagram"'):form.index('value="facebook"')]
    yt = form[form.index('value="youtube"'):]
    assert "checked" in ig and "checked" not in yt and "canal nuevo" in yt
    assert 'data-plataforma="youtube" hidden' in yt


def test_propuesta_sin_ningun_canal_dice_como_salir(app, base_temporal):
    import propuestas
    app["meta"].clear()
    os.remove(app["tmp"] / "clientes" / "acme" / "token_youtube.json")
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    prid = propuestas.crear("acme", eid, "publicar_organico", {"ep_id": ep, "plataformas": [], "captions": {}}, "ganador")
    html = _seccion(_html(app), "experimentos")
    form = html[html.index(f"/propuestas/{prid}/aprobar"):html.index("Aprobar y publicar")]
    assert 'name="plataformas"' not in form
    assert "conecta un canal en" in form and "Canales orgánicos" in form and "para poder aprobarla" in form


def test_prop_aprobar_sin_form_organico_deja_el_payload_tal_cual(app, base_temporal):
    eid, pid, ep, prid = _propuesta_organica(base_temporal)
    app["c"].post(f"/cliente/acme/propuestas/{prid}/aprobar")
    payload = app["ejecutadas"][0][3]
    assert payload["plataformas"] == ["instagram", "facebook"]
    assert payload["captions"]["instagram"]["caption"] == "Texto IG del motor #a #b #c"


def test_prop_aprobar_otras_acciones_no_cambia(app, base_temporal):
    """Regresión: una propuesta que no es publicar_organico sigue ejecutándose
    con su payload aunque el form traiga campos sueltos."""
    import experimentos as ex
    import propuestas
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    prid = propuestas.crear("acme", eid, "pausar", {"ep_id": ep}, "CTR bajo")
    app["c"].post(f"/cliente/acme/propuestas/{prid}/aprobar", data={"org_form": "1", "caption_instagram": "x"})
    assert app["ejecutadas"] == [("acme", eid, "pausar", {"ep_id": ep, "motivo": "CTR bajo"})]
    assert propuestas.obtener("acme", prid)["estado"] == "ejecutada"
    assert ex.obtener("acme", eid) is not None


# ---- bloque en Experimentos y Crear -------------------------------------------

def test_experimentos_muestra_bloque_publicar_y_publicaciones(app, base_temporal):
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    org = app["organico"]
    ok = org.crear("acme", pid, "facebook", "salió #a #b #c")
    org.actualizar("acme", ok, estado="publicada", url="https://www.facebook.com/777", publicado_en="2026-09-18T10:00:00")
    mal = org.crear("acme", pid, "youtube", "falló #a #b #c")
    org.actualizar("acme", mal, estado="error", error="YouTube dijo que no")
    html = _seccion(_html(app), "experimentos")
    assert "Publicar orgánico" in html and "/cliente/acme/organico/publicar" in html
    assert f'name="ep_id" value="{ep}"' in html and f'name="pieza_id" value="{pid}"' in html
    assert 'href="https://www.facebook.com/777"' in html and "YouTube dijo que no" in html
    assert f"/organico/{mal}/reintentar" in html
    # Ya publicada en Facebook: la casilla va deshabilitada; TikTok sin canal, con el motivo.
    fb = html[html.index('value="facebook" data-nombre'):]
    assert "disabled" in fb[:200] and "ya publicada" in fb[:400]
    tk = html[html.index('value="tiktok" data-nombre'):]
    assert "disabled" in tk[:200] and "Falta token_tiktok.json" in tk[:500]
    assert 'name="caption_instagram"' in html and 'name="caption_facebook"' not in html   # facebook ya tiene fila viva


def test_experimentos_bloque_youtube_en_error_sigue_disponible(app, base_temporal):
    """Una fila en `error` no es viva: la plataforma se ofrece de nuevo (y
    también «Reintentar» sobre la fila)."""
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    org = app["organico"]
    mal = org.crear("acme", pid, "youtube", "falló #a #b #c")
    org.actualizar("acme", mal, estado="error", error="no")
    html = _seccion(_html(app), "experimentos")
    assert 'name="titulo_youtube"' in html and 'name="caption_youtube"' in html


def test_experimentos_muestra_barra_si_hay_trabajo(app, base_temporal, monkeypatch):
    eid = _experimento()
    pid, ep = _pieza_en(base_temporal, eid)
    app["organico"].crear("acme", pid, "facebook", "x #a #b #c")
    monkeypatch.setattr(app["dashboard"].cola, "job_ids_vivos", lambda c, tipo: {f"acme__pieza{pid}__organico"} if tipo == "organico_publicar" else set())
    html = _seccion(_html(app), "experimentos")
    # Minor #4: el id lleva el sitio para no chocar con la misma barra en Crear.
    assert f'id="trabajo-acme__pieza{pid}__organico-experimentos"' in html
    assert f'iniciarPolling("acme__pieza{pid}__organico", "trabajo-acme__pieza{pid}__organico-experimentos")' in html
    assert f'id="trabajo-acme__pieza{pid}__organico"' not in html
    assert 'name="caption_facebook"' not in html   # mientras publica no hay formulario


def test_crear_muestra_bloque_en_final_lista(app, base_temporal):
    import creative_flow as cf
    from tests.test_rutas_final_edition import _sesion_video_listo
    cf_id = _sesion_video_listo()
    fid = cf.crear_final("acme", cf_id, "es", "CO")
    cf.actualizar_final("acme", fid, estado="listo", url_video="https://r2/f.mp4")
    pid = cf.pieza_id_por_legado("acme", fid)
    html = _seccion(_html(app), "creativeflowplus")
    assert "Publicación orgánica" in html and f'name="pieza_id" value="{pid}"' in html
    assert 'name="volver" value="creativeflowplus"' in html
    assert "window.orgConfirmar" in html and 'name="ep_id"' not in html
    # Una final en error no lo muestra.
    cf.actualizar_final("acme", fid, estado="error")
    assert "Publicación orgánica" not in _seccion(_html(app), "creativeflowplus")


def test_pagina_trae_los_scripts_una_vez(app):
    html = _html(app)
    assert html.count("window.orgRedactar = function") == 1
    assert html.count("window.orgConfirmar = function") == 1


# ---- tablero ---------------------------------------------------------------------

def _ganadora(base_temporal, veredicto="ganador"):
    import experimentos as ex
    eid = _experimento()
    ex.actualizar("acme", eid, estado="corriendo")
    pid, ep = _pieza_en(base_temporal, eid)
    ex.actualizar_pieza("acme", ep, estado="activo", veredicto=veredicto, veredicto_motivo="ROAS", veredicto_en="2026-09-10T10:00:00")
    return eid, pid, ep


def test_tablero_alerta_ganadora_sin_publicar_y_tile(app, base_temporal, monkeypatch):
    import db
    import tablero
    eid, pid, ep = _ganadora(base_temporal)
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-18T12:00:00")
    ctx = tablero.contexto("acme")
    al = [a for a in ctx["alertas"] if a["tipo"] == "ganador_sin_publicar"]
    assert len(al) == 1 and al[0]["nivel"] == "media" and al[0]["tab"] == "experimentos" and al[0]["experimento_id"] == eid
    assert "sin publicar orgánicamente" in al[0]["texto"]
    assert ctx["resumen"]["ganadoras_publicadas"] == 0
    html = _seccion(_html(app), "tablero")
    assert "Ganadoras publicadas" in html and "sin publicar orgánicamente" in html
    # Publicada este mes → tile 1 y sin alerta.
    org = app["organico"]
    pub = org.crear("acme", pid, "instagram", "x #a #b #c")
    org.actualizar("acme", pub, estado="publicada", publicado_en="2026-09-17T09:00:00")
    ctx = tablero.contexto("acme")
    assert ctx["resumen"]["ganadoras_publicadas"] == 1
    assert not [a for a in ctx["alertas"] if a["tipo"] == "ganador_sin_publicar"]
    html = _seccion(_html(app), "tablero")
    assert "sin publicar orgánicamente" not in html
    tile = html[html.index("Ganadoras publicadas"):]
    assert "<strong>1</strong>" in tile[:200]
    # Minor #2: la misma ganadora en otra plataforma sigue contando 1 (ganadoras, no publicaciones).
    pub_fb = org.crear("acme", pid, "facebook", "x #a #b #c")
    org.actualizar("acme", pub_fb, estado="publicada", publicado_en="2026-09-17T10:00:00")
    assert tablero.contexto("acme")["resumen"]["ganadoras_publicadas"] == 1
    # Fuera del mes no cuenta.
    org.actualizar("acme", pub, publicado_en="2026-08-17T09:00:00")
    org.actualizar("acme", pub_fb, publicado_en="2026-08-17T10:00:00")
    assert tablero.contexto("acme")["resumen"]["ganadoras_publicadas"] == 0


def test_tablero_alerta_sin_canales_manda_a_configuracion(app, base_temporal, monkeypatch):
    import db
    import tablero
    eid, pid, ep = _ganadora(base_temporal)
    app["meta"].clear()
    os.remove(app["tmp"] / "clientes" / "acme" / "token_youtube.json")
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-18T12:00:00")
    al = [a for a in tablero.alertas("acme") if a["tipo"] == "ganador_sin_publicar"]
    assert len(al) == 1 and al[0]["tab"] == "settings"
    assert "configura un canal orgánico en Configuración" in al[0]["texto"]
    html = _seccion(_html(app), "tablero")
    assert "configura un canal orgánico en Configuración" in html
    # Sin ganadoras: nada.
    import experimentos as ex
    ex.actualizar_pieza("acme", ep, veredicto="perdedor")
    assert not [a for a in tablero.alertas("acme") if a["tipo"] == "ganador_sin_publicar"]


def test_tablero_no_cuenta_publicaciones_de_no_ganadoras(app, base_temporal, monkeypatch):
    import db
    import tablero
    eid, pid, ep = _ganadora(base_temporal, veredicto="perdedor")
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-18T12:00:00")
    org = app["organico"]
    pub = org.crear("acme", pid, "instagram", "x #a #b #c")
    org.actualizar("acme", pub, estado="publicada", publicado_en="2026-09-17T09:00:00")
    assert tablero.resumen_mes("acme")["ganadoras_publicadas"] == 0


# ---- guard por cliente --------------------------------------------------------

def test_rutas_organico_rechazan_cliente_cruzado(app, base_temporal):
    pid = _pieza(base_temporal, cliente="otro")
    org = app["organico"]
    pub = org.crear("otro", pid, "facebook", "x #a #b #c")
    org.actualizar("otro", pub, estado="error", error="no")
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    for url, data in ((f"/cliente/otro/organico/publicar", dict(FORM_OK, pieza_id=str(pid))),
                      (f"/cliente/otro/organico/redactar", {"pieza_id": str(pid), "plataformas": ["facebook"]}),
                      (f"/cliente/otro/organico/{pub}/reintentar", {})):
        r = c.post(url, data=data)
        assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"]
    assert [p["estado"] for p in org.listar("otro", pieza_id=pid)] == ["error"] and app["encolados"] == []
    # Con sesión de acme, una publicación de `otro` tampoco se reintenta por id.
    app["c"].post(f"/cliente/acme/organico/{pub}/reintentar")
    assert org.obtener("otro", pub)["estado"] == "error" and app["encolados"] == []

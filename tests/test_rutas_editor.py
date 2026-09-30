"""Rutas de la vista previa del editor (capa 3): entra quien tiene acceso al
proyecto; la página trae el documento, los materiales y la configuración, y
encola los proxies que faltan (gratis)."""
import io
import json
import os
import re

import pytest

from tests.test_rutas_productos import _cliente_admin

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def dashboard(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    import dashboard as dash
    dash.app.config["TESTING"] = True
    return dash


@pytest.fixture()
def encolados(monkeypatch):
    import trabajos
    llamadas = []
    monkeypatch.setattr(trabajos, "encolar", lambda *a, **k: llamadas.append((a, k)) or True)
    return llamadas


def _cliente(dashboard, usuario, cliente):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario; s["rol"] = "cliente"; s["cliente"] = cliente
    return c


def _edicion():
    import ediciones
    import materiales
    from final_edition import documento
    clon = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2.test/clon.mp4", hash="h-clon",
                                bytes=10, duracion_ms=8000, ancho=1080, alto=1920)
    voz = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2.test/voz.wav", hash="h-voz",
                               bytes=10, duracion_ms=2000, extra={"picos": [0.1, 0.5]})
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "v0", "inicio_ms": 0, "duracion_ms": 4000, "material_id": clon["id"],
                                  "recorte": {"desde_ms": 0, "hasta_ms": 4000}}]
    doc["pistas"].append({"id": "p_voz", "tipo": "audio", "clips": [
        {"id": "a0", "inicio_ms": 0, "duracion_ms": 2000, "material_id": voz["id"], "rol_audio": "voz",
         "recorte": {"desde_ms": 0, "hasta_ms": 2000}}]})
    doc["guion"] = {"idioma": "es", "pais": "CO"}
    return ediciones.crear("acme", "video", "Demo <editor>", doc), clon, voz


def _datos(html):
    m = re.search(r'<script type="application/json" id="datos-editor">(.*?)</script>', html, re.S)
    assert m, "la página no trae los datos del editor"
    return json.loads(m.group(1))


def test_la_vista_previa_trae_sus_datos_y_encola_el_proxy(dashboard, encolados):
    ed, clon, voz = _edicion()
    r = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for id_ in ("lienzo", "destino", "reproducir", "inicio", "tiempo", "barra", "aviso-destino", "aviso-faltan",
                "aviso-recortes", "aviso-preparando", "aviso-audio", "aproximada",
                "producir", "linea", "linea-zoom", "h-cortar", "h-borrar", "h-duplicar", "h-deshacer",
                "h-rehacer", "estado-guardado", "recargar", "aviso-edicion", "producir-dialogo", "producir-destinos",
                "producir-confirmar", "producir-cancelar", "producir-aviso", "producir-tiempo", "producir-hecho",
                "producir-hecho-texto", "producir-hecho-enlace", "producir-reemplazo", "producir-reemplazo-texto",
                "producir-reemplazar"):
        assert f'id="{id_}"' in html, id_
    assert "editor/pagina_editor.js" in html and 'type="module"' in html
    assert "Demo &lt;editor&gt;" in html                     # el nombre va escapado
    assert '@font-face' in html and 'font-family: "SpaceGrotesk-Bold"' in html
    assert 'href="/cliente/acme#final"' in html              # vuelve a la pestaña Final edition
    datos = _datos(html)
    assert set(datos["materiales"]) == {str(clon["id"]), str(voz["id"])}
    assert datos["pendientes"] == [clon["id"]]               # el clon aún no tiene proxy
    assert datos["faltantes"] == []
    assert datos["aviso_recortes"] is None
    assert datos["destinos"] == ["es_CO"]
    assert datos["documento"]["pistas"][0]["clips"][0]["id"] == "v0"
    assert datos["config"]["formatos"]["9:16"] == [1080, 1920]
    assert datos["urls"] == {"materiales": f"/cliente/acme/ediciones/{ed['id']}/materiales",
                             "guardar": f"/cliente/acme/ediciones/{ed['id']}",
                             "producir": f"/cliente/acme/ediciones/{ed['id']}/producir",
                             "final": "/cliente/acme#final",
                             # capa 4b: la biblioteca del proyecto (Task 1)
                             "biblioteca": "/cliente/acme/ediciones/biblioteca",
                             "subir": "/cliente/acme/ediciones/materiales/subir",
                             "agregar_pieza": "/cliente/acme/ediciones/biblioteca/pieza/__CF__",
                             "materiales_por_id": "/cliente/acme/ediciones/materiales",
                             # capa 4c (8/10): «Borrar» en la biblioteca (`__ID__` = el material)
                             "borrar_material": "/cliente/acme/ediciones/materiales/__ID__/borrar"}
    assert datos["estimado_s"] >= 20 and datos["cf_id"] is None
    assert [a[1] for a, _k in encolados] == ["edicion_proxy"]
    assert encolados[0][0][2] == {"cliente": "acme", "material_id": clon["id"]}


def test_el_cliente_del_proyecto_entra_y_los_demas_no(dashboard, encolados):
    ed, _c, _v = _edicion()
    assert _cliente(dashboard, "user_acme", "acme").get(f"/cliente/acme/ediciones/{ed['id']}").status_code == 200
    ajeno = _cliente(dashboard, "otro", "otro").get(f"/cliente/acme/ediciones/{ed['id']}")
    assert ajeno.status_code == 302 and "/cliente/acme/" not in ajeno.headers["Location"]
    anonimo = dashboard.app.test_client().get(f"/cliente/acme/ediciones/{ed['id']}")
    assert anonimo.status_code == 302 and anonimo.headers["Location"].endswith("/login")


def test_edicion_inexistente_o_de_otro_proyecto_es_404(dashboard, encolados):
    ed, _c, _v = _edicion()
    assert _cliente_admin(dashboard).get("/cliente/acme/ediciones/999").status_code == 404
    assert _cliente_admin(dashboard).get("/cliente/acme/ediciones/999/materiales").status_code == 404
    assert _cliente_admin(dashboard).get(f"/cliente/otro/ediciones/{ed['id']}").status_code == 404


def test_json_de_materiales_deja_de_pedir_el_proxy_cuando_existe(dashboard, encolados):
    import db
    from tareas import edicion
    ed, clon, _v = _edicion()
    with db.conectar() as con:
        con.execute(db.material.update().where(db.material.c.id == clon["id"]).values(
            url_proxy="https://r2.test/clon_proxy.mp4", extra={"proxy_version": edicion.PROXY_VERSION}))
    j = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}/materiales").get_json()
    assert j["pendientes"] == []
    assert j["materiales"][str(clon["id"])]["url_proxy"] == "https://r2.test/clon_proxy.mp4"


def test_modulos_del_editor_se_revalidan_siempre(dashboard):
    r = dashboard.app.test_client().get("/static/editor/formatos.js")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-cache"


def _doc_valido(clon_id):
    from final_edition import documento
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "v0", "inicio_ms": 0, "duracion_ms": 3000, "material_id": clon_id,
                                  "recorte": {"desde_ms": 0, "hasta_ms": 3000}}]
    return doc


def test_guardar_acepta_la_version_vigente_y_devuelve_la_siguiente(dashboard, encolados):
    import ediciones
    ed, clon, _v = _edicion()
    c = _cliente_admin(dashboard)
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": _doc_valido(clon["id"]), "version_n": ed["version_n"]})
    assert r.status_code == 200 and r.get_json() == {"version_n": ed["version_n"] + 1}
    assert ediciones.cargar("acme", ed["id"])["documento"]["pistas"][0]["clips"][0]["duracion_ms"] == 3000
    viejo = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": _doc_valido(clon["id"]), "version_n": ed["version_n"]})
    assert viejo.status_code == 409 and "otra pestaña" in viejo.get_json()["error"]


def test_guardar_rechaza_documentos_invalidos_y_materiales_ajenos(dashboard, encolados):
    import materiales
    ed, clon, _v = _edicion()
    c = _cliente_admin(dashboard)
    malo = _doc_valido(clon["id"])
    malo["pistas"][0]["clips"][0]["inicio_ms"] = 500                     # la principal debe arrancar en 0
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": malo, "version_n": ed["version_n"]})
    # capa 4c (5/10): la persona lee una frase llana; la ruta del validador va
    # aparte (`detalle`, el editor la pone en el `title` del estado)
    assert r.status_code == 400
    assert r.get_json()["error"] == "No se pudo guardar este cambio; deshazlo y vuelve a intentar."
    assert "contigua" in r.get_json()["detalle"] and "pistas[" in r.get_json()["detalle"]
    ajeno = materiales.registrar("otro", tipo="video", origen="crear", url="https://r2.test/x.mp4", hash="h-ajeno", bytes=1)
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": _doc_valido(ajeno["id"]), "version_n": ed["version_n"]})
    assert r.status_code == 400 and "no son de este proyecto" in r.get_json()["error"]
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": "nada", "version_n": "x"})
    assert r.status_code == 400


def test_guardar_con_una_forma_rara_responde_400_y_no_500(dashboard, encolados):
    import ediciones
    ed, clon, _v = _edicion()
    c = _cliente_admin(dashboard)
    url = f"/cliente/acme/ediciones/{ed['id']}"
    for romper in (lambda doc: doc.__setitem__("pistas", [1]),
                   lambda doc: doc["pistas"][0].__setitem__("clips", "abc"),
                   lambda doc: doc.__setitem__("subtitulos", "x"),
                   lambda doc: doc.__setitem__("marca", "x")):
        doc = _doc_valido(clon["id"])
        romper(doc)
        r = c.put(url, json={"documento": doc, "version_n": ed["version_n"]})
        assert r.status_code == 400 and r.get_json() == {"error": "El documento no tiene la forma esperada."}
    doc = _doc_valido(clon["id"])
    doc["marca"] = None                                          # null explícito: la marca por defecto
    r = c.put(url, json={"documento": doc, "version_n": ed["version_n"]})
    assert r.status_code == 200
    assert ediciones.cargar("acme", ed["id"])["documento"]["marca"]["color"] == "#7c3aed"


def test_guardar_exige_mismo_origen_y_acceso(dashboard, encolados):
    ed, clon, _v = _edicion()
    cuerpo = {"documento": _doc_valido(clon["id"]), "version_n": ed["version_n"]}
    r = _cliente_admin(dashboard).put(f"/cliente/acme/ediciones/{ed['id']}", json=cuerpo, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = _cliente(dashboard, "otro", "otro").put(f"/cliente/acme/ediciones/{ed['id']}", json=cuerpo)
    assert r.status_code == 302
    r = _cliente_admin(dashboard).put("/cliente/acme/ediciones/999", json=cuerpo)
    assert r.status_code == 409


def test_guardar_rechaza_el_logo_de_marca_de_otro_proyecto(dashboard, encolados):
    # el logo puede llegar solo en marca.logo_material_id, sin ningún clip
    # que lo use — el chequeo de "materiales ajenos" tiene que verlo igual
    # (documento.validar lo deriva a doc["materiales"]).
    import ediciones
    import materiales
    ed, clon, _v = _edicion()
    c = _cliente_admin(dashboard)
    ajeno = materiales.registrar("otro", tipo="imagen", origen="marca", url="https://r2.test/logo.png",
                                  hash="h-logo-ajeno", bytes=1)
    doc = _doc_valido(clon["id"])
    doc["marca"]["logo_material_id"] = ajeno["id"]
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": doc, "version_n": ed["version_n"]})
    assert r.status_code == 400 and "no son de este proyecto" in r.get_json()["error"]
    assert ediciones.cargar("acme", ed["id"])["documento"]["marca"]["logo_material_id"] is None


def _edicion_con_pieza():
    import creative_flow
    import ediciones
    ed, clon, voz = _edicion()
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    import db
    with db.conectar() as con:
        con.execute(db.edicion.update().where(db.edicion.c.id == ed["id"]).values(cf_id=cf))
    return ediciones.cargar("acme", ed["id"]), cf


def test_producir_congela_la_version_y_encola_un_render_por_destino(dashboard, encolados):
    import ediciones
    ed, cf = _edicion_con_pieza()
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 200, r.get_json()
    cuerpo = r.get_json()
    assert cuerpo["producidas"] == [{"destino": "es_CO", "final_id": f"{cf}__es_CO", "encolada": True}]
    assert cuerpo["url"].endswith(f"#final?cf={cf}")
    (args, kw), = [(a, k) for a, k in encolados if a[1] == "edicion_producir"]
    version = ediciones.versiones("acme", ed["id"])[-1]
    assert args[2] == {"cliente": "acme", "edicion_id": ed["id"], "version_id": version["id"],
                       "final_id": f"{cf}__es_CO", "idioma": "es", "pais": "CO"}
    assert kw["max_intentos"] == 1 and kw["duracion_estimada"] >= 20 and kw["cliente"] == "acme"


def test_producir_pide_la_version_guardada_y_destinos_del_documento(dashboard, encolados):
    ed, _cf = _edicion_con_pieza()
    c = _cliente_admin(dashboard)
    url = f"/cliente/acme/ediciones/{ed['id']}/producir"
    assert c.post(url, json={"version_n": ed["version_n"] + 5, "destinos": ["es_CO"]}).status_code == 409
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": ["pt_BR"]}).status_code == 400
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": []}).status_code == 400
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": ["../x"]}).status_code == 400
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": ["es_CO"]},
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]


def test_producir_sin_pieza_de_crear_no_se_puede(dashboard, encolados):
    ed, _c, _v = _edicion()
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 400 and "video de Crear" in r.get_json()["error"]


def test_producir_avisa_los_textos_sin_traducir(dashboard, encolados):
    import ediciones
    ed, _cf = _edicion_con_pieza()
    doc = ed["documento"]
    doc["pistas"].append({"id": "p_texto", "tipo": "texto", "clips": [
        {"id": "t1", "inicio_ms": 0, "duracion_ms": 1000, "texto": {"variable": "hook"}, "estilo": {"fuente": "Inter-Bold"}}]})
    doc["variables"]["textos"] = {"hook": {"es_CO": "Hola"}}
    doc["variables"]["precios"] = {"en_US": 10}
    nuevo = ediciones.guardar("acme", ed["id"], doc, ed["version_n"])
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": nuevo, "destinos": ["es_CO", "en_US"]})
    assert r.status_code == 400
    assert any(p.startswith("en_US") for p in r.get_json()["problemas"])


def test_producir_no_repite_un_render_que_ya_corre(dashboard, encolados, monkeypatch):
    import trabajos
    ed, _cf = _edicion_con_pieza()
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: job_id.endswith("__producir"))   # el render del editor
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 200
    assert r.get_json()["producidas"][0]["encolada"] is False
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]


def test_producir_detecta_un_guardado_colado_antes_de_congelar(dashboard, encolados, monkeypatch):
    # Fix round 1 (Important): la ruta leía `version_n` una vez al comienzo y
    # solo mucho después llamaba a `ediciones.versionar`, que congelaba lo
    # que hubiera EN ESE MOMENTO en la fila — un autoguardado de otra pestaña
    # colado justo en el medio congelaba un documento que nunca pasó por la
    # validación de destinos, y la versión vieja no se rechazaba. Se simula
    # el autoguardado colado dentro de una función que la ruta llama DESPUÉS
    # del chequeo rápido en memoria pero ANTES de `ediciones.versionar`.
    import ediciones
    from final_edition import rutas_editor
    ed, _cf = _edicion_con_pieza()
    original = rutas_editor.vista_previa.destinos

    def _colado(doc):
        ediciones.guardar("acme", ed["id"], ed["documento"], ed["version_n"])
        return original(doc)

    monkeypatch.setattr(rutas_editor.vista_previa, "destinos", _colado)
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 409
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]
    assert ediciones.versiones("acme", ed["id"]) == []


def test_producir_valida_la_forma_del_cuerpo(dashboard, encolados):
    # Fix round 1 (Minor): un cuerpo sin JSON válido, sin version_n o sin
    # destinos daba 409 ("La edición cambió") en vez de un 400 claro, porque
    # `request.get_json(silent=True) or {}` convertía cualquier cosa rara en
    # `{}` y `cuerpo.get("version_n")` daba None, distinto de `ed["version_n"]`.
    ed, _cf = _edicion_con_pieza()
    c = _cliente_admin(dashboard)
    url = f"/cliente/acme/ediciones/{ed['id']}/producir"
    assert c.post(url, data="no es json", content_type="application/json").status_code == 400
    assert c.post(url, json={"destinos": ["es_CO"]}).status_code == 400             # falta version_n
    assert c.post(url, json={"version_n": ed["version_n"]}).status_code == 400      # falta destinos
    assert c.post(url, json={"version_n": True, "destinos": ["es_CO"]}).status_code == 400   # bool no es int
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": "es_CO"}).status_code == 400  # no es lista
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]


def test_editar_este_video_encola_la_preparacion_gratis(dashboard, encolados):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/desde/{cf}")
    # capa 4b (9/9): el &abrir=editor es lo que le dice a la pestaña que, al
    # ver la edición lista, entre directo al editor sin pasar por el detalle.
    assert r.status_code == 302 and r.headers["Location"].endswith(f"#final?cf={cf}&abrir=editor")
    (args, kw), = [(a, k) for a, k in encolados if a[1] == "edicion_desde_clon"]
    assert args[0] == f"acme__{cf}__editor" and args[2] == {"cliente": "acme", "cf_id": cf}
    assert kw["max_intentos"] == 2 and kw["cliente"] == "acme"


def test_editar_este_video_rechaza_piezas_sin_video_y_otro_origen(dashboard, encolados):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/desde/{cf}")
    assert r.status_code == 302 and r.headers["Location"].endswith("#final")
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/desde/{cf}", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert not [a for a, _k in encolados if a[1] == "edicion_desde_clon"]


def test_el_editor_de_una_pieza_vuelve_a_esa_pieza(dashboard, encolados):
    ed, cf = _edicion_con_pieza()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    assert f'href="/cliente/acme#final?cf={cf}"' in html     # «← Final edition» abre esa pieza
    assert _datos(html)["cf_id"] == cf                         # con pieza, «Producir» queda habilitado


def _nada_creado(ed, cf, encolados):
    import creative_flow
    import ediciones
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]
    assert ediciones.versiones("acme", ed["id"]) == []
    return creative_flow.final_por_legado("acme", f"{cf}__es_CO")


def test_producir_revisa_los_recortes_antes_de_congelar(dashboard, encolados):
    # El render falla si un clip pide más material del que hay: la ruta lo
    # revisa con compilador.verificar_recortes (duraciones de los materiales
    # de ESTE proyecto) antes de congelar ni crear la final.
    import ediciones
    ed, cf = _edicion_con_pieza()
    doc = ed["documento"]
    doc["pistas"][0]["clips"][0].update(duracion_ms=9000, recorte={"desde_ms": 0, "hasta_ms": 9000})   # el clon dura 8000
    nuevo = ediciones.guardar("acme", ed["id"], doc, ed["version_n"])
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": nuevo, "destinos": ["es_CO"]})
    assert r.status_code == 400
    j = r.get_json()
    assert j["error"] == "Esta edición no se puede producir así:"
    assert j["problemas"] == ["es_CO: El clip 'v0' pide 9000 ms de un material de 8000 ms; acorta el clip o el recorte."]
    assert _nada_creado(ed, cf, encolados) is None


def test_producir_no_pisa_una_final_con_voz_que_se_esta_produciendo(dashboard, encolados, monkeypatch):
    import trabajos
    from tareas import final_edition as tareas_fe
    ed, cf = _edicion_con_pieza()
    pagada = tareas_fe.job_id_final("acme", cf, "es", "CO")
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: job_id == pagada)
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 409
    assert r.get_json() == {"error": "Esa final se está produciendo con voz; espera a que termine."}
    assert _nada_creado(ed, cf, encolados) is None


def _final_con_video(cf, capas=None):
    import creative_flow
    final_id = creative_flow.crear_final("acme", cf, "es", "CO")
    creative_flow.actualizar_final("acme", final_id, estado="listo", url_video="https://r2.test/final.mp4",
                                   capas=capas or {"voz": {"estado": "ok", "costo_usd": 0.25}}, costo_usd=0.27)
    return final_id


def test_producir_pregunta_antes_de_reemplazar_una_final_hecha_por_otro_camino(dashboard, encolados):
    import creative_flow
    ed, cf = _edicion_con_pieza()
    final_id = _final_con_video(cf)                              # la de la vía automática: sin enlace a esta edición
    url = f"/cliente/acme/ediciones/{ed['id']}/producir"
    c = _cliente_admin(dashboard)
    r = c.post(url, json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 409
    j = r.get_json()
    assert j["reemplazos"] == ["es_CO"] and j["error"]
    f = _nada_creado(ed, cf, encolados)
    assert f["estado"] == "listo" and f["capas"]["voz"]["costo_usd"] == 0.25 and f["costo_usd"] == 0.27   # intacta
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": ["es_CO"], "reemplazar": "sí"}).status_code == 409
    r = c.post(url, json={"version_n": ed["version_n"], "destinos": ["es_CO"], "reemplazar": True})
    assert r.status_code == 200 and r.get_json()["producidas"][0]["encolada"] is True
    assert creative_flow.final_por_legado("acme", final_id)["estado"] == "generando"


def test_producir_reemplaza_sin_preguntar_la_final_de_esta_misma_edicion(dashboard, encolados):
    import ediciones
    ed, cf = _edicion_con_pieza()
    final_id = _final_con_video(cf)
    ediciones.apuntar_final("acme", final_id, ediciones.versionar("acme", ed["id"], "producir")["id"])
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 200, r.get_json()


def test_producir_pregunta_si_la_final_salio_de_otra_edicion(dashboard, encolados):
    import ediciones
    ed, cf = _edicion_con_pieza()
    otra = ediciones.crear("acme", "video", "Otra", ed["documento"], cf_id=cf)
    final_id = _final_con_video(cf)
    ediciones.apuntar_final("acme", final_id, ediciones.versionar("acme", otra["id"], "producir")["id"])
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 409 and r.get_json()["reemplazos"] == ["es_CO"]


def test_producir_sin_video_previo_no_pregunta(dashboard, encolados):
    import creative_flow
    ed, cf = _edicion_con_pieza()
    final_id = creative_flow.crear_final("acme", cf, "es", "CO")
    creative_flow.actualizar_final("acme", final_id, estado="error", error="falló")   # nunca tuvo video
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 200


def test_el_dialogo_de_producir_no_promete_voz_ni_musica(dashboard, encolados):
    ed, _cf = _edicion_con_pieza()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    assert "ya están hechos" not in html
    assert "Es gratis" in html and "lo que hay en esta edición" in html
    assert "Reemplazar y producir" in html


# --- Disposición tipo CapCut (capa 4b, Task 4) ---

_VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def _ancestros(html):
    """{id: [ids de sus ancestros, del más cercano al más lejano]}."""
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.pila, self.out = [], {}

        def handle_starttag(self, tag, attrs):
            ident = dict(attrs).get("id")
            if ident:
                self.out[ident] = [i for _t, i in reversed(self.pila) if i]
            if tag not in _VACIOS:
                self.pila.append((tag, ident))

        def handle_endtag(self, tag):
            for k in range(len(self.pila) - 1, -1, -1):
                if self.pila[k][0] == tag:
                    del self.pila[k:]
                    break

    p = _P()
    p.feed(html)
    return p.out


def test_la_pagina_tiene_la_disposicion_de_capcut(dashboard, encolados):
    ed, _c, _v = _edicion()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    arbol = _ancestros(html)
    # barra de arriba: volver, nombre, destino, guardado y Producir
    for ident in ("destino", "estado-guardado", "recargar", "producir"):
        assert "ed-barra" in arbol[ident], ident
    # fila del medio: biblioteca | reproductor | propiedades
    for ident in ("ed-biblioteca", "ed-centro", "ed-propiedades"):
        assert "ed-cuerpo" in arbol[ident], ident
    assert "ed-biblioteca" in arbol["ed-pestanas-biblioteca"] and "ed-biblioteca" in arbol["ed-panel-biblioteca"]
    assert "ed-propiedades" in arbol["ed-panel-propiedades"]
    assert arbol["lienzo"][0] == "ed-escenario" and "ed-centro" in arbol["ed-escenario"]
    for ident in ("reproducir", "inicio", "tiempo", "barra", "aviso-edicion", "producir-hecho"):
        assert "ed-centro" in arbol[ident], ident
    # abajo, a todo el ancho: herramientas y línea de tiempo (fuera de la fila del medio)
    for ident in ("h-deshacer", "h-rehacer", "h-cortar", "h-borrar", "h-duplicar", "linea-zoom"):
        assert "ed-herramientas" in arbol[ident], ident
    # la velocidad ya no está en la barra: es del formulario del video, en «Editar»
    # (propiedades.js lo arma y conserva el id h-velocidad)
    assert 'id="h-velocidad"' not in html
    assert "ed-cuerpo" not in arbol["ed-herramientas"] and "ed-cuerpo" not in arbol["linea"]
    # la biblioteca: cuatro pestañas con su icono
    pestanas = re.search(r'id="ed-pestanas-biblioteca".*?</div>', html, re.S).group(0)
    for panel in ("medios", "audio", "texto", "transiciones"):
        boton = re.search(rf'<button[^>]*data-panel="{panel}"[^>]*>(.*?)</button>', pestanas, re.S)
        assert boton and "<svg" in boton.group(1), panel
    assert pestanas.count('aria-selected="true"') == 1
    # propiedades: el estado vacío
    assert "Elige algo en la línea de tiempo o en el video para cambiarlo." in html
    # celular: hojas que se abren desde abajo y se cierran con «Listo»
    for ident, hoja in (("ed-abrir-medios", "ed-biblioteca"), ("ed-abrir-propiedades", "ed-propiedades")):
        boton = re.search(rf'<button[^>]*id="{ident}"[^>]*>', html).group(0)
        assert f'aria-controls="{hoja}"' in boton and 'aria-expanded="false"' in boton, ident
    for hoja in ("ed-biblioteca", "ed-propiedades"):
        cerrar = re.search(rf'<button[^>]*data-cerrar-hoja="{hoja}"[^>]*>\s*Listo\s*</button>', html)
        assert cerrar, hoja
    # CSS: la columna del centro puede achicarse (nada empuja la página de lado)
    # y en el celular el reproductor ocupa como mucho 42vh
    assert "minmax(0, 1fr)" in html and "42vh" in html
    assert "@media (max-width: 760px)" in html


def test_las_pestanas_de_la_biblioteca_dicen_su_nombre(dashboard, encolados):
    """Task 6: en una columna de 220–300 px «Transiciones» no cabía y se cortaba
    («Me…», «Au…»; ni siquiera la elegida sola cabía a 800 px): las pestañas van
    solo con el icono, el nombre para el lector de pantalla (visualmente oculto,
    no borrado) y en el cartelito (`title`); el panel abierto lo dice en su título
    (biblioteca.js), y con lugar (la hoja ancha del celular) se ven los nombres."""
    ed, _c, _v = _edicion()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    pestanas = re.search(r'id="ed-pestanas-biblioteca".*?</div>', html, re.S).group(0)
    for panel, nombre in (("medios", "Medios"), ("audio", "Audio"), ("texto", "Texto"), ("transiciones", "Transiciones")):
        boton = re.search(rf'<button[^>]*data-panel="{panel}"[^>]*>(.*?)</button>', pestanas, re.S)
        assert boton and f'title="{nombre}"' in boton.group(0) and f"<span>{nombre}</span>" in boton.group(1), panel
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    oculta = re.search(r'\.ed-pestanas \.ed-pestana span \{([^}]*)\}', css)
    assert oculta and "clip-path: inset(50%)" in oculta.group(1) and "display: none" not in oculta.group(1)
    assert re.search(r"@container ed-pestanas \(min-width: \d+px\)", css), "con lugar, los nombres se ven"
    # la biblioteca la arma biblioteca.js dentro de su panel; la marca de una unión con transición, la línea
    assert "#ed-panel-biblioteca [hidden]" in css and ".ed-union {" in css


def test_ningun_ancho_queda_sin_disposicion(dashboard, encolados):
    """Fix 1 de la Task 4: `(min-width: 761px)` + `(max-width: 760px)` dejaban
    sin regla los 760,x px (zoom del navegador) y el reproductor medía 0×0. El
    escritorio es el complemento EXACTO del celular y el escenario tiene ancho
    fuera de toda media query."""
    ed, _c, _v = _edicion()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    consultas = re.findall(r"@media\s*([^{]+?)\s*\{", css)
    anchos = [c for c in consultas if "width" in c]
    assert sorted(anchos) == ["(max-width: 760px)", "not all and (max-width: 760px)"], anchos
    base = css[:css.index("@media")]
    regla = re.search(r"\.ed-escenario\s*\{([^}]*)\}", base)
    assert regla and re.search(r"(?<![-\w])width\s*:", regla.group(1)), "el escenario necesita ancho sin media query"


def test_el_estado_del_guardado_no_mueve_la_barra_en_el_celular(dashboard, encolados):
    """Fix final 7: en el celular «Guardado» → «Cambios sin guardar…» cambiaba el
    ancho del texto, la barra de arriba se volvía a acomodar en otra fila y el
    reproductor saltaba. El estado va en un hueco de ancho fijo, en una línea,
    con «…» si no cabe; el texto entero queda en el `title` (el error largo)."""
    ed, _c, _v = _edicion()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    celular = css[css.index("@media (max-width: 760px)"):]
    regla = re.search(r"\.ed-guardado \{([^}]*)\}", celular)
    assert regla, "falta la regla del celular para .ed-guardado"
    for decl in ("flex: none", "white-space: nowrap", "overflow: hidden", "text-overflow: ellipsis"):
        assert decl in regla.group(1), decl
    assert re.search(r"(?<![-\w])width:\s*[\d.]+(em|rem|px)", regla.group(1)), "el hueco necesita un ancho fijo"
    js = open(os.path.join(RAIZ, "static", "editor", "pagina_editor.js"), encoding="utf-8").read()
    pintar = re.search(r"function pintarGuardado\(estado, mensaje[^)]*\) \{(.*?)\n\}", js, re.S).group(1)
    assert "n.title = " in pintar


def test_el_escenario_sabe_la_proporcion_del_formato(dashboard, encolados):
    ed, _c, _v = _edicion()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    escenario = re.search(r'<div[^>]*id="ed-escenario"[^>]*>', html).group(0)
    assert "--ed-ancho: 1080" in escenario and "--ed-alto: 1920" in escenario


# --- Biblioteca del editor (capa 4b, Task 1) ---

def test_subir_material_delega_en_la_biblioteca(dashboard, encolados, monkeypatch):
    from final_edition import rutas_editor
    llamadas = []
    monkeypatch.setattr(rutas_editor.biblioteca, "subir",
                        lambda cliente, archivo: llamadas.append((cliente, archivo.filename)) or {"id": 9, "tipo": "video"})
    c = _cliente_admin(dashboard)
    r = c.post("/cliente/acme/ediciones/materiales/subir", data={"archivo": (io.BytesIO(b"x"), "clip.mp4")},
              content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json() == {"material": {"id": 9, "tipo": "video"}}
    assert llamadas == [("acme", "clip.mp4")]


def test_subir_material_responde_400_en_subida_invalida(dashboard, encolados, monkeypatch):
    from final_edition import biblioteca
    from final_edition import rutas_editor

    def _falla(cliente, archivo):
        raise biblioteca.SubidaInvalida("Sube un video, una imagen o un audio.")
    monkeypatch.setattr(rutas_editor.biblioteca, "subir", _falla)
    r = _cliente_admin(dashboard).post("/cliente/acme/ediciones/materiales/subir",
                                       data={"archivo": (io.BytesIO(b"MZ"), "virus.exe")},
                                       content_type="multipart/form-data")
    assert r.status_code == 400 and "video, una imagen o un audio" in r.get_json()["error"]


def test_subir_material_exige_archivo_y_mismo_origen(dashboard, encolados):
    c = _cliente_admin(dashboard)
    r = c.post("/cliente/acme/ediciones/materiales/subir", data={}, content_type="multipart/form-data")
    assert r.status_code == 400
    r = c.post("/cliente/acme/ediciones/materiales/subir", data={"archivo": (io.BytesIO(b"x"), "a.mp4")},
              content_type="multipart/form-data", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_biblioteca_devuelve_lo_que_arma_el_modulo(dashboard, encolados, monkeypatch):
    from final_edition import rutas_editor
    esperado = {"materiales": [{"id": 1}], "piezas": [{"cf_id": "cf_1"}]}
    monkeypatch.setattr(rutas_editor.biblioteca, "listar", lambda cliente: esperado if cliente == "acme" else None)
    r = _cliente_admin(dashboard).get("/cliente/acme/ediciones/biblioteca")
    assert r.status_code == 200 and r.get_json() == esperado


def _pieza_lista(dashboard_cliente="acme", tipo=None):
    import creative_flow
    cf = creative_flow.crear(dashboard_cliente, [], ["Espejo LED"], [], "gira", 8, "", "A")
    creative_flow.actualizar(dashboard_cliente, cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    if tipo:
        creative_flow.actualizar(dashboard_cliente, cf, tipo=tipo)
    return cf


def test_agregar_pieza_encola_la_preparacion_si_no_es_material(dashboard, encolados):
    cf = _pieza_lista()
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/biblioteca/pieza/{cf}")
    assert r.status_code == 202 and r.get_json() == {"preparando": True}
    (args, kw), = [(a, k) for a, k in encolados if a[1] == "material_de_pieza"]
    assert args[0] == f"acme__{cf}__material" and args[2] == {"cliente": "acme", "cf_id": cf}
    assert kw["max_intentos"] == 2 and kw["cliente"] == "acme"


def test_agregar_pieza_devuelve_el_material_si_ya_existe(dashboard, encolados):
    import materiales
    cf = _pieza_lista()
    mat = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2/clon.mp4", hash="h-clon",
                               bytes=1, extra={"cf_id": cf})
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/biblioteca/pieza/{cf}")
    assert r.status_code == 200 and r.get_json()["material"]["id"] == mat["id"]
    assert not [a for a, _k in encolados if a[1] == "material_de_pieza"]


def test_agregar_pieza_rechaza_id_invalido_ajena_o_no_lista(dashboard, encolados):
    c = _cliente_admin(dashboard)
    assert c.post("/cliente/acme/ediciones/biblioteca/pieza/../x").status_code == 404
    assert c.post("/cliente/acme/ediciones/biblioteca/pieza/cf_no_existe").status_code == 404
    import creative_flow
    sin_video = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    assert c.post(f"/cliente/acme/ediciones/biblioteca/pieza/{sin_video}").status_code == 404
    cf_imagen = _pieza_lista(tipo="imagen")
    assert c.post(f"/cliente/acme/ediciones/biblioteca/pieza/{cf_imagen}").status_code == 404
    r = c.post(f"/cliente/acme/ediciones/biblioteca/pieza/{_pieza_lista()}", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert not [a for a, _k in encolados if a[1] == "material_de_pieza"]


def test_materiales_por_id_solo_los_de_este_proyecto(dashboard, encolados):
    import materiales
    propio = materiales.registrar("acme", tipo="video", origen="subida", url="https://r2/a.mp4", hash="h-a", bytes=1)
    ajeno = materiales.registrar("otro", tipo="video", origen="subida", url="https://r2/b.mp4", hash="h-b", bytes=1)
    r = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/materiales?ids={propio['id']},{ajeno['id']},999")
    j = r.get_json()
    assert r.status_code == 200 and set(j["materiales"]) == {str(propio["id"])}
    assert j["materiales"][str(propio["id"])]["url"] == "https://r2/a.mp4"


def test_materiales_por_id_prepara_lo_pedido_que_falta(dashboard, encolados):
    """Fix final 11: una canción de Mi música (audio sin picos) agregada desde la
    biblioteca nunca tenía onda: nadie encolaba su edicion_proxy. Con
    `preparar=<ids>` la ruta encola (gratis, el mismo job que `ver`) solo lo que
    de esos ids todavía falta: audios sin picos y videos sin copia liviana."""
    import materiales
    from tareas import edicion as te
    cancion = materiales.registrar("acme", tipo="audio", origen="musica", url="https://r2/c.mp3", hash="h-c", bytes=1,
                                   duracion_ms=60000)
    listo = materiales.registrar("acme", tipo="audio", origen="subida", url="https://r2/d.mp3", hash="h-d", bytes=1,
                                 duracion_ms=3000, extra={"picos": [0.1, 0.2]})
    ajeno = materiales.registrar("otro", tipo="audio", origen="musica", url="https://r2/e.mp3", hash="h-e", bytes=1)
    c = _cliente_admin(dashboard)
    ids = f"{cancion['id']},{listo['id']},{ajeno['id']}"
    # sin `preparar` solo se lee (lo que la biblioteca pregunta cada 3 s)
    assert c.get(f"/cliente/acme/ediciones/materiales?ids={ids}").status_code == 200
    assert encolados == []
    r = c.get(f"/cliente/acme/ediciones/materiales?ids={ids}&preparar={ids}")
    assert r.status_code == 200 and set(r.get_json()["materiales"]) == {str(cancion["id"]), str(listo["id"])}
    assert [(a[0], a[1], a[2]) for a, _k in encolados] == [
        (te.job_id_proxy("acme", cancion["id"]), "edicion_proxy", {"cliente": "acme", "material_id": cancion["id"]})]
    assert encolados[0][1]["max_intentos"] == 3


@pytest.mark.slow
@pytest.mark.parametrize("subido_antes", [True, False])
def test_preparar_piezas_con_bytes_compartidos_resuelve_listado_y_post(
        dashboard, encolados, monkeypatch, tmp_path, subido_antes):
    import final_edition
    import materiales
    from final_edition import biblioteca, insumos
    from tareas import edicion as te
    from tests.test_biblioteca_editor import _mp4_bytes, _pieza_lista as crear_pieza
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(te, "_carpeta", lambda *args: str(tmp_path / "preparar"))
    monkeypatch.setattr(insumos.cortes, "detectar_cortes", lambda *args: [])
    subidas = []
    monkeypatch.setattr(materiales.r2_uploader, "upload_file",
                        lambda *args: subidas.append(args) or "https://r2.test/subido.mp4")
    datos = _mp4_bytes(tmp_path)
    local = tmp_path / "crudo.mp4"
    local.write_bytes(datos)
    c = _cliente_admin(dashboard)
    mid = None
    if subido_antes:
        r = c.post("/cliente/acme/ediciones/materiales/subir",
                   data={"archivo": (io.BytesIO(datos), "Mi original.mp4")})
        assert r.status_code == 200
        mid = r.get_json()["material"]["id"]
        materiales.actualizar_extra("acme", mid, propio={"conservar": True})
    piezas = [crear_pieza(nombre=nombre, video_local_crudo=str(local))
              for nombre in ("Primera pieza", "Segunda pieza")]
    for cf in piezas:
        url = f"/cliente/acme/ediciones/biblioteca/pieza/{cf}"
        assert c.post(url).status_code == 202
        te.ejecutar_material_de_pieza({"payload": {"cliente": "acme", "cf_id": cf}})
        listado = c.get("/cliente/acme/ediciones/biblioteca").get_json()
        por_cf = {p["cf_id"]: p for p in listado["piezas"]}
        preparado = por_cf[cf]["material_id"]
        assert preparado is not None
        mid = mid or preparado
        assert preparado == mid
        n = len(encolados)
        repetido = c.post(url)
        assert repetido.status_code == 200
        assert repetido.get_json()["material"]["id"] == mid
        assert len(encolados) == n
    assert {p["material_id"] for p in biblioteca.listar("acme")["piezas"]} == {mid}
    mat = materiales.obtener("acme", mid)
    assert mat["origen"] == ("subida" if subido_antes else "crear")
    assert mat["extra"]["nombre"] == ("Mi original" if subido_antes else "Primera pieza")
    if subido_antes:
        assert mat["extra"]["propio"] == {"conservar": True}
    else:
        assert mat["extra"]["cf_id"] == piezas[0]
    assert biblioteca.material_de_pieza("otro", piezas[0]) is None
    assert len(subidas) == int(subido_antes)


@pytest.mark.parametrize("nombre", ["audio.mp4", pytest.param("silencioso.mp3", marks=pytest.mark.slow)])
def test_subida_rechaza_stream_equivocado_antes_de_subir_o_encolar(
        dashboard, encolados, monkeypatch, tmp_path, nombre):
    import final_edition
    import materiales
    from tests.test_biblioteca_editor import _wav_bytes, _mp4_bytes
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    subidas = []
    monkeypatch.setattr(materiales.r2_uploader, "upload_file",
                        lambda *args: subidas.append(args) or "https://r2.test/incorrecto")
    datos = _wav_bytes() if nombre.endswith("mp4") else _mp4_bytes(tmp_path)
    r = _cliente_admin(dashboard).post("/cliente/acme/ediciones/materiales/subir",
                                       data={"archivo": (io.BytesIO(datos), nombre)})
    assert r.status_code == 400
    assert r.get_json()["error"]
    assert not subidas and not encolados
    assert materiales.bytes_usados("acme") == 0
    assert list((tmp_path / "clientes/acme/tmp_editor").iterdir()) == []


def test_el_panel_de_propiedades_cabe_y_lo_arma_su_modulo(dashboard, encolados):
    """Task 7 (capa 4b): el panel de la derecha lo arma static/editor/propiedades.js
    dentro de #ed-panel-propiedades (un formulario por clase de clip; sin nada
    elegido, la mezcla de la edición). La página trae sus estilos: todo se
    envuelve o se achica (nada empuja la columna ni la hoja de lado)."""
    ed, _c, _v = _edicion()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    assert "#ed-panel-propiedades [hidden]" in css
    for regla in (".ed-prop {", ".ed-prop-campo {", ".ed-prop-fila {", ".ed-prop-colores {", ".ed-prop-acciones {"):
        assert regla in css, regla
    campo = re.search(r"\.ed-prop-campo \{([^}]*)\}", css).group(1)
    assert "min-width: 0" in campo
    assert re.search(r"\.ed-prop input\[type=\"range\"\] \{[^}]*width: 100%", css)
    assert re.search(r"\.ed-prop-colores \{[^}]*flex-wrap: wrap", css)
    js = open(os.path.join(RAIZ, "static", "editor", "pagina_editor.js"), encoding="utf-8").read()
    assert 'import { Propiedades } from "./propiedades.js";' in js
    assert 'new Propiedades({ contenedor: $("ed-panel-propiedades"), editor' in js


def test_la_capa_para_tocar_el_video_cubre_el_lienzo(dashboard, encolados):
    """Task 8 (capa 4b): #ed-interaccion va dentro del escenario, encima del
    lienzo y del mismo tamaño; el dedo no mueve la página ahí, nada se sale de
    lado (la caja de una foto más grande que el video se corta) y la arma
    static/editor/lienzo_interaccion.js, que recibe la vista previa."""
    ed, _c, _v = _edicion()
    html = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}").get_data(as_text=True)
    arbol = _ancestros(html)
    assert arbol["ed-interaccion"][0] == "ed-escenario"
    assert html.index('id="lienzo"') < html.index('id="ed-interaccion"')        # encima del lienzo
    capa = re.search(r'<div[^>]*id="ed-interaccion"[^>]*>', html).group(0)
    assert 'aria-hidden="true"' in capa
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    regla = re.search(r"\.ed-interaccion \{([^}]*)\}", css).group(1)
    for decl in ("position: absolute", "inset: 0", "touch-action: none", "overflow: hidden"):
        assert decl in regla, decl
    for sel in (".ed-caja {", ".ed-asa {", ".ed-guia {"):
        assert sel in css, sel
    assert re.search(r"\.ed-caja \{[^}]*pointer-events: none", css)
    js = open(os.path.join(RAIZ, "static", "editor", "pagina_editor.js"), encoding="utf-8").read()
    assert 'import { InteraccionLienzo } from "./lienzo_interaccion.js";' in js
    assert 'new InteraccionLienzo({ escenario: $("ed-escenario"), lienzo: $("lienzo"), editor, vista });' in js


# ---- Capa 4c (8/10): borrar de la biblioteca ----

@pytest.fixture()
def r2_borrados(monkeypatch):
    import materiales
    borrados = []
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    return borrados


def _subida(nombre="foto", bytes_=1000, **campos):
    import materiales
    return materiales.registrar("acme", tipo="imagen", origen=campos.pop("origen", "subida"),
                                url=f"https://r2.test/clientes/acme/materiales/{nombre}.png", hash=f"h-{nombre}",
                                bytes=bytes_, ancho=10, alto=10, extra={"nombre": nombre}, **campos)


def test_borrar_de_la_biblioteca_un_archivo_sin_uso_libera_la_cuota(dashboard, encolados, r2_borrados):
    import materiales
    _edicion()
    foto = _subida(bytes_=5000)
    antes = materiales.bytes_usados("acme")
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/materiales/{foto['id']}/borrar")
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert materiales.obtener("acme", foto["id"]) is None
    assert materiales.bytes_usados("acme") == antes - 5000                    # la cuota descuenta
    assert r2_borrados == ["clientes/acme/materiales/foto.png"]


def test_borrar_un_video_de_crear_preparado_solo_quita_su_fila(dashboard, encolados, r2_borrados):
    import materiales
    _edicion()
    clon = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2.test/crear/pieza.mp4", hash="h-otro-clon",
                                bytes=10, duracion_ms=3000, extra={"cf_id": "cf1"})
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/materiales/{clon['id']}/borrar")
    assert r.status_code == 200 and materiales.obtener("acme", clon["id"]) is None
    assert r2_borrados == []                                                  # el video de la pieza no es suyo


def test_borrar_un_archivo_en_uso_dice_en_que_edicion(dashboard, encolados, r2_borrados):
    import materiales
    ed, clon, voz = _edicion()                                                # «Demo <editor>» usa el clon y la voz
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/materiales/{clon['id']}/borrar")
    assert r.status_code == 409
    assert r.get_json()["error"] == "Está en uso en la edición «Demo <editor>»: quítalo de ahí primero."
    assert materiales.obtener("acme", clon["id"]) and r2_borrados == []


def test_borrar_solo_lo_subido_o_lo_de_crear_de_este_proyecto(dashboard, encolados, r2_borrados):
    import materiales
    _edicion()
    c = _cliente_admin(dashboard)
    for origen in ("voz", "marca", "musica"):
        m = _subida(nombre=f"x-{origen}", origen=origen)
        r = c.post(f"/cliente/acme/ediciones/materiales/{m['id']}/borrar")
        assert r.status_code == 400 and "no se borra desde aquí" in r.get_json()["error"], origen
        assert materiales.obtener("acme", m["id"])
    ajeno = materiales.registrar("otro", tipo="imagen", origen="subida", url="https://r2.test/y.png", hash="h-y", bytes=1)
    assert c.post(f"/cliente/acme/ediciones/materiales/{ajeno['id']}/borrar").status_code == 404
    assert c.post("/cliente/acme/ediciones/materiales/abc/borrar").status_code == 404
    foto = _subida(nombre="lejos")
    assert c.post(f"/cliente/acme/ediciones/materiales/{foto['id']}/borrar",
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert materiales.obtener("acme", foto["id"])
    assert _cliente(dashboard, "otro", "otro").post(f"/cliente/acme/ediciones/materiales/{foto['id']}/borrar").status_code == 302


def test_una_cancion_de_mi_musica_no_se_borra_desde_el_editor(dashboard, encolados, r2_borrados):
    """Arreglo 3: las canciones de Mi música (subidas o creadas) también
    tienen origen «subida»; se reconocen por `extra.fuente` (mi_musica.py) y
    se borran solo en Crear › Mi música. La biblioteca lo sabe por
    `material_para(...)["mi_musica"]`."""
    import materiales
    from final_edition import vista_previa
    _edicion()
    cancion = materiales.registrar("acme", tipo="audio", origen="subida", url="https://r2.test/clientes/acme/materiales/c.mp3",
                                   hash="h-cancion", bytes=10, duracion_ms=60000, extra={"nombre": "Mi canción", "fuente": "subida"})
    audio = materiales.registrar("acme", tipo="audio", origen="subida", url="https://r2.test/clientes/acme/materiales/a.mp3",
                                 hash="h-audio", bytes=10, duracion_ms=2000, extra={"nombre": "whoosh"})
    assert vista_previa.material_para(cancion)["mi_musica"] is True
    assert vista_previa.material_para(audio)["mi_musica"] is False
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/ediciones/materiales/{cancion['id']}/borrar")
    assert r.status_code == 400 and "Mi música" in r.get_json()["error"]
    assert materiales.obtener("acme", cancion["id"]) and r2_borrados == []
    assert c.post(f"/cliente/acme/ediciones/materiales/{audio['id']}/borrar").status_code == 200

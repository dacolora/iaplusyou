"""Pantallas en inglés sin español visible (spec 2026-09-26 §Pruebas). Render
real: atrapa también los textos que vienen de Python (flash, nombres de
constantes, tarjetas de llaves). Cada tarea que traduce una pantalla agrega su
test aquí."""
import json
import re

import pytest

import idiomas
from tests.i18n_util import _con_marca, espanol_visible

CLAVES = [
    "ANTHROPIC_API_KEY", "FAL_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL", "META_APP_ID", "META_APP_SECRET", "SMTP_HOST",
    "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "PLATAFORMA_URL", "MELI_APP_ID", "MELI_SECRET", "ATRIA_API_KEY",
]


@pytest.fixture()
def app_i18n(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import dashboard
    import proyectos
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    for v in CLAVES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(dashboard.estado_mod, "listar_clientes", lambda: ["acme"])
    dashboard.app.config["TESTING"] = True
    return dashboard


def _cliente(dashboard, usuario, rol, cliente):
    idiomas.guardar_de_usuario(usuario, "en")
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = rol
        s["cliente"] = cliente
    return c


@pytest.fixture()
def admin_en(app_i18n):
    return _cliente(app_i18n, "admin", "admin", None)


@pytest.fixture()
def cliente_en(app_i18n):
    return _cliente(app_i18n, "user_acme", "cliente", "acme")


@pytest.fixture()
def publico_en(app_i18n):
    c = app_i18n.app.test_client()
    c.set_cookie(idiomas.COOKIE, "en")
    return c


def html_de(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def test_la_deteccion_funciona():
    html = '<div id="a"><p>Hello</p><input placeholder="Escribe aquí"></div><div id="b"><p>Guardar</p></div>'
    assert espanol_visible(html, ("a",)) == ["Escribe aquí"]
    assert espanol_visible(html) == ["Escribe aquí", "Guardar"]
    # Void element with matching id must have its attributes inspected
    assert espanol_visible('<input id="campo" placeholder="Escribe aquí">', ("campo",)) == ["Escribe aquí"]


def test_deteccion_exige_que_el_id_pedido_exista():
    # Un id renombrado (o que nunca existió) no debe pasar en silencio: sin
    # esto p.region terminaba en 0 tanto si el id se encontró y se cerró bien
    # como si nunca apareció, así que la guardia de una región nunca fallaba.
    with pytest.raises(AssertionError):
        espanol_visible('<div id="otro">x</div>', ("no-existe",))


@pytest.mark.parametrize("url", ["/", "/login", "/recuperar", "/privacidad", "/terminos", "/eliminar-datos"])
def test_publicas_en_ingles(publico_en, url):
    fugas = espanol_visible(html_de(publico_en, url))
    assert not fugas, f"{url}: {fugas[:15]}"


def test_restablecer_en_ingles(publico_en):
    import cuentas
    token = cuentas.emitir("restablecer", "admin", "admin@prueba.local")
    fugas = espanol_visible(html_de(publico_en, f"/restablecer/{token}"))
    assert not fugas, fugas[:15]


def test_panel_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/panel"))
    assert not fugas, fugas[:15]


def test_esqueleto_del_proyecto_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("sidebar", "barra-superior"))
    assert not fugas, fugas[:15]


def test_config_puesta_y_conexiones_admin(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("config-ap-puesta", "config-ap-conexiones"))
    assert not fugas, fugas[:15]


def test_config_conexiones_cliente(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("config-ap-conexiones",))
    assert not fugas, fugas[:15]


def test_configuracion_entera_admin(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-settings",))
    assert not fugas, fugas[:15]


def test_configuracion_entera_cliente(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("tab-settings",))
    assert not fugas, fugas[:15]


def test_bloqueo_cambio_forma_en_ingles_y_espanol_intacto(app_i18n, monkeypatch):
    """El aviso de _bloqueo_cambio_forma (Configuración > Meta, mostrado dentro
    de config-ap-conexiones vía _meta_conectar.html y en los flash de
    meta_forma/meta_agencia_salir) va con ngettext/gettext desde 6e5c9... — se
    prueba la función directo (más liviano que armar un experimento vivo de
    verdad + una publicación orgánica en_cola solo para renderizar la página):
    en español (sin catálogo) tiene que salir BYTE a byte igual que antes de
    envolverla, y en inglés no puede dejar ninguna marca de español."""
    monkeypatch.setattr(app_i18n.experimentos, "cargar", lambda cliente: [{"estado": "corriendo"}])
    monkeypatch.setattr(app_i18n.organico, "listar", lambda cliente: [{"estado": "en_cola"}, {"estado": "en_cola"}])

    with idiomas.en_idioma("es"):
        es = app_i18n._bloqueo_cambio_forma("acme")
    assert es == "Termina o cierra primero: 1 experimento vivo · 2 publicaciones en curso"

    with idiomas.en_idioma("en"):
        en = app_i18n._bloqueo_cambio_forma("acme")
    assert not _con_marca(en), en
    assert en == "Finish or close first: 1 live experiment · 2 posts in progress"

    # Un solo caso (singular real, no monkeypatch de una lista con un elemento
    # cualquiera) para que la concordancia "1 ... vivo" / "1 live experiment"
    # (sin la "s") quede probada de verdad, no solo el plural.
    monkeypatch.setattr(app_i18n.organico, "listar", lambda cliente: [])
    with idiomas.en_idioma("es"):
        es_singular = app_i18n._bloqueo_cambio_forma("acme")
    assert es_singular == "Termina o cierra primero: 1 experimento vivo"
    with idiomas.en_idioma("en"):
        en_singular = app_i18n._bloqueo_cambio_forma("acme")
    assert en_singular == "Finish or close first: 1 live experiment"


_ONSUBMIT_FORM_LOGO = re.compile(
    r'<form[^>]*action="[^"]*logos/[^"]*eliminar[^"]*"[^>]*onsubmit=([\'"])(.*?)\1', re.S)


def test_logo_quitar_onsubmit_bien_formado(app_i18n, tmp_path):
    """Regresión (task-6 fix round 1): `onsubmit="return confirm({{ ... |
    tojson }});"` con el atributo entre comillas dobles se rompe — tojson
    emite comillas dobles, que cierran el atributo a la mitad y el manejador
    nunca compila (ni el confirm sale, en ningún idioma). Con un logo
    presente, comprueba que el atributo va entre comillas simples y que
    adentro hay un `confirm("...")` con un string JSON válido, en español Y
    en inglés.

    OJO: `_tab_catalogo.html` tiene un panel «logo» DUPLICADO (mismo
    `eliminar_logo`, mismo `nombre`) con un `onsubmit` hardcodeado en español
    sin `tojson` — no forma parte de este bug (no usa tojson) y cliente.html
    renderiza las dos pestañas en la misma página, así que el texto sale dos
    veces; por eso se acota la búsqueda al recorte de `config-ap-marca`
    (Configuración › Marca), que es la única instancia que toca esta task."""
    carpeta = tmp_path / "clientes" / "acme" / "logos"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "logo1.png").write_bytes(b"fake-png")

    for idioma in ("es", "en"):
        idiomas.guardar_de_usuario("admin", idioma)
        c = app_i18n.app.test_client()
        with c.session_transaction() as s:
            s["usuario"] = "admin"
            s["rol"] = "admin"
            s["cliente"] = None
        html = html_de(c, "/cliente/acme")
        recorte = html[html.index('id="config-ap-marca"'):html.index('id="config-ap-generacion"')]
        m = _ONSUBMIT_FORM_LOGO.search(recorte)
        assert m, f"[{idioma}] no encontré el <form> de Quitar logo con onsubmit en Configuración > Marca"
        comillas, contenido = m.group(1), m.group(2)
        assert comillas == "'", f"[{idioma}] el atributo onsubmit debe ir con comillas simples: {contenido!r}"
        cm = re.fullmatch(r"return confirm\((\".*\")\);", contenido, re.S)
        assert cm, f"[{idioma}] onsubmit mal formado (falta confirm(...); dentro del mismo atributo): {contenido!r}"
        json.loads(cm.group(1))  # el argumento de confirm() tiene que ser un string JSON válido


def test_crear_desde_referencias_admin(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("crear-modos", "crear-modo-referencias"))
    assert not fugas, fugas[:15]


def test_crear_desde_referencias_cliente(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("crear-modos", "crear-modo-referencias"))
    assert not fugas, fugas[:15]


def test_crear_flowplus_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("crear-modo-flowplus",))
    assert not fugas, fugas[:15]


def test_panel_de_guiones_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme/guiones/panel"))
    assert not fugas, fugas[:15]


def test_panel_de_guiones_con_video_en_ingles(admin_en):
    """Fix round 1: `%(n)s palabras/s · hook: %(hook)s` (_gpg_video.html
    ~l.30) se armaba sin `_()` — «2.4 palabras/s · hook: original» salía
    igual en cualquier idioma. Necesita un video de verdad (con `config`)
    para ejercitar esa línea; `fixtures_guiones.video_nuevo` lo crea con la
    escritura real (`guiones.datos`), sin red ni Claude.

    Fix round 2: `espanol_visible` completo (ya no acotado a «palabras») —
    esa misma pantalla también mostraba `guiones.datos.nombre_version`
    («Completo · diálogo · v1», ahora `etiqueta_version` traducida para
    mostrar) y las etiquetas de `FORMATOS_NOMBRES` sin `|traducir` en
    `_gpg_macros.html` (p. ej. «Retrato 4:5 (feed de Instagram)»), ambas
    corregidas en ese round. `name="palabras_por_segundo"` (un campo de
    formulario interno) no cuenta como fuga porque `espanol_visible` ya
    excluye `name`/`id`/`value` — solo mira texto y los atributos
    `placeholder`/`title`/`aria-label`/`alt`."""
    import tests.fixtures_guiones as fx
    gid, vid = fx.video_nuevo("acme")
    html = html_de(admin_en, f"/cliente/acme/guiones/panel?guion={gid}&video={vid}")
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]


def test_guiones_rutas_error_en_ingles(admin_en):
    """guiones/rutas.py (el chat de prompts): un prompt vacío dispara
    refinador.DatoInvalido -> _error(e) -> {"error": str(e)}, ya en gettext
    desde la Task 3. Aquí solo se comprueba que sale en inglés (sin marcas de
    español) para quien mira la pantalla en inglés."""
    r = admin_en.post("/cliente/acme/guiones/prompts", json={"texto": ""})
    assert r.status_code == 400, r.get_data(as_text=True)
    error = r.get_json()["error"]
    assert not _con_marca(error), error
    assert error == "The prompt can't be empty."


def test_guiones_rutas_pipeline_error_en_ingles(admin_en):
    """guiones/rutas_pipeline.py: un lote sin texto dispara datos.crear_lote's
    DatoInvalido, ahora con gettext (Task 5)."""
    r = admin_en.post("/cliente/acme/guiones/lotes", json={"texto": ""})
    assert r.status_code == 400, r.get_data(as_text=True)
    error = r.get_json()["error"]
    assert not _con_marca(error), error
    assert error == "Paste the script first."


def test_etapas_del_trabajo_en_ingles(admin_en, app_i18n, monkeypatch):
    """`estado_trabajo` traduce etapa/mensaje/detalle al responder (spec Task 4):
    tareas/flowplus.py y tareas/director.py marcan sus etapas con N_, y el
    catálogo trae la traducción — sin tocar `trabajos.consultar` en sí."""
    import tareas.flowplus as tf
    monkeypatch.setattr(app_i18n.trabajos, "consultar",
                        lambda job_id: {"estado": "corriendo", "etapa": tf.ETAPA_MODELO, "mensaje": None,
                                        "detalle": None, "progreso": 10, "elapsed": 1, "progreso_real": False})
    datos = admin_en.get("/trabajo/x/estado").get_json()
    assert datos["etapa"] == "Generating with the model"


def test_etapas_del_trabajo_mensaje_vacio_sigue_vacio(admin_en, app_i18n, monkeypatch):
    """Fix ronda revisión final (finding 3a): `mensaje`/`detalle` en "" es
    habitual (nada que mostrar todavía) — `gettext("")` devolvería la cabecera
    del .po en vez de "", así que `estado_trabajo` usa `idiomas.traducir`, que
    deja vacío/None tal cual antes de llamar a gettext."""
    monkeypatch.setattr(app_i18n.trabajos, "consultar",
                        lambda job_id: {"estado": "corriendo", "etapa": None, "mensaje": "",
                                        "detalle": "", "progreso": 10, "elapsed": 1, "progreso_real": False})
    datos = admin_en.get("/trabajo/x/estado").get_json()
    assert datos["mensaje"] == "" and datos["detalle"] == ""


MISMO_ORIGEN = {"Sec-Fetch-Site": "same-origin"}


def test_catalogo_admin_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-catalogo",))
    assert not fugas, fugas[:15]


def test_catalogo_cliente_en_ingles(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("tab-catalogo",))
    assert not fugas, fugas[:15]


def test_flash_de_producto_en_ingles(admin_en):
    admin_en.post("/cliente/acme/productos/crear", data={"nombre": ""}, headers=MISMO_ORIGEN)
    assert "Give it a name." in html_de(admin_en, "/cliente/acme")


def test_flash_eliminar_imagen_inexistente_en_ingles(admin_en):
    """Fix round 1: catalogo_productos.eliminar_imagen() flasheaba sus 3
    mensajes en español crudo (nunca por gettext); una foto que no existe es
    el caso más simple de disparar uno de ellos desde la ruta. El apóstrofo de
    "couldn't" sale escapado como entidad HTML (autoescape de Jinja en el
    `{{ message }}` de base.html), como ya se compara en otros tests
    (tests/test_rutas_productos.py con "Cojín d&#39;Or")."""
    admin_en.post("/cliente/acme/productos/cualquier-id/imagenes/no-existe.jpg/eliminar",
                  data={"categoria": "producto"}, headers=MISMO_ORIGEN)
    assert "I couldn&#39;t find that image." in html_de(admin_en, "/cliente/acme")


def _experimento_sembrado():
    import experimentos
    return experimentos.crear("acme", "Summer test", [{"pais": "CO", "presupuesto_dia": 20000}], "OUTCOME_TRAFFIC",
                              7, 100000, "https://shop.example/p", "COP", atribucion="ninguna")


def test_experimentos_admin_en_ingles(admin_en):
    _experimento_sembrado()
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-experimentos",))
    assert not fugas, fugas[:15]


def test_experimentos_cliente_en_ingles(cliente_en):
    _experimento_sembrado()
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("tab-experimentos",))
    assert not fugas, fugas[:15]


def test_etiquetas_de_estado_en_ingles(admin_en):
    _experimento_sembrado()
    html = html_de(admin_en, "/cliente/acme")
    assert ">drafting<" in html and ">queued<" in html
    assert ">armando<" not in html and ">en_cola<" not in html


def test_flash_de_experimentos_en_ingles(admin_en):
    admin_en.post("/cliente/acme/experimentos/probar", data={}, headers=MISMO_ORIGEN)
    assert "Connect Meta in Settings before testing pieces." in html_de(admin_en, "/cliente/acme")


def test_experimentos_sin_valores_crudos_en_ingles(admin_en, app_i18n, monkeypatch):
    """Fix round 1, hallazgo 3: atribución (e.atribucion y el <select>), la
    acción de una propuesta pendiente (pr.accion), el tipo de una derivación
    (d.tipo) y el evento que crea una ruta (ev.tipo/ev.mensaje) son claves
    guardadas en español que espanol_visible/MARCAS NO detecta (ninguna
    palabra tiene tilde ni está en la lista de palabras frecuentes) — se
    comprueban a mano, palabra por palabra."""
    import experimentos as ex
    import propuestas
    # Proyecto también en inglés (app_i18n ya aisló proyectos.BASE_DIR en
    # tmp_path): lo guardado sigue al proyecto (spec 2026-09-26 §B3), así que
    # el evento de exp_crear solo sale en inglés si el proyecto también lo
    # está — igual que un equipo angloparlante con su proyecto en inglés.
    idiomas.guardar_de_proyecto("acme", "en")
    monkeypatch.setattr(app_i18n.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    # Ruta de verdad (exp_crear): deja el evento "creado" con "Experimento
    # creado con..." — el caso que el hallazgo pide comprobar explícitamente.
    admin_en.post("/cliente/acme/experimentos/nuevo", data={
        "nombre": "Test EN", "objetivo": "OUTCOME_TRAFFIC", "paises": ["CO"], "presupuesto_CO": "20000",
        "dias": "7", "tope_total": "100000", "destino_url": "https://shop.example/p", "atribucion": "ninguna",
    }, headers=MISMO_ORIGEN)
    eid = ex.cargar("acme")[0]["id"]
    propuestas.crear("acme", eid, "escalar", {"pais": "CO"}, "ganador")
    ex.actualizar("acme", eid, extra={"derivaciones": [
        {"id": "d1", "tipo": "rescatar", "estado": "produciendo", "origen_ep_id": None, "motivo": "", "items": []},
    ]})

    html = html_de(admin_en, "/cliente/acme")
    # atribución (tag del experimento + <select> Avanzado)
    assert "atribución ninguna" not in html and "attribution none" in html
    assert ">ninguna<" not in html
    # accion de la propuesta pendiente (tag + el confirm() de Aprobar)
    assert ">escalar<" not in html and ">scale<" in html
    # tipo de la derivación
    assert ">rescatar<" not in html and ">rescue<" in html
    # evento creado por la ruta (tipo + mensaje)
    assert ">creado<" not in html and ">created<" in html
    assert "Experimento creado" not in html and "Experiment created" in html


def test_tablero_en_ingles(admin_en, monkeypatch):
    import dashboard
    dashboard._TABLERO_CACHE.clear()
    monkeypatch.setattr(dashboard.db, "ahora", lambda: "2026-09-26T10:00:00")
    html = html_de(admin_en, "/cliente/acme")
    assert "Dashboard · September 2026" in html
    fugas = espanol_visible(html, ("tab-tablero",))
    assert not fugas, fugas[:15]


def test_tablero_no_mezcla_idiomas_en_la_cache(app_i18n, monkeypatch):
    app_i18n._TABLERO_CACHE.clear()
    monkeypatch.setattr(app_i18n.db, "ahora", lambda: "2026-09-26T10:00:00")
    c = app_i18n.app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = "admin", "admin", None
    assert "Tablero · septiembre 2026" in html_de(c, "/cliente/acme")
    idiomas.guardar_de_usuario("admin", "en")
    assert "Dashboard · September 2026" in html_de(c, "/cliente/acme")


def test_csv_del_tablero_con_encabezados_en_ingles(admin_en):
    texto = admin_en.get("/cliente/acme/tablero/mes.csv").get_data(as_text=True)
    assert texto.lstrip("﻿").splitlines()[0] == \
        "experiment;country;piece;verdict;impressions;clicks;spend;purchases;revenue;roas;currency"


def test_landing_en_el_idioma_del_proyecto(app_i18n, tmp_path, monkeypatch):
    import json
    import os
    monkeypatch.setattr(app_i18n, "BASE_DIR", str(tmp_path))
    os.makedirs(tmp_path / "clientes" / "acme", exist_ok=True)
    (tmp_path / "clientes" / "acme" / "landing.json").write_text(json.dumps(
        {"titulo": "Glow Serum", "descripcion": "Radiant skin in seven days.", "boton_url": "https://shop.example"}),
        encoding="utf-8")
    idiomas.guardar_de_proyecto("acme", "en")
    c = app_i18n.app.test_client()
    c.set_cookie(idiomas.COOKIE, "es")              # quien mira pidió español: manda el proyecto
    html = html_de(c, "/l/acme")
    assert '<html lang="en">' in html and ">Download →<" in html.replace("\n", "")
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]


def test_catalogo_producto_con_doctrina_en_ingles(admin_en):
    """Merge de main (doctrina, bloque 2): la ficha de un producto trae el
    selector de sofisticación, «Lo que Claude necesita» y las pruebas del
    producto (_catalogo_campos_comerciales.html, _producto_doctrina.html,
    _catalogo_lista.html). Datos sembrados en inglés."""
    import io

    import tiendas
    from doctrina import producto as doctrina_producto
    r = admin_en.post("/cliente/acme/productos/crear", headers=MISMO_ORIGEN, content_type="multipart/form-data",
                      data={"nombre": "Blue Cushion", "descripcion": "soft", "categoria": "producto", "volver": "catalogo",
                            "imagenes": (io.BytesIO(b"\xff\xd8\xff\xe0fake-jpg"), "a.jpg")})
    assert r.status_code == 302
    pid = tiendas.por_activo("acme")["blue_cushion"]["id"]
    admin_en.post(f"/cliente/acme/productos/{pid}/pruebas", data={"texto": "Filling of 1,200 g", "fuente": "ficha"},
                  headers=MISMO_ORIGEN)
    doctrina_producto.reemplazar_abiertos("acme", pid, [{"texto": "Paste a buyer review", "para_que": "proof"},
                                                         {"texto": "Tell us the warranty", "para_que": "figure"}])
    html = html_de(admin_en, "/cliente/acme")
    assert "Proof saved: Claude can now use it with this product." in html
    assert "What Claude needs" in html and "2 requests from Claude" in html and "Let Claude decide" in html
    fugas = espanol_visible(html, ("tab-catalogo",))
    assert not fugas, fugas[:15]


def test_experimentos_doctrina_en_ingles(admin_en):
    """Merge de main (doctrina, bloque 3): las constantes del aviso del paso 3
    salen en inglés (el marcado lo cubre test_experimentos_admin_en_ingles)."""
    html = html_de(admin_en, "/cliente/acme")
    assert "Doctrine: {n} to improve" in html
    assert "chosen pieces have points to improve according to the doctrine" in html


PRODUCTO_EN = {"id": "mirror", "nombre": "LED mirror", "descripcion": "round", "representativa_url": "https://r2/m.jpg",
               "regla": "Identical.", "referencias": []}
ANGULO_EN = {"audiencia": "people renovating their bathroom", "consciencia": "consciente_de_la_solucion",
             "sofisticacion": 2, "deseo": "a bathroom that looks new", "promesa": "your bathroom looks new with a new mirror",
             "mecanismo": None, "pruebas": [{"texto": "light built into the frame", "fuente": "ficha"}], "lead": "promesa",
             "gancho": "Light that wakes you up", "faltantes": ["error: cifra_no_verificada:47", "real buyer reviews"]}


def _sprint_sembrado(monkeypatch):
    import catalogo_productos
    from sprints import datos
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [PRODUCTO_EN])
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: PRODUCTO_EN)
    idiomas.guardar_de_proyecto("acme", "en")
    pid = datos.crear_persona("acme", "Premium buyer", resumen="Wants quality")
    sid = datos.crear_sprint("acme", "October", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "mirror", None, 2, 1)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="side light")
    datos.crear_idea("acme", cid, "video", "Sunrise mirror", "The camera circles the mirror.",
                     gancho=ANGULO_EN["gancho"], extra={"angulo": ANGULO_EN})
    return sid, cid, rid


def test_pestana_sprints_en_ingles(admin_en, monkeypatch):
    _sprint_sembrado(monkeypatch)
    html = html_de(admin_en, "/cliente/acme")
    fugas = espanol_visible(html, ("tab-sprints",))
    assert not fugas, fugas[:15]
    tab = html[html.index('id="tab-sprints"'):html.index('id="tab-catalogo"')]
    for clave in ("planeando", "referencias", "listo para generar"):   # claves crudas que MARCAS no detecta
        assert f">{clave}<" not in tab


@pytest.mark.parametrize("ruta", ["", "/campanas/{cid}", "/campanas/{cid}/panel", "/campanas/{cid}/piezas",
                                  "/campanas/{cid}/sugeridos", "/campanas/{cid}/tarjeta", "/revision", "/entrega"])
def test_paginas_de_sprint_en_ingles(admin_en, monkeypatch, ruta):
    sid, cid, _ = _sprint_sembrado(monkeypatch)
    html = html_de(admin_en, f"/cliente/acme/sprints/{sid}" + ruta.format(cid=cid))
    fugas = espanol_visible(html)
    assert not fugas, (ruta, fugas[:15])


def test_pagina_de_la_doctrina_en_ingles(admin_en):
    """Los textos de la doctrina quedan en español (spec §B4: instrucciones
    internas); se traduce todo lo demás de la página."""
    html = html_de(admin_en, "/cliente/acme/doctrina")
    fugas = espanol_visible(html, ("doctrina-cabecera", "doctrina-indice", "doctrina-pie"))
    assert not fugas, fugas[:15]

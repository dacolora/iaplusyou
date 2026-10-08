"""Pantallas en inglés sin español visible (spec 2026-09-26 §Pruebas). Render
real: atrapa también los textos que vienen de Python (flash, nombres de
constantes, tarjetas de llaves). Cada tarea que traduce una pantalla agrega su
test aquí."""
import json
import re

import pytest

import idiomas
from tests.conftest import JPG_VALIDO
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
    monkeypatch.setenv("CREATV_LOGS", str(tmp_path / "logs"))
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
    monkeypatch.setattr(app_i18n.experimentos, "contar_vivos", lambda cliente: 1)
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


FRAGMENTO = "/cliente/acme/experimentos/resultados"


def _experimento_con_pieza(base_temporal):
    """Un experimento con una pieza de video que ya gastó: el fragmento de resultados tiene tarjetas, tabla de ranking
    y evolución, y el panel de la pieza (`exp_pieza`) tiene algo que mostrar. Devuelve (eid, ep_id)."""
    import experimentos as ex
    from tests.test_experimentos_db import _pieza
    eid = _experimento_sembrado()
    pid = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.snapshot(ep, {"impresiones": 1000, "clics_enlace": 20, "gasto": 100.0, "ctr": 2.0, "cpc": 5.0})
    return eid, ep


def _meta_conectada(app_i18n, monkeypatch):
    """Con Meta conectada «Nuevo experimento» pinta sus pasos (sin conectar vuelve a la pestaña, desde 2026-10-08)."""
    monkeypatch.setattr(app_i18n.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})


def _urls_del_centro(eid, ep):
    """Dónde vive ahora lo que antes pintaba la pestaña de Experimentos: el fragmento (sin y con un experimento
    elegido, con un periodo y con un filtro de tipo), el panel de una pieza y «Nuevo experimento»."""
    return [FRAGMENTO, f"{FRAGMENTO}?exp={eid}", f"{FRAGMENTO}?dias=30&tipo=video",
            f"/cliente/acme/experimentos/pieza/{ep}", "/cliente/acme/experimentos/nuevo"]


def test_experimentos_admin_en_ingles(admin_en, app_i18n, base_temporal, monkeypatch):
    _meta_conectada(app_i18n, monkeypatch)
    eid, ep = _experimento_con_pieza(base_temporal)
    html = html_de(admin_en, "/cliente/acme")
    assert "Results center" in html and "Loading results…" in html and "How the engine decides" in html
    fugas = espanol_visible(html, ("tab-experimentos",))
    assert not fugas, fugas[:15]
    for url in _urls_del_centro(eid, ep):
        fugas = espanol_visible(html_de(admin_en, url))
        assert not fugas, (url, fugas[:15])


def test_experimentos_cliente_en_ingles(cliente_en, app_i18n, base_temporal, monkeypatch):
    _meta_conectada(app_i18n, monkeypatch)
    eid, ep = _experimento_con_pieza(base_temporal)
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("tab-experimentos",))
    assert not fugas, fugas[:15]
    for url in _urls_del_centro(eid, ep):
        fugas = espanol_visible(html_de(cliente_en, url))
        assert not fugas, (url, fugas[:15])


def test_centro_de_resultados_dice_lo_suyo_en_ingles(admin_en, app_i18n, base_temporal, monkeypatch):
    """Textos concretos del centro (no solo «sin español»: una cadena sin traducir que se lee igual en inglés, como
    «Total» o «CPC», no la atrapa la heurística), en el fragmento, en la gestión, en el panel y en «Nuevo»."""
    _meta_conectada(app_i18n, monkeypatch)
    eid, ep = _experimento_con_pieza(base_temporal)
    html = html_de(admin_en, FRAGMENTO)
    for texto in ("Needs your decision", "Period summary", "Day by day", "Where people drop off", "Piece ranking",
                  "By country", "What the project has already learned", "Month-by-month history",
                  "+ New experiment", "Since the start", "All experiments", "All pieces", "Video only"):
        assert texto in html, texto
    assert "Resumen del periodo" not in html and "Historial mes a mes" not in html
    gestion = html_de(admin_en, f"{FRAGMENTO}?exp={eid}")
    assert "Selected experiment" in gestion and "See all experiments" in gestion and "How the engine decides" in gestion
    assert "Elegido" not in gestion
    panel = html_de(admin_en, f"/cliente/acme/experimentos/pieza/{ep}")
    for texto in ("Key metrics", "Day by day", "Who sees it", "Activity log", "Test in another experiment", "See in Create",
                  "See its experiment", "No events yet."):
        assert texto in panel, texto
    nuevo = html_de(admin_en, "/cliente/acme/experimentos/nuevo")
    for texto in ("01 · Pieces", "02 · Where", "03 · Total and days", "04 · Review", "Back to results",
                  "Quick test", "Standard", "Strong", "Adjust the split", "Nothing is spent until you press Activate"):
        assert texto in nuevo, texto


def test_etiquetas_de_estado_en_ingles(admin_en, base_temporal):
    eid, _ep = _experimento_con_pieza(base_temporal)
    html = html_de(admin_en, f"{FRAGMENTO}?exp={eid}")
    assert ">drafting<" in html and ">queued<" in html
    assert ">armando<" not in html and ">en_cola<" not in html


def test_flash_de_experimentos_en_ingles(admin_en):
    admin_en.post("/cliente/acme/experimentos/probar", data={}, headers=MISMO_ORIGEN)
    assert "Connect Meta in Settings › Connections before testing pieces." in html_de(admin_en, "/cliente/acme")


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
        "dias": "7", "tope_total": "150000", "destino_url": "https://shop.example/p", "atribucion": "ninguna",
    }, headers=MISMO_ORIGEN)
    eid = ex.cargar("acme")[0]["id"]
    propuestas.crear("acme", eid, "escalar", {"pais": "CO"}, "ganador")
    ex.actualizar("acme", eid, extra={"derivaciones": [
        {"id": "d1", "tipo": "rescatar", "estado": "produciendo", "origen_ep_id": None, "motivo": "", "items": []},
    ]})

    # La gestión de un experimento (etiquetas, propuestas, derivaciones, eventos) vive en el fragmento del centro
    # de resultados con el experimento elegido, ya no en la página del proyecto.
    html = html_de(admin_en, f"{FRAGMENTO}?exp={eid}")
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


def _cobro_de_septiembre():
    """Un cobro de generación: la tabla «Mes a mes» tiene una fila con el
    nombre del mes, que sale del tablero cacheado."""
    import gastos
    gastos.registrar("acme", "video", 0.85, "video:cf_1", creado_en="2026-09-10T09:00:00")


def test_tablero_en_ingles(admin_en, monkeypatch):
    """El Tablero ya no es una pestaña (E2, 2026-10-03): su total y su «Mes a mes» viven en el «Historial» del
    fragmento del centro de resultados."""
    import dashboard
    dashboard._TABLERO_CACHE.clear()
    _cobro_de_septiembre()
    monkeypatch.setattr(dashboard.db, "ahora", lambda: "2026-09-26T10:00:00")
    html = html_de(admin_en, FRAGMENTO)
    assert "Month-by-month history" in html and "Month by month" in html and "September 2026" in html
    assert "<h2>Tablero</h2>" not in html and "Mes a mes" not in html
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
    # La página del proyecto ya no trae una pestaña Tablero.
    assert 'id="tab-tablero"' not in html_de(admin_en, "/cliente/acme")


def test_tablero_no_mezcla_idiomas_en_la_cache(app_i18n, monkeypatch):
    app_i18n._TABLERO_CACHE.clear()
    _cobro_de_septiembre()
    monkeypatch.setattr(app_i18n.db, "ahora", lambda: "2026-09-26T10:00:00")
    c = app_i18n.app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = "admin", "admin", None
    html = html_de(c, FRAGMENTO)
    assert "Historial mes a mes" in html and "Mes a mes" in html and "septiembre 2026" in html
    idiomas.guardar_de_usuario("admin", "en")
    html = html_de(c, FRAGMENTO)
    assert "Month-by-month history" in html and "Month by month" in html and "September 2026" in html
    assert "septiembre 2026" not in html


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
    producto (_catalogo_campos_comerciales.html, _producto_doctrina.html).
    Desde la Tarea 12 la ficha es un fragmento propio (catalogo_ficha), no
    parte de la página — el flash de «Prueba guardada» sí sigue viéndose ahí.
    Datos sembrados en inglés."""
    import io

    import tiendas
    from doctrina import producto as doctrina_producto
    r = admin_en.post("/cliente/acme/productos/crear", headers=MISMO_ORIGEN, content_type="multipart/form-data",
                      data={"nombre": "Blue Cushion", "descripcion": "soft", "categoria": "producto", "volver": "catalogo",
                            "imagenes": (io.BytesIO(JPG_VALIDO), "a.jpg")})
    assert r.status_code == 302
    pid = tiendas.por_activo("acme")["blue_cushion"]["id"]
    admin_en.post(f"/cliente/acme/productos/{pid}/pruebas", data={"texto": "Filling of 1,200 g", "fuente": "ficha"},
                  headers=MISMO_ORIGEN)
    doctrina_producto.reemplazar_abiertos("acme", pid, [{"texto": "Paste a buyer review", "para_que": "proof"},
                                                         {"texto": "Tell us the warranty", "para_que": "figure"}])
    html = html_de(admin_en, "/cliente/acme")
    assert "Proof saved: Claude can now use it with this product." in html
    fugas = espanol_visible(html, ("tab-catalogo",))
    assert not fugas, fugas[:15]
    ficha = html_de(admin_en, "/cliente/acme/catalogo/producto/blue_cushion/ficha")
    assert "What Claude needs" in ficha and "Paste a buyer review" in ficha and "Let Claude decide" in ficha
    fugas = espanol_visible(ficha)
    assert not fugas, fugas[:15]


def test_experimentos_doctrina_en_ingles(admin_en, app_i18n, monkeypatch):
    """Merge de main (doctrina, bloque 3): las constantes del aviso del paso 3
    salen en inglés (el marcado lo cubre test_experimentos_admin_en_ingles)."""
    _meta_conectada(app_i18n, monkeypatch)
    html = html_de(admin_en, "/cliente/acme/experimentos/nuevo")
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


def test_lote_estimar_en_ingles(admin_en, monkeypatch):
    """Fix round 1 (Task 4): produccion.estimar() armaba su 'texto' con un
    f-string crudo; la ruta lote_estimar es su único lector (lanzar_lote solo
    lee las claves numéricas), así que el idioma correcto es el de quien mira
    la pantalla."""
    sid, cid, _ = _sprint_sembrado(monkeypatch)
    r = admin_en.get(f"/cliente/acme/sprints/{sid}/lote/estimar")
    assert r.status_code == 200
    texto = r.get_json()["texto"]
    assert not _con_marca(texto), texto


# ------ Task 5 (fase 5): Nicho ------

SUB_EN = {"base": "emocion", "nombre": "Ana / Carries the jugs", "deseo": "Wash without carrying weight", "demografia": "",
          "edad_rango": "30-45", "emocion": "Tiredness",
          "identidad": {"quiere_que_vean": "organized", "cree_de_si": "practical", "quiere_lograr": "free time"},
          "soluciones_previas": [{"que": "Liquid detergent", "por_que_fallo": ["heavy"]}],
          "situaciones": ["Carrying jugs upstairs"], "comportamiento": "Keeps buying jugs",
          "conciencia": {"nivel": "consciente_del_problema", "detalle": "knows the jug is the issue"},
          "encaje_producto": "Pods weigh nothing", "tono": "Direct", "palabras_clave": ["jug"],
          "evidencia": [{"comentario_id": 1, "cita": "the jug is too heavy"}], "sin_evidencia": False}


def _estudio_sembrado():
    from nicho import datos
    eid = datos.crear_estudio("acme", "Detergent", producto="Pods", tema="laundry", idioma="en")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comment {i}: the jug is too heavy."}
                                                     for i in range(25)])
    datos.guardar_generacion("acme", eid, [{"nombre": "No weight", "deseo": "Wash without carrying weight",
                                            "resumen": "Tired of jugs", "sub_avatares": [SUB_EN]}])
    return eid


def test_pestana_nicho_en_ingles(admin_en):
    _estudio_sembrado()
    html = html_de(admin_en, "/cliente/acme")
    fugas = espanol_visible(html, ("tab-nicho",))
    assert not fugas, fugas[:15]
    tab = html[html.index('id="tab-nicho"'):html.index('id="tab-referentes"')]
    for clave in ("armando", "generando", "revisando"):              # claves crudas que MARCAS no detecta
        assert f">{clave}<" not in tab


def test_pagina_del_estudio_en_ingles(admin_en):
    eid = _estudio_sembrado()
    html = html_de(admin_en, f"/cliente/acme/nicho/{eid}")
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
    assert ">propuesto<" not in html


def test_exportacion_md_en_ingles(admin_en):
    eid = _estudio_sembrado()
    texto = admin_en.get(f"/cliente/acme/nicho/{eid}/exportar.md").get_data(as_text=True)
    encabezados = [l for l in texto.splitlines() if l.startswith("#")]
    assert encabezados and not any(_con_marca(l) for l in encabezados), encabezados


# ------ Task 6 (fase 5): Referentes ------

def _referente_sembrado():
    import proyectos
    from referentes import datos
    proyectos.guardar_referentes_copycoders("acme", True)   # la biblioteca de copycoders visible en el grid
    datos.familia_asegurar("Price Slash Hero", "Big struck-through price.")
    rid, _ = datos.guardar_referente({
        "anuncio_id": "900", "pagina_id": "1", "fuente": "copycoders", "marca": "Glow Tea",
        "url_anuncio": "https://www.facebook.com/ads/library/?id=900", "titular": "Save big today", "idioma": "en",
        "tipo": "imagen", "imagen_origen": "https://cdn/x.jpg", "dias": 10, "variantes": 2, "activo": True,
        "etapa": "BOF", "consciencia": "most-aware", "familia": "Price Slash Hero", "dolor": "ninguno-oferta",
        "firma": "Shows the saving first.", "clasificacion": "fuente",
        "extra": {"i18n": {"en": {"firma": "Shows the saving first."}}}})
    datos.marcar_imagen(rid, "ok", "https://r2/referentes/900.jpg")
    return rid


def test_pestana_referentes_en_ingles(admin_en):
    _referente_sembrado()
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-referentes",))
    assert not fugas, fugas[:15]


@pytest.mark.parametrize("ruta", ["grid", "{rid}/ficha", "traer", "{rid}/recrear", "{rid}/usar_en_sprint"])
def test_fragmentos_de_referentes_en_ingles(admin_en, monkeypatch, ruta):
    import catalogo_productos
    # Un producto con fotos: sin él, Recrear solo muestra el aviso de catálogo vacío
    # y ni el formulario ni el prompt entrarían en la revisión.
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [PRODUCTO_EN])
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: PRODUCTO_EN)
    rid = _referente_sembrado()
    idiomas.guardar_de_proyecto("acme", "en")        # el prompt de Recrear sale en el idioma del proyecto
    r = admin_en.get(f"/cliente/acme/referentes/{ruta.format(rid=rid)}", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200, (ruta, r.status_code)
    html = r.get_data(as_text=True)
    if ruta == "grid":
        assert "Save big today" in html, "el referente sembrado no está en el grid"
    if ruta == "{rid}/recrear":
        assert "LED mirror" in html and "Static social media ad" in html, "sin el formulario ni el prompt en inglés"
    fugas = espanol_visible(html)
    assert not fugas, (ruta, fugas[:15])


def test_mis_barridos_en_ingles(admin_en, monkeypatch):
    import db
    from referentes import datos
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-25T15:04:09")
    datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "foot pain", "palabra_original": "sore feet",
                                          "idioma": "en", "formato": "imagen", "pais": "US"}, 50)
    html = admin_en.get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    assert "25 Sep · 15:04" in html
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]


# ---- Fase 6, Task 1: Final edition y los parciales de Crear por fetch -----

GUION_EN = {"idioma": "en", "pais": "US", "moneda": None, "precio_texto": None, "precio_base": None, "bloques": [
    {"rol": "hook", "texto_pantalla": "Hello", "texto_voz": "Hello there", "inicio_s": 0, "fin_s": 1.5},
    {"rol": "problema", "texto_pantalla": "It hurts", "texto_voz": "Your feet hurt", "inicio_s": 1.5, "fin_s": 3},
    {"rol": "producto", "texto_pantalla": "Flip-flops", "texto_voz": "These flip-flops", "inicio_s": 3, "fin_s": 5},
    {"rol": "prueba", "texto_pantalla": "Thousands", "texto_voz": "Thousands wear them", "inicio_s": 5, "fin_s": 6.5},
    {"rol": "cta", "texto_pantalla": "Order today", "texto_voz": "Order yours", "inicio_s": 6.5, "fin_s": 8}]}


def _final_sembrado():
    """Un video listo con guion, una final lista con capas y una edición en el
    editor, todo con datos en inglés (una fuga de un dato no es de la UI)."""
    import creative_flow as cf
    import ediciones
    import materiales
    from final_edition import documento
    cf_id = cf.crear("acme", [], ["Rose flip-flop"], [], "the person walks", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2.test/clon.mp4", enfoque="producto")
    cf.guardar_guion_base("acme", cf_id, GUION_EN)
    fid = cf.crear_final("acme", cf_id, "en", "US")
    cf.actualizar_final("acme", fid, estado="listo", url_video="https://r2.test/f.mp4",
                        url_miniatura="https://r2.test/f.png", duracion_s=8.0, costo_usd=0.12,
                        capas={"guion": {"proveedor": "anthropic", "estado": "ok", "costo_usd": 0.02},
                               "voz": {"proveedor": "fal/elevenlabs", "estado": "omitida"},
                               "musica": {"proveedor": "fal/stable-audio", "estado": "error", "error": "timeout"}})
    clon = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2.test/clon.mp4", hash="h-fe-clon",
                                bytes=10, duracion_ms=8000, ancho=1080, alto=1920)
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "v0", "inicio_ms": 0, "duracion_ms": 4000, "material_id": clon["id"],
                                  "recorte": {"desde_ms": 0, "hasta_ms": 4000}}]
    ediciones.crear("acme", "video", "Rose flip-flop cut", doc, cf_id=cf_id)
    return cf_id, fid


def test_translate_no_salta_solo_el_codigo_de_idioma():
    """El código de idioma de un destino («en» = inglés, un identificador que
    no se traduce, §B6) va en un <span translate="no"> y el detector no lo
    mira; «en» suelto sigue siendo la preposición española y sí cuenta."""
    codigos = ('<span class="generado-badge">🇺🇸 <span translate="no">en</span></span>'
               '<small>(<span translate="no">en</span>)</small>'
               '<p class="detalle-texto">🇺🇸 United States · <span translate="no">en</span></p>')
    assert espanol_visible(codigos) == []
    fugas = ('<p>Genera uno en <a>Crear</a></p><p>Filtra en</p><p>Guarda (en)</p>'
             '<p>Genera uno en Crear</p><p>Qué pasó · en</p>')
    assert espanol_visible(fugas) == ["Genera uno en", "Filtra en", "Guarda (en)", "Genera uno en Crear", "Qué pasó · en"]
    # Solo el subárbol marcado: lo que sigue después del </span> vuelve a contar.
    assert espanol_visible('<p><span translate="no">en</span> Guardar</p>') == ["Guardar"]


def test_pestana_final_edition_en_ingles(admin_en):
    _final_sembrado()
    html = html_de(admin_en, "/cliente/acme")
    fugas = espanol_visible(html, ("tab-final",))
    assert not fugas, fugas[:15]
    # Tablero (2026-10-02): la final lista va a «Finished»; nada en edición.
    assert ">Editing <" in html and ">Finished <" in html and "New final edition" in html
    assert 'fe-contador">1<' in html and "1 ready video in Create" in html


@pytest.mark.parametrize("ruta", ["final/detalle", "final/{fid}/detalle"])
def test_detalles_de_final_edition_en_ingles(admin_en, ruta):
    cf_id, fid = _final_sembrado()
    html = html_de(admin_en, f"/cliente/acme/creative_flow/{cf_id}/" + ruta.format(fid=fid))
    fugas = espanol_visible(html)
    assert not fugas, (ruta, fugas[:15])
    for crudo in (">omitida<", ">musica<", ">Lista<", "2. problema<", ">equilibrada<"):   # lo que MARCAS no ve
        assert crudo not in html, crudo


@pytest.mark.parametrize("url", ["/cliente/acme/final/tarjetas?lista=elegir&desde=0",
                                 "/cliente/acme/final/tarjetas?lista=en_edicion&desde=0",
                                 "/cliente/acme/final/tarjetas?lista=finalizados&desde=0",
                                 "/cliente/acme/crear/tarjetas?desde=0",
                                 "/cliente/acme/creative_flow/{cf}/detalle"])
def test_tarjetas_y_detalle_por_fetch_en_ingles(admin_en, url):
    cf_id, _fid = _final_sembrado()
    fugas = espanol_visible(html_de(admin_en, url.format(cf=cf_id)))
    assert not fugas, (url, fugas[:15])


# ---- Fase 6, Task 2: el editor ------------------------------------------------

def test_editor_en_ingles(admin_en):
    from tests.test_rutas_editor import _datos, _edicion
    ed, _clon, _voz = _edicion()
    html = html_de(admin_en, f"/cliente/acme/ediciones/{ed['id']}")
    assert '<html lang="en">' in html
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
    datos = _datos(html)
    assert datos["idioma_ui"] == "en"
    assert datos["textos"]["guardado.ok"] == "Saved"


def test_mensajes_del_editor_en_ingles(admin_en):
    """`_edicion()` no está unida a un video de Crear: producir responde 400
    con su mensaje, en el idioma de quien mira. La subida de la biblioteca
    (capa 4b) sin archivo, igual."""
    from tests.test_rutas_editor import _edicion
    ed, _clon, _voz = _edicion()
    r = admin_en.post(f"/cliente/acme/ediciones/{ed['id']}/producir", json={"version_n": 1, "destinos": ["es_CO"]})
    assert r.status_code == 400
    assert r.get_json()["error"] == "This edit isn't linked to a Create video: it can't be produced from here yet."
    r = admin_en.post("/cliente/acme/ediciones/materiales/subir", data={})
    assert r.status_code == 400 and r.get_json()["error"] == "Choose a file."


# ---- Fase 6, Task 4: Crear › Cambiar producto y restos de Configuración -----

def test_cambiar_producto_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("crear-modo-cambiar",))
    assert not fugas, fugas[:15]


def _apartado_gasto(html):
    """Solo Configuración › Gasto: el Tablero de la misma página ya dice
    «1 charge to providers →» (otro msgid) y taparía lo que se prueba."""
    ini = html.index('id="config-ap-gasto"')
    fin = html.find('<section class="config-apartado"', ini + 1)
    return html[ini:fin if fin != -1 else None]


def test_un_cobro_en_singular_en_ingles(admin_en):
    import gastos
    gastos.registrar("acme", "video", 0.5, "video:x", detalle="wan3 · 5 s", proveedor="wavespeed")
    gasto = _apartado_gasto(html_de(admin_en, "/cliente/acme"))
    assert "1 charge to providers" in gasto and "charge(s)" not in gasto


def test_un_cobro_en_espanol_no_cambia(app_i18n):
    """El plural inglés sale de ngettext con el MISMO msgid en las dos formas:
    el español se ve igual. Falla antes del cambio por la primera línea."""
    import os
    import gastos
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "templates", "_tab_settings.html"), encoding="utf-8") as f:
        assert "ngettext('%(num)s cobro(s) a proveedores', '%(num)s cobro(s) a proveedores'" in f.read()
    gastos.registrar("acme", "video", 0.5, "video:x", detalle="wan3 · 5 s", proveedor="wavespeed")
    c = app_i18n.app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = "admin", "admin", None
    assert "1 cobro(s) a proveedores" in _apartado_gasto(html_de(c, "/cliente/acme"))   # admin sin idioma = es


def test_csv_del_gasto_con_encabezados_en_ingles(admin_en):
    texto = admin_en.get("/cliente/acme/gasto/mes.csv").get_data(as_text=True)
    assert texto.lstrip("﻿").splitlines()[0] == "date;type;provider;reference;detail;usd"


def test_error_de_link_en_ingles(tmp_path):
    import referencias_link
    with idiomas.en_idioma("en"), pytest.raises(referencias_link.LinkError) as e:
        referencias_link.descargar("ftp://algo", str(tmp_path), "x")
    assert str(e.value) == "That doesn't look like a link (it must start with http:// or https://)."


def test_describir_referencias_en_el_idioma_pedido(monkeypatch):
    import anthropic
    import generador_prompts
    import referencias_link
    visto = {}

    class _Resp:
        content = [type("B", (), {"type": "text", "text": "A sandal on the sand."})()]

    class _Cliente:
        def __init__(self, api_key=None, max_retries=0):
            self.messages = self

        def create(self, **kw):
            visto.update(kw)
            return _Resp()

    monkeypatch.setattr(anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr(generador_prompts, "_api_key", lambda: "sk-test")
    referencias_link.describir([{"etiqueta": "@Imagen 1", "tipo": "imagen", "url": "https://r2/a.jpg"}], idioma="en")
    texto = visto["messages"][0]["content"][0]["text"]
    orden = idiomas.orden_idioma("en")
    assert texto.startswith(orden) and texto.rstrip().endswith(orden) and "Describe en inglés" in texto


# ---- Fase 6, Task 5: admin, Meta y el mapa ---------------------------------

@pytest.mark.parametrize("url", ["/admin/meta", "/admin/referentes"])
def test_paginas_de_admin_en_ingles(admin_en, url):
    fugas = espanol_visible(html_de(admin_en, url))
    assert not fugas, (url, fugas[:15])


def test_aviso_de_fallo_de_las_familias_en_ingles(admin_en, monkeypatch):
    import dashboard
    from tareas import referentes as tareas_ref
    real = dashboard.trabajos.consultar
    monkeypatch.setattr(dashboard.trabajos, "consultar", lambda job_id: (
        {"estado": "error", "mensaje": "boom"} if job_id == tareas_ref.JOB_FAMILIAS_EN else real(job_id)))
    assert "The last batch of English descriptions failed: boom" in html_de(admin_en, "/admin/referentes")


def test_meta_elegir_en_ingles(cliente_en, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "cargar_pendiente", lambda c: {
        "usuario_meta": "Glow Owner",
        "activos": {"ad_accounts": [{"id": "act_1", "name": "Glow Ads", "currency": "USD"}],
                    "pages": [{"id": "9", "name": "Glow Page", "ig_username": None}]}})
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme/meta/elegir"))
    assert not fugas, fugas[:15]


def test_detalle_del_pixel_se_traduce_al_mostrarlo(admin_en, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: {
        "estado": "sin_pixel", "pixel_id": None, "nombre": None, "ultimo_disparo": None,
        "detalle": "La cuenta publicitaria no tiene ningún Pixel."})
    assert "The ad account has no Pixel." in html_de(admin_en, "/cliente/acme")


def test_barra_del_mapa_en_ingles(admin_en):
    html = html_de(admin_en, "/mapa")
    fugas = espanol_visible(html, ("mapa-barra",))
    assert not fugas, fugas
    assert "This map is internal documentation and is written in Spanish." in html


def test_csv_del_panel_con_encabezados_en_ingles(admin_en):
    texto = admin_en.get("/panel/gasto.csv").get_data(as_text=True)
    assert texto.lstrip("﻿").splitlines()[0] == "project;date;type;provider;reference;detail;usd"


def test_estados_de_barrido_del_admin_con_etiqueta(admin_en):
    """Fix round 1 (F6-17): los estados de barrido de /admin/referentes se ven
    con su etiqueta (la de «Mis barridos»), no con la clave cruda."""
    from referentes import datos
    for _ in range(2):   # dos importaciones: la última va en la frase, la otra en el historial
        bid = datos.crear_barrido(None, "copycoders", {"url": "https://go.copycoders.ai/x"}, 100)
        datos.actualizar_barrido(bid, estado="parcial", traidos=3, nuevos=2, con_imagen=1)
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "shoes", "idioma": "en"}, 50)
    datos.actualizar_barrido(bid, estado="parcial", traidos=5)
    html = html_de(admin_en, "/admin/referentes")
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
    assert ">parcial<" not in html and html.count("Incomplete") == 3   # frase, historial y barridos globales


def test_fixture_idioma_aisla_registros_locales(app_i18n, tmp_path):
    from pathlib import Path
    ruta = Path(app_i18n.registro_app.ruta('web'))
    assert tmp_path in ruta.parents

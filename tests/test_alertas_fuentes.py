# tests/test_alertas_fuentes.py
"""Fuentes de alertas.py, «puesta a punto» y «faltantes» (spec 2026-09-20-alertas-design.md
§2.1, §2.2 y §12): llaves, cuentas, worker, saldo, tablero y proyecto. Cada una con su
estado simulado (monkeypatch sobre cada dependencia) y, donde cuenta, con el dato real."""
import json
import time

from sqlalchemy import event

AHORA = "2026-10-02T10:00:00"


def _claves(lista):
    return [a["clave"] for a in lista]


def _por_clave(lista):
    return {a["clave"]: a for a in lista}


# ---------- registro ----------

def test_las_seis_fuentes_se_registran_en_su_orden():
    import alertas
    nombres = [n for n, _ in alertas.FUENTES]
    assert nombres[:6] == ["llaves", "cuentas", "worker", "saldo", "tablero", "proyecto"]


def test_alertas_no_importa_el_dashboard():
    """Importar `dashboard` desde aquí sería circular, y el worker puede importar alertas."""
    import alertas
    with open(alertas.__file__, encoding="utf-8") as f:
        codigo = f.read()
    assert "import dashboard" not in codigo and "from dashboard" not in codigo


# ---------- llaves ----------

def _tarjeta(id_, nombre, estado, faltan, opcional=False, nota="Nota de la tarjeta."):
    return {"id": id_, "nombre": nombre, "estado": estado, "faltan": faltan, "opcional": opcional, "nota": nota}


def test_llaves_faltante_parcial_opcional_configurada_y_meta(monkeypatch):
    import alertas
    import llaves
    monkeypatch.setattr(llaves, "estado", lambda *a, **k: [
        _tarjeta("anthropic", "Anthropic", "configurada", []),
        _tarjeta("wavespeed", "WaveSpeed", "falta", ["WAVESPEED_API_KEY"], nota="Sin ella no se genera."),
        _tarjeta("r2", "Cloudflare R2", "parcial", ["R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL"]),
        _tarjeta("higgsfield", "Higgsfield", "falta", ["HF_API_KEY_ID", "HF_API_KEY_SECRET"], opcional=True),
        _tarjeta("meta", "Meta", "falta", ["app de Meta del proyecto"]),
    ])
    a = alertas._fuente_llaves("acme", AHORA)
    assert _claves(a) == ["llave:wavespeed", "llave:r2", "llave:higgsfield"]   # Meta la cubre tablero:meta_*
    ws, r2, hf = a
    assert ws["nivel"] == "bloquea" and ws["titulo"] == "Falta la llave de WaveSpeed"
    assert "WAVESPEED_API_KEY" in ws["detalle"] and "Sin ella no se genera." in ws["detalle"]
    assert r2["nivel"] == "bloquea" and r2["titulo"] == "Llave incompleta de Cloudflare R2"
    assert "R2_BUCKET_NAME, R2_PUBLIC_BASE_URL" in r2["detalle"]
    assert hf["nivel"] == "info"                                  # opcional: conviene, no urge
    assert ws["huella"] == alertas.huella("WAVESPEED_API_KEY")
    assert r2["huella"] == alertas.huella("R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL")
    assert [x["ancla"] for x in a] == ["llave-wavespeed", "llave-r2", "llave-higgsfield"]
    assert all(x["tab"] == "settings" and x["grupo"] == "puesta_a_punto" and x["solo_admin"] is True for x in a)


def test_llaves_todas_configuradas_no_alertan(monkeypatch):
    import alertas
    import llaves
    monkeypatch.setattr(llaves, "estado", lambda *a, **k: [_tarjeta("fal", "fal.ai", "configurada", [])])
    assert alertas._fuente_llaves("acme", AHORA) == []


def test_llaves_reales_higgsfield_opcional_y_ningun_valor_sale(monkeypatch):
    """Con `llaves.estado()` de verdad: Higgsfield (opcional) es info, WaveSpeed bloquea, y el valor de
    una variable presente no aparece en ninguna alerta (solo nombres de variables)."""
    import alertas
    import llaves
    for s in llaves.SERVICIOS:
        for v in s["variables"]:
            monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("FAL_KEY", "fal-valor-secreto-123")                  # configurada: no alerta
    monkeypatch.setenv("R2_ACCOUNT_ID", "r2-valor-secreto-456")             # parcial: alerta
    por = _por_clave(alertas._fuente_llaves("acme", AHORA))
    assert "llave:fal" not in por
    assert por["llave:wavespeed"]["nivel"] == "bloquea" and por["llave:higgsfield"]["nivel"] == "info"
    assert por["llave:r2"]["titulo"].startswith("Llave incompleta de")
    assert "R2_ACCOUNT_ID" not in por["llave:r2"]["detalle"]                # esa sí está: no falta
    assert "R2_BUCKET_NAME" in por["llave:r2"]["detalle"]
    volcado = json.dumps(list(por.values()), ensure_ascii=False)
    assert "fal-valor-secreto-123" not in volcado and "r2-valor-secreto-456" not in volcado


# ---------- cuentas ----------

def test_cuentas_sin_correo_sin_verificar_y_verificada(usuarios_tmp):
    import alertas
    usuarios_tmp.crear("nuevo", "secreta1234", "cliente", cliente="acme")
    usuarios_tmp.crear("ana", "secreta1234", "cliente", cliente="acme", correo="ana@ejemplo.com")
    usuarios_tmp.crear("ajena", "secreta1234", "cliente", cliente="otro")
    a = alertas._fuente_cuentas("acme", AHORA)
    # «alguien» y «user_acme» ya vienen verificados; «ajena» es de otro proyecto; el admin no tiene proyecto.
    assert _claves(a) == ["cuenta:correo:ana", "cuenta:correo:nuevo"]
    ana, nuevo = a
    assert ana["titulo"] == "Confirma el correo de la cuenta ana" and "ana@ejemplo.com" in ana["detalle"]
    assert ana["huella"] == alertas.huella("sin_verificar", "ana@ejemplo.com")
    assert nuevo["titulo"] == "La cuenta nuevo no tiene correo" and nuevo["huella"] == alertas.huella("sin_correo")
    assert "Sin correo confirmado no puedes conectar Meta ni una tienda" in ana["detalle"] + nuevo["detalle"]
    assert all(x["nivel"] == "bloquea" and x["grupo"] == "puesta_a_punto" and x["tab"] == "settings"
               and x["ancla"] == "config-cuenta" and x["solo_admin"] is False for x in a)
    usuarios_tmp.actualizar("ana", correo_verificado=True)
    assert _claves(alertas._fuente_cuentas("acme", AHORA)) == ["cuenta:correo:nuevo"]


def test_cuentas_una_cuenta_vieja_con_nombre_raro_igual_se_puede_descartar(usuarios_tmp):
    """`usuarios.validar_usuario` solo exige el formato al crear: una cuenta anterior puede traer espacios o acentos,
    y su clave tiene que seguir pasando CLAVE_VALIDA (si no, el botón Descartar daría 400)."""
    import re

    import _json_store
    import alertas
    datos = usuarios_tmp.cargar()
    datos["María López"] = {"rol": "cliente", "cliente": "acme", "correo": None, "correo_verificado": False,
                            "password_hash": "x", "session_version": 1, "creado_en": "2026-01-01T00:00:00"}
    _json_store.guardar(usuarios_tmp._path(), datos)
    x, = alertas._fuente_cuentas("acme", AHORA)
    assert re.match(alertas.CLAVE_VALIDA, x["clave"]) and x["clave"].startswith("cuenta:correo:")
    assert "María López" in x["titulo"]                                             # la persona sí ve su nombre real


def test_cuentas_cambiar_el_correo_cambia_la_huella(usuarios_tmp):
    import alertas
    usuarios_tmp.crear("ana", "secreta1234", "cliente", cliente="acme", correo="ana@ejemplo.com")
    h1 = alertas._fuente_cuentas("acme", AHORA)[0]["huella"]
    usuarios_tmp.actualizar("ana", correo="ana@otro.com")
    assert alertas._fuente_cuentas("acme", AHORA)[0]["huella"] != h1


# ---------- worker ----------

def _kv(db, clave, valor):
    with db.conectar() as con:
        con.execute(db.kv.insert().values(clave=clave, valor=valor, actualizado_en=db.ahora()))


def _tarea(db, iniciada_en):
    with db.conectar() as con:
        con.execute(db.tarea.insert().values(cliente="acme", job_id=f"j_{iniciada_en}", tipo="flowplus_video", payload={},
                                             estado="hecha", ejecutar_desde=AHORA, creada_en=AHORA,
                                             iniciada_en=iniciada_en))


def test_worker_nunca_ha_corrido(base_temporal):
    import alertas
    a = alertas._fuente_worker("acme", AHORA)
    assert len(a) == 1
    x = a[0]
    assert x["clave"] == "worker:parado" and x["nivel"] == "bloquea" and x["grupo"] == "puesta_a_punto"
    assert x["titulo"] == "El worker no está corriendo" and "Última actividad: nunca" in x["detalle"]
    assert x["huella"] == alertas.huella("nunca")
    assert x["solo_admin"] is True and x["tab"] == "settings" and x["ancla"] == "config-puesta-a-punto"


def test_worker_vivo_si_la_marca_periodica_es_reciente(base_temporal):
    import alertas
    _kv(base_temporal, "ultimo_sprint_qa_pendientes", "2026-10-02T09:55:00")      # hace 5 min
    assert alertas._fuente_worker("acme", AHORA) == []


def test_worker_parado_si_la_ultima_senal_pasa_de_30_minutos(base_temporal):
    import alertas
    _kv(base_temporal, "ultimo_sprint_qa_pendientes", "2026-10-02T08:00:00")      # hace 2 h
    a = alertas._fuente_worker("acme", AHORA)
    assert len(a) == 1 and "Última actividad: hace 120 min" in a[0]["detalle"]
    assert a[0]["huella"] == alertas.huella("2026-10-02T08:00:00")                 # cada caída nueva reaparece


def test_worker_el_umbral_es_de_30_minutos(base_temporal):
    import alertas
    _kv(base_temporal, "ultimo_cola_limpiar", "2026-10-02T09:30:00")              # justo 30 min: vivo
    assert alertas._fuente_worker("acme", AHORA) == []
    assert len(alertas._fuente_worker("acme", "2026-10-02T10:01:00")) == 1        # 31 min: parado


def test_worker_vivo_por_la_ultima_tarea_iniciada(base_temporal):
    """Marca vieja (45 min), pero una tarea iniciada hace 10 min: estaba ocupado, no parado."""
    import alertas
    _kv(base_temporal, "ultimo_sprint_qa_pendientes", "2026-10-02T09:15:00")
    _tarea(base_temporal, "2026-10-02T09:50:00")
    assert alertas._fuente_worker("acme", AHORA) == []


def test_worker_vivo_solo_por_tarea_sin_ninguna_marca(base_temporal):
    import alertas
    _tarea(base_temporal, "2026-10-02T09:58:00")
    assert alertas._fuente_worker("acme", AHORA) == []


def test_worker_la_huella_es_la_senal_mas_reciente_de_todas(base_temporal):
    import alertas
    _kv(base_temporal, "ultimo_sprint_qa_pendientes", "2026-10-02T08:00:00")
    _kv(base_temporal, "ultimo_exp_avanzar_todos", "2026-10-02T09:00:00")         # cualquier `ultimo_*`
    _tarea(base_temporal, "2026-10-02T08:30:00")
    a = alertas._fuente_worker("acme", AHORA)
    assert len(a) == 1 and "hace 60 min" in a[0]["detalle"] and a[0]["huella"] == alertas.huella("2026-10-02T09:00:00")
    _tarea(base_temporal, "2026-10-02T09:20:00")                                  # la tarea gana: sigue parado, otra huella
    a = alertas._fuente_worker("acme", AHORA)
    assert "hace 40 min" in a[0]["detalle"] and a[0]["huella"] == alertas.huella("2026-10-02T09:20:00")


def test_worker_ignora_claves_que_no_son_ultimo_y_valores_ilegibles(base_temporal):
    import alertas
    _kv(base_temporal, "sin_saldo:wavespeed", "2026-10-02T09:59:00")              # no es una marca del worker
    _kv(base_temporal, "otra_cosa", "2026-10-02T09:59:00")
    _kv(base_temporal, "ultimo_basura", "zzz-no-es-una-fecha")                    # ilegible: no vale (y no rompe)
    a = alertas._fuente_worker("acme", AHORA)
    assert len(a) == 1 and "Última actividad: nunca" in a[0]["detalle"]


def test_worker_una_sola_consulta_por_fuente_de_senal(base_temporal):
    import alertas
    import db
    for i in range(12):
        _kv(db, f"ultimo_tipo_{i}", "2026-10-02T09:55:00")
    consultas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        assert alertas._fuente_worker("acme", AHORA) == []
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    assert len(consultas) == 2                                                    # kv + tarea, sin importar cuántas marcas


# ---------- saldo ----------

def _vigente(monkeypatch, **campos):
    import saldo
    aviso = {"proveedor": "wavespeed", "nombre": "WaveSpeed", "recarga": "https://wavespeed.ai/top-up",
             "desde": "2026-10-02T09:12:30", "fallos": 3, "cliente": "proyecto_ajeno_zzz",
             "detalle": "Insufficient credits access_token=SECRETO"}
    aviso.update(campos)
    monkeypatch.setattr(saldo, "vigente", lambda proveedor: aviso if proveedor == "wavespeed" else None)


def test_saldo_sin_aviso_no_alerta(monkeypatch):
    import alertas
    import saldo
    monkeypatch.setattr(saldo, "vigente", lambda proveedor: None)
    assert alertas._fuente_saldo("acme", AHORA) == []


def test_saldo_son_dos_alertas_una_neutra_y_otra_solo_para_el_admin(monkeypatch):
    import alertas
    _vigente(monkeypatch)
    a = alertas._fuente_saldo("acme", AHORA)
    assert _claves(a) == ["saldo:wavespeed", "saldo:wavespeed_recarga"]
    neutra, recarga = a
    assert all(x["nivel"] == "bloquea" and x["grupo"] == "puesta_a_punto" for x in a)
    assert all(x["huella"] == alertas.huella("2026-10-02T09:12:30") for x in a)   # la misma: la cierra el mismo evento
    # La que ve el cliente: neutra, sin enlace de recarga ni datos del proveedor ni de otro proyecto.
    assert neutra["solo_admin"] is False
    assert neutra["titulo"] == "La generación de videos e imágenes está en pausa"
    assert "wavespeed" not in (neutra["titulo"] + neutra["detalle"]).lower() and "http" not in neutra["detalle"]
    assert "proyecto_ajeno_zzz" not in neutra["detalle"] + recarga["detalle"]
    assert "SECRETO" not in neutra["detalle"] + recarga["detalle"] + neutra["titulo"] + recarga["titulo"]
    # La del admin: desde cuándo y dónde recargar.
    assert recarga["solo_admin"] is True
    assert recarga["titulo"] == "WaveSpeed se quedó sin saldo"
    assert "2026-10-02 09:12" in recarga["detalle"] and "https://wavespeed.ai/top-up" in recarga["detalle"]
    assert recarga["url"] is None                                                  # la URL de recarga va en el texto


def test_saldo_con_aviso_real_en_kv(base_temporal):
    """Con `saldo.vigente` de verdad (la fila `sin_saldo:wavespeed` de kv): sale; sin fila, no."""
    import alertas
    assert alertas._fuente_saldo("acme", AHORA) == []
    ahora = time.time()
    _kv(base_temporal, "sin_saldo:wavespeed", json.dumps({"desde": "2026-10-02T09:12:30", "desde_ts": ahora - 600,
                                                          "ultimo_ts": ahora - 60, "fallos": 2, "detalle": "x"}))
    a = alertas._fuente_saldo("acme", AHORA)
    assert _claves(a) == ["saldo:wavespeed", "saldo:wavespeed_recarga"]
    assert a[0]["huella"] == alertas.huella("2026-10-02T09:12:30")


# ---------- tablero ----------

def _texto_tablero(monkeypatch, lista):
    import tablero
    visto = {}

    def falso(cliente, ahora_iso=None, datos=None):
        visto["args"] = (cliente, ahora_iso)
        return lista
    monkeypatch.setattr(tablero, "alertas", falso)
    return visto


def test_tablero_se_traduce_sin_reescribir_reglas(monkeypatch):
    import alertas
    visto = _texto_tablero(monkeypatch, [
        {"tipo": "meta_roto", "nivel": "alta", "texto": "La conexión con Meta está rota.", "tab": "settings", "experimento_id": None},
        {"tipo": "tienda_rota", "nivel": "media", "texto": "La tienda X dejó de sincronizar.", "tab": "settings", "experimento_id": None},
        {"tipo": "propuestas_pendientes", "nivel": "media", "texto": "«X» tiene 2 propuestas.", "tab": "experimentos", "experimento_id": 7},
        {"tipo": "ganador_sin_publicar", "nivel": "media", "texto": "2 ganadoras sin publicar.", "tab": "settings", "experimento_id": None},
        {"tipo": "experimento_error", "nivel": "alta", "texto": "«X» falló al lanzar.", "tab": "experimentos", "experimento_id": 7},
        {"tipo": "sin_metricas", "nivel": "baja", "texto": "«X» lleva 11 h sin métricas nuevas de Meta.", "tab": "experimentos", "experimento_id": 7},
        {"tipo": "productos_sin_experimento", "nivel": "baja", "texto": "1 producto marcado «en prueba».", "tab": "catalogo", "experimento_id": None},
    ])
    a = alertas._fuente_tablero("acme", AHORA)
    assert visto["args"] == ("acme", AHORA)
    assert _claves(a) == ["tablero:meta_roto:-", "tablero:tienda_rota:-", "tablero:propuestas_pendientes:7",
                          "tablero:ganador_sin_publicar:-", "tablero:experimento_error:7", "tablero:sin_metricas:7",
                          "tablero:productos_sin_experimento:-"]
    assert [x["nivel"] for x in a] == ["bloquea", "atencion", "atencion", "atencion", "bloquea", "info", "info"]
    assert [x["grupo"] for x in a] == ["puesta_a_punto", "puesta_a_punto", "decision", "decision", "fallos", "fallos",
                                       "faltantes"]
    por = _por_clave(a)
    assert por["tablero:propuestas_pendientes:7"]["url"] == "?exp=7#experimentos"
    assert por["tablero:propuestas_pendientes:7"]["entidad"] == 7
    assert por["tablero:meta_roto:-"]["url"] is None and por["tablero:meta_roto:-"]["tab"] == "settings"
    assert por["tablero:productos_sin_experimento:-"]["tab"] == "catalogo"
    assert por["tablero:meta_roto:-"]["titulo"] == "La conexión con Meta está rota." and por["tablero:meta_roto:-"]["detalle"] == ""
    assert all(x["solo_admin"] is False for x in a)


def test_tablero_las_horas_de_sin_metricas_no_entran_en_la_huella(monkeypatch):
    import alertas
    _texto_tablero(monkeypatch, [
        {"tipo": "sin_metricas", "nivel": "baja", "texto": "«X» lleva 11 h sin métricas nuevas de Meta.", "tab": "experimentos", "experimento_id": 7},
        {"tipo": "propuestas_pendientes", "nivel": "media", "texto": "«X» tiene 2 propuestas.", "tab": "experimentos", "experimento_id": 7}])
    sin_metricas, propuestas = alertas._fuente_tablero("acme", AHORA)
    assert sin_metricas["huella"] == alertas.huella()                              # el texto cambia cada hora: no puede entrar
    assert propuestas["huella"] == alertas.huella("«X» tiene 2 propuestas.")      # las demás sí: otro texto, otra huella


def test_tablero_ningun_token_sale_en_el_texto(monkeypatch):
    import alertas
    _texto_tablero(monkeypatch, [
        {"tipo": "tienda_rota", "nivel": "media", "texto": "La tienda X falló: access_token=SECRETO&x=1. Vuelve a conectarla.",
         "tab": "settings", "experimento_id": None}])
    x, = alertas._fuente_tablero("acme", AHORA)
    assert "SECRETO" not in x["titulo"] and "access_token=***" in x["titulo"]
    assert x["huella"] == alertas.huella(x["titulo"])


def test_tablero_sin_alertas_no_devuelve_nada(monkeypatch):
    import alertas
    _texto_tablero(monkeypatch, [])
    assert alertas._fuente_tablero("acme", AHORA) == []


# ---------- proyecto (faltantes) ----------

def _proyecto(monkeypatch, tmp_path):
    """Un proyecto vacío con todas las dependencias simuladas; `estado` se edita para resolver cada faltante."""
    import alertas
    import catalogo_productos
    import marca
    import organico
    import proyectos
    import tiendas
    monkeypatch.setattr(alertas, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    estado = {"guia": "", "productos": [], "personajes": [], "tiendas": [], "correo": None, "canales": [],
              "archivados": set()}
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: estado["guia"])
    monkeypatch.setattr(catalogo_productos, "listar_productos", lambda c, cat="producto": estado["productos"])
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": estado["personajes"])
    monkeypatch.setattr(tiendas, "listar", lambda c: estado["tiendas"])
    monkeypatch.setattr(tiendas, "activos_archivados", lambda c: estado["archivados"])
    monkeypatch.setattr(proyectos, "correo_notificaciones", lambda c: estado["correo"])
    monkeypatch.setattr(organico, "disponibles", lambda c: estado["canales"])
    return estado


def test_proyecto_todos_los_faltantes_y_luego_ninguno(monkeypatch, tmp_path):
    import alertas
    estado = _proyecto(monkeypatch, tmp_path)
    a = alertas._fuente_proyecto("acme", AHORA)
    assert _claves(a) == ["proyecto:guia_marca", "proyecto:producto", "proyecto:logo", "proyecto:personaje",
                          "proyecto:tienda", "proyecto:correo_avisos", "proyecto:canal_organico"]
    por = _por_clave(a)
    assert por["proyecto:guia_marca"]["nivel"] == "atencion" and por["proyecto:guia_marca"]["ancla"] == "config-marca"
    assert por["proyecto:producto"]["nivel"] == "atencion" and por["proyecto:producto"]["tab"] == "catalogo"
    assert por["proyecto:producto"]["ancla"] is None
    assert por["proyecto:correo_avisos"]["nivel"] == "atencion" and por["proyecto:correo_avisos"]["ancla"] == "config-correo"
    assert {por[k]["nivel"] for k in ("proyecto:logo", "proyecto:personaje", "proyecto:tienda",
                                      "proyecto:canal_organico")} == {"info"}
    assert por["proyecto:logo"]["ancla"] == "config-logos" and por["proyecto:tienda"]["ancla"] == "config-tienda"
    assert por["proyecto:personaje"]["tab"] == "catalogo"
    assert por["proyecto:canal_organico"]["ancla"] == "config-canales-organicos"
    assert all(x["huella"] == alertas.huella() and x["grupo"] == "faltantes" and x["solo_admin"] is False for x in a)
    assert por["proyecto:guia_marca"]["titulo"] == "El proyecto no tiene guía de marca"
    assert por["proyecto:producto"]["titulo"] == "No hay ningún producto con foto en el catálogo"
    assert por["proyecto:logo"]["titulo"] == "Sin logos oficiales"
    assert por["proyecto:personaje"]["titulo"] == "Sin personaje en el catálogo"
    assert por["proyecto:tienda"]["titulo"] == "Sin tienda conectada"
    assert por["proyecto:correo_avisos"]["titulo"] == "Sin correo de avisos"
    assert por["proyecto:canal_organico"]["titulo"] == "Sin canales orgánicos"
    assert all(x["detalle"] for x in a)
    # Se resuelve todo: no queda ninguno.
    estado.update({"guia": "Luz natural.", "productos": [{"id": "rose"}], "personajes": [{"id": "ana"}],
                   "tiendas": [{"id": 1}], "correo": "avisos@acme.com", "canales": ["instagram"]})
    (tmp_path / "clientes" / "acme" / "logos").mkdir()
    (tmp_path / "clientes" / "acme" / "logos" / "logo.PNG").write_bytes(b"x")
    assert alertas._fuente_proyecto("acme", AHORA) == []


def test_proyecto_cada_faltante_se_resuelve_por_separado(monkeypatch, tmp_path):
    import alertas
    estado = _proyecto(monkeypatch, tmp_path)
    resuelve = {"proyecto:guia_marca": {"guia": "x"}, "proyecto:producto": {"productos": [{"id": "p"}]},
                "proyecto:personaje": {"personajes": [{"id": "p"}]}, "proyecto:tienda": {"tiendas": [{"id": 1}]},
                "proyecto:correo_avisos": {"correo": "a@b.com"}, "proyecto:canal_organico": {"canales": ["youtube"]}}
    base = dict(estado)
    for clave, cambio in resuelve.items():
        estado.clear(); estado.update(base); estado.update(cambio)
        a = _claves(alertas._fuente_proyecto("acme", AHORA))
        assert clave not in a and len(a) == 6, clave


def test_proyecto_el_logo_solo_cuenta_si_es_una_imagen(monkeypatch, tmp_path):
    import alertas
    _proyecto(monkeypatch, tmp_path)
    logos = tmp_path / "clientes" / "acme" / "logos"
    assert "proyecto:logo" in _claves(alertas._fuente_proyecto("acme", AHORA))     # ni la carpeta existe
    logos.mkdir()
    (logos / "notas.txt").write_text("x")
    (logos / "intro.mp4").write_bytes(b"x")
    assert "proyecto:logo" in _claves(alertas._fuente_proyecto("acme", AHORA))     # existe pero sin imágenes
    (logos / "Marca.JPEG").write_bytes(b"x")
    assert "proyecto:logo" not in _claves(alertas._fuente_proyecto("acme", AHORA))


def test_proyecto_el_correo_de_avisos_solo_cuenta_con_smtp(monkeypatch, tmp_path):
    import alertas
    _proyecto(monkeypatch, tmp_path)
    monkeypatch.delenv("SMTP_HOST")
    assert "proyecto:correo_avisos" not in _claves(alertas._fuente_proyecto("acme", AHORA))
    monkeypatch.setenv("SMTP_HOST", "   ")                                         # en blanco = sin servidor
    assert "proyecto:correo_avisos" not in _claves(alertas._fuente_proyecto("acme", AHORA))
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    assert "proyecto:correo_avisos" in _claves(alertas._fuente_proyecto("acme", AHORA))


def test_proyecto_la_guia_en_blanco_cuenta_como_vacia(monkeypatch, tmp_path):
    import alertas
    estado = _proyecto(monkeypatch, tmp_path)
    estado["guia"] = "   \n"
    assert "proyecto:guia_marca" in _claves(alertas._fuente_proyecto("acme", AHORA))
    estado["guia"] = None
    assert "proyecto:guia_marca" in _claves(alertas._fuente_proyecto("acme", AHORA))


def test_proyecto_un_producto_archivado_no_cuenta_como_producto(monkeypatch, tmp_path):
    """Como los selectores de Crear y Sprints: si todos los productos con foto están archivados, no hay
    con qué trabajar; con uno vivo, sí."""
    import alertas
    estado = _proyecto(monkeypatch, tmp_path)
    estado["productos"] = [{"id": "rose"}]
    estado["archivados"] = {"rose"}
    assert "proyecto:producto" in _claves(alertas._fuente_proyecto("acme", AHORA))
    estado["productos"] = [{"id": "rose"}, {"id": "lila"}]
    assert "proyecto:producto" not in _claves(alertas._fuente_proyecto("acme", AHORA))
    estado["archivados"] = {"rose", "lila"}
    assert "proyecto:producto" in _claves(alertas._fuente_proyecto("acme", AHORA))
    # Un color de un producto archivado (`pid/color`) tampoco cuenta.
    estado["productos"] = [{"id": "rose/rojo"}]
    estado["archivados"] = {"rose"}
    assert "proyecto:producto" in _claves(alertas._fuente_proyecto("acme", AHORA))


def test_proyecto_producto_con_el_catalogo_real(monkeypatch, tmp_path, base_temporal):
    """Sin simular el catálogo: una carpeta de producto con una foto en disco, y un producto archivado en la tabla."""
    import alertas
    import catalogo_productos
    import db
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(alertas, "BASE_DIR", str(tmp_path))
    carpeta = tmp_path / "clientes" / "acme" / "productos" / "rose"
    assert "proyecto:producto" in _claves(alertas._fuente_proyecto("acme", AHORA))   # nada en disco
    carpeta.mkdir(parents=True)
    (carpeta / "frente.jpg").write_bytes(b"x")
    assert "proyecto:producto" not in _claves(alertas._fuente_proyecto("acme", AHORA))
    with db.conectar() as con:                                                       # archivado en la tabla de productos
        con.execute(db.producto.insert().values(cliente="acme", fuente="manual", nombre="Rose", activo_catalogo_id="rose",
                                                archivado=True, creado_en=AHORA, actualizado_en=AHORA))
    assert "proyecto:producto" in _claves(alertas._fuente_proyecto("acme", AHORA))


# ---------- las seis juntas, con lo real ----------

def test_las_seis_fuentes_reales_corren_juntas_sin_romperse_y_el_cliente_no_ve_lo_del_servidor(base_temporal, monkeypatch, tmp_path):
    """Sin simular nada (salvo el .env y la carpeta del proyecto): ninguna fuente revienta en un proyecto vacío, el
    admin ve las llaves y el worker, y el cliente solo lo que es suyo."""
    import alertas
    import catalogo_productos
    import llaves
    import marca
    import proyectos
    for s in llaves.SERVICIOS:
        for v in s["variables"]:
            monkeypatch.delenv(v, raising=False)
    for modulo in (alertas, catalogo_productos, marca, proyectos):
        monkeypatch.setattr(modulo, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    todas = alertas.calcular("acme", AHORA)
    assert not [a for a in todas if a["clave"].startswith("revision:")]
    claves = set(_claves(todas))
    assert {"llave:wavespeed", "worker:parado", "proyecto:guia_marca", "proyecto:producto"} <= claves
    assert all(a["solo_admin"] for a in todas if a["clave"].startswith(("llave:", "worker:")))
    ven_admin = set(_claves(alertas.visibles("acme", AHORA, rol="admin")["visibles"]))
    ven_cliente = set(_claves(alertas.visibles("acme", AHORA, rol="cliente")["visibles"]))
    assert {"llave:wavespeed", "worker:parado"} <= ven_admin
    assert not [c for c in ven_cliente if c.startswith(("llave:", "worker:"))]
    assert {"proyecto:guia_marca", "proyecto:producto", "tablero:meta_sin_conectar:-"} <= ven_cliente
    # Todas las claves y huellas que salen sirven para descartar (lo que las rutas validan).
    import re
    assert all(re.match(alertas.CLAVE_VALIDA, a["clave"]) and re.match(alertas.HUELLA_VALIDA, a["huella"]) for a in todas)


# ---------- inglés ----------

def test_los_textos_salen_en_ingles_cuando_quien_mira_lee_en_ingles(monkeypatch, tmp_path, base_temporal, usuarios_tmp):
    """Todo título y detalle pasa por el catálogo: en inglés ninguno queda igual que en español."""
    import alertas
    import idiomas
    import llaves
    import saldo
    _proyecto(monkeypatch, tmp_path)
    for s in llaves.SERVICIOS:
        for v in s["variables"]:
            monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(saldo, "vigente", lambda p: {"proveedor": p, "nombre": "WaveSpeed", "recarga": "https://wavespeed.ai/top-up",
                                                     "desde": "2026-10-02T09:12:30", "fallos": 1, "cliente": "", "detalle": ""})
    usuarios_tmp.crear("nuevo", "secreta1234", "cliente", cliente="acme")
    usuarios_tmp.crear("ana", "secreta1234", "cliente", cliente="acme", correo="ana@ejemplo.com")
    fuentes = (alertas._fuente_llaves, alertas._fuente_cuentas, alertas._fuente_worker, alertas._fuente_saldo,
               alertas._fuente_proyecto)
    es = {a["clave"]: a for f in fuentes for a in f("acme", AHORA)}
    with idiomas.en_idioma("en"):
        en = {a["clave"]: a for f in fuentes for a in f("acme", AHORA)}
        nombre_ws = next(t["nombre"] for t in llaves.estado() if t["id"] == "wavespeed")
    assert set(en) == set(es) and len(en) > 15
    sin_traducir = [(c, campo) for c, a in en.items() for campo in ("titulo", "detalle") if a[campo] == es[c][campo]]
    assert sin_traducir == []
    assert en["llave:wavespeed"]["titulo"] == f"The {nombre_ws} key is missing"
    assert en["cuenta:correo:nuevo"]["titulo"] == "The account nuevo has no email"
    assert en["cuenta:correo:ana"]["titulo"] == "Confirm the email of the account ana"
    assert en["worker:parado"]["titulo"] == "The worker isn't running"
    assert "Last activity: never" in en["worker:parado"]["detalle"]
    assert en["saldo:wavespeed"]["titulo"] == "Video and image generation is paused"
    assert en["saldo:wavespeed_recarga"]["titulo"] == "WaveSpeed ran out of credit"
    assert en["proyecto:logo"]["titulo"] == "No official logos"

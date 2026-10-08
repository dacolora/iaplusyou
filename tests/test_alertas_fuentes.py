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
    assert por["tablero:propuestas_pendientes:7"]["url"] == "#experimentos?exp=7"   # el filtro va en el hash (E2)
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
    # Las demás: tipo, experimento y los números del texto (no el texto, que viene traducido).
    assert propuestas["huella"] == alertas.huella("propuestas_pendientes", 7, "2")


def test_tablero_ningun_token_sale_en_el_texto(monkeypatch):
    import alertas
    _texto_tablero(monkeypatch, [
        {"tipo": "tienda_rota", "nivel": "media", "texto": "La tienda X falló: access_token=SECRETO987&x=1. Vuelve a conectarla.",
         "tab": "settings", "experimento_id": None}])
    x, = alertas._fuente_tablero("acme", AHORA)
    assert "SECRETO" not in x["titulo"] and "access_token=***" in x["titulo"]
    assert x["huella"] == alertas.huella("tienda_rota", "-", "1")          # los dígitos del token tampoco entran


def test_tablero_la_huella_no_depende_del_idioma(monkeypatch):
    """Un descarte es del proyecto y lo comparten personas que miran en idiomas distintos: la misma alerta del
    Tablero, calculada en español y en inglés (textos distintos, miles con punto o con coma), tiene la misma
    huella; si cambia un número, cambia la huella."""
    import alertas
    import idiomas
    import tablero
    from flask_babel import gettext, ngettext
    gastado = {"valor": 1250000.5}

    def falso(cliente, ahora_iso=None, datos=None):
        cuenta = ngettext("%(num)s propuesta", "%(num)s propuestas", 2)
        return [
            {"tipo": "propuestas_pendientes", "nivel": "media", "tab": "experimentos", "experimento_id": 7,
             "texto": gettext("«%(nombre)s» tiene %(cuenta)s del motor esperando tu aprobación.", nombre="Cojín 3",
                              cuenta=cuenta)},
            {"tipo": "tope_alcanzado", "nivel": "media", "tab": "experimentos", "experimento_id": 7,
             "texto": gettext("«%(nombre)s» alcanzó su tope: %(gastado)s gastados de %(tope)s. Ciérralo o súbele el tope.",
                              nombre="Cojín 3", gastado=tablero.dinero(gastado["valor"], "COP"),
                              tope=tablero.dinero(1000000, "COP"))},
        ]
    monkeypatch.setattr(tablero, "alertas", falso)
    with idiomas.en_idioma("es"):
        es = alertas._fuente_tablero("acme", AHORA)
    with idiomas.en_idioma("en"):
        en = alertas._fuente_tablero("acme", AHORA)
    assert "esperando tu aprobación" in es[0]["titulo"] and "waiting for your approval" in en[0]["titulo"]
    assert "1.250.000,50 COP" in es[1]["titulo"] and "1,250,000.50 COP" in en[1]["titulo"]
    assert [(a["clave"], a["huella"]) for a in es] == [(a["clave"], a["huella"]) for a in en]
    gastado["valor"] = 1300000
    with idiomas.en_idioma("en"):
        otra = alertas._fuente_tablero("acme", AHORA)
    assert otra[0]["huella"] == es[0]["huella"] and otra[1]["huella"] != es[1]["huella"]


def test_tablero_la_huella_toma_los_numeros_del_texto_entero_no_del_recortado(monkeypatch):
    """El título se recorta a 400, pero los números de la huella salen del texto completo: si en un idioma el texto se
    corta antes del último número y en el otro no, la huella no puede cambiar."""
    import alertas
    import idiomas
    import tablero
    # El español es más largo y su último número cae después del carácter 400; el inglés cabe entero.
    largo = {"es": "Aviso largo del Tablero. " + "x" * 575 + " Código final 777", "en": "Dashboard notice. " + "x" * 280 + " Final code 777"}

    def falso(cliente, ahora_iso=None, datos=None):
        return [{"tipo": "tienda_rota", "nivel": "media", "tab": "settings", "experimento_id": None,
                 "texto": largo[idiomas.activo()]}]
    monkeypatch.setattr(tablero, "alertas", falso)
    with idiomas.en_idioma("es"):
        es, = alertas._fuente_tablero("acme", AHORA)
    with idiomas.en_idioma("en"):
        en, = alertas._fuente_tablero("acme", AHORA)
    assert len(largo["es"]) > 600 and len(es["titulo"]) == 400 and "777" not in es["titulo"]    # el 777 queda fuera del recorte
    assert len(en["titulo"]) < 400 and en["titulo"].endswith("777")                              # en inglés sí cabe
    assert es["huella"] == alertas.huella("tienda_rota", "-", "777")                             # y aun así entra en la huella
    assert en["huella"] == es["huella"]


def test_tablero_un_error_larguisimo_queda_acotado(monkeypatch):
    import alertas
    _texto_tablero(monkeypatch, [
        {"tipo": "tienda_rota", "nivel": "media", "texto": "La tienda X falló: " + "<html>" * 500,
         "tab": "settings", "experimento_id": None}])
    x, = alertas._fuente_tablero("acme", AHORA)
    assert len(x["titulo"]) == 400 and x["titulo"].startswith("La tienda X falló: ")


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


# =====================================================================================
# Tarea 4: fuentes de «decisión» y de «fallos» — Crear, orgánico, Sprints y Nicho
# (spec 2026-09-20-alertas-design.md §2.3, §2.4 y §12.7–8). Con filas reales en la base temporal.
# =====================================================================================

HACE_30_MIN = "2026-10-02T09:30:00"
HACE_2_H = "2026-10-02T08:00:00"
HACE_5_DIAS = "2026-09-27T10:00:00"
HACE_40_DIAS = "2026-08-23T10:00:00"


def _consultas(db, fn, *a, **k):
    """(resultado, número de sentencias SQL) de llamar a fn."""
    vistas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        vistas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        return fn(*a, **k), len(vistas)
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)


# ---------- Crear ----------

def _sesion(cf_id, estado, creado_en, error=None, accion="Zapatillas bajo la lluvia", cliente="acme"):
    import creative_flow
    creative_flow.crear(cliente, [], [], [], accion, 8, "tono", "A", legado_id=cf_id, creado_en=creado_en)
    campos = {"estado": estado}
    if error is not None:
        campos["error"] = error
    creative_flow.actualizar(cliente, cf_id, **campos)
    return cf_id


def test_las_diez_fuentes_se_registran_en_su_orden():
    import alertas
    assert [n for n, _ in alertas.FUENTES][:10] == ["llaves", "cuentas", "worker", "saldo", "tablero", "proyecto",
                                                    "crear", "organico", "sprints", "nicho"]


def test_crear_un_prompt_listo_reciente_no_molesta_y_uno_de_2_horas_si(base_temporal):
    import alertas
    _sesion("cf_20261002_093000_000001", "prompt_listo", HACE_30_MIN)
    assert alertas._fuente_crear("acme", AHORA) == []                               # la persona sigue trabajando
    _sesion("cf_20261002_080000_000002", "prompt_listo", HACE_2_H)
    x, = alertas._fuente_crear("acme", AHORA)
    assert x["clave"] == "crear:prompt_listo" and x["nivel"] == "atencion" and x["grupo"] == "decision"
    assert x["titulo"] == "1 prompt listo sin generar en Crear" and x["tab"] == "creativeflowplus"
    assert x["ancla"] == "cf-cf_20261002_080000_000002"
    assert x["url"] == "#creativeflowplus?cf=cf_20261002_080000_000002" and x["solo_admin"] is False
    assert x["huella"] == alertas.huella("cf_20261002_080000_000002")
    assert "generar cuesta lo que dice el botón" in x["detalle"]                    # nada se cobra sin ver el precio


def test_crear_una_sesion_con_dos_piezas_cuenta_una_vez(base_temporal):
    import alertas
    import db
    for cf, estado in (("cf_20261002_080000_000002", "prompt_listo"), ("cf_20261002_070000_000003", "error")):
        _sesion(cf, estado, HACE_2_H, error="falló" if estado == "error" else None)
        with db.conectar() as con:
            pz = con.execute(db.pieza.select().where(db.pieza.c.legado_id == cf)).mappings().first()
            fila = {k: v for k, v in pz.items() if k != "id"}
            con.execute(db.pieza.insert().values(**fila))                         # una segunda pieza clon igual
    listos, fallo = alertas._fuente_crear("acme", AHORA)
    assert listos["titulo"] == "1 prompt listo sin generar en Crear"
    assert listos["huella"] == alertas.huella("cf_20261002_080000_000002")
    assert fallo["clave"] == "crear:error:cf_20261002_070000_000003"


def test_crear_el_umbral_de_prompt_listo_es_estrictamente_mas_de_60_minutos(base_temporal):
    import alertas
    _sesion("cf_20261002_090000_000001", "prompt_listo", "2026-10-02T09:00:00")      # justo 60 min
    assert alertas._fuente_crear("acme", AHORA) == []
    _sesion("cf_20261002_085900_000002", "prompt_listo", "2026-10-02T08:59:00")      # 61 min
    x, = alertas._fuente_crear("acme", AHORA)
    assert x["huella"] == alertas.huella("cf_20261002_085900_000002")


def test_crear_los_prompts_listos_son_una_sola_alerta_con_el_conteo_y_ids_ordenados(base_temporal):
    import alertas
    _sesion("cf_20261002_080000_000009", "prompt_listo", HACE_2_H)
    _sesion("cf_20261001_080000_000003", "prompt_listo", "2026-10-01T08:00:00")
    _sesion("cf_20261001_090000_000004", "prompt_listo", "2026-10-01T09:00:00")
    x, = alertas._fuente_crear("acme", AHORA)
    assert x["titulo"] == "3 prompts listos sin generar en Crear"
    ids = ["cf_20261001_080000_000003", "cf_20261001_090000_000004", "cf_20261002_080000_000009"]
    assert x["huella"] == alertas.huella(*ids) and x["ancla"] == "cf-cf_20261001_080000_000003"
    _sesion("cf_20261002_050000_000010", "prompt_listo", "2026-10-02T05:00:00")      # otro más: otra huella
    assert alertas._fuente_crear("acme", AHORA)[0]["huella"] != x["huella"]


def test_crear_solo_cuentan_los_prompt_listo_viejos_de_los_ultimos_30_dias(base_temporal):
    """Un prompt_pendiente (sin armar), un video listo o generando no son «prompt listo»; uno de hace 40 días tampoco."""
    import alertas
    _sesion("cf_a", "prompt_pendiente", HACE_2_H)
    _sesion("cf_b", "video_listo", HACE_2_H)
    _sesion("cf_c", "video_generando", HACE_2_H)
    _sesion("cf_d", "prompt_listo", HACE_40_DIAS)
    assert alertas._fuente_crear("acme", AHORA) == []


def test_crear_una_sesion_en_error_es_una_alerta_por_sesion(base_temporal):
    import alertas
    _sesion("cf_e1", "error", HACE_5_DIAS, error="WaveSpeed rechazó el prompt: contenido no permitido",
            accion="  Zapatillas\n bajo   la lluvia ")
    _sesion("cf_e2", "error", HACE_30_MIN, error=None, accion="x" * 100)
    por = _por_clave(alertas._fuente_crear("acme", AHORA))
    assert set(por) == {"crear:error:cf_e1", "crear:error:cf_e2"}
    e1, e2 = por["crear:error:cf_e1"], por["crear:error:cf_e2"]
    assert e1["nivel"] == "atencion" and e1["grupo"] == "fallos" and e1["tab"] == "creativeflowplus"
    assert e1["ancla"] == "cf-cf_e1" and e1["entidad"] == "cf_e1" and e1["solo_admin"] is False
    assert e1["titulo"] == "Falló «Zapatillas bajo la lluvia» en Crear"            # una línea, sin saltos
    assert e1["detalle"] == "WaveSpeed rechazó el prompt: contenido no permitido Rearma el prompt o vuelve a generar."
    assert e1["huella"] == alertas.huella("WaveSpeed rechazó el prompt: contenido no permitido")
    assert e2["titulo"] == "Falló «" + "x" * 60 + "» en Crear"                      # la acción central, recortada a 60
    assert e2["detalle"] == "Rearma el prompt o vuelve a generar." and e2["huella"] == alertas.huella("")


def test_crear_un_error_de_hace_40_dias_es_historia_y_el_de_30_dias_justos_todavia_cuenta(base_temporal):
    import alertas
    _sesion("cf_viejo", "error", HACE_40_DIAS, error="viejo")
    _sesion("cf_justo", "error", "2026-09-02T10:00:00", error="justo")                # 30 días exactos
    _sesion("cf_pasado", "error", "2026-09-02T09:59:00", error="pasado")              # 30 días y un minuto
    assert _claves(alertas._fuente_crear("acme", AHORA)) == ["crear:error:cf_justo"]


def test_crear_el_error_sale_sin_tokens_y_acotado_a_200(base_temporal):
    import alertas
    _sesion("cf_t", "error", HACE_30_MIN, error="Falló: https://api.x/y?access_token=SECRETO&z=1 " + "<html>" * 100)
    x, = alertas._fuente_crear("acme", AHORA)
    assert "SECRETO" not in x["detalle"] and "access_token=***" in x["detalle"]
    assert len(x["detalle"]) <= 200 + len(" Rearma el prompt o vuelve a generar.")
    assert x["huella"] == alertas.huella(x["detalle"][: -len(" Rearma el prompt o vuelve a generar.")])


def test_crear_el_error_sale_sin_bearer_ni_password_ni_llaves_sk(base_temporal):
    """El error de un proveedor llega tal cual a la alerta: `_limpio` usa `monitoreo.limpiar_texto`, que además de los
    tokens en URLs de `cola.sin_token` cubre cabeceras `Bearer`, llaves `sk-…` y `password=`."""
    import alertas
    _sesion("cf_b", "error", HACE_30_MIN,
            error="401 de WaveSpeed. Authorization: Bearer abc.def.ghi-0123456789 password=hunter2 sk-abcdefghijklmnop1234")
    x, = alertas._fuente_crear("acme", AHORA)
    for secreto in ("abc.def.ghi", "0123456789", "hunter2", "sk-abcdefghijkl"):
        assert secreto not in x["detalle"] and secreto not in x["titulo"]
    assert "password=***" in x["detalle"] and x["detalle"].startswith("401 de WaveSpeed. Authorization:")
    assert x["huella"] == alertas.huella(x["detalle"][: -len(" Rearma el prompt o vuelve a generar.")])   # la huella, del texto limpio


def test_limpio_sin_texto_es_vacio_y_recorta(base_temporal):
    import alertas
    assert alertas._limpio(None) == "" and alertas._limpio("") == ""
    assert len(alertas._limpio("p" * 500)) == 200 and len(alertas._limpio("p" * 500, 50)) == 50
    assert len(alertas._limpio("p" * 500, None)) == 500                               # None: sin recorte


def test_crear_no_mezcla_proyectos_ni_cuenta_las_finales(base_temporal):
    import alertas
    import creative_flow
    _sesion("cf_otro", "error", HACE_30_MIN, error="de otro", cliente="otro")
    _sesion("cf_base", "video_listo", HACE_5_DIAS)
    fid = creative_flow.crear_final("acme", "cf_base", "es", "CO")
    creative_flow.actualizar_final("acme", fid, estado="error")                      # una final en error NO es una sesión de Crear
    assert alertas._fuente_crear("acme", AHORA) == []
    assert _claves(alertas._fuente_crear("otro", AHORA)) == ["crear:error:cf_otro"]


def test_crear_las_finales_de_una_sesion_no_la_duplican(base_temporal):
    """Una final cuelga del mismo concepto que su sesión: sin filtrar `tipo != final` cada final repetiría la alerta."""
    import alertas
    import creative_flow
    _sesion("cf_con_finales", "error", HACE_5_DIAS, error="falló")
    _sesion("cf_listo_con_finales", "prompt_listo", HACE_2_H)
    for cf in ("cf_con_finales", "cf_listo_con_finales"):
        for pais in ("CO", "MX"):
            creative_flow.crear_final("acme", cf, "es", pais)
    a = alertas._fuente_crear("acme", AHORA)
    assert sorted(_claves(a)) == ["crear:error:cf_con_finales", "crear:prompt_listo"]
    assert _por_clave(a)["crear:prompt_listo"]["titulo"] == "1 prompt listo sin generar en Crear"


def test_crear_el_estado_sale_igual_que_creative_flow_cargar(base_temporal):
    """El estado se deriva como `creative_flow._a_dict` (estado_legado, o el de la pieza), sin cargar nada."""
    import alertas
    import creative_flow
    for i, (estado, creado) in enumerate([("prompt_listo", HACE_2_H), ("error", HACE_5_DIAS), ("video_listo", HACE_2_H),
                                          ("prompt_pendiente", HACE_2_H), ("video_generando", HACE_2_H)]):
        _sesion(f"cf_{i}", estado, creado, error="falló" if estado == "error" else None)
    cargadas = creative_flow.cargar("acme")
    esperadas = {f"crear:error:{c}" for c, s in cargadas.items() if s["estado"] == "error"}
    esperadas |= {"crear:prompt_listo"} if any(s["estado"] == "prompt_listo" for s in cargadas.values()) else set()
    assert set(_claves(alertas._fuente_crear("acme", AHORA))) == esperadas == {"crear:error:cf_1", "crear:prompt_listo"}


def test_crear_una_sesion_sin_estado_legado_usa_el_estado_de_su_pieza(base_temporal):
    """Las sesiones anteriores al `estado_legado` solo traen el estado de la pieza: `pendiente` es un prompt listo
    (`creative_flow._PIEZA_A_ESTADO`) y `error` es un error, igual que en `creative_flow.cargar`."""
    import alertas
    import creative_flow
    import db
    _sesion("cf_vieja_listo", "prompt_listo", HACE_2_H)
    _sesion("cf_vieja_error", "error", HACE_5_DIAS, error="falló")
    _sesion("cf_vieja_video", "video_listo", HACE_2_H)
    with db.conectar() as con:
        for f in con.execute(db.concepto.select().where(db.concepto.c.cliente == "acme")).fetchall():
            extra = {k: v for k, v in (f.extra or {}).items() if k != "estado_legado"}
            con.execute(db.concepto.update().where(db.concepto.c.id == f.id).values(extra=extra))
    estados = {cf: s["estado"] for cf, s in creative_flow.cargar("acme").items()}
    assert estados == {"cf_vieja_listo": "prompt_listo", "cf_vieja_error": "error", "cf_vieja_video": "video_listo"}
    assert sorted(_claves(alertas._fuente_crear("acme", AHORA))) == ["crear:error:cf_vieja_error", "crear:prompt_listo"]


def test_crear_corre_una_sola_consulta_y_nunca_carga_las_sesiones(base_temporal, monkeypatch):
    import alertas
    import creative_flow
    monkeypatch.setattr(creative_flow, "cargar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("cargó todo")))
    for i in range(12):
        _sesion(f"cf_{i:02d}", ["prompt_listo", "error", "video_listo"][i % 3], HACE_2_H, error="falló")
    lista, n = _consultas(base_temporal, alertas._fuente_crear, "acme", AHORA)
    assert n == 1 and len(lista) == 5                                                  # 1 de prompts listos + 4 errores


def test_calcular_no_crece_con_las_sesiones_de_crear(base_temporal, monkeypatch, tmp_path):
    """3 sesiones o 30: las mismas sentencias SQL (la pestaña se calcula en cada carga de página)."""
    import alertas
    _proyecto(monkeypatch, tmp_path)

    def sembrar(desde, hasta):
        for i in range(desde, hasta):
            _sesion(f"cf_{i:03d}", ["prompt_listo", "error", "video_listo"][i % 3], HACE_2_H, error="falló")
    sembrar(0, 3)
    alertas.calcular("acme", AHORA)                                                    # calienta cachés de módulos
    _, con_3 = _consultas(base_temporal, alertas.calcular, "acme", AHORA)
    sembrar(3, 30)
    todas, con_30 = _consultas(base_temporal, alertas.calcular, "acme", AHORA)
    assert con_30 == con_3
    assert sum(1 for a in todas if a["clave"].startswith("crear:error:")) == 10        # y de verdad vio las 30


# ---------- orgánico ----------

def _publicacion(estado, actualizado_en, error=None, plataforma="instagram", accion="Pantuflas de lana", cliente="acme",
                 cf_id=None):
    """Una publicación de la pieza de una sesión de Crear; devuelve su id."""
    import creative_flow
    import db
    cf_id = cf_id or f"cf_pub_{db.ahora()}_{plataforma}_{estado}_{actualizado_en}"
    if not creative_flow.pieza_id_por_legado(cliente, cf_id):
        _sesion(cf_id, "video_listo", HACE_5_DIAS, accion=accion, cliente=cliente)
    pid = creative_flow.pieza_id_por_legado(cliente, cf_id)
    with db.conectar() as con:
        return con.execute(db.publicacion.insert().values(
            cliente=cliente, creado_en=actualizado_en, actualizado_en=actualizado_en, pieza_id=pid, plataforma=plataforma,
            estado=estado, caption="texto", error=error, origen="manual", extra={})).inserted_primary_key[0]


def test_organico_una_publicacion_en_error_es_una_alerta(base_temporal):
    import alertas
    pid = _publicacion("error", HACE_5_DIAS, error="TikTok: el video dura más del máximo permitido", plataforma="tiktok")
    x, = alertas._fuente_organico("acme", AHORA)
    assert x["clave"] == f"organico:error:{pid}" and x["nivel"] == "atencion" and x["grupo"] == "fallos"
    assert x["titulo"] == "Falló la publicación en TikTok de «Pantuflas de lana»" and x["tab"] == "experimentos"
    assert x["detalle"] == "TikTok: el video dura más del máximo permitido Reintenta desde la pieza."
    assert x["huella"] == alertas.huella("TikTok: el video dura más del máximo permitido")
    assert x["entidad"] == pid and x["ancla"] is None and x["url"] is None and x["solo_admin"] is False


def test_organico_solo_cuentan_los_errores_de_los_ultimos_30_dias(base_temporal):
    import alertas
    _publicacion("error", HACE_40_DIAS, error="viejo", plataforma="facebook")
    _publicacion("publicada", HACE_5_DIAS, plataforma="instagram")
    _publicacion("en_cola", HACE_5_DIAS, plataforma="youtube")
    _publicacion("publicando", HACE_5_DIAS, plataforma="tiktok")
    _publicacion("error", "2026-09-02T10:00:00", error="justo", plataforma="youtube", accion="Otra")      # 30 días exactos
    _publicacion("error", "2026-09-02T09:59:00", error="pasado", plataforma="facebook", accion="Otra más")
    _publicacion("error", HACE_5_DIAS, error="de otro", cliente="otro")
    a = alertas._fuente_organico("acme", AHORA)
    assert [x["huella"] for x in a] == [alertas.huella("justo")]


def test_organico_error_sin_tokens_y_sin_nombre_de_pieza(base_temporal):
    import alertas
    _publicacion("error", HACE_5_DIAS, error="Meta: access_token=SECRETO&x=1 " + "z" * 400, plataforma="facebook", accion="")
    x, = alertas._fuente_organico("acme", AHORA)
    assert "SECRETO" not in x["detalle"] and "access_token=***" in x["detalle"]
    assert x["titulo"].startswith("Falló la publicación en Facebook (Página) de «pieza ")
    assert len(x["detalle"]) <= 200 + len(" Reintenta desde la pieza.")


def test_organico_corre_una_sola_consulta_sin_importar_cuantas_publicaciones(base_temporal):
    import alertas
    for i in range(8):
        _publicacion("error", HACE_5_DIAS, error=f"falló {i}", plataforma="instagram", accion=f"Pieza {i}", cf_id=f"cf_p{i}")
    lista, n = _consultas(base_temporal, alertas._fuente_organico, "acme", AHORA)
    assert n == 1 and len(lista) == 8


# ---------- Sprints ----------

def _sprint(nombre="Octubre", estado=None, archivado=False, inicio="2026-10-01", cliente="acme"):
    from sprints import datos
    sid = datos.crear_sprint(cliente, nombre, inicio, "2026-10-31")
    if estado:
        datos.actualizar_sprint(cliente, sid, estado=estado)
    if archivado:
        datos.archivar_sprint(cliente, sid)
    return sid


def _campana(sid, estado=None, cliente="acme"):
    from sprints import datos
    personas = datos.personas(cliente)
    pid = personas[0]["id"] if personas else datos.crear_persona(cliente, "Carla")
    cid = datos.agregar_campana(cliente, sid, pid, "pantuflas")
    if estado:
        datos.actualizar_campana(cliente, cid, estado=estado)
    return cid


def _idea(cid, estado_idea=None, cf_estado=None, revision="pendiente", qa=None, pieza_estado=None, cliente="acme"):
    """Una idea de la campaña (propuesta, o aprobada si ya tiene sesión); con `cf_estado` tiene su sesión de Crear
    (y `pieza_estado` fuerza el estado de su pieza)."""
    import db
    from sprints import datos
    estado_idea = estado_idea or ("aprobada" if cf_estado else "propuesta")
    cp = datos.crear_idea(cliente, cid, "video", f"Idea {cid}-{estado_idea}", "escena", estado_idea=estado_idea)
    if cf_estado:
        cf = f"cf_sp_{cp}"
        _sesion(cf, cf_estado, HACE_5_DIAS, cliente=cliente)
        if pieza_estado:
            with db.conectar() as con:
                con.execute(db.pieza.update().where(db.pieza.c.legado_id == cf).values(estado=pieza_estado))
        datos.actualizar_idea(cliente, cp, cf_id=cf, revision=revision, qa=qa)
    return cp


def test_sprint_ideas_propuestas_en_una_campana_en_ideas_propuestas(base_temporal):
    import alertas
    sid = _sprint("Octubre")
    cid = _campana(sid, estado="ideas_propuestas")
    a1, a2 = _idea(cid), _idea(cid)
    _idea(cid, estado_idea="aprobada")
    _idea(cid, estado_idea="descartada")
    otra = _campana(sid, estado="ideas_aprobadas")
    _idea(otra)                                                                       # propuesta, pero su campaña no espera ideas
    x, = alertas._fuente_sprints("acme", AHORA)
    assert x["clave"] == f"sprint:ideas:{sid}" and x["nivel"] == "atencion" and x["grupo"] == "decision"
    assert x["titulo"] == "2 ideas por aprobar en el sprint «Octubre»" and x["tab"] == "sprints"
    assert x["url"] == f"/cliente/acme/sprints/{sid}" and x["entidad"] == sid and x["ancla"] is None
    assert x["huella"] == alertas.huella(a1, a2)
    assert "para poder generar el lote" in x["detalle"]


def test_sprint_ideas_en_singular(base_temporal):
    import alertas
    cid = _campana(_sprint("Octubre"), estado="ideas_propuestas")
    _idea(cid)
    x, = alertas._fuente_sprints("acme", AHORA)
    assert x["titulo"] == "1 idea por aprobar en el sprint «Octubre»"


def test_sprint_revision_piezas_terminadas_sin_revisar_igual_que_el_resumen(base_temporal):
    import alertas
    from sprints import revision
    sid = _sprint("Octubre")
    cid = _campana(sid, estado="revision")
    p1 = _idea(cid, cf_estado="video_listo", revision="pendiente")
    p2 = _idea(cid, cf_estado="video_listo", revision="pendiente", pieza_estado="degradada")
    _idea(cid, cf_estado="video_listo", revision="aprobada")
    _idea(cid, cf_estado="video_listo", revision="rechazada")
    _idea(cid, cf_estado="video_generando", revision="pendiente")                     # todavía no terminó
    _idea(cid, cf_estado="error", revision="pendiente", pieza_estado="error")         # fallida: no se revisa
    _idea(cid, estado_idea="descartada", cf_estado="video_listo", revision="pendiente")   # descartada: no es una pieza
    x, = [a for a in alertas._fuente_sprints("acme", AHORA) if a["clave"].startswith("sprint:revision:")]
    assert x["clave"] == f"sprint:revision:{sid}" and x["nivel"] == "atencion" and x["grupo"] == "decision"
    assert x["titulo"] == "2 piezas por revisar en el sprint «Octubre»" and x["huella"] == alertas.huella(2)
    assert x["url"] == f"/cliente/acme/sprints/{sid}" and x["tab"] == "sprints"
    assert revision.resumen("acme", sid)["sin_revisar"] == 2                           # la misma cuenta que el resumen del sprint
    assert p1 != p2


def test_sprint_fallos_piezas_en_error_o_con_qa_que_falla(base_temporal):
    import alertas
    from sprints import revision
    sid = _sprint("Octubre")
    cid = _campana(sid, estado="revision")
    e = _idea(cid, cf_estado="error", pieza_estado="error")
    q = _idea(cid, cf_estado="video_listo", qa={"veredicto": "falla", "puntaje": 40})
    _idea(cid, cf_estado="video_listo", qa={"veredicto": "pasa", "puntaje": 90})
    _idea(cid, cf_estado="video_listo")
    _idea(cid, estado_idea="descartada", cf_estado="error", pieza_estado="error")
    x, = [a for a in alertas._fuente_sprints("acme", AHORA) if a["clave"].startswith("sprint:fallos:")]
    assert x["clave"] == f"sprint:fallos:{sid}" and x["nivel"] == "atencion" and x["grupo"] == "fallos"
    assert x["titulo"] == "2 piezas fallidas en el sprint «Octubre»" and x["huella"] == alertas.huella(*sorted([e, q]))
    assert x["url"] == f"/cliente/acme/sprints/{sid}" and "vuelve a pasar por el costo" in x["detalle"]
    assert revision.resumen("acme", sid)["error"] == 1                                 # el error del resumen es una de las dos


def test_sprint_referencias_con_el_analisis_en_error(base_temporal):
    import alertas
    from sprints import datos
    sid = _sprint("Octubre")
    cid = _campana(sid)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://x/1.png")
    r2 = datos.agregar_referencia("acme", cid, "imagen", "https://x/2.png")
    r3 = datos.agregar_referencia("acme", cid, "imagen", "https://x/3.png")
    datos.actualizar_referencia("acme", r1, analisis_estado="error")
    datos.actualizar_referencia("acme", r2, analisis_estado="error")
    datos.actualizar_referencia("acme", r3, analisis_estado="listo")
    datos.agregar_referencia("acme", cid, "imagen", "https://x/4.png")                 # sin analizar todavía: no es un error
    x, = alertas._fuente_sprints("acme", AHORA)
    assert x["clave"] == f"sprint:referencias:{sid}" and x["nivel"] == "info" and x["grupo"] == "fallos"
    assert x["titulo"] == "2 referencias sin analizar en el sprint «Octubre»" and x["huella"] == alertas.huella(r1, r2)
    assert x["url"] == f"/cliente/acme/sprints/{sid}" and x["entidad"] == sid


def test_sprint_completado_o_archivado_no_alerta(base_temporal):
    import alertas
    from sprints import datos
    for kw in ({"estado": "completado"}, {"archivado": True}):
        cid = _campana(_sprint(f"Cerrado {kw}", **kw), estado="ideas_propuestas")
        _idea(cid)
        _idea(cid, cf_estado="error", pieza_estado="error")
        r = datos.agregar_referencia("acme", cid, "imagen", "https://x/1.png")
        datos.actualizar_referencia("acme", r, analisis_estado="error")
    assert alertas._fuente_sprints("acme", AHORA) == []


def test_sprint_un_sprint_vivo_de_otro_proyecto_no_se_mezcla(base_temporal):
    """Un sprint VIVO de `otro` (ideas propuestas, una pieza en error y una referencia en error) alerta en `otro` y
    no en `acme`, que tiene el suyo. (Con solo sprints cerrados la prueba no probaba nada: no habría alertas en
    ningún proyecto.)"""
    import alertas
    from sprints import datos
    propio = _sprint("Propio")
    _idea(_campana(propio, estado="ideas_propuestas"))
    ajeno = _sprint("Ajeno", cliente="otro")
    cid = _campana(ajeno, estado="ideas_propuestas", cliente="otro")
    _idea(cid, cliente="otro")
    _idea(cid, cf_estado="error", pieza_estado="error", cliente="otro")
    r = datos.agregar_referencia("otro", cid, "imagen", "https://x/otro.png")
    datos.actualizar_referencia("otro", r, analisis_estado="error")
    assert _claves(alertas._fuente_sprints("acme", AHORA)) == [f"sprint:ideas:{propio}"]
    de_otro = alertas._fuente_sprints("otro", AHORA)
    assert sorted(_claves(de_otro)) == sorted([f"sprint:ideas:{ajeno}", f"sprint:fallos:{ajeno}",
                                               f"sprint:referencias:{ajeno}"])
    assert all(a["titulo"].endswith("«Ajeno»") and a["url"] == f"/cliente/otro/sprints/{ajeno}" for a in de_otro)


def test_sprint_las_alertas_siguen_el_orden_de_la_lista_de_sprints(base_temporal):
    import alertas
    viejo = _sprint("Septiembre", inicio="2026-09-01")
    nuevo = _sprint("Octubre", inicio="2026-10-01")
    for sid in (viejo, nuevo):
        _idea(_campana(sid, estado="ideas_propuestas"))
    assert _claves(alertas._fuente_sprints("acme", AHORA)) == [f"sprint:ideas:{nuevo}", f"sprint:ideas:{viejo}"]


def test_sprint_una_reserva_vencida_no_es_una_pieza(base_temporal):
    """Una idea reservada para generar cuyo proceso murió (placeholder vencido) no cuenta como pieza."""
    import alertas
    from sprints import datos
    sid = _sprint("Octubre")
    cid = _campana(sid, estado="ideas_aprobadas")
    cp = _idea(cid, estado_idea="aprobada")
    datos.actualizar_idea("acme", cp, cf_id=datos.reserva_placeholder(cp, ahora=1_000), qa={"veredicto": "falla"})
    assert alertas._fuente_sprints("acme", AHORA) == []


def test_sprints_corre_las_mismas_consultas_con_1_o_con_6_sprints(base_temporal):
    import alertas
    from sprints import datos

    def sembrar(n):
        for i in range(n):
            sid = _sprint(f"Sprint {i}", inicio=f"2026-0{1 + i % 9}-01")
            for _ in range(2):
                cid = _campana(sid, estado="ideas_propuestas")
                _idea(cid)
                _idea(cid, cf_estado="video_listo")
                _idea(cid, cf_estado="error", pieza_estado="error")
                datos.actualizar_referencia("acme", datos.agregar_referencia("acme", cid, "imagen", f"https://x/{i}.png"),
                                            analisis_estado="error")
    sembrar(1)
    a1, con_1 = _consultas(base_temporal, alertas._fuente_sprints, "acme", AHORA)
    sembrar(5)
    a6, con_6 = _consultas(base_temporal, alertas._fuente_sprints, "acme", AHORA)
    assert con_1 == con_6 == 2 and len(a1) == 4 and len(a6) == 24


# ---------- Nicho ----------

def _estudio(nombre="Pantuflas", archivado=False, cliente="acme"):
    from nicho import datos
    eid = datos.crear_estudio(cliente, nombre, tema="t")
    if archivado:
        datos.archivar_estudio(cliente, eid)
    return eid


def _proponer(eid, n, nombre="Sub"):
    """n sub-avatares propuestos en el estudio."""
    from nicho import datos
    datos.guardar_generacion("acme", eid, [{"nombre": "Núcleo", "deseo": "d", "resumen": "r",
                                            "sub_avatares": [{"nombre": f"{nombre} {i}", "deseo": "d", "base": "emocion"}
                                                             for i in range(n)]}])


def test_nicho_avatares_propuestos_son_una_sola_alerta_del_proyecto(base_temporal):
    import alertas
    assert alertas._fuente_nicho("acme", AHORA) == []
    _proponer(_estudio("Uno"), 2)
    _proponer(_estudio("Dos"), 1)
    x, = alertas._fuente_nicho("acme", AHORA)
    assert x["clave"] == "nicho:avatares" and x["nivel"] == "atencion" and x["grupo"] == "decision"
    assert x["titulo"] == "3 avatares propuestos por aprobar" and x["tab"] == "nicho"
    assert x["url"] == "/cliente/acme/nicho/avatares" and x["huella"] == alertas.huella(3)
    assert "cada uno se vuelve una persona de Sprints" in x["detalle"] and x["entidad"] is None


def test_nicho_un_avatar_en_singular_y_los_de_un_estudio_archivado_no_cuentan(base_temporal):
    import alertas
    _proponer(_estudio("Viejo", archivado=True), 4)
    _proponer(_estudio("Nuevo"), 1)
    x, = alertas._fuente_nicho("acme", AHORA)
    assert x["titulo"] == "1 avatar propuesto por aprobar"


def test_nicho_aprobar_un_avatar_baja_el_conteo_y_aprobarlos_todos_quita_la_alerta(base_temporal):
    import alertas
    from nicho import datos
    eid = _estudio()
    _proponer(eid, 2)
    antes, = alertas._fuente_nicho("acme", AHORA)
    subs = datos.avatares("acme", eid)[0]["subs"]
    datos.descartar_avatar("acme", subs[0]["id"])
    despues, = alertas._fuente_nicho("acme", AHORA)
    assert despues["titulo"] == "1 avatar propuesto por aprobar" and despues["huella"] != antes["huella"]
    datos.descartar_avatar("acme", subs[1]["id"])
    assert alertas._fuente_nicho("acme", AHORA) == []


def test_nicho_una_investigacion_interrumpida_es_un_fallo(base_temporal):
    import alertas
    from nicho import datos
    eid = _estudio("Pantuflas")
    datos.iniciar_investigacion("acme", eid, {"estado": "interrumpida", "ultimo_error": "Apify: límite del plan alcanzado"})
    x, = alertas._fuente_nicho("acme", AHORA)
    assert x["clave"] == f"nicho:error:{eid}" and x["nivel"] == "atencion" and x["grupo"] == "fallos"
    assert x["titulo"] == "Se interrumpió la investigación de «Pantuflas»" and x["tab"] == "nicho"
    assert x["url"] == f"/cliente/acme/nicho/{eid}" and x["entidad"] == eid
    assert x["detalle"] == "Apify: límite del plan alcanzado Ábrela y pulsa «Reanudar» para retomarla donde quedó."
    assert x["huella"] == alertas.huella("Apify: límite del plan alcanzado")
    datos.actualizar_investigacion("acme", eid, lambda i: {**i, "estado": "lista"})                    # se resolvió: desaparece
    assert alertas._fuente_nicho("acme", AHORA) == []


def test_nicho_una_investigacion_detenida_es_un_fallo_salvo_que_la_persona_la_cancelara(base_temporal):
    import alertas
    from nicho import datos
    eid = _estudio("Pantuflas")
    datos.iniciar_investigacion("acme", eid, {"estado": "detenida", "detenida_por": "cancelada"})
    assert alertas._fuente_nicho("acme", AHORA) == []                                                  # lo decidió la persona
    datos.actualizar_investigacion("acme", eid, lambda i: {**i, "detenida_por": "sin consultas"})
    x, = alertas._fuente_nicho("acme", AHORA)
    assert x["clave"] == f"nicho:error:{eid}" and x["titulo"] == "Se detuvo la investigación de «Pantuflas»"
    assert x["detalle"] == "Detenida: sin consultas. Ábrela en el estudio para reanudarla o investigar de nuevo."
    assert x["huella"] == alertas.huella("sin consultas")


def test_nicho_la_huella_de_una_investigacion_detenida_no_depende_del_idioma_de_quien_mira(base_temporal):
    """El motivo se guarda como msgid (`N_`) y se traduce al mostrarlo; la huella usa lo guardado, así un descarte
    hecho en inglés sigue valiendo en español."""
    import alertas
    import idiomas
    from nicho import datos
    eid = _estudio("Pantuflas")
    datos.iniciar_investigacion("acme", eid, {"estado": "detenida", "detenida_por": "sin consultas"})
    es, = alertas._fuente_nicho("acme", AHORA)
    with idiomas.en_idioma("en"):
        en, = alertas._fuente_nicho("acme", AHORA)
    assert en["huella"] == es["huella"] == alertas.huella("sin consultas")
    assert en["detalle"] != es["detalle"] and "sin consultas" not in en["detalle"]          # lo que se ve sí se traduce


def test_nicho_un_error_de_generacion_en_el_estudio_es_un_fallo(base_temporal):
    import alertas
    from nicho import datos
    eid = _estudio("Pantuflas")
    datos.actualizar_extra_estudio("acme", eid, lambda x: {**x, "ultimo_error": "Claude devolvió una respuesta vacía"})
    x, = alertas._fuente_nicho("acme", AHORA)
    assert x["clave"] == f"nicho:error:{eid}" and x["titulo"] == "Falló la generación de avatares en «Pantuflas»"
    assert x["detalle"] == "Claude devolvió una respuesta vacía Vuelve a generar desde el estudio."
    assert x["huella"] == alertas.huella("Claude devolvió una respuesta vacía") and x["url"] == f"/cliente/acme/nicho/{eid}"


def test_nicho_una_sola_alerta_de_error_por_estudio_y_la_investigacion_manda(base_temporal):
    import alertas
    from nicho import datos
    eid = _estudio("Pantuflas")
    datos.actualizar_extra_estudio("acme", eid, lambda x: {**x, "ultimo_error": "viejo"})
    datos.iniciar_investigacion("acme", eid, {"estado": "interrumpida", "ultimo_error": "nuevo"})
    x, = alertas._fuente_nicho("acme", AHORA)
    assert x["titulo"].startswith("Se interrumpió la investigación") and x["huella"] == alertas.huella("nuevo")


def test_nicho_estudios_archivados_ocultos_y_sin_error_no_alertan(base_temporal):
    import alertas
    from nicho import datos
    sano = _estudio("Sano")
    datos.iniciar_investigacion("acme", sano, {"estado": "consultas"})                                  # viva: no es un fallo
    viejo = _estudio("Archivado", archivado=True)
    datos.actualizar_extra_estudio("acme", viejo, lambda x: {**x, "ultimo_error": "falló"})
    oculto, _ = datos.estudio_manual("acme")                                                              # el de avatares a mano
    datos.actualizar_extra_estudio("acme", oculto, lambda x: {**x, "ultimo_error": "falló"})
    assert alertas._fuente_nicho("acme", AHORA) == []


def test_nicho_el_error_sale_sin_tokens_y_acotado_a_200(base_temporal):
    import alertas
    from nicho import datos
    eid = _estudio()
    datos.iniciar_investigacion("acme", eid, {"estado": "interrumpida", "ultimo_error": "Apify: token=SECRETO&x=1 " + "p" * 400})
    x, = alertas._fuente_nicho("acme", AHORA)
    assert "SECRETO" not in x["detalle"] and "token=***" in x["detalle"]
    assert len(x["detalle"]) <= 200 + len(" Ábrela y pulsa «Reanudar» para retomarla donde quedó.")


def test_nicho_el_error_de_generacion_tambien_sale_sin_tokens_y_acotado(base_temporal):
    import alertas
    from nicho import datos
    eid = _estudio()
    datos.actualizar_extra_estudio("acme", eid, lambda x: {**x, "ultimo_error": "Claude: key=SECRETO&x=1 " + "p" * 400})
    x, = alertas._fuente_nicho("acme", AHORA)
    assert "SECRETO" not in x["detalle"] and "key=***" in x["detalle"]
    assert len(x["detalle"]) <= 200 + len(" Vuelve a generar desde el estudio.")


def test_nicho_los_errores_de_otro_proyecto_no_se_mezclan(base_temporal):
    """Los estudios de `otro` (uno con el error de su última generación y otro con la investigación interrumpida)
    alertan en `otro` y no en `acme`, que tiene el suyo."""
    import alertas
    from nicho import datos
    propio = _estudio("Propio")
    datos.actualizar_extra_estudio("acme", propio, lambda x: {**x, "ultimo_error": "falló aquí"})
    con_error = _estudio("Ajeno con error", cliente="otro")
    datos.actualizar_extra_estudio("otro", con_error, lambda x: {**x, "ultimo_error": "falló allá"})
    interrumpido = _estudio("Ajeno interrumpido", cliente="otro")
    datos.iniciar_investigacion("otro", interrumpido, {"estado": "interrumpida", "ultimo_error": "se cortó allá"})
    assert _claves(alertas._fuente_nicho("acme", AHORA)) == [f"nicho:error:{propio}"]
    de_otro = alertas._fuente_nicho("otro", AHORA)
    assert sorted(_claves(de_otro)) == sorted([f"nicho:error:{con_error}", f"nicho:error:{interrumpido}"])
    assert all(a["url"].startswith("/cliente/otro/nicho/") for a in de_otro)


def test_nicho_corre_las_mismas_consultas_con_1_o_con_6_estudios(base_temporal):
    import alertas
    from nicho import datos

    def sembrar(n):
        for i in range(n):
            eid = _estudio(f"Estudio {i}")
            _proponer(eid, 2)
            datos.iniciar_investigacion("acme", eid, {"estado": "interrumpida", "ultimo_error": f"falló {i}"})
    sembrar(1)
    a1, con_1 = _consultas(base_temporal, alertas._fuente_nicho, "acme", AHORA)
    sembrar(5)
    a6, con_6 = _consultas(base_temporal, alertas._fuente_nicho, "acme", AHORA)
    assert con_1 == con_6 == 4 and len(a1) == 2 and len(a6) == 7                                        # 1 de errores + 3 de avatares


# ---------- las rutas armadas sin Flask ----------

def test_las_rutas_armadas_sin_flask_son_las_reales(base_temporal):
    """`alertas` no puede usar `url_for` (nunca importa `dashboard`): si una ruta cambia, esto avisa."""
    import alertas
    import dashboard
    from flask import url_for
    with dashboard.app.test_request_context():
        assert alertas._url_proyecto("acme", "sprints", 7) == url_for("sprints.ver", cliente="acme", sid=7)
        assert alertas._url_proyecto("acme", "nicho", 5) == url_for("nicho.ver", cliente="acme", eid=5)
        assert alertas._url_proyecto("acme", "nicho", "avatares") == url_for("nicho.avatares_proyecto", cliente="acme")
        assert alertas._url_proyecto("a b", "nicho", 5) == url_for("nicho.ver", cliente="a b", eid=5)      # también escapa


# ---------- las diez juntas, con lo real ----------

def test_las_diez_fuentes_reales_corren_juntas_y_el_cliente_ve_lo_suyo(base_temporal, monkeypatch, tmp_path):
    import alertas
    from nicho import datos as nicho
    _proyecto(monkeypatch, tmp_path)
    _sesion("cf_listo", "prompt_listo", HACE_2_H)
    _sesion("cf_error", "error", HACE_5_DIAS, error="falló")
    _publicacion("error", HACE_5_DIAS, error="falló", plataforma="tiktok")
    sid = _sprint("Octubre")
    _idea(_campana(sid, estado="ideas_propuestas"))
    eid = _estudio()
    _proponer(eid, 1)
    nicho.iniciar_investigacion("acme", eid, {"estado": "interrumpida", "ultimo_error": "falló"})
    todas = alertas.calcular("acme", AHORA)
    assert not [a for a in todas if a["clave"].startswith("revision:")]
    claves = set(_claves(todas))
    assert {"crear:prompt_listo", "crear:error:cf_error", f"sprint:ideas:{sid}", "nicho:avatares",
            f"nicho:error:{eid}"} <= claves
    assert any(c.startswith("organico:error:") for c in claves)
    ve = alertas.visibles("acme", AHORA, rol="cliente")["visibles"]
    assert {"crear:prompt_listo", f"sprint:ideas:{sid}", "nicho:avatares"} <= set(_claves(ve))
    por_grupo = {a["clave"]: a["grupo"] for a in todas}
    assert por_grupo["crear:prompt_listo"] == por_grupo["nicho:avatares"] == "decision"
    assert por_grupo["crear:error:cf_error"] == por_grupo[f"nicho:error:{eid}"] == "fallos"
    import re
    assert all(re.match(alertas.CLAVE_VALIDA, a["clave"]) and re.match(alertas.HUELLA_VALIDA, a["huella"]) for a in todas)


def test_los_textos_nuevos_salen_en_ingles_cuando_quien_mira_lee_en_ingles(base_temporal):
    """Todo título y detalle de las cuatro fuentes pasa por el catálogo, con su plural."""
    import alertas
    import idiomas
    from nicho import datos as nicho
    from sprints import datos
    _sesion("cf_a", "prompt_listo", HACE_2_H)
    _sesion("cf_b", "prompt_listo", HACE_2_H)
    _sesion("cf_e", "error", HACE_5_DIAS, error="falló", accion="Zapatillas")
    fb = _publicacion("error", HACE_5_DIAS, error="falló", plataforma="facebook", accion="Pantuflas")
    _publicacion("error", HACE_5_DIAS, error="", plataforma="tiktok", accion="")
    sid = _sprint("Octubre")
    cid = _campana(sid, estado="ideas_propuestas")
    _idea(cid)
    _idea(cid)
    _idea(cid, cf_estado="video_listo")
    _idea(cid, cf_estado="error", pieza_estado="error")
    datos.actualizar_referencia("acme", datos.agregar_referencia("acme", cid, "imagen", "https://x/1.png"), analisis_estado="error")
    e1, e2, e3 = _estudio("Uno"), _estudio("Dos"), _estudio("Tres")
    _proponer(e1, 3)
    nicho.iniciar_investigacion("acme", e1, {"estado": "interrumpida", "ultimo_error": "falló"})
    nicho.iniciar_investigacion("acme", e2, {"estado": "detenida", "detenida_por": "sin consultas"})
    nicho.actualizar_extra_estudio("acme", e3, lambda x: {**x, "ultimo_error": "falló"})
    fuentes = (alertas._fuente_crear, alertas._fuente_organico, alertas._fuente_sprints, alertas._fuente_nicho)
    es = {a["clave"]: a for f in fuentes for a in f("acme", AHORA)}
    with idiomas.en_idioma("en"):
        en = {a["clave"]: a for f in fuentes for a in f("acme", AHORA)}
    assert set(en) == set(es) and len(en) >= 10
    assert [(c, campo) for c, a in en.items() for campo in ("titulo", "detalle") if a[campo] == es[c][campo]] == []
    assert en["crear:prompt_listo"]["titulo"] == "2 ready prompts not yet generated in Create"
    assert en["crear:error:cf_e"]["titulo"] == "“Zapatillas” failed in Create"
    assert en[f"sprint:ideas:{sid}"]["titulo"] == "2 ideas to approve in the sprint “Octubre”"
    assert en[f"organico:error:{fb}"]["titulo"] == "Publishing “Pantuflas” to Facebook (Page) failed"
    assert en["nicho:avatares"]["titulo"] == "3 proposed avatars to approve"
    assert en[f"nicho:error:{e1}"]["titulo"] == "The research of “Uno” was interrupted"


def test_pnd119_error_desaparece_solo_con_republicacion_posterior(base_temporal):
    import alertas
    cf = 'cf_republicado'
    fallida = _publicacion('error', HACE_5_DIAS, 'falló', cf_id=cf)
    _publicacion('publicada', AHORA, cf_id=cf)
    otra = _publicacion('error', HACE_5_DIAS, 'falló', plataforma='youtube', cf_id=cf)
    claves = _claves(alertas._fuente_organico('acme', AHORA))
    assert f'organico:error:{fallida}' not in claves
    assert f'organico:error:{otra}' in claves


def test_pnd119_publicacion_anterior_no_oculta_error_nuevo(base_temporal):
    import alertas
    _publicacion('publicada', HACE_5_DIAS, cf_id='cf_antes')
    fallida = _publicacion('error', AHORA, 'falló', cf_id='cf_antes')
    assert f'organico:error:{fallida}' in _claves(alertas._fuente_organico('acme', AHORA))


def test_fuente_meta_recuerda_el_metodo_de_pago_solo_con_app_propia_conectada(monkeypatch):
    import alertas
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "estado", lambda c: {"estado": "conectado"})
    monkeypatch.setattr(meta_conexion, "modo", lambda c: "propia")
    [a] = alertas._fuente_meta("acme", "2026-10-04T10:00:00")
    assert a["clave"] == "meta:metodo_pago" and a["nivel"] == "info" and a["tab"] == "settings"
    monkeypatch.setattr(meta_conexion, "modo", lambda c: "agencia")
    assert alertas._fuente_meta("acme", "2026-10-04T10:00:00") == []
    monkeypatch.setattr(meta_conexion, "modo", lambda c: "propia")
    monkeypatch.setattr(meta_conexion, "estado", lambda c: {"estado": "sin_conectar"})
    assert alertas._fuente_meta("acme", "2026-10-04T10:00:00") == []

"""Tareas del worker del rendimiento de Meta (spec 2026-10-08 §6): una copia por cuenta, la periódica de 3 h
y la limpieza diaria."""
from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa

import cola
import db
import meta_conexion
from meta_rendimiento import cuentas, datos, graph, pausa, sync
from tareas import meta_rendimiento as t

TOKEN = "EAAtokenSECRETO123"
DOS = [{"id": "act_1", "name": "HappyFlops Norway", "currency": "SEK"},
       {"id": "act_2", "name": "HappyFlops Poland", "currency": "SEK"}]


@pytest.fixture()
def hf(base_temporal, monkeypatch):
    """El proyecto «hf» con dos cuentas y Meta conectado (token de prueba); reportar no escribe."""
    cuentas.elegir("hf", DOS)
    monkeypatch.setattr(meta_conexion, "cargar", lambda cliente: {"token": TOKEN})
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    return base_temporal


def _tarea(act="act_1", cliente="hf"):
    return {"id": 7, "payload": {"cliente": cliente, "ad_account_id": act}, "job_id": t.job_id_sync(cliente, act)}


def _filas_cola(tipo):
    with db.conectar() as con:
        return con.execute(sa.select(db.tarea).where(db.tarea.c.tipo == tipo).order_by(db.tarea.c.id)).all()


def _falla_con(monkeypatch, error):
    def _sincronizar(*a, **k):
        raise error
    monkeypatch.setattr(sync, "sincronizar", _sincronizar)


# ----------------------------------------------------------- encolar ---

def test_encolar_una_por_cuenta_con_dos_intentos_y_prioridad_baja(hf):
    assert t.encolar_sync("hf") == 2
    filas = _filas_cola(t.TIPO_SYNC)
    assert [f.job_id for f in filas] == ["hf__meta_rend__act_1", "hf__meta_rend__act_2"]
    assert {f.max_intentos for f in filas} == {2}
    assert {f.cliente for f in filas} == {"hf"}
    assert filas[0].payload == {"cliente": "hf", "ad_account_id": "act_1"}
    # Leer de Meta no cobra y no debe adelantarse a Crear ni a los experimentos: menos que el 5 normal.
    assert {f.prioridad for f in filas} == {t.PRIORIDAD_SYNC} and t.PRIORIDAD_SYNC < 5
    assert t.encolar_sync("hf") == 0          # ya hay una viva por cuenta: un segundo clic no lanza otra
    assert len(_filas_cola(t.TIPO_SYNC)) == 2


def test_encolar_una_cuenta_normaliza_el_id_y_ignora_las_ajenas(hf):
    assert t.encolar_sync("hf", "2") == 1
    assert [f.job_id for f in _filas_cola(t.TIPO_SYNC)] == ["hf__meta_rend__act_2"]
    assert t.encolar_sync("hf", "act_999") == 0     # no está en el proyecto
    assert t.encolar_sync("otro") == 0              # un proyecto sin cuentas
    assert len(_filas_cola(t.TIPO_SYNC)) == 1


def test_syncs_en_curso_lista_los_job_ids_vivos_del_proyecto(hf):
    assert t.syncs_en_curso("hf") == []
    t.encolar_sync("hf")
    assert t.syncs_en_curso("hf") == ["hf__meta_rend__act_1", "hf__meta_rend__act_2"]
    assert t.syncs_en_curso("otro") == []


def test_trabajos_del_panel_trae_las_copias_y_la_evaluacion_en_una_lectura(hf):
    assert t.trabajos_del_panel("hf") == set()
    t.encolar_sync("hf", "act_1")
    t.encolar_evaluacion("hf", 7)
    cola.encolar("tw_sincronizar", {}, job_id="hf__otra_cosa", cliente="hf")
    assert t.trabajos_del_panel("hf") == {"hf__meta_rend__act_1", "hf__meta_eval"}
    assert t.trabajos_del_panel("otro") == set()
    assert cola.job_ids_vivos("hf", t.TIPO_SYNC) == {"hf__meta_rend__act_1"}     # un tipo solo, como siempre


def test_la_copia_de_meta_va_despues_de_lo_normal_en_la_cola(hf):
    t.encolar_sync("hf")
    cola.encolar("tw_sincronizar", {}, job_id="x__normal")        # prioridad 5 por defecto, llegó DESPUÉS
    assert cola.reclamar()["job_id"] == "x__normal"
    assert cola.reclamar()["job_id"] == "hf__meta_rend__act_1"


def test_las_etapas_son_las_que_emite_la_copia():
    assert [e[0] for e in t.ETAPAS_SYNC] == [sync.ETAPA_CUENTA, sync.ETAPA_OBJETOS, sync.ETAPA_METRICAS,
                                            sync.ETAPA_ALCANCE]
    assert sum(e[1] for e in t.ETAPAS_SYNC) == 100


# ------------------------------------------------------- la tarea ---

def test_copia_ok_reporta_las_etapas_y_cuenta_lo_copiado(hf, monkeypatch):
    reportes = []
    monkeypatch.setattr(t.trabajos, "reportar", lambda job_id, **k: reportes.append((job_id, k)))
    llamadas = []

    def _sincronizar(cliente, act, token, hoy=None, on_etapa=None):
        llamadas.append((cliente, act, token))
        on_etapa(sync.ETAPA_CUENTA, 5)
        on_etapa(sync.ETAPA_METRICAS, 40)
        return {"omitida": False, "dias_cuenta": 12, "filas_anuncio": 345, "objetos": 9,
                "desde": "2026-07-10", "hasta": "2026-10-08"}
    monkeypatch.setattr(sync, "sincronizar", _sincronizar)
    texto = t.meta_rend_sincronizar(_tarea())
    assert llamadas == [("hf", "act_1", TOKEN)]
    assert reportes == [("hf__meta_rend__act_1", {"etapa": sync.ETAPA_CUENTA, "progreso": 5}),
                        ("hf__meta_rend__act_1", {"etapa": sync.ETAPA_METRICAS, "progreso": 40})]
    assert "Listo" in texto and "HappyFlops Norway" in texto and "345" in texto and "12" in texto
    assert "2026-07-10" in texto and "2026-10-08" in texto
    assert TOKEN not in texto


def _copia_ok(monkeypatch):
    monkeypatch.setattr(sync, "sincronizar", lambda *a, **k: {
        "omitida": False, "dias_cuenta": 1, "filas_anuncio": 1, "objetos": 1, "desde": "2026-10-08",
        "hasta": "2026-10-08"})


def _rec(tipo, nivel, huella):
    return {"id": huella, "nivel": nivel, "tipo": tipo, "cuenta": "act_1", "titulo": f"Título {tipo}"}


def test_copia_ok_guarda_las_recomendaciones_altas_de_esa_cuenta_para_alertas(hf, monkeypatch):
    from meta_rendimiento import panel
    _copia_ok(monkeypatch)
    pedidas = []

    def _recs(cliente, act, hoy=None):
        pedidas.append((cliente, act))
        return [_rec("cuenta_roas_bajo", "alta", "a" * 64), _rec("escalar", "media", "b" * 64),
                _rec("perdedores_gastando", "alta", "c" * 64), _rec("concentracion", "baja", "d" * 64)]
    monkeypatch.setattr(panel, "recomendaciones_de_cuenta", _recs)
    t.meta_rend_sincronizar(_tarea())
    assert pedidas == [("hf", "act_1")]
    extra = cuentas.cuenta("hf", "act_1")["extra"]
    # Solo tipo y huella: el título lo arma Alertas en el idioma de quien mira (skill alertas).
    assert extra["alertas"] == [{"tipo": "cuenta_roas_bajo", "huella": "a" * 64},
                                {"tipo": "perdedores_gastando", "huella": "c" * 64}]
    assert "alertas" not in cuentas.cuenta("hf", "act_2")["extra"]
    # La copia siguiente sin nada alto deja la lista vacía (la alerta desaparece sola).
    monkeypatch.setattr(panel, "recomendaciones_de_cuenta", lambda *a, **k: [_rec("escalar", "media", "b" * 64)])
    t.meta_rend_sincronizar(_tarea())
    assert cuentas.cuenta("hf", "act_1")["extra"]["alertas"] == []


def test_si_calcular_las_alertas_falla_la_copia_igual_termina_bien(hf, monkeypatch, caplog):
    from meta_rendimiento import panel
    _copia_ok(monkeypatch)
    cuentas.actualizar_extra("hf", "act_1", {"alertas": [{"tipo": "cuenta_roas_bajo", "huella": "a" * 64}]})

    def _revienta(*a, **k):
        raise ValueError(f"algo con el token {TOKEN}")
    monkeypatch.setattr(panel, "recomendaciones_de_cuenta", _revienta)
    texto = t.meta_rend_sincronizar(_tarea())
    assert "Listo" in texto
    # Lo guardado antes se queda (no se inventa que no hay alertas) y el registro dice solo el tipo del error.
    assert cuentas.cuenta("hf", "act_1")["extra"]["alertas"] == [{"tipo": "cuenta_roas_bajo", "huella": "a" * 64}]
    assert "ValueError" in caplog.text and TOKEN not in caplog.text


def test_una_copia_que_falla_no_toca_las_alertas_guardadas(hf, monkeypatch):
    from meta_rendimiento import panel
    _falla_con(monkeypatch, graph.ErrorGraph("Meta rechazó la consulta", codigo=100))
    monkeypatch.setattr(panel, "recomendaciones_de_cuenta", lambda *a, **k: pytest.fail("solo tras una copia buena"))
    with pytest.raises(RuntimeError):
        t.meta_rend_sincronizar(_tarea())


def test_la_copia_guarda_las_alertas_con_las_reglas_de_verdad(hf, monkeypatch):
    """Sin dobles en el cálculo: una cuenta que vende menos de la mitad de lo que gasta deja `cuenta_roas_bajo`."""
    from meta_rendimiento import recomendaciones
    _copia_ok(monkeypatch)
    hoy = date.today()
    dias = [(hoy - timedelta(days=i)).isoformat() for i in range(10)]
    datos.reemplazar_cuenta_dias("hf", "act_1", dias[-1], dias[0], [
        dict(fecha=f, gasto=500, impresiones=1000, alcance=500, clics=10, clics_salida=5, compras=1, valor=100,
             vistas_3s=0, thruplays=0) for f in dias])
    t.meta_rend_sincronizar(_tarea())
    alerta, = cuentas.cuenta("hf", "act_1")["extra"]["alertas"]
    assert alerta == {"tipo": "cuenta_roas_bajo",
                      "huella": recomendaciones.huella_recomendacion("cuenta_roas_bajo", "act_1", "alta")}


def test_sin_token_deja_la_cuenta_en_error_y_no_lanza(hf, monkeypatch):
    monkeypatch.setattr(meta_conexion, "cargar", lambda cliente: {"token": None})
    _falla_con(monkeypatch, AssertionError("sin token no se llama a Meta"))
    texto = t.meta_rend_sincronizar(_tarea())
    c = cuentas.cuenta("hf", "act_1")
    assert c["estado"] == "error" and "conecta" in c["error"].lower() and "Conexiones" in c["error"]
    assert c["error"] == texto
    # Sin conexión guardada del todo (cargar devuelve None) es lo mismo.
    monkeypatch.setattr(meta_conexion, "cargar", lambda cliente: None)
    t.meta_rend_sincronizar(_tarea("act_2"))
    assert cuentas.cuenta("hf", "act_2")["estado"] == "error"


def test_error_de_meta_marca_error_sin_token_y_sube_para_reintentar(hf, monkeypatch):
    _falla_con(monkeypatch, graph.ErrorGraph(f"Meta rechazó la consulta (access_token={TOKEN}). Vuelve a intentar",
                                             codigo=100))
    with pytest.raises(RuntimeError) as e:
        t.meta_rend_sincronizar(_tarea())
    c = cuentas.cuenta("hf", "act_1")
    assert c["estado"] == "error" and "Meta rechazó la consulta" in c["error"]
    assert TOKEN not in c["error"] and TOKEN not in str(e.value)
    assert str(e.value) == c["error"]
    assert e.value.__cause__ is None and e.value.__suppress_context__      # el error original no viaja en el traceback
    # Las demás cuentas del proyecto no se enteran.
    assert cuentas.cuenta("hf", "act_2")["estado"] == "nueva"
    assert not pausa.activa()          # un error que no es de límite no pone la pausa


def test_el_token_pelado_dentro_del_mensaje_tambien_se_tacha(hf, monkeypatch):
    # sin_token tacha «access_token=…»; un mensaje que repite el valor suelto lo tacha la propia tarea.
    _falla_con(monkeypatch, graph.ErrorGraph(f"Invalid OAuth access token {TOKEN} cannot be parsed", codigo=190))
    with pytest.raises(RuntimeError):
        t.meta_rend_sincronizar(_tarea())
    assert TOKEN not in cuentas.cuenta("hf", "act_1")["error"]


def test_limite_de_uso_marca_error_pone_la_pausa_y_no_sube(hf, monkeypatch):
    # Meta pidió esperar: la cuenta queda en error con el motivo, TODAS las copias esperan y la tarea termina sin
    # subir (un reintento inmediato volvería a chocar con el mismo límite).
    error = graph.ErrorGraph(f"Meta pidió esperar un rato (access_token={TOKEN})", codigo=17)
    assert error.limite
    _falla_con(monkeypatch, error)
    texto = t.meta_rend_sincronizar(_tarea())
    c = cuentas.cuenta("hf", "act_1")
    assert c["estado"] == "error" and c["error"] == texto and "Meta pidió esperar" in texto and TOKEN not in texto
    hasta = pausa.pausada_hasta()
    assert hasta is not None and pausa.activa()
    minutos = (datetime.fromisoformat(hasta) - datetime.now()).total_seconds() / 60
    assert 29 <= minutos <= 31                       # sin espera de Meta: 30 minutos
    assert cuentas.cuenta("hf", "act_2")["estado"] == "nueva"


def test_el_limite_con_espera_de_meta_mayor_alarga_la_pausa(hf, monkeypatch):
    # El freno del 75 % (limite=True, sin código) y los 90 minutos que Meta dice que faltan.
    _falla_con(monkeypatch, graph.ErrorGraph("Meta está cerca de su límite de uso; la copia sigue más tarde.",
                                             limite=True, espera_min=90))
    t.meta_rend_sincronizar(_tarea())
    assert cuentas.cuenta("hf", "act_1")["estado"] == "error"
    minutos = (datetime.fromisoformat(pausa.pausada_hasta()) - datetime.now()).total_seconds() / 60
    assert 89 <= minutos <= 91


def test_con_la_pausa_vigente_la_copia_no_llama_a_meta_ni_cambia_la_cuenta(hf, monkeypatch):
    pausa.pausar(30)
    _falla_con(monkeypatch, AssertionError("con la pausa vigente no se llama a Meta"))
    texto = t.meta_rend_sincronizar(_tarea())
    assert "Meta pidió esperar" in texto
    c = cuentas.cuenta("hf", "act_1")
    assert c["estado"] == "nueva" and not c.get("error")      # ni error ni «copiando»: cede el turno sin ruido


def test_vencida_la_pausa_la_copia_vuelve_a_correr(hf, monkeypatch):
    pausa.pausar(30, ahora=datetime.now() - timedelta(hours=2))
    assert not pausa.activa()
    monkeypatch.setattr(sync, "sincronizar", lambda *a, **k: {"dias_cuenta": 1, "filas_anuncio": 2, "objetos": 3,
                                                              "desde": "2026-10-01", "hasta": "2026-10-08"})
    t.meta_rend_sincronizar(_tarea())     # no lanza: llegó a sincronizar


def _tarea_viva(tipo, estado="pendiente"):
    cola.encolar(tipo, {"cliente": "hf"}, cliente="hf", job_id=f"hf__{tipo}__1", duracion_estimada=30,
                 max_intentos=1)
    if estado != "pendiente":
        with db.conectar() as con:
            con.execute(db.tarea.update().where(db.tarea.c.tipo == tipo).values(estado=estado))


def _se_pospone(monkeypatch, payload_extra=None):
    """Corre la copia con Meta intocable y devuelve lo que devolvió (una `Continuar` si cedió el turno)."""
    _falla_con(monkeypatch, AssertionError("con una acción en Meta en curso no se copia"))
    tarea = _tarea()
    tarea["payload"].update(payload_extra or {})
    return t.meta_rend_sincronizar(tarea)


@pytest.mark.parametrize("tipo", ["exp_lanzar", "meta_publicar", "organico_publicar"])
@pytest.mark.parametrize("estado", ["pendiente", "en_curso"])
def test_una_escritura_disparada_por_una_persona_pospone_la_copia_en_cola_o_corriendo(hf, monkeypatch, tipo, estado):
    _tarea_viva(tipo, estado)
    r = _se_pospone(monkeypatch)
    assert isinstance(r, t.Continuar) and r.tipo == t.TIPO_SYNC
    c = cuentas.cuenta("hf", "act_1")
    assert c["estado"] == "nueva" and not c.get("error") and not pausa.activa()


@pytest.mark.parametrize("tipo", ["exp_decidir", "exp_avanzar_todos"])
def test_una_periodica_que_escribe_pospone_la_copia_solo_mientras_corre(hf, monkeypatch, tipo):
    # Mutación C9: sacar `exp_avanzar_todos` de la guarda tiene que romper esta prueba.
    _tarea_viva(tipo, "en_curso")
    assert isinstance(_se_pospone(monkeypatch), t.Continuar)


@pytest.mark.parametrize("tipo", ["exp_decidir", "exp_avanzar_todos"])
def test_una_periodica_pendiente_no_pospone_la_copia(hf, monkeypatch, tipo):
    # `exp_avanzar_todos` espera en la cola general detrás de tareas largas: todavía no escribe nada en Meta.
    _tarea_viva(tipo, "pendiente")
    monkeypatch.setattr(sync, "sincronizar", lambda *a, **k: {"dias_cuenta": 1, "filas_anuncio": 2, "objetos": 3,
                                                              "desde": "2026-10-01", "hasta": "2026-10-08"})
    texto = t.meta_rend_sincronizar(_tarea())
    assert isinstance(texto, str) and "Listo" in texto


def test_la_copia_pospuesta_se_vuelve_a_encolar_sola_en_10_minutos_con_su_contador(hf, monkeypatch):
    _tarea_viva("exp_lanzar", "en_curso")
    antes = datetime.now()
    r = _se_pospone(monkeypatch)
    assert r.payload == {"cliente": "hf", "ad_account_id": "act_1", "pospuestas": 1}
    assert antes + timedelta(minutes=9, seconds=50) <= r.ejecutar_desde <= datetime.now() + timedelta(minutes=10)
    assert r.max_intentos == t.MAX_INTENTOS_SYNC
    assert "10 minutos" in r.mensaje and "1 de 6" in r.mensaje
    r2 = _se_pospone(monkeypatch, {"pospuestas": 3})
    assert r2.payload["pospuestas"] == 4 and "4 de 6" in r2.mensaje


def test_tras_seis_posposiciones_se_rinde_y_deja_el_texto_de_la_proxima_copia(hf, monkeypatch):
    _tarea_viva("exp_lanzar")
    texto = _se_pospone(monkeypatch, {"pospuestas": t.MAX_POSPOSICIONES})
    assert isinstance(texto, str) and "pospuesta" in texto.lower() and "acción en Meta en curso" in texto
    assert "próxima copia programada" in texto


def test_el_worker_sigue_la_copia_pospuesta_con_el_mismo_job_y_sus_dos_intentos(hf, monkeypatch):
    import worker
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    _tarea_viva("exp_lanzar", "en_curso")
    t.encolar_sync("hf", "act_1")
    fila = cola.reclamar()
    assert fila["tipo"] == t.TIPO_SYNC
    _falla_con(monkeypatch, AssertionError("con una acción en Meta en curso no se copia"))
    worker._correr(fila)
    nueva = cola.consultar_por_job(t.job_id_sync("hf", "act_1"))
    assert nueva["id"] != fila["id"] and nueva["estado"] == "pendiente" and nueva["max_intentos"] == 2
    assert nueva["payload"]["pospuestas"] == 1 and cola.consultar_por_id(fila["id"])["estado"] == "hecha"
    assert cola.reclamar() is None          # todavía no le toca: es para dentro de 10 minutos


def test_las_escrituras_en_meta_son_los_tipos_que_de_verdad_escriben():
    # Nombres que existen de verdad en el registro del worker (un typo aquí dejaría la guarda sin efecto).
    import tareas
    tareas.cargar_todas()
    assert set(t.TIPOS_ESCRITURA_META) <= set(tareas.REGISTRO)
    assert {"exp_lanzar", "exp_decidir", "meta_publicar", "organico_publicar"} <= set(t.TIPOS_ESCRITURA_META)
    assert set(t.TIPOS_ESCRITURA_USUARIO) == {"exp_lanzar", "meta_publicar", "organico_publicar"}
    assert set(t.TIPOS_ESCRITURA_PERIODICAS) == {"exp_decidir", "exp_avanzar_todos"}


def test_una_tarea_que_solo_lee_de_meta_o_ya_terminada_no_pospone_la_copia(hf, monkeypatch):
    _tarea_viva("exp_refrescar")                      # lee métricas: no escribe
    _tarea_viva("exp_lanzar", "hecha")                # terminada
    monkeypatch.setattr(sync, "sincronizar", lambda *a, **k: {"dias_cuenta": 0, "filas_anuncio": 0, "objetos": 0,
                                                              "desde": "2026-10-01", "hasta": "2026-10-08"})
    texto = t.meta_rend_sincronizar(_tarea())
    assert "pospuesta" not in texto.lower()


def test_cualquier_otra_excepcion_marca_error_con_su_tipo_y_sin_url(hf, monkeypatch):
    class ConnectionError_(Exception):
        pass
    url = f"https://graph.facebook.com/v21.0/act_1?access_token={TOKEN}&fields=name"
    _falla_con(monkeypatch, ConnectionError_(f"HTTPSConnectionPool: Max retries exceeded with url: {url}"))
    with pytest.raises(RuntimeError) as e:
        t.meta_rend_sincronizar(_tarea())
    c = cuentas.cuenta("hf", "act_1")
    assert c["estado"] == "error" and "ConnectionError_" in c["error"]
    assert TOKEN not in c["error"] and "graph.facebook.com" not in c["error"] and "https://" not in c["error"]
    assert TOKEN not in str(e.value)


def test_un_error_largo_se_recorta(hf, monkeypatch):
    _falla_con(monkeypatch, graph.ErrorGraph("x" * 3000, codigo=1))
    with pytest.raises(RuntimeError):
        t.meta_rend_sincronizar(_tarea())
    assert len(cuentas.cuenta("hf", "act_1")["error"]) == 500


def test_cuenta_que_ya_no_esta_en_el_proyecto_no_llama_a_meta(hf, monkeypatch):
    _falla_con(monkeypatch, AssertionError("no se llama a Meta"))
    texto = t.meta_rend_sincronizar(_tarea("act_999"))
    assert "ya no está en el proyecto" in texto
    assert cuentas.cuenta("hf", "act_999") is None


def test_omitida_por_la_copia_no_es_un_error(hf, monkeypatch):
    # La quitaron entre la comprobación de la tarea y la de la copia.
    monkeypatch.setattr(sync, "sincronizar", lambda *a, **k: {"omitida": True, "dias_cuenta": 0, "filas_anuncio": 0,
                                                              "objetos": 0, "desde": None, "hasta": None})
    texto = t.meta_rend_sincronizar(_tarea())
    assert "ya no está en el proyecto" in texto
    assert cuentas.cuenta("hf", "act_1")["estado"] == "nueva"


def test_interrumpida_deja_en_error_solo_a_la_que_estaba_copiando(hf):
    cuentas.actualizar("hf", "act_1", estado="copiando")
    cuentas.actualizar("hf", "act_2", estado="ok")
    t._sync_interrumpida(_tarea("act_1"), "Se interrumpió por un reinicio del servidor.")
    t._sync_interrumpida(_tarea("act_2"), "Se interrumpió por un reinicio del servidor.")
    t._sync_interrumpida({"payload": {}}, "x")      # sin payload: no hace nada
    assert cuentas.cuenta("hf", "act_1")["estado"] == "error"
    assert cuentas.cuenta("hf", "act_1")["error"] == "Se interrumpió por un reinicio del servidor."
    assert cuentas.cuenta("hf", "act_2")["estado"] == "ok"


def test_interrumpida_no_toca_la_cuenta_de_otro_proyecto(hf):
    cuentas.elegir("otro", [{"id": "act_77", "name": "Otro", "currency": "USD"}])
    for cliente, act in (("hf", "act_1"), ("hf", "act_2"), ("otro", "act_77")):
        cuentas.actualizar(cliente, act, estado="copiando")
    t._sync_interrumpida(_tarea("act_1"), "reinicio")
    assert [cuentas.cuenta(c, a)["estado"] for c, a in (("hf", "act_1"), ("hf", "act_2"), ("otro", "act_77"))] == \
        ["error", "copiando", "copiando"]
    # Un payload con el proyecto equivocado para esa cuenta no la toca (la cuenta es de «hf», no de «otro»).
    cuentas.actualizar("hf", "act_1", estado="copiando")
    t._sync_interrumpida(_tarea("act_1", cliente="otro"), "reinicio")
    assert cuentas.cuenta("hf", "act_1")["estado"] == "copiando"


# ------------------------------------------------------- periódicas ---

def test_todas_encola_una_por_cuenta_de_cada_proyecto(hf):
    cuentas.elegir("otro", [{"id": "act_77", "name": "Otro", "currency": "USD"}])
    assert "3" in t.meta_rend_sincronizar_todas({"payload": {}})
    assert [f.job_id for f in _filas_cola(t.TIPO_SYNC)] == ["hf__meta_rend__act_1", "hf__meta_rend__act_2",
                                                            "otro__meta_rend__act_77"]
    assert "0" in t.meta_rend_sincronizar_todas({"payload": {}})     # ya había una viva por cuenta


def test_todas_no_encola_nada_mientras_dura_la_pausa(hf):
    pausa.pausar(30)
    texto = t.meta_rend_sincronizar_todas({"payload": {}})
    assert "Meta pidió esperar" in texto and _filas_cola(t.TIPO_SYNC) == []
    assert t.encolar_sync("hf") == 2     # a mano (Actualizar ahora) sí se encola; la tarea misma cede el turno


def test_limpiar_borra_lo_de_mas_de_95_dias(hf, monkeypatch):
    recibido = []
    monkeypatch.setattr(datos, "purgar_anuncios", lambda antes_de: recibido.append(antes_de) or 4)
    texto = t.meta_rend_limpiar({"payload": {}})
    assert recibido == [(date.today() - timedelta(days=95)).isoformat()] and t.DIAS_ANUNCIO_GUARDADOS == 95
    assert "4" in texto


def test_limpiar_de_verdad_conserva_la_frontera(hf):
    hoy = date.today()
    fila = dict(gasto=1.0, impresiones=10, clics=1)
    for dias in (96, 95, 3):
        f = (hoy - timedelta(days=dias)).isoformat()
        datos.reemplazar_anuncio_dias("hf", "act_1", f, f, [dict(fila, ad_id="a1", fecha=f)])
    assert "1" in t.meta_rend_limpiar({"payload": {}})
    with db.conectar() as con:
        quedan = sorted(r[0] for r in con.execute(sa.select(db.meta_anuncio_dia.c.fecha)))
    assert quedan == sorted([(hoy - timedelta(days=95)).isoformat(), (hoy - timedelta(days=3)).isoformat()])


def test_limpiar_tambien_borra_los_dias_de_cuenta_de_mas_de_400_dias(hf):
    hoy = date.today()
    dia = dict(gasto=1.0, impresiones=10, alcance=5, clics=1, clics_salida=1, compras=0.0, valor=0.0, vistas_3s=0,
               thruplays=0)
    fechas = [(hoy - timedelta(days=d)).isoformat() for d in (401, 400, 30)]
    datos.reemplazar_cuenta_dias("hf", "act_1", fechas[0], fechas[2], [dict(dia, fecha=f) for f in fechas])
    assert t.DIAS_CUENTA_GUARDADOS == 400
    texto = t.meta_rend_limpiar({"payload": {}})
    assert "1 día(s) viejos de cuentas" in texto
    with db.conectar() as con:
        quedan = sorted(r[0] for r in con.execute(sa.select(db.meta_cuenta_dia.c.fecha)))
    assert quedan == sorted(fechas[1:])


def test_registradas_y_periodicas_en_el_worker():
    import tareas
    import worker
    tareas.cargar_todas()
    assert {"meta_rend_sincronizar", "meta_rend_sincronizar_todas", "meta_rend_limpiar"} <= set(tareas.REGISTRO)
    assert tareas.AL_INTERRUMPIR["meta_rend_sincronizar"] is t._sync_interrumpida
    assert "meta_rend_sincronizar" in worker.CARRIL_LECTURA and "meta_rend_sincronizar_todas" not in worker.CARRIL_LECTURA
    periodicas = dict(worker.PERIODICAS)
    assert periodicas["meta_rend_sincronizar_todas"] == 10800 and periodicas["meta_rend_limpiar"] == 86400
    tipos = [tipo for tipo, _ in worker.PERIODICAS]
    assert tipos.index("tw_sincronizar_todas") < tipos.index("meta_rend_sincronizar_todas") < tipos.index("exp_refrescar_todos")


# ---------------------------------------------------------- «Evaluar con IA» (spec E2 §8) ---

import json  # noqa: E402

import gastos  # noqa: E402
from meta_rendimiento import analisis  # noqa: E402
from nicho.avatares import costo_real  # noqa: E402
from triple_whale import analisis as tw_analisis  # noqa: E402

def _respuesta(n_ideas=3):
    return json.dumps({
        "resumen": "Norway vende con un solo video; los perdedores se comen el presupuesto.",
        "diagnostico": [{"causa": "Perdedores activos", "evidencia": "A2 gastó sin ventas"}],
        "plan": [{"prioridad": 1, "accion": "pausar", "objetos": ["A2", "R1"], "que_hacer": "Pausa el perdedor",
                  "por_que": "gasta sin vender", "impacto": None}],
        "patrones_ganadores": [{"patron": "Demostración del producto", "anuncios": ["A1"]}],
        "patrones_perdedores": [], "anuncios": [{"id": "A1", "por_que": "Muestra el producto"}],
        "ideas": [{"titulo": f"Sandalia en la lluvia {i}", "basada_en": ["A1"], "por_que": "repite la demostración",
                   "angulo": {}, "escena": "Pies en un charco", "prompt": "Close-up of feet in a puddle..."}
                  for i in range(1, n_ideas + 1)]})


RESPUESTA_OK = _respuesta()


def _jpeg():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def evaluacion(hf, monkeypatch):
    """Una evaluación «en_cola» de hf con dos anuncios de la cuenta 1 (uno con miniatura de Meta) y una
    recomendación; R2 y la descarga de la miniatura son falsas."""
    datos.guardar_objetos("hf", "act_1", [{"nivel": "anuncio", "objeto_id": "1001", "nombre": "Video gana",
                                           "estado": "ACTIVE", "miniatura_url": "https://scontent.xx.fbcdn.net/g.jpg"}])
    m = {k: 1.0 for k in tw_analisis.CAMPOS_M}
    muestra = [dict(ref="A1", canal="meta", ad_id="1001", nombre="Video gana", veredicto="ganador", motivo="ROAS",
                    problemas=[], fortalezas=[], m=m, ad_account_id="act_1", moneda="SEK", cuenta_nombre="N"),
               dict(ref="A2", canal="meta", ad_id="2001", nombre="Pierde", veredicto="perdedor", motivo="sin ventas",
                    problemas=[], fortalezas=[], m=m, ad_account_id="act_1", moneda="SEK", cuenta_nombre="N")]
    recs = [{"ref": "R1", "id": "f" * 64, "nivel": "alta", "tipo": "perdedores_gastando", "cuenta": "act_1",
             "cuenta_nombre": "N", "titulo": "Un perdedor gasta", "que_hacer": "Páusalo", "por_que": "gasta",
             "impacto": None, "objetos": [], "enlace": None}]
    eid = datos.crear_evaluacion("hf", ["act_1"], "2026-09-09", "2026-10-08", "SEK", muestra, recs, pedido_por="u",
                                 extra={"dias": 30, "cuenta": None, "resumen": [], "segmentos": {}})
    subidas, borradas = [], []
    monkeypatch.setattr(tw_analisis.r2_uploader, "upload_image",
                        lambda local, clave: subidas.append(clave) or f"https://r2/{clave}")
    monkeypatch.setattr(tw_analisis.r2_uploader, "delete_files",
                        lambda claves: (borradas.extend(claves), (len(claves), []))[1])
    from referentes import imagenes
    monkeypatch.setattr(imagenes, "_bajar", lambda url: _jpeg())
    return {"eid": eid, "subidas": subidas, "borradas": borradas}


def _tarea_eval(eid, cliente="hf"):
    return {"id": 7, "payload": {"cliente": cliente, "evaluacion_id": eid}, "job_id": t.job_id_evaluar(cliente)}


def _gastos_eval():
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(
            sa.select(db.gasto.c.tipo, db.gasto.c.usd, db.gasto.c.referencia, db.gasto.c.proveedor))]


def test_evaluar_encola_una_por_proyecto_con_un_intento_en_el_carril_general(hf):
    import tareas
    import worker
    assert t.encolar_evaluacion("hf", 5, costo_estimado=0.2) is True
    fila, = _filas_cola(t.TIPO_EVALUAR)
    assert fila.job_id == "hf__meta_eval" and fila.max_intentos == 1 and fila.cliente == "hf"
    assert fila.duracion_estimada == t.DURACION_EVALUAR == 360      # E2-R8: lo medido, para que la barra no mienta
    assert fila.payload == {"cliente": "hf", "evaluacion_id": 5}
    assert t.evaluacion_en_curso("hf") and not t.evaluacion_en_curso("otro")
    assert t.encolar_evaluacion("hf", 6) is False and len(_filas_cola(t.TIPO_EVALUAR)) == 1
    tareas.cargar_todas()
    assert tareas.REGISTRO[t.TIPO_EVALUAR] is t.meta_rend_evaluar
    assert tareas.AL_INTERRUMPIR[t.TIPO_EVALUAR] is t._evaluar_interrumpida
    assert t.TIPO_EVALUAR in tareas.TIPOS_QUE_COBRAN and t.TIPO_EVALUAR not in worker.CARRIL_LECTURA


def test_evaluar_guarda_el_resultado_las_miniaturas_en_r2_y_el_gasto_real(evaluacion, monkeypatch):
    eid = evaluacion["eid"]
    visto = {}

    def _llamar(content, system_):
        visto["content"] = content
        return RESPUESTA_OK, 10000, 5000
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    texto = t.meta_rend_evaluar(_tarea_eval(eid))
    assert "1 paso(s)" in texto and "3 idea(s)" in texto
    fila = datos.evaluacion("hf", eid)
    usd = costo_real(10000, 5000)
    assert fila["estado"] == "lista" and fila["error"] is None and fila["usd"] == pytest.approx(usd)
    assert fila["tarea_id"] == 7 and fila["resultado"]["plan"][0]["enlace"].endswith("selected_ad_ids=2001")
    # La miniatura de Meta quedó copiada a R2 en la carpeta de Meta (la de Meta caduca) y Claude la vio.
    clave = f"clientes/hf/meta_rendimiento/eval{eid}_A1.jpg"
    assert evaluacion["subidas"] == [clave]
    a1, a2 = fila["muestra"]
    assert a1["medio"]["imagen"] == f"https://r2/{clave}" and a1["visual"] == "imagen"
    assert a2["medio"]["imagen"] is None and "visual" not in a2
    assert [b["type"] for b in visto["content"]] == ["text", "text", "image"]
    assert "<anuncios>" in visto["content"][0]["text"]
    assert evaluacion["borradas"] == []                  # con la fila en su lugar, las miniaturas se quedan
    assert _gastos_eval() == [{"tipo": "evaluacion", "usd": pytest.approx(usd), "referencia": f"meta_eval:{eid}:t7",
                               "proveedor": "anthropic"}]


def test_evaluar_con_respuesta_invalida_dos_veces_queda_en_error_y_anota_lo_pagado(evaluacion, monkeypatch):
    eid = evaluacion["eid"]
    monkeypatch.setattr(analisis, "_llamar", lambda c, s: ("no es JSON", 3000, 800))
    with pytest.raises(RuntimeError) as e:
        t.meta_rend_evaluar(_tarea_eval(eid))
    fila = datos.evaluacion("hf", eid)
    usd = costo_real(6000, 1600)
    assert fila["estado"] == "error" and fila["error"] == str(e.value) and "Claude" in fila["error"]
    assert fila["usd"] == pytest.approx(usd)
    assert _gastos_eval() == [{"tipo": "evaluacion", "usd": pytest.approx(usd), "referencia": f"meta_eval:{eid}:t7",
                               "proveedor": "anthropic"}]


def test_evaluar_si_falla_tras_pagar_anota_el_gasto_y_el_error_va_sin_token(evaluacion, monkeypatch):
    eid = evaluacion["eid"]

    class Fallo(RuntimeError):
        tokens_entrada, tokens_salida = 4000, 900

    def _analizar(*a, **k):
        raise Fallo(f"Meta devolvió https://graph.facebook.com/x?access_token={TOKEN}")
    monkeypatch.setattr(analisis, "analizar", _analizar)
    with pytest.raises(RuntimeError) as e:
        t.meta_rend_evaluar(_tarea_eval(eid))
    fila = datos.evaluacion("hf", eid)
    assert fila["estado"] == "error" and TOKEN not in fila["error"] and TOKEN not in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__
    assert _gastos_eval()[0]["usd"] == pytest.approx(costo_real(4000, 900))


def _cobra_hf():
    from cobros import libro
    libro.configurar("hf", usuario="admin", cobrar=True)
    with db.conectar() as con:
        libro.acreditar(con, "hf", "ajuste", 50_000, "ajuste", usuario="admin", detalle="prueba")


def _movimientos_hf():
    with db.conectar() as con:
        return [r.tipo for r in con.execute(sa.select(db.movimiento_saldo.c.tipo).where(
            db.movimiento_saldo.c.cliente == "hf", db.movimiento_saldo.c.tipo != "ajuste"))]


def test_evaluar_en_un_proyecto_que_cobra_cobra_lo_entregado(evaluacion, monkeypatch):
    _cobra_hf()
    monkeypatch.setattr(analisis, "_llamar", lambda c, s: (RESPUESTA_OK, 10000, 5000))
    t.meta_rend_evaluar(_tarea_eval(evaluacion["eid"]))
    assert _movimientos_hf() == ["cobro"]


def test_evaluar_invalida_en_un_proyecto_que_cobra_no_se_le_cobra(evaluacion, monkeypatch):
    _cobra_hf()
    monkeypatch.setattr(analisis, "_llamar", lambda c, s: ("no es JSON", 3000, 800))
    with pytest.raises(RuntimeError):
        t.meta_rend_evaluar(_tarea_eval(evaluacion["eid"]))
    assert _movimientos_hf() == ["no_cobrado"] and _gastos_eval()[0]["usd"] == pytest.approx(costo_real(6000, 1600))


def test_evaluar_si_la_fila_se_borra_a_mitad_igual_anota_lo_que_claude_cobro(evaluacion, monkeypatch):
    """Desconectar Meta borra las evaluaciones del proyecto: si pasa mientras Claude responde, lo pagado se anota (sin
    entregar: nadie va a ver ese resultado, al cliente no se le cobra)."""
    eid = evaluacion["eid"]
    _cobra_hf()

    def _llamar(content, system_):
        datos.borrar_evaluaciones("hf")
        return RESPUESTA_OK, 10000, 5000
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    assert t.meta_rend_evaluar(_tarea_eval(eid)) == "Esa evaluación ya no existe."
    assert datos.evaluacion("hf", eid) is None
    assert _gastos_eval()[0]["usd"] == pytest.approx(costo_real(10000, 5000))
    assert _movimientos_hf() == ["no_cobrado"]


def test_evaluar_si_la_fila_se_borra_a_mitad_borra_tambien_las_miniaturas_que_copio(evaluacion, monkeypatch):
    """Revisión de privacidad de E2: desconectar Meta ya borró las filas, y las miniaturas que la tarea subió a R2
    después no las encontraría nadie."""
    eid = evaluacion["eid"]

    def _llamar(content, system_):
        datos.borrar_evaluaciones("hf")
        return RESPUESTA_OK, 10000, 5000
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    t.meta_rend_evaluar(_tarea_eval(eid))
    base = "clientes/hf/meta_rendimiento"
    assert evaluacion["subidas"] == [f"{base}/eval{eid}_A1.jpg"]
    assert sorted(evaluacion["borradas"]) == [f"{base}/eval{eid}_A1.jpg", f"{base}/eval{eid}_A2.jpg"]
    assert _gastos_eval()[0]["usd"] == pytest.approx(costo_real(10000, 5000))        # y lo pagado se anota igual


def test_evaluar_si_la_fila_se_borra_y_ademas_claude_falla_borra_las_miniaturas_y_anota_lo_pagado(evaluacion,
                                                                                                   monkeypatch):
    eid = evaluacion["eid"]

    def _llamar(content, system_):
        datos.borrar_evaluaciones("hf")
        return "no es JSON", 3000, 800
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    with pytest.raises(RuntimeError):
        t.meta_rend_evaluar(_tarea_eval(eid))
    base = "clientes/hf/meta_rendimiento"
    assert sorted(evaluacion["borradas"]) == [f"{base}/eval{eid}_A1.jpg", f"{base}/eval{eid}_A2.jpg"]
    assert _gastos_eval()[0]["usd"] == pytest.approx(costo_real(6000, 1600))


def test_evaluar_si_r2_falla_al_soltar_las_miniaturas_la_tarea_termina_igual_y_anota_el_gasto(evaluacion, monkeypatch):
    eid = evaluacion["eid"]

    def _llamar(content, system_):
        datos.borrar_evaluaciones("hf")
        return RESPUESTA_OK, 10000, 5000

    def _falla(claves):
        raise RuntimeError(f"Faltan R2_ACCOUNT_ID {TOKEN}")
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    monkeypatch.setattr(tw_analisis.r2_uploader, "delete_files", _falla)
    assert t.meta_rend_evaluar(_tarea_eval(eid)) == "Esa evaluación ya no existe."
    assert _gastos_eval()[0]["usd"] == pytest.approx(costo_real(10000, 5000))


def test_evaluar_si_guardar_el_resultado_falla_anota_lo_pagado_sin_cobrarlo(evaluacion, monkeypatch):
    eid = evaluacion["eid"]
    _cobra_hf()
    monkeypatch.setattr(analisis, "_llamar", lambda c, s: (RESPUESTA_OK, 10000, 5000))
    original = datos.actualizar_evaluacion

    def _falla_al_guardar(evaluacion_id, **campos):
        if campos.get("estado") == "lista":
            raise RuntimeError("database is locked")
        return original(evaluacion_id, **campos)
    monkeypatch.setattr(datos, "actualizar_evaluacion", _falla_al_guardar)
    with pytest.raises(RuntimeError):
        t.meta_rend_evaluar(_tarea_eval(eid))
    assert datos.evaluacion("hf", eid)["estado"] == "error"
    assert len(_gastos_eval()) == 1 and _movimientos_hf() == ["no_cobrado"]


def test_evaluar_una_que_no_existe_o_es_de_otro_proyecto_no_llama_a_claude(evaluacion, monkeypatch):
    monkeypatch.setattr(analisis, "_llamar", lambda c, s: pytest.fail("no debía llamar a Claude"))
    assert t.meta_rend_evaluar(_tarea_eval(evaluacion["eid"], cliente="otro")) == "Esa evaluación ya no existe."
    assert t.meta_rend_evaluar(_tarea_eval(999)) == "Esa evaluación ya no existe."
    assert datos.evaluacion("hf", evaluacion["eid"])["estado"] == "en_cola" and _gastos_eval() == []


def test_evaluacion_interrumpida_queda_en_error_sin_token(evaluacion):
    eid = evaluacion["eid"]
    t._evaluar_interrumpida(_tarea_eval(eid, cliente="otro"), "x")         # otro proyecto: no la toca
    assert datos.evaluacion("hf", eid)["estado"] == "en_cola"
    t._evaluar_interrumpida(_tarea_eval(eid), f"Interrumpida: access_token={TOKEN}")
    fila = datos.evaluacion("hf", eid)
    assert fila["estado"] == "error" and TOKEN not in fila["error"] and fila["error"].startswith("Interrumpida")
    datos.actualizar_evaluacion(eid, estado="lista")
    t._evaluar_interrumpida(_tarea_eval(eid), "otra vez")                 # una lista no vuelve a error
    assert datos.evaluacion("hf", eid)["estado"] == "lista"


def _timeout():
    import anthropic
    import httpx
    return anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def _detalles():
    with db.conectar() as con:
        return [r.detalle for r in con.execute(sa.select(db.gasto.c.detalle))]


def test_evaluar_si_claude_no_responde_anota_el_estimado_sin_cobrarlo(evaluacion, monkeypatch):
    """E2-R7: un tope de tiempo o una conexión cortada no traen `usage`, pero Anthropic pudo cobrar: se anota el
    estimado de la tarifa, sin entregar (al cliente no se le cobra)."""
    eid = evaluacion["eid"]
    _cobra_hf()

    def _llamar(content, system_):
        raise _timeout()
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    with pytest.raises(RuntimeError) as e:
        t.meta_rend_evaluar(_tarea_eval(eid))
    estimado = gastos.estimar("evaluacion_meta", n=2)["usd"]
    assert _gastos_eval()[0]["usd"] == pytest.approx(estimado)
    assert _detalles() == ["estimado: sin respuesta de Claude"] and _movimientos_hf() == ["no_cobrado"]
    fila = datos.evaluacion("hf", eid)
    assert fila["estado"] == "error" and "APITimeoutError" in fila["error"] and "anthropic.com" not in str(e.value)


def test_evaluar_si_la_correccion_no_responde_anota_lo_exacto_mas_el_estimado(evaluacion, monkeypatch):
    eid = evaluacion["eid"]
    llamadas = []

    def _llamar(content, system_):
        llamadas.append(1)
        if len(llamadas) > 1:
            raise _timeout()
        return "no es JSON", 3000, 800
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    with pytest.raises(RuntimeError):
        t.meta_rend_evaluar(_tarea_eval(eid))
    esperado = costo_real(3000, 800) + gastos.estimar("evaluacion_meta", n=2)["usd"]
    assert _gastos_eval()[0]["usd"] == pytest.approx(esperado) and _detalles() == ["estimado: sin respuesta de Claude"]


def test_un_fallo_antes_de_llamar_a_claude_no_anota_ningun_estimado(evaluacion, monkeypatch):
    eid = evaluacion["eid"]

    def _sin_red(*a, **k):
        raise _timeout()            # p. ej. armar los DATOS falla con algo que parece de red: Claude no se llamó
    monkeypatch.setattr(analisis, "armar", _sin_red)
    with pytest.raises(RuntimeError):
        t.meta_rend_evaluar(_tarea_eval(eid))
    assert _gastos_eval() == [] and datos.evaluacion("hf", eid)["estado"] == "error"


# ------------------------------------------------- E2-R8: sin ideas no hay evaluación (2026-10-10) ---

def test_evaluar_sin_ideas_pide_la_correccion_con_el_json_completo(evaluacion, monkeypatch):
    """La eval del 2026-10-10: 2 de 3 correcciones llegaron sin ideas y se aceptaban. Ahora menos de 3 ideas no sirve:
    se paga UNA corrección, que pide el JSON completo, y se cobran las dos llamadas."""
    eid = evaluacion["eid"]
    respuestas = [(_respuesta(n_ideas=0), 3000, 800), (RESPUESTA_OK, 3100, 900)]
    pedidos = []

    def _llamar(content, system_):
        pedidos.append(content)
        return respuestas.pop(0)
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    assert "3 idea(s)" in t.meta_rend_evaluar(_tarea_eval(eid))
    assert len(pedidos) == 2 and "JSON COMPLETO" in pedidos[1][-1]["text"] and "ideas" in pedidos[1][-1]["text"]
    fila = datos.evaluacion("hf", eid)
    usd = costo_real(6100, 1700)
    assert fila["estado"] == "lista" and len(fila["resultado"]["ideas"]) == 3 and fila["usd"] == pytest.approx(usd)
    assert _gastos_eval()[0]["usd"] == pytest.approx(usd)


def test_evaluar_sin_ideas_tambien_tras_la_correccion_queda_en_error_y_anota_lo_pagado(evaluacion, monkeypatch):
    eid = evaluacion["eid"]
    _cobra_hf()
    respuestas = [(_respuesta(n_ideas=0), 3000, 800), (_respuesta(n_ideas=2), 3100, 900)]
    monkeypatch.setattr(analisis, "_llamar", lambda c, s: respuestas.pop(0))
    with pytest.raises(RuntimeError) as e:
        t.meta_rend_evaluar(_tarea_eval(eid))
    assert respuestas == []                      # una corrección y nada más
    fila = datos.evaluacion("hf", eid)
    usd = costo_real(6100, 1700)
    assert fila["estado"] == "error" and fila["error"] == str(e.value) and fila["resultado"] in (None, {})
    assert fila["usd"] == pytest.approx(usd)
    assert _gastos_eval() == [{"tipo": "evaluacion", "usd": pytest.approx(usd), "referencia": f"meta_eval:{eid}:t7",
                               "proveedor": "anthropic"}]
    assert _detalles() == ["sin resultado usable"] and _movimientos_hf() == ["no_cobrado"]

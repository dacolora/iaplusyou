"""Tareas del worker para el rendimiento de Meta (spec 2026-10-08 meta rendimiento §6).

  meta_rend_sincronizar        -> f"{cliente}__meta_rend__{act}"  (max_intentos=2: leer de Meta no cobra).
                                  Una por CUENTA; el payload lleva `cliente` y `ad_account_id`.
  meta_rend_sincronizar_todas  -> periódica (worker.PERIODICAS, 3 h): encola la de cada cuenta de cada proyecto
  meta_rend_limpiar            -> periódica diaria: borra los días de anuncio de más de 95 días y los de cuenta de
                                  más de 400
  meta_rend_evaluar            -> f"{cliente}__meta_eval"  (max_intentos=1: paga a Claude; «Evaluar con IA», spec E2
                                  §8). Una viva por proyecto, en el carril general (no en el de lectura). El gasto
                                  real se anota como tipo `evaluacion` también si la respuesta no sirvió.

Un error de Meta (o cualquier otro) deja ESA cuenta en estado `error` con el motivo en palabras y sin token, y sube
para que la cola reintente; las demás cuentas del proyecto no se enteran.

Límites de uso (ruling R22 de la revisión final, 2026-10-08): el mismo usuario y la misma app de Meta lanzan los
experimentos de colorado_forja, así que leer nunca debe gastar lo que necesita un lanzamiento. Si Meta pide esperar
(códigos 4/17/32/613/8000x o un uso de 75 % o más en las cabeceras), la copia deja la cuenta en `error` con el motivo,
pone la pausa compartida (`meta_rendimiento.pausa`, al menos 30 min) y termina SIN subir: un reintento inmediato
volvería a chocar. Mientras dure la pausa ninguna copia arranca ni la periódica encola, y una copia tampoco arranca
si hay una tarea que ESCRIBE en Meta (`TIPOS_ESCRITURA_META`: las disparadas por una persona, en cola o corriendo;
las periódicas, solo corriendo): cede el turno y se vuelve a encolar sola para dentro de 10 minutos (hasta 6 veces,
ruling R30); después la retoma la siguiente periódica. Como la copia inicial se reanuda desde su marcador, nada se
pierde.

Al terminar bien, la copia guarda en la cuenta las recomendaciones de nivel «alta» de sus reglas (`extra.alertas`, spec
E2 §10) para la pestaña Alertas."""
import logging
from datetime import date, datetime, timedelta

from flask_babel import gettext

import cola
import gastos
import idiomas
import meta_conexion
import trabajos
from meta_rendimiento import analisis, cuentas, datos, graph, pausa, sync
from nicho.avatares import costo_real
from tareas import Continuar, al_interrumpir, ref_sufijo, registrar
from triple_whale import analisis as tw_analisis
from triple_whale import datos as tw_datos

log = logging.getLogger(__name__)
TIPO_SYNC = "meta_rend_sincronizar"
TIPO_TODAS = "meta_rend_sincronizar_todas"
TIPO_LIMPIAR = "meta_rend_limpiar"
# Los nombres son los que emite `sync.sincronizar` por `on_etapa` (así la barra mueve su rango); los pesos suman 100.
ETAPAS_SYNC = [(sync.ETAPA_CUENTA, 5), (sync.ETAPA_OBJETOS, 15), (sync.ETAPA_METRICAS, 70), (sync.ETAPA_ALCANCE, 10)]
MAX_INTENTOS_SYNC = 2
# Mayor = antes (cola.reclamar ordena por prioridad descendente; 5 es lo normal). La copia corre en su propio carril
# (`worker.CARRIL_LECTURA`, un hilo), así que la prioridad solo ordena las copias entre sí; lo que la hace ceder ante
# los lanzamientos es la pausa compartida y `TIPOS_ESCRITURA_META`.
PRIORIDAD_SYNC = 2
DIAS_ANUNCIO_GUARDADOS = 95
DIAS_CUENTA_GUARDADOS = 400   # la copia inicial trae 395 días de cuenta; lo de más de 13 meses se borra
# Tareas que ESCRIBEN en Meta con el usuario y la app que también usa la copia. Las que una persona dispara (lanzar y
# activar al lanzar, la publicación vieja y la orgánica en Facebook e Instagram) frenan la copia desde que están en
# cola. Las periódicas (el decisor: pausa, escala, activa y ejecuta acciones; `exp_avanzar_todos`: las derivaciones
# que lanzan piezas nuevas) solo mientras CORREN: `exp_avanzar_todos` pasa cada 10 min por el único carril general y
# casi siempre espera su turno detrás de tareas largas; frenar la copia por eso la dejaría sin correr durante horas
# (ruling R30, 2026-10-08).
TIPOS_ESCRITURA_USUARIO = ("exp_lanzar", "meta_publicar", "organico_publicar")
TIPOS_ESCRITURA_PERIODICAS = ("exp_decidir", "exp_avanzar_todos")
TIPOS_ESCRITURA_META = TIPOS_ESCRITURA_USUARIO + TIPOS_ESCRITURA_PERIODICAS
# Una copia que cede el turno se vuelve a encolar sola para dentro de 10 minutos, hasta 6 veces (1 hora); después
# se rinde y la siguiente periódica la retoma. El contador viaja en el payload.
ESPERA_POSPUESTA = timedelta(minutes=10)
MAX_POSPOSICIONES = 6


def job_id_sync(cliente, act):
    return f"{cliente}__meta_rend__{act}"


def encolar_sync(cliente, act=None):
    """Encola la copia de esa cuenta, o la de todas las del proyecto si no se dice cuál. Devuelve cuántas quedaron
    en cola (0: ya había una viva, o la cuenta no está en el proyecto)."""
    quiero = cuentas.normalizar_id(act) if act is not None else None
    lista = [a for a in cuentas.ids(cliente) if quiero is None or a == quiero]
    return sum(1 for a in lista if trabajos.encolar(
        job_id_sync(cliente, a), TIPO_SYNC, {"cliente": cliente, "ad_account_id": a}, cliente=cliente,
        duracion_estimada=180, etapas=ETAPAS_SYNC, max_intentos=MAX_INTENTOS_SYNC, prioridad=PRIORIDAD_SYNC))


def syncs_en_curso(cliente):
    """Los job ids de las copias del proyecto que están en cola o corriendo (una consulta): las barras del panel."""
    return sorted(cola.job_ids_vivos(cliente, TIPO_SYNC))


def trabajos_del_panel(cliente):
    """Los job ids vivos (en cola o corriendo) de las copias Y de la evaluación con IA del proyecto, en UNA consulta:
    el panel pinta con ellos las barras de las copias y la de «Evaluar con IA» sin una consulta más."""
    return cola.job_ids_vivos(cliente, (TIPO_SYNC, TIPO_EVALUAR))


def _mensaje_error(e, token):
    """El motivo que se guarda en la cuenta y se muestra: sin token y de 500 caracteres como mucho. De un error de
    Meta (`ErrorGraph`) va su texto, que ya viene traducido; de cualquier otra excepción solo su tipo, porque su
    `str` (una `requests` con la URL) puede traer el token."""
    if isinstance(e, graph.ErrorGraph):
        texto = str(e) or type(e).__name__
    else:
        texto = gettext("No se pudo copiar la cuenta de Meta (%(tipo)s).", tipo=type(e).__name__)
    if token:
        texto = texto.replace(token, "***")
    return cola.recortar(cola.sin_token(texto), 500)


@registrar(TIPO_SYNC)
def meta_rend_sincronizar(tarea):
    p = tarea["payload"]
    cliente, act = p["cliente"], p["ad_account_id"]
    ya_no_esta = gettext("Esa cuenta de Meta ya no está en el proyecto.")
    if not cuentas.cuenta(cliente, act):
        return ya_no_esta
    token = (meta_conexion.cargar(cliente) or {}).get("token")
    if not token:
        # Reintentar no arregla una conexión que falta: se avisa en la cuenta y la tarea termina.
        mensaje = gettext("Meta no está conectado en este proyecto: conéctalo en Configuración › Conexiones.")
        cuentas.actualizar(cliente, act, estado="error", error=mensaje)
        return mensaje
    # Ceder ante Meta: ni con la pausa vigente ni con una escritura en Meta en cola. La cuenta no cambia de estado.
    hasta = pausa.pausada_hasta()
    if hasta:
        return _mensaje_pausa(hasta)
    if escribiendo_en_meta():
        return _pospuesta(p)
    job_id = tarea.get("job_id") or job_id_sync(cliente, act)

    def etapa(nombre, progreso=None):
        trabajos.reportar(job_id, etapa=nombre, progreso=progreso)

    try:
        r = sync.sincronizar(cliente, act, token, on_etapa=etapa)
    except Exception as e:  # noqa: BLE001 — cualquier fallo deja la cuenta en error y la cola reintenta
        mensaje = _mensaje_error(e, token)
        cuentas.actualizar(cliente, act, estado="error", error=mensaje)
        if isinstance(e, graph.ErrorGraph) and e.limite:
            # Meta pidió esperar: pausa para todas las copias y sin subir (un reintento ya volvería a chocar).
            pausa.pausar(e.espera_min)
            return mensaje
        # `from None`: el traceback del worker no arrastra la excepción original (su texto puede traer la URL).
        raise RuntimeError(mensaje) from None
    if r.get("omitida"):
        return ya_no_esta
    _guardar_alertas(cliente, act)
    nombre = (cuentas.cuenta(cliente, act) or {}).get("nombre") or act
    return gettext("Listo (%(cuenta)s): %(dias)s día(s) de la cuenta y %(filas)s fila(s) de anuncios, del %(desde)s al %(hasta)s.",
                   cuenta=nombre, dias=r["dias_cuenta"], filas=r["filas_anuncio"], desde=r["desde"], hasta=r["hasta"])


def _guardar_alertas(cliente, act):
    """Tras una copia buena, las recomendaciones de nivel «alta» de ESA cuenta quedan en `extra.alertas` como
    [{tipo, huella}] para la fuente de Alertas, que así no calcula nada pesado en cada página (spec E2 §10). El título
    no se guarda: Alertas lo arma al vuelo en el idioma de quien mira con el tipo y el nombre de la cuenta (skill
    `alertas`: los textos se traducen al calcular y la huella nunca sale de un texto). Un fallo aquí no tumba la copia:
    se anota solo el tipo del error (su texto podría arrastrar un token) y lo guardado antes se queda."""
    from meta_rendimiento import panel  # noqa: PLC0415 — tardío: panel importa este módulo
    try:
        recs = panel.recomendaciones_de_cuenta(cliente, act)
        cuentas.actualizar_extra(cliente, act, {"alertas": [{"tipo": r["tipo"], "huella": r["id"]}
                                                            for r in recs if r["nivel"] == "alta"]})
    except Exception as e:  # noqa: BLE001 — las alertas son un extra: la copia ya terminó bien
        log.warning("Meta rendimiento: no se calcularon las alertas de %s en %s (%s)", act, cliente,
                    type(e).__name__)


def escribiendo_en_meta():
    """True si una escritura en Meta está en camino: una disparada por una persona, en cola o corriendo, o una
    periódica corriendo ahora."""
    return cola.hay_viva_de(TIPOS_ESCRITURA_USUARIO) or cola.hay_viva_de(TIPOS_ESCRITURA_PERIODICAS, solo_en_curso=True)


def _pospuesta(payload):
    """La copia cede el turno: se vuelve a encolar (mismo job_id, así la barra sigue viva) para dentro de 10 minutos.
    Tras `MAX_POSPOSICIONES` se rinde y deja el texto de siempre: la siguiente copia programada la retoma."""
    n = int(payload.get("pospuestas") or 0)
    if n >= MAX_POSPOSICIONES:
        return gettext("Copia pospuesta: hay una acción en Meta en curso (lanzar, pausar, escalar o publicar). "
                       "La próxima copia programada la retoma.")
    return Continuar(TIPO_SYNC, {**payload, "pospuestas": n + 1}, ejecutar_desde=datetime.now() + ESPERA_POSPUESTA,
                     max_intentos=MAX_INTENTOS_SYNC,
                     mensaje=gettext("Copia pospuesta: hay una acción en Meta en curso (lanzar, pausar, escalar o publicar). "
                                     "Se reintenta en 10 minutos (%(n)s de %(total)s).", n=n + 1, total=MAX_POSPOSICIONES))


def _mensaje_pausa(hasta):
    return gettext("Meta pidió esperar: las copias siguen después de las %(hora)s.", hora=str(hasta)[11:16])


@al_interrumpir(TIPO_SYNC)
def _sync_interrumpida(tarea, mensaje):
    """Un reinicio mató la copia sin reintentos que darle: la cuenta no se queda «copiando» para siempre."""
    p = tarea.get("payload") or {}
    if not (p.get("cliente") and p.get("ad_account_id")):
        return
    c = cuentas.cuenta(p["cliente"], p["ad_account_id"])
    if c and c["estado"] == "copiando":
        cuentas.actualizar(p["cliente"], p["ad_account_id"], estado="error",
                           error=cola.recortar(cola.sin_token(str(mensaje)), 500))


@registrar(TIPO_TODAS)
def meta_rend_sincronizar_todas(tarea):
    hasta = pausa.pausada_hasta()
    if hasta:
        return _mensaje_pausa(hasta)
    n = sum(encolar_sync(cliente, act) for cliente, act in cuentas.todas())
    return gettext("%(n)s copia(s) de Meta en cola", n=n)


@registrar(TIPO_LIMPIAR)
def meta_rend_limpiar(tarea):
    hoy = date.today()
    n = datos.purgar_anuncios((hoy - timedelta(days=DIAS_ANUNCIO_GUARDADOS)).isoformat())
    m = datos.purgar_cuenta_dias((hoy - timedelta(days=DIAS_CUENTA_GUARDADOS)).isoformat())
    return gettext("%(n)s fila(s) viejas de anuncios y %(m)s día(s) viejos de cuentas de Meta borrados", n=n, m=m)


# ---------------------------------------------------------- «Evaluar con IA» (spec E2 §8) ---

TIPO_EVALUAR = "meta_rend_evaluar"
ETAPAS_EVALUAR = [(idiomas.N_("Buscando miniaturas"), 10), (idiomas.N_("Sacando fotogramas"), 15),
                  (idiomas.N_("Analizando con Claude"), 75)]


def job_id_evaluar(cliente):
    return f"{cliente}__meta_eval"


def encolar_evaluacion(cliente, evaluacion_id, costo_estimado=None):
    """max_intentos=1: paga a Claude (una tarea que cobra nunca se reintenta sola). `costo_estimado` (USD del
    proveedor, sin margen): en un proyecto que cobra, `trabajos.encolar` exige y reserva ese precio (skill `cobros`) y
    puede lanzar `SaldoInsuficiente`. False si ya había una evaluación viva en el proyecto."""
    return trabajos.encolar(job_id_evaluar(cliente), TIPO_EVALUAR, {"cliente": cliente, "evaluacion_id": int(evaluacion_id)},
                            cliente=cliente, duracion_estimada=150, etapas=ETAPAS_EVALUAR, max_intentos=1,
                            costo_estimado=costo_estimado)


def evaluacion_en_curso(cliente):
    return trabajos.en_curso(job_id_evaluar(cliente))


@registrar(TIPO_EVALUAR)
def meta_rend_evaluar(tarea):
    """Miniaturas de la muestra (de la copia, copiadas a R2) → fotogramas o imagen → Claude → gasto real → fila
    `lista`. Cualquier fallo deja la fila en `error` con palabras y sin token, y el gasto de lo que Claude sí cobró
    queda anotado (con `entregado=False` si no hubo resultado: en un proyecto que cobra no se le cobra al cliente).
    Si la fila desapareció a mitad (desconectar Meta borra las evaluaciones), el gasto ya pagado igual se anota."""
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["evaluacion_id"])
    job_id = tarea.get("job_id") or job_id_evaluar(cliente)
    referencia = f"meta_eval:{eid}{ref_sufijo(tarea)}"
    entrada = salida = 0
    usd = 0.0
    claude_anotado = llamada_hecha = False
    temporales, elegidos = [], []
    ya_no_existe = gettext("Esa evaluación ya no existe.")
    try:
        fila = datos.evaluacion(cliente, eid)
        if fila is None or not datos.actualizar_evaluacion(eid, estado="analizando", tarea_id=tarea.get("id"),
                                                           error=None):
            return ya_no_existe
        elegidos = list(fila["muestra"] or [])
        trabajos.reportar(job_id, etapa=idiomas.N_("Buscando miniaturas"),
                          detalle=gettext("%(n)s anuncio(s)", n=len(elegidos)))
        medios = analisis.medios(cliente, elegidos)
        creatv = tw_datos.piezas_creatv(cliente, [a["ad_id"] for a in elegidos])
        tw_analisis.con_piezas_creatv(elegidos, medios, creatv)
        medios = tw_analisis.copiar_miniaturas(cliente, eid, elegidos, medios, carpeta=analisis.CARPETA_R2)
        trabajos.reportar(job_id, etapa=idiomas.N_("Sacando fotogramas"))
        bloques, temporales = tw_analisis.visuales(cliente, elegidos, medios, creatv)
        trabajos.reportar(job_id, etapa=idiomas.N_("Analizando con Claude"))
        texto, imagenes = analisis.armar(cliente, fila, medios, bloques)
        llamada_hecha = True
        resultado, entrada, salida = analisis.analizar(texto, imagenes, idiomas.de_proyecto(cliente), elegidos,
                                                       fila["recomendaciones"] or [])
        usd = costo_real(entrada, salida)
        for a in elegidos:
            if medios.get(a["ad_id"]):
                a["medio"] = medios[a["ad_id"]]
            if a["ad_id"] in bloques:
                a["visual"] = bloques[a["ad_id"]]["clase"]
        guardada = datos.actualizar_evaluacion(eid, estado="lista", resultado=resultado, usd=usd, muestra=elegidos,
                                               error=None)
        # El gasto de Claude se anota UNA vez (`registrar_seguro` nunca lanza). Si la fila ya no estaba (desconectar
        # Meta borra las evaluaciones mientras Claude respondía), lo pagado se anota igual pero sin entregar: nadie
        # va a ver ese resultado, así que en un proyecto que cobra no se le cobra.
        gastos.registrar_seguro(cliente, "evaluacion", usd, referencia, proveedor="anthropic", entregado=guardada,
                                detalle=gettext("%(n)s anuncio(s) de Meta", n=len(elegidos)) if guardada
                                else gettext("sin resultado usable"))
        claude_anotado = True
        if not guardada:
            return ya_no_existe
    except Exception as e:
        if not claude_anotado:
            # Los tokens vienen de la excepción (AnalisisInvalido) o, si Claude sí contestó y falló el precio, de aquí.
            entrada = int(getattr(e, "tokens_entrada", entrada) or 0)
            salida = int(getattr(e, "tokens_salida", salida) or 0)
            try:
                usd = costo_real(entrada, salida) if (entrada or salida) else 0.0
            except Exception:  # noqa: BLE001 — sin precio no se inventa uno; el error de la fila sigue en palabras
                log.exception("sin precio para los tokens de la evaluación de Meta %s", eid)
                usd = 0.0
            # E2-R7: una llamada que se quedó sin respuesta (tope de tiempo, conexión cortada) no trae `usage`, pero
            # Anthropic pudo cobrarla: se anota el estimado de la tarifa (sobre lo exacto que ya se sepa).
            estimado = llamada_hecha and tw_analisis.sin_respuesta(e)
            if estimado:
                usd += float(gastos.estimar("evaluacion_meta", n=len(elegidos))["usd"] or 0.0)
            if usd:     # pagado y sin entregar: en un proyecto que cobra no se le cobra (skill `cobros`)
                gastos.registrar_seguro(cliente, "evaluacion", usd, referencia, proveedor="anthropic",
                                        detalle=gettext("estimado: sin respuesta de Claude") if estimado
                                        else gettext("sin resultado usable"), entregado=False)
        mensaje = cola.recortar(cola.sin_token(analisis.texto_error(e)), 500)
        try:
            datos.actualizar_evaluacion(eid, estado="error", error=mensaje, usd=usd)
        except Exception as e_fila:  # noqa: BLE001 — la tarea igual termina en error con su mensaje
            log.warning("la evaluación de Meta %s no se pudo dejar en error: %s", eid, type(e_fila).__name__)
        # `from None`: el traceback del worker no arrastra la excepción original (su texto podría traer un token).
        raise RuntimeError(mensaje) from None
    finally:
        tw_analisis.borrar_temporales(temporales)
    return gettext("Evaluación lista: %(pasos)s paso(s) en el plan y %(ideas)s idea(s) de anuncios nuevos.",
                   pasos=len(resultado["plan"]), ideas=len(resultado["ideas"]))


@al_interrumpir(TIPO_EVALUAR)
def _evaluar_interrumpida(tarea, mensaje):
    """Un reinicio (o el respaldo sin saldo del worker) mató la evaluación: la fila no se queda «analizando»."""
    p = tarea.get("payload") or {}
    if not (p.get("cliente") and p.get("evaluacion_id")):
        return
    fila = datos.evaluacion(p["cliente"], int(p["evaluacion_id"]))
    if fila and fila["estado"] in ("en_cola", "analizando"):
        datos.actualizar_evaluacion(fila["id"], estado="error", error=cola.recortar(cola.sin_token(str(mensaje)), 500))

"""
Trabajos en segundo plano para las acciones lentas del dashboard (generar
prompts, imagen candidata, video, publicar). Evita que el navegador se quede
"colgado" sin avisar nada, y evita que un doble clic dispare la misma acción
dos veces (si ya hay un trabajo en curso con el mismo job_id, no se lanza otro).

Estado en memoria nada más — vive mientras el proceso de dashboard.py esté
arriba. Por eso dashboard.py corre con use_reloader=False: si el auto-reload
matara el proceso a mitad de una generación, esa llamada a Higgsfield se
perdería sin dejar rastro.

Sobre el porcentaje que ve el usuario
-------------------------------------
Ningún proveedor de imagen/video entrega un porcentaje numérico real, así que
inventar un número exacto sería mentir. Lo que sí es verdad y se puede mostrar
son las ETAPAS del trabajo (subir a R2, llamar al modelo, descargar, evaluar).
Por eso un trabajo puede declarar sus etapas con pesos al lanzarse, y llamar a
reportar() cuando pasa de una a la siguiente.

Dentro de cada etapa, si el proveedor no da un progreso real, el avance se
estima con una curva ASINTÓTICA contra el reloj (cada vez avanza menos pero
nunca se detiene) en vez de la rampa lineal topada en 95% que había antes: con
un estimado de 380s contra un timeout real de 900s, la barra vieja llegaba a
95% a los ~6 minutos y se quedaba clavada ahí otros 9, que es exactamente la
sensación de "se colgó".

consultar() devuelve además progreso_real: True SOLO cuando el número viene
medido de verdad (ej. "foto 3 de 9"). Cuando es False la UI no debe imprimir un
porcentaje preciso — pegado a una etapa que sí es real, un número estimado
aparenta ser real, y "en cola · 51%" mientras el proveedor todavía no arrancó es
justo la mentira que este módulo trata de evitar.
"""
import functools
import logging
import math
import re
import threading
import time
from datetime import datetime

import cola  # cola persistente (db.py); los trabajos migrados al worker viven ahí

log = logging.getLogger("creatv.trabajos")

_LOCK = threading.Lock()
_TRABAJOS = {}

# Cuánto tiempo se conserva un trabajo ya terminado. Conservarlos un rato es
# DESEABLE, no un descuido: es lo que permite que el polling del navegador vea
# "completado" y recargue la página. Pasado ese rato ya nadie los mira.
_EDAD_MAXIMA_TERMINADO = 1800  # 30 min


def _preparar_etapas(etapas, duracion_estimada):
    """etapas: [(nombre, peso), ...] -> lista de dicts con el rango de la barra que
    le toca a cada una. Los pesos se normalizan a 100, así el llamador puede
    escribirlos como "más o menos qué fracción del tiempo se lleva cada paso" sin
    preocuparse de que sumen exacto."""
    if not etapas:
        # Sin etapas declaradas: una sola implícita que ocupa toda la barra —
        # mismo contrato que tenían todos los trabajos antes de este cambio.
        return [{"nombre": None, "piso": 0.0, "techo": 100.0, "dur": float(duracion_estimada)}]

    total = float(sum(max(peso, 0) for _, peso in etapas)) or 1.0
    preparadas = []
    acumulado = 0.0
    for nombre, peso in etapas:
        fraccion = max(peso, 0) / total
        piso = acumulado
        acumulado = min(100.0, acumulado + fraccion * 100.0)
        preparadas.append({
            "nombre": nombre,
            "piso": piso,
            "techo": acumulado,
            # Cuánto se espera que dure ESTA etapa, para la curva asintótica.
            "dur": max(1.0, float(duracion_estimada) * fraccion),
        })
    preparadas[-1]["techo"] = 100.0
    return preparadas


def _dur_efectiva(dur, transcurrido):
    """Constante de tiempo de la curva asintótica, con PRESUPUESTO ADAPTATIVO.

    Mientras la etapa va dentro de lo previsto se usa su duración estimada tal
    cual. Cuando se pasa, la constante se estira como sqrt(dur * transcurrido)
    en vez de quedarse fija: así el cociente transcurrido/dur_efectiva sigue
    creciendo (como sqrt del atraso) sin techo, pero cada vez más lento.

    El porqué: ETAPA_SUBIR_ORIGINAL pesa 5 sobre 100 y con un estimado de 380s
    le tocan dur=19s. Subir un mp4 de 720p a R2 tarda 30-120s, y con la constante
    fija la curva saturaba a los ~45s (4.75 de un techo de 5) — la barra quedaba
    visualmente CLAVADA justo en el tramo más largo, peor que la rampa lineal
    vieja. Con el estirón, ese mismo tramo recorre 3.6 -> 4.6 entre los 30 y los
    120 segundos: siempre avanza, nunca retrocede, y nunca alcanza su techo
    antes de tiempo (la exponencial no llega nunca a 1).
    """
    if transcurrido <= dur:
        return dur
    return math.sqrt(dur * transcurrido)


def _progreso_de(t, ahora):
    """% de la barra para un trabajo en progreso: progreso real de la etapa si
    lo hay, si no la curva asintótica contra el reloj. Nunca retrocede
    (progreso_visto). Sirve igual para un dict en memoria que para una fila
    de la tabla tarea (mismas claves)."""
    etapa = t["etapas"][t["indice_etapa"]]
    piso, techo = etapa["piso"], etapa["techo"]
    if t["progreso_etapa"] is not None:
        p = piso + (techo - piso) * t["progreso_etapa"] / 100.0
    else:
        transcurrido_etapa = ahora - t["inicio_etapa"]
        frac = 1.0 - math.exp(-transcurrido_etapa / _dur_efectiva(etapa["dur"], transcurrido_etapa))
        p = piso + (techo - piso) * frac
    p = max(t["progreso_visto"], min(techo, p))
    t["progreso_visto"] = p
    return round(min(99.0, p), 1)


def _purgar():
    """Saca de memoria los trabajos terminados hace rato. OJO: se llama con _LOCK
    YA TOMADO (threading.Lock no es reentrante, volver a pedirlo acá colgaría el
    proceso)."""
    ahora = time.time()
    viejos = [
        jid for jid, t in _TRABAJOS.items()
        if t.get("fin") and ahora - t["fin"] > _EDAD_MAXIMA_TERMINADO
    ]
    for jid in viejos:
        _TRABAJOS.pop(jid, None)


def iniciar(job_id, fn, duracion_estimada=60, etapas=None, cliente=None):
    """Lanza fn() en un hilo aparte, salvo que ya haya un trabajo en curso con
    este mismo job_id (entonces no hace nada). Devuelve True si lo lanzó,
    False si ya estaba en curso (ese es el guardado contra doble clic).

    etapas (opcional): [(nombre, peso), ...] con los pasos reales del trabajo,
    en orden. fn() los va anunciando con reportar(job_id, etapa=...). Si no se
    declaran, el comportamiento es el de siempre: una sola barra de 0 a 100.

    cliente: el proyecto dueño. Es lo que deja a una persona de ese proyecto
    ver la barra en /trabajo/<job_id>/estado (ver `dueno`); sin él, solo el
    administrador la ve."""
    with _LOCK:
        existente = _TRABAJOS.get(job_id)
        if existente and existente["estado"] == "en_progreso":
            return False
        _purgar()
        ahora = time.time()
        preparadas = _preparar_etapas(etapas, duracion_estimada)
        _TRABAJOS[job_id] = {
            "estado": "en_progreso",
            "cliente": cliente,
            "inicio": ahora,
            "fin": None,
            "duracion_estimada": duracion_estimada,
            "mensaje": None,
            "etapas": preparadas,
            "indice_por_nombre": {e["nombre"]: i for i, e in enumerate(preparadas) if e["nombre"]},
            "indice_etapa": 0,
            "inicio_etapa": ahora,
            "etapa_actual": preparadas[0]["nombre"],
            # Progreso REAL dentro de la etapa (0..100), o None si esta etapa no
            # tiene forma de saberlo (que es lo normal).
            "progreso_etapa": None,
            "detalle": None,
            # La barra nunca retrocede: al cambiar de etapa el cronómetro de la
            # nueva arranca en cero, y sin este piso la barra saltaría hacia atrás
            # justo cuando hay buenas noticias que dar.
            "progreso_visto": 0.0,
        }

    def _run():
        try:
            mensaje = fn()
            with _LOCK:
                t = _TRABAJOS.get(job_id)
                if t:
                    t["estado"] = "completado"
                    t["mensaje"] = mensaje or "Listo."
                    t["fin"] = time.time()
        except Exception as e:
            # A /admin/salud: agrupado por la acción (lo último del job_id), no por
            # el job entero, que lleva proyecto e ids.
            import monitoreo
            partes = str(job_id).split("__")
            monitoreo.registrar_excepcion(e, "hilo", ruta=re.sub(r"\d+", "N", partes[-1])[:80],
                                          cliente=partes[0] if len(partes) > 1 else None)
            with _LOCK:
                t = _TRABAJOS.get(job_id)
                if t:
                    t["estado"] = "error"
                    t["mensaje"] = str(e)
                    t["fin"] = time.time()

    threading.Thread(target=_run, daemon=True).start()
    return True


def reportar(job_id, etapa=None, progreso=None, detalle=None):
    """Canal para que un trabajo EN CURSO cuente en qué va. Se llama desde dentro
    de la propia fn() (todas son closures que ya tienen job_id en scope, así que
    no hace falta cambiarles la firma a ninguna).

      etapa    nombre exacto de una de las etapas declaradas en iniciar(); mueve
               el rango de la barra y reinicia el cronómetro de la etapa. Si el
               nombre no está declarado, igual se muestra como texto pero no
               mueve el rango.
      progreso 0..100 REAL dentro de la etapa, o None si no se sabe.
      detalle  texto libre para la UI (ej. "foto 3 de 9", "en cola, puesto 2").

    No-op silencioso si el job_id no existe: reportar jamás debe tumbar una
    generación que ya gastó créditos."""
    with _LOCK:
        t = _TRABAJOS.get(job_id)
    if not t:
        try:
            cola.reportar(job_id, etapa=etapa, progreso=progreso, detalle=detalle)
        except Exception:  # noqa: BLE001 — p. ej. «database is locked» con varios hilos escribiendo
            log.warning("no se pudo reportar el avance de %s", job_id, exc_info=True)
        return
    with _LOCK:
        t = _TRABAJOS.get(job_id)
        if not t:
            return
        if etapa is not None:
            t["etapa_actual"] = etapa
            idx = t["indice_por_nombre"].get(etapa)
            if idx is not None and idx != t["indice_etapa"]:
                t["indice_etapa"] = idx
                t["inicio_etapa"] = time.time()
                t["progreso_etapa"] = None
                # El detalle de la etapa anterior ya no aplica.
                t["detalle"] = None
                t["progreso_visto"] = max(t["progreso_visto"], t["etapas"][idx]["piso"])
        if progreso is not None:
            t["progreso_etapa"] = max(0.0, min(100.0, float(progreso)))
        if detalle is not None:
            t["detalle"] = detalle


_PRECARGA = threading.local()


def con_vivos_precargados(fn):
    """Decorador para una ruta que pinta muchas tarjetas: dentro de `fn`,
    en_curso() no consulta la base por cada job_id sino que mira UNA lectura
    de los job_ids pendientes/en_curso (la página del proyecto lo pedía ~600
    veces por carga, incidente 2026-09-28). Los hilos en memoria (_TRABAJOS)
    se siguen mirando primero. Se limpia al salir, porque gunicorn reutiliza
    los hilos entre peticiones."""
    @functools.wraps(fn)
    def envoltura(*args, **kwargs):
        _PRECARGA.vivos = cola.job_ids_vivos_todos()
        try:
            return fn(*args, **kwargs)
        finally:
            _PRECARGA.vivos = None
    return envoltura


def en_curso(job_id):
    with _LOCK:
        t = _TRABAJOS.get(job_id)
        if t:
            return t["estado"] == "en_progreso"
    vivos = getattr(_PRECARGA, "vivos", None)
    if vivos is not None:
        return job_id in vivos
    fila = cola.consultar_por_job(job_id)
    return bool(fila and fila["estado"] in ("pendiente", "en_curso"))


def dueno(job_id):
    """Proyecto dueño del trabajo (el `cliente` de iniciar() o el de la fila
    de la cola), o None si no existe o no tiene dueño (periódicas, barridos
    globales, hilos lanzados sin `cliente`). El endpoint de estado lo usa para
    que nadie lea la barra —ni el error, que puede traer datos— de un trabajo
    de otro proyecto."""
    with _LOCK:
        t = _TRABAJOS.get(job_id)
        if t:
            return t.get("cliente")
    fila = cola.consultar_por_job(job_id)
    return (fila or {}).get("cliente")


def consultar(job_id):
    """Para el endpoint que el navegador consulta (polling). None si no existe."""
    with _LOCK:
        t = _TRABAJOS.get(job_id)
    if not t:
        fila = cola.consultar_por_job(job_id)
        return _desde_fila(fila) if fila else None
    with _LOCK:
        t = _TRABAJOS.get(job_id)
        if not t:
            return None
        ahora = time.time()
        # El cronómetro se congela al terminar: antes se calculaba siempre contra
        # time.time(), así que un trabajo ya completado seguía "corriendo" para
        # siempre en pantalla.
        elapsed = (t.get("fin") or ahora) - t["inicio"]

        if t["estado"] == "en_progreso":
            # Un decimal, no int(): hay etapas cuyo rango entero mide apenas 5
            # puntos (subir el video original pesa 5 sobre 100), y ahí int()
            # dejaba el mismo número en pantalla durante minutos aunque la barra
            # por dentro sí estuviera avanzando. El decimal cuesta un carácter y
            # devuelve la sensación de que algo está pasando. Ojo: JSON manda
            # 59.0 y JavaScript lo imprime como "59", así que las etapas anchas
            # se siguen viendo redondas.
            progreso = _progreso_de(t, ahora)
        else:
            progreso = 100

        return {
            "estado": t["estado"],
            "progreso": progreso,
            "elapsed": int(elapsed),
            "mensaje": t["mensaje"],
            "etapa": t.get("etapa_actual"),
            "detalle": t.get("detalle"),
            "progreso_real": t.get("progreso_etapa") is not None,
        }


def limpiar(job_id):
    with _LOCK:
        _TRABAJOS.pop(job_id, None)


# ---------- Trabajos persistentes (worker) ----------

def encolar(job_id, tipo, payload, duracion_estimada=60, etapas=None, cliente=None, max_intentos=5, prioridad=5,
            costo_estimado=None, excluir_job=None):
    """Igual que iniciar(), pero la tarea la ejecuta el worker (worker.py) y
    sobrevive reinicios. Devuelve False si ya hay una viva con ese job_id.
    `prioridad`: mayor se atiende antes (5 = normal; los lotes de sprint usan 3
    para no bloquear a quien genera una pieza suelta desde Crear).

    `costo_estimado` (USD, costo del proveedor sin margen; None si no se sabe):
    si el tipo cobra (`tareas.TIPOS_QUE_COBRAN`) y el proyecto cobra, se exige y
    se reserva saldo antes de encolar (spec 2026-10-08 §4-§5); lanza
    cobros.SaldoInsuficiente sin encolar nada. Un job_id ya vivo no exige: el
    clic repetido no hace nada. Un proyecto que no cobra no cambia.
    `excluir_job`: el job_id de la tarea que encola el paso siguiente de su
    cadena mientras corre; su propia reserva no cuenta (ver `libro.exigir`).

    Planes (spec 2026-10-09 §4): si el tipo de tarea anota un tipo de gasto
    incluido (`planes.GASTO_DE_TAREA`), `exigir` lo recibe y, con plan y dentro
    del tope, no pide saldo. Un proyecto que cobra con periodo de plan abierto sube a 6 la
    prioridad normal (5); la de un lote (< 5) o una pedida a mano no cambia."""
    import tareas  # noqa: PLC0415 — tareas/__init__ no importa nada: sin ciclo
    from cobros import libro, planes  # noqa: PLC0415
    if job_id and cola.viva(job_id):
        return False
    if tipo in tareas.TIPOS_QUE_COBRAN:
        tipo_gasto = planes.GASTO_DE_TAREA.get(tipo)
        libro.exigir(cliente, costo_estimado, job_id=job_id, excluir_job=excluir_job,
                     **({"tipo": tipo_gasto} if tipo_gasto else {}))
    if prioridad == 5 and cliente:
        prioridad = _prioridad_de_plan(cliente)
    tid = cola.encolar(tipo, payload, cliente=cliente, job_id=job_id,
                       duracion_estimada=duracion_estimada, etapas=etapas or [],
                       max_intentos=max_intentos, prioridad=prioridad)
    return tid is not None


def _prioridad_de_plan(cliente):
    """6 si el proyecto cobra y tiene un periodo de plan abierto, 5 si no. Si la
    lectura falla, 5: la prioridad nunca frena un encolado."""
    from cobros import libro, planes  # noqa: PLC0415
    try:
        if not libro.cobra_activo(cliente):   # sin «Cobrar» prendido no hay plan que mirar: una lectura barata
            return 5
        return 6 if planes.periodo_abierto(None, cliente) is not None else 5
    except Exception:  # noqa: BLE001
        log.warning("no se pudo leer el plan de %s para la prioridad", cliente, exc_info=True)
        return 5


def _desde_fila(fila):
    """Fila de la tabla tarea -> el mismo dict que devuelve consultar()."""
    ahora = time.time()
    if fila["estado"] == "pendiente":
        return {"estado": "en_progreso", "progreso": 0, "elapsed": 0, "mensaje": None,
                "etapa": "En cola", "detalle": fila.get("error"), "progreso_real": False}
    if fila["estado"] == "en_curso":
        etapas = _preparar_etapas([tuple(e) for e in (fila.get("etapas") or [])], fila.get("duracion_estimada") or 60)
        t = {
            "etapas": etapas,
            "indice_etapa": min(fila.get("indice_etapa") or 0, len(etapas) - 1),
            "progreso_etapa": fila.get("progreso_etapa"),
            "inicio_etapa": fila.get("inicio_etapa") or fila.get("inicio") or ahora,
            "progreso_visto": fila.get("progreso_visto") or 0.0,
        }
        progreso = _progreso_de(t, ahora)
        cola.actualizar_progreso_visto(fila["id"], t["progreso_visto"])
        return {"estado": "en_progreso", "progreso": progreso,
                "elapsed": int(ahora - (fila.get("inicio") or ahora)), "mensaje": None,
                "etapa": fila.get("etapa_actual"), "detalle": fila.get("detalle"),
                "progreso_real": fila.get("progreso_etapa") is not None}
    estado = "completado" if fila["estado"] == "hecha" else "error"
    inicio = fila.get("inicio") or ahora
    fin = ahora
    try:
        fin = datetime.fromisoformat(fila["terminada_en"]).timestamp() if fila.get("terminada_en") else ahora
    except (TypeError, ValueError):
        pass
    return {"estado": estado, "progreso": 100, "elapsed": int(max(0, fin - inicio)),
            "mensaje": fila.get("mensaje"), "etapa": None, "detalle": None, "progreso_real": False}

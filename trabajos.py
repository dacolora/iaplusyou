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
import math
import threading
import time

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


def iniciar(job_id, fn, duracion_estimada=60, etapas=None):
    """Lanza fn() en un hilo aparte, salvo que ya haya un trabajo en curso con
    este mismo job_id (entonces no hace nada). Devuelve True si lo lanzó,
    False si ya estaba en curso (ese es el guardado contra doble clic).

    etapas (opcional): [(nombre, peso), ...] con los pasos reales del trabajo,
    en orden. fn() los va anunciando con reportar(job_id, etapa=...). Si no se
    declaran, el comportamiento es el de siempre: una sola barra de 0 a 100."""
    with _LOCK:
        existente = _TRABAJOS.get(job_id)
        if existente and existente["estado"] == "en_progreso":
            return False
        _purgar()
        ahora = time.time()
        preparadas = _preparar_etapas(etapas, duracion_estimada)
        _TRABAJOS[job_id] = {
            "estado": "en_progreso",
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


def en_curso(job_id):
    with _LOCK:
        t = _TRABAJOS.get(job_id)
        return bool(t and t["estado"] == "en_progreso")


def consultar(job_id):
    """Para el endpoint que el navegador consulta (polling). None si no existe."""
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
            etapa = t["etapas"][t["indice_etapa"]]
            piso, techo = etapa["piso"], etapa["techo"]
            if t["progreso_etapa"] is not None:
                p = piso + (techo - piso) * t["progreso_etapa"] / 100.0
            else:
                # Curva asintótica: se acerca al techo de la etapa sin llegar
                # nunca, así que la barra siempre se mueve un poquito y nunca
                # miente diciendo que ya terminó.
                transcurrido_etapa = ahora - t["inicio_etapa"]
                frac = 1.0 - math.exp(-transcurrido_etapa / _dur_efectiva(etapa["dur"], transcurrido_etapa))
                p = piso + (techo - piso) * frac
            p = max(t["progreso_visto"], min(techo, p))
            t["progreso_visto"] = p
            # Un decimal, no int(): hay etapas cuyo rango entero mide apenas 5
            # puntos (subir el video original pesa 5 sobre 100), y ahí int()
            # dejaba el mismo número en pantalla durante minutos aunque la barra
            # por dentro sí estuviera avanzando. El decimal cuesta un carácter y
            # devuelve la sensación de que algo está pasando. Ojo: JSON manda
            # 59.0 y JavaScript lo imprime como "59", así que las etapas anchas
            # se siguen viendo redondas.
            progreso = round(min(99.0, p), 1)
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

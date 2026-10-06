"""
Monitoreo de la plataforma (spec docs/superpowers/specs/2026-10-01-escala-y-monitoreo-design.md
§6): lo que el administrador ve en /admin/salud para enterarse de los errores
sin entrar al servidor.

- **Errores agrupados** (tabla `error_app`): cada excepción que llega sin
  atrapar a una ruta de Flask, a una tarea del worker o a un hilo de
  `trabajos.iniciar`, y cada `log.error`/`log.exception` de cualquier módulo,
  se guarda UNA vez por huella (origen + tipo + dónde pasó + ruta) con cuántas
  veces pasó, la primera y la última, y la traza de la última — sin tokens
  ni llaves (`limpiar_texto`). Un error nuevo (o uno resuelto que vuelve)
  avisa a los admins por correo (`notificaciones.avisar_admin`, como mucho
  `AVISOS_POR_HORA`). `registrar*` nunca lanza: el monitoreo jamás tumba lo
  que monitorea.
- **Métricas de peticiones** (`METRICAS`, en la memoria del proceso web: hay
  UN proceso, deploy/gunicorn.conf.py): por ruta, cuántas, cuántas 5xx,
  percentiles aproximados, consultas a la base por petición; peticiones por
  minuto de la última hora; las más lentas; cuántas hay en curso.
- **Sistema** (`sistema()`): base y su WAL, disco, memoria, carga, el worker y
  la cola, el último respaldo y los registros. `avisos()` dice en palabras lo
  que hay que arreglar (r2.dev sin CDN, sin SMTP, sin respaldo, disco lleno…).
"""
import hashlib
import logging
import os
import re
import shutil
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timedelta

import sqlalchemy as sa
from flask_babel import gettext, ngettext

import cola
import db
import idiomas
from idiomas import N_

log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORIGENES = ("web", "worker", "hilo", "log")
ESTADOS = ("abierto", "resuelto", "silenciado")
NOMBRES_ORIGEN = {"web": N_("Página o ruta"), "worker": N_("Tarea del worker"), "hilo": N_("Trabajo en segundo plano"),
                  "log": N_("Registro (log.error)")}
NOMBRES_ESTADO = {"abierto": N_("Abierto"), "resuelto": N_("Resuelto"), "silenciado": N_("Silenciado")}
MAX_TRAZA = 8000
MAX_MENSAJE = 500
AVISOS_POR_HORA = 10
# Resueltos y silenciados se borran a los DIAS_CONSERVAR días de su última vez;
# nunca quedan más de MAX_FILAS (los más viejos primero).
DIAS_CONSERVAR = 90
MAX_FILAS = 2000
LENTA_MS = 1000

# Lo que nunca debe quedar guardado ni mostrarse: además de los tokens en
# URLs que ya limpia cola.sin_token, cabeceras Authorization, llaves de
# Anthropic/OpenAI/fal y asignaciones tipo password=… / "secret": "…".
_SECRETOS = (
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 ***"),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{12,}"), "***"),
    (re.compile(r"(?i)((?:api[_-]?key|secret|password|passwd|clave|contrase(?:ñ|n)a|authorization|x-api-key|fal_key)"
                r"[\"']?\s*[:=]\s*[\"']?)[^\s\"',}&]+"), r"\1***"),
)


def limpiar_texto(texto, n=None, final=False):
    """Texto sin tokens ni llaves, recortado a `n` caracteres si se pide (los
    primeros, o los últimos con `final`: de una traza importa el final)."""
    t = cola.sin_token(texto)
    for patron, reemplazo in _SECRETOS:
        t = patron.sub(reemplazo, t)
    if n and len(t) > n:
        return ("…" + t[-(n - 1):]) if final else t[:n]
    return t


def huella(origen, tipo, ubicacion, ruta):
    """Lo que agrupa: el mismo error en el mismo sitio es UNA fila, aunque el
    mensaje cambie (ids, nombres de archivo)."""
    base = "|".join(str(x or "") for x in (origen, tipo, ubicacion, ruta))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]


def _es_de_la_app(nombre):
    return nombre.startswith(BASE_DIR + os.sep) and f"{os.sep}venv{os.sep}" not in nombre[len(BASE_DIR):] \
        and "site-packages" not in nombre


def ubicacion_de(tb):
    """«archivo.py:123 funcion()» del marco MÁS ADENTRO que es código de la
    app (no de una librería): ahí es donde hay que mirar. Sin marcos de la app,
    el más adentro de todos."""
    marcos = traceback.extract_tb(tb) if tb is not None else []
    elegido = next((m for m in reversed(marcos) if _es_de_la_app(m.filename)), marcos[-1] if marcos else None)
    if elegido is None:
        return ""
    nombre = elegido.filename[len(BASE_DIR) + 1:] if _es_de_la_app(elegido.filename) else os.path.basename(elegido.filename)
    return f"{nombre}:{elegido.lineno} {elegido.name}()"


# ------------------------------------------------------------------ errores ---

_REENTRADA = threading.local()


def registrar_excepcion(exc, origen, ruta=None, metodo=None, url=None, cliente=None, usuario=None):
    """Guarda una excepción (con su traza) y devuelve el id de su fila, o None
    si no se pudo. Nunca lanza."""
    try:
        tb = exc.__traceback__
        traza = "".join(traceback.format_exception(type(exc), exc, tb))
        return registrar(origen, type(exc).__name__, f"{type(exc).__name__}: {exc}", ubicacion_de(tb), traza,
                         ruta=ruta, metodo=metodo, url=url, cliente=cliente, usuario=usuario)
    except Exception as e:  # noqa: BLE001 — el monitoreo nunca tumba lo que monitorea
        _sin_monitoreo("no se pudo registrar la excepción: %s", type(e).__name__)
        return None


def _sin_monitoreo(mensaje, *args):
    log.warning(mensaje, *args, extra={"sin_monitoreo": True})


def registrar(origen, tipo, mensaje, ubicacion, traza=None, ruta=None, metodo=None, url=None, cliente=None,
              usuario=None):
    """Suma una vez a la fila de su huella (o la crea). Una fila `resuelto`
    que vuelve a pasar se reabre; una `silenciado` solo suma. Un error nuevo o
    reabierto avisa a los admins. Devuelve el id o None. Nunca lanza."""
    if getattr(_REENTRADA, "activo", False) or apagado():
        return None
    _REENTRADA.activo = True
    try:
        origen = origen if origen in ORIGENES else "log"
        ahora = db.ahora()
        h = huella(origen, tipo, ubicacion, ruta)
        valores = {
            "origen": origen, "tipo": str(tipo or "")[:120], "mensaje": limpiar_texto(mensaje, MAX_MENSAJE),
            "ubicacion": str(ubicacion or "")[:300], "traza": limpiar_texto(traza, MAX_TRAZA, final=True) if traza else None,
            "ruta": str(ruta or "")[:200] or None, "metodo": (metodo or None) and str(metodo)[:8],
            "url": (url or None) and limpiar_texto(str(url).split("?", 1)[0], 500),
            "cliente": (cliente or None) and str(cliente)[:80], "usuario": (usuario or None) and str(usuario)[:80],
        }
        t = db.error_app
        avisar = False
        with db.conectar() as con:
            # Candado de escritura ANTES de leer (como experimentos._bloquear): dos
            # hilos con el mismo error no crean dos filas ni pierden una vez.
            con.execute(t.update().where(t.c.huella == h).values(veces=t.c.veces))
            fila = con.execute(sa.select(t.c.id, t.c.estado).where(t.c.huella == h)).first()
            if fila is None:
                fid = con.execute(t.insert().values(huella=h, veces=1, primera_vez=ahora, ultima_vez=ahora,
                                                    estado="abierto", extra={}, **valores)).inserted_primary_key[0]
                avisar = True
            else:
                fid = fila.id
                # Lo que esta vez no se sabe (sin petición, sin proyecto) no borra lo de la anterior.
                cambios = {"veces": t.c.veces + 1, "ultima_vez": ahora,
                           **{k: v for k, v in valores.items() if v is not None}}
                if fila.estado == "resuelto":
                    cambios.update(estado="abierto", resuelto_en=None)
                    avisar = True
                con.execute(t.update().where(t.c.id == fid).values(**cambios))
        if avisar:
            _avisar_en_hilo(fid)
        return fid
    except Exception as e:  # noqa: BLE001 — sin base (o la base es el problema): queda en el log
        _sin_monitoreo("no se pudo guardar el error %s: %s", tipo, type(e).__name__)
        return None
    finally:
        _REENTRADA.activo = False


def apagado():
    """En las pruebas no se guarda ningún error (una excepción a propósito no
    es un error de la plataforma, y la base podría ser la real) salvo que la
    prueba lo pida con CREATV_MONITOREO_EN_PRUEBAS=1."""
    return "pytest" in sys.modules and (os.environ.get("CREATV_MONITOREO_EN_PRUEBAS") or "").strip() != "1"


def _avisar_en_hilo(fid):
    """El correo sale en otro hilo: un SMTP lento no demora la respuesta 500
    ni la tarea del worker."""
    if not _avisos_activos():
        return
    threading.Thread(target=avisar_error, args=(fid,), daemon=True, name="aviso-error").start()


def _avisos_activos():
    return (os.environ.get("CREATV_AVISOS_ERRORES") or "1").strip() != "0"


def avisar_error(fid):
    """Correo a los admins por un error nuevo o reabierto (como mucho
    AVISOS_POR_HORA por hora entre todos). Nunca lanza."""
    try:
        import cuentas
        import notificaciones
        fila = obtener(fid)
        if not fila or fila["estado"] == "silenciado" or not cuentas.limite_ok("aviso_error_app", AVISOS_POR_HORA, 3600):
            return
        url = (os.environ.get("PLATAFORMA_URL") or "").rstrip("/") + "/admin/salud"

        def asunto():
            return gettext("Error en Creatv: %(tipo)s", tipo=fila["tipo"])

        def cuerpo():
            return gettext("%(mensaje)s\n\nDónde: %(donde)s\nRuta: %(ruta)s\nVeces: %(veces)s\n\nDetalle: %(url)s",
                           mensaje=fila["mensaje"] or "", donde=fila["ubicacion"] or "—", ruta=fila["ruta"] or "—",
                           veces=fila["veces"], url=url)
        notificaciones.avisar_admin("error_app", asunto, cuerpo, cliente=fila.get("cliente") or "")
    except Exception as e:  # noqa: BLE001
        _sin_monitoreo("no se pudo avisar el error %s: %s", fid, type(e).__name__)


def obtener(fid):
    with db.conectar() as con:
        f = con.execute(sa.select(db.error_app).where(db.error_app.c.id == int(fid))).first()
    return dict(f._mapping) if f else None


def listar(estado="abierto", limite=200, origen=None):
    """Filas de `error_app` (la última vez primero). `estado=None` = todas."""
    t = db.error_app
    q = sa.select(t).order_by(t.c.ultima_vez.desc(), t.c.id.desc()).limit(int(limite))
    if estado:
        q = q.where(t.c.estado == estado)
    if origen:
        q = q.where(t.c.origen == origen)
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(q)]


def contar(desde=None):
    """{estado: n} y cuántos abiertos pasaron desde `desde` (ISO; por defecto
    las últimas 24 h)."""
    t = db.error_app
    desde = desde or (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
    out = {e: 0 for e in ESTADOS}
    with db.conectar() as con:
        for estado, n in con.execute(sa.select(t.c.estado, sa.func.count()).group_by(t.c.estado)):
            out[estado] = int(n)
        out["recientes"] = int(con.execute(sa.select(sa.func.count()).select_from(t).where(
            t.c.estado == "abierto", t.c.ultima_vez >= desde)).scalar() or 0)
    return out


def cambiar_estado(fid, estado):
    """Resolver, silenciar o reabrir. True si la fila existía."""
    if estado not in ESTADOS:
        raise ValueError(estado)
    t = db.error_app
    with db.conectar() as con:
        r = con.execute(t.update().where(t.c.id == int(fid)).values(
            estado=estado, resuelto_en=db.ahora() if estado == "resuelto" else None))
    return r.rowcount > 0


def limpiar(dias=DIAS_CONSERVAR, max_filas=MAX_FILAS):
    """Borra resueltos y silenciados cuya última vez tiene más de `dias` días,
    y lo que pase de `max_filas` (los más viejos). Nunca un abierto reciente.
    Devuelve cuántas borró."""
    t = db.error_app
    limite = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    with db.conectar() as con:
        n = con.execute(t.delete().where(t.c.estado != "abierto", t.c.ultima_vez < limite)).rowcount
        sobran = con.execute(sa.select(t.c.id).order_by(t.c.ultima_vez.desc(), t.c.id.desc()).offset(max_filas)).scalars().all()
        if sobran:
            n += con.execute(t.delete().where(t.c.id.in_(sobran))).rowcount
    return n


# ---------------------------------------------------------------- métricas ---

BORDES_MS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)


class Metricas:
    """Peticiones del proceso web desde que arrancó. Un candado; cada petición
    cuesta unos microsegundos."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reiniciar()

    def reiniciar(self):
        with self._lock:
            self.inicio = time.time()
            self.por_ruta = {}
            self.minutos = deque(maxlen=60)
            self.lentas = deque(maxlen=50)
            self.en_vuelo = 0
            self.max_en_vuelo = 0
            self.total = 0
            self.errores = 0

    def empezar(self):
        with self._lock:
            self.en_vuelo += 1
            self.max_en_vuelo = max(self.max_en_vuelo, self.en_vuelo)

    def terminar(self, ruta, estado, ms, consultas=0, url=None, usuario=None, ahora=None):
        ahora = time.time() if ahora is None else ahora
        error = int(estado) >= 500
        with self._lock:
            self.en_vuelo = max(0, self.en_vuelo - 1)
            self.total += 1
            self.errores += error
            r = self.por_ruta.get(ruta)
            if r is None:
                r = self.por_ruta[ruta] = {"n": 0, "errores": 0, "ms": 0.0, "max_ms": 0.0, "consultas": 0,
                                          "hist": [0] * (len(BORDES_MS) + 1)}
            r["n"] += 1
            r["errores"] += error
            r["ms"] += ms
            r["max_ms"] = max(r["max_ms"], ms)
            r["consultas"] += consultas
            r["hist"][_cubeta(ms)] += 1
            minuto = int(ahora // 60)
            if not self.minutos or self.minutos[-1][0] != minuto:
                self.minutos.append([minuto, 0, 0, 0.0])
            m = self.minutos[-1]
            m[1] += 1
            m[2] += error
            m[3] += ms
            if ms >= LENTA_MS:
                self.lentas.appendleft({"ruta": ruta, "url": url, "estado": int(estado), "ms": round(ms),
                                        "usuario": usuario, "cuando": datetime.fromtimestamp(ahora).isoformat(timespec="seconds")})

    def resumen(self, ahora=None, top=25):
        ahora = time.time() if ahora is None else ahora
        with self._lock:
            rutas = [{"ruta": k, **{c: v[c] for c in ("n", "errores", "max_ms")},
                      "medio_ms": v["ms"] / v["n"], "total_ms": v["ms"], "consultas": v["consultas"] / v["n"],
                      "p50": _percentil(v["hist"], 0.5, v["max_ms"]), "p95": _percentil(v["hist"], 0.95, v["max_ms"])}
                     for k, v in self.por_ruta.items()]
            por_minuto = {m[0]: m for m in self.minutos}
            fin = int(ahora // 60)
            serie = [{"minuto": datetime.fromtimestamp(k * 60).strftime("%H:%M"),
                      "n": por_minuto.get(k, [k, 0, 0, 0.0])[1], "errores": por_minuto.get(k, [k, 0, 0, 0.0])[2]}
                     for k in range(fin - 59, fin + 1)]
            out = {"desde": datetime.fromtimestamp(self.inicio).isoformat(timespec="seconds"),
                   "segundos": int(ahora - self.inicio), "total": self.total, "errores": self.errores,
                   "en_vuelo": self.en_vuelo, "max_en_vuelo": self.max_en_vuelo,
                   "lentas": list(self.lentas), "serie": serie,
                   "ultima_hora": sum(p["n"] for p in serie), "ultima_hora_errores": sum(p["errores"] for p in serie)}
        out["rutas"] = sorted(rutas, key=lambda r: -r["total_ms"])[:top]
        out["max_minuto"] = max([p["n"] for p in out["serie"]] + [1])
        return out


def _cubeta(ms):
    for i, borde in enumerate(BORDES_MS):
        if ms <= borde:
            return i
    return len(BORDES_MS)


def _percentil(hist, q, max_ms):
    """Borde superior de la cubeta donde cae el percentil `q` (aproximado,
    «≤ 250 ms»); en la última cubeta, el máximo visto."""
    n = sum(hist)
    if not n:
        return 0
    meta, acumulado = q * n, 0
    for i, c in enumerate(hist):
        acumulado += c
        if acumulado >= meta:
            return BORDES_MS[i] if i < len(BORDES_MS) else round(max_ms)
    return round(max_ms)


METRICAS = Metricas()
_CONSULTAS = threading.local()


def contar_consultas_en_hilo():
    """Empieza a contar las consultas a la base de esta petición (el hilo de
    gunicorn que la atiende). La cuenta la lee `consultas_del_hilo()`."""
    _CONSULTAS.n = 0


def consultas_del_hilo():
    n = getattr(_CONSULTAS, "n", None)
    _CONSULTAS.n = None
    return n or 0


def _contar(*_a, **_k):
    n = getattr(_CONSULTAS, "n", None)
    if n is not None:
        _CONSULTAS.n = n + 1


def instalar_contador_consultas():
    """Una vez por proceso: cada consulta suma al contador del hilo que la
    hizo (fuera de una petición no hay contador y no cuenta)."""
    if not sa.event.contains(sa.engine.Engine, "before_cursor_execute", _contar):
        sa.event.listen(sa.engine.Engine, "before_cursor_execute", _contar)


# ----------------------------------------------------------------- sistema ---

def _bytes(ruta):
    try:
        return os.path.getsize(ruta)
    except OSError:
        return None


def _meminfo():
    datos = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for linea in f:
                clave, _, valor = linea.partition(":")
                datos[clave] = int(valor.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return datos


def _rss():
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for linea in f:
                if linea.startswith("VmRSS:"):
                    return int(linea.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _ruta_sqlite():
    u = db.url()
    return u[len("sqlite:///"):] if u.startswith("sqlite:///") else None


def _respaldo_mas_nuevo(ruta_db):
    carpeta = os.path.join(os.path.dirname(ruta_db), "respaldos") if ruta_db else None
    try:
        nombres = [n for n in os.listdir(carpeta) if n.startswith("creatv_") and n.endswith(".db")]
    except (OSError, TypeError):
        return None
    if not nombres:
        return None
    return datetime.fromtimestamp(max(os.path.getmtime(os.path.join(carpeta, n)) for n in nombres)).isoformat(timespec="seconds")


def cola_salud(ahora=None):
    """Lo que dice si el worker está vivo: tareas por estado, la última que
    terminó, las pendientes atrasadas (deberían haber empezado hace más de
    10 min) y las en curso hace más de 30 min; y por tipo, las de las últimas
    24 h con su duración media."""
    ahora = ahora or datetime.now()
    t = db.tarea
    hace_10 = (ahora - timedelta(minutes=10)).isoformat(timespec="seconds")
    hace_30 = (ahora - timedelta(minutes=30)).isoformat(timespec="seconds")
    hace_24h = (ahora - timedelta(hours=24)).isoformat(timespec="seconds")
    with db.conectar() as con:
        conteo = {e: int(n) for e, n in con.execute(sa.select(t.c.estado, sa.func.count()).group_by(t.c.estado))}
        ultima = con.execute(sa.select(sa.func.max(t.c.terminada_en)).where(t.c.estado == "hecha")).scalar()
        atrasadas = con.execute(sa.select(sa.func.count()).select_from(t).where(
            t.c.estado == "pendiente", t.c.ejecutar_desde < hace_10)).scalar() or 0
        largas = con.execute(sa.select(sa.func.count()).select_from(t).where(
            t.c.estado == "en_curso", t.c.iniciada_en < hace_30)).scalar() or 0
        por_tipo = con.execute(
            sa.select(t.c.tipo, t.c.estado, sa.func.count(),
                      sa.func.avg(sa.func.julianday(t.c.terminada_en) - sa.func.julianday(t.c.iniciada_en)),
                      sa.func.max(sa.func.julianday(t.c.terminada_en) - sa.func.julianday(t.c.iniciada_en)))
            .where(t.c.terminada_en >= hace_24h).group_by(t.c.tipo, t.c.estado)).fetchall()
    tipos = {}
    for tipo, estado, n, media, maximo in por_tipo:
        d = tipos.setdefault(tipo, {"tipo": tipo, "hechas": 0, "error": 0, "media_s": None, "max_s": None})
        d["hechas" if estado == "hecha" else "error"] += int(n)
        if estado == "hecha" and media is not None:
            d["media_s"] = round(media * 86400, 1)
            d["max_s"] = round((maximo or 0) * 86400, 1)
    return {"pendientes": conteo.get("pendiente", 0), "en_curso": conteo.get("en_curso", 0),
            "error": conteo.get("error", 0), "hechas": conteo.get("hecha", 0), "ultima_hecha": ultima,
            "atrasadas": int(atrasadas), "largas": int(largas),
            "por_tipo": sorted(tipos.values(), key=lambda d: -(d["hechas"] + d["error"]))}


def sistema():
    """Foto del servidor para el panel. Cada parte que no se puede leer queda
    en None (otra plataforma, sin /proc) y la página lo dice."""
    ruta_db = _ruta_sqlite()
    mem = _meminfo()
    try:
        disco = shutil.disk_usage(os.path.dirname(ruta_db) if ruta_db else BASE_DIR)
        libre, total = disco.free, disco.total
    except OSError:
        libre = total = None
    try:
        carga = os.getloadavg()
    except (OSError, AttributeError):
        carga = None
    import registro_app
    return {
        "db_bytes": _bytes(ruta_db) if ruta_db else None, "wal_bytes": _bytes(ruta_db + "-wal") if ruta_db else None,
        "disco_libre": libre, "disco_total": total,
        "mem_total": mem.get("MemTotal"), "mem_disponible": mem.get("MemAvailable"), "mem_proceso": _rss(),
        "carga": [round(x, 2) for x in carga] if carga else None, "cpus": os.cpu_count(),
        "hilos": threading.active_count(), "python": sys.version.split()[0],
        "respaldo": _respaldo_mas_nuevo(ruta_db), "registros_bytes": registro_app.tamano_total(),
        "pool": _estado_pool(),
    }


def _estado_pool():
    """Conexiones del pool del proceso web: prestadas ahora y su tamaño."""
    try:
        p = db.engine().pool
        return {"tamano": p.size(), "prestadas": p.checkedout(), "extra": p.overflow()}
    except Exception:  # noqa: BLE001 — otro tipo de pool (tests): no se muestra
        return None


AVISOS = {
    "r2_dev": N_("Las imágenes y los videos salen de r2.dev: tiene límite de tráfico, no pasa por el CDN de "
                 "Cloudflare y no es para producción. Conecta un dominio propio al bucket y ponlo en "
                 "R2_PUBLIC_BASE_URL."),
    "sin_plataforma": N_("Falta PLATAFORMA_URL en el .env: los enlaces de los correos y el host aceptado no están fijos."),
    "sin_proxy": N_("El sitio es https pero falta DETRAS_DE_PROXY=1: detrás de nginx la app ve la IP de nginx, "
                    "no la de cada persona (los límites por IP no sirven)."),
    "sin_smtp": N_("No hay SMTP: los avisos de errores nuevos no salen por correo, solo quedan aquí."),
    "sin_respaldo": N_("No hay un respaldo de la base de las últimas 48 h (data/respaldos). Revisa que el worker "
                       "esté corriendo la tarea diaria db_respaldar."),
    "disco": N_("Queda poco disco (%(libre)s libres). Borra salidas/ viejas o amplía el disco."),
    "memoria": N_("Queda poca memoria (%(libre)s disponibles)."),
    "wal": N_("El WAL de la base pesa %(peso)s: algo mantiene una lectura abierta y no deja hacer checkpoint."),
}


def avisos(sist=None, salud_cola=None, errores=None, entorno=None):
    """[(nivel, clave, texto)] de lo que hay que arreglar, lo grave primero.
    nivel: 'problema' (algo ya falla) o 'aviso' (va a fallar o falla en
    silencio)."""
    entorno = os.environ if entorno is None else entorno
    sist = sist if sist is not None else sistema()
    salud_cola = salud_cola if salud_cola is not None else cola_salud()
    out = []

    def poner(nivel, clave, **x):
        out.append((nivel, clave, gettext(AVISOS[clave], **x) if x else gettext(AVISOS[clave])))

    if salud_cola["atrasadas"]:
        out.append(("problema", "worker_atrasado", ngettext(
            "Hay %(num)d tarea que debía empezar hace más de 10 min: ¿está corriendo el worker?",
            "Hay %(num)d tareas que debían empezar hace más de 10 min: ¿está corriendo el worker?",
            salud_cola["atrasadas"])))
    if errores and errores.get("recientes"):
        out.append(("problema", "errores", ngettext("%(num)d error abierto en las últimas 24 h.",
                                                     "%(num)d errores abiertos en las últimas 24 h.",
                                                     errores["recientes"])))
    if sist.get("disco_libre") is not None and sist.get("disco_total"):
        if sist["disco_libre"] < 2e9 or sist["disco_libre"] / sist["disco_total"] < 0.1:
            poner("problema", "disco", libre=tamano_legible(sist["disco_libre"]))
    if sist.get("mem_disponible") is not None and sist.get("mem_total"):
        if sist["mem_disponible"] / sist["mem_total"] < 0.1:
            poner("aviso", "memoria", libre=tamano_legible(sist["mem_disponible"]))
    if (sist.get("wal_bytes") or 0) > 200e6:
        poner("aviso", "wal", peso=tamano_legible(sist["wal_bytes"]))
    if salud_cola["largas"]:
        out.append(("aviso", "worker_largas", ngettext("Hay %(num)d tarea en curso hace más de 30 min.",
                                                       "Hay %(num)d tareas en curso hace más de 30 min.",
                                                       salud_cola["largas"])))
    respaldo = sist.get("respaldo")
    if sist.get("db_bytes") and (not respaldo or respaldo < (datetime.now() - timedelta(hours=48)).isoformat()):
        poner("aviso", "sin_respaldo")
    r2 = (entorno.get("R2_PUBLIC_BASE_URL") or "").lower()
    if ".r2.dev" in r2:
        poner("aviso", "r2_dev")
    plataforma = (entorno.get("PLATAFORMA_URL") or "").strip()
    if not plataforma:
        poner("aviso", "sin_plataforma")
    elif plataforma.lower().startswith("https://") and (entorno.get("DETRAS_DE_PROXY") or "").strip() != "1":
        poner("aviso", "sin_proxy")
    if not (entorno.get("SMTP_HOST") or "").strip():
        poner("aviso", "sin_smtp")
    return sorted(out, key=lambda a: a[0] != "problema")


def tamano_legible(n):
    if n is None:
        return "—"
    for unidad in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unidad == "TB":
            return f"{idiomas.numero(n, 0 if unidad == 'B' else 1)} {unidad}"
        n /= 1024
    return str(n)


def estado_general(lista_avisos):
    """'problema' | 'aviso' | 'ok' para la cabecera del panel."""
    niveles = {a[0] for a in lista_avisos}
    return "problema" if "problema" in niveles else ("aviso" if niveles else "ok")


def base_responde():
    """True si la base contesta un SELECT 1 (lo que mira /salud)."""
    try:
        with db.conectar() as con:
            return con.execute(sa.text("SELECT 1")).scalar() == 1
    except Exception:  # noqa: BLE001
        return False

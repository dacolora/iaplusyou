"""
Registro (log) de la app en archivos que el administrador lee en
/admin/salud/registros (spec 2026-10-01-escala-y-monitoreo §6.3), sin entrar
al servidor ni a journalctl.

`configurar("web" | "worker")` — una vez por proceso, nunca en las pruebas:
- `data/logs/<proceso>.log`, rotando a los 5 MB y guardando 5 archivos;
- todo `logging` de nivel INFO o más (con los tokens y llaves borrados);
- los `print()` de los módulos, línea por línea (un «[aviso] …» queda como
  WARNING): la salida estándar sigue yendo a journald igual que antes;
- cada registro ERROR o peor (`log.error`, `log.exception`) también entra a
  la tabla de errores agrupados (`monitoreo.registrar`), salvo los que marcan
  `extra={"sin_monitoreo": True}` y los de una excepción que ya se registró
  por otro lado (la ruta de Flask o la tarea del worker).

`leer(proceso, …)` devuelve las últimas entradas (una entrada = una línea con
fecha y las líneas que la siguen, como una traza), la más nueva primero.
"""
import io
import logging
import logging.handlers
import os
import re
import sys
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESOS = ("web", "worker")
NIVELES = ("ERROR", "WARNING", "INFO")
TAMANO_ARCHIVO = 5 * 1024 * 1024
ARCHIVOS_GUARDADOS = 5
FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LEER_BYTES = 2 * 1024 * 1024
_INICIO_ENTRADA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ (CRITICAL|ERROR|WARNING|INFO|DEBUG) (\S+): ?(.*)$")
_configurado = []
_LOCK = threading.Lock()


def carpeta():
    return os.environ.get("CREATV_LOGS") or os.path.join(BASE_DIR, "data", "logs")


def ruta(proceso):
    if proceso not in PROCESOS:
        raise ValueError(proceso)
    return os.path.join(carpeta(), f"{proceso}.log")


class _SinSecretos(logging.Filter):
    """Borra tokens y llaves del texto ANTES de escribirlo."""

    def filter(self, record):
        import monitoreo
        try:
            texto = record.getMessage()
        except Exception:  # noqa: BLE001 — un mensaje mal formado se escribe como venga
            return True
        limpio = monitoreo.limpiar_texto(texto)
        if limpio != texto:
            record.msg, record.args = limpio, ()
        return True


class _AErrores(logging.Handler):
    """ERROR o peor → la tabla de errores agrupados. La huella es el logger y
    la plantilla del mensaje (sin los datos), o la excepción si la trae."""

    def __init__(self, proceso):
        super().__init__(level=logging.ERROR)
        self.origen = "worker" if proceso == "worker" else "log"

    def emit(self, record):
        # sqlalchemy: un error del pool registrado pediría otra conexión al mismo pool.
        if getattr(record, "sin_monitoreo", False) or record.name in ("creatv.salida", "monitoreo") \
                or record.name.startswith("sqlalchemy"):
            return
        import monitoreo
        exc = record.exc_info[1] if record.exc_info else None
        if exc is not None and _ya_registrada(exc):
            return
        try:
            mensaje = record.getMessage()
        except Exception:  # noqa: BLE001
            mensaje = str(record.msg)
        if exc is not None:
            monitoreo.registrar_excepcion(exc, self.origen, ruta=record.name)
        else:
            plantilla = str(record.msg)[:120]
            monitoreo.registrar(self.origen, record.name, mensaje, f"{record.pathname[len(BASE_DIR) + 1:] if record.pathname.startswith(BASE_DIR) else record.pathname}:{record.lineno}",
                                ruta=plantilla)


_YA = threading.local()


def marcar_registrada(exc):
    """La ruta de Flask (o la tarea) ya guardó esta excepción: el log.error que
    Flask escribe después no la vuelve a contar."""
    _YA.exc = exc


def _ya_registrada(exc):
    return getattr(_YA, "exc", None) is exc


class _Espejo(io.TextIOBase):
    """La salida estándar de siempre (journald) y, línea por línea, al logger
    `creatv.salida` (que solo escribe en el archivo)."""

    def __init__(self, original, nivel):
        super().__init__()
        self._original = original
        self._nivel = nivel
        self._pendiente = ""
        self._lock = threading.Lock()
        self._log = logging.getLogger("creatv.salida")

    def write(self, texto):
        self._original.write(texto)
        with self._lock:
            self._pendiente += texto
            *lineas, self._pendiente = self._pendiente.split("\n")
        for linea in lineas:
            if linea.strip():
                nivel = logging.WARNING if linea.lstrip().startswith("[aviso]") else self._nivel
                self._log.log(nivel, linea)
        return len(texto)

    def flush(self):
        self._original.flush()

    def __getattr__(self, nombre):
        return getattr(self._original, nombre)


def configurar(proceso):
    """Idempotente. Devuelve la ruta del archivo o None si no se pudo (sin
    permiso para escribir data/logs: la app sigue igual, sin archivo)."""
    with _LOCK:
        if _configurado:
            return _configurado[0]
        destino = ruta(proceso)
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            archivo = logging.handlers.RotatingFileHandler(destino, maxBytes=TAMANO_ARCHIVO,
                                                           backupCount=ARCHIVOS_GUARDADOS, encoding="utf-8")
        except OSError:
            return None
        archivo.setFormatter(logging.Formatter(FORMATO))
        archivo.addFilter(_SinSecretos())
        raiz = logging.getLogger()
        if raiz.level > logging.INFO or raiz.level == logging.NOTSET:
            raiz.setLevel(logging.INFO)
        # Sin ningún manejador en la raíz, logging escribe WARNING+ a sys.stderr
        # (que ahora es el espejo) y el archivo lo tendría dos veces. La consola
        # (journald) sigue viendo lo mismo que antes: WARNING o más.
        if not raiz.handlers:
            consola = logging.StreamHandler(sys.__stderr__)
            consola.setLevel(logging.WARNING)
            consola.setFormatter(logging.Formatter(FORMATO))
            consola.addFilter(_SinSecretos())
            raiz.addHandler(consola)
        raiz.addHandler(archivo)
        raiz.addHandler(_AErrores(proceso))
        salida = logging.getLogger("creatv.salida")
        salida.propagate = False
        salida.setLevel(logging.INFO)
        salida.addHandler(archivo)
        sys.stdout = _Espejo(sys.stdout, logging.INFO)
        sys.stderr = _Espejo(sys.stderr, logging.WARNING)
        _configurado.append(destino)
        return destino


def tamano_total():
    """Bytes de todos los archivos de registro (con los rotados)."""
    total = 0
    try:
        for nombre in os.listdir(carpeta()):
            if nombre.endswith(".log") or ".log." in nombre:
                total += os.path.getsize(os.path.join(carpeta(), nombre))
    except OSError:
        return None
    return total


def _cola_de(ruta_archivo, n_bytes):
    """Los últimos `n_bytes` del archivo, desde el comienzo de una línea."""
    try:
        with open(ruta_archivo, "rb") as f:
            f.seek(0, os.SEEK_END)
            fin = f.tell()
            f.seek(max(0, fin - n_bytes))
            datos = f.read()
    except OSError:
        return ""
    texto = datos.decode("utf-8", errors="replace")
    if fin > n_bytes and "\n" in texto:
        texto = texto.split("\n", 1)[1]
    return texto


def leer(proceso, n=300, nivel=None, buscar=None, n_bytes=LEER_BYTES):
    """Últimas `n` entradas del registro de `proceso`, la más nueva primero:
    [{"fecha", "nivel", "origen", "texto"}]. `nivel` = mínimo (ERROR muestra
    ERROR y CRITICAL; WARNING, también los avisos). `buscar` filtra por texto
    (sin mayúsculas). Si el archivo actual es corto, sigue con el rotado."""
    import monitoreo
    actual = ruta(proceso)
    texto = _cola_de(actual, n_bytes)
    if len(texto.encode("utf-8")) < n_bytes // 2:
        texto = _cola_de(actual + ".1", n_bytes // 2) + texto
    entradas = []
    for linea in texto.splitlines():
        m = _INICIO_ENTRADA.match(linea)
        if m:
            entradas.append({"fecha": m.group(1), "nivel": m.group(2), "origen": m.group(3), "texto": m.group(4)})
        elif entradas:
            entradas[-1]["texto"] += "\n" + linea
    minimos = {"ERROR": ("ERROR", "CRITICAL"), "WARNING": ("ERROR", "CRITICAL", "WARNING")}.get(nivel)
    q = (buscar or "").strip().casefold()
    out = []
    for e in reversed(entradas):
        if minimos and e["nivel"] not in minimos:
            continue
        if q and q not in e["texto"].casefold() and q not in e["origen"].casefold():
            continue
        e["texto"] = monitoreo.limpiar_texto(e["texto"], 20000)
        out.append(e)
        if len(out) >= n:
            break
    return out

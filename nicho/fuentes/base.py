"""
Contrato común de las fuentes de comentarios (spec §3.1). Toda fuente
(texto pegado, CSV/Excel, Reddit, YouTube, Apify) entrega dicts con las
MISMAS claves — `CLAVES_COMENTARIO` — y `normalizar_comentario` es el único
camino para construirlos: limpia el texto (sin caracteres de control,
espacios colapsados, máximo MAX_TEXTO), descarta textos de menos de
MIN_TEXTO caracteres, cae al hash del texto como `fuente_id`, valida la url,
castea puntuación y fecha. Nunca guarda el autor.

`ErrorFuente` es el único error que una fuente deja escapar hacia el
dashboard o el worker: `.usuario` (== `str(e)`) es un mensaje en español
apto para mostrar tal cual y NUNCA lleva llaves ni HTML ajeno.
"""
import hashlib
import re
from datetime import datetime

CLAVES_COMENTARIO = ("fuente_id", "texto", "url", "contexto", "puntuacion", "fecha", "extra")
MAX_TEXTO = 2000
MIN_TEXTO = 3
MIN_CITA = 12          # largo mínimo de una cita de evidencia (spec §4.3)

_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_RE_ESPACIOS = re.compile(r"\s+")
_RE_URL_HTTP = re.compile(r"^https?://", re.IGNORECASE)


class ErrorFuente(Exception):
    """Error mostrable al usuario. `usuario` es el mensaje en español (sin
    llaves, sin HTML) y `str(e)` devuelve exactamente lo mismo."""

    def __init__(self, usuario):
        self.usuario = str(usuario)
        super().__init__(self.usuario)


def limpiar_texto(texto):
    """Sin caracteres de control, espacios (incluidos saltos) colapsados a
    uno, recortado a MAX_TEXTO."""
    t = _RE_CONTROL.sub("", "" if texto is None else str(texto))
    return _RE_ESPACIOS.sub(" ", t).strip()[:MAX_TEXTO]


def hash_texto(texto):
    """Identidad de un comentario pegado: SHA-1 del texto en minúsculas con
    espacios colapsados, 16 hex. El mismo comentario pegado dos veces no duplica."""
    plano = _RE_ESPACIOS.sub(" ", "" if texto is None else str(texto)).strip().lower()
    return hashlib.sha1(plano.encode("utf-8")).hexdigest()[:16]


def _entero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _fecha_iso(valor):
    """datetime, epoch (int/float) o texto ISO / 'YYYY-MM-DD' -> 'YYYY-MM-DDTHH:MM:SS'.
    Nunca lanza: una fecha ilegible es None (el comentario no se pierde por eso)."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(valor, (int, float)):
        try:
            return datetime.fromtimestamp(float(valor)).strftime("%Y-%m-%dT%H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return None
    t = str(valor).strip().replace(" ", "T", 1)
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(t).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def normalizar_comentario(d):
    """dict cualquiera -> dict con exactamente CLAVES_COMENTARIO, o None si el
    texto no alcanza MIN_TEXTO."""
    d = dict(d or {})
    texto = limpiar_texto(d.get("texto"))
    if len(texto) < MIN_TEXTO:
        return None
    url = ("" if d.get("url") is None else str(d.get("url"))).strip()
    if not _RE_URL_HTTP.match(url):
        url = None
    fuente_id = ("" if d.get("fuente_id") is None else str(d.get("fuente_id"))).strip() or hash_texto(texto)
    extra = d.get("extra")
    return {
        "fuente_id": fuente_id[:120],
        "texto": texto,
        "url": url[:500] if url else None,
        "contexto": limpiar_texto(d.get("contexto"))[:300] or None,
        "puntuacion": _entero(d.get("puntuacion")),
        "fecha": _fecha_iso(d.get("fecha")),
        "extra": dict(extra) if isinstance(extra, dict) else {},
    }


class Fuente:
    """Base de toda fuente. Las subclases fijan `tipo` (clave del registro en
    `nicho.fuentes.REGISTRO`) y `de_pago` (True muestra la puerta de costo).
    `recolectar(params, avanzar)` ITERA dicts ya normalizados; `avanzar(etapa,
    detalle)` es el callback de progreso que el worker traduce a `cola.reportar`.
    `aviso` queda vacío salvo entrega parcial."""
    tipo = None
    de_pago = False

    # Texto que el worker guarda en la recolección cuando la fuente entregó
    # parcial (429 persistente, cuota agotada): la tarea termina bien, con aviso.
    aviso = ""

    def probar(self):
        """Verifica llaves sin gastar. {"ok", "detalle"}."""
        return {"ok": True, "detalle": f"Fuente {self.tipo or 'base'} lista."}

    def estimar(self, params):
        """Solo las de pago: {"max_resultados", "usd"}. Las gratis devuelven None."""
        return None

    def recolectar(self, params, avanzar=None):
        raise NotImplementedError

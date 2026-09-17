"""
Contrato común de los conectores de tienda (bloque 5 del motor de ecommerce).

Todo conector (Shopify, Woo, MELI, CSV/Excel, URL) devuelve productos y
pedidos con las MISMAS claves — `CLAVES_PRODUCTO` / `CLAVES_PEDIDO` — para
que `tiendas.upsert_producto` / `tiendas.upsert_pedidos` no sepan de dónde
vienen. `normalizar_producto` / `normalizar_pedido` son el único camino para
construirlos: rellenan lo que falte, castean el precio (`parsear_precio`
entiende "89.900,00" y "$ 12,50"), suben la moneda a ISO-4217 y deduplican
las fotos.

`ErrorConector` es el único error que un conector deja escapar hacia el
dashboard/worker: `.usuario` (== `str(e)`) es un mensaje en español apto
para mostrar tal cual y NUNCA lleva credenciales ni HTML ajeno.
"""
import html
import re
import unicodedata
from datetime import datetime

CLAVES_PRODUCTO = ("fuente_id", "nombre", "descripcion", "precio", "moneda", "url_compra", "fotos",
                   "categoria", "url_imagen_principal", "extra")
CLAVES_PEDIDO = ("fuente_id", "fecha", "total", "moneda", "items", "utm_content")

_RE_URL_HTTP = re.compile(r"^https?://", re.IGNORECASE)
_RE_MONEDA = re.compile(r"^[A-Z]{3}$")
_RE_ETIQUETAS = re.compile(r"<[^>]+>")
_RE_ESPACIOS = re.compile(r"\s+")
# Caracteres de control (salvo los espacios en blanco normales, que
# _RE_ESPACIOS colapsa): un nombre importado nunca debe llevar \x00, ESC ni
# saltos raros hasta el catálogo/los prompts/la pestaña.
_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
MAX_NOMBRE = 200


class ErrorConector(Exception):
    """Error mostrable al usuario. `usuario` es el mensaje en español (sin
    credenciales, sin HTML) y `str(e)` devuelve exactamente lo mismo."""

    def __init__(self, usuario):
        self.usuario = str(usuario)
        super().__init__(self.usuario)


# --- helpers de normalización ----------------------------------------------

def limpiar_html(texto):
    """HTML de una descripción -> texto plano: quita etiquetas, decodifica
    entidades y colapsa espacios. `<br>`/`</p>` se vuelven un espacio."""
    if texto is None:
        return ""
    texto = html.unescape(_RE_ETIQUETAS.sub(" ", str(texto)))
    return _RE_ESPACIOS.sub(" ", texto).strip()


def slug(texto):
    """"Espejo redondo 60cm" -> "espejo-redondo-60cm" (sin acentos, ASCII)."""
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return texto or "sin-nombre"


def parsear_precio(texto):
    """Texto de precio (con símbolo, espacios, separadores de miles/decimales
    en cualquiera de las dos convenciones) -> float, o None si no hay número.

    Reglas: si aparecen `,` y `.`, el ÚLTIMO separador es el decimal y el otro
    es de miles. Si solo hay `,`: con 1–2 dígitos después es decimal
    ("12,50"), si no es de miles ("1,234"). Si solo hay `.`: varios puntos
    ("1.234.567") o un solo punto con exactamente 3 dígitos detrás y 1–3
    delante distintos de cero ("89.900", precios COP) es de miles; cualquier
    otro caso ("1234.5", "0.999", "199.99") es decimal.
    """
    if texto is None:
        return None
    if isinstance(texto, bool):
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    s = str(texto).strip()
    if not s:
        return None
    # solo dígitos y separadores; el signo negativo se conserva
    negativo = s.startswith("-")
    s = re.sub(r"[^0-9.,]", "", s)
    if not re.search(r"\d", s):
        return None
    tiene_coma, tiene_punto = "," in s, "." in s
    if tiene_coma and tiene_punto:
        ultimo = max(s.rfind(","), s.rfind("."))
        decimal = s[ultimo]
        miles = "." if decimal == "," else ","
        s = s.replace(miles, "").replace(decimal, ".")
    elif tiene_coma:
        entero, _, frac = s.rpartition(",")
        if s.count(",") == 1 and 1 <= len(frac) <= 2:
            s = entero + "." + frac
        else:
            s = s.replace(",", "")
    elif tiene_punto:
        entero, _, frac = s.rpartition(".")
        if s.count(".") > 1 or (len(frac) == 3 and entero.isdigit() and 0 < int(entero) < 1000):
            # "1.234.567" o "89.900" -> separador de miles ("0.999" sigue siendo decimal)
            s = s.replace(".", "")
    try:
        valor = float(s)
    except ValueError:
        return None
    return -valor if negativo else valor


def _texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _nombre(valor):
    """Nombre de producto saneado: sin caracteres de control, espacios
    colapsados, máximo MAX_NOMBRE caracteres."""
    t = _RE_ESPACIOS.sub(" ", _RE_CONTROL.sub("", _texto(valor))).strip()
    return t[:MAX_NOMBRE].strip()


def _texto_o_none(valor):
    t = _texto(valor)
    return t or None


def _moneda(valor):
    t = _texto(valor).upper()
    return t if _RE_MONEDA.match(t) else None


def _fotos(valor):
    """Lista de urls http(s) únicas, en orden. Acepta str, list o None."""
    if not valor:
        return []
    if isinstance(valor, str):
        candidatas = [valor]
    else:
        candidatas = list(valor)
    vistas, salida = set(), []
    for c in candidatas:
        u = _texto(c)
        if not u or not _RE_URL_HTTP.match(u) or u in vistas:
            continue
        vistas.add(u)
        salida.append(u)
    return salida


def normalizar_producto(d):
    """dict cualquiera -> dict con exactamente CLAVES_PRODUCTO (en ese orden).
    `nombre` es obligatorio (ErrorConector si falta); `fuente_id` cae al slug
    del nombre; `url_imagen_principal` cae a la primera foto."""
    d = dict(d or {})
    nombre = _nombre(d.get("nombre"))
    if not nombre:
        raise ErrorConector("El producto no tiene nombre: cada producto necesita un nombre.")
    fotos = _fotos(d.get("fotos"))
    principal = _texto_o_none(d.get("url_imagen_principal"))
    if principal and not _RE_URL_HTTP.match(principal):
        principal = None
    if not principal and fotos:
        principal = fotos[0]
    extra = d.get("extra")
    fuente_id = _texto(d.get("fuente_id")) or slug(nombre)
    return {
        "fuente_id": fuente_id,
        "nombre": nombre,
        "descripcion": _texto(d.get("descripcion")),
        "precio": parsear_precio(d.get("precio")),
        "moneda": _moneda(d.get("moneda")),
        "url_compra": _texto_o_none(d.get("url_compra")),
        "fotos": fotos,
        "categoria": _texto_o_none(d.get("categoria")),
        "url_imagen_principal": principal,
        "extra": dict(extra) if isinstance(extra, dict) else {},
    }


def _fecha_iso(valor):
    """ISO con zona/Z, `YYYY-MM-DD` o `YYYY-MM-DD HH:MM:SS` -> 'YYYY-MM-DDTHH:MM:SS'
    (19 caracteres, sin zona: se conserva la hora tal cual la reportó la tienda)."""
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%dT%H:%M:%S")
    t = _texto(valor)
    if not t:
        raise ErrorConector("El pedido no tiene fecha.")
    t = t.replace(" ", "T", 1)
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        raise ErrorConector(f"Fecha de pedido no reconocida: {t[:40]}")
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _entero(valor, defecto=1):
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return defecto


def normalizar_pedido(d):
    """dict cualquiera -> dict con exactamente CLAVES_PEDIDO."""
    d = dict(d or {})
    fuente_id = _texto(d.get("fuente_id"))
    if not fuente_id:
        raise ErrorConector("El pedido no tiene identificador.")
    items = []
    for it in d.get("items") or []:
        if not isinstance(it, dict):
            continue
        items.append({
            "sku": _texto_o_none(it.get("sku")),
            "nombre": _texto(it.get("nombre")),
            "cantidad": _entero(it.get("cantidad"), 1),
            "precio": parsear_precio(it.get("precio")),
        })
    return {
        "fuente_id": fuente_id,
        "fecha": _fecha_iso(d.get("fecha")),
        "total": parsear_precio(d.get("total")) or 0.0,
        "moneda": _moneda(d.get("moneda")),
        "items": items,
        "utm_content": _texto_o_none(d.get("utm_content")),
    }


# --- clase base -------------------------------------------------------------

class Conector:
    """Base de todo conector de tienda. Las subclases fijan `tipo` (clave del
    registro en `conectores.REGISTRO`), `tiene_pedidos` (si sabe leer ventas)
    y `soporta_utm` (si esas ventas traen `utm_content` para atribuir a una
    pieza). Nunca guardan credenciales fuera de `self.credenciales`."""
    tipo = None
    tiene_pedidos = False
    soporta_utm = False

    def __init__(self, credenciales):
        self.credenciales = dict(credenciales or {})

    def listar_productos(self):
        """-> list[dict] normalizados con `normalizar_producto`."""
        raise NotImplementedError

    def pedidos_desde(self, fecha_iso):
        """-> list[dict] normalizados con `normalizar_pedido`, creados desde
        `fecha_iso` (inclusive). Por defecto la tienda no expone pedidos."""
        return []

    def probar(self):
        """Verifica credenciales sin tocar nada. `{"ok", "nombre", "detalle"}`;
        `nombre` es el nombre de la tienda si la API lo devuelve."""
        return {"ok": True, "nombre": "", "detalle": f"Conector {self.tipo or 'base'} listo."}

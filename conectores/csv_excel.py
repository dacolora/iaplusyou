"""
Catálogo desde un archivo `.csv` o `.xlsx` subido por el cliente (sin API).

`leer(ruta_o_bytes, nombre_archivo)` -> list[dict] normalizados con
`base.normalizar_producto`. Las columnas se reconocen por nombre sin importar
mayúsculas ni acentos, con alias (`name`/`producto`/`titulo` valen como
`nombre`, `image`/`imagenes`/`foto` como `fotos`, etc. — ver `_ALIAS`). La
única obligatoria es `nombre`; sin ella, o sin ningún producto, se lanza
`ErrorConector` con un mensaje que el dashboard muestra tal cual.

Tope de `MAX_FILAS` filas de datos (CSV y Excel por igual, leídas con
`islice` para no materializar un libro de cientos de miles de filas): si el
archivo trae más, se importan las primeras y `leer(..., avisos=[...])`
deja el aviso en español para que la persona sepa que se recortó.
"""
import csv
import io
import os
import re
import unicodedata
from itertools import islice

from .base import ErrorConector, normalizar_producto

COLUMNAS_AYUDA = "nombre, precio, moneda, url_compra, fotos (varias con |), descripcion, categoria, sku"

# clave normalizada -> alias aceptados (ya sin acentos, en minúscula)
_ALIAS = {
    "nombre": ("nombre", "name", "producto", "titulo", "title"),
    "precio": ("precio", "price"),
    "moneda": ("moneda", "currency", "divisa"),
    "url_compra": ("url_compra", "url", "link", "enlace"),
    "fotos": ("fotos", "foto", "imagen", "imagenes", "images", "image", "image_url"),
    "descripcion": ("descripcion", "description", "detalle"),
    "categoria": ("categoria", "category", "tipo"),
    "fuente_id": ("sku", "id", "codigo", "referencia"),
}
_ALIAS_A_CLAVE = {alias: clave for clave, aliases in _ALIAS.items() for alias in aliases}

_RE_VARIAS_URLS = re.compile(r"\s*[|,]\s*")
MAX_FILAS = 5000
AVISO_RECORTE = (f"El archivo tiene más de {MAX_FILAS} filas: solo se importaron las primeras {MAX_FILAS}. "
                 "Divídelo en varios archivos para importar el resto.")


def _clave_columna(cabecera):
    """"Descripción " -> "descripcion" -> clave normalizada o None."""
    t = unicodedata.normalize("NFKD", str(cabecera or "")).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[\s\-]+", "_", t.strip().lower())
    return _ALIAS_A_CLAVE.get(t)


def _celda(valor):
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def _separar_fotos(texto):
    """"a.jpg|b.jpg" o "a.jpg, b.jpg" -> lista; una sola url queda como está
    (una coma dentro de una única url no la parte)."""
    texto = _celda(texto)
    if not texto:
        return []
    partes = [p for p in _RE_VARIAS_URLS.split(texto) if p]
    if len(partes) > 1 and all(p.lower().startswith(("http://", "https://")) for p in partes):
        return partes
    return [texto]


def _filas_csv(datos):
    """bytes -> (cabeceras, filas) probando utf-8-sig y luego latin-1, con
    separador detectado por csv.Sniffer (`,`/`;`/tab; si duda, `,`)."""
    texto = None
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            texto = datos.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    if texto is None or not texto.strip():
        raise ErrorConector("El archivo está vacío.")
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
        separador = dialecto.delimiter
    except csv.Error:
        separador = ","
    lector = csv.reader(io.StringIO(texto), delimiter=separador)
    # cabecera + MAX_FILAS + 1 de más para saber si se recortó
    filas = list(islice(lector, MAX_FILAS + 2))
    if not filas:
        raise ErrorConector("El archivo está vacío.")
    return filas[0], filas[1:]


def _filas_xlsx(datos):
    try:
        import openpyxl
    except ImportError:  # pragma: no cover - openpyxl está en requirements
        raise ErrorConector("No se puede leer Excel en este servidor (falta openpyxl). Sube un CSV.")
    try:
        libro = openpyxl.load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
    except Exception:
        raise ErrorConector("No se pudo abrir el archivo Excel. ¿Es un .xlsx válido?")
    try:
        hoja = libro.worksheets[0]
        filas = [list(f) for f in islice(hoja.iter_rows(values_only=True), MAX_FILAS + 2)]
    finally:
        libro.close()
    if not filas:
        raise ErrorConector("El archivo está vacío.")
    return filas[0], filas[1:]


def leer(ruta_o_bytes, nombre_archivo, avisos=None):
    """`ruta_o_bytes`: ruta en disco o el contenido en bytes. `nombre_archivo`
    solo aporta la extensión (.csv / .xlsx). `avisos` (lista opcional) recibe
    los avisos no fatales, hoy solo AVISO_RECORTE cuando hay más de MAX_FILAS."""
    extension = os.path.splitext(str(nombre_archivo or ""))[1].lower()
    if extension not in (".csv", ".xlsx"):
        raise ErrorConector("Formato no soportado: sube un archivo .csv o .xlsx.")
    if isinstance(ruta_o_bytes, (bytes, bytearray)):
        datos = bytes(ruta_o_bytes)
    else:
        with open(ruta_o_bytes, "rb") as f:
            datos = f.read()
    if not datos.strip():
        raise ErrorConector("El archivo está vacío.")

    cabeceras, filas = _filas_csv(datos) if extension == ".csv" else _filas_xlsx(datos)
    columnas = {}
    for indice, cabecera in enumerate(cabeceras):
        clave = _clave_columna(cabecera)
        if clave and clave not in columnas:
            columnas[clave] = indice
    if "nombre" not in columnas:
        raise ErrorConector(
            "No encontré la columna 'nombre' en la primera fila. Columnas reconocidas: " + COLUMNAS_AYUDA + ".")

    if len(filas) > MAX_FILAS and avisos is not None:
        avisos.append(AVISO_RECORTE)
    productos = []
    for numero, fila in enumerate(filas[:MAX_FILAS], start=2):
        celdas = [_celda(v) for v in fila]
        if not any(celdas):
            continue

        def valor(clave):
            i = columnas.get(clave)
            return celdas[i] if i is not None and i < len(celdas) else ""

        if not valor("nombre"):
            continue  # fila con datos pero sin nombre: no es un producto
        crudo = {
            "fuente_id": valor("fuente_id"),
            "nombre": valor("nombre"),
            "descripcion": valor("descripcion"),
            "precio": valor("precio"),
            "moneda": valor("moneda"),
            "url_compra": valor("url_compra"),
            "fotos": _separar_fotos(valor("fotos")),
            "categoria": valor("categoria"),
            "extra": {"fila": numero},
        }
        productos.append(normalizar_producto(crudo))
    if not productos:
        raise ErrorConector("El archivo no tiene productos (solo la fila de cabeceras).")
    return productos

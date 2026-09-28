"""
Importador (Bloque 5): producto normalizado de un conector → fila `producto`
(tiendas.py) → activo del catálogo de Crear (catalogo_productos.py), para que
lo que vende la tienda se pueda usar como @Producto en los prompts sin subir
las fotos a mano.

`importar_lista(cliente, fuente, productos)` hace, por producto:
  1. `tiendas.upsert_producto` (nuevo o actualizado según ya existiera la
     fila (cliente, fuente, fuente_id));
  2. `vincular_activo`: si el producto ya está ligado a un activo que sigue en
     disco, solo refresca nombre/descripción (NUNCA la regla — la persona la
     pudo editar — ni las fotos, salvo `forzar_fotos`); si no, descarga hasta
     `MAX_FOTOS` fotos (≤ `MAX_BYTES_FOTO` cada una, solo hosts públicos por
     `host_permitido`), crea el activo con `tipo` inferido por palabras clave
     (`inferir_tipo`) y una regla de fidelidad escrita por Claude
     (`generador_prompts.regla_fidelidad`, vacía si falla). Si ya hay una
     carpeta con ese id (mismo nombre subido a mano antes), se ADOPTA en vez
     de duplicarla. Sin ninguna foto descargable no se crea activo: el
     producto queda con `activo_catalogo_id=None` y un aviso en `errores`.

Si el producto trae colores (`extra.variantes` del conector, ver
`conectores.base.normalizar_variante`), cada uno se guarda como una
subcarpeta del activo (`catalogo_productos.agregar_color`/`actualizar_color`)
con sus propias fotos; las fotos del producto van a la raíz como generales,
nunca como referencia de un color. La regla de fidelidad se paga UNA sola
vez por producto al crear el activo — nunca por color, nunca al refrescar.
Un color que deja de venir de la tienda queda `disponible=False` sin borrar
sus fotos; las fotos de un color ya existente solo se vuelven a bajar con
`forzar_fotos` o si su subcarpeta está vacía. `resumen["colores"]` cuenta
cuántos colores se crearon en la corrida.

`max_activos` (opcional) acota cuántos productos SIN activo se ligan por
corrida — el paso 2 baja fotos y llama a Claude, y el worker es de un solo
hilo. El resto se guarda igual (paso 1) y cuenta en `resumen["pendientes"]`
para que la tarea encole otra corrida (ver `tareas/tiendas.py`); los ya
ligados siempre se refrescan (barato) y no cuentan para el tope.

Un producto que falle no frena a los demás: el error queda listado en
`errores` (texto en el idioma del proyecto, sin URLs completas ni
credenciales) y el resumen sigue. Las fotos se bajan primero a una carpeta temporal y solo se
mueven a la carpeta del activo cuando hay al menos una — así una descarga
fallida no deja carpetas fantasma ni gasta la llamada a Claude.
"""
import logging
import os
import re
import shutil
import tempfile
import unicodedata
from urllib.parse import urljoin, urlparse

import requests
from flask_babel import gettext

import catalogo_productos
import db
import gastos
import generador_prompts
import idiomas
import prompt_swap
import tiendas
from conectores import csv_excel
from conectores import url as conector_url
from conectores.base import ErrorConector
from conectores.url import host_permitido  # noqa: F401 — re-export: los tests lo parchean acá

log = logging.getLogger("creatv.importador")

CATEGORIA_ACTIVO = "producto"
MAX_FOTOS = 6
MAX_BYTES_FOTO = 8 * 1024 * 1024
TIMEOUT_FOTO = 30
MAX_REDIRECCIONES = 3
_CODIGOS_REDIRECCION = (301, 302, 303, 307, 308)
_EXT_POR_CONTENT_TYPE = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/pjpeg": ".jpg",
    "image/png": ".png", "image/webp": ".webp",
}
_CABECERAS_FOTO = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "image/jpeg,image/png,image/webp,image/*;q=0.8,*/*;q=0.5",
}

# Palabras clave (sin acentos, minúsculas) por tipo de prompt_swap.TIPOS. Se
# mira primero el nombre, después la categoría y al final la descripción; y
# dentro de cada texto gana la PRIMERA palabra clave que aparece — en español
# el sustantivo principal va adelante ("Bolso para tenis" es un bolso,
# "Tenis con bolso de regalo" es calzado).
PALABRAS_TIPO = {
    "calzado": ("zapato", "zapatos", "zapatilla", "zapatillas", "tenis", "sneaker", "sneakers", "sandalia",
                "sandalias", "bota", "botas", "botin", "botines", "chancla", "chanclas", "chancleta",
                "chancletas", "slide", "slides", "mocasin", "mocasines", "tacon", "tacones", "calzado",
                "pantufla", "pantuflas", "crocs", "alpargata", "alpargatas"),
    "prenda": ("camisa", "camisas", "camiseta", "camisetas", "playera", "polo", "blusa", "blusas", "pantalon",
               "pantalones", "jean", "jeans", "vestido", "vestidos", "hoodie", "buzo", "buzos", "sudadera",
               "chaqueta", "chaquetas", "abrigo", "falda", "faldas", "short", "shorts", "bermuda", "leggins",
               "leggings", "licra", "chaleco", "saco", "sueter", "top", "bikini", "traje", "enterizo",
               "conjunto", "pijama", "ropa", "prenda", "uniforme", "gorra", "gorro"),
    "bolso": ("bolso", "bolsos", "mochila", "mochilas", "cartera", "carteras", "morral", "morrales",
              "rinonera", "canguro", "maleta", "maletin", "bandolera", "tote", "billetera", "neceser"),
    "textil_hogar": ("cobija", "cobijas", "manta", "mantas", "cojin", "cojines", "almohada", "almohadas",
                     "sabana", "sabanas", "toalla", "toallas", "edredon", "cubrelecho", "funda", "cortina",
                     "cortinas", "mantel", "manteles", "tapete", "alfombra"),
}


# --- tipo ----------------------------------------------------------------------

def _palabras(texto):
    """Palabras ASCII minúsculas (sin acentos) de un texto, en orden."""
    limpio = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9]+", limpio)


_TIPO_POR_PALABRA = {palabra: tipo for tipo, claves in PALABRAS_TIPO.items() for palabra in claves}

# "tenis" solo es calzado si no va con una raqueta: "Raqueta de tenis" es un
# implemento deportivo, no un zapato. Compañeras de un deporte de raqueta —
# si aparecen en el mismo texto, "tenis" se ignora como palabra clave.
_DEMOTE_TENIS = ("raqueta", "raquetas")


def inferir_tipo(nombre, descripcion="", categoria=""):
    """Tipo de `prompt_swap.TIPOS` por palabras clave; `otro` si nada calza.
    Solo tipos que existan en prompt_swap (si alguien renombra uno, cae a
    `otro` en vez de guardar un tipo inválido)."""
    textos = (nombre, categoria, descripcion)
    demotar_tenis = any(palabra in _DEMOTE_TENIS for texto in textos for palabra in _palabras(texto))
    for texto in textos:
        for palabra in _palabras(texto):
            if demotar_tenis and palabra == "tenis":
                continue
            tipo = _TIPO_POR_PALABRA.get(palabra)
            if tipo and tipo in prompt_swap.TIPOS:
                return tipo
    return "otro" if "otro" in prompt_swap.TIPOS else prompt_swap.TIPO_POR_DEFECTO


# --- fotos ---------------------------------------------------------------------

def _extension(content_type, url_foto):
    """Extensión del archivo por content-type; si el servidor no lo dice (o
    manda octet-stream), por la extensión de la URL. Un content-type que no
    es imagen (text/html de una página de error, JSON) descarta la foto."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _EXT_POR_CONTENT_TYPE:
        return _EXT_POR_CONTENT_TYPE[ct]
    if ct and not ct.startswith("image/") and ct not in ("application/octet-stream", "binary/octet-stream"):
        return None
    try:
        ruta = urlparse(url_foto).path
    except ValueError:
        ruta = ""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    return ext if ext in (".jpg", ".png", ".webp") else None


def _host_ok(url_foto):
    """host_permitido tolerante: un DNS que no resuelve es "no permitido",
    nunca una excepción (una foto no puede tumbar la importación)."""
    try:
        return bool(host_permitido(url_foto))
    except ErrorConector:
        return False


def _abrir_foto(url_foto):
    """GET en streaming siguiendo redirecciones A MANO (máximo
    MAX_REDIRECCIONES) y validando el host en cada salto, igual que
    conectores.url: una URL pública que redirige a la red interna no se
    sigue. None si no se pudo abrir."""
    redirecciones = 0
    while True:
        if not _host_ok(url_foto):
            return None
        try:
            respuesta = requests.get(url_foto, headers=_CABECERAS_FOTO, timeout=TIMEOUT_FOTO, stream=True,
                                     allow_redirects=False)
        except requests.RequestException:
            return None
        if getattr(respuesta, "status_code", 500) not in _CODIGOS_REDIRECCION:
            return respuesta
        cerrar = getattr(respuesta, "close", None)
        if cerrar:
            cerrar()
        ubicacion = (getattr(respuesta, "headers", None) or {}).get("Location")
        if redirecciones >= MAX_REDIRECCIONES or not ubicacion:
            return None
        redirecciones += 1
        url_foto = urljoin(url_foto, ubicacion)


def _descargar_foto(url_foto, destino_sin_ext):
    """Baja UNA foto a `destino_sin_ext + extensión`. Devuelve la ruta final
    o None (cualquier problema: host privado, HTTP >= 400, no es imagen,
    pesa más de MAX_BYTES_FOTO, corte de red)."""
    respuesta = _abrir_foto(url_foto)
    if respuesta is None:
        return None
    ruta = None
    try:
        if getattr(respuesta, "status_code", 500) >= 400:
            return None
        cabeceras = getattr(respuesta, "headers", None) or {}
        ext = _extension(cabeceras.get("Content-Type"), url_foto)
        if not ext:
            return None
        try:
            largo = int(cabeceras.get("Content-Length") or 0)
        except (TypeError, ValueError):
            largo = 0
        if largo > MAX_BYTES_FOTO:
            return None
        ruta = destino_sin_ext + ext
        total = 0
        with open(ruta, "wb") as f:
            for trozo in respuesta.iter_content(chunk_size=65536):
                if not trozo:
                    continue
                total += len(trozo)
                if total > MAX_BYTES_FOTO:
                    f.close()
                    os.remove(ruta)
                    return None
                f.write(trozo)
        if total == 0:
            os.remove(ruta)
            return None
        return ruta
    except (requests.RequestException, OSError):
        if ruta and os.path.exists(ruta):
            try:
                os.remove(ruta)
            except OSError:
                pass
        return None
    finally:
        cerrar = getattr(respuesta, "close", None)
        if cerrar:
            cerrar()


def descargar_fotos(urls, carpeta):
    """Baja hasta MAX_FOTOS fotos a `carpeta` como 01.jpg, 02.png… (numeradas
    por orden de la fuente, así la primera sigue siendo la representativa).
    Devuelve (rutas_descargadas, fallidas) — fallidas es cuántas URLs no se
    pudieron bajar."""
    os.makedirs(carpeta, exist_ok=True)
    rutas, fallidas = [], 0
    for i, url_foto in enumerate((urls or [])[:MAX_FOTOS], start=1):
        ruta = _descargar_foto(url_foto, os.path.join(carpeta, f"{i:02d}"))
        if ruta:
            rutas.append(ruta)
        else:
            fallidas += 1
    return rutas, fallidas


def _tiene_imagenes(carpeta):
    try:
        return any(f.lower().endswith(catalogo_productos.IMAGE_EXTS) for f in os.listdir(carpeta))
    except OSError:
        return False


def _reemplazar_fotos(carpeta, temporal):
    """Mueve las fotos de `temporal` a `carpeta` reemplazando las numeradas
    que ya hubiera (01.*, 02.*…). Las fotos con otro nombre (subidas a mano)
    se conservan."""
    os.makedirs(carpeta, exist_ok=True)
    for f in os.listdir(carpeta):
        if re.match(r"^\d{2}\.(jpg|jpeg|png|webp)$", f.lower()):
            try:
                os.remove(os.path.join(carpeta, f))
            except OSError:
                pass
    for f in sorted(os.listdir(temporal)):
        shutil.move(os.path.join(temporal, f), os.path.join(carpeta, f))


def _variantes_de(prod):
    """Colores que trae el conector en `extra.variantes` (§6 del spec)."""
    vs = (prod.get("extra") or {}).get("variantes") or []
    return [v for v in vs if isinstance(v, dict) and str(v.get("nombre") or "").strip()]


def _activo_con_fotos(cliente, activo_id):
    """True si el activo tiene alguna foto en la raíz o en algún color."""
    carpeta = catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO)
    if _tiene_imagenes(carpeta):
        return True
    try:
        sub = [d for d in os.listdir(carpeta) if os.path.isdir(os.path.join(carpeta, d))]
    except OSError:
        return False
    return any(_tiene_imagenes(os.path.join(carpeta, d)) for d in sub)


def _bajar_a(fotos, carpeta_destino, prod, errores, que=""):
    """Descarga `fotos` a un temporal y, si bajó alguna, reemplaza las
    numeradas de `carpeta_destino`. True si colocó al menos una."""
    if not fotos:
        return False
    temporal = tempfile.mkdtemp(prefix="creatv_fotos_")
    try:
        rutas, fallidas = descargar_fotos(fotos, temporal)
        if fallidas:
            errores.append(_aviso(prod, f"{que + ': ' if que else ''}{fallidas} foto(s) no se pudieron descargar."))
        if not rutas:
            return False
        _reemplazar_fotos(carpeta_destino, temporal)
        return True
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def _color_existente(meta_variantes, var):
    """color_id ya guardado para esta variante: por fuente_id, o por el id derivado del nombre."""
    fid = str(var.get("fuente_id") or "")
    if fid:
        for cid, datos in meta_variantes.items():
            if str((datos or {}).get("fuente_id") or "") == fid:
                return cid
    cid = catalogo_productos.id_desde_nombre(var["nombre"])
    return cid if cid in meta_variantes else None


def _color_id_libre(meta_variantes, nombre):
    base = catalogo_productos.id_desde_nombre(nombre)
    cid, n = base, 2
    while cid in meta_variantes:
        cid = f"{base}-{n}"
        n += 1
    return cid


def _colocar_colores(cliente, activo_id, prod, variantes, forzar_fotos, errores, descargadas=None):
    """Agrega los colores que falten, refresca los existentes (nombre, url,
    disponible, fuente_id) y coloca sus fotos: de `descargadas`
    ({índice: carpeta temporal}) si ya se bajaron, o descargándolas — colores
    nuevos siempre; existentes solo con `forzar_fotos` o si no tienen
    ninguna. Un color importado que ya no viene de la tienda queda
    `disponible=False` (sus fotos no se borran). Devuelve cuántos se crearon."""
    nombre_producto = (prod.get("nombre") or "").strip()
    carpeta = catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO)

    def _existentes():
        v = (catalogo_productos.cargar_meta(cliente).get(activo_id) or {}).get("variantes")
        return dict(v) if isinstance(v, dict) else {}

    existentes = _existentes()
    nuevos, vistos = 0, set()
    for i, var in enumerate(variantes):
        nombre_color = f"{nombre_producto} — {var['nombre'].strip()}" if nombre_producto else var["nombre"].strip()
        datos = {"fuente_id": var.get("fuente_id"), "url_compra": var.get("url_compra"),
                 "disponible": var.get("disponible", True) is not False}
        cid = _color_existente(existentes, var)
        if cid is None:
            try:
                cid = catalogo_productos.agregar_color(
                    cliente, activo_id, nombre_color, color_id=_color_id_libre(existentes, var["nombre"]),
                    convertir_actual=nombre_producto or activo_id, **datos)
            except ValueError as e:
                errores.append(_aviso(prod, f"color «{var['nombre']}»: {e}"))
                continue
            existentes = _existentes()
            nuevos += 1
            bajar = True
        else:
            catalogo_productos.actualizar_color(cliente, activo_id, cid, nombre=nombre_color, **datos)
            bajar = forzar_fotos or not _tiene_imagenes(os.path.join(carpeta, cid))
        vistos.add(cid)
        destino = os.path.join(carpeta, cid)
        if descargadas is not None:
            if bajar and i in descargadas:
                _reemplazar_fotos(destino, descargadas[i])
        elif bajar:
            _bajar_a(var.get("fotos") or [], destino, prod, errores, f"color «{var['nombre']}»")
    for cid, datos in existentes.items():
        if cid not in vistos and (datos or {}).get("fuente_id") and (datos or {}).get("disponible", True) is not False:
            catalogo_productos.actualizar_color(cliente, activo_id, cid, disponible=False)
    return nuevos


def _completar_fotos(cliente, activo_id, prod, fotos, variantes, forzar_fotos, errores):
    """Activo ya existente: colores (los nuevos siempre; los existentes según
    `forzar_fotos`) y luego las fotos de la raíz — generales si hay colores,
    la referencia si es plano — solo con `forzar_fotos` o si no hay ninguna.
    Devuelve cuántos colores se crearon."""
    carpeta = catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO)
    nuevos = _colocar_colores(cliente, activo_id, prod, variantes, forzar_fotos, errores) if variantes else 0
    if fotos and (forzar_fotos or not _tiene_imagenes(carpeta)):
        _bajar_a(fotos, carpeta, prod, errores, "fotos generales" if variantes else "")
    return nuevos


# --- activo --------------------------------------------------------------------

def _aviso(prod, texto):
    return f"{prod.get('nombre') or prod.get('fuente_id') or '?'}: {texto}"


def _activo_ocupado_por_otro(cliente, activo_id, producto_id):
    """True si OTRO producto (id distinto) del mismo cliente ya está ligado a
    `activo_id`. Dos productos con el mismo nombre ("Gorra" en dos
    colecciones) derivarían el mismo id por `id_desde_nombre`; sin este
    chequeo el segundo pisaría fotos/descripción del primero cada sync."""
    return any(p["activo_catalogo_id"] == activo_id and p["id"] != producto_id
               for p in tiendas.productos(cliente, incluir_archivados=True))


def _id_activo_disponible(cliente, nombre, fuente_id, producto_id):
    """`activo_id` derivado del nombre, o `-2`/`-3`… si ese id ya lo tiene
    OTRO producto. Uno libre (no existe en disco, o existe pero nadie más lo
    reclama — carpeta subida a mano) se devuelve tal cual."""
    base = catalogo_productos.id_desde_nombre(nombre or fuente_id or "producto")
    candidato = base
    sufijo = 2
    while (catalogo_productos.existe(cliente, candidato, CATEGORIA_ACTIVO)
           and _activo_ocupado_por_otro(cliente, candidato, producto_id)):
        candidato = f"{base}-{sufijo}"
        sufijo += 1
    return candidato


def vincular_activo(cliente, producto_id, forzar_fotos=False, errores=None):
    """Liga el producto (fila `producto`) a un activo del catálogo de Crear.
    Devuelve el `activo_id` (None si no se pudo). Con `extra.variantes`
    (§7 del spec) cada color es una subcarpeta con sus fotos y las fotos del
    producto van a la raíz como generales; sin variantes, todo como antes.

    - Ya ligado y la carpeta existe → refresca nombre/descripción (NUNCA la
      regla), agrega los colores nuevos, refresca los existentes y solo
      vuelve a bajar fotos con `forzar_fotos` o donde no haya ninguna.
    - No ligado → si otro producto ya reclamó el id derivado del nombre, se
      desambigua (`-2`, `-3`…). Si ya existe la carpeta con ese id (subida a
      mano) se ADOPTA: sus fotos de raíz pasan a ser un color con el nombre
      del producto y se le agregan los de la tienda. Si no, se baja TODO a un
      temporal primero; sin ninguna foto no hay activo ni llamada a Claude;
      con alguna, `catalogo_productos.crear` con tipo inferido y regla de
      Claude, luego los colores y por último las generales.
    Nunca deja un activo sin ninguna foto (no aparecería en listar())."""
    if errores is None:
        errores = []
    prod = tiendas.producto(cliente, producto_id)
    if prod is None:
        errores.append(f"producto {producto_id}: no existe.")
        return None
    nombre = (prod.get("nombre") or "").strip()
    descripcion = (prod.get("descripcion") or "").strip()
    fotos = list(prod.get("fotos") or [])
    variantes = _variantes_de(prod)

    activo_id = prod.get("activo_catalogo_id")
    if activo_id and catalogo_productos.existe(cliente, activo_id, CATEGORIA_ACTIVO):
        catalogo_productos.actualizar(cliente, activo_id, nombre=nombre, descripcion=descripcion or None,
                                      categoria=CATEGORIA_ACTIVO)
        _completar_fotos(cliente, activo_id, prod, fotos, variantes, forzar_fotos, errores)
        return activo_id

    if not fotos and not any(v.get("fotos") for v in variantes):
        errores.append(_aviso(prod, "sin fotos: no se creó el activo del catálogo."))
        return None

    activo_id = _id_activo_disponible(cliente, nombre, prod.get("fuente_id"), producto_id)
    if catalogo_productos.existe(cliente, activo_id, CATEGORIA_ACTIVO):
        # Mismo nombre que un activo subido a mano (y libre): se adopta, no se duplica.
        catalogo_productos.actualizar(cliente, activo_id, nombre=nombre, descripcion=descripcion or None,
                                      categoria=CATEGORIA_ACTIVO)
        _completar_fotos(cliente, activo_id, prod, fotos, variantes,
                         forzar_fotos or not _activo_con_fotos(cliente, activo_id), errores)
        if not _activo_con_fotos(cliente, activo_id):
            errores.append(_aviso(prod, "sin fotos: no se enlazó al activo del catálogo."))
            return None
        tiendas.marcar_producto(cliente, producto_id, activo_catalogo_id=activo_id)
        return activo_id

    temporal = tempfile.mkdtemp(prefix="creatv_fotos_")
    creado_ahora = False
    try:
        # Todo se baja ANTES de crear el activo y de pagar la regla.
        raiz = os.path.join(temporal, "_raiz")
        rutas_raiz, fallidas = descargar_fotos(fotos, raiz)
        descargadas = {}
        for i, var in enumerate(variantes):
            carpeta_c = os.path.join(temporal, f"c{i}")
            rutas_c, f = descargar_fotos(var.get("fotos") or [], carpeta_c)
            fallidas += f
            if rutas_c:
                descargadas[i] = carpeta_c
        if not rutas_raiz and not descargadas:
            errores.append(_aviso(prod, "no se pudo descargar ninguna foto: no se creó el activo del catálogo."))
            return None
        if fallidas:
            errores.append(_aviso(prod, f"{fallidas} foto(s) no se pudieron descargar."))
        regla = generador_prompts.regla_fidelidad(nombre, descripcion, prod.get("categoria") or "",
                                                   idiomas.de_proyecto(cliente))
        if regla:
            # Claude respondió (una regla vacía es el fallback sin llamada o
            # con error, que no cobra). Tarifa fija: el SDK no devuelve el
            # precio y una llamada de ~600 tokens cuesta menos que ese tope.
            gastos.registrar_seguro(cliente, "regla_producto", gastos.TARIFAS["regla_producto"],
                                    f"regla_producto:{producto_id}", proveedor="anthropic",
                                    detalle=f"regla de fidelidad de «{nombre}»"[:300])
        tipo = inferir_tipo(nombre, descripcion, prod.get("categoria") or "")
        try:
            activo_id = catalogo_productos.crear(cliente, nombre, descripcion, tipo=tipo,
                                                 categoria=CATEGORIA_ACTIVO, regla=regla, producto_id=activo_id)
            creado_ahora = True
        except ValueError:
            # Carrera: alguien creó la carpeta entre `existe` y `crear`. Se adopta.
            if not catalogo_productos.existe(cliente, activo_id, CATEGORIA_ACTIVO):
                raise
        carpeta = catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO)
        # Colores ANTES que las generales: con la raíz vacía agregar_color no
        # convierte nada; las generales de un producto con colores no son referencia.
        if variantes:
            _colocar_colores(cliente, activo_id, prod, variantes, True, errores, descargadas=descargadas)
        if rutas_raiz:
            _reemplazar_fotos(carpeta, raiz)
        if not _activo_con_fotos(cliente, activo_id):
            if creado_ahora:
                catalogo_productos.eliminar(cliente, activo_id, CATEGORIA_ACTIVO)
            errores.append(_aviso(prod, "sin fotos: no se creó el activo del catálogo."))
            return None
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
    tiendas.marcar_producto(cliente, producto_id, activo_catalogo_id=activo_id)
    return activo_id


def _bajar_y_colocar(cliente, activo_id, fotos, prod, errores):
    """Envoltorio de compatibilidad sobre `_bajar_a` (por si algún test u otro
    módulo la sigue llamando directo)."""
    return _bajar_a(fotos, catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO), prod, errores)


# --- lista ---------------------------------------------------------------------

def _progreso(on_progreso, etapa, detalle=None):
    if on_progreso is None:
        return
    try:
        on_progreso(etapa, detalle)
    except Exception:  # noqa: BLE001 — la barra nunca frena la importación
        log.debug("on_progreso falló", exc_info=True)


def _activo_completo(cliente, prod):
    """True si el producto ya está ligado a un activo que existe en disco y
    tiene al menos una imagen — o sea, `vincular_activo` solo le refrescaría
    nombre/descripción (barato: ni fotos ni Claude)."""
    activo_id = prod.get("activo_catalogo_id")
    if not activo_id or not catalogo_productos.existe(cliente, activo_id, CATEGORIA_ACTIVO):
        return False
    return _activo_con_fotos(cliente, activo_id)


def _orden_pendientes(prod):
    """Primero lo que NUNCA se intentó ligar (así cada corrida hace progreso
    real y la continuación termina aunque haya muchos productos sin fotos
    descargables ya intentados), luego lo que está en prueba, luego por
    prioridad, y por id para que sea estable. Los ya intentados quedan al
    final: se reintentan solo cuando no queda nada nuevo."""
    extra = prod.get("extra") or {}
    return (1 if extra.get("vinculo_intentado_en") else 0, 0 if prod.get("en_prueba") else 1,
            -int(prod.get("prioridad") or 0), int(prod.get("id") or 0))


def _n_colores(cliente, pid):
    """Cuántos colores tiene guardados en la meta el activo ligado a `pid`
    (0 si no está ligado o el activo no existe en disco). Sirve para contar
    `resumen["colores"]` por diferencia sin cambiar la firma de
    `vincular_activo`."""
    prod = tiendas.producto(cliente, pid) or {}
    aid = prod.get("activo_catalogo_id")
    if not aid or not catalogo_productos.existe(cliente, aid, CATEGORIA_ACTIVO):
        return 0
    v = (catalogo_productos.cargar_meta(cliente).get(aid) or {}).get("variantes")
    return len(v) if isinstance(v, dict) else 0


def importar_lista(cliente, fuente, productos_normalizados, on_progreso=None, max_activos=None):
    """Guarda cada producto normalizado (ver conectores.base.CLAVES_PRODUCTO)
    bajo `fuente` y le liga su activo. `on_progreso(etapa, detalle)` recibe
    "Guardando productos" y luego "Creando activos" con "n de N".

    `max_activos` acota el trabajo caro por corrida: cuántos productos SIN
    activo completo (fotos a bajar + regla de Claude) se intentan ligar
    (orden `_orden_pendientes`); los ya ligados se refrescan siempre (solo
    nombre/descripción). Los que quedan fuera del tope se guardan igual
    (fila `producto`, sin activo) y cuentan en `pendientes` — la tarea que
    llama decide cómo completarlos (una corrida siguiente). `pendientes`
    solo cuenta los que NUNCA se intentaron: los que ya se intentaron y no
    dieron activo (sin fotos) no justifican otra corrida.
    Devuelve {"nuevos", "actualizados", "activos", "colores", "pendientes", "errores": [str]}."""
    resumen = {"nuevos": 0, "actualizados": 0, "activos": 0, "colores": 0, "pendientes": 0, "errores": []}
    lista = list(productos_normalizados or [])
    _progreso(on_progreso, "Guardando productos", f"{len(lista)} producto(s)")
    ids = []
    for prod in lista:
        try:
            fuente_id = str(prod.get("fuente_id") or "").strip()
            if not fuente_id or not (prod.get("nombre") or "").strip():
                resumen["errores"].append(_aviso(prod, "sin nombre o sin identificador; se omitió."))
                continue
            existia = tiendas.producto_por_fuente(cliente, fuente, fuente_id) is not None
            if existia and (prod.get("extra") or {}).get("descripcion_cargada") is False:
                # MELI solo trae la descripción en la primera sync (cuota por
                # ítem): una corrida sin ella no debe borrar la guardada.
                prod = {k: v for k, v in prod.items() if k != "descripcion"}
            pid = tiendas.upsert_producto(cliente, fuente, fuente_id, prod)
            resumen["actualizados" if existia else "nuevos"] += 1
            ids.append(pid)
        except Exception as error:  # noqa: BLE001 — un producto malo no frena la lista
            log.warning("importar %s/%s: %s", cliente, fuente, error, exc_info=True)
            resumen["errores"].append(_aviso(prod, f"no se pudo guardar ({type(error).__name__})."))

    ids_set = set(ids)
    guardados = {p["id"]: p for p in tiendas.productos(cliente, incluir_archivados=True) if p["id"] in ids_set}
    completos = [pid for pid in ids if pid in guardados and _activo_completo(cliente, guardados[pid])]
    completos_set = set(completos)
    pendientes = sorted((guardados[pid] for pid in ids if pid in guardados and pid not in completos_set),
                        key=_orden_pendientes)
    if max_activos is not None and len(pendientes) > max_activos:
        fuera = pendientes[max_activos:]
        pendientes = pendientes[:max_activos]
        resumen["pendientes"] = sum(1 for p in fuera if not (p.get("extra") or {}).get("vinculo_intentado_en"))
    a_ligar = {p["id"] for p in pendientes}
    orden = [p["id"] for p in pendientes] + completos
    for i, pid in enumerate(orden, start=1):
        _progreso(on_progreso, "Creando activos", f"{i} de {len(orden)}")
        try:
            antes = _n_colores(cliente, pid)
            if vincular_activo(cliente, pid, errores=resumen["errores"]):
                resumen["activos"] += 1
            elif pid in a_ligar:
                tiendas.anotar_extra(cliente, pid, vinculo_intentado_en=db.ahora())
            resumen["colores"] += max(0, _n_colores(cliente, pid) - antes)
        except Exception as error:  # noqa: BLE001
            log.warning("vincular activo %s/%s: %s", cliente, pid, error, exc_info=True)
            prod = tiendas.producto(cliente, pid) or {}
            resumen["errores"].append(_aviso(prod, f"no se pudo crear el activo ({type(error).__name__})."))
            if pid in a_ligar:
                tiendas.anotar_extra(cliente, pid, vinculo_intentado_en=db.ahora())
    return resumen


def desde_archivo(cliente, ruta, nombre_archivo, on_progreso=None, max_activos=None):
    """CSV/Excel (conectores.csv_excel) → importar_lista(fuente="csv").
    ErrorConector si el archivo no se puede leer (la tarea lo muestra tal
    cual). Un archivo con más filas que el tope del lector deja el aviso
    en `errores` (la persona tiene que saber que se recortó)."""
    _progreso(on_progreso, "Leyendo", os.path.basename(str(nombre_archivo or "")))
    avisos = []
    lista = csv_excel.leer(ruta, nombre_archivo, avisos=avisos)
    resumen = importar_lista(cliente, "csv", lista, on_progreso=on_progreso, max_activos=max_activos)
    resumen["errores"] = avisos + resumen["errores"]
    return resumen


def desde_url(cliente, url, on_progreso=None, max_activos=None):
    """Página de producto (conectores.url) → importar_lista(fuente="url")."""
    _progreso(on_progreso, "Leyendo", None)
    prod = conector_url.leer(url)
    return importar_lista(cliente, "url", [prod], on_progreso=on_progreso, max_activos=max_activos)


def resumen_texto(resumen):
    """Frase en el idioma del proyecto para la barra/el mensaje de la tarea."""
    partes = [gettext("%(n)s producto(s) nuevo(s)", n=resumen.get("nuevos", 0)),
              gettext("%(n)s actualizado(s)", n=resumen.get("actualizados", 0)),
              gettext("%(n)s con activo en el catálogo", n=resumen.get("activos", 0))]
    if resumen.get("colores"):
        partes.append(gettext("%(n)s color(es) nuevo(s)", n=resumen["colores"]))
    texto = ", ".join(partes) + "."
    pendientes = int(resumen.get("pendientes") or 0)
    if pendientes:
        texto += " " + gettext(
            "%(n)s producto(s) guardado(s) sin activo todavía: el resto se completa solo en las próximas corridas.",
            n=pendientes)
    errores = resumen.get("errores") or []
    if errores:
        muestra = "; ".join(errores[:3])
        if len(errores) > 3:
            muestra += "; " + gettext("y %(n)s más", n=len(errores) - 3)
        texto += " " + gettext("%(n)s aviso(s): %(muestra)s", n=len(errores), muestra=muestra)
    return texto

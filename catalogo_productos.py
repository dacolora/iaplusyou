"""
Catálogo de productos para el flujo de "cambiar calzado": cada carpeta en
clientes/<cliente>/productos/ es UN producto (colorway), con varias fotos de
referencia (mismo producto, distintos ángulos/tomas) para darle a Nano Banana
la mejor fidelidad posible al generar. Al usuario solo se le muestra UNA foto
representativa por producto — las demás son material interno.
"""
import hashlib
import os
import re
import unicodedata

from flask_babel import gettext

import _json_store
import idiomas
import mapa_corporal
import prompt_swap

BASE_DIR = os.path.dirname(__file__)
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# Defaults históricos de happyflops, de cuando el catálogo era código. Se
# conservan como CAPA BASE para no renombrarle los productos a nadie: lo que el
# usuario edite desde el dashboard vive en productos.json y pisa esto.
NOMBRES = {
    "horiginal": "HOriginal — Beige",
    "ho_sky": "HOriginal — Sky Blue",
    "ho_rose": "HOriginal — Rose",
}

# Solo para el proveedor Higgsfield: no acepta una foto de producto como segunda
# referencia (una sola imagen de referencia por llamada), así que el color/diseño
# del calzado se le describe en texto en vez de mostrárselo.
DESCRIPCIONES = {
    "horiginal": "chanclas tipo slide HappyFlops, de goma acanalada, color beige claro uniforme",
    "ho_sky": "chanclas tipo slide HappyFlops, de goma acanalada, color celeste (sky blue) uniforme",
    "ho_rose": "chanclas tipo slide HappyFlops, de goma acanalada, color rosa (rose) uniforme",
}


# Categorías del catálogo. "producto" conserva su carpeta y su meta históricas
# (productos/, productos.json) porque los swaps ya generados apuntan ahí; las
# nuevas categorías viven en sus propias carpetas. Cada una tiene su regla de
# consistencia, que es lo que se le dice al modelo para que NO cambie el activo.
CATEGORIAS = {
    "producto": {
        "nombre": idiomas.N_("Producto"), "plural": idiomas.N_("Productos"), "carpeta": "productos", "meta": "productos.json",
        "etiqueta": "@Producto", "descripcion_ui": idiomas.N_("Lo que vendes: calzado, ropa, decoración, comida, lo que sea."),
        "regla": idiomas.N_(
            "Reprodúcelo idéntico a su referencia: misma forma, mismo color, misma textura y el mismo "
            "logotipo o marca tal como aparece, en el mismo lugar. No inventes ni cambies letras, logos ni etiquetas."),
        "regla_en": ("Reproduce it identical to its reference: same shape, same color, same texture and the "
                     "same logo or brand exactly as it appears, in the same place. Do not invent or change "
                     "letters, logos or labels."),
        "con_mapa": True,
    },
    "personaje": {
        "nombre": idiomas.N_("Personaje"), "plural": idiomas.N_("Personajes"), "carpeta": "personajes_catalogo", "meta": "personajes_catalogo.json",
        "etiqueta": "@Personaje", "descripcion_ui": idiomas.N_("La cara de la marca: una persona real, un embajador o un personaje creado que debe verse igual siempre."),
        "regla": idiomas.N_(
            "Es la MISMA persona/personaje en todas las tomas: misma cara, mismos rasgos, mismo pelo, misma "
            "complexión y la misma ropa y accesorios que en las referencias. No cambies edad, género, piel ni estilo. "
            "Manos y pies anatómicamente correctos."),
        "regla_en": ("It is the SAME person/character in every shot: same face, same features, same hair, "
                     "same build and the same clothes and accessories as in the references. Do not change "
                     "age, gender, skin or style. Anatomically correct hands and feet."),
        "con_mapa": False,
    },
    "entorno": {
        "nombre": idiomas.N_("Entorno"), "plural": idiomas.N_("Entornos"), "carpeta": "entornos", "meta": "entornos.json",
        "etiqueta": "@Entorno", "descripcion_ui": idiomas.N_("Lugares y escenas: tu tienda, un showroom, la sala donde va el espejo."),
        "regla": idiomas.N_(
            "La escena ocurre en ESTE lugar: conserva paredes, piso, muebles, decoración y luz tal como se ven en las "
            "referencias. El producto y las personas se integran ahí; no reconstruyas ni redecores el espacio."),
        "regla_en": ("The scene takes place in THIS place: keep walls, floor, furniture, decoration and light "
                     "exactly as seen in the references. The product and the people blend in there; do not "
                     "rebuild or redecorate the space."),
        "con_mapa": False,
    },
}
CATEGORIA_POR_DEFECTO = "producto"


def categoria_valida(cat):
    return cat if cat in CATEGORIAS else CATEGORIA_POR_DEFECTO


def regla_categoria(categoria, idioma="es"):
    """Regla de consistencia de la categoría en el idioma de los prompts del proyecto."""
    info = CATEGORIAS[categoria_valida(categoria)]
    return info["regla_en"] if idioma == "en" else info["regla"]


def _carpeta(cliente, categoria=CATEGORIA_POR_DEFECTO):
    return os.path.join(BASE_DIR, "clientes", cliente, CATEGORIAS[categoria_valida(categoria)]["carpeta"])


def _meta_path(cliente, categoria=CATEGORIA_POR_DEFECTO):
    return os.path.join(BASE_DIR, "clientes", cliente, CATEGORIAS[categoria_valida(categoria)]["meta"])


def cargar_meta(cliente, categoria=CATEGORIA_POR_DEFECTO):
    """{id: {"nombre":..., "descripcion":...}} — lo que el usuario editó desde el
    dashboard. Es una capa ENCIMA de NOMBRES/DESCRIPCIONES, no un reemplazo."""
    return _json_store.cargar(_meta_path(cliente, categoria), {})


def guardar_meta(cliente, meta, categoria=CATEGORIA_POR_DEFECTO):
    """Escritura directa (atómica, pero SIN lock). Para leer-modificar-
    escribir usa `modificar_meta`: gunicorn (Catálogo) y el worker
    (importador, una vez por producto durante una sync) escriben el mismo
    JSON, y sin lock una de las dos escrituras pisa a la otra."""
    _json_store.guardar(_meta_path(cliente, categoria), meta)


def _lock_meta(cliente, categoria):
    return os.path.join(_carpeta(cliente, categoria), ".meta.lock")


def modificar_meta(cliente, categoria, fn):
    """cargar → `fn(meta) -> meta` → guardar, bajo un `fcntl.flock` exclusivo
    sobre `<carpeta de la categoría>/.meta.lock`, que serializa hilos Y
    procesos (Flask y worker) sobre el JSON de metadatos. `fn` recibe el
    dict recién leído y devuelve el que se guarda (None = no guardar
    nada). Devuelve lo que devolvió `fn`."""
    import fcntl

    categoria = categoria_valida(categoria)
    ruta_lock = _lock_meta(cliente, categoria)
    os.makedirs(os.path.dirname(ruta_lock), exist_ok=True)
    with open(ruta_lock, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            resultado = fn(cargar_meta(cliente, categoria))
            if resultado is not None:
                guardar_meta(cliente, resultado, categoria)
            return resultado
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def id_desde_nombre(nombre):
    """El id es también el nombre de la carpeta en disco, así que tiene que ser
    seguro: sin acentos, sin espacios, sin nada que pueda escaparse del
    directorio de productos."""
    limpio = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-zA-Z0-9]+", "_", limpio).strip("_").lower()
    return limpio or "producto"


def producto_base(activo_id):
    """'horiginal/beige' -> 'horiginal'; un id sin color vuelve igual; None -> ''."""
    return str(activo_id or "").split("/", 1)[0]


def sin_archivados(entradas, archivados, conservar=()):
    """Las entradas de `listar()`/`listar_productos()` (categoría producto)
    que un selector puede ofrecer: sin los productos archivados (`archivados`
    = set de pids, `tiendas.activos_archivados`) — con todos sus colores —,
    salvo los que ya están elegidos en lo que se pinta (`conservar`: ids de
    producto o de color; vacíos y None se ignoran). Un selector nunca debe
    perder en silencio el producto que una campaña, un estudio o una
    precarga ya usan."""
    entradas = list(entradas)
    if not archivados:
        return entradas
    guardar = {producto_base(c) for c in conservar or () if c}
    return [e for e in entradas if producto_base(e["id"]) not in archivados or producto_base(e["id"]) in guardar]


def _imagenes_en(carpeta):
    try:
        return sorted(f for f in os.listdir(carpeta) if f.lower().endswith(IMAGE_EXTS))
    except OSError:
        return []


def _variantes_de(propio):
    """Los colores de la meta de un producto, en el orden guardado ({} si es plano)."""
    v = propio.get("variantes")
    return v if isinstance(v, dict) and v else {}


def _frase_variante(nombre_color, descripcion, idioma):
    if idioma == "en":
        return f'Variant "{nombre_color}": {descripcion}'
    return f"Variante «{nombre_color}»: {descripcion}"


def _regla_de(propio, categoria, idioma, variante=None):
    """Regla de la categoría + regla propia + (color) su descripción."""
    partes = [regla_categoria(categoria, idioma), (propio.get("regla") or "").strip()]
    if variante and (variante.get("descripcion") or "").strip():
        partes.append(_frase_variante(variante.get("nombre") or "", variante["descripcion"].strip(), idioma))
    return " ".join(p for p in partes if p).strip()


def _mapa(propio, idioma):
    zonas = propio.get("zonas")
    return {
        "zonas": mapa_corporal.normalizar(zonas),
        "mapa_texto": mapa_corporal.describir(zonas, idioma),
        "mapa_etiqueta": mapa_corporal.ETIQUETAS_PRESETS.get(mapa_corporal.preset_de(zonas)),
    }


def _recorrer(cliente, categoria):
    """(pid, propio, ruta, variantes, archivos_raiz) por carpeta de la categoría, en orden de nombre."""
    carpeta = _carpeta(cliente, categoria)
    if not os.path.isdir(carpeta):
        return
    meta = cargar_meta(cliente, categoria)
    for pid in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, pid)
        if not os.path.isdir(ruta) or pid.startswith("."):
            continue
        propio = meta.get(pid, {})
        yield pid, propio, ruta, _variantes_de(propio), _imagenes_en(ruta)


def _nombre_producto(pid, propio):
    return propio.get("nombre") or NOMBRES.get(pid, pid.replace("_", " ").title())


def _url_publica(cliente, info_cat, relativa):
    public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    return f"{public_base}/clientes/{cliente}/{info_cat['carpeta']}/{relativa}" if public_base else None


def listar(cliente, categoria=CATEGORIA_POR_DEFECTO):
    """Una entrada por activo del catálogo: cada color de un producto con
    colores (id `pid/color`) o el producto plano (id `pid`). Un color o un
    producto sin fotos no aparece. Las fotos de la raíz de un producto con
    colores son generales: no son referencia y no salen aquí."""
    categoria = categoria_valida(categoria)
    info_cat = CATEGORIAS[categoria]
    idioma = idiomas.de_proyecto(cliente)
    productos = []
    for pid, propio, ruta, variantes, raiz in _recorrer(cliente, categoria):
        nombre_prod = _nombre_producto(pid, propio)
        comun = {"categoria": categoria, "etiqueta_base": info_cat["etiqueta"], "producto_id": pid,
                 "nombre_producto": nombre_prod, "tipo": prompt_swap.tipo_valido(propio.get("tipo")),
                 "regla_propia": (propio.get("regla") or "").strip(), **_mapa(propio, idioma)}
        if variantes:
            for cid, var in variantes.items():
                ruta_c = os.path.join(ruta, cid)
                archivos = _imagenes_en(ruta_c)
                if not archivos:
                    continue
                id_color = f"{pid}/{cid}"
                nombre = var.get("nombre") or f"{nombre_prod} {cid.title()}"
                productos.append({**comun, "id": id_color, "nombre": nombre, "variante": cid, "variante_nombre": nombre,
                                  "descripcion": var.get("descripcion") or "",
                                  "disponible": var.get("disponible", True) is not False,
                                  "regla": _regla_de(propio, categoria, idioma, dict(var, nombre=nombre)),
                                  "referencias": [os.path.join(ruta_c, f) for f in archivos], "imagenes": archivos,
                                  "representativa": os.path.join(ruta_c, archivos[0]),
                                  "representativa_url": _url_publica(cliente, info_cat, f"{id_color}/{archivos[0]}")})
        else:
            if not raiz:
                continue
            productos.append({**comun, "id": pid, "nombre": nombre_prod, "variante": None, "variante_nombre": None,
                              "descripcion": propio.get("descripcion") or DESCRIPCIONES.get(pid, ""), "disponible": True,
                              "regla": _regla_de(propio, categoria, idioma),
                              "referencias": [os.path.join(ruta, f) for f in raiz], "imagenes": raiz,
                              "representativa": os.path.join(ruta, raiz[0]),
                              "representativa_url": _url_publica(cliente, info_cat, f"{pid}/{raiz[0]}")})
    return productos


def agrupar_por_producto(lista):
    """Agrupa una lista de `listar()` por producto (spec 2026-09-28 §10.5): un
    producto con colores queda con todas sus entradas juntas, en el orden en
    que aparecieron. Filtro de plantilla (`_selector_productos.html`,
    `_sprint_panel_armar.html`) en vez de `|groupby('producto_id')` porque ese
    filtro de Jinja ORDENA por la clave antes de agrupar, y una entrada sin
    `producto_id` (catálogos falsos de tests viejos, previos a los colores)
    vuelve esa clave `Undefined` — comparar dos `Undefined` para ordenar
    revienta con `UndefinedError` apenas hay 2 o más entradas así. Acá cada
    entrada sin `producto_id` cae sola en su propio grupo, por su `id`."""
    grupos, indice = [], {}
    for p in lista:
        clave = p.get("producto_id") or p["id"]
        if clave not in indice:
            indice[clave] = []
            grupos.append(indice[clave])
        indice[clave].append(p)
    return grupos


def listar_productos(cliente, categoria=CATEGORIA_POR_DEFECTO):
    """Una entrada por PRODUCTO (§5.2 del spec): sus colores (con o sin fotos),
    sus fotos generales y la representativa. Un producto sin ninguna foto en
    ningún lado no aparece (misma regla que listar())."""
    categoria = categoria_valida(categoria)
    info_cat = CATEGORIAS[categoria]
    idioma = idiomas.de_proyecto(cliente)
    salida = []
    for pid, propio, ruta, variantes, raiz in _recorrer(cliente, categoria):
        nombre_prod = _nombre_producto(pid, propio)
        colores = []
        for cid, var in variantes.items():
            ruta_c = os.path.join(ruta, cid)
            archivos = _imagenes_en(ruta_c)
            colores.append({"id": f"{pid}/{cid}", "color_id": cid, "nombre": var.get("nombre") or f"{nombre_prod} {cid.title()}",
                            "descripcion": var.get("descripcion") or "", "fuente_id": var.get("fuente_id"),
                            "url_compra": var.get("url_compra"), "disponible": var.get("disponible", True) is not False,
                            "imagenes": archivos, "referencias": [os.path.join(ruta_c, f) for f in archivos],
                            "representativa": os.path.join(ruta_c, archivos[0]) if archivos else None,
                            "sin_fotos": not archivos})
        tiene_colores = bool(variantes)
        n_fotos = sum(len(c["imagenes"]) for c in colores) + len(raiz)
        if not n_fotos:
            continue
        representativa = next((c["representativa"] for c in colores if c["representativa"]), None)
        if representativa is None:
            representativa = os.path.join(ruta, raiz[0])
        salida.append({
            "id": pid, "categoria": categoria, "etiqueta_base": info_cat["etiqueta"], "nombre": nombre_prod,
            "descripcion": propio.get("descripcion") or ("" if tiene_colores else DESCRIPCIONES.get(pid, "")),
            "tipo": prompt_swap.tipo_valido(propio.get("tipo")), **_mapa(propio, idioma),
            "regla": _regla_de(propio, categoria, idioma), "regla_propia": (propio.get("regla") or "").strip(),
            "tiene_colores": tiene_colores, "colores": colores,
            "fotos_generales": raiz if tiene_colores else [],
            "imagenes": [] if tiene_colores else raiz,
            "referencias": [] if tiene_colores else [os.path.join(ruta, f) for f in raiz],
            "representativa": representativa, "n_fotos": n_fotos, "n_colores": len(colores),
            "fuente": propio.get("fuente") if isinstance(propio.get("fuente"), dict) else {},
        })
    return salida


def claves_de(entrada):
    """Ids y nombres (casefold) con los que Crear, Sprints y los experimentos
    pueden referirse a un producto de listar_productos(): el pid, cada color y
    sus nombres. Sirve para contar usos y reunir faltantes sin repetir."""
    ids = {str(entrada["id"]).casefold()}
    nombres = {str(entrada.get("nombre") or "").casefold()} - {""}
    for c in entrada.get("colores") or []:
        ids.add(str(c["id"]).casefold())
        if c.get("nombre"):
            nombres.add(str(c["nombre"]).casefold())
    return {"ids": ids, "nombres": nombres}


def listar_todo(cliente):
    """Todas las categorías, en orden Productos → Personajes → Entornos."""
    todo = []
    for cat in CATEGORIAS:
        todo.extend(listar(cliente, cat))
    return todo


ANCHOS_MINIATURA = (320,)


def miniatura(ruta, ancho=320):
    """Ruta de una miniatura JPEG de `ancho` px de la foto `ruta`, hecha con
    Pillow y guardada en data/miniaturas/ con la fecha y el tamaño del
    original en el nombre (una foto reemplazada da otra miniatura; las
    huérfanas pesan KB). Las fotos del catálogo se sirven originales (2–6 MB
    cada una) y el selector de Crear las muestra a 80 px: 32 fotos eran 34 MB
    por carga (auditoría 2026-09-28). Si Pillow no puede abrir el archivo,
    devuelve `ruta` tal cual y se sirve el original."""
    st = os.stat(ruta)
    clave = hashlib.sha1(f"{ruta}|{int(st.st_mtime)}|{st.st_size}|{ancho}".encode()).hexdigest()
    carpeta = os.path.join(BASE_DIR, "data", "miniaturas")
    destino = os.path.join(carpeta, f"{clave}.jpg")
    if os.path.exists(destino):
        return destino
    try:
        from PIL import Image, ImageOps
        with Image.open(ruta) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((ancho, ancho * 2))
            os.makedirs(carpeta, exist_ok=True)
            tmp = f"{destino}.{os.getpid()}.parcial"
            im.save(tmp, "JPEG", quality=82, optimize=True)
            os.replace(tmp, destino)
    except Exception:  # noqa: BLE001 — no es una imagen que Pillow entienda: va el original
        return ruta
    return destino


def encontrar(cliente, producto_id, categoria=None):
    """Busca por id en una categoría, o en todas si categoria es None. Un id
    de producto con colores (que no es entrada por sí mismo) devuelve su
    primer color con fotos: así `campana.catalogo_id` o un `productos_ids`
    viejo siguen dando una referencia con foto."""
    if not producto_id:
        return None
    cats = [categoria_valida(categoria)] if categoria else list(CATEGORIAS)
    for cat in cats:
        lista = listar(cliente, cat)
        for p in lista:
            if p["id"] == producto_id:
                return p
        if "/" not in str(producto_id):
            for p in lista:
                if p["producto_id"] == producto_id and p["variante"]:
                    return p
    return None


def encontrar_producto(cliente, pid, categoria=CATEGORIA_POR_DEFECTO):
    """La entrada de listar_productos() del producto `pid` (o del producto de
    un id de color). None si no existe o no tiene fotos."""
    base = producto_base(pid)
    return next((p for p in listar_productos(cliente, categoria) if p["id"] == base), None)


def claves_de_producto(cliente, pid, categoria=CATEGORIA_POR_DEFECTO):
    """claves_de() del producto de `pid`; si no está en el catálogo, solo su id."""
    prod = encontrar_producto(cliente, pid, categoria)
    if prod is None:
        return {"ids": {producto_base(pid).casefold()}, "nombres": set()}
    return claves_de(prod)


def encontrar_por_id_o_nombre(cliente, valor, categoria=CATEGORIA_POR_DEFECTO):
    """Por id y, si no, por nombre visible exacto (de un color o del
    producto): `productos_ids` de Crear y Sprints guarda NOMBRES, no ids."""
    if not valor:
        return None
    p = encontrar(cliente, valor, categoria=categoria)
    if p:
        return p
    lista = listar(cliente, categoria)
    p = next((c for c in lista if c.get("nombre") == valor), None)
    if p:
        return p
    return next((c for c in lista if c.get("nombre_producto") == valor), None)


def carpeta_de(cliente, producto_id, categoria=CATEGORIA_POR_DEFECTO, variante=None):
    """Ruta en disco de un activo (o de uno de sus colores con `variante`),
    validada contra fugas de directorio: el id y el color llegan desde la
    URL o un formulario, así que un '../..' no puede salir de la carpeta. Un
    id que resuelve a la carpeta de la categoría misma («.», «./», «»,
    «x/..») tampoco vale: `eliminar` con él borraría el catálogo entero."""
    base = os.path.abspath(_carpeta(cliente, categoria))
    destino = os.path.abspath(os.path.join(base, producto_id))
    if not destino.startswith(base + os.sep):
        raise ValueError(f"id de producto inválido: {producto_id!r}")
    if variante:
        if os.sep in variante or "/" in variante:
            raise ValueError(f"color inválido: {variante!r}")
        ruta_color = os.path.abspath(os.path.join(destino, variante))
        if not ruta_color.startswith(destino + os.sep):
            raise ValueError(f"color inválido: {variante!r}")
        return ruta_color
    return destino


def existe(cliente, producto_id, categoria=CATEGORIA_POR_DEFECTO):
    """True si la carpeta del activo existe en disco (tenga o no fotos: un
    activo recién creado sin imágenes también "existe", aunque no aparezca
    en listar()). Un id inválido (fuga de directorio) es False, no error."""
    if not producto_id:
        return False
    try:
        return os.path.isdir(carpeta_de(cliente, producto_id, categoria))
    except ValueError:
        return False


def crear(cliente, nombre, descripcion="", tipo=None, zonas=None, categoria=CATEGORIA_POR_DEFECTO, regla="",
          producto_id=None):
    """Crea la carpeta del activo y guarda su metadata. Devuelve el id nuevo
    (el derivado de `nombre`, salvo que se pase `producto_id` explícito —
    lo usa el importador para desambiguar dos productos con el mismo
    nombre sin pisar el activo del primero). OJO: hasta que no tenga al
    menos una imagen no aparece en listar(), porque un activo sin fotos de
    referencia no sirve para generar nada."""
    categoria = categoria_valida(categoria)
    producto_id = producto_id or id_desde_nombre(nombre)
    carpeta = carpeta_de(cliente, producto_id, categoria)
    if os.path.isdir(carpeta):
        # nombre_categoria por variable local: gettext(CATEGORIAS[categoria]["nombre"])
        # directo hace que el extractor de Babel, al no ver un string literal,
        # grabe por error un msgid "nombre" (la clave del subscript).
        nombre_categoria = CATEGORIAS[categoria]["nombre"]
        raise ValueError(gettext("Ya existe un %(tipo)s con ese nombre (%(id)s).",
                                 tipo=gettext(nombre_categoria).lower(), id=producto_id))
    os.makedirs(carpeta, exist_ok=True)

    def _poner(meta):
        meta[producto_id] = {
            "nombre": nombre.strip(),
            "descripcion": (descripcion or "").strip(),
            "tipo": prompt_swap.tipo_valido(tipo),
            "zonas": mapa_corporal.normalizar(zonas) if CATEGORIAS[categoria]["con_mapa"] else [],
            "regla": (regla or "").strip(),
        }
        return meta
    modificar_meta(cliente, categoria, _poner)
    return producto_id


def actualizar(cliente, producto_id, nombre=None, descripcion=None, tipo=None, zonas=None, categoria=CATEGORIA_POR_DEFECTO, regla=None):
    """Cambia nombre/descripción SIN tocar la carpeta ni su id. El id se queda
    como está a propósito: es lo que guardan los swaps ya generados
    (swaps.json -> producto_id), y renombrar la carpeta los dejaría huérfanos."""
    categoria = categoria_valida(categoria)
    carpeta_de(cliente, producto_id, categoria)  # valida el id

    def _editar(meta):
        actual = meta.get(producto_id, {})
        if nombre is not None and nombre.strip():
            actual["nombre"] = nombre.strip()
        if descripcion is not None:
            actual["descripcion"] = descripcion.strip()
        if tipo is not None:
            actual["tipo"] = prompt_swap.tipo_valido(tipo)
        if zonas is not None:
            actual["zonas"] = mapa_corporal.normalizar(zonas)
        if regla is not None:
            actual["regla"] = regla.strip()
        meta[producto_id] = actual
        return meta
    modificar_meta(cliente, categoria, _editar)


def eliminar(cliente, producto_id, categoria=CATEGORIA_POR_DEFECTO):
    """Borra la carpeta del activo con todas sus imágenes, y su metadata.
    Irreversible: los archivos no van a una papelera."""
    import shutil

    categoria = categoria_valida(categoria)
    carpeta = carpeta_de(cliente, producto_id, categoria)
    if os.path.isdir(carpeta):
        shutil.rmtree(carpeta)

    def _quitar(meta):
        return meta if meta.pop(producto_id, None) is not None else None
    modificar_meta(cliente, categoria, _quitar)


def eliminar_imagen(cliente, producto_id, nombre_archivo, categoria=CATEGORIA_POR_DEFECTO, variante=None):
    """Borra UNA imagen. Devuelve (ok, mensaje). Nunca deja sin fotos a un
    color ni a un producto plano (desaparecerían de listar()); una foto
    general de un producto con colores sí puede ser la última."""
    categoria = categoria_valida(categoria)
    try:
        carpeta = carpeta_de(cliente, producto_id, categoria, variante=variante)
    except ValueError as e:
        return False, str(e)
    seguro = os.path.basename(nombre_archivo)
    ruta = os.path.join(carpeta, seguro)
    if seguro != nombre_archivo or not os.path.isfile(ruta):
        return False, gettext("No encontré esa imagen.")
    restantes = [f for f in _imagenes_en(carpeta) if f != seguro]
    es_general = not variante and categoria == "producto" and bool(_variantes_de(cargar_meta(cliente).get(producto_base(producto_id)) or {}))
    if not restantes and not es_general:
        return False, gettext("Es la única foto del producto. Si quieres quitarla, sube otra primero "
                              "o elimina el producto completo.")
    os.remove(ruta)
    return True, gettext("Imagen eliminada: %(nombre)s", nombre=seguro)


def nombre_libre(carpeta, nombre):
    """`a.jpg` -> `a.jpg`, o `a_2.jpg`, `a_3.jpg`… si ya existe en `carpeta`."""
    base, ext = os.path.splitext(nombre)
    candidato, n = nombre, 2
    while os.path.exists(os.path.join(carpeta, candidato)):
        candidato = f"{base}_{n}{ext}"
        n += 1
    return candidato


_CAMPOS_COLOR = ("nombre", "descripcion", "fuente_id", "url_compra", "disponible")


def _mover_raiz_a_color(carpeta, color_id):
    destino = os.path.join(carpeta, color_id)
    os.makedirs(destino, exist_ok=True)
    for f in _imagenes_en(carpeta):
        os.replace(os.path.join(carpeta, f), os.path.join(destino, nombre_libre(destino, f)))


def _id_color_desde_nombre(cliente, categoria, pid, nombre):
    """id_desde_nombre(nombre), pero si `nombre` sigue la convención "<nombre
    del producto> — <color>" (la de NOMBRES/el importador) se deriva solo del
    color: si no, cada color heredaría el nombre del producto en su propio id
    (p. ej. "original_sky_blue" en vez de "sky_blue"), distinto del criterio
    del resto de colores del mismo producto."""
    nombre_producto = (cargar_meta(cliente, categoria).get(pid) or {}).get("nombre") or ""
    prefijo = f"{nombre_producto} — "
    color_nombre = nombre[len(prefijo):] if nombre_producto and nombre.startswith(prefijo) else nombre
    return id_desde_nombre(color_nombre)


def agregar_color(cliente, pid, nombre, descripcion="", fuente_id=None, url_compra=None, disponible=True,
                  color_id=None, convertir_actual=None, conservar_raiz=False):
    """Crea el color `color_id` (derivado del nombre si no se pasa) del producto
    `pid`: entrada en `variantes` y subcarpeta. Un producto plano con fotos
    en la raíz exige `convertir_actual` (el nombre del color de esas fotos):
    pasan a ser su primer color — salvo con `conservar_raiz=True` (el
    importador, para un activo ya ligado a la tienda: esas fotos son de la
    tienda, no de un color), que las deja en la raíz y, como el producto ya
    tiene colores, pasan a ser fotos de ambiente. Devuelve el color_id.
    ValueError si el producto no existe, el color ya existe o hay fotos sin
    color dicho."""
    categoria = "producto"
    carpeta = carpeta_de(cliente, pid, categoria)
    if not os.path.isdir(carpeta):
        raise ValueError(gettext("No existe ese producto."))
    color_id = (color_id or _id_color_desde_nombre(cliente, categoria, pid, nombre)).strip()
    if not color_id or "/" in color_id or os.sep in color_id:
        raise ValueError(gettext("Nombre de color inválido."))
    carpeta_de(cliente, pid, categoria, variante=color_id)  # valida

    def _poner(meta):
        actual = meta.setdefault(pid, {})
        variantes = dict(_variantes_de(actual))
        if not variantes and _imagenes_en(carpeta) and not conservar_raiz:
            if not (convertir_actual or "").strip():
                raise ValueError(gettext("Este producto ya tiene fotos: dime de qué color son para poder agregar otro."))
            cid_actual = id_desde_nombre(convertir_actual)
            _mover_raiz_a_color(carpeta, cid_actual)
            variantes[cid_actual] = {"nombre": convertir_actual.strip(), "descripcion": "", "fuente_id": None,
                                     "url_compra": None, "disponible": True}
            if cid_actual == color_id:
                variantes[cid_actual].update({"nombre": nombre.strip(), "descripcion": (descripcion or "").strip(),
                                              "fuente_id": fuente_id, "url_compra": url_compra, "disponible": bool(disponible)})
                actual["variantes"] = variantes
                meta[pid] = actual
                return meta
        if color_id in variantes:
            raise ValueError(gettext("Ya hay un color con ese nombre (%(id)s).", id=color_id))
        variantes[color_id] = {"nombre": nombre.strip(), "descripcion": (descripcion or "").strip(), "fuente_id": fuente_id,
                               "url_compra": url_compra, "disponible": bool(disponible)}
        actual["variantes"] = variantes
        meta[pid] = actual
        return meta
    modificar_meta(cliente, categoria, _poner)
    os.makedirs(os.path.join(carpeta, color_id), exist_ok=True)
    return color_id


def actualizar_color(cliente, pid, color_id, **campos):
    """nombre, descripcion, fuente_id, url_compra, disponible de un color."""
    malos = set(campos) - set(_CAMPOS_COLOR)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    carpeta_de(cliente, pid, "producto", variante=color_id)

    def _editar(meta):
        variantes = _variantes_de(meta.get(pid) or {})
        if color_id not in variantes:
            raise ValueError(gettext("Ese color no existe."))
        for k, v in campos.items():
            if k in ("nombre", "descripcion"):
                v = (v or "").strip()
                if k == "nombre" and not v:
                    continue
            if k == "disponible":
                v = bool(v)
            variantes[color_id][k] = v
        meta[pid]["variantes"] = variantes
        return meta
    modificar_meta(cliente, "producto", _editar)


def quitar_color(cliente, pid, color_id):
    """Borra el color con sus fotos. Se niega si es el único color con fotos."""
    import shutil

    carpeta = carpeta_de(cliente, pid, "producto")
    ruta_color = carpeta_de(cliente, pid, "producto", variante=color_id)

    def _quitar(meta):
        actual = meta.get(pid) or {}
        variantes = dict(_variantes_de(actual))
        if color_id not in variantes:
            raise ValueError(gettext("Ese color no existe."))
        otros = [c for c in variantes if c != color_id and _imagenes_en(os.path.join(carpeta, c))]
        if _imagenes_en(ruta_color) and not otros:
            raise ValueError(gettext("Es el único color con fotos. Si quieres quitarlo, elimina el producto completo."))
        variantes.pop(color_id)
        actual["variantes"] = variantes
        meta[pid] = actual
        return meta
    modificar_meta(cliente, "producto", _quitar)
    shutil.rmtree(ruta_color, ignore_errors=True)


def mover_foto_a_color(cliente, pid, nombre_archivo, color_id):
    """Una foto general (raíz) pasa a ser referencia del color. Devuelve el
    nombre final (renumerado si chocaba)."""
    carpeta = carpeta_de(cliente, pid, "producto")
    destino = carpeta_de(cliente, pid, "producto", variante=color_id)
    if color_id not in _variantes_de(cargar_meta(cliente).get(pid) or {}):
        raise ValueError(gettext("Ese color no existe."))
    seguro = os.path.basename(nombre_archivo)
    origen = os.path.join(carpeta, seguro)
    if not os.path.isfile(origen) or not seguro.lower().endswith(IMAGE_EXTS):
        raise ValueError(gettext("No encontré esa imagen."))
    os.makedirs(destino, exist_ok=True)
    final = nombre_libre(destino, seguro)
    os.replace(origen, os.path.join(destino, final))
    return final

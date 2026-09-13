"""
Catálogo de productos para el flujo de "cambiar calzado": cada carpeta en
clientes/<cliente>/productos/ es UN producto (colorway), con varias fotos de
referencia (mismo producto, distintos ángulos/tomas) para darle a Nano Banana
la mejor fidelidad posible al generar. Al usuario solo se le muestra UNA foto
representativa por producto — las demás son material interno.
"""
import os
import re
import unicodedata

import _json_store
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
        "nombre": "Producto", "plural": "Productos", "carpeta": "productos", "meta": "productos.json",
        "etiqueta": "@Producto", "descripcion_ui": "Lo que vendes: calzado, ropa, decoración, comida, lo que sea.",
        "regla": ("Reprodúcelo idéntico a su referencia: misma forma, mismo color, misma textura y el mismo "
                  "logotipo o marca tal como aparece, en el mismo lugar. No inventes ni cambies letras, logos ni etiquetas."),
        "con_mapa": True,
    },
    "personaje": {
        "nombre": "Personaje", "plural": "Personajes", "carpeta": "personajes_catalogo", "meta": "personajes_catalogo.json",
        "etiqueta": "@Personaje", "descripcion_ui": "La cara de la marca: una persona real, un embajador o un personaje creado que debe verse igual siempre.",
        "regla": ("Es la MISMA persona/personaje en todas las tomas: misma cara, mismos rasgos, mismo pelo, misma "
                  "complexión y la misma ropa y accesorios que en las referencias. No cambies edad, género, piel ni estilo. "
                  "Manos y pies anatómicamente correctos."),
        "con_mapa": False,
    },
    "entorno": {
        "nombre": "Entorno", "plural": "Entornos", "carpeta": "entornos", "meta": "entornos.json",
        "etiqueta": "@Entorno", "descripcion_ui": "Lugares y escenas: tu tienda, un showroom, la sala donde va el espejo.",
        "regla": ("La escena ocurre en ESTE lugar: conserva paredes, piso, muebles, decoración y luz tal como se ven en las "
                  "referencias. El producto y las personas se integran ahí; no reconstruyas ni redecores el espacio."),
        "con_mapa": False,
    },
}
CATEGORIA_POR_DEFECTO = "producto"


def categoria_valida(cat):
    return cat if cat in CATEGORIAS else CATEGORIA_POR_DEFECTO


def _carpeta(cliente, categoria=CATEGORIA_POR_DEFECTO):
    return os.path.join(BASE_DIR, "clientes", cliente, CATEGORIAS[categoria_valida(categoria)]["carpeta"])


def _meta_path(cliente, categoria=CATEGORIA_POR_DEFECTO):
    return os.path.join(BASE_DIR, "clientes", cliente, CATEGORIAS[categoria_valida(categoria)]["meta"])


def cargar_meta(cliente, categoria=CATEGORIA_POR_DEFECTO):
    """{id: {"nombre":..., "descripcion":...}} — lo que el usuario editó desde el
    dashboard. Es una capa ENCIMA de NOMBRES/DESCRIPCIONES, no un reemplazo."""
    return _json_store.cargar(_meta_path(cliente, categoria), {})


def guardar_meta(cliente, meta, categoria=CATEGORIA_POR_DEFECTO):
    _json_store.guardar(_meta_path(cliente, categoria), meta)


def id_desde_nombre(nombre):
    """El id es también el nombre de la carpeta en disco, así que tiene que ser
    seguro: sin acentos, sin espacios, sin nada que pueda escaparse del
    directorio de productos."""
    limpio = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-zA-Z0-9]+", "_", limpio).strip("_").lower()
    return limpio or "producto"


def listar(cliente, categoria=CATEGORIA_POR_DEFECTO):
    categoria = categoria_valida(categoria)
    carpeta = _carpeta(cliente, categoria)
    if not os.path.isdir(carpeta):
        return []
    meta = cargar_meta(cliente, categoria)
    info_cat = CATEGORIAS[categoria]
    productos = []
    public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    for nombre_carpeta in sorted(os.listdir(carpeta)):
        subcarpeta = os.path.join(carpeta, nombre_carpeta)
        if not os.path.isdir(subcarpeta):
            continue
        archivos = sorted(f for f in os.listdir(subcarpeta) if f.lower().endswith(IMAGE_EXTS))
        if not archivos:
            continue
        propio = meta.get(nombre_carpeta, {})
        productos.append({
            "id": nombre_carpeta,
            "categoria": categoria,
            "etiqueta_base": info_cat["etiqueta"],
            # Regla de consistencia: la de la categoría más lo que la persona anotó
            # (ej. "siempre lleva la gorra roja") — es lo que va al prompt.
            "regla": (info_cat["regla"] + (" " + propio["regla"].strip() if propio.get("regla") else "")).strip(),
            "regla_propia": (propio.get("regla") or "").strip(),
            "nombre": propio.get("nombre") or NOMBRES.get(nombre_carpeta, nombre_carpeta.replace("_", " ").title()),
            "descripcion": propio.get("descripcion") or DESCRIPCIONES.get(nombre_carpeta, ""),
            # El tipo decide QUÉ prompt se le manda al modelo (un calzado va en
            # los pies, una cobija se drapea). Los productos que ya existían son
            # todos calzado, así que ese es el default y no hay que migrar nada.
            "tipo": prompt_swap.tipo_valido(propio.get("tipo")),
            # Zonas del cuerpo que ocupa el producto (mapa corporal). Vacío =
            # no va sobre una persona (una cobija, un objeto de escena).
            "zonas": mapa_corporal.normalizar(propio.get("zonas")),
            "mapa_texto": mapa_corporal.describir(propio.get("zonas")),
            "mapa_etiqueta": (lambda pid: mapa_corporal.ETIQUETAS_PRESETS.get(pid))(
                mapa_corporal.preset_de(propio.get("zonas"))),
            "referencias": [os.path.join(subcarpeta, f) for f in archivos],
            # Nombres de archivo sueltos: la UI de gestión necesita poder
            # referirse a una imagen concreta (para borrarla o mostrarla) sin
            # exponer rutas absolutas del disco en una URL.
            "imagenes": archivos,
            "representativa": os.path.join(subcarpeta, archivos[0]),
            "representativa_url": f"{public_base}/clientes/{cliente}/{info_cat['carpeta']}/{nombre_carpeta}/{archivos[0]}" if public_base else None,
        })
    return productos


def listar_todo(cliente):
    """Todas las categorías, en orden Productos → Personajes → Entornos."""
    todo = []
    for cat in CATEGORIAS:
        todo.extend(listar(cliente, cat))
    return todo


def encontrar(cliente, producto_id, categoria=None):
    """Busca por id en una categoría, o en todas si categoria es None."""
    cats = [categoria_valida(categoria)] if categoria else list(CATEGORIAS)
    for cat in cats:
        for p in listar(cliente, cat):
            if p["id"] == producto_id:
                return p
    return None


def carpeta_de(cliente, producto_id, categoria=CATEGORIA_POR_DEFECTO):
    """Ruta en disco de un producto, validada contra fugas de directorio: el id
    llega desde la URL, así que un '../..' no puede terminar borrando otra cosa."""
    base = os.path.abspath(_carpeta(cliente, categoria))
    destino = os.path.abspath(os.path.join(base, producto_id))
    if destino != base and not destino.startswith(base + os.sep):
        raise ValueError(f"id de producto inválido: {producto_id!r}")
    return destino


def crear(cliente, nombre, descripcion="", tipo=None, zonas=None, categoria=CATEGORIA_POR_DEFECTO, regla=""):
    """Crea la carpeta del activo y guarda su metadata. Devuelve el id nuevo.
    OJO: hasta que no tenga al menos una imagen no aparece en listar(), porque
    un activo sin fotos de referencia no sirve para generar nada."""
    categoria = categoria_valida(categoria)
    producto_id = id_desde_nombre(nombre)
    carpeta = carpeta_de(cliente, producto_id, categoria)
    if os.path.isdir(carpeta):
        raise ValueError(f"Ya existe un {CATEGORIAS[categoria]['nombre'].lower()} con ese nombre ({producto_id}).")
    os.makedirs(carpeta, exist_ok=True)
    meta = cargar_meta(cliente, categoria)
    meta[producto_id] = {
        "nombre": nombre.strip(),
        "descripcion": (descripcion or "").strip(),
        "tipo": prompt_swap.tipo_valido(tipo),
        "zonas": mapa_corporal.normalizar(zonas) if CATEGORIAS[categoria]["con_mapa"] else [],
        "regla": (regla or "").strip(),
    }
    guardar_meta(cliente, meta, categoria)
    return producto_id


def actualizar(cliente, producto_id, nombre=None, descripcion=None, tipo=None, zonas=None, categoria=CATEGORIA_POR_DEFECTO, regla=None):
    """Cambia nombre/descripción SIN tocar la carpeta ni su id. El id se queda
    como está a propósito: es lo que guardan los swaps ya generados
    (swaps.json -> producto_id), y renombrar la carpeta los dejaría huérfanos."""
    categoria = categoria_valida(categoria)
    carpeta_de(cliente, producto_id, categoria)  # valida el id
    meta = cargar_meta(cliente, categoria)
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
    guardar_meta(cliente, meta, categoria)


def eliminar(cliente, producto_id, categoria=CATEGORIA_POR_DEFECTO):
    """Borra la carpeta del activo con todas sus imágenes, y su metadata.
    Irreversible: los archivos no van a una papelera."""
    import shutil

    categoria = categoria_valida(categoria)
    carpeta = carpeta_de(cliente, producto_id, categoria)
    if os.path.isdir(carpeta):
        shutil.rmtree(carpeta)
    meta = cargar_meta(cliente, categoria)
    if meta.pop(producto_id, None) is not None:
        guardar_meta(cliente, meta, categoria)


def eliminar_imagen(cliente, producto_id, nombre_archivo, categoria=CATEGORIA_POR_DEFECTO):
    """Borra UNA imagen de referencia. Devuelve (ok, mensaje). Nunca deja al
    activo sin fotos: sin ninguna referencia desaparecería de listar() y
    quedaría una carpeta fantasma imposible de gestionar desde la UI."""
    carpeta = carpeta_de(cliente, producto_id, categoria_valida(categoria))
    seguro = os.path.basename(nombre_archivo)
    ruta = os.path.join(carpeta, seguro)
    if not os.path.isfile(ruta):
        return False, "No encontré esa imagen."
    restantes = [f for f in os.listdir(carpeta) if f.lower().endswith(IMAGE_EXTS) and f != seguro]
    if not restantes:
        return False, ("Es la única foto del producto. Si quieres quitarla, sube otra primero "
                       "o elimina el producto completo.")
    os.remove(ruta)
    return True, f"Imagen eliminada: {seguro}"

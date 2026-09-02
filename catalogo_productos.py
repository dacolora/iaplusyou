"""
Catálogo de productos para el flujo de "cambiar calzado": cada carpeta en
clientes/<cliente>/productos/ es UN producto (colorway), con varias fotos de
referencia (mismo producto, distintos ángulos/tomas) para darle a Nano Banana
la mejor fidelidad posible al generar. Al usuario solo se le muestra UNA foto
representativa por producto — las demás son material interno.
"""
import os

BASE_DIR = os.path.dirname(__file__)
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

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


def _carpeta(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "productos")


def listar(cliente):
    carpeta = _carpeta(cliente)
    if not os.path.isdir(carpeta):
        return []
    productos = []
    public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    for nombre_carpeta in sorted(os.listdir(carpeta)):
        subcarpeta = os.path.join(carpeta, nombre_carpeta)
        if not os.path.isdir(subcarpeta):
            continue
        archivos = sorted(f for f in os.listdir(subcarpeta) if f.lower().endswith(IMAGE_EXTS))
        if not archivos:
            continue
        productos.append({
            "id": nombre_carpeta,
            "nombre": NOMBRES.get(nombre_carpeta, nombre_carpeta.replace("_", " ").title()),
            "descripcion": DESCRIPCIONES.get(nombre_carpeta, ""),
            "referencias": [os.path.join(subcarpeta, f) for f in archivos],
            "representativa": os.path.join(subcarpeta, archivos[0]),
            "representativa_url": f"{public_base}/clientes/{cliente}/productos/{nombre_carpeta}/{archivos[0]}" if public_base else None,
        })
    return productos


def encontrar(cliente, producto_id):
    for p in listar(cliente):
        if p["id"] == producto_id:
            return p
    return None

"""Las métricas que faltaban en Rendimiento (spec 2026-10-13-rendimiento-metricas-que-faltaban): productos con gasto y
ROAS, los mejores para iterar, los que mejor convierten y las mejores imágenes y videos.

Todo sale de los anuncios que el panel ya evaluó (`triple_whale.panel.contexto()["ev"]["anuncios"]`: país, periodo y
canal de la pestaña, solo canales con gasto por R9) más dos lecturas fijas en `armar`: el tipo de cada anuncio
(`tw_creativo`) y el Catálogo. No cobra ni llama a nadie. Daniel (2026-10-13): «necesito que esas métricas que faltan
las tengamos desde Triple Whale»."""
import re
from urllib.parse import unquote, urlsplit

from idiomas import N_
from triple_whale.datos import CANAL_META

PEDIDOS_MIN_ITERAR = 10            # «real purchase volume»: un ROAS de 1 o 2 compras no es una base segura
SESIONES_MIN_CONVERSION = 100
PEDIDOS_MIN_CONVERSION = 3
MAX_ITERAR = 8
MAX_CONVERSION = 8
MAX_POR_TIPO = 6
MAX_PRODUCTOS = 10
LARGO_MIN_NOMBRE = 5               # un nombre de producto más corto se encontraría por casualidad en cualquier anuncio

# El ad_type de Triple Whale (tw_creativo.tipo) en palabras; se traducen al pintar (`| traducir`).
TIPOS = {"image": N_("Imagen"), "carousel": N_("Carrusel"), "video": N_("Video"), "dynamic": N_("Dinámico")}
OTROS = "otros"

_HANDLE = re.compile(r"/products/([^/?#]+)")
_SUFIJO_TIENDA = re.compile(r"-\d+$")
_NO_ALFANUM = re.compile(r"[^a-z0-9]")


def _norm(texto):
    return _NO_ALFANUM.sub("", (texto or "").lower())


def _div(a, b):
    return a / b if b else None


def handle(url):
    """El handle de `/products/<handle>` en minúsculas y sin el `-<dígitos>` final que Shopify agrega cuando el mismo
    producto existe en otra tienda (`happyflops-cozy-1` → `happyflops-cozy`); None sin página de producto. Al
    Catálogo se le aplica lo mismo, así que un handle que de verdad termina en número sigue emparejando."""
    try:
        ruta = urlsplit(url or "").path
    except ValueError:
        return None
    m = _HANDLE.search(ruta or "")
    if not m:
        return None
    return _SUFIJO_TIENDA.sub("", unquote(m.group(1)).strip().lower()) or None


def catalogo_indice(productos):
    """El Catálogo listo para ubicar anuncios: {"handles": {handle normalizado: producto}, "nombres": [(nombre
    normalizado, producto)] del más largo al más corto}."""
    handles, nombres = {}, []
    for p in productos or []:
        h = handle(p.get("url_compra"))
        if h:
            handles.setdefault(_norm(h), p)
        n = _norm(p.get("nombre"))
        if len(n) >= LARGO_MIN_NOMBRE:
            nombres.append((n, p))
    nombres.sort(key=lambda x: (-len(x[0]), x[1].get("id") or 0))
    return {"handles": handles, "nombres": nombres}


def producto_de(anuncio, indice):
    """{"clave", "nombre", "producto_id"} del anuncio, en este orden (spec §4.1): su página de producto en el
    Catálogo; el nombre de un producto del Catálogo dentro del nombre del anuncio (gana el más largo); el handle tal
    cual; «Otros» (`clave == OTROS`, nombre None)."""
    h = handle(anuncio.get("destino_url"))
    p = indice["handles"].get(_norm(h)) if h else None
    if p is None:
        nombre = _norm(anuncio.get("nombre"))
        p = next((prod for n, prod in indice["nombres"] if n in nombre), None) if nombre else None
    if p is not None:
        return {"clave": f"p{p['id']}", "nombre": p["nombre"], "producto_id": p["id"]}
    if h:
        return {"clave": f"h:{_norm(h)}", "nombre": h, "producto_id": None}
    return {"clave": OTROS, "nombre": None, "producto_id": None}


def tipo_de(anuncio, tipos):
    """{"tipo", "etiqueta", "grupo"} (spec §4.4 y §9). `tipos`: {(canal, ad_id): ad_type de tw_creativo}. Grupo:
    «video» si Triple Whale dice video; «imagen» si dice imagen o carrusel; si no dice ninguno, «video» con vistas de
    3 s, «imagen» en Meta (Meta informa las vistas de sus videos) y None en otro canal: un anuncio de búsqueda de Google
    o uno de Snapchat sin vistas en la copia no es una imagen, no se sabe (datos reales de Noruega, 2026-10-13). Sin
    grupo, la etiqueta es None y el anuncio no entra en «Mejores imágenes» ni en «Mejores videos»."""
    tipo = (tipos.get((anuncio["canal"], anuncio["ad_id"])) or "").lower() or None
    if tipo == "video":
        grupo = "video"
    elif tipo in ("image", "carousel"):
        grupo = "imagen"
    elif anuncio["m"].get("es_video"):
        grupo = "video"
    else:
        grupo = "imagen" if anuncio["canal"] == CANAL_META else None
    etiqueta = TIPOS.get(tipo) or {"video": TIPOS["video"], "imagen": TIPOS["image"]}.get(grupo)
    return {"tipo": tipo, "etiqueta": etiqueta, "grupo": grupo}


def _fila(a, indice, tipos):
    return {"canal": a["canal"], "ad_id": a["ad_id"], "nombre": a["nombre"], "m": a["m"],
            "producto": producto_de(a, indice), **tipo_de(a, tipos),
            "creatv": a.get("creatv"), "video_url": a.get("video_url")}


def _por_ventas(f):
    return (-f["m"]["ingresos"], f["canal"], f["ad_id"])


def _productos(filas):
    grupos = {}
    for f in filas:
        p = f["producto"]
        g = grupos.setdefault(p["clave"], {"clave": p["clave"], "nombre": p["nombre"], "producto_id": p["producto_id"],
                                            "gasto": 0.0, "ingresos": 0.0, "pedidos": 0.0, "anuncios": 0,
                                            "es_otros": p["clave"] == OTROS})
        g["gasto"] += f["m"]["gasto"]
        g["ingresos"] += f["m"]["ingresos"]
        g["pedidos"] += f["m"]["pedidos"]
        g["anuncios"] += 1
    otros = grupos.pop(OTROS, None)
    lista = sorted(grupos.values(), key=lambda g: (-g["ingresos"], -g["gasto"], g["clave"]))
    sobra = lista[MAX_PRODUCTOS:]
    lista = lista[:MAX_PRODUCTOS]
    if sobra and otros is None:
        otros = {"clave": OTROS, "nombre": None, "producto_id": None, "gasto": 0.0, "ingresos": 0.0, "pedidos": 0.0,
                 "anuncios": 0, "es_otros": True}
    for g in sobra:
        for k in ("gasto", "ingresos", "pedidos", "anuncios"):
            otros[k] += g[k]
    if otros:
        lista.append(otros)
    for g in lista:
        g["roas"] = _div(g["ingresos"], g["gasto"])
    return lista


def resumir(anuncios, roas_cuenta, indice, tipos):
    """Las cinco piezas de la pantalla, sin tocar la base: «iterar», «conversion», «imagenes», «videos» (filas de
    `_fila`) y «productos» (con «Otros» al final; la suma de su gasto es la de todos los anuncios)."""
    filas = [_fila(a, indice, tipos) for a in anuncios or []]
    # Las listas y las tarjetas son de anuncios con gasto: Google Ads trae filas como «(not set)» o «sag_organic» con
    # ventas atribuidas y gasto 0, que no son anuncios (§9). «Productos» sí las cuenta: su gasto suma el del tile.
    pagados = [f for f in filas if f["m"]["gasto"] > 0]
    iterar = sorted((f for f in pagados if roas_cuenta and f["m"]["pedidos"] >= PEDIDOS_MIN_ITERAR
                     and (f["m"]["roas"] or 0) >= roas_cuenta), key=_por_ventas)[:MAX_ITERAR]
    conversion = sorted((f for f in pagados if f["m"]["sesiones"] >= SESIONES_MIN_CONVERSION
                         and f["m"]["pedidos"] >= PEDIDOS_MIN_CONVERSION and f["m"]["cv_sesion"] is not None),
                        key=lambda f: (-f["m"]["cv_sesion"], -f["m"]["pedidos"], f["canal"], f["ad_id"]))
    por_grupo = {"imagen": [], "video": []}
    for f in sorted((f for f in pagados if f["m"]["pedidos"] > 0 and f["grupo"]), key=_por_ventas):
        if len(por_grupo[f["grupo"]]) < MAX_POR_TIPO:
            por_grupo[f["grupo"]].append(f)
    return {"iterar": iterar, "conversion": conversion[:MAX_CONVERSION], "imagenes": por_grupo["imagen"],
            "videos": por_grupo["video"], "productos": _productos(filas), "roas_cuenta": roas_cuenta,
            "minimos": {"pedidos_iterar": PEDIDOS_MIN_ITERAR, "sesiones": SESIONES_MIN_CONVERSION,
                        "pedidos_conversion": PEDIDOS_MIN_CONVERSION}}


def armar(cliente, tw):
    """Lo que pinta la pantalla (`r.destacados`) desde el contexto de Triple Whale del panel (`tw`, de
    `triple_whale.panel.contexto`): `resumir` + `moneda` y, en cada tarjeta de «imagenes»/«videos», su `medio` (el de
    la galería: solo hosts permitidos o lo de una pieza de Creatv en R2). Lecturas fijas: tipos, Catálogo y los
    creativos de las ≤ 12 tarjetas; sin anuncios, ninguna."""
    import tiendas
    from triple_whale import datos
    from triple_whale import panel as tw_panel
    ev = tw["ev"]
    anuncios = ev["anuncios"]
    tipos = datos.tipos_creativo(cliente) if anuncios else {}
    catalogo = tiendas.productos(cliente) if anuncios else []
    r = resumir(anuncios, ev["cuenta"]["m"].get("roas"), catalogo_indice(catalogo), tipos)
    tarjetas = r["imagenes"] + r["videos"]
    creativos = datos.creativos(cliente, [(f["canal"], f["ad_id"]) for f in tarjetas])
    for f in tarjetas:
        f["medio"] = tw_panel.medio_tarjeta({"canal": f["canal"], "video_url": f["video_url"], "creatv": f["creatv"],
                                             "creativo": creativos.get((f["canal"], f["ad_id"]))})
    r["moneda"] = tw["moneda"]
    return r

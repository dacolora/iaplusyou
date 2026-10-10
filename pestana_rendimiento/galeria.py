"""«04 Tus anuncios» de la pestaña Rendimiento: UNA galería con los anuncios de las dos fuentes y UN lote (Rendimiento
E2, tarea 4, 2026-10-10; spec 2026-10-09 §5 y enmienda A1, que dejó la unión para E2; cierra PND-196).

Por qué existe: en E1 «Tus anuncios» era la galería de Triple Whale tal cual y, debajo, tarjetas de los anuncios cuya
fuente es Meta, sin IA (R14). Con «Cómo mejorarlo» para Meta (E2, tareas 1 a 3) las dos son la misma tarjeta con el
mismo flujo pagado, así que se juntan: una lista, un orden, un filtro y un botón «Analizar los N que más gastaron».
Lo que cobra NO se reescribe: cada anuncio se pide con `triple_whale/pedidos.py` y el alcance de SU fuente
(`triple_whale.panel.alcance` o `pestana_rendimiento.alcance_meta.alcance`, la misma forma), con todas sus garantías
(precio a la vista, Cobros antes de crear filas, `max_intentos=1`, nunca pagar dos veces lo mismo, una fila colgada no
bloquea). Este módulo solo decide el orden, la página, el lote y lo que pinta cada tarjeta.

Reglas, cada una con su motivo:

1. Orden: por gasto en USD, de mayor a menor (PND-196: con cuentas en monedas distintas, el gasto nominal no ordena
   por valor). Cada anuncio en su moneda (Triple Whale: la del proyecto; Meta: la de su cuenta) convertida con la tasa
   del ÚLTIMO día del periodo de su alcance (`meta_rendimiento.tasas.usd`, una lectura por moneda). Un anuncio sin
   tasa (o sin moneda conocida) va al final, en su orden nominal: jamás una tasa inventada (R6).
2. Una página = `triple_whale.panel.POR_PAGINA` (12) tarjetas mezcladas; `panel.enriquecer` corre UNA vez por fuente con
   las tarjetas de la página, y los análisis, las tareas vivas y los creativos se leen una vez para las dos: un número
   fijo de consultas, nunca una por tarjeta (auditoría del 2026-09-28: 1 158 consultas por página).
3. El lote: los `N_LOTE` de más gasto en USD, entre las dos fuentes, a los que su tarjeta les ofrece el botón principal
   (`panel.elegir_analisis`, con el alcance de su fuente); su precio es la suma de los de sus tarjetas (A5), y con uno
   desconocido, «precio no disponible». Cada clave es "<fuente>:<canal>:<ad_id>". Al cobrar, las confirmadas se
   recortan a `N_LOTE` ENTRE LAS DOS fuentes antes de separarlas (si no, cada fuente cobraría hasta N, B6) y cada fuente
   cobra solo lo confirmado Y aún elegible con su `pedidos.pedir_lote`; la primera sin saldo para todo.
4. Tarjeta de Meta: la misma macro que la de Triple Whale (`_tw_galeria.html`). Su medio: lo de `panel.medio_tarjeta`
   (una pieza de Creatv en R2); si no, la imagen que un análisis listo copió a R2 (`foto.creativo.imagen_url`); si no,
   la miniatura de Meta solo si su host es de Meta (`meta_rendimiento.datos.miniatura_valida`, al pintar y no solo al
   guardar: PND-220). Sin «Guardar en Referentes» (PND-222) y sin «Meta reporta» (R12 es de Triple Whale).
"""
import gastos
import triple_whale
from cobros import SaldoInsuficiente
from meta_rendimiento import datos as meta_datos
from meta_rendimiento import tasas
from tareas import triple_whale as tareas_tw
from triple_whale import datos as twdatos
from triple_whale import panel as tw_panel
from triple_whale import pedidos

TW, META = "tw", "meta"
FUENTES = (TW, META)


def clave(a):
    """La clave del lote de un anuncio ya marcado (`_marcar`): "<fuente>:<canal>:<ad_id>"."""
    return f"{a['fuente']}:{a['canal']}:{a['ad_id']}"


def _tasa(moneda, fecha, cache):
    """USD por unidad de `moneda` el día `fecha` (una lectura por moneda y día); None sin moneda o sin tasa."""
    moneda = (moneda or "").upper()
    if not moneda or not fecha:
        return None
    k = (moneda, str(fecha)[:10])
    if k not in cache:
        cache[k] = tasas.usd(moneda, k[1])
    return cache[k]


def _moneda(fuente, alc, a):
    """La moneda de las cifras de un anuncio: Meta, la de su cuenta; Triple Whale, la del proyecto en Triple Whale."""
    return a.get("moneda") if fuente == META else (alc.get("config") or {}).get("moneda")


def _marcar(a, fuente, alc, tasa=None):
    """Deja en el anuncio su `fuente`, su `moneda` y su `gasto_usd` (None sin tasa: la tarjeta sola no lo calcula)."""
    a["fuente"] = fuente
    a["moneda"] = _moneda(fuente, alc, a)
    a["gasto_usd"] = a["m"]["gasto"] * tasa if tasa is not None else None
    return a


def _orden(a):
    """Regla 1: primero los que tienen gasto en USD, de mayor a menor; al final los sin tasa, por su gasto nominal."""
    usd = a.get("gasto_usd")
    if usd is None:
        return (1, -a["m"]["gasto"], a["fuente"], a["canal"], a["ad_id"])
    return (0, -usd, a["fuente"], a["canal"], a["ad_id"])


def medio_meta(a):
    """Regla 4: lo que muestra la tarjeta de un anuncio de Meta (después de `panel.enriquecer`)."""
    if a.get("medio"):
        return a["medio"]
    fila = a.get("analisis") or {}
    if fila.get("estado") == "lista":
        imagen = ((fila.get("foto") or {}).get("creativo") or {}).get("imagen_url")
        if triple_whale.medio_permitido(imagen):
            return {"imagen": imagen}
    mini = a.get("miniatura_url")
    # `miniatura`: la de Meta llega chica (64 px): la tarjeta la muestra sin agrandarla (`.tw-medio-miniatura`).
    return {"imagen": mini, "miniatura": True} if meta_datos.miniatura_valida(mini) else {}


def _elegible(cliente, a, por_clave, vivos, alc):
    job = tareas_tw.job_id_analisis(cliente, a["canal"], a["ad_id"])
    return tw_panel.elegir_analisis(a, por_clave.get((a["canal"], a["ad_id"])), alc, vivo=job in vivos)["ofrecer"]


def armar(cliente, alc_tw, alc_meta, veredicto="", pagina=1):
    """Una página de la galería y su lote, con la forma de `triple_whale.panel.galeria` (`tarjetas`, `pagina`,
    `hay_mas`, `total`, `veredicto`, `conteo_filtros`, `lote` {n, claves, elegibles, precio}) más `n_anuncios` (todos
    los anuncios de las dos fuentes, también los de muy pocos datos) y `hay_meta`. Cada tarjeta lleva `fuente`
    ("tw" | "meta"), `moneda` y `gasto_usd`. `alc_tw` / `alc_meta`: el alcance de cada fuente, o None."""
    veredicto = veredicto if veredicto in tw_panel.FILTROS_GALERIA else ""
    try:
        pagina = max(1, int(pagina or 1))
    except (TypeError, ValueError):
        pagina = 1
    fuentes = [(f, alc) for f, alc in ((TW, alc_tw), (META, alc_meta)) if alc]
    alcance_de = dict(fuentes)
    cache, todos = {}, []
    for fuente, alc in fuentes:
        for a in alc["ev"]["anuncios"]:
            todos.append(_marcar(a, fuente, alc, _tasa(_moneda(fuente, alc, a), alc.get("hasta"), cache)))
    lista = sorted(tw_panel.filtrar(todos, veredicto), key=_orden)
    tarjetas = lista[(pagina - 1) * tw_panel.POR_PAGINA: pagina * tw_panel.POR_PAGINA]
    candidatos = [a for a in lista if a["veredicto"] != "sin_datos"]
    por_clave = twdatos.analisis_de_anuncios(cliente, list({(a["canal"], a["ad_id"]) for a in tarjetas + candidatos}))
    vivos = tareas_tw.analisis_vivos(cliente)
    elegibles = [a for a in candidatos if _elegible(cliente, a, por_clave, vivos, alcance_de[a["fuente"]])]
    lote = elegibles[:tw_panel.N_LOTE]
    # Una lectura de creativos para la página Y el lote: el precio del lote es la suma de los de sus tarjetas (A5).
    creativos = twdatos.creativos(cliente, [(a["canal"], a["ad_id"]) for a in tarjetas + lote])
    for fuente, alc in fuentes:                    # regla 2: una vez por fuente, con sus tarjetas de la página
        suyas = [a for a in tarjetas if a["fuente"] == fuente]
        tw_panel.enriquecer(cliente, suyas, alc["ev"], por_clave, alc, vivos=vivos, creativos=creativos)
        if fuente == META:
            for a in suyas:
                a["medio"] = medio_meta(a)
    precios = [tw_panel.precio_analisis(creativos.get((a["canal"], a["ad_id"])))["usd"] for a in lote]
    # Sin precio de alguno, el total es «precio no disponible», nunca «US$ 0» (regla 1 del repo).
    total = None if any(p is None for p in precios) else sum(precios)
    return {"tarjetas": tarjetas, "pagina": pagina, "hay_mas": pagina * tw_panel.POR_PAGINA < len(lista),
            "total": len(lista), "veredicto": veredicto, "n_anuncios": len(todos),
            "hay_meta": any(a["fuente"] == META for a in todos),
            "conteo_filtros": {f: len(tw_panel.filtrar(todos, f)) for f in tw_panel.FILTROS_GALERIA},
            # `claves`: las que muestra el botón (hasta N_LOTE); `elegibles`: todas las que hoy se podrían analizar
            # (la ruta cobra lo confirmado Y aún elegible, revisión de la tarea 8 de tw-tarjetas).
            "lote": {"n": len(lote), "claves": [clave(a) for a in lote], "elegibles": {clave(a) for a in elegibles},
                     "precio": gastos._estimado(total, "análisis por anuncio")}}


def tarjeta(cliente, fuente, alc, a):
    """Una tarjeta sola (repintarla, o la respuesta del pedido por fetch): el anuncio `a` de `alc` (de esa `fuente`)
    con lo mismo que le pone `armar`, salvo `gasto_usd` (no se muestra y costaría leer una tasa)."""
    _marcar(a, fuente, alc)
    tw_panel.enriquecer(cliente, [a], alc["ev"], twdatos.analisis_de_anuncios(cliente, [(a["canal"], a["ad_id"])]),
                        alcance=alc)
    if fuente == META:
        a["medio"] = medio_meta(a)
    return a


def claves_confirmadas(valores, tope=None):
    """[(fuente, canal, ad_id)] de los `clave=<fuente>:<canal>:<ad_id>` del formulario del lote: la fuente es "tw" o
    "meta", cada `<canal>:<ad_id>` se valida con `pedidos.claves_confirmadas` (la misma regla del lote de siempre), no se
    repite ninguna y se para en `tope` claves válidas ENTRE LAS DOS fuentes (por defecto `N_LOTE`; regla 3, B6)."""
    tope = tw_panel.N_LOTE if tope is None else tope
    claves, vistas = [], set()
    for v in valores:
        if len(claves) >= tope:
            break
        fuente, dos_puntos, resto = str(v or "").partition(":")
        par = pedidos.claves_confirmadas([resto], tope=1) if dos_puntos and fuente in FUENTES else []
        if par and (fuente, *par[0]) not in vistas:
            vistas.add((fuente, *par[0]))
            claves.append((fuente, *par[0]))
    return claves


def pedir_lote(cliente, alcances, claves, usuario, veredicto=""):
    """«Analizar los N que más gastaron» con las dos fuentes: (encolados, fallos). `alcances` = {"tw": …, "meta": …}
    (None si el alcance no tiene esa fuente); `claves`, las confirmadas (`claves_confirmadas`: ya recortadas a N_LOTE
    entre las dos). Cada fuente cobra con SU alcance y su `pedidos.pedir_lote` (confirmadas ∩ aún elegibles con el
    filtro `veredicto`), en el orden de su primera clave: la del anuncio de más gasto en USD va primero. Sin saldo,
    para ahí (la otra fuente no se pide) y re-lanza `SaldoInsuficiente` con `.lote` = lo de las dos."""
    n = fallos = 0
    for fuente in dict.fromkeys(f for f, _, _ in claves):
        alc = alcances.get(fuente)
        if not alc:
            continue
        suyas = [(c, ad) for f, c, ad in claves if f == fuente]
        try:
            hechos, fallidos = pedidos.pedir_lote(cliente, alc, suyas, usuario, veredicto=veredicto)
        except SaldoInsuficiente as e:
            hechos, fallidos = getattr(e, "lote", (0, 0))
            e.lote = (n + hechos, fallos + fallidos)
            raise
        n += hechos
        fallos += fallidos
    return n, fallos

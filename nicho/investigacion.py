"""
Máquina de estados de la investigación automática del nicho (spec Parte 3
§1, §2.4, §5, §6): funciones puras sobre el diccionario
`estudio.extra.investigacion` (quien persiste es `nicho.datos`), el estimado
que se aprueba con un clic, y las dos llamadas a Claude (consultas y
selección) por `nicho.avatares._llamar` (modelo del proyecto, tokens reales).

Una investigación tiene un `orden` de pasos derivado de las plataformas y
redes elegidas: consultas → buscar:<plataforma>… → seleccionar →
resenas:<plataforma>… → redes:<red>… → generar. Cada paso vive en
`pasos[paso] = {"estado": pendiente|en_curso|hecho|vacio|saltado|error, …}`;
`gastado_usd` es la suma de los `usd` de los pasos; el `estado` de la
investigación es el del primer paso pendiente o en curso según el `orden`
(`buscando`, `resenas`, …) -- el que está corriendo o el que se va a encolar
enseguida, aunque el worker todavía no lo haya marcado `en_curso` -- y pasa a
`lista` cuando todos los pasos son finales, o a `detenida`/`interrumpida`.
Las claves guardadas no se traducen; las etiquetas sí (`|traducir`).
"""
import math
from datetime import datetime

from flask_babel import gettext

from idiomas import N_
from nicho import avatares, datos
from nicho.fuentes import plataformas

ESTADOS_CADENA = ("consultas", "buscando", "seleccionando", "resenas", "redes", "generando", "lista", "detenida", "interrumpida")
REDES = ("reddit", "youtube")
PASOS_CADENA = ("consultas", "buscar:amazon", "buscar:meli", "buscar:tiktok_shop", "seleccionar", "resenas:amazon", "resenas:meli",
                "resenas:tiktok_shop", "redes:reddit", "redes:youtube", "generar")
FINALES = ("hecho", "vacio", "saltado", "error")
ETIQUETAS_ESTADO = {"consultas": N_("consultas"), "buscando": N_("buscando"), "seleccionando": N_("seleccionando"),
                    "resenas": N_("reseñas"), "redes": N_("redes"), "generando": N_("generando"), "lista": N_("lista"),
                    "detenida": N_("detenida"), "interrumpida": N_("interrumpida")}
ETIQUETAS_ESTADO_PASO = {"hecho": N_("hecho"), "en_curso": N_("en curso"), "error": N_("error"), "vacio": N_("sin resultados"),
                         "pendiente": N_("pendiente"), "saltado": N_("saltado")}
ETIQUETAS_PASO = {"consultas": N_("consultas"), "buscar:amazon": N_("buscar en Amazon"), "buscar:meli": N_("buscar en Mercado Libre"),
                  "buscar:tiktok_shop": N_("buscar en TikTok Shop"), "seleccionar": N_("elegir productos"),
                  "resenas:amazon": N_("reseñas de Amazon"), "resenas:meli": N_("opiniones de Mercado Libre"),
                  "resenas:tiktok_shop": N_("reseñas de TikTok Shop"), "redes:reddit": N_("Reddit"), "redes:youtube": N_("YouTube"),
                  "generar": N_("avatares")}
TOPES_DEFECTO = {"consultas": 3, "productos_por_consulta": 20, "productos_elegidos": 15, "resenas_por_producto": 100}
LIMITES = {"consultas": (1, 4), "productos_por_consulta": (5, 40), "productos_elegidos": (3, 30), "resenas_por_producto": (20, 200)}
MAX_FILAS_SELECCION = 300
MAX_TOKENS_CONSULTAS = 400
MAX_TOKENS_SELECCION = 6000
IDIOMAS = plataformas.IDIOMA_POR_PAIS
PLATAFORMAS_POR_PAIS = {clave: plataformas.PLATAFORMAS[clave]["paises"] for clave in plataformas.PLATAFORMAS}


def _ahora():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _centavos(x):
    return math.ceil(round(x * 100, 6)) / 100


# --------------------------------------------------------------- topes ---

def normalizar_topes(d):
    """Enteros dentro de LIMITES; vacío = defecto. ValueError si no es un número."""
    salida = {}
    for clave, (minimo, maximo) in LIMITES.items():
        v = (d or {}).get(clave)
        if v in (None, ""):
            salida[clave] = TOPES_DEFECTO[clave]
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError(gettext("«%(campo)s» debe ser un número entero.", campo=clave))
        salida[clave] = max(minimo, min(maximo, n))
    return salida


# --------------------------------------------------------------- pasos ---

def orden_pasos(plataformas_elegidas, redes_elegidas):
    p = [x for x in (plataformas_elegidas or []) if x in plataformas.PLATAFORMAS]
    r = [x for x in (redes_elegidas or []) if x in REDES]
    return ["consultas"] + [f"buscar:{x}" for x in p] + ["seleccionar"] + [f"resenas:{x}" for x in p] + [f"redes:{x}" for x in r] + ["generar"]


def estado_por_paso(paso):
    if paso == "consultas":
        return "consultas"
    if paso.startswith("buscar:"):
        return "buscando"
    if paso == "seleccionar":
        return "seleccionando"
    if paso.startswith("resenas:"):
        return "resenas"
    if paso.startswith("redes:"):
        return "redes"
    return "generando"


def _orden(inv):
    if inv.get("orden"):
        return list(inv["orden"])
    plat, redes = inv.get("plataformas"), inv.get("redes")
    return [p for p in PASOS_CADENA
            if not (p.startswith("buscar:") or p.startswith("resenas:")) or plat is None or p.split(":", 1)[1] in plat
            if not p.startswith("redes:") or redes is None or p.split(":", 1)[1] in redes]


def siguiente_paso(inv):
    """El primer paso pendiente o en curso según el `orden`; None si la
    investigación está `lista`, `detenida`, `interrumpida` o no le queda nada."""
    if not inv or inv.get("estado") in ("lista", "detenida", "interrumpida"):
        return None
    pasos = inv.get("pasos") or {}
    for paso in _orden(inv):
        estado = (pasos.get(paso) or {}).get("estado")
        if estado in (None, "pendiente", "en_curso"):
            return paso
    return None


def terminada(inv):
    pasos = inv.get("pasos") or {}
    orden = _orden(inv)
    return bool(orden) and all((pasos.get(p) or {}).get("estado") in FINALES for p in orden)


def marcar_paso(inv, paso, estado, **kw):
    """Copia con `pasos[paso]` actualizado (+ kwargs: usd, productos, relevantes,
    resenas, aviso…), `gastado_usd` recalculado y el `estado` de la
    investigación derivado: el del primer paso pendiente o en curso según el
    `orden` -- el que está corriendo, o el que `avanzar()` va a encolar
    enseguida sin marcarlo todavía (el worker solo marca `en_curso` una vez
    que la tarea arranca de verdad) --, o `lista` si ya no queda nada
    pendiente. Por eso a veces coincide con `estado_por_paso(paso)` (mismo
    paso, o el siguiente de la misma fase) y a veces salta a la fase
    siguiente completa (p. ej. a "generando" en cuanto el último paso antes
    de "generar" queda en un estado final)."""
    nuevo = dict(inv or {})
    pasos = dict(nuevo.get("pasos") or {})
    pasos[paso] = {**(pasos.get(paso) or {}), "estado": estado, **kw}
    nuevo["pasos"] = pasos
    nuevo["gastado_usd"] = round(sum(float((p or {}).get("usd") or 0) for p in pasos.values()), 4)
    if nuevo.get("estado") not in ("detenida", "interrumpida"):
        if terminada(nuevo):
            nuevo["estado"], nuevo["terminada_en"] = "lista", nuevo.get("terminada_en") or _ahora()
        else:
            siguiente = siguiente_paso({**nuevo, "estado": estado_por_paso(paso)})
            nuevo["estado"] = estado_por_paso(siguiente or paso)
    return nuevo


def detener(inv, motivo):
    return {**dict(inv or {}), "estado": "detenida", "detenida_por": motivo, "terminada_en": _ahora()}


def puede_reanudar(estado):
    return estado in ("detenida", "interrumpida")


def reanudar(inv):
    """Reanudar (spec §7): los pasos `en_curso` (interrumpidos) vuelven a
    `pendiente`, y también consultas y selección con `error` (Claude,
    centavos); una búsqueda o unas reseñas con `error` NO se repiten solas
    porque ya cobraron: para eso está «Investigar de nuevo», que aprueba otra
    cifra."""
    nuevo = dict(inv or {})
    pasos = {}
    for paso, info in (nuevo.get("pasos") or {}).items():
        info = dict(info or {})
        if info.get("estado") == "en_curso" or (paso in ("consultas", "seleccionar") and info.get("estado") == "error"):
            info["estado"] = "pendiente"
        pasos[paso] = info
    nuevo.update(pasos=pasos, detenida_por=None, ultimo_error=None, terminada_en=None)
    siguiente = siguiente_paso({**nuevo, "estado": "consultas"})
    nuevo["estado"] = estado_por_paso(siguiente) if siguiente else "lista"
    return nuevo


def job_de_paso(cliente, estudio_id, paso):
    """El job_id de la tarea que corre ese paso (para la barra de progreso)."""
    if paso in ("consultas", "seleccionar") or paso.startswith("buscar:"):
        return datos.job_id_inv(cliente, estudio_id, paso)
    if paso.startswith("resenas:") or paso.startswith("redes:"):
        return datos.job_id_recolectar(cliente, estudio_id, paso.split(":", 1)[1])
    return datos.job_id_generar(cliente, estudio_id)


def resumen(inv):
    """Lo que la plantilla necesita; tolera `{}`."""
    inv = inv or {}
    pasos = inv.get("pasos") or {}
    productos = sum(int((v or {}).get("productos") or 0) for k, v in pasos.items() if k.startswith("buscar:"))
    resenas = sum(int((v or {}).get("nuevos") or 0) for k, v in pasos.items() if k.startswith("resenas:") or k.startswith("redes:"))
    return {"consultas": inv.get("consultas") or [], "productos": productos, "relevantes": int((pasos.get("seleccionar") or {}).get("relevantes") or 0),
            "elegidos": sum(len(v) for v in (inv.get("elegidos") or {}).values()), "resenas": resenas,
            "gastado": float(inv.get("gastado_usd") or 0), "aprobado": float(inv.get("aprobado_usd") or 0),
            "detenida_por": inv.get("detenida_por"), "pasos": pasos, "orden": _orden(inv) if inv else [], "estado": inv.get("estado"),
            "ultimo_error": inv.get("ultimo_error"), "pais": inv.get("pais"), "plataformas": inv.get("plataformas") or [],
            "redes": inv.get("redes") or [], "topes": inv.get("topes") or {}, "estimado": inv.get("estimado") or {},
            "iniciada_en": inv.get("iniciada_en"), "terminada_en": inv.get("terminada_en")}


# ------------------------------------------------------------ estimado ---

def _tokens_claude(n_plataformas, topes):
    productos = n_plataformas * topes["consultas"] * topes["productos_por_consulta"]
    entrada = 1500 + 100 + 600 + 80 * productos
    salida = 100 + 25 * productos
    return entrada, salida


def costo_claude(tokens_entrada, tokens_salida):
    return avatares.costo_real(tokens_entrada, tokens_salida)


def estimar(estudio, pais, plataformas_elegidas, redes_elegidas, topes):
    """Desglose del peor caso: búsquedas y reseñas por plataforma (registro),
    Claude (consultas + selección) y avatares (`estimar_costo_maximo`).
    ErrorFuente si una plataforma no cubre el país."""
    topes = {**TOPES_DEFECTO, **(topes or {})}
    filas, total = [], 0.0
    for clave in plataformas_elegidas or []:
        if not plataformas.cubre(clave, pais):
            raise plataformas.ErrorFuente(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=plataformas.nombre(clave), pais=pais))
        busqueda = plataformas.estimar_busqueda(clave, topes["consultas"], topes["productos_por_consulta"])
        resenas = plataformas.estimar_resenas(clave, topes["productos_elegidos"], topes["resenas_por_producto"])
        filas.append({"clave": clave, "nombre": plataformas.nombre(clave), "busqueda_usd": busqueda, "resenas_usd": resenas,
                      "texto": gettext("Búsqueda + reseñas")})
        total += busqueda + resenas
    entrada, salida = _tokens_claude(len(filas), topes)
    claude_usd = _centavos(costo_claude(entrada, salida))
    avatares_usd = _centavos(avatares.estimar_costo_maximo()["usd"])
    total = _centavos(total + claude_usd + avatares_usd)
    return {"filas": filas, "claude_usd": claude_usd, "avatares_usd": avatares_usd, "total_usd": total,
            "texto": gettext("Investigación: %(plataformas)s plataforma(s), %(redes)s red(es)",
                             plataformas=len(filas), redes=len([r for r in (redes_elegidas or []) if r in REDES]))}


def crear_inicial(tema, pais, plataformas_elegidas, redes_elegidas, topes, estimado=None):
    """El diccionario inicial (spec §2.4): orden y pasos prellenados, la cifra
    aprobada = `estimado["total_usd"]` (se calcula si no se pasa)."""
    topes = {**TOPES_DEFECTO, **(topes or {})}
    plat = [x for x in (plataformas_elegidas or []) if x in plataformas.PLATAFORMAS]
    redes = [x for x in (redes_elegidas or []) if x in REDES]
    estimado = estimado or estimar({}, pais, plat, redes, topes)
    orden = orden_pasos(plat, redes)
    return {"version": 1, "estado": "consultas", "tema": tema or "", "pais": pais, "idioma_consultas": plataformas.idioma(pais),
            "plataformas": plat, "redes": redes, "topes": topes, "consultas": [], "orden": orden,
            "pasos": {p: {"estado": "pendiente"} for p in orden}, "elegidos": {}, "estimado": estimado,
            "aprobado_usd": float(estimado.get("total_usd") or 0), "gastado_usd": 0.0,
            "iniciada_en": _ahora(), "terminada_en": None, "detenida_por": None, "ultimo_error": None}


# ---------------------------------------------------------- selección ---

def elegir(productos, decisiones, productos_elegidos):
    """Por plataforma, los `productos_elegidos` relevantes con más reseñas (sin
    dato = 0; empate por id). -> {plataforma: [fuente_id, …]} solo con
    plataformas que tengan alguno."""
    por_plataforma = {}
    for p in productos or []:
        d = (decisiones or {}).get(p.get("id"))
        if not d or not d.get("relevante"):
            continue
        por_plataforma.setdefault(p.get("plataforma"), []).append(p)
    salida = {}
    for clave, lista in por_plataforma.items():
        lista.sort(key=lambda p: (-(p.get("n_resenas") or 0), int(p.get("id") or 0)))
        salida[clave] = [p["fuente_id"] for p in lista[:max(1, int(productos_elegidos))]]
    return salida


def params_redes(red, inv):
    consultas = [c for c in (inv.get("consultas") or []) if c]
    pais = inv.get("pais") or ""
    if red == "reddit":
        return {"palabras_clave": " OR ".join(consultas), "subreddits": [], "links": [], "max_posts": 25, "max_comentarios_por_post": 50, "periodo": "year"}
    return {"palabras_clave": " | ".join(consultas), "links": [], "max_videos": 10, "max_comentarios_por_video": 100,
            "idioma": plataformas.idioma(pais), "region": pais}


# --------------------------------------------------------------- Claude ---

PROMPT_CONSULTAS = """Eres un comprador experto que busca productos en tiendas en línea (Amazon, Mercado Libre, TikTok Shop).
Nicho o tema a investigar: {tema}
Producto que vendemos (solo como referencia; NO busques nuestra marca): {producto}
Mercado: {pais}. Idioma de las búsquedas: {idioma}.

Escribe de {minimo} a {maximo} búsquedas cortas (2 a 6 palabras cada una), en {idioma}, tal como las escribiría un comprador en el buscador de una tienda para encontrar los productos de ese nicho y de su competencia. Sin marcas nuestras, sin comillas, sin explicaciones.
Responde SOLO con JSON: {{"consultas": ["...", "..."]}}"""

PROMPT_SELECCION = """Eres un analista de mercado. Tema del nicho: {tema}
Producto que vendemos: {producto}
Mercado: {pais}.

Abajo hay productos encontrados buscando ese nicho en tiendas en línea. Marca cuáles son de verdad del nicho (competencia directa o sustitutos que compra la misma persona para el mismo problema) y cuáles no (accesorios, repuestos, otra categoría, ruido de la búsqueda). Motivo de máximo 12 palabras, en {idioma_salida}.
Productos (id · plataforma · título · marca · precio · estrellas · reseñas):
{lista}

Responde SOLO con JSON, con TODOS los ids: {{"productos": [{{"id": 12, "relevante": true, "motivo": "..."}}, ...]}}"""

_NOMBRE_IDIOMA = {"sv": "sueco", "es": "español", "en": "inglés", "pt": "portugués", "de": "alemán", "fr": "francés", "it": "italiano",
                  "nl": "neerlandés", "ja": "japonés"}


def _idioma_texto(codigo):
    return f"{_NOMBRE_IDIOMA.get(codigo, codigo)} ({codigo})"


def _con_tokens(e, entrada, salida):
    e.tokens_entrada, e.tokens_salida = entrada, salida
    return e


def consultas_con_claude(estudio, pais, n=None):
    """-> (consultas, tokens_entrada, tokens_salida). Entre min(2, n) y n
    consultas limpias y sin repetir, con n = el tope aprobado (la búsqueda nunca
    gasta más que su línea del estimado); AnalisisInvalido (con tokens) si Claude
    no devuelve eso."""
    minimo_tope, maximo_tope = LIMITES["consultas"]
    n = max(minimo_tope, min(int(n or TOPES_DEFECTO["consultas"]), maximo_tope))
    minimo = min(2, n)
    idioma = plataformas.idioma(pais)
    prompt = PROMPT_CONSULTAS.format(tema=(estudio.get("tema") or "").strip(), producto=(estudio.get("producto") or "").strip() or "—",
                                     pais=pais, idioma=_idioma_texto(idioma), minimo=minimo, maximo=n)
    texto, entrada, salida = avatares._llamar(prompt, MAX_TOKENS_CONSULTAS)
    try:
        data = avatares._json_objeto(texto)
    except avatares.AnalisisInvalido as e:
        raise _con_tokens(e, entrada, salida)
    consultas, vistas = [], set()
    for c in (data.get("consultas") or []) if isinstance(data.get("consultas"), list) else []:
        c = " ".join(str(c or "").split()).strip(' "“”')[:80]
        if c and c.lower() not in vistas:
            vistas.add(c.lower())
            consultas.append(c)
    consultas = consultas[:n]
    if len(consultas) < minimo:
        raise _con_tokens(avatares.AnalisisInvalido(gettext("Claude devolvió menos de %(n)s consultas.", n=minimo)), entrada, salida)
    return consultas, entrada, salida


def _fila_producto(p):
    precio = f"{p.get('precio')} {p.get('moneda') or ''}".strip() if p.get("precio") is not None else "—"
    return (f"{p['id']} · {p.get('plataforma')} · {(p.get('titulo') or '')[:120]} · {p.get('marca') or '—'} · {precio} · "
            f"{p.get('estrellas') if p.get('estrellas') is not None else '—'} · {p.get('n_resenas') if p.get('n_resenas') is not None else '—'}")


def seleccion_con_claude(estudio, productos):
    """-> ({id: {"relevante", "motivo"}}, tokens_entrada, tokens_salida) para
    los productos dados (máximo MAX_FILAS_SELECCION, los de más reseñas
    primero); ids que Claude no menciona quedan fuera del dict."""
    lista = sorted(productos or [], key=lambda p: (-(p.get("n_resenas") or 0), int(p.get("id") or 0)))[:MAX_FILAS_SELECCION]
    validos = {int(p["id"]) for p in lista}
    prompt = PROMPT_SELECCION.format(tema=(estudio.get("tema") or "").strip(), producto=(estudio.get("producto") or "").strip() or "—",
                                     pais=(estudio.get("pais") or ""),
                                     idioma_salida=_idioma_texto((estudio.get("idioma") or "es")[:2]),
                                     lista="\n".join(_fila_producto(p) for p in lista))
    texto, entrada, salida = avatares._llamar(prompt, MAX_TOKENS_SELECCION)
    try:
        data = avatares._json_objeto(texto)
    except avatares.AnalisisInvalido as e:
        raise _con_tokens(e, entrada, salida)
    decisiones = {}
    for d in (data.get("productos") or []) if isinstance(data.get("productos"), list) else []:
        try:
            pid = int((d or {}).get("id"))
        except (TypeError, ValueError):
            continue
        if pid in validos:
            decisiones[pid] = {"relevante": bool((d or {}).get("relevante")), "motivo": str((d or {}).get("motivo") or "")[:300]}
    if not decisiones:
        raise _con_tokens(avatares.AnalisisInvalido(gettext("Claude no juzgó ningún producto.")), entrada, salida)
    return decisiones, entrada, salida

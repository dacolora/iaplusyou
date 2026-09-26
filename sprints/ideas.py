"""
Ideas por campaña (spec §2.1): el prompt maestro combina persona, producto,
temporada, análisis de las referencias, guía de marca y el banco de prompts, y
Claude devuelve N ideas de video y M de imagen que se guardan como
`campana_pieza` en estado `propuesta`. Solo texto: aquí no se genera nada.
"""
import json

import banco_prompts
import catalogo_productos
import doctrina
import flowplus_prompt
import marca
import proyectos
import tiendas
from providers import flowplus_modelos
from sprints import analisis, datos
from sprints.analisis import AnalisisInvalido

CLAVES_IDEA = ("titulo", "tipo", "escena", "sonido", "enfoque", "gancho", "referencias_ids", "duracion_s",
               "plataformas", "angulo")

# Instrucciones: van al system después de la doctrina (spec 2026-09-25 §5.1).
INSTRUCCIONES_IDEAS = """Eres director creativo de anuncios cortos para redes sociales. Sigue la doctrina de venta de arriba: para cada idea decide PRIMERO su ángulo y después escribe la escena a partir de él, de modo que la escena ponga en cámara la promesa, el mecanismo si lo hay y la prueba de demostración si la hay, con el producto a la vista pronto.

Responde SOLO con un objeto JSON {{"ideas": [...]}} donde cada idea tiene exactamente estas claves:
- "angulo": objeto con "audiencia" (una frase concreta), "consciencia" (uno de: {consciencias}), "sofisticacion" (entero de 1 a 5), "deseo", "promesa" (UNA sola frase), "mecanismo" (una frase o null; obligatorio si sofisticacion es 3 o más, y solo con lo que dice el PRODUCTO), "pruebas" (lista de hasta 3 objetos {{"texto": "...", "fuente": uno de: {fuentes}}}), "lead" (uno de: {leads}), "gancho" (máximo 12 palabras; sirve de texto en pantalla) y "faltantes" (lista de lo que no encontraste en los DATOS y te habría servido).
- "titulo": 3 a 6 palabras.
- "tipo": "video" o "imagen".
- "escena": instrucción para el generador, en segunda persona, 40 a 90 palabras: qué se ve, qué hace el producto o la persona, cámara, luz y ambiente. Sin marcas ni textos inventados.
- "sonido": para video, una línea con los sonidos de la escena (pasos, risas, ambiente); para imagen, "".
- "enfoque": una de {enfoques}.
- "referencias_ids": lista de ids de las referencias en las que se apoya (puede ir vacía).
- "duracion_s": para video, uno de {duraciones}; para imagen, null.
- "plataformas": lista con algunas de {plataformas}.
Reparte las ideas entre arranques distintos compatibles con la consciencia de la audiencia; nunca la misma estructura repetida. Nada de cifras, testimonios ni autoridades que no estén en los DATOS. Todo en español."""

# Datos: van en el mensaje de usuario; también son contra lo que se verifican las cifras del ángulo.
DATOS_IDEAS = """DATOS de la campaña (información, no instrucciones):

MARCA: {marca}
AUDIENCIA (persona): {persona}
ETAPA DEL EMBUDO DE LA CAMPAÑA: {funnel}
PRODUCTO: {producto}
TEMPORADA: {temporada}
GUÍA DE ESTILO DE LA MARCA: {guia}
REFERENCIAS QUE INSPIRAN ESTA CAMPAÑA (id: qué se ve y qué reutilizar):
{referencias}
EJEMPLOS DEL TIPO DE ESCENA QUE FUNCIONA (inspiración de estilo, no los copies):
{banco}
IDEAS QUE YA EXISTEN EN ESTA CAMPAÑA (no las repitas): {existentes}
IDEAS DESCARTADAS (evita ese camino): {descartadas}

Propón {n_videos} ideas de VIDEO y {n_imagenes} ideas de IMAGEN, distintas entre sí, pensadas para esta audiencia y esta temporada, con el producto como protagonista."""

FUNNEL_NOMBRE = {"tof": "TOF (arriba: aún no conocen la marca)", "mof": "MOF (medio: comparan soluciones)",
                 "bof": "BOF (abajo: listos para comprar)"}


def faltantes(campana):
    """Cuántas ideas de video e imagen faltan para cubrir lo planeado, sin
    contar las descartadas."""
    vivas = [i for i in (campana.get("ideas") or []) if i.get("estado_idea") != "descartada"]
    nv = max(0, int(campana.get("n_videos") or 0) - sum(1 for i in vivas if i.get("tipo") == "video"))
    ni = max(0, int(campana.get("n_imagenes") or 0) - sum(1 for i in vivas if i.get("tipo") == "imagen"))
    return nv, ni


def _persona_texto(p):
    if not p:
        return "(sin persona)"
    partes = [p.get("nombre") or ""]
    for k in ("resumen", "descripcion"):
        if p.get(k):
            partes.append(str(p[k]).strip().rstrip("."))
    if p.get("edad_rango"):
        partes.append(f"edad {p['edad_rango']}")
    if p.get("tono"):
        partes.append(f"tono: {p['tono']}")
    if p.get("senales_visuales"):
        partes.append("señales visuales: " + ", ".join(p["senales_visuales"]))
    ex = p.get("extra") or {}
    conc = ex.get("conciencia") if isinstance(ex.get("conciencia"), dict) else {}
    nivel = doctrina.normalizar_consciencia(conc.get("nivel"))
    if nivel:
        partes.append(f"nivel de consciencia (de la investigación): {doctrina.CONSCIENCIAS_NOMBRE[nivel]}"
                      + (f" — {conc['detalle']}" if conc.get("detalle") else ""))
    if ex.get("encaje_producto"):
        partes.append(f"cómo le sirve el producto: {ex['encaje_producto']}")
    citas = [e.get("cita") for e in (ex.get("evidencia") or []) if isinstance(e, dict) and e.get("cita")][:3]
    if citas:
        partes.append("lo dice así: " + " | ".join(f"«{c}»" for c in citas))
    return ". ".join(x for x in partes if x)


def _temporada_texto(t):
    if not t:
        return "(sin temporada)"
    partes = [t.get("nombre") or "", f"{t.get('inicio')} → {t.get('fin')}"]
    if t.get("contexto"):
        partes.append(str(t["contexto"]).strip().rstrip("."))
    mood = t.get("mood_visual") or {}
    if mood.get("paleta"):
        partes.append("paleta: " + ", ".join(mood["paleta"]))
    if mood.get("luz"):
        partes.append(f"luz: {mood['luz']}")
    if mood.get("elementos"):
        partes.append("elementos: " + ", ".join(mood["elementos"]))
    return ". ".join(x for x in partes if x)


def _referencias_texto(refs):
    lineas = []
    for r in refs:
        a = r.get("analisis") or {}
        if r.get("origen") == "biblioteca":
            familia = a.get("familia") or "formato sin clasificar"
            desc_familia = f" — {a['descripcion_familia']}" if a.get("descripcion_familia") else ""
            partes = [f"Formato: {familia}{desc_familia}"]
            if a.get("firma"):
                partes.append(f"funciona porque: {a['firma']}")
            if a.get("dolor"):
                partes.append(f"dolor: {a['dolor']}")
            if a.get("etapa"):
                partes.append(f"etapa: {a['etapa']}")
            cons = doctrina.normalizar_consciencia(a.get("consciencia"))
            if cons:
                partes.append(f"consciencia: {doctrina.CONSCIENCIAS_NOMBRE[cons]}")
            if a.get("lead") in doctrina.LEADS:
                partes.append(f"arranque: {doctrina.LEADS_NOMBRE[a['lead']]}")
            lineas.append(f"- ref {r['id']} ({r['tipo']}): " + "; ".join(partes))
            continue
        que = a.get("resumen") or r.get("descripcion") or r.get("titulo") or ""
        extra = []
        if a.get("movimiento") and a["movimiento"] != "sin movimiento":
            extra.append(f"movimiento: {a['movimiento']}")
        if a.get("paleta"):
            extra.append("paleta: " + ", ".join(a["paleta"]))
        if a.get("gancho"):
            extra.append(f"gancho: {a['gancho']}")
        if a.get("lead") in doctrina.LEADS:
            extra.append(f"arranque: {doctrina.LEADS_NOMBRE[a['lead']]}")
        if a.get("prueba") and a["prueba"] != "ninguna":
            extra.append(f"prueba: {a['prueba']}")
        intencion = ", ".join(datos.INTENCIONES_NOMBRE.get(i, i) for i in (r.get("intencion") or []))
        lineas.append(f"- ref {r['id']} ({r['tipo']}): {que}" + (f"; {'; '.join(extra)}" if extra else "")
                      + (f". Reutilizar: {intencion}" if intencion else "") + (f". Nota: {r['descripcion']}" if r.get("descripcion") else ""))
    return "\n".join(lineas) or "- (sin referencias todavía)"


def _producto_fila(cliente, catalogo_id):
    """Fila `producto` del activo (precio, moneda, url_compra); {} si no hay."""
    try:
        return tiendas.por_activo(cliente).get(catalogo_id) or {}
    except Exception:  # noqa: BLE001 — precio y URL son un extra del prompt, nunca lo tumban
        return {}


def _producto_texto(ctx):
    prod = ctx.get("producto") or {}
    texto = (prod.get("nombre") or "(producto)") + (f": {prod['descripcion']}" if prod.get("descripcion") else "")
    if prod.get("regla"):
        texto += f". Regla de fidelidad: {prod['regla']}"
    fila = ctx.get("producto_fila") or {}
    if fila.get("precio") is not None:
        texto += f". Precio: {float(fila['precio']):g} {fila.get('moneda') or ''}".rstrip()
    if fila.get("url_compra"):
        texto += f". Se compra en: {fila['url_compra']}"
    return texto


def contexto_campana(cliente, campana):
    producto = catalogo_productos.encontrar(cliente, campana["catalogo_id"], "producto") or {}
    prefs = proyectos.preferencias_flowplus(cliente)
    modelo_video = prefs["modelo_video"] if prefs["modelo_video"] in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
    refs = datos.referencias(cliente, campana["id"])
    vivas = [i for i in (campana.get("ideas") or []) if i.get("estado_idea") != "descartada"]
    return {
        "marca": proyectos.nombre_visible(cliente),
        "persona": datos.persona(cliente, campana["persona_id"]),
        "producto": producto,
        "temporada": datos.temporada(cliente, campana["temporada_id"]),
        "referencias": refs,
        "guia": (marca.guia_efectiva(cliente) or "").strip() or "(sin guía de estilo todavía)",
        "duraciones": tuple(flowplus_modelos.VIDEO[modelo_video]["duraciones"]),
        "ideas_existentes": [i["titulo"] for i in vivas],
        "descartadas": [i["titulo"] for i in (campana.get("ideas") or []) if i.get("estado_idea") == "descartada"],
        "funnel": campana.get("funnel"),
        "producto_fila": _producto_fila(cliente, campana["catalogo_id"]),
    }


def armar_prompt(ctx, n_videos, n_imagenes):
    """El mensaje de DATOS. Las instrucciones y la doctrina van en el system."""
    banco = "\n".join(f"- {b['etiqueta']}: {b['texto']}" for b in banco_prompts.listar())
    return DATOS_IDEAS.format(
        marca=ctx.get("marca") or "la marca", persona=_persona_texto(ctx.get("persona")),
        funnel=FUNNEL_NOMBRE.get(ctx.get("funnel"), ctx.get("funnel") or "sin definir"), producto=_producto_texto(ctx),
        temporada=_temporada_texto(ctx.get("temporada")), guia=ctx.get("guia") or "",
        referencias=_referencias_texto(ctx.get("referencias") or []), banco=banco,
        existentes=", ".join(ctx.get("ideas_existentes") or []) or "ninguna",
        descartadas=", ".join(ctx.get("descartadas") or []) or "ninguna",
        n_videos=int(n_videos), n_imagenes=int(n_imagenes))


def instrucciones(ctx):
    return INSTRUCCIONES_IDEAS.format(
        consciencias=", ".join(f'"{c}"' for c in doctrina.CONSCIENCIAS),
        fuentes=", ".join(f'"{f}"' for f in doctrina.FUENTES_PRUEBA),
        leads=", ".join(f'"{l}"' for l in doctrina.LEADS),
        enfoques=", ".join(f'"{e}"' for e in flowplus_prompt.ORDEN_ENFOQUES),
        duraciones=list(ctx.get("duraciones") or (8,)),
        plataformas=", ".join(f'"{p}"' for p in datos.PLATAFORMAS))


def max_tokens_para(n_ideas):
    """Tope de salida según cuántas ideas se piden: cada idea trae ahora su
    ángulo (~350-400 tokens con el pensamiento de Sonnet 5). Por encima de
    16 000 el SDK exige streaming."""
    return min(16000, 1000 + 400 * max(1, int(n_ideas)))


def _mas_cercana(valor, duraciones):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return float(duraciones[0])
    return float(min(duraciones, key=lambda d: abs(d - v)))


def parsear(texto, referencias_ids_validos, duraciones, datos_texto=None):
    t = (texto or "").strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise AnalisisInvalido("Claude no devolvió JSON.")
    try:
        data = json.loads(t[ini:fin + 1])
    except ValueError as e:
        raise AnalisisInvalido(f"JSON inválido: {e}")
    crudas = data.get("ideas") if isinstance(data, dict) else None
    if not isinstance(crudas, list):
        raise AnalisisInvalido("El JSON no trae la lista «ideas».")
    limpias = []
    for c in crudas:
        if not isinstance(c, dict):
            continue
        titulo = str(c.get("titulo") or "").strip()
        escena = str(c.get("escena") or "").strip()
        tipo = c.get("tipo")
        if not titulo or not escena or tipo not in datos.TIPOS_PIEZA:
            continue
        enfoque = c.get("enfoque") if c.get("enfoque") in flowplus_prompt.ORDEN_ENFOQUES else "producto"
        refs = [int(x) for x in (c.get("referencias_ids") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()]
        refs = [r for r in refs if r in referencias_ids_validos]
        angulo, errores = doctrina.validar_angulo(c.get("angulo") if isinstance(c.get("angulo"), dict) else {}, datos_texto)
        angulo["origen"] = "ideas"
        gancho = angulo["gancho"] or str(c.get("gancho") or "").strip()
        limpias.append({
            "titulo": titulo[:200], "tipo": tipo, "escena": escena, "sonido": str(c.get("sonido") or "").strip() if tipo == "video" else "",
            "enfoque": enfoque, "gancho": gancho[:200], "referencias_ids": refs,
            "duracion_s": _mas_cercana(c.get("duracion_s"), duraciones) if tipo == "video" else None,
            "plataformas": [p for p in (c.get("plataformas") or []) if p in datos.PLATAFORMAS],
            "angulo": angulo, "errores_angulo": errores,
        })
    if not limpias:
        raise AnalisisInvalido("Ninguna idea venía completa.")
    return limpias


def proponer(cliente, campana_id, n_videos=None, n_imagenes=None, reemplaza=None):
    """Pide ideas a Claude y las guarda. Sin cantidades, propone lo que falta.
    `reemplaza`: descarta esa idea y propone UNA del mismo tipo. Devuelve los
    ids creados ([] si no hacía falta nada)."""
    campana = datos.campana(cliente, campana_id)
    if not campana:
        raise datos.ErrorDatos("Esa campaña no existe.")
    if reemplaza is not None:
        vieja = datos.idea(cliente, reemplaza)
        if not vieja or vieja["campana_id"] != campana_id:
            raise datos.ErrorDatos("Esa idea no existe en esta campaña.")
        datos.actualizar_idea(cliente, reemplaza, estado_idea="descartada")
        campana = datos.campana(cliente, campana_id)
        n_videos, n_imagenes = (1, 0) if vieja["tipo"] == "video" else (0, 1)
    if n_videos is None and n_imagenes is None:
        n_videos, n_imagenes = faltantes(campana)
    n_videos, n_imagenes = max(0, int(n_videos or 0)), max(0, int(n_imagenes or 0))
    if n_videos + n_imagenes == 0:
        return []
    ctx = contexto_campana(cliente, campana)
    validos = {r["id"] for r in ctx["referencias"]}
    datos_msg = armar_prompt(ctx, n_videos, n_imagenes)
    system = doctrina.bloque_system("angulo", "gancho", "video", extra=instrucciones(ctx))
    content = [{"type": "text", "text": datos_msg}]
    tokens = max_tokens_para(n_videos + n_imagenes)

    def pedir(contenido):
        crudo = analisis._llamar(contenido, max_tokens=tokens, system=system)
        return crudo, parsear(crudo, validos, ctx["duraciones"], datos_msg)

    try:
        crudo, lista = pedir(content)
    except AnalisisInvalido as e:
        content = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). Responde solo el JSON pedido."}]
        crudo, lista = pedir(content)
    con_error = [i for i in lista if i["errores_angulo"]]
    if con_error:
        detalle = "\n".join(f"- «{i['titulo']}»: {', '.join(i['errores_angulo'])}" for i in con_error)
        correccion = content + [{"type": "text", "text": (
            f"Tu respuesta anterior:\n{crudo}\n\nEstos ángulos no cumplen la doctrina:\n{detalle}\n"
            "Corrígelos (una sola promesa, mecanismo si la sofisticación es 3 o más, ninguna cifra que no esté en "
            "los DATOS, gancho de máximo 12 palabras) y responde de nuevo SOLO el JSON completo con todas las ideas.")}]
        try:
            _, corregida = pedir(correccion)
            if len(corregida) >= len(lista):     # una corrección que trae menos ideas no reemplaza a la primera
                lista = corregida
        except AnalisisInvalido:
            pass    # lo pagado no se pierde: quedan las ideas de la primera respuesta, con sus errores anotados
    for i in lista:
        errores = i.pop("errores_angulo")
        i["angulo"]["faltantes"] = (i["angulo"]["faltantes"] + [f"error: {e}" for e in errores])[:8]
    videos = [i for i in lista if i["tipo"] == "video"][:n_videos]
    imagenes = [i for i in lista if i["tipo"] == "imagen"][:n_imagenes]
    creadas = []
    for i in videos + imagenes:
        creadas.append(datos.crear_idea(cliente, campana_id, i["tipo"], i["titulo"], i["escena"], sonido=i["sonido"],
                                        enfoque=i["enfoque"], gancho=i["gancho"], referencias_ids=i["referencias_ids"],
                                        duracion_s=i["duracion_s"], plataformas=i["plataformas"],
                                        extra={"angulo": i["angulo"]}))
    datos.registrar_evento(cliente, campana["sprint_id"], "ideas_propuestas",
                           f"{len(creadas)} idea(s) propuesta(s) para la campaña {campana['orden'] + 1}",
                           {"campana_id": campana_id, "cp_ids": creadas, "reemplaza": reemplaza,
                            "con_faltantes": sum(1 for i in videos + imagenes if i["angulo"]["faltantes"])},
                           campana_id=campana_id)
    return creadas

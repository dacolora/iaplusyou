"""Evaluación de los anuncios con IA (spec 2026-09-28 §6): Claude mira los
ganadores y los perdedores de la evaluación gratis (`evaluacion.py`) —
miniatura, texto y números— y devuelve por qué ganan, qué patrones se
repiten y anuncios nuevos para probar, cada uno con su ángulo (doctrina) y un
prompt listo para Crear.

Es PAGADO: la ruta muestra `gastos.estimar("evaluacion_tw", n=)` antes de
encolar, la tarea corre con `max_intentos=1` y el gasto real se registra con
los tokens medidos (tipo `evaluacion`), también si la respuesta no sirvió.
Nunca genera ni publica nada: las ideas solo llegan a Crear si la persona
pulsa «Llevar a Crear», y ahí se sigue pagando con el botón de siempre.

Miniaturas: de la Marketing API de Meta con la conexión del proyecto
(`medios_meta`, solo lectura), copiadas a R2 (`copiar_miniaturas`) porque las
URL de Meta caducan. Un anuncio hecho en Creatv tiene su video en R2: Claude
recibe sus fotogramas reales (`visuales`, los mismos del revisor de la
doctrina), no la miniatura. Sin Meta conectado, o si un anuncio es de otra
cuenta publicitaria, Claude juzga por el nombre y los números. Si la tienda
trae ventas por producto, la lista de los que más venden entra al prompt y
cada idea dice a cuál apunta.
"""
import base64
import io
import json
import logging
import os
import tempfile

import requests
from flask_babel import gettext

import doctrina
import idiomas
from referentes import datos as referentes_datos
from storage import r2_uploader

log = logging.getLogger("creatv.triple_whale.analisis")

MAX_BUENOS = 6
MAX_MALOS = 4
MIN_ANUNCIOS = 2
N_IDEAS = 4
MAX_TOKENS = 16000
LADO_IMAGEN = 768
TIMEOUT_META = 20
MAX_PRODUCTOS = 5
CAMPOS_M = ("gasto", "impresiones", "clics", "ctr", "cpm", "gancho", "retencion", "pedidos", "ingresos", "roas",
            "cpa", "conversion", "ticket", "nc_pedidos")


class AnalisisInvalido(RuntimeError):
    """Claude no devolvió lo pedido. Lleva los tokens ya pagados."""
    tokens_entrada = 0
    tokens_salida = 0


# ------------------------------------------------------------- muestra ---

def _redondear(v):
    if v is None:
        return None
    return round(float(v), 4)


def muestra(ev):
    """Qué anuncios ve Claude: hasta MAX_BUENOS ganadores/prometedores (por
    ingresos) y hasta MAX_MALOS perdedores (los que más gastaron), con una
    referencia corta (A1, A2…). Si no hay de ambos lados se completa con los
    que más gastaron «en prueba». Lista vacía si hay menos de MIN_ANUNCIOS."""
    anuncios = ev.get("anuncios") or []
    buenos = [a for a in anuncios if a["veredicto"] in ("ganador", "prometedor")][:MAX_BUENOS]
    malos = sorted((a for a in anuncios if a["veredicto"] == "perdedor"), key=lambda a: -a["m"]["gasto"])[:MAX_MALOS]
    elegidos = buenos + malos
    if len(elegidos) < MAX_BUENOS + MAX_MALOS:
        resto = sorted((a for a in anuncios if a["veredicto"] == "en_prueba"), key=lambda a: -a["m"]["gasto"])
        elegidos += resto[:max(0, MIN_ANUNCIOS + 2 - len(elegidos))]
    if len(elegidos) < MIN_ANUNCIOS:
        return []
    salida = []
    for i, a in enumerate(elegidos, start=1):
        salida.append({
            "ref": f"A{i}", "canal": a["canal"], "ad_id": a["ad_id"], "nombre": a["nombre"],
            "campana": a.get("campana"), "creative_id": a.get("creative_id"), "video_url": a.get("video_url"),
            "veredicto": a["veredicto"], "motivo": a["motivo"],
            "problemas": list(a["problemas"]), "fortalezas": list(a["fortalezas"]),
            "m": {k: _redondear(a["m"].get(k)) for k in CAMPOS_M},
        })
    return salida


# -------------------------------------------------------------- medios ---

def _graph(ruta, token, params):
    """GET de solo lectura a la Graph API. El token va en params y nunca en un
    mensaje: los errores salen solo con el tipo."""
    from meta_ads import auth as meta_auth
    p = dict(params or {})
    p["access_token"] = token
    try:
        resp = requests.get(f"{meta_auth.BASE_URL}/{ruta}", params=p, timeout=TIMEOUT_META)
    except requests.RequestException as e:
        raise RuntimeError(f"Meta: {type(e).__name__}") from None
    if not resp.ok:
        raise RuntimeError(f"Meta respondió {resp.status_code}")
    return resp.json()


def medios_meta(cliente, anuncios):
    """{ad_id: {"imagen", "titulo", "texto", "tipo"}} de los anuncios de Meta
    que la conexión del proyecto puede leer. Nunca lanza: lo que falla queda
    fuera (un anuncio de otra cuenta, Meta sin conectar)."""
    import meta_conexion
    try:
        token = meta_conexion.credenciales_ads(cliente)["token"]
    except Exception:  # noqa: BLE001 — sin Meta, la evaluación sigue sin miniaturas
        return {}
    salida = {}
    for a in anuncios:
        if a.get("canal") != "facebook-ads":
            continue
        try:
            creative_id = a.get("creative_id")
            if not creative_id:
                creative_id = ((_graph(a["ad_id"], token, {"fields": "creative"}) or {}).get("creative") or {}).get("id")
            if not creative_id:
                continue
            c = _graph(str(creative_id), token, {"fields": "thumbnail_url,image_url,body,title,object_type",
                                                 "thumbnail_width": 600, "thumbnail_height": 600})
        except Exception as e:  # noqa: BLE001
            log.info("sin miniatura para %s/%s: %s", cliente, a.get("ad_id"), e)
            continue
        imagen = c.get("image_url") or c.get("thumbnail_url")
        if not str(imagen or "").startswith("https://"):
            imagen = None
        salida[a["ad_id"]] = {
            "imagen": imagen, "titulo": (c.get("title") or "")[:200], "texto": (c.get("body") or "")[:600],
            "tipo": "video" if str(c.get("object_type") or "").upper() == "VIDEO" else "imagen",
        }
    return salida


def _imagen_base64(url):
    """La miniatura bajada con la misma guarda de SSRF que Referentes, achicada
    y en JPEG base64. None si no se pudo."""
    from PIL import Image
    from referentes import imagenes
    try:
        crudo = imagenes._bajar(url)
        with Image.open(io.BytesIO(crudo)) as im:
            im = im.convert("RGB")
            im.thumbnail((LADO_IMAGEN, LADO_IMAGEN))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:  # noqa: BLE001 — sin imagen, Claude juzga por el texto
        log.info("no pude bajar la miniatura: %s", type(e).__name__)
        return None


def _bloque_imagen(datos_b64):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": datos_b64}}


def _fotogramas_pieza(pieza, temporales):
    """Bloques de visión de una pieza hecha en Creatv: los fotogramas del
    video (bajado a un temporal que el llamador borra) o la imagen por URL,
    como los arma el revisor de la doctrina. None si algo falla: entonces se
    usa la miniatura de Meta, como con cualquier otro anuncio."""
    from doctrina import revisor
    from sprints import qa
    entry = {"tipo": pieza.get("tipo") or "video", "video_url": pieza.get("url_video"),
             "url_miniatura": pieza.get("url_miniatura")}
    try:
        if entry["tipo"] == "video":
            ruta = qa.archivo_local(entry)
            if not ruta:
                return None
            temporales.append(ruta)
            return revisor.bloques_visuales(entry, ruta) or None
        return revisor.bloques_visuales(entry) or None
    except Exception as e:  # noqa: BLE001 — sin fotogramas queda la miniatura
        log.info("sin fotogramas para la pieza %s: %s", pieza.get("pieza_id"), type(e).__name__)
        return None


def visuales(cliente, anuncios, medios, creatv=None):
    """({ad_id: {"bloques": [...], "clase": "fotogramas"|"imagen"}}, temporales).
    Un anuncio hecho en Creatv (`creatv`, de `datos.piezas_creatv`) manda
    sus fotogramas reales; los demás, la miniatura en base64. `temporales`
    son los videos bajados: el llamador los borra al terminar."""
    salida, temporales = {}, []
    for a in anuncios:
        pieza = (creatv or {}).get(a["ad_id"])
        if pieza and (pieza.get("url_video") or pieza.get("url_miniatura")):
            bloques = _fotogramas_pieza(pieza, temporales)
            if bloques:
                salida[a["ad_id"]] = {"bloques": bloques, "clase": "fotogramas" if pieza.get("tipo") != "imagen"
                                      else "imagen"}
                continue
        medio = medios.get(a["ad_id"]) or {}
        datos_b64 = _imagen_base64(medio["imagen"]) if medio.get("imagen") else None
        if datos_b64:
            salida[a["ad_id"]] = {"bloques": [_bloque_imagen(datos_b64)], "clase": "imagen"}
    return salida, temporales


def con_piezas_creatv(anuncios, medios, creatv):
    """Las piezas hechas en Creatv (`creatv`, de `datos.piezas_creatv`) tienen su video y su miniatura en R2: su
    miniatura sirve tal cual (no se copia: `imagen_origen` ya está puesta) y `visuales` les saca los fotogramas.
    Cambia `medios` en su lugar y lo devuelve."""
    for a in anuncios:
        pieza = (creatv or {}).get(a["ad_id"])
        if not pieza:
            continue
        imagen = pieza.get("url_video") if pieza.get("tipo") == "imagen" else pieza.get("url_miniatura")
        medio = medios.setdefault(a["ad_id"], {"imagen": None, "titulo": "", "texto": "", "tipo": pieza.get("tipo")})
        if imagen:
            medio.update(imagen=imagen, imagen_origen=imagen)
        medio["origen"] = "creatv"
    return medios


def borrar_temporales(rutas):
    for ruta in rutas or []:
        try:
            os.remove(ruta)
        except OSError:
            pass


def clave_miniatura(cliente, evaluacion_id, ref, carpeta="triple_whale"):
    """La clave en R2 de la miniatura de `ref` en una evaluación. `carpeta` separa las evaluaciones de cada pestaña:
    la de Meta rendimiento (`meta_rendimiento`) tiene sus propios ids, y con la misma carpeta la evaluación 3 de
    Meta pisaría las miniaturas de la evaluación 3 de Triple Whale."""
    return f"clientes/{cliente}/{carpeta}/eval{int(evaluacion_id)}_{ref}.jpg"


def copiar_miniaturas(cliente, evaluacion_id, anuncios, medios, carpeta="triple_whale"):
    """Las URL de miniatura de Meta caducan: la de cada anuncio se copia a R2
    y `medio["imagen"]` pasa a ser esa copia (`imagen_origen` guarda la de
    Meta). Lo que no se pueda copiar queda como estaba. Nunca lanza.
    `carpeta`: ver `clave_miniatura`."""
    from PIL import Image
    from referentes import imagenes
    for a in anuncios:
        medio = medios.get(a["ad_id"])
        if not medio or not medio.get("imagen") or medio.get("imagen_origen") or medio.get("origen") == "creatv":
            continue
        try:
            crudo = imagenes._bajar(medio["imagen"])
            with tempfile.TemporaryDirectory(prefix="tw_mini_") as temporal:
                local = os.path.join(temporal, f"{a['ref']}.jpg")
                with Image.open(io.BytesIO(crudo)) as im:
                    im = im.convert("RGB")
                    im.thumbnail((LADO_IMAGEN, LADO_IMAGEN))
                    im.save(local, format="JPEG", quality=85)
                url = r2_uploader.upload_image(local, clave_miniatura(cliente, evaluacion_id, a["ref"], carpeta))
        except Exception as e:  # noqa: BLE001 — se queda la URL de Meta mientras dure
            log.info("no pude copiar la miniatura de %s a R2: %s", a.get("ref"), type(e).__name__)
            continue
        medio["imagen_origen"] = medio["imagen"]
        medio["imagen"] = url
    return medios


# -------------------------------------------------------------- prompt ---

PROMPT = """Eres estratega creativo de anuncios de performance para ecommerce. Estos son anuncios REALES de {marca}, con sus métricas de Triple Whale del {desde} al {hasta} (moneda {moneda}; atribución «{modelo}», ventana «{ventana}»).

Medianas de la cuenta: CTR {ctr} %, gancho (vistas de 3 s / impresiones) {gancho}, retención (ThruPlays / vistas de 3 s) {retencion}, ROAS {roas}×. Meta de ROAS del proyecto: {meta}×.

ANUNCIOS:
{bloques}
{productos}
Tu trabajo: entender POR QUÉ ganan los ganadores y por qué pierden los perdedores —mirando la imagen cuando la hay, el texto y los números— y proponer {n_ideas} anuncios nuevos que repitan lo que funciona.

Responde SOLO con un objeto JSON, sin texto antes ni después, con esta forma:
{{"resumen": "máximo 3 frases: qué funciona en esta cuenta y qué no",
 "patrones_ganadores": [{{"patron": "...", "anuncios": ["A1"]}}],
 "patrones_perdedores": [{{"patron": "...", "anuncios": ["A5"]}}],
 "anuncios": [{{"id": "A1", "por_que": "máximo 30 palabras", "gancho": "qué pasa o qué dice en los primeros 3 segundos", "formato": "p. ej. testimonio a cámara, demostración, antes y después", "etapa": "TOF|MOF|BOF", "consciencia": "unaware|problem-aware|solution-aware|product-aware|most-aware"}}],
 "ideas": [{{"titulo": "máximo 8 palabras", "basada_en": ["A1"], "por_que": "qué patrón ganador repite", "producto": "el producto de la lista de los que más venden al que apunta, tal cual está escrito, o null", "angulo": {{"audiencia": "...", "consciencia": "...", "sofisticacion": 3, "deseo": "...", "promesa": "...", "mecanismo": "una frase (o null; obligatorio si sofisticacion es 3 o más)", "pruebas": [{{"texto": "...", "fuente": "demostracion"}}], "lead": "...", "gancho": "...", "faltantes": []}}, "escena": "qué se ve, plano a plano, máximo 60 palabras", "prompt": "prompt en inglés para el modelo de video, 60 a 120 palabras"}}]}}

Reglas:
- Un patrón vale si lo sostienen dos anuncios o uno con muchos datos; nombra los anuncios por su id (A1, A2…).
- Ninguna cifra que no esté en los datos de arriba.
- Si un anuncio no tiene imagen, júzgalo por su nombre, su texto y sus números, y dilo en "por_que".
- Si un anuncio viene con fotogramas, están en orden y con su segundo: el gancho se juzga por los primeros.
- Si hay lista de productos que más venden, cada idea apunta a uno de ellos ("producto"), salvo que los ganadores vendan otro.
- Las ideas son para {marca}: el mismo producto y la misma promesa que los ganadores, cada una con un gancho distinto. El "prompt" describe la escena para un modelo de video: nada de logos ni marcas ajenas."""


def _num(v, decimales=2):
    return "—" if v is None else idiomas.numero(v, decimales)


def _pct(v):
    return "—" if v is None else idiomas.numero(v * 100, 1) + " %"


def _bloque(a, medio):
    m = a["m"]
    lineas = [f"[{a['ref']}] «{a['nombre']}» · {a['canal']} · campaña «{a.get('campana') or '—'}» · veredicto: "
              f"{a['veredicto']} ({a['motivo']})",
              f"  gasto {_num(m['gasto'])} · impresiones {_num(m['impresiones'], 0)} · CTR {_num(m['ctr'])} % · "
              f"CPM {_num(m['cpm'])} · gancho {_pct(m['gancho'])} · retención {_pct(m['retencion'])}",
              f"  pedidos {_num(m['pedidos'], 1)} · ingresos {_num(m['ingresos'])} · ROAS {_num(m['roas'])}× · "
              f"CPA {_num(m['cpa'])} · conversión {_pct(m['conversion'])}"]
    if a["problemas"] or a["fortalezas"]:
        lineas.append(f"  señales: {', '.join(a['fortalezas'] + a['problemas'])}")
    if medio and (medio.get("titulo") or medio.get("texto")):
        lineas.append(f"  texto del anuncio: «{medio.get('titulo') or ''}» {medio.get('texto') or ''}".rstrip())
    clase = (medio or {}).get("visual")
    if clase == "fotogramas":
        lineas.append("  (abajo van los fotogramas de su video)")
    elif clase != "imagen":
        lineas.append("  (sin imagen)")
    return "\n".join(lineas)


def texto_productos(productos, moneda=""):
    """Bloque «PRODUCTOS QUE MÁS VENDEN» para el prompt; "" sin datos."""
    lista = [p for p in (productos or []) if p.get("nombre") or p.get("sku") or p.get("producto_id")][:MAX_PRODUCTOS]
    if not lista:
        return ""
    lineas = [f"PRODUCTOS QUE MÁS VENDEN en la tienda en ese periodo ({moneda or 'moneda de la tienda'}):"]
    for p in lista:
        nombre = p.get("nombre") or p.get("sku") or p.get("producto_id")
        sku = f" (sku {p['sku']})" if p.get("sku") and p.get("nombre") else ""
        lineas.append(f"- «{nombre}»{sku}: {_num(p.get('pedidos'), 0)} pedidos · {_num(p.get('unidades'), 0)} unidades · "
                      f"ingresos {_num(p.get('ingresos'))}")
    return "\n" + "\n".join(lineas) + "\n"


def armar(marca, contexto, anuncios, medios, bloques=None, productos=None):
    """(texto de DATOS, bloques de visión). `contexto`: desde, hasta, moneda,
    modelo, ventana, benchmarks, meta_roas. `bloques` es lo que devolvió
    `visuales` (sin él, la miniatura de cada anuncio se baja aquí);
    `productos`, los de `datos.top_productos`."""
    b = contexto.get("benchmarks") or {}
    if bloques is None:
        bloques, _ = visuales(None, anuncios, medios)
    con_visual = {}
    for a in anuncios:
        medio = dict(medios.get(a["ad_id"]) or {})
        medio["visual"] = (bloques.get(a["ad_id"]) or {}).get("clase")
        con_visual[a["ad_id"]] = medio
    texto = PROMPT.format(
        marca=marca or "este proyecto", desde=contexto["desde"], hasta=contexto["hasta"],
        moneda=contexto.get("moneda") or "", modelo=contexto.get("modelo") or "", ventana=contexto.get("ventana") or "",
        ctr=_num(b.get("ctr")), gancho=_pct(b.get("gancho")), retencion=_pct(b.get("retencion")),
        roas=_num(b.get("roas")), meta=_num(contexto.get("meta_roas")),
        bloques="\n\n".join(_bloque(a, con_visual.get(a["ad_id"])) for a in anuncios), n_ideas=N_IDEAS,
        productos=texto_productos(productos, contexto.get("moneda") or ""))
    return texto, imagenes_para(anuncios, bloques)


def imagenes_para(anuncios, bloques):
    """Los bloques de visión que siguen a los DATOS: por cada anuncio con imagen o fotogramas (`bloques`, de
    `visuales`), una línea que dice de cuál es y después sus bloques. La usan Triple Whale y Meta rendimiento."""
    imagenes = []
    for a in anuncios:
        v = bloques.get(a["ad_id"])
        if not v or not v.get("bloques"):
            continue
        if v.get("clase") == "fotogramas":
            imagenes.append({"type": "text", "text": f"Fotogramas de {a['ref']} ({a['veredicto']}), en orden:"})
        else:
            imagenes.append({"type": "text", "text": f"Imagen de {a['ref']} ({a['veredicto']}):"})
        imagenes.extend(v["bloques"])
    return imagenes


def system(idioma):
    extra = ("Todo el texto de la respuesta va en el idioma pedido, salvo el campo \"prompt\" de cada idea, que "
             "siempre va en inglés porque es para el modelo de video.")
    return doctrina.bloque_system("clasificar", "angulo", "gancho", "video", extra=extra, idioma=idioma)


# ------------------------------------------------------------- parsear ---

def _json(texto):
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        data = json.loads(t)
    except ValueError:
        ini, fin = t.find("{"), t.rfind("}")
        if ini < 0 or fin <= ini:
            raise AnalisisInvalido("Claude no devolvió JSON.")
        try:
            data = json.loads(t[ini:fin + 1])
        except ValueError as e:
            raise AnalisisInvalido(f"JSON inválido: {e}")
    if not isinstance(data, dict):
        raise AnalisisInvalido("El JSON no es un objeto.")
    return data


def _cadena(v):
    """El texto de un campo de la respuesta: un texto o un número; cualquier otra cosa (un objeto, una lista, un
    booleano, null) vale "" — nunca su `repr`, que llegaría a la pantalla o a un prompt de Crear como si fuera texto."""
    if isinstance(v, bool) or not isinstance(v, (str, int, float)) or not v:
        return ""
    return str(v)


def _texto(v, largo):
    return " ".join(_cadena(v).split())[:largo]


def _refs(valor, validas):
    salida = []
    for r in valor if isinstance(valor, list) else []:
        r = str(r).strip().upper()
        if r in validas and r not in salida:
            salida.append(r)
    return salida


def _patrones(lista, validas):
    salida = []
    for p in lista if isinstance(lista, list) else []:
        if not isinstance(p, dict):
            continue
        patron = _texto(p.get("patron"), 300)
        if patron:
            salida.append({"patron": patron, "anuncios": _refs(p.get("anuncios"), validas)})
    return salida[:5]


def parsear(texto, validas, datos_texto, origen="triple_whale"):
    """El resultado limpio. AnalisisInvalido si no trae ni patrones ni ideas. `origen` es el de cada ángulo de las
    ideas («triple_whale», o «meta» cuando lo usa la evaluación de Meta rendimiento)."""
    data = _json(texto)
    anuncios = {}
    for a in data.get("anuncios") if isinstance(data.get("anuncios"), list) else []:
        if not isinstance(a, dict):
            continue
        ref = str(a.get("id") or "").strip().upper()
        if ref not in validas:
            continue
        anuncios[ref] = {
            "por_que": _texto(a.get("por_que"), 300), "gancho": _texto(a.get("gancho"), 200),
            "formato": _texto(a.get("formato"), 80),
            "etapa": a.get("etapa") if a.get("etapa") in referentes_datos.ETAPAS else None,
            "consciencia": a.get("consciencia") if a.get("consciencia") in referentes_datos.CONSCIENCIAS else None,
        }
    ideas = []
    for i in data.get("ideas") if isinstance(data.get("ideas"), list) else []:
        if not isinstance(i, dict):
            continue
        titulo, prompt = _texto(i.get("titulo"), 80), _cadena(i.get("prompt")).strip()[:1500]
        if not titulo or not prompt:
            continue
        angulo, errores = doctrina.validar_angulo(i.get("angulo") if isinstance(i.get("angulo"), dict) else {},
                                                  datos_texto)
        angulo["origen"] = origen
        ideas.append({"titulo": titulo, "prompt": prompt, "por_que": _texto(i.get("por_que"), 300),
                      "escena": _texto(i.get("escena"), 600), "basada_en": _refs(i.get("basada_en"), validas),
                      "producto": _texto(i.get("producto"), 120) or None,
                      "angulo": doctrina.anotar_errores(angulo, errores)})
    resultado = {"resumen": _texto(data.get("resumen"), 700),
                 "patrones_ganadores": _patrones(data.get("patrones_ganadores"), validas),
                 "patrones_perdedores": _patrones(data.get("patrones_perdedores"), validas),
                 "anuncios": anuncios, "ideas": ideas[:N_IDEAS + 2]}
    if not resultado["ideas"] and not resultado["patrones_ganadores"] and not resultado["patrones_perdedores"]:
        raise AnalisisInvalido("Claude no devolvió patrones ni ideas.")
    return resultado


# ------------------------------------------------------------- analizar ---

def _llamar(content, system_):
    from sprints import analisis as sprints_analisis
    return sprints_analisis._llamar_contando(content, max_tokens=MAX_TOKENS, system=system_)


def anotar_tokens(error, entrada, salida):
    """Deja en `error` los tokens ya pagados (`tokens_entrada`, `tokens_salida`), que la tarea lee para anotar el
    gasto real aunque falle. Nunca lanza."""
    try:
        error.tokens_entrada, error.tokens_salida = int(entrada or 0), int(salida or 0)
    except Exception:  # noqa: BLE001 — una excepción que no acepta atributos sigue su camino sin ellos
        pass
    return error


def sin_respuesta(error):
    """True si la llamada a Claude falló SIN respuesta (tope de tiempo o conexión cortada después de enviarla): no hay
    `usage`, pero Anthropic pudo haberla cobrado. Quien anota el gasto usa entonces el estimado."""
    try:
        import anthropic
        tipos = (anthropic.APITimeoutError, anthropic.APIConnectionError)
    except Exception:  # noqa: BLE001 — sin el SDK no hay llamada que pudo cobrarse
        tipos = ()
    return bool(getattr(error, "sin_respuesta", False)) or (bool(tipos) and isinstance(error, tipos))


def _correccion_de_siempre(error):
    return f"Tu respuesta anterior no sirvió ({error}). Responde solo el JSON pedido."


def llamar_con_correccion(content, system_, parsear_fn, llamar=None, correccion=None):
    """(resultado, tokens_entrada, tokens_salida) de una llamada a Claude con UNA corrección como mucho, y solo si la
    respuesta no sirve (no es JSON o le falta lo pedido: `parsear_fn` lanza AnalisisInvalido). La de Triple Whale y la
    de Meta rendimiento comparten este camino (no se copia). Una respuesta que sirve nunca se paga dos veces: lo que
    haya que marcar en ella (p. ej. cifras sin dato) se marca, no se corrige con otra llamada (E2-R5).

    `llamar(content, system_) -> (texto, entrada, salida)`; por defecto `_llamar`. `correccion(error) -> texto` es lo
    que se le pide a Claude en la corrección; por defecto «Responde solo el JSON pedido» (Meta pide el JSON completo:
    con ese texto 2 de 3 correcciones medidas llegaron sin ideas, eval 2026-10-10). Si la corrección tampoco sirve, o
    su llamada falla, AnalisisInvalido con los tokens ya pagados (`sin_respuesta=True` si la corrección se quedó sin
    respuesta: pudo cobrarse). Cualquier otra excepción después de que Claude respondió (un parser que revienta) sale
    también con los tokens pagados (`anotar_tokens`)."""
    llamar = llamar or _llamar
    crudo, entrada, salida = llamar(content, system_)
    pagado = [entrada, salida]
    try:
        return _con_una_correccion(content, system_, parsear_fn, llamar, crudo, pagado,
                                   correccion or _correccion_de_siempre)
    except Exception as e:
        anotar_tokens(e, *pagado)
        raise


def _con_una_correccion(content, system_, parsear_fn, llamar, crudo, pagado, correccion):
    """El cuerpo de `llamar_con_correccion` tras la primera respuesta; `pagado` ([entrada, salida]) se actualiza en
    su lugar con lo que cobra la corrección."""
    try:
        return parsear_fn(crudo), pagado[0], pagado[1]
    except AnalisisInvalido as e:
        error = e
    pedido = content + [{"type": "text", "text": correccion(error)}]
    try:
        crudo, e2, s2 = llamar(pedido, system_)
    except Exception as e_llamada:
        if sin_respuesta(e_llamada):
            error.sin_respuesta = True
        raise error from None
    pagado[0], pagado[1] = pagado[0] + e2, pagado[1] + s2
    return parsear_fn(crudo), pagado[0], pagado[1]


def analizar(marca, contexto, anuncios, medios, idioma, bloques=None, productos=None):
    """(resultado, tokens_entrada, tokens_salida). Una corrección si la primera
    respuesta no sirve; si tampoco, AnalisisInvalido con los tokens pagados."""
    texto, imagenes = armar(marca, contexto, anuncios, medios, bloques=bloques, productos=productos)
    content = [{"type": "text", "text": texto}] + imagenes
    validas = {a["ref"] for a in anuncios}
    return llamar_con_correccion(content, system(idioma), lambda crudo: parsear(crudo, validas, texto))


def texto_error(error):
    """Lo que ve la persona cuando el análisis falla (sin tokens ni rutas)."""
    if isinstance(error, AnalisisInvalido):
        return gettext("Claude no devolvió un análisis que se pueda usar. Puedes intentarlo otra vez.")
    return gettext("No se pudo hacer el análisis: %(error)s", error=type(error).__name__)

"""Final edition: localización, producción y render de piezas finales por
idioma/país a partir de un clon de creative flow.

Orquestador de las capas (`guion` -> `cortes` -> `voz` -> `musica` -> `texto`
-> `render`) y del estado en la base (`creative_flow.crear_final` /
`actualizar_final`). Dos entradas:

  preparar_guion(cliente, cf_id, opciones) -> (guion_base, costo_usd)
      Escribe el guion base (idioma base) con lo que hay en la sesión y lo
      guarda en el concepto. Se hace UNA vez por sesión; cada idioma/país
      después solo localiza.

  producir(cliente, cf_id, idioma, pais, opciones, on_etapa) -> (final_id, resumen)
      Produce una pieza final. Voz y música son degradables: si fallan la
      pieza sale igual sin esa capa (`estado="degradada"`). Guion, cortes,
      texto y render no: la pieza queda en `error` y la excepción se relanza.

Las capas se invocan siempre como atributo de su módulo (`voz.sintetizar`,
`render.componer`, ...) para que las pruebas puedan sustituirlas una a una.
"""
import os
import shutil

import requests

import catalogo_productos
import creative_flow
import marca
import proyectos
from final_edition import cortes, guion as guion_mod, musica, render, texto, tipos, voz
from providers import fal_audio
from storage import r2_uploader

# Monkeypatchable en pruebas: raíz bajo la que viven salidas/ y clientes/.
BASE_DIR = tipos.BASE_DIR

# (nombre, duración estimada en s) — el mismo orden en que se ejecutan.
ETAPAS_FINAL = (
    ("Escribiendo el guion", 10),
    ("Cortes", 5),
    ("Voz", 25),
    ("Música", 15),
    ("Texto y render", 45),
)

COLOR_ACENTO_DEFECTO = texto.COLOR_ACENTO_DEFECTO
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
_OPCIONES_DEFECTO = {"voz": None, "estilo_musica": None, "precio": None, "precios": None, "con_voz": True,
                     "con_musica": True, "idioma_base": "es", "duracion_s": None}


# ------------------------------------------------------------------ rutas ---

def _carpeta_salidas():
    return os.environ.get("CREATV_SALIDAS") or os.path.join(BASE_DIR, "salidas")


def _carpeta_final(cliente, final_id):
    return os.path.join(_carpeta_salidas(), cliente, "finales", final_id)


def _clon_local(cliente, cf_id, entry):
    """Ruta local del clon: `video_local` si existe; si no, descarga
    `video_url` una vez a salidas/<cliente>/finales/clones/<cf_id>.mp4."""
    local = entry.get("video_local")
    if local and os.path.exists(local):
        return local
    url = entry.get("video_url")
    if not url:
        raise ValueError(f"La sesión {cf_id} no tiene video listo para producir.")
    destino = os.path.join(_carpeta_salidas(), cliente, "finales", "clones", f"{cf_id}.mp4")
    if os.path.exists(destino):
        return destino
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    tmp = destino + ".parcial"
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(1024 * 256):
            f.write(chunk)
    os.replace(tmp, destino)
    return destino


def _logo_local(cliente, carpeta):
    """Primer logo del proyecto (clientes/<c>/logos/, misma convención que
    `dashboard._logos` pero sin importar dashboard), copiado a la carpeta de
    trabajo. None si no hay."""
    origen = os.path.join(BASE_DIR, "clientes", cliente, "logos")
    if not os.path.isdir(origen):
        return None
    for nombre in sorted(os.listdir(origen)):
        low = nombre.lower()
        if low.endswith(".frame.jpg") or not low.endswith(IMAGE_EXTS):
            continue
        os.makedirs(carpeta, exist_ok=True)
        destino = os.path.join(carpeta, "logo" + os.path.splitext(nombre)[1].lower())
        shutil.copy(os.path.join(origen, nombre), destino)
        return destino
    return None


def _color_acento(cliente):
    try:
        datos = proyectos.cargar(cliente)
    except Exception:
        return COLOR_ACENTO_DEFECTO
    return datos.get("color_acento") or COLOR_ACENTO_DEFECTO


def _guia_marca(cliente):
    """Guía de estilo efectiva del cliente para inyectar en el prompt del
    guion. Un `root.json` de marca corrupto es un extra, no algo que deba
    tumbar la escritura del guion: se degrada a "" (M6)."""
    try:
        return marca.guia_efectiva(cliente) or ""
    except (OSError, ValueError):
        return ""


# ---------------------------------------------------------------- sesión ---

def _sesion(cliente, cf_id):
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        raise ValueError(f"No existe la sesión {cf_id} de {cliente}.")
    return entry


def _producto(cliente, entry, precio):
    """{"nombre","descripcion","precio","moneda","beneficios","tipo"} desde el
    catálogo o desde la acción central.

    `productos_ids` guarda NOMBRES visibles (no ids), y puede mezclar
    productos con personajes/entornos — se busca cada uno primero por id en
    la categoría "producto" (compatibilidad con sesiones viejas) y si no,
    por nombre entre los productos del catálogo. Si nada resuelve, se cae a
    la primera referencia con categoria=="producto" (el nombre del activo
    tal como quedó en la sesión) y luego a la acción central."""
    ids = entry.get("productos_ids") or []
    p = None
    nombre_activo = None
    for x in ids:
        p = catalogo_productos.encontrar(cliente, x, categoria="producto")
        if p:
            nombre_activo = x
            break
        for cand in catalogo_productos.listar(cliente, "producto"):
            if cand.get("nombre") == x:
                p, nombre_activo = cand, x
                break
        if p:
            break
    if not p:
        for r in entry.get("referencias") or []:
            if r.get("categoria") == "producto" and r.get("activo"):
                nombre_activo = r["activo"]
                break
    if p:
        return {"nombre": p.get("nombre") or nombre_activo, "descripcion": p.get("descripcion") or "",
                "precio": precio, "moneda": None, "beneficios": [], "tipo": p.get("tipo")}
    if nombre_activo:
        return {"nombre": nombre_activo, "descripcion": "", "precio": precio, "moneda": None,
                "beneficios": [], "tipo": None}
    accion = entry.get("accion_central") or ""
    return {"nombre": accion[:60], "descripcion": accion, "precio": precio, "moneda": None,
            "beneficios": [], "tipo": None}


def _referencia(entry, idioma_base):
    referencias = [r for r in (entry.get("referencias") or [])
                   if not r.get("logo") and r.get("tipo") != "logo"]
    frames = [r["frame_url"] for r in referencias if r.get("frame_url")]
    transcripcion, costo = None, 0.0
    for r in referencias:
        if r.get("tipo") == "video" and r.get("url"):
            try:
                t = fal_audio.transcribir_palabras(r["url"], idioma_base) or {}
                transcripcion = t.get("texto") or None
                costo = float(t.get("costo_usd") or 0.0)
            except Exception:
                transcripcion = None  # la transcripción es un extra: sin ella el guion sale igual
            break
    if not frames and not transcripcion:
        return None, costo
    return {"frames": frames, "transcripcion": transcripcion}, costo


def _opciones(opciones):
    o = dict(_OPCIONES_DEFECTO)
    o.update(opciones or {})
    return o


# ------------------------------------------------------------------- API ---

def preparar_guion(cliente, cf_id, opciones=None):
    """Guion base de la sesión (capa 0). Devuelve `(guion_base, costo_usd)` y
    lo deja guardado en el concepto (`creative_flow.guardar_guion_base`)."""
    o = _opciones(opciones)
    entry = _sesion(cliente, cf_id)
    idioma_base = o.get("idioma_base") or "es"
    producto = _producto(cliente, entry, o.get("precio"))
    referencia, costo = _referencia(entry, idioma_base)
    duracion_s = o.get("duracion_s") or cortes.duracion(_clon_local(cliente, cf_id, entry))
    enfoque = entry.get("enfoque") or "producto"

    guion_base, costo_guion = guion_mod.generar_guion_base(
        producto, referencia, enfoque, float(duracion_s), idioma_base,
        _guia_marca(cliente), entry.get("tono") or "")
    costo += float(costo_guion or 0.0)
    # El precio escrito al preparar viaja con el guion base para prellenar el
    # destino del país base al producir (los demás países piden el suyo).
    guion_base["precio_base"] = o.get("precio")
    creative_flow.guardar_guion_base(cliente, cf_id, guion_base)
    return guion_base, round(costo, 4)


def producir(cliente, cf_id, idioma, pais, opciones=None, on_etapa=None):
    """Produce la pieza final `idioma`/`pais` de la sesión. Devuelve
    `(final_id, resumen)`; `resumen` es el dict de `creative_flow.finales`.
    `on_etapa(nombre)` se llama antes de cada etapa de `ETAPAS_FINAL`."""
    o = _opciones(opciones)
    entry = _sesion(cliente, cf_id)
    avisar = on_etapa or (lambda nombre: None)

    final_id = creative_flow.crear_final(cliente, cf_id, idioma, pais)
    costo = 0.0
    guion_base = None
    guion = None
    capas = {}
    degradada = False

    avisar(ETAPAS_FINAL[0][0])
    try:
        # Guion base (una vez por sesión) — si aún no existe se escribe aquí.
        guion_base = creative_flow.guion_base(cliente, cf_id)
        if not guion_base:
            guion_base, costo_base = preparar_guion(cliente, cf_id, o)
            costo += costo_base
    except Exception as e:
        capas["guion"] = {"proveedor": "anthropic", "parametros": {}, "costo_usd": 0.0,
                          "estado": "error", "error": str(e)}
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=str(e), capas=capas)
        raise
    carpeta = _carpeta_final(cliente, final_id)
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta, exist_ok=True)

    def capa(nombre, proveedor, parametros, costo_capa=0.0, estado="ok", error=None):
        capas[nombre] = {"proveedor": proveedor, "parametros": parametros,
                         "costo_usd": round(float(costo_capa or 0.0), 4), "estado": estado, "error": error}

    try:
        # 0. Guion localizado — precio por destino (I1): la moneda del país
        # base y la del destino casi nunca coinciden, así que un solo precio
        # no se convierte de una a otra. `opciones["precios"]` trae un valor
        # por destino (clave "<idioma>_<pais>"); `opciones["precio"]` es un
        # atajo que solo aplica al país base del guion (misma moneda), nunca
        # a los demás destinos.
        precios_por_destino = o.get("precios") or {}
        clave_destino = f"{idioma}_{pais}"
        if clave_destino in precios_por_destino:
            precio = precios_por_destino.get(clave_destino)
        elif pais == (guion_base or {}).get("pais"):
            precio = o.get("precio")
            if precio is None:
                precio = (guion_base or {}).get("precio_base")
        else:
            precio = None
        try:
            guion, c = guion_mod.localizar_guion(guion_base, idioma, pais, precio)
        except Exception as e:
            capa("guion", "anthropic", {"idioma": idioma, "pais": pais, "precio": precio}, estado="error", error=str(e))
            raise
        costo += float(c or 0.0)
        capa("guion", "anthropic", {"idioma": idioma, "pais": pais, "precio": precio}, c)

        # 1. Cortes y plan de segmentos
        avisar(ETAPAS_FINAL[1][0])
        try:
            clon = _clon_local(cliente, cf_id, entry)
            duracion_clon = cortes.duracion(clon)
            fin_guion = (guion.get("bloques") or [{}])[-1].get("fin_s") or duracion_clon
            cortes_t = cortes.detectar_cortes(clon)
            segmentos = cortes.planificar_segmentos(duracion_clon, cortes_t, float(fin_guion))
            if not segmentos:
                raise RuntimeError("El clon no da para ningún segmento.")
            duracion_final = float(segmentos[-1]["fin"])
        except Exception as e:
            capa("cortes", "ffmpeg", {}, estado="error", error=str(e))
            raise
        capa("cortes", "ffmpeg", {"cortes": cortes_t, "segmentos": len(segmentos)})

        # 2. Voz (degradable)
        avisar(ETAPAS_FINAL[2][0])
        archivo_voz, palabras = None, []
        nombre_voz = o.get("voz") or (fal_audio.VOCES.get(idioma) or fal_audio.VOCES["es"])[0]
        if not o.get("con_voz", True):
            capa("voz", "fal/elevenlabs", {"voz": nombre_voz}, estado="omitida")
        else:
            try:
                salida_voz, c = voz.sintetizar(guion, nombre_voz, os.path.join(carpeta, "voz"), cliente=cliente)
                archivo_voz = salida_voz.get("archivo_voz")
                palabras = salida_voz.get("palabras") or []
                costo += float(c or 0.0)
                capa("voz", "fal/elevenlabs", {"voz": nombre_voz}, c)
            except voz.ErrorPrimerBloque as e:
                # El primer bloque (hook) falló: casi siempre algo
                # determinístico (voz inválida para fal/ElevenLabs, texto
                # vacío) que fallaría igual en cualquier otro bloque —
                # degradar aquí solo pagaría música por una pieza que de
                # todos modos sale sin voz. Es fatal: no se genera música.
                capa("voz", "fal/elevenlabs", {"voz": nombre_voz}, estado="error", error=str(e))
                raise ValueError(
                    f"No se pudo generar la voz (revisa la voz elegida, '{nombre_voz}'): {e}"
                ) from e
            except Exception as e:
                degradada = True
                archivo_voz, palabras = None, []
                capa("voz", "fal/elevenlabs", {"voz": nombre_voz}, estado="error", error=str(e))

        # 3. Música (degradable)
        avisar(ETAPAS_FINAL[3][0])
        pista_musica = None
        estilo = o.get("estilo_musica")
        if not estilo:
            producto = _producto(cliente, entry, precio)
            estilo = musica.elegir_estilo(producto.get("tipo"), entry.get("enfoque"))
        if not o.get("con_musica", True):
            capa("musica", "fal/stable-audio", {"estilo": estilo}, estado="omitida")
        else:
            try:
                pista, c = musica.obtener_pista(estilo, duracion_final)
                pista_musica = pista.get("archivo")
                costo += float(c or 0.0)
                capa("musica", "fal/stable-audio", {"estilo": estilo, "url": pista.get("url")}, c)
            except Exception as e:
                degradada = True
                pista_musica = None
                capa("musica", "fal/stable-audio", {"estilo": estilo}, estado="error", error=str(e))

        # 4. Texto en pantalla + 5. Render
        avisar(ETAPAS_FINAL[4][0])
        ancho, alto = _TAMANOS.get(entry.get("aspect_ratio") or "9:16", _TAMANOS["9:16"])
        try:
            marca_textos = {"color_acento": _color_acento(cliente), "logo_path": _logo_local(cliente, carpeta)}
            overlays = texto.generar_overlays(guion, palabras, marca_textos, os.path.join(carpeta, "overlays"), ancho, alto)
        except Exception as e:
            capa("texto", "pillow", {"ancho": ancho, "alto": alto}, estado="error", error=str(e))
            raise
        capa("texto", "pillow", {"ancho": ancho, "alto": alto, "logo": bool(marca_textos["logo_path"])})

        salida_mp4 = os.path.join(carpeta, f"{final_id}.mp4")
        try:
            resultado = render.componer(clon, segmentos, overlays, archivo_voz, pista_musica, salida_mp4,
                                        duracion_final, ancho, alto)
            key = f"clientes/{cliente}/finales/{final_id}"
            url_video = r2_uploader.upload_video(resultado["archivo"], key + ".mp4")
            url_miniatura = r2_uploader.upload_image(resultado["miniatura"], key + ".png")
        except Exception as e:
            capa("render", "ffmpeg", {"ancho": ancho, "alto": alto}, estado="error", error=str(e))
            raise
        capa("render", "ffmpeg", {"ancho": ancho, "alto": alto, "con_voz": bool(archivo_voz),
                                  "con_musica": bool(pista_musica)})
    except Exception as e:
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=str(e), capas=capas,
                                       costo_usd=round(costo, 4), guion=guion)
        raise

    creative_flow.actualizar_final(
        cliente, final_id, estado="degradada" if degradada else "listo", url_video=url_video,
        url_miniatura=url_miniatura, url_local=resultado["archivo"],
        duracion_s=float(resultado.get("duracion_s") or duracion_final), capas=capas,
        costo_usd=round(costo, 4), guion=guion, error=None)
    return final_id, creative_flow.final_por_legado(cliente, final_id)

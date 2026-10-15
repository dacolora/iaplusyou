"""
Tarea del worker para Crear › Cambiar producto (swap): genera la foto o el
video con el producto del catálogo puesto sobre lo que subió la persona.
Cuerpo movido de dashboard._lanzar_swap (la closure trabajo()); dashboard
ahora guarda el archivo, crea el swap y solo encola. Todo lo que la closure
tomaba del scope del request se relee del swap guardado (swaps.cargar) y del
catálogo.

Copiados tal cual de dashboard.py (que conserva los suyos para lo que aún usa):
`_extraer_frame`, `_texto_fase`, `_avisar_fase_de`, `_evaluar_swap_contra_matriz`
y las constantes ETAPA_*. Las listas ETAPAS_SWAP_* viven acá y dashboard las
importa (las necesita al encolar) — deben seguir siendo las mismas cadenas que
se anuncian con trabajos.reportar.
"""
import os
import subprocess

import requests
from flask_babel import gettext

import bitacora
import catalogo_productos
import gastos
import generador_prompts
import idiomas
import marca as marca_mod
import prompt_swap
import saldo
import swaps as swaps_mod
import trabajos
from idiomas import N_
from providers import aspect_ratio as aspect_ratio_mod
from providers import nano_banana_client, kling_o1_client, comparador_modelos, wavespeed_client
from providers import swap_video_precio, wavespeed_common, wavespeed_video_edit, wavespeed_imagen
from storage import r2_uploader
from tareas import al_interrumpir, ref_sufijo, registrar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Etapas reales del swap. Los nombres se usan en DOS lados (al declararlas en
# trabajos.encolar y al anunciarlas con trabajos.reportar), así que van en
# constantes para que no puedan desincronizarse por un typo. Los pesos son
# "qué fracción del tiempo se lleva más o menos cada paso" — la llamada al
# modelo es de lejos la más larga.
# Se guardan en español (N_) y estado_trabajo las traduce al mostrarlas.
ETAPA_SUBIR_ORIGINAL = N_("Subiendo tu video original")
ETAPA_SUBIR_REFERENCIAS = N_("Subiendo las fotos del producto")
ETAPA_PREPARAR_FOTO = N_("Preparando la imagen")
ETAPA_MODELO = N_("Generando con el modelo")
ETAPA_DESCARGAR = N_("Descargando el resultado")
ETAPA_GUARDAR = N_("Guardando y evaluando la marca")
ETAPA_MEJORAR = N_("Mejorando la calidad de la imagen")

ETAPAS_SWAP_VIDEO = [
    (ETAPA_SUBIR_ORIGINAL, 5),
    (ETAPA_SUBIR_REFERENCIAS, 10),
    (ETAPA_MODELO, 70),
    (ETAPA_DESCARGAR, 5),
    (ETAPA_GUARDAR, 10),
]
ETAPAS_SWAP_FOTO = [
    (ETAPA_PREPARAR_FOTO, 10),
    (ETAPA_MODELO, 70),
    (ETAPA_GUARDAR, 20),
]
# Con la mejora activada hay una llamada más al proveedor entre medio.
ETAPAS_SWAP_FOTO_MEJORADA = [
    (ETAPA_PREPARAR_FOTO, 8),
    (ETAPA_MODELO, 57),
    (ETAPA_MEJORAR, 20),
    (ETAPA_GUARDAR, 15),
]

# «Recuperar el resultado» (PND-318): vuelve a preguntar por la predicción que ya se pagó, sin lanzar otra.
ETAPA_BUSCAR = N_("Buscando el resultado en WaveSpeed")
ETAPAS_SWAP_RECUPERAR = [
    (ETAPA_BUSCAR, 70),
    (ETAPA_DESCARGAR, 15),
    (ETAPA_GUARDAR, 15),
]
TIEMPO_RECUPERAR = 120
# Los swaps que van por WaveSpeed (los únicos que se pueden recuperar por su id) y el nombre de cada modelo.
MODELOS_WAVESPEED = {
    "wan27_edit": "Wan 2.7 Video Edit",
    **{k: v["nombre"] for k, v in wavespeed_video_edit.MODELOS.items()},
    "nano_banana_pro_ultra": "Nano Banana Pro Ultra",
    "seedream_v5_pro": "Seedream V5.0 Pro Edit",
}
ESTADOS_FALLIDOS = ("failed", "cancelled", "timeout", "deleted")


class SwapEnEspera(RuntimeError):
    """PND-318: el worker dejó de esperar y el proveedor sigue con el pedido (y lo cobra igual). Lleva el costo
    previsto para anotarlo (sin cobrárselo al cliente) y, si es de WaveSpeed, el id para «Recuperar el
    resultado» sin pagar de nuevo. Su texto se guarda en la tarjeta (idioma del proyecto)."""

    def __init__(self, nombre_modelo, prediction_id, costo, recuperable=True):
        self.nombre_modelo, self.prediction_id, self.costo, self.recuperable = (nombre_modelo, prediction_id,
                                                                                costo, recuperable)
        if recuperable:
            texto = gettext("%(modelo)s sigue trabajando en este swap y lo cobra igual. Toca «Recuperar el "
                            "resultado» en unos minutos: no se paga de nuevo y no se te cobra hasta que llegue.",
                            modelo=nombre_modelo)
        else:
            texto = gettext("%(modelo)s siguió trabajando en este swap después de que dejamos de esperar. No se "
                            "puede recuperar desde aquí y no se te cobró.", modelo=nombre_modelo)
        super().__init__(texto)


def _al_agotarse(e, proveedor, costo_previsto):
    """La espera del modelo principal se agotó (PND-318): se pregunta UNA vez a WaveSpeed cómo va el pedido.
    Terminado → su URL (se entrega como siempre); fallido → ErrorProveedor (no cobró); en curso o sin poder
    preguntar → SwapEnEspera (lo cobra igual). Un pedido de fal que fal va a cobrar → SwapEnEspera sin
    recuperar; uno que fal canceló a tiempo sube tal cual."""
    if isinstance(e, wavespeed_common.EsperaAgotada):
        try:
            data = wavespeed_common.consultar(e.prediction_id)
        except Exception:  # noqa: BLE001 — sin poder preguntar, WaveSpeed casi siempre termina y cobra
            data = {}
        estado = data.get("status")
        if estado == "completed" and data.get("outputs"):
            return data["outputs"][0]
        if estado in ESTADOS_FALLIDOS:
            raise wavespeed_common.ErrorProveedor(e.nombre_modelo, estado, detalle=data.get("error") or None,
                                                  codigo=data.get("code"), prediction_id=e.prediction_id,
                                                  datos=data) from e
        raise SwapEnEspera(e.nombre_modelo, e.prediction_id, costo_previsto,
                           recuperable=proveedor in MODELOS_WAVESPEED) from e
    if getattr(e, "cobrado", False):
        raise SwapEnEspera(getattr(e, "model_path", proveedor), getattr(e, "request_id", None), costo_previsto,
                           recuperable=False) from e
    raise e


def _esperas():
    """Las esperas agotadas que `_al_agotarse` sabe atender (la de fal llega con PND-313)."""
    from providers import fal_client  # noqa: PLC0415
    return (wavespeed_common.EsperaAgotada, getattr(fal_client, "EsperaAgotadaFal", wavespeed_common.EsperaAgotada))


# Los proveedores hablan en sus propios códigos de estado; esto es lo único
# honesto que se puede mostrar de ellos (ninguno da un porcentaje numérico).
_FASES_PROVEEDOR = {
    "IN_QUEUE": N_("en cola"),
    "IN_PROGRESS": N_("el modelo está trabajando"),
    "created": N_("en cola"),
    "processing": N_("el modelo está trabajando"),
    "queued": N_("en cola"),
    "starting": N_("arrancando"),
    "running": N_("el modelo está trabajando"),
    "in_progress": N_("el modelo está trabajando"),
    "pending": N_("en cola"),
}

# Estados terminales: el poll también los emite en su última vuelta, pero mostrar
# "completed" como detalle no le dice nada al usuario — la etapa siguiente ya se
# encarga de contar qué sigue.
_FASES_TERMINALES = ("COMPLETED", "completed", "succeeded", "success", "done")


def _texto_fase(info):
    """Traduce al idioma del proyecto (el worker ya corre en él) el estado crudo
    que reporta un proveedor durante el poll.
    Con fallback: si aparece una fase que no conocemos se muestra tal cual en vez
    de tragarse la información (los proveedores agregan estados sin avisar)."""
    if not info:
        return None
    fase = info.get("fase")
    if fase in _FASES_TERMINALES:
        return None
    texto = idiomas.traducir(_FASES_PROVEEDOR.get(fase, fase))
    if not texto:
        return None
    posicion = info.get("queue_position")
    if posicion is not None:
        texto = gettext("%(fase)s (puesto %(n)s)", fase=texto, n=posicion)
    return texto


def _avisar_fase_de(job_id, guardar_prediccion=None):
    """Devuelve el callback on_progreso que esperan los clientes de proveedores
    (Higgsfield, fal.ai, WaveSpeed): traduce la fase cruda del poll y la publica
    como detalle del trabajo. Envuelto en try/except porque un fallo REPORTANDO
    jamás puede tumbar una generación que ya gastó créditos.
    `guardar_prediccion(id)` (PND-318): se llama una vez por id nuevo, apenas el
    proveedor lo devuelve, para que el swap lo tenga aunque la espera se agote."""
    vista = {"id": None}

    def avisar_fase(info):
        try:
            pid = (info or {}).get("prediction_id")
            if guardar_prediccion and pid and pid != vista["id"]:
                vista["id"] = pid
                guardar_prediccion(pid)
        except Exception:
            pass
        try:
            texto = _texto_fase(info)
            if texto:
                trabajos.reportar(job_id, detalle=texto)
        except Exception:
            pass
    return avisar_fase


def _extraer_frame(video_path, frame_path, segundo=1.0):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(segundo), "-i", video_path, "-frames:v", "1", "-q:v", "2", frame_path],
        check=True, capture_output=True,
    )


def _evaluar_swap_contra_matriz(cliente, swap_id, image_url):
    """Corre la evaluación de marca sobre una imagen (foto final, o un fotograma
    extraído de un video final) y guarda el resultado. No falla el swap si esto
    falla — es un plus, no el resultado principal."""
    # El desenlace se PERSISTE (evaluacion_estado), no solo se anota en la
    # bitácora: sin eso, un fallo silencioso dejaba la tarjeta diciendo
    # "Evaluando cumplimiento de marca…" para siempre, porque `evaluacion` se
    # quedaba en None y nada volvía a tocar esa entrada. Hoy hay 6 swaps así en
    # disco. Lo mismo cuando el cliente no tiene invariantes definidas: no es un
    # error, pero la evaluación tampoco va a llegar nunca.
    try:
        root = marca_mod.cargar_root(cliente)
        invariantes = root.get("invariants", []) if root else []
        if not invariantes:
            swaps_mod.actualizar(cliente, swap_id, evaluacion_estado="sin_matriz")
            return
        evaluacion = generador_prompts.evaluar_contra_matriz(image_url, invariantes)
        swaps_mod.actualizar(cliente, swap_id, evaluacion=evaluacion, evaluacion_estado="ok")
        bitacora.registrar(cliente, swap_id, "evaluacion", "ok", "")
    except Exception as e:
        swaps_mod.actualizar(cliente, swap_id, evaluacion_estado="error", evaluacion_error=str(e))
        bitacora.registrar(cliente, swap_id, "evaluacion", "error", str(e))


@al_interrumpir("swap_generar")
def interrumpida(tarea, mensaje):
    """El worker murió a mitad del swap: sin esto la tarjeta queda en
    `generando` para siempre. En error, con motivo, se puede volver a lanzar."""
    cliente, swap_id = tarea["payload"]["cliente"], tarea["payload"]["swap_id"]
    swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje)


@registrar("swap_generar")
def ejecutar(tarea):
    """Genera un swap ya creado por dashboard._lanzar_swap. Reconstruye las
    variables que la closure vieja tomaba del scope del request y después
    corre el mismo cuerpo, sin cambios de lógica."""
    payload = tarea["payload"]
    cliente = payload["cliente"]
    swap_id = payload["swap_id"]
    producto_id = payload["producto_id"]
    proveedor = payload["proveedor"]
    tipo = payload["tipo"]
    mejorar_calidad = bool(payload.get("mejorar_calidad"))
    job_id = tarea["job_id"]
    ref = f"swap:{swap_id}{ref_sufijo(tarea)}"
    # Distinto de `mejorar_calidad` (lo que se pidió): esto es si el upscale
    # de verdad corrió y se cobró — si revienta, el swap sale igual sin la
    # mejora y el detalle del gasto no puede decir "con mejora" de algo que
    # no se pagó.
    mejora_ok = False

    entry = swaps_mod.cargar(cliente)[swap_id]
    foto_local = entry["foto_original_local"]
    # En dashboard el archivo se guardó como f"{ts}_{nombre}"; acá ya solo
    # existe la ruta, así que la clave de R2 sale del nombre en disco.
    nombre_subida = os.path.basename(foto_local)
    producto = catalogo_productos.encontrar(cliente, producto_id)
    if producto is None:
        # Lo borraron del catálogo entre encolar y ejecutar: sin referencias no
        # hay nada que generar, y el swap no puede quedar "generando" por siempre.
        mensaje = gettext("El producto ya no está en el catálogo; no se generó el swap.")
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje)
        bitacora.registrar(cliente, swap_id, "swap", "error", mensaje)
        return mensaje

    # Cada etapa se anuncia con trabajos.reportar(job_id, ...) para que la barra
    # deje de ser un número inventado: el usuario ve en qué paso real va.
    avisar_fase = _avisar_fase_de(job_id)

    def _guardar_prediccion(pid):
        swaps_mod.actualizar(cliente, swap_id, prediccion={"id": pid, "proveedor": proveedor,
                                                           "referencia_gasto": ref, "en": _ahora()})
    # Solo el modelo principal guarda su id (la mejora de calidad es otra predicción).
    avisar_modelo = _avisar_fase_de(job_id, guardar_prediccion=_guardar_prediccion)
    # None hasta que el proveedor cobró: si algo falla después, el gasto se
    # registra igual (el cobro ya ocurrió).
    costo = None

    try:
        # os.makedirs y negative_prompt_efectivo estaban FUERA del try:
        # negative_prompt_efectivo lee marca/root.json y revienta si ese
        # archivo está mal formado, dejando el job en "error" pero el swap
        # en "generando" para siempre en disco (tarjeta zombie).
        resultados_dir = os.path.join(BASE_DIR, "salidas", cliente, "swaps")
        os.makedirs(resultados_dir, exist_ok=True)
        negative_prompt = marca_mod.negative_prompt_efectivo(cliente)
        # El TIPO del producto decide qué prompt se arma: un calzado va en
        # los pies y no puede sobresalir del contorno del pie; una cobija se
        # drapea sobre la persona o el mueble y sigue sus pliegues.
        tipo_producto = producto.get("tipo")
        # Instrucción de ubicación y proporción derivada del mapa corporal.
        # None si el producto no va sobre una persona (cobija, objeto).
        mapa_producto = producto.get("mapa_texto")
        # Si la subida a R2 falla, el resultado SÍ existe en disco. Se guarda
        # el motivo para que la plantilla pueda decir la verdad ("se generó
        # pero no se pudo subir, está acá") en vez de dar por muerta una
        # generación que sí terminó y ya se pagó.
        error_storage = None

        if tipo == "video":
            local_path = os.path.join(resultados_dir, f"{swap_id}.mp4")
            # Lo que cobra el proveedor depende de cuánto dura el video subido (PND-312): la medida que guardó
            # dashboard._lanzar_swap, o se mide aquí (un swap encolado antes del cambio). Sin medida, 5 s como antes.
            duracion_in, fps_in = entry.get("duracion_s"), entry.get("fps")
            if not duracion_in:
                duracion_in, fps_in = swap_video_precio.medir(foto_local)
            duracion_in = duracion_in or 5
            trabajos.reportar(job_id, etapa=ETAPA_SUBIR_ORIGINAL)
            video_url = r2_uploader.upload_video(foto_local, f"clientes/{cliente}/swaps_subidas/{nombre_subida}")
            # Se suben hasta 9 (el máximo que acepta Wan 2.7 Video Edit) — cada
            # cliente recorta a su propio límite (Kling O1 usa las primeras 4).
            referencias = producto["referencias"][:9]
            trabajos.reportar(job_id, etapa=ETAPA_SUBIR_REFERENCIAS)
            referencias_urls = []
            for i, ref_local in enumerate(referencias):
                # Son 1-2MB cada una y suben en serie: sin este detalle el
                # tramo se percibía como una barra colgada.
                trabajos.reportar(
                    job_id,
                    progreso=100.0 * i / len(referencias),
                    detalle=gettext("foto %(n)s de %(total)s", n=i + 1, total=len(referencias)),
                )
                key = f"clientes/{cliente}/productos/{producto_id}/{os.path.basename(ref_local)}"
                referencias_urls.append(r2_uploader.upload_image(ref_local, key))

            trabajos.reportar(job_id, etapa=ETAPA_MODELO)
            # El costo se calcula ANTES de llamar: si la espera se agota, es lo que se anota (PND-318).
            if proveedor == "kling_o1":
                citas = " ".join(f"@Image{i + 1}" for i in range(len(referencias_urls)))
                prompt = prompt_swap.prompt_video(tipo_producto, citas=citas, mapa=mapa_producto)
                previsto = kling_o1_client.estimate_video(duracion_in, fps_in)
                llamar = lambda: kling_o1_client.editar_video(  # noqa: E731
                    video_url, prompt, referencias_urls=referencias_urls, on_progreso=avisar_modelo,
                )
            elif proveedor == "wan27_edit":
                prompt = prompt_swap.prompt_video(tipo_producto, mapa=mapa_producto)
                previsto = wavespeed_client.estimate_video(duracion_in, fps_in)
                llamar = lambda: wavespeed_client.editar_video(  # noqa: E731
                    video_url, prompt, referencias_urls=referencias_urls, on_progreso=avisar_modelo,
                )
            elif proveedor in wavespeed_video_edit.MODELOS:
                prompt = prompt_swap.prompt_video(tipo_producto, mapa=mapa_producto)
                previsto = wavespeed_video_edit.estimate_video(proveedor, duracion_in, fps_in)
                llamar = lambda: wavespeed_video_edit.editar_video(  # noqa: E731
                    proveedor, video_url, prompt, referencias_urls=referencias_urls,
                    on_progreso=avisar_modelo,
                )
            else:
                referencia = referencias_urls[0] if referencias_urls else None
                previsto = comparador_modelos.estimate_video(proveedor, duracion_in, fps_in)
                llamar = lambda: comparador_modelos.editar_video(  # noqa: E731
                    proveedor, video_url, producto["descripcion"], referencia_imagen_url=referencia,
                    on_progreso=avisar_modelo, tipo=tipo_producto, mapa=mapa_producto,
                )
            try:
                resultado_url = llamar()
            except _esperas() as e:
                resultado_url = _al_agotarse(e, proveedor, previsto)
            costo = previsto

            trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
            resp = requests.get(resultado_url, timeout=180)
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                f.write(resp.content)
            trabajos.reportar(job_id, etapa=ETAPA_GUARDAR)
            try:
                url = r2_uploader.upload_video(local_path, f"clientes/{cliente}/swaps/{swap_id}.mp4")
            except Exception as e:
                # Acá sí hay plan B: la URL del proveedor sirve igual para
                # mostrar y publicar, así que no queda "listo sin url".
                url = resultado_url
                error_storage = str(e)
                bitacora.registrar(cliente, swap_id, "storage", "error", str(e))
        else:
            local_path = os.path.join(resultados_dir, f"{swap_id}.png")
            trabajos.reportar(job_id, etapa=ETAPA_PREPARAR_FOTO)
            if proveedor == "nano_banana":
                trabajos.reportar(job_id, etapa=ETAPA_MODELO)
                img_bytes = nano_banana_client.swap_producto(
                    foto_local, producto["referencias"], negative_prompt=negative_prompt,
                    tipo=tipo_producto, mapa=mapa_producto,
                )
                with open(local_path, "wb") as f:
                    f.write(img_bytes)
                costo = nano_banana_client.estimate_image()
            else:  # nano_banana_fal, qwen_edit, nano_banana_pro_ultra
                foto_url = r2_uploader.upload_image(foto_local, f"clientes/{cliente}/swaps_subidas/{nombre_subida}")
                # Nano Banana Pro Ultra acepta hasta 14 imágenes (13 de
                # referencia + la foto); los de fal solo 2. Se sube lo que
                # cada uno puede aprovechar, ni una más.
                if proveedor == "nano_banana_pro_ultra":
                    tope_refs = 13
                elif proveedor == "seedream_v5_pro":
                    tope_refs = 9   # acepta 10 en total, una la ocupa la foto
                else:
                    tope_refs = 2
                referencias_urls = [
                    r2_uploader.upload_image(ref, f"clientes/{cliente}/productos/{producto_id}/{os.path.basename(ref)}")
                    for ref in producto["referencias"][:tope_refs]
                ]
                trabajos.reportar(job_id, etapa=ETAPA_MODELO)
                if proveedor == "nano_banana_pro_ultra":
                    referencias_lista = "\n".join(
                        f"Imagen {i + 2}: referencia del producto (mismo producto, otro ángulo)."
                        for i in range(len(referencias_urls))
                    )
                    previsto = wavespeed_imagen.estimate_image()
                    llamar = lambda: wavespeed_imagen.editar_imagen(  # noqa: E731
                        foto_url, prompt_swap.prompt_imagen(tipo_producto, referencias_lista, mapa=mapa_producto),
                        referencias_urls=referencias_urls,
                        aspect_ratio=aspect_ratio_mod.detectar_wavespeed_nano_banana_pro(foto_local),
                        on_progreso=avisar_modelo,
                    )
                elif proveedor == "seedream_v5_pro":
                    referencias_lista = "\n".join(
                        f"Imagen {i + 2}: referencia del producto (mismo producto, otro ángulo)."
                        for i in range(len(referencias_urls))
                    )
                    previsto = wavespeed_imagen.estimate_seedream(n_imagenes=len(referencias_urls) + 1)
                    llamar = lambda: wavespeed_imagen.editar_imagen_seedream(  # noqa: E731
                        foto_url,
                        prompt_swap.prompt_imagen(tipo_producto, referencias_lista, mapa=mapa_producto),
                        referencias_urls=referencias_urls, on_progreso=avisar_modelo,
                    )
                else:
                    previsto = comparador_modelos.estimate_image(proveedor)
                    llamar = lambda: comparador_modelos.editar_imagen(  # noqa: E731
                        proveedor, foto_url, producto["descripcion"], referencias_urls=referencias_urls,
                        foto_local_path=foto_local, on_progreso=avisar_modelo, tipo=tipo_producto,
                        mapa=mapa_producto,
                    )
                try:
                    resultado_url = llamar()
                except _esperas() as e:
                    resultado_url = _al_agotarse(e, proveedor, previsto)
                costo = previsto
                trabajos.reportar(job_id, etapa=ETAPA_GUARDAR)
                resp = requests.get(resultado_url, timeout=120)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)

            if mejorar_calidad:
                # Segunda pasada: agranda SIN regenerar (Bria). Necesita una
                # URL pública, así que primero sube el resultado del swap a
                # R2 y después reemplaza el archivo local por el mejorado.
                trabajos.reportar(job_id, etapa=ETAPA_MEJORAR)
                mejora_pagada = False
                try:
                    url_para_mejorar = r2_uploader.upload_image(
                        local_path, f"clientes/{cliente}/swaps/{swap_id}.previo.png")
                    ancho_prev, alto_prev = aspect_ratio_mod.dimensiones(local_path)
                    try:
                        mejorada_url = wavespeed_imagen.mejorar_calidad(
                            url_para_mejorar,
                            factor=wavespeed_imagen.factor_seguro(ancho_prev, alto_prev),
                            on_progreso=avisar_fase,
                        )
                    except wavespeed_common.EsperaAgotada:
                        mejora_pagada = True   # WaveSpeed la termina y la cobra igual
                        raise
                    mejora_pagada = True
                    resp_mejorada = requests.get(mejorada_url, timeout=180)
                    resp_mejorada.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(resp_mejorada.content)
                    costo = {
                        "credits": costo.get("credits"),
                        "usd": round((costo.get("usd") or 0) + wavespeed_imagen.COSTO_USD_UPSCALE, 3),
                    }
                    mejora_ok = True
                except Exception as e:
                    # La mejora es un extra: si falla, el swap YA está hecho y
                    # se entrega igual. Perder el resultado por el paso opcional
                    # sería tirar a la basura lo que el usuario ya pagó.
                    bitacora.registrar(cliente, swap_id, "mejora_calidad", "error", str(e))
                    if mejora_pagada:
                        # PND-315: WaveSpeed ya cobró la mejora y no llegó: se anota aparte, sin cobrarla.
                        gastos.registrar_seguro(
                            cliente, "swap", wavespeed_imagen.COSTO_USD_UPSCALE, f"{ref}:mejora",
                            proveedor="wavespeed", entregado=False,
                            detalle=gettext("mejora de calidad pagada que no llegó (%(error)s)", error=str(e)[:120]))

            trabajos.reportar(job_id, etapa=ETAPA_GUARDAR)
            try:
                url = r2_uploader.upload_image(local_path, f"clientes/{cliente}/swaps/{swap_id}.png")
            except Exception as e:
                # Sin plan B (nano_banana devuelve bytes, no una URL): queda
                # "listo" sin resultado_url. La plantilla necesita saber que
                # el archivo existe igual, si no muestra un mensaje falso.
                url = None
                error_storage = str(e)
                bitacora.registrar(cliente, swap_id, "storage", "error", str(e))

        swaps_mod.actualizar(
            cliente, swap_id, estado="listo", resultado_url=url, resultado_local=local_path,
            credits=costo.get("credits"), usd=costo.get("usd"), error_storage=error_storage, prediccion=None,
        )
        bitacora.registrar(cliente, swap_id, "swap", "ok", local_path)
        _registrar_gasto(cliente, ref, proveedor, tipo, costo, mejora_ok)

        if url:
            if tipo == "video":
                frame_path = os.path.join(resultados_dir, f"{swap_id}.frame.jpg")
                try:
                    _extraer_frame(local_path, frame_path)
                    frame_url = r2_uploader.upload_image(frame_path, f"clientes/{cliente}/swaps/{swap_id}.frame.jpg")
                    _evaluar_swap_contra_matriz(cliente, swap_id, frame_url)
                except Exception as e:
                    bitacora.registrar(cliente, swap_id, "evaluacion", "error", str(e))
            else:
                _evaluar_swap_contra_matriz(cliente, swap_id, url)

        return gettext("Swap listo.")
    except Exception as e:
        mensaje_error = str(e)
        sufijo = " · " + gettext("falló después de generar; el proveedor ya cobró")
        campos = {}
        if isinstance(e, wavespeed_common.SinSaldo):
            # Incidente 2026-09-30: en palabras, y el administrador se entera.
            saldo.marcar(e.proveedor, e.detalle, cliente=cliente)
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
                mensaje_error = saldo.mensaje_tarjeta(e.proveedor)
        elif isinstance(e, SwapEnEspera):
            # PND-318: el proveedor sigue y cobra igual: se anota (sin cobrárselo al cliente) y, en WaveSpeed,
            # el id queda para «Recuperar el resultado», que lo trae sin pagar de nuevo y ahí lo cobra.
            costo = e.costo
            sufijo = " · " + gettext("se agotó la espera; el proveedor lo cobra igual")
            if e.recuperable and e.prediction_id:
                campos["prediccion"] = {"id": e.prediction_id, "proveedor": proveedor, "referencia_gasto": ref,
                                        "en": _ahora()}
            else:
                campos["prediccion"] = None
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje_error, **campos)
        bitacora.registrar(cliente, swap_id, "swap", "error", str(e))
        if costo is not None:
            _registrar_gasto(cliente, ref, proveedor, tipo, costo, mejora_ok, sufijo=sufijo, entregado=False)
        raise


def _ahora():
    from datetime import datetime  # noqa: PLC0415
    return datetime.now().isoformat(timespec="seconds")


def _registrar_gasto(cliente, referencia, proveedor, tipo, costo, mejora_ok, sufijo="", entregado=True):
    """`swap:<swap_id><ref_sufijo>` con el `usd` del estimate del proveedor
    (ya incluye la mejora de calidad si de verdad corrió). Un proveedor sin
    tarifa (usd None) se registra en 0 con "sin tarifa" para que quede
    constancia del cobro."""
    usd = (costo or {}).get("usd")
    partes = [proveedor, gettext("video") if tipo == "video" else gettext("foto")]
    if mejora_ok:
        partes.append(gettext("con mejora"))
    if usd is None:
        partes.append(gettext("sin tarifa"))
    detalle = " · ".join(partes)
    gastos.registrar_seguro(cliente, "swap", usd, referencia, detalle=detalle + sufijo, proveedor=proveedor,
                            entregado=entregado,
                            extra={"credits": (costo or {}).get("credits"), "sin_tarifa": usd is None})


# ------------------------------------------------------------- recuperar ---

@al_interrumpir("swap_recuperar")
def recuperar_interrumpida(tarea, mensaje):
    """Se cortó mientras preguntaba: el swap vuelve a error con su predicción (se puede volver a recuperar)."""
    cliente, swap_id = tarea["payload"]["cliente"], tarea["payload"]["swap_id"]
    swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje)


@registrar("swap_recuperar")
def recuperar(tarea):
    """«Recuperar el resultado» (PND-318, como «Recuperar el video» de Crear): vuelve a preguntar a WaveSpeed
    por la predicción que el swap ya pagó y, si terminó, lo entrega. Nunca lanza otra (no paga de nuevo).
    Lo que se anotó al agotarse la espera pasa a la fila de esta entrega y ahí se le cobra al cliente
    (`gastos.registrar_trasladando`). Si WaveSpeed no lo terminó, no cobró: lo anotado vuelve a 0."""
    p = tarea["payload"]
    cliente, swap_id = p["cliente"], p["swap_id"]
    job_id = tarea.get("job_id")
    entry = swaps_mod.cargar(cliente).get(swap_id) or {}
    pred = entry.get("prediccion") or {}
    proveedor = pred.get("proveedor") or entry.get("proveedor")
    ref_original = pred.get("referencia_gasto")
    if not pred.get("id") or proveedor not in MODELOS_WAVESPEED:
        mensaje = gettext("Este swap no tiene nada que recuperar.")
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje)
        raise RuntimeError(mensaje)
    nombre = MODELOS_WAVESPEED[proveedor]
    trabajos.reportar(job_id, etapa=ETAPA_BUSCAR)
    try:
        data = wavespeed_common.poll_hasta_listo(pred["id"], nombre, timeout_seconds=TIEMPO_RECUPERAR,
                                                 on_progreso=_avisar_fase_de(job_id))
    except wavespeed_common.ErrorProveedor as e:
        # No lo terminó: WaveSpeed no cobra un pedido fallido. Lo anotado al agotarse la espera vuelve a 0.
        if ref_original:
            gastos.registrar_seguro(cliente, "swap", 0, ref_original, proveedor=proveedor, entregado=False,
                                    detalle=gettext("%(modelo)s no terminó el swap; no cobró", modelo=nombre))
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=str(e), prediccion=None)
        raise
    except wavespeed_common.EsperaAgotada as e:
        mensaje = gettext("%(modelo)s todavía no termina este swap. Vuelve a tocar «Recuperar el resultado» en "
                          "unos minutos; no se paga de nuevo.", modelo=nombre)
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje)
        raise RuntimeError(mensaje) from e
    salidas = data.get("outputs") or []
    if not salidas:
        mensaje = gettext("%(modelo)s terminó sin devolver ningún resultado.", modelo=nombre)
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje)
        raise RuntimeError(mensaje)
    resultado_url = salidas[0]
    es_video = entry.get("tipo") == "video"
    resultados_dir = os.path.join(BASE_DIR, "salidas", cliente, "swaps")
    os.makedirs(resultados_dir, exist_ok=True)
    local_path = os.path.join(resultados_dir, f"{swap_id}.mp4" if es_video else f"{swap_id}.png")
    trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
    try:
        resp = requests.get(resultado_url, timeout=180)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        # Ya está en WaveSpeed: la predicción se conserva y se puede volver a intentar.
        mensaje = gettext("El resultado ya está listo en %(modelo)s pero no se pudo bajar: %(error)s. Vuelve a "
                          "tocar «Recuperar el resultado».", modelo=nombre, error=e)
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje)
        raise RuntimeError(mensaje) from e
    trabajos.reportar(job_id, etapa=ETAPA_GUARDAR)
    error_storage = None
    clave = f"clientes/{cliente}/swaps/{swap_id}.mp4" if es_video else f"clientes/{cliente}/swaps/{swap_id}.png"
    try:
        url = r2_uploader.upload_video(local_path, clave) if es_video else r2_uploader.upload_image(local_path, clave)
    except Exception as e:
        url, error_storage = resultado_url, str(e)
        bitacora.registrar(cliente, swap_id, "storage", "error", str(e))
    gastos.registrar_trasladando_seguro(
        cliente, "swap", 0, f"swap:{swap_id}{ref_sufijo(tarea)}",
        [{"referencia": ref_original}] if ref_original else [], proveedor=proveedor,
        detalle=" · ".join([proveedor, gettext("video") if es_video else gettext("foto"),
                            gettext("recuperado sin pagar de nuevo")]))
    pagado = (gastos.por_referencia(cliente, f"swap:{swap_id}{ref_sufijo(tarea)}") or {}).get("usd")
    swaps_mod.actualizar(cliente, swap_id, estado="listo", resultado_url=url, resultado_local=local_path,
                         error=None, error_storage=error_storage, prediccion=None,
                         **({"usd": pagado} if pagado else {}))
    bitacora.registrar(cliente, swap_id, "swap", "ok", local_path)
    if url:
        if es_video:
            frame_path = os.path.join(resultados_dir, f"{swap_id}.frame.jpg")
            try:
                _extraer_frame(local_path, frame_path)
                frame_url = r2_uploader.upload_image(frame_path, f"clientes/{cliente}/swaps/{swap_id}.frame.jpg")
                _evaluar_swap_contra_matriz(cliente, swap_id, frame_url)
            except Exception as e:
                bitacora.registrar(cliente, swap_id, "evaluacion", "error", str(e))
        else:
            _evaluar_swap_contra_matriz(cliente, swap_id, url)
    return gettext("Swap recuperado sin pagar de nuevo.")

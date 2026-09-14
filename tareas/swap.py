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

import bitacora
import catalogo_productos
import generador_prompts
import marca as marca_mod
import prompt_swap
import swaps as swaps_mod
import trabajos
from providers import aspect_ratio as aspect_ratio_mod
from providers import nano_banana_client, kling_o1_client, comparador_modelos, wavespeed_client
from providers import wavespeed_video_edit, wavespeed_imagen
from storage import r2_uploader
from tareas import registrar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Etapas reales del swap. Los nombres se usan en DOS lados (al declararlas en
# trabajos.encolar y al anunciarlas con trabajos.reportar), así que van en
# constantes para que no puedan desincronizarse por un typo. Los pesos son
# "qué fracción del tiempo se lleva más o menos cada paso" — la llamada al
# modelo es de lejos la más larga.
ETAPA_SUBIR_ORIGINAL = "Subiendo tu video original"
ETAPA_SUBIR_REFERENCIAS = "Subiendo las fotos del producto"
ETAPA_PREPARAR_FOTO = "Preparando la imagen"
ETAPA_MODELO = "Generando con el modelo"
ETAPA_DESCARGAR = "Descargando el resultado"
ETAPA_GUARDAR = "Guardando y evaluando la marca"
ETAPA_MEJORAR = "Mejorando la calidad de la imagen"

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

# Los proveedores hablan en sus propios códigos de estado; esto es lo único
# honesto que se puede mostrar de ellos (ninguno da un porcentaje numérico).
_FASES_PROVEEDOR = {
    "IN_QUEUE": "en cola",
    "IN_PROGRESS": "el modelo está trabajando",
    "created": "en cola",
    "processing": "el modelo está trabajando",
    "queued": "en cola",
    "starting": "arrancando",
    "running": "el modelo está trabajando",
    "in_progress": "el modelo está trabajando",
    "pending": "en cola",
}

# Estados terminales: el poll también los emite en su última vuelta, pero mostrar
# "completed" como detalle no le dice nada al usuario — la etapa siguiente ya se
# encarga de contar qué sigue.
_FASES_TERMINALES = ("COMPLETED", "completed", "succeeded", "success", "done")


def _texto_fase(info):
    """Traduce a español el estado crudo que reporta un proveedor durante el poll.
    Con fallback: si aparece una fase que no conocemos se muestra tal cual en vez
    de tragarse la información (los proveedores agregan estados sin avisar)."""
    if not info:
        return None
    fase = info.get("fase")
    if fase in _FASES_TERMINALES:
        return None
    texto = _FASES_PROVEEDOR.get(fase, fase)
    if not texto:
        return None
    posicion = info.get("queue_position")
    if posicion is not None:
        texto = f"{texto} (puesto {posicion})"
    return texto


def _avisar_fase_de(job_id):
    """Devuelve el callback on_progreso que esperan los clientes de proveedores
    (Higgsfield, fal.ai, WaveSpeed): traduce la fase cruda del poll y la publica
    como detalle del trabajo. Envuelto en try/except porque un fallo REPORTANDO
    jamás puede tumbar una generación que ya gastó créditos."""
    def avisar_fase(info):
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

    entry = swaps_mod.cargar(cliente)[swap_id]
    foto_local = entry["foto_original_local"]
    # En dashboard el archivo se guardó como f"{ts}_{nombre}"; acá ya solo
    # existe la ruta, así que la clave de R2 sale del nombre en disco.
    nombre_subida = os.path.basename(foto_local)
    producto = catalogo_productos.encontrar(cliente, producto_id)
    if producto is None:
        # Lo borraron del catálogo entre encolar y ejecutar: sin referencias no
        # hay nada que generar, y el swap no puede quedar "generando" por siempre.
        mensaje = "El producto ya no está en el catálogo; no se generó el swap."
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=mensaje)
        bitacora.registrar(cliente, swap_id, "swap", "error", mensaje)
        return mensaje

    # Cada etapa se anuncia con trabajos.reportar(job_id, ...) para que la barra
    # deje de ser un número inventado: el usuario ve en qué paso real va.
    avisar_fase = _avisar_fase_de(job_id)

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
                    detalle=f"foto {i + 1} de {len(referencias)}",
                )
                key = f"clientes/{cliente}/productos/{producto_id}/{os.path.basename(ref_local)}"
                referencias_urls.append(r2_uploader.upload_image(ref_local, key))

            trabajos.reportar(job_id, etapa=ETAPA_MODELO)
            if proveedor == "kling_o1":
                citas = " ".join(f"@Image{i + 1}" for i in range(len(referencias_urls)))
                prompt = prompt_swap.prompt_video(tipo_producto, citas=citas, mapa=mapa_producto)
                resultado_url = kling_o1_client.editar_video(
                    video_url, prompt, referencias_urls=referencias_urls, on_progreso=avisar_fase,
                )
                costo = kling_o1_client.estimate_video()
            elif proveedor == "wan27_edit":
                prompt = prompt_swap.prompt_video(tipo_producto, mapa=mapa_producto)
                resultado_url = wavespeed_client.editar_video(
                    video_url, prompt, referencias_urls=referencias_urls, on_progreso=avisar_fase,
                )
                costo = wavespeed_client.estimate_video()
            elif proveedor in wavespeed_video_edit.MODELOS:
                prompt = prompt_swap.prompt_video(tipo_producto, mapa=mapa_producto)
                resultado_url = wavespeed_video_edit.editar_video(
                    proveedor, video_url, prompt, referencias_urls=referencias_urls,
                    on_progreso=avisar_fase,
                )
                costo = wavespeed_video_edit.estimate_video(proveedor)
            else:
                referencia = referencias_urls[0] if referencias_urls else None
                resultado_url = comparador_modelos.editar_video(
                    proveedor, video_url, producto["descripcion"], referencia_imagen_url=referencia,
                    on_progreso=avisar_fase, tipo=tipo_producto, mapa=mapa_producto,
                )
                costo = comparador_modelos.estimate_video(proveedor)

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
                    resultado_url = wavespeed_imagen.editar_imagen(
                        foto_url, prompt_swap.prompt_imagen(tipo_producto, referencias_lista, mapa=mapa_producto),
                        referencias_urls=referencias_urls,
                        aspect_ratio=aspect_ratio_mod.detectar_wavespeed_nano_banana_pro(foto_local),
                        on_progreso=avisar_fase,
                    )
                    costo = wavespeed_imagen.estimate_image()
                elif proveedor == "seedream_v5_pro":
                    referencias_lista = "\n".join(
                        f"Imagen {i + 2}: referencia del producto (mismo producto, otro ángulo)."
                        for i in range(len(referencias_urls))
                    )
                    resultado_url = wavespeed_imagen.editar_imagen_seedream(
                        foto_url,
                        prompt_swap.prompt_imagen(tipo_producto, referencias_lista, mapa=mapa_producto),
                        referencias_urls=referencias_urls, on_progreso=avisar_fase,
                    )
                    costo = wavespeed_imagen.estimate_seedream(n_imagenes=len(referencias_urls) + 1)
                else:
                    resultado_url = comparador_modelos.editar_imagen(
                        proveedor, foto_url, producto["descripcion"], referencias_urls=referencias_urls,
                        foto_local_path=foto_local, on_progreso=avisar_fase, tipo=tipo_producto, mapa=mapa_producto,
                    )
                    costo = comparador_modelos.estimate_image(proveedor)
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
                try:
                    url_para_mejorar = r2_uploader.upload_image(
                        local_path, f"clientes/{cliente}/swaps/{swap_id}.previo.png")
                    ancho_prev, alto_prev = aspect_ratio_mod.dimensiones(local_path)
                    mejorada_url = wavespeed_imagen.mejorar_calidad(
                        url_para_mejorar,
                        factor=wavespeed_imagen.factor_seguro(ancho_prev, alto_prev),
                        on_progreso=avisar_fase,
                    )
                    resp_mejorada = requests.get(mejorada_url, timeout=180)
                    resp_mejorada.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(resp_mejorada.content)
                    costo = {
                        "credits": costo.get("credits"),
                        "usd": round((costo.get("usd") or 0) + wavespeed_imagen.COSTO_USD_UPSCALE, 3),
                    }
                except Exception as e:
                    # La mejora es un extra: si falla, el swap YA está hecho y
                    # se entrega igual. Perder el resultado por el paso opcional
                    # sería tirar a la basura lo que el usuario ya pagó.
                    bitacora.registrar(cliente, swap_id, "mejora_calidad", "error", str(e))

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
            credits=costo.get("credits"), usd=costo.get("usd"), error_storage=error_storage,
        )
        bitacora.registrar(cliente, swap_id, "swap", "ok", local_path)

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

        return "Swap listo."
    except Exception as e:
        swaps_mod.actualizar(cliente, swap_id, estado="error", error=str(e))
        bitacora.registrar(cliente, swap_id, "swap", "error", str(e))
        raise

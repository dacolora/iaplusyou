"""
Tareas del worker para Campañas: publicar un anuncio en Meta y refrescar sus
métricas. Cuerpos movidos de dashboard.publicar_ad (la closure trabajo()) y de
dashboard.actualizar_resultados_ad; dashboard ahora solo valida y encola.

El worker es de un hilo, pero se conserva el lock (el _ENV_LOCK de dashboard):
meta_auth.configurar() escribe credenciales globales del proceso
(meta_ads/auth._CREDENCIALES) y el lock cubre configurar -> llamadas a Meta ->
limpiar() para que dos proyectos nunca se mezclen si esto corre en un proceso
con más de un hilo (gunicorn, tests).

`_miniatura_para_ad`, `_extraer_frame` y MONEDAS_SIN_DECIMALES están copiados
tal cual de dashboard.py (que conserva los suyos). La ruta sigue validando el
mínimo diario y guardando moneda/presupuesto en la fila antes de encolar; acá
se relee la moneda de meta.json solo para convertir el presupuesto a centavos.
"""
import os
import subprocess
import threading

import requests

import ads
import bitacora
import db
import meta_conexion
from meta_ads import ad as meta_ad, adset as meta_adset, auth as meta_auth, campaign as meta_campaign
from meta_ads import creative as meta_creative, insights as meta_insights
from meta_ads.targeting import Targeting
from storage import r2_uploader
from tareas import registrar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Divisas que Meta maneja sin decimales (el monto se manda tal cual, no ×100).
MONEDAS_SIN_DECIMALES = {"JPY", "CLP", "HUF", "ISK", "KRW", "TWD", "VND", "PYG", "UGX", "XAF", "XOF"}

_LOCK = threading.Lock()


def _extraer_frame(video_path, frame_path, segundo=1.0):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(segundo), "-i", video_path, "-frames:v", "1", "-q:v", "2", frame_path],
        check=True, capture_output=True,
    )


def _miniatura_para_ad(cliente, ad_id, video_url):
    """Fotograma del video (segundo 1) subido a R2, para image_url del creative.
    Si algo falla, devuelve la propia URL del video (Meta genera una por defecto)."""
    try:
        carpeta = os.path.join(BASE_DIR, "salidas", cliente, "ads")
        os.makedirs(carpeta, exist_ok=True)
        local_video = os.path.join(carpeta, f"{ad_id}.mp4")
        with requests.get(video_url, timeout=120, stream=True) as r:
            r.raise_for_status()
            with open(local_video, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        frame = os.path.join(carpeta, f"{ad_id}.jpg")
        _extraer_frame(local_video, frame)
        return r2_uploader.upload_image(frame, f"clientes/{cliente}/ads/{ad_id}.jpg")
    except Exception as e:
        bitacora.registrar(cliente, ad_id, "ads_miniatura", "error", str(e))
        return video_url


@registrar("meta_publicar")
def publicar(tarea):
    """Campaign -> AdSet -> AdCreative -> Ad, todo PAUSED. Se encola con
    max_intentos=1: reintentar automáticamente solo crearía campañas huérfanas
    en Meta; la persona reintenta con "Volver a intentar"."""
    p = tarea["payload"]
    cliente, ad_id = p["cliente"], p["ad_id"]
    objetivo = p["objetivo"]
    presupuesto_diario = float(p["presupuesto_diario"])
    dias = int(p["dias"])
    pais = p["pais"]
    edad_min = int(p["edad_min"])
    edad_max = int(p["edad_max"])
    destino_url = p["destino_url"]
    entry = ads.cargar(cliente)[ad_id]

    # El presupuesto se escribe en la MONEDA DE LA CUENTA (meta.json -> moneda):
    # Meta interpreta daily_budget en esa divisa. Antes se asumía USD y con una
    # cuenta en COP "5" terminaba siendo 500 pesos diarios.
    moneda = (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"

    # Serializado: meta_auth.configurar() escribe credenciales globales del
    # proceso (meta_ads/auth._CREDENCIALES); el lock cubre configurar ->
    # llamadas a Meta -> limpiar() para que dos proyectos nunca se mezclen.
    with _LOCK:
        # Meta recibe el presupuesto en la unidad menor de la divisa (centavos
        # para USD y COP; sin decimales para JPY/CLP/etc.).
        centavos = int(round(presupuesto_diario * (1 if moneda in MONEDAS_SIN_DECIMALES else 100)))
        try:
            # Credenciales del proyecto (meta.json), no del .env: cada
            # cliente conectó su propia cuenta desde FlowMarketing.
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            campaign_resp = meta_campaign.crear_campaign(entry["nombre"], objetivo)
            campaign_id = campaign_resp["id"]

            targeting = Targeting().edad(edad_min, edad_max).paises([pais]).to_dict()
            adset_resp = meta_adset.crear_adset(
                f"{entry['nombre']} — adset", campaign_id, objetivo, targeting, centavos, dias,
            )
            adset_id = adset_resp["id"]

            ig_user_id = creds["ig_user_id"]
            if entry["contenido_tipo"] == "foto":
                creative_resp = meta_creative.crear_creative_imagen(
                    f"{entry['nombre']} — creative", entry["contenido_url"], entry["nombre"],
                    link=destino_url, instagram_user_id=ig_user_id,
                )
            else:
                # El video se sube a la cuenta publicitaria (advideos) y se
                # usa su id; la miniatura es un fotograma real subido a R2.
                meta_video_id = meta_creative.subir_video(entry["contenido_url"], titulo=entry["nombre"])
                miniatura_url = _miniatura_para_ad(cliente, ad_id, entry["contenido_url"])
                creative_resp = meta_creative.crear_creative_video(
                    f"{entry['nombre']} — creative", meta_video_id, miniatura_url,
                    entry["nombre"], destino_url, instagram_user_id=ig_user_id,
                )
                ads.actualizar(cliente, ad_id, meta_video_id=meta_video_id)
            creative_id = creative_resp["id"]

            ad_resp = meta_ad.crear_ad(entry["nombre"], adset_id, creative_id)

            ads.actualizar(
                cliente, ad_id, estado="pausado",
                meta_ids={
                    "campaign_id": campaign_id, "adset_id": adset_id,
                    "ad_id": ad_resp["id"], "creative_id": creative_id,
                },
            )
            bitacora.registrar(cliente, ad_id, "ads_publicar", "ok", campaign_id)
            return "Anuncio publicado (pausado, revísalo en Meta Ads Manager antes de activarlo)."
        except Exception as e:
            msg = str(e)
            # Meta no permite crear anuncios con la app en modo desarrollo
            # (subcode 1885183 / "(#3) capability"): hasta pasar App Review
            # se conecta y se leen métricas, pero no se publica.
            if "1359188" in msg or "todo de pago" in msg:
                msg = ("Tu cuenta publicitaria de Meta no tiene un método de pago. Agrégalo en "
                       "business.facebook.com › Facturación y pagos (tarjeta o PSE) y vuelve a intentar; "
                       "la pieza sigue en la lista.")
            elif "1885183" in msg or "modo de desarrollo" in msg or "does not have the capability" in msg:
                msg = ("Meta rechazó la solicitud por permisos de la app (#3). Desconecta y vuelve a "
                       "conectar Meta para renovar los permisos; si sigue igual, avísanos. La pieza "
                       "sigue en la lista.")
            ads.actualizar(cliente, ad_id, estado="error", error=msg)
            bitacora.registrar(cliente, ad_id, "ads_publicar", "error", str(e))
            raise
        finally:
            meta_auth.limpiar()


@registrar("meta_refrescar")
def refrescar(tarea):
    """Trae el snapshot de métricas del anuncio desde Meta. Idempotente: puede
    reintentarse con los max_intentos por defecto."""
    p = tarea["payload"]
    cliente, ad_id = p["cliente"], p["ad_id"]
    entry = ads.cargar(cliente)[ad_id]
    if not entry.get("meta_ids", {}).get("ad_id"):
        return "Ese anuncio todavía no está publicado en Meta."
    # Serializado: meta_auth.configurar() escribe credenciales globales del
    # proceso (meta_ads/auth._CREDENCIALES); el lock cubre configurar ->
    # llamadas a Meta -> limpiar() para que dos proyectos nunca se mezclen.
    with _LOCK:
        try:
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            resultados = meta_insights.obtener_resultados(entry["meta_ids"]["ad_id"], objetivo=entry.get("objetivo"))
            resultados["actualizado_en"] = db.ahora()
            ads.actualizar(cliente, ad_id, metricas=resultados)
            return "Resultados actualizados."
        finally:
            meta_auth.limpiar()

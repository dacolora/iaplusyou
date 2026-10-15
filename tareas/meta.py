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
tal cual de dashboard.py (que conserva los suyos). Hoy ninguna ruta encola
meta_publicar, pero la tarea sigue registrada para los anuncios sueltos viejos y
pasa por los mismos frenos de plata que el lanzador (PND-324, 2026-10-15):
`lanzador.comprobar_moneda` antes de crear nada y la lectura de vuelta del
diario (`lanzador._confirmar_presupuesto`) después de crear el conjunto.
"""
import logging
import os
import subprocess
import threading

import requests
from flask_babel import gettext, ngettext

import ads
import bitacora
import db
import meta_conexion
import monedas_meta
import triple_whale_tiendas
from meta_ads import ad as meta_ad, adset as meta_adset, auth as meta_auth, campaign as meta_campaign
from meta_ads import creative as meta_creative, insights as meta_insights
from meta_ads.targeting import Targeting
from storage import r2_uploader
from tareas import al_interrumpir, registrar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Divisas que Meta recibe sin decimales (offset 1): la tabla oficial vive en `monedas_meta` (PND-322: la lista
# escrita aquí de memoria no tenía el COP y los presupuestos en pesos colombianos salían 100 veces más altos).
MONEDAS_SIN_DECIMALES = monedas_meta.SIN_DECIMALES

_LOCK = threading.Lock()
log = logging.getLogger("creatv.tareas.meta")


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


@al_interrumpir("meta_publicar")
def interrumpida(tarea, mensaje):
    """El worker murió a mitad de la cadena Campaign -> Ad: el anuncio quedaría
    en `publicando` para siempre. Solo si sigue ahí pasa a error (si ya llegó a
    pausado/error por otro camino no se pisa); meta_refrescar no necesita hook."""
    cliente, ad_id = tarea["payload"]["cliente"], tarea["payload"]["ad_id"]
    entry = ads.cargar(cliente).get(ad_id)
    if entry is None or entry.get("estado") != "publicando":
        return
    ads.actualizar(cliente, ad_id, estado="error", error=mensaje)


@registrar("meta_publicar")
def publicar(tarea):
    """Campaign -> AdSet -> AdCreative -> Ad, todo PAUSED. Se encola con
    max_intentos=1: reintentar automáticamente solo crearía campañas huérfanas
    en Meta; la persona reintenta con "Volver a intentar". Ningún monto sale sin
    `lanzador.comprobar_moneda`, y si Meta guarda en el conjunto otro diario que
    el enviado, el conjunto queda en pausa y no se crea el anuncio (PND-324)."""
    p = tarea["payload"]
    cliente, ad_id = p["cliente"], p["ad_id"]
    objetivo = p["objetivo"]
    presupuesto_diario = float(p["presupuesto_diario"])
    dias = int(p["dias"])
    pais = p["pais"]
    edad_min = int(p["edad_min"])
    edad_max = int(p["edad_max"])
    destino_url = p["destino_url"]
    entry = ads.cargar(cliente).get(ad_id)
    if entry is None:
        return gettext("Ese anuncio ya no existe.")

    # Idempotencia: max_intentos=1, pero si el proceso murió a mitad de la
    # cadena (recuperar_colgadas la marcó "error") no reintentamos solos —
    # reintentar automáticamente crearía una segunda campaña huérfana en
    # Meta. Si ya no está "publicando" o si ya alcanzó a crear una campaña,
    # paramos sin llamar a Meta; la persona revisa y reintenta a mano.
    if entry.get("estado") != "publicando" or (entry.get("meta_ids") or {}).get("campaign_id"):
        msg = gettext("Se interrumpió la publicación; revisa Ads Manager antes de volver a intentar.")
        ads.actualizar(cliente, ad_id, estado="error", error=msg)
        return msg

    # El presupuesto se escribe en la MONEDA DE LA CUENTA: Meta interpreta daily_budget en esa divisa. Antes se
    # asumía USD y con una cuenta en COP "5" terminaba siendo 500 pesos diarios. La de la ficha manda (el diario se
    # escribió en esa moneda, como al activar en dashboard.cambiar_estado_ad); si no la tiene, la de meta.json.
    moneda = entry.get("moneda") or (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    # Import tardío: lanzador importa este módulo (_LOCK, _miniatura_para_ad).
    import lanzador  # noqa: PLC0415

    # Serializado: meta_auth.configurar() escribe credenciales globales del
    # proceso (meta_ads/auth._CREDENCIALES); el lock cubre configurar ->
    # llamadas a Meta -> limpiar() para que dos proyectos nunca se mezclen.
    with _LOCK:
        try:
            # Meta recibe el presupuesto en la unidad de la divisa según su tabla (centavos para USD o EUR; la moneda
            # entera para COP, CLP o JPY): `monedas_meta`, que se niega con una moneda fuera de la tabla. Dentro del
            # try: una moneda fuera de la tabla deja la ficha en error, no en «publicando».
            centavos = monedas_meta.a_unidad_meta(presupuesto_diario, moneda)
            # Credenciales del proyecto (meta.json), no del .env: cada
            # cliente conectó su propia cuenta desde FlowMarketing.
            creds = meta_conexion.credenciales_ads(cliente)
            if not creds.get("page_id"):
                # Conexión «solo métricas»: el creative exige Página; se frena antes de crear campaña o conjunto.
                raise ValueError(meta_conexion.error_solo_metricas(cliente))
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            # PND-324: los mismos frenos que el lanzador (PND-322). Antes de crear nada, la cuenta factura en esa
            # moneda y la unidad cuadra con su mínimo diario; después de crear el conjunto, el diario se lee de vuelta.
            lanzador.comprobar_moneda(lanzador._cuenta_meta(creds), moneda)
            campaign_resp = meta_campaign.crear_campaign(entry["nombre"], objetivo)
            campaign_id = campaign_resp["id"]
            # Se guarda ya: si un paso posterior falla o el proceso muere, el
            # guardia de idempotencia de arriba ve la campaña y no crea otra.
            ads.actualizar(cliente, ad_id, meta_ids={
                "campaign_id": campaign_id, "adset_id": None, "ad_id": None, "creative_id": None,
            })

            targeting = Targeting().edad(edad_min, edad_max).paises([pais]).to_dict()
            adset_resp = meta_adset.crear_adset(
                f"{entry['nombre']} — adset", campaign_id, objetivo, targeting, centavos, dias,
            )
            adset_id = adset_resp["id"]
            # El conjunto queda anotado (para revisarlo en Meta si lo de abajo falla) con el diario y la moneda que se
            # mandaron: «Activar» de un anuncio suelto vuelve a leer ese diario contra Meta antes de encender.
            ads.actualizar(cliente, ad_id, presupuesto_diario=presupuesto_diario, moneda=moneda, meta_ids={
                "campaign_id": campaign_id, "adset_id": adset_id, "ad_id": None, "creative_id": None,
            })
            # Si Meta guardó otro diario, el conjunto queda en pausa y no se crea nada más (PresupuestoNoCoincide).
            lanzador._confirmar_presupuesto(adset_id, centavos)

            ig_user_id = creds["ig_user_id"]
            # Parámetros de rastreo de Triple Whale si el proyecto lo conectó.
            kw_tags = triple_whale_tiendas.kw_url_tags(cliente)
            if entry["contenido_tipo"] == "foto":
                creative_resp = meta_creative.crear_creative_imagen(
                    f"{entry['nombre']} — creative", entry["contenido_url"], entry["nombre"],
                    link=destino_url, instagram_user_id=ig_user_id, **kw_tags,
                )
            else:
                # El video se sube a la cuenta publicitaria (advideos) y se
                # usa su id; la miniatura es un fotograma real subido a R2.
                meta_video_id = meta_creative.subir_video(entry["contenido_url"], titulo=entry["nombre"])
                miniatura_url = _miniatura_para_ad(cliente, ad_id, entry["contenido_url"])
                creative_resp = meta_creative.crear_creative_video(
                    f"{entry['nombre']} — creative", meta_video_id, miniatura_url,
                    entry["nombre"], destino_url, instagram_user_id=ig_user_id, **kw_tags,
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
            return gettext("Anuncio publicado (pausado, revísalo en Meta Ads Manager antes de activarlo).")
        except Exception as e:
            msg = str(e)
            # Meta no permite crear anuncios con la app en modo desarrollo
            # (subcode 1885183 / "(#3) capability"): hasta pasar App Review
            # se conecta y se leen métricas, pero no se publica.
            if "1359188" in msg or "todo de pago" in msg:
                msg = gettext("Tu cuenta publicitaria de Meta no tiene un método de pago. Agrégalo en "
                              "business.facebook.com › Facturación y pagos (tarjeta o PSE) y vuelve a intentar; "
                              "la pieza sigue en la lista.")
            elif "1885183" in msg or "modo de desarrollo" in msg:
                msg = gettext("Meta rechazó el anuncio porque la app está en modo Desarrollo (subcódigo 1885183). "
                              "Pásala a modo Live y revisa lo creado en Ads Manager antes de volver a intentar.")
            elif "does not have the capability" in msg:
                msg = gettext("Meta rechazó la solicitud por permisos de la app (#3). Desconecta y vuelve a "
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
    entry = ads.cargar(cliente).get(ad_id)
    if entry is None:
        return gettext("Ese anuncio ya no existe.")
    if not entry.get("meta_ids", {}).get("ad_id"):
        return gettext("Ese anuncio todavía no está publicado en Meta.")
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
            return gettext("Resultados actualizados.")
        finally:
            meta_auth.limpiar()


@registrar("meta_revisar_acceso")
def revisar_acceso(tarea):
    """Periódica diaria (PND-058): lee en Meta (`debug_token`) cuándo vence el acceso a los datos de cada proyecto con
    su app propia conectada y lo guarda en su meta.json, para que Alertas avise 14 días antes. Rellena también las
    conexiones hechas antes de que se leyera al conectar (colorado_forja: 2026-12-18). Gratis: no cobra ni escribe en
    Meta. Un proyecto que falla no frena a los demás; el registro lleva solo el tipo del error (nunca su texto)."""
    revisados = fallidos = 0
    for cliente in meta_conexion.clientes():
        try:
            if meta_conexion.revisar_vencimientos(cliente) is not None:
                revisados += 1
        except Exception as e:  # noqa: BLE001 — uno que falla no frena a los demás
            fallidos += 1
            log.warning("meta_revisar_acceso %s: %s", cliente, type(e).__name__)
    texto = ngettext("Acceso a los datos de Meta revisado en %(num)s proyecto.",
                     "Acceso a los datos de Meta revisado en %(num)s proyectos.", revisados)
    if fallidos:
        texto += " " + ngettext("%(num)s no se pudo revisar.", "%(num)s no se pudieron revisar.", fallidos)
    return texto

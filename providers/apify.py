"""
Mecánica compartida de la API de Apify (arrancar una corrida, sondearla hasta
un estado terminal, leer su dataset, contarlo) — extraída de
`nicho/fuentes/apify.py` (spec bloque 5, 2026-09-23 §4.2) para que
`referentes/fuentes/apify_adlibrary.py` no la duplique. Cada actor/entrada es
cosa de quien llama: este módulo no sabe qué actor está corriendo, solo habla
con la API v2 de Apify. API v2 verificada 2026-09-20:
  POST /v2/actors/<usuario~actor>/runs (entrada JSON; ?timeout= segundos,
       ?maxItems= ítems cobrados, ?maxTotalChargeUsd= tope de cobro)
       -> data.id, data.status, data.defaultDatasetId
  GET  /v2/actor-runs/<id> -> data.status (READY, RUNNING, SUCCEEDED, FAILED,
       TIMING-OUT, TIMED-OUT, ABORTING, ABORTED)
  GET  /v2/datasets/<id>/items?clean=true&format=json&limit=N -> lista de ítems
  GET  /v2/datasets/<id> -> data.itemCount
Una corrida se paga aunque termine mal, así que después de `arrancar()` nada
se abandona: se sondea hasta un estado terminal (o hasta que vence el reloj
local) y el dataset se lee igual, tolerando fallos pasajeros (un 200 cuyo
cuerpo no es JSON es uno más) — perder la lectura de un dataset ya pagado
sería peor que reintentarla.

Los mensajes se muestran a la persona (nunca van a Claude): pasan por
`gettext` y salen en el idioma del contexto (el del proyecto en el worker).
"""
from flask_babel import gettext

from nicho.fuentes import _http
from nicho.fuentes.base import ErrorFuente

URL_API = "https://api.apify.com/v2"
PAUSA_SONDEO = 10.0
MAX_ESPERA_S = 1200
TERMINALES = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")
MAX_FALLOS_SONDEO = 6          # lecturas de estado malas SEGUIDAS antes de rendirse
INTENTOS_DATASET = 3           # lecturas del dataset antes de caer al itemCount
ESTADO_SIN_TERMINAR = "sin terminar"   # estado ficticio: venció el reloj local
MAX_SIMULTANEAS = 5            # corridas de un lote a la vez (Apify limita las concurrentes por cuenta)
ESTADO_NO_ARRANCO = "no arrancó"     # el POST fue rechazado: no se cobró nada
ESTADO_SIN_ESTADO = "sin estado"     # el sondeo se rindió: la corrida sigue viva en Apify


def cabeceras(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _mensaje_apify(r):
    try:
        return str(((r.json() or {}).get("error") or {}).get("message") or "")[:200]
    except (ValueError, AttributeError):
        return ""


def _tipo_apify(r):
    """`error.type` del cuerpo de una respuesta, o "" si no es JSON o no lo trae (un 403
    cualquiera). Hoy solo se usa para distinguir "full-permission-actor-not-approved" —
    el actor ahora pide acceso completo a la cuenta — del 403 de siempre (token)."""
    try:
        return str(((r.json() or {}).get("error") or {}).get("type") or "")
    except (ValueError, AttributeError):
        return ""


def _cuerpo(r):
    """El JSON de una respuesta como dict: `{}` si es JSON pero no un objeto
    (`null`, una lista). Un cuerpo que no es JSON sube ValueError y quien llama
    decide: nunca debe tumbar el sondeo de una corrida que ya pudo cobrar."""
    cuerpo = r.json()
    return cuerpo if isinstance(cuerpo, dict) else {}


def _leer_estado(r):
    """(status o None, "") de un sondeo que respondió 200, o (None, motivo) si
    el cuerpo no es JSON: cuenta como una lectura mala más, igual que un error HTTP."""
    try:
        data = _cuerpo(r).get("data")
    except ValueError:
        return None, gettext("respuesta ilegible")
    return (data if isinstance(data, dict) else {}).get("status") or None, ""


def frase_estado(estado):
    """«terminó en FAILED» / «no terminó en 20 min»: el sujeto de los mensajes
    del final, con el estado terminal real o el reloj local vencido."""
    if estado == ESTADO_SIN_TERMINAR:
        return gettext("no terminó en %(minutos)s min", minutos=int(MAX_ESPERA_S / 60))
    if estado == ESTADO_NO_ARRANCO:
        return gettext("no arrancó")
    if estado == ESTADO_SIN_ESTADO:
        return gettext("no se pudo saber cómo terminó")
    return gettext("terminó en %(estado)s", estado=estado)


def probar_token(sesion, token):
    """Golpea /users/me para confirmar que el token es válido. Nunca lanza
    (errores de red incluidos): siempre {"ok": bool, "detalle": str}."""
    try:
        r = _http.pedir(sesion, "GET", URL_API + "/users/me", "Apify", headers=cabeceras(token))
    except ErrorFuente as e:
        return {"ok": False, "detalle": e.usuario}
    if r.status_code != 200:
        return {"ok": False, "detalle": gettext("Apify no aceptó el token (%(codigo)s).", codigo=r.status_code)}
    return {"ok": True, "detalle": gettext("Apify aceptó el token.")}


def arrancar(sesion, token, actor, entrada, max_items, max_total_charge_usd, on_ids=None):
    """POST de la corrida. `max_items`/`max_total_charge_usd` son el tope de
    cobro del lado de Apify — lo que se le mostró a la persona antes de
    lanzar, nada más. Devuelve (run_id, dataset_id, estado). `on_ids(run_id,
    dataset_id)`, si se da, se llama en TODA respuesta 2xx ya parseada —
    traiga ambos ids, uno solo o ninguno, incluida una corrida exitosa — y
    SIEMPRE antes de decidir si hace falta lanzar el error de "sin ids". No
    es una señal exclusiva de error: sirve para que quien llama guarde el id
    de una corrida que ya pudo cobrar, tanto si `arrancar` devuelve como si
    termina lanzando. Un 2xx cuyo cuerpo no es JSON no trae ids: ErrorFuente
    sin llamar a `on_ids` (la corrida no consta como lanzada)."""
    r = _http.pedir(sesion, "POST", f"{URL_API}/actors/{actor}/runs", "Apify", headers=cabeceras(token),
                    params={"timeout": MAX_ESPERA_S, "maxItems": max_items, "maxTotalChargeUsd": max_total_charge_usd},
                    json=entrada)
    if r.status_code == 403 and _tipo_apify(r) == "full-permission-actor-not-approved":
        # No es un problema de token (2026-10-01: `axesso_data~amazon-reviews-scraper` empezó a
        # pedir esto): el mensaje de siempre manda a revisar APIFY_TOKEN y no hay nada que revisar
        # ahí. Nunca se repite la URL de aprobación de Apify ni el token.
        raise ErrorFuente(gettext("Este actor de Apify ahora pide acceso completo a la cuenta y Creatv "
                                  "no se lo da; hay que cambiar de actor."))
    if r.status_code in (401, 403):
        raise ErrorFuente(gettext("Apify no aceptó el token (APIFY_TOKEN)."))
    if r.status_code == 400:
        motivo = _mensaje_apify(r) or gettext("entrada inválida")
        raise ErrorFuente(gettext("Apify rechazó la entrada del actor: %(motivo)s", motivo=motivo))
    if r.status_code not in (200, 201):
        raise ErrorFuente(gettext("Apify no arrancó la corrida (%(codigo)s).", codigo=r.status_code))
    try:
        corrida = _cuerpo(r).get("data")
    except ValueError:
        # Sin cuerpo legible no hay ids que guardar (no se llama a `on_ids`): para quien llama, la corrida no
        # consta como lanzada; si Apify sí la arrancó, solo la consola lo dice.
        raise ErrorFuente(gettext("Apify respondió sin datos legibles al arrancar la corrida (%(codigo)s); "
                                  "revisa en console.apify.com si arrancó.", codigo=r.status_code))
    corrida = corrida if isinstance(corrida, dict) else {}
    run_id, dataset_id = corrida.get("id") or None, corrida.get("defaultDatasetId") or None
    if on_ids:
        on_ids(run_id, dataset_id)
    if not run_id or not dataset_id:
        # Si el id sí vino, la corrida pudo arrancar (y cobrar) igual.
        raise ErrorFuente(gettext("Apify no devolvió los ids de la corrida (corrida %(corrida)s, "
                                  "dataset %(dataset)s); revísala en console.apify.com.",
                                  corrida=run_id or "?", dataset=dataset_id or "?"))
    return run_id, dataset_id, corrida.get("status") or "READY"


def sondear(sesion, token, run_id, estado, etapa_leyendo, avanzar=None):
    """Sondea hasta un estado terminal y lo devuelve, o ESTADO_SIN_TERMINAR si
    venció MAX_ESPERA_S. Un fallo pasajero no abandona la corrida: se toleran
    MAX_FALLOS_SONDEO lecturas malas SEGUIDAS (una buena reinicia el
    contador). `etapa_leyendo` es la etiqueta que cada llamador manda a
    `avanzar()` en cada lectura — nicho usa "Leyendo comentarios", referentes
    la suya — para no cambiarle el texto de progreso a nadie que ya dependa
    de él."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    esperado, fallos, ultimo = 0.0, 0, ""
    while estado not in TERMINALES:
        if esperado >= MAX_ESPERA_S:
            return ESTADO_SIN_TERMINAR
        _http.dormir(PAUSA_SONDEO)
        esperado += PAUSA_SONDEO
        try:
            r = _http.pedir(sesion, "GET", f"{URL_API}/actor-runs/{run_id}", "Apify", headers=cabeceras(token))
            malo = "" if r.status_code == 200 else f"HTTP {r.status_code}"
        except ErrorFuente as e:                            # sin URL ni cabeceras: nunca lleva el token
            r, malo = None, e.usuario or gettext("sin respuesta")
        status = None
        if not malo:
            status, malo = _leer_estado(r)                  # un 200 que no es JSON también es una lectura mala
        if malo:
            fallos, ultimo = fallos + 1, malo
            if fallos >= MAX_FALLOS_SONDEO:
                raise ErrorFuente(gettext("Apify no respondió el estado %(n)s veces seguidas (%(ultimo)s); "
                                          "corrida %(corrida)s: revísala en console.apify.com.",
                                          n=MAX_FALLOS_SONDEO, ultimo=ultimo, corrida=run_id))
            continue
        fallos = 0
        estado = status or estado
        avanzar(etapa_leyendo, gettext("Apify: %(estado)s · corrida %(corrida)s", estado=estado, corrida=run_id))
    return estado


def leer_dataset(sesion, token, dataset_id, limite):
    """Ítems crudos del dataset, hasta INTENTOS_DATASET intentos. Devuelve
    (lista, "") cuando se pudo leer (la lista puede venir vacía) y
    (None, motivo) cuando no."""
    motivo = ""
    for intento in range(INTENTOS_DATASET):
        if intento:
            _http.dormir(PAUSA_SONDEO)
        try:
            r = _http.pedir(sesion, "GET", f"{URL_API}/datasets/{dataset_id}/items", "Apify", headers=cabeceras(token),
                            params={"clean": "true", "format": "json", "limit": limite})
        except ErrorFuente as e:
            motivo = e.usuario
            continue
        if r.status_code != 200:
            motivo = f"HTTP {r.status_code}"
            continue
        try:
            datos = r.json()
        except ValueError:                      # 200 con cuerpo ilegible: cuenta como intento fallido
            motivo = gettext("respuesta ilegible")
            continue
        return (datos if isinstance(datos, list) else []), ""
    return None, motivo


def contar_dataset(sesion, token, dataset_id):
    """`itemCount` del dataset cuando no se pudieron leer los ítems: sirve
    para registrar el gasto de todos modos. None si tampoco se puede."""
    try:
        r = _http.pedir(sesion, "GET", f"{URL_API}/datasets/{dataset_id}", "Apify", headers=cabeceras(token))
    except ErrorFuente:
        return None
    if r.status_code != 200:
        return None
    try:
        return max(0, int(((r.json() or {}).get("data") or {}).get("itemCount")))
    except (AttributeError, TypeError, ValueError):
        return None


def correr_lote(sesion, token, actor, corridas, etapa, avanzar=None, max_simultaneas=MAX_SIMULTANEAS):
    """Varias corridas del mismo actor, hasta `max_simultaneas` a la vez.
    `corridas` = [{"entrada", "max_items", "max_usd", "etiqueta"}]. Cada una
    lleva su propio techo de cobro. Se sondean todas en una misma vuelta (una
    pausa por vuelta, no por corrida); una lectura mala no tumba a las demás;
    cuando una termina arranca la siguiente. Al final se lee el dataset de
    TODAS las que arrancaron, cualquiera sea su estado (una corrida se paga
    aunque termine mal); si un dataset no se puede leer, `resultados` cae al
    `itemCount` y en último caso al `max_items` de esa corrida.

    Devuelve {"items": [(indice, item), …] en orden de corrida, "resultados":
    ítems crudos totales (lo que Apify cobra), "corridas": [{indice, etiqueta,
    run_id, dataset_id, estado, resultados, motivo}], "aviso": una línea por
    corrida que no terminó en SUCCEEDED o cuyo dataset no se pudo leer}.
    Levanta ErrorFuente solo si NINGUNA corrida arrancó (nada se cobró)."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    registros = [{"indice": i, "etiqueta": c.get("etiqueta"), "run_id": None, "dataset_id": None, "estado": None, "resultados": 0, "motivo": ""}
                 for i, c in enumerate(corridas)]
    pendientes = list(range(len(corridas)))
    vivas = {}                                  # indice -> {"esperado": s, "fallos": n}
    total = len(corridas)

    def _arrancar_siguientes():
        while pendientes and len(vivas) < max_simultaneas:
            i = pendientes.pop(0)
            reg, c = registros[i], corridas[i]

            def _ids(run_id, dataset_id, reg=reg):
                reg["run_id"], reg["dataset_id"] = run_id, dataset_id
            try:
                _, _, estado = arrancar(sesion, token, actor, c["entrada"], c["max_items"], c["max_usd"], on_ids=_ids)
            except ErrorFuente as e:
                if reg["run_id"]:                       # arrancó pero sin dataset: se sondea igual, ya pudo cobrar
                    reg["estado"], reg["motivo"] = "READY", e.usuario
                    vivas[i] = {"esperado": 0.0, "fallos": 0}
                else:
                    reg["estado"], reg["motivo"] = ESTADO_NO_ARRANCO, e.usuario
                continue
            reg["estado"] = estado
            if estado in TERMINALES:
                continue
            vivas[i] = {"esperado": 0.0, "fallos": 0}

    _arrancar_siguientes()
    if all(r["estado"] == ESTADO_NO_ARRANCO for r in registros):
        raise ErrorFuente(registros[0]["motivo"] if registros else gettext("No hay corridas que lanzar."))
    while vivas:
        _http.dormir(PAUSA_SONDEO)
        for i in list(vivas):
            reg, v = registros[i], vivas[i]
            v["esperado"] += PAUSA_SONDEO
            if v["esperado"] > MAX_ESPERA_S:
                reg["estado"] = ESTADO_SIN_TERMINAR
                del vivas[i]
                continue
            try:
                r = _http.pedir(sesion, "GET", f"{URL_API}/actor-runs/{reg['run_id']}", "Apify", headers=cabeceras(token))
                malo = "" if r.status_code == 200 else f"HTTP {r.status_code}"
            except ErrorFuente as e:                            # sin URL ni cabeceras: nunca lleva el token
                r, malo = None, e.usuario or gettext("sin respuesta")
            status = None
            if not malo:
                # un 200 que no es JSON es una lectura mala más: nunca una excepción que pierda el gasto del lote
                status, malo = _leer_estado(r)
            if malo:
                v["fallos"] += 1
                if v["fallos"] >= MAX_FALLOS_SONDEO:
                    reg["estado"], reg["motivo"] = ESTADO_SIN_ESTADO, malo
                    del vivas[i]
                continue
            v["fallos"] = 0
            reg["estado"] = status or reg["estado"]
            hechas = total - len(vivas) - len(pendientes)
            avanzar(etapa, gettext("Apify: %(estado)s · corrida %(corrida)s (%(hechas)s/%(total)s)",
                                   estado=reg["estado"], corrida=reg["run_id"], hechas=hechas, total=total))
            if reg["estado"] in TERMINALES:
                del vivas[i]
        _arrancar_siguientes()
    items, avisos = [], []
    for reg, c in zip(registros, corridas):
        if not reg["run_id"]:
            avisos.append(gettext("corrida no lanzada (%(etiqueta)s): %(motivo)s", etiqueta=reg["etiqueta"], motivo=reg["motivo"]))
            continue
        crudos, motivo = (None, gettext("sin dataset")) if not reg["dataset_id"] else leer_dataset(sesion, token, reg["dataset_id"], c["max_items"])
        if crudos is None:
            contados = contar_dataset(sesion, token, reg["dataset_id"]) if reg["dataset_id"] else None
            reg["resultados"] = c["max_items"] if contados is None else contados
            reg["motivo"] = (reg["motivo"] + "; " if reg["motivo"] else "") + gettext("dataset %(dataset)s no leído (%(motivo)s)",
                                                                                     dataset=reg["dataset_id"] or "?", motivo=motivo)
        else:
            reg["resultados"] = len(crudos)
            items.extend((reg["indice"], it) for it in crudos)
        if reg["estado"] != "SUCCEEDED" or reg["motivo"]:
            avisos.append(gettext("corrida %(corrida)s (%(etiqueta)s) %(estado)s: %(n)s resultado(s)%(motivo)s",
                                  corrida=reg["run_id"], etiqueta=reg["etiqueta"], estado=frase_estado(reg["estado"]),
                                  n=reg["resultados"], motivo=("; " + reg["motivo"]) if reg["motivo"] else ""))
    return {"items": items, "resultados": sum(r["resultados"] for r in registros), "corridas": registros, "aviso": " · ".join(avisos)}

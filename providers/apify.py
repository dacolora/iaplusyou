"""
Mecánica compartida de la API de Apify (arrancar una corrida, sondearla hasta
un estado terminal, leer su dataset, contarlo) — extraída de
`nicho/fuentes/apify.py` (spec bloque 5, 2026-09-23 §4.2) para que
`referentes/fuentes/apify_adlibrary.py` no la duplique. Cada actor/entrada es
cosa de quien llama: este módulo no sabe qué actor está corriendo, solo habla
con la API v2 de Apify. Una corrida se paga aunque termine mal, así que
después de `arrancar()` nada se abandona: se sondea hasta un estado terminal
(o hasta que vence el reloj local) y el dataset se lee igual, tolerando
fallos pasajeros — perder la lectura de un dataset ya pagado sería peor que
reintentarla.
"""
from nicho.fuentes import _http
from nicho.fuentes.base import ErrorFuente

URL_API = "https://api.apify.com/v2"
PAUSA_SONDEO = 10.0
MAX_ESPERA_S = 1200
TERMINALES = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")
MAX_FALLOS_SONDEO = 6          # lecturas de estado malas SEGUIDAS antes de rendirse
INTENTOS_DATASET = 3           # lecturas del dataset antes de caer al itemCount
ESTADO_SIN_TERMINAR = "sin terminar"   # estado ficticio: venció el reloj local


def cabeceras(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _mensaje_apify(r):
    try:
        return str(((r.json() or {}).get("error") or {}).get("message") or "")[:200]
    except (ValueError, AttributeError):
        return ""


def frase_estado(estado):
    """«terminó en FAILED» / «no terminó en 20 min»: el sujeto de los mensajes
    del final, con el estado terminal real o el reloj local vencido."""
    if estado == ESTADO_SIN_TERMINAR:
        return f"no terminó en {int(MAX_ESPERA_S / 60)} min"
    return f"terminó en {estado}"


def probar_token(sesion, token):
    """Golpea /users/me para confirmar que el token es válido. Nunca lanza
    (errores de red incluidos): siempre {"ok": bool, "detalle": str}."""
    try:
        r = _http.pedir(sesion, "GET", URL_API + "/users/me", "Apify", headers=cabeceras(token))
    except ErrorFuente as e:
        return {"ok": False, "detalle": e.usuario}
    if r.status_code != 200:
        return {"ok": False, "detalle": f"Apify no aceptó el token ({r.status_code})."}
    return {"ok": True, "detalle": "Apify aceptó el token."}


def arrancar(sesion, token, actor, entrada, max_items, max_total_charge_usd):
    """POST de la corrida. `max_items`/`max_total_charge_usd` son el tope de
    cobro del lado de Apify — lo que se le mostró a la persona antes de
    lanzar, nada más. Devuelve (run_id, dataset_id, estado)."""
    r = _http.pedir(sesion, "POST", f"{URL_API}/actors/{actor}/runs", "Apify", headers=cabeceras(token),
                    params={"timeout": MAX_ESPERA_S, "maxItems": max_items, "maxTotalChargeUsd": max_total_charge_usd},
                    json=entrada)
    if r.status_code in (401, 403):
        raise ErrorFuente("Apify no aceptó el token (APIFY_TOKEN).")
    if r.status_code == 400:
        raise ErrorFuente(f"Apify rechazó la entrada del actor: {_mensaje_apify(r) or 'entrada inválida'}")
    if r.status_code not in (200, 201):
        raise ErrorFuente(f"Apify no arrancó la corrida ({r.status_code}).")
    corrida = (r.json() or {}).get("data") or {}
    run_id, dataset_id = corrida.get("id") or None, corrida.get("defaultDatasetId") or None
    if not run_id or not dataset_id:
        # Si el id sí vino, la corrida pudo arrancar (y cobrar) igual.
        raise ErrorFuente(f"Apify no devolvió los ids de la corrida (corrida {run_id or '?'}, "
                          f"dataset {dataset_id or '?'}); revísala en console.apify.com.")
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
            r, malo = None, e.usuario or "sin respuesta"
        if malo:
            fallos, ultimo = fallos + 1, malo
            if fallos >= MAX_FALLOS_SONDEO:
                raise ErrorFuente(f"Apify no respondió el estado {MAX_FALLOS_SONDEO} veces seguidas ({ultimo}); "
                                  f"corrida {run_id}: revísala en console.apify.com.")
            continue
        fallos = 0
        estado = ((r.json() or {}).get("data") or {}).get("status") or estado
        avanzar(etapa_leyendo, f"Apify: {estado} · corrida {run_id}")
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
            motivo = "respuesta ilegible"
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

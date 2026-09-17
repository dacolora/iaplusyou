"""
Conexión de un proyecto con Meta (Facebook Login for Business) y sus
credenciales en clientes/<cliente>/meta.json.

La autorización ya no es un script de terminal con callback en localhost, es
una ruta de la app — así funciona en el VPS y desde el celular. Un solo
permiso cubre anuncios (meta_ads/) y publicación orgánica
(uploaders/meta_uploader.py).

Reglas que este módulo hace cumplir por sí mismo:
  - El token nunca entra a un mensaje de excepción, log ni dry_run.
  - META_APP_SECRET solo se lee en cambiar_code_por_token().
  - meta.json se escribe atómico (tmp + os.replace) y con permisos 0600.

Ver docs/superpowers/specs/2026-09-11-conexion-meta-design.md.
"""
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Una sola versión para todo lo de Meta. meta_ads/auth.py y
# uploaders/meta_uploader.py llevan el MISMO valor (no se importa entre repos:
# meta_ads es un submódulo que no debe depender del anfitrión).
GRAPH_VERSION = "v25.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
DIALOG_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"

# Códigos de error de Graph que significan "esta conexión ya no sirve"
# (token inválido/expirado, permiso retirado). Cualquier otro error NO cambia
# el estado guardado: un timeout no es una desconexión.
CODIGOS_CONEXION_ROTA = {190, 10, 200}

_TTL_ESTADO_SEG = 600
_cache_estado = {}
# estado_pixel: misma vida que estado(), en su propio dict — invalidar la
# conexión (guardar/borrar) tira los dos; invalidar_pixel solo este.
_cache_pixel = {}
# Un Pixel "vivo" es uno que disparó en la última semana: con menos, las
# compras que reporte Meta no sirven para juzgar piezas (atribución "pixel").
_PIXEL_DIAS_VIVO = 7

# Un meta.pendiente.json abandonado (el usuario cerró la pestaña en la
# pantalla de elegir cuenta/Página) deja tokens en disco indefinidamente si
# nadie lo borra; a los 30 min se considera abandonado y se descarta.
_TTL_PENDIENTE_SEG = 1800


class MetaConexionError(RuntimeError):
    """Error legible para el usuario. Nunca contiene un token."""

    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo


# ---------- configuración de la app (viene del .env raíz) ----------

def _env_obligatoria(clave, para_que):
    valor = os.environ.get(clave, "").strip()
    if not valor:
        raise MetaConexionError(f"Falta {clave} en el .env — hace falta para {para_que}.")
    return valor


def redirect_uri():
    return _env_obligatoria(
        "META_REDIRECT_URI",
        "armar la URL de vuelta desde Meta (tiene que coincidir con la registrada en la app)",
    )


def nuevo_state():
    return secrets.token_urlsafe(32)


def url_dialogo(state):
    """URL del diálogo de Facebook Login for Business. config_id reemplaza a
    scope: la configuración (creada en el panel de la app) define el tipo de
    token y los permisos. override_default_response_type va por si la
    configuración pide token de usuario del sistema — se confirma contra
    Meta en la Task 7 del plan."""
    params = {
        "client_id": _env_obligatoria("META_APP_ID", "abrir el diálogo de Meta"),
        "config_id": _env_obligatoria("META_LOGIN_CONFIG_ID", "abrir el diálogo de Meta"),
        "redirect_uri": redirect_uri(),
        "state": state,
        "response_type": "code",
        "override_default_response_type": "true",
    }
    return f"{DIALOG_URL}?{urlencode(params)}"


# ---------- meta.json por cliente ----------

def _dir(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente)


def _path(cliente):
    return os.path.join(_dir(cliente), "meta.json")


def _path_pendiente(cliente):
    return os.path.join(_dir(cliente), "meta.pendiente.json")


def _escribir_atomico(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    os.chmod(tmp, 0o600)  # a prueba de umask, por si el fd nació con otros permisos
    os.replace(tmp, ruta)


def _leer(ruta):
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (ValueError, OSError):
        # Corrupto: se trata como "sin conectar" (nunca como excepción en una
        # ruta) y se deja rastro. Import tardío para no acoplar el módulo.
        try:
            import bitacora
            cliente = os.path.basename(os.path.dirname(ruta))
            bitacora.registrar(cliente, "meta", "conexion", "error", f"{os.path.basename(ruta)} ilegible")
        except Exception:
            pass
        return None
    return datos if isinstance(datos, dict) else None


def _borrar(ruta):
    if not os.path.exists(ruta):
        return False
    os.remove(ruta)
    return True


def cargar(cliente):
    return _leer(_path(cliente))


def guardar(cliente, datos):
    _escribir_atomico(_path(cliente), datos)
    _cache_estado.pop(cliente, None)
    _cache_pixel.pop(cliente, None)


def borrar(cliente):
    _cache_estado.pop(cliente, None)
    _cache_pixel.pop(cliente, None)
    return _borrar(_path(cliente))


def cargar_pendiente(cliente):
    ruta = _path_pendiente(cliente)
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        return None
    if time.time() - mtime > _TTL_PENDIENTE_SEG:
        # Abandonado: se descarta en vez de dejar tokens en disco sin límite.
        _borrar(ruta)
        return None
    return _leer(ruta)


def guardar_pendiente(cliente, datos):
    datos = {**datos, "creado_en": datetime.now().isoformat(timespec="seconds")}
    _escribir_atomico(_path_pendiente(cliente), datos)


def borrar_pendiente(cliente):
    return _borrar(_path_pendiente(cliente))


def revocar(cliente):
    """DELETE /me/permissions con el token guardado: Meta invalida ese token y
    los de Página derivados. Devuelve True si Meta confirmó; nunca lanza."""
    datos = cargar(cliente)
    token = (datos or {}).get("token")
    if not token:
        return False
    try:
        r = requests.delete(f"{GRAPH_URL}/me/permissions", params={"access_token": token}, timeout=30)
        return bool(r.ok and r.json().get("success"))
    except Exception:
        return False


def credenciales_ads(cliente):
    """Lo que meta_ads/auth.configurar() necesita, o MetaConexionError si el
    proyecto no está conectado. ad_account_id se guarda tal cual lo devuelve
    Meta (con el prefijo act_); meta_ads/auth lo normaliza."""
    datos = cargar(cliente)
    if not datos or not datos.get("token") or not datos.get("ad_account_id"):
        raise MetaConexionError("Este proyecto no tiene Meta conectado — conéctalo en FlowMarketing.")
    return {
        "token": datos["token"],
        "ad_account_id": datos["ad_account_id"],
        "page_id": datos.get("page_id"),
        "ig_user_id": datos.get("ig_user_id"),
    }


# ---------- llamadas a Graph ----------

def _graph_get(edge, token, params=None, timeout=30):
    """GET a Graph con el token en params (nunca en la URL construida a mano).
    Convierte cualquier error en MetaConexionError sin token adentro."""
    p = dict(params or {})
    p["access_token"] = token
    try:
        resp = requests.get(f"{GRAPH_URL}/{edge}", params=p, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise MetaConexionError(f"No pude hablar con Meta ({type(e).__name__}).") from None
    try:
        datos = resp.json() if resp.content else {}
    except ValueError:
        datos = {}
    if not resp.ok or "error" in datos:
        err = datos.get("error") or {}
        mensaje = err.get("message") or f"HTTP {resp.status_code}"
        raise MetaConexionError(f"Meta respondió: {mensaje}", codigo=err.get("code"))
    return datos


def cambiar_code_por_token(code):
    """Servidor a servidor: el único lugar donde se usa META_APP_SECRET."""
    params = {
        "client_id": _env_obligatoria("META_APP_ID", "cambiar el código por un token"),
        "client_secret": _env_obligatoria("META_APP_SECRET", "cambiar el código por un token"),
        "redirect_uri": redirect_uri(),
        "code": code,
    }
    try:
        resp = requests.get(f"{GRAPH_URL}/oauth/access_token", params=params, timeout=30)
    except requests.exceptions.RequestException as e:
        raise MetaConexionError(f"No pude hablar con Meta ({type(e).__name__}).") from None
    try:
        datos = resp.json() if resp.content else {}
    except ValueError:
        datos = {}
    if not resp.ok or "error" in datos or not datos.get("access_token"):
        err = datos.get("error") or {}
        raise MetaConexionError(f"Meta no aceptó la autorización: {err.get('message') or 'sin token'}",
                                codigo=err.get("code"))
    expira_en = None
    if datos.get("expires_in"):
        expira_en = (datetime.now() + timedelta(seconds=int(datos["expires_in"]))).isoformat(timespec="seconds")
    return {"token": datos["access_token"], "tipo_token": datos.get("token_type", ""), "expira_en": expira_en}


def obtener_perfil(token):
    return _graph_get("me", token, {"fields": "id,name,client_business_id"})


def listar_activos(token):
    """Cuentas publicitarias y Páginas que el token puede ver. Endpoints
    candidatos según la doc; la Task 7 confirma que sirven con un token de
    usuario del sistema y, si no, cambia a los edges del negocio
    (/{business_id}/owned_ad_accounts, /owned_pages)."""
    cuentas = _graph_get("me/adaccounts", token, {
        "fields": "id,name,account_status,currency", "limit": 100,
    }).get("data", [])
    paginas_raw = _graph_get("me/accounts", token, {
        "fields": "id,name,access_token,instagram_business_account{id,username}", "limit": 100,
    }).get("data", [])
    paginas = []
    for p in paginas_raw:
        ig = p.get("instagram_business_account") or {}
        paginas.append({
            "id": p["id"], "name": p.get("name", p["id"]), "access_token": p.get("access_token"),
            "ig_user_id": ig.get("id"), "ig_username": ig.get("username"),
        })
    return {"ad_accounts": cuentas, "pages": paginas}


def _detalle(datos):
    """Lo que se puede mostrar en pantalla: nunca tokens."""
    return {
        "ad_account_id": datos.get("ad_account_id"), "ad_account_nombre": datos.get("ad_account_nombre"),
        "page_id": datos.get("page_id"), "page_nombre": datos.get("page_nombre"),
        "ig_username": datos.get("ig_username"), "conectado_en": datos.get("conectado_en"),
        "moneda": datos.get("moneda"),
    }


def estado(cliente):
    """sin_conectar / conectado / roto. Una llamada barata a /me, cacheada
    10 min por proceso. Solo un error de token/permiso (190/10/200) marca
    'roto'; un fallo de red devuelve lo último conocido con verificado=False."""
    datos = cargar(cliente)
    if not datos or not datos.get("token"):
        return {"estado": "sin_conectar", "detalle": {}, "verificado": True}

    ahora = time.time()
    cacheado = _cache_estado.get(cliente)
    if cacheado and ahora - cacheado[0] < _TTL_ESTADO_SEG:
        return cacheado[1]

    try:
        _graph_get("me", datos["token"], {"fields": "id"}, timeout=5)
        resultado = {"estado": "conectado", "detalle": _detalle(datos), "verificado": True}
    except MetaConexionError as e:
        if e.codigo in CODIGOS_CONEXION_ROTA:
            resultado = {"estado": "roto", "detalle": _detalle(datos), "verificado": True, "motivo": str(e)}
        elif cacheado:
            # Un fallo de red (timeout, DNS, etc.) no debe volver a golpear a
            # Meta en cada render mientras dure la caída: se refresca el
            # timestamp del último estado conocido para que siga sirviendo de
            # caché en vez de reintentar la llamada de 30s en cada request.
            _cache_estado[cliente] = (ahora, cacheado[1])
            return cacheado[1]
        else:
            resultado = {"estado": "conectado", "detalle": _detalle(datos), "verificado": False}
    _cache_estado[cliente] = (ahora, resultado)
    return resultado


# ---------- Pixel ----------

def _parsear_fecha_meta(texto):
    """`last_fired_time` de Meta ('2026-09-15T10:00:00+0000') como datetime
    con zona, o None si viene vacío o en un formato inesperado."""
    if not texto:
        return None
    for formato in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(str(texto), formato)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(str(texto))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pixel_mas_reciente(pixels):
    """El pixel con el `last_fired_time` más reciente (los que nunca dispararon
    van al final; entre iguales, el primero que devolvió Meta)."""
    mejor, mejor_fecha = None, None
    for p in pixels:
        fecha = _parsear_fecha_meta(p.get("last_fired_time"))
        if mejor is None or (fecha is not None and (mejor_fecha is None or fecha > mejor_fecha)):
            mejor, mejor_fecha = p, fecha
    return mejor, mejor_fecha


def _listar_pixels_con_credenciales(cliente):
    # Imports tardíos: tareas.meta importa meta_conexion (ciclo) y meta_ads
    # solo se necesita acá; el lock es el mismo que usan las tareas de Meta
    # para que configurar() -> llamar -> limpiar() no se mezcle entre proyectos.
    from meta_ads import auth as meta_auth, pixel as meta_pixel  # noqa: PLC0415
    from tareas.meta import _LOCK  # noqa: PLC0415
    creds = credenciales_ads(cliente)
    with _LOCK:
        try:
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            return meta_pixel.listar_pixels()
        finally:
            meta_auth.limpiar()


def estado_pixel(cliente, solo_cache=False):
    """¿Tiene el proyecto un Pixel de Meta disparando? Cacheado 10 min por
    proceso (como estado()). Devuelve {estado, pixel_id, nombre,
    ultimo_disparo, detalle}:
      sin_conexion  Meta no está conectado (no se llama a la API)
      sin_pixel     la cuenta no tiene ningún pixel
      sin_datos     hay pixel pero nunca disparó, o no en los últimos 7 días
      ok            disparó en los últimos 7 días
      error         la API falló (detalle sin token)
    Con `solo_cache=True` nunca llama a Graph: devuelve lo cacheado o None
    si no hay nada vigente — para rutas POST (crear experimento) que no
    pueden esperar hasta 30 s bajo el lock de Meta — y para ver_cliente, que
    tampoco puede. Quien llena el caché es cfg_pixel_refrescar (el botón
    «Comprobar Pixel»/«Volver a comprobar» de Configuración, un POST)."""
    ahora = time.time()
    cacheado = _cache_pixel.get(cliente)
    if cacheado and ahora - cacheado[0] < _TTL_ESTADO_SEG:
        return cacheado[1]
    if solo_cache:
        return None

    resultado = {"estado": "sin_conexion", "pixel_id": None, "nombre": None, "ultimo_disparo": None, "detalle": ""}
    if estado(cliente).get("estado") != "conectado":
        resultado["detalle"] = "Meta no está conectado."
    else:
        try:
            pixels = _listar_pixels_con_credenciales(cliente)
        except Exception as e:  # noqa: BLE001 — cualquier fallo se muestra, nunca se relanza a una ruta
            import cola  # noqa: PLC0415
            resultado.update(estado="error", detalle=cola.sin_token(str(e)))
        else:
            if not pixels:
                resultado.update(estado="sin_pixel", detalle="La cuenta publicitaria no tiene ningún Pixel.")
            else:
                pixel, fecha = _pixel_mas_reciente(pixels)
                resultado.update(pixel_id=pixel.get("id"), nombre=pixel.get("name"),
                                 ultimo_disparo=pixel.get("last_fired_time"))
                if fecha is None:
                    resultado.update(estado="sin_datos", detalle="El Pixel existe pero nunca ha disparado.")
                elif datetime.now(timezone.utc) - fecha <= timedelta(days=_PIXEL_DIAS_VIVO):
                    resultado.update(estado="ok", detalle="El Pixel disparó en los últimos 7 días.")
                else:
                    resultado.update(estado="sin_datos",
                                     detalle=f"El Pixel lleva más de {_PIXEL_DIAS_VIVO} días sin disparar.")
    _cache_pixel[cliente] = (ahora, resultado)
    return resultado


def invalidar_pixel(cliente):
    """Olvida el estado del Pixel cacheado (p. ej. tras instalarlo en la
    tienda) para que la próxima consulta vuelva a preguntar a Meta."""
    _cache_pixel.pop(cliente, None)

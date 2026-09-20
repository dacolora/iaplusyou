"""
Meta en modo agencia: UNA conexión del Business Manager de Creatv (token de
usuario del sistema) que el admin conecta una sola vez, y de la que a cada
proyecto se le asigna una cuenta publicitaria y una Página de las que ese
Business posee o ve como socio de sus clientes.

Complementa ADR 0001 (cada proyecto trae su app): un proyecto está en modo
`propia` (lo de siempre) o `agencia` (esto), nunca en los dos. Ver ADR 0002 y
docs/superpowers/plans/2026-09-20-meta-agencia-multicliente.md.

Reglas que este módulo hace cumplir por sí mismo:
  - El token de agencia vive cifrado (Fernet con FLASK_SECRET_KEY, cifrado.py)
    en la tabla `kv`, clave `meta_agencia`. Nunca entra a un log, a un
    mensaje de excepción, a `publica()`/`estado()` ni a `meta.json`.
  - `meta.json` de un proyecto asignado guarda modo="agencia", los ids y el
    page_access_token (como en modo propia) — SIN token de usuario:
    `meta_conexion.cargar()` lo inyecta desde acá al leer.
  - Las URLs de paginación de Graph (`paging.next`) llevan el token: se sigue
    con el cursor `after`, jamás se registran.
"""
import json
import logging
import time
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import cifrado
import db
import estado as estado_mod
import meta_conexion
from meta_conexion import CODIGOS_CONEXION_ROTA, MetaConexionError

log = logging.getLogger(__name__)

CLAVE_KV = "meta_agencia"
MODO = "agencia"

_TTL_ACTIVOS_SEG = 600
_TTL_ESTADO_SEG = meta_conexion._TTL_ESTADO_SEG

# (timestamp, activos) — lista de cuentas/Páginas del Business, 10 min.
_cache_activos = None
# (timestamp, resultado) — estado() de la agencia, misma vida que meta_conexion.estado.
_cache_estado = None
# (cifrado, registro) — el último kv descifrado: derivar la clave Fernet cuesta
# ~0.1 s (PBKDF2), y cargar() de cada proyecto en modo agencia pide el token en
# cada render. Si el texto cifrado en kv cambia (otro proceso conectó o
# desconectó), se vuelve a descifrar.
_cache_registro = None


class MetaAgenciaError(MetaConexionError):
    """Error legible para el usuario. Nunca contiene un token."""


# ---------- almacenamiento cifrado en kv ----------

def _leer_kv():
    with db.conectar() as con:
        return con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE_KV)).scalar()


def _escribir_kv(valor):
    with db.conectar() as con:
        con.execute(insert_sqlite(db.kv).values(
            clave=CLAVE_KV, valor=valor, actualizado_en=db.ahora(),
        ).on_conflict_do_update(index_elements=["clave"], set_={"valor": valor, "actualizado_en": db.ahora()}))


def _borrar_kv():
    with db.conectar() as con:
        con.execute(db.kv.delete().where(db.kv.c.clave == CLAVE_KV))


def _cargar():
    """Registro completo (con token) o None. Un valor ilegible (cambió
    FLASK_SECRET_KEY, fila corrupta) cuenta como 'sin conectar': hay que
    volver a conectar la agencia.

    `_cache_registro` guarda (crudo, registro_o_None): un fallo de lectura
    también se cachea atado al mismo texto cifrado (M2 del review de Task 1)
    — sin esto, cada cargar() de cada proyecto en modo agencia (uno por
    render: moneda, estado, canales…) volvía a pagar el PBKDF2 de
    cifrado.descifrar (~0.1 s) y a loguear el warning mientras el admin no
    reconectaba."""
    global _cache_registro
    crudo = _leer_kv()
    if not crudo:
        _cache_registro = None
        return None
    if _cache_registro and _cache_registro[0] == crudo:
        registro = _cache_registro[1]
        return dict(registro) if registro else None
    try:
        registro = json.loads(cifrado.descifrar(crudo))
    except (cifrado.ErrorCifrado, ValueError):
        log.warning("meta_agencia: el registro guardado en kv no se puede leer (¿cambió FLASK_SECRET_KEY?)")
        _cache_registro = (crudo, None)
        return None
    if not isinstance(registro, dict) or not registro.get("token"):
        _cache_registro = (crudo, None)
        return None
    _cache_registro = (crudo, registro)
    return dict(registro)


def _registro_ilegible():
    """True si hay algo guardado en kv pero no se puede leer (rotó
    FLASK_SECRET_KEY, fila corrupta) — distinto de "nadie conectó la
    agencia todavía". Usa la misma caché que _cargar(): no vuelve a
    descifrar ni a loguear (M2/M3 del review de Task 1)."""
    crudo = _leer_kv()
    if not crudo:
        return False
    return _cargar() is None


def _sin_token(registro):
    return {k: v for k, v in registro.items() if k != "token"}


def _invalidar_caches(incluir_proyectos=True):
    """Tira lo cacheado acá y, si se pide, el estado/Pixel cacheado en
    meta_conexion de cada proyecto en modo agencia (su token cambió)."""
    global _cache_activos, _cache_estado
    _cache_activos = None
    _cache_estado = None
    if incluir_proyectos:
        for cliente in _clientes_en_modo_agencia():
            meta_conexion._cache_estado.pop(cliente, None)
            meta_conexion._cache_pixel.pop(cliente, None)


# ---------- conexión de la agencia ----------

def conectada():
    return _cargar() is not None


def publica():
    """Lo que se puede mostrar en pantalla: nunca el token."""
    registro = _cargar()
    return _sin_token(registro) if registro else None


def token():
    registro = _cargar()
    if not registro:
        raise MetaAgenciaError("La agencia no está conectada.")
    return registro["token"]


def conectar(token_usuario, business_id):
    """Valida el token contra Graph (/me y el Business) y lo guarda cifrado.
    Devuelve el registro público. Si algo falla no se guarda nada."""
    token_usuario = str(token_usuario or "").strip()
    business_id = str(business_id or "").strip()
    if not token_usuario or not business_id:
        raise MetaAgenciaError("Faltan datos: hacen falta el token del usuario del sistema y el id del Business.")
    if not cifrado.disponible():
        raise MetaAgenciaError("Falta FLASK_SECRET_KEY en el .env: sin ella no se puede guardar el token de la agencia.")
    usuario = meta_conexion._graph_get("me", token_usuario, {"fields": "id,name"})
    try:
        negocio = meta_conexion._graph_get(business_id, token_usuario, {"fields": "id,name"})
    except MetaConexionError as e:
        raise MetaAgenciaError(
            f"El token no ve el Business {business_id} ({e}). Revisa que el usuario del sistema "
            "pertenezca a ese Business Manager y tenga permiso business_management.", codigo=e.codigo) from None
    registro = {
        "business_id": str(negocio.get("id") or business_id),
        "business_nombre": negocio.get("name") or business_id,
        "usuario_id": usuario.get("id"),
        "usuario_nombre": usuario.get("name"),
        "token": token_usuario,
        "conectado_en": datetime.now().isoformat(timespec="seconds"),
        "graph_version": meta_conexion.GRAPH_VERSION,
    }
    _escribir_kv(cifrado.cifrar(json.dumps(registro, ensure_ascii=False)))
    _invalidar_caches()
    log.info("meta_agencia: Business %s conectado", registro["business_id"])
    return _sin_token(registro)


def desconectar():
    """Borra la conexión de la agencia y desasigna todos los proyectos que
    estaban en modo agencia (vuelven a modo propia, restaurando su
    `propia_respaldo` si lo tenían, o se quedan sin meta.json si no).

    M4 del review de Task 1: la alternativa (dejar los proyectos asignados
    con `page_access_token`s de un Business ya desconectado) permitía que
    `organico`/`meta_uploader` siguieran publicando en esas Páginas hasta que
    alguien desasignara cada proyecto a mano — un "desconectar" que no
    desconecta nada visible para el cliente. Se eligió la opción simple:
    desasignar todo de una. Devuelve {"habia": bool (si había una conexión
    que borrar), "desasignados": int (cuántos proyectos volvieron a propia)}."""
    global _cache_registro
    habia = _leer_kv() is not None
    clientes = _clientes_en_modo_agencia()
    desasignados = sum(1 for cliente in clientes if desasignar(cliente))
    _borrar_kv()
    _cache_registro = None
    # Los proyectos ya se desasignaron arriba (cada desasignar() invalida su
    # propia caché en meta_conexion); no hace falta que _invalidar_caches
    # los vuelva a recorrer.
    _invalidar_caches(incluir_proyectos=False)
    if habia or desasignados:
        log.info("meta_agencia: Business desconectado (%d proyecto(s) desasignado(s))", desasignados)
    return {"habia": habia, "desasignados": desasignados}


def estado():
    """sin_conectar / conectada / rota, con una llamada barata a /me cacheada
    10 min por proceso (como meta_conexion.estado). Solo un error de
    token/permiso marca 'rota'; un fallo de red devuelve lo último conocido."""
    global _cache_estado
    registro = _cargar()
    if not registro:
        return {"estado": "sin_conectar", "detalle": {}, "verificado": True, "motivo": ""}
    ahora = time.time()
    if _cache_estado and ahora - _cache_estado[0] < _TTL_ESTADO_SEG:
        return _cache_estado[1]
    detalle = _sin_token(registro)
    try:
        meta_conexion._graph_get("me", registro["token"], {"fields": "id"}, timeout=5)
        resultado = {"estado": "conectada", "detalle": detalle, "verificado": True, "motivo": ""}
    except MetaConexionError as e:
        if e.codigo in CODIGOS_CONEXION_ROTA:
            resultado = {"estado": "rota", "detalle": detalle, "verificado": True, "motivo": str(e)}
        elif _cache_estado:
            _cache_estado = (ahora, _cache_estado[1])
            return _cache_estado[1]
        else:
            resultado = {"estado": "conectada", "detalle": detalle, "verificado": False, "motivo": str(e)}
    _cache_estado = (ahora, resultado)
    return resultado


# ---------- activos del Business ----------

_TOPE_PAGINAS = 50  # 50 * limit(100) = 5 000 activos por edge; ver M1 abajo.


def _paginar(edge, token_usuario, params):
    """Recorre todas las páginas de un edge siguiendo el cursor `after`.
    `paging.next` trae el token en la URL: no se usa ni se registra.

    M1 del review de Task 1: sin tope, un Graph que repitiera el mismo
    cursor (o no lo avanzara nunca) dejaba esto en un `while True` contra un
    tercero. Corta si el cursor no avanza y, por si Meta sí avanza el cursor
    pero jamás termina de paginar, a los 50 páginas (5 000 activos — nadie
    real tiene tantas cuentas/Páginas en un Business) con un error claro en
    vez de colgar el proceso."""
    filas = []
    cursor = None
    for _ in range(_TOPE_PAGINAS):
        p = {**params, "limit": 100}
        if cursor:
            p["after"] = cursor
        datos = meta_conexion._graph_get(edge, token_usuario, p)
        filas.extend(datos.get("data") or [])
        paging = datos.get("paging") or {}
        siguiente = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not siguiente or siguiente == cursor:
            return filas
        cursor = siguiente
    raise MetaAgenciaError(
        f"Meta no termina de paginar {edge} después de {_TOPE_PAGINAS} páginas — parece un bucle; "
        "revisa el Business o avisa a soporte.")


def _negocio(fila):
    negocio = fila.get("business") or {}
    return (str(negocio["id"]) if negocio.get("id") else None), (negocio.get("name") or None)


def _cuenta(fila, origen):
    business_id, business_nombre = _negocio(fila)
    return {
        "id": fila["id"], "name": fila.get("name") or fila["id"],
        "currency": fila.get("currency"), "account_status": fila.get("account_status"),
        "activa": fila.get("account_status") == 1,
        "origen": origen,
        "business_id": business_id, "business_nombre": business_nombre,
    }


def _pagina(fila, origen):
    ig = fila.get("instagram_business_account") or {}
    business_id, business_nombre = _negocio(fila)
    return {
        "id": fila["id"], "name": fila.get("name") or fila["id"],
        "ig_user_id": ig.get("id"), "ig_username": ig.get("username"),
        "origen": origen,
        "business_id": business_id, "business_nombre": business_nombre,
    }


CAMPOS_CUENTA = "id,name,currency,account_status,business{id,name}"
CAMPOS_PAGINA = "id,name,instagram_business_account{id,username},business{id,name}"
CAMPOS_PAGINA_SIN_DUENO = "id,name,instagram_business_account{id,username}"


def _paginar_paginas(edge, tok):
    """`business` en una Página exige business_management y que quien generó
    el token administre la Página; si Meta rechaza el campo (code 100) se
    lista sin dueño en vez de dejar al admin sin Páginas."""
    try:
        return _paginar(edge, tok, {"fields": CAMPOS_PAGINA})
    except MetaConexionError as e:
        if e.codigo != 100:
            raise
        log.info("meta_agencia: %s no acepta business{id,name}; se lista sin dueño", edge)
        return _paginar(edge, tok, {"fields": CAMPOS_PAGINA_SIN_DUENO})


def listar_activos(forzar=False):
    """Cuentas publicitarias y Páginas que el Business posee (origen 'propia')
    o administra para sus clientes socios (origen 'cliente'), cada una con el
    portafolio dueño (`business_id`/`business_nombre`, None si Meta no lo
    entrega). Cacheado 10 min por proceso; `forzar=True` vuelve a preguntar."""
    global _cache_activos
    ahora = time.time()
    if not forzar and _cache_activos and ahora - _cache_activos[0] < _TTL_ACTIVOS_SEG:
        return _cache_activos[1]
    registro = _cargar()
    if not registro:
        raise MetaAgenciaError("La agencia no está conectada.")
    tok, bid = registro["token"], registro["business_id"]
    cuentas, paginas = {}, {}
    for edge, origen in ((f"{bid}/owned_ad_accounts", "propia"), (f"{bid}/client_ad_accounts", "cliente")):
        for fila in _paginar(edge, tok, {"fields": CAMPOS_CUENTA}):
            cuentas.setdefault(fila["id"], _cuenta(fila, origen))
    for edge, origen in ((f"{bid}/owned_pages", "propia"), (f"{bid}/client_pages", "cliente")):
        for fila in _paginar_paginas(edge, tok):
            paginas.setdefault(fila["id"], _pagina(fila, origen))
    activos = {"ad_accounts": list(cuentas.values()), "pages": list(paginas.values())}
    _cache_activos = (ahora, activos)
    return activos


def _token_pagina(page_id, token_usuario):
    """Token de Página (y su Instagram) con el token de usuario del sistema.
    Es lo que uploaders/meta_uploader lee de meta.json."""
    datos = meta_conexion._graph_get(page_id, token_usuario, {
        "fields": "access_token,name,instagram_business_account{id,username}",
    })
    if not datos.get("access_token"):
        raise MetaAgenciaError(
            f"Meta no entregó token para la Página {page_id}: el usuario del sistema necesita la Página "
            "asignada con permisos de contenido (pages_manage_posts).")
    ig = datos.get("instagram_business_account") or {}
    return {
        "page_access_token": datos["access_token"], "page_nombre": datos.get("name"),
        "ig_user_id": ig.get("id"), "ig_username": ig.get("username"),
    }


# ---------- solicitudes de clientes ----------
# Un cliente en forma «agencia» que no vio sus activos (Meta tarda, o el
# nivel Limited no lista socios) pide que Creatv termine la conexión a mano.
# Una fila en kv por proyecto (clave meta_solicitud:<cliente>); asignar() y
# desasignar() la borran. Nunca guarda nada secreto: ids y texto.

PREFIJO_SOLICITUD = "meta_solicitud:"


def _clave_solicitud(cliente):
    return f"{PREFIJO_SOLICITUD}{cliente}"


def solicitar(cliente, portafolio_id, ad_account_id=None, page_id=None, nota=None, usuario=None):
    """Guarda (o reemplaza) la solicitud pendiente del proyecto y la devuelve."""
    datos = {
        "cliente": cliente,
        "portafolio_id": str(portafolio_id or "").strip(),
        "ad_account_id": str(ad_account_id or "").strip() or None,
        "page_id": str(page_id or "").strip() or None,
        "nota": str(nota or "").strip()[:500] or None,
        "usuario": usuario,
        "creado_en": datetime.now().isoformat(timespec="seconds"),
    }
    if not datos["portafolio_id"]:
        raise MetaAgenciaError("Falta el id de tu portafolio comercial.")
    valor = json.dumps(datos, ensure_ascii=False)
    with db.conectar() as con:
        con.execute(insert_sqlite(db.kv).values(
            clave=_clave_solicitud(cliente), valor=valor, actualizado_en=db.ahora(),
        ).on_conflict_do_update(index_elements=["clave"], set_={"valor": valor, "actualizado_en": db.ahora()}))
    return datos


def _solicitud_de(crudo, cliente):
    try:
        datos = json.loads(crudo)
    except (TypeError, ValueError):
        return None
    if not isinstance(datos, dict):
        return None
    datos.setdefault("cliente", cliente)
    return datos


def solicitud(cliente):
    """La solicitud pendiente del proyecto, o None."""
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == _clave_solicitud(cliente))).scalar()
    return _solicitud_de(crudo, cliente) if crudo else None


def solicitudes():
    """Todas las solicitudes pendientes, la más antigua primero."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.kv.c.clave, db.kv.c.valor)
                            .where(db.kv.c.clave.like(f"{PREFIJO_SOLICITUD}%"))).all()
    out = [s for clave, crudo in filas if (s := _solicitud_de(crudo, clave[len(PREFIJO_SOLICITUD):]))]
    return sorted(out, key=lambda s: s.get("creado_en") or "")


def borrar_solicitud(cliente):
    """True si había una solicitud que borrar."""
    with db.conectar() as con:
        return bool(con.execute(db.kv.delete().where(db.kv.c.clave == _clave_solicitud(cliente))).rowcount)


# ---------- asignación por proyecto ----------

def _clientes_en_modo_agencia():
    try:
        clientes = estado_mod.listar_clientes()
    except OSError:
        return []
    return [c for c in clientes if meta_conexion.modo(c) == MODO]


def asignar(cliente, ad_account_id, page_id=None, asignado_por=None, portafolio_id=None):
    """Pone el proyecto en modo agencia con esa cuenta (y Página). Los datos
    propios previos (incluido su token) quedan en `propia_respaldo` dentro del
    mismo meta.json (0600) para restaurarlos con desasignar(). Una cuenta
    publicitaria solo puede estar asignada a un proyecto (spec 2026-09-20
    §2.3). `portafolio_id` es el portafolio del cliente que la compartió
    (auditoría; si falta se guarda el dueño que reportó Meta). Devuelve el
    detalle público (meta_conexion._detalle) con `cambio_cuenta` cuando la
    cuenta asignada es distinta a la que el proyecto tenía."""
    registro = _cargar()
    if not registro:
        raise MetaAgenciaError("La agencia no está conectada.")
    activos = listar_activos()
    cuenta = next((a for a in activos["ad_accounts"] if a["id"] == ad_account_id), None)
    if not cuenta:
        raise MetaAgenciaError(f"La cuenta publicitaria {ad_account_id} no está entre las que ve el Business de la agencia.")
    ocupada = cuentas_asignadas().get(cuenta["id"])
    if ocupada and ocupada != cliente:
        raise MetaAgenciaError("Esa cuenta publicitaria ya está conectada a otro proyecto; avísale a Creatv.")
    pagina = None
    if page_id:
        pagina = next((p for p in activos["pages"] if p["id"] == page_id), None)
        if not pagina:
            raise MetaAgenciaError(f"La Página {page_id} no está entre las que ve el Business de la agencia.")

    previo = meta_conexion._cargar_crudo(cliente) or {}
    if previo.get("modo") == MODO:
        respaldo = previo.get("propia_respaldo")
        modo_anterior = previo.get("modo_anterior") or "propia"
    else:
        respaldo = previo or None
        modo_anterior = "propia"
    cuenta_previa = previo.get("ad_account_id")

    datos = {
        "modo": MODO,
        "modo_anterior": modo_anterior,
        "business_id": registro["business_id"],
        "ad_account_id": cuenta["id"],
        "ad_account_nombre": cuenta.get("name"),
        "ad_account_origen": cuenta.get("origen"),
        "moneda": cuenta.get("currency"),
        "page_id": None, "page_nombre": None, "page_origen": None, "page_access_token": None,
        "ig_user_id": None, "ig_username": None,
        "asignado_en": datetime.now().isoformat(timespec="seconds"),
        "asignado_por": asignado_por,
        "portafolio_cliente_id": str(portafolio_id).strip() if portafolio_id else cuenta.get("business_id"),
        "graph_version": meta_conexion.GRAPH_VERSION,
    }
    if pagina:
        datos.update(_token_pagina(pagina["id"], registro["token"]))
        datos.update(page_id=pagina["id"], page_origen=pagina.get("origen"))
        datos["page_nombre"] = datos.get("page_nombre") or pagina.get("name")
        datos["ig_user_id"] = datos.get("ig_user_id") or pagina.get("ig_user_id")
        datos["ig_username"] = datos.get("ig_username") or pagina.get("ig_username")
    if respaldo:
        datos["propia_respaldo"] = respaldo
    assert "token" not in datos  # el token de usuario nunca se escribe en meta.json
    meta_conexion.guardar(cliente, datos, permitir_agencia=True)
    borrar_solicitud(cliente)
    log.info("meta_agencia: proyecto %s asignado a la cuenta %s", cliente, cuenta["id"])
    detalle = meta_conexion._detalle(datos)
    detalle["cambio_cuenta"] = bool(cuenta_previa and cuenta_previa != cuenta["id"])
    return detalle


def desasignar(cliente):
    """Saca el proyecto del modo agencia: restaura `propia_respaldo` si lo
    había o borra meta.json. Nunca toca la conexión de la agencia. Devuelve
    True si el proyecto estaba asignado."""
    previo = meta_conexion._cargar_crudo(cliente)
    if not previo or previo.get("modo") != MODO:
        return False
    respaldo = previo.get("propia_respaldo")
    if isinstance(respaldo, dict) and respaldo:
        respaldo = {k: v for k, v in respaldo.items() if k not in ("modo", "propia_respaldo")}
        meta_conexion.guardar(cliente, respaldo, permitir_agencia=True)
    else:
        meta_conexion._borrar_crudo(cliente)
    borrar_solicitud(cliente)
    log.info("meta_agencia: proyecto %s vuelve a modo propia", cliente)
    return True


def proyectos_asignados():
    """{cliente: detalle público} de todos los proyectos en modo agencia."""
    out = {}
    for cliente in _clientes_en_modo_agencia():
        datos = meta_conexion._cargar_crudo(cliente) or {}
        out[cliente] = meta_conexion._detalle(datos)
    return out


def cuentas_asignadas():
    """{ad_account_id: cliente} de los proyectos en modo agencia."""
    return {d["ad_account_id"]: c for c, d in proyectos_asignados().items() if d.get("ad_account_id")}


# ---------- autoservicio del cliente (spec 2026-09-20 §2.2) ----------

def activos_de_portafolio(portafolio_id, cliente=None, forzar=False):
    """Cuentas y Páginas de socio cuyo dueño es ese portafolio, sin las
    cuentas ya asignadas a OTRO proyecto (`cliente` es el que pregunta: su
    propia cuenta sí se muestra). `paginas_sin_dueno` es True cuando hay
    Páginas de socio pero Meta no dijo de quién es ninguna (la pantalla pide
    entonces el id de la Página a mano)."""
    portafolio_id = str(portafolio_id or "").strip()
    if not portafolio_id:
        raise MetaAgenciaError("Falta el id de tu portafolio comercial.")
    activos = listar_activos(forzar=forzar)
    ocupadas = cuentas_asignadas()
    cuentas = [a for a in activos["ad_accounts"]
               if a["origen"] == "cliente" and a["business_id"] == portafolio_id
               and ocupadas.get(a["id"]) in (None, cliente)]
    de_socios = [p for p in activos["pages"] if p["origen"] == "cliente"]
    paginas = [p for p in de_socios if p["business_id"] == portafolio_id]
    return {
        "ad_accounts": cuentas,
        "pages": paginas,
        "paginas_sin_dueno": bool(de_socios) and all(p["business_id"] is None for p in de_socios),
    }


def pagina_de_socio(page_id):
    """La Página de socio con ese id (respaldo cuando Meta no entrega el
    dueño), o None si no está compartida con el Business."""
    page_id = str(page_id or "").strip()
    if not page_id:
        return None
    return next((p for p in listar_activos()["pages"] if p["origen"] == "cliente" and p["id"] == page_id), None)

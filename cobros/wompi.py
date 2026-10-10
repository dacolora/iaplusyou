"""Wompi (pasarela colombiana; spec planes 2026-10-09 §5): checkout de una
recarga, aceptaciones, fuentes de pago (tarjeta o Nequi), el cobro de un
periodo y la firma de los eventos. El ÚNICO módulo que habla con Wompi.
Referencia de la API (endpoints, campos, firmas y lo que la doc no aclara):
docs/pagos/wompi-api.md.

Llaves en el .env: WOMPI_LLAVE_PUBLICA, WOMPI_LLAVE_PRIVADA,
WOMPI_SECRETO_EVENTOS, WOMPI_SECRETO_INTEGRIDAD. El prefijo de la llave dice
el ambiente (`pub_test_`/`prv_test_` → sandbox; `pub_prod_`/`prv_prod_` →
producción) y las llaves de pruebas solo valen si PLATAFORMA_URL es local
(como BOLD_PRUEBAS): en el VPS una llave de pruebas olvidada no crearía
checkouts que acreditan saldo real ni volvería falsificables los eventos.

Solo hosts fijos (SANDBOX, PRODUCCION, CHECKOUT), sin seguir redirecciones;
ningún texto de error lleva una llave, la URL ni la respuesta: dicen el
código HTTP o el tipo de error de red (y se lanzan `from None`)."""
import hashlib
import hmac
import os
import re
from urllib.parse import urlencode, urlsplit

import requests
from flask_babel import gettext

from cobros._entorno import plataforma_local

SANDBOX = "https://sandbox.wompi.co/v1"
PRODUCCION = "https://production.wompi.co/v1"
CHECKOUT = "https://checkout.wompi.co/p/"
TIEMPO = 15                  # worker, crear la fuente, cobrar: Wompi puede tardar
TIEMPO_INTERACTIVO = (3, 5)  # (conectar, leer) de un sondeo de la página: no retener un hilo de gunicorn
MONEDA = "COP"               # Wompi Colombia solo cobra en pesos (wompi-api.md §10)
TIPOS_FUENTE = ("CARD", "NEQUI")

_PREFIJOS = {
    "WOMPI_LLAVE_PUBLICA": ("pub_test_", "pub_prod_"),
    "WOMPI_LLAVE_PRIVADA": ("prv_test_", "prv_prod_"),
    "WOMPI_SECRETO_EVENTOS": ("test_events_", "prod_events_"),
    "WOMPI_SECRETO_INTEGRIDAD": ("test_integrity_", "prod_integrity_"),
}
_TX_ID = re.compile(r"[0-9A-Za-z]{1,24}(?:-[0-9A-Za-z]{1,24}){0,4}")   # «1292-1602113476-10985»
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,200}")                          # tok_…, nequi_…
_PROPIEDAD = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*")
_CELULAR = re.compile(r"3\d{9}")


class ErrorWompi(Exception):
    """Wompi no respondió lo esperado. El texto va en palabras y sin llaves.

    - `caida`: Wompi no está disponible (red, tiempo agotado o HTTP 5xx); quien
      consulta muchas seguidas para ahí.
    - `incierto`: SOLO en un cobro (`cobrar_fuente`): el pedido pudo llegar y
      Wompi pudo cobrar (tiempo agotado leyendo, conexión cortada, 5xx, 2xx
      ilegible). Quien llama deja el pago pendiente y lo reconcilia; nunca
      reintenta con otra referencia (sería un segundo cobro).
    - `codigo`: el HTTP de Wompi, si lo hubo.
    - `referencia_usada`: 422 «The reference has already been used».
    """

    def __init__(self, mensaje, caida=False, codigo=None, incierto=False, referencia_usada=False):
        super().__init__(mensaje)
        self.caida = bool(caida)
        self.codigo = codigo
        self.incierto = bool(incierto)
        self.referencia_usada = bool(referencia_usada)


# ------------------------------------------------------------- llaves ---

def _llave(nombre):
    # strip(): un espacio de más al final del .env haría fallar todas las firmas.
    return (os.environ.get(nombre) or "").strip()


def _publica():
    return _llave("WOMPI_LLAVE_PUBLICA")


def _privada():
    return _llave("WOMPI_LLAVE_PRIVADA")


def _secreto_eventos():
    return _llave("WOMPI_SECRETO_EVENTOS")


def _secreto_integridad():
    return _llave("WOMPI_SECRETO_INTEGRIDAD")


def _ambiente_de(nombre):
    """"test", "prod" o None (prefijo desconocido) según la llave."""
    valor = _llave(nombre)
    prueba, prod = _PREFIJOS[nombre]
    if valor.startswith(prueba) and len(valor) > len(prueba):
        return "test"
    if valor.startswith(prod) and len(valor) > len(prod):
        return "prod"
    return None


def _estado():
    """(ambiente, problema): el ambiente si todo cuadra; si no, el problema en palabras."""
    if not all(_llave(n) for n in _PREFIJOS):
        return None, gettext("Faltan las llaves de Wompi")
    ambiente = _ambiente_de("WOMPI_LLAVE_PUBLICA")
    if ambiente is None or _ambiente_de("WOMPI_LLAVE_PRIVADA") != ambiente:
        return None, gettext("Las llaves de Wompi no son válidas o mezclan pruebas y producción")
    # Los secretos: si su prefijo es reconocible tiene que ser del mismo ambiente
    # (un prefijo distinto se acepta: la doc no garantiza su forma).
    for nombre in ("WOMPI_SECRETO_EVENTOS", "WOMPI_SECRETO_INTEGRIDAD"):
        otro = _ambiente_de(nombre)
        if otro is not None and otro != ambiente:
            return None, gettext("Las llaves de Wompi no son válidas o mezclan pruebas y producción")
    if ambiente == "test" and not plataforma_local():
        return None, gettext("Las llaves de pruebas de Wompi solo sirven en un servidor local")
    return ambiente, None


def configurado():
    """Las cuatro llaves, del mismo ambiente, y las de pruebas solo en local."""
    return _estado()[1] is None


def llave_publica():
    """La llave pública para el widget de tokenización (planes 6/8: va en el
    HTML del formulario de alta, `data-public-key`; es pública por diseño), o
    None si Wompi no está configurado. Nunca las otras tres."""
    return _publica() if configurado() else None


WIDGET = "https://checkout.wompi.co/widget.js"   # el widget de tokenización (wompi-api.md §5.b)


def pruebas():
    """¿Las llaves son de pruebas (sandbox)? No dice si sirven: eso es `configurado`."""
    return _ambiente_de("WOMPI_LLAVE_PUBLICA") == "test"


def pruebas_fuera_de_local():
    """Llaves de pruebas en un servidor que no es local: Wompi queda apagado y el admin lo ve."""
    return pruebas() and not plataforma_local()


def _exigir():
    ambiente, problema = _estado()
    if problema:
        raise ErrorWompi(problema)
    return ambiente


def base_url():
    return SANDBOX if _exigir() == "test" else PRODUCCION


# ------------------------------------------------------------- HTTP ---

def _referencia_usada(datos):
    try:
        mensajes = (datos.get("error") or {}).get("messages") or {}
        return any("already" in str(m).lower() for m in (mensajes.get("reference") or []))
    except AttributeError:
        return False


def _pedir(verbo, ruta, *, llave=None, cabeceras=None, cuerpo=None, tiempo=TIEMPO, cobro=False):
    """Pide a un host fijo de Wompi y devuelve `data` (un dict). `cobro=True`
    marca `incierto` en todo error en el que Wompi pudo haber cobrado."""
    url = base_url() + ruta
    h = {"Accept": "application/json", **(cabeceras or {})}
    if llave:
        h["Authorization"] = f"Bearer {llave}"
    k = {"headers": h, "timeout": tiempo, "allow_redirects": False}
    if cuerpo is not None:
        k["json"] = cuerpo
    try:
        r = getattr(requests, verbo)(url, **k)
    except requests.ConnectTimeout:
        # No llegó a conectar: el pedido no salió, no hay cobro posible.
        raise ErrorWompi(gettext("No se pudo hablar con Wompi (%(tipo)s)", tipo="ConnectTimeout"),
                         caida=True) from None
    except requests.RequestException as e:
        # Solo el nombre del error: el texto de requests puede traer la URL o cabeceras.
        raise ErrorWompi(gettext("No se pudo hablar con Wompi (%(tipo)s)", tipo=type(e).__name__),
                         caida=True, incierto=cobro) from None
    codigo = r.status_code
    if 300 <= codigo < 400:
        raise ErrorWompi(gettext("Wompi respondió algo inesperado (HTTP %(codigo)s)", codigo=codigo), codigo=codigo)
    try:
        j = r.json()
    except ValueError:
        j = None
    if codigo >= 400:
        usada = codigo == 422 and isinstance(j, dict) and _referencia_usada(j)
        mensaje = (gettext("Wompi dice que esa referencia de pago ya se usó") if usada else
                   gettext("Wompi no aceptó el pedido (HTTP %(codigo)s)", codigo=codigo))
        raise ErrorWompi(mensaje, caida=codigo >= 500, codigo=codigo,
                         incierto=cobro and codigo >= 500, referencia_usada=usada)
    if j is None:
        raise ErrorWompi(gettext("Wompi respondió algo que no es JSON"), codigo=codigo, incierto=cobro)
    datos = j.get("data") if isinstance(j, dict) else None
    if not isinstance(datos, dict):
        raise ErrorWompi(gettext("Wompi no devolvió los datos esperados"), codigo=codigo, incierto=cobro)
    return datos


def _entero(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _texto(v, largo):
    return str(v)[:largo] if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v) else None


def _transaccion(d):
    return {
        "id": _texto(d.get("id"), 64),
        "reference": _texto(d.get("reference"), 255),
        "status": (_texto(d.get("status"), 20) or "").upper(),
        "amount_in_cents": _entero(d.get("amount_in_cents")),
        "currency": _texto(d.get("currency"), 3),
        "payment_method_type": _texto(d.get("payment_method_type"), 30),
        "status_message": _texto(d.get("status_message"), 300),
        "payment_source_id": _entero(d.get("payment_source_id")),
    }


# ------------------------------------------------------- validaciones ---

def _validar_referencia(referencia):
    if not isinstance(referencia, str) or not 1 <= len(referencia) <= 255 or not referencia.isprintable():
        raise ErrorWompi(gettext("Referencia de pago inválida"))
    return referencia


def _validar_centavos(centavos):
    if _entero(centavos) is None or centavos <= 0:
        raise ErrorWompi(gettext("Monto inválido para Wompi"))
    return centavos


def _validar_correo(correo):
    if not isinstance(correo, str) or "@" not in correo or not 3 <= len(correo.strip()) <= 254:
        raise ErrorWompi(gettext("Correo de cobro inválido"))
    return correo.strip()


def correo_valido(correo):
    """El correo limpio si Wompi lo aceptaría; si no, None (el checkout lo pide)."""
    try:
        return _validar_correo(correo)
    except ErrorWompi:
        return None


def _validar_token(token):
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise ErrorWompi(gettext("Token de pago inválido"))
    return token


# ------------------------------------------------------------ firmas ---

def firma_integridad(referencia, centavos, moneda=MONEDA, expiracion=None):
    """sha256 hex de referencia + centavos + moneda [+ vencimiento] + secreto
    de integridad (wompi-api.md §4). La misma firma va en el checkout y en
    cada transacción con fuente (§7)."""
    _exigir()
    _validar_referencia(referencia)
    _validar_centavos(centavos)
    vence = "" if expiracion is None else str(expiracion)
    cadena = f"{referencia}{centavos}{moneda}{vence}{_secreto_integridad()}"
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest()


def evento_valido(cuerpo, checksum_header=None):
    """Firma de un evento (wompi-api.md §8): sha256 de los valores de
    `signature.properties` (rutas dentro de `data`, en orden) + `timestamp` +
    secreto de eventos, comparado en tiempo constante (sin importar
    mayúsculas) con `signature.checksum` y, si viene, con X-Event-Checksum.
    Cualquier forma rara → False, nunca una excepción. Con llaves de pruebas
    fuera de local (o sin secreto) → False."""
    if not configurado():
        return False
    if not isinstance(cuerpo, dict):
        return False
    firma, datos = cuerpo.get("signature"), cuerpo.get("data")
    if not isinstance(firma, dict) or not isinstance(datos, dict):
        return False
    propiedades, marca, suma = firma.get("properties"), firma.get("timestamp"), firma.get("checksum")
    if not isinstance(propiedades, list) or not propiedades or not isinstance(suma, str) or not suma.strip():
        return False
    if _entero(marca) is None:
        return False
    valores = []
    for prop in propiedades:
        if not isinstance(prop, str) or not _PROPIEDAD.fullmatch(prop):
            return False
        nodo = datos
        for parte in prop.split("."):
            if not isinstance(nodo, dict) or parte not in nodo:
                return False
            nodo = nodo[parte]
        # Solo texto o entero: un nulo, un objeto o un booleano no tienen una
        # forma documentada en la cadena firmada (wompi-api.md §13.5).
        if _texto(nodo, 10_000) is None and nodo != "":
            return False
        valores.append(str(nodo))
    cadena = "".join(valores) + str(marca) + _secreto_eventos()
    esperado = hashlib.sha256(cadena.encode("utf-8")).hexdigest().encode()

    def igual(otro):
        # En bytes: compare_digest con un str que no es ASCII lanza TypeError.
        return hmac.compare_digest(esperado, str(otro).strip().lower().encode("utf-8", "replace"))

    if not igual(suma):
        return False
    if checksum_header is not None and str(checksum_header).strip() and not igual(checksum_header):
        return False
    return True


# ---------------------------------------------------------- checkout ---

def url_checkout(referencia, centavos, redirect_url, correo=None):
    """La URL del Web Checkout (GET a https://checkout.wompi.co/p/) con los
    parámetros de la doc, codificados como los manda un formulario."""
    firma = firma_integridad(referencia, centavos)
    try:
        partes = urlsplit(str(redirect_url or ""))
    except ValueError:
        partes = None
    if partes is None or partes.scheme not in ("http", "https") or not partes.netloc:
        raise ErrorWompi(gettext("La dirección de vuelta del pago no es válida"))
    params = [
        ("public-key", _publica()),
        ("currency", MONEDA),
        ("amount-in-cents", str(centavos)),
        ("reference", referencia),
        ("signature:integrity", firma),
        ("redirect-url", str(redirect_url)),
    ]
    if correo:
        params.append(("customer-data:email", _validar_correo(correo)))
    return CHECKOUT + "?" + urlencode(params)


# ------------------------------------------------------- aceptaciones ---

def _enlace_https(v):
    if not isinstance(v, str) or len(v) > 2000:
        return None
    try:
        p = urlsplit(v)
    except ValueError:
        return None
    return v if p.scheme == "https" and p.netloc else None


def aceptaciones(tiempo=TIEMPO):
    """Los dos contratos que la persona acepta antes de registrar su medio de
    pago (wompi-api.md §2): `GET /merchants/info` con la llave pública en la
    cabecera x-merchant-public-key (el GET /merchants/<llave> se apaga el
    2026-10-31). Los tokens duran poco (≈1 h): se piden al mostrar el
    formulario y se usan al crear la fuente."""
    d = _pedir("get", "/merchants/info", cabeceras={"x-merchant-public-key": _publica()}, tiempo=tiempo)
    salida = {}
    for clave, nombre in (("presigned_acceptance", "acceptance"), ("presigned_personal_data_auth", "personal")):
        bloque = d.get(clave)
        token = bloque.get("acceptance_token") if isinstance(bloque, dict) else None
        enlace = _enlace_https(bloque.get("permalink")) if isinstance(bloque, dict) else None
        if not isinstance(token, str) or not token.strip() or len(token) > 8000 or not enlace:
            raise ErrorWompi(gettext("Wompi no devolvió los contratos para aceptar"))
        salida[f"{nombre}_token"] = token.strip()
        salida[f"{nombre}_url"] = enlace
    return salida


# ------------------------------------------------------- transacciones ---

def id_valido(transaccion_id):
    """¿Tiene forma de id de transacción de Wompi («1292-1602113476-10985»)?
    Para el `?id=` que agrega Wompi a la vuelta del checkout (lo escribe quien
    sea): solo con esto se consulta."""
    return isinstance(transaccion_id, str) and len(transaccion_id) <= 64 and bool(_TX_ID.fullmatch(transaccion_id))


def normalizar(datos):
    """La transacción de un evento (`data.transaction`) con la misma forma que
    devuelve `transaccion()`; un dict vacío si no es un objeto."""
    return _transaccion(datos if isinstance(datos, dict) else {})


def transaccion(transaccion_id, tiempo=TIEMPO):
    """`GET /transactions/<id>` con la llave privada: la verdad sobre un pago
    (la vuelta del checkout nunca acredita sin esto)."""
    if not id_valido(transaccion_id):
        raise ErrorWompi(gettext("Identificador de transacción inválido"))
    d = _pedir("get", f"/transactions/{transaccion_id}", llave=_privada(), tiempo=tiempo)
    return _transaccion(d)


def _resumen(tipo, publico):
    if not isinstance(publico, dict):
        return ""
    if tipo == "NEQUI":
        cel = re.sub(r"\D", "", str(publico.get("phone_number") or ""))
        return f"Nequi ···{cel[-4:]}" if len(cel) >= 4 else ""
    ultimos = str(publico.get("last_four") or "")
    if not re.fullmatch(r"\d{4}", ultimos):
        return ""
    marca = publico.get("brand")
    marca = marca.strip().title() if isinstance(marca, str) and re.fullmatch(r"[A-Za-z ]{2,20}", marca.strip()) else ""
    return f"{marca} ···{ultimos}".strip()


def crear_fuente(tipo, token, correo, acceptance_token, personal_token, tiempo=TIEMPO):
    """`POST /payment_sources` con la llave privada (wompi-api.md §6): una
    tarjeta tokenizada por el widget o un token de Nequi aprobado, con las dos
    aceptaciones. Devuelve {"id", "tipo", "resumen"} («Visa ···4242»; vacío
    si Wompi no manda los datos públicos)."""
    if tipo not in TIPOS_FUENTE:
        raise ErrorWompi(gettext("Medio de pago no soportado"))
    _validar_token(token)
    correo = _validar_correo(correo)
    for t in (acceptance_token, personal_token):
        if not isinstance(t, str) or not t.strip() or len(t) > 8000:
            raise ErrorWompi(gettext("Faltan las aceptaciones de Wompi"))
    cuerpo = {"type": tipo, "token": token, "customer_email": correo,
              "acceptance_token": acceptance_token.strip(), "accept_personal_auth": personal_token.strip()}
    d = _pedir("post", "/payment_sources", llave=_privada(), cuerpo=cuerpo, tiempo=tiempo)
    fuente = _entero(d.get("id"))
    estado = (_texto(d.get("status"), 20) or "").upper()
    if estado != "AVAILABLE":
        raise ErrorWompi(gettext("Wompi no aceptó el medio de pago (%(estado)s)", estado=estado or "?"))
    if fuente is None or fuente <= 0:
        raise ErrorWompi(gettext("Wompi no devolvió los datos esperados"))
    tipo_real = str(d.get("type") or tipo).upper()
    tipo_real = tipo_real if tipo_real in TIPOS_FUENTE else tipo
    return {"id": fuente, "tipo": tipo_real, "resumen": _resumen(tipo_real, d.get("public_data"))}


def cobrar_fuente(fuente_id, centavos, correo, referencia, *, tipo="CARD", acceptance_token=None, tiempo=TIEMPO):
    """`POST /transactions` con `payment_source_id` (wompi-api.md §7): el
    cobro de un periodo. Siempre con `recurrent=True` y la firma de
    integridad; `payment_method.installments=1` solo para tarjeta (la doc pide
    no mandar `payment_method` para otras fuentes). Devuelve la transacción
    normalizada (casi siempre PENDING: la verdad llega por evento o consulta).
    La referencia es única por cuenta en Wompi: un reintento con la misma
    referencia da `ErrorWompi.referencia_usada`, nunca un segundo cobro.
    `acceptance_token` (opcional): el del formulario recién aceptado, en el
    primer cobro (la página de transacciones lo lista como obligatorio y el
    ejemplo de fuentes lo omite: wompi-api.md §13.2); en una renovación ya
    venció (≈1 h) y no se manda."""
    if tipo not in TIPOS_FUENTE:
        raise ErrorWompi(gettext("Medio de pago no soportado"))
    if _entero(fuente_id) is None or fuente_id <= 0:
        raise ErrorWompi(gettext("Fuente de pago inválida"))
    if acceptance_token is not None and (not isinstance(acceptance_token, str) or not acceptance_token.strip()
                                         or len(acceptance_token) > 8000):
        raise ErrorWompi(gettext("Faltan las aceptaciones de Wompi"))
    firma = firma_integridad(referencia, centavos)
    cuerpo = {
        "amount_in_cents": centavos,
        "currency": MONEDA,
        "customer_email": _validar_correo(correo),
        "reference": referencia,
        "payment_source_id": fuente_id,
    }
    if tipo == "CARD":
        cuerpo["payment_method"] = {"installments": 1}
    cuerpo["recurrent"] = True
    cuerpo["signature"] = firma
    if acceptance_token is not None:
        cuerpo["acceptance_token"] = acceptance_token.strip()
    d = _pedir("post", "/transactions", llave=_privada(), cuerpo=cuerpo, tiempo=tiempo, cobro=True)
    tx = _transaccion(d)
    if not tx["id"]:
        raise ErrorWompi(gettext("Wompi no devolvió los datos esperados"), incierto=True)
    return tx


# --------------------------------------------------------------- Nequi ---

def token_nequi(celular, tiempo=TIEMPO):
    """`POST /tokens/nequi` con la llave pública: Wompi le pide a la persona
    que acepte la suscripción en su app. Devuelve el token (PENDING)."""
    numero = re.sub(r"[\s-]", "", str(celular or ""))
    if not _CELULAR.fullmatch(numero):
        raise ErrorWompi(gettext("El celular de Nequi debe tener 10 dígitos y empezar por 3"))
    d = _pedir("post", "/tokens/nequi", llave=_publica(), cuerpo={"phone_number": numero}, tiempo=tiempo)
    token = d.get("id")
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise ErrorWompi(gettext("Wompi no devolvió los datos esperados"))
    return token


def estado_token_nequi(token, tiempo=TIEMPO_INTERACTIVO):
    """`GET /tokens/nequi/<token>` (llave pública, inferido de la doc):
    PENDING, APPROVED o DECLINED."""
    _validar_token(token)
    d = _pedir("get", f"/tokens/nequi/{token}", llave=_publica(), tiempo=tiempo)
    estado = (_texto(d.get("status"), 20) or "").upper()
    if not estado:
        raise ErrorWompi(gettext("Wompi no devolvió los datos esperados"))
    return estado

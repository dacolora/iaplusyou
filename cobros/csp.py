"""Los reportes de la política de scripts de la página de la tarjeta (PND-304 a, 2026-10-15).

`plan_alta.html` (el alta del plan y el cambio de tarjeta, donde el widget de Wompi pide la tarjeta) lleva su propia
política (`cobros.rutas.CSP_TARJETA`), que arrancó en «solo reporte»: el navegador dice en su consola qué habría
bloqueado y no rompe nada. Para pasarla a «bloquear» había que mirar esa consola con el widget de verdad; ahora la
política lleva `report-uri` y el navegador manda cada violación a `POST /pagos/csp/tarjeta`, que la anota aquí (sin
`report-to`: ver `cobros.rutas._con_politica_tarjeta`; igual se lee el formato de la Reporting API). Lo que se ve en /admin/cobros («Política de scripts de la página de la tarjeta») decide el cambio.

Lo que se guarda es lo justo, nunca un dato de tarjeta ni del proyecto: la directiva (de una lista blanca), lo
bloqueado reducido a su origen (`https://host[:puerto]`) o a su palabra (`inline`, `eval`, `data`…), qué página
(`alta` o `tarjeta`), si fue reporte o bloqueo, cuántas veces y la primera y la última. Nada de la URL completa, la
consulta, el `script-sample`, el archivo fuente ni el proyecto de la ruta. La ruta la llama el navegador sin cookie
(y a veces marcada de otro sitio): está exenta de la barrera CSRF y de la sesión por nombre exacto de endpoint
(`dashboard.ENDPOINTS_OTRO_ORIGEN`), y como no se puede firmar, la protegen los topes: 16 KB por envío,
TOPE_IP_HORA por IP y TOPE_HORA entre todos (en memoria y en `kv`), y a lo más MAX_DISTINTAS violaciones distintas
guardadas (las de más de DIAS días sin repetirse se olvidan). Una violación nueva avisa al admin una vez
(`csp_tarjeta`, en «Avisos de plata»).

ÚNICO escritor de `kv` `cobros:csp:<huella>`."""
import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import sqlalchemy as sa
from flask_babel import gettext

import cuentas
import db
from cobros import avisos

log = logging.getLogger(__name__)

MAX_CUERPO = 16384               # un reporte pesa ≈ 1 KB; la Reporting API puede juntar varios
MAX_REPORTES_POR_ENVIO = 10
TOPE_HORA = 60                   # reportes anotados por hora entre todos
TOPE_IP_HORA = 10                # reportes anotados por hora desde una misma IP
MAX_DISTINTAS = 20               # violaciones distintas guardadas a la vez
DIAS = 30                        # una violación que no se repite en estos días se olvida
PREFIJO = "cobros:csp:"
# Las directivas de CSP_TARJETA y las que caen en ellas (los navegadores reportan la «efectiva»).
DIRECTIVAS = frozenset(("script-src", "script-src-elem", "script-src-attr", "worker-src", "frame-src", "child-src",
                        "form-action"))
PALABRAS = frozenset(("inline", "eval", "wasm-eval", "self", "data", "blob", "trusted-types-policy",
                      "trusted-types-sink"))
DISPOSICIONES = frozenset(("report", "enforce", "desconocida"))   # sin `disposition` (un navegador viejo): no se sabe
_PAGINA = re.compile(r"/cliente/[^/?#]{1,120}/plan/(alta|tarjeta)")
_ESQUEMA = re.compile(r"[a-z][a-z0-9+.-]{0,30}")
_HOST = re.compile(r"[a-z0-9.-]{1,253}")
_CUPO = {"desde": None, "n": 0, "ips": {}}
_CANDADO = threading.Lock()


def _en_segundo_plano(fn):
    """El aviso (correo SMTP, hasta 30 s) sale en un hilo aparte: el navegador no espera. Nunca lanza."""
    def correr():
        try:
            fn()
        except Exception:  # noqa: BLE001 — un aviso nunca tumba nada
            log.exception("aviso de la política de la tarjeta no salió")
    try:
        threading.Thread(target=correr, name="aviso-csp", daemon=True).start()
    except RuntimeError:
        correr()


# ------------------------------------------------------------------- leer ---

def _texto(valor, n=300):
    return valor.strip()[:n] if isinstance(valor, str) else ""


def _origen(valor):
    """Lo bloqueado reducido a su palabra (`inline`, `eval`…), a su esquema (`data`, `blob`, `chrome-extension`) o a
    su origen `https://host[:puerto]`: nunca la ruta, la consulta ni un usuario y clave. Lo que no se lee, `otro`."""
    valor = _texto(valor, 2000).lower()
    if valor in PALABRAS:
        return valor
    try:
        partes = urlsplit(valor)
        esquema, host, puerto = partes.scheme, partes.hostname or "", partes.port
    except ValueError:
        return "otro"
    if not _ESQUEMA.fullmatch(esquema or ""):
        return "otro"
    if esquema not in ("http", "https", "ws", "wss"):
        return esquema
    if not _HOST.fullmatch(host):
        return "otro"
    estandar = {"http": 80, "https": 443, "ws": 80, "wss": 443}[esquema]
    return f"{esquema}://{host}" + (f":{puerto}" if puerto and puerto != estandar else "")


def _pagina(documento):
    """`alta` o `tarjeta` si el reporte es de la página de la tarjeta; None si es de otra."""
    try:
        ruta = urlsplit(_texto(documento, 2000)).path
    except ValueError:
        return None
    m = _PAGINA.fullmatch(ruta or "")
    return m.group(1) if m else None


def _crudos(ev):
    """Los reportes de un envío, en los dos formatos: `report-uri` (`{"csp-report": {…}}`, claves con guion) y la
    Reporting API (`[{"type": "csp-violation", "body": {…}}]`, claves en camelCase). (documento, directiva,
    bloqueado, disposición) de cada uno, a lo más MAX_REPORTES_POR_ENVIO."""
    if isinstance(ev, dict) and isinstance(ev.get("csp-report"), dict):
        r = ev["csp-report"]
        directiva = _texto(r.get("effective-directive")) or _texto(r.get("violated-directive")).split(" ")[0]
        return [(r.get("document-uri"), directiva, r.get("blocked-uri"), r.get("disposition") or "desconocida")]
    if not isinstance(ev, list):
        return []
    salida = []
    for item in ev[:MAX_REPORTES_POR_ENVIO]:
        if not isinstance(item, dict) or item.get("type") != "csp-violation" or not isinstance(item.get("body"), dict):
            continue
        b = item["body"]
        salida.append((b.get("documentURL"), b.get("effectiveDirective"), b.get("blockedURL"),
                       b.get("disposition") or "desconocida"))
    return salida


def _limpio(documento, directiva, bloqueado, disposicion):
    """El reporte con solo lo que se guarda, o None si no es de la página de la tarjeta o de una directiva suya."""
    pagina = _pagina(documento)
    directiva = _texto(directiva, 40).lower()
    disposicion = _texto(disposicion, 10).lower()
    if pagina is None or directiva not in DIRECTIVAS or disposicion not in DISPOSICIONES:
        return None
    return {"directiva": directiva, "bloqueado": _origen(bloqueado), "pagina": pagina, "disposicion": disposicion}


# ------------------------------------------------------------------ topes ---

def _cupo(ip):
    """¿Cabe otro reporte? Primero en la memoria del proceso (sin tocar la base: pasado el cupo, ni el candado),
    por IP y entre todos; después el global en kv (`cuentas.limite_ok`), que cuenta todos los procesos."""
    ahora = time.monotonic()
    ip = str(ip or "desconocida")[:64]
    with _CANDADO:
        if _CUPO["desde"] is None or ahora - _CUPO["desde"] >= 3600:
            _CUPO.update(desde=ahora, n=0, ips={})
        if _CUPO["n"] >= TOPE_HORA or _CUPO["ips"].get(ip, 0) >= TOPE_IP_HORA:
            return False
        if len(_CUPO["ips"]) > 5000:
            return False   # demasiadas IP en una hora: algo raro, no se anota más
        _CUPO["n"] += 1
        _CUPO["ips"][ip] = _CUPO["ips"].get(ip, 0) + 1
    try:
        return cuentas.limite_ok("csp_tarjeta", TOPE_HORA, 3600)
    except Exception:  # noqa: BLE001 — sin contador no se anota; la respuesta sigue siendo 204
        log.exception("no se pudo contar un reporte de la política de la tarjeta")
        return False


# ---------------------------------------------------------------- anotar ---

def _huella(rep):
    texto = "|".join((rep["directiva"], rep["bloqueado"], rep["pagina"], rep["disposicion"]))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:24]


def _anotar(rep):
    """Suma una vez a la violación (o la crea si cabe). Toma el candado de escritura ANTES de leer. Devuelve True si
    es una violación nueva (para avisar), False si ya estaba o no cupo."""
    kv = db.kv
    clave, ahora = PREFIJO + _huella(rep), db.ahora()
    viejas = (datetime.now() - timedelta(days=DIAS)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(kv.update().where(kv.c.clave == clave).values(valor=kv.c.valor))   # el candado, antes de leer
        filas = dict(con.execute(sa.select(kv.c.clave, kv.c.valor).where(kv.c.clave.like(PREFIJO + "%"))).all())
        olvidar = [c for c, v in filas.items() if c != clave and str(_leer(v).get("ultima") or "") < viejas]
        if olvidar:
            con.execute(kv.delete().where(kv.c.clave.in_(olvidar)))
        actual = _leer(filas.get(clave)) if clave in filas else None
        if actual is not None and str(actual.get("ultima") or "") >= viejas:
            actual.update(veces=int(actual.get("veces") or 0) + 1, ultima=ahora)
            con.execute(kv.update().where(kv.c.clave == clave).values(valor=json.dumps(actual), actualizado_en=ahora))
            return False
        if len(filas) - len(olvidar) - (1 if clave in filas else 0) >= MAX_DISTINTAS:
            log.warning("la política de la tarjeta ya tiene %s violaciones distintas anotadas: no se anota otra",
                        MAX_DISTINTAS)
            return False
        valor = json.dumps({**rep, "veces": 1, "primera": ahora, "ultima": ahora})
        if clave in filas:
            con.execute(kv.update().where(kv.c.clave == clave).values(valor=valor, actualizado_en=ahora))
        else:
            con.execute(kv.insert().values(clave=clave, valor=valor, actualizado_en=ahora))
    return True


def _leer(valor):
    try:
        dato = json.loads(valor) if valor else {}
    except (TypeError, ValueError):
        return {}
    return dato if isinstance(dato, dict) else {}


def _avisar(rep):
    directiva, bloqueado, pagina = rep["directiva"], rep["bloqueado"], rep["pagina"]
    bloqueo = rep["disposicion"] == "enforce"

    def asunto():
        return gettext("La página de la tarjeta reportó algo que su política bloquea")

    def cuerpo():
        nombre = gettext("Cambio de tarjeta") if pagina == "tarjeta" else gettext("Alta del plan")
        if bloqueo:
            return gettext("En la página de la tarjeta (%(pagina)s) el navegador BLOQUEÓ «%(bloqueado)s» por la "
                           "directiva %(directiva)s. Si es de Creatv o de Wompi, el pago puede estar roto: revísalo "
                           "en /admin/cobros.", pagina=nombre, bloqueado=bloqueado, directiva=directiva)
        return gettext("En la página de la tarjeta (%(pagina)s) el navegador reportó «%(bloqueado)s» por la "
                       "directiva %(directiva)s. La política está en «solo reporte» y no se bloqueó nada; antes de "
                       "pasarla a «bloquear», revísalo en /admin/cobros.", pagina=nombre, bloqueado=bloqueado,
                       directiva=directiva)
    _en_segundo_plano(lambda: avisos.admin("csp_tarjeta", asunto, cuerpo))


def procesar(cuerpo, ip=None):
    """El cuerpo crudo de `POST /pagos/csp/tarjeta` y la IP de quien lo manda. Devuelve el status HTTP: 413 si pasa
    de MAX_CUERPO, 400 si no es JSON, 204 a todo lo demás (también lo que no se anota: un reporte de otra página,
    otra directiva o fuera de cupo; al navegador no le importa la respuesta). Nunca lanza."""
    cuerpo = cuerpo or b""
    if len(cuerpo) > MAX_CUERPO:
        return 413
    try:
        ev = json.loads(cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):   # RecursionError: «[[[[…» anidado sin fin
        return 400
    for crudo in _crudos(ev):
        rep = _limpio(*crudo)
        if rep is None or not _cupo(ip):
            continue
        try:
            nueva = _anotar(rep)
        except Exception:  # noqa: BLE001 — un reporte que no se anota no es un error de quien lo manda
            log.exception("no se pudo anotar un reporte de la política de la tarjeta")
            continue
        if nueva:
            _avisar(rep)
    return 204


# ---------------------------------------------------------------- lectura ---

def resumen():
    """Las violaciones anotadas de los últimos DIAS días, la más reciente primero (para /admin/cobros). Solo lee."""
    viejas = (datetime.now() - timedelta(days=DIAS)).isoformat(timespec="seconds")
    with db.conectar() as con:
        valores = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave.like(PREFIJO + "%"))).scalars().all()
    salida = []
    for v in valores:
        d = _leer(v)
        if not d.get("directiva") or str(d.get("ultima") or "") < viejas:
            continue
        salida.append({"directiva": str(d["directiva"]), "bloqueado": str(d.get("bloqueado") or ""),
                       "pagina": str(d.get("pagina") or ""), "disposicion": str(d.get("disposicion") or ""),
                       "veces": int(d.get("veces") or 0), "primera": str(d.get("primera") or ""),
                       "ultima": str(d.get("ultima") or "")})
    return sorted(salida, key=lambda d: d["ultima"], reverse=True)

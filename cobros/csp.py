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
TOPE_IP_HORA por IP (una IPv6 por su /64) y TOPE_HORA entre todos (en memoria y en `kv`), y a lo más MAX_DISTINTAS
violaciones distintas guardadas (las de más de DIAS días sin repetirse se olvidan; con la lista llena, lo nuestro o de
Wompi desplaza a lo ajeno). Solo cuentan los reportes de un documento de Creatv (`_host_nuestro`). Lo que se descarta
por un tope deja la lista marcada como incompleta (`kv` `cobros:csp_incompleta`, /admin/cobros lo avisa): quien gaste
el cupo con basura no puede dejarla con cara de limpia. Una violación nueva avisa al admin una vez (`csp_tarjeta`, en
«Avisos de plata»), diciendo que los reportes no van firmados (auditoría de seguridad 2026-10-15).

ÚNICO escritor de `kv` `cobros:csp:<huella>` y `cobros:csp_incompleta`."""
import hashlib
import ipaddress
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import sqlalchemy as sa
from flask_babel import gettext

import cuentas
import db
from cobros import _entorno, avisos

log = logging.getLogger(__name__)

MAX_CUERPO = 16384               # un reporte pesa ≈ 1 KB; la Reporting API puede juntar varios
MAX_REPORTES_POR_ENVIO = 10
TOPE_HORA = 60                   # reportes anotados por hora entre todos
TOPE_IP_HORA = 10                # reportes anotados por hora desde una misma IP
MAX_DISTINTAS = 20               # violaciones distintas guardadas a la vez
DIAS = 30                        # una violación que no se repite en estos días se olvida
PREFIJO = "cobros:csp:"
# Cuándo se descartó por última vez un reporte de la página por los topes (auditoría 2026-10-15): sin esto, quien
# gastara el cupo con basura dejaba la lista con cara de limpia. Fuera de PREFIJO a propósito (no es una violación).
CLAVE_INCOMPLETA = "cobros:csp_incompleta"
# Lo que importa para decidir el cambio a «bloquear»: lo nuestro y lo de Wompi. Con la lista llena desplaza a lo ajeno.
PRIORITARIAS = frozenset(("inline", "eval", "wasm-eval", "self", "data", "blob"))
# Las directivas de CSP_TARJETA y las que caen en ellas (los navegadores reportan la «efectiva»).
DIRECTIVAS = frozenset(("script-src", "script-src-elem", "script-src-attr", "worker-src", "frame-src", "child-src",
                        "form-action"))
PALABRAS = frozenset(("inline", "eval", "wasm-eval", "self", "data", "blob", "trusted-types-policy",
                      "trusted-types-sink"))
DISPOSICIONES = frozenset(("report", "enforce", "desconocida"))   # sin `disposition` (un navegador viejo): no se sabe
_PAGINA = re.compile(r"/cliente/[^/?#]{1,120}/plan/(alta|tarjeta)")
_ESQUEMA = re.compile(r"[a-z][a-z0-9+.-]{0,30}")
_HOST = re.compile(r"[a-z0-9.-]{1,253}")
_CUPO = {"desde": None, "n": 0, "ips": {}, "marcada": False}
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
    # Una parte del host con 5 dígitos seguidos o más se tapa: un skimmer podría cargar https://<número>.evil.tld/x.js
    # y el número quedaría en la base y en el correo (auditoría 2026-10-15).
    host = ".".join("*" if re.search(r"\d{5,}", parte) else parte for parte in host.split("."))
    estandar = {"http": 80, "https": 443, "ws": 80, "wss": 443}[esquema]
    return f"{esquema}://{host}" + (f":{puerto}" if puerto and puerto != estandar else "")


def _host_nuestro(host):
    """¿El host del documento es de Creatv? Sin PLATAFORMA_URL (pruebas, local), cualquiera; con ella, el suyo, los
    de PLATAFORMA_HOSTS_EXTRA o uno local (la misma regla que `dashboard._verificar_host`)."""
    fijo = (os.environ.get("PLATAFORMA_URL") or "").strip()
    if not fijo:
        return True
    host = (host or "").lower().rstrip(".")
    extra = {h.strip().lower() for h in (os.environ.get("PLATAFORMA_HOSTS_EXTRA") or "").split(",") if h.strip()}
    return bool(host) and (host == (urlsplit(fijo).hostname or "").lower() or host in extra
                           or _entorno.host_local(f"//{host}"))


def _pagina(documento):
    """`alta` o `tarjeta` si el reporte es de la página de la tarjeta de Creatv; None si es de otra página o de otro
    sitio (auditoría 2026-10-15: un reporte inventado de https://evil.example/cliente/x/plan/alta no cuenta)."""
    try:
        partes = urlsplit(_texto(documento, 2000))
        ruta, host = partes.path, partes.hostname
    except ValueError:
        return None
    m = _PAGINA.fullmatch(ruta or "")
    return m.group(1) if m and _host_nuestro(host) else None


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
    disposicion = _texto(disposicion, 20).lower()
    if pagina is None or directiva not in DIRECTIVAS or disposicion not in DISPOSICIONES:
        return None
    return {"directiva": directiva, "bloqueado": _origen(bloqueado), "pagina": pagina, "disposicion": disposicion}


# ------------------------------------------------------------------ topes ---

def _clave_ip(ip):
    """La IP para el tope por IP: una IPv6 cuenta por su /64 (quien tiene una /64 tiene 2^64 direcciones)."""
    if not ip:
        return "desconocida"
    try:
        dir_ = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return str(ip)[:64]
    if dir_.version == 4:
        return str(dir_)
    if dir_.ipv4_mapped is not None:
        return str(dir_.ipv4_mapped)
    return str(ipaddress.ip_network(f"{dir_}/64", strict=False))


def _cupo(ip):
    """¿Cabe otro reporte? Primero en la memoria del proceso (sin tocar la base: pasado el cupo, ni el candado),
    por IP (una IPv6 por su /64) y entre todos; después el global en kv (`cuentas.limite_ok`), que cuenta todos los
    procesos. Un reporte que no cabe deja la lista marcada como incompleta (`_marcar_incompleta`)."""
    ahora = time.monotonic()
    ip = _clave_ip(ip)
    with _CANDADO:
        if _CUPO["desde"] is None or ahora - _CUPO["desde"] >= 3600:
            _CUPO.update(desde=ahora, n=0, ips={}, marcada=False)
        lleno = (_CUPO["n"] >= TOPE_HORA or _CUPO["ips"].get(ip, 0) >= TOPE_IP_HORA
                 or len(_CUPO["ips"]) > 5000)   # demasiadas IP en una hora: algo raro, no se anota más
        if not lleno:
            _CUPO["n"] += 1
            _CUPO["ips"][ip] = _CUPO["ips"].get(ip, 0) + 1
    if lleno:
        _marcar_incompleta()
        return False
    try:
        if cuentas.limite_ok("csp_tarjeta", TOPE_HORA, 3600):
            return True
    except Exception:  # noqa: BLE001 — sin contador no se anota; la respuesta sigue siendo 204
        log.exception("no se pudo contar un reporte de la política de la tarjeta")
    _marcar_incompleta()
    return False


def _marcar_incompleta():
    """Anota en kv que desde ahora la lista puede estar incompleta: a lo más una escritura por hora y proceso (bajo
    una inundación no compite por el candado con los cobros). Nunca lanza."""
    with _CANDADO:
        if _CUPO.get("marcada"):
            return
        _CUPO["marcada"] = True
    ahora = db.ahora()
    try:
        with db.conectar() as con:
            if not con.execute(db.kv.update().where(db.kv.c.clave == CLAVE_INCOMPLETA)
                               .values(valor=ahora, actualizado_en=ahora)).rowcount:
                con.execute(db.kv.insert().values(clave=CLAVE_INCOMPLETA, valor=ahora, actualizado_en=ahora))
    except Exception:  # noqa: BLE001 — sin la marca, el log dice lo mismo
        log.exception("no se pudo marcar la lista de la política de la tarjeta como incompleta")
    log.warning("reportes de la política de la tarjeta descartados por los topes: la lista puede estar incompleta")


def incompleta():
    """Cuándo se descartó por última vez un reporte por los topes (ISO), si fue en los últimos DIAS días; si no, None.
    Para /admin/cobros: con esto la lista no se puede leer como «limpia». Solo lee."""
    with db.conectar() as con:
        valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE_INCOMPLETA)).scalar()
    viejas = (datetime.now() - timedelta(days=DIAS)).isoformat(timespec="seconds")
    return str(valor) if valor and str(valor) >= viejas else None


# ---------------------------------------------------------------- anotar ---

def _huella(rep):
    texto = "|".join((rep["directiva"], rep["bloqueado"], rep["pagina"], rep["disposicion"]))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:24]


def _prioritaria(rep):
    """¿Es algo nuestro o de Wompi? Lo que decide si se puede pasar a «bloquear»: `inline`, `eval`, `self`, `data`,
    `blob`, el host de la plataforma o uno de `wompi.co`."""
    bloqueado = str(rep.get("bloqueado") or "")
    if bloqueado in PRIORITARIAS:
        return True
    host = (urlsplit(bloqueado).hostname or "") if "://" in bloqueado else ""
    plataforma = (urlsplit((os.environ.get("PLATAFORMA_URL") or "").strip()).hostname or "").lower()
    return bool(host) and (host == "wompi.co" or host.endswith(".wompi.co") or (bool(plataforma) and host == plataforma))


def _anotar(rep):
    """Suma una vez a la violación (o la crea si cabe). Toma el candado de escritura ANTES de leer. Devuelve `nueva`
    (para avisar), `repetida` o `llena` (no cupo: quien llama marca la lista como incompleta, fuera de esta
    transacción)."""
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
            return "repetida"
        vivas = {c: _leer(v) for c, v in filas.items() if c not in olvidar and c != clave}
        if len(vivas) >= MAX_DISTINTAS:
            # Llena. Lo nuestro o de Wompi desplaza a la ajena que lleva más tiempo sin repetirse; si no, se descarta
            # y la lista queda marcada como incompleta (auditoría 2026-10-15).
            ajenas = sorted((str(d.get("ultima") or ""), c) for c, d in vivas.items() if not _prioritaria(d))
            if not _prioritaria(rep) or not ajenas:
                log.warning("la política de la tarjeta ya tiene %s violaciones distintas anotadas: no se anota otra",
                            MAX_DISTINTAS)
                return "llena"
            con.execute(kv.delete().where(kv.c.clave == ajenas[0][1]))
        valor = json.dumps({**rep, "veces": 1, "primera": ahora, "ultima": ahora})
        if clave in filas:
            con.execute(kv.update().where(kv.c.clave == clave).values(valor=valor, actualizado_en=ahora))
        else:
            con.execute(kv.insert().values(clave=clave, valor=valor, actualizado_en=ahora))
    return "nueva"


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
        # Auditoría 2026-10-15: los reportes no van firmados. Un origen parecido al de Wompi
        # (checkout.wompi.co.otro.example) no se permite en la política por un correo: se reproduce antes.
        cuidado = gettext("Estos reportes no van firmados: cualquiera puede mandar uno. Antes de permitir un origen en "
                          "la política, reprodúcelo en la consola de la página real y compáralo letra por letra con "
                          "https://checkout.wompi.co.")
        if bloqueo:
            texto = gettext("En la página de la tarjeta (%(pagina)s) el navegador BLOQUEÓ «%(bloqueado)s» por la "
                            "directiva %(directiva)s. Si es de Creatv o de Wompi, el pago puede estar roto: revísalo "
                            "en /admin/cobros.", pagina=nombre, bloqueado=bloqueado, directiva=directiva)
        else:
            texto = gettext("En la página de la tarjeta (%(pagina)s) el navegador reportó «%(bloqueado)s» por la "
                            "directiva %(directiva)s. La política está en «solo reporte» y no se bloqueó nada; antes "
                            "de pasarla a «bloquear», revísalo en /admin/cobros.", pagina=nombre,
                            bloqueado=bloqueado, directiva=directiva)
        return f"{texto} {cuidado}"
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
            resultado = _anotar(rep)
        except Exception:  # noqa: BLE001 — un reporte que no se anota no es un error de quien lo manda
            log.exception("no se pudo anotar un reporte de la política de la tarjeta")
            continue
        if resultado == "nueva":
            _avisar(rep)
        elif resultado == "llena":
            _marcar_incompleta()
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

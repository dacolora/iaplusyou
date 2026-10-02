"""
Alertas del proyecto: todo lo que necesita la atención de la persona, en un
solo lugar (pestaña Alertas). Spec: docs/superpowers/specs/2026-09-20-alertas-design.md
(§12 «Rescate del 2026-10-02» manda donde difiere de las secciones viejas).

Regla de oro: NADA se almacena salvo los descartes. Cada alerta se calcula al
vuelo desde el estado real (llaves, tablas, archivos del proyecto), así nunca
hay una alerta vieja que ya no corresponda: si algo se resuelve, desaparece
sola. Cada fuente (FUENTES) corre en su propio try/except: si una revienta
sale una alerta `revision:<fuente>` con SOLO el nombre de la clase de la
excepción (nunca el mensaje, que podría arrastrar un token) y el resto se
calcula igual.

Una alerta es un dict (spec §1) con `clave` estable (`<fuente>:<tipo>[:<entidad>]`)
y `huella` (sha256 de la situación): un descarte vive mientras la alerta
exista con esa misma huella; si cambia la situación, vuelve a mostrarse; si
la alerta desaparece, `visibles` poda el descarte. Las que llevan
`solo_admin` (las llaves del .env y el worker son de Creatv) no las ve un
cliente.

Idioma: los títulos y detalles se arman con `gettext` al calcular (así salen
en el idioma de quien mira); los nombres de grupo, nivel y pestaña son
constantes `idiomas.N_` que la plantilla traduce con `|traducir`.

Ningún valor de llave sale de aquí; los textos de error que llegan a una
alerta pasan por `_limpio` (cola.sin_token + cola.recortar). Nada de aquí
gasta, encola, publica ni llama a un proveedor. Sin rutas ni app de Flask
(solo `gettext`, que fuera de una petición devuelve el español): lo importan
dashboard.py y los tests. El ÚNICO escritor de `alerta_descartada` es este
módulo.
"""
import hashlib
from datetime import datetime

import sqlalchemy as sa
from flask_babel import gettext
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import cola
import db
import idiomas

NIVELES = ("bloquea", "atencion", "info")
GRUPOS = ("puesta_a_punto", "faltantes", "decision", "fallos")
NOMBRES_GRUPO = {"puesta_a_punto": idiomas.N_("Puesta a punto pendiente"), "faltantes": idiomas.N_("Faltantes del proyecto"),
                 "decision": idiomas.N_("Esperan tu decisión"), "fallos": idiomas.N_("Fallos y errores")}
NOMBRES_NIVEL = {"bloquea": idiomas.N_("bloquea"), "atencion": idiomas.N_("atención"), "info": idiomas.N_("info")}
NOMBRES_TAB = {"settings": idiomas.N_("Configuración"), "catalogo": idiomas.N_("Catálogo"), "creativeflowplus": idiomas.N_("Crear"),
               "experimentos": idiomas.N_("Experimentos"), "sprints": idiomas.N_("Sprints"), "nicho": idiomas.N_("Nicho")}

# Lo que las rutas aceptan al descartar/restaurar (una clave o huella que no
# calce no se guarda). La clave: `<fuente>:<tipo>[:<entidad>]`; la huella: sha256 hex.
CLAVE_VALIDA = r"^[a-z_]+:[A-Za-z0-9_:.\-]{1,180}$"
HUELLA_VALIDA = r"^[0-9a-f]{64}$"

# (nombre, función(cliente, ahora_iso) -> lista de alertas), en el orden en
# que se muestran dentro de un mismo grupo y nivel. Las fuentes reales se
# registran aquí; los tests lo reemplazan con fuentes falsas.
FUENTES = []


def huella(*partes):
    """sha256 hex de la «situación» de una alerta. Sin partes es la huella
    vacía: una constante para las alertas cuya situación no cambia."""
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()


def _alerta(clave, huella_, nivel, grupo, titulo, detalle, tab, ancla=None, url=None, entidad=None,
            solo_admin=False):
    """El constructor de toda alerta (spec §1). `solo_admin`: la ve solo un
    admin (llaves del .env, worker, fuentes caídas)."""
    if nivel not in NIVELES:
        raise ValueError(f"nivel inválido: {nivel}")
    if grupo not in GRUPOS:
        raise ValueError(f"grupo inválido: {grupo}")
    return {"clave": clave, "huella": huella_, "nivel": nivel, "grupo": grupo, "titulo": titulo,
            "detalle": detalle, "tab": tab, "ancla": ancla, "url": url, "entidad": entidad,
            "solo_admin": bool(solo_admin)}


def _minutos(desde_iso, ahora_iso):
    """Minutos entre dos ISO (None si alguno no se puede leer)."""
    try:
        return (datetime.fromisoformat(str(ahora_iso)[:19]) - datetime.fromisoformat(str(desde_iso)[:19])).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def _limpio(texto, n=200):
    """Texto de error apto para una alerta: sin tokens y recortado."""
    return cola.recortar(cola.sin_token(texto), n)


# ---------- cálculo ----------

def calcular(cliente, ahora_iso=None):
    """Todas las alertas del proyecto, sin mirar descartes ni rol, ordenadas
    por grupo (GRUPOS) y nivel (NIVELES); dentro del mismo nivel, en el orden
    en que las produjo su fuente (sorted es estable)."""
    ahora = ahora_iso or db.ahora()
    out = []
    for nombre, fn in FUENTES:
        try:
            out.extend(fn(cliente, ahora))
        except Exception as e:  # noqa: BLE001 — una fuente rota no tumba las demás ni la página
            clase = type(e).__name__          # solo la clase: el mensaje podría arrastrar un token
            out.append(_alerta(f"revision:{nombre}", huella(clase), "info", "puesta_a_punto",
                               gettext("No se pudo revisar %(fuente)s", fuente=nombre),
                               gettext("Falló el cálculo (%(error)s). El resto de alertas sigue abajo.", error=clase),
                               "settings", solo_admin=True))
    orden_grupo = {g: i for i, g in enumerate(GRUPOS)}
    orden_nivel = {n: i for i, n in enumerate(NIVELES)}
    return sorted(out, key=lambda a: (orden_grupo[a["grupo"]], orden_nivel[a["nivel"]]))


def resumen(lista):
    r = {"n": len(lista), "bloquea": 0, "atencion": 0, "info": 0}
    for a in lista:
        r[a["nivel"]] += 1
    return r


# ---------- descartes ----------

def _descartes(cliente):
    """{clave: (huella, descartada_en)} de los descartes del proyecto."""
    t = db.alerta_descartada
    with db.conectar() as con:
        return {f.clave: (f.huella, f.descartada_en) for f in con.execute(
            sa.select(t.c.clave, t.c.huella, t.c.descartada_en).where(t.c.cliente == cliente))}


def descartar(cliente, clave, huella_):
    """Upsert atómico de (cliente, clave) → huella: un descarte nuevo sobre la
    misma clave reemplaza al anterior."""
    t = db.alerta_descartada
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(insert_sqlite(t).values(cliente=cliente, clave=clave, huella=huella_, descartada_en=ahora)
                    .on_conflict_do_update(index_elements=["cliente", "clave"],
                                           set_={"huella": huella_, "descartada_en": ahora}))


def restaurar(cliente, clave):
    t = db.alerta_descartada
    with db.conectar() as con:
        con.execute(sa.delete(t).where(t.c.cliente == cliente, t.c.clave == clave))


def _borrar_descartes(cliente, huerfanos):
    """Borra los descartes `{clave: huella}` que `visibles` leyó y vio huérfanos.
    Cada borrado exige también la huella que se leyó: si otro proceso reescribió
    ese descarte entre la lectura y este borrado (otra huella), no se lo lleva."""
    t = db.alerta_descartada
    with db.conectar() as con:
        for clave, huella_ in huerfanos.items():
            con.execute(sa.delete(t).where(t.c.cliente == cliente, t.c.clave == clave, t.c.huella == huella_))


def visibles(cliente, ahora_iso=None, rol="cliente", calculadas=None):
    """calcular() menos las alertas descartadas con la MISMA huella, y menos
    las `solo_admin` salvo que `rol == "admin"`. `calculadas` deja al llamador
    pasar un `calcular` ya hecho (la caché de 60 s del context processor); los
    descartes siempre se leen en vivo. Devuelve {"visibles", "descartadas"
    (las actuales que coinciden con un descarte, con `descartada_en`),
    "resumen" (de las visibles)}. De paso poda los descartes cuya clave ya no
    existe (la alerta se resolvió) mirando TODAS las alertas, no solo las que
    ve esta persona, salvo que en esta pasada haya fallado alguna fuente
    (`revision:*`): sus alertas podrían faltar por el fallo y se perderían
    descartes válidos."""
    todas = calculadas if calculadas is not None else calcular(cliente, ahora_iso)
    filas = _descartes(cliente)
    vis, desc = [], []
    for a in todas:
        if a.get("solo_admin") and rol != "admin":
            continue
        d = filas.get(a["clave"])
        if d and d[0] == a["huella"]:
            desc.append({**a, "descartada_en": d[1]})
        else:
            vis.append(a)
    claves = {a["clave"] for a in todas}
    huerfanos = {c: f[0] for c, f in filas.items() if c not in claves}
    if huerfanos and not any(a["clave"].startswith("revision:") for a in todas):
        _borrar_descartes(cliente, huerfanos)
    return {"visibles": vis, "descartadas": desc, "resumen": resumen(vis)}

"""Reglas de diagnóstico de la pestaña «Meta» (spec E2 §6): PURAS y gratis. Reciben lo que el panel ya leyó de la
copia y devuelven recomendaciones; no tocan la base, ni Flask, ni la red, ni a Claude. Se ven siempre y sin pagar; la
evaluación con IA las explica y las prioriza, nunca las reemplaza (spec E2 §2.1).

Entrada (`calcular(entrada)`), un dict que arma `panel` (Task 4) sin una consulta por fila:

    {
      "cuentas": [{"ad_account_id": "act_…", "nombre", "moneda",
                   "extra": {"cuenta": {"account_status", "disable_reason", "amount_spent", "spend_cap"}}}],
                       # las cuentas del alcance (`cuentas.listar`); `amount_spent`/`spend_cap` tal cual los manda
                       # Meta: texto en la unidad menor de la moneda (centavos), «0» = sin tope
      "totales_7":  {act: {"gasto", "valor", "compras", …}},   # `datos.totales_por_cuenta`, últimos 7 días
      "totales_30": {act: {"gasto", "valor", "compras", …}},   # ídem, últimos 30 días
      "objetos": [{"objeto_id", "ad_account_id", "nivel": "campana"|"conjunto", "nombre", "estado",
                   "presupuesto_diario", "aprendizaje", "campaign_id", "padre_id"}],
                       # filas de `meta_objeto` (campañas y conjuntos); solo cuentan las de estado ACTIVE;
                       # `presupuesto_diario` ya en unidades (None = sin presupuesto en ese nivel)
      "conjuntos_7": {adset_id: {"gasto", "compras", "valor"}},  # `datos.gasto_por_conjunto`, últimos 7 días
      "anuncios": [{"ad_id", "ad_account_id", "adset_id", "campaign_id", "nombre", "conjunto", "estado",
                    "veredicto", "problemas", "m", "gasto_7", "gasto_30"}],
                       # los evaluados por `panel.evaluar_anuncios` más `gasto_7` (su gasto de los últimos 7 días,
                       # de la lectura `recientes` que esa función ya hace) y `gasto_30` (si falta, `m["gasto"]`:
                       # el panel evalúa 30 días por defecto)
      "frecuencia_7": {campaign_id: {"alcance", "frecuencia"}},  # `datos.alcance(…, 7, "campana")`
      "desgloses_30": [{"ad_account_id", "dimension", "clave", "gasto", "compras", "valor", …}],
                       # `datos.desgloses(…, 30)`
    }

Una clave que falta vale vacío. Una cuenta sin gasto en 30 días no genera ninguna regla (spec §6).

Salida: [{"id", "nivel": alta|media|baja, "tipo", "cuenta" (act_…), "cuenta_nombre", "titulo", "que_hacer",
"por_que", "impacto": {"monto", "moneda", "texto"}|None, "objetos": [{"nivel", "id", "nombre"}], "enlace"}],
ordenadas por nivel y luego por impacto (los que no tienen van después en su nivel). Los montos van en la moneda de
la cuenta: en «Todas» el orden por impacto es nominal entre monedas (como PND-196). `impacto.monto` es siempre «por
día» (lo que está en juego cada día), para que se puedan comparar. `objetos` trae como mucho `MAX_OBJETOS` (los de
más gasto) y `enlace` es el Administrador de anuncios con ellos seleccionados (`administrador.enlace`) o, para lo que
es de toda la cuenta, sus campañas. `id` es la huella (`huella`): tipo + cuenta + TODOS los ids de los objetos,
ordenados; las de toda la cuenta (ROAS bajo, estado) solo tipo + cuenta, y un segmento su dimensión y clave.

Textos con gettext/ngettext (en el idioma de quien mira, o el del proyecto si se arman dentro de `idiomas.en_idioma`)
y cifras con `idiomas.numero`."""
import hashlib
from collections import Counter

from flask_babel import gettext, ngettext

import idiomas
from idiomas import N_
from meta_rendimiento import administrador

# ---------------------------------------------------------------- umbrales (spec E2 §6) ---
# aprendizaje_limitado: alta si los conjuntos FAIL llevan ≥ 30 % del gasto de 7 días o son ≥ 50 % de los activos;
# media si llevan del 15 al 30 % del gasto. Meta pide unas 50 compras por semana por conjunto para salir.
APRENDIZAJE_GASTO_ALTA = 0.30
APRENDIZAJE_CONJUNTOS_ALTA = 0.50
APRENDIZAJE_GASTO_MEDIA = 0.15
COMPRAS_SEMANA_POR_CONJUNTO = 50
APRENDIZAJE_CAMPANAS = 3          # campañas con más conjuntos FAIL que se listan
# perdedores_gastando: alta si los perdedores activos llevan ≥ 20 % del gasto de 7 días de la cuenta.
PERDEDORES_GASTO_ALTA = 0.20
# escalar: ≥ 10 compras en 7 días, ROAS ≥ 1,3 × el de la cuenta, subir 20 % (más reinicia el aprendizaje).
ESCALAR_COMPRAS_MIN = 10
ESCALAR_FACTOR_ROAS = 1.3
ESCALAR_SUBIDA = 0.20
# Una campaña CBO está «fuera de aprendizaje limitado» si menos de la mitad de su gasto de 7 días va en conjuntos
# FAIL (decisión de la Task 3 de E2: el aprendizaje es de cada conjunto, no de la campaña; exigir CERO conjuntos
# FAIL dejaba sin escalar a casi toda campaña de HappyFlops, con el 70 % de sus conjuntos en FAIL).
ESCALAR_FAIL_MAX_CBO = 0.5
# fatiga: anuncio ganador o prometedor con el problema «fatiga» y frecuencia de 7 días de su campaña ≥ 3.
FATIGA_FRECUENCIA_MIN = 3
FATIGA_VEREDICTOS = ("ganador", "prometedor")
# cuenta_roas_bajo: ROAS de 30 días < 0,5 con gasto de 30 días ≥ 1 000 en su moneda.
CUENTA_ROAS_MIN = 0.5
CUENTA_GASTO_MIN = 1000
# cuenta_estado: account_status distinto de 1 (activa), o gastado ≥ 90 % del tope de gasto.
CUENTA_ACTIVA = 1
TOPE_FRACCION = 0.90
# segmento_caro: segmento de 30 días con ≥ 10 % del gasto y ROAS < 0,5 × el de la cuenta (en esa dimensión).
SEGMENTO_GASTO_MIN = 0.10
SEGMENTO_FACTOR_ROAS = 0.5
SIN_VALOR = "unknown"             # = desgloses.SIN_VALOR: lo que Meta no sabe clasificar no se excluye
# concentracion: un anuncio con ≥ 60 % del gasto de 7 días de su conjunto, y el conjunto con ≥ 5 % del de la cuenta.
CONCENTRACION_ANUNCIO_MIN = 0.60
CONCENTRACION_CONJUNTO_MIN = 0.05

DIAS_SEMANA = 7
DIAS_MES = 30
MAX_OBJETOS = administrador.MAX_IDS
NIVELES = ("alta", "media", "baja")
TIPOS = ("cuenta_estado", "cuenta_roas_bajo", "aprendizaje_limitado", "perdedores_gastando", "anuncios_con_problemas",
         "escalar", "fatiga", "segmento_caro", "concentracion")
# effective_status de un anuncio que entrega (o puede entregar): WITH_ISSUES sigue gastando en muchos casos.
ESTADOS_ENTREGA = ("ACTIVE", "WITH_ISSUES")
ESTADOS_PROBLEMA = ("WITH_ISSUES", "DISAPPROVED")

# account_status de Meta -> (el motivo, qué hacer). Otro código: OTRO_ESTADO.
ESTADOS_CUENTA = {
    2: (N_("Meta desactivó la cuenta: no entrega anuncios."),
        N_("Revisa en Meta por qué la desactivó y pide una revisión si no corresponde.")),
    3: (N_("La cuenta tiene un saldo sin pagar: Meta no entrega anuncios hasta que se pague."),
        N_("Paga el saldo pendiente en la facturación de la cuenta.")),
    7: (N_("Meta está revisando la cuenta por riesgo y puede frenar la entrega."),
        N_("Completa lo que Meta pida en la cuenta y espera su revisión.")),
    8: (N_("La cuenta tiene un pago pendiente de liquidar."),
        N_("Revisa la facturación de la cuenta y salda el pago pendiente.")),
    9: (N_("La cuenta está en período de gracia por un pago: si no se paga, Meta la desactiva."),
        N_("Paga el saldo pendiente antes de que termine el período de gracia.")),
    100: (N_("La cuenta se está cerrando."),
          N_("Si no quieres cerrarla, revísala en Meta; si sí, quítala de las cuentas del proyecto.")),
    101: (N_("La cuenta está cerrada."), N_("Quítala de las cuentas del proyecto o usa otra.")),
}
OTRO_ESTADO = (N_("Meta marca la cuenta con el estado %(codigo)s: no está activa."),
               N_("Revisa el estado de la cuenta en Meta."))

# Dimensiones de los desgloses en palabras (las usa también la sección «Segmentos» del panel).
DIMENSIONES = {"edad_genero": N_("Edad y género"), "ubicacion": N_("Ubicación"), "pais": N_("País"),
               "dispositivo": N_("Dispositivo")}
GENEROS = {"female": N_("mujeres"), "male": N_("hombres"), SIN_VALOR: N_("sin dato")}


# ---------------------------------------------------------------- utilidades ---

def _f(valor):
    """Un número seguro: None, texto ilegible, NaN o un booleano valen 0."""
    if isinstance(valor, bool):
        return 0.0
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v else 0.0


def _div(a, b):
    return a / b if b else None


def _entero(valor):
    if isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _una_linea(texto):
    t = " ".join(str(texto).split()) if texto is not None else ""
    return t or None


def _num(valor, decimales=0):
    return idiomas.numero(_f(valor), decimales)


def _pct(fraccion):
    return idiomas.numero(_f(fraccion) * 100, 0)


def _roas(valor):
    return idiomas.numero(_f(valor), 2)


def _dinero(valor, moneda):
    """«1.250 SEK» / «12,50 SEK»: sin decimales desde 100 (los montos de una cuenta son grandes)."""
    v = _f(valor)
    texto = idiomas.numero(v, 0 if abs(v) >= 100 or v == int(v) else 2)
    return f"{texto} {moneda}" if moneda else texto


def _monto_menor(valor, moneda):
    """Un monto de Meta en la unidad menor de la moneda (texto: «123400») -> unidades (1 234,00). Las monedas sin
    decimales vienen enteras."""
    from tareas.meta import MONEDAS_SIN_DECIMALES   # tardío: ese módulo arrastra el SDK de Meta
    v = _f(valor)
    return v if (moneda or "").upper() in MONEDAS_SIN_DECIMALES else v / 100


def huella(tipo, act, claves):
    """El id estable de una recomendación: tipo + cuenta + las claves (ids de objetos) ordenadas y sin repetir."""
    texto = "|".join((str(tipo), str(act), ",".join(sorted({str(c) for c in claves or ()}))))
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


def _impacto(monto_dia, moneda):
    if not monto_dia or monto_dia <= 0:
        return None
    return {"monto": monto_dia, "moneda": moneda,
            "texto": gettext("%(monto)s por día en juego", monto=_dinero(monto_dia, moneda))}


def _objeto(nivel, objeto_id, nombre):
    return {"nivel": nivel, "id": str(objeto_id), "nombre": _una_linea(nombre) or str(objeto_id)}


# ---------------------------------------------------------------- la cuenta ---

class _Cuenta:
    """Lo de UNA cuenta que miran las reglas, ya filtrado y sumado."""

    def __init__(self, c, t7, t30, objetos, conj7, anuncios, frecuencia, desgloses):
        self.act = c["ad_account_id"]
        self.nombre = _una_linea(c.get("nombre")) or self.act
        self.moneda = (c.get("moneda") or "").upper() or None
        self.info = ((c.get("extra") or {}).get("cuenta") or {})
        self.gasto_7, self.valor_7, self.compras_7 = (_f(t7.get(k)) for k in ("gasto", "valor", "compras"))
        self.gasto_30, self.valor_30 = _f(t30.get("gasto")), _f(t30.get("valor"))
        self.campanas = {str(o["objeto_id"]): o for o in objetos if o.get("nivel") == "campana"}
        self.conjuntos = {str(o["objeto_id"]): o for o in objetos if o.get("nivel") == "conjunto"}
        self.conj7 = conj7
        self.anuncios = anuncios
        self.frecuencia = frecuencia
        self.desgloses = desgloses
        # conjunto -> campaña: de los conjuntos activos y, para los que no lo están, de sus anuncios.
        self.campana_de = {}
        for a in anuncios:
            if a.get("adset_id") and a.get("campaign_id"):
                self.campana_de[str(a["adset_id"])] = str(a["campaign_id"])
        for sid, s in self.conjuntos.items():
            cid = s.get("campaign_id") or s.get("padre_id")
            if cid:
                self.campana_de[sid] = str(cid)

    def g7(self, adset_id):
        return self.conj7.get(str(adset_id)) or self.conj7.get(adset_id) or {}

    def rec(self, tipo, nivel, titulo, que_hacer, por_que, objetos=(), impacto=None, claves=None, enlace=None):
        """Una recomendación. `objetos` ya ordenados (los de más peso primero): se guardan los primeros
        MAX_OBJETOS, pero la huella usa TODOS (o `claves`, si se dan)."""
        objetos = list(objetos)
        ids = [o["id"] for o in objetos] if claves is None else claves
        visibles = objetos[:MAX_OBJETOS]
        if enlace is None:
            enlace = (administrador.enlace(self.act, visibles[0]["nivel"], [o["id"] for o in visibles])
                      if visibles else None) or administrador.enlace_cuenta(self.act)
        return {"id": huella(tipo, self.act, ids), "nivel": nivel, "tipo": tipo, "cuenta": self.act,
                "cuenta_nombre": self.nombre, "titulo": titulo, "que_hacer": que_hacer, "por_que": por_que,
                "impacto": impacto, "objetos": visibles, "enlace": enlace}

    def dinero(self, valor):
        return _dinero(valor, self.moneda)

    def impacto(self, monto_dia):
        return _impacto(monto_dia, self.moneda)


# ---------------------------------------------------------------- reglas ---

def _aprendizaje_limitado(cx):
    activos = list(cx.conjuntos.values())
    fail = [sid for sid, s in cx.conjuntos.items() if s.get("aprendizaje") == "FAIL"]
    if not activos or not fail:
        return []
    gasto_fail = sum(_f(cx.g7(sid).get("gasto")) for sid in fail)
    frac_gasto = _div(gasto_fail, cx.gasto_7) or 0.0
    frac_conjuntos = len(fail) / len(activos)
    if frac_gasto >= APRENDIZAJE_GASTO_ALTA or frac_conjuntos >= APRENDIZAJE_CONJUNTOS_ALTA:
        nivel = "alta"
    elif frac_gasto >= APRENDIZAJE_GASTO_MEDIA:
        nivel = "media"
    else:
        return []

    por_campana = Counter(cx.campana_de[sid] for sid in fail if sid in cx.campana_de)

    def nombre(cid):
        return _una_linea((cx.campanas.get(cid) or {}).get("nombre")) or cid

    top = sorted(por_campana.items(), key=lambda kv: (-kv[1], nombre(kv[0]), kv[0]))[:APRENDIZAJE_CAMPANAS]
    cabe = max(1, int(cx.compras_7 // COMPRAS_SEMANA_POR_CONJUNTO))
    total = len(activos)
    titulo = ngettext("%(n)s de %(total)s conjunto activo en aprendizaje limitado",
                      "%(n)s de %(total)s conjuntos activos en aprendizaje limitado", total,
                      n=_num(len(fail)), total=_num(total))
    que_hacer = ngettext(
        "Consolida conjuntos parecidos dentro de la misma campaña: con %(compras)s compras por semana, esta cuenta da "
        "para ~%(cabe)s conjunto que salga del aprendizaje (Meta pide unas %(meta)s por conjunto).",
        "Consolida conjuntos parecidos dentro de la misma campaña: con %(compras)s compras por semana, esta cuenta da "
        "para ~%(cabe)s conjuntos que salgan del aprendizaje (Meta pide unas %(meta)s por conjunto).",
        cabe, compras=_num(cx.compras_7), cabe=_num(cabe), meta=_num(COMPRAS_SEMANA_POR_CONJUNTO))
    if top:
        lista = ", ".join(f"{nombre(cid)} ({_num(n)})" for cid, n in top)
        que_hacer += " " + gettext("Empieza por las campañas con más conjuntos limitados: %(campanas)s.",
                                   campanas=lista)
    por_que = gettext(
        "%(n)s de %(total)s conjuntos activos (%(pct_conjuntos)s %%) están en aprendizaje limitado y se llevaron "
        "%(gasto)s de los %(gasto_cuenta)s de los últimos 7 días (%(pct_gasto)s %%): sin salir del aprendizaje, Meta "
        "no estabiliza su entrega.",
        n=_num(len(fail)), total=_num(total), pct_conjuntos=_pct(frac_conjuntos), gasto=cx.dinero(gasto_fail),
        gasto_cuenta=cx.dinero(cx.gasto_7), pct_gasto=_pct(frac_gasto))
    objetos = [_objeto("campana", cid, nombre(cid)) for cid, _ in top]
    return [cx.rec("aprendizaje_limitado", nivel, titulo, que_hacer, por_que, objetos,
                   cx.impacto(gasto_fail / DIAS_SEMANA))]


def _perdedores_gastando(cx):
    perdedores = [a for a in cx.anuncios if a.get("veredicto") == "perdedor"
                  and a.get("estado") in ESTADOS_ENTREGA and _f(a.get("gasto_7")) > 0]
    if not perdedores:
        return []
    perdedores.sort(key=lambda a: (-_f(a.get("gasto_7")), str(a.get("ad_id"))))
    n = len(perdedores)
    gasto = sum(_f(a.get("gasto_7")) for a in perdedores)
    fraccion = _div(gasto, cx.gasto_7)
    nivel = "alta" if fraccion is not None and fraccion >= PERDEDORES_GASTO_ALTA else "media"
    titulo = ngettext("%(n)s anuncio perdedor sigue gastando", "%(n)s anuncios perdedores siguen gastando", n,
                      n=_num(n))
    que_hacer = ngettext("Pausa este anuncio: libera su presupuesto para los que venden.",
                         "Pausa estos %(n)s anuncios: libera su presupuesto para los que venden.", n, n=_num(n))
    por_que = ngettext(
        "Gastó %(gasto)s en los últimos 7 días (%(pct)s %% del gasto de la cuenta) y es perdedor: gastó lo de dos "
        "ventas o más con un ROAS de menos de la mitad de la meta.",
        "Gastaron %(gasto)s en los últimos 7 días (%(pct)s %% del gasto de la cuenta) y son perdedores: cada uno "
        "gastó lo de dos ventas o más con un ROAS de menos de la mitad de la meta.",
        n, gasto=cx.dinero(gasto), pct=_pct(fraccion or 0))
    objetos = [_objeto("anuncio", a["ad_id"], a.get("nombre")) for a in perdedores]
    return [cx.rec("perdedores_gastando", nivel, titulo, que_hacer, por_que, objetos,
                   cx.impacto(gasto / DIAS_SEMANA))]


def _escalar(cx):
    roas_cuenta = _div(cx.valor_7, cx.gasto_7)
    if not roas_cuenta:
        return []
    # Las sumas de 7 días de cada campaña, y cuánto de su gasto va en conjuntos FAIL activos.
    por_campana = {}
    for sid, cid in cx.campana_de.items():
        t = por_campana.setdefault(cid, {"gasto": 0.0, "compras": 0.0, "valor": 0.0, "gasto_fail": 0.0})
        g = cx.g7(sid)
        for k in ("gasto", "compras", "valor"):
            t[k] += _f(g.get(k))
        if (cx.conjuntos.get(sid) or {}).get("aprendizaje") == "FAIL":
            t["gasto_fail"] += _f(g.get("gasto"))

    candidatos = []
    for cid, c in cx.campanas.items():
        t = por_campana.get(cid)
        if _f(c.get("presupuesto_diario")) > 0 and t and t["gasto"] > 0 \
                and t["gasto_fail"] / t["gasto"] < ESCALAR_FAIL_MAX_CBO:
            candidatos.append(("campana", cid, c, t))
    for sid, s in cx.conjuntos.items():
        if _f(s.get("presupuesto_diario")) > 0 and s.get("aprendizaje") != "FAIL":
            candidatos.append(("conjunto", sid, s, cx.g7(sid)))

    salida = []
    for nivel_obj, oid, obj, t in candidatos:
        gasto, compras, valor = _f(t.get("gasto")), _f(t.get("compras")), _f(t.get("valor"))
        roas = _div(valor, gasto)
        if compras < ESCALAR_COMPRAS_MIN or not roas or roas < ESCALAR_FACTOR_ROAS * roas_cuenta:
            continue
        antes = _f(obj.get("presupuesto_diario"))
        despues = antes * (1 + ESCALAR_SUBIDA)
        nombre = _una_linea(obj.get("nombre")) or oid
        titulo = gettext("Sube el presupuesto de «%(nombre)s»", nombre=nombre)
        if nivel_obj == "campana":
            que_hacer = gettext("Sube %(pct)s %% el presupuesto de la campaña (de %(antes)s a %(despues)s por día); "
                                "más de %(pct)s %% reinicia el aprendizaje.", pct=_pct(ESCALAR_SUBIDA),
                                antes=cx.dinero(antes), despues=cx.dinero(despues))
        else:
            que_hacer = gettext("Sube %(pct)s %% el presupuesto del conjunto (de %(antes)s a %(despues)s por día); "
                                "más de %(pct)s %% reinicia el aprendizaje.", pct=_pct(ESCALAR_SUBIDA),
                                antes=cx.dinero(antes), despues=cx.dinero(despues))
        por_que = gettext(
            "%(compras)s compras en los últimos 7 días con ROAS %(roas)s×, %(veces)s veces el de la cuenta "
            "(%(roas_cuenta)s×), y fuera del aprendizaje limitado.",
            compras=_num(compras), roas=_roas(roas), veces=_roas(roas / roas_cuenta), roas_cuenta=_roas(roas_cuenta))
        salida.append(cx.rec("escalar", "media", titulo, que_hacer, por_que, [_objeto(nivel_obj, oid, nombre)]))
    return salida


def _frecuencia(valor):
    if isinstance(valor, dict):
        valor = valor.get("frecuencia")
    return _f(valor)


def _fatiga(cx):
    cansados = [a for a in cx.anuncios if a.get("veredicto") in FATIGA_VEREDICTOS
                and "fatiga" in (a.get("problemas") or ()) and a.get("estado") in ESTADOS_ENTREGA
                and _frecuencia(cx.frecuencia.get(str(a.get("campaign_id")))) >= FATIGA_FRECUENCIA_MIN]
    if not cansados:
        return []
    cansados.sort(key=lambda a: (-_f(a.get("gasto_7")), str(a.get("ad_id"))))
    n = len(cansados)
    frecuencia = max(_frecuencia(cx.frecuencia.get(str(a.get("campaign_id")))) for a in cansados)
    titulo = ngettext("%(n)s anuncio que funciona se está cansando", "%(n)s anuncios que funcionan se están cansando",
                      n, n=_num(n))
    que_hacer = ngettext("Prepara variantes antes de que se apague: «Evaluar con IA» propone ideas a partir de lo que "
                         "ya funciona.",
                         "Prepara variantes antes de que se apaguen: «Evaluar con IA» propone ideas a partir de lo que "
                         "ya funciona.", n)
    por_que = ngettext(
        "Su ROAS o su CTR cayó frente a la semana anterior y su campaña ya muestra cada anuncio %(frecuencia)s veces "
        "por persona en 7 días (desde %(minimo)s se nota el cansancio).",
        "Su ROAS o su CTR cayó frente a la semana anterior y sus campañas ya muestran cada anuncio hasta "
        "%(frecuencia)s veces por persona en 7 días (desde %(minimo)s se nota el cansancio).",
        n, frecuencia=_num(frecuencia, 1), minimo=_num(FATIGA_FRECUENCIA_MIN))
    objetos = [_objeto("anuncio", a["ad_id"], a.get("nombre")) for a in cansados]
    return [cx.rec("fatiga", "media", titulo, que_hacer, por_que, objetos)]


def _gasto_30(a):
    return _f(a["gasto_30"]) if a.get("gasto_30") is not None else _f((a.get("m") or {}).get("gasto"))


def _anuncios_con_problemas(cx):
    malos = [a for a in cx.anuncios if a.get("estado") in ESTADOS_PROBLEMA and _gasto_30(a) > 0]
    if not malos:
        return []
    malos.sort(key=lambda a: (-_gasto_30(a), str(a.get("ad_id"))))
    rechazados_7 = [a for a in malos if a.get("estado") == "DISAPPROVED" and _f(a.get("gasto_7")) > 0]
    n = len(malos)
    gasto = sum(_gasto_30(a) for a in malos)
    titulo = ngettext("%(n)s anuncio con problemas en Meta", "%(n)s anuncios con problemas en Meta", n, n=_num(n))
    que_hacer = ngettext(
        "Revísalo en el Administrador de anuncios: Meta le marca un problema que frena o detiene su entrega.",
        "Revísalos en el Administrador de anuncios: Meta les marca un problema que frena o detiene su entrega.", n)
    por_que = ngettext("%(n)s anuncio con problemas o rechazado gastó %(gasto)s en los últimos 30 días.",
                       "%(n)s anuncios con problemas o rechazados gastaron %(gasto)s en los últimos 30 días.", n,
                       n=_num(n), gasto=cx.dinero(gasto))
    if rechazados_7:
        k = len(rechazados_7)
        por_que += " " + ngettext(
            "%(n)s está rechazado y gastó %(gasto)s en los últimos 7 días.",
            "%(n)s están rechazados y gastaron %(gasto)s en los últimos 7 días.", k,
            n=_num(k), gasto=cx.dinero(sum(_f(a.get("gasto_7")) for a in rechazados_7)))
    objetos = [_objeto("anuncio", a["ad_id"], a.get("nombre")) for a in malos]
    return [cx.rec("anuncios_con_problemas", "alta" if rechazados_7 else "media", titulo, que_hacer, por_que,
                   objetos, cx.impacto(gasto / DIAS_MES))]


def _cuenta_roas_bajo(cx):
    roas = _div(cx.valor_30, cx.gasto_30)
    if cx.gasto_30 < CUENTA_GASTO_MIN or roas is None or roas >= CUENTA_ROAS_MIN:
        return []
    titulo = gettext("La cuenta vende menos de lo que gasta: ROAS %(roas)s× en 30 días", roas=_roas(roas))
    que_hacer = gettext("Pausa o rehace esta cuenta: gastó %(gasto)s con ROAS %(roas)s× en los últimos 30 días.",
                        gasto=cx.dinero(cx.gasto_30), roas=_roas(roas))
    por_que = gettext("Meta le atribuye %(valor)s en ventas por %(gasto)s de gasto: por debajo de %(minimo)s× se "
                      "pierde dinero casi seguro.", valor=cx.dinero(cx.valor_30), gasto=cx.dinero(cx.gasto_30),
                      minimo=_roas(CUENTA_ROAS_MIN))
    # Sus campañas activas, las de más gasto de 7 días primero (para pausarlas allá de una vez).
    gasto_campana = Counter()
    for sid, cid in cx.campana_de.items():
        gasto_campana[cid] += _f(cx.g7(sid).get("gasto"))
    campanas = sorted(cx.campanas.items(), key=lambda kv: (-gasto_campana[kv[0]], kv[0]))
    objetos = [_objeto("campana", cid, c.get("nombre")) for cid, c in campanas]
    return [cx.rec("cuenta_roas_bajo", "alta", titulo, que_hacer, por_que, objetos,
                   cx.impacto(cx.gasto_30 / DIAS_MES), claves=[])]


def _cuenta_estado(cx):
    estado = _entero(cx.info.get("account_status"))
    motivos, acciones = [], []
    titulo = None
    if estado is not None and estado != CUENTA_ACTIVA:
        motivo, accion = ESTADOS_CUENTA.get(estado, OTRO_ESTADO)
        motivos.append(gettext(motivo, codigo=estado))
        acciones.append(gettext(accion))
        titulo = gettext("La cuenta no está activa en Meta")
    tope = _monto_menor(cx.info.get("spend_cap"), cx.moneda)
    gastado = _monto_menor(cx.info.get("amount_spent"), cx.moneda)
    if tope > 0 and gastado >= TOPE_FRACCION * tope:
        motivos.append(gettext("Gastó %(gastado)s de su tope de %(tope)s (%(pct)s %%): al llegar al tope, Meta deja de "
                               "entregar sus anuncios.", gastado=cx.dinero(gastado), tope=cx.dinero(tope),
                               pct=_pct(gastado / tope)))
        acciones.append(gettext("Sube o quita el tope de gasto en la configuración de pagos de la cuenta."))
        titulo = titulo or gettext("La cuenta está por llegar a su tope de gasto")
    if not motivos:
        return []
    return [cx.rec("cuenta_estado", "alta", titulo, " ".join(acciones), " ".join(motivos), claves=[])]


def nombre_segmento(dimension, clave):
    """«55-64 · mujeres», «facebook · feed», «NO»: la clave de un desglose en palabras (las partes unidas con «·»;
    el género traducido)."""
    partes = str(clave or "").split("|")
    if dimension == "edad_genero" and len(partes) == 2:
        partes[1] = gettext(GENEROS[partes[1]]) if partes[1] in GENEROS else partes[1]
    return " · ".join(p if p != SIN_VALOR else gettext(GENEROS[SIN_VALOR]) for p in partes)


def _segmento_caro(cx):
    por_dimension = {}
    for f in cx.desgloses:
        por_dimension.setdefault(f.get("dimension"), []).append(f)
    salida = []
    for dimension, filas in por_dimension.items():
        gasto_total = sum(_f(f.get("gasto")) for f in filas)
        roas_cuenta = _div(sum(_f(f.get("valor")) for f in filas), gasto_total)
        if not roas_cuenta:
            continue
        for f in sorted(filas, key=lambda f: (-_f(f.get("gasto")), str(f.get("clave")))):
            clave = str(f.get("clave") or "")
            if not clave or all(p == SIN_VALOR for p in clave.split("|")):
                continue
            gasto = _f(f.get("gasto"))
            roas = _div(_f(f.get("valor")), gasto) or 0.0
            if gasto / gasto_total < SEGMENTO_GASTO_MIN or roas >= SEGMENTO_FACTOR_ROAS * roas_cuenta:
                continue
            nombre_dim = gettext(DIMENSIONES[dimension]) if dimension in DIMENSIONES else str(dimension)
            segmento = nombre_segmento(dimension, clave)
            titulo = gettext("Segmento caro: %(segmento)s (%(dimension)s)", segmento=segmento, dimension=nombre_dim)
            que_hacer = gettext("Excluye o baja el peso de %(segmento)s (%(dimension)s) en los conjuntos de esta "
                                "cuenta.", segmento=segmento, dimension=nombre_dim)
            por_que = gettext(
                "Se llevó el %(pct)s %% del gasto de los últimos 30 días (%(gasto)s) con ROAS %(roas)s×, menos de la "
                "mitad del de la cuenta (%(roas_cuenta)s×).",
                pct=_pct(gasto / gasto_total), gasto=cx.dinero(gasto), roas=_roas(roas),
                roas_cuenta=_roas(roas_cuenta))
            salida.append(cx.rec("segmento_caro", "media", titulo, que_hacer, por_que,
                                 impacto=cx.impacto(gasto / DIAS_MES), claves=[f"{dimension}:{clave}"],
                                 enlace=administrador.enlace_cuenta(cx.act)))
    return salida


def _concentracion(cx):
    if cx.gasto_7 <= 0:
        return []
    por_conjunto = {}
    for a in cx.anuncios:
        if a.get("adset_id") and a.get("estado") in ESTADOS_ENTREGA and _f(a.get("gasto_7")) > 0:
            por_conjunto.setdefault(str(a["adset_id"]), []).append(a)
    dependientes = []
    for sid, anuncios in por_conjunto.items():
        gasto_conjunto = _f(cx.g7(sid).get("gasto"))
        if gasto_conjunto <= 0 or gasto_conjunto / cx.gasto_7 < CONCENTRACION_CONJUNTO_MIN:
            continue
        top = max(anuncios, key=lambda a: (_f(a.get("gasto_7")), str(a.get("ad_id"))))
        fraccion = _f(top.get("gasto_7")) / gasto_conjunto
        if fraccion >= CONCENTRACION_ANUNCIO_MIN:
            dependientes.append((top, fraccion, gasto_conjunto))
    if not dependientes:
        return []
    dependientes.sort(key=lambda d: (-d[2], str(d[0].get("ad_id"))))
    n = len(dependientes)
    titulo = ngettext("%(n)s conjunto depende de un solo anuncio", "%(n)s conjuntos dependen de un solo anuncio", n,
                      n=_num(n))
    que_hacer = ngettext("Depende de un solo creativo: prepara variantes de este anuncio antes de que se canse.",
                         "Dependen de un solo creativo: prepara variantes de estos %(n)s anuncios antes de que se "
                         "cansen.", n, n=_num(n))
    ejemplos = "; ".join(
        gettext("«%(anuncio)s» lleva el %(pct)s %% de «%(conjunto)s»",
                anuncio=_una_linea(a.get("nombre")) or str(a.get("ad_id")), pct=_pct(fr),
                conjunto=_una_linea(a.get("conjunto")) or str(a.get("adset_id")))
        for a, fr, _ in dependientes[:3])
    por_que = gettext("Del gasto de los últimos 7 días de su conjunto: %(ejemplos)s. Cada conjunto pesa %(minimo)s %% o "
                      "más del gasto de la cuenta.", ejemplos=ejemplos, minimo=_pct(CONCENTRACION_CONJUNTO_MIN))
    objetos = [_objeto("anuncio", a["ad_id"], a.get("nombre")) for a, _, _ in dependientes]
    return [cx.rec("concentracion", "baja", titulo, que_hacer, por_que, objetos)]


_REGLAS = (_cuenta_estado, _cuenta_roas_bajo, _aprendizaje_limitado, _perdedores_gastando, _anuncios_con_problemas,
           _escalar, _fatiga, _segmento_caro, _concentracion)


# ---------------------------------------------------------------- entrada y orden ---

def _por_cuenta(filas):
    salida = {}
    for f in filas or ():
        salida.setdefault(f.get("ad_account_id"), []).append(f)
    return salida


def _orden(r):
    impacto = r.get("impacto")
    return (NIVELES.index(r["nivel"]), (0, -impacto["monto"]) if impacto else (1, 0), TIPOS.index(r["tipo"]),
            r["cuenta"], r["id"])


def calcular(entrada):
    """Las recomendaciones de todas las cuentas de `entrada` (forma en el docstring del módulo), ya ordenadas."""
    entrada = entrada or {}
    t7, t30 = entrada.get("totales_7") or {}, entrada.get("totales_30") or {}
    objetos = _por_cuenta(o for o in entrada.get("objetos") or () if o.get("estado") == "ACTIVE"
                          and o.get("objeto_id"))
    anuncios = _por_cuenta(a for a in entrada.get("anuncios") or () if a.get("ad_id"))
    desgloses = _por_cuenta(entrada.get("desgloses_30"))
    conj7 = {str(k): v for k, v in (entrada.get("conjuntos_7") or {}).items()}
    frecuencia = {str(k): v for k, v in (entrada.get("frecuencia_7") or {}).items()}
    salida = []
    for c in entrada.get("cuentas") or ():
        act = c.get("ad_account_id")
        totales_30 = t30.get(act) or {}
        if not act or _f(totales_30.get("gasto")) <= 0:
            continue    # sin datos en el período: ninguna regla
        cx = _Cuenta(c, t7.get(act) or {}, totales_30, objetos.get(act, []), conj7, anuncios.get(act, []),
                     frecuencia, desgloses.get(act, []))
        for regla in _REGLAS:
            salida.extend(regla(cx))
    salida.sort(key=_orden)
    return salida

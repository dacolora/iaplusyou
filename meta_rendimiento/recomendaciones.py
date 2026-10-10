"""Qué hacer en las cuentas de Meta del alcance (Rendimiento E2, tarea 6; spec meta rendimiento §9, PND-192 sin los
desgloses): reglas PURAS y gratis sobre lo que Creatv ya copia de Meta. No lee la base, no llama a Meta ni a Claude:
recibe datos planos y devuelve `[{"nivel": "alta"|"media"|"bien", "texto"}]` ya traducido en el idioma de quien mira,
la forma de «Lo que necesita tu atención» (`triple_whale.evaluacion.alertas`). Toda cifra de un texto sale de los
datos que recibe; sin datos, la regla calla.

Entradas:
- `cuentas`: las cuentas del alcance (`meta_rendimiento.panel.lista`), con `nombre`, `moneda` y
  `extra.cuenta{account_status, disable_reason, amount_spent, spend_cap}` tal cual los manda Meta (los montos en la
  unidad menor de la moneda y como texto).
- `objetos`: `meta_rendimiento.datos.objetos_para_recomendar` (conjuntos y anuncios activos, rechazados o con
  problemas, con su gasto del período y la frecuencia de 7 días de la campaña de cada anuncio).
- `anuncios`: los anuncios evaluados de las cuentas cuya fuente es Meta (`panel.anuncios_evaluados(...)["ev"]`), con
  `veredicto` y `fatiga`. Las cuentas que cubre Triple Whale no traen anuncios evaluados de Meta: las reglas 4 y 6
  solo hablan de las demás.

Reglas, cada una con su umbral (spec §9; las de los desgloses quedan fuera, A6 del spec de la pestaña):
1. Aprendizaje limitado (media): N de M conjuntos activos con `aprendizaje == "FAIL"` que se llevan el 30 % o más
   del gasto de los conjuntos activos. El porcentaje nunca suma monedas distintas: con varias, cada moneda habla por su
   lado. Por debajo del umbral calla (la sección no tiene un nivel «baja» y sería ruido).
2. Rechazados o con problemas (alta): anuncios y conjuntos con `estado` DISAPPROVED o WITH_ISSUES.
3. Cuenta (alta / media): `account_status` distinto de 1, con el motivo de Meta en palabras si se conoce; un límite
   de gasto (`spend_cap`) al que le queda menos del 10 % (`amount_spent`).
4. Ganadores con poco presupuesto (bien): un ganador ACTIVO (un ganador en pausa no cuenta: subir el presupuesto
   gastaría en los otros anuncios del conjunto; revisión de la tarea 6, 2026-10-10) cuyo conjunto activo tiene
   presupuesto diario propio menor que la mediana de los conjuntos activos CON presupuesto de SU cuenta (cada cuenta
   tiene su moneda y su escala).
5. Concentración (media): en un conjunto activo con 3 o más anuncios activos, uno se lleva el 60 % o más del gasto
   del conjunto en el período.
6. Fatiga con frecuencia (media): un anuncio activo que se está cansando (`fatiga`) y cuya campaña tiene frecuencia
   de 7 días de 3 o más. Un perdedor no entra: hacerle variantes es mal consejo (ya lo cubre «gasto en perdedores»).

Orden de salida: alta, media, bien; dentro de cada nivel, el orden de las reglas."""
import math
import statistics

from flask_babel import gettext, ngettext

import idiomas
import tablero
from idiomas import N_
from meta_rendimiento.constantes import ESTADOS_CUENTA, OTRO_ESTADO
from tareas.meta import MONEDAS_SIN_DECIMALES

UMBRAL_APRENDIZAJE = 0.30          # parte del gasto de los conjuntos activos en aprendizaje limitado
UMBRAL_LIMITE_GASTO = 0.10         # lo que le queda al spend_cap de la cuenta
UMBRAL_CONCENTRACION = 0.60        # parte del gasto de un conjunto que se lleva un solo anuncio
MIN_ANUNCIOS_CONCENTRACION = 3     # anuncios activos que tiene que tener el conjunto para hablar de dependencia
FRECUENCIA_FATIGA = 3.0            # frecuencia de 7 días de la campaña
MAX_NOMBRES = 3                    # nombres de conjuntos que se listan antes de «y N más»
ESTADOS_PROBLEMA = ("DISAPPROVED", "WITH_ISSUES")
NIVELES = ("alta", "media", "bien")

# disable_reason de una cuenta publicitaria (Graph API, AdAccount). Solo los que se pueden decir con certeza; otro
# código no lleva motivo.
MOTIVOS_DESACTIVACION = {
    1: N_("incumplimiento de las políticas de publicidad"), 2: N_("revisión de propiedad intelectual"),
    3: N_("riesgo en los pagos"), 7: N_("cierre permanente"), 9: N_("cuenta sin uso"),
    11: N_("incumplimiento de las políticas del administrador comercial"),
    15: N_("cuenta comprometida (alguien entró sin permiso)"),
}


# ------------------------------------------------------------ números ---

def _entero(valor):
    """Un código de Meta (int o texto) como int; None si no se puede leer."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _monto(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(fraccion):
    """«30», nunca redondeado hacia arriba: un 59,9 % no se lee «60» junto a un umbral de 60 %."""
    return idiomas.numero(math.floor(round(fraccion * 100, 6)))


def _n(valor):
    return idiomas.numero(valor)


def _dinero(valor, moneda):
    """La misma regla que «Resultados» (`triple_whale.resultados`): entero desde 100, con centavos por debajo."""
    v = float(valor or 0)
    return tablero.dinero(round(v) if abs(v) >= 100 else round(v, 2), moneda or "")


def _de_unidad_menor(valor, moneda):
    """Meta manda amount_spent y spend_cap en la unidad menor (centavos) salvo en las monedas sin decimales."""
    v = _monto(valor)
    return v if (moneda or "").upper() in MONEDAS_SIN_DECIMALES else v / 100


def _nombre(texto, defecto):
    return f"«{texto or defecto}»"


def _lista_nombres(nombres):
    """«A», «B», «C» y N más."""
    primeros = ", ".join(nombres[:MAX_NOMBRES])
    resto = len(nombres) - MAX_NOMBRES
    return gettext("%(nombres)s y %(n)s más", nombres=primeros, n=_n(resto)) if resto > 0 else primeros


def _activos(objetos, nivel):
    return [o for o in objetos if o.get("nivel") == nivel and o.get("estado") == "ACTIVE"]


# ------------------------------------------------------------- reglas ---

def _aprendizaje(objetos, monedas):
    """Regla 1: un texto por moneda (uno solo si el alcance tiene una)."""
    por_moneda = {}
    for o in _activos(objetos, "conjunto"):
        por_moneda.setdefault(monedas.get(o.get("ad_account_id")), []).append(o)
    salida = []
    for moneda, conjuntos in por_moneda.items():
        limitados = [o for o in conjuntos if o.get("aprendizaje") == "FAIL"]
        total = sum(_monto(o.get("gasto")) for o in conjuntos)
        if not limitados or total <= 0:
            continue
        parte = sum(_monto(o.get("gasto")) for o in limitados) / total
        if parte < UMBRAL_APRENDIZAJE:
            continue
        texto = ngettext(
            "%(n)s de %(m)s conjuntos activos está en aprendizaje limitado (%(pct)s%% del gasto): júntalo con otro o "
            "sube su presupuesto para que salga de ahí. Meta necesita unas 50 conversiones por semana en cada conjunto.",
            "%(n)s de %(m)s conjuntos activos están en aprendizaje limitado (%(pct)s%% del gasto): junta conjuntos o "
            "sube su presupuesto para que salgan de ahí. Meta necesita unas 50 conversiones por semana en cada "
            "conjunto.", len(limitados), n=_n(len(limitados)), m=_n(len(conjuntos)), pct=_pct(parte))
        if len(por_moneda) > 1:
            texto = gettext("Cuentas en %(moneda)s: %(texto)s", moneda=moneda or "—", texto=texto)
        salida.append({"nivel": "media", "texto": texto})
    return salida


def _rechazados(objetos):
    """Regla 2."""
    n_anuncios = sum(1 for o in objetos if o.get("nivel") == "anuncio" and o.get("estado") in ESTADOS_PROBLEMA)
    n_conjuntos = sum(1 for o in objetos if o.get("nivel") == "conjunto" and o.get("estado") in ESTADOS_PROBLEMA)
    if n_anuncios and n_conjuntos:
        anuncios = ngettext("%(n)s anuncio", "%(n)s anuncios", n_anuncios, n=_n(n_anuncios))
        conjuntos = ngettext("%(n)s conjunto", "%(n)s conjuntos", n_conjuntos, n=_n(n_conjuntos))
        texto = gettext("%(anuncios)s y %(conjuntos)s están rechazados o con problemas: revisa en Meta qué piden para "
                        "que vuelvan a entregar.", anuncios=anuncios, conjuntos=conjuntos)
    elif n_anuncios:
        texto = ngettext("%(n)s anuncio está rechazado o con problemas: revisa en Meta qué pide para que vuelva a "
                         "entregar.",
                         "%(n)s anuncios están rechazados o con problemas: revisa en Meta qué piden para que vuelvan "
                         "a entregar.", n_anuncios, n=_n(n_anuncios))
    elif n_conjuntos:
        texto = ngettext("%(n)s conjunto está rechazado o con problemas: revisa en Meta qué pide para que vuelva a "
                         "entregar.",
                         "%(n)s conjuntos están rechazados o con problemas: revisa en Meta qué piden para que "
                         "vuelvan a entregar.", n_conjuntos, n=_n(n_conjuntos))
    else:
        return []
    return [{"nivel": "alta", "texto": texto}]


def _cuentas(cuentas):
    """Regla 3: el estado de cada cuenta (alta) y su límite de gasto (media)."""
    salida = []
    for c in cuentas:
        info = (c.get("extra") or {}).get("cuenta") or {}
        nombre = _nombre(c.get("nombre"), c.get("ad_account_id"))
        estado = _entero(info.get("account_status"))
        if estado is not None and estado != 1:
            etiqueta = ESTADOS_CUENTA.get(estado, OTRO_ESTADO)
            estado_txt = gettext(etiqueta)
            motivo = MOTIVOS_DESACTIVACION.get(_entero(info.get("disable_reason")))
            if motivo:
                motivo_txt = gettext(motivo)
                texto = gettext("La cuenta %(cuenta)s tiene un problema en Meta (%(estado)s, motivo: %(motivo)s): "
                                "revísala en el Administrador de anuncios.", cuenta=nombre, estado=estado_txt,
                                motivo=motivo_txt)
            else:
                texto = gettext("La cuenta %(cuenta)s tiene un problema en Meta (%(estado)s): revísala en el "
                                "Administrador de anuncios.", cuenta=nombre, estado=estado_txt)
            salida.append({"nivel": "alta", "texto": texto})
        moneda = c.get("moneda")
        limite = _de_unidad_menor(info.get("spend_cap"), moneda)
        if limite > 0:
            queda = max(0.0, limite - _de_unidad_menor(info.get("amount_spent"), moneda))
            if queda < limite * UMBRAL_LIMITE_GASTO:
                salida.append({"nivel": "media", "texto": gettext(
                    "A la cuenta %(cuenta)s le quedan %(queda)s de su límite de gasto de %(limite)s: súbelo en Meta "
                    "antes de que sus anuncios se detengan.", cuenta=nombre, queda=_dinero(queda, moneda),
                    limite=_dinero(limite, moneda))})
    return salida


def _ganadores_con_poco_presupuesto(objetos, anuncios, monedas):
    """Regla 4: un texto con el conjunto (o los conjuntos) cuyo presupuesto diario está bajo la mediana de su cuenta."""
    conjuntos = {o["objeto_id"]: o for o in _activos(objetos, "conjunto")}
    presupuestos = {}
    for o in conjuntos.values():
        if _monto(o.get("presupuesto_diario")) > 0:
            presupuestos.setdefault(o.get("ad_account_id"), []).append(_monto(o.get("presupuesto_diario")))
    medianas = {act: statistics.median(v) for act, v in presupuestos.items()}
    # Solo un ganador que entrega hoy: subir el presupuesto por uno en pausa gastaría en los otros anuncios del conjunto.
    activos = {o["objeto_id"] for o in _activos(objetos, "anuncio")}
    elegidos = {}                         # adset_id -> (conjunto, mediana, ganadores); en el orden de los anuncios
    for a in anuncios:
        if a.get("veredicto") != "ganador" or str(a.get("ad_id") or "") not in activos:
            continue
        s = conjuntos.get(str(a.get("adset_id") or ""))
        presupuesto = _monto((s or {}).get("presupuesto_diario"))
        mediana = medianas.get((s or {}).get("ad_account_id"))
        if not s or presupuesto <= 0 or mediana is None or presupuesto >= mediana:
            continue
        previo = elegidos.get(s["objeto_id"])
        elegidos[s["objeto_id"]] = (s, mediana, (previo[2] if previo else 0) + 1)
    if not elegidos:
        return []
    if len(elegidos) == 1:
        s, mediana, ganadores = next(iter(elegidos.values()))
        moneda = monedas.get(s.get("ad_account_id"))
        texto = ngettext(
            "Sube el presupuesto de %(conjunto)s: tiene %(n)s anuncio ganador y su presupuesto diario (%(presupuesto)s) "
            "está por debajo de la mediana de los conjuntos activos de su cuenta (%(mediana)s). Súbelo de a 20%% para "
            "no reiniciar el aprendizaje.",
            "Sube el presupuesto de %(conjunto)s: tiene %(n)s anuncios ganadores y su presupuesto diario "
            "(%(presupuesto)s) está por debajo de la mediana de los conjuntos activos de su cuenta (%(mediana)s). "
            "Súbelo de a 20%% para no reiniciar el aprendizaje.", ganadores, n=_n(ganadores),
            conjunto=_nombre(s.get("nombre"), s["objeto_id"]), presupuesto=_dinero(s.get("presupuesto_diario"), moneda),
            mediana=_dinero(mediana, moneda))
    else:
        nombres = [_nombre(s.get("nombre"), s["objeto_id"]) for s, _, _ in elegidos.values()]
        texto = gettext(
            "Sube el presupuesto de %(n)s conjuntos con anuncios ganadores y presupuesto diario por debajo de la mediana "
            "de los conjuntos activos de su cuenta: %(nombres)s. Súbelos de a 20%% para no reiniciar el aprendizaje.",
            n=_n(len(elegidos)), nombres=_lista_nombres(nombres))
    return [{"nivel": "bien", "texto": texto}]


def _concentracion(objetos):
    """Regla 5: un texto; con varios conjuntos, el ejemplo es el de más gasto."""
    por_conjunto = {}
    for o in _activos(objetos, "anuncio"):
        por_conjunto.setdefault(str(o.get("padre_id") or ""), []).append(o)
    casos = []                            # (conjunto, anuncio, parte, n_anuncios)
    for s in _activos(objetos, "conjunto"):
        propios = por_conjunto.get(s["objeto_id"]) or []
        total = _monto(s.get("gasto"))
        if len(propios) < MIN_ANUNCIOS_CONCENTRACION or total <= 0:
            continue
        mayor = max(propios, key=lambda o: (_monto(o.get("gasto")), o["objeto_id"]))
        parte = _monto(mayor.get("gasto")) / total
        if parte >= UMBRAL_CONCENTRACION:
            casos.append((s, mayor, parte, len(propios)))
    if not casos:
        return []
    s, anuncio, parte, n = max(casos, key=lambda c: (_monto(c[0].get("gasto")), c[0]["objeto_id"]))
    conjunto_txt, anuncio_txt = _nombre(s.get("nombre"), s["objeto_id"]), _nombre(anuncio.get("nombre"),
                                                                                  anuncio["objeto_id"])
    if len(casos) == 1:
        texto = gettext("El anuncio %(anuncio)s se lleva el %(pct)s%% del gasto de su conjunto %(conjunto)s, que tiene "
                        "%(n)s anuncios activos: si se cansa, el conjunto cae con él. Prueba variantes nuevas para no "
                        "depender de un solo creativo.", anuncio=anuncio_txt, pct=_pct(parte), conjunto=conjunto_txt,
                        n=_n(n))
    else:
        texto = gettext("En %(n)s conjuntos un solo anuncio se lleva el %(umbral)s%% o más del gasto, como %(anuncio)s "
                        "(%(pct)s%% de %(conjunto)s): si se cansa, el conjunto cae con él. Prueba variantes nuevas "
                        "para no depender de un solo creativo.", n=_n(len(casos)),
                        umbral=_pct(UMBRAL_CONCENTRACION), anuncio=anuncio_txt, pct=_pct(parte),
                        conjunto=conjunto_txt)
    return [{"nivel": "media", "texto": texto}]


def _fatiga(objetos, anuncios):
    """Regla 6: un texto con cuántos y la frecuencia más alta de sus campañas."""
    frecuencias = {o["objeto_id"]: o.get("frecuencia_7") for o in _activos(objetos, "anuncio")}
    vistas = [frecuencias.get(str(a.get("ad_id"))) for a in anuncios
              if a.get("fatiga") and a.get("veredicto") != "perdedor"]
    altas = [f for f in vistas if f is not None and f >= FRECUENCIA_FATIGA]
    if not altas:
        return []
    texto = ngettext(
        "%(n)s anuncio se está cansando y su campaña ya tiene una frecuencia de %(f)s en 7 días: haz variantes nuevas "
        "en Crear para no cansar más a la misma gente.",
        "%(n)s anuncios se están cansando en campañas con una frecuencia de hasta %(f)s en 7 días: haz variantes "
        "nuevas en Crear para no cansar más a la misma gente.", len(altas), n=_n(len(altas)),
        f=idiomas.numero(max(altas), 1))
    return [{"nivel": "media", "texto": texto}]


# ------------------------------------------------------------ entrada ---

def recomendar(cuentas, objetos, anuncios=()):
    """Las recomendaciones de esas cuentas, de la más urgente a la buena noticia (ver el docstring del módulo)."""
    cuentas, objetos, anuncios = list(cuentas or []), list(objetos or []), list(anuncios or [])
    monedas = {c.get("ad_account_id"): (c.get("moneda") or "").upper() or None for c in cuentas}
    salida = (_cuentas(cuentas) + _rechazados(objetos) + _aprendizaje(objetos, monedas) + _concentracion(objetos)
              + _fatiga(objetos, anuncios) + _ganadores_con_poco_presupuesto(objetos, anuncios, monedas))
    orden = {n: i for i, n in enumerate(NIVELES)}
    return sorted(salida, key=lambda r: orden[r["nivel"]])

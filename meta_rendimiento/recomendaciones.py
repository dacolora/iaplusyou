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
      "conjuntos_problema": [{"objeto_id", "ad_account_id", "nombre", "estado", "problemas_meta"}],
                       # los conjuntos WITH_ISSUES o DISAPPROVED (PND-287), con lo que Meta dice de cada uno
      "conjuntos_7": {adset_id: {"gasto", "compras", "valor"}},  # `datos.gasto_por_conjunto`, últimos 7 días
      "anuncios": [{"ad_id", "ad_account_id", "adset_id", "campaign_id", "nombre", "conjunto", "estado",
                    "veredicto", "problemas", "problemas_meta", "m", "gasto_7", "gasto_30"}],
                       # los evaluados por `panel.evaluar_anuncios` más `gasto_7` (su gasto de los últimos 7 días,
                       # de la lectura `recientes` que esa función ya hace) y `gasto_30` (si falta, `m["gasto"]`:
                       # el panel evalúa 30 días por defecto). `problemas_meta`: lo que Meta dice de cada problema
                       # del anuncio ([{"resumen", "mensaje"}], `issues_info` copiado; PND-258)
      "frecuencia_7": {campaign_id: {"alcance", "frecuencia"}},  # `datos.alcance(…, 7, "campana")`
      "desgloses_30": [{"ad_account_id", "dimension", "clave", "gasto", "compras", "valor", …}],
                       # `datos.desgloses(…, 30)`
    }

Una clave que falta vale vacío. Una cuenta sin gasto en 30 días no genera ninguna regla (spec §6).

Salida: [{"id", "nivel": alta|media|baja, "tipo", "cuenta" (act_…), "cuenta_nombre", "titulo", "que_hacer",
"por_que", "impacto": {"monto", "moneda", "texto", "corto"}|None, "objetos": [{"nivel", "id", "nombre"}], "enlace",
"fila": {"etiqueta", "cifra", "nota", "barra", "gasto"}}], ordenadas por nivel y luego por impacto (los que no tienen
van después en su nivel). `fila` son las cifras sueltas de la fila del Diagnóstico agrupado (`agrupar`, pedido de
Daniel 2026-10-13: cinco tarjetas repetían el mismo consejo con las cifras enterradas en la prosa): `etiqueta` es lo
que nombra la fila cuando no es la cuenta (la campaña o el conjunto de `escalar`, el segmento de `segmento_caro`),
`cifra` y `nota` lo que se ve de un vistazo, `barra` una fracción 0–1 o None y `gasto` la parte del gasto de la cuenta
en texto o None. `anuncios_con_problemas` y `conjuntos_con_problemas` traen además `problemas`: [{"nombre", "texto"}] de sus anuncios con lo que
Meta dice de cada uno (como mucho `MAX_PROBLEMAS_VISIBLES`, los de más gasto; PND-258). No va en `que_hacer` ni en
`por_que`, que la «Evaluación con IA» le manda a Claude: así su prompt y su precio no cambian. Los montos van en la moneda de
la cuenta: en «Todas» el orden por impacto es nominal entre monedas (como PND-196). `impacto.monto` es siempre «por
día» (lo que está en juego cada día), para que se puedan comparar. `objetos` trae como mucho `MAX_OBJETOS` (los de
más gasto) y `enlace` es el Administrador de anuncios con ellos seleccionados (`administrador.enlace`) o, para lo que
es de toda la cuenta, sus campañas. `id` es la huella de Alertas (ruling E2-R4: sha256 hex completo, el formato de
`alertas.huella` y `alertas.HUELLA_VALIDA`; `huella_recomendacion`): en los tipos que juntan TODO lo de una cuenta
(`AGREGADOS`) es tipo + cuenta + nivel, porque su lista de objetos cambia en cada copia (un anuncio con problemas que
sale de los 30 días) y una alerta descartada no debe volver cada 3 horas; en los demás, tipo + cuenta + los ids de
sus objetos ordenados (un segmento: su dimensión y clave).

Textos con gettext/ngettext (en el idioma de quien mira, o el del proyecto si se arman dentro de `idiomas.en_idioma`)
y cifras con `idiomas.numero`."""
import hashlib
from collections import Counter

from flask_babel import gettext, ngettext

import idiomas
from idiomas import N_
from meta_rendimiento import administrador
from triple_whale import paises

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
         "conjuntos_con_problemas", "escalar", "fatiga", "segmento_caro", "concentracion")
# Tipos que juntan todo lo de una cuenta en una sola recomendación: su huella no lleva los objetos (ruling E2-R4).
AGREGADOS = ("aprendizaje_limitado", "perdedores_gastando", "anuncios_con_problemas", "cuenta_roas_bajo",
             "cuenta_estado", "conjuntos_con_problemas")
# Tipos que alguna regla puede marcar «alta»: los que la copia guarda para Alertas, y cada uno tiene su título en
# `alertas.TEXTOS_META_RENDIMIENTO` (la fuente ignora un tipo sin texto). Una prueba exige que coincidan con las
# reglas y con esos textos, para que un «alta» nuevo no se pierda en silencio (revisión de la Task 4 de E2).
TIPOS_ALTA = ("cuenta_estado", "cuenta_roas_bajo", "aprendizaje_limitado", "perdedores_gastando",
              "anuncios_con_problemas", "conjuntos_con_problemas")
# effective_status de un anuncio que entrega (o puede entregar): WITH_ISSUES sigue gastando en muchos casos.
ESTADOS_ENTREGA = ("ACTIVE", "WITH_ISSUES")
ESTADOS_PROBLEMA = ("WITH_ISSUES", "DISAPPROVED")
MAX_PROBLEMAS_VISIBLES = 10       # anuncios con su motivo de Meta en la fila de `anuncios_con_problemas` (PND-258)

# El Diagnóstico agrupado (`agrupar`): un bloque por tipo con el consejo UNA vez y una fila por recomendación. Cada
# consejo recibe las mismas cifras (`_cifras_consejo`); el título va en `_titulo_grupo` porque lleva plural.
CONSEJOS = {
    "cuenta_estado": N_("Cada cuenta dice qué la frena: ábrela para ver qué hacer."),
    "cuenta_roas_bajo": N_("Pausa o rehace estas cuentas: por debajo de ROAS %(minimo)s× se pierde dinero casi seguro."),
    "aprendizaje_limitado": N_("Consolida conjuntos parecidos dentro de la misma campaña: Meta pide unas %(meta)s "
                               "compras por semana por conjunto para sacarlo del aprendizaje. Abre una cuenta para ver "
                               "por qué campañas empezar."),
    "perdedores_gastando": N_("Páusalos: libera su presupuesto para los anuncios que venden."),
    "anuncios_con_problemas": N_("Revísalos en el Administrador de anuncios: Meta les marca un problema que frena o "
                                 "detiene su entrega."),
    "conjuntos_con_problemas": N_("Revísalos en el Administrador de anuncios: mientras Meta les marque un problema, "
                                  "sus anuncios no entregan o entregan menos."),
    "escalar": N_("Venden mejor que su cuenta: sube %(pct)s %% el presupuesto diario (más de %(pct)s %% reinicia el "
                  "aprendizaje)."),
    "fatiga": N_("Prepara variantes antes de que se apaguen: «Evaluar con IA» propone ideas a partir de lo que ya "
                 "funciona."),
    "segmento_caro": N_("Excluye o baja el peso de estos segmentos en los conjuntos de su cuenta: gastan mucho y venden "
                        "menos de la mitad que el resto."),
    "concentracion": N_("Prepara variantes del anuncio que carga cada conjunto antes de que se canse."),
}
# Encabezados de las columnas de cada bloque: lo que nombra la fila, la cifra y la parte del gasto (con su ventana).
CABECERA_ETIQUETA = {"escalar": N_("Campaña o conjunto"), "segmento_caro": N_("Segmento")}
CABECERA_CUENTA = N_("Cuenta")
CABECERA_CIFRA = {
    "cuenta_estado": N_("Qué pasa"),
    "cuenta_roas_bajo": N_("ROAS de 30 días"),
    "aprendizaje_limitado": N_("Conjuntos activos en aprendizaje limitado"),
    "perdedores_gastando": N_("Perdedores activos"),
    "anuncios_con_problemas": N_("Anuncios con problemas"),
    "conjuntos_con_problemas": N_("Conjuntos con problemas"),
    "escalar": N_("ROAS de 7 días"),
    "fatiga": N_("Anuncios que se cansan"),
    "segmento_caro": N_("ROAS de 30 días"),
    "concentracion": N_("Conjuntos que dependen de uno"),
}
GASTO_7, GASTO_30 = N_("Del gasto de 7 días"), N_("Del gasto de 30 días")
CABECERA_GASTO = {"aprendizaje_limitado": GASTO_7, "perdedores_gastando": GASTO_7,
                  "anuncios_con_problemas": GASTO_30, "segmento_caro": GASTO_30}

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
# disable_reason de una cuenta publicitaria (Graph API, AdAccount), en palabras (PND-287: la regla jubilada de
# Rendimiento E2 lo decía y el Diagnóstico no). Solo los que se pueden decir con certeza; otro código no lleva motivo.
MOTIVOS_DESACTIVACION = {
    1: N_("incumplimiento de las políticas de publicidad"), 2: N_("revisión de propiedad intelectual"),
    3: N_("riesgo en los pagos"), 7: N_("cierre permanente"), 9: N_("cuenta sin uso"),
    11: N_("incumplimiento de las políticas del administrador comercial"),
    15: N_("cuenta comprometida (alguien entró sin permiso)"),
}

# Dimensiones de los desgloses en palabras (las usa también la sección «Segmentos» del panel).
DIMENSIONES = {"edad_genero": N_("Edad y género"), "ubicacion": N_("Ubicación"), "pais": N_("País"),
               "dispositivo": N_("Dispositivo")}
# Las claves de Meta en palabras (`nombre_segmento`). Mismos textos que las etiquetas de los desgloses de Experimentos
# (`resultados._PLATAFORMAS`, `_POSICIONES`, `_GENEROS`, `_DISPOSITIVOS`): las dos pantallas dicen lo mismo y comparten
# la traducción. No se importan de ahí porque `resultados` arrastra la base y el Tablero. Los nombres de marca
# (Facebook, iPhone…) no pasan por el catálogo.
SIN_DATO = N_("Sin dato")
GENEROS = {"female": N_("Mujeres"), "male": N_("Hombres")}
PLATAFORMAS = {"facebook": "Facebook", "instagram": "Instagram", "messenger": "Messenger",
               "audience_network": "Audience Network", "threads": "Threads", "whatsapp": "WhatsApp"}
POSICIONES = {"feed": N_("Feed"), "marketplace": N_("Marketplace"), "video_feeds": N_("Videos"),
              "instream_video": N_("En el video"), "search": N_("Búsqueda"), "instagram_search": N_("Búsqueda"),
              "right_hand_column": N_("Columna derecha"), "profile_feed": N_("Feed del perfil"),
              "instagram_profile_feed": N_("Feed del perfil"), "facebook_reels_overlay": N_("Anuncios en Reels"),
              "messenger_inbox": N_("Bandeja de entrada"), "an_classic": N_("Nativo, banner e intersticial"),
              "classic": N_("Nativo, banner e intersticial"), "rewarded_video": N_("Video con recompensa"),
              "notification": N_("Notificaciones"), "threads_feed": N_("Feed")}
POSICION_REELS, POSICION_HISTORIAS, POSICION_EXPLORAR = N_("Reels"), N_("Historias"), N_("Explorar")
DISPOSITIVOS = {"mobile_app": N_("Celular (app)"), "mobile_web": N_("Celular (web)"), "desktop": N_("Computador"),
                "iphone": "iPhone", "ipad": "iPad", "ipod": "iPod", "android_smartphone": N_("Celular Android"),
                "android_tablet": N_("Tableta Android"), "connected_tv": N_("Televisor conectado"),
                "other": N_("Otro")}


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


def huella(*partes):
    """sha256 hex (64) de las partes unidas con «|»: la misma fórmula que `alertas.huella` (una prueba lo compara), sin
    importar `alertas`, que arrastra la base."""
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()


def huella_recomendacion(tipo, act, nivel, claves=()):
    """El id estable de una recomendación (= la huella de su alerta, ruling E2-R4). Tipos `AGREGADOS`: tipo + cuenta +
    nivel (una alerta descartada vuelve solo si sube o baja de nivel, no porque cambió su lista de anuncios). Los
    demás: tipo + cuenta + las claves (ids de objetos) ordenadas y sin repetir."""
    if tipo in AGREGADOS:
        return huella(tipo, act, nivel)
    return huella(tipo, act, ",".join(sorted({str(c) for c in claves or ()})))


def _impacto(monto_dia, moneda):
    if not monto_dia or monto_dia <= 0:
        return None
    corto = _dinero(monto_dia, moneda)
    return {"monto": monto_dia, "moneda": moneda, "corto": corto,
            "texto": gettext("%(monto)s por día en juego", monto=corto)}


def _fila(cifra, nota=None, barra=None, gasto=None, etiqueta=None):
    """Las cifras sueltas de una recomendación para su fila en el Diagnóstico agrupado (ver la salida en el docstring
    del módulo). `barra` y `gasto` son fracciones (None = no aplica): la barra se acota a 0–1 y el gasto sale en texto
    («10 %»)."""
    return {"etiqueta": etiqueta, "cifra": cifra, "nota": nota,
            "barra": None if barra is None else round(min(max(_f(barra), 0.0), 1.0), 3),
            "gasto": None if gasto is None else gettext("%(pct)s %%", pct=_pct(gasto))}


def _objeto(nivel, objeto_id, nombre):
    return {"nivel": nivel, "id": str(objeto_id), "nombre": _una_linea(nombre) or str(objeto_id)}


# ---------------------------------------------------------------- la cuenta ---

class _Cuenta:
    """Lo de UNA cuenta que miran las reglas, ya filtrado y sumado."""

    def __init__(self, c, t7, t30, objetos, conj7, anuncios, frecuencia, desgloses, conjuntos_problema=()):
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
        self.conjuntos_problema = list(conjuntos_problema)
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

    def rec(self, tipo, nivel, titulo, que_hacer, por_que, objetos=(), impacto=None, claves=None, enlace=None,
            fila=None):
        """Una recomendación. `objetos` ya ordenados (los de más peso primero): se guardan los primeros
        MAX_OBJETOS, pero la huella usa TODOS (o `claves`, si se dan; los `AGREGADOS` no usan ninguno). `fila` es
        `_fila(...)`; sin ella la fila muestra el título."""
        objetos = list(objetos)
        ids = [o["id"] for o in objetos] if claves is None else claves
        visibles = objetos[:MAX_OBJETOS]
        if enlace is None:
            enlace = (administrador.enlace(self.act, visibles[0]["nivel"], [o["id"] for o in visibles])
                      if visibles else None) or administrador.enlace_cuenta(self.act)
        return {"id": huella_recomendacion(tipo, self.act, nivel, ids), "nivel": nivel, "tipo": tipo, "cuenta": self.act,
                "cuenta_nombre": self.nombre, "titulo": titulo, "que_hacer": que_hacer, "por_que": por_que,
                "impacto": impacto, "objetos": visibles, "enlace": enlace, "fila": fila or _fila(titulo)}

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
    cabe = int(cx.compras_7 // COMPRAS_SEMANA_POR_CONJUNTO)
    total = len(activos)
    titulo = ngettext("%(n)s de %(total)s conjunto activo en aprendizaje limitado",
                      "%(n)s de %(total)s conjuntos activos en aprendizaje limitado", total,
                      n=_num(len(fail)), total=_num(total))
    if cabe < 1:
        que_hacer = gettext(
            "Consolida conjuntos parecidos dentro de la misma campaña: con %(compras)s compras por semana, ningún "
            "conjunto llega a las %(meta)s que Meta necesita para salir del aprendizaje; concentra el presupuesto en 1 "
            "o 2 conjuntos.", compras=_num(cx.compras_7), meta=_num(COMPRAS_SEMANA_POR_CONJUNTO))
    else:
        que_hacer = ngettext(
            "Consolida conjuntos parecidos dentro de la misma campaña: con %(compras)s compras por semana, esta "
            "cuenta da para ~%(cabe)s conjunto que salga del aprendizaje (Meta pide unas %(meta)s por conjunto).",
            "Consolida conjuntos parecidos dentro de la misma campaña: con %(compras)s compras por semana, esta "
            "cuenta da para ~%(cabe)s conjuntos que salgan del aprendizaje (Meta pide unas %(meta)s por conjunto).",
            cabe, compras=_num(cx.compras_7), cabe=_num(cabe), meta=_num(COMPRAS_SEMANA_POR_CONJUNTO))
    if top:
        lista = ", ".join(gettext("«%(nombre)s» (%(n)s)", nombre=nombre(cid), n=_num(n)) for cid, n in top)
        que_hacer += " " + gettext("Empieza por las campañas con más conjuntos limitados: %(campanas)s.",
                                   campanas=lista)
    por_que = ngettext(
        "%(n)s de %(total)s conjunto activo (%(pct_conjuntos)s %%) está en aprendizaje limitado y se llevó "
        "%(gasto)s de los %(gasto_cuenta)s de los últimos 7 días (%(pct_gasto)s %%): sin salir del aprendizaje, Meta "
        "no estabiliza su entrega.",
        "%(n)s de %(total)s conjuntos activos (%(pct_conjuntos)s %%) están en aprendizaje limitado y se llevaron "
        "%(gasto)s de los %(gasto_cuenta)s de los últimos 7 días (%(pct_gasto)s %%): sin salir del aprendizaje, Meta "
        "no estabiliza su entrega.",
        total, n=_num(len(fail)), total=_num(total), pct_conjuntos=_pct(frac_conjuntos), gasto=cx.dinero(gasto_fail),
        gasto_cuenta=cx.dinero(cx.gasto_7), pct_gasto=_pct(frac_gasto))
    objetos = [_objeto("campana", cid, nombre(cid)) for cid, _ in top]
    if cabe < 1:
        nota = gettext("ninguno junta %(meta)s compras por semana", meta=_num(COMPRAS_SEMANA_POR_CONJUNTO))
    else:
        nota = ngettext("da para ~%(cabe)s fuera del aprendizaje", "da para ~%(cabe)s fuera del aprendizaje", cabe,
                        cabe=_num(cabe))
    fila = _fila(gettext("%(n)s de %(total)s", n=_num(len(fail)), total=_num(total)), nota, barra=frac_conjuntos,
                 gasto=frac_gasto)
    return [cx.rec("aprendizaje_limitado", nivel, titulo, que_hacer, por_que, objetos,
                   cx.impacto(gasto_fail / DIAS_SEMANA), fila=fila)]


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
    fila = _fila(ngettext("%(n)s anuncio", "%(n)s anuncios", n, n=_num(n)),
                 gettext("%(gasto)s en 7 días", gasto=cx.dinero(gasto)), gasto=fraccion or 0)
    return [cx.rec("perdedores_gastando", nivel, titulo, que_hacer, por_que, objetos,
                   cx.impacto(gasto / DIAS_SEMANA), fila=fila)]


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
        fila = _fila(gettext("%(roas)s× (la cuenta, %(roas_cuenta)s×)", roas=_roas(roas),
                             roas_cuenta=_roas(roas_cuenta)),
                     gettext("de %(antes)s a %(despues)s por día", antes=cx.dinero(antes), despues=cx.dinero(despues)),
                     etiqueta=nombre)
        salida.append(cx.rec("escalar", "media", titulo, que_hacer, por_que, [_objeto(nivel_obj, oid, nombre)],
                             fila=fila))
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
        "Su ROAS o su CTR cayó frente a la semana anterior, y las personas de su campaña ya vieron sus anuncios "
        "%(frecuencia)s veces en promedio en los últimos 7 días (desde %(minimo)s se nota el cansancio).",
        "A cada uno le cayó el ROAS o el CTR frente a la semana anterior, y las personas de sus campañas ya vieron "
        "sus anuncios hasta %(frecuencia)s veces en promedio en los últimos 7 días (desde %(minimo)s se nota el "
        "cansancio).",
        n, frecuencia=_num(frecuencia, 1), minimo=_num(FATIGA_FRECUENCIA_MIN))
    objetos = [_objeto("anuncio", a["ad_id"], a.get("nombre")) for a in cansados]
    fila = _fila(ngettext("%(n)s anuncio", "%(n)s anuncios", n, n=_num(n)),
                 gettext("frecuencia de 7 días: %(frecuencia)s", frecuencia=_num(frecuencia, 1)))
    return [cx.rec("fatiga", "media", titulo, que_hacer, por_que, objetos, fila=fila)]


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
    nota = (ngettext("%(n)s rechazado sigue gastando", "%(n)s rechazados siguen gastando", len(rechazados_7),
                     n=_num(len(rechazados_7))) if rechazados_7 else
            gettext("%(gasto)s en 30 días", gasto=cx.dinero(gasto)))
    fila = _fila(ngettext("%(n)s anuncio", "%(n)s anuncios", n, n=_num(n)), nota,
                 gasto=min(_div(gasto, cx.gasto_30) or 0.0, 1.0))
    r = cx.rec("anuncios_con_problemas", "alta" if rechazados_7 else "media", titulo, que_hacer, por_que,
               objetos, cx.impacto(gasto / DIAS_MES), fila=fila)
    r["problemas"] = [{"nombre": _una_linea(a.get("nombre")) or str(a["ad_id"]), "texto": _texto_problema(p)}
                      for a in malos for p in (a.get("problemas_meta") or [])[:1]][:MAX_PROBLEMAS_VISIBLES]
    return [r]


def _texto_problema(p):
    """«Resumen: mensaje» de un problema de Meta (`sync.problemas_de`), o lo que traiga de los dos."""
    resumen, mensaje = _una_linea(p.get("resumen")), _una_linea(p.get("mensaje"))
    if resumen and mensaje and mensaje != resumen:
        return f"{resumen}: {mensaje}"
    return resumen or mensaje


def _conjuntos_con_problemas(cx):
    """PND-287 (la regla jubilada de Rendimiento E2 que el Diagnóstico no tenía): los conjuntos que Meta rechazó o marca
    con problemas (WITH_ISSUES/DISAPPROVED) frenan TODOS sus anuncios, aunque cada anuncio esté bien. Alta, como la
    regla vieja: es un conjunto que el anunciante quiere entregando. No depende del gasto (uno bloqueado no gasta);
    se ordenan por su gasto de 7 días y lo que estaba en juego es ese gasto por día."""
    malos = sorted(cx.conjuntos_problema, key=lambda o: (-_f(cx.g7(o["objeto_id"]).get("gasto")), str(o["objeto_id"])))
    if not malos:
        return []
    n = len(malos)
    gasto = sum(_f(cx.g7(o["objeto_id"]).get("gasto")) for o in malos)
    titulo = ngettext("%(n)s conjunto rechazado o con problemas en Meta",
                      "%(n)s conjuntos rechazados o con problemas en Meta", n, n=_num(n))
    que_hacer = ngettext(
        "Revísalo en el Administrador de anuncios: mientras Meta le marque un problema, sus anuncios no entregan o "
        "entregan menos.",
        "Revísalos en el Administrador de anuncios: mientras Meta les marque un problema, sus anuncios no entregan o "
        "entregan menos.", n)
    por_que = ngettext("%(n)s conjunto está rechazado o con problemas en Meta y frena la entrega de sus anuncios.",
                       "%(n)s conjuntos están rechazados o con problemas en Meta y frenan la entrega de sus anuncios.",
                       n, n=_num(n))
    objetos = [_objeto("conjunto", o["objeto_id"], o.get("nombre")) for o in malos]
    nota = (gettext("%(gasto)s en 7 días", gasto=cx.dinero(gasto)) if gasto > 0
            else gettext("sin gasto en 7 días"))
    fila = _fila(ngettext("%(n)s conjunto", "%(n)s conjuntos", n, n=_num(n)), nota)
    r = cx.rec("conjuntos_con_problemas", "alta", titulo, que_hacer, por_que, objetos, cx.impacto(gasto / DIAS_SEMANA),
               fila=fila)
    r["problemas"] = [{"nombre": _una_linea(o.get("nombre")) or str(o["objeto_id"]), "texto": _texto_problema(p)}
                      for o in malos for p in (o.get("problemas_meta") or [])[:1]][:MAX_PROBLEMAS_VISIBLES]
    return [r]


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
    fila = _fila(gettext("ROAS %(roas)s×", roas=_roas(roas)),
                 gettext("vendió %(valor)s de %(gasto)s gastados", valor=cx.dinero(cx.valor_30),
                         gasto=cx.dinero(cx.gasto_30)))
    return [cx.rec("cuenta_roas_bajo", "alta", titulo, que_hacer, por_que, objetos,
                   cx.impacto(cx.gasto_30 / DIAS_MES), fila=fila)]


def _cuenta_estado(cx):
    estado = _entero(cx.info.get("account_status"))
    motivos, acciones, cifras = [], [], []
    titulo, barra, razon = None, None, None
    if estado is not None and estado != CUENTA_ACTIVA:
        motivo, accion = ESTADOS_CUENTA.get(estado, OTRO_ESTADO)
        motivos.append(gettext(motivo, codigo=estado))
        acciones.append(gettext(accion))
        titulo = gettext("La cuenta no está activa en Meta")
        cifras.append(gettext("No está activa"))
        # PND-287: por qué la desactivó, en palabras. Va en la fila (lo que se ve de un vistazo), no en `por_que`, que
        # la «Evaluación con IA» le manda a Claude: su prompt y su precio no cambian.
        if MOTIVOS_DESACTIVACION.get(_entero(cx.info.get("disable_reason"))):
            razon = gettext("motivo según Meta: %(motivo)s",
                            motivo=gettext(MOTIVOS_DESACTIVACION[_entero(cx.info.get("disable_reason"))]))
    tope = _monto_menor(cx.info.get("spend_cap"), cx.moneda)
    gastado = _monto_menor(cx.info.get("amount_spent"), cx.moneda)
    if tope > 0 and gastado >= TOPE_FRACCION * tope:
        motivos.append(gettext("Gastó %(gastado)s de su tope de %(tope)s (%(pct)s %%): al llegar al tope, Meta deja de "
                               "entregar sus anuncios.", gastado=cx.dinero(gastado), tope=cx.dinero(tope),
                               pct=_pct(gastado / tope)))
        acciones.append(gettext("Sube o quita el tope de gasto en la configuración de pagos de la cuenta."))
        titulo = titulo or gettext("La cuenta está por llegar a su tope de gasto")
        cifras.append(gettext("%(pct)s %% de su tope de gasto", pct=_pct(gastado / tope)))
        barra = gastado / tope
    if not motivos:
        return []
    nota = " · ".join(t for t in (razon, cifras[1] if len(cifras) > 1 else None) if t) or None
    fila = _fila(cifras[0], nota, barra=barra)
    return [cx.rec("cuenta_estado", "alta", titulo, " ".join(acciones), " ".join(motivos), fila=fila)]


def _legible(valor):
    """Una clave de Meta que no está en los diccionarios: guiones bajos a espacios y la primera letra en mayúscula."""
    texto = str(valor).replace("_", " ").strip()
    return texto[:1].upper() + texto[1:]


def _parte(valor, diccionario):
    if valor.lower() == SIN_VALOR:
        return gettext(SIN_DATO)
    texto = diccionario.get(valor.lower())
    return gettext(texto) if texto else _legible(valor)


def _posicion(valor):
    k = valor.lower()
    if k == SIN_VALOR:
        return gettext(SIN_DATO)
    texto = POSICIONES.get(k) or (POSICION_REELS if k.endswith("reels") else
                                  POSICION_HISTORIAS if k.endswith(("stories", "story")) else
                                  POSICION_EXPLORAR if "explore" in k else None)
    return gettext(texto) if texto else _legible(valor)


def nombre_segmento(dimension, clave, locale=None):
    """Un segmento de desglose en palabras, para la regla `segmento_caro` y la sección «Segmentos» del panel:
    «25–34 · Mujeres», «Instagram · Reels», «Noruega» (el país en el idioma `locale`; por defecto el activo, el de
    quien mira o el de `idiomas.en_idioma`), «Celular (app)». Lo que Meta no sabe clasificar es «Sin dato» y una
    clave desconocida va legible (guiones bajos a espacios)."""
    partes = [p.strip() for p in str(clave or "").split("|")]
    if dimension == "edad_genero" and len(partes) == 2:
        edad, genero = partes
        edad = gettext(SIN_DATO) if edad.lower() == SIN_VALOR else edad.replace("-", "–")
        return " · ".join((edad, _parte(genero, GENEROS)))
    if dimension == "ubicacion":
        plataforma, posicion = (partes + [""])[:2]
        return " · ".join(t for t in (_parte(plataforma, PLATAFORMAS) if plataforma else "",
                                      _posicion(posicion) if posicion else "") if t)
    if dimension == "pais" and len(partes) == 1:
        codigo = partes[0]
        if not codigo or codigo.lower() == SIN_VALOR:
            return gettext(SIN_DATO)
        return paises.nombre_pais(codigo, locale or idiomas.activo())
    if dimension == "dispositivo" and len(partes) == 1:
        return _parte(partes[0], DISPOSITIVOS)
    return " · ".join(_legible(p) for p in partes)


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
            fila = _fila(gettext("%(roas)s× (la cuenta, %(roas_cuenta)s×)", roas=_roas(roas),
                                 roas_cuenta=_roas(roas_cuenta)),
                         gettext("%(gasto)s en 30 días", gasto=cx.dinero(gasto)), gasto=gasto / gasto_total,
                         etiqueta=gettext("%(segmento)s (%(dimension)s)", segmento=segmento, dimension=nombre_dim))
            salida.append(cx.rec("segmento_caro", "media", titulo, que_hacer, por_que,
                                 impacto=cx.impacto(gasto / DIAS_MES), claves=[f"{dimension}:{clave}"],
                                 enlace=administrador.enlace_cuenta(cx.act), fila=fila))
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
    a, fr, _ = dependientes[0]
    fila = _fila(ngettext("%(n)s conjunto", "%(n)s conjuntos", n, n=_num(n)),
                 gettext("«%(anuncio)s» lleva el %(pct)s %% de su conjunto",
                         anuncio=_una_linea(a.get("nombre")) or str(a.get("ad_id")), pct=_pct(fr)))
    return [cx.rec("concentracion", "baja", titulo, que_hacer, por_que, objetos, fila=fila)]


_REGLAS = (_cuenta_estado, _cuenta_roas_bajo, _aprendizaje_limitado, _perdedores_gastando, _anuncios_con_problemas,
           _conjuntos_con_problemas, _escalar, _fatiga, _segmento_caro, _concentracion)


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
    problema = _por_cuenta(o for o in entrada.get("conjuntos_problema") or () if o.get("objeto_id")
                           and o.get("nivel", "conjunto") == "conjunto" and o.get("estado") in ESTADOS_PROBLEMA)
    conj7 = {str(k): v for k, v in (entrada.get("conjuntos_7") or {}).items()}
    frecuencia = {str(k): v for k, v in (entrada.get("frecuencia_7") or {}).items()}
    salida = []
    for c in entrada.get("cuentas") or ():
        act = c.get("ad_account_id")
        totales_30 = t30.get(act) or {}
        if not act or _f(totales_30.get("gasto")) <= 0:
            continue    # sin datos en el período: ninguna regla
        cx = _Cuenta(c, t7.get(act) or {}, totales_30, objetos.get(act, []), conj7, anuncios.get(act, []),
                     frecuencia, desgloses.get(act, []), problema.get(act, []))
        for regla in _REGLAS:
            salida.extend(regla(cx))
    salida.sort(key=_orden)
    return salida


# ---------------------------------------------------------------- el Diagnóstico agrupado ---

def _titulo_grupo(tipo, n):
    """El título de un bloque en plural: `n` son sus cuentas (o sus filas en `escalar` y `segmento_caro`, que tienen
    varias por cuenta)."""
    if tipo == "cuenta_estado":
        return ngettext("%(n)s cuenta inactiva o cerca de su tope de gasto",
                        "%(n)s cuentas inactivas o cerca de su tope de gasto", n, n=_num(n))
    if tipo == "cuenta_roas_bajo":
        return ngettext("%(n)s cuenta vende menos de lo que gasta", "%(n)s cuentas venden menos de lo que gastan", n,
                        n=_num(n))
    if tipo == "aprendizaje_limitado":
        return ngettext("Aprendizaje limitado en %(n)s cuenta", "Aprendizaje limitado en %(n)s cuentas", n, n=_num(n))
    if tipo == "perdedores_gastando":
        return ngettext("Perdedores que siguen gastando en %(n)s cuenta",
                        "Perdedores que siguen gastando en %(n)s cuentas", n, n=_num(n))
    if tipo == "anuncios_con_problemas":
        return ngettext("Anuncios que Meta frena en %(n)s cuenta", "Anuncios que Meta frena en %(n)s cuentas", n,
                        n=_num(n))
    if tipo == "conjuntos_con_problemas":
        return ngettext("Conjuntos que Meta frena en %(n)s cuenta", "Conjuntos que Meta frena en %(n)s cuentas", n,
                        n=_num(n))
    if tipo == "escalar":
        return ngettext("%(n)s presupuesto listo para subir", "%(n)s presupuestos listos para subir", n, n=_num(n))
    if tipo == "fatiga":
        return ngettext("Anuncios que funcionan y se cansan en %(n)s cuenta",
                        "Anuncios que funcionan y se cansan en %(n)s cuentas", n, n=_num(n))
    if tipo == "segmento_caro":
        return ngettext("%(n)s segmento caro", "%(n)s segmentos caros", n, n=_num(n))
    return ngettext("Conjuntos que dependen de un solo anuncio en %(n)s cuenta",
                    "Conjuntos que dependen de un solo anuncio en %(n)s cuentas", n, n=_num(n))


def _impacto_total(recs):
    """Lo que está en juego por día en todo el bloque, solo si sus montos están en UNA moneda (en «Todas» con monedas
    distintas no se suman: cada fila dice lo suyo)."""
    con = [r["impacto"] for r in recs if r.get("impacto")]
    monedas = {i["moneda"] for i in con}
    if not con or len(monedas) != 1:
        return None
    return _impacto(sum(i["monto"] for i in con), monedas.pop())


def agrupar(recs):
    """Las recomendaciones de `calcular` en bloques, uno por tipo (pedido de Daniel 2026-10-13: el mismo consejo se
    repetía en una tarjeta por cuenta y las cifras quedaban enterradas en la prosa). Cada bloque: {"tipo", "nivel" (el
    más alto de sus filas), "mixto" (sus filas no tienen todas el mismo nivel), "titulo", "consejo", "recs" (en el
    orden de `calcular`), "impacto" (`_impacto_total`), "cab_etiqueta", "cab_cifra", "cab_gasto" (None si el tipo no
    mide parte del gasto), "con_gasto", "con_impacto"}. Orden: nivel, lo que está en juego (nominal entre monedas,
    como `_orden`) y el orden de `TIPOS`. PURA: no cambia ni copia las recomendaciones."""
    por_tipo = {}
    for r in recs or ():
        por_tipo.setdefault(r["tipo"], []).append(r)
    grupos = []
    for tipo, filas in por_tipo.items():
        niveles = {r["nivel"] for r in filas}
        nivel = min(niveles, key=NIVELES.index)
        n = len(filas) if tipo in ("escalar", "segmento_caro") else len({r["cuenta"] for r in filas})
        consejo = CONSEJOS.get(tipo)
        etiqueta = CABECERA_ETIQUETA.get(tipo, CABECERA_CUENTA)
        cifra = CABECERA_CIFRA.get(tipo)
        gasto = CABECERA_GASTO.get(tipo)
        montos = [r["impacto"]["monto"] for r in filas if r.get("impacto")]
        grupos.append({
            "tipo": tipo, "nivel": nivel, "mixto": len(niveles) > 1, "titulo": _titulo_grupo(tipo, n),
            "consejo": gettext(consejo, minimo=_roas(CUENTA_ROAS_MIN), meta=_num(COMPRAS_SEMANA_POR_CONJUNTO),
                               pct=_pct(ESCALAR_SUBIDA)) if consejo else None,
            "recs": filas, "impacto": _impacto_total(filas),
            "cab_etiqueta": gettext(etiqueta), "cab_cifra": gettext(cifra) if cifra else "",
            "cab_gasto": gettext(gasto) if gasto else None,
            "con_gasto": any((r.get("fila") or {}).get("gasto") for r in filas),
            "con_impacto": bool(montos),
            "_orden": (NIVELES.index(nivel), (0, -sum(montos)) if montos else (1, 0),
                       TIPOS.index(tipo) if tipo in TIPOS else len(TIPOS)),
        })
    grupos.sort(key=lambda g: g["_orden"])
    for g in grupos:
        del g["_orden"]
    return grupos

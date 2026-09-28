"""Diagnóstico de una pieza perdedora (doctrina, bloque 4; spec
`docs/superpowers/specs/2026-09-28-doctrina-bloque-4-cerrar-el-ciclo-design.md` §3).

Dos capas, como el revisor: `pistas(snapshots, reglas, contexto)` saca de los
números lo que se puede saber sin pagar (pura), y `diagnosticar(...)` le pide a
Claude, con la rebanada «diagnosticar» (la lista de Theriot), las causas, el
siguiente paso y una frase de aprendizaje. Nunca bloquea el veredicto: informa
al rescate y a la persona."""
import json

from flask_babel import gettext

import doctrina
import idiomas

VERSION = 1
MAX_TOKENS = 4000
# La llamada corre dentro del worker, entre la pausa y el rescate: no puede
# quedarse minutos colgada (el cliente por defecto espera 600 s y reintenta 2 veces).
TIMEOUT_S = 120
MAX_DETALLE = 300
FRECUENCIA_REPETICION = 3.0


class ErrorDiagnostico(RuntimeError):
    """Claude no respondió algo usable. `tokens_entrada`/`tokens_salida`
    traen lo ya pagado (0 si no se llamó)."""
    def __init__(self, mensaje, tokens_entrada=0, tokens_salida=0):
        super().__init__(mensaje)
        self.tokens_entrada, self.tokens_salida = tokens_entrada, tokens_salida


INSTRUCCIONES = """Diagnostica UNA pieza que el motor de pruebas marcó como perdedora, con la lista de causas de arriba.
Recibes los DATOS: el veredicto con sus números, las pistas que ya salieron de los números, el ángulo con el que se
escribió, la revisión de la doctrina si la hubo, el guion si lo hay y el producto. No ves el video.
Responde SOLO un JSON:
{"causas": [{"codigo": "<uno de: {causas}>", "detalle": "qué pasa, en una o dos frases", "evidencia": "el número, el
segundo o la frase que lo muestra"}],
 "siguiente": {"que": "<uno de: {siguientes}>", "porque": "una frase", "hipotesis": "qué debería pasar si se cambia eso"},
 "aprendizaje": "una frase para este proyecto: en este mercado, X no funcionó porque Y"}
Reglas: nombra solo causas con evidencia (la más probable primero); "siguiente" es UNA sola cosa: "gancho" (otro
arranque, mismo mensaje), "estructura" (otra forma de contar la misma promesa), "regenerar" (concepto nuevo), "oferta"
(cambiar oferta o urgencia), "landing" (la página, no el creativo), "pausar" (estación o posicionamiento: no gastar
más ahora). __IDIOMA__ simple, para el dueño de la marca, sin culpar a la plataforma sin evidencia."""


def _f(m, k):
    try:
        return float((m or {}).get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


def pistas(snapshots, reglas, contexto):
    """Lo que dicen los números, gratis: [{"codigo", "texto"}] en orden de
    peso. `reglas`: las efectivas del decisor (umbrales); `contexto`:
    {"es_imagen", "puerta"} (la puerta del veredicto: 2 = pasó tráfico y no
    ventas). Sin snapshots, []."""
    if not snapshots:
        return []
    u = snapshots[-1]
    r = reglas or {}
    c = contexto or {}
    salida = []
    thruplay, ctr, cpc, frecuencia = _f(u, "thruplay_rate"), _f(u, "ctr"), _f(u, "cpc"), _f(u, "frecuencia")
    thruplay_min, ctr_min, cpc_max = r.get("thruplay_min"), r.get("ctr_min"), r.get("cpc_max")
    es_imagen = bool(c.get("es_imagen"))
    retiene = es_imagen or thruplay_min is None or thruplay >= float(thruplay_min)
    if not es_imagen and thruplay_min is not None and thruplay < float(thruplay_min):
        salida.append({"codigo": "gancho", "texto": gettext(
            "Pocos pasan de los primeros segundos: ThruPlay %(t)s %% (mínimo %(min)s %%).",
            t=f"{thruplay * 100:.0f}", min=f"{float(thruplay_min) * 100:.0f}")})
    if retiene and ctr_min is not None and ctr < float(ctr_min):
        salida.append({"codigo": "sin_urgencia", "texto": gettext(
            "Miran pero no clican: CTR %(ctr)s %% (mínimo %(min)s %%).", ctr=f"{ctr:.2f}", min=f"{float(ctr_min):.2f}")})
    if int(c.get("puerta") or 0) == 2:
        salida.append({"codigo": "landing", "texto": gettext(
            "Pasó la puerta de tráfico y no vendió: la página o la oferta no continúan el anuncio.")})
    if frecuencia >= FRECUENCIA_REPETICION:
        salida.append({"codigo": "repeticion", "texto": gettext(
            "La misma gente ya lo vio %(n)s veces en promedio.", n=f"{frecuencia:.1f}")})
    if cpc_max is not None and cpc > float(cpc_max) and (ctr_min is None or ctr >= float(ctr_min)):
        salida.append({"codigo": "subasta_cara", "texto": gettext(
            "El clic sale caro con un CTR normal: CPC %(cpc)s (máximo %(max)s); es la subasta, no el creativo.",
            cpc=f"{cpc:.2f}", max=f"{float(cpc_max):.2f}")})
    return salida


def _linea(texto, tope=MAX_DETALLE):
    return " ".join(str(texto or "").split())[:tope]


def parsear(texto):
    """{"causas": [...], "siguiente": {...}, "aprendizaje"} desde la respuesta
    de Claude. Exige al menos una causa con código conocido y un
    `siguiente.que` válido; si no, `ErrorDiagnostico` (sin tokens)."""
    t = (texto or "").strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise ErrorDiagnostico(gettext("Claude no devolvió JSON."))
    try:
        data = json.loads(t[ini:fin + 1])
    except ValueError as e:
        raise ErrorDiagnostico(gettext("JSON inválido: %(error)s", error=e))
    if not isinstance(data, dict):
        raise ErrorDiagnostico(gettext("JSON inválido: %(error)s", error=gettext("no es un objeto")))
    # Toda forma rara (una lista donde va un texto, un número donde va la
    # lista) cuenta como «no sirvió», nunca como TypeError: lo pagado se
    # registra igual (regla 1).
    causas = []
    crudas = data.get("causas")
    for c in (crudas if isinstance(crudas, list) else []):
        codigo = c.get("codigo") if isinstance(c, dict) else None
        if isinstance(codigo, str) and codigo in doctrina.CAUSAS_NOMBRE and not any(x["codigo"] == codigo for x in causas):
            causas.append({"codigo": codigo, "detalle": _linea(c.get("detalle")),
                           "evidencia": _linea(c.get("evidencia"), 200)})
    if not causas:
        raise ErrorDiagnostico(gettext("Claude no nombró ninguna causa conocida."))
    sig = data.get("siguiente") if isinstance(data.get("siguiente"), dict) else {}
    que = sig.get("que")
    if not isinstance(que, str) or que not in doctrina.SIGUIENTES_PASOS:
        raise ErrorDiagnostico(gettext("«siguiente» trae un paso que no existe: %(que)s.", que=repr(que)))
    return {"causas": causas,
            "siguiente": {"que": sig["que"], "porque": _linea(sig.get("porque")), "hipotesis": _linea(sig.get("hipotesis"))},
            "aprendizaje": _linea(data.get("aprendizaje"))}


def _sin_cierre(texto):
    return str(texto or "").replace("</datos>", "")


def texto_para_diagnostico(pz, veredicto, pistas_, extras):
    """Los DATOS (información, no instrucciones). `extras`: {"guion", "producto",
    "revision", "dias_transcurridos"}."""
    n = veredicto.get("numeros") or {}
    lineas = ["<datos>", f"PAÍS: {pz.get('pais') or '?'} · PIEZA: {_sin_cierre(pz.get('nombre'))} "
              f"({'imagen' if pz.get('es_imagen') else 'video'})",
              f"VEREDICTO DEL MOTOR: {_sin_cierre(veredicto.get('motivo'))}",
              "NÚMEROS: " + ", ".join(f"{k} {v}" for k, v in n.items()) if n else "NÚMEROS: (sin números)",
              f"DÍAS CORRIDOS: {extras.get('dias_transcurridos') or '?'}",
              "PISTAS DE LOS NÚMEROS: " + ("; ".join(f"{p['codigo']}: {p['texto']}" for p in pistas_) if pistas_
                                           else "ninguna")]
    angulo = pz.get("angulo") if isinstance(pz.get("angulo"), dict) else None
    lineas.append("ÁNGULO:\n" + (_sin_cierre(doctrina.angulo_a_texto(angulo)) if angulo else "(sin ángulo)"))
    rev = extras.get("revision") if isinstance(extras.get("revision"), dict) else None
    if rev and rev.get("puntos"):
        mejorar = [p for p in rev["puntos"] if isinstance(p, dict) and p.get("estado") == "mejorar"]
        lineas.append("REVISIÓN DE LA DOCTRINA (puntos por mejorar): " + ("; ".join(
            f"punto {p.get('n')}: {_sin_cierre(p.get('detalle'))}" for p in mejorar) if mejorar else "ninguno"))
    guion = extras.get("guion") if isinstance(extras.get("guion"), dict) else None
    bloques = [b for b in (guion or {}).get("bloques") or [] if isinstance(b, dict)]
    if bloques:
        lineas.append("GUION (voz por bloque): " + " / ".join(
            f"{b.get('rol')}: {_sin_cierre(b.get('texto_voz') or b.get('texto_pantalla') or '')}" for b in bloques))
    producto = extras.get("producto") or {}
    if producto:
        lineas.append("PRODUCTO: " + _sin_cierre(json.dumps(producto, ensure_ascii=False)))
    lineas.append("</datos>")
    return "\n".join(lineas)


def _instrucciones(idioma=None):
    """Las instrucciones del sitio con el nombre del idioma del proyecto
    (spec 2026-09-26 §B4); sin idioma, el DEFECTO de `idiomas` (español en las
    pruebas, que lo fijan en conftest)."""
    nombre = idiomas.nombre_para_claude(idioma)
    return INSTRUCCIONES.replace("{causas}", ", ".join(c for c, _ in doctrina.CAUSAS_PERDIDA)) \
        .replace("{siguientes}", ", ".join(doctrina.SIGUIENTES_PASOS)).replace("__IDIOMA__", nombre)


def diagnosticar(pz, veredicto, snapshots, reglas, extras=None, idioma=None):
    """La llamada a Claude: (diagnostico, tokens_entrada, tokens_salida).
    `extras` como en `texto_para_diagnostico`; `idioma`, el del proyecto
    (la orden de idioma rodea las instrucciones del sitio). Una corrección si
    la primera respuesta no sirve; si tampoco, `ErrorDiagnostico` con los
    tokens de las dos llamadas. Quien llama guarda y registra el gasto
    (tareas/experimentos)."""
    from sprints import analisis
    extras = extras or {}
    pistas_ = pistas(snapshots, reglas, {"es_imagen": pz.get("es_imagen"), "puerta": veredicto.get("puerta")})
    content = [{"type": "text", "text": texto_para_diagnostico(pz, veredicto, pistas_, extras)}]
    system = doctrina.bloque_system("diagnosticar", extra=_instrucciones(idioma), idioma=idioma)
    texto, ent, sal = analisis._llamar_contando(content, max_tokens=MAX_TOKENS, system=system,
                                                timeout=TIMEOUT_S, max_retries=1)
    try:
        d = parsear(texto)
    except Exception as primero:  # noqa: BLE001 — una forma rara también es «no sirvió»
        pedido = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({primero}). Responde de nuevo "
                                                    "SOLO el JSON pedido."}]
        try:
            texto, e2, s2 = analisis._llamar_contando(pedido, max_tokens=MAX_TOKENS, system=system,
                                                      timeout=TIMEOUT_S, max_retries=1)
        except Exception as falla:  # noqa: BLE001 — lo pagado en la primera llamada viaja con el error
            raise ErrorDiagnostico(str(falla)[:200] or gettext("La corrección falló."), ent, sal) from falla
        ent, sal = ent + e2, sal + s2
        try:
            d = parsear(texto)
        except Exception as segundo:  # noqa: BLE001 — con los tokens de las dos llamadas
            raise ErrorDiagnostico(str(segundo)[:200], ent, sal)
    d["pistas"] = pistas_
    return d, ent, sal


def causa_principal(diagnostico):
    causas = (diagnostico or {}).get("causas") or []
    return causas[0]["codigo"] if causas and isinstance(causas[0], dict) else None


def decision_rescate(diagnostico):
    """Qué le dice el diagnóstico al rescate: {"salto": 2|3|None,
    "solo_proponer": bool, "motivo": str}. Sin diagnóstico (o con error), el
    rescate sigue como siempre."""
    if not isinstance(diagnostico, dict) or diagnostico.get("error") or not diagnostico.get("siguiente"):
        return {"salto": None, "solo_proponer": False, "motivo": ""}
    sig = diagnostico["siguiente"]
    que = sig.get("que")
    causas = ", ".join(idiomas.traducir(doctrina.CAUSAS_NOMBRE.get(c.get("codigo"), c.get("codigo")))
                       for c in diagnostico.get("causas") or [] if isinstance(c, dict))
    motivo = gettext("Diagnóstico: %(causas)s — siguiente: %(que)s", causas=causas or gettext("sin causa clara"),
                     que=idiomas.traducir(doctrina.SIGUIENTES_NOMBRE.get(que, que)))
    if sig.get("porque"):
        motivo += f" ({sig['porque']})"
    salto = {"estructura": 2, "regenerar": 3}.get(que)
    principal = causa_principal(diagnostico)
    solo = que in ("oferta", "landing", "pausar") or principal in doctrina.CAUSAS_NO_CREATIVAS
    if solo:
        motivo += gettext(" — apunta a algo que no es el creativo: decide tú si rescatar")
    return {"salto": salto, "solo_proponer": solo, "motivo": motivo}

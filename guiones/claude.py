"""
Un solo punto para hablar con Claude desde el pipeline de Flow Plus: la
llamada real, el parseo del JSON y el registro del gasto. `llamar` es la
costura que las pruebas reemplazan; ningún paso importa anthropic directo.
"""
import json
import logging
import re
from contextlib import nullcontext
from uuid import uuid4

from flask_babel import gettext

import gastos
import idiomas
from nicho.avatares import costo_real, modelo_actual

log = logging.getLogger(__name__)
TIPO_GASTO = "guion_clips"


class RespuestaFallida(RuntimeError):
    """Claude contestó pero no sirve (cortada o rechazada); lleva los tokens que ya se cobraron."""
    tokens_entrada = 0
    tokens_salida = 0


def tokens_entrada_equivalentes(uso):
    """`input_tokens` más la caché de prompts (la doctrina va en el system con
    cache_control desde el bloque 4 §7): escribirla cuesta 1,25× y leerla 0,1×
    — igual que `sprints.analisis._llamar_contando`, para que el gasto no
    quede corto."""
    entrada = int(getattr(uso, "input_tokens", 0) or 0)
    escrita = int(getattr(uso, "cache_creation_input_tokens", 0) or 0)
    leida = int(getattr(uso, "cache_read_input_tokens", 0) or 0)
    return entrada + round(escrita * 1.25 + leida * 0.1)


def llamar(system, messages, max_tokens=8000, timeout=150):
    """(texto, tokens_entrada, tokens_salida). El mensaje de una `RespuestaFallida`
    sale en el idioma que `pedir_json` haya dejado activo (el de la pantalla
    dentro de una petición, el del proyecto sin petición)."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    api = anthropic.Anthropic(api_key=_api_key(), timeout=timeout, max_retries=0)
    # Con streaming: el pensamiento adaptativo de claude-sonnet-5 gasta del mismo
    # tope que la respuesta, así que armar clips necesita topes grandes (48 000),
    # y el SDK no acepta topes así sin stream; además `timeout` pasa a contar
    # entre fragmentos y no para la respuesta entera.
    with api.messages.stream(model=MODEL, max_tokens=max_tokens, system=system, messages=messages) as s:
        resp = s.get_final_message()
    uso = getattr(resp, "usage", None)
    entrada = tokens_entrada_equivalentes(uso)
    salida = int(getattr(uso, "output_tokens", 0) or 0)
    if resp.stop_reason in ("refusal", "max_tokens"):
        mensaje = (gettext("Claude no quiso responder esa solicitud.") if resp.stop_reason == "refusal"
                  else gettext("La respuesta de Claude salió incompleta. Intenta con un guion más corto."))
        e = RespuestaFallida(mensaje)
        e.tokens_entrada, e.tokens_salida = entrada, salida
        raise e
    return "".join(b.text for b in resp.content if b.type == "text").strip(), entrada, salida


def limpio(texto, etiqueta):
    """Texto ajeno sin el cierre de su bloque, para que no escape del delimitador."""
    return re.sub(re.escape(f"</{etiqueta}>"), "", texto or "", flags=re.I)


def parsear_json(texto):
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        data = json.loads(t)
    except ValueError:
        ini, fin = t.find("{"), t.rfind("}")
        if ini < 0 or fin <= ini:
            raise ValueError("sin JSON") from None
        data = json.loads(t[ini:fin + 1])
    if not isinstance(data, dict):
        raise ValueError("no es un objeto JSON")
    return data


def _registrar(cliente, paso, ref_id, entrada, salida, detalle):
    usd = costo_real(entrada, salida)
    gastos.registrar_seguro(cliente, TIPO_GASTO, usd, f"guiones:{paso}:{ref_id}:{uuid4().hex[:8]}",
                            detalle=detalle, proveedor="anthropic",
                            extra={"tokens_entrada": entrada, "tokens_salida": salida, "modelo": modelo_actual()})
    return usd


def pedir_json(cliente, paso, ref_id, system, messages, detalle, llamar_fn=None, max_tokens=8000, timeout=150):
    """(data | None, usd, error | None). Nunca lanza: corre en un hilo, y lo
    que se pagó queda registrado aunque la respuesta no sirva.

    Idioma de los mensajes de error que llegan a la persona: dentro de una
    petición (spec §B4, «pantallas = la persona») `gettext` ya resuelve con
    `idiomas.de_peticion()` — el locale_selector de la app —, así que no hay
    que forzar nada. Este paso corre casi siempre SIN petición, en el hilo del
    worker (`trabajos.iniciar` no empuja ningún contexto de Flask): ahí no hay
    locale de quien mira la pantalla que leer, así que se fuerza el idioma del
    proyecto con `idiomas.en_idioma` — la mejor señal disponible."""
    from flask import has_request_context
    fn = llamar_fn or llamar
    forzar_idioma = nullcontext() if has_request_context() else idiomas.en_idioma(idiomas.de_proyecto(cliente))
    with forzar_idioma:
        try:
            texto, ent, sal = fn(system, messages, max_tokens, timeout)
        except Exception as e:  # noqa: BLE001 — ver docstring
            ent, sal = int(getattr(e, "tokens_entrada", 0) or 0), int(getattr(e, "tokens_salida", 0) or 0)
            usd = _registrar(cliente, paso, ref_id, ent, sal, f"{detalle} · sin respuesta útil") if (ent or sal) else 0.0
            log.warning("guiones: Claude falló en %s %s (%s)", paso, ref_id, type(e).__name__)
            if isinstance(e, RespuestaFallida):
                return None, usd, str(e)
            return None, usd, gettext("No se pudo consultar a Claude (%(tipo)s). Vuelve a intentarlo.",
                                      tipo=type(e).__name__)
        try:
            data = parsear_json(texto)
        except ValueError:
            usd = _registrar(cliente, paso, ref_id, ent, sal, f"{detalle} · respuesta inválida")
            return None, usd, gettext("Claude no respondió en el formato esperado. Vuelve a intentarlo.")
        return data, _registrar(cliente, paso, ref_id, ent, sal, detalle), None

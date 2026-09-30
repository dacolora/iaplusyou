"""Barridos por palabra: SIEMPRE en inglés (2026-09-27, pedido del usuario).

Un barrido de «DOLOR DE PIES» con el idioma en Inglés trajo pasteles
(«American pies»): la palabra y el idioma de los anuncios tienen que
coincidir, y el mercado en inglés es el más grande. Así que lo que la
persona escriba —en español o en inglés— se traduce al inglés con una
llamada corta a Claude (centavos, queda en Gasto) y se buscan anuncios en
inglés; la palabra original se guarda para mostrar «dolor de pies» →
«foot pain» en «Mis barridos». Si no se puede traducir, el barrido no se
lanza: buscar la palabra sin traducir en inglés trae ruido pagado."""
from uuid import uuid4

from flask_babel import gettext

import gastos

MAX_TOKENS = 60
PROMPT = ("Translate this ad-search keyword into the natural English an advertiser would use in a Facebook ad "
          "(keep it short, no quotes, no explanation). If it is already English, return it unchanged.\n\n"
          "Keyword: {palabra}")


class TraduccionInvalida(RuntimeError):
    """El mensaje va tal cual a la persona (se lanza en la ruta: idioma de quien mira)."""


def _llamar(texto):
    """Una llamada de texto a Claude; devuelve (texto, tokens_entrada, tokens_salida)."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": texto}])
    uso = getattr(resp, "usage", None)
    entrada = int(getattr(uso, "input_tokens", 0) or 0)
    salida = int(getattr(uso, "output_tokens", 0) or 0)
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise TraduccionInvalida(gettext("No pude traducir la palabra al inglés; escríbela de otra forma."))
    return "".join(b.text for b in resp.content if b.type == "text"), entrada, salida


def al_ingles(palabra):
    """(palabra en inglés, tokens_entrada, tokens_salida)."""
    texto, entrada, salida = _llamar(PROMPT.format(palabra=palabra))
    limpio = ((texto or "").strip().splitlines() or [""])[0].strip().strip("\"'«»“”").strip()
    if not limpio:
        raise TraduccionInvalida(gettext("No pude traducir la palabra al inglés; escríbela de otra forma."))
    return limpio[:120], entrada, salida


def preparar_consulta(consulta, cliente):
    """La consulta de un barrido lista para lanzar: en modo palabra, `palabra`
    traducida al inglés, `palabra_original` la escrita e `idioma` en, con el
    gasto registrado (bajo `_creatv` si es un barrido global). Lanza
    TraduccionInvalida si no se pudo traducir."""
    if consulta.get("modo") != "palabra":
        return consulta
    from nicho.avatares import costo_real
    original = consulta["palabra"]
    try:
        ingles, entrada, salida = al_ingles(original)
    except TraduccionInvalida:
        raise
    except Exception as e:
        raise TraduccionInvalida(gettext("No pude traducir la palabra al inglés; intenta de nuevo en un momento.")) from e
    gastos.registrar_seguro(cliente or "_creatv", "otro", costo_real(entrada, salida),
                            f"referentes:traducir:{uuid4().hex[:12]}",
                            detalle=f"Traducir «{original}» → «{ingles}»", proveedor="anthropic")
    return {**consulta, "palabra_original": original, "palabra": ingles, "idioma": "en"}

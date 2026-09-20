"""
Generación de avatares con Claude (spec §4): dos pasadas — núcleos por deseo
y, por cada núcleo, sub-avatares con los campos de las dos plantillas del
cliente (doc "Desire-Based Core Avatar" y hoja "Personas") — con citas
verificadas contra el comentario real. `_llamar` es la única función que
toca la API: las pruebas la reemplazan. El modelo es el del proyecto
(`generador_prompts.MODEL`); los precios de PRECIOS_USD_POR_MILLON están
verificados contra la referencia de Anthropic (tabla del 2026-06-24).
"""
import json
import math
import re

import marca
import proyectos
from nicho import datos
from nicho.fuentes.base import MIN_CITA

MIN_COMENTARIOS = 20
MAX_COMENTARIOS = 600
MAX_CARACTERES = 250_000
MAX_NUCLEOS = 5
MAX_SUBS_POR_NUCLEO = 4
TOKENS_POR_CARACTER = 1 / 3.5          # conservador para español
TOKENS_PROMPT = 800                    # instrucciones por llamada
TOKENS_SALIDA_ESTIMADO_NUCLEOS = 1500  # lo que suele ocupar la pasada 1
TOKENS_SALIDA_ESTIMADO_SUBS = 3000     # por núcleo, pasada 2
MAX_TOKENS_NUCLEOS = 4000              # tope de salida real (no es costo: es el corte)
MAX_TOKENS_SUBS = 8000

# USD por millón de tokens (entrada, salida). Referencia de Anthropic, 2026-06-24.
PRECIOS_USD_POR_MILLON = {
    "claude-sonnet-5": {"entrada": 2.0, "salida": 10.0},
    "claude-opus-5": {"entrada": 5.0, "salida": 25.0},
    "claude-haiku-4-5": {"entrada": 1.0, "salida": 5.0},
}
IDIOMAS = {"es": "español", "en": "inglés", "pt": "portugués", "sv": "sueco", "fr": "francés", "de": "alemán",
           "it": "italiano"}


class AnalisisInvalido(RuntimeError):
    """Claude no devolvió lo pedido (JSON roto, claves faltantes, corte)."""


def modelo_actual():
    from generador_prompts import MODEL
    return MODEL


# ----------------------------------------------------------- selección ---

def seleccionar(comentarios, max_n=MAX_COMENTARIOS, max_caracteres=MAX_CARACTERES):
    """Los que entran a Claude (spec §4.1): fuera los excluidos; dentro de
    cada fuente por puntuación desc, fecha desc, id asc; se toman en ronda
    entre fuentes hasta llenar el primer tope. Un comentario que no cabe en
    los caracteres se salta (no corta la ronda)."""
    por_fuente = {}
    for c in comentarios or []:
        if c.get("excluido"):
            continue
        por_fuente.setdefault(c.get("fuente") or "texto", []).append(c)
    for lista in por_fuente.values():
        # tres ordenamientos estables = (puntuación desc, fecha desc, id asc)
        lista.sort(key=lambda c: int(c.get("id") or 0))
        lista.sort(key=lambda c: c.get("fecha") or "", reverse=True)
        lista.sort(key=lambda c: -(c.get("puntuacion") or 0))
    colas = [iter(l) for _, l in sorted(por_fuente.items())]
    salida, caracteres = [], 0
    while colas and len(salida) < max_n:
        siguientes = []
        for it in colas:
            if len(salida) >= max_n:
                break
            c = next(it, None)
            if c is None:
                continue
            siguientes.append(it)
            largo = len(c.get("texto") or "")
            if caracteres + largo > max_caracteres:
                continue
            salida.append(c)
            caracteres += largo
        colas = siguientes
    return salida


# -------------------------------------------------------------- costo ---

def _precios(modelo):
    """(precios, es_referencia). Modelo desconocido -> el más caro de la tabla."""
    if modelo in PRECIOS_USD_POR_MILLON:
        return PRECIOS_USD_POR_MILLON[modelo], False
    caro = max(PRECIOS_USD_POR_MILLON.values(), key=lambda p: p["entrada"] + p["salida"])
    return caro, True


def costo_real(tokens_entrada, tokens_salida, modelo=None):
    precios, _ = _precios(modelo or modelo_actual())
    return round((tokens_entrada * precios["entrada"] + tokens_salida * precios["salida"]) / 1e6, 4)


def estimar_costo(comentarios, modelo=None):
    """Precio ANTES de gastar (spec §4.4): la entrada se cuenta dos veces
    (pasada 1 y repartida en la pasada 2) más el prompt por llamada; la
    salida es lo esperado, con MAX_NUCLEOS en la pasada 2. Redondeado hacia
    arriba al centavo."""
    modelo = modelo or modelo_actual()
    sel = seleccionar(comentarios)
    caracteres = sum(len(c.get("texto") or "") for c in sel)
    tokens_texto = int(caracteres * TOKENS_POR_CARACTER)
    entrada = tokens_texto * 2 + TOKENS_PROMPT * (1 + MAX_NUCLEOS)
    salida = TOKENS_SALIDA_ESTIMADO_NUCLEOS + TOKENS_SALIDA_ESTIMADO_SUBS * MAX_NUCLEOS
    precios, referencia = _precios(modelo)
    usd = math.ceil((entrada * precios["entrada"] + salida * precios["salida"]) / 1e6 * 100) / 100
    return {"comentarios": len(sel), "tokens_entrada": entrada, "tokens_salida": salida, "usd": usd,
            "referencia": referencia, "modelo": modelo, "suficientes": len(sel) >= MIN_COMENTARIOS}

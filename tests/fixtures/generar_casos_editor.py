"""Tablas de paridad Python↔navegador del editor (capa 3). Python es la
referencia: este script escribe lo que Python responde hoy y las pruebas de
Node (tests/js/*.test.mjs) exigen lo mismo al navegador.

    venv/bin/python3 tests/fixtures/generar_casos_editor.py

tests/test_editor_js.py::test_casos_del_editor_al_dia falla si un archivo
quedó distinto de lo que Python produce: se regenera con este script y se
revisa el cambio en el navegador."""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(AQUI)))

from final_edition import documento, tipos  # noqa: E402

VALORES_PRECIO = (89900, 24.99, 1234567.891, 499.5, 0, 0.125, 1.005, 2.675, 19.995, 1500000, -5.5, -1234.5)


def casos_precios():
    return [{"valor": v, "pais": pais, "esperado": tipos.formatear_precio(v, pais)}
            for pais in sorted(tipos.PAISES) for v in VALORES_PRECIO]


def _doc_resolver():
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [
        {"id": "v0", "inicio_ms": 0, "duracion_ms": 4000, "material_id": 1,
         "recorte": {"desde_ms": 0, "hasta_ms": 4000},
         # capa 5b: una transición "solape" (D9) junta v0 con la foto que
         # sigue; `resolver` la copia tal cual, no la interpreta.
         "transicion": {"tipo": "fundido", "duracion_ms": 500, "modo": "solape"}},
        # capa 5b: una foto (D1) con encuadre (D4) en la principal.
        {"id": "foto1", "inicio_ms": 4000, "duracion_ms": 3000, "material_id": 6, "foto": True,
         "encuadre": {"modo": "ajustar", "zoom": 1.2, "x": 0.3, "y": 0.7}},
    ]
    doc["pistas"].append({"id": "p_texto", "tipo": "texto", "clips": [
        {"id": "t_hook", "inicio_ms": 0, "duracion_ms": 2000, "texto": {"variable": "hook"}, "estilo": {"fuente": "SpaceGrotesk-Bold"}},
        {"id": "t_precio", "inicio_ms": 1000, "duracion_ms": 2000, "texto": {"variable": "precio"}, "estilo": {"fuente": "Inter-Bold"}},
        {"id": "t_fijo", "inicio_ms": 3000, "duracion_ms": 1000, "texto": {"literal": "Compra ya"}, "estilo": {"fuente": "Inter-Bold"}},
    ]})
    doc["pistas"].append({"id": "p_voz", "tipo": "audio", "clips": [
        {"id": "voz_hook", "inicio_ms": 0, "duracion_ms": 1800, "material_id": 2, "rol_audio": "voz", "bloque": "hook",
         "recorte": {"desde_ms": 0, "hasta_ms": 1800},
         "por_destino": {"es_CO": {"material_id": 2, "duracion_ms": 1800}, "es": {"material_id": 2, "duracion_ms": 1800},
                         "en_US": {"material_id": 5, "duracion_ms": 1500}, "pt_BR": None}},
        {"id": "sonido", "inicio_ms": 0, "duracion_ms": 4000, "material_id": 1, "rol_audio": "sonido",
         "recorte": {"desde_ms": 0, "hasta_ms": 4000}},
        # D10 (capa 5a): un audio marcado para OTRO idioma no suena fuera de él.
        {"id": "voz_en", "inicio_ms": 0, "duracion_ms": 1500, "material_id": 7, "rol_audio": "voz", "idioma": "en",
         "recorte": {"desde_ms": 0, "hasta_ms": 1500}},
    ]})
    doc["variables"] = {"textos": {"hook": {"es_CO": "Tu piel, en 7 días", "es": "Tu piel en 7 días",
                                            "en_US": "Your skin in 7 days", "pt": "Sua pele em 7 dias"}},
                        "voz": {}, "precios": {"es_CO": 89900, "es_MX": 499.5, "en_US": 24.99}}
    # visibles: false (capa 5a, D1): apaga los subtítulos en TODO destino,
    # aunque haya palabras guardadas para él.
    doc["subtitulos"] = {"visibles": False,
                         "palabras": {"es_CO": [{"t_ms": 0, "dur_ms": 400, "texto": "Tu"}],
                                      "es": [{"t_ms": 0, "dur_ms": 500, "texto": "Tu"}]}}
    doc["pngs"] = {"t_precio": 9}
    return documento.validar(doc)


DESTINOS = (("es", "CO"), ("es", "MX"), ("es", "AR"), ("en", "US"), ("pt", "BR"), ("en", "GB"))


def casos_resolver():
    doc = _doc_resolver()
    casos = []
    for idioma, pais in DESTINOS:
        try:
            casos.append({"idioma": idioma, "pais": pais, "esperado": documento.resolver(doc, idioma, pais)})
        except documento.DocumentoInvalido as e:
            casos.append({"idioma": idioma, "pais": pais, "error": type(e).__name__})
    return {"doc": doc, "casos": casos}


class _MedidorFalso:
    """10 px por carácter: el mismo medidor en Python y en Node."""
    def textlength(self, texto, font=None):
        return 10 * len(texto)


TEXTOS_AJUSTE = ("Tu piel, en 7 días", "Una frase bastante más larga que el ancho disponible",
                 "Palabraenormesinespacios corta", "Dos\nPárrafos aquí", "", "   espacios   raros  ",
                 "Linea\n\ncon vacía")


def casos_ajuste():
    from final_edition import rasterizar
    return [{"texto": t, "ancho_max_px": ancho, "esperado": rasterizar.ajustar_lineas(_MedidorFalso(), t, None, ancho)}
            for t in TEXTOS_AJUSTE for ancho in (None, 60, 100, 150)]


PALABRAS_VENTANAS = (
    [{"t_ms": 0, "dur_ms": 400, "texto": "Hola"}, {"t_ms": 400, "dur_ms": 500, "texto": "mundo"}],
    [{"t_ms": i * 300, "dur_ms": 280, "texto": f"p{i}"} for i in range(9)],
    [{"t_ms": 0, "dur_ms": 300, "texto": "antes"}, {"t_ms": 1000, "dur_ms": 300, "texto": "después"}],
    [{"t_ms": 0, "dur_ms": 900, "texto": "larga"}, {"t_ms": 900, "dur_ms": 950, "texto": "más"}],
    [{"t_ms": 500, "dur_ms": 200, "texto": "b"}, {"t_ms": 0, "dur_ms": 200, "texto": "{a}"}],
    [{"t_ms": 0, "dur_ms": 200, "texto": "  con   espacios "}],
    [],
)


def casos_ventanas():
    from final_edition.motor import subtitulos
    casos = [{"palabras": p, "esperado": subtitulos.ventanas(p)} for p in PALABRAS_VENTANAS]
    # D7: casos con `max_caracteres` (los tres parámetros van EXPLÍCITOS
    # cuando no son los de por defecto, para que quien los consuma sepa con
    # qué llamar a `ventanas`).
    extra_parametros = (
        [{"t_ms": 0, "dur_ms": 300, "texto": "Hola"}, {"t_ms": 300, "dur_ms": 300, "texto": "mundo"},
         {"t_ms": 600, "dur_ms": 300, "texto": "extraordinario"}],
        [{"t_ms": 0, "dur_ms": 300, "texto": "a" * 30}],
        # revisión final (m3): la barra invertida pasa a «/» (libass la leería
        # como una orden) y el largo se cuenta en caracteres, no en unidades de
        # UTF-16: «𝔸𝔹𝔺𝔻𝔼𝔽» son 6 letras (12 unidades) — tres caben en 22.
        [{"t_ms": 0, "dur_ms": 300, "texto": "a\\b"}, {"t_ms": 300, "dur_ms": 300, "texto": "c\\\\d"}],
        [{"t_ms": 0, "dur_ms": 300, "texto": "\U0001D538\U0001D539\U0001D53A\U0001D53B\U0001D53C\U0001D53D"},
         {"t_ms": 300, "dur_ms": 300, "texto": "\U0001D538\U0001D539\U0001D53A\U0001D53B\U0001D53C\U0001D53D"},
         {"t_ms": 600, "dur_ms": 300, "texto": "\U0001D538\U0001D539\U0001D53A\U0001D53B\U0001D53C\U0001D53D"}],
        [{"t_ms": 0, "dur_ms": 300, "texto": "acción"}, {"t_ms": 300, "dur_ms": 300, "texto": "ñandú"},
         {"t_ms": 600, "dur_ms": 300, "texto": "pingüino"}, {"t_ms": 900, "dur_ms": 300, "texto": "ok"}],
    )
    for p in extra_parametros:
        casos.append({"palabras": p, "max_palabras": 4, "max_ms": 1800, "max_caracteres": 22,
                     "esperado": subtitulos.ventanas(p, max_palabras=4, max_ms=1800, max_caracteres=22)})
    return casos


# --- eventos/estilos (D7, Tarea 2): la Tarea 3 escribe el espejo
# static/editor/subtitulos.js (`eventos`/`estiloEfectivo`) contra esta tabla.
_EV_PAL = [{"t_ms": 0, "dur_ms": 400, "texto": "Hola"}, {"t_ms": 400, "dur_ms": 500, "texto": "mundo"},
          {"t_ms": 900, "dur_ms": 300, "texto": "esto"}, {"t_ms": 1200, "dur_ms": 300, "texto": "es"},
          {"t_ms": 1500, "dur_ms": 400, "texto": "una"}, {"t_ms": 3000, "dur_ms": 400, "texto": "prueba"}]


def _ev_sub(estilo_id, palabras, **extra):
    return {"estilo_id": estilo_id, "posicion": 0.78, "palabras": palabras, **extra}


def casos_eventos():
    from final_edition.motor import subtitulos as sub_mod
    casos = []

    def agregar(nombre, sub):
        casos.append({"nombre": nombre, "subtitulos": sub,
                     "esperado": {"estilo": sub_mod.estilo_efectivo(sub), "eventos": sub_mod.eventos(sub)}})

    agregar("karaoke por defecto: una palabra resaltada a la vez", _ev_sub("karaoke", _EV_PAL))
    agregar("caja: una línea por ventana, sin resaltar", _ev_sub("caja", _EV_PAL))
    agregar("minimal: tope de 5 palabras por línea",
           _ev_sub("minimal", [{"t_ms": i * 100, "dur_ms": 50, "texto": c} for i, c in enumerate("abcdef")]))
    agregar("palabra_grande: una palabra por línea, en mayúsculas, estirada", _ev_sub("palabra_grande", _EV_PAL))
    agregar("escala 0.6 achica el tamaño", _ev_sub("karaoke", _EV_PAL[:2], escala=0.6))
    agregar("escala 1.5 agranda el tamaño", _ev_sub("karaoke", _EV_PAL[:2], escala=1.5))
    agregar("resaltado propio del documento", _ev_sub("karaoke", _EV_PAL[:1], resaltado="#3DDC84"))
    agregar("caja no resalta aunque el documento pida un color", _ev_sub("caja", _EV_PAL[:1], resaltado="#3DDC84"))
    agregar("palabra más larga que el tope achica SU línea (palabra_grande)",
           _ev_sub("palabra_grande", [{"t_ms": 0, "dur_ms": 500, "texto": "extraordinariamente"}]))
    agregar("mayúsculas con tildes, eñe y la ß alemana",
           _ev_sub("palabra_grande", [{"t_ms": 0, "dur_ms": 300, "texto": "ñandú"},
                                       {"t_ms": 2000, "dur_ms": 300, "texto": "acción"},
                                       {"t_ms": 4000, "dur_ms": 300, "texto": "straße"}]))
    agregar("líneas que se solapan: la primera termina donde empieza la segunda",
           _ev_sub("palabra_grande", [{"t_ms": 0, "dur_ms": 1000, "texto": "Hola"},
                                       {"t_ms": 800, "dur_ms": 200, "texto": "mundo"}]))
    agregar("hueco de exactamente 600 ms: se estira hasta la siguiente",
           _ev_sub("palabra_grande", [{"t_ms": 0, "dur_ms": 300, "texto": "Hola"},
                                       {"t_ms": 900, "dur_ms": 200, "texto": "mundo"}]))
    agregar("hueco de 601 ms: no se estira",
           _ev_sub("palabra_grande", [{"t_ms": 0, "dur_ms": 300, "texto": "Hola"},
                                       {"t_ms": 901, "dur_ms": 200, "texto": "mundo"}]))
    agregar("sin palabras: sin eventos", _ev_sub("karaoke", []))
    agregar("estilo desconocido cae a karaoke", _ev_sub("inventado", _EV_PAL[:1]))
    # revisión final (I2): la caja de una línea achicada se achica con ella (\\bord)
    agregar("caja: línea más larga que el tope achica su tamaño y su margen",
           _ev_sub("caja", [{"t_ms": 0, "dur_ms": 500, "texto": "a" * 30}]))
    agregar("karaoke a escala 1.5: margen de la caja más grande", _ev_sub("karaoke", _EV_PAL[:1], escala=1.5))
    # revisión final (m3): barra invertida, tildes y letras fuera del plano básico
    agregar("barra invertida pasa a barra", _ev_sub("karaoke", [{"t_ms": 0, "dur_ms": 300, "texto": "a\\b"}]))
    agregar("el largo de la línea se cuenta en caracteres (plano astral)",
           _ev_sub("palabra_grande", [{"t_ms": 0, "dur_ms": 300,
                                       "texto": "\U0001D538\U0001D539\U0001D53A\U0001D53B\U0001D53C\U0001D53D\U0001D538\U0001D539"}]))
    return {"estilos": sub_mod.ESTILOS_ASS, "casos": casos}


# --- subtitulos_fuente (editor, capa 5a, D1-D4): la Tarea 3 escribe el espejo
# static/editor/subtitulos_fuente.js contra esta tabla.
def _sf_clip_video(id_, inicio_ms, duracion_ms, desde_ms, hasta_ms, material_id=1, velocidad=1.0):
    return {"id": id_, "inicio_ms": inicio_ms, "duracion_ms": duracion_ms, "material_id": material_id,
            "recorte": {"desde_ms": desde_ms, "hasta_ms": hasta_ms}, "velocidad": velocidad,
            "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
            "keyframes": [], "animacion": None, "transicion": None,
            "audio": {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}}


def _sf_clip_audio(id_, inicio_ms, duracion_ms, material_id, desde_ms=0, hasta_ms=None, rol_audio="voz", **extra):
    hasta_ms = duracion_ms if hasta_ms is None else hasta_ms
    base = {"id": id_, "inicio_ms": inicio_ms, "duracion_ms": duracion_ms, "material_id": material_id,
            "rol_audio": rol_audio, "recorte": {"desde_ms": desde_ms, "hasta_ms": hasta_ms}, "velocidad": 1.0,
            "audio": {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}}
    base.update(extra)
    return base


def _sf_pista(id_, tipo, clips):
    return {"id": id_, "tipo": tipo, "bloqueada": False, "silenciada": False, "oculta": False, "clips": clips}


def _sf_clip_foto(id_, inicio_ms, duracion_ms, material_id):
    # capa 5b, D11: una foto en la principal; `{tipo: "sonido"}` la salta.
    return {"id": id_, "inicio_ms": inicio_ms, "duracion_ms": duracion_ms, "material_id": material_id, "foto": True,
            "recorte": {"desde_ms": 0, "hasta_ms": duracion_ms}, "velocidad": 1.0,
            "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
            "keyframes": [], "animacion": None, "transicion": None,
            "audio": {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}}


def _sf_doc_base(fuentes=None):
    """v0 (material 1, 0-4000, recorte 0-4000) + v1 (material 1, 4000-7000,
    recorte 5000-8000) en la principal; voz_a (material 2, 1000-4000,
    bloque "hook", por_destino {es: 2, en: 5}) en p_voz."""
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [_sf_clip_video("v0", 0, 4000, 0, 4000), _sf_clip_video("v1", 4000, 3000, 5000, 8000)]
    doc["pistas"].append(_sf_pista("p_voz", "audio", [_sf_clip_audio(
        "voz_a", 1000, 3000, 2, bloque="hook",
        por_destino={"es": {"material_id": 2, "duracion_ms": 3000}, "en": {"material_id": 5, "duracion_ms": 3000}})]))
    if fuentes is not None:
        doc["subtitulos"] = {**doc["subtitulos"], "fuentes": fuentes}
    return doc


_SF_PALABRAS_M1 = [{"t_ms": 500, "dur_ms": 200, "texto": "Hola"},
                   {"t_ms": 4400, "dur_ms": 200, "texto": "fuera"},
                   {"t_ms": 5200, "dur_ms": 200, "texto": "video"}]
_SF_PALABRAS_M2 = [{"t_ms": 0, "dur_ms": 300, "texto": "voz-es"}]
_SF_PALABRAS_M5 = [{"t_ms": 0, "dur_ms": 300, "texto": "voz-en"}]


def _sf_caso(nombre, doc, idioma, pais, palabras_por_material, vacio_a_proposito=False):
    """`palabras_por_material` se guarda con las claves de texto (JSON no
    tiene claves enteras; el JS las lee como texto) pero `derivar` busca por
    el `material_id` ENTERO del clip — así que `esperado` se calcula con una
    copia de claves `int`, nunca con la que se guarda. `vacio_a_proposito`
    marca los pocos casos donde `esperado == []` es la regla (D10, pista
    oculta/silenciada), para que la prueba de guardia (`test_subtitulos_fuente.py`)
    distinga eso de este mismo bug (claves de texto) volviendo en silencio."""
    from final_edition import subtitulos_fuente as sf
    resuelto = documento.resolver(documento.validar(doc), idioma, pais)
    con_enteros = {int(k): v for k, v in palabras_por_material.items()}
    return {"nombre": nombre, "resuelto": resuelto, "palabras_por_material": palabras_por_material,
            "vacio_a_proposito": vacio_a_proposito, "esperado": sf.derivar(resuelto, con_enteros)}


def casos_subtitulos_fuente():
    casos = []
    casos.append(_sf_caso("fuente sonido: regla del centro y tope del clip",
                          _sf_doc_base(fuentes={"es": [{"tipo": "sonido"}]}), "es", "CO", {"1": _SF_PALABRAS_M1}))

    corte = documento.nuevo_video("9:16")
    corte["pistas"][0]["clips"] = [_sf_clip_video("v0a", 0, 2000, 0, 2000), _sf_clip_video("v0b", 2000, 2000, 2000, 4000)]
    corte["subtitulos"] = {**corte["subtitulos"], "fuentes": {"es": [{"tipo": "sonido"}]}}
    casos.append(_sf_caso("corte a mitad de palabra: UNA sola mitad", corte, "es", "CO",
                         {"1": [{"t_ms": 1900, "dur_ms": 200, "texto": "corte"}]}))

    reorden = _sf_doc_base()
    v0, v1 = reorden["pistas"][0]["clips"]
    reorden["pistas"][0]["clips"] = [{**v1, "inicio_ms": 0}, {**v0, "inicio_ms": 3000}]
    reorden["subtitulos"] = {**reorden["subtitulos"], "fuentes": {"es": [{"tipo": "sonido"}]}}
    casos.append(_sf_caso("reordenar la principal no rompe el mapeo", reorden, "es", "CO", {"1": _SF_PALABRAS_M1}))

    borrado = _sf_doc_base(fuentes={"es": [{"tipo": "sonido"}]})
    borrado["pistas"][0]["clips"] = [borrado["pistas"][0]["clips"][0]]
    casos.append(_sf_caso("borrar el clip borra sus palabras", borrado, "es", "CO", {"1": _SF_PALABRAS_M1}))

    veloz = _sf_doc_base(fuentes={"es": [{"tipo": "sonido"}]})
    veloz["pistas"][0]["clips"][1] = _sf_clip_video("v1", 4000, 1500, 5000, 8000, velocidad=2.0)
    casos.append(_sf_caso("velocidad 2x en el clip escala el mapeo", veloz, "es", "CO", {"1": _SF_PALABRAS_M1}))

    correcciones = documento.nuevo_video("9:16")
    correcciones["pistas"][0]["clips"] = [_sf_clip_video("v0a", 0, 2000, 0, 2000), _sf_clip_video("v0b", 2000, 2000, 2000, 4000)]
    correcciones["subtitulos"] = {**correcciones["subtitulos"], "fuentes": {"es": [{"tipo": "sonido"}]},
                                  "correcciones": {"1": {"0": "¡Hola!", "1": ""}}}
    casos.append(_sf_caso("correcciones por material e índice; '' quita la palabra", correcciones, "es", "CO",
                         {"1": [{"t_ms": 100, "dur_ms": 200, "texto": "hola"}, {"t_ms": 2100, "dur_ms": 200, "texto": "adios"}]}))

    casos.append(_sf_caso("fuente voz: el material resuelto por destino (es)",
                          _sf_doc_base(fuentes={"es": [{"tipo": "voz"}], "en": [{"tipo": "voz"}]}), "es", "CO",
                          {"2": _SF_PALABRAS_M2, "5": _SF_PALABRAS_M5}))
    casos.append(_sf_caso("fuente voz: el material resuelto por destino (en)",
                          _sf_doc_base(fuentes={"es": [{"tipo": "voz"}], "en": [{"tipo": "voz"}]}), "en", "US",
                          {"2": _SF_PALABRAS_M2, "5": _SF_PALABRAS_M5}))

    idioma_clip = _sf_doc_base(fuentes={"es": [{"tipo": "voz"}]})
    idioma_clip["pistas"][1]["clips"][0]["idioma"] = "en"
    casos.append(_sf_caso("un clip de voz con idioma no suena en otro destino", idioma_clip, "es", "CO",
                         {"2": _SF_PALABRAS_M2, "5": _SF_PALABRAS_M5}, vacio_a_proposito=True))

    for campo in ("oculta", "silenciada"):
        oculta = _sf_doc_base(fuentes={"es": [{"tipo": "voz"}]})
        oculta["pistas"][1][campo] = True
        casos.append(_sf_caso(f"pista {campo} no aporta subtítulos", oculta, "es", "CO",
                             {"2": _SF_PALABRAS_M2, "5": _SF_PALABRAS_M5}, vacio_a_proposito=True))

    empate = documento.nuevo_video("9:16")
    empate["pistas"][0]["clips"] = [_sf_clip_video("v0", 0, 4000, 0, 4000)]
    empate["pistas"].append(_sf_pista("p_voz", "audio", [_sf_clip_audio("voz_a", 1000, 3000, 2)]))
    empate["subtitulos"] = {**empate["subtitulos"], "fuentes": {"es": [{"tipo": "sonido"}, {"tipo": "voz"}]}}
    # dos palabras de pistas distintas (sonido de la principal, voz) que
    # caen en el MISMO t_ms derivado (1000): el orden es estable, por el
    # orden del documento (la principal antes que la pista de voz) — nunca
    # el orden en que `fuentes` las nombra ni el de las palabras originales.
    casos.append(_sf_caso("dos palabras en el mismo t_ms: orden estable por pista/clip", empate, "es", "CO",
                         {"1": [{"t_ms": 1000, "dur_ms": 100, "texto": "video_dice"}],
                          "2": [{"t_ms": 0, "dur_ms": 100, "texto": "voz_dice"}]}))

    tope = documento.nuevo_video("9:16")
    tope["pistas"][0]["clips"] = [_sf_clip_video("v0", 0, 1000, 0, 1000)]
    tope["pistas"].append(_sf_pista("p_voz", "audio", [_sf_clip_audio("voz_larga", 800, 500, 2)]))
    tope["subtitulos"] = {**tope["subtitulos"], "fuentes": {"es": [{"tipo": "voz"}]}}
    casos.append(_sf_caso("palabra tras el fin de la principal no sale; la que lo cruza se acota", tope, "es", "CO",
                         {"2": [{"t_ms": 150, "dur_ms": 100, "texto": "cruza"}, {"t_ms": 300, "dur_ms": 100, "texto": "fuera"}]}))

    dedup = _sf_doc_base(fuentes={"es": [{"tipo": "material", "material_id": 2}, {"tipo": "voz"}]})
    casos.append(_sf_caso("material + voz no duplican el clip; texto en blanco no sale", dedup, "es", "CO",
                         {"2": [{"t_ms": 0, "dur_ms": 300, "texto": "voz-es"}, {"t_ms": 400, "dur_ms": 100, "texto": "   "}]}))

    # capa 5b, D11: una foto en la principal (f0, material 4) no suena — la
    # fuente "sonido" la salta y solo salen las palabras del video (v0,
    # material 1) que la sigue. Una imagen nunca tiene `palabras` (nadie la
    # transcribe), así que esta tabla NO le da ninguna a material 4: el
    # salto explícito de la JS (Tarea 4) no hace falta para que este caso
    # pase hoy en los dos motores — la prueba de Python
    # (test_subtitulos_fuente.py) sí le da palabras a la foto para probar
    # que `clips_de_fuente` la excluye de verdad.
    foto_fuente = documento.nuevo_video("9:16")
    foto_fuente["pistas"][0]["clips"] = [_sf_clip_foto("f0", 0, 3000, 4),
                                         _sf_clip_video("v0", 3000, 4000, 0, 4000, material_id=1)]
    foto_fuente["subtitulos"] = {**foto_fuente["subtitulos"], "fuentes": {"es": [{"tipo": "sonido"}]}}
    casos.append(_sf_caso("una foto en la principal no aporta subtítulos (D11)", foto_fuente, "es", "CO",
                         {"1": [{"t_ms": 100, "dur_ms": 200, "texto": "video"}]}))
    return casos


# --- encuadre (editor, capa 5b, D4-D7): la Tarea 1 escribe el espejo
# static/editor/encuadre.js contra esta tabla.
ENCUADRE_MEDIDAS = (
    (1920, 1080), (1080, 1920), (1000, 1000), (400, 200), (1284, 2778),
    (3000, 2000), (3024, 4032), (800, 600), (1081, 1919),      # redondeos
)

ENCUADRE_VARIANTES = (
    None,
    {"modo": "llenar", "x": 0},
    {"modo": "llenar", "x": 1},
    {"modo": "llenar", "y": 0},
    {"modo": "llenar", "zoom": 1.5},
    {"modo": "llenar", "zoom": 1.37, "x": 0.3, "y": 0.7},
    {"modo": "llenar", "zoom": 4},
    {"modo": "ajustar"},
    {"modo": "ajustar", "zoom": 2, "x": 0.25},
)


def casos_encuadre():
    from final_edition import encuadre
    cajas = []
    automaticos = []
    fondos = {}
    for formato, (lienzo_w, lienzo_h) in documento.FORMATOS.items():
        fondos[formato] = encuadre.fondo(lienzo_w, lienzo_h)
        for ancho, alto in ENCUADRE_MEDIDAS:
            automaticos.append({"ancho": ancho, "alto": alto, "formato": formato,
                               "esperado": encuadre.ajuste_automatico(ancho, alto, lienzo_w, lienzo_h)})
            for enc in ENCUADRE_VARIANTES:
                cajas.append({"ancho": ancho, "alto": alto, "formato": formato, "encuadre": enc,
                             "esperado": encuadre.caja(ancho, alto, lienzo_w, lienzo_h, enc)})
    return {"cajas": cajas, "fondos": fondos, "automaticos": automaticos}


TIPOGRAFIA_SIMPLIFICAR = (
    "👍🏽 Listo", "🇨🇴 Envíos", "❤️ Amor", "👨‍👩‍👧 Familia", "1️⃣ Paso", "Hola",
    "", "🔥🔥 doble", "a\u200db", "🔥\u200d", "👩🏿‍🦰 y 👩🏻", "❤️\u200d🔥 fuego", "x🇨", "\U000E0067\U000E007Fb", "\u3000👍",
)
TIPOGRAFIA_LIMPIAR = (
    "✓ Envío", "🔥 50% OFF", "❤️ Amor ❤️", "a\tb\r\nc", "a\rb", "  a   b  \n  c ", "a\u00a0\u00a0b \u00a0",
    "👍🏽 Listo 🇨🇴", "Precio\u00a0$\u00a089.900", "→ ★ ✓ ✗ ♥ ⚡", "Ñandú ¡Hola! ¿Qué tal? 50 % — € £ ¥", "日本語 и кириллица", "🔥✓🔥 a ✓ 🚀",
    "", "\x00\x07 raro",
)
TIPOGRAFIA_FUENTES = ("Inter-Bold", "SpaceGrotesk-Bold", "Anton-Regular")
TIPOGRAFIA_FUENTES_V1 = ("Inter-Bold", "SpaceGrotesk-Bold", "Poppins-ExtraBold")
TIPOGRAFIA_V1 = TIPOGRAFIA_LIMPIAR + ("👨‍👩‍👧 Familia", "a🔥\u200d b", "1️⃣ paso  doble", "Hola 🔥 mundo", "🔥🔥 dos\n🚀 tres")
TIPOGRAFIA_FRASES = ("Envío gratis a todo el país en 24 horas", "Precio\u00a0$\u00a089.900 hoy en toda la tienda con descuento")
TIPOGRAFIA_ANCHOS = (None, 540, 929)

_V2 = {"fuente": "Inter-Bold", "tamano": 0.05, "color": "#FFFFFF", "version": 2}
TIPOGRAFIA_MAQUETAS = (
    ("Hola", _V2, "9:16", 1),
    ("Hola", {**_V2, "alineacion": "izquierda"}, "9:16", 1),
    ("Hola", {**_V2, "alineacion": "derecha"}, "9:16", 2),
    ("Envío gratis a todo el país en 24 horas", {**_V2, "ancho_max": 0.6, "interlineado": 1.2}, "9:16", 1),
    ("Compra hoy\ny llévate el segundo\n\ncon 50 % menos",
     {**_V2, "fuente": "SpaceGrotesk-Bold", "alineacion": "izquierda", "ancho_max": 0.8, "interlineado": 1.3}, "4:5", 1),
    ("Compra ya", {**_V2, "fuente": "Poppins-ExtraBold", "tamano": 0.04, "ancho_max": 0.6815, "interlineado": 1.194,
                    "fondo": {"color": "#121218", "opacidad": 0.92, "radio": 0.025, "relleno_x": 0.0333, "relleno_y": 0.0333,
                              "ancho": 0.8}}, "9:16", 1),
    ("Tu piel, en 7 días", {**_V2, "fuente": "Anton-Regular", "tamano": 0.07,
                            "contorno": {"color": "#000000", "grosor": 0.004}, "ancho_max": 0.9}, "9:16", 3),
    ("Última oferta del mes", {**_V2, "fuente": "Pacifico-Regular", "ancho_max": 0.5, "alineacion": "derecha",
                               "sombra": {"color": "#000000C8", "dx": 0.0031, "dy": 0.0031},
                               "contorno": {"color": "#000000DC", "grosor": 0.0016}}, "1:1", 1),
    ("Precio\u00a0$\u00a089.900 hoy", {**_V2, "ancho_max": 0.4}, "9:16", 1),
    ("🔥 50% OFF ❤️", {**_V2, "fuente": "LilitaOne-Regular", "tamano": 0.06}, "9:16", 1),
    ("Hola 👍🏽 ✓ → ¡Envío!", {**_V2, "fuente": "SpaceGrotesk-Bold", "alineacion": "izquierda", "ancho_max": 0.7}, "9:16", 3),
    ("Envío gratis a todo el país", {**_V2, "fuente": "DMSerifDisplay-Regular", "tamano": 0.08, "ancho_max": 0.5}, "16:9", 1),
    ("OFERTA\nSOLO HOY", {**_V2, "fuente": "BebasNeue-Regular", "tamano": 0.09, "interlineado": 1.0}, "16:9", 2),
    # un radio mayor que la mitad de la caja se acota a ella; un fondo con ancho mínimo y relleno pequeño
    ("Sí", {**_V2, "tamano": 0.03, "fondo": {"color": "#FF0000", "opacidad": 1, "radio": 0.5, "relleno_x": 0.01, "relleno_y": 0.005,
                                              "ancho": 0.3}}, "1:1", 1),
)

TIPOGRAFIA_CLIPS = (
    {"transform": {"escala": 1.5}, "keyframes": [{"t_ms": 0, "transform": {"escala": 2.5}}]},
    {"transform": {"escala": 1.5}},
    {},
    {"transform": {"x": 0.5}},
    {"transform": {"escala": 0.5}, "keyframes": [{"t_ms": 0, "transform": {"x": 0.1}}, {"t_ms": 500, "transform": {"escala": 0.8}}]},
    {"transform": {"escala": 3.0}, "keyframes": [{"t_ms": 0, "transform": {"escala": 0.5}}]},
)
TIPOGRAFIA_FACTORES = ((1.0, 221, 125), (1.2, 221, 125), (2.0, 221, 125), (3.5, 221, 125), (9, 221, 125), (3.5, 1500, 200),
                       (0.4, 100, 100), (4, 5000, 100), (2, 100, 2048), (2, 100, 2049))


def _tabla_real():
    """La tabla del repo tal como está en disco: sin la válvula `EDITOR_SIN_EMOJI` de `cargar_tabla` (la tabla de paridad no
    puede cambiar según el entorno de quien la regenera)."""
    from final_edition import fuentes
    with open(fuentes.RUTA_TABLA, encoding="utf-8") as f:
        return json.load(f)


def casos_tipografia():
    from final_edition import tipografia as tp
    tabla = _tabla_real()
    fuentes_ = [f for f in TIPOGRAFIA_FUENTES if f in tabla["fuentes"]]
    cps = sorted({ord(c) for t in TIPOGRAFIA_LIMPIAR + TIPOGRAFIA_SIMPLIFICAR for c in t} | {0x20, 0xA0, 0x0A, 0x2190, 0x2713, 0x2764, 0x1F525})
    return {
        "simplificar": [{"texto": t, "esperado": tp.simplificar(t)} for t in TIPOGRAFIA_SIMPLIFICAR],
        "limpiar": [{"texto": t, "fuente": f, "esperado": tp.limpiar(t, f, tabla)} for f in fuentes_ for t in TIPOGRAFIA_LIMPIAR],
        "fuente_de": [{"cp": cp, "fuente": f, "esperado": tp.fuente_de(cp, f, tabla)} for f in fuentes_ for cp in cps],
        # v1 con las dos fuentes de hoy y con Poppins, que SÍ trae la unión ZWJ (U+200D): ahí la regla «la unión se
        # va con el carácter quitado» no es redundante con la cobertura
        "sin_glifos_v1": [{"texto": t, "fuente": f, "esperado": tp.sin_glifos_v1(t, f, tabla)}
                          for f in [x for x in TIPOGRAFIA_FUENTES_V1 if x in tabla["fuentes"]] for t in TIPOGRAFIA_V1],
        "ajustar": [{"texto": t, "fuente": "Inter-Bold", "tam": 72, "ancho_max_px": a,
                     "esperado": tp.ajustar(t, "Inter-Bold", 72, a, tabla)}
                    for t in TIPOGRAFIA_FRASES for a in TIPOGRAFIA_ANCHOS],
        "maquetar": [{"texto": t, "estilo": e, "formato": fmt, "factor": f, "esperado": tp.maquetar(t, e, fmt, tabla, f)}
                     for t, e, fmt, f in TIPOGRAFIA_MAQUETAS],
        "escala_max": [{"clip": c, "esperado": tp.escala_max(c)} for c in TIPOGRAFIA_CLIPS],
        "factor": [{"escala": e, "ancho_px": w, "alto_px": h, "esperado": tp.factor_nitidez(e, w, h)}
                   for e, w, h in TIPOGRAFIA_FACTORES],
    }


ARCHIVOS = {
    "precios_casos.json": casos_precios,
    "resolver_casos.json": casos_resolver,
    "ajuste_casos.json": casos_ajuste,
    "ventanas_casos.json": casos_ventanas,
    "subtitulos_fuente_casos.json": casos_subtitulos_fuente,
    "subtitulos_eventos_casos.json": casos_eventos,
    "encuadre_casos.json": casos_encuadre,
    "tipografia_casos.json": casos_tipografia,
}


def texto(funcion):
    return json.dumps(funcion(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    for nombre, funcion in ARCHIVOS.items():
        with open(os.path.join(AQUI, nombre), "w", encoding="utf-8") as f:
            f.write(texto(funcion))
        print("escrito", nombre)

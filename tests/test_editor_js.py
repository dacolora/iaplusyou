"""Pruebas de los módulos del editor en el navegador (static/editor/*.js).
Corren con el runner que trae Node (`node --test`), sin npm ni node_modules;
donde no hay Node (el VPS) se saltan. Además se comparan con Python las
constantes que el navegador no puede recibir de la página (las que usan
las pruebas de Node)."""
import glob
import json
import os
import re
import shutil
import subprocess

import pytest

from final_edition import documento

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="sin Node no corren las pruebas de JS (el VPS no lo tiene)")
def test_modulos_del_editor_pasan_sus_pruebas():
    archivos = sorted(glob.glob(os.path.join(RAIZ, "tests", "js", "*.test.mjs")))
    assert archivos, "no hay pruebas en tests/js"
    r = subprocess.run([NODE, "--test", *archivos], cwd=RAIZ, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, (r.stdout[-6000:] + "\n" + r.stderr[-3000:])


def _constante_js(archivo, nombre):
    with open(os.path.join(RAIZ, "static", "editor", archivo), encoding="utf-8") as f:
        texto = f.read()
    m = re.search(rf"export const {nombre} = (.*?);\n", texto, re.S)
    assert m, f"{archivo} no exporta {nombre}"
    return json.loads(m.group(1))


def test_formatos_js_iguales_a_python():
    assert _constante_js("formatos.js", "FORMATOS") == {k: list(v) for k, v in documento.FORMATOS.items()}


def test_ventana_de_picos_igual_a_python():
    # La onda de la línea de tiempo (escala.barrasOnda) lee un pico cada
    # VENTANA_PICOS_MS de fuente: los que guarda tareas.edicion._picos.
    import inspect

    from final_edition import vista_previa
    from tareas import edicion
    assert _constante_js("escala.js", "VENTANA_PICOS_MS") == vista_previa.VENTANA_PICOS_MS
    assert inspect.signature(edicion._picos).parameters["ventana_ms"].default == vista_previa.VENTANA_PICOS_MS


def test_biblioteca_js_acepta_lo_mismo_que_el_servidor():
    # biblioteca.js revisa tipo y peso ANTES de subir (un video de 500 MB no
    # viaja para que el servidor lo rechace): sus copias tienen que ser las de Python.
    import materiales
    from final_edition import biblioteca
    assert _constante_js("biblioteca.js", "EXTENSIONES_SUBIDA") == {ext: t for ext, (t, _ct) in biblioteca.EXTENSIONES.items()}
    assert _constante_js("biblioteca.js", "LIMITES_SUBIDA") == {t: b for t, (b, _ms) in materiales.LIMITES.items()}


def test_grabacion_js_acepta_lo_mismo_que_el_servidor():
    # Capa 5a (Task 8, D8): el micrófono graba en un formato que la ruta
    # editor.grabacion acepta, y el reloj se detiene en el mismo tope.
    from final_edition import biblioteca
    formatos = _constante_js("voz_modelo.js", "FORMATOS_GRABACION")
    assert {ext for _mime, ext in formatos} <= biblioteca.EXTENSIONES_GRABACION
    assert _constante_js("voz_modelo.js", "MAX_GRABACION_MS") == biblioteca.MAX_GRABACION_MS


def test_desplazamiento_de_deslizar_igual_a_python():
    # Capa 4c (2/10): la entrada «deslizar» baja la capa una fracción de la
    # altura del lienzo, la misma en la vista previa y en el render.
    from final_edition.motor import compilador
    assert _constante_js("tiempo.js", "DESPLAZ_ANIM_FRACCION") == compilador.DESPLAZ_ANIM_FRACCION


def test_la_biblioteca_ofrece_borrar_lo_mismo_que_el_servidor_acepta():
    # Capa 4c (8/10): el tacho sale solo donde la ruta sí borra.
    from final_edition import biblioteca
    assert _constante_js("biblioteca.js", "ORIGENES_BORRABLES") == list(biblioteca.ORIGENES_BORRABLES)


def test_pagina_editor_no_ejecuta_nada_antes_de_declararlo_todo():
    # Arreglo crítico de la capa 4c: `guardado.pedir` corría al cargar el
    # módulo ANTES de `const TEXTO_GUARDADO` (pedir → pintarGuardado lo lee):
    # ReferenceError y el editor no arrancaba justo en las ediciones que el
    # ítem 4 arregla. El módulo no se puede importar en Node (toca el DOM), así
    # que se mira el texto: toda sentencia de nivel superior que ejecuta algo
    # (una llamada, un `if`, un `await`, un `new` suelto) va DESPUÉS de la
    # última declaración `const`/`let` de nivel superior, y el guardado de lo
    # arreglado al abrir es una de ellas.
    with open(os.path.join(RAIZ, "static", "editor", "pagina_editor.js"), encoding="utf-8") as f:
        lineas = f.read().splitlines()
    declaraciones = [i for i, l in enumerate(lineas) if re.match(r"(const|let) ", l)]
    ejecuta = [i for i, l in enumerate(lineas) if re.match(r"(if \(|await |new |\{|[A-Za-z_$][\w$.]*\()", l)]
    assert declaraciones and ejecuta
    antes = [lineas[i] for i in ejecuta if i < max(declaraciones)]
    assert not antes, f"se ejecuta antes de declarar todo: {antes}"
    pedir = [i for i, l in enumerate(lineas) if re.match(r"\S.*guardado\.pedir\(", l)]
    assert pedir and min(pedir) > max(declaraciones), "el guardado de lo arreglado al abrir va al final del arranque"


def test_transiciones_js_iguales_a_python():
    # la biblioteca ofrece solo las transiciones que el render hace
    assert _constante_js("operaciones.js", "TRANSICIONES") == list(documento.TRANSICIONES)


def test_estilos_subtitulos_js_iguales_a_python():
    # cambiarSubtitulos solo acepta un estilo_id que documento.validar conoce
    assert _constante_js("operaciones.js", "ESTILOS_SUBTITULOS") == list(documento.ESTILOS_SUBTITULOS)


def test_max_fuentes_subtitulo_js_igual_a_python():
    # ponerFuentesSubtitulos rechaza lo que documento.validar rechazaría por tener más fuentes de la cuenta
    assert _constante_js("operaciones.js", "MAX_FUENTES_SUBTITULO") == documento.MAX_FUENTES_SUBTITULO


def test_fuentes_js_iguales_al_catalogo():
    # capa 5c (D9.2): operaciones.cambiar acepta toda fuente del catálogo, en
    # su orden; el panel agrupa por las mismas familias, en el mismo orden
    from final_edition import fuentes
    assert _constante_js("operaciones.js", "FUENTES") == [c[0] for c in fuentes.CATALOGO]
    assert _constante_js("propiedades_modelo.js", "CATEGORIAS_FUENTE") == list(fuentes.CATEGORIAS)


def test_max_pistas_js_igual_a_python():
    # agregar*/pistaNueva rechazan con «demasiadas pistas» donde documento.validar
    # rechazaría: ni antes (con 8 un borrador con título y stickers ya no aceptaba
    # otro emoji) ni después (la edición guardaría un documento que el servidor no
    # acepta). Capa 5c, prueba en vivo: 20 en los dos motores.
    assert _constante_js("operaciones.js", "MAX_PISTAS") == documento.MAX_PISTAS == 20


def test_max_correccion_js_igual_a_python():
    # corregirPalabra y el campo de la pestaña Subtítulos (maxLength) cortan
    # donde documento.validar cortaría (capa 5a, D3)
    assert _constante_js("operaciones.js", "MAX_CORRECCION") == documento.MAX_CORRECCION


def _generador():
    import importlib.util
    ruta = os.path.join(RAIZ, "tests", "fixtures", "generar_casos_editor.py")
    spec = importlib.util.spec_from_file_location("generar_casos_editor", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_casos_del_editor_al_dia():
    gen = _generador()
    for nombre, funcion in gen.ARCHIVOS.items():
        with open(os.path.join(RAIZ, "tests", "fixtures", nombre), encoding="utf-8") as f:
            assert f.read() == gen.texto(funcion), (
                f"{nombre} quedó viejo: correr `venv/bin/python3 tests/fixtures/generar_casos_editor.py`")


def test_ducking_de_mezcla_es_legible_por_el_navegador():
    # audio.js::parsearDucking lee "clave=valor:clave=valor" con estas cuatro claves.
    from final_edition import mezcla
    for cadena in (mezcla.DUCKING_VOZ_SOBRE_MUSICA, mezcla.DUCKING_VOZ_SOBRE_SONIDO):
        partes = dict(p.split("=") for p in cadena.split(":"))
        assert set(partes) == {"threshold", "ratio", "attack", "release"}
        assert all(float(v) > 0 for v in partes.values())


def test_mezclas_del_panel_iguales_a_python():
    # El panel de propiedades ofrece estas mezclas (operaciones.cambiarMezcla):
    # tienen que ser las que conoce el render (mezcla.PRESETS), ni una más.
    from final_edition import mezcla
    assert _constante_js("operaciones.js", "MEZCLAS") == list(mezcla.PRESETS)
    assert mezcla.PRESET_DEFECTO == "equilibrada"


def test_foto_constantes_js_iguales_a_python():
    # Capa 5b (D1): agregarFoto/cambiarDuracionFoto acotan a lo mismo que
    # documento.validar aceptaría (FOTO_MIN_MS es MIN_CLIP_MS, ya igual: 100).
    from final_edition import documento
    assert _constante_js("operaciones.js", "FOTO_MAX_MS") == documento.FOTO_MAX_MS
    assert _constante_js("operaciones.js", "FOTO_DEFECTO_MS") == documento.FOTO_DEFECTO_MS
    assert _constante_js("operaciones.js", "MIN_CLIP_MS") == documento.FOTO_MIN_MS


def test_encuadre_js_constantes_iguales_a_python():
    # Capa 5b (D4-D7): el panel «Encuadre» y el arrastre/asa del lienzo
    # clavan los mismos límites que `documento.validar` y el compilador.
    from final_edition import encuadre
    assert _constante_js("encuadre.js", "MODOS") == list(encuadre.MODOS)
    assert _constante_js("encuadre.js", "ZOOM_MIN") == encuadre.ZOOM_MIN
    assert _constante_js("encuadre.js", "ZOOM_MAX") == encuadre.ZOOM_MAX
    assert _constante_js("encuadre.js", "DEFECTO") == encuadre.DEFECTO
    assert _constante_js("encuadre.js", "FONDO_DIVISOR") == encuadre.FONDO_DIVISOR
    assert _constante_js("encuadre.js", "UMBRAL_AJUSTE") == list(encuadre.UMBRAL_AJUSTE)


def test_tipografia_js_constantes_iguales_a_python():
    # capa 5c (D5): la maqueta del texto comparte constantes con final_edition/tipografia.py
    from final_edition import tipografia
    assert _constante_js("tipografia.js", "SEPARADOR") == tipografia.SEPARADOR
    assert _constante_js("tipografia.js", "FACTOR_MAX") == tipografia.FACTOR_MAX
    assert _constante_js("tipografia.js", "LADO_MAX_PNG") == tipografia.LADO_MAX_PNG
    assert _constante_js("tipografia.js", "SELECTORES") == list(tipografia.SELECTORES)
    assert _constante_js("tipografia.js", "TONOS") == list(tipografia.TONOS)
    assert _constante_js("tipografia.js", "KEYCAP") == tipografia.KEYCAP
    assert _constante_js("tipografia.js", "ZWJ") == tipografia.ZWJ
    assert _constante_js("tipografia.js", "ETIQUETAS") == list(tipografia.ETIQUETAS)
    assert _constante_js("tipografia.js", "REGIONALES") == list(tipografia.REGIONALES)
    assert _constante_js("tipografia.js", "ESPACIOS") == list(tipografia.ESPACIOS)


def test_la_familia_de_emojis_es_la_misma_en_la_plantilla_el_js_y_la_config():
    # Capa 5c (4/9): el lienzo dibuja los emojis con `font = "<tam>px "CreatvEmoji""`; la @font-face que la
    # declara y la config que la ofrece tienen que decir lo mismo, o el emoji cae a la fuente de respaldo.
    from final_edition import vista_previa
    familia = _constante_js("texto_canvas.js", "FAMILIA_EMOJI")
    assert familia == vista_previa.EMOJI_NAVEGADOR["familia"] == vista_previa.config_navegador()["emoji"]["familia"]
    with open(os.path.join(RAIZ, "templates", "editor.html"), encoding="utf-8") as f:
        plantilla = f.read()
    bloque = re.search(r"\{% if datos\.config\.emoji %\}(.*?)\{% endif %\}", plantilla, re.S)
    assert bloque, "la plantilla declara la @font-face de emojis solo si hay fuente"
    assert f'@font-face {{ font-family: "{familia}";' in bloque.group(1)
    assert "filename=datos.config.emoji.archivo" in bloque.group(1)
    # los demás módulos la importan: ningún otro escribe el nombre
    for ruta in glob.glob(os.path.join(RAIZ, "static", "editor", "*.js")):
        if os.path.basename(ruta) != "texto_canvas.js":
            with open(ruta, encoding="utf-8") as f:
                assert f'"{familia}"' not in f.read(), os.path.basename(ruta)


def test_la_pagina_le_pasa_a_la_biblioteca_los_stickers_y_la_tabla_de_emojis():
    """Capa 5c (Tarea 8): pagina_editor.js no se puede importar en Node (toca el DOM), así que se mira el texto: la
    biblioteca pinta la pestaña «Stickers» con `datos.stickers` (los 20 de la casa) y decide si hay emojis con la tabla
    tipográfica de la página (`datos.config.tipografia.emoji`). Sin esos dos argumentos la pestaña salía vacía."""
    with open(os.path.join(RAIZ, "static", "editor", "pagina_editor.js"), encoding="utf-8") as f:
        texto = f.read()
    llamada = re.search(r"new Biblioteca\(\{(.*?)\}\);", texto, re.S).group(1)
    assert "stickers: datos.stickers" in llamada
    assert "tabla: datos.config?.tipografia" in llamada

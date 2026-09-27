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

VALORES_PRECIO = (89900, 24.99, 1234567.891, 499.5, 0, 0.125, 1.005, 2.675, 19.995, 1500000)


def casos_precios():
    return [{"valor": v, "pais": pais, "esperado": tipos.formatear_precio(v, pais)}
            for pais in sorted(tipos.PAISES) for v in VALORES_PRECIO]


def _doc_resolver():
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "v0", "inicio_ms": 0, "duracion_ms": 4000, "material_id": 1,
                                  "recorte": {"desde_ms": 0, "hasta_ms": 4000}}]
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
    ]})
    doc["variables"] = {"textos": {"hook": {"es_CO": "Tu piel, en 7 días", "es": "Tu piel en 7 días",
                                            "en_US": "Your skin in 7 days"}},
                        "voz": {}, "precios": {"es_CO": 89900, "es_MX": 499.5, "en_US": 24.99}}
    doc["subtitulos"] = {"palabras": {"es_CO": [{"t_ms": 0, "dur_ms": 400, "texto": "Tu"}],
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


ARCHIVOS = {
    "precios_casos.json": casos_precios,
    "resolver_casos.json": casos_resolver,
    "ajuste_casos.json": casos_ajuste,
}


def texto(funcion):
    return json.dumps(funcion(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    for nombre, funcion in ARCHIVOS.items():
        with open(os.path.join(AQUI, nombre), "w", encoding="utf-8") as f:
            f.write(texto(funcion))
        print("escrito", nombre)

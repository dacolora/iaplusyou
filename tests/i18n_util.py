"""Detección de español en HTML (spec 2026-09-26 §Pruebas). Heurística: acentos,
ñ, ¿ ¡ y palabras muy frecuentes del español que no existen sueltas en inglés.
EXCEPCIONES son palabras que pueden quedar a propósito (el nombre del idioma en
el selector bilingüe)."""
import re
from html.parser import HTMLParser

MARCAS = re.compile(
    r"[¿¡ñÑáéíóúÁÉÍÓÚ]"
    r"|\b(?:el|la|los|las|de|del|en|para|con|una|que|por|tu|tus|sin|está|aquí|más|también|nuevo|nueva|"
    r"guardar|entrar|cuenta|correo|contraseña|proyecto|usuario|conectar|todavía|ahora)\b",
    re.I)
EXCEPCIONES = ("Español", "Idioma")
VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ATRIBUTOS = ("placeholder", "title", "aria-label", "alt")


def _con_marca(texto):
    for palabra in EXCEPCIONES:
        texto = texto.replace(palabra, " ")
    return bool(MARCAS.search(texto))


class _Visible(HTMLParser):
    def __init__(self, ids=None):
        super().__init__(convert_charrefs=True)
        self.ids = set(ids or ())
        self.pila = []
        self.region = 0 if self.ids else 1
        self.oculto = 0
        self.trozos = []
        self.vistos = set()

    def handle_starttag(self, tag, attrs):
        a = {k: v for k, v in attrs if v is not None}
        el_id = a.get("id")
        abre = bool(self.ids) and el_id in self.ids
        if abre:
            self.vistos.add(el_id)
        is_void = tag in VACIOS
        # translate="no" (HTML estándar: «no traducir esto») marca un
        # identificador que se pinta tal cual, p. ej. el código de idioma de
        # un destino de Final edition («en» = inglés, no la preposición): su
        # subárbol no se mira, igual que un <script>.
        oculta = tag in ("script", "style", "template") or (a.get("translate") or "").lower() == "no"
        if not is_void:
            self.pila.append((tag, abre, oculta))
            self.region += abre
            self.oculto += oculta
        # Inspect attributes if we're in a region, OR if this is a void element with matching id
        should_inspect = ((self.region and not self.oculto) or (abre and is_void and not self.oculto)) and not oculta
        if should_inspect:
            self.trozos += [a[k] for k in ATRIBUTOS if a.get(k)]
            if tag in ("input", "button") and a.get("type") in ("submit", "button") and a.get("value"):
                self.trozos.append(a["value"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VACIOS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in [t for t, _abre, _oculta in self.pila]:
            return
        while self.pila:
            t, abre, oculta = self.pila.pop()
            self.region -= abre
            self.oculto -= oculta
            if t == tag:
                break

    def handle_data(self, data):
        if self.region and not self.oculto and data.strip():
            self.trozos.append(" ".join(data.split()))


def espanol_visible(html, ids=None):
    p = _Visible(ids)
    p.feed(html)
    if ids:
        # p.region siempre vuelve a 0 al terminar el parseo (abre/cierra se
        # balancean), incluso cuando NINGÚN id pedido apareció nunca — así que
        # comparar contra region no detecta un id renombrado. Se exige en
        # cambio que cada id pedido se haya visto de verdad.
        faltan = set(ids) - p.vistos
        assert not faltan, f"no encontré los elementos {sorted(faltan)}"
    return [t for t in p.trozos if _con_marca(t)]


_SCRIPT_TOKEN = re.compile(
    r"'(?:[^'\\\n]|\\.)*'|"  # single-quoted string
    r'"(?:[^\"\\\n]|\\.)*"|'  # double-quoted string
    r"`(?:[^`\\]|\\.)*`|"     # template literal
    r"//[^\n]*|"              # line comment
    r"/\*.*?\*/",             # block comment
    re.S)


def espanol_en_plantilla(ruta):
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r"\{#.*?#\}", " ", src, flags=re.S)
    src = re.sub(r"\{%.*?%\}", " ", src, flags=re.S)
    src = re.sub(r"\{\{.*?\}\}", " ", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)
    hallazgos = espanol_visible(src)
    for bloque in re.findall(r"<script\b[^>]*>(.*?)</script>", src, flags=re.S | re.I):
        tokens = _SCRIPT_TOKEN.findall(bloque)
        # Keep only string literals (start with ', ", or `) that have Spanish marks
        hallazgos += [t for t in tokens if t[0] in ("'", '"', "`") and _con_marca(t)]
    return hallazgos


# Palabras españolas que MARCAS no incluye (a propósito: en HTML darían falsos
# positivos) y que sí delatan un texto suelto en CÓDIGO: etiquetas cortas del
# editor («Guardado», «Pista»), etapas («Renderizando») y mensajes sin tildes
# («Ya se estaba preparando ese video.»). Solo lo usan las guardias de código
# (tests/test_i18n_mensajes.py, tests/test_i18n_editor.py).
MARCAS_CODIGO = re.compile(
    r"\b(?:ya|se|esa|ese|eso|esos|esas|este|esta|estos|estas|listo|lista|listos|listas|hecho|hecha|"
    r"falta|faltan|borrados?|borradas?|elige|marca|destinos?|pista|voz|sonido|efecto|textos?|imagen|encima|"
    r"precio|pausar|reproducir|guardado|guardando|cambios|recarga|recargar|cortar|duplicar|borrar|velocidad|"
    r"archivos?|produciendo|preparando|cargando|pudo|pudieron|materiales|renderizando|subiendo|uniendo|"
    r"tramos?|inexistente|interrumpida|interrumpido|agregado)\b", re.I)


def espanol_en_codigo(texto):
    return _con_marca(texto) or bool(MARCAS_CODIGO.search(texto))

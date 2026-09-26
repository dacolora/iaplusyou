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

    def handle_starttag(self, tag, attrs):
        a = {k: v for k, v in attrs if v is not None}
        abre = bool(self.ids) and a.get("id") in self.ids
        if tag not in VACIOS:
            self.pila.append((tag, abre))
            self.region += abre
            self.oculto += tag in ("script", "style", "template")
        if self.region and not self.oculto:
            self.trozos += [a[k] for k in ATRIBUTOS if a.get(k)]
            if tag in ("input", "button") and a.get("type") in ("submit", "button") and a.get("value"):
                self.trozos.append(a["value"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VACIOS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in [t for t, _abre in self.pila]:
            return
        while self.pila:
            t, abre = self.pila.pop()
            self.region -= abre
            self.oculto -= t in ("script", "style", "template")
            if t == tag:
                break

    def handle_data(self, data):
        if self.region and not self.oculto and data.strip():
            self.trozos.append(" ".join(data.split()))


def espanol_visible(html, ids=None):
    p = _Visible(ids)
    p.feed(html)
    if ids:
        assert p.region == 0 or p.trozos, f"no encontré los elementos {ids}"
    return [t for t in p.trozos if _con_marca(t)]


_LITERAL_JS = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`")


def espanol_en_plantilla(ruta):
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r"\{#.*?#\}", " ", src, flags=re.S)
    src = re.sub(r"\{%.*?%\}", " ", src, flags=re.S)
    src = re.sub(r"\{\{.*?\}\}", " ", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)
    hallazgos = espanol_visible(src)
    for bloque in re.findall(r"<script\b[^>]*>(.*?)</script>", src, flags=re.S | re.I):
        bloque = re.sub(r"/\*.*?\*/", " ", bloque, flags=re.S)
        bloque = re.sub(r"(?<![:'\"\\])//[^\n]*", " ", bloque)
        hallazgos += [lit for lit in _LITERAL_JS.findall(bloque) if _con_marca(lit)]
    return hallazgos

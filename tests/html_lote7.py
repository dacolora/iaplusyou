"""Árbol mínimo del HTML renderizado para comprobar cada acción y su botón."""
from html.parser import HTMLParser


class Nodo:
    def __init__(self, tag='', attrs=(), padre=None):
        self.tag, self.attrs, self.padre = tag, dict(attrs), padre
        self.hijos, self.textos = [], []

    def todos(self, tag):
        return [n for h in self.hijos for n in ([h] if h.tag == tag else []) + h.todos(tag)]

    def texto(self):
        return ''.join(self.textos) + ''.join(h.texto() for h in self.hijos)

    def dentro(self, tag):
        return bool(self.padre and (self.padre.tag == tag or self.padre.dentro(tag)))


class HTML(HTMLParser):
    def __init__(self, texto):
        super().__init__()
        self.raiz = self.actual = Nodo()
        self.feed(texto)

    def handle_starttag(self, tag, attrs):
        n = Nodo(tag, attrs, self.actual)
        self.actual.hijos.append(n)
        if tag not in ('input', 'img', 'br', 'hr', 'meta', 'link', 'source', 'wbr'):
            self.actual = n

    def handle_endtag(self, tag):
        n = self.actual
        while n.padre:
            if n.tag == tag:
                self.actual = n.padre
                break
            n = n.padre

    def handle_data(self, data):
        self.actual.textos.append(data)

    def form(self, action):
        return next(f for f in self.raiz.todos('form') if f.attrs.get('action') == action)

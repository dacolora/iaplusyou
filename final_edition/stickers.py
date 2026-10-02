"""Stickers propios del editor (capa 5c, D11): 20 dibujos sin palabras, hechos aquí con Pillow, sin nada que bajar
ni licencias de terceros. Cada uno es BLANCO sobre transparente (el color lo pone después el `tinte` de la capa:
`lutrgb` en el render, `destination-in` en la vista previa, y para eso hace falta que todo píxel visible sea
(255, 255, 255)) y mide 512 px en su lado mayor.

El paquete va commiteado (`static/stickers/*.png` + `stickers.json`); este módulo es lo que lo regenera:

    venv/bin/python3 -m final_edition.stickers

Cómo se dibuja: en un lienzo de `LADO·SUPER` píxeles, en una máscara de un solo canal (255 = tinta), con un
espacio de 1000×1000 unidades que cada dibujo recorre a su gusto. Los trazos son líneas de ancho fijo
(`ImageDraw.line(..., joint="curve")`) con un círculo en cada punta y en cada vértice, así que el grosor es parejo
aunque la línea tiemble; los «a mano» salen de unos pocos puntos de control con un temblor de `random.Random` de
semilla fija por id, suavizados con una curva de Catmull-Rom (el mismo id da siempre el mismo trazo). Al final se
recorta lo transparente, se reduce con LANCZOS de modo que el lado mayor mida `LADO` menos el aire de los dos lados y
se deja `AIRE` px de margen: ninguna forma toca el borde del PNG.

Este módulo no tiene textos que vea una persona: los nombres de los stickers viven en el editor (`bib.sticker_<id>`)."""
import json
import math
import os
import random
import re
from functools import lru_cache

from PIL import Image, ImageDraw

CATEGORIAS = ("flechas", "marcas", "formas")
IDS = ("flecha_recta", "flecha_curva", "flecha_mano", "flecha_abajo",
       "circulo_mano", "subrayado_mano", "tachado_mano", "chulo", "equis", "exclamacion",
       "estallido", "estrella", "estrellas_5", "corazon", "etiqueta", "cinta", "circulo", "burbuja", "rayo",
       "destellos")
CATEGORIA_DE = {**{i: "flechas" for i in IDS[:4]}, **{i: "marcas" for i in IDS[4:10]}, **{i: "formas" for i in IDS[10:]}}
LADO = 512            # lado mayor de cada PNG
SUPER = 4             # se dibuja a 4× y se reduce: bordes suaves
AIRE = 8              # píxeles transparentes entre la forma y el borde del PNG
COLORES = {"flechas": "#FFD400", "formas": "#FFD400", "marcas": "#E11D48"}   # el de entrada; el tinte lo cambia
CARPETA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "stickers")
ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_VERSION = 1

# Semilla fija de cada dibujo «a mano»: el temblor es siempre el mismo. Cambiar una es cambiar ese dibujo.
SEMILLAS = {"flecha_mano": 11, "circulo_mano": 23, "subrayado_mano": 35, "tachado_mano": 47, "chulo": 59,
            "equis": 71, "exclamacion": 83, "estallido": 97}


# --- El pincel: una máscara de 255 = tinta, en unidades de un espacio de 1000×1000 ---

class _Pincel:
    def __init__(self):
        self.lado = LADO * SUPER
        self.u = self.lado / 1000.0
        self.mascara = Image.new("L", (self.lado, self.lado), 0)
        self.d = ImageDraw.Draw(self.mascara)

    def _px(self, puntos):
        return [(x * self.u, y * self.u) for x, y in puntos]

    def poligono(self, puntos, tinta=255):
        self.d.polygon(self._px(puntos), fill=tinta)

    def disco(self, cx, cy, r, tinta=255):
        self.d.ellipse([(cx - r) * self.u, (cy - r) * self.u, (cx + r) * self.u, (cy + r) * self.u], fill=tinta)

    def trazo(self, puntos, ancho, tinta=255, cerrado=False):
        """Una línea de ancho parejo con círculos en las puntas y en cada vértice (juntas redondas)."""
        pts = list(puntos) + ([puntos[0]] if cerrado else [])
        self.d.line(self._px(pts), fill=tinta, width=max(1, int(round(ancho * self.u))), joint="curve")
        for x, y in pts:
            self.disco(x, y, ancho / 2.0, tinta)

    def redondeado(self, puntos, radio, tinta=255):
        """Un polígono con las esquinas redondeadas (lo agranda `radio` por cada lado): se pinta el relleno y un
        trazo de ancho `2·radio` por todo su contorno."""
        self.poligono(puntos, tinta)
        self.trazo(puntos, 2 * radio, tinta, cerrado=True)

    def caja_redondeada(self, x0, y0, x1, y1, radio, tinta=255):
        self.d.rounded_rectangle([x0 * self.u, y0 * self.u, x1 * self.u, y1 * self.u],
                                 radius=radio * self.u, fill=tinta)


# --- Geometría ---

def _girar(puntos, grados, centro=(500, 500)):
    a = math.radians(grados)
    c, s = math.cos(a), math.sin(a)
    cx, cy = centro
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in puntos]


def _catmull(puntos, pasos=14):
    """Una curva suave (Catmull-Rom) que pasa por todos los puntos de control."""
    if len(puntos) < 3:
        return list(puntos)
    p = [puntos[0]] + list(puntos) + [puntos[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for k in range(pasos):
            t = k / pasos
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(tuple(puntos[-1]))
    return out


def _temblor(rng, puntos, amp):
    return [(x + rng.uniform(-amp, amp), y + rng.uniform(-amp, amp)) for x, y in puntos]


def _mano(pincel, rng, puntos, ancho, amp=9.0, pasos=14):
    """Un trazo a mano: puntos de control con temblor, suavizados, de ancho parejo. Devuelve los puntos de control
    ya movidos (la punta de una flecha sale del último)."""
    movidos = _temblor(rng, puntos, amp)
    pincel.trazo(_catmull(movidos, pasos), ancho)
    return movidos


def _estrella(cx, cy, radio, interior, puntas=5, giro=-90.0):
    pts = []
    for i in range(puntas * 2):
        r = radio if i % 2 == 0 else interior
        a = math.radians(giro + i * 180.0 / puntas)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _destello(cx, cy, radio, potencia=2.6, n=180):
    """Una estrella de cuatro puntas de lados cóncavos (una astroide más o menos gorda)."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        pts.append((cx + radio * math.copysign(abs(c) ** potencia, c), cy + radio * math.copysign(abs(s) ** potencia, s)))
    return pts


def _cabeza_abierta(pincel, rng, punta, direccion, largo, ancho, abertura=32.0, amp=7.0):
    """Las dos rayas de una punta de flecha dibujada a mano, hacia atrás desde `punta`."""
    for lado in (-1, 1):
        a = math.radians(180 + lado * abertura)
        dx, dy = direccion
        vx = dx * math.cos(a) - dy * math.sin(a)
        vy = dx * math.sin(a) + dy * math.cos(a)
        largo_ = largo * rng.uniform(0.94, 1.06)
        fin = (punta[0] + vx * largo_, punta[1] + vy * largo_)
        medio = ((punta[0] + fin[0]) / 2 + rng.uniform(-amp, amp), (punta[1] + fin[1]) / 2 + rng.uniform(-amp, amp))
        pincel.trazo(_catmull([punta, medio, fin], 10), ancho)


# --- Los 20 dibujos ---

def _flecha_recta(p, rng):
    p.redondeado([(60, 425), (610, 425), (610, 210), (940, 500), (610, 790), (610, 575), (60, 575)], 22)


def _flecha_curva(p, rng):
    cx, cy, r = 480, 640, 330
    inicio, fin = 184.0, 350.0
    arco = []
    for i in range(61):
        a = math.radians(inicio + (fin - inicio) * i / 60)
        arco.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    p.trazo(arco, 112)
    a = math.radians(fin)
    tx, ty = -math.sin(a), math.cos(a)                  # hacia donde sigue el arco
    nx, ny = -ty, tx
    base = (cx + r * math.cos(a), cy + r * math.sin(a))
    ala, largo = 175, 215
    p.redondeado([(base[0] + nx * ala, base[1] + ny * ala), (base[0] + tx * largo, base[1] + ty * largo),
                  (base[0] - nx * ala, base[1] - ny * ala)], 14)


def _flecha_mano(p, rng):
    ruta = [(90, 840), (270, 680), (470, 510), (680, 330), (880, 160)]
    pts = _mano(p, rng, ruta, 66)
    dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
    n = math.hypot(dx, dy)
    _cabeza_abierta(p, rng, pts[-1], (dx / n, dy / n), 300, 66)


def _flecha_abajo(p, rng):
    p.redondeado([(380, 60), (620, 60), (620, 520), (850, 520), (500, 960), (150, 520), (380, 520)], 36)


def _circulo_mano(p, rng):
    n = 16
    pts = []
    for i in range(n + 1):
        t = i / n
        a = math.radians(-120 + 395 * t)
        k = 0.86 + 0.33 * t ** 1.6                               # una espiral suave: el final pasa por fuera del principio
        pts.append((500 + 410 * k * math.cos(a), 500 + 330 * k * math.sin(a)))
    giro = math.radians(-8)
    pts = [(500 + (x - 500) * math.cos(giro) - (y - 500) * math.sin(giro),
            500 + (x - 500) * math.sin(giro) + (y - 500) * math.cos(giro)) for x, y in pts]
    _mano(p, rng, pts, 62, amp=6.0, pasos=12)


def _subrayado_mano(p, rng):
    _mano(p, rng, [(40, 300), (260, 282), (520, 298), (780, 276), (960, 290)], 70, amp=8.0)
    _mano(p, rng, [(190, 540), (420, 522), (660, 542), (870, 526)], 70, amp=8.0)


def _tachado_mano(p, rng):
    """Un garabato de ida y vuelta, apretado: se lee «tachado» aunque no haya nada debajo."""
    vertices = _temblor(rng, [(60, 120), (940, 150), (70, 235), (930, 265), (80, 350), (920, 380)], 8.0)
    for a, b in zip(vertices, vertices[1:]):
        medio = ((a[0] + b[0]) / 2 + rng.uniform(-8, 8), (a[1] + b[1]) / 2 + rng.uniform(-10, 10))
        p.trazo(_catmull([a, medio, b], 12), 58)


def _chulo(p, rng):
    corto = _catmull(_temblor(rng, [(80, 520), (190, 640), (330, 800)], 8), 12)
    largo = _catmull(_temblor(rng, [(330, 800), (480, 590), (700, 330), (940, 120)], 8), 12)
    p.trazo(corto + largo[1:], 104)


def _equis(p, rng):
    _mano(p, rng, [(140, 130), (380, 410), (620, 600), (870, 870)], 92, amp=10.0)
    _mano(p, rng, [(870, 130), (630, 390), (390, 610), (140, 880)], 92, amp=10.0)


def _exclamacion(p, rng):
    _mano(p, rng, [(520, 125), (510, 295), (495, 455), (480, 610)], 170, amp=6.0, pasos=10)
    p.disco(468 + rng.uniform(-4, 4), 860, 98)


def _estallido(p, rng):
    n = 14
    pts = []
    for i in range(n * 2):
        a = math.radians(-90 + i * 180.0 / n)
        if i % 2 == 0:
            r = 480 * rng.uniform(0.92, 1.0)
        else:
            r = 330 * rng.uniform(0.94, 1.04)
        pts.append((500 + r * math.cos(a), 500 + r * math.sin(a)))
    p.redondeado(pts, 14)


def _estrella_f(p, rng):
    p.redondeado(_estrella(500, 535, 440, 190), 26)


def _estrellas_5(p, rng):
    for i in range(5):
        p.redondeado(_estrella(100 + i * 200, 500, 88, 37), 6)


def _corazon(p, rng):
    pts = []
    for i in range(240):
        t = 2 * math.pi * i / 240
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((500 + x * 29.5, 470 - y * 29.5))
    p.poligono(pts)


def _etiqueta(p, rng):
    cuerpo = [(60, 500), (290, 250), (940, 250), (940, 750), (290, 750)]
    giro, k = -28.0, 0.84                                   # girada, y achicada para que no se salga del lienzo

    def _poner(puntos):
        return _girar([(500 + (x - 500) * k, 500 + (y - 500) * k) for x, y in puntos], giro)
    p.redondeado(_poner(cuerpo), 34 * k)
    p.disco(*_poner([(262, 500)])[0], 62 * k, tinta=0)                    # el agujero del hilo
    interior = [(500 + (x - 500) * 0.82, 500 + (y - 500) * 0.82) for x, y in cuerpo]
    p.trazo(_poner(interior), 16 * k, tinta=0, cerrado=True)              # el filete


def _cinta(p, rng):
    cola_izq = [(30, 430), (300, 430), (300, 740), (30, 740), (115, 585)]
    cola_der = [(970, 430), (700, 430), (700, 740), (970, 740), (885, 585)]
    p.poligono(cola_izq)
    p.poligono(cola_der)
    p.poligono([(185, 290), (815, 290), (815, 640), (185, 640)], tinta=0)   # el hueco que separa el centro de las colas
    p.poligono([(215, 320), (785, 320), (785, 610), (215, 610)])


def _circulo_f(p, rng):
    p.disco(500, 500, 470)
    p.d.ellipse([(500 - 385) * p.u, (500 - 385) * p.u, (500 + 385) * p.u, (500 + 385) * p.u],
                outline=0, width=int(round(24 * p.u)))


def _burbuja(p, rng):
    p.caja_redondeada(40, 90, 960, 700, 210)
    p.redondeado([(230, 640), (230, 930), (520, 680)], 20)
    for x in (300, 500, 700):
        p.disco(x, 395, 58, tinta=0)


def _rayo(p, rng):
    p.redondeado([(590, 40), (210, 560), (450, 560), (330, 960), (790, 400), (545, 400), (700, 40)], 18)


def _destellos(p, rng):
    p.poligono(_destello(400, 580, 360))
    p.poligono(_destello(810, 220, 175))
    p.poligono(_destello(800, 800, 115))


_DIBUJOS = {
    "flecha_recta": _flecha_recta, "flecha_curva": _flecha_curva, "flecha_mano": _flecha_mano,
    "flecha_abajo": _flecha_abajo, "circulo_mano": _circulo_mano, "subrayado_mano": _subrayado_mano,
    "tachado_mano": _tachado_mano, "chulo": _chulo, "equis": _equis, "exclamacion": _exclamacion,
    "estallido": _estallido, "estrella": _estrella_f, "estrellas_5": _estrellas_5, "corazon": _corazon,
    "etiqueta": _etiqueta, "cinta": _cinta, "circulo": _circulo_f, "burbuja": _burbuja, "rayo": _rayo,
    "destellos": _destellos,
}


# --- De la máscara al PNG ---

def _acabar(mascara, id_=""):
    """Recorta lo transparente, reduce con LANCZOS para que el lado mayor mida `LADO - 2·AIRE` y deja `AIRE` px de
    margen: el lado mayor del PNG mide exactamente `LADO`. RGB blanco en todo píxel. Un dibujo que toca el borde del
    lienzo está cortado (se salió del espacio de 1000×1000): se rechaza en vez de entregar una forma mocha."""
    caja = mascara.getbbox()
    if caja is None or caja[0] <= 0 or caja[1] <= 0 or caja[2] >= mascara.size[0] or caja[3] >= mascara.size[1]:
        raise ValueError(f"el sticker {id_} está vacío o se sale del lienzo: {caja}")
    recorte = mascara.crop(caja)
    ancho, alto = recorte.size
    escala = (LADO - 2 * AIRE) / float(max(ancho, alto))
    nuevo = (max(1, int(round(ancho * escala))), max(1, int(round(alto * escala))))
    chico = recorte.resize(nuevo, Image.LANCZOS)
    alfa = Image.new("L", (nuevo[0] + 2 * AIRE, nuevo[1] + 2 * AIRE), 0)
    alfa.paste(chico, (AIRE, AIRE))
    blanco = Image.new("L", alfa.size, 255)
    return Image.merge("RGBA", (blanco, blanco, blanco, alfa))


def dibujar(id_):
    """El PNG (RGBA, blanco sobre transparente) del sticker `id_`."""
    pincel = _Pincel()
    _DIBUJOS[id_](pincel, random.Random(SEMILLAS.get(id_, 1)))
    return _acabar(pincel.mascara, id_)


def generar(carpeta=CARPETA):
    """Dibuja los 20 stickers, los guarda como `<id>.png` en `carpeta` con `stickers.json` y devuelve el manifiesto.
    Es determinista: misma versión de Pillow, mismos píxeles."""
    os.makedirs(carpeta, exist_ok=True)
    fichas = []
    for id_ in IDS:
        imagen = dibujar(id_)
        archivo = f"{id_}.png"
        imagen.save(os.path.join(carpeta, archivo), format="PNG", optimize=True)
        categoria = CATEGORIA_DE[id_]
        fichas.append({"id": id_, "categoria": categoria, "archivo": archivo, "ancho": imagen.size[0],
                       "alto": imagen.size[1], "color": COLORES[categoria]})
    manifiesto_ = {"version": _VERSION, "stickers": fichas}
    with open(os.path.join(carpeta, "stickers.json"), "w", encoding="utf-8") as f:
        json.dump(manifiesto_, f, ensure_ascii=False, indent=1)
        f.write("\n")
    manifiesto.cache_clear()
    return manifiesto_


# --- Lo que usan la ruta y la biblioteca ---

@lru_cache(maxsize=1)
def manifiesto():
    """`static/stickers/stickers.json` (se lee una vez; no se modifica lo que devuelve)."""
    with open(os.path.join(CARPETA, "stickers.json"), encoding="utf-8") as f:
        return json.load(f)


def por_id(id_):
    """La ficha del sticker `id_`, o None si no tiene la forma de un id o no está en el manifiesto. Es lo único que
    deja pasar un id que viene de una URL: lo que no está aquí nunca llega al disco."""
    if not isinstance(id_, str) or not ID_RE.fullmatch(id_):
        return None
    return next((s for s in manifiesto()["stickers"] if s["id"] == id_), None)


def ruta(id_):
    """La ruta del PNG de un sticker del manifiesto; `KeyError` si el id no existe."""
    ficha = por_id(id_)
    if ficha is None:
        raise KeyError(id_)
    return os.path.join(CARPETA, ficha["archivo"])


if __name__ == "__main__":
    generar()

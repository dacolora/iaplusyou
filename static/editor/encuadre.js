// Encuadre de un clip de la pista principal (editor, capa 5b, spec D4-D7):
// espejo de final_edition/encuadre.py — ver ese módulo para la explicación
// completa (qué parte del cuadro se ve y cómo se compone cuando no coincide
// con el lienzo; `caja`/`fondo`/`ajusteAutomatico` son la misma fórmula,
// las mismas operaciones de coma flotante en el mismo orden, que el
// servidor — tests/fixtures/encuadre_casos.json es la tabla de paridad).
// Puro: sin DOM, sin red. Sin textos visibles: no importa textos.js.
export const MODOS = ["llenar", "ajustar"];
export const ZOOM_MIN = 1.0;
export const ZOOM_MAX = 4.0;
export const DEFECTO = {"modo": "llenar", "zoom": 1.0, "x": 0.5, "y": 0.5};
// D5: el lienzo del fondo desenfocado es 1/10 del lienzo real.
export const FONDO_DIVISOR = 10;
// D7: la proporción del clip difiere de la del lienzo en más de un 25 %
// (5/4) cuando `UMBRAL_AJUSTE[1]·w·H > UMBRAL_AJUSTE[0]·h·W` o
// `UMBRAL_AJUSTE[0]·w·H < UMBRAL_AJUSTE[1]·h·W` — enteros, sin error de
// coma flotante.
export const UMBRAL_AJUSTE = [5, 4];
// Solo navegador: ctx.filter = "blur(5px)" (D5).
export const FONDO_SIGMA_PX = 5;

// El entero PAR más cercano a `v` (yuv420p: medidas y desplazamientos
// pares); un `v` a mitad de camino entre dos pares (un entero impar)
// redondea hacia arriba. Misma cuenta, en el mismo orden, que
// encuadre.par en Python.
export function par(v) {
  return Math.floor(v / 2 + 0.5) * 2;
}

// El encuadre con sus valores por defecto rellenados (D4); `null`/`{}` dan
// DEFECTO tal cual.
export function completo(enc) {
  return { ...DEFECTO, ...(enc || {}) };
}

// `true` si `enc` (ausente, `null` o un objeto) equivale al encuadre por
// defecto — llenar, centrado, sin acercar.
export function esDefecto(enc) {
  if (!enc) return true;
  const c = completo(enc);
  return c.modo === DEFECTO.modo && c.zoom === DEFECTO.zoom && c.x === DEFECTO.x && c.y === DEFECTO.y;
}

function redondear4(v) {
  return Math.round(v * 10000) / 10000;
}

// El encuadre listo para guardar (lo que escribe un arrastre o el
// deslizador de zoom): completo, `zoom` acotado a 1–4, `x`/`y` a 0–1,
// redondeado a 4 decimales; igual al defecto -> `null` (como
// `documento.validar` del lado del servidor, que es quien de verdad
// decide si el documento es válido). Un `modo` fuera de MODOS lo decide
// quien llama — esta función solo limpia los números, no valida.
export function limpio(enc) {
  const c = completo(enc);
  const zoom = redondear4(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number(c.zoom))));
  const x = redondear4(Math.min(1, Math.max(0, Number(c.x))));
  const y = redondear4(Math.min(1, Math.max(0, Number(c.y))));
  const salida = { modo: c.modo, zoom, x, y };
  return esDefecto(salida) ? null : salida;
}

// La caja del cuadro escalado dentro del lienzo (D4): `sw`/`sh` su tamaño
// en píxeles, `px`/`py` dónde queda su esquina superior izquierda (pueden
// ser negativos o, en «ajustar», positivos — overlay/crop los usan tal
// cual). `ancho`/`alto` son las medidas que se VEN del clip; `lienzoW`/
// `lienzoH`, el formato de la edición. `0 − par(...)` (nunca `-par(...)`)
// para que un resultado en 0 nunca sea `-0`.
export function caja(ancho, alto, lienzoW, lienzoH, enc) {
  const c = completo(enc);
  const { modo, zoom, x, y } = c;
  const w = ancho, h = alto, W = lienzoW, H = lienzoH;
  const mandaElAlto = (w * H >= h * W) === (modo === "llenar");
  let sw, sh;
  if (mandaElAlto) {
    sh = par(H * zoom);
    sw = par((w * sh) / h);
  } else {
    sw = par(W * zoom);
    sh = par((h * sw) / w);
  }
  const px = 0 - par((sw - W) * x);
  const py = 0 - par((sh - H) * y);
  return { sw, sh, px, py };
}

// El lienzo chico del fondo desenfocado de «ajustar» (D5): par(W/10),
// par(H/10).
export function fondo(lienzoW, lienzoH) {
  return [par(lienzoW / FONDO_DIVISOR), par(lienzoH / FONDO_DIVISOR)];
}

// `{modo: "ajustar"}` si la proporción de `ancho×alto` difiere de la del
// lienzo en más de un 25 % (D7); si no, `null` (sin encuadre: llena
// igual). Frontera incluida en «no hace falta» (exactamente 25 % no
// ajusta).
export function ajusteAutomatico(ancho, alto, lienzoW, lienzoH) {
  const [mayor, menor] = UMBRAL_AJUSTE;
  const w = ancho, h = alto, W = lienzoW, H = lienzoH;
  if (menor * w * H > mayor * h * W || mayor * w * H < menor * h * W) return { modo: "ajustar" };
  return null;
}

// Solo navegador (sin espejo en Python: el render aplica `zoompan` directo
// sobre el filtergraph, nunca sobre un rectángulo ya compuesto). El
// rectángulo `{x, y, w, h}` (la caja de D4, o `{0, 0, W, H}` para el fondo
// de D5) con el zoom lento acercando hacia el CENTRO del lienzo — como
// `zoompan` — y, en una transición «deslizar», el desplazamiento `dx`
// (fracción del ancho del lienzo, de tiempo.principalEn). `zoom` 1 y `dx` 0
// devuelven el mismo rectángulo.
export function rectConZoom({ x, y, w, h }, zoom, dx, lienzoW, lienzoH) {
  const W = lienzoW, H = lienzoH;
  return {
    x: W / 2 + (x - W / 2) * zoom + dx * W,
    y: H / 2 + (y - H / 2) * zoom,
    w: w * zoom,
    h: h * zoom,
  };
}

// ---- Mover y acercar sobre el video (D8, Tarea 7; solo navegador: el
// render recibe el encuadre ya guardado, nunca un arrastre) ----

const acotar = (v, min, max) => Math.min(max, Math.max(min, v));

// Un eje del arrastre: `margen` es lo que el cuadro escalado pasa del
// lienzo en ese eje (`sw − W`; negativo en «ajustar», donde el cuadro es más
// chico y se mueve DENTRO del lienzo). Con margen 0 el eje no se mueve ni
// pega al centro (no hay nada que mover).
function ejeArrastre(v, d, margen, iman) {
  if (margen === 0) return { v, guia: false };
  const nuevo = acotar(v - d / margen, 0, 1);
  if (Math.abs((nuevo - 0.5) * margen) < iman) return { v: 0.5, guia: true };
  return { v: nuevo, guia: false };
}

// La imagen sigue al dedo: un arrastre de (dxPx, dyPx) px del LIENZO desde
// donde estaba `enc` mueve el cuadro escalado lo mismo (con `c = caja(…)`,
// `x' = x − dx / (c.sw − W)`, acotado a 0–1; igual en `y`). Imán al centro:
// a menos de `iman` px del lienzo del cuadro centrado pega en 0,5 y lo dice
// en `guias` (vertical = el eje x, como las capas). A 4 decimales. `medidas`:
// [ancho, alto] que se VEN del clip.
export function moverEncuadre(enc, [w, h], lienzoW, lienzoH, dxPx, dyPx, { iman = 12 } = {}) {
  const c0 = completo(enc);
  const c = caja(w, h, lienzoW, lienzoH, c0);
  const ex = ejeArrastre(Number(c0.x), dxPx, c.sw - lienzoW, iman);
  const ey = ejeArrastre(Number(c0.y), dyPx, c.sh - lienzoH, iman);
  return { x: redondear4(ex.v), y: redondear4(ey.v), guias: { vertical: ex.guia, horizontal: ey.guia } };
}

// El asa de la esquina acerca o aleja: `zoom0 · distancia(centro, asa0 + d)
// / distancia(centro, asa0)`, con el centro del LIENZO (el zoom de D4 crece
// desde ahí cuando el cuadro está centrado), acotado a ZOOM_MIN–ZOOM_MAX y a
// 4 decimales. El arrastre no pasa del centro: más allá la distancia
// volvería a crecer y el cuadro se agrandaría al revés (como
// seleccion.escalarDesdeAsa).
export function zoomEncuadre(enc, asa0, dxPx, dyPx, lienzoW, lienzoH) {
  const zoom0 = Number(completo(enc).zoom);
  const vx = asa0.x - lienzoW / 2;
  const vy = asa0.y - lienzoH / 2;
  const distancia = Math.hypot(vx, vy);
  if (!distancia) return redondear4(acotar(zoom0, ZOOM_MIN, ZOOM_MAX));
  const hastaCentro = (v, d) => (v > 0 ? Math.max(d, -v) : v < 0 ? Math.min(d, -v) : d);
  const dx = hastaCentro(vx, dxPx);
  const dy = hastaCentro(vy, dyPx);
  return redondear4(acotar(zoom0 * Math.hypot(vx + dx, vy + dy) / distancia, ZOOM_MIN, ZOOM_MAX));
}

// El rectángulo del cuadro colocado (la caja de D4) recortado al lienzo:
// lo que se ve del clip, `{x, y, ancho, alto}` en px del lienzo — la caja de
// selección del clip de la principal. En «llenar» es el lienzo entero. Sin
// medidas (el cuadro todavía no cargó) no se sabe: el lienzo entero.
export function cajaVisible(enc, medidas, lienzoW, lienzoH) {
  const [w, h] = medidas ?? [0, 0];
  if (!(w > 0) || !(h > 0)) return { x: 0, y: 0, ancho: lienzoW, alto: lienzoH };
  const { sw, sh, px, py } = caja(w, h, lienzoW, lienzoH, enc);
  const x = Math.max(0, px);
  const y = Math.max(0, py);
  return { x, y, ancho: Math.min(lienzoW, px + sw) - x, alto: Math.min(lienzoH, py + sh) - y };
}

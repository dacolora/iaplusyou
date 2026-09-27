// Medidas del texto libre (spec editor §1.1): espejo de las fórmulas de
// final_edition/rasterizar.png_texto. Tamaños, grosor, sombra, radio y
// relleno son fracción de la ALTURA; ancho_max y fondo.ancho, del ANCHO. La
// caja no se recorta al contenido: es la que geometria.caja coloca.
import { FORMATOS } from "./formatos.js";
import { redondearPar } from "./numeros.js";

export const MARGEN_PX = 4;       // rasterizar.MARGEN_PX
export const TAMANO_MIN_PX = 8;   // rasterizar.TAMANO_MIN_PX

const px = (fraccion, base) => redondearPar(Number(fraccion || 0) * base);

// Ajuste voraz por palabras (rasterizar.ajustar_lineas): línea nueva cuando
// la medida superaría el ancho; una palabra más ancha va sola; sin ancho
// cada párrafo es una línea; los saltos explícitos se respetan.
export function ajustarLineas(texto, anchoMaxPx, medir) {
  const lineas = [];
  for (const parrafo of String(texto ?? "").split("\n")) {
    let actual = "";
    for (const palabra of parrafo.split(/\s+/).filter(Boolean)) {
      const candidata = `${actual} ${palabra}`.trim();
      if (actual && anchoMaxPx && medir(candidata) > anchoMaxPx) {
        lineas.push(actual);
        actual = palabra;
      } else {
        actual = candidata;
      }
    }
    lineas.push(actual);
  }
  return lineas.length ? lineas : [""];
}

export function medidasTexto(estilo, formato) {
  const [anchoL, altoL] = FORMATOS[formato];
  const tam = Math.max(TAMANO_MIN_PX, px(estilo.tamano ?? 0.04, altoL));
  const f = estilo.fondo;
  return {
    tam,
    espaciado: px(Number(estilo.interlineado || 1.1) - 1, tam),
    grosor: estilo.contorno ? px(estilo.contorno.grosor, altoL) : 0,
    sdx: estilo.sombra ? px(estilo.sombra.dx, altoL) : 0,
    sdy: estilo.sombra ? px(estilo.sombra.dy, altoL) : 0,
    padX: f ? px(f.relleno_x, altoL) : 0,
    padY: f ? px(f.relleno_y, altoL) : 0,
    anchoMaxPx: estilo.ancho_max ? px(estilo.ancho_max, anchoL) : null,
    fondoAnchoPx: f && f.ancho ? px(f.ancho, anchoL) : 0,
    radio: f ? px(f.radio, altoL) : 0,
  };
}

// Caja del PNG a partir del bloque de texto medido (tw × th, ya con el
// grosor del contorno): relleno del fondo, ancho mínimo del fondo, margen
// para contorno y sombra.
export function cajaTexto(m, tw, th) {
  let cajaW = tw + 2 * m.padX;
  if (m.fondoAnchoPx) cajaW = Math.max(cajaW, m.fondoAnchoPx);
  const cajaH = th + 2 * m.padY;
  const margen = MARGEN_PX + Math.max(Math.abs(m.sdx), Math.abs(m.sdy));
  const radio = Math.min(m.radio, Math.floor(cajaH / 2), Math.floor(cajaW / 2));
  return { cajaW, cajaH, margen, radio, ancho: Math.trunc(cajaW + 2 * margen), alto: Math.trunc(cajaH + 2 * margen) };
}

// '#RRGGBB' | '#RRGGBBAA' → rgba(); `opacidad` multiplica el alfa
// (rasterizar.color).
export function colorCss(hex, opacidad = 1) {
  const v = String(hex || "#FFFFFF").replace("#", "");
  const r = parseInt(v.slice(0, 2), 16);
  const g = parseInt(v.slice(2, 4), 16);
  const b = parseInt(v.slice(4, 6), 16);
  const a = (v.length === 8 ? parseInt(v.slice(6, 8), 16) / 255 : 1) * Math.max(0, Math.min(1, Number(opacidad)));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

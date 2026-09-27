// Redondeo al par: el round() de Python (round(2.5) == 2). Donde el servidor
// usa round() (rasterizar._px, formatear_precio, el \k de los subtítulos, la
// n del Ken Burns) el navegador usa esto para llegar al mismo número.
export function redondearPar(v) {
  const piso = Math.floor(v);
  const resto = v - piso;
  if (resto > 0.5) return piso + 1;
  if (resto < 0.5) return piso;
  return piso % 2 === 0 ? piso : piso + 1;
}

// Espejo de final_edition/tipos.formatear_precio (tabla compartida en
// tests/fixtures/precios_casos.json). El precio de un país es el número
// escrito para ese país: aquí solo se le da formato, nunca se convierte.
import { redondearPar } from "./numeros.js";
import { t } from "./textos.js";

export const SIMBOLOS = { CO: "$", MX: "$", US: "$", ES: "€", BR: "R$", AR: "$", CL: "$", PE: "S/", NO: "kr", SE: "kr" };
const CORONAS = new Set(["NO", "SE"]);
const SIN_DECIMALES = new Set(["CO", "AR", "CL"]);

function miles(digitos, separador) {
  return digitos.replace(/\B(?=(\d{3})+(?!\d))/g, separador);
}

// Centavos redondeados como f"{v:.2f}" de Python: sobre el valor binario
// EXACTO (toFixed(20) lo expande) y al par solo en un empate verdadero.
function centavos(valor) {
  const [ent, dec] = Math.abs(valor).toFixed(20).split(".");
  let n = BigInt(ent + dec.slice(0, 2));
  const resto = dec.slice(2);
  const empate = "5" + "0".repeat(resto.length - 1);
  if (resto > empate || (resto === empate && n % 2n === 1n)) n += 1n;
  const s = n.toString().padStart(3, "0");
  return [s.slice(0, -2), s.slice(-2)];
}

export function formatearPrecio(valor, pais) {
  const simbolo = SIMBOLOS[pais];
  if (simbolo === undefined) throw new Error(t("precio.sin_formato", { pais }));
  if (SIN_DECIMALES.has(pais)) {
    // El signo sale del entero YA redondeado (como Python: int(round(valor))
    // nunca es "-0"), no del valor original.
    const entero = redondearPar(valor);
    const signo = entero < 0 ? "-" : "";
    return `${simbolo} ${signo}${miles(String(Math.abs(entero)), ".")}`;
  }
  if (CORONAS.has(pais)) {
    // Coronas: miles con espacio, símbolo detrás; sin decimales si el valor es entero, con coma si no.
    const neg = valor < 0 ? "-" : "";
    if (Number.isInteger(valor)) return `${neg}${miles(String(Math.abs(valor)), " ")} ${simbolo}`;
    const [e, d] = centavos(valor);
    return `${neg}${miles(e, " ")},${d} ${simbolo}`;
  }
  // Aquí el signo sí sale del valor original (como f"{valor:,.2f}" de Python):
  // -0.001 en US da "$-0.00", con el signo aunque los dígitos sean cero.
  const signo = valor < 0 ? "-" : "";
  const [ent, dec] = centavos(valor);
  if (pais === "BR") return `${simbolo} ${signo}${miles(ent, ".")},${dec}`;
  if (pais === "ES") return `${signo}${miles(ent, ".")},${dec} ${simbolo}`;
  return `${simbolo}${signo}${miles(ent, ",")}.${dec}`;
}

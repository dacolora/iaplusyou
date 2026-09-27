// Espejo de final_edition/tipos.formatear_precio (tabla compartida en
// tests/fixtures/precios_casos.json). El precio de un país es el número
// escrito para ese país: aquí solo se le da formato, nunca se convierte.
import { redondearPar } from "./numeros.js";

export const SIMBOLOS = { CO: "$", MX: "$", US: "$", ES: "€", BR: "R$", AR: "$", CL: "$", PE: "S/" };
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
  if (simbolo === undefined) throw new Error(`No sé formatear precios de ${pais}.`);
  if (SIN_DECIMALES.has(pais)) return `${simbolo} ${miles(String(redondearPar(valor)), ".")}`;
  const [ent, dec] = centavos(valor);
  if (pais === "BR") return `${simbolo} ${miles(ent, ".")},${dec}`;
  if (pais === "ES") return `${miles(ent, ".")},${dec} ${simbolo}`;
  return `${simbolo}${miles(ent, ",")}.${dec}`;
}

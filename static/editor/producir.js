// «Producir» desde el editor (capa 4c): qué decir con la respuesta del
// servidor. Puro, sin DOM (lo prueba tests/js/producir.test.mjs); la página
// (pagina_editor.js) hace el POST y pinta lo que esto devuelve.
//
// Con la sesión vencida el POST termina en la página de entrar (200, HTML):
// antes eso se leía como «Esos destinos ya se estaban produciendo.» aunque no
// se hubiera producido nada.
import { MENSAJE_SESION, sesionTerminada } from "./guardado.js";

// `r`: la Response (status, ok, redirected, headers); `j`: su JSON, o null.
// Devuelve {que: "error", texto} | {que: "reemplazo", destinos} |
// {que: "hecho", texto, url}.
export function respuestaProducir(r, j) {
  if (sesionTerminada(r)) return { que: "error", texto: MENSAJE_SESION };
  if (r.status === 409 && Array.isArray(j?.reemplazos) && j.reemplazos.length) return { que: "reemplazo", destinos: j.reemplazos };
  if (!r.ok) return { que: "error", texto: [j?.error || `No se pudo producir (error ${r.status}).`, ...(j?.problemas ?? [])].join(" ") };
  if (!Array.isArray(j?.producidas)) {
    return { que: "error", texto: "No se pudo producir: el servidor no respondió como se esperaba. Vuelve a intentar." };
  }
  const n = j.producidas.filter((p) => p.encolada).length;
  return {
    que: "hecho",
    texto: n ? `Produciendo ${n} final${n === 1 ? "" : "es"}. Las vas a ver en Final edition cuando terminen.`
      : "Esos destinos ya se estaban produciendo.",
    url: j.url ?? null,
  };
}

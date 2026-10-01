// «Producir» desde el editor (capa 4c): qué decir con la respuesta del
// servidor. Puro, sin DOM (lo prueba tests/js/producir.test.mjs); la página
// (pagina_editor.js) hace el POST y pinta lo que esto devuelve.
//
// Con la sesión vencida el POST termina en la página de entrar (redirigido a
// /login, 200, HTML): antes eso se leía como «Esos destinos ya se estaban
// produciendo.» aunque no se hubiera producido nada. Un 5xx no es la sesión
// (guardado.sesionTerminada).
import { mensajeSesion, sesionTerminada } from "./guardado.js";
import { t } from "./textos.js";

// `r`: la Response (status, ok, redirected, headers); `j`: su JSON, o null.
// Devuelve {que: "error", texto} | {que: "reemplazo", destinos} |
// {que: "hecho", texto, url}.
export function respuestaProducir(r, j) {
  if (sesionTerminada(r)) return { que: "error", texto: mensajeSesion() };
  if (r.status === 409 && Array.isArray(j?.reemplazos) && j.reemplazos.length) return { que: "reemplazo", destinos: j.reemplazos };
  if (!r.ok) {
    // un 5xx (HTML o no: un 500 de Flask, un 502/504 de nginx) no es la sesión
    const porDefecto = r.status >= 500
      ? t("producir.fallo_servidor", { status: r.status })
      : t("producir.error", { status: r.status });
    return { que: "error", texto: [j?.error || porDefecto, ...(j?.problemas ?? [])].join(" ") };
  }
  if (!Array.isArray(j?.producidas)) {
    return { que: "error", texto: t("producir.respuesta_rara") };
  }
  const n = j.producidas.filter((p) => p.encolada).length;
  return {
    que: "hecho",
    texto: n ? t(n === 1 ? "producir.hecha_una" : "producir.hechas", { n }) : t("producir.ya_estaban"),
    url: j.url ?? null,
  };
}

// Capa 4c (6/10): qué dice «Producir» con cada respuesta del servidor. Con la
// sesión vencida el POST llega a la página de entrar (200, HTML): antes eso
// se leía como «Esos destinos ya se estaban produciendo.»
import { test } from "node:test";
import assert from "node:assert/strict";
import { MENSAJE_SESION } from "../../static/editor/guardado.js";
import { respuestaProducir } from "../../static/editor/producir.js";

const cab = (tipo) => ({ get: (k) => (k.toLowerCase() === "content-type" ? tipo : null) });
const JSON_ = cab("application/json");

test("la página de entrar (redirigida o HTML) es «tu sesión terminó», nunca «ya se estaban produciendo»", () => {
  for (const r of [{ ok: true, status: 200, redirected: true, headers: cab("text/html") },
    { ok: true, status: 200, redirected: false, headers: cab("text/html; charset=utf-8") }]) {
    assert.deepEqual(respuestaProducir(r, null), { que: "error", texto: MENSAJE_SESION });
  }
});

test("lo demás sigue igual: reemplazos, errores con sus problemas y lo que quedó en cola", () => {
  assert.deepEqual(respuestaProducir({ ok: false, status: 409, headers: JSON_ }, { reemplazos: ["es_CO"] }),
    { que: "reemplazo", destinos: ["es_CO"] });
  assert.deepEqual(respuestaProducir({ ok: false, status: 400, headers: JSON_ }, { error: "Hay textos sin traducir.", problemas: ["en_US: falta"] }),
    { que: "error", texto: "Hay textos sin traducir. en_US: falta" });
  assert.deepEqual(respuestaProducir({ ok: false, status: 500, headers: cab("text/html") }, null).que, "error");
  const hecho = respuestaProducir({ ok: true, status: 200, headers: JSON_ },
    { producidas: [{ encolada: true }, { encolada: true }], url: "/cliente/acme#final" });
  assert.deepEqual(hecho, { que: "hecho", texto: "Produciendo 2 finales. Las vas a ver en Final edition cuando terminen.", url: "/cliente/acme#final" });
  assert.equal(respuestaProducir({ ok: true, status: 200, headers: JSON_ }, { producidas: [{ encolada: false }] }).texto,
    "Esos destinos ya se estaban produciendo.");
  // un 200 sin la lista esperada no se lee como «ya se estaban produciendo»
  assert.equal(respuestaProducir({ ok: true, status: 200, headers: JSON_ }, {}).que, "error");
});

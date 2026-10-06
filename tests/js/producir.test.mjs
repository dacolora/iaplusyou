// Capa 4c (6/10): qué dice «Producir» con cada respuesta del servidor. Con la
// sesión vencida el POST llega a la página de entrar (200, HTML): antes eso
// se leía como «Esos destinos ya se estaban produciendo.»
import { test } from "node:test";
import assert from "node:assert/strict";
import { mensajeSesion } from "../../static/editor/guardado.js";
import { respuestaProducir } from "../../static/editor/producir.js";

const cab = (tipo) => ({ get: (k) => (k.toLowerCase() === "content-type" ? tipo : null) });
const JSON_ = cab("application/json");

test("la página de entrar (redirigida o HTML) es «tu sesión terminó», nunca «ya se estaban produciendo»", () => {
  for (const r of [{ ok: true, status: 200, redirected: true, url: "https://app.test/login", headers: cab("text/html") },
    { ok: true, status: 200, redirected: false, headers: cab("text/html; charset=utf-8") }]) {
    assert.deepEqual(respuestaProducir(r, null), { que: "error", texto: mensajeSesion() });
  }
});

test("lo demás sigue igual: reemplazos, errores con sus problemas y lo que quedó en cola", () => {
  assert.deepEqual(respuestaProducir({ ok: false, status: 409, headers: JSON_ }, { reemplazos: ["es_CO"] }),
    { que: "reemplazo", destinos: ["es_CO"] });
  assert.deepEqual(respuestaProducir({ ok: false, status: 400, headers: JSON_ }, { error: "Hay textos sin traducir.", problemas: ["en_US: falta"] }),
    { que: "error", texto: "Hay textos sin traducir. en_US: falta" });
  // un 5xx con HTML (Flask 500, nginx 502 durante un despliegue) no es «tu sesión terminó»
  for (const status of [500, 502]) {
    assert.deepEqual(respuestaProducir({ ok: false, status, redirected: false, headers: cab("text/html") }, null),
      { que: "error", texto: `No se pudo producir: el servidor falló (error ${status}). Vuelve a intentar en un momento.` });
  }
  const hecho = respuestaProducir({ ok: true, status: 200, headers: JSON_ },
    { producidas: [{ encolada: true }, { encolada: true }], url: "/cliente/acme#final" });
  assert.deepEqual(hecho, { que: "hecho", texto: "Produciendo 2 finales. Las vas a ver en Final edition cuando terminen.", url: "/cliente/acme#final" });
  assert.equal(respuestaProducir({ ok: true, status: 200, headers: JSON_ }, { producidas: [{ encolada: false }] }).texto,
    "Esos destinos ya se estaban produciendo.");
  // un 200 sin la lista esperada no se lee como «ya se estaban produciendo»
  assert.equal(respuestaProducir({ ok: true, status: 200, headers: JSON_ }, {}).que, "error");
});

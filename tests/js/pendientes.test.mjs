// El sondeo de las copias livianas: qué respuesta se lee, cuál se reintenta
// y cuál hace rendirse; y qué materiales ya se pueden cambiar.
import { test } from "node:test";
import assert from "node:assert/strict";
import { evaluarRespuesta, INTERVALO_SONDEO_MS, listos, TOPE_SONDEO_MS } from "../../static/editor/pendientes.js";

const resp = (extra = {}, tipo = "application/json") => ({
  ok: true, status: 200, redirected: false, headers: { get: (k) => (k === "content-type" ? tipo : null) }, ...extra,
});

test("una respuesta JSON se lee; un 5xx se reintenta", () => {
  assert.equal(evaluarRespuesta(resp()), "json");
  assert.equal(evaluarRespuesta(resp({}, "application/json; charset=utf-8")), "json");
  assert.equal(evaluarRespuesta(resp({ ok: false, status: 502 })), "reintentar");
});

test("redirección (sesión vencida), HTML o un 4xx: se deja de preguntar", () => {
  assert.equal(evaluarRespuesta(resp({ redirected: true }, "text/html; charset=utf-8")), "parar");
  assert.equal(evaluarRespuesta(resp({}, "text/html")), "parar");
  assert.equal(evaluarRespuesta(resp({ ok: false, status: 404 })), "parar");
  assert.equal(evaluarRespuesta(resp({ ok: false, status: 403 })), "parar");
});

test("listos: los que dejaron de estar pendientes y vienen en la respuesta, aunque falten otros", () => {
  const r = { pendientes: [3], materiales: { 1: { tipo: "video" }, 3: { tipo: "video" } } };
  assert.deepEqual(listos([1, 3], r), [1]);
  assert.deepEqual(listos(["1", "3"], r), [1]);            // las claves del JSON llegan como texto
  assert.deepEqual(listos([1, 2], r), [1], "2 ya no está entre los materiales: no se cambia");
  assert.deepEqual(listos([3], r), []);
});

test("el sondeo tiene tope (unos cinco minutos) y un intervalo menor", () => {
  assert.equal(TOPE_SONDEO_MS, 5 * 60 * 1000);
  assert.ok(INTERVALO_SONDEO_MS > 0 && INTERVALO_SONDEO_MS < TOPE_SONDEO_MS);
});

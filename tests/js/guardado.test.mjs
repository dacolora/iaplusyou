import { test } from "node:test";
import assert from "node:assert/strict";
import { Guardado } from "../../static/editor/guardado.js";

function banco(respuestas) {
  const enviados = [];
  const timers = [];
  const g = new Guardado({
    url: "/e/1", versionN: 3, esperaMs: 1000,
    enviar: async (url, cuerpo) => {
      enviados.push(cuerpo);
      const r = respuestas.shift() ?? { status: 200, cuerpo: { version_n: cuerpo.version_n + 1 } };
      if (r.lanza) throw new Error("red caída");
      return { status: r.status, json: async () => r.cuerpo };
    },
    programar: (fn) => { timers.push(fn); return timers.length; },
    cancelar: (id) => { timers[id - 1] = null; },
  });
  const correrTimers = async () => { const fns = timers.splice(0).filter(Boolean); for (const f of fns) await f(); };
  return { g, enviados, correrTimers };
}

test("junta los cambios seguidos en un solo guardado con la última versión", async () => {
  const { g, enviados, correrTimers } = banco([]);
  g.pedir({ n: 1 });
  g.pedir({ n: 2 });
  assert.equal(g.estado, "pendiente");
  await correrTimers();
  assert.deepEqual(enviados, [{ documento: { n: 2 }, version_n: 3 }]);
  assert.equal(g.estado, "guardado");
  assert.equal(g.versionN, 4);
});

test("un cambio durante un guardado se guarda después, con la versión nueva", async () => {
  const { g, enviados } = banco([]);
  g.pedir({ n: 1 });
  const primero = g.ahora();
  g.pedir({ n: 2 });
  await primero;
  await g.ahora();
  assert.deepEqual(enviados.map((e) => [e.documento.n, e.version_n]), [[1, 3], [2, 4]]);
  assert.equal(g.sinGuardar, false);
});

test("409 deja la edición en conflicto y no vuelve a guardar", async () => {
  const { g, enviados } = banco([{ status: 409, cuerpo: { error: "La edición cambió en otra pestaña; recarga para seguir." } }]);
  g.pedir({ n: 1 });
  await g.ahora();
  assert.equal(g.estado, "conflicto");
  assert.match(g.mensaje, /otra pestaña/);
  g.pedir({ n: 2 });
  await g.ahora();
  assert.equal(enviados.length, 1);
});

test("sin red queda en error y reintenta con el próximo cambio", async () => {
  const { g, enviados } = banco([{ lanza: true }]);
  g.pedir({ n: 1 });
  await g.ahora();
  assert.equal(g.estado, "error");
  assert.ok(g.sinGuardar);
  g.pedir({ n: 2 });
  await g.ahora();
  assert.equal(g.estado, "guardado");
  assert.deepEqual(enviados.map((e) => e.documento.n), [1, 2]);
});

test("400 muestra el motivo del servidor", async () => {
  const { g } = banco([{ status: 400, cuerpo: { error: "La principal debe ser contigua." } }]);
  g.pedir({ n: 1 });
  await g.ahora();
  assert.equal(g.estado, "error");
  assert.match(g.mensaje, /contigua/);
});

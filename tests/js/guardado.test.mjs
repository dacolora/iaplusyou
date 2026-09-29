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

test("capa 4c (5/10): un 400 del validador muestra la frase llana y guarda el detalle aparte", async () => {
  const vistos = [];
  const { g } = banco([{ status: 400, cuerpo: { error: "No se pudo guardar este cambio; deshazlo y vuelve a intentar.",
    detalle: "pistas[p_texto].clips[0]: estilo.tamano fuera de rango." } }]);
  g.alCambiar = (estado, mensaje, detalle) => vistos.push([estado, mensaje, detalle]);
  g.pedir({ n: 1 });
  await g.ahora();
  assert.equal(g.estado, "error");
  assert.equal(g.mensaje, "No se pudo guardar este cambio; deshazlo y vuelve a intentar.");
  assert.equal(g.detalle, "pistas[p_texto].clips[0]: estilo.tamano fuera de rango.");
  assert.deepEqual(vistos.at(-1), ["error", g.mensaje, g.detalle]);
});

// ---- Capa 4c (6/10): la sesión venció ----
import { MENSAJE_SESION, sesionTerminada } from "../../static/editor/guardado.js";

const html = { get: (k) => (k.toLowerCase() === "content-type" ? "text/html; charset=utf-8" : null) };
const json = { get: (k) => (k.toLowerCase() === "content-type" ? "application/json" : null) };

const LOGIN = "https://app.test/login";

test("sesionTerminada: solo una redirección a /login o una página HTML con 200 son la página de entrar", () => {
  assert.equal(sesionTerminada({ status: 405, redirected: true, url: LOGIN, headers: html }), true);   // el PUT seguido a /login
  assert.equal(sesionTerminada({ status: 200, redirected: false, headers: html }), true);
  assert.equal(sesionTerminada({ status: 200, redirected: false, headers: json }), false);
  assert.equal(sesionTerminada({ status: 400 }), false);                // sin cabeceras (las pruebas): no se sabe, no se asume
  // un 5xx con HTML (Flask 500, nginx 502/504 durante un despliegue) NO es la sesión
  for (const status of [500, 502, 504]) assert.equal(sesionTerminada({ status, redirected: false, headers: html }), false, status);
  // una redirección que no va a /login tampoco
  assert.equal(sesionTerminada({ status: 405, redirected: true, url: "https://app.test/cliente/acme", headers: html }), false);
  assert.match(MENSAJE_SESION, /sesión terminó.*recarga la página e inicia sesión/);
});

test("un 5xx al guardar no dice «sesión terminó»: queda pendiente y se guarda con el próximo cambio", async () => {
  for (const status of [500, 502]) {
    const g = new Guardado({ url: "/e/1", versionN: 3, programar: () => 1, cancelar: () => {},
      enviar: async () => ({ status, redirected: false, headers: html, json: async () => { throw new Error("no es JSON"); } }) });
    g.pedir({ n: 1 });
    await g.ahora();
    assert.equal(g.estado, "error");
    assert.notEqual(g.mensaje, MENSAJE_SESION);
    assert.match(g.mensaje, new RegExp(`error ${status}.*se guarda con el próximo cambio`));
    assert.ok(g.sinGuardar, "el cambio sigue pendiente");
  }
});

test("guardar con la sesión vencida dice eso (no «error 405») y no pierde el cambio", async () => {
  for (const r of [{ status: 405, redirected: true, url: LOGIN, headers: html }, { status: 200, headers: html }]) {
    const enviados = [];
    const g = new Guardado({ url: "/e/1", versionN: 3, programar: () => 1, cancelar: () => {},
      enviar: async (url, cuerpo) => { enviados.push(cuerpo); return { ...r, json: async () => { throw new Error("no es JSON"); } }; } });
    g.pedir({ n: 1 });
    await g.ahora();
    assert.equal(g.estado, "error");
    assert.equal(g.mensaje, MENSAJE_SESION);
    assert.equal(g.versionN, 3, "no toma una versión de la página de entrar");
    assert.ok(g.sinGuardar, "el cambio sigue pendiente");
  }
});

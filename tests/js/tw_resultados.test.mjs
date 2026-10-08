// «Resultados de tu tienda» (spec 2026-10-08-tw-resultados): las funciones puras de static/tw_resultados.js.
// El archivo es un script clásico (no módulo): se evalúa con un `window` y un `document` mínimos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

globalThis.window = globalThis;
globalThis.document = { documentElement: { lang: 'es' } };
(0, eval)(fs.readFileSync(new URL('../../static/tw_resultados.js', import.meta.url), 'utf8'));
const P = window.TwResultados._puro;

test('escala con pasos redondos', () => {
  assert.deepEqual(P.escala(19273), { paso: 5000, tope: 20000 });
  assert.deepEqual(P.escala(3.1), { paso: 1, tope: 4 });
  assert.deepEqual(P.escala(20000), { paso: 5000, tope: 20000 });
  assert.deepEqual(P.escala(0), { paso: 1, tope: 1 });
});

test('promedio de 7 días ignora los vacíos', () => {
  assert.equal(P.promedio7([1, 2, 3, 4, 5, 6, 7, 8], 7), 5);
  assert.equal(P.promedio7([null, 2, null], 2), 2);
  assert.equal(P.promedio7([null, null], 1), null);
});

test('valor por métrica con divisor cero', () => {
  const d = { ing: 100, gas: 50, ped: 0, nc: 0 };
  assert.equal(P.valor('mer', d), 2);
  assert.equal(P.valor('ticket', d), null);
  assert.equal(P.valor('ventas', d), 100);
  assert.equal(P.valor('cpp', { ing: 0, gas: 30, ped: 3, nc: 0 }), 10);
  assert.equal(P.valor('clientes_nuevos', { ing: 0, gas: 0, ped: 4, nc: 1 }), 0.25);
});

test('el aviso no se sale del contenedor', () => {
  assert.equal(P.posicionAviso(100, 600, 200, 12), 112);
  assert.equal(P.posicionAviso(550, 600, 200, 12), 338);
  assert.equal(P.posicionAviso(5, 120, 200, 12), 4);
});

test('día más cercano a un punto', () => {
  assert.equal(P.indiceEn(46, 46, 10, 30), 0);
  assert.equal(P.indiceEn(46 + 10 * 29.9, 46, 10, 30), 29);
  assert.equal(P.indiceEn(9999, 46, 10, 30), 29);
  assert.equal(P.indiceEn(-50, 46, 10, 30), 0);
});

test('formatos: dinero, veces y porcentaje como en Python', () => {
  assert.equal(P.dinero(19273.4, 'USD', 'es'), '19.273 USD');
  assert.equal(P.dinero(77, 'USD', 'es'), '77 USD');
  assert.equal(P.dinero(77.126, 'USD', 'es'), '77,13 USD');
  assert.equal(P.dinero(4000, 'USD', 'en'), '4,000 USD');
  assert.equal(P.veces(2.4249, 'es'), '2,42×');
  assert.equal(P.pct(0.05, 'es'), '5 %');
  assert.equal(P.pct(0.008, 'es'), '0,8 %');
  assert.equal(P.dinero(null, 'USD', 'es'), '—');
});

test('reemplaza los %(…)s de los textos que manda el servidor', () => {
  assert.equal(P.texto('%(pct)s sobre un %(dia)s normal', { pct: '38 %', dia: 'miércoles' }),
    '38 % sobre un miércoles normal');
});

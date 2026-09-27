// Los módulos de navegador no se pueden ejecutar en Node (usan el DOM al
// llamarlos), pero sí importarse: esto atrapa errores de sintaxis y de
// importación antes de abrir la página. vista.js no se importa: arranca solo.
import { test } from "node:test";
import assert from "node:assert/strict";

test("los módulos de navegador cargan y exportan lo que la página usa", async () => {
  const t = await import("../../static/editor/texto_canvas.js");
  const v = await import("../../static/editor/videos.js");
  const l = await import("../../static/editor/lienzo.js");
  const a = await import("../../static/editor/motor_audio.js");
  assert.equal(typeof t.rasterizarTexto, "function");
  assert.equal(typeof v.Videos, "function");
  assert.equal(typeof l.dibujarCuadro, "function");
  assert.equal(typeof a.MotorAudio, "function");
});

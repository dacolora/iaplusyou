// Los módulos de navegador no se pueden ejecutar en Node (usan el DOM al
// llamarlos), pero sí importarse: esto atrapa errores de sintaxis y de
// importación antes de abrir la página. Importarlos también prueba que no
// tocan `document` ni `window` al cargar (en Node no existen: la importación
// fallaría). vista.js y linea_tiempo.js ya no arrancan solos desde la capa 4a
// (lo hace pagina_editor.js, que sí lee la página al cargar y no se importa).
import { test } from "node:test";
import assert from "node:assert/strict";

test("los módulos de navegador cargan y exportan lo que la página usa", async () => {
  assert.equal(typeof globalThis.document, "undefined");
  assert.equal(typeof globalThis.window, "undefined");
  const t = await import("../../static/editor/texto_canvas.js");
  const v = await import("../../static/editor/videos.js");
  const l = await import("../../static/editor/lienzo.js");
  const a = await import("../../static/editor/motor_audio.js");
  const vp = await import("../../static/editor/vista.js");
  const lt = await import("../../static/editor/linea_tiempo.js");
  assert.equal(typeof t.rasterizarTexto, "function");
  assert.equal(typeof v.Videos, "function");
  assert.equal(typeof l.dibujarCuadro, "function");
  assert.equal(typeof a.MotorAudio, "function");
  assert.equal(typeof vp.VistaPrevia, "function");
  assert.equal(typeof lt.LineaTiempo, "function");
  for (const m of ["iniciar", "setDocumento", "tiempo", "ir", "pausar"]) {
    assert.equal(typeof vp.VistaPrevia.prototype[m], "function", `VistaPrevia.${m}`);
  }
  for (const g of ["materiales", "destino"]) {
    assert.equal(typeof Object.getOwnPropertyDescriptor(vp.VistaPrevia.prototype, g)?.get, "function", `VistaPrevia.${g}`);
  }
  for (const m of ["dibujar", "moverCabezal"]) {
    assert.equal(typeof lt.LineaTiempo.prototype[m], "function", `LineaTiempo.${m}`);
  }
  const pps = Object.getOwnPropertyDescriptor(lt.LineaTiempo.prototype, "pps");
  assert.equal(typeof pps?.get, "function");
  assert.equal(typeof pps?.set, "function");
});

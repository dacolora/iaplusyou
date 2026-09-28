// Tablas en el celular (2026-09-28): hasta 640 px cada fila se muestra como
// una tarjeta y cada dato lleva delante el título de su columna (el CSS lo lee
// de data-etiqueta). Aquí solo se copian esos títulos desde la cabecera, así
// que sirven en cualquier idioma y en las tablas que llegan después por fetch.
(function () {
  var SELECTOR = 'table.tabla-apilada, table.tabla-admin, table.tabla-tiendas, table.tabla-productos, ' +
                 'table.gasto-tabla, table.sprint-entrega, table.gpg-tabla';

  function etiquetar(tabla) {
    var cab = tabla.querySelector('thead tr') || tabla.querySelector('tr');
    if (!cab || !cab.querySelector('th')) return;
    var nombres = [];
    Array.prototype.forEach.call(cab.children, function (celda) {
      for (var i = 0; i < (celda.colSpan || 1); i++) nombres.push(celda.tagName === 'TH' ? celda.textContent.trim() : '');
    });
    if (!tabla.querySelector('thead')) cab.classList.add('tabla-cabecera');
    tabla.querySelectorAll('tr').forEach(function (fila) {
      if (fila === cab) return;
      var col = 0;
      Array.prototype.forEach.call(fila.children, function (celda) {
        if (celda.tagName === 'TD' && !celda.hasAttribute('data-etiqueta') && nombres[col] && (celda.colSpan || 1) === 1) {
          celda.setAttribute('data-etiqueta', nombres[col]);
        }
        col += celda.colSpan || 1;
      });
    });
  }

  function etiquetarTodas() {
    document.querySelectorAll(SELECTOR).forEach(etiquetar);
  }

  var espera = null;
  function programar() {
    clearTimeout(espera);
    espera = setTimeout(etiquetarTodas, 60);
  }

  window.etiquetarTablas = etiquetarTodas;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', etiquetarTodas);
  else etiquetarTodas();
  new MutationObserver(function (cambios) {
    for (var i = 0; i < cambios.length; i++) {
      if (cambios[i].addedNodes.length) { programar(); return; }
    }
  }).observe(document.documentElement, {childList: true, subtree: true});
})();

// Barras de pestañas accesibles (PND-317, 2026-10-15; decisión 2026-10-13: «arreglarlo una vez para las tres
// barras»). Las barras de pastillas `cat-tabs` que cambian de panel (Sprints · Nicho, Catálogo, Configuración y su
// «Conectar tienda») llevan role="tablist" y `data-pestanas`; cada botón, role="tab", su id y `aria-controls` hacia
// su panel (role="tabpanel" con `aria-labelledby`), escritos en la plantilla. Aquí, una sola vez para todas:
// `aria-selected` y el tabindex itinerante siguen a la clase `activo` (la pone el script de cada pantalla, también al
// llegar por el hash o por lo guardado en el navegador), y las flechas ← →, Inicio y Fin mueven el foco a otra
// pestaña y la activan con el mismo clic de siempre. Lo carga base.html en todas las páginas.
(function () {
  var PASO = {ArrowRight: 1, ArrowLeft: -1};

  function pestanas(lista) {
    return Array.prototype.filter.call(lista.querySelectorAll('[role="tab"]'), function (t) {
      return !t.hidden && !t.disabled;
    });
  }

  function sincronizar(lista) {
    var tabs = pestanas(lista);
    var activa = tabs.filter(function (t) { return t.classList.contains('activo'); })[0] || null;
    tabs.forEach(function (t, i) {
      var esta = t === activa;
      // Sin ninguna activa (antes de que corra el script de la pantalla), la primera recibe el foco con Tab.
      t.setAttribute('aria-selected', esta ? 'true' : 'false');
      t.setAttribute('tabindex', esta || (!activa && i === 0) ? '0' : '-1');
    });
  }

  function alTeclado(lista, ev) {
    var tabs = pestanas(lista);
    var actual = ev.target && ev.target.closest ? ev.target.closest('[role="tab"]') : null;
    var i = tabs.indexOf(actual);
    if (i === -1 || ev.altKey || ev.ctrlKey || ev.metaKey) return;
    var destino = null;
    if (PASO[ev.key]) destino = tabs[(i + PASO[ev.key] + tabs.length) % tabs.length];
    else if (ev.key === 'Home') destino = tabs[0];
    else if (ev.key === 'End') destino = tabs[tabs.length - 1];
    if (!destino) return;
    ev.preventDefault();
    destino.focus();
    if (!destino.classList.contains('activo')) destino.click();
  }

  function mejorar(lista) {
    if (lista.getAttribute('data-pestanas-listas')) return;
    lista.setAttribute('data-pestanas-listas', '1');
    sincronizar(lista);
    lista.addEventListener('keydown', function (ev) { alTeclado(lista, ev); });
    if (typeof MutationObserver === 'function') {
      // Solo la clase: lo que escribe `sincronizar` (aria-selected, tabindex) no vuelve a dispararlo.
      new MutationObserver(function () { sincronizar(lista); })
        .observe(lista, {subtree: true, attributes: true, attributeFilter: ['class']});
    }
  }

  function todas() {
    Array.prototype.forEach.call(document.querySelectorAll('[role="tablist"][data-pestanas]'), mejorar);
  }

  window.Pestanas = {mejorar: mejorar, sincronizar: sincronizar};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', todas);
  else todas();
})();

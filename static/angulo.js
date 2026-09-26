/* Editor del ángulo (doctrina, bloque 2): autoguarda cada cambio por fetch
   JSON contra data-url de cada <details class="angulo-editor">, muestra los
   avisos (no bloquean) y cuenta las palabras del gancho. */
(function () {
  function leer(caja) {
    var angulo = {};
    caja.querySelectorAll('[data-angulo-campo]').forEach(function (el) { angulo[el.dataset.anguloCampo] = el.value; });
    angulo.pruebas = [];
    caja.querySelectorAll('[data-angulo-prueba]').forEach(function (fila) {
      var texto = fila.querySelector('[data-prueba-texto]').value.trim();
      if (texto) angulo.pruebas.push({texto: texto, fuente: fila.querySelector('[data-prueba-fuente]').value});
    });
    return angulo;
  }

  function pintarAvisos(caja, avisos) {
    var lista = caja.querySelector('.angulo-avisos');
    lista.innerHTML = '';
    (avisos || []).forEach(function (texto) {
      var li = document.createElement('li');
      li.textContent = texto;
      lista.appendChild(li);
    });
    lista.hidden = !(avisos && avisos.length);
  }

  function contarGancho(caja) {
    var gancho = caja.querySelector('[data-angulo-campo="gancho"]');
    var cuenta = caja.querySelector('.angulo-cuenta-gancho');
    if (!gancho || !cuenta) return;
    var n = gancho.value.trim() ? gancho.value.trim().split(/\s+/).length : 0;
    cuenta.textContent = n + '/12 palabras';
  }

  function iniciar(caja) {
    if (caja.dataset.listo) return;
    caja.dataset.listo = '1';
    contarGancho(caja);
    if (caja.dataset.soloLectura) return;
    var espera = null;
    function guardar() {
      fetch(caja.dataset.url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'},
                               body: JSON.stringify({angulo: leer(caja)})})
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (!j.ok) { pintarAvisos(caja, [j.error]); return; }
          pintarAvisos(caja, j.avisos);
          var resumen = caja.querySelector('.angulo-resumen');
          if (resumen && j.resumen) resumen.textContent = j.resumen;
          // Gancho sync: copy saved gancho back to the idea card (doctrina, bloque 2, §3.3)
          var tarjeta = caja.closest('.sprint-idea');
          var ganchoTarjeta = tarjeta ? tarjeta.querySelector('input[name="gancho"]') : null;
          if (ganchoTarjeta && !ganchoTarjeta.readOnly && j.angulo) ganchoTarjeta.value = j.angulo.gancho || '';
          var ok = caja.querySelector('.angulo-guardado');
          ok.hidden = false;
          setTimeout(function () { ok.hidden = true; }, 1500);
        })
        .catch(function () {});
    }
    caja.querySelectorAll('input, textarea, select').forEach(function (el) {
      el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', function () {
        contarGancho(caja);
        clearTimeout(espera);
        espera = setTimeout(guardar, 800);
      });
    });
  }

  window.iniciarEditoresAngulo = function (raiz) {
    (raiz || document).querySelectorAll('.angulo-editor').forEach(iniciar);
  };
  window.iniciarEditoresAngulo();
})();

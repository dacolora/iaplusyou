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

  function fijarEnPlantilla(el, valor) {
    // cloneNode copia el valor de un input o textarea, pero NO la opción
    // elegida de un <select>: el clon vuelve a la del atributo `selected`.
    // Por eso se escriben los atributos (lo que el clon sí hereda).
    valor = valor == null ? '' : String(valor);
    if (el.tagName === 'SELECT') {
      Array.prototype.forEach.call(el.options, function (o) {
        if (o.value === valor) o.setAttribute('selected', ''); else o.removeAttribute('selected');
      });
    } else if (el.tagName === 'TEXTAREA') {
      el.textContent = valor;
    } else {
      el.setAttribute('value', valor);
    }
    el.value = valor;
  }

  function escribirEnPlantillaOriginal(url, angulo, avisos, resumen) {
    // Bug crítico (doctrina, bloque 2, revisión final): el modal de Crear
    // clona su <template class="generado-detalle"> de cero cada vez que se
    // abre, así que sin esto el siguiente guardado revertiría el anterior en
    // cuanto se reabriera la pieza. Busca la <template> cuyo editor tiene la
    // misma data-url y le deja los mismos valores, avisos y resumen.
    document.querySelectorAll('template.generado-detalle').forEach(function (tpl) {
      var editor = tpl.content.querySelector('.angulo-editor[data-url="' + url + '"]');
      if (!editor) return;
      editor.querySelectorAll('[data-angulo-campo]').forEach(function (el) {
        fijarEnPlantilla(el, angulo && angulo[el.dataset.anguloCampo]);
      });
      var pruebas = (angulo && angulo.pruebas) || [];
      editor.querySelectorAll('[data-angulo-prueba]').forEach(function (fila, i) {
        var p = pruebas[i] || {};
        fijarEnPlantilla(fila.querySelector('[data-prueba-texto]'), p.texto);
        fijarEnPlantilla(fila.querySelector('[data-prueba-fuente]'), p.fuente);
      });
      pintarAvisos(editor, avisos);
      var r = editor.querySelector('.angulo-resumen');
      if (r && resumen) r.textContent = resumen;
    });
  }

  function contarGancho(caja) {
    var gancho = caja.querySelector('[data-angulo-campo="gancho"]');
    var cuenta = caja.querySelector('.angulo-cuenta-gancho');
    if (!gancho || !cuenta) return;
    var n = gancho.value.trim() ? gancho.value.trim().split(/\s+/).length : 0;
    cuenta.textContent = (cuenta.dataset.plantilla || '{n}/12').replace('{n}', n);
  }

  function iniciar(caja) {
    if (caja.dataset.listo) return;
    caja.dataset.listo = '1';
    contarGancho(caja);
    if (caja.dataset.soloLectura) return;
    var espera = null;
    var cambios = 0;
    function guardar() {
      var enviado = cambios;
      fetch(caja.dataset.url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'},
                               body: JSON.stringify({angulo: leer(caja)})})
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (!j.ok) { pintarAvisos(caja, [j.error]); return; }
          pintarAvisos(caja, j.avisos);
          var resumen = caja.querySelector('.angulo-resumen');
          if (resumen && j.resumen) resumen.textContent = j.resumen;
          escribirEnPlantillaOriginal(caja.dataset.url, j.angulo, j.avisos, j.resumen);
          // Gancho sync: copy saved gancho back to the idea card (doctrina, bloque 2, §3.3)
          var tarjeta = caja.closest('.sprint-idea');
          var ganchoTarjeta = tarjeta ? tarjeta.querySelector('input[name="gancho"]') : null;
          if (ganchoTarjeta && !ganchoTarjeta.readOnly && j.angulo) ganchoTarjeta.value = j.angulo.gancho || '';
          // Regla global: `data-sucio` solo se borra tras un autoguardado que
          // SÍ terminó de guardar lo que hay ahora — si el campo cambió otra
          // vez mientras esta llamada estaba en vuelo, sigue sucio (lo agarra
          // el guardado siguiente).
          if (enviado === cambios) caja.querySelectorAll('[data-sucio]').forEach(function (el) { delete el.dataset.sucio; });
          var ok = caja.querySelector('.angulo-guardado');
          ok.hidden = false;
          setTimeout(function () { ok.hidden = true; }, 1500);
        })
        .catch(function () {});
    }
    caja.querySelectorAll('input, textarea, select').forEach(function (el) {
      el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', function () {
        contarGancho(caja);
        cambios++;
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

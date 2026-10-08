// Cobros: saldo prepagado (spec 2026-10-08 §5.4, §7 y §9.4). Lo carga base.html
// (defer) en toda página de un proyecto. Tres cosas, sin textos propios (los
// trae el servidor ya traducidos en data-* o en el HTML):
// 1. Un rechazo 402 con `saldo_insuficiente` de CUALQUIER fetch muestra un aviso
//    con «Recargar saldo» (el enlace `recargar_url`). Es el único lugar: cada
//    pantalla sigue pintando su `error` como siempre y aquí se suma el enlace.
// 2. Configuración › Saldo: pide el panel (data-saldo-panel) la primera vez que
//    el apartado se ve, los montos sugeridos llenan el campo y «Ver más» trae la
//    página siguiente de movimientos.
// 3. La vuelta del pago (#recarga-vuelta): sondea data-estado-url cada 3 s
//    hasta 60 s y cambia el texto con lo que responde el servidor.
(function (raiz) {
  'use strict';
  var doc = raiz.document;
  var script = doc && doc.currentScript;
  var TEXTOS = {
    recargar: (script && script.getAttribute('data-texto-recargar')) || '',
    cerrar: (script && script.getAttribute('data-texto-cerrar')) || ''
  };
  var CABECERAS = { 'X-Requested-With': 'fetch' };
  var CADA_MS = 3000;
  var LIMITE_MS = 60000;

  // ---------------------------------------------------------------- 402 ---

  // Solo rutas de este sitio: el enlace sale de una respuesta del servidor,
  // pero nunca se pinta un «javascript:» ni una URL de otro dominio.
  function urlSegura(url) {
    url = String(url || '');
    return url.charAt(0) === '/' && url.charAt(1) !== '/' && url.charAt(1) !== '\\' ? url : '';
  }

  // La respuesta es un 402 de saldo insuficiente → sus datos; si no, null.
  // Lee una COPIA: quien hizo el fetch sigue leyendo su cuerpo.
  function datosDe402(respuesta) {
    if (!respuesta || respuesta.status !== 402) return Promise.resolve(null);
    var tipo = (respuesta.headers && respuesta.headers.get('content-type')) || '';
    if (tipo.indexOf('json') < 0) return Promise.resolve(null);
    return respuesta.clone().json().then(function (d) {
      return d && d.saldo_insuficiente === true ? d : null;
    }, function () { return null; });
  }

  // fetch envuelto: devuelve la MISMA promesa (nada cambia para quien llama) y,
  // si la respuesta es un 402 de saldo, llama a `avisar(datos)`.
  function envolver(fetchOriginal, avisar) {
    var envuelto = function () {
      var promesa = fetchOriginal.apply(raiz, arguments);
      promesa.then(function (r) {
        return datosDe402(r).then(function (d) { if (d) avisar(d); });
      }).catch(function () {});
      return promesa;
    };
    envuelto.cobros = true;
    return envuelto;
  }

  function pintarAviso(d) {
    var viejo = doc.getElementById('aviso-sin-saldo');
    if (viejo) viejo.parentNode.removeChild(viejo);
    var caja = doc.createElement('div');
    caja.id = 'aviso-sin-saldo';
    caja.className = 'flash error aviso-sin-saldo';
    caja.setAttribute('role', 'alert');
    var texto = doc.createElement('span');
    texto.textContent = d.error || '';
    caja.appendChild(texto);
    var url = urlSegura(d.recargar_url);
    if (url && TEXTOS.recargar) {
      var enlace = doc.createElement('a');
      enlace.href = url;
      enlace.className = 'aviso-sin-saldo-enlace';
      enlace.textContent = TEXTOS.recargar;
      caja.appendChild(enlace);
    }
    var cerrar = doc.createElement('button');
    cerrar.type = 'button';
    cerrar.className = 'aviso-sin-saldo-cerrar';
    cerrar.setAttribute('aria-label', TEXTOS.cerrar);
    cerrar.textContent = '×';
    cerrar.addEventListener('click', function () { if (caja.parentNode) caja.parentNode.removeChild(caja); });
    caja.appendChild(cerrar);
    doc.body.appendChild(caja);
  }

  // ------------------------------------------------- Configuración › Saldo ---

  function iniciarPanel() {
    var caja = doc.querySelector('[data-saldo-panel]');
    if (!caja) return;
    var estado = 'nada';   // nada | pidiendo | listo
    function visible() { return caja.getClientRects().length > 0; }
    function marcarError() {
      var cargando = caja.querySelector('[data-saldo-cargando]');
      var error = caja.querySelector('[data-saldo-error]');
      if (cargando) cargando.hidden = true;
      if (error) error.hidden = false;
    }
    function cargar() {
      if (estado !== 'nada' || !visible()) return;
      estado = 'pidiendo';
      raiz.fetch(caja.getAttribute('data-saldo-panel'), { headers: CABECERAS, cache: 'no-store', credentials: 'same-origin' })
        .then(function (r) {
          if (!r.ok || r.redirected) throw new Error('saldo ' + r.status);
          return r.text();
        })
        .then(function (html) { caja.innerHTML = html; estado = 'listo'; })
        .catch(function () { estado = 'nada'; marcarError(); });
    }
    function luego() { setTimeout(cargar, 0); }
    cargar();
    raiz.addEventListener('cr:tab', luego);
    raiz.addEventListener('hashchange', luego);
    doc.addEventListener('click', function (ev) {
      if (ev.target.closest('.config-apartados [data-apartado="saldo"], .sidebar-item[data-tab="settings"]')) luego();
    });

    caja.addEventListener('click', function (ev) {
      var monto = ev.target.closest('[data-saldo-monto]');
      if (monto) {
        var campo = caja.querySelector('#saldo-usd');
        if (campo) { campo.value = monto.getAttribute('data-saldo-monto'); campo.focus(); }
        return;
      }
      var mas = ev.target.closest('[data-saldo-mas]');
      if (mas && !mas.disabled) verMas(mas);
    });

    function verMas(boton) {
      var cuerpo = caja.querySelector('[data-saldo-filas]');
      if (!cuerpo) return;
      boton.disabled = true;
      raiz.fetch(boton.getAttribute('data-saldo-mas'), { headers: CABECERAS, cache: 'no-store', credentials: 'same-origin' })
        .then(function (r) {
          if (!r.ok || r.redirected) throw new Error('movimientos ' + r.status);
          return r.text();
        })
        .then(function (html) {
          var temporal = doc.createElement('tbody');
          temporal.innerHTML = html;
          var siguiente = null;
          Array.prototype.slice.call(temporal.children).forEach(function (fila) {
            if (fila.hasAttribute('data-saldo-siguiente')) siguiente = fila.getAttribute('data-saldo-siguiente');
            else cuerpo.appendChild(fila);
          });
          if (siguiente) { boton.setAttribute('data-saldo-mas', siguiente); boton.disabled = false; }
          else boton.parentNode.removeChild(boton);
        })
        .catch(function () { boton.disabled = false; });
    }
  }

  // ------------------------------------------------------ vuelta del pago ---

  // Qué hacer con una respuesta del estado: 'final' (aprobada, rechazada,
  // expirada, anulada), 'tarde' (sigue pendiente pasados 60 s) o 'seguir'.
  function pasoSondeo(datos, transcurridoMs) {
    if (datos && datos.estado && datos.estado !== 'pendiente') return 'final';
    return transcurridoMs >= LIMITE_MS ? 'tarde' : 'seguir';
  }

  function iniciarVuelta() {
    var caja = doc.getElementById('recarga-vuelta');
    if (!caja || !caja.getAttribute('data-estado-url')) return;
    var url = caja.getAttribute('data-estado-url');
    var inicio = Date.now();
    function q(sel) { return caja.querySelector(sel); }
    function mostrar(sel, si) { var el = q(sel); if (el) el.hidden = !si; }
    function cerrarEspera() { mostrar('[data-recarga-barra]', false); mostrar('[data-recarga-verificar]', false); }
    function final(d) {
      cerrarEspera();
      caja.setAttribute('data-estado', d.estado);
      if (d.estado === 'aprobada' && d.saldo_texto) {
        var saldo = q('[data-recarga-saldo] strong');
        if (saldo) saldo.textContent = d.saldo_texto;
        mostrar('[data-recarga-saldo]', true);
      }
      mostrar('[data-recarga-reintentar]', d.estado === 'rechazada' || d.estado === 'expirada');
    }
    function tarde() { mostrar('[data-recarga-barra]', false); mostrar('[data-recarga-tarde]', true); }
    function seguir(d) {
      var paso = pasoSondeo(d, Date.now() - inicio);
      if (paso === 'final') return final(d);
      if (paso === 'tarde') return tarde();
      setTimeout(sondear, CADA_MS);
    }
    function sondear() {
      raiz.fetch(url, { headers: CABECERAS, cache: 'no-store', credentials: 'same-origin' })
        .then(function (r) { return r.ok && !r.redirected ? r.json() : null; })
        .then(function (d) {
          if (d && d.texto) { var t = q('[data-recarga-texto]'); if (t) t.textContent = d.texto; }
          seguir(d);
        })
        .catch(function () { seguir(null); });
    }
    sondear();
  }

  raiz.CobrosSaldo = { urlSegura: urlSegura, datosDe402: datosDe402, envolver: envolver, pasoSondeo: pasoSondeo, avisar: pintarAviso,
                       LIMITE_MS: LIMITE_MS, CADA_MS: CADA_MS };
  if (typeof raiz.fetch === 'function' && !raiz.fetch.cobros) raiz.fetch = envolver(raiz.fetch, pintarAviso);
  if (doc && doc.querySelector) {
    iniciarPanel();
    iniciarVuelta();
  }
})(typeof window !== 'undefined' ? window : this);

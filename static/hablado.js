/* Crear › Anuncio hablado (spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md).
   La cáscara (_crear_hablado.html) va en la página; el panel con las fotos y
   las voces (_hablado_panel.html) llega por fetch la primera vez que el modo
   se ve en pantalla: nada pesado en la carga de la página. Los textos llegan
   ya traducidos en window.HB_TEXTOS. Solo se mete con innerHTML el HTML que
   devuelve el servidor (escapado por Jinja), nunca lo que escribe la persona.
   La barra de la voz no lleva el atributo que recargaría la página (lo usan
   otras barras de Crear): este archivo sondea /trabajo/<job_id>/estado. */
(function () {
  'use strict';
  var raiz = document.getElementById('hb');
  if (!raiz) return;
  var T = window.HB_TEXTOS || {};
  var CABECERAS = {'X-Requested-With': 'fetch'};
  var estado = {cargado: false, cargando: false, ocupado: false, voz: null, sonando: null, activo: raiz.offsetParent !== null};

  function $(id) { return document.getElementById(id); }
  function sep() { return raiz.dataset.sep || ','; }
  // Hasta 3 decimales, y solo cuando el tercero no es cero (0,275 por 11 s de
  // voz; 0,20 se queda en dos) — el precio real (0,025 por segundo) a veces
  // cae en medio centavo y redondear a 2 decimales mentía sobre lo cobrado.
  function fmtUsd(v) {
    var miles = Math.round(v * 1000);
    var dec = miles % 10 === 0 ? 2 : 3;
    return 'US$ ' + (miles / 1000).toFixed(dec).replace('.', sep());
  }
  function mostrar(id, msg) {
    var el = $(id);
    if (!el) return;
    el.textContent = msg || '';
    el.hidden = !msg;
  }
  function enviar(url, fd) {
    return fetch(url, {method: 'POST', body: fd, headers: CABECERAS, credentials: 'same-origin'})
      .then(function (r) { return r.json(); });
  }

  // ---- El panel: se pide la primera vez que el modo se ve ----
  function abrir() {
    if (estado.cargado || estado.cargando) return;
    estado.cargando = true;
    mostrar('hb-carga-error', '');
    fetch(raiz.dataset.urlPanel, {headers: CABECERAS, credentials: 'same-origin'})
      .then(function (r) { if (!r.ok) throw new Error('panel ' + r.status); return r.text(); })
      .then(function (html) {
        $('hb-panel').innerHTML = html;
        estado.cargado = true;
        iniciar();
      })
      .catch(function () { mostrar('hb-carga-error', T.sinConexion); })
      .then(function () { estado.cargando = false; });
  }
  if ('IntersectionObserver' in window) {
    var observador = new IntersectionObserver(function (entradas) {
      if (entradas.some(function (e) { return e.isIntersecting; })) { observador.disconnect(); abrir(); }
    });
    observador.observe(raiz);
  } else {
    document.addEventListener('crear:modo', function (ev) { if (ev.detail && ev.detail.modo === 'hablado') abrir(); });
    if (raiz.offsetParent !== null) abrir();
  }
  // Si la persona cambia de modo mientras la voz se está creando, el resultado
  // puede llegar tarde: no se reproduce solo (ponerVoz la reusa igual) y la
  // que ya sonaba se calla, para que nada suene fuera de este modo.
  document.addEventListener('crear:modo', function (ev) {
    estado.activo = !!(ev.detail && ev.detail.modo === 'hablado');
    if (!estado.activo) {
      var audio = $('hb-voz-audio');
      if (audio) audio.pause();
    }
  });

  // ---- Lo que hay escrito y elegido ----
  function texto() { return ($('hb-texto').value || '').replace(/\s+/g, ' ').trim(); }
  function clave() {
    return JSON.stringify([texto(), $('hb-voz').value, $('hb-idioma').value, $('hb-velocidad').value]);
  }
  function fotoElegida() {
    var r = raiz.querySelector('input[name="hb-foto"]:checked');
    return r ? r.value : '';
  }
  // «Generar video» solo con una foto elegida y una voz escuchada que sea la
  // del texto, voz, idioma y velocidad de AHORA (spec §1.3).
  function refrescar() {
    if (!estado.cargado) return;
    var n = texto().length;
    $('hb-contador').textContent = n;
    var usd = n * (parseFloat($('hb-form').dataset.usdCaracter) || 0);
    $('hb-escuchar-precio').textContent = n ? ('· ' + T.aprox + ' ' + (usd < 0.01 ? 'US$ <0' + sep() + '01' : fmtUsd(usd))) : '';
    $('hb-escuchar').disabled = !n || estado.ocupado;
    var vigente = !!(estado.voz && estado.voz.clave === clave());
    var precio = vigente ? estado.voz.datos.precio_video : null;
    var hayPrecio = typeof precio === 'number';
    $('hb-generar-precio').textContent = hayPrecio ? '· ' + fmtUsd(precio) : '';
    $('hb-generar').disabled = estado.ocupado || !hayPrecio || !fotoElegida();
    var falta = '';
    if (!estado.ocupado && n && !vigente) falta = T.faltaVoz;
    else if (!estado.ocupado && hayPrecio && !fotoElegida()) falta = T.faltaFoto;
    mostrar('hb-falta', falta);
  }
  function ponerOcupado(si) { estado.ocupado = si; refrescar(); }

  // ---- Fotos ----
  function marcarFotos() {
    raiz.querySelectorAll('.hb-foto').forEach(function (l) {
      var i = l.querySelector('input');
      l.classList.toggle('elegida', !!(i && i.checked));
    });
    refrescar();
  }
  function subirFoto(input) {
    if (!input.files.length) return;
    var fd = new FormData();
    fd.append('foto', input.files[0]);
    mostrar('hb-subida', T.subiendo);
    mostrar('hb-error', '');
    enviar(raiz.dataset.urlFoto, fd).then(function (d) {
      input.value = '';
      mostrar('hb-subida', '');
      if (!d.ok) { mostrar('hb-error', d.error || T.errorSubir); return; }
      var grilla = $('hb-fotos');
      var radio = grilla.querySelector('input[value="' + d.foto.ficha + '"]');
      if (!radio) {
        grilla.insertAdjacentHTML('afterbegin', d.html);
        radio = grilla.querySelector('input[value="' + d.foto.ficha + '"]');
      }
      mostrar('hb-fotos-vacio', '');
      if (radio) { radio.checked = true; marcarFotos(); }
    }).catch(function () { input.value = ''; mostrar('hb-subida', ''); mostrar('hb-error', T.errorRed); });
  }

  // ---- Voces: elegir, filtrar y oír la muestra (la misma ruta de Audios) ----
  function elegirVoz(valor) {
    $('hb-voz').value = valor;
    var nombre = raiz.querySelector('.au-voz[data-voz="' + valor + '"] .au-voz-nombre');
    $('hb-voz-nombre').textContent = nombre ? nombre.textContent : valor;
    raiz.querySelectorAll('.au-voz').forEach(function (c) {
      c.setAttribute('aria-checked', c.dataset.voz === valor ? 'true' : 'false');
    });
    refrescar();
  }
  function filtrar(boton) {
    raiz.querySelectorAll('[data-filtro-genero]').forEach(function (b) { b.classList.toggle('activo', b === boton); });
    var g = boton.dataset.filtroGenero;
    raiz.querySelectorAll('#hb-voces .au-voz').forEach(function (c) { c.hidden = !!g && c.dataset.genero !== g; });
  }
  function oirMuestra(boton) {
    var fd = new FormData();
    fd.append('voz', boton.dataset.voz);
    fd.append('idioma', $('hb-idioma').value);
    boton.disabled = true;
    boton.textContent = '…';
    mostrar('hb-error', '');
    enviar(raiz.dataset.urlMuestra, fd).then(function (d) {
      if (!d.ok) { mostrar('hb-error', d.error || T.sinMuestra); return; }
      var audio = $('hb-muestra');
      if (estado.sonando) estado.sonando.classList.remove('sonando');
      estado.sonando = boton;
      boton.classList.add('sonando');
      audio.src = d.url;
      audio.play().catch(function () {});
    }).catch(function () { mostrar('hb-error', T.sinConexion); })
      .then(function () { boton.disabled = false; boton.textContent = '▶'; });
  }

  // ---- La voz del guion: «Escuchar la voz» ----
  function datosVoz() {
    var fd = new FormData();
    fd.append('texto', $('hb-texto').value);
    fd.append('voz', $('hb-voz').value);
    fd.append('idioma', $('hb-idioma').value);
    fd.append('velocidad', $('hb-velocidad').value);
    return fd;
  }
  function ponerVoz(claveVoz, datos) {
    estado.voz = {clave: claveVoz, datos: datos};
    var audio = $('hb-voz-audio');
    audio.src = datos.url;
    $('hb-voz-lista').hidden = false;
    $('hb-voz-duracion').textContent = T.dura.replace('{s}', String(datos.duracion_s).replace('.', sep()));
    mostrar('hb-aviso', datos.aviso || '');
    refrescar();
    // Si la persona cambió de modo o de texto/voz/idioma/velocidad mientras
    // esta voz se creaba, queda guardada (Generar video ya exige su clave
    // vigente, en refrescar) pero no suena sola ni encima de otro modo. Y si
    // esto es otra pestaña del mismo proyecto, estado.activo puede seguir en
    // true (sigue crear:modo) aunque el panel no esté realmente a la vista:
    // se exige también que esté visible justo antes de reproducir.
    if (estado.activo && raiz.offsetParent !== null && claveVoz === clave()) audio.play().catch(function () {});
  }
  function barra(si, textoBarra) {
    $('hb-barra').hidden = !si;
    mostrar('hb-barra-texto', si ? textoBarra : '');
  }
  // Sondea el trabajo de la voz cada 2 s; cinco fallos seguidos lo paran.
  function vigilar(url, alTerminar) {
    barra(true, T.creandoVoz);
    var fallos = 0;
    var t = setInterval(function () {
      fetch(url, {headers: CABECERAS, credentials: 'same-origin'}).then(function (r) { return r.json(); }).then(function (e) {
        fallos = 0;
        if (e.estado === 'en_progreso') { if (e.etapa) $('hb-barra-texto').textContent = e.etapa; return; }
        clearInterval(t);
        barra(false);
        if (e.estado === 'error') { ponerOcupado(false); mostrar('hb-error', e.mensaje || T.noSePudoVoz); return; }
        alTerminar();
      }).catch(function () {
        if (++fallos >= 5) { clearInterval(t); barra(false); ponerOcupado(false); mostrar('hb-error', T.sinConexion); }
      });
    }, 2000);
  }
  function escuchar() {
    var claveVoz = clave(), fd = datosVoz();
    mostrar('hb-error', '');
    mostrar('hb-aviso', '');
    ponerOcupado(true);
    enviar(raiz.dataset.urlVoz, fd).then(function (d) {
      if (d.listo && d.voz) { ponerOcupado(false); ponerVoz(claveVoz, d.voz); return; }
      if (d.job_id) {
        if (!d.ok) mostrar('hb-aviso', d.error || '');
        vigilar(d.estado_url, function () {
          // Terminó: el mismo pedido ya sale de la caché. solo_cache=1 nunca
          // encola otra síntesis: nada se paga sin un clic.
          fd.append('solo_cache', '1');
          enviar(raiz.dataset.urlVoz, fd).then(function (d2) {
            ponerOcupado(false);
            mostrar('hb-aviso', '');
            if (d2.listo && d2.voz) ponerVoz(claveVoz, d2.voz);
            else mostrar('hb-error', d2.error || T.noSePudoVoz);
          }).catch(function () { ponerOcupado(false); mostrar('hb-error', T.sinConexion); });
        });
        return;
      }
      ponerOcupado(false);
      mostrar('hb-error', d.error || T.noSePudoVoz);
    }).catch(function () { ponerOcupado(false); mostrar('hb-error', T.sinConexion); });
  }

  // ---- «Generar video» ----
  function generar() {
    if (!estado.voz || estado.voz.clave !== clave() || !fotoElegida()) return;
    var fd = new FormData();
    fd.append('foto', fotoElegida());
    fd.append('voz_hash', estado.voz.datos.hash);
    fd.append('movimiento', $('hb-movimiento').value);
    fd.append('precio_visto', String(estado.voz.datos.precio_video));
    mostrar('hb-error', '');
    mostrar('hb-aviso', T.lanzando);
    ponerOcupado(true);
    enviar(raiz.dataset.urlCrear, fd).then(function (d) {
      if (d.ok) {
        // Lo escrito ya se usó: la guardia de base.html no debe frenar la recarga.
        raiz.querySelectorAll('[data-sucio]').forEach(function (el) { delete el.dataset.sucio; });
        location.hash = d.ir || '#referencias';
        location.reload();
        return;
      }
      ponerOcupado(false);
      mostrar('hb-aviso', '');
      mostrar('hb-error', d.error || T.noSePudoVideo);
    }).catch(function () { ponerOcupado(false); mostrar('hb-aviso', ''); mostrar('hb-error', T.sinConexion); });
  }

  // ---- Eventos (delegados: el panel llega después) ----
  raiz.addEventListener('click', function (ev) {
    var t = ev.target;
    var play = t.closest('.au-voz-play');
    if (play) { oirMuestra(play); return; }
    var tarjeta = t.closest('.au-voz');
    if (tarjeta) { elegirVoz(tarjeta.dataset.voz); return; }
    var filtro = t.closest('[data-filtro-genero]');
    if (filtro) { filtrar(filtro); return; }
    if (t.closest('#hb-escuchar')) { escuchar(); return; }
    if (t.closest('#hb-generar')) { generar(); return; }
    var modo = t.closest('[data-crear-modo]');
    if (modo) {
      ev.preventDefault();
      var pastilla = document.querySelector('#crear-modos [data-modo="' + modo.dataset.crearModo + '"]');
      if (pastilla) pastilla.click();
      window.scrollTo(0, 0);
    }
  });
  raiz.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var tarjeta = ev.target.closest('.au-voz');
    if (tarjeta && ev.target === tarjeta) { ev.preventDefault(); elegirVoz(tarjeta.dataset.voz); }
  });
  raiz.addEventListener('input', function () { refrescar(); });
  raiz.addEventListener('change', function (ev) {
    if (ev.target.name === 'hb-foto') marcarFotos();
    else if (ev.target.id === 'hb-archivo') subirFoto(ev.target);
    else refrescar();
  });

  function iniciar() {
    $('hb-muestra').addEventListener('ended', function () {
      if (estado.sonando) { estado.sonando.classList.remove('sonando'); estado.sonando = null; }
    });
    var form = $('hb-form');
    if (form.dataset.jobVoz) {
      // Una voz que se estaba creando al abrir el panel: se espera y se avisa.
      ponerOcupado(true);
      vigilar(form.dataset.estadoVoz, function () { ponerOcupado(false); mostrar('hb-aviso', T.vozHecha); });
    }
    marcarFotos();
  }
})();

/* Pozicijos form engine
 * Centralizuoja formos blokų logiką (be vizualinių pertvarkymų).
 * Tikslai:
 * - vienas init taškas;
 * - idempotentinis binding (neprisiriša kelis kartus);
 * - veikia tiek pozicijos formoje, tiek kainų valdymo puslapyje;
 * - blokai komunikuoja per event bus (CustomEvent).
 */
(function () {
  'use strict';

  if (window.__POZ_FORM_ENGINE_LOADED__ === true) {
    return;
  }
  window.__POZ_FORM_ENGINE_LOADED__ = true;

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function emit(name, detail) {
    try {
      document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
    } catch (e) {
      var ev = document.createEvent('CustomEvent');
      ev.initCustomEvent(name, false, false, detail || {});
      document.dispatchEvent(ev);
    }
  }

  function autoGrow(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = (el.scrollHeight + 2) + 'px';
  }

  function bindAutoResize(root) {
    $all('textarea[data-autoresize="1"]', root).forEach(function (ta) {
      if (ta.dataset.autoresizeBound === '1') return;
      ta.dataset.autoresizeBound = '1';
      ['input', 'change'].forEach(function (ev) {
        ta.addEventListener(ev, function () { autoGrow(ta); });
      });
      autoGrow(ta);
    });
  }

  function normalizeDecimalValue(raw, decimals) {
    if (raw == null) return '';
    var s = String(raw).trim();
    if (!s) return '';
    s = s.replace(',', '.');
    var n = Number(s);
    if (!isFinite(n)) return raw;
    var d = parseInt(decimals || '0', 10) || 0;
    return n.toFixed(d);
  }

  function bindDecimalInputs(root) {
    $all('input[data-decimals]', root).forEach(function (inp) {
      if (inp.dataset && inp.dataset.decimalsBound === '1') return;
      if (inp.dataset) inp.dataset.decimalsBound = '1';

      inp.addEventListener('blur', function () {
        var d = inp.getAttribute('data-decimals');
        var v = normalizeDecimalValue(inp.value, d);
        if (v !== inp.value) inp.value = v;
      });
    });
  }

  function bindPapildomos(root) {
    var sel = $('#id_papildomos_paslaugos', root);
    var row = $('#papildomos-paslaugos-aprasymas-row', root);
    if (!sel || !row) return;

    function sync() {
      row.style.display = (String(sel.value) === 'taip') ? '' : 'none';
    }
    if (sel.dataset.boundPapildomos !== '1') {
      sel.dataset.boundPapildomos = '1';
      sel.addEventListener('change', sync);
    }
    sync();
  }

  function bindKTLGeometry(root) {
    var il = $('#id_ktl_ilgis_mm', root);
    var au = $('#id_ktl_aukstis_mm', root);
    var gy = $('#id_ktl_gylis_mm', root);
    var out = $('#ktl-sandauga-preview', root);
    if (!il || !au || !gy || !out) return;

    function parse(v) {
      if (v == null) return null;
      var s = String(v).trim().replace(',', '.');
      if (!s) return null;
      var n = Number(s);
      return isFinite(n) ? n : null;
    }

    function calc() {
      var a = parse(il.value);
      var b = parse(au.value);
      var c = parse(gy.value);
      if (a == null || b == null || c == null) {
        out.value = '';
        return;
      }
      var r = a * b * c;
      if (!isFinite(r)) out.value = '';
      else out.value = String(Math.round(r)); // be .0
    }

    ['input', 'change'].forEach(function (ev) {
      il.addEventListener(ev, calc);
      au.addEventListener(ev, calc);
      gy.addEventListener(ev, calc);
    });
    calc();
  }

  function bindPaslaugaSubblocks(root) {
    var cbKtl = $('#id_paslauga_ktl', root);
    var cbMilt = $('#id_paslauga_miltai', root);
    var cbPar = $('#id_paslauga_paruosimas', root);

    var blKtl = $('#ktl-subblock', root);
    var blMilt = $('#miltai-subblock', root);
    var grid = $('#paslauga-subgrid', root);

    if (!cbKtl || !cbMilt || !cbPar || !blKtl || !blMilt || !grid) return;

    function enforceParuosimas() {
      if (cbKtl.checked || cbMilt.checked) cbPar.checked = true;
    }

    function sync(reason, source) {
      enforceParuosimas();

      blKtl.style.display = cbKtl.checked ? '' : 'none';
      blMilt.style.display = cbMilt.checked ? '' : 'none';

      if (cbKtl.checked && cbMilt.checked) grid.classList.remove('one-col');
      else grid.classList.add('one-col');

      emit('poz:paslauga:changed', {
        reason: reason || 'sync',
        source: source || null,
        ktl: !!cbKtl.checked,
        miltai: !!cbMilt.checked,
        paruosimas: !!cbPar.checked
      });
    }

    if (cbKtl.dataset.boundPaslauga !== '1') {
      cbKtl.dataset.boundPaslauga = '1';
      cbKtl.addEventListener('change', function () { sync('change', 'ktl'); });
    }
    if (cbMilt.dataset.boundPaslauga !== '1') {
      cbMilt.dataset.boundPaslauga = '1';
      cbMilt.addEventListener('change', function () { sync('change', 'miltai'); });
    }
    if (cbPar.dataset.boundPaslauga !== '1') {
      cbPar.dataset.boundPaslauga = '1';
      cbPar.addEventListener('change', function () { sync('change', 'paruosimas'); });
    }

    sync('init', 'boot');
  }

  function bindMaskFormset(root, prefix) {
    var total = $('#id_' + prefix + '-TOTAL_FORMS', root);
    var items = $('#' + prefix + '-items', root);
    var tpl = $('#' + prefix + '-empty-form', root);
    if (!total || !items || !tpl) return;

    function reindexHtml(html, idx) {
      return html.replace(/__prefix__/g, String(idx));
    }

    function hasVisibleItems() {
      return $all('.maskavimas-item', items).some(function (el) {
        return el.style.display !== 'none';
      });
    }

    function syncContainerVisibility() {
      items.style.display = hasVisibleItems() ? '' : 'none';
    }

    function bindRemoveButtons(scope) {
      $all('.maskavimas-remove', scope || items).forEach(function (btn) {
        if (btn.dataset.boundRemove === '1') return;
        btn.dataset.boundRemove = '1';
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          var row = btn.closest('.maskavimas-item');
          if (!row) return;

          var del = $('input[type="checkbox"][name$="-DELETE"]', row);
          if (del) {
            del.checked = true;
            row.style.display = 'none';
          } else {
            row.remove();
          }
          syncContainerVisibility();
        });
      });
    }

    function addRow() {
      var idx = parseInt(total.value || '0', 10);
      var html = reindexHtml(tpl.innerHTML, idx);

      var wrap = document.createElement('div');
      wrap.innerHTML = html.trim();
      var row = wrap.firstElementChild;
      if (!row) return;

      items.appendChild(row);
      total.value = String(idx + 1);
      bindRemoveButtons(row);
      syncContainerVisibility();
    }

    $all('.maskavimas-add[data-mask-prefix="' + prefix + '"]', root).forEach(function (btn) {
      if (btn.dataset.boundAdd === '1') return;
      btn.dataset.boundAdd = '1';
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        addRow();
      });
    });

    bindRemoveButtons(items);
    syncContainerVisibility();
  }

  function boot(root) {
    bindAutoResize(root);
    bindDecimalInputs(root);
    bindPapildomos(root);
    bindKTLGeometry(root);
    bindPaslaugaSubblocks(root);
    bindMaskFormset(root, 'maskavimas_ktl');
    bindMaskFormset(root, 'maskavimas_miltai');
    emit('poz:form:booted', {});
  }

  document.addEventListener('DOMContentLoaded', function () {
    boot(document);
  });
})();

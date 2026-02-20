/* pozicijos/static/pozicijos/js/poz_form_engine.js */
(function () {
  "use strict";

  // =========================
  // Helpers
  // =========================
  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  function $all(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  function autoResizeTextarea(el) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = (el.scrollHeight || 34) + "px";
  }

  function bindAutoResize(root) {
    $all("textarea", root).forEach(function (ta) {
      if (ta.dataset.autoresizeBound === "1") return;
      ta.dataset.autoresizeBound = "1";
      autoResizeTextarea(ta);
      ta.addEventListener("input", function () {
        autoResizeTextarea(ta);
      });
    });
  }

  function removeEmptyPlaceholder(tbody) {
    if (!tbody) return;
    var empty = tbody.querySelector('tr[data-empty-row="1"]');
    if (empty) empty.remove();
  }

  // =========================
  // Matmenys preview (XYZ)
  // =========================
  function initMatmenysPreview() {
    var x = $("#id_x_mm");
    var y = $("#id_y_mm");
    var z = $("#id_z_mm");
    var out = $("#matmenys-xyz-preview");
    if (!out || (!x && !y && !z)) return;

    function val(v) {
      if (v == null) return "";
      v = String(v).trim();
      return v;
    }

    function render() {
      var xv = x ? val(x.value) : "";
      var yv = y ? val(y.value) : "";
      var zv = z ? val(z.value) : "";
      if (!xv && !yv && !zv) {
        out.textContent = "—";
        return;
      }
      out.textContent = [xv || "0", yv || "0", zv || "0"].join(" × ") + " mm";
    }

    [x, y, z].forEach(function (el) {
      if (!el) return;
      el.addEventListener("input", render);
      el.addEventListener("change", render);
    });

    render();
  }

  // =========================
  // KTL I×A×G sandauga preview (be .0)
  // =========================
  function initKtlSandaugaPreview() {
    var iEl = $("#id_ktl_ilgis_mm");
    var aEl = $("#id_ktl_aukstis_mm");
    var gEl = $("#id_ktl_gylis_mm");
    var out = $("#ktl-sandauga-preview");
    if (!iEl || !aEl || !gEl || !out) return;

    function parseNum(v) {
      if (v == null) return NaN;
      v = String(v).trim().replace(",", ".");
      if (!v) return NaN;
      var n = Number(v);
      return Number.isFinite(n) ? n : NaN;
    }

    function pretty(n) {
      if (!Number.isFinite(n)) return "";
      // be nereikalingo ".0"
      if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
      return String(n);
    }

    function render() {
      var i = parseNum(iEl.value);
      var a = parseNum(aEl.value);
      var g = parseNum(gEl.value);
      if (!Number.isFinite(i) || !Number.isFinite(a) || !Number.isFinite(g)) {
        out.value = "";
        return;
      }
      var prod = i * a * g;
      out.value = pretty(prod);
    }

    [iEl, aEl, gEl].forEach(function (el) {
      el.addEventListener("input", render);
      el.addEventListener("change", render);
    });

    render();
  }

  // =========================
  // Papildomos paslaugos show/hide
  // =========================
  function initPapildomosPaslaugosToggle() {
    var select = $("#id_papildomos_paslaugos");
    var row = $("#papildomos-paslaugos-aprasymas-row");
    if (!select || !row) return;

    function render() {
      var v = (select.value || "").toLowerCase();
      row.style.display = v === "taip" ? "" : "none";
    }

    select.addEventListener("change", render);
    render();
  }

  // =========================
  // Detalė: vienetų formatavimas (blur)
  // - Metalo storis mm: 1 sk. po kablelio
  // - Plotas m2: neribotas (neformatuojam)
  // - Svoris kg: 3 sk. po kablelio
  // =========================
  function initDetaleUnitsFormatting() {
    function normalizeNumberString(v) {
      return String(v || "").trim().replace(",", ".");
    }

    function formatFixedOnBlur(el, decimals) {
      if (!el || el.dataset.fixedBound === "1") return;
      el.dataset.fixedBound = "1";
      el.addEventListener("blur", function () {
        var raw = normalizeNumberString(el.value);
        if (!raw) return;
        var n = Number(raw);
        if (!Number.isFinite(n)) return;
        el.value = n.toFixed(decimals);
      });
    }

    // Metalo storis (pagrindinis laukas): 1 dp
    formatFixedOnBlur(document.getElementById("id_metalo_storis"), 1);

    // Svoris: 3 dp
    formatFixedOnBlur(document.getElementById("id_svoris"), 3);

    // Dinaminės metalo storio eilutės: 1 dp (metalo_storis_values[])
    document.querySelectorAll('input[name="metalo_storis_values[]"]').forEach(function (el) {
      formatFixedOnBlur(el, 1);
    });

    // Plotas: neribotas – nieko neformatuojam
  }

  // =========================
  // Paslauga subblokų rodymas (KTL/Miltai) + PRIVERSTINIS Paruošimas lock
  // =========================
  function initPaslaugaBlocks() {
    // Checkbox'ai
    var ktlCb = $("#id_paslauga_ktl");
    var milCb = $("#id_paslauga_miltai");
    var parCb = $("#id_paslauga_paruosimas");

    // Subblokai / grid
    var ktlBlock = $("#ktl-subblock");
    var milBlock = $("#miltai-subblock");
    var grid = $("#paslauga-subgrid");

    // Paruošimo "eilutės" tekstinis laukas
    var parText = $("#id_paruosimas");

    // Paruošimo checkbox wrapper (tavo template turi: <label id="paruosimas-lock-wrap">...)
    var parWrap = $("#paruosimas-lock-wrap");

    if (!ktlBlock || !milBlock || !grid) return;

    function applyParuosimasAutofill() {
      if (!parCb || !parText) return;

      var on = !!parCb.checked;
      var autoValue = "Gardobond 24T";

      if (on) {
        var v = String(parText.value || "").trim();
        // pildom tik jei tuščia ARBA tai buvo mūsų autofill
        if (v === "" || parText.dataset.autofill === "1") {
          parText.value = autoValue;
          parText.dataset.autofill = "1";
        }
      } else {
        // išvalom tik jei tai buvo mūsų autofill ir vartotojas nepakeitė
        var v2 = String(parText.value || "").trim();
        if (parText.dataset.autofill === "1" && v2 === autoValue) {
          parText.value = "";
          delete parText.dataset.autofill;
        }
      }
    }

    function setLocked(lock) {
      if (!parCb) return;

      if (lock) {
        parCb.checked = true;
        parCb.disabled = true;
        parCb.dataset.locked = "1";
        if (parWrap) parWrap.classList.add("is-locked");
      } else {
        parCb.disabled = false;
        delete parCb.dataset.locked;
        if (parWrap) parWrap.classList.remove("is-locked");
      }

      applyParuosimasAutofill();
    }

    function render() {
      var ktlOn = !!(ktlCb && ktlCb.checked);
      var milOn = !!(milCb && milCb.checked);

      ktlBlock.style.display = ktlOn ? "" : "none";
      milBlock.style.display = milOn ? "" : "none";

      if (ktlOn && milOn) grid.classList.remove("one-col");
      else grid.classList.add("one-col");

      // Jei KTL arba Miltai -> Paruošimas privalomas ir negali būti atžymimas
      setLocked(ktlOn || milOn);
    }

    [ktlCb, milCb].forEach(function (el) {
      if (!el) return;
      el.addEventListener("change", render);
    });

    // Kritinė apsauga: label/wrapper gali bandyti perjungti – blokuojam CAPTURE fazėje.
    if (parWrap) {
      ["click", "mousedown", "pointerdown", "touchstart"].forEach(function (evt) {
        parWrap.addEventListener(
          evt,
          function (e) {
            if (parCb && parCb.dataset.locked === "1") {
              e.preventDefault();
              e.stopPropagation();
              parCb.checked = true;
              return false;
            }
          },
          true
        );
      });

      parWrap.addEventListener(
        "keydown",
        function (e) {
          if (!parCb || parCb.dataset.locked !== "1") return;
          if (e.key === " " || e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            parCb.checked = true;
            return false;
          }
        },
        true
      );
    }

    // Jei vis tiek įvyksta change (pvz. programiškai) – atstatom + autofill
    if (parCb) {
      parCb.addEventListener("change", function () {
        if (parCb.dataset.locked === "1") {
          parCb.checked = true;
          parCb.disabled = true;
        }
        applyParuosimasAutofill();
      });
    }

    // Jei vartotojas pats pakeičia tekstą – nebeperrašom automatiškai
    if (parText) {
      parText.addEventListener("input", function () {
        if (parText.dataset.autofill === "1") {
          delete parText.dataset.autofill;
        }
      });
    }

    render();
  }

  // =========================
  // Maskavimo formset (KTL/Miltai)
  // =========================
  function initMaskavimoFormset(prefix) {
    var totalInput = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
    var itemsWrap = document.getElementById(prefix + "-items");
    var addBtn = document.querySelector('.maskavimas-add[data-mask-prefix="' + prefix + '"]');
    var tpl = document.getElementById(prefix + "-empty-form");

    if (!totalInput || !itemsWrap || !addBtn || !tpl) return;

    function ensureVisible() {
      var hasRows = !!itemsWrap.querySelector(".maskavimas-item");
      itemsWrap.style.display = hasRows ? "" : "none";
    }

    function replacePrefix(html, index) {
      return html.replace(/__prefix__/g, String(index));
    }

    function bindRemove(btn) {
      if (!btn || btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var row = btn.closest(".maskavimas-item");
        if (!row) return;

        var delInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (delInput) {
          delInput.checked = true;
          row.style.display = "none";
        } else {
          row.remove();
        }
        ensureVisible();
      });
    }

    $all(".maskavimas-remove", itemsWrap).forEach(bindRemove);

    addBtn.addEventListener("click", function (e) {
      e.preventDefault();
      var idx = parseInt(totalInput.value || "0", 10);
      var html = replacePrefix(tpl.innerHTML, idx);
      itemsWrap.insertAdjacentHTML("beforeend", html);
      totalInput.value = String(idx + 1);

      var newRow = itemsWrap.lastElementChild;
      if (newRow) {
        var rm = newRow.querySelector(".maskavimas-remove");
        bindRemove(rm);
        bindAutoResize(newRow);
      }
      ensureVisible();

      // Nauja eilutė gali turėti metalo storio input'ą – perbindinam formatavimą
      initDetaleUnitsFormatting();
    });

    ensureVisible();
  }

  // =========================
  // Metalo storio papildomos eilutės
  // (jei global addMetaloStorisRow jau yra form.html, netrukdom)
  // =========================
  function initMetaloStorisRemoveOnly() {
    var items = document.getElementById("metalo-storis-items");
    if (!items) return;

    function bindRemove(btn) {
      if (!btn || btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var row = btn.closest(".metalo-storis-item");
        if (row) row.remove();
      });
    }

    $all(".metalo-storis-remove", items).forEach(bindRemove);
  }

  // =========================
  // KAINŲ FORMSET: + Pridėti eilutę
  // =========================
  function initKainosFormsets() {
    $all(".kainos-formset").forEach(function (root) {
      var prefix = root.getAttribute("data-prefix");
      if (!prefix) return;

      var totalInput = root.querySelector("#id_" + prefix + "-TOTAL_FORMS");
      var tbody = root.querySelector("#kainu-formset-body-" + prefix);
      var addBtn = root.querySelector("#kainos-add-row-" + prefix);
      var tpl = document.getElementById("kainos-empty-template-" + prefix);

      if (!totalInput || !tbody || !addBtn || !tpl) return;

      function replacePrefix(html, index) {
        return html.replace(/__prefix__/g, String(index));
      }

      function bindRow(row) {
        // autosize textarea
        bindAutoResize(row);

        // busenos spalvinimas
        var busSel = row.querySelector('select[name$="-busena_ui"]');
        function recolor() {
          var v = busSel && busSel.value ? busSel.value : "";
          row.classList.remove("kaina-row--aktuali", "kaina-row--neaktuali");
          if (v === "aktuali") row.classList.add("kaina-row--aktuali");
          else row.classList.add("kaina-row--neaktuali");
        }
        if (busSel && busSel.dataset.bound !== "1") {
          busSel.dataset.bound = "1";
          busSel.addEventListener("change", recolor);
        }
        recolor();
      }

      // esamoms eilutėms
      $all("tr.kaina-row", tbody).forEach(bindRow);

      addBtn.addEventListener("click", function (e) {
        e.preventDefault();

        var idx = parseInt(totalInput.value || "0", 10);
        var html = replacePrefix(tpl.innerHTML, idx);

        removeEmptyPlaceholder(tbody);
        tbody.insertAdjacentHTML("beforeend", html);
        totalInput.value = String(idx + 1);

        var row = tbody.lastElementChild;
        if (row) bindRow(row);
      });
    });
  }

  // =========================
  // Init
  // =========================
  document.addEventListener("DOMContentLoaded", function () {
    bindAutoResize(document);

    initMatmenysPreview();
    initKtlSandaugaPreview();
    initPapildomosPaslaugosToggle();

    // Detalė formatavimas (mm 1dp, kg 3dp)
    initDetaleUnitsFormatting();

    // Paslauga lock/autofill
    initPaslaugaBlocks();

    initMaskavimoFormset("maskavimas_ktl");
    initMaskavimoFormset("maskavimas_miltai");

    initMetaloStorisRemoveOnly();
    initKainosFormsets();
  });
})();

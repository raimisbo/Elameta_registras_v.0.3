// static/js/uzklausa_history.js
// Valdo: 1) Istorijos AJAX įkėlimą  2) Blokų matomumą (per "Stulpeliai" checkbox'us)

(function () {
  const STORAGE_KEY = "uzklausa-detail-blocks-v1";

  function restoreVisibility() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      document.querySelectorAll(".blokas").forEach((sec) => {
        const key = sec.getAttribute("data-block-key");
        if (key === "pagrindine") {
          // 1-as blokas visada matomas
          sec.style.display = "";
          return;
        }
        const visible = saved[key] !== false; // default: true
        sec.style.display = visible ? "" : "none";
        const cb = document.querySelector('.js-block-toggle[value="' + key + '"]');
        if (cb) cb.checked = visible;
      });
    } catch (e) {}
  }

  function persistVisibility() {
    const state = {};
    document.querySelectorAll(".blokas").forEach((sec) => {
      const key = sec.getAttribute("data-block-key");
      if (key === "pagrindine") return;
      state[key] = sec.style.display !== "none";
    });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  document.addEventListener("click", async function (e) {
    // "Stulpeliai" panelės ON/OFF (paliekam tavo mygtuką)
    const toggleBtn = e.target.closest(".js-columns-toggle");
    if (toggleBtn) {
      e.preventDefault();
      const panel = document.querySelector('[data-panel="stulpeliai"]');
      if (!panel) return;
      panel.style.display = panel.style.display === "none" || !panel.style.display ? "inline-block" : "none";
      return;
    }

    // Istorijos toggle (užkrova tik pirmą kartą)
    const link = e.target.closest(".js-history-link");
    if (link) {
      e.preventDefault();
      const targetSel = link.getAttribute("data-target");
      const box = document.querySelector(targetSel);
      if (!box) return;

      if (box.dataset.loaded === "1") {
        box.style.display = box.style.display === "none" || !box.style.display ? "" : "none";
        return;
      }

      box.style.display = "";
      box.innerHTML = "<em>Kraunama...</em>";
      try {
        const resp = await fetch(link.href, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        const html = await resp.text();
        box.innerHTML = html;
        box.dataset.loaded = "1"; // užkrovėm kartą – toliau tik perjungiame
      } catch (err) {
        box.innerHTML = '<span class="text-danger">Nepavyko užkrauti istorijos.</span>';
      }
      return;
    }
  });

  document.addEventListener("change", function (e) {
    // Checkbox'ai → rodyti/slėpti bloką
    const cb = e.target.closest(".js-block-toggle");
    if (!cb) return;

    const key = cb.value;
    if (key === "pagrindine") {
      // neleidžiam paslėpti 1-o bloko
      cb.checked = true;
      return;
    }
    const sec = document.querySelector('.blokas[data-block-key="' + key + '"]');
    if (sec) {
      sec.style.display = cb.checked ? "" : "none";
      persistVisibility();
    }
  });

  // Pritaikom išsaugotą būseną
  restoreVisibility();
})();

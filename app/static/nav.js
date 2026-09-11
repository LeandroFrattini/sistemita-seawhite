"use strict";
// Desplegables de la barra superior (Barcos / Reportes). El panel se saca del
// <nav> con scroll horizontal y se posiciona con position:fixed, igual que
// el popup de "otras agencias" del line-up, para que no se recorte.
(function () {
  function closeAll() {
    document.querySelectorAll(".nav-drop-panel").forEach((p) => (p.hidden = true));
  }

  document.querySelectorAll(".nav-group").forEach((group) => {
    const btn = group.querySelector(".nav-drop-btn");
    const panel = group.querySelector(".nav-drop-panel");
    if (!btn || !panel) return;
    document.body.appendChild(panel);
    panel.hidden = true;

    function place() {
      const r = btn.getBoundingClientRect();
      panel.style.visibility = "hidden";
      panel.hidden = false;
      const w = panel.offsetWidth || 180;
      panel.hidden = true;
      panel.style.visibility = "";
      let left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
      panel.style.left = left + "px";
      panel.style.top = r.bottom + 6 + "px";
    }

    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const willOpen = panel.hidden;
      closeAll();
      if (willOpen) {
        place();
        panel.hidden = false;
      }
    });
    panel.addEventListener("click", (ev) => ev.stopPropagation());
  });

  document.addEventListener("click", closeAll);
  window.addEventListener("scroll", closeAll, true);
  window.addEventListener("resize", closeAll);
})();

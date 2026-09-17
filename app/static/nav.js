"use strict";
// Desplegables de la barra superior (Line Up / Operaciones, y los flyouts
// anidados de Barcos/Reportes dentro de Operaciones). Cada panel se saca de
// su lugar original con position:fixed, igual que el popup de "otras
// agencias" del line-up, para que no se recorte por overflow del <nav>.
(function () {
  function closeAllTop() {
    document.querySelectorAll(".nav-drop-panel, .nav-sub-panel").forEach((p) => (p.hidden = true));
  }
  function closeAllSub() {
    document.querySelectorAll(".nav-sub-panel").forEach((p) => (p.hidden = true));
  }

  // Nivel 1: grupos de la barra (Line Up, Operaciones) -- el panel se abre
  // debajo del boton, como siempre.
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
      closeAllTop();
      if (willOpen) {
        place();
        panel.hidden = false;
      }
    });
    panel.addEventListener("click", (ev) => ev.stopPropagation());
  });

  // Nivel 2: submenus anidados (Barcos, Reportes dentro de Operaciones) --
  // se abren "para el costado" (a la derecha del boton, o a la izquierda si
  // no entra), sin cerrar el panel padre.
  document.querySelectorAll(".nav-subgroup").forEach((group) => {
    const btn = group.querySelector(".nav-sub-btn");
    const panel = group.querySelector(".nav-sub-panel");
    if (!btn || !panel) return;
    document.body.appendChild(panel);
    panel.hidden = true;

    function place() {
      const r = btn.getBoundingClientRect();
      panel.style.visibility = "hidden";
      panel.hidden = false;
      const w = panel.offsetWidth || 180;
      const h = panel.offsetHeight || 0;
      panel.hidden = true;
      panel.style.visibility = "";
      let left = r.right + 4;
      if (left + w > window.innerWidth - 8) left = Math.max(8, r.left - w - 4);
      let top = Math.min(r.top, window.innerHeight - h - 8);
      panel.style.left = left + "px";
      panel.style.top = top + "px";
    }

    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const willOpen = panel.hidden;
      closeAllSub();
      if (willOpen) {
        place();
        panel.hidden = false;
      }
    });
    panel.addEventListener("click", (ev) => ev.stopPropagation());
  });

  document.addEventListener("click", closeAllTop);
  window.addEventListener("scroll", closeAllTop, true);
  window.addEventListener("resize", closeAllTop);
})();

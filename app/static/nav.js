"use strict";
// Desplegables de la barra superior (Line Up / Operaciones). Cada panel se
// saca de su lugar original con position:fixed, igual que el popup de
// "otras agencias" del line-up, para que no se recorte por overflow del <nav>.
// El nivel 2 (.nav-subgroup / .nav-sub-panel) queda soportado por si algun
// dia se vuelve a anidar un submenu, aunque hoy ningun template lo usa.
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

  // Celular: el boton ☰ abre/cierra el menu vertical (.m-menu); en pantallas grandes no se ve.
  const toggle = document.getElementById("nav-toggle");
  if (toggle) {
    toggle.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const open = document.querySelector(".topbar").classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "✕" : "☰";
      toggle.setAttribute("aria-label", open ? "Cerrar el menú" : "Abrir el menú");
    });
  }

  document.addEventListener("click", closeAllTop);
  window.addEventListener("scroll", closeAllTop, true);
  window.addEventListener("resize", closeAllTop);
})();

// Aviso verde para Administracion: «PEPITO envió el voucher del barco MV X: queda para proformar».
// Se actualiza solo cada minuto; cada persona puede ocultar los suyos. Desaparece cuando la proforma del barco se guarda.
(function () {
  const caja = document.getElementById("avisos-proformar");
  if (!caja) return;
  const VER = 3;  // cuantos se muestran juntos; el resto se resume
  function pintar(lista) {
    caja.replaceChildren();
    caja.hidden = !lista.length;
    lista.slice(0, VER).forEach((a) => {
      const fila = document.createElement("div");
      fila.className = "avp-fila";
      const t = document.createElement("span");
      t.className = "avp-txt";
      const quien = document.createElement("b"); quien.textContent = a.quien.toUpperCase();
      t.append("✓ ", quien, " envió el voucher del barco ");
      const barco = document.createElement("b"); barco.textContent = a.barco + (a.agencia ? " (" + a.agencia + ")" : "");
      t.append(barco, " — queda para proformar" + (a.servicio === "HUSBANDRY" ? " (Husbandry)" : ""));
      const ir = document.createElement("a"); ir.href = a.url; ir.className = "avp-btn"; ir.textContent = "Proformar →";
      const x = document.createElement("button"); x.type = "button"; x.className = "avp-x"; x.setAttribute("aria-label", "Ocultar este aviso"); x.title = "Ocultar"; x.textContent = "×";
      x.addEventListener("click", () => {
        fila.remove();
        fetch("/avisos/proformar/" + a.id + "/ocultar", { method: "POST" }).then(cargar).catch(() => {});
      });
      fila.append(t, ir, x);
      caja.appendChild(fila);
    });
    if (lista.length > VER) {
      const mas = document.createElement("div"); mas.className = "avp-mas"; mas.textContent = "y " + (lista.length - VER) + " más para proformar";
      caja.appendChild(mas);
    }
  }
  function cargar() {
    fetch("/avisos/proformar", { headers: { Accept: "application/json" } })
      .then((r) => (r.ok && (r.headers.get("Content-Type") || "").includes("json") ? r.json() : null))
      .then((d) => { if (d && Array.isArray(d.avisos)) pintar(d.avisos); })
      .catch(() => {});
  }
  cargar();
  setInterval(() => { if (!document.hidden) cargar(); }, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) cargar(); });
})();

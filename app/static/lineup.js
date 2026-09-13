"use strict";

function flash(msg, ok = true) {
  const el = document.getElementById("flash");
  el.textContent = msg;
  el.className = "flash " + (ok ? "ok" : "err");
  el.hidden = false;
  clearTimeout(flash._t);
  flash._t = setTimeout(() => (el.hidden = true), 2500);
}

async function api(url, method, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).error || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.status === 204 ? {} : res.json();
}

function callId(el) {
  return el.closest("tr[data-call]").dataset.call;
}

// --- autocompletar fechas cortas (ETA/ETB/ETC) --------------------------- //
// "14-9", "14.9", "14 9" o "14/9" -> "14/09/26". Si no matchea un patron de
// fecha corta (por ej. texto libre como "At roads"), se deja tal cual.
const DATE_FIELDS = new Set(["eta", "etb", "etc"]);
function normalizeShortDate(raw) {
  const s = (raw || "").trim();
  const m = s.match(/^(\d{1,2})[/\-. ](\d{1,2})(?:[/\-. ](\d{2,4}))?$/);
  if (!m) return s;
  let [, d, mo, y] = m;
  const dn = +d, mn = +mo;
  if (dn < 1 || dn > 31 || mn < 1 || mn > 12) return s;
  d = d.padStart(2, "0");
  mo = mo.padStart(2, "0");
  y = y ? y.slice(-2).padStart(2, "0") : String(new Date().getFullYear()).slice(-2);
  return `${d}/${mo}/${y}`;
}

// --- edicion de celdas ---------------------------------------------------- //
document.querySelectorAll(".grid [data-f]").forEach((input) => {
  const evt = input.type === "checkbox" || input.tagName === "SELECT" ? "change" : "change";
  input.addEventListener(evt, async () => {
    const field = input.dataset.f;
    if (DATE_FIELDS.has(field)) {
      const normalized = normalizeShortDate(input.value);
      if (normalized !== input.value) input.value = normalized;
    }
    const value = input.type === "checkbox" ? input.checked : input.value;
    try {
      const r = await api(`/api/calls/${callId(input)}`, "PATCH", { field, value });
      const tr = input.closest("tr");
      if (field === "is_ours" || field === "local_agent") {
        tr.classList.toggle("is-ours", r.is_ours);
        const chk = tr.querySelector('[data-f="is_ours"]');
        if (chk) chk.checked = r.is_ours;
      }
      if (field === "principal") {
        input.classList.toggle("linked", r.linked);
      }
      flash("Guardado");
    } catch (e) {
      flash("Error: " + e.message, false);
    }
  });
});

// --- puerto del line-up (la fecha ya no se edita a mano) ---------------- //
["lineup-port"].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("change", async () => {
    try {
      await api("/api/lineup", "POST", { kind: el.dataset.kind || "GRAIN", port_name: el.value });
      flash("Guardado");
    } catch (e) {
      flash("Error: " + e.message, false);
    }
  });
});

// --- nota de estado del muelle (flammable) -------------------------- //
document.querySelectorAll("input[data-note]").forEach((el) => {
  el.addEventListener("change", async () => {
    try {
      await api(`/api/terminals/${el.dataset.note}/note`, "POST", { value: el.value });
      flash("Nota guardada");
    } catch (e) {
      flash("Error: " + e.message, false);
    }
  });
});

// --- agregar / mover / eliminar filas -------------------------------- //
document.querySelectorAll("[data-add]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    try {
      await api("/api/calls", "POST", { terminal_id: btn.dataset.add });
      location.reload();
    } catch (e) {
      flash("Error: " + e.message, false);
    }
  });
});

document.querySelectorAll(".grid").forEach((grid) => {
  grid.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button");
    if (!btn) return;
    const id = callId(btn);
    try {
      if (btn.dataset.move) {
        await api(`/api/calls/${id}/move`, "POST", { direction: btn.dataset.move });
        location.reload();
      } else if (btn.hasAttribute("data-del")) {
        if (!confirm("¿Eliminar este barco del line-up?")) return;
        await api(`/api/calls/${id}`, "DELETE");
        btn.closest("tr").remove();
        flash("Eliminado");
      }
    } catch (e) {
      flash("Error: " + e.message, false);
    }
  });
});

// --- panel de "otras agencias" (popup flotante, fuera del scroll) --- //
function closeExtras() {
  document.querySelectorAll(".extras-panel").forEach((p) => (p.hidden = true));
}

document.querySelectorAll(".extras-cell").forEach((cell) => {
  const toggle = cell.querySelector("[data-extras]");
  const panel = cell.querySelector(".extras-panel");
  const cnt = cell.querySelector(".cnt");
  document.body.appendChild(panel); // sacarlo de la tabla para que no se recorte
  panel.hidden = true;

  function open() {
    closeExtras();
    const r = toggle.getBoundingClientRect();
    const w = 260;
    let left = Math.min(Math.max(8, r.right - w), window.innerWidth - w - 8);
    panel.style.width = w + "px";
    panel.style.left = left + "px";
    panel.hidden = false;
    const h = panel.offsetHeight;
    let top = r.bottom + 4;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 4);
    panel.style.top = top + "px";
  }

  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    panel.hidden ? open() : (panel.hidden = true);
  });
  panel.addEventListener("click", (e) => e.stopPropagation());

  panel.addEventListener("change", async () => {
    const ids = [...panel.querySelectorAll("input:checked")].map((i) => i.value);
    cnt.textContent = ids.length;
    try {
      await api(`/api/calls/${callId(cell)}/extras`, "POST", { client_ids: ids });
      flash("Destinatarios guardados");
    } catch (e) {
      flash("Error: " + e.message, false);
    }
  });
});

document.addEventListener("click", closeExtras);
window.addEventListener(
  "scroll",
  (e) => {
    // no cerrar si el scroll pasa DENTRO del propio panel (la ruedita
    // sobre la lista de agencias) -- solo cerrar si scrollea la pagina
    // o algun contenedor por fuera del popup.
    if (e.target && e.target.closest && e.target.closest(".extras-panel")) return;
    closeExtras();
  },
  true
);
window.addEventListener("resize", closeExtras);

// --- recalcular por muelle ----------------------------------------- //
document.querySelectorAll("[data-recalc-term]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    try {
      const r = await api(`/api/terminals/${btn.dataset.recalcTerm}/recalc`, "POST");
      if (!r.count) {
        flash("Muelle sin cambios");
      } else {
        flash(`${r.count} fecha(s) ajustada(s)`);
        setTimeout(() => location.reload(), 900);
      }
    } catch (e) {
      flash("Error: " + e.message, false);
    }
  });
});

// --- recalcular TODO ---------------------------------------------- //
document.getElementById("btn-recalc").addEventListener("click", async (ev) => {
  const box = document.getElementById("recalc-result");
  const kind = ev.currentTarget.dataset.kind || "GRAIN";
  try {
    const r = await api("/api/recalc?kind=" + encodeURIComponent(kind), "POST");
    if (!r.count) {
      box.innerHTML = "<strong>Sin cambios.</strong> Todas las fechas ya estaban en cascada.";
    } else {
      box.innerHTML =
        `<strong>${r.count} cambios:</strong><ul>` +
        r.changes
          .map((c) => `<li>${c.vessel}: ${c.field} <s>${c.old || "—"}</s> → <b>${c.new}</b></li>`)
          .join("") +
        "</ul><em>Recargando…</em>";
    }
    box.hidden = false;
    if (r.count) setTimeout(() => location.reload(), 1400);
  } catch (e) {
    flash("Error: " + e.message, false);
  }
});

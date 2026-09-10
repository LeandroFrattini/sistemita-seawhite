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

// --- edicion de celdas ---------------------------------------------------- //
document.querySelectorAll(".grid [data-f]").forEach((input) => {
  const evt = input.type === "checkbox" || input.tagName === "SELECT" ? "change" : "change";
  input.addEventListener(evt, async () => {
    const field = input.dataset.f;
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

// --- fecha / puerto del line-up ---------------------------------------- //
["lineup-date", "lineup-port"].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("change", async () => {
    const key = id === "lineup-date" ? "lineup_date" : "port_name";
    try {
      await api("/api/lineup", "POST", { kind: el.dataset.kind || "GRAIN", [key]: el.value });
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

// --- panel de "otras agencias" -------------------------------------- //
document.querySelectorAll(".extras-cell").forEach((cell) => {
  const toggle = cell.querySelector("[data-extras]");
  const panel = cell.querySelector(".extras-panel");
  const cnt = cell.querySelector(".cnt");

  toggle.addEventListener("click", () => {
    document.querySelectorAll(".extras-panel").forEach((p) => {
      if (p !== panel) p.hidden = true;
    });
    panel.hidden = !panel.hidden;
  });

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

document.addEventListener("click", (ev) => {
  if (!ev.target.closest(".extras-cell")) {
    document.querySelectorAll(".extras-panel").forEach((p) => (p.hidden = true));
  }
});

// --- recalcular ------------------------------------------------------ //
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

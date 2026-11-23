const form = document.querySelector("#form");
const err = document.querySelector("#err");
const chart = document.querySelector("#chart");
const table = document.querySelector("#table");
const legend = document.querySelector("#legend");

const COLORS = {
  black_scholes: "rgba(236,230,216,0.55)",
  merton: "#c4a574",
  variance_gamma: "#8fb3a3",
  nig: "#b9c3cc",
  heston: "#d67860",
  bates: "#a68fc4",
};

let hidden = new Set();
let latest = null;

function cell(tag, text) {
  const el = document.createElement(tag);
  el.textContent = text;
  return el;
}

function pct(v) {
  return v === null || !Number.isFinite(v) ? "—" : `${(v * 100).toFixed(2)}%`;
}

function paint() {
  if (!latest) return;
  const shown = latest.models.filter((m) => !hidden.has(m.name));
  multiLineChart(
    chart,
    latest.strikes,
    shown.map((m) => ({ ys: m.vols.map((v) => (v === null ? null : v * 100)), color: COLORS[m.name] })),
    { yLabel: "implied vol %", marker: latest.forward, digits: 0 }
  );
  legend.replaceChildren(
    ...latest.models.map((m) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.setAttribute("aria-pressed", String(!hidden.has(m.name)));
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = COLORS[m.name];
      button.append(swatch, document.createTextNode(m.label));
      button.addEventListener("click", () => {
        if (hidden.has(m.name)) hidden.delete(m.name);
        else hidden.add(m.name);
        paint();
      });
      return button;
    })
  );
  table.replaceChildren();
  const head = document.createElement("tr");
  head.append(cell("th", "strike"), ...latest.models.map((m) => cell("th", m.label)));
  table.append(head);
  const atm = document.createElement("tr");
  atm.append(cell("td", "ATM-fwd call"), ...latest.models.map((m) => cell("td", m.atm_forward_call.toFixed(4))));
  table.append(atm);
  latest.strikes.forEach((k, i) => {
    const tr = document.createElement("tr");
    tr.append(cell("td", k.toFixed(2)), ...latest.models.map((m) => cell("td", pct(m.vols[i]))));
    table.append(tr);
  });
}

async function run() {
  err.textContent = "";
  const qs = new URLSearchParams(new FormData(form));
  history.replaceState(null, "", `/models?${qs.toString()}`);
  const res = await fetch(`/api/models?${qs.toString()}`);
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "pricing failed";
    return;
  }
  latest = data;
  paint();
}

new URLSearchParams(window.location.search).forEach((value, key) => {
  const field = form.elements.namedItem(key);
  if (field) field.value = value;
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});

window.addEventListener("resize", () => paint());
run().catch((exc) => {
  err.textContent = String(exc);
});

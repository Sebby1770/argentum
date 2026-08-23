const form = document.querySelector("#form");
const err = document.querySelector("#err");
const metrics = document.querySelector("#metrics");
const compare = document.querySelector("#compare");
const chart = document.querySelector("#chart");

function metric(label, value) {
  const el = document.createElement("div");
  el.className = "metric";
  el.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
  return el;
}

async function mark() {
  err.textContent = "";
  const body = Object.fromEntries(new FormData(form).entries());
  const res = await fetch("/api/vanilla", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "mark failed";
    return;
  }
  metrics.replaceChildren(
    metric("NPV", data.npv.toFixed(6)),
    metric("Tree", data.tree.toFixed(6)),
    metric("Delta", data.greeks.delta.toFixed(4)),
    metric("Gamma", data.greeks.gamma.toFixed(5)),
    metric("Vega", data.greeks.vega.toFixed(4)),
    metric("Theta", data.greeks.theta.toFixed(4)),
    metric("Rho", data.greeks.rho.toFixed(4)),
    metric("Volga", data.greeks.volga.toFixed(4))
  );
  compare.textContent = `Analytic − tree = ${(data.npv - data.tree).toFixed(6)} · intrinsic ${data.intrinsic.toFixed(4)}`;
  lineChart(chart, data.grid.spot, data.grid.value, { color: "#c4a574", yLabel: "value", zero: true });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  mark().catch((exc) => {
    err.textContent = String(exc);
  });
});

mark().catch(() => {});

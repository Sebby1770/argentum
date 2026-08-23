const form = document.querySelector("#form");
const err = document.querySelector("#err");
const metrics = document.querySelector("#metrics");
const table = document.querySelector("#table");

function metric(label, value) {
  const el = document.createElement("div");
  el.className = "metric";
  el.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
  return el;
}

async function run() {
  err.textContent = "";
  const res = await fetch("/api/book", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "book failed";
    return;
  }
  metrics.replaceChildren(
    metric("NPV", data.npv.toFixed(4)),
    metric("Delta", data.greeks.delta.toFixed(4)),
    metric("Vega", data.greeks.vega.toFixed(4)),
    metric("N", String(data.n))
  );
  table.innerHTML =
    "<tr><th>scenario</th><th>NPV</th><th>PnL</th><th>delta</th></tr>" +
    data.scenarios
      .map(
        (row) =>
          `<tr><td>${row.label}</td><td>${row.npv.toFixed(4)}</td><td>${row.pnl.toFixed(4)}</td><td>${row.delta.toFixed(4)}</td></tr>`
      )
      .join("");
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});
run().catch(() => {});

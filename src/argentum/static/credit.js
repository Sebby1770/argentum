const form = document.querySelector("#form");
const err = document.querySelector("#err");
const metrics = document.querySelector("#metrics");
const table = document.querySelector("#table");
const blurb = document.querySelector("#blurb");

function metric(label, value) {
  const el = document.createElement("div");
  el.className = "metric";
  el.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
  return el;
}

async function run() {
  err.textContent = "";
  const qs = new URLSearchParams(new FormData(form)).toString();
  const res = await fetch(`/api/credit?${qs}`);
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "credit failed";
    return;
  }
  const money = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  metrics.replaceChildren(
    metric("Par", (data.par * 10000).toFixed(1) + " bp"),
    metric("NPV", money.format(data.npv)),
    metric("Upfront", (data.upfront * 100).toFixed(2) + "%"),
    metric("Protection", money.format(data.protection))
  );
  table.innerHTML =
    "<tr><th>T</th><th>boot hazard</th></tr>" +
    data.boot_hazards.map((row) => `<tr><td>${row.t.toFixed(0)}y</td><td>${(row.h * 100).toFixed(3)}%</td></tr>`).join("");
  blurb.textContent = `Evaluation date ${data.as_of}. Hazard, recovery, coupon, and curve inputs are decimal fractions.`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});
run().catch(() => {});

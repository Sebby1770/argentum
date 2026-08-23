const form = document.querySelector("#form");
const err = document.querySelector("#err");
const metrics = document.querySelector("#metrics");

function metric(label, value) {
  const el = document.createElement("div");
  el.className = "metric";
  el.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
  return el;
}

async function run() {
  err.textContent = "";
  const qs = new URLSearchParams(new FormData(form)).toString();
  const res = await fetch(`/api/bond?${qs}`);
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "bond failed";
    return;
  }
  metrics.replaceChildren(
    metric("Dirty", data.dirty.toFixed(4)),
    metric("Clean", data.clean.toFixed(4)),
    metric("Accrued", data.accrued.toFixed(4)),
    metric("Macaulay", data.macaulay.toFixed(3)),
    metric("Modified", data.modified.toFixed(3)),
    metric("Convexity", data.convexity.toFixed(3))
  );
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});

run().catch(() => {});

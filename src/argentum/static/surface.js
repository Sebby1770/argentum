const form = document.querySelector("#form");
const err = document.querySelector("#err");
const heat = document.querySelector("#heat");

async function run() {
  err.textContent = "";
  const qs = new URLSearchParams(new FormData(form)).toString();
  const res = await fetch(`/api/surface?${qs}`);
  const data = await res.json();
  if (!res.ok) {
    err.textContent = data.error || "surface failed";
    return;
  }
  const vols = data.grid.map((row) => row.vol);
  const lo = Math.min(...vols);
  const hi = Math.max(...vols);
  const tone = (v) => {
    const t = hi === lo ? 0.5 : (v - lo) / (hi - lo);
    const g = Math.round(80 + t * 90);
    const b = Math.round(90 + (1 - t) * 80);
    return `rgb(${g + 40}, ${g}, ${b})`;
  };
  const header =
    `<div class="heat-row"><div class="heat-cell">T\\K</div>` +
    data.strikes.map((k) => `<div class="heat-cell">${(k / data.forward).toFixed(2)}</div>`).join("") +
    "</div>";
  const rows = data.tenors
    .map((t) => {
      const cells = data.strikes
        .map((k) => {
          const hit = data.grid.find((row) => row.texp === t && row.strike === k);
          const v = hit ? hit.vol : 0;
          return `<div class="heat-cell" style="background:${tone(v)}">${(v * 100).toFixed(1)}</div>`;
        })
        .join("");
      return `<div class="heat-row"><div class="heat-cell">${t}y</div>${cells}</div>`;
    })
    .join("");
  heat.innerHTML = header + rows;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  run().catch((exc) => {
    err.textContent = String(exc);
  });
});
run().catch(() => {});

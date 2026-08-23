const ARGENTUM_LINKS = [
  ["/", "Front"],
  ["/lab", "Lab"],
  ["/smile", "Smile"],
  ["/surface", "Surface"],
  ["/heston", "Heston"],
  ["/rates", "Rates"],
  ["/bond", "Bond"],
  ["/credit", "Credit"],
  ["/book", "Book"],
  ["/docs", "Docs"],
];

function argentumPath() {
  const p = window.location.pathname.replace(/\/$/, "");
  return p || "/";
}

function paintNav() {
  const nav = document.querySelector("header.top nav");
  if (!nav) return;
  const here = argentumPath();
  nav.innerHTML = ARGENTUM_LINKS.map(([href, label]) => {
    const current = here === href ? ' aria-current="page"' : "";
    return `<a href="${href}"${current}>${label}</a>`;
  }).join("");
}

function ensurePalette() {
  if (document.querySelector("#cmd-palette")) return;
  const wrap = document.createElement("div");
  wrap.id = "cmd-palette";
  wrap.hidden = true;
  wrap.innerHTML =
    '<div class="cmd-card"><p class="eyebrow">Jump</p><input id="cmd-input" type="search" placeholder="lab, smile, heston…" autocomplete="off" /><ul id="cmd-list"></ul><p class="note">Press K</p></div>';
  document.body.appendChild(wrap);
  const input = wrap.querySelector("#cmd-input");
  const list = wrap.querySelector("#cmd-list");
  function render(q) {
    const needle = q.trim().toLowerCase();
    const rows = ARGENTUM_LINKS.filter(
      ([href, label]) => !needle || href.toLowerCase().includes(needle) || label.toLowerCase().includes(needle)
    );
    list.innerHTML = rows.map(([href, label]) => `<li><a href="${href}">${label}</a></li>`).join("");
  }
  input.addEventListener("input", () => render(input.value));
  wrap.addEventListener("click", (event) => {
    if (event.target === wrap) wrap.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "k" || event.key === "K") {
      if (event.target && ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
      event.preventDefault();
      wrap.hidden = !wrap.hidden;
      if (!wrap.hidden) {
        render("");
        input.focus();
      }
    }
    if (event.key === "Escape") wrap.hidden = true;
  });
  render("");
}

function registerSW() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}

paintNav();
ensurePalette();
registerSW();

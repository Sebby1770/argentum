const ARGENTUM_LINKS = [
  ["/", "Front"],
  ["/#connect", "Market"],
  ["/lab", "Lab"],
  ["/smile", "Smile"],
  ["/surface", "Surface"],
  ["/heston", "Heston"],
  ["/rates", "Rates"],
  ["/bond", "Bond"],
  ["/credit", "Credit"],
  ["/book", "Portfolio"],
  ["/docs", "Docs"],
];

let argentumSession;

async function argentumSessionToken() {
  if (!argentumSession) {
    argentumSession = fetch("/api/session", { credentials: "same-origin" })
      .then((res) => {
        if (!res.ok) throw new Error("Could not establish a local Studio session");
        return res.json();
      })
      .then((data) => data.csrf);
  }
  return argentumSession;
}

async function argentumFetch(input, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("X-Argentum-CSRF", await argentumSessionToken());
  return fetch(input, { ...init, headers, credentials: "same-origin" });
}

window.argentumFetch = argentumFetch;

function argentumPath() {
  const p = window.location.pathname.replace(/\/$/, "");
  return p || "/";
}

function paintNav() {
  const nav = document.querySelector("header.top nav");
  if (!nav) return;
  const here = argentumPath();
  const hash = window.location.hash;
  nav.innerHTML = ARGENTUM_LINKS.map(([href, label]) => {
    let on = here === href;
    if (href === "/#connect") on = here === "/" && hash === "#connect";
    else if (href === "/") on = here === "/" && hash !== "#connect";
    const current = on ? ' aria-current="page"' : "";
    return `<a href="${href}"${current}>${label}</a>`;
  }).join("");
}

function paintBreadcrumbs() {
  const main = document.querySelector("main");
  const here = argentumPath();
  if (!main || here === "/" || document.querySelector(".studio-breadcrumbs")) return;
  const current = ARGENTUM_LINKS.find(([href]) => href === here);
  const trail = document.createElement("nav");
  trail.className = "wrap studio-breadcrumbs";
  trail.setAttribute("aria-label", "Breadcrumb");
  const home = document.createElement("a");
  home.href = "/";
  home.textContent = "Front";
  const label = document.createElement("span");
  label.textContent = current ? current[1] : document.title.split("—")[0].trim();
  label.setAttribute("aria-current", "page");
  trail.append(home, document.createTextNode(" / "), label);
  main.before(trail);
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
paintBreadcrumbs();
window.addEventListener("hashchange", paintNav);
ensurePalette();
registerSW();

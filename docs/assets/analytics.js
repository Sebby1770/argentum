(async () => {
  const SETTINGS_KEY = "argentum.analytics-consent";
  const controls = document.querySelectorAll("[data-analytics-settings]");
  let config;
  try {
    config = await fetch("/argentum/assets/site-config.json", { cache: "no-store" }).then((res) => res.json());
  } catch {
    return;
  }
  const id = String(config.googleAnalyticsId || "").trim();
  if (!/^G-[A-Z0-9]+$/.test(id)) return;
  controls.forEach((control) => { control.hidden = false; });

  function loadAnalytics() {
    if (document.querySelector("script[data-argentum-ga]")) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", id, { anonymize_ip: true });
    const script = document.createElement("script");
    script.async = true;
    script.dataset.argentumGa = "true";
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
    document.head.appendChild(script);
  }

  function ask() {
    document.querySelector(".consent")?.remove();
    const panel = document.createElement("aside");
    panel.className = "consent";
    panel.setAttribute("aria-label", "Analytics choice");
    const copy = document.createElement("p");
    copy.textContent = "May Argentum load Google Analytics to measure public-site visits? It stays off unless you choose allow.";
    const actions = document.createElement("div");
    actions.className = "actions";
    const allow = document.createElement("button");
    allow.className = "button";
    allow.type = "button";
    allow.textContent = "Allow analytics";
    const decline = document.createElement("button");
    decline.className = "button secondary";
    decline.type = "button";
    decline.textContent = "No thanks";
    actions.append(allow, decline);
    panel.append(copy, actions);
    document.body.appendChild(panel);
    allow.addEventListener("click", () => {
      localStorage.setItem(SETTINGS_KEY, "granted");
      panel.remove();
      loadAnalytics();
    });
    decline.addEventListener("click", () => {
      localStorage.setItem(SETTINGS_KEY, "denied");
      panel.remove();
    });
  }

  controls.forEach((control) => control.addEventListener("click", ask));
  const choice = localStorage.getItem(SETTINGS_KEY);
  if (choice === "granted") loadAnalytics();
  else if (choice !== "denied") ask();
})();

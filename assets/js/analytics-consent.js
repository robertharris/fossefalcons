(() => {
  "use strict";

  const panel = document.getElementById("analytics-consent");
  const status = document.getElementById("analytics-consent-status");
  const measurementId = panel.dataset.measurementId;
  // Changing the ID invalidates consent previously given to another stream.
  const storageKey = `fosse-analytics-consent-v1:${measurementId}`;
  const lifetime = 180 * 24 * 60 * 60 * 1000;
  let returnFocus;
  let analyticsStarted = false;

  function show(message = "", focus = false) {
    status.textContent = message;
    panel.hidden = false;
    if (focus) panel.focus();
  }

  function hide() {
    panel.hidden = true;
    if (returnFocus) returnFocus.focus();
  }

  function storageError(error) {
    console.error("Could not access the analytics consent preference.", error);
    show("Your browser could not save or read your cookie choice. Analytics is off for this page. Please allow this site's preference storage to remember your decision.");
  }

  function readChoice() {
    let raw;
    try {
      raw = localStorage.getItem(storageKey);
    } catch (error) {
      storageError(error);
      return undefined;
    }
    if (!raw) return null;
    let saved;
    try {
      saved = JSON.parse(raw);
    } catch (error) {
      console.warn("Invalid analytics consent preference; asking again.", error);
      return null;
    }
    if (!saved || !["accepted", "rejected"].includes(saved.choice) ||
        !Number.isFinite(saved.time) || saved.time > Date.now() ||
        Date.now() - saved.time >= lifetime) return null;
    return saved.choice;
  }

  function clearAnalyticsCookies() {
    const domains = window.location.hostname.split(".");
    const suffixes = [""];
    while (domains.length > 1) {
      suffixes.push(`; domain=${domains.join(".")}`, `; domain=.${domains.join(".")}`);
      domains.shift();
    }
    for (const cookie of document.cookie.split(";")) {
      const name = cookie.trim().split("=")[0];
      if (!/^_ga(?:_|$)/.test(name)) continue;
      for (const domain of suffixes) {
        document.cookie = `${name}=; Max-Age=0; path=/${domain}; SameSite=Lax`;
      }
    }
  }

  function stopAnalytics() {
    window[`ga-disable-${measurementId}`] = true;
    clearAnalyticsCookies();
  }

  function startAnalytics() {
    window[`ga-disable-${measurementId}`] = false;
    if (analyticsStarted) return;
    analyticsStarted = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("consent", "default", {
      analytics_storage: "granted",
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
    });
    window.gtag("js", new Date());
    window.gtag("config", measurementId, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      cookie_path: "/",
      cookie_expires: lifetime / 1000,
      cookie_update: false,
      // Do not send query strings, fragments or referrer parameters to Google.
      page_location: window.location.origin + window.location.pathname,
      page_referrer: document.referrer.split(/[?#]/)[0],
    });
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
    script.addEventListener("error", () => {
      console.error("Google Analytics could not be loaded.");
      show("Google Analytics could not be loaded. You can continue using the site normally.");
    });
    document.head.appendChild(script);
  }

  document.querySelectorAll("[data-analytics-settings]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      returnFocus = link;
      const choice = measurementId ? readChoice() : null;
      show(choice ? `Your current choice is ${choice === "accepted" ? "Accept" : "Reject"}.` :
        choice === undefined ? status.textContent : "", true);
    });
  });
  panel.querySelector("[data-analytics-close]").addEventListener("click", hide);
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });

  panel.querySelectorAll("[data-analytics-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      const choice = button.dataset.analyticsChoice;
      // Disable collection immediately, even if saving a rejection fails.
      if (choice === "rejected") stopAnalytics();
      try {
        localStorage.setItem(storageKey, JSON.stringify({ choice, time: Date.now() }));
      } catch (error) {
        stopAnalytics();
        storageError(error);
        return;
      }
      hide();
      if (choice === "accepted") startAnalytics();
      // Remove the already-loaded Google script and its event handlers on withdrawal.
      else if (analyticsStarted) window.location.reload();
    });
  });

  if (!measurementId) return;
  const choice = readChoice();
  if (choice === "accepted") startAnalytics();
  else {
    stopAnalytics();
    if (!choice) show(status.textContent);
  }
  window.addEventListener("storage", (event) => {
    if (event.key !== storageKey && event.key !== null) return;
    // Reload with the latest decision, including withdrawal in another tab.
    stopAnalytics();
    window.location.reload();
  });
})();

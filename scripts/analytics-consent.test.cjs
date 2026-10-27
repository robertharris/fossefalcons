const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const { runInNewContext } = require("node:vm");

const source = readFileSync(join(__dirname, "..", "assets", "js", "analytics-consent.js"), "utf8");
const id = "G-TEST123";
const key = `fosse-analytics-consent-v1:${id}`;
const lifetime = 180 * 24 * 60 * 60 * 1000;

function element(dataset = {}) {
  const handlers = {};
  return {
    dataset, handlers, hidden: true, textContent: "", focused: false,
    addEventListener(name, handler) { handlers[name] = handler; },
    focus() { this.focused = true; },
    click() { handlers.click({ preventDefault() {} }); },
  };
}

function setup(options = {}) {
  const measurementId = options.id === undefined ? id : options.id;
  const accept = element({ analyticsChoice: "accepted" });
  const reject = element({ analyticsChoice: "rejected" });
  const close = element();
  const settings = element();
  const status = element();
  const panel = element({ measurementId });
  panel.querySelector = () => close;
  panel.querySelectorAll = () => measurementId ? [accept, reject] : [];
  const stored = new Map(options.stored || []);
  const scripts = [];
  const cookieWrites = [];
  const errors = [];
  const warnings = [];
  let reloads = 0;
  const window = element();
  window.location = {
    hostname: "www.fossefalcons.co.uk",
    origin: "https://www.fossefalcons.co.uk",
    pathname: "/join/",
    search: "?email=private@example.com",
    hash: "#private",
    reload() { reloads++; },
  };
  const document = {
    referrer: "https://example.com/start?private=value#private",
    getElementById(name) { return name === "analytics-consent" ? panel : status; },
    querySelectorAll() { return [settings]; },
    createElement() { return element(); },
    head: { appendChild(script) { scripts.push(script); } },
    get cookie() { return "_ga=old; _ga_TEST123=session; unrelated=keep"; },
    set cookie(value) { cookieWrites.push(value); },
  };
  const localStorage = {
    getItem(name) {
      if (options.readError) throw new Error("Storage blocked");
      return stored.get(name) || null;
    },
    setItem(name, value) {
      if (options.writeError) throw new Error("Storage blocked");
      stored.set(name, value);
    },
  };
  runInNewContext(source, {
    document, window, localStorage,
    console: { error(...args) { errors.push(args); }, warn(...args) { warnings.push(args); } },
  });
  return {
    accept, reject, close, settings, status, panel, stored, scripts,
    cookieWrites, errors, warnings, window,
    get reloads() { return reloads; },
  };
}

function saved(choice, time = Date.now()) {
  return [[key, JSON.stringify({ choice, time })]];
}

test("no ID means no prompt, storage choice or Google requests", () => {
  const app = setup({ id: "" });
  assert.equal(app.panel.hidden, true);
  assert.equal(app.scripts.length, 0);
  assert.equal(app.stored.size, 0);
  app.settings.click();
  assert.equal(app.panel.hidden, false);
  assert.equal(app.panel.focused, true);
});

test("first visit asks for consent without loading Google or creating a data layer", () => {
  const app = setup();
  assert.equal(app.panel.hidden, false);
  assert.equal(app.scripts.length, 0);
  assert.equal(app.window.dataLayer, undefined);
  assert.equal(app.stored.size, 0);
  assert.equal(app.window[`ga-disable-${id}`], true);
});

test("Accept persists consent and loads Analytics only once with advertising denied", () => {
  const app = setup();
  app.accept.click();
  app.accept.click();
  assert.equal(JSON.parse(app.stored.get(key)).choice, "accepted");
  assert.equal(app.panel.hidden, true);
  assert.equal(app.scripts.length, 1);
  assert.equal(app.scripts[0].src, `https://www.googletagmanager.com/gtag/js?id=${id}`);
  const commands = app.window.dataLayer.map((args) => Array.from(args));
  assert.equal(commands[0][0], "consent");
  assert.equal(commands[0][2].analytics_storage, "granted");
  for (const name of ["ad_storage", "ad_user_data", "ad_personalization"]) {
    assert.equal(commands[0][2][name], "denied");
  }
  const config = commands.find((args) => args[0] === "config")[2];
  assert.equal(config.allow_google_signals, false);
  assert.equal(config.allow_ad_personalization_signals, false);
  assert.equal(config.cookie_expires, lifetime / 1000);
  assert.equal(config.cookie_update, false);
  assert.equal(config.page_location, "https://www.fossefalcons.co.uk/join/");
  assert.equal(config.page_referrer, "https://example.com/start");
});

test("Reject is remembered and never loads Analytics", () => {
  const app = setup();
  app.reject.click();
  assert.equal(JSON.parse(app.stored.get(key)).choice, "rejected");
  assert.equal(app.scripts.length, 0);
  const next = setup({ stored: Array.from(app.stored) });
  assert.equal(next.panel.hidden, true);
  assert.equal(next.scripts.length, 0);
});

test("valid saved acceptance loads Analytics on subsequent pages", () => {
  const app = setup({ stored: saved("accepted") });
  assert.equal(app.panel.hidden, true);
  assert.equal(app.scripts.length, 1);
});

test("footer reopens controls with current choice and Close restores focus", () => {
  const app = setup({ stored: saved("rejected") });
  app.settings.click();
  assert.match(app.status.textContent, /Reject/);
  assert.equal(app.panel.focused, true);
  app.close.click();
  assert.equal(app.panel.hidden, true);
  assert.equal(app.settings.focused, true);
  app.settings.click();
  app.panel.handlers.keydown({ key: "Escape" });
  assert.equal(app.panel.hidden, true);
});

test("withdrawal disables Analytics, clears only GA cookies and reloads", () => {
  const app = setup({ stored: saved("accepted") });
  app.settings.click();
  app.reject.click();
  assert.equal(app.window[`ga-disable-${id}`], true);
  assert.equal(JSON.parse(app.stored.get(key)).choice, "rejected");
  assert.equal(app.reloads, 1);
  assert.ok(app.cookieWrites.some((value) => value.startsWith("_ga=;")));
  assert.ok(app.cookieWrites.some((value) => value.includes("domain=.fossefalcons.co.uk")));
  assert.ok(app.cookieWrites.every((value) => /^_ga(?:_|=)/.test(value)));
  assert.ok(app.cookieWrites.every((value) => value.includes("Max-Age=0; path=/")));
});

test("expired, future, malformed or invalid preferences never grant consent", () => {
  const invalid = [
    JSON.stringify({ choice: "accepted", time: Date.now() - lifetime }),
    JSON.stringify({ choice: "accepted", time: Date.now() + lifetime }),
    JSON.stringify({ choice: "accepted", time: "yesterday" }),
    JSON.stringify({ choice: "other", time: Date.now() }),
    "{broken", "null",
  ];
  for (const raw of invalid) {
    const app = setup({ stored: [[key, raw]] });
    assert.equal(app.panel.hidden, false);
    assert.equal(app.scripts.length, 0);
  }
  assert.equal(setup({ stored: [[key, "{broken"]] }).warnings.length, 1);
});

test("a different measurement ID requires new consent", () => {
  const app = setup({ id: "G-NEW123", stored: saved("accepted") });
  assert.equal(app.scripts.length, 0);
  assert.equal(app.panel.hidden, false);
});

test("storage read failure fails closed and remains visible when opening settings", () => {
  const app = setup({ readError: true });
  assert.equal(app.scripts.length, 0);
  assert.match(app.status.textContent, /could not save or read/);
  assert.equal(app.errors.length, 1);
  app.settings.click();
  assert.match(app.status.textContent, /could not save or read/);
});

test("storage write failure does not start Analytics and displays an error", () => {
  const app = setup({ writeError: true });
  app.accept.click();
  assert.equal(app.scripts.length, 0);
  assert.equal(app.window[`ga-disable-${id}`], true);
  assert.equal(app.panel.hidden, false);
  assert.match(app.status.textContent, /Analytics is off/);
  assert.equal(app.errors.length, 1);
});

test("failed withdrawal persistence still stops collection and reports the failure", () => {
  const app = setup({ stored: saved("accepted"), writeError: true });
  app.reject.click();
  assert.equal(app.window[`ga-disable-${id}`], true);
  assert.equal(app.reloads, 0);
  assert.match(app.status.textContent, /could not save or read/);
});

test("preference updates or clearing storage in another tab stops collection and reloads", () => {
  for (const changedKey of [key, null]) {
    const app = setup({ stored: saved("accepted") });
    app.window.handlers.storage({ key: "unrelated" });
    assert.equal(app.reloads, 0);
    app.window.handlers.storage({ key: changedKey });
    assert.equal(app.window[`ga-disable-${id}`], true);
    assert.equal(app.reloads, 1);
  }
});

test("script load errors are explicitly reported without blocking the site", () => {
  const app = setup({ stored: saved("accepted") });
  app.scripts[0].handlers.error();
  assert.equal(app.errors.length, 1);
  assert.equal(app.panel.hidden, false);
  assert.match(app.status.textContent, /could not be loaded/);
});

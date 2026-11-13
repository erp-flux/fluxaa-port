/* FLUXAA Port — field application (CDC EF-14, ENF-6).
 *
 * Installable and fully usable offline once the page has been opened online:
 *  - the call bundle (milestone types, interruption causes, open interruptions, milestones awaiting
 *    your countersignature, your tasks) and the queue of entries live in IndexedDB on the device
 *    (database "fluxaa-field": store "bundles" keyed by call reference, store "queue" keyed by
 *    client_uuid); localStorage is used only when IndexedDB is unavailable;
 *  - every entry keeps the declared time of the fact and the time it was saved on the device (double
 *    timestamp); the registry adds its own time on receipt and marks late arrivals "saisie différée";
 *  - a competing entry never overwrites anything: the registry records it and opens a dispute.
 * Vanilla JavaScript, no external resource. Every visible string comes from the #field-i18n block. */
(function () {
  "use strict";

  var root = document.getElementById("field-app");
  if (!root) { return; }

  // =========================================================================== configuration and strings
  function readJSON(id) {
    var node = document.getElementById(id);
    if (!node) { return {}; }
    try { return JSON.parse(node.textContent || "{}") || {}; } catch (err) { return {}; }
  }

  var CONFIG = readJSON("field-config");
  var STRINGS = readJSON("field-i18n");
  var REF = String(CONFIG.reference || "");
  if (!REF || !CONFIG.bundleUrl || !CONFIG.syncUrl) { return; }

  var SW_URL = "/sw.js";
  var DB_NAME = "fluxaa-field";
  var LS_PREFIX = "fluxaa-field:";
  var BATCH_SIZE = 50;                       // entries per synchronisation request
  var BATCH_BYTES = 4 * 1024 * 1024;         // keeps batches of photos well under the upload limits
  var SYNC_EVERY_MS = 60 * 1000;
  var FUTURE_TOLERANCE_MS = 5 * 60 * 1000;   // the registry refuses facts declared in the future
  var PHOTO_MAX_SIDE = 1600;
  var PHOTO_QUALITY = 0.8;
  var RESULTS_KEPT = 30;
  var TERMINAL_STATUSES = ["CLOSED", "ARCHIVED", "REJECTED", "CANCELLED"];
  var FIELD_PAGE = /^\/escales\/\d+\/terrain\/$/;

  function has(object, key) {
    return object !== null && typeof object === "object" && Object.prototype.hasOwnProperty.call(object, key);
  }

  function t(key, params) {
    var text = has(STRINGS, key) ? String(STRINGS[key]) : key;
    if (params) {
      text = text.replace(/\{(\w+)\}/g, function (match, name) {
        return has(params, name) ? String(params[name]) : match;
      });
    }
    return text;
  }

  // =========================================================================== small helpers
  function byId(id) { return document.getElementById(id); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function truncate(text, max) { return text.length > max ? text.slice(0, max - 1) + "…" : text; }
  function cssEscape(value) {
    return window.CSS && typeof window.CSS.escape === "function" ? window.CSS.escape(value) : String(value).replace(/["\\]/g, "\\$&");
  }
  function logError(err) { if (window.console && console.error) { console.error("[FLUXAA field]", err); } }

  function append(node, children) {
    if (children === null || children === undefined || children === false) { return; }
    if (Array.isArray(children)) { children.forEach(function (child) { append(node, child); }); return; }
    node.appendChild(typeof children === "object" ? children : document.createTextNode(String(children)));
  }

  /* Builds DOM nodes; text always goes through text nodes (never innerHTML). */
  function h(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (name) {
        var value = attrs[name];
        if (value === null || value === undefined || value === false) { return; }
        if (name === "class") { node.className = value; } else { node.setAttribute(name, value === true ? "" : String(value)); }
      });
    }
    append(node, children);
    return node;
  }

  function chip(kind, text) { return h("span", {class: "chip " + kind}, text); }

  // ------------------------------------------------------------------ times
  function toDate(value) {
    if (value instanceof Date) { return isNaN(value.getTime()) ? null : value; }
    if (!value) { return null; }
    var date = new Date(String(value).replace(/(\.\d{3})\d+/, "$1"));
    return isNaN(date.getTime()) ? null : date;
  }
  function timeValue(value) { var date = toDate(value); return date ? date.getTime() : 0; }

  /* Times are shown as on the device clock: "dd/mm HH:MM" (the format used across the registry). */
  function fmt(value, withSeconds) {
    var date = toDate(value);
    if (!date) { return "—"; }
    var text = pad(date.getDate()) + "/" + pad(date.getMonth() + 1) + " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
    return withSeconds ? text + ":" + pad(date.getSeconds()) : text;
  }

  function offsetLabel(minutes) {
    var abs = Math.abs(minutes);
    return "UTC" + (minutes < 0 ? "-" : "+") + pad(Math.floor(abs / 60)) + ":" + pad(abs % 60);
  }

  /* ISO 8601 with the device's own offset, e.g. 2026-10-24T14:32:00+01:00 */
  function isoWithOffset(date) {
    var offset = -date.getTimezoneOffset();
    var abs = Math.abs(offset);
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + "T" + pad(date.getHours()) +
      ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds()) + (offset < 0 ? "-" : "+") + pad(Math.floor(abs / 60)) +
      ":" + pad(abs % 60);
  }

  /* Value for <input type="datetime-local"> in device time. */
  function inputValue(date) {
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + "T" + pad(date.getHours()) + ":" +
      pad(date.getMinutes());
  }

  function inputToDate(value) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/.exec(String(value || "").trim());
    if (!m) { return null; }
    var date = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0), 0);
    return isNaN(date.getTime()) ? null : date;
  }

  /* Offset of the port time zone at *date*, in minutes (null when the browser cannot tell). */
  function portOffsetMinutes(timeZone, date) {
    try {
      var parts = {};
      new Intl.DateTimeFormat("en-GB", {
        timeZone: timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
      }).formatToParts(date).forEach(function (part) { parts[part.type] = part.value; });
      var asUtc = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour % 24, +parts.minute);
      return Math.round((asUtc - Math.floor(date.getTime() / 60000) * 60000) / 60000);
    } catch (err) {
      return null;
    }
  }

  function uuid4() {
    var cryptoApi = window.crypto || window.msCrypto;
    if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
      try { return cryptoApi.randomUUID(); } catch (err) { /* insecure context: fall through */ }
    }
    var bytes = new Uint8Array(16);
    if (cryptoApi && typeof cryptoApi.getRandomValues === "function") {
      cryptoApi.getRandomValues(bytes);
    } else {
      for (var i = 0; i < 16; i += 1) { bytes[i] = Math.floor(Math.random() * 256); }
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    var hex = Array.prototype.map.call(bytes, function (b) { return (b < 16 ? "0" : "") + b.toString(16); }).join("");
    return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16) + "-" + hex.slice(16, 20) + "-" + hex.slice(20);
  }

  /* Accepts "12,5" as well as "12.5"; returns the number as a string (the registry stores decimals). */
  function parseDecimal(raw) {
    var text = String(raw || "").replace(/[\s\u00a0\u202f]/g, "").replace(",", ".");
    if (!text) { return {ok: true, value: null}; }
    if (!/^-?(\d+(\.\d*)?|\.\d+)$/.test(text)) { return {ok: false, value: null}; }
    return {ok: true, value: text};
  }

  // =========================================================================== storage (IndexedDB, fallbacks)
  function idbApi(db) {
    function run(storeName, mode, work) {
      return new Promise(function (resolve, reject) {
        var tx;
        try { tx = db.transaction(storeName, mode); } catch (err) { reject(err); return; }
        var result;
        var request = work(tx.objectStore(storeName));
        if (request) { request.onsuccess = function () { result = request.result; }; }
        tx.oncomplete = function () { resolve(result); };
        tx.onerror = function () { reject(tx.error); };
        tx.onabort = function () { reject(tx.error || new Error("IndexedDB transaction aborted")); };
      });
    }
    return {
      kind: "indexeddb",
      getBundle: function (reference) {
        return run("bundles", "readonly", function (s) { return s.get(reference); }).then(function (r) { return r || null; });
      },
      putBundle: function (record) { return run("bundles", "readwrite", function (s) { s.put(record); }); },
      listQueue: function () {
        return run("queue", "readonly", function (s) { return s.getAll(); }).then(function (r) { return r || []; });
      },
      putEntries: function (records) {
        return run("queue", "readwrite", function (s) { records.forEach(function (r) { s.put(r); }); });
      },
      deleteEntries: function (ids) {
        return run("queue", "readwrite", function (s) { ids.forEach(function (id) { s.delete(id); }); });
      }
    };
  }

  function idbStore() {
    return new Promise(function (resolve, reject) {
      if (typeof window.indexedDB === "undefined" || !window.indexedDB) { reject(new Error("IndexedDB unavailable")); return; }
      var settled = false;
      var timer = setTimeout(function () {
        if (!settled) { settled = true; reject(new Error("IndexedDB did not open")); }
      }, 5000);
      var request;
      try { request = window.indexedDB.open(DB_NAME, 1); } catch (err) { clearTimeout(timer); reject(err); return; }
      request.onupgradeneeded = function () {
        var db = request.result;
        if (!db.objectStoreNames.contains("bundles")) { db.createObjectStore("bundles", {keyPath: "reference"}); }
        if (!db.objectStoreNames.contains("queue")) {
          db.createObjectStore("queue", {keyPath: "client_uuid"}).createIndex("reference", "reference", {unique: false});
        }
      };
      request.onsuccess = function () {
        var db = request.result;
        if (settled) { db.close(); return; }
        settled = true;
        clearTimeout(timer);
        db.onversionchange = function () { db.close(); };
        resolve(idbApi(db));
      };
      request.onerror = function () {
        if (!settled) { settled = true; clearTimeout(timer); reject(request.error || new Error("IndexedDB error")); }
      };
    });
  }

  function attempt(work) {
    return new Promise(function (resolve, reject) {
      try { resolve(work()); } catch (err) { reject(err); }
    });
  }

  function localStore() {
    var ls = window.localStorage;
    ls.setItem(LS_PREFIX + "probe", "1");
    ls.removeItem(LS_PREFIX + "probe");
    function readQueue() {
      try { return JSON.parse(ls.getItem(LS_PREFIX + "queue") || "{}") || {}; } catch (err) { return {}; }
    }
    function writeQueue(queue) { ls.setItem(LS_PREFIX + "queue", JSON.stringify(queue)); }
    return {
      kind: "localstorage",
      getBundle: function (reference) {
        return attempt(function () { return JSON.parse(ls.getItem(LS_PREFIX + "bundles:" + reference) || "null"); });
      },
      putBundle: function (record) {
        return attempt(function () { ls.setItem(LS_PREFIX + "bundles:" + record.reference, JSON.stringify(record)); });
      },
      listQueue: function () {
        return attempt(function () { var q = readQueue(); return Object.keys(q).map(function (k) { return q[k]; }); });
      },
      putEntries: function (records) {
        return attempt(function () {
          var q = readQueue();
          records.forEach(function (r) { q[r.client_uuid] = r; });
          writeQueue(q);
        });
      },
      deleteEntries: function (ids) {
        return attempt(function () {
          var q = readQueue();
          ids.forEach(function (id) { delete q[id]; });
          writeQueue(q);
        });
      }
    };
  }

  /* Last resort: nothing survives a reload — the page warns before leaving with unsent entries. */
  function memoryStore() {
    var bundles = {};
    var queue = {};
    function copy(value) { return value === null || value === undefined ? null : JSON.parse(JSON.stringify(value)); }
    return {
      kind: "memory",
      getBundle: function (reference) { return Promise.resolve(copy(bundles[reference])); },
      putBundle: function (record) { bundles[record.reference] = copy(record); return Promise.resolve(); },
      listQueue: function () { return Promise.resolve(Object.keys(queue).map(function (k) { return copy(queue[k]); })); },
      putEntries: function (records) { records.forEach(function (r) { queue[r.client_uuid] = copy(r); }); return Promise.resolve(); },
      deleteEntries: function (ids) { ids.forEach(function (id) { delete queue[id]; }); return Promise.resolve(); }
    };
  }

  /* Entries saved in localStorage while IndexedDB was unavailable are moved back into IndexedDB. */
  function migrateLocalQueue(store) {
    var records = [];
    try {
      var raw = window.localStorage && window.localStorage.getItem(LS_PREFIX + "queue");
      if (!raw) { return Promise.resolve(); }
      var queue = JSON.parse(raw) || {};
      records = Object.keys(queue).map(function (k) { return queue[k]; });
    } catch (err) {
      return Promise.resolve();
    }
    if (!records.length) { return Promise.resolve(); }
    return store.putEntries(records).then(function () {
      try { window.localStorage.removeItem(LS_PREFIX + "queue"); } catch (err) { /* left in place */ }
    }, function () { /* keep them where they are */ });
  }

  function openStore() {
    return idbStore().then(function (store) {
      return migrateLocalQueue(store).then(function () { return store; });
    }, function () {
      try { return localStore(); } catch (err) { return memoryStore(); }
    });
  }

  // =========================================================================== state
  function emptyMeta() {
    return {reference: REF, bundle: null, fetched_at: null, last_sync_at: null, last_results: [], results_cleared_at: null};
  }

  var state = {
    store: null,
    meta: emptyMeta(),
    queue: [],
    syncing: false,
    syncAgain: false,
    syncPromise: null,
    sending: {},
    reachable: null,
    fresh: false,
    problem: "",
    storageFull: false,
    swProblem: false,
    owner: String(CONFIG.owner || ""),
    verifiedOwner: "",
    form: null,
    photo: null,
    photoToken: 0,
    photoBusy: false,
    csOpen: null,
    csDirty: false,
    seq: 0,
    persistAsked: false,
    lastResult: "",
    lastTone: ""
  };
  var signatures = {};

  function bundle() { return state.meta && state.meta.bundle; }
  function owner() { return state.verifiedOwner || state.owner; }
  function roles() {
    var b = bundle();
    return (b && (b.roles || (b.call && b.call.your_roles))) || [];
  }
  function belongsTo(record, who) { return !record.owner || record.owner === who; }
  function callRecords() { return state.queue.filter(function (r) { return r.reference === REF; }); }
  function ownRecords() { var me = owner(); return callRecords().filter(function (r) { return belongsTo(r, me); }); }
  function pendingRecords() { return ownRecords().filter(function (r) { return r.state !== "refused"; }); }
  function refusedRecords() { return ownRecords().filter(function (r) { return r.state === "refused"; }); }
  function findType(code) {
    var b = bundle();
    return ((b && b.milestone_types) || []).filter(function (type) { return type.code === code; })[0] || null;
  }
  function closingTypes() {
    var b = bundle();
    return ((b && b.milestone_types) || []).filter(function (type) { return type.closes; });
  }
  function causeFor(code) {
    var b = bundle();
    return ((b && b.causes) || []).filter(function (c) { return c.code === code; })[0] || null;
  }
  function callClosed() {
    var b = bundle();
    return !!(b && b.call && TERMINAL_STATUSES.indexOf(b.call.status) >= 0);
  }
  function byDeviceTime(a, b) {
    var x = (a.entry && a.entry.device_recorded_at) || "";
    var y = (b.entry && b.entry.device_recorded_at) || "";
    if (x < y) { return -1; }
    if (x > y) { return 1; }
    return (a.seq || 0) - (b.seq || 0);
  }
  /* Entries synchronised after the bundle was fetched: the bundle does not show them yet. */
  function sentSinceFetch() {
    var fetchedAt = state.meta.fetched_at || "";
    return (state.meta.last_results || []).filter(function (res) { return res.synced_at > fetchedAt; });
  }

  /* Open interruptions known here: the bundle's list, interruptions sent since it was fetched, and
     interruptions recorded on this device that are not sent yet (optimistic), minus those whose end
     is already waiting in the queue. Local ones are referenced by client_uuid. */
  function openInterruptions() {
    var b = bundle();
    if (!b) { return []; }
    var closable = {};
    var closers = {};
    closingTypes().forEach(function (type) { closable[type.closes] = true; closers[type.code] = true; });
    var closedIds = {};
    var closedUuids = {};
    pendingRecords().forEach(function (r) {
      var e = r.entry;
      if (e.kind === "milestone" && closers[e.type]) {
        if (e.related_id) { closedIds[e.related_id] = true; }
        if (e.related_client_uuid) { closedUuids[e.related_client_uuid] = true; }
      }
    });
    sentSinceFetch().forEach(function (res) {
      if (res.kind === "milestone" && closers[res.type]) {
        if (res.related_id) { closedIds[res.related_id] = true; }
        if (res.related_client_uuid) { closedUuids[res.related_client_uuid] = true; }
      }
    });
    var items = [];
    var known = {};
    function closed(id, uuid) { return (id && closedIds[id]) || (uuid && closedUuids[uuid]); }
    (b.open_interruptions || []).forEach(function (m) {
      if (m.client_uuid) { known[m.client_uuid] = true; }
      known["id:" + m.id] = true;
      if (closed(m.id, m.client_uuid)) { return; }
      items.push({
        key: "id:" + m.id, id: m.id, client_uuid: m.client_uuid || "", type: m.type, label: m.label,
        declared_at: m.declared_at, cause: m.cause ? m.cause.label : "", reason: m.cause_reason || "",
        emitter: m.emitter || m.emitter_role || "", local: false
      });
    });
    sentSinceFetch().forEach(function (res) {
      if (res.kind !== "milestone" || !closable[res.type] || res.status !== "ok" || !res.id) { return; }
      if (known["id:" + res.id] || known[res.client_uuid] || closed(res.id, res.client_uuid)) { return; }
      known[res.client_uuid] = true;
      var cause = causeFor(res.cause);
      items.push({
        key: "id:" + res.id, id: res.id, client_uuid: res.client_uuid, type: res.type, label: res.label,
        declared_at: res.declared_at, cause: cause ? cause.label : res.cause, reason: res.cause_reason || "",
        emitter: "", local: false
      });
    });
    pendingRecords().forEach(function (r) {
      var e = r.entry;
      if (e.kind !== "milestone" || !closable[e.type] || known[e.client_uuid] || closed(null, e.client_uuid)) { return; }
      var cause = causeFor(e.cause);
      items.push({
        key: "uuid:" + e.client_uuid, id: null, client_uuid: e.client_uuid, type: e.type, label: r.label,
        declared_at: e.declared_at, cause: cause ? cause.label : (e.cause || ""), reason: e.cause_reason || "",
        emitter: "", local: true
      });
    });
    items.sort(function (x, y) { return timeValue(x.declared_at) - timeValue(y.declared_at); });
    return items;
  }

  /* Was a milestone of this type already recorded (registry, sent since, or waiting here)? */
  function existingRecord(code) {
    var b = bundle();
    var found = null;
    ((b && b.recent_milestones) || []).forEach(function (m) {
      if (!found && m.type === code && !m.conflict && !m.rectification) { found = {at: m.declared_at, local: false}; }
    });
    sentSinceFetch().forEach(function (res) {
      if (!found && res.kind === "milestone" && res.type === code && res.status === "ok") { found = {at: res.declared_at, local: false}; }
    });
    pendingRecords().forEach(function (r) {
      if (!found && r.entry.kind === "milestone" && r.entry.type === code) { found = {at: r.entry.declared_at, local: true}; }
    });
    return found;
  }

  function interruptionTitle(item) {
    if (!item.cause) { return item.label; }
    return item.reason ? t("cause_reason", {cause: item.cause, reason: item.reason}) : item.cause;
  }

  // =========================================================================== DOM references
  var el = {
    callStatus: byId("f-callstatus"),
    roles: byId("f-roles"),
    net: byId("f-net"),
    data: byId("f-data"),
    queueCount: byId("f-queue-count"),
    refusedCount: byId("f-refused-count"),
    lastSync: byId("f-last-sync"),
    syncButton: byId("f-sync"),
    result: byId("f-result"),
    notices: byId("f-notices"),
    navCountersign: byId("f-nav-cs"),
    navPumping: byId("f-nav-pumping"),
    navTasks: byId("f-nav-tasks"),
    navQueue: byId("f-nav-queue"),
    milestonesTitle: byId("f-milestones-title"),
    openBlock: byId("f-open-block"),
    openList: byId("f-open-list"),
    types: byId("f-types"),
    typesEmpty: byId("f-types-empty"),
    msDone: byId("f-ms-done"),
    msForm: byId("f-ms-form"),
    msTitle: byId("f-ms-title"),
    msNotes: byId("f-ms-notes"),
    msTime: byId("f-ms-time"),
    msTimeHint: byId("f-ms-time-hint"),
    msCauseRow: byId("f-ms-cause-row"),
    msCause: byId("f-ms-cause"),
    msReasonRow: byId("f-ms-reason-row"),
    msReason: byId("f-ms-reason"),
    msRelatedRow: byId("f-ms-related-row"),
    msRelated: byId("f-ms-related"),
    msRelatedEmpty: byId("f-ms-related-empty"),
    msNote: byId("f-ms-note"),
    msPhoto: byId("f-ms-photo"),
    msPhotoStatus: byId("f-ms-photo-status"),
    msPhotoPreview: byId("f-ms-photo-preview"),
    msPhotoImg: byId("f-ms-photo-img"),
    msPhotoRemove: byId("f-ms-photo-remove"),
    msError: byId("f-ms-error"),
    msSubmit: byId("f-ms-submit"),
    msCancel: byId("f-ms-cancel"),
    csTitle: byId("f-countersign-title"),
    csList: byId("f-cs-list"),
    csEmpty: byId("f-cs-empty"),
    csDone: byId("f-cs-done"),
    pumpSection: byId("f-pumping"),
    pumpForm: byId("f-pump-form"),
    pumpTime: byId("f-pump-time"),
    pumpTimeHint: byId("f-pump-time-hint"),
    pumpPressure: byId("f-pump-pressure"),
    pumpRate: byId("f-pump-rate"),
    pumpTemp: byId("f-pump-temp"),
    pumpLevel: byId("f-pump-level"),
    pumpMoved: byId("f-pump-moved"),
    pumpCumul: byId("f-pump-cumul"),
    pumpError: byId("f-pump-error"),
    pumpDone: byId("f-pump-done"),
    pumpSubmit: byId("f-pump-submit"),
    taskList: byId("f-task-list"),
    tasksEmpty: byId("f-tasks-empty"),
    queueTitle: byId("f-queue-title"),
    queueList: byId("f-queue-list"),
    queueEmpty: byId("f-queue-empty"),
    others: byId("f-others"),
    resultsTitle: byId("f-results-title"),
    resultsList: byId("f-results-list"),
    resultsEmpty: byId("f-results-empty"),
    resultsClear: byId("f-results-clear")
  };
  var missing = Object.keys(el).filter(function (key) { return !el[key]; });
  if (missing.length) { logError("field.html is missing: " + missing.join(", ")); return; }

  // =========================================================================== rendering helpers
  /* Re-render a block only when what it shows has changed, so that the 60-second refresh never
     steals the focus or the reading position. */
  function changed(name, model) {
    var signature = JSON.stringify(model === undefined ? null : model);
    if (signatures[name] === signature) { return false; }
    signatures[name] = signature;
    return true;
  }

  /* Rebuild *container* and give the focus back to the same item/action when it was inside. */
  function keepFocus(container, build, fallback) {
    var active = document.activeElement;
    var memo = null;
    if (active && active !== document.body && container.contains(active)) {
      var item = active.closest("[data-key]");
      memo = {key: item ? item.getAttribute("data-key") : "", action: active.getAttribute("data-action") || ""};
    }
    build();
    if (!memo) { return; }
    var target = null;
    if (memo.key) {
      var again = container.querySelector('[data-key="' + cssEscape(memo.key) + '"]');
      if (again) {
        if (memo.action && again.getAttribute("data-action") === memo.action) { target = again; }
        if (!target && memo.action) { target = again.querySelector('[data-action="' + cssEscape(memo.action) + '"]'); }
        if (!target) { target = again.matches("button, a, input") ? again : again.querySelector("button, a, input"); }
      }
    }
    target = target && !target.disabled ? target : fallback;
    if (target) { target.focus(); }
  }

  function setText(node, text) { if (node.textContent !== text) { node.textContent = text; } }

  /* The live region of the status bar. News and warnings fade after a while (the chips, the queue and
     the results list keep the lasting state); errors stay until the next result. */
  var resultTimer = null;
  function setResult(text, tone) {
    el.result.className = "fieldbar-result" + (tone ? " " + tone : "");
    el.result.textContent = text;
    if (resultTimer) { clearTimeout(resultTimer); resultTimer = null; }
    if (tone !== "error") {
      resultTimer = setTimeout(function () {
        if (el.result.textContent === text) { el.result.textContent = ""; }
      }, 20000);
    }
  }

  function showError(errorNode, message, field) {
    errorNode.textContent = message;
    errorNode.hidden = false;
    if (field) {
      field.setAttribute("aria-invalid", "true");
      var ids = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
      if (ids.indexOf(errorNode.id) < 0) { ids.push(errorNode.id); }
      field.setAttribute("aria-describedby", ids.join(" "));
      try { field.focus(); } catch (err) { /* not focusable */ }
    }
    return false;
  }

  function clearErrors(container, errorNode) {
    errorNode.hidden = true;
    errorNode.textContent = "";
    Array.prototype.forEach.call(container.querySelectorAll("[aria-invalid]"), function (field) {
      field.removeAttribute("aria-invalid");
      var ids = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter(function (id) { return id && id !== errorNode.id; });
      if (ids.length) { field.setAttribute("aria-describedby", ids.join(" ")); } else { field.removeAttribute("aria-describedby"); }
    });
  }

  function setNow(input) {
    input.value = inputValue(new Date());
    input.setAttribute("data-auto", "1");
  }

  /* Focused fields and anchor targets must never sit under the sticky status bar (WCAG 2.4.11). */
  function watchStatusBar() {
    var bar = byId("f-status");
    if (!bar) { return; }
    function apply() { document.documentElement.style.scrollPaddingTop = (bar.offsetHeight + 16) + "px"; }
    apply();
    if (typeof window.ResizeObserver === "function") { new window.ResizeObserver(apply).observe(bar); }
    else { window.addEventListener("resize", apply); }
  }

  /* A time field the user has not touched follows the clock ("now"). */
  function refreshAutoTimes() {
    [el.msTime, el.pumpTime].forEach(function (input) {
      if (input.getAttribute("data-auto") === "1" && document.activeElement !== input) { input.value = inputValue(new Date()); }
    });
  }

  function deviceTimeHint() {
    return t("device_time_hint", {offset: offsetLabel(-new Date().getTimezoneOffset())});
  }

  // =========================================================================== rendering: header, status, notices
  function renderHeader() {
    var b = bundle();
    var status = b && b.call ? [b.call.status, b.call.status_label || b.call.status] : null;
    if (changed("header", status)) {
      el.callStatus.textContent = "";
      if (status) { el.callStatus.appendChild(h("span", {class: "chip status st-" + status[0]}, status[1])); }
    }
    var list = roles();
    el.roles.hidden = !list.length;
    setText(el.roles, list.length ? t("your_roles", {roles: list.join(", ")}) : "");
  }

  function renderStatus() {
    var net;
    if (state.syncing) { net = ["reminder", t("net_syncing")]; }
    else if (navigator.onLine === false) { net = ["hold", t("net_offline")]; }
    else if (state.reachable === false) { net = ["late", t("net_unreachable")]; }
    else if (state.reachable === null) { net = ["pending", t("net_starting")]; }
    else { net = ["done", t("net_online")]; }
    el.net.className = "chip " + net[0];
    setText(el.net, net[1]);

    var b = bundle();
    el.data.hidden = !b || state.fresh;
    setText(el.data, b ? t("data_saved_chip", {time: fmt(state.meta.fetched_at)}) : "");

    var pending = pendingRecords().length;
    var refused = refusedRecords().length;
    el.queueCount.className = "chip " + (pending ? "pending" : "done");
    setText(el.queueCount, pending ? t("queue_count", {n: pending}) : t("queue_none"));
    el.refusedCount.hidden = !refused;
    setText(el.refusedCount, t("refused_count", {n: refused}));
    setText(el.lastSync, state.meta.last_sync_at ? t("last_sync", {time: fmt(state.meta.last_sync_at)}) : t("never_synced"));
    el.syncButton.disabled = state.syncing || !state.store;
    el.syncButton.setAttribute("aria-busy", state.syncing ? "true" : "false");
    setText(el.navQueue, pending + refused ? String(pending + refused) : "");
  }

  function tzNote() {
    var b = bundle();
    var zone = b && b.call && b.call.port && b.call.port.timezone;
    if (!zone) { return ""; }
    var now = new Date();
    var port = portOffsetMinutes(zone, now);
    var device = -now.getTimezoneOffset();
    if (port === null || port === device) { return ""; }
    return t("tz_note", {device: offsetLabel(device), port: zone + " (" + offsetLabel(port) + ")"});
  }

  function renderNotices() {
    var b = bundle();
    var model = [];
    if (!b) { model.push(["warning", navigator.onLine === false ? t("no_data_offline") : t("no_data"), ""]); }
    else if (!state.fresh) { model.push(["warning", t("cached_data", {time: fmt(state.meta.fetched_at)}), ""]); }
    if (state.store && state.store.kind === "memory") { model.push(["error", t("storage_memory"), ""]); }
    if (state.storageFull) { model.push(["warning", t("storage_full"), ""]); }
    if (state.swProblem) { model.push(["warning", t("sw_unavailable"), ""]); }
    if (state.problem === "auth") { model.push(["error", t("problem_auth"), "signin"]); }
    if (state.problem === "notfound") { model.push(["error", t("problem_notfound"), ""]); }
    if (state.problem === "otheruser") { model.push(["error", t("problem_other_user"), "reload"]); }
    if (callClosed()) { model.push(["warning", t("call_closed"), ""]); }
    var zone = tzNote();
    if (zone) { model.push(["", zone, ""]); }
    var foreign = callRecords().length - ownRecords().length;
    if (foreign) { model.push(["", t("other_person_entries", {n: foreign}), ""]); }
    if (!changed("notices", model)) { return; }
    keepFocus(el.notices, function () {
      el.notices.textContent = "";
      model.forEach(function (n) {
        var action = null;
        if (n[2] === "signin" && CONFIG.signInUrl) {
          action = h("a", {class: "btn big secondary", href: CONFIG.signInUrl, "data-key": "signin"}, t("sign_in"));
        } else if (n[2] === "reload") {
          action = h("button", {type: "button", class: "btn big secondary", "data-key": "reload", "data-action": "reload"}, t("reload"));
        }
        el.notices.appendChild(h("div", {class: "flash" + (n[0] ? " " + n[0] : "")}, [h("p", null, n[1]), action]));
      });
    }, el.milestonesTitle);
  }

  // =========================================================================== rendering: milestones
  function typesModel() {
    var b = bundle();
    if (!b) { return null; }
    var open = openInterruptions();
    return (b.milestone_types || []).map(function (type) {
      var lines = [];
      var disabled = false;
      if (type.closes && !open.some(function (item) { return item.type === type.closes; })) {
        disabled = true;
        lines.push(t("no_open_interruption"));
      }
      if (type.hold_point) { lines.push(t("hold_point")); }
      if (!type.repeatable && !type.closes && existingRecord(type.code)) { lines.push(t("already_chip")); }
      return {code: type.code, label: type.label, lines: lines, disabled: disabled};
    });
  }

  function renderMilestones() {
    var formOpen = !!state.form;
    var model = typesModel();
    var open = bundle() ? openInterruptions() : [];
    el.types.hidden = formOpen || !model || !model.length;
    el.typesEmpty.hidden = formOpen || !!(model && model.length);
    setText(el.typesEmpty, model ? t("ms_none") : t("section_needs_data"));
    el.openBlock.hidden = formOpen || !open.length;
    if (changed("types", model)) {
      keepFocus(el.types, function () {
        el.types.textContent = "";
        (model || []).forEach(function (m) {
          el.types.appendChild(h("button", {
            type: "button", class: "btn big secondary", disabled: m.disabled, "data-key": m.code, "data-action": "record",
            "data-code": m.code
          }, [h("span", {class: "tlabel"}, m.label), m.lines.length ? h("small", null, m.lines.join(" · ")) : null]));
        });
      }, el.milestonesTitle);
    }
    var closerFor = {};
    closingTypes().forEach(function (type) { closerFor[type.closes] = type.code; });
    var openModel = open.map(function (item) {
      return {
        key: item.key, title: interruptionTitle(item), started: item.declared_at, emitter: item.emitter, local: item.local,
        closer: closerFor[item.type] || ""
      };
    });
    if (changed("open", openModel)) {
      keepFocus(el.openList, function () {
        el.openList.textContent = "";
        openModel.forEach(function (item) {
          el.openList.appendChild(h("li", {"data-key": item.key}, [
            h("strong", null, item.title),
            h("div", {class: "meta"}, [
              h("span", null, t("started_at", {time: fmt(item.started)})),
              item.emitter ? h("span", null, item.emitter) : null,
              item.local ? chip("pending", t("local_not_sent")) : chip("hold", t("open_chip"))
            ]),
            item.closer ? h("div", {class: "acts"}, [h("button", {
              type: "button", class: "btn big", "data-action": "end", "data-code": item.closer, "data-related": item.key
            }, t("record_end"))]) : null
          ]));
        });
      }, el.milestonesTitle);
    }
    if (formOpen) { refreshOpenForm(); }
  }

  function fillCauses() {
    var b = bundle();
    var keep = el.msCause.value;
    var causes = (b && b.causes) || [];
    if (!changed("causes", causes) && el.msCause.options.length === causes.length + 1) { return; }
    while (el.msCause.options.length > 1) { el.msCause.remove(1); }
    causes.forEach(function (cause) { el.msCause.add(new Option(cause.label, cause.code)); });
    el.msCause.value = keep;
    if (el.msCause.value !== keep) { el.msCause.value = ""; }
  }

  function syncReasonRow() {
    var cause = state.form && state.form.type.requires_cause ? causeFor(el.msCause.value) : null;
    var needed = !!(cause && cause.requires_reason);
    el.msReasonRow.hidden = !needed;
    el.msReason.required = needed;
  }

  function selectedRelatedKey() {
    var checked = el.msRelated.querySelector("input[name=related]:checked");
    return checked ? checked.value : "";
  }

  function drawRelated() {
    var type = state.form.type;
    var model = openInterruptions().filter(function (item) { return item.type === type.closes; }).map(function (item) {
      return {key: item.key, title: interruptionTitle(item), started: item.declared_at, emitter: item.emitter, local: item.local};
    });
    var selected = selectedRelatedKey() || state.form.relatedKey || "";
    if (!model.some(function (m) { return m.key === selected; })) { selected = model.length === 1 ? model[0].key : ""; }
    state.form.relatedKey = selected;
    el.msRelatedEmpty.hidden = model.length > 0;
    el.msSubmit.disabled = model.length === 0;
    if (!changed("related", [model, selected])) { return; }
    keepFocus(el.msRelated, function () {
      el.msRelated.textContent = "";
      model.forEach(function (m, index) {
        var id = "f-rel-" + index;
        var input = h("input", {type: "radio", name: "related", id: id, value: m.key, "data-action": "pick"});
        input.checked = m.key === selected;
        el.msRelated.appendChild(h("label", {class: "choice", for: id, "data-key": m.key}, [input, h("span", null, [
          h("strong", null, m.title),
          h("span", {class: "small muted"}, t("started_at", {time: fmt(m.started)}) + (m.emitter ? " · " + m.emitter : "")),
          m.local ? [" ", chip("pending", t("local_not_sent"))] : null
        ])]));
      });
    }, el.msTitle);
  }

  function drawFormNotes() {
    var type = state.form.type;
    var notes = [];
    if (type.hold_point) { notes.push(t("hold_point_hint")); }
    if (!type.repeatable && !type.closes) {
      var existing = existingRecord(type.code);
      if (existing) { notes.push(t(existing.local ? "already_local" : "already_server", {time: fmt(existing.at)})); }
    }
    if (callClosed()) { notes.push(t("call_closed")); }
    if (!changed("formnotes", notes)) { return; }
    el.msNotes.textContent = "";
    notes.forEach(function (note) { el.msNotes.appendChild(h("p", {class: "flash warning"}, note)); });
    el.msNotes.hidden = !notes.length;
  }

  function refreshOpenForm() {
    if (!state.form) { return; }
    state.form.type = findType(state.form.type.code) || state.form.type;
    if (state.form.type.requires_cause) { fillCauses(); syncReasonRow(); }
    if (state.form.type.closes) { drawRelated(); }
    drawFormNotes();
  }

  // =========================================================================== rendering: countersign, pumping, tasks
  function countersignState(m) {
    var queued = pendingRecords().filter(function (r) {
      return r.entry.kind === "countersign" && String(r.entry.milestone_id) === String(m.id);
    })[0];
    if (queued) { return {state: "queued", contest: !!queued.entry.contest}; }
    var sent = sentSinceFetch().filter(function (res) {
      return res.kind === "countersign" && String(res.milestone_id) === String(m.id);
    })[0];
    if (sent) { return {state: "sent", contest: !!sent.contest}; }
    return null;
  }

  function renderCountersign() {
    var b = bundle();
    var items = (b && b.to_countersign) || [];
    var model = b ? items.map(function (m) {
      var st = countersignState(m);
      var who = m.emitter ? m.emitter + (m.emitter_role ? " (" + m.emitter_role + ")" : "") : (m.emitter_role || "");
      return {
        id: m.id, label: m.label, declared: m.declared_at, who: who, deferred: !!m.deferred,
        cause: m.cause ? (m.cause_reason ? t("cause_reason", {cause: m.cause.label, reason: m.cause_reason}) : m.cause.label) : "",
        state: st ? st.state : "", contest: st ? st.contest : false
      };
    }) : null;
    var waiting = (model || []).filter(function (m) { return !m.state; }).length;
    setText(el.navCountersign, waiting ? String(waiting) : "");
    el.csEmpty.hidden = !!(model && model.length);
    setText(el.csEmpty, model ? t("cs_none") : t("section_needs_data"));
    if (state.csOpen) { state.csDirty = true; return; }       // never rebuild under an open panel
    state.csDirty = false;
    if (!changed("countersign", model)) { return; }
    keepFocus(el.csList, function () {
      el.csList.textContent = "";
      (model || []).forEach(function (m) {
        var actions;
        if (m.state === "queued") {
          actions = h("div", {class: "meta"}, chip("pending", t(m.contest ? "contest_queued" : "cs_queued")));
        } else if (m.state === "sent") {
          actions = h("div", {class: "meta"}, chip("done", t(m.contest ? "contest_sent" : "cs_sent")));
        } else {
          actions = h("div", {class: "acts"}, [
            h("button", {type: "button", class: "btn big", "data-action": "countersign"}, t("countersign")),
            h("button", {type: "button", class: "btn big danger", "data-action": "contest"}, t("contest"))
          ]);
        }
        el.csList.appendChild(h("li", {"data-key": String(m.id)}, [
          h("strong", null, m.label),
          h("div", {class: "meta"}, [
            h("span", null, t("declared_at", {time: fmt(m.declared)})),
            m.who ? h("span", null, t("recorded_by", {who: m.who})) : null,
            m.cause ? h("span", null, m.cause) : null,
            m.deferred ? chip("deferred", t("deferred_chip")) : null
          ]),
          actions
        ]));
      });
    }, el.csTitle);
  }

  function renderPumping() {
    var list = roles();
    var allowed = list.indexOf("TER") >= 0 || list.indexOf("NAV") >= 0;
    el.pumpSection.hidden = !allowed;
    el.navPumping.hidden = !allowed;
    setText(el.pumpTimeHint, deviceTimeHint());
  }

  function renderTasks() {
    var b = bundle();
    var now = Date.now();
    var tasks = ((b && b.tasks) || []).slice().sort(function (x, y) {
      var a = x.due_at ? timeValue(x.due_at) : Number.MAX_VALUE;
      var c = y.due_at ? timeValue(y.due_at) : Number.MAX_VALUE;
      return a === c ? String(x.code).localeCompare(String(y.code)) : (a < c ? -1 : 1);
    });
    var model = b ? tasks.map(function (task) {
      var level = task.alert_level;
      if (task.due_at && timeValue(task.due_at) < now && level !== "ESCALATED") { level = "LATE"; }
      return {
        id: task.id, title: task.title, code: task.code, due: task.due_at || "", timing: task.timing || "", level: level,
        blocking: !!task.blocking
      };
    }) : null;
    setText(el.navTasks, model && model.length ? String(model.length) : "");
    el.tasksEmpty.hidden = !!(model && model.length);
    setText(el.tasksEmpty, model ? t("tasks_none") : t("section_needs_data"));
    if (!changed("tasks", model)) { return; }
    el.taskList.textContent = "";
    (model || []).forEach(function (task) {
      var due = task.due ? t("due_at", {time: fmt(task.due)}) : (task.timing ? t("due_timing", {timing: task.timing}) : t("no_due"));
      el.taskList.appendChild(h("li", {"data-key": String(task.id)}, [
        h("strong", null, task.title),
        h("div", {class: "meta"}, [
          h("span", {class: "code"}, task.code),
          h("span", null, due),
          task.level === "REMINDER" ? chip("reminder", t("alert_reminder")) : null,
          task.level === "LATE" ? chip("late", t("alert_late")) : null,
          task.level === "ESCALATED" ? chip("escalated", t("alert_escalated")) : null,
          task.blocking ? chip("blocking", t("blocking")) : null
        ])
      ]));
    });
  }

  // =========================================================================== rendering: queue and results
  function kindLabel(kind, contest) { return t(kind === "countersign" && contest ? "kind_contest" : "kind_" + kind); }

  function renderQueue() {
    var me = owner();
    var records = callRecords().slice().sort(byDeviceTime);
    var model = records.map(function (rec) {
      var st = !belongsTo(rec, me) ? "foreign" : (state.sending[rec.client_uuid] ? "sending" : (rec.state === "refused" ? "refused" : "pending"));
      return {
        uuid: rec.client_uuid, kind: rec.entry.kind, contest: !!rec.entry.contest, label: rec.label || "", detail: rec.detail || "",
        declared: rec.entry.declared_at, device: rec.entry.device_recorded_at, state: st, message: rec.message || ""
      };
    });
    el.queueEmpty.hidden = model.length > 0;
    setText(el.queueEmpty, t("queue_empty"));
    if (changed("queue", model)) {
      keepFocus(el.queueList, function () {
        el.queueList.textContent = "";
        model.forEach(function (item) {
          var status = {
            foreign: ["na", t("st_foreign")], sending: ["reminder", t("st_sending")], refused: ["contested", t("st_refused")],
            pending: ["pending", t("st_pending")]
          }[item.state];
          el.queueList.appendChild(h("li", {"data-key": item.uuid}, [
            h("div", {class: "qhead"}, [
              h("span", {class: "qkind"}, kindLabel(item.kind, item.contest)),
              h("strong", {class: "qlabel"}, item.label || kindLabel(item.kind, item.contest)),
              chip(status[0], status[1])
            ]),
            item.detail ? h("p", {class: "msg"}, item.detail) : null,
            h("p", {class: "qtimes"}, [
              h("span", null, t("declared_at", {time: fmt(item.declared)})), " · ",
              h("span", null, t("device_short", {time: fmt(item.device, true)}))
            ]),
            item.state === "refused" ? h("p", {class: "msg qrefusal"}, t("refused_message", {message: item.message || "—"})) : null,
            item.state === "refused" ? h("div", {class: "acts"}, [
              h("button", {type: "button", class: "btn big secondary", "data-action": "retry"}, t("retry")),
              h("button", {type: "button", class: "btn big secondary", "data-action": "dismiss"}, t("dismiss"))
            ]) : null
          ]));
        });
      }, el.queueTitle);
    }
    renderOthers();
  }

  /* Entries of other calls never leave this device from here: link to their field page. */
  function renderOthers() {
    var me = owner();
    var groups = {};
    state.queue.forEach(function (r) {
      if (r.reference === REF || !belongsTo(r, me)) { return; }
      var group = groups[r.reference] || (groups[r.reference] = {n: 0, page: ""});
      group.n += 1;
      if (FIELD_PAGE.test(r.page || "")) { group.page = r.page; }
    });
    var model = Object.keys(groups).sort().map(function (ref) { return [ref, groups[ref].n, groups[ref].page]; });
    el.others.hidden = !model.length;
    if (!changed("others", model)) { return; }
    el.others.textContent = "";
    if (!model.length) { return; }
    el.others.appendChild(h("p", null, t("other_calls")));
    el.others.appendChild(h("ul", null, model.map(function (g) {
      return h("li", null, [g[2] ? h("a", {href: g[2]}, g[0]) : h("span", null, g[0]), " — " + t("other_calls_count", {n: g[1]})]);
    })));
  }

  function visibleResults() {
    var since = state.meta.results_cleared_at || "";
    return (state.meta.last_results || []).filter(function (res) { return !since || res.synced_at > since; });
  }

  function renderResults() {
    var list = visibleResults();
    el.resultsEmpty.hidden = list.length > 0;
    setText(el.resultsEmpty, t("results_empty"));
    el.resultsClear.hidden = !list.length;
    if (!changed("results", list)) { return; }
    el.resultsList.textContent = "";
    list.forEach(function (res) {
      el.resultsList.appendChild(h("li", {"data-key": res.client_uuid}, [
        h("div", {class: "qhead"}, [
          h("span", {class: "qkind"}, kindLabel(res.kind, res.contest)),
          h("strong", {class: "qlabel"}, res.label || kindLabel(res.kind, res.contest)),
          res.status === "conflict" ? chip("contested", t("res_conflict")) : chip("done", t("res_ok")),
          res.deferred ? chip("deferred", t("deferred_chip")) : null
        ]),
        res.detail ? h("p", {class: "msg"}, res.detail) : null,
        res.status === "conflict" ? h("p", {class: "msg"}, t("res_conflict_hint")) : null,
        h("p", {class: "qtimes"}, [
          h("span", null, t("declared_at", {time: fmt(res.declared_at)})), " · ",
          h("span", null, t("device_short", {time: fmt(res.device_recorded_at, true)})), " · ",
          h("span", null, t("synced_short", {time: fmt(res.synced_at, true)}))
        ])
      ]));
    });
  }

  function renderAll() {
    renderHeader();
    renderStatus();
    renderNotices();
    renderMilestones();
    renderCountersign();
    renderPumping();
    renderTasks();
    renderQueue();
    renderResults();
  }

  // =========================================================================== recording entries
  function makeRecord(entry, label, detail) {
    state.seq += 1;
    return {
      client_uuid: entry.client_uuid, reference: REF, owner: owner(), page: location.pathname, seq: Date.now() + state.seq / 1000,
      state: "pending", message: "", code: "", label: label, detail: detail || "", entry: entry
    };
  }

  function askPersistence() {
    if (state.persistAsked || !navigator.storage || typeof navigator.storage.persist !== "function") { return; }
    state.persistAsked = true;
    navigator.storage.persisted().then(function (persisted) {
      return persisted || navigator.storage.persist();
    }).catch(function () { /* best effort */ });
  }

  /* Saves records on the device (all or nothing), then sends them at once when the network allows. */
  function enqueue(records) {
    return state.store.putEntries(records).then(function () {
      records.forEach(function (rec) { state.queue.push(rec); });
      askPersistence();
      renderAll();
      if (navigator.onLine !== false) { requestSync({quiet: true}); }
    });
  }

  function savedMessage(label, savedAt) {
    return t(navigator.onLine === false ? "saved_offline" : "saved_local", {label: label, time: fmt(savedAt, true)});
  }

  // ------------------------------------------------------------------ milestone form
  function openMilestoneForm(code, relatedKey) {
    var type = findType(code);
    if (!type) { return; }
    state.form = {type: type, relatedKey: relatedKey || "", returnKey: relatedKey || code, returnFromOpen: !!relatedKey};
    el.msForm.reset();
    clearErrors(el.msForm, el.msError);
    clearPhoto();
    setText(el.msTitle, type.label);
    setNow(el.msTime);
    setText(el.msTimeHint, deviceTimeHint());
    el.msCauseRow.hidden = !type.requires_cause;
    el.msCause.required = !!type.requires_cause;
    if (type.requires_cause) { delete signatures.causes; fillCauses(); }
    syncReasonRow();
    el.msRelatedRow.hidden = !type.closes;
    delete signatures.related;
    delete signatures.formnotes;
    el.msRelated.textContent = "";
    if (type.closes) { drawRelated(); } else { el.msSubmit.disabled = false; }
    drawFormNotes();
    setText(el.msDone, "");
    el.msForm.hidden = false;
    renderMilestones();
    el.msTitle.focus();
  }

  function closeMilestoneForm(restoreFocus) {
    var form = state.form;
    if (!form) { return; }
    state.form = null;
    clearPhoto();
    el.msForm.hidden = true;
    renderMilestones();
    if (!restoreFocus) { return; }
    var target = null;
    if (form.returnFromOpen) {
      var item = el.openList.querySelector('[data-key="' + cssEscape(form.returnKey) + '"] button');
      target = item || null;
    } else {
      target = el.types.querySelector('[data-code="' + cssEscape(form.returnKey) + '"]');
    }
    (target && !target.disabled && !target.closest("[hidden]") ? target : el.milestonesTitle).focus();
  }

  function submitMilestone(event) {
    event.preventDefault();
    if (!state.form || !state.store) { return; }
    var type = state.form.type;
    clearErrors(el.msForm, el.msError);
    if (state.photoBusy) { showError(el.msError, t("photo_wait")); return; }
    var declared = inputToDate(el.msTime.value);
    if (!declared) { showError(el.msError, t("err_time"), el.msTime); return; }
    if (declared.getTime() > Date.now() + FUTURE_TOLERANCE_MS) { showError(el.msError, t("err_future"), el.msTime); return; }
    var entry = {
      kind: "milestone", client_uuid: uuid4(), device_recorded_at: "", declared_at: isoWithOffset(declared), type: type.code,
      note: el.msNote.value.trim()
    };
    var detail = [];
    if (type.requires_cause) {
      var cause = causeFor(el.msCause.value);
      if (!cause) { showError(el.msError, t("err_cause"), el.msCause); return; }
      entry.cause = cause.code;
      if (cause.requires_reason) {
        var reason = el.msReason.value.trim();
        if (!reason) { showError(el.msError, t("err_reason"), el.msReason); return; }
        entry.cause_reason = reason;
        detail.push(t("cause_reason", {cause: cause.label, reason: reason}));
      } else {
        detail.push(cause.label);
      }
    }
    if (type.closes) {
      var key = selectedRelatedKey();
      var item = openInterruptions().filter(function (i) { return i.key === key && i.type === type.closes; })[0];
      if (!item) { showError(el.msError, t("err_related"), el.msRelated.querySelector("input")); return; }
      if (declared.getTime() < timeValue(item.declared_at)) { showError(el.msError, t("err_before_start"), el.msTime); return; }
      if (item.id) { entry.related_id = item.id; } else { entry.related_client_uuid = item.client_uuid; }
      detail.push(t("ends_interruption", {what: interruptionTitle(item), time: fmt(item.declared_at)}));
    }
    if (entry.note) { detail.push(entry.note); }
    var savedAt = new Date();
    entry.device_recorded_at = savedAt.toISOString();
    var records = [makeRecord(entry, type.label, detail.join(" — "))];
    if (state.photo) {
      var photo = {
        kind: "photo", client_uuid: uuid4(), device_recorded_at: entry.device_recorded_at, declared_at: entry.declared_at,
        data_url: state.photo.dataUrl, title: truncate(t("photo_title", {label: type.label, time: fmt(declared)}), 240),
        document_type: "PHOTO"
      };
      records.push(makeRecord(photo, photo.title, t("photo_size", {w: state.photo.width, h: state.photo.height,
        kb: Math.round(state.photo.bytes / 1024)})));
    }
    el.msSubmit.disabled = true;
    enqueue(records).then(function () {
      el.msSubmit.disabled = false;
      closeMilestoneForm(true);
      setText(el.msDone, savedMessage(type.label, savedAt));
    }, function (err) {
      logError(err);
      el.msSubmit.disabled = false;
      showError(el.msError, records.length > 1 ? t("err_storage_photo") : t("err_storage"));
    });
  }

  // ------------------------------------------------------------------ photo (compressed on the device)
  function compressPhoto(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        try {
          var width = img.naturalWidth || img.width;
          var height = img.naturalHeight || img.height;
          var scale = Math.min(1, PHOTO_MAX_SIDE / Math.max(width, height, 1));
          var canvas = document.createElement("canvas");
          canvas.width = Math.max(1, Math.round(width * scale));
          canvas.height = Math.max(1, Math.round(height * scale));
          var ctx = canvas.getContext("2d");
          ctx.fillStyle = "#ffffff";
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          var dataUrl = canvas.toDataURL("image/jpeg", PHOTO_QUALITY);
          URL.revokeObjectURL(url);
          if (dataUrl.indexOf("data:image/jpeg") !== 0) { reject(new Error("JPEG encoding unavailable")); return; }
          var base64 = dataUrl.length - dataUrl.indexOf(",") - 1;
          resolve({dataUrl: dataUrl, width: canvas.width, height: canvas.height, bytes: Math.round(base64 * 3 / 4)});
        } catch (err) {
          URL.revokeObjectURL(url);
          reject(err);
        }
      };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("Unreadable image")); };
      img.src = url;
    });
  }

  function clearPhoto(keepInput) {
    state.photoToken += 1;
    state.photo = null;
    state.photoBusy = false;
    if (!keepInput) { el.msPhoto.value = ""; }
    el.msPhotoPreview.hidden = true;
    el.msPhotoImg.removeAttribute("src");
    setText(el.msPhotoStatus, "");
  }

  function onPhotoChange() {
    var file = el.msPhoto.files && el.msPhoto.files[0];
    clearPhoto(true);
    if (!file) { return; }
    var token = state.photoToken;
    state.photoBusy = true;
    setText(el.msPhotoStatus, t("photo_processing"));
    compressPhoto(file).then(function (photo) {
      if (token !== state.photoToken || !state.form) { return; }
      state.photoBusy = false;
      state.photo = photo;
      el.msPhotoImg.src = photo.dataUrl;
      el.msPhotoPreview.hidden = false;
      setText(el.msPhotoStatus, t("photo_ready", {w: photo.width, h: photo.height, kb: Math.round(photo.bytes / 1024)}));
    }, function (err) {
      if (token !== state.photoToken) { return; }
      logError(err);
      state.photoBusy = false;
      el.msPhoto.value = "";
      setText(el.msPhotoStatus, t("photo_error"));
    });
  }

  // ------------------------------------------------------------------ countersignature (with optional touch signature)
  function signaturePad() {
    var canvas = h("canvas", {class: "sigpad", role: "img", "aria-label": t("signature_area")});
    var ctx = null;
    var drawing = false;
    var dirty = false;
    function setup() {
      var ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round((canvas.clientWidth || 300) * ratio);
      canvas.height = Math.round((canvas.clientHeight || 160) * ratio);
      ctx = canvas.getContext("2d");
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.lineWidth = 2.4;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#202528";
      dirty = false;
    }
    function point(event) {
      var rect = canvas.getBoundingClientRect();
      return {x: event.clientX - rect.left, y: event.clientY - rect.top};
    }
    canvas.addEventListener("pointerdown", function (event) {
      if (!ctx) { setup(); }
      drawing = true;
      var p = point(event);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(p.x + 0.01, p.y + 0.01);
      ctx.stroke();
      dirty = true;
      try { canvas.setPointerCapture(event.pointerId); } catch (err) { /* not supported */ }
      event.preventDefault();
    });
    canvas.addEventListener("pointermove", function (event) {
      if (!drawing) { return; }
      var p = point(event);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      event.preventDefault();
    });
    function end() { drawing = false; }
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
    canvas.addEventListener("lostpointercapture", end);
    return {
      canvas: canvas,
      setup: setup,
      clear: function () {
        if (ctx) {
          ctx.save();
          ctx.setTransform(1, 0, 0, 1, 0, 0);
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.restore();
        }
        dirty = false;
      },
      isEmpty: function () { return !dirty; },
      toDataURL: function () {
        var out = document.createElement("canvas");
        out.width = canvas.width;
        out.height = canvas.height;
        var octx = out.getContext("2d");
        octx.fillStyle = "#ffffff";
        octx.fillRect(0, 0, out.width, out.height);
        octx.drawImage(canvas, 0, 0);
        return out.toDataURL("image/png");
      }
    };
  }

  function findCountersignItem(id) {
    var b = bundle();
    return ((b && b.to_countersign) || []).filter(function (m) { return String(m.id) === String(id); })[0] || null;
  }

  function openCountersignPanel(li, m, contest) {
    if (state.csOpen) { closeCountersignPanel(false); }
    var uid = "f-cs-" + m.id;
    var question = h("p", {class: "cs-q", id: uid + "-q", tabindex: "-1"},
      t(contest ? "contest_q" : "countersign_q", {label: m.label, time: fmt(m.declared_at)}));
    var comment = null;
    var commentBlock = null;
    if (contest) {
      comment = h("textarea", {id: uid + "-comment", rows: "3", maxlength: "2000", required: true, "aria-describedby": uid + "-hint"});
      commentBlock = h("div", null, [
        h("label", {for: uid + "-comment"}, t("contest_comment")),
        h("p", {class: "hint", id: uid + "-hint"}, t("contest_comment_hint")),
        comment
      ]);
    }
    var pad = signaturePad();
    pad.canvas.id = uid + "-sig";
    var clearButton = h("button", {type: "button", class: "btn big secondary"}, t("signature_clear"));
    var sigBlock = h("div", {class: "sigblock"}, [
      h("p", {class: "label", id: uid + "-sig-label"}, t("signature_optional")),
      h("p", {class: "hint"}, t("signature_hint")),
      pad.canvas,
      h("div", {class: "acts"}, clearButton)
    ]);
    var error = h("p", {class: "fmsg error", id: uid + "-error", role: "alert", hidden: true});
    var confirm = h("button", {type: "button", class: contest ? "btn big danger" : "btn big"}, t(contest ? "contest_send" : "countersign_confirm"));
    var cancel = h("button", {type: "button", class: "btn big secondary"}, t("cancel"));
    var panel = h("div", {class: "fpanel", role: "group", "aria-labelledby": uid + "-q"},
      [question, commentBlock, sigBlock, error, h("div", {class: "acts"}, [confirm, cancel])]);
    var acts = li.querySelector(".acts");
    if (acts) { acts.hidden = true; }
    li.appendChild(panel);
    pad.setup();
    state.csOpen = {id: m.id, li: li, panel: panel};
    clearButton.addEventListener("click", function () { pad.clear(); });
    if (comment) {
      comment.addEventListener("input", function () {
        if (comment.getAttribute("aria-invalid") === "true") { clearErrors(panel, error); }
      });
    }
    cancel.addEventListener("click", function () { closeCountersignPanel(true); });
    confirm.addEventListener("click", function () { confirmCountersign(m, contest, comment, pad, error, confirm); });
    panel.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { event.preventDefault(); closeCountersignPanel(true); }
    });
    (comment || question).focus();
  }

  function closeCountersignPanel(restoreFocus) {
    var open = state.csOpen;
    if (!open) { return; }
    state.csOpen = null;
    if (open.panel.parentNode) { open.panel.parentNode.removeChild(open.panel); }
    var acts = open.li.querySelector(".acts");
    if (acts) { acts.hidden = false; }
    if (state.csDirty) { renderCountersign(); }
    if (!restoreFocus) { return; }
    var li = el.csList.querySelector('[data-key="' + cssEscape(String(open.id)) + '"]');
    var button = li && li.querySelector(".acts button");
    (button || el.csTitle).focus();
  }

  function confirmCountersign(m, contest, commentField, pad, errorNode, button) {
    if (!state.store) { return; }
    clearErrors(errorNode.parentNode, errorNode);
    var comment = commentField ? commentField.value.trim() : "";
    if (contest && !comment) { showError(errorNode, t("err_comment"), commentField); return; }
    var now = new Date();
    var entry = {
      kind: "countersign", client_uuid: uuid4(), device_recorded_at: now.toISOString(), declared_at: isoWithOffset(now),
      milestone_id: m.id, contest: contest, comment: comment
    };
    var action = t(contest ? "contest_of" : "countersign_of", {label: m.label});
    var which = t("milestone_of", {time: fmt(m.declared_at)});    // repeatable milestones: which occurrence
    var records = [makeRecord(entry, m.label, comment ? which + " — " + comment : which)];
    if (!pad.isEmpty()) {
      var signature = {
        kind: "photo", client_uuid: uuid4(), device_recorded_at: entry.device_recorded_at, declared_at: entry.declared_at,
        data_url: pad.toDataURL(), title: truncate(t("signature_title", {action: action, time: fmt(m.declared_at)}), 240),
        document_type: "PHOTO"
      };
      records.push(makeRecord(signature, t("signature_label"), signature.title));
    }
    button.disabled = true;
    enqueue(records).then(function () {
      closeCountersignPanel(false);
      renderCountersign();
      setText(el.csDone, t(contest ? "contest_saved" : "countersign_saved", {label: m.label}));
      el.csTitle.focus();
    }, function (err) {
      logError(err);
      button.disabled = false;
      showError(errorNode, t("err_storage"));
    });
  }

  // ------------------------------------------------------------------ pumping log
  function submitPumping(event) {
    event.preventDefault();
    if (!state.store) { return; }
    clearErrors(el.pumpForm, el.pumpError);
    setText(el.pumpDone, "");
    var declared = inputToDate(el.pumpTime.value);
    if (!declared) { showError(el.pumpError, t("err_time"), el.pumpTime); return; }
    if (declared.getTime() > Date.now() + FUTURE_TOLERANCE_MS) { showError(el.pumpError, t("err_future"), el.pumpTime); return; }
    var entry = {kind: "pumping", client_uuid: uuid4(), device_recorded_at: "", declared_at: isoWithOffset(declared)};
    var fields = [
      [el.pumpPressure, "pressure_bar", t("field_pressure"), "bar"],
      [el.pumpRate, "rate_m3h", t("field_rate"), "m³/h"],
      [el.pumpTemp, "temperature_c", t("field_temperature"), "°C"],
      [el.pumpLevel, "level_mm", t("field_level"), "mm"],
      [el.pumpMoved, "hourly_m3", t("field_moved"), "m³"],
      [el.pumpCumul, "cumulative_m3", t("field_cumulated"), "m³"]
    ];
    var parts = [];
    for (var i = 0; i < fields.length; i += 1) {
      var parsed = parseDecimal(fields[i][0].value);
      if (!parsed.ok) { showError(el.pumpError, t("err_number", {field: fields[i][2]}), fields[i][0]); return; }
      if (parsed.value !== null) {
        entry[fields[i][1]] = parsed.value;
        parts.push(parsed.value + " " + fields[i][3]);
      }
    }
    if (!parts.length) { showError(el.pumpError, t("err_pump_empty"), el.pumpPressure); return; }
    var savedAt = new Date();
    entry.device_recorded_at = savedAt.toISOString();
    el.pumpSubmit.disabled = true;
    enqueue([makeRecord(entry, t("kind_pumping"), parts.join(" · "))]).then(function () {
      el.pumpSubmit.disabled = false;
      el.pumpPressure.value = "";
      el.pumpRate.value = "";
      el.pumpTemp.value = "";
      el.pumpLevel.value = "";
      el.pumpMoved.value = "";
      el.pumpCumul.value = "";
      setNow(el.pumpTime);
      setText(el.pumpDone, savedMessage(t("kind_pumping"), savedAt));
      el.pumpPressure.focus();
    }, function (err) {
      logError(err);
      el.pumpSubmit.disabled = false;
      showError(el.pumpError, t("err_storage"));
    });
  }

  // ------------------------------------------------------------------ queue actions
  function findRecord(uuid) { return state.queue.filter(function (r) { return r.client_uuid === uuid; })[0] || null; }

  function retryRecord(uuid) {
    var rec = findRecord(uuid);
    if (!rec) { return; }
    rec.state = "pending";
    rec.message = "";
    rec.code = "";
    state.store.putEntries([rec]).then(function () {
      renderAll();
      requestSync({wait: true});
    }, function (err) { logError(err); setResult(t("err_storage"), "error"); });
  }

  function dismissRecord(uuid) {
    state.store.deleteEntries([uuid]).then(function () {
      state.queue = state.queue.filter(function (r) { return r.client_uuid !== uuid; });
      renderAll();
      if (!el.queueList.contains(document.activeElement)) { el.queueTitle.focus(); }
    }, function (err) { logError(err); setResult(t("err_storage"), "error"); });
  }

  function clearResults() {
    state.meta.results_cleared_at = new Date().toISOString();
    saveMeta();
    renderResults();
    el.resultsTitle.focus();
  }

  // =========================================================================== synchronisation
  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (match) { return decodeURIComponent(match[1]); }
    try {
      var headers = JSON.parse(document.body.getAttribute("hx-headers") || "{}");
      return headers["X-CSRFToken"] || "";
    } catch (err) {
      return "";
    }
  }

  /* JSON request; failures carry .network (no answer), .status (HTTP error) or .invalid (not JSON). */
  function api(method, url, payload, timeoutMs) {
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs || 30000) : null;
    var headers = {"Accept": "application/json"};
    var init = {method: method, headers: headers, credentials: "same-origin", cache: "no-store"};
    if (controller) { init.signal = controller.signal; }
    if (payload !== undefined) {
      headers["Content-Type"] = "application/json";
      headers["X-CSRFToken"] = csrfToken();
      init.body = JSON.stringify(payload);
    }
    return fetch(url, init).then(function (response) {
      return response.text().then(function (text) { return {response: response, text: text}; });
    }).then(function (got) {
      if (timer) { clearTimeout(timer); }
      var data = null;
      try { data = got.text ? JSON.parse(got.text) : null; } catch (err) { data = null; }
      if (!got.response.ok) {
        var failure = new Error("HTTP " + got.response.status);
        failure.status = got.response.status;
        failure.data = data;
        throw failure;
      }
      if (data === null || typeof data !== "object") {
        var invalid = new Error("Unexpected response");
        invalid.invalid = true;
        invalid.status = got.response.status;
        throw invalid;
      }
      return data;
    }, function (err) {
      if (timer) { clearTimeout(timer); }
      var failure = new Error("Network failure");
      failure.network = true;
      failure.cause = err;
      throw failure;
    });
  }

  function classify(err) {
    if (!err) { return "local"; }
    if (err.network) { return "network"; }
    if (err.status === 401 || err.status === 403) { return "auth"; }
    if (err.status === 404) { return "notfound"; }
    if (err.status || err.invalid) { return "server"; }
    return "local";
  }

  /* Entries are sent only for the person signed in now (an entry is never re-attributed). */
  function verifyOwner() {
    if (state.verifiedOwner) { return Promise.resolve(state.verifiedOwner); }
    if (!CONFIG.meUrl) { state.verifiedOwner = state.owner; return Promise.resolve(state.owner); }
    return api("GET", CONFIG.meUrl, undefined, 20000).then(function (me) {
      // a master is identified by his own access link: entries left by a relieved master are never sent as his successor's
      var key = me.kind === "master" ? "master:" + String(me.call || "") + ":" + String(me.link || "")
                                     : "user:" + String(me.email || "").toLowerCase();
      state.verifiedOwner = key;
      if (state.owner && key !== state.owner) { state.problem = "otheruser"; }
      return key;
    });
  }

  function saveMeta() {
    if (!state.store) { return Promise.resolve(); }
    return state.store.putBundle(state.meta).then(function () {
      state.storageFull = false;
    }, function (err) {
      logError(err);
      state.storageFull = true;
    });
  }

  function refreshBundle() {
    return api("GET", CONFIG.bundleUrl, undefined, 30000).then(function (data) {
      if (!data.call || !Array.isArray(data.milestone_types)) {
        var invalid = new Error("Unexpected bundle");
        invalid.invalid = true;
        throw invalid;
      }
      state.meta.bundle = data;
      state.meta.fetched_at = new Date().toISOString();
      state.fresh = true;
      state.reachable = true;
    });
  }

  function makeBatches(records) {
    var batches = [];
    var current = [];
    var bytes = 0;
    records.forEach(function (rec) {
      var size = JSON.stringify(rec.entry).length;
      if (current.length && (current.length >= BATCH_SIZE || bytes + size > BATCH_BYTES)) {
        batches.push(current);
        current = [];
        bytes = 0;
      }
      current.push(rec);
      bytes += size;
    });
    if (current.length) { batches.push(current); }
    return batches;
  }

  function logResult(rec, res, syncedAt) {
    var e = rec.entry;
    var item = {
      client_uuid: rec.client_uuid, kind: e.kind, label: rec.label, detail: rec.detail, status: res.status,
      deferred: !!res.deferred, id: res.id || null, declared_at: e.declared_at, device_recorded_at: e.device_recorded_at,
      synced_at: syncedAt, type: e.type || "", cause: e.cause || "", cause_reason: e.cause_reason || "",
      related_id: e.related_id || null, related_client_uuid: e.related_client_uuid || "", milestone_id: e.milestone_id || null,
      contest: !!e.contest
    };
    state.meta.last_results = [item].concat(state.meta.last_results || []).slice(0, RESULTS_KEPT);
  }

  async function refuseLocally(rec, code, message, outcome) {
    rec.state = "refused";
    rec.code = code;
    rec.message = message;
    await state.store.putEntries([rec]);
    outcome.sent += 1;
    outcome.refused += 1;
  }

  async function sendBatch(records, outcome) {
    records.forEach(function (r) { state.sending[r.client_uuid] = true; });
    renderQueue();
    var response;
    try {
      response = await api("POST", CONFIG.syncUrl, {entries: records.map(function (r) { return r.entry; })}, 120000);
    } catch (err) {
      records.forEach(function (r) { delete state.sending[r.client_uuid]; });
      if (err && err.status === 413) {                      // too large for a proxy in front of the registry
        if (records.length > 1) {
          var half = Math.ceil(records.length / 2);
          await sendBatch(records.slice(0, half), outcome);
          await sendBatch(records.slice(half), outcome);
          return;
        }
        await refuseLocally(records[0], "too_large", t("too_large"), outcome);
        return;
      }
      throw err;
    }
    var byUuid = {};
    (Array.isArray(response.results) ? response.results : []).forEach(function (res) {
      if (res && res.client_uuid) { byUuid[String(res.client_uuid)] = res; }
    });
    var syncedAt = new Date().toISOString();
    var done = [];
    var refused = [];
    records.forEach(function (rec) {
      delete state.sending[rec.client_uuid];
      var res = byUuid[rec.client_uuid];
      if (!res) { return; }                                   // not processed: stays in the queue
      if (res.status === "ok" || res.status === "conflict") {
        outcome.sent += 1;
        outcome[res.status] += 1;
        if (res.deferred) { outcome.deferred += 1; }
        done.push(rec.client_uuid);
        logResult(rec, res, syncedAt);
      } else if (res.status === "refused") {
        outcome.sent += 1;
        outcome.refused += 1;
        rec.state = "refused";
        rec.code = String(res.code || "");
        rec.message = String(res.message || "");
        refused.push(rec);
      }
    });
    if (refused.length) { await state.store.putEntries(refused); }
    if (done.length) { await state.store.deleteEntries(done); }
    state.queue = state.queue.filter(function (r) { return done.indexOf(r.client_uuid) < 0; });
    await saveMeta();
    renderQueue();
    renderResults();
    renderStatus();
  }

  function noteFailure(err, outcome) {
    var kind = classify(err);
    outcome.error = kind;
    outcome.status = (err && err.status) || 0;
    if (kind === "network") { state.reachable = false; }
    else if (kind !== "local") { state.reachable = true; }
    if (kind === "auth") { state.problem = "auth"; }
    if (kind === "notfound") { state.problem = "notfound"; }
    if (kind !== "network") { logError(err); }
  }

  function report(outcome, opts) {
    var parts = [];
    var tone = "success";
    if (outcome.sent) {
      parts.push(t("sync_done", {time: fmt(new Date())}));
      if (outcome.ok) { parts.push(t("sync_ok", {n: outcome.ok})); }
      if (outcome.conflict) { parts.push(t("sync_conflict", {n: outcome.conflict})); tone = "warning"; }
      if (outcome.deferred) { parts.push(t("sync_deferred", {n: outcome.deferred})); }
      if (outcome.refused) { parts.push(t("sync_refused", {n: outcome.refused})); tone = "error"; }
    }
    if (outcome.error) {
      parts.push(t({
        offline: "offline_kept", network: "sync_failed_network", auth: "sync_failed_auth", notfound: "sync_failed_notfound",
        server: "sync_failed_server", local: "err_storage"
      }[outcome.error] || "sync_failed_server", {status: outcome.status || "—"}));
      tone = outcome.error === "offline" ? "warning" : "error";
    } else if (!outcome.sent) {
      if (opts.quiet && !opts.initial) {                       // nothing worth announcing…
        if (state.lastTone === "error") { state.lastResult = ""; state.lastTone = ""; setResult("", ""); }  // …but the problem is over
        return;
      }
      parts.push(t("sync_nothing", {time: fmt(new Date())}));
    }
    var text = parts.join(" ");
    if (opts.quiet && text === state.lastResult) { return; }  // do not repeat the same news every minute
    state.lastResult = text;
    state.lastTone = tone;
    setResult(text, tone);
  }

  async function runSync(opts) {
    var outcome = {sent: 0, ok: 0, conflict: 0, deferred: 0, refused: 0, error: "", status: 0};
    if (navigator.onLine === false) {
      outcome.error = "offline";
      report(outcome, opts);
      return;
    }
    try {
      state.queue = await state.store.listQueue();               // another window may have sent some
    } catch (err) {
      logError(err);
    }
    try {
      var me = await verifyOwner();
      var pending = state.queue.filter(function (r) {
        return r.reference === REF && belongsTo(r, me) && r.state !== "refused";
      }).sort(byDeviceTime);
      var batches = makeBatches(pending);
      for (var i = 0; i < batches.length; i += 1) { await sendBatch(batches[i], outcome); }
      state.meta.last_sync_at = new Date().toISOString();
      state.reachable = true;
      await refreshBundle();
      if (state.problem !== "otheruser") { state.problem = ""; }
    } catch (err) {
      noteFailure(err, outcome);
    }
    await saveMeta();
    report(outcome, opts);
  }

  function withLock(wait, work) {
    if (!navigator.locks || typeof navigator.locks.request !== "function") { return Promise.resolve(work()); }
    return navigator.locks.request("fluxaa-field-sync", wait ? {} : {ifAvailable: true}, function (lock) {
      return lock ? work() : null;                                // another window is synchronising
    });
  }

  /* Sends the whole queue of this call (oldest first, batches of 50), then refreshes the bundle. */
  function requestSync(options) {
    var opts = options || {};
    if (!state.store) { return Promise.resolve(); }
    if (state.syncing) { state.syncAgain = true; return state.syncPromise || Promise.resolve(); }
    state.syncing = true;
    renderStatus();
    state.syncPromise = withLock(!!opts.wait, function () { return runSync(opts); })
      .catch(logError)
      .then(function () {
        state.syncing = false;
        state.sending = {};
        state.syncPromise = null;
        renderAll();
        if (state.syncAgain) {
          state.syncAgain = false;
          return requestSync({quiet: true});
        }
        return null;
      });
    return state.syncPromise;
  }

  // =========================================================================== offline shell (service worker)
  function pageUrls() {
    var urls = [location.pathname];
    Array.prototype.forEach.call(document.querySelectorAll("link[href], script[src], img[src]"), function (node) {
      urls.push(node.href || node.src);
    });
    if (window.performance && typeof performance.getEntriesByType === "function") {
      performance.getEntriesByType("resource").forEach(function (entry) { urls.push(entry.name); });
    }
    var seen = {};
    return urls.map(function (url) {
      try { return new URL(url, location.href); } catch (err) { return null; }
    }).filter(function (url) {
      if (!url || url.origin !== location.origin || seen[url.pathname]) { return false; }
      seen[url.pathname] = true;
      return url.pathname === location.pathname || url.pathname.indexOf("/static/") === 0;
    }).map(function (url) { return url.pathname; });
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) {
      state.swProblem = true;
      return;
    }
    var controlled = !!navigator.serviceWorker.controller;
    navigator.serviceWorker.register(SW_URL, {scope: "/"}).then(function () {
      if (controlled) { return null; }                           // this page already went through the worker
      return navigator.serviceWorker.ready.then(function (registration) {
        // first visit: the page and its assets were loaded before the worker existed
        if (registration.active) { registration.active.postMessage({type: "cache-urls", urls: pageUrls()}); }
      });
    }).catch(function (err) {
      logError(err);
      state.swProblem = true;
      renderNotices();
    });
  }

  // =========================================================================== events and start
  function tick() {
    refreshAutoTimes();
    renderStatus();
    renderNotices();
    renderTasks();
    if (navigator.onLine === false || !state.store) { return; }
    if (document.visibilityState === "visible" || pendingRecords().length) { requestSync({quiet: true}); }
  }

  function wireEvents() {
    el.syncButton.addEventListener("click", function () {
      if (navigator.onLine === false) {
        state.lastResult = "";
        report({sent: 0, error: "offline"}, {});
        renderStatus();
        return;
      }
      requestSync({wait: true});
    });

    el.types.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-code]");
      if (button && !button.disabled) { openMilestoneForm(button.getAttribute("data-code"), ""); }
    });
    el.openList.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-action='end']");
      if (button) { openMilestoneForm(button.getAttribute("data-code"), button.getAttribute("data-related")); }
    });
    el.msForm.addEventListener("submit", submitMilestone);
    el.msCancel.addEventListener("click", function () { closeMilestoneForm(true); });
    el.msForm.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { event.preventDefault(); closeMilestoneForm(true); }
    });
    el.msCause.addEventListener("change", syncReasonRow);
    el.msPhoto.addEventListener("change", onPhotoChange);
    el.msPhotoRemove.addEventListener("click", function () { clearPhoto(); el.msPhoto.focus(); });

    el.csList.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-action='countersign'], button[data-action='contest']");
      if (!button) { return; }
      var li = button.closest("[data-key]");
      var m = li && findCountersignItem(li.getAttribute("data-key"));
      if (m) { openCountersignPanel(li, m, button.getAttribute("data-action") === "contest"); }
    });

    el.pumpForm.addEventListener("submit", submitPumping);
    [[el.msForm, el.msError], [el.pumpForm, el.pumpError]].forEach(function (pair) {
      pair[0].addEventListener("input", function (event) {
        var invalid = pair[0].querySelector("[aria-invalid='true']");
        if (invalid && (invalid === event.target || (invalid.name && invalid.name === event.target.name))) { clearErrors(pair[0], pair[1]); }
      });
    });

    el.queueList.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-action]");
      var li = button && button.closest("[data-key]");
      if (!li) { return; }
      if (button.getAttribute("data-action") === "retry") { retryRecord(li.getAttribute("data-key")); }
      if (button.getAttribute("data-action") === "dismiss") { dismissRecord(li.getAttribute("data-key")); }
    });
    el.resultsClear.addEventListener("click", clearResults);
    el.notices.addEventListener("click", function (event) {
      if (event.target.closest("[data-action='reload']")) { location.reload(); }
    });

    root.addEventListener("click", function (event) {
      var button = event.target.closest("[data-now]");
      var input = button && byId(button.getAttribute("data-now"));
      if (input) { setNow(input); input.focus(); }
    });
    [el.msTime, el.pumpTime].forEach(function (input) {
      input.addEventListener("input", function () { input.removeAttribute("data-auto"); });
    });
    root.addEventListener("focusin", function (event) {
      if (event.target !== el.msTime && event.target !== el.pumpTime) { refreshAutoTimes(); }
    });

    window.addEventListener("online", function () {
      state.lastResult = "";
      state.lastTone = "";
      setResult(t("back_online"));
      renderStatus();
      requestSync({});
    });
    window.addEventListener("offline", function () {
      state.lastResult = "";
      report({sent: 0, error: "offline"}, {});
      renderAll();
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible" && state.store && navigator.onLine !== false) { requestSync({quiet: true}); }
    });
    window.addEventListener("beforeunload", function (event) {
      if (state.store && state.store.kind === "memory" && pendingRecords().length) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  }

  function start() {
    wireEvents();
    watchStatusBar();
    setNow(el.pumpTime);
    renderAll();
    registerServiceWorker();
    openStore().then(function (store) {
      state.store = store;
      return Promise.all([
        store.getBundle(REF).catch(function () { return null; }),
        store.listQueue().catch(function () { return []; })
      ]);
    }).then(function (loaded) {
      if (loaded[0]) {
        var meta = emptyMeta();
        Object.keys(meta).forEach(function (key) { if (has(loaded[0], key) && loaded[0][key] !== undefined) { meta[key] = loaded[0][key]; } });
        meta.reference = REF;
        state.meta = meta;
      }
      state.queue = loaded[1] || [];
      renderAll();
      if (navigator.onLine === false) {
        report({sent: 0, error: "offline"}, {});
        return null;
      }
      return requestSync({quiet: true, initial: true});
    }).catch(function (err) {
      logError(err);
      setResult(t("err_start"), "error");
    });
    setInterval(tick, SYNC_EVERY_MS);
  }

  start();
})();

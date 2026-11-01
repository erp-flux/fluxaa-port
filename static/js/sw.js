/* FLUXAA Port — service worker of the field application (CDC EF-14, ENF-6).
 * Served at /sw.js (scope "/") by registry.views.service_worker.
 *  - install: pre-caches the application shell (stylesheet, scripts, fonts, icon);
 *  - field pages (/escales/<id>/terrain/): network first, the cached copy when the network fails;
 *  - static assets (/static/…): cache first;
 *  - /api/ responses and non-GET requests are NEVER cached: call data and the queue of entries are
 *    kept by field.js in IndexedDB.
 * Bump CACHE to publish a new shell; activate deletes the caches of previous versions. */
"use strict";

var CACHE = "fluxaa-field-v1";
var CACHE_PREFIX = "fluxaa-field-";
var SHELL = [
  "/static/css/fluxaa.css",
  "/static/js/app.js",
  "/static/js/field.js",
  "/static/vendor/htmx-2.0.11.min.js",
  "/static/fonts/poppins-latin-400-normal.woff2",
  "/static/fonts/poppins-latin-500-normal.woff2",
  "/static/fonts/poppins-latin-600-normal.woff2",
  "/static/fonts/poppins-latin-700-normal.woff2",
  "/static/fonts/poppins-latin-ext-400-normal.woff2",
  "/static/fonts/poppins-latin-ext-500-normal.woff2",
  "/static/fonts/poppins-latin-ext-600-normal.woff2",
  "/static/fonts/ibm-plex-mono-latin-400-normal.woff2",
  "/static/fonts/ibm-plex-mono-latin-500-normal.woff2",
  "/static/img/favicon.svg"
];
var FIELD_PAGE = /^\/escales\/\d+\/terrain\/$/;
// ManifestStaticFilesStorage names files "name.<12 hex>.ext": such a URL never changes content.
var HASHED = /\.[0-9a-f]{12}(\.[A-Za-z0-9]+)$/;
// On a weak link, the cached field page is served after this delay (the network still refreshes it).
var NETWORK_TIMEOUT_MS = 6000;

function isCacheable(response) {
  return !!response && response.status === 200 && response.type === "basic" && !response.redirected;
}

function isStatic(url) { return url.pathname.indexOf("/static/") === 0; }

// ------------------------------------------------------------------ life cycle
self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return Promise.all(SHELL.map(function (path) {
      // one missing file must not leave the device without any offline shell
      return cache.add(new Request(path, {cache: "reload", credentials: "same-origin"})).catch(function (err) {
        console.warn("[FLUXAA sw] not pre-cached:", path, err);
      });
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (names) {
    return Promise.all(names.filter(function (name) {
      return name.indexOf(CACHE_PREFIX) === 0 && name !== CACHE;
    }).map(function (name) { return caches.delete(name); }));
  }).then(function () { return self.clients.claim(); }));
});

// ------------------------------------------------------------------ requests
self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") { return; }                      // never a non-GET request
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) { return; }
  if (url.pathname.indexOf("/api/") === 0) { return; }           // never an API response
  if (request.mode === "navigate") {
    if (FIELD_PAGE.test(url.pathname)) {
      event.respondWith(fieldPage(event, request, url));
    } else if (url.pathname === "/" || url.pathname.indexOf("/escales/") === 0) {
      // not kept offline; when the network fails, point to the field apps this device holds
      event.respondWith(fetch(request).catch(offlinePage));
    }
    return;
  }
  if (isStatic(url) && !request.headers.has("range")) {
    event.respondWith(staticAsset(event, request, url));
  }
});

/* Network first; the copy kept on the device when the network fails, answers with a server error,
   or takes longer than NETWORK_TIMEOUT_MS. One copy per call, whatever the query string. */
function fieldPage(event, request, url) {
  var key = url.pathname;
  var saved = null;
  var network = fetch(request).then(function (response) {
    if (isCacheable(response)) {
      var copy = response.clone();
      saved = caches.open(CACHE).then(function (cache) { return cache.put(key, copy); });
    }
    return response;
  });
  event.waitUntil(network.then(function () { return saved; }, function () { return null; }).catch(function () { return null; }));
  return caches.open(CACHE).then(function (cache) {
    return cache.match(key, {ignoreVary: true});
  }).then(function (cached) {
    if (!cached) { return network.catch(offlinePage); }
    return new Promise(function (resolve) {
      var done = false;
      function finish(response) {
        if (done) { return; }
        done = true;
        clearTimeout(timer);
        resolve(response);
      }
      var timer = setTimeout(function () { finish(cached); }, NETWORK_TIMEOUT_MS);
      network.then(function (response) { finish(response.status >= 500 ? cached : response); }, function () { finish(cached); });
    });
  });
}

/* Cache first. Unversioned names are refreshed in the background so that the next load is current;
   offline, a versioned name never fetched before falls back to the pre-cached unversioned file. */
function staticAsset(event, request, url) {
  return caches.open(CACHE).then(function (cache) {
    return cache.match(request, {ignoreVary: true}).then(function (cached) {
      if (cached) {
        if (!HASHED.test(url.pathname)) {
          event.waitUntil(fetch(request).then(function (response) {
            return isCacheable(response) ? cache.put(request, response) : null;
          }).catch(function () { return null; }));
        }
        return cached;
      }
      return fetch(request).then(function (response) {
        if (isCacheable(response)) {
          var copy = response.clone();
          event.waitUntil(cache.put(request, copy).catch(function () { return null; }));
        }
        return response;
      }, function () {
        var plain = url.pathname.replace(HASHED, "$1");
        if (plain === url.pathname) { return Response.error(); }
        return cache.match(plain, {ignoreVary: true}).then(function (fallback) { return fallback || Response.error(); });
      });
    });
  });
}

// ------------------------------------------------------------------ messages from field.js
/* On its first visit the page was loaded before this worker existed: field.js sends the URLs of the
   page and of its static files so that they are kept for offline use. Only those two kinds are kept. */
self.addEventListener("message", function (event) {
  var data = event.data || {};
  if (data.type !== "cache-urls" || !Array.isArray(data.urls)) { return; }
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return Promise.all(data.urls.slice(0, 100).map(function (path) {
      var url;
      try { url = new URL(String(path), self.location.origin); } catch (err) { return null; }
      if (url.origin !== self.location.origin) { return null; }
      var page = FIELD_PAGE.test(url.pathname);
      if (!page && !isStatic(url)) { return null; }
      var key = page ? url.pathname : url.pathname + url.search;
      return cache.match(key, {ignoreVary: true}).then(function (hit) {
        if (hit && !page) { return null; }
        return fetch(new Request(url.href, {credentials: "same-origin", redirect: "manual"})).then(function (response) {
          return isCacheable(response) ? cache.put(key, response) : null;
        });
      }).catch(function () { return null; });
    }));
  }));
});

// ------------------------------------------------------------------ offline answer for other pages
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[c];
  });
}

function decodeEntities(text) {
  return String(text).replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, function (all, code) {
    var named = {amp: "&", lt: "<", gt: ">", quot: "\"", apos: "'"}[code.toLowerCase()];
    if (named) { return named; }
    var n = code.charAt(1).toLowerCase() === "x" ? parseInt(code.slice(2), 16) : parseInt(code.slice(1), 10);
    return isNaN(n) ? all : String.fromCharCode(n);
  });
}

/* Bilingual on purpose: the worker has no access to the translation catalogue. */
function offlinePage() {
  return caches.open(CACHE).then(function (cache) {
    return cache.keys().then(function (requests) {
      var paths = requests.map(function (r) { return new URL(r.url).pathname; }).filter(function (p) { return FIELD_PAGE.test(p); });
      return Promise.all(paths.map(function (path) {
        return cache.match(path, {ignoreVary: true}).then(function (response) {
          return response ? response.text() : "";
        }).then(function (html) {
          var match = /<title>([^<]*)<\/title>/i.exec(html);
          var title = match ? decodeEntities(match[1]).replace(/\s+/g, " ").trim() : path;
          return {path: path, title: title};
        });
      }));
    });
  }).catch(function () { return []; }).then(function (pages) {
    var list = pages.map(function (p) {
      return "<li><a class=\"btn big secondary\" href=\"" + escapeHtml(p.path) + "\">" + escapeHtml(p.title) + "</a></li>";
    }).join("");
    var body = list
      ? "<p>Applications terrain disponibles sur cet appareil <span lang=\"en\">/ Field apps available on this device</span> :</p>" +
        "<ul style=\"list-style:none;padding:0;display:grid;gap:8px\">" + list + "</ul>"
      : "<p>Aucune application terrain n’est encore enregistrée sur cet appareil : ouvrez-la une fois connecté." +
        " <span lang=\"en\">No field app is saved on this device yet: open it once while connected.</span></p>";
    var html = "<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">" +
      "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">" +
      "<title>Hors ligne / Offline — FLUXAA Port</title><link rel=\"stylesheet\" href=\"/static/css/fluxaa.css\"></head>" +
      "<body><main id=\"main\"><div class=\"wrap\"><div class=\"section\" style=\"max-width:720px;margin:24px auto\">" +
      "<h1>Hors ligne <span lang=\"en\">/ Offline</span></h1>" +
      "<p>Cette page n’est pas disponible sans connexion. <span lang=\"en\">This page is not available offline.</span></p>" +
      body + "</div></div></main></body></html>";
    return new Response(html, {status: 503, headers: {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}});
  });
}

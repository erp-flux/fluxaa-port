/* FLUXAA Port — small progressive enhancements. The application works without JavaScript. */
(function () {
  "use strict";

  // Confirmation for irreversible acts (decisions, closures, cancellations)
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) { event.preventDefault(); }
  }, true);

  // Lists that reload their page when changed (request type, period): <select data-autosubmit>.
  // A <noscript> button does the same without JavaScript. No inline handlers: see the CSP.
  document.addEventListener("change", function (event) {
    var field = event.target;
    if (field.matches && field.matches("select[data-autosubmit]") && field.form) { field.form.submit(); }
  });

  // Default "declared time" inputs to now (port time zone is applied server-side)
  function pad(n) { return String(n).padStart(2, "0"); }
  function nowLocal() {
    var d = new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  document.querySelectorAll("input[data-default-now]").forEach(function (input) {
    if (!input.value) { input.value = nowLocal(); }
  });

  // Hand-drawn signature pads: <canvas class="sigpad" data-target="input-id">
  document.querySelectorAll("canvas.sigpad").forEach(function (canvas) {
    var target = document.getElementById(canvas.getAttribute("data-target"));
    var ctx = canvas.getContext("2d");
    var drawing = false, dirty = false;
    function size() {
      var ratio = window.devicePixelRatio || 1;
      canvas.width = canvas.clientWidth * ratio; canvas.height = canvas.clientHeight * ratio;
      ctx.scale(ratio, ratio); ctx.lineWidth = 2.2; ctx.lineCap = "round"; ctx.strokeStyle = "#202528";
    }
    size();
    function point(e) { var r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
    canvas.addEventListener("pointerdown", function (e) { drawing = true; var p = point(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointermove", function (e) { if (!drawing) return; var p = point(e); ctx.lineTo(p.x, p.y); ctx.stroke(); dirty = true; });
    function end() { if (drawing && dirty && target) { target.value = canvas.toDataURL("image/png"); } drawing = false; }
    canvas.addEventListener("pointerup", end); canvas.addEventListener("pointerleave", end);
    var clear = document.querySelector("[data-clear='" + canvas.id + "']");
    if (clear) clear.addEventListener("click", function () { ctx.clearRect(0, 0, canvas.width, canvas.height); dirty = false; if (target) target.value = ""; });
  });

  // After signing out: remove the call data kept for offline use (cached field pages and call
  // bundles). Entries still waiting to be sent are kept: they stay bound to the person who made them.
  if (document.body.hasAttribute("data-purge-field")) {
    try {
      if (window.caches) {
        caches.keys().then(function (names) {
          names.filter(function (n) { return n.indexOf("fluxaa-field-") === 0; }).forEach(function (name) {
            caches.open(name).then(function (cache) {
              cache.keys().then(function (requests) {
                requests.forEach(function (req) {
                  if (/^\/escales\/\d+\/terrain\/$/.test(new URL(req.url).pathname)) { cache.delete(req); }
                });
              });
            });
          });
        });
      }
      if (window.indexedDB) {
        var open = indexedDB.open("fluxaa-field");
        open.onupgradeneeded = function (e) { e.target.transaction.abort(); };  // nothing stored: create nothing
        open.onsuccess = function () {
          var db = open.result;
          if (db.objectStoreNames.contains("bundles")) { db.transaction("bundles", "readwrite").objectStore("bundles").clear(); }
          db.close();
        };
      }
      for (var i = localStorage.length - 1; i >= 0; i--) {
        var key = localStorage.key(i);
        if (key && key.indexOf("fluxaa-field:bundles:") === 0) { localStorage.removeItem(key); }
      }
    } catch (err) { /* storage unavailable: nothing to remove */ }
  }

  // Show the extra reason field when the interruption cause requires it
  document.querySelectorAll("select[data-reason-for]").forEach(function (select) {
    var box = document.getElementById(select.getAttribute("data-reason-for"));
    function sync() {
      var opt = select.options[select.selectedIndex];
      if (box) box.hidden = !(opt && opt.getAttribute("data-requires-reason") === "1");
    }
    select.addEventListener("change", sync); sync();
  });

  // Parties of a call: an open list. A row (a table row at the announcement, the whole form on the Parties tab)
  // names a role, a registered organisation (filtered by that role) or a new one (name, kind, e-mail, phone).
  // "Add a party" clones the last table row. Without JavaScript every field is shown: the server validates
  // the rows the same way.
  document.querySelectorAll("[data-parties]").forEach(function (box) {
    function sync(row) {
      var role = row.querySelector("select[data-party-role]"), org = row.querySelector("select[data-party-org]");
      if (!role || !org) return;
      var current = role.value;
      Array.prototype.forEach.call(org.options, function (opt) {
        var roles = opt.getAttribute("data-roles");
        opt.hidden = !!(roles && roles.split(" ").indexOf(current) < 0);
        if (opt.hidden && opt.selected) org.value = "";
      });
      var kind = row.querySelector("input[data-party-kind]");
      if (kind) kind.setAttribute("list", "kinds-" + current);
      var isNew = org.value === "new";
      row.querySelectorAll("[data-new]").forEach(function (el) { el.hidden = !isNew; });
    }
    function wire(row) {
      row.querySelectorAll("select").forEach(function (s) { s.addEventListener("change", function () { sync(row); }); });
      var remove = row.querySelector("[data-remove]");
      if (remove) remove.addEventListener("click", function () {
        var rows = box.querySelectorAll("[data-party-row]");
        if (rows.length > 1) row.remove(); else { row.querySelectorAll("input, select").forEach(function (f) { f.value = ""; }); sync(row); }
      });
      sync(row);
    }
    box.querySelectorAll("[data-party-row]").forEach(wire);
    var add = box.querySelector("[data-add]"), body = box.querySelector("tbody");
    if (add && body) add.addEventListener("click", function () {
      var rows = body.querySelectorAll("[data-party-row]"), clone = rows[rows.length - 1].cloneNode(true);
      clone.querySelectorAll("input").forEach(function (f) { f.value = ""; });
      clone.querySelectorAll("select[data-party-org]").forEach(function (f) { f.value = ""; });
      body.appendChild(clone); wire(clone); clone.querySelector("select").focus();
    });
  });
})();

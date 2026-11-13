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
    function addRow(role, kind) {
      var rows = body.querySelectorAll("[data-party-row]"), last = rows[rows.length - 1], target = last;
      var empty = last && !last.querySelector("select[data-party-org]").value && !last.querySelector("input[name=party_name]").value;
      if (!empty) {
        target = last.cloneNode(true);
        target.querySelectorAll("input").forEach(function (f) { f.value = ""; });
        target.querySelectorAll("select[data-party-org]").forEach(function (f) { f.value = ""; });
        body.appendChild(target); wire(target);
      }
      if (role) { var r = target.querySelector("select[data-party-role]"); if (r) { r.value = role; } }
      if (kind) { var k = target.querySelector("input[data-party-kind]"); if (k) { k.value = kind; } }
      sync(target); target.querySelector("select").focus();
      return target;
    }
    box.addRow = addRow;
    if (add && body) add.addEventListener("click", function () { addRow("", ""); });
  });

  // The announcement of a call (v1.5): the kind of cargo filters the operation models and the units; the
  // operations chosen reveal the documents their templates require; the STS block follows the STS model or
  // area; the open list of other documents clones its last row.
  document.querySelectorAll("form[data-announce]").forEach(function (form) {
    function cargo() { var c = form.querySelector("input[data-cargo-kind]:checked"); return c ? c.value : ""; }
    function fits(el, kind) { var kinds = (el.getAttribute("data-cargo") || "").trim(); return !kinds || kinds.split(" ").indexOf(kind) >= 0; }
    function syncCargo() {
      var kind = cargo();
      form.querySelectorAll("label[data-operation], label[data-cargo]").forEach(function (label) {
        var ok = fits(label, kind); label.hidden = !ok;
        var box = label.querySelector("input"); if (box && !ok && box.checked) { box.checked = false; }
      });
      var unit = form.querySelector("#quantity_unit"), first = null;
      if (unit) {
        Array.prototype.forEach.call(unit.options, function (opt) {
          var ok = fits(opt, kind); opt.hidden = !ok; if (ok && first === null) first = opt.value;
          if (!ok && opt.selected && first !== null) unit.value = first;
        });
        if (unit.selectedOptions.length && unit.selectedOptions[0].hidden && first !== null) unit.value = first;
      }
      syncTemplates();
    }
    function syncTemplates() {
      var chosen = {M0: true};
      form.querySelectorAll("input[data-template]:checked").forEach(function (b) { chosen[b.value] = true; });
      form.querySelectorAll("[data-required-docs] li").forEach(function (li) { li.hidden = !chosen[li.getAttribute("data-template")]; });
      var sts = form.querySelector("[data-sts]"), area = form.querySelector("input[name=kind]:checked");
      if (sts) sts.hidden = !(chosen.M3 || (area && area.value === "STS_AREA"));
      // the announcement adapts to the operation (v1.6): the double-banking block follows M9, each model's own
      // questions follow its box; a required question only binds while its block is shown
      var db = form.querySelector("[data-double-banking]");
      if (db) db.hidden = !chosen.M9;
      form.querySelectorAll("fieldset[data-intake]").forEach(function (fs) {
        var on = !!chosen[fs.getAttribute("data-intake")];
        fs.hidden = !on;
        fs.querySelectorAll("[data-required]").forEach(function (f) { f.required = on; });
      });
      // the parties the operations chosen usually bring (port practice): listed beside the parties block
      var hints = form.querySelector("[data-party-hints]");
      if (hints) {
        var any = false;
        hints.querySelectorAll("li[data-template]").forEach(function (li) { var on = !!chosen[li.getAttribute("data-template")]; li.hidden = !on; any = any || on; });
        hints.hidden = !any;
      }
    }
    form.querySelectorAll("[data-add-party-role]").forEach(function (b) {
      b.addEventListener("click", function () {
        var box = form.querySelector("[data-parties]");
        if (box && box.addRow) {
          var row = box.addRow(b.getAttribute("data-add-party-role"), b.getAttribute("data-add-party-kind"));
          b.disabled = true; b.textContent = "✓";
          if (row && row.scrollIntoView) row.scrollIntoView({block: "nearest"});
        }
      });
    });
    // a partner named by its call already has its vessel and its agency: the two other ways of naming it step back
    [["#linked_call", ["#partner_vessel", "#partner_agency", "#partner_agency_name", "#partner_agency_email"]],
     ["#db_partner_call", ["#db_partner_vessel", "#db_partner_agency", "#db_agency_name", "#db_agency_email"]]].forEach(function (pair) {
      var byCall = form.querySelector(pair[0]);
      if (!byCall) return;
      function syncPartner() {
        pair[1].forEach(function (selector) {
          var field = form.querySelector(selector);
          if (!field) return;
          if (byCall.value) field.value = "";
          field.disabled = !!byCall.value;
        });
      }
      byCall.addEventListener("change", syncPartner);
      syncPartner();
    });
    form.querySelectorAll("input[data-cargo-kind]").forEach(function (r) { r.addEventListener("change", syncCargo); });
    form.querySelectorAll("input[data-template], input[name=kind]").forEach(function (b) { b.addEventListener("change", syncTemplates); });
    var table = form.querySelector("table[data-custom-docs]"), add = form.querySelector("[data-add-custom]");
    function wireCustom(row) {
      var remove = row.querySelector("[data-remove-custom]");
      if (remove) remove.addEventListener("click", function () {
        var rows = table.querySelectorAll("[data-custom-row]");
        if (rows.length > 1) row.remove(); else row.querySelectorAll("input").forEach(function (f) { f.value = f.type === "number" ? "24" : ""; });
      });
    }
    if (table) table.querySelectorAll("[data-custom-row]").forEach(wireCustom);
    if (add && table) add.addEventListener("click", function () {
      var rows = table.querySelectorAll("[data-custom-row]"), clone = rows[rows.length - 1].cloneNode(true);
      clone.querySelectorAll("input").forEach(function (f) { f.value = f.type === "number" ? "24" : ""; });
      table.querySelector("tbody").appendChild(clone); wireCustom(clone); clone.querySelector("input").focus();
    });
    syncCargo();
  });
})();

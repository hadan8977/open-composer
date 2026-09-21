// The cockpit's only script. Four jobs, nothing else:
//   1. open a row's detail in the inspector (desktop) or a sheet (phone)
//      by fetching the same route with ?partial=1 -- no page navigation;
//   2. keyboard: ⌘1-6 screens, ⌘F filter, ↑/↓ select, Space/Enter open, Esc close;
//   3. the phone tab bar minimises while scrolling down;
//   4. the agent timeline tail (EventSource) appends rows with textContent.
// Every string that reaches the DOM is either server-rendered HTML from our own
// origin (already escaped and secret-scrubbed) or inserted via textContent.
(function () {
  "use strict";

  var app = document.getElementById("app");
  var inspector = document.getElementById("inspector");
  var sheet = document.getElementById("sheet");
  var tabbar = document.getElementById("tabbar");
  var wide = window.matchMedia("(min-width: 900px)");
  var current = null;
  var stream = null;

  var SAFE_PATH = /^\/[A-Za-z0-9._~\/-]*$/;

  function body() {
    return wide.matches
      ? inspector.querySelector(".inspector-body")
      : sheet.querySelector(".sheet-body");
  }

  function setTitle(text) {
    var nodes = document.querySelectorAll("#inspector .title, #sheet .title");
    for (var i = 0; i < nodes.length; i++) nodes[i].textContent = text || "Detail";
  }

  function select(row) {
    var rows = document.querySelectorAll(".row.is-selected");
    for (var i = 0; i < rows.length; i++) rows[i].classList.remove("is-selected");
    if (row) row.classList.add("is-selected");
  }

  function open(path, row) {
    if (!SAFE_PATH.test(path)) return;
    var url = path + (path.indexOf("?") < 0 ? "?" : "&") + "partial=1";
    fetch(url, { headers: { Accept: "text/html" }, credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error(String(r.status));
        return r.text();
      })
      .then(function (html) {
        var target = body();
        target.innerHTML = html;
        var titled = target.querySelector("[data-title]");
        setTitle(titled ? titled.getAttribute("data-title") : "");
        if (wide.matches) {
          inspector.hidden = false;
          app.classList.add("has-inspector");
          inspector.scrollTop = 0;
        } else if (!sheet.open) {
          sheet.showModal();
          sheet.querySelector(".sheet-body").scrollTop = 0;
        }
        select(row);
        current = path;
        history.replaceState(null, "", location.pathname + location.search + "#" + path);
        startStream(target);
      })
      .catch(function () {
        // A failed partial falls back to the full page.
        location.href = path;
      });
  }

  function close() {
    stopStream();
    if (sheet && sheet.open) sheet.close();
    if (inspector) inspector.hidden = true;
    app.classList.remove("has-inspector");
    select(null);
    current = null;
    if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  }

  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-close]")) {
      e.preventDefault();
      close();
      return;
    }
    var link = e.target.closest("a[data-detail]");
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    open(link.getAttribute("href"), link.classList.contains("row") ? link : link.closest(".row"));
  });

  if (sheet) {
    sheet.addEventListener("click", function (e) {
      if (e.target === sheet) close();
    });
    sheet.addEventListener("close", function () {
      stopStream();
      select(null);
      current = null;
    });
  }

  // ---- keyboard ----

  function visibleRows() {
    var all = document.querySelectorAll("a.row[data-detail]");
    var out = [];
    for (var i = 0; i < all.length; i++) {
      if (!all[i].hidden && all[i].offsetParent !== null) out.push(all[i]);
    }
    return out;
  }

  function move(delta) {
    var rows = visibleRows();
    if (!rows.length) return;
    var index = -1;
    for (var i = 0; i < rows.length; i++) if (rows[i].classList.contains("is-selected")) index = i;
    var next = Math.max(0, Math.min(rows.length - 1, index + delta));
    select(rows[next]);
    rows[next].scrollIntoView({ block: "nearest" });
    if (wide.matches && app.classList.contains("has-inspector")) {
      open(rows[next].getAttribute("href"), rows[next]);
    }
  }

  document.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    var typing = tag === "input" || tag === "textarea" || tag === "select";
    var filter = document.getElementById("filter") || document.getElementById("filter-m");

    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
      var n = parseInt(e.key, 10);
      var screens = document.querySelectorAll("[data-screen]");
      if (n >= 1 && n <= screens.length) {
        e.preventDefault();
        location.href = screens[n - 1].getAttribute("href");
        return;
      }
      if (e.key === "f" || e.key === "F") {
        if (filter) {
          e.preventDefault();
          filter.focus();
          filter.select();
        }
        return;
      }
      return;
    }
    if (typing) {
      if (e.key === "Escape") {
        e.target.value = "";
        applyFilter("");
        e.target.blur();
      }
      return;
    }
    if (e.key === "Escape") {
      close();
      return;
    }
    if (e.key === "ArrowDown" || e.key === "j") {
      e.preventDefault();
      move(1);
      return;
    }
    if (e.key === "ArrowUp" || e.key === "k") {
      e.preventDefault();
      move(-1);
      return;
    }
    if (e.key === " " || e.key === "Enter") {
      var selected = document.querySelector("a.row.is-selected[data-detail]");
      if (selected) {
        e.preventDefault();
        open(selected.getAttribute("href"), selected);
      }
    }
  });

  // ---- filter (client side, current list only) ----

  function applyFilter(query) {
    var q = query.trim().toLowerCase();
    var items = document.querySelectorAll("[data-filter]");
    for (var i = 0; i < items.length; i++) {
      items[i].hidden = q !== "" && items[i].getAttribute("data-filter").toLowerCase().indexOf(q) < 0;
    }
    var groups = document.querySelectorAll(".group[data-filter-group]");
    for (var g = 0; g < groups.length; g++) {
      var rows = groups[g].querySelectorAll("[data-filter]");
      var anyVisible = false;
      for (var r = 0; r < rows.length; r++) if (!rows[r].hidden) anyVisible = true;
      groups[g].hidden = rows.length > 0 && !anyVisible;
    }
  }

  var filters = document.querySelectorAll("#filter, #filter-m");
  for (var f = 0; f < filters.length; f++) {
    filters[f].addEventListener("input", function (e) {
      applyFilter(e.target.value);
    });
  }

  // ---- tab bar minimise ----

  if (tabbar) {
    var lastY = window.scrollY;
    window.addEventListener(
      "scroll",
      function () {
        var y = window.scrollY;
        if (y > lastY + 8 && y > 96) tabbar.classList.add("is-min");
        else if (y < lastY - 8 || y < 48) tabbar.classList.remove("is-min");
        lastY = y;
      },
      { passive: true }
    );
  }

  // ---- agent timeline tail ----

  function stopStream() {
    if (stream) {
      stream.close();
      stream = null;
    }
  }

  function startStream(root) {
    stopStream();
    var host = (root || document).querySelector("[data-stream]");
    if (!host || typeof EventSource === "undefined") return;
    var tbody = host.querySelector("tbody");
    var streamPath = host.getAttribute("data-stream");
    if (!tbody || !SAFE_PATH.test(streamPath)) return;
    var scroller = host;
    scroller.scrollTop = scroller.scrollHeight;

    stream = new EventSource(streamPath);
    stream.onmessage = function (ev) {
      var d;
      try {
        d = JSON.parse(ev.data);
      } catch (_) {
        return;
      }
      var nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
      var tr = document.createElement("tr");
      tr.className = "is-new" + (d.is_error ? " is-error" : "");
      var what = document.createElement("td");
      what.className = "what";
      var chip = document.createElement("span");
      if (d.kind === "tool") {
        chip.className = "chip chip--tool";
        chip.textContent = d.tool_name || "tool";
        what.appendChild(chip);
      } else if (d.kind === "result") {
        chip.className = "chip chip--text";
        chip.textContent = "↳ " + (d.tool_name || "result");
        what.appendChild(chip);
      } else {
        chip.className = "chip chip--text";
        chip.textContent = "text";
        what.appendChild(chip);
      }
      var cells = [
        [d.at, "mono"],
        [d.content, "target"],
        [d.duration_seconds == null ? "" : d.duration_seconds + "s", "num"],
        [d.kind === "result" ? (d.is_error ? "error" : "ok") : "", ""],
      ];
      for (var i = 0; i < cells.length; i++) {
        var td = document.createElement("td");
        if (cells[i][1]) td.className = cells[i][1];
        var v = cells[i][0];
        td.textContent = v == null || v === "" ? "–" : String(v);
        tr.appendChild(td);
        if (i === 0) tr.appendChild(what);
      }
      tbody.appendChild(tr);
      if (nearBottom) scroller.scrollTop = scroller.scrollHeight;
    };
  }

  // ---- boot ----

  startStream(document);

  if (location.hash.length > 1) {
    var deep = location.hash.slice(1);
    if (SAFE_PATH.test(deep)) {
      var row = document.querySelector('a.row[data-detail][href="' + deep + '"]');
      open(deep, row);
    }
  }

  wide.addEventListener("change", function () {
    if (current) close();
  });
})();

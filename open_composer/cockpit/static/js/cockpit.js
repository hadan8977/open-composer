// The cockpit's only script. Five jobs, nothing else:
//   1. open a row's detail in the inspector (desktop) or a sheet (phone)
//      by fetching the same route with ?partial=1 -- no page navigation;
//   2. keyboard: ⌘1-6 screens, ⌘F filter, ↑/↓ select, Space/Enter open, Esc close;
//   3. the phone tab bar minimises while scrolling down;
//   4. the agent timeline tail (EventSource) appends rows with textContent;
//   5. the six screens are prefetched and switched in place (see "screens").
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
      if (n >= 1 && n <= screens.length) {
        e.preventDefault();
        go(screens[n - 1], "push");
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
    var lanes = document.querySelectorAll("details[data-lane]");
    for (var l = 0; l < lanes.length; l++) {
      if (q !== "") {
        if (!lanes[l].hasAttribute("data-was-open")) lanes[l].setAttribute("data-was-open", lanes[l].open ? "1" : "0");
        lanes[l].open = true;
      } else if (lanes[l].hasAttribute("data-was-open")) {
        lanes[l].open = lanes[l].getAttribute("data-was-open") === "1";
        lanes[l].removeAttribute("data-was-open");
      }
    }
    var items = document.querySelectorAll("[data-filter]");
    for (var i = 0; i < items.length; i++) {
      var miss = q !== "" && items[i].getAttribute("data-filter").toLowerCase().indexOf(q) < 0;
      // Graph nodes fade instead of vanishing so the shape of the graph stays readable.
      if (items[i].hasAttribute("data-dim")) items[i].classList.toggle("is-dim", miss);
      else items[i].hidden = miss;
    }
    var edges = document.querySelectorAll(".edge[data-a][data-b]");
    for (var e = 0; e < edges.length; e++) {
      var a = document.querySelector('[data-dim][data-id="' + edges[e].getAttribute("data-a") + '"]');
      var b = document.querySelector('[data-dim][data-id="' + edges[e].getAttribute("data-b") + '"]');
      var dim = (a && a.classList.contains("is-dim")) || (b && b.classList.contains("is-dim"));
      edges[e].classList.toggle("is-dim", !!dim);
    }
    var groups = document.querySelectorAll(".group[data-filter-group]");
    for (var g = 0; g < groups.length; g++) {
      var rows = groups[g].querySelectorAll("[data-filter]");
      var anyVisible = false;
      for (var r = 0; r < rows.length; r++) if (!rows[r].hidden) anyVisible = true;
      groups[g].hidden = rows.length > 0 && !anyVisible;
      var lane = groups[g].closest("details[data-lane]");
      if (lane) lane.hidden = groups[g].hidden;
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

  function setLive(on) {
    var badges = document.querySelectorAll("[data-live]");
    for (var i = 0; i < badges.length; i++) badges[i].hidden = !on;
  }

  function stopStream() {
    if (stream) {
      stream.close();
      stream = null;
    }
    setLive(false);
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
    stream.onopen = function () {
      setLive(true);
    };
    stream.onerror = function () {
      setLive(false);
    };
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

  // ---- screens: instant switching ----
  // The six screens are fetched in parallel right after first paint and kept
  // in memory, so tapping the rail or the tab bar swaps the content block in
  // place instead of reloading the whole page through the tunnel. A copy older
  // than FRESH_MS is refetched before it is shown (a thin progress line says
  // so); the rest are refreshed in the background after every switch. Tapping
  // the screen you are already on refetches it. Everything else -- detail
  // pages, /v2/, a session the edge has expired -- stays a normal navigation.

  var FRESH_MS = 120000;
  var screens = [];
  var pages = {};
  var inflight = {};
  var progress = null;

  (function () {
    var links = document.querySelectorAll("[data-screen]");
    for (var i = 0; i < links.length; i++) screens.push(links[i].getAttribute("href"));
  })();

  function isScreen(path) {
    return screens.indexOf(path) >= 0;
  }

  function fetchPage(path) {
    if (inflight[path]) return inflight[path];
    var p = fetch(path, { headers: { Accept: "text/html" }, credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok || r.redirected) throw new Error(String(r.status));
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        if (!doc.getElementById("content")) throw new Error("no content");
        pages[path] = { doc: doc, at: Date.now() };
        return pages[path];
      });
    inflight[path] = p;
    p.then(
      function () {
        delete inflight[path];
      },
      function () {
        delete inflight[path];
      }
    );
    return p;
  }

  function prefetchOthers(except) {
    for (var i = 0; i < screens.length; i++) {
      var path = screens[i];
      var have = pages[path];
      if (path === except || (have && Date.now() - have.at < FRESH_MS)) continue;
      fetchPage(path).catch(function () {});
    }
  }

  function showProgress() {
    if (!progress) {
      progress = document.createElement("div");
      progress.className = "progress";
      document.body.appendChild(progress);
    }
    progress.classList.add("is-on");
  }

  function hideProgress() {
    if (progress) progress.classList.remove("is-on");
  }

  function replaceStripItems(doc) {
    var strip = document.querySelector(".strip");
    var fresh = doc.querySelector(".strip");
    if (!strip || !fresh) return;
    var old = strip.querySelectorAll(".strip-item, .strip-spacer");
    for (var i = 0; i < old.length; i++) old[i].remove();
    var filter = document.getElementById("filter");
    var items = fresh.querySelectorAll(".strip-item, .strip-spacer");
    for (var j = 0; j < items.length; j++) strip.insertBefore(document.importNode(items[j], true), filter);
  }

  function setActive(path) {
    var links = document.querySelectorAll("[data-screen], #tabbar a");
    for (var i = 0; i < links.length; i++) {
      var on = links[i].getAttribute("href") === path;
      links[i].classList.toggle("is-active", on);
      if (!links[i].hasAttribute("data-screen")) continue;
      if (on) links[i].setAttribute("aria-current", "page");
      else links[i].removeAttribute("aria-current");
    }
  }

  function swap(path, page) {
    var doc = page.doc;
    var hash = location.hash;
    close();
    document.getElementById("content").innerHTML = doc.getElementById("content").innerHTML;
    document.title = doc.title;
    var brand = document.querySelector(".mobile-head .brand");
    var freshBrand = doc.querySelector(".mobile-head .brand");
    if (brand && freshBrand) brand.textContent = freshBrand.textContent;
    var foot = document.querySelector(".rail-foot");
    var freshFoot = doc.querySelector(".rail-foot");
    if (foot && freshFoot) {
      foot.innerHTML = freshFoot.innerHTML;
      foot.title = freshFoot.title;
    }
    replaceStripItems(doc);
    setActive(path);
    var filters = document.querySelectorAll("#filter, #filter-m");
    for (var i = 0; i < filters.length; i++) filters[i].value = "";
    if (tabbar) tabbar.classList.remove("is-min");
    window.scrollTo(0, 0);
    startStream(document);
    openDeep(hash);
  }

  function go(path, mode) {
    if (!isScreen(path)) {
      location.href = path;
      return;
    }
    var have = pages[path];
    var ready;
    if (have && have.doc && Date.now() - have.at < FRESH_MS) {
      ready = Promise.resolve(have);
    } else {
      showProgress();
      ready = fetchPage(path);
    }
    ready
      .then(function (page) {
        hideProgress();
        if (mode === "push") history.pushState({ screen: path }, "", path);
        else if (mode === "replace") history.replaceState({ screen: path }, "", path);
        var run = function () {
          swap(path, page);
        };
        if (document.startViewTransition) document.startViewTransition(run);
        else run();
        setTimeout(function () {
          prefetchOthers(path);
        }, 600);
      })
      .catch(function () {
        hideProgress();
        location.href = path;
      });
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    var a = e.target.closest("a[href]");
    if (!a || a.hasAttribute("data-detail") || a.getAttribute("target")) return;
    var href = a.getAttribute("href");
    if (!isScreen(href)) return;
    e.preventDefault();
    if (href === location.pathname) {
      // The screen you are on: fetch it again rather than trust the copy.
      pages[href] = null;
      go(href, "replace");
      return;
    }
    go(href, "push");
  });

  window.addEventListener("popstate", function () {
    if (isScreen(location.pathname)) go(location.pathname, "pop");
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") return;
    var here = location.pathname;
    if (!isScreen(here) || current) return;
    var have = pages[here];
    if (have && Date.now() - have.at < FRESH_MS) return;
    fetchPage(here)
      .then(function (page) {
        if (location.pathname === here && !current) swap(here, page);
      })
      .catch(function () {});
    prefetchOthers(here);
  });

  // ---- boot ----

  function openDeep(hash) {
    var h = hash == null ? location.hash : hash;
    if (h.length < 2) return;
    var deep = h.slice(1);
    if (!SAFE_PATH.test(deep)) return;
    var row = document.querySelector('a.row[data-detail][href="' + deep + '"]');
    open(deep, row);
  }

  startStream(document);
  openDeep();

  if (isScreen(location.pathname)) {
    pages[location.pathname] = { doc: null, at: Date.now() };
    setTimeout(function () {
      prefetchOthers(location.pathname);
    }, 300);
  } else {
    setTimeout(function () {
      prefetchOthers(null);
    }, 1200);
  }

  wide.addEventListener("change", function () {
    if (current) close();
  });
})();

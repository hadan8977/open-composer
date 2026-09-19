// Collapses the persistent top bar into a single icon row on narrow
// viewports; the CSS breakpoint in cockpit.css hides `.topbar-nav` and
// `.topbar-status` below 640px unless `.topbar` also has `.is-expanded`.
// No framework, no build step, no network calls -- this file is the entire
// client-side behavior of the cockpit.
(function () {
  "use strict";

  var toggle = document.getElementById("topbar-toggle");
  var topbar = toggle ? toggle.closest(".topbar") : null;

  if (!toggle || !topbar) {
    return;
  }

  toggle.addEventListener("click", function () {
    var expanded = topbar.classList.toggle("is-expanded");
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  });
})();

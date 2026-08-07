// ============================================================================
// Charts module — vanilla JS (no dependencies).
// Renders the analytics bar chart (data-mf-chart="bars" + data-mf-bars) and
// the unread distribution donut (data-mf-donut) on the analytics page.
// ============================================================================

(function () {
  "use strict";

  function parseJson(attr) {
    if (!attr) return null;
    try {
      return JSON.parse(attr.replace(/'/g, '"'));
    } catch (e) {
      return null;
    }
  }

  function renderBars(container) {
    if (!container) return;
    var data = parseJson(container.dataset.mfBars);
    if (!data || !data.length) return;
    var html = "";
    for (var i = 0; i < data.length; i++) {
      html += '<div class="bar" style="height: ' + data[i] + '%"></div>';
    }
    container.innerHTML = html;
  }

  function renderDonut(container) {
    if (!container) return;
    var data = parseJson(container.dataset.mfDonut);
    if (!data || !data.length) return;

    var total = 0;
    var i;
    for (i = 0; i < data.length; i++) total += Number(data[i].value) || 0;
    if (!total) return;

    var colors = [];
    for (i = 0; i < data.length; i++) colors.push(data[i].color || "#2563EB");

    var stops = [];
    var running = 0;
    for (i = 0; i < data.length; i++) {
      var share = ((Number(data[i].value) || 0) / total) * 360;
      stops.push(colors[i] + " " + running + "deg " + (running + share) + "deg");
      running += share;
    }
    container.style.background =
      "conic-gradient(" + stops.join(", ") + ")";
  }

  function init() {
    document.querySelectorAll('[data-mf-chart="bars"]').forEach(renderBars);
    document.querySelectorAll("[data-mf-donut]").forEach(renderDonut);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
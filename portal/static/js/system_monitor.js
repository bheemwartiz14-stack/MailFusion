// System Monitor — tabbed dashboard, Chart.js activity chart, range/log tabs,
// auto-refresh, live feed animation, and HTMX re-initialisation on swaps.
(function () {
  'use strict';

  var chart = null;
  var currentRange = '24h';

  function readChartData() {
    var el = document.getElementById('sys-chart-data');
    if (!el) return null;
    try { return JSON.parse(el.textContent.trim()); } catch (e) { return null; }
  }

  function buildChart() {
    var data = readChartData();
    var canvas = document.getElementById('sys-activity-chart');
    if (!data || !canvas || !window.Chart) return;
    // Only build when the container is actually visible (Chart needs a size).
    if (canvas.offsetParent === null) return;

    var series = data[currentRange] || data['24h'] || { labels: [], success: [], processing: [], failed: [] };
    var tick = '#64748b';
    var gridC = 'rgba(100,116,139,0.14)';

    var config = {
      type: 'line',
      data: {
        labels: series.labels,
        datasets: [
          { label: 'Success', data: series.success, borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.10)', tension: 0.4, fill: true, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4 },
          { label: 'Processing', data: series.processing, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)', tension: 0.4, fill: true, borderWidth: 2, pointHoverRadius: 4, borderDash: [4, 3] },
          { label: 'Failed', data: series.failed, borderColor: '#f43f5e', backgroundColor: 'rgba(244,63,94,0.08)', tension: 0.4, fill: true, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0f172a', titleColor: '#f1f5f9', bodyColor: '#cbd5e1',
            padding: 12, cornerRadius: 10, boxPadding: 4,
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: tick, maxTicksLimit: 8, maxRotation: 0 } },
          y: { beginAtZero: true, grace: 1, grid: { color: gridC }, ticks: { color: tick, precision: 0 } },
        },
      },
    };

    if (chart) chart.destroy();
    chart = new Chart(canvas.getContext('2d'), config);
  }

  function paintRangeButtons() {
    document.querySelectorAll('[data-sys-range] [data-range]').forEach(function (btn) {
      var on = btn.dataset.range === currentRange;
      btn.classList.toggle('bg-primary', on);
      btn.classList.toggle('text-white', on);
      btn.classList.toggle('text-on-surface-variant', !on);
    });
  }

  function initChart() {
    paintRangeButtons();
    document.querySelectorAll('[data-sys-range] [data-range]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        currentRange = btn.dataset.range;
        paintRangeButtons();
        buildChart();
      });
    });
  }

  // ---- Main tabs -----------------------------------------------------------
  function activateTab(name) {
    document.querySelectorAll('[data-sys-tab]').forEach(function (t) {
      var on = t.dataset.sysTab === name;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      if (on) t.tabIndex = 0; else t.tabIndex = -1;
    });
    document.querySelectorAll('[data-sys-panel]').forEach(function (p) {
      p.classList.toggle('hidden', p.dataset.sysPanel !== name);
    });
    localStorage.setItem('sysmon-tab', name);
    buildChart(); // chart only exists in the visible Sync tab
  }

  function initTabs() {
    var tabs = document.querySelectorAll('[data-sys-tab]');
    if (!tabs.length) return;
    var saved = localStorage.getItem('sysmon-tab') || 'overview';
    if (!document.querySelector('[data-sys-tab="' + saved + '"]')) saved = 'overview';
    activateTabShown(saved);
    tabs.forEach(function (t) {
      t.addEventListener('click', function () { activateTab(t.dataset.sysTab); });
    });
  }

  // Reveal the saved tab without rebuilding the chart twice.
  function activateTabShown(name) {
    document.querySelectorAll('[data-sys-tab]').forEach(function (t) {
      var on = t.dataset.sysTab === name;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    document.querySelectorAll('[data-sys-panel]').forEach(function (p) {
      p.classList.toggle('hidden', p.dataset.sysPanel !== name);
    });
  }

  function paintLogTab(active) {
    document.querySelectorAll('[data-log-tab]').forEach(function (tab) {
      var on = tab.dataset.logTab === active;
      tab.classList.toggle('bg-primary', on);
      tab.classList.toggle('text-white', on);
      tab.classList.toggle('text-on-surface-variant', !on);
    });
  }

  function initLogTabs() {
    var tabs = document.querySelectorAll('[data-log-tab]');
    if (!tabs.length) return;
    var active = (document.querySelector('.sys-log-tab.active') || tabs[0]).dataset.logTab;
    paintLogTab(active);
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () { paintLogTab(tab.dataset.logTab); });
    });

    var search = document.querySelector('[data-sys-log-search]');
    if (search) {
      search.addEventListener('input', function () {
        var q = search.value.toLowerCase();
        document.querySelectorAll('[data-sys-log-body] tr').forEach(function (row) {
          row.style.display = row.textContent.toLowerCase().indexOf(q) === -1 ? 'none' : '';
        });
      });
    }
  }

  function animateFeed() {
    var feed = document.querySelector('[data-sys-feed]');
    if (!feed || feed.children.length < 2) return;
    setInterval(function () {
      var first = feed.firstElementChild;
      if (first) { feed.removeChild(first); feed.appendChild(first); }
    }, 3500);
  }

  function initAutoRefresh(container) {
    var btn = document.querySelector('[data-sys-auto]');
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.dataset.enabled = '1';
    var icon = btn.querySelector('i');
    btn.addEventListener('click', function () {
      var enabled = btn.dataset.enabled === '1';
      btn.dataset.enabled = enabled ? '0' : '1';
      btn.setAttribute('aria-pressed', String(!enabled));
      container.setAttribute('hx-trigger', enabled ? 'none' : 'every 30s');
      if (icon) icon.classList.toggle('text-success', enabled);
    });
  }

  function initRefreshNow(container) {
    var btn = document.querySelector('[data-refresh-monitor]');
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', function () {
      if (window.htmx && htmx.trigger) htmx.trigger(container, 'refresh');
    });
  }

  function lucide() {
    if (window.lucide && lucide.createIcons) { try { lucide.createIcons(); } catch (e) {} }
  }

  function reinit() {
    lucide();
    initTabs();
    initChart();
    initLogTabs();
    animateFeed();
  }

  function boot() {
    var container = document.getElementById('system-monitor');
    initTabs();
    initChart();
    initLogTabs();
    initAutoRefresh(container);
    initRefreshNow(container);
    animateFeed();

    if (container) {
      container.addEventListener('htmx:afterSwap', function () {
        requestAnimationFrame(reinit);
      });
    }
  }

  function domReady() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { requestAnimationFrame(boot); });
    } else {
      requestAnimationFrame(boot);
    }
  }

  domReady();
})();
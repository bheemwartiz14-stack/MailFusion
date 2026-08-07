// ============================================================================
// Tables module — vanilla JS (no dependencies).
// Powers data-mf-table-search, data-mf-table-filter, data-mf-select-all,
// data-mf-row-check and data-mf-require-check behaviours across list pages.
// ============================================================================

(function () {
  "use strict";

  function tableFor(id) {
    return document.getElementById(id);
  }

  function rowsOf(table) {
    return table ? Array.prototype.slice.call(table.querySelectorAll("tbody tr")) : [];
  }

  function rowChecks(table) {
    return rowsOf(table)
      .map((r) => r.querySelector("[data-mf-row-check]"))
      .filter(Boolean);
  }

  function applySearch(table, query) {
    if (!table) return;
    const q = (query || "").toLowerCase().trim();
    rowsOf(table).forEach(function (row) {
      row.style.display = !q || row.textContent.toLowerCase().indexOf(q) !== -1 ? "" : "none";
    });
  }

  function applyFilter(table, filter, keyAttr) {
    if (!table) return;
    const value = filter ? filter.value : "";
    const attr = keyAttr || "data-status";
    rowsOf(table).forEach(function (row) {
      row.style.display = !value || row.getAttribute(attr) === value ? "" : "none";
    });
  }

  function syncSelectAll(table) {
    if (!table) return;
    const checks = rowChecks(table);
    const all = table.querySelector("[data-mf-select-all]");
    if (!all || checks.length === 0) return;
    all.checked = checks.every((c) => c.checked);
    all.indeterminate = !all.checked && checks.some((c) => c.checked);
  }

  function syncRequireCheck() {
    document.querySelectorAll("[data-mf-require-check]").forEach(function (el) {
      const table = el.closest("table");
      const scope = table || document;
      const anyChecked = rowsOf(scope).some(function (r) {
        const c = r.querySelector("input[type='checkbox']");
        return c && c.checked;
      });
      if (el.tagName === "BUTTON") {
        el.disabled = !anyChecked;
        el.classList.toggle("disabled", !anyChecked);
      }
    });
  }

  function initSearch() {
    document.querySelectorAll("[data-mf-table-search]").forEach(function (input) {
      input.addEventListener("input", function () {
        applySearch(tableFor(input.dataset.mfTableSearch), input.value);
      });
    });
  }

  function initFilter() {
    document.querySelectorAll("[data-mf-table-filter]").forEach(function (select) {
      select.addEventListener("change", function () {
        applyFilter(tableFor(select.dataset.mfTableFilter), select, select.dataset.mfFilterKey);
      });
    });
  }

  function initRowCheck() {
    document.querySelectorAll("[data-mf-row-check]").forEach(function (checkbox) {
      checkbox.addEventListener("change", function () {
        const table = checkbox.closest("table");
        if (table) syncSelectAll(table);
        syncRequireCheck();
      });
    });
  }

  function initSelectAll() {
    document.querySelectorAll("[data-mf-select-all]").forEach(function (all) {
      all.addEventListener("change", function () {
        const table = all.closest("table");
        if (!table) return;
        const checks = rowChecks(table);
        checks.forEach((c) => (c.checked = all.checked));
        syncRequireCheck();
      });
    });
  }

  function init() {
    initSearch();
    initFilter();
    initRowCheck();
    initSelectAll();
    syncRequireCheck();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
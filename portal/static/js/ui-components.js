// Tailwind UI Components - Replaces Bootstrap
// Custom modal, toast, and dropdown components

class Modal {
  constructor(element) {
    this.element = element;
    this.backdrop = document.createElement('div');
    this.backdrop.className = 'fixed inset-0 z-50 bg-black/40 hidden';
    document.body.appendChild(this.backdrop);

    this.isOpen = false;
    this.onClose = null;

    this.backdrop.addEventListener('click', () => this.close());

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.isOpen) {
        e.preventDefault();
        this.close();
      }
    });
  }

  show() {
    this.element.classList.remove('hidden');
    this.backdrop.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    this.isOpen = true;

    const focusableElement = this.element.querySelector('button, input, a, select, textarea');
    if (focusableElement) {
      setTimeout(() => focusableElement.focus(), 100);
    }
  }

  hide() {
    this.element.classList.add('hidden');
    this.backdrop.classList.add('hidden');
    document.body.style.overflow = '';
    this.isOpen = false;

    if (this.onClose) {
      this.onClose();
    }
  }

  close() {
    this.hide();
  }

  toggle() {
    if (this.isOpen) {
      this.hide();
    } else {
      this.show();
    }
  }
}

class Toast {
  constructor(message, type = 'info', delay = 4000) {
    this.delay = delay;
    this.toast = document.createElement('div');
    this.toast.className = `mb-3 rounded-lg border border-white/20 bg-slate-900 px-4 py-3 text-sm font-medium text-white shadow-lg ${this.getTypeClass(type)}`;
    this.toast.setAttribute('role', 'alert');
    this.toast.setAttribute('aria-live', 'assertive');
    this.toast.setAttribute('aria-atomic', 'true');

    this.toast.innerHTML = `
      <div class="flex items-center gap-3">
        <div>${message}</div>
        <button type="button" class="ml-auto text-white/80 transition hover:text-white" aria-label="Close">×</button>
      </div>
    `;

    this.closeBtn = this.toast.querySelector('button');
    this.timeout = null;

    this.closeBtn.addEventListener('click', () => this.close());
  }

  getTypeClass(type) {
    const types = {
      success: 'bg-emerald-600',
      error: 'bg-rose-600',
      warning: 'bg-amber-600',
      info: 'bg-slate-900'
    };
    return types[type] || types.info;
  }

  show(container = document.getElementById('accounts-toast') || document.body) {
    if (!container) {
      console.error('Toast container not found');
      return;
    }

    container.appendChild(this.toast);
    this.timeout = setTimeout(() => this.close(), this.delay);
  }

  close() {
    if (this.timeout) {
      clearTimeout(this.timeout);
    }

    if (this.toast.parentNode) {
      this.toast.remove();
    }
  }
}

class Dropdown {
  constructor(trigger) {
    this.trigger = trigger;
    this.dropdown = trigger.nextElementSibling;

    if (!this.dropdown || !this.dropdown.dataset.mfMenu) {
      return;
    }

    this.isOpen = false;

    this.trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      this.toggle();
    });

    document.addEventListener('click', () => this.hide());
  }

  show() {
    this.dropdown.classList.remove('hidden');
    this.dropdown.classList.add('block');
    this.isOpen = true;
  }

  hide() {
    this.dropdown.classList.add('hidden');
    this.dropdown.classList.remove('block');
    this.isOpen = false;
  }

  toggle() {
    if (this.isOpen) {
      this.hide();
    } else {
      this.show();
    }
  }
}

window.Modal = Modal;
window.Toast = Toast;
window.Dropdown = Dropdown;

function initDropdowns() {
  document.querySelectorAll('[data-mf-menu-trigger]').forEach(trigger => {
    new Dropdown(trigger);
  });
}

function initModals() {
  document.querySelectorAll('[data-mf-modal]').forEach(modalEl => {
    new Modal(modalEl);
  });
}

function initToasts() {
  document.querySelectorAll('[data-toast]').forEach(toastEl => {
    new Toast(toastEl.textContent).show();
  });
}

function initSidebar() {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');

  const open = () => {
    if (!sidebar || !backdrop) return;
    sidebar.classList.remove('max-lg:-translate-x-full');
    sidebar.classList.add('max-lg:translate-x-0');
    backdrop.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  };

  const close = () => {
    if (!sidebar || !backdrop) return;
    sidebar.classList.add('max-lg:-translate-x-full');
    sidebar.classList.remove('max-lg:translate-x-0');
    backdrop.classList.add('hidden');
    document.body.style.overflow = '';
  };

  document.querySelectorAll('[data-mf-open-sidebar]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      open();
    });
  });
  document.querySelectorAll('[data-mf-close-sidebar]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      close();
    });
  });
  if (backdrop) backdrop.addEventListener('click', close);
  window.addEventListener('resize', () => {
    if (window.innerWidth >= 1024) close();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initDropdowns();
  initModals();
  initSidebar();

  document.body.addEventListener('htmx:afterRequest', function (e) {
    if (e.detail.target.id === 'accounts-toast' && e.detail.successful) {
      const toast = new Toast(e.detail.xhr.responseText, 'success', 4000);
      toast.show();
    }
  });
});

// ---------------------------------------------------------------------------
// Trigger a manual sync (accounts page) via AJAX and surface the result as a
// toast, then refresh so the "Last sync" column stays in sync.
// Usage: <button data-mf-sync="{url}" data-mf-sync-name="{Account name}"> or
//        <button data-mf-sync-all="{url}">
// ---------------------------------------------------------------------------
document.addEventListener('click', function (e) {
  const btn = e.target.closest('[data-mf-sync], [data-mf-sync-all]');
  if (!btn) return;
  e.preventDefault();
  if (btn.disabled) return;

  const url = btn.getAttribute('data-mf-sync') || btn.getAttribute('data-mf-sync-all');
  const label = btn.getAttribute('data-mf-sync-name') || 'Sync';
  const original = btn.innerHTML;

  btn.disabled = true;
  btn.classList.add('opacity-60', 'pointer-events-none');
  new Toast(`Syncing ${label}…`, 'info', 2500).show();

  fetch(url, {
    method: 'POST',
    headers: {
      'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
    }
  })
    .then(async (res) => {
      const text = await res.text().catch(() => '');
      const msg = (text.trim() && !text.toLowerCase().includes('<html')) ? text.trim() : 'Sync complete';
      if (res.ok) {
        new Toast(msg, 'success').show();
        return res.ok;
      }
      new Toast('Sync failed: ' + res.status, 'error').show();
      return false;
    })
    .catch(() => new Toast('Sync failed. Check your connection.', 'error').show())
    .finally(() => {
      btn.disabled = false;
      btn.classList.remove('opacity-60', 'pointer-events-none');
      // Model, refresh Last Sync + unread after a beat.
      setTimeout(() => window.location.reload(), 900);
    });
});

// ---------------------------------------------------------------------------
// Inbox module (was inbox.js) — selection, bulk actions, composer modal.
// ---------------------------------------------------------------------------
(function () {
  'use strict';
  const state = { selected: new Set(), bulkVisible: false };
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function getSelectedEl() { return $('[data-mf-selected-count]'); }
  function getBulkBar() { return $('[data-mf-bulk-bar]'); }
  function bulkForm() { return $('[data-mf-bulk-form]'); }

  function refreshUI() {
    const count = state.selected.size;
    const selectedEl = getSelectedEl();
    const bar = getBulkBar();
    if (selectedEl) selectedEl.textContent = String(count);
    if (bar) bar.classList.toggle('hidden', count === 0);
    $$('[data-mf-email]').forEach((row) => {
      const pk = row.dataset.mfEmail || '';
      const check = row.querySelector('[data-mf-email-check]');
      if (check) check.checked = state.selected.has(pk);
      row.classList.toggle('selected', state.selected.has(pk));
    });
    const selectAll = $('[data-mf-select-all]');
    if (selectAll) {
      const checks = $$('[data-mf-email-check]');
      const allChecked = checks.length > 0 && checks.every((c) => c.checked);
      selectAll.checked = allChecked;
      selectAll.indeterminate = !allChecked && state.selected.size > 0;
    }
  }

  function showToast(message, type = 'success') {
    const tone = type === 'error' ? 'bg-rose-600' : type === 'warning' ? 'bg-amber-600' : 'bg-emerald-600';
    if (window.Toast) {
      new window.Toast(message, type === 'error' ? 'error' : type === 'warning' ? 'warning' : 'success').show();
      return;
    }
    const toast = document.createElement('div');
    toast.className = `fixed bottom-4 right-4 z-[60] rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${tone}`;
    toast.setAttribute('role', 'alert');
    toast.textContent = message;
    (document.getElementById('mf-toast-container') || document.body).appendChild(toast);
    window.setTimeout(() => toast.remove(), 3000);
  }

  function toggleBulkDropdown(button) {
    const container = button.parentElement;
    const menu = container && container.nextElementSibling;
    if (menu && menu.dataset.mfBulkMenu) menu.classList.toggle('hidden');
  }

  function executeBulkAction(action) {
    if (!action || state.selected.size === 0) return;
    const form = bulkForm();
    if (!form) return;
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'action';
    input.value = action;
    form.appendChild(input);
    showToast(`${action} ${state.selected.size} email(s)`);
    const done = () => { input.remove(); state.selected.clear(); refreshUI(); };
    const htmx = window.htmx;
    if (htmx && typeof htmx.ajax === 'function') {
      htmx.ajax('POST', form.getAttribute('action'), form).then(done, done);
    } else {
      form.submit();
      done();
    }
  }

  function openComposer() {
    const modal = document.getElementById('mfComposeModal');
    if (modal) { modal.classList.remove('hidden'); return; }
    const host = document.getElementById('mf-compose-modal-host');
    const htmx = window.htmx;
    if (host && htmx && typeof htmx.ajax === 'function') {
      htmx.ajax('GET', '/inbox/compose/modal/', { target: host, swap: 'innerHTML' });
    }
  }

  function initInbox() {
    refreshUI();
    document.addEventListener('click', (e) => {
      const check = e.target.closest('[data-mf-email-check]');
      if (check) {
        const pk = check.value || '';
        if (state.selected.has(pk)) state.selected.delete(pk); else state.selected.add(pk);
        refreshUI();
        return;
      }
      const selectAll = e.target.closest('[data-mf-select-all]');
      if (selectAll) {
        const checks = $$('[data-mf-email-check]');
        const all = checks.length > 0 && checks.every((c) => c.checked);
        if (all) state.selected.clear();
        else checks.forEach((c) => state.selected.add(c.value));
        refreshUI();
        return;
      }
      const bulkBtn = e.target.closest('[data-mf-bulk-dropdown]');
      if (bulkBtn) { toggleBulkDropdown(bulkBtn); return; }
      const actionEl = e.target.closest('[data-mf-bulk-action]');
      if (actionEl) { e.preventDefault(); executeBulkAction(actionEl.dataset.mfBulkAction || ''); return; }
      if (e.target.closest('[data-mf-open-compose]')) { openComposer(); return; }
    });
    document.addEventListener('keydown', (e) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && state.selected.size > 0) {
        e.preventDefault();
        executeBulkAction('trash');
      }
    });
    document.addEventListener('htmx:afterSwap', (e) => {
      const t = e.detail && e.detail.target;
      if (t && t.id === 'mf-email-list') refreshUI();
    });
  }

  window.InboxFusion = window.InboxFusion || {};
  window.InboxFusion.inbox = { init: initInbox, openComposer, refreshUI, showToast };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initInbox);
  else initInbox();
})();

// ---------------------------------------------------------------------------
// Compose module (was compose.js) — editor toolbar, dropzone, bcc/discard.
// ---------------------------------------------------------------------------
(function () {
  'use strict';
  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function syncEditorToForm(form) {
    const editor = form.querySelector('[data-mf-editor]');
    const htmlInput = form.querySelector('[data-mf-body-html]');
    const textInput = form.querySelector('[data-mf-body-text]');
    if (!editor || (!htmlInput && !textInput)) return;
    if (htmlInput) htmlInput.value = editor.innerHTML;
    if (textInput) textInput.value = editor.innerText || '';
  }

  function updateAutosaveStatus(form, saving) {
    const status = form.querySelector('[data-mf-autosave-status]');
    if (!status) return;
    status.textContent = saving ? 'Saving…' : 'Draft saved';
    status.classList.toggle('text-primary', saving);
    status.classList.toggle('text-on-surface-variant', !saving);
  }

  function setupEditorToolbar(form) {
    const toolbar = form.querySelector('[data-mf-editor-toolbar]');
    const editor = form.querySelector('[data-mf-editor]');
    if (!toolbar || !editor || !document.execCommand) return;
    toolbar.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-mf-cmd]');
      if (!btn) return;
      e.preventDefault();
      editor.focus();
      const cmd = btn.dataset.mfCmd;
      if (cmd) document.execCommand(cmd, false, null);
    });
  }

  function setupDropzone(form) {
    const dropzone = form.querySelector('[data-mf-dropzone]');
    const fileInput = form.querySelector('[data-mf-file-input]');
    if (!dropzone) return;
    const highlight = () => dropzone.classList.add('!border-primary', 'bg-primary-soft');
    const unhighlight = () => dropzone.classList.remove('!border-primary', 'bg-primary-soft');
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); highlight(); });
    dropzone.addEventListener('dragleave', (e) => { e.preventDefault(); unhighlight(); });
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      unhighlight();
      if (fileInput && e.dataTransfer && e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
      }
    });
  }

  function setupAutosave(form) {
    let timer;
    form.querySelectorAll('[data-mf-subject], [data-mf-editor], [data-mf-recipient]').forEach((el) => {
      el.addEventListener('input', () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => updateAutosaveStatus(form, false), 2000);
      });
    });
  }

  function bccLinkHandler(form, trigger) {
    if (!trigger) return;
    trigger.addEventListener('click', (e) => {
      e.preventDefault();
      const row = form.querySelector('[data-mf-bcc-row]');
      if (row) row.style.display = row.style.display === 'none' || !row.style.display ? 'block' : 'none';
    });
  }

  function initCompose() {
    document.querySelectorAll('[data-mf-compose-form]').forEach((form) => {
      setupEditorToolbar(form);
      setupDropzone(form);
      setupAutosave(form);
      form.addEventListener('submit', () => syncEditorToForm(form));
      bccHandler(form, form.querySelector('[data-mf-show-cc-bcc]'));
      const discard = form.querySelector('[data-mf-discard]');
      if (discard) discard.addEventListener('click', (e) => {
        if (form.hasAttribute('data-mf-dirty') && !window.confirm('Discard this message? Unsaved changes will be lost.')) {
          e.preventDefault();
        }
      });
    });
  }

  window.InboxFusion = window.InboxFusion || {};
  window.InboxFusion.compose = { init: initCompose };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initCompose);
  else initCompose();
})();
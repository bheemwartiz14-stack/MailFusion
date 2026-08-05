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

document.addEventListener('DOMContentLoaded', () => {
  initDropdowns();
  initModals();

  document.body.addEventListener('htmx:afterRequest', function (e) {
    if (e.detail.target.id === 'accounts-toast' && e.detail.successful) {
      const toast = new Toast(e.detail.xhr.responseText, 'success', 4000);
      toast.show();
    }
  });
});
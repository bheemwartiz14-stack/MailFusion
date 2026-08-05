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
    this.toast = document.createElement('div');
    this.toast.className = `toast align-items-center text-white border-0 shadow-lg mb-3 p-3 rounded-lg ${this.getTypeClass(type)}`;
    this.toast.setAttribute('role', 'alert');
    this.toast.setAttribute('aria-live', 'assertive');
    this.toast.setAttribute('aria-atomic', 'true');
    
    this.toast.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" aria-label="Close"></button>
      </div>
    `;
    
    this.closeBtn = this.toast.querySelector('.btn-close');
    this.timeout = null;
    
    this.closeBtn.addEventListener('click', () => this.close());
  }
  
  getTypeClass(type) {
    const types = {
      'success': 'bg-success',
      'error': 'bg-error',
      'warning': 'bg-warning',
      'info': 'bg-primary'
    };
    return types[type] || types['info'];
  }
  
  show(container = document.getElementById('accounts-toast') || document.body) {
    if (!container) {
      console.error('Toast container not found');
      return;
    }
    
    container.appendChild(this.toast);
    
    const bsToast = new bootstrap.Toast(this.toast, { delay: this.delay });
    bsToast.show();
    
    this.timeout = setTimeout(() => this.close(), this.delay);
    
    this.toast.addEventListener('hidden.bs.toast', () => {
      this.toast.remove();
    });
  }
  
  close() {
    if (this.timeout) {
      clearTimeout(this.timeout);
    }
    
    if (this.toast.parentNode) {
      const bsToast = bootstrap.Toast.getInstance(this.toast);
      if (bsToast) {
        bsToast.hide();
      }
    }
  }
}

class Dropdown {
  constructor(trigger) {
    this.trigger = trigger;
    this.dropdown = trigger.nextElementSibling;
    
    if (!this.dropdown || !this.dropdown.classList.contains('dropdown-menu')) {
      return;
    }
    
    this.isOpen = false;
    
    this.trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      this.toggle();
    });
  }
  
  show() {
    this.dropdown.classList.remove('hidden', 'opacity-0', 'invisible');
    this.dropdown.classList.add('block', 'opacity-100', 'visible');
    this.isOpen = true;
  }
  
  hide() {
    this.dropdown.classList.add('hidden', 'opacity-0', 'invisible');
    this.dropdown.classList.remove('block', 'opacity-100', 'visible');
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

// Initialize all dropdowns
function initDropdowns() {
  document.querySelectorAll('[data-dropdown]').forEach(trigger => {
    new Dropdown(trigger);
  });
}

// Initialize modals
function initModals() {
  document.querySelectorAll('[data-modal]').forEach(modalEl => {
    new Modal(modalEl);
  });
}

// Initialize toasts
function initToasts() {
  document.querySelectorAll('[data-toast]').forEach(toastEl => {
    new Toast(toastEl.textContent).show();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initDropdowns();
  initModals();
  
  // Handle HTMX events
  document.body.addEventListener('htmx:afterRequest', function(e) {
    if (e.detail.target.id === 'accounts-toast' && e.detail.successful) {
      const toast = new Toast(e.detail.xhr.responseText, 'success', 4000);
      toast.show();
    }
  });
});
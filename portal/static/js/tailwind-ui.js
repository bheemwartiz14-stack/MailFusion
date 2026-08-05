import "tailwindcss/browser";

// Initialize Alpine.js if available
if (typeof Alpine === 'undefined') {
  window.Alpine = {
    start: () => {},
    directive: (name, callback) => {},
    store: (name, initial) => initial,
    effect: (callback) => callback
  };
}

// Custom dropdown component
window.Dropdown = {
  init(el) {
    this.el = el;
    this.menu = el.nextElementSibling;
    this.isOpen = false;
    
    if (!this.menu || !this.menu.classList.contains('custom-dropdown')) {
      return;
    }
    
    this.el.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle();
    });
  },
  
  show() {
    this.menu.classList.remove('hidden', 'opacity-0', 'invisible');
    this.menu.classList.add('block', 'opacity-100', 'visible');
    this.isOpen = true;
  },
  
  hide() {
    this.menu.classList.add('hidden', 'opacity-0', 'invisible');
    this.menu.classList.remove('block', 'opacity-100', 'visible');
    this.isOpen = false;
  },
  
  toggle() {
    if (this.isOpen) {
      this.hide();
    } else {
      this.show();
    }
  }
};

window.Alpine.directive('dropdown', window.Dropdown);

window.Alpine.directive('modal', (el, { expression }, { effect, evaluate }) => {
  el.classList.add('modal-container');
  
  const toggleModal = (show) => {
    if (show) {
      el.classList.remove('hidden');
      document.body.style.overflow = 'hidden';
    } else {
      el.classList.add('hidden');
      document.body.style.overflow = '';
    }
  };
  
  el.addEventListener('click', (e) => {
    if (e.target === el || e.target.hasAttribute('data-close')) {
      toggleModal(false);
    }
  });
  
  effect(() => {
    const isOpen = evaluate(expression);
    toggleModal(isOpen);
  });
});
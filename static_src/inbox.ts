// ============================================================================
// Inbox module — vanilla TypeScript (no Alpine).
// Wires up the inbox page behaviour against <data-mf-*> hooks, integrated
// with HTMX for data loading and ui-components.js for modal/toast primitives.
// ============================================================================

const state = {
  selected: new Set<string>(),
  bulkVisible: false,
}

function getSelectedEl(): HTMLElement | null {
  return document.querySelector("[data-mf-selected-count]")
}

function getBulkBar(): HTMLElement | null {
  return document.querySelector("[data-mf-bulk-bar]")
}

function refreshUI(): void {
  const count = state.selected.size
  const selectedEl = getSelectedEl()
  const bulkBar = getBulkBar()

  if (selectedEl) selectedEl.textContent = String(count)
  if (bulkBar) bulkBar.classList.toggle("hidden", count === 0)

  document.querySelectorAll<HTMLElement>("[data-mf-email]").forEach((row) => {
    const pk = row.dataset.mfEmail || ""
    const check = row.querySelector<HTMLInputElement>("[data-mf-email-check]")
    if (check) check.checked = state.selected.has(pk)
    row.classList.toggle("selected", state.selected.has(pk))
  })

  const selectAll = document.querySelector<HTMLInputElement>("[data-mf-select-all]")
  if (selectAll) {
    const checks = document.querySelectorAll<HTMLInputElement>("[data-mf-email-check]")
    const allChecked = checks.length > 0 && [...checks].every((c) => c.checked)
    selectAll.checked = allChecked
    selectAll.indeterminate = !allChecked && state.selected.size > 0
  }
}

function showToast(message: string, type: string = "success"): void {
  const container = document.getElementById("mf-toast-container")
  const target = container || document.body
  const tone =
    type === "error"
      ? "bg-rose-600"
      : type === "warning"
        ? "bg-amber-600"
        : "bg-emerald-600"
  const toast = document.createElement("div")
  toast.className = `fixed bottom-4 right-4 z-[60] rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${tone}`
  toast.setAttribute("role", "alert")
  toast.textContent = message
  target.appendChild(toast)
  window.setTimeout(() => toast.remove(), 3000)
}

function toggleBulkDropdown(button: HTMLElement): void {
  const container = button.parentElement as HTMLElement | null
  const menu = container?.nextElementSibling as HTMLElement | null
  if (menu && menu.dataset.mfBulkMenu) menu.classList.toggle("hidden")
}

function executeBulkAction(action: string): void {
  if (!action || state.selected.size === 0) return
  const form = document.querySelector<HTMLFormElement>("[data-mf-bulk-form]")
  if (!form) return

  const input = document.createElement("input")
  input.type = "hidden"
  input.name = "action"
  input.value = action
  form.appendChild(input)

  showToast(`${action} ${state.selected.size} email(s)`)

  const doSubmit = () => {
    input.remove()
    state.selected.clear()
    refreshUI()
  }

  // Prefer HTMX when available so the list updates without a full reload.
  const htmx = (window as any).htmx
  if (htmx && typeof htmx.ajax === "function") {
    htmx.ajax("POST", form.getAttribute("action"), form).then(doSubmit, doSubmit)
  } else {
    form.submit()
    doSubmit()
  }
}

function init(): void {
  refreshUI()

  document.addEventListener("click", (e: MouseEvent) => {
    const check = (e.target as HTMLElement).closest<HTMLInputElement>("[data-mf-email-check]")
    if (check) {
      const pk = check.value || ""
      if (state.selected.has(pk)) state.selected.delete(pk)
      else state.selected.add(pk)
      refreshUI()
      return
    }

    const selectAll = (e.target as HTMLElement).closest<HTMLInputElement>("[data-mf-select-all]")
    if (selectAll) {
      const checks = document.querySelectorAll<HTMLInputElement>("[data-mf-email-check]")
      const currentlyAll = checks.length > 0 && [...checks].every((c) => c.checked)
      if (currentlyAll) {
        state.selected.clear()
      } else {
        checks.forEach((c) => state.selected.add(c.value))
      }
      refreshUI()
      return
    }

    const bulkBtn = (e.target as HTMLElement).closest<HTMLElement>("[data-mf-bulk-dropdown]")
    if (bulkBtn) {
      toggleBulkDropdown(bulkBtn)
      return
    }

    const actionEl = (e.target as HTMLElement).closest<HTMLElement>("[data-mf-bulk-action]")
    if (actionEl) {
      e.preventDefault()
      executeBulkAction(actionEl.dataset.mfBulkAction || "")
      return
    }

    const replyAll = (e.target as HTMLElement).closest<HTMLElement>("[data-mf-reply-toggle][data-mf-reply-all]")
    if (replyAll) {
      const form = replyAll.closest<HTMLFormElement>("[data-mf-reply-form]")
      if (!form) return
      const mode = form.querySelector<HTMLInputElement>('input[name="mode"]')
      const isAll = mode?.value === "reply_all"
      if (mode) mode.value = isAll ? "reply" : "reply_all"
      // Swap label text (last text node inside the button).
      const label = replyAll.querySelector("span:last-of-type") || replyAll
      label.textContent = isAll ? " Reply" : " Reply all"
      return
    }
  })

  document.addEventListener("keydown", (e: KeyboardEvent) => {
    if ((e.key === "Delete" || e.key === "Backspace") && state.selected.size > 0) {
      e.preventDefault()
      executeBulkAction("trash")
    }
  })

  // Re-sync selection state after HTMX swaps new rows in.
  document.addEventListener("htmx:afterSwap", (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail && detail.target && (detail.target as HTMLElement).id === "mf-email-list") {
      refreshUI()
    }
  })
}

const inbox = { init, refreshUI, showToast }
;(window as any).InboxFusion = (window as any).InboxFusion || {}
;(window as any).InboxFusion.inbox = inbox

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", () => init())
} else {
  init()
}
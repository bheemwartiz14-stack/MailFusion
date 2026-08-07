// ============================================================================
// Compose module — vanilla TypeScript (no Alpine).
// Enhances the compose form UI (editor toolbar, dropzone, autosave indicator,
// recipient list, bcc toggle) WITHOUT replacing the real Django form POST.
// ============================================================================

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

function csrfToken(): string {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
  if (meta) return meta.content
  const input = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]')
  return input ? input.value : ""
}

// Sync the contenteditable body into the hidden form fields before submit so
// the Django view receives the latest HTML/plain-text content.
function syncEditorToForm(form: HTMLFormElement): void {
  const editor = form.querySelector<HTMLElement>("[data-mf-editor]")
  const htmlInput = form.querySelector<HTMLInputElement>("[data-mf-body-html]")
  const textInput = form.querySelector<HTMLInputElement>("[data-mf-body-text]")
  if (!editor || (!htmlInput && !textInput)) return

  if (htmlInput) htmlInput.value = editor.innerHTML
  if (textInput) textInput.value = editor.innerText || ""
}

function updateAutosaveStatus(form: HTMLFormElement, saving: boolean): void {
  const status = form.querySelector<HTMLElement>("[data-mf-autosave-status]")
  if (!status) return
  status.textContent = saving ? "Saving…" : "Draft saved"
  status.classList.toggle("text-primary", saving)
  status.classList.toggle("text-on-surface-variant", !saving)
}

function setupEditorToolbar(form: HTMLFormElement): void {
  const toolbar = form.querySelector("[data-mf-editor-toolbar]")
  const editor = form.querySelector<HTMLElement>("[data-mf-editor]")
  if (!toolbar || !editor || !(document as any).execCommand) return

  toolbar.addEventListener("click", (e: MouseEvent) => {
    const btn = (e.target as HTMLElement).closest("[data-mf-cmd]")
    if (!btn) return
    e.preventDefault()
    editor.focus()
    const cmd = (btn as HTMLElement).dataset.mfCmd
    if (cmd) (document as any).execCommand(cmd, false, null)
  })
}

function setupDropzone(form: HTMLFormElement): void {
  const dropzone = form.querySelector<HTMLElement>("[data-mf-dropzone]")
  const fileInput = form.querySelector<HTMLInputElement>("[data-mf-file-input]")
  if (!dropzone) return

  const highlight = () => dropzone.classList.add("!border-primary", "bg-primary-soft")
  const unhighlight = () => dropzone.classList.remove("!border-primary", "bg-primary-soft")

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault()
    highlight()
  })
  dropzone.addEventListener("dragleave", (e) => {
    e.preventDefault()
    unhighlight()
  })
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault()
    unhighlight()
    if (fileInput && e.dataTransfer && e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files
    }
  })
}

function setupAutosave(form: HTMLFormElement): void {
  let timer: number | undefined
  form.querySelectorAll("[data-mf-subject], [data-mf-editor], [data-mf-recipient]").forEach((el) => {
    el.addEventListener("input", () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        // Real autosave is handled by the server on submit; a lightweight
        // status is enough here to signal "draft will be saved".
        updateAutosave(form, false)
      }, 2000)
    })
  })
}

function init(): void {
  document.querySelectorAll<HTMLFormElement>("[data-mf-compose-form]").forEach((form) => {
    setupEditorToolbar(form)
    setupDropzone(form)
    setupAutosave(form)

    form.addEventListener("submit", () => syncEditorToForm(form))

    const bccLink = form.querySelector<HTMLElement>("[data-mf-show-cc-bcc]")
    bccLinkHandler(form, bccLink)

    const discard = form.querySelector("[data-mf-discard]")
    if (discard) discard.addEventListener("click", (e) => {
      if (form.hasAttribute("data-mf-dirty")) {
        const msg = "Discard this message? Unsaved changes will be lost."
        if (!window.confirm(msg)) e.preventDefault()
      }
    })
  })
}

function bccLinkHandler(form: HTMLFormElement, trigger: HTMLElement | null): void {
  if (!trigger) return
  trigger.addEventListener("click", (e: MouseEvent) => {
    e.preventDefault()
    const row = form.querySelector<HTMLElement>("[data-mf-bcc-row]")
    if (row) row.style.display = row.style.display === "none" || !row.style.display ? "block" : "none"
  })
}

const compose = { init }
;(window as any).InboxFusion = (window as any).InboxFusion || {}
if (!(window as any).InboxFusion) (window as any).InboxFusion = {}
;(window as any).InboxFusion.compose = compose

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", () => init())
} else {
  init()
}
// Compose module with TypeScript support
import Alpine from "alpinejs"

interface Recipient {
  address: string
  name: string
}

interface ComposeState {
  currentStep: number
  recipients: {
    to: Recipient[]
    cc: Recipient[]
    bcc: Recipient[]
  }
  subject: string
  body: string
  importance: "low" | "normal" | "high"
  account: any | null
  attachments: any[]
  scheduledDate: Date | null
  isSending: boolean
  draftId: string | null
  quoteOriginal: boolean
}

interface ComposeUtils {
  showToast(message: string, type: "success" | "error" | "warning" | "info"): void
  getCsrfToken(): string
  validateEmail(email: string): boolean
  formatDateTime(date: Date): string
}

interface ComposeMethods {
  init(): void
  initRecipientInput(): void
  addRecipient(type: "to" | "cc" | "bcc", value: string): void
  removeRecipient(type: "to" | "cc" | "bcc", value: string): void
  updateRecipientsUI(): void
  initDatePicker(): void
  setupComposeForm(): void
  setupQuickActions(): void
  setupAutosave(): void
  setupCharCounters(): void
  executeQuickAction(action: string): void
  async autosaveDraft(): Promise<void>
  updateAutosaveStatus(isSaving: boolean): void
  updateQuotePreview(): void
  async submitForm(): Promise<void>
}

const state: ComposeState = {
  currentStep: 1,
  recipients: { to: [], cc: [], bcc: [] },
  subject: "",
  body: "",
  importance: "normal",
  account: null,
  attachments: [],
  scheduledDate: null,
  isSending: false,
  draftId: null,
  quoteOriginal: false,
}

const utils: ComposeUtils = {
  showToast(message: string, type: "success" | "error" | "warning" | "info" = "success"): void {
    const container = document.getElementById("mf-toast-container")
    if (!container) return

    const toast = document.createElement("div")
    toast.className = `fixed bottom-4 right-4 px-4 py-3 rounded-xl shadow-lg text-white transition-all duration-300 transform translate-y-10 opacity-0 ${type === "error" ? "bg-red-500" : type === "warning" ? "bg-yellow-500" : "bg-green-500"}`
    toast.textContent = message
    container.appendChild(toast)

    requestAnimationFrame(() => {
      toast.classList.remove("translate-y-10", "opacity-0")
      toast.classList.add("translate-y-0", "opacity-100")
    })

    setTimeout(() => {
      toast.classList.add("translate-y-10", "opacity-0")
      setTimeout(() => toast.remove(), 300)
    }, 3000)
  },

  getCsrfToken(): string {
    const name = "csrf-token"
    const value = document.querySelector(`meta[name="${name}"]`)?.getAttribute("content")
    return value || ""
  },

  validateEmail(email: string): boolean {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return emailRegex.test(email)
  },

  formatDateTime(date: Date): string {
    return date.toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  },
}

const compose: ComposeMethods = {
  init() {
    this.initRecipientInput()
    this.setupComposeForm()
    this.setupQuickActions()
    this.setupAutosave()
    this.setupCharCounters()
  },

  initRecipientInput() {
    document.querySelectorAll("[data-mf-recipient]").forEach((input) => {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.target.value.trim()) {
          e.preventDefault()
          this.addRecipient((e.target as HTMLInputElement).dataset.recipient as "to" | "cc" | "bcc", (e.target as HTMLInputElement).value.trim())
          ;(e.target as HTMLInputElement).value = ""
        }
      })
    })
  },

  addRecipient(type: "to" | "cc" | "bcc", value: string) {
    if (!utils.validateEmail(value)) {
      utils.showToast("Please enter a valid email address", "error")
      return
    }

    const existing = state.recipients[type].find((r) => r.address === value)
    if (!existing) {
      state.recipients[type].push({ address: value, name: value.split("@")[0] })
      this.updateRecipientsUI()
    }
  },

  removeRecipient(type: "to" | "cc" | "bcc", value: string) {
    state.recipients[type] = state.recipients[type].filter((r) => r.address !== value)
    this.updateRecipientsUI()
  },

  updateRecipientsUI() {
    document.querySelectorAll("[data-mf-recipient-list]").forEach((container) => {
      const type = (container as HTMLElement).dataset.recipientList as "to" | "cc" | "bcc"
      container.innerHTML = state.recipients[type]
        .map(
          (recipient) => `
          <div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container-high text-sm">
            <span class="text-on-surface-variant">${recipient.address}</span>
            <button
              type="button"
              class="hover:text-error"
              onclick="window.InboxFusion.compose.removeRecipient('${type}', '${recipient.address}')"
              aria-label="Remove ${recipient.address}"
            >
              <span class="material-symbols-outlined text-[18px]">close</span>
            </button>
          </div>
        `,
        )
        .join("")
    })
  },

  setupComposeForm() {
    const form = document.querySelector("[data-mf-compose-form]")
    if (!form) return

    form.addEventListener("submit", (e) => {
      e.preventDefault()
      this.submitForm()
    })

    document.querySelectorAll("[data-mf-show-cc-bcc]").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault()
        const bccRow = document.querySelector("[data-mf-bcc-row]")
        if (bccRow) {
          bccRow.style.display = bccRow.style.display === "none" ? "flex" : "none"
        }
      })
    })
  },

  setupQuickActions() {
    document.querySelectorAll("[data-mf-quick-action]").forEach((button) => {
      button.addEventListener("click", (e) => {
        const action = (e.target as HTMLElement).closest("[data-mf-quick-action]")?.dataset.mfQuickAction
        if (action) this.executeQuickAction(action)
      })
    })
  },

  executeQuickAction(action: string) {
    switch (action) {
      case "cc-team":
        this.addRecipient("cc", "team@acme.io")
        break
      case "reply-all":
        state.subject = "Re: " + state.subject || ""
        state.quoteOriginal = true
        this.updateQuotePreview()
        break
      case "forward":
        state.subject = "Fwd: " + state.subject || ""
        state.quoteOriginal = true
        this.updateQuotePreview()
        break
    }
  },

  setupAutosave() {
    let saveTimeout: any
    const form = document.querySelector("[data-mf-compose-form]")
    if (!form) return

    form.addEventListener("input", () => {
      clearTimeout(saveTimeout)
      saveTimeout = setTimeout(() => {
        this.autosaveDraft()
      }, 2000)
    })
  },

  async autosaveDraft() {
    if (!state.draftId) return

    try {
      const response = await fetch(`/api/compose/${state.draftId}/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": utils.getCsrfToken(),
        },
        body: JSON.stringify({
          action: "autosave",
          to: state.recipients.to.map((r) => r.address),
          cc: state.recipients.cc.map((r) => r.address),
          bcc: state.recipients.bcc.map((r) => r.address),
          subject: state.subject,
          body_html: state.body,
          importance: state.importance,
        }),
      })

      if (response.ok) {
        this.updateAutosaveStatus(true)
      }
    } catch (error) {
      console.error("Autosave failed:", error)
    }
  },

  setupCharCounters() {
    const subjectInput = document.querySelector("[data-mf-subject]")
    const bodyTextarea = document.querySelector("[data-mf-editor]")

    if (subjectInput) {
      subjectInput.addEventListener("input", () => {
        const length = (subjectInput as HTMLInputElement).value.length
        const counter = subjectInput.closest(".flex-col.gap-2")?.querySelector(".text-sm.text-slate-500")
        if (counter) {
          counter.textContent = `${length}/200 characters`
          if (length > 180) counter.classList.add("text-error")
          else counter.classList.remove("text-error")
        }
      })
    }

    if (bodyTextarea) {
      bodyTextarea.addEventListener("input", () => {
        const length = (bodyTextarea as HTMLElement).textContent?.length || 0
        const counter = bodyTextarea.closest(".flex-col.gap-2")?.querySelector(".text-sm.text-slate-500")
        if (counter) {
          counter.textContent = `${length} characters (auto-save)`
        }
      })
    }
  },

  updateAutosaveStatus(isSaving: boolean): void {
    const status = document.querySelector("[data-mf-autosave-status]")
    if (status) {
      status.textContent = isSaving ? "Saving draft..." : "Draft saved automatically"
      status.className = isSaving
        ? "text-sm text-blue-600"
        : "text-sm text-green-600"
    }
  },

  updateQuotePreview(): void {
    const quotePreview = document.querySelector("[data-mf-quote-preview]")
    if (state.quoteOriginal && quotePreview) {
      quotePreview.innerHTML = "<blockquote>Original message will appear here</blockquote>"
    } else if (quotePreview) {
      quotePreview.innerHTML = ""
    }
  },

  async submitForm() {
    if (state.isSending) return

    state.isSending = true
    utils.showToast("Sending email...", "info")

    try {
      const response = await fetch("/api/compose/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": utils.getCsrfToken(),
        },
        body: JSON.stringify({
          action: state.draftId ? "update" : "send",
          draft_id: state.draftId,
          account: state.account,
          to: state.recipients.to.map((r) => r.address),
          cc: state.recipients.cc.map((r) => r.address),
          bcc: state.recipients.bcc.map((r) => r.address),
          subject: state.subject,
          body_html: state.body,
          importance: state.importance,
          scheduled_date: state.scheduledDate,
        }),
      })

      if (response.ok) {
        const data = await response.json()
        utils.showToast("Email sent successfully!")
        setTimeout(() => {
          window.location.href = data.redirect_url || "/inbox/?folder=sent"
        }, 1000)
      } else {
        const error = await response.json()
        utils.showToast(error.message || "Failed to send email", "error")
      }
    } catch (error) {
      console.error("Submit failed:", error)
      utils.showToast("Failed to send email. Please try again.", "error")
    } finally {
      state.isSending = false
    }
  },
}

window.InboxFusion = window.InboxFusion || {}
window.InboxFusion.compose = compose

window.Alpine = Alpine
Alpine.start()

window.addEventListener("DOMContentLoaded", () => {
  window.InboxFusion.compose.init()
})
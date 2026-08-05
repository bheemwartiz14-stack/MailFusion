// Mailfusion UI - Alpine.js based component system
// This replaces Bootstrap components with modern, accessible alternatives

// Global state management
window.InboxFusion = window.InboxFusion || {};
window.InboxFusion.compose = {
  state: {
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
  },

  init() {
    this.initRecipientInput()
    this.setupComposeForm()
    this.setupQuickActions()
    this.setupAutosave()
    this.setupCharCounters()
  },

  initRecipientInput() {
    document.querySelectorAll("[data-mf-recipient]").forEach((input) => {
      // Initialize recipient chips for better UX
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.target.value.trim()) {
          e.preventDefault()
          this.addRecipient(input.dataset.recipient, e.target.value.trim())
          e.target.value = ""
        }
      })
    })
  },

  addRecipient(type, value) {
    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(value)) {
      this.showToast("Please enter a valid email address", "error")
      return
    }

    const existing = this.state.recipients[type].find((r) => r === value)
    if (!existing) {
      this.state.recipients[type].push(value)
      this.updateRecipientsUI()
    }
  },

  removeRecipient(type, value) {
    this.state.recipients[type] = this.state.recipients[type].filter(
      (r) => r !== value,
    )
    this.updateRecipientsUI()
  },

  updateRecipientsUI() {
    document.querySelectorAll("[data-mf-recipient-list]").forEach((container) => {
      const type = container.dataset.recipientList
      container.innerHTML = this.state.recipients[type]
        .map(
          (recipient) => `
          <div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container-high text-sm">
            <span class="text-on-surface-variant">${recipient}</span>
            <button
              type="button"
              class="hover:text-error"
              onclick="window.InboxFusion.compose.removeRecipient('${type}', '${recipient}')"
              aria-label="Remove ${recipient}"
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

    // Show CC/BCC fields when CC/Bcc text is clicked
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
    // Quick action buttons for common recipients/templates
    document.querySelectorAll("[data-mf-quick-action]").forEach((button) => {
      button.addEventListener("click", (e) => {
        const action = button.dataset.mfQuickAction
        this.executeQuickAction(action)
      })
    })
  },

  executeQuickAction(action) {
    switch (action) {
      case "cc-team":
        this.addRecipient("cc", "team@acme.io")
        break
      case "reply-all":
        this.state.subject = "Re: " + this.state.subject || ""
        this.state.quoteOriginal = true
        this.updateQuotePreview()
        break
      case "forward":
        this.state.subject = "Fwd: " + this.state.subject || ""
        this.state.quoteOriginal = true
        this.updateQuotePreview()
        break
    }
  },

  setupAutosave() {
    let saveTimeout
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
    if (!this.state.draftId) return

    try {
      const response = await fetch(`/api/compose/${this.state.draftId}/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": this.getCsrfToken(),
        },
        body: JSON.stringify({
          action: "autosave",
          to: this.state.recipients.to,
          cc: this.state.recipients.cc,
          bcc: this.state.recipients.bcc,
          subject: this.state.subject,
          body_html: this.state.body,
          importance: this.state.importance,
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
        const length = subjectInput.value.length
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
        const length = bodyTextarea.textContent.length
        const counter = bodyTextarea.closest(".flex-col.gap-2")?.querySelector(".text-sm.text-slate-500")
        if (counter) {
          counter.textContent = `${length} characters (auto-save)`
        }
      })
    }
  },

  updateAutosaveStatus(isSaving) {
    const status = document.querySelector("[data-mf-autosave-status]")
    if (status) {
      status.textContent = isSaving ? "Saving draft..." : "Draft saved automatically"
      status.className = isSaving
        ? "text-sm text-blue-600"
        : "text-sm text-green-600"
    }
  },

  showToast(message, type = "success") {
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

  getCsrfToken() {
    const name = "csrf-token"
    const value = document.querySelector(`meta[name="${name}"]`)?.getAttribute("content")
    return value || ""
  },

  async submitForm() {
    if (this.state.isSending) return

    this.state.isSending = true
    this.showToast("Sending email...", "info")

    try {
      const response = await fetch("/api/compose/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": this.getCsrfToken(),
        },
        body: JSON.stringify({
          action: this.state.draftId ? "update" : "send",
          draft_id: this.state.draftId,
          account: this.state.account,
          to: this.state.recipients.to,
          cc: this.state.recipients.cc,
          bcc: this.state.recipients.bcc,
          subject: this.state.subject,
          body_html: this.state.body,
          importance: this.state.importance,
          scheduled_date: this.state.scheduledDate,
        }),
      })

      if (response.ok) {
        const data = await response.json()
        this.showToast("Email sent successfully!")
        // Redirect to sent items or the sent email
        setTimeout(() => {
          window.location.href = data.redirect_url || "/inbox/?folder=sent"
        }, 1000)
      } else {
        const error = await response.json()
        this.showToast(error.message || "Failed to send email", "error")
      }
    } catch (error) {
      console.error("Submit failed:", error)
      this.showToast("Failed to send email. Please try again.", "error")
    } finally {
      this.state.isSending = false
    }
  },
}

// Initialize Alpine
window.Alpine = Alpine
Alpine.start()

// Initialize the compose module
window.addEventListener("DOMContentLoaded", () => {
  window.InboxFusion.compose.init()
})

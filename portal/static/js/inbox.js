// Global state management
window.InboxFusion = {
  currentUser: { name: "Alex Morgan", email: "alex.morgan@acme.io", initials: "AM" },
  state: {
    selectedEmails: new Set(),
    isSelecting: false,
    showBulkBar: false,
    isComposing: false,
    currentFolder: "all",
    currentAccount: null,
    composeMode: "new",
    originalEmail: null,
    draftEmail: null,
    attachmentCount: 0,
  },
  utils: {
    formatDate: (date) => {
      const d = new Date(date)
      const now = new Date()
      const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24))
      if (diffDays === 0) return "Today"
      if (diffDays === 1) return "Yesterday"
      if (diffDays < 7) return d.toLocaleDateString("en-US", { weekday: "short" })
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
    },

    getInitials: (name) => {
      return name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    },

    debounce: (func, wait) => {
      let timeout
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout)
          func(...args)
        }
        clearTimeout(timeout)
        timeout = setTimeout(later, wait)
      }
    },

    toggleSelection: (emailId, event) => {
      if (event.ctrlKey || event.metaKey) {
        if (window.InboxFusion.state.selectedEmails.has(emailId)) {
          window.InboxFusion.state.selectedEmails.delete(emailId)
        } else {
          window.InboxFusion.state.selectedEmails.add(emailId)
        }
      } else {
        window.InboxFusion.state.selectedEmails.clear()
        window.InboxFusion.state.selectedEmails.add(emailId)
      }
      window.InboxFusion.updateUI()
    },

    selectAll: () => {
      const emailList = document.querySelectorAll('[data-mf-email-row]')
      if (window.InboxFusion.state.selectedEmails.size === emailList.length) {
        window.InboxFusion.state.selectedEmails.clear()
      } else {
        emailList.forEach((row) => {
          const emailId = row.dataset.emailId
          window.InboxFusion.state.selectedEmails.add(emailId)
        })
      }
      window.InboxFusion.updateUI()
    },

    showToast: (message, type = "success") => {
      const container = document.getElementById("mf-toast-container")
      if (!container) return

      const toast = document.createElement("div")
      toast.className = `fixed bottom-4 right-4 px-4 py-3 rounded-lg shadow-lg text-white transition-all duration-300 transform translate-y-10 opacity-0 ${type === "error" ? "bg-red-500" : "bg-green-500"}`
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
  },

  inbox: {
    init() {
      this.setupKeyboardShortcuts()
      this.setupInfiniteScroll()
      this.setupBulkActions()
      this.setupComposeModal()
      this.setupFileUpload()
      this.setupEditor()
    },

    setupKeyboardShortcuts() {
      document.addEventListener("keydown", (e) => {
        // Delete to trash
        if (e.key === "Delete" && window.InboxFusion.state.selectedEmails.size > 0) {
          e.preventDefault()
          window.InboxFusion.inbox.executeBulkAction("trash")
        }

        // Select all
        if ((e.ctrlKey || e.metaKey) && e.key === "a") {
          e.preventDefault()
          window.InboxFusion.utils.selectAll()
        }

        // Compose shortcut
        if ((e.ctrlKey || e.metaKey) && e.key === "c") {
          e.preventDefault()
          window.InboxFusion.inbox.openComposer()
        }
      })
    },

    setupInfiniteScroll() {
      const scrollContainer = document.querySelector("[data-mf-inbox-scroll]")
      if (!scrollContainer) return

      let isLoading = false
      let currentOffset = 0
      const pageSize = 25

      scrollContainer.addEventListener("scroll", () => {
        if (isLoading) return

        const { scrollTop, scrollHeight, clientHeight } = scrollContainer
        if (scrollTop + clientHeight >= scrollHeight - 100) {
          isLoading = true
          currentOffset += pageSize

          window.InboxFusion.inbox.loadMoreEmails(currentOffset)
            .finally(() => {
              isLoading = false
            })
        }
      })
    },

    async loadMoreEmails(offset) {
      const emailList = document.getElementById("mf-email-list")
      if (!emailList || !emailList.hxTrigger) return

      // This would typically make an HTMX request
      // For demo, we'll just show a toast
      window.InboxFusion.utils.showToast("Loading more emails...")
    },

    setupBulkActions() {
      // Bulk action dropdown
      document.addEventListener("click", (e) => {
        if (e.target.closest("[data-mf-bulk-dropdown]")) {
          e.stopPropagation()
          const dropdown = e.target.closest("[data-mf-bulk-dropdown]").nextElementSibling
          dropdown.classList.toggle("hidden")
        }

        if (!e.target.closest("[data-mf-bulk-action]")) return

        e.preventDefault()
        const action = e.target.closest("[data-mf-bulk-action]").dataset mfBulkAction
        window.InboxFusion.inbox.executeBulkAction(action)
      })
    },

    executeBulkAction(action) {
      const count = window.InboxFusion.state.selectedEmails.size
      window.InboxFusion.utils.showToast(`${action} ${count} email(s)`)
      window.InboxFusion.state.selectedEmails.clear()
      window.InboxFusion.updateUI()
    },

    setupComposeModal() {
      // Modal open/close handlers
      document.addEventListener("click", (e) => {
        if (e.target.closest("[data-mf-open-compose]")) {
          e.preventDefault()
          window.InboxFusion.inbox.openComposer()
        }

        if (e.target.id === "mfComposeModal" || e.target.closest("[data-mf-modal-close]")) {
          window.InboxFusion.inbox.closeComposer()
        }
      })
    },

    openComposer() {
      window.InboxFusion.state.isComposing = true
      const modal = document.getElementById("mfComposeModal")
      if (modal) {
        modal.classList.remove("hidden")
        setTimeout(() => {
          modal.classList.remove("opacity-0")
          modal.classList.add("opacity-100")
        }, 10)
      }
    },

    closeComposer() {
      window.InboxFusion.state.isComposing = false
      const modal = document.getElementById("mfComposeModal")
      if (modal) {
        modal.classList.add("opacity-0")
        setTimeout(() => {
          modal.classList.add("hidden")
          modal.classList.remove("opacity-100")
        }, 300)
      }
    },

    setupFileUpload() {
      const dropzone = document.querySelector("[data-mf-dropzone]")
      if (!dropzone) return

      dropzone.addEventListener("dragover", (e) => {
        e.preventDefault()
        dropzone.classList.add("border-blue-500", "bg-blue-50")
      })

      dropzone.addEventListener("dragleave", (e) => {
        e.preventDefault()
        dropzone.classList.remove("border-blue-500", "bg-blue-50")
      })

      dropzone.addEventListener("drop", (e) => {
        e.preventDefault()
        dropzone.classList.remove("border-blue-500", "bg-blue-50")
        window.InboxFusion.utils.showToast("File dropped - processing...")
      })
    },

    setupEditor() {
      const editor = document.querySelector("[data-mf-editor]")
      if (!editor) return

      editor.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault()
          document.execCommand("insertLineBreak")
        }
      })

      // Simple toolbar commands
      document.addEventListener("click", (e) => {
        if (e.target.closest("[data-mf-cmd]")) {
          e.preventDefault()
          const command = e.target.closest("[data-mf-cmd]").dataset mfCmd
          document.execCommand(command)
        }
      })
    },
  },

  notifications: {
    init() {
      this.setupNotificationClose()
    },

    setupNotificationClose() {
      document.addEventListener("click", (e) => {
        if (e.target.closest("[data-mf-notification-close]")) {
          e.preventDefault()
          e.target.closest("[data-mf-notification]").remove()
        }
      })
    },
  },

  updateUI() {
    const selectedCount = window.InboxFusion.state.selectedEmails.size
    const bulkBar = document.querySelector("[data-mf-bulk-bar]")
    const selectedCountEl = document.querySelector("[data-mf-selected-count]")
    const bulkMenu = document.querySelector("[data-mf-bulk-menu]")

    if (bulkBar && selectedCountEl) {
      window.InboxFusion.state.showBulkBar = selectedCount > 0
      bulkBar.classList.toggle("hidden", !window.InboxFusion.state.showBulkBar)
      selectedCountEl.textContent = selectedCount

      if (bulkMenu) {
        bulkMenu.classList.add("hidden")
      }
    }

    // Update email row selection states
    document.querySelectorAll("[data-mf-email-row]").forEach((row) => {
      const emailId = row.dataset.emailId
      row.classList.toggle("selected", window.InboxFusion.state.selectedEmails.has(emailId))
    })
  },
}

// Initialize Alpine
window.Alpine = Alpine
Alpine.start()

// Initialize the app
window.addEventListener("DOMContentLoaded", () => {
  window.InboxFusion.inbox.init()
  window.InboxFusion.notifications.init()
})

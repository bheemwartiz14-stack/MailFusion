// Inbox module with TypeScript support
import Alpine from "alpinejs"
import normalizeWheel from "npm:normalize-wheel"

interface InboxState {
  selectedEmails: Set<string>
  isSelecting: boolean
  showBulkBar: boolean
  isComposing: boolean
  currentFolder: string
  currentAccount: string | null
  composeMode: string
  originalEmail: any | null
  draftEmail: any | null
  attachmentCount: number
}

interface InboxUtils {
  formatDate(date: Date): string
  getInitials(name: string): string
  debounce(func: Function, wait: number): Function
  toggleSelection(emailId: string, event: KeyboardEvent): void
  selectAll(): void
  showToast(message: string, type?: string): void
}

interface InboxMethods {
  init(): void
  setupKeyboardShortcuts(): void
  setupInfiniteScroll(): void
  setupBulkActions(): void
  setupComposeModal(): void
  setupFileUpload(): void
  setupEditor(): void
  loadMoreEmails(offset: number): Promise<void>
  executeBulkAction(action: string): void
  openComposer(): void
  closeComposer(): void
}

const state: InboxState = {
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
}

const utils: InboxUtils = {
  formatDate(date: Date): string {
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
    if (diffDays === 0) return "Today"
    if (diffDays === 1) return "Yesterday"
    if (diffDays < 7) return date.toLocaleDateString("en-US", { weekday: "short" })
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" })
  },

  getInitials(name: string): string {
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2)
  },

  debounce(func: Function, wait: number): Function {
    let timeout: any
    return function (...args: any[]) {
      clearTimeout(timeout)
      timeout = setTimeout(() => func(...args), wait)
    }
  },

  toggleSelection(emailId: string, event: KeyboardEvent): void {
    if (event.ctrlKey || event.metaKey) {
      if (state.selectedEmails.has(emailId)) {
        state.selectedEmails.delete(emailId)
      } else {
        state.selectedEmails.add(emailId)
      }
    } else {
      state.selectedEmails.clear()
      state.selectedEmails.add(emailId)
    }
    updateUI()
  },

  selectAll(): void {
    const emailList = document.querySelectorAll('[data-mf-email-row]')
    if (state.selectedEmails.size === emailList.length) {
      state.selectedEmails.clear()
    } else {
      emailList.forEach((row) => {
        const emailId = row.dataset.emailId
        if (emailId) state.selectedEmails.add(emailId)
      })
    }
    updateUI()
  },

  showToast(message: string, type: string = "success"): void {
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
}

const inbox: InboxMethods = {
  init() {
    this.setupKeyboardShortcuts()
    this.setupInfiniteScroll()
    this.setupBulkActions()
    this.setupComposeModal()
    this.setupFileUpload()
    this.setupEditor()
  },

  setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e: KeyboardEvent) => {
      if (e.key === "Delete" && state.selectedEmails.size > 0) {
        e.preventDefault()
        this.executeBulkAction("trash")
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "a") {
        e.preventDefault()
        utils.selectAll()
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "c") {
        e.preventDefault()
        this.openComposer()
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
        this.loadMoreEmails(currentOffset).finally(() => {
          isLoading = false
        })
      }
    })
  },

  async loadMoreEmails(offset: number): Promise<void> {
    const emailList = document.getElementById("mf-email-list")
    if (!emailList || !emailList.hxTrigger) return

    utils.showToast("Loading more emails...")
  },

  setupBulkActions() {
    document.addEventListener("click", (e: MouseEvent) => {
      if (e.target.closest("[data-mf-bulk-dropdown]")) {
        e.stopPropagation()
        const dropdown = (e.target as HTMLElement).closest("[data-mf-bulk-dropdown]")?.nextElementSibling
        if (dropdown) dropdown.classList.toggle("hidden")
      }

      if (!e.target.closest("[data-mf-bulk-action]")) return

      e.preventDefault()
      const action = (e.target as HTMLElement).closest("[data-mf-bulk-action]")?.dataset.mfBulkAction
      if (action) this.executeBulkAction(action)
    })
  },

  executeBulkAction(action: string): void {
    const count = state.selectedEmails.size
    utils.showToast(`${action} ${count} email(s)`)
    state.selectedEmails.clear()
    updateUI()
  },

  setupComposeModal() {
    document.addEventListener("click", (e: MouseEvent) => {
      if (e.target.closest("[data-mf-open-compose]")) {
        e.preventDefault()
        this.openComposer()
      }

      if (e.target.id === "mfComposeModal" || e.target.closest("[data-mf-modal-close]")) {
        this.closeComposer()
      }
    })
  },

  openComposer(): void {
    state.isComposing = true
    const modal = document.getElementById("mfComposeModal")
    if (modal) {
      modal.classList.remove("hidden")
      setTimeout(() => {
        modal.classList.remove("opacity-0")
        modal.classList.add("opacity-100")
      }, 10)
    }
  },

  closeComposer(): void {
    state.isComposing = false
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

    dropzone.addEventListener("dragover", (e: DragEvent) => {
      e.preventDefault()
      dropzone.classList.add("border-blue-500", "bg-blue-50")
    })

    dropzone.addEventListener("dragleave", (e: DragEvent) => {
      e.preventDefault()
      dropzone.classList.remove("border-blue-500", "bg-blue-50")
    })

    dropzone.addEventListener("drop", (e: DragEvent) => {
      e.preventDefault()
      dropzone.classList.remove("border-blue-500", "bg-blue-50")
      utils.showToast("File dropped - processing...")
    })
  },

  setupEditor() {
    const editor = document.querySelector("[data-mf-editor]")
    if (!editor) return

    editor.addEventListener("keydown", (e: KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        document.execCommand("insertLineBreak")
      }
    })

    document.addEventListener("click", (e: MouseEvent) => {
      if (e.target.closest("[data-mf-cmd]")) {
        e.preventDefault()
        const command = (e.target as HTMLElement).closest("[data-mf-cmd]")?.dataset.mfCmd
        if (command) document.execCommand(command)
      }
    })
  },
}

function updateUI(): void {
  const selectedCount = state.selectedEmails.size
  const bulkBar = document.querySelector("[data-mf-bulk-bar]")
  const selectedCountEl = document.querySelector("[data-mf-selected-count]")
  const bulkMenu = document.querySelector("[data-mf-bulk-menu]")

  if (bulkBar && selectedCountEl) {
    state.showBulkBar = selectedCount > 0
    bulkBar.classList.toggle("hidden", !state.showBulkBar)
    selectedCountEl.textContent = selectedCount.toString()

    if (bulkMenu) {
      bulkMenu.classList.add("hidden")
    }
  }

  document.querySelectorAll("[data-mf-email-row]").forEach((row) => {
    const emailId = row.dataset.emailId
    if (emailId) row.classList.toggle("selected", state.selectedEmails.has(emailId))
  })
}

window.InboxFusion = window.InboxFusion || {}
window.InboxFusion.inbox = inbox
window.InboxFusion.updateUI = updateUI

window.Alpine = Alpine
Alpine.start()

window.addEventListener("DOMContentLoaded", () => {
  window.InboxFusion.inbox.init()
})
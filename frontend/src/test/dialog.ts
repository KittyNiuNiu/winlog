// jsdom has no showModal() or close() on <dialog>. This stub opens and closes the dialog
// through its `open` attribute and fires "close", which is all the app relies on.
export function installDialogStub(): void {
  if (typeof HTMLDialogElement === 'undefined') {
    return
  }
  const proto = HTMLDialogElement.prototype
  if (typeof proto.showModal !== 'function') {
    proto.showModal = function showModal(this: HTMLDialogElement) {
      this.setAttribute('open', '')
    }
  }
  if (typeof proto.close !== 'function') {
    proto.close = function close(this: HTMLDialogElement) {
      if (this.hasAttribute('open')) {
        this.removeAttribute('open')
        this.dispatchEvent(new Event('close'))
      }
    }
  }
}

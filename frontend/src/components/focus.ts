/**
 * Focus helpers for moves after a request (#84): a new "Try again" after a failed retry, the
 * edit page's text field once the entry has loaded, "Try the demo" after a failed demo.
 */

interface MoveOptions extends FocusOptions {
  /**
   * The element focus was on when the request started, for example a login field after a
   * mouse press on "Try the demo". Focus still there means the user has not moved on.
   */
  stayed?: Element | null
}

/**
 * Whether the user has moved keyboard focus to a control: focus is on something other than
 * the page body, the main landmark or `stayed`. The main landmark takes focus from the skip
 * link and from a click on the page's text (it has `tabindex="-1"`); neither is a control.
 */
export function focusMovedOn(stayed: Element | null = null): boolean {
  const active = document.activeElement
  return active !== null && active !== document.body && active.tagName !== 'MAIN' && active !== stayed
}

/** Focuses `element`, unless the user has moved focus to another control meanwhile. */
export function focusUnlessMovedOn(element: HTMLElement | null, { stayed = null, ...options }: MoveOptions = {}): void {
  if (element !== null && (element === document.activeElement || !focusMovedOn(stayed))) {
    element.focus(options)
  }
}

/**
 * A ref callback that focuses its element when it is put in the page, unless the user has
 * moved on. For example the new "Try again" after a retry failed again.
 */
export function focusWhenShown(element: HTMLElement | null): void {
  focusUnlessMovedOn(element)
}

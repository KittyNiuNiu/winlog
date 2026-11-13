import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import * as api from '../api/index.ts'
import {
  DemoAccountNotDeletableError,
  NetworkError,
  NotAuthenticatedError,
  TooManyAttemptsError,
  UnknownError,
  ValidationError,
  WrongPasswordError,
  type DownloadedFile,
} from '../api/index.ts'
import { clearSession, saveSession } from '../api/session.ts'
import { connectLoginRedirect } from '../auth/loginRedirect.ts'
import { routes } from '../routes.tsx'
import { REVOKE_URL_AFTER_MS } from '../settings/saveFile.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

// The data and account settings page (#34): downloads (FR-D1) and account deletion with a
// confirmation step in the page (FR-D2). The API client is mocked, and so are
// URL.createObjectURL / revokeObjectURL, which jsdom does not provide. The temporary
// link's click is caught, so jsdom does not try to navigate. This page makes no AI call.

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    exportJson: vi.fn(),
    exportMarkdown: vi.fn(),
    deleteAccount: vi.fn(),
    login: vi.fn(),
    listEntries: vi.fn(),
    listTags: vi.fn(),
    logout: vi.fn(),
    setLoginRedirect: vi.fn(actual.setLoginRedirect),
  }
})

const exportJson = vi.mocked(api.exportJson)
const exportMarkdown = vi.mocked(api.exportMarkdown)
const deleteAccount = vi.mocked(api.deleteAccount)
const login = vi.mocked(api.login)

const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'
const WRONG_PASSWORD = 'That password is incorrect.'
const DELETED_NOTICE = 'Your account has been deleted.'
const DEMO_NOT_DELETABLE = "The demo account can't be deleted."
const PASSWORD = 'Correct-Horse-7'
const BLOB_URL = 'blob:http://localhost/winlog-export'

const JSON_BODY = '{"entries":[{"id":"1","text":"Led the incident review."}],"summaries":[]}'
const MARKDOWN_BODY = '# Winlog export\n\n## Entries\n\nLed the incident review.\n'
const EMPTY_JSON_BODY = '{"exported_at":"2026-11-13T10:00:00Z","entries":[],"summaries":[]}'
const EMPTY_MARKDOWN_BODY = '# Winlog export\n\n## Entries\n\nNone\n\n## Summaries\n\nNone\n'

function file(contents: string, filename: string, type: string): DownloadedFile {
  return { contents: new Blob([contents], { type }), filename }
}

function jsonFile(contents = JSON_BODY): DownloadedFile {
  return file(contents, 'winlog-export-2026-11-13.json', 'application/json')
}

function markdownFile(contents = MARKDOWN_BODY): DownloadedFile {
  return file(contents, 'winlog-export-2026-11-13.md', 'text/markdown')
}

function deferred<T>() {
  let resolve: (value: T) => void = () => {}
  let reject: (reason: unknown) => void = () => {}
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

// --- The browser's file saving, mocked ---

interface SavedLink {
  href: string
  download: string
  inPage: boolean
}

let createObjectURL: ReturnType<typeof vi.fn<(blob: Blob) => string>>
let revokeObjectURL: ReturnType<typeof vi.fn<(url: string) => void>>
let linkClick: MockInstance<(this: HTMLElement) => void>
let savedLinks: SavedLink[]

function installFileSaving(): void {
  createObjectURL = vi.fn<(blob: Blob) => string>(() => BLOB_URL)
  revokeObjectURL = vi.fn<(url: string) => void>()
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: revokeObjectURL })
  savedLinks = []
  linkClick = vi.spyOn(HTMLElement.prototype, 'click').mockImplementation(function (this: HTMLElement) {
    if (this instanceof HTMLAnchorElement) {
      savedLinks.push({ href: this.href, download: this.download, inPage: document.body.contains(this) })
    }
  })
}

/** The contents of the n-th file handed to the browser. */
async function savedContents(index = 0): Promise<string> {
  const blob = createObjectURL.mock.calls[index]?.[0]
  if (blob === undefined) {
    throw new Error(`no file ${index} was saved`)
  }
  return blob.text()
}

// --- Rendering and finding things ---

function registeredRedirect(): () => void {
  const redirect = vi.mocked(api.setLoginRedirect).mock.lastCall?.[0]
  if (redirect === undefined) {
    throw new Error('setLoginRedirect was not called')
  }
  return redirect
}

async function renderSettings() {
  const result = renderRoute('/settings')
  await act(async () => {})
  return result
}

async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element)
  })
}

async function type(element: HTMLElement, value: string): Promise<void> {
  await act(async () => {
    fireEvent.change(element, { target: { value } })
  })
}

function main(): HTMLElement {
  return screen.getByRole('main')
}

function dataSection(): HTMLElement {
  return screen.getByRole('region', { name: 'Your data' })
}

function accountSection(): HTMLElement {
  return screen.getByRole('region', { name: 'Account' })
}

function step(): HTMLElement {
  return screen.getByRole('region', { name: 'Delete your account?' })
}

function queryStep(): HTMLElement | null {
  return screen.queryByRole('region', { name: 'Delete your account?' })
}

function button(container: HTMLElement, name: string | RegExp): HTMLButtonElement {
  return within(container).getByRole('button', { name }) as HTMLButtonElement
}

function deleteAccountButton(): HTMLButtonElement {
  return button(accountSection(), 'Delete account')
}

function passwordInput(): HTMLInputElement {
  return within(step()).getByLabelText('Current password') as HTMLInputElement
}

function confirmInput(): HTMLInputElement {
  return within(step()).getByLabelText('Type "delete" to confirm') as HTMLInputElement
}

function deleteMyAccountButton(): HTMLButtonElement {
  return button(step(), /^(Delete my account|Deleting…)$/)
}

function cancelButton(): HTMLButtonElement {
  return button(step(), 'Cancel')
}

function messagesOf(input: HTMLInputElement): string[] {
  const container = document.getElementById(`${input.id}-messages`)
  if (container === null) {
    throw new Error(`no messages for ${input.id}`)
  }
  return Array.from(container.querySelectorAll('p'), (p) => p.textContent ?? '')
}

/** The texts of the error and information messages in `container`, without the empty ones. */
function messageTexts(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('.message'), (element) => element.textContent ?? '').filter(
    (text) => text !== '',
  )
}

/** Messages in "Your data" and in the step, apart from the field messages. */
function dataMessages(): string[] {
  return messageTexts(dataSection())
}

async function openStep(): Promise<void> {
  await click(deleteAccountButton())
}

async function fillStep(password = PASSWORD, word = 'delete'): Promise<void> {
  await type(passwordInput(), password)
  await type(confirmInput(), word)
}

async function submitDeletion(): Promise<void> {
  await click(deleteMyAccountButton())
}

/** The download buttons in the whole page: in "Your data" and, when open, in the step. */
function allDownloadButtons(): HTMLButtonElement[] {
  return within(main()).getAllByRole('button', { name: /^(Download JSON|Download Markdown|Downloading…)$/ }) as HTMLButtonElement[]
}

// Like the real client: a successful deletion removes the stored session.
async function deleteClearingSession(): Promise<void> {
  clearSession()
}

beforeEach(() => {
  storeTestSession()
  installFileSaving()
  vi.mocked(api.listEntries).mockResolvedValue({ entries: [] })
  vi.mocked(api.listTags).mockResolvedValue({ tags: [] })
})

afterEach(() => {
  linkClick.mockRestore()
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
})

describe('the settings page', () => {
  it('test_fr_d1_settings_page_shows_your_data_then_account', async () => {
    await renderSettings()

    expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeTruthy()
    const headings = within(main()).getAllByRole('heading', { level: 2 })
    expect(headings.map((heading) => heading.textContent)).toEqual(['Your data', 'Account'])
    expect(screen.queryByText('This page is coming soon.')).toBeNull()
    expect(
      within(dataSection()).getByText(
        'Download all your entries and summaries. JSON is complete and machine-readable. Markdown is easy to read.',
      ),
    ).toBeTruthy()
    expect(within(accountSection()).getByText('Deleting your account removes all of your data.')).toBeTruthy()
    expect(queryStep()).toBeNull()
  })

  it('test_fr_a2_settings_stays_current_and_log_out_stays_in_the_navigation_only', async () => {
    for (const width of ['phone', 'laptop'] as const) {
      setViewport(width)
      await renderSettings()

      expect(within(main()).queryByRole('button', { name: 'Log out' })).toBeNull()
      expect(within(main()).queryByText('Log out')).toBeNull()
      if (width === 'laptop') {
        const settingsLink = screen.getByRole('link', { name: 'Settings' })
        expect(settingsLink.getAttribute('aria-current')).toBe('page')
        expect(screen.getByRole('button', { name: 'Log out' })).toBeTruthy()
      } else {
        const more = screen.getByRole('button', { name: 'More' })
        expect(more.classList.contains('shell__pill--current')).toBe(true)
        fireEvent.click(more)
        expect(screen.getByRole('button', { name: 'Log out' })).toBeTruthy()
      }
      cleanup()
    }
  })

  it('test_fr_d1_fr_d2_every_button_on_the_page_is_secondary', async () => {
    await renderSettings()
    await openStep()
    await fillStep()

    const buttons = within(main()).getAllByRole('button')
    // Two download pairs, Show, Cancel and Delete my account.
    expect(buttons).toHaveLength(7)
    for (const element of buttons) {
      expect(element.classList.contains('button--secondary')).toBe(true)
      expect(element.classList.contains('button--primary')).toBe(false)
    }
  })

  it('test_fr_d1_download_buttons_have_the_download_icon_before_the_label', async () => {
    await renderSettings()

    for (const name of ['Download JSON', 'Download Markdown']) {
      const element = button(dataSection(), name)
      const icon = element.firstElementChild
      expect(icon?.tagName.toLowerCase()).toBe('svg')
      expect(icon?.getAttribute('class')).toContain('lucide-download')
      expect(icon?.getAttribute('aria-hidden')).toBe('true')
    }
  })
})

describe('downloads (FR-D1)', () => {
  it('test_fr_d1_download_json_saves_file_with_server_name', async () => {
    vi.useFakeTimers()
    const exported = jsonFile()
    exportJson.mockResolvedValue(exported)
    await renderSettings()

    await click(button(dataSection(), 'Download JSON'))

    expect(exportJson).toHaveBeenCalledTimes(1)
    expect(exportMarkdown).not.toHaveBeenCalled()
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(createObjectURL.mock.calls[0]?.[0]).toBe(exported.contents)
    expect(await savedContents()).toBe(JSON_BODY)
    expect(savedLinks).toEqual([{ href: BLOB_URL, download: 'winlog-export-2026-11-13.json', inPage: true }])
    // The temporary link is gone, and the URL is revoked once the browser has the file.
    expect(document.querySelector('a[download]')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(REVOKE_URL_AFTER_MS)
    })
    expect(revokeObjectURL).toHaveBeenCalledWith(BLOB_URL)
    // No message on the page.
    expect(dataMessages()).toEqual([])
    expect(button(dataSection(), 'Download JSON').disabled).toBe(false)
  })

  it('test_fr_d1_download_markdown_saves_file_with_server_name', async () => {
    vi.useFakeTimers()
    exportMarkdown.mockResolvedValue(markdownFile())
    await renderSettings()

    await click(button(dataSection(), 'Download Markdown'))

    expect(exportMarkdown).toHaveBeenCalledTimes(1)
    expect(exportJson).not.toHaveBeenCalled()
    expect(await savedContents()).toBe(MARKDOWN_BODY)
    expect(savedLinks).toEqual([{ href: BLOB_URL, download: 'winlog-export-2026-11-13.md', inPage: true }])
    expect(document.querySelector('a[download]')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(REVOKE_URL_AFTER_MS)
    })
    expect(revokeObjectURL).toHaveBeenCalledWith(BLOB_URL)
    expect(dataMessages()).toEqual([])
  })

  it('test_fr_d1_empty_account_gets_both_files', async () => {
    exportJson.mockResolvedValue(jsonFile(EMPTY_JSON_BODY))
    exportMarkdown.mockResolvedValue(markdownFile(EMPTY_MARKDOWN_BODY))
    await renderSettings()

    await click(button(dataSection(), 'Download JSON'))
    await click(button(dataSection(), 'Download Markdown'))

    expect(savedLinks.map((link) => link.download)).toEqual([
      'winlog-export-2026-11-13.json',
      'winlog-export-2026-11-13.md',
    ])
    expect(await savedContents(0)).toBe(EMPTY_JSON_BODY)
    expect(await savedContents(1)).toBe(EMPTY_MARKDOWN_BODY)
    expect(dataMessages()).toEqual([])
  })

  it('test_fr_d1_running_download_is_busy_and_sends_no_second_request', async () => {
    const json = deferred<DownloadedFile>()
    exportJson.mockReturnValue(json.promise)
    exportMarkdown.mockResolvedValue(markdownFile())
    await renderSettings()

    await click(button(dataSection(), 'Download JSON'))

    const busy = button(dataSection(), 'Downloading…')
    // Busy: announced as unavailable, but not natively disabled, so it keeps focus (#84).
    expect(busy.getAttribute('aria-disabled')).toBe('true')
    expect(busy.disabled).toBe(false)
    expect(busy.getAttribute('aria-busy')).toBe('true')
    expect(busy.querySelector('.spinner')).not.toBeNull()
    await click(busy)
    expect(exportJson).toHaveBeenCalledTimes(1)

    // The other download still works.
    const markdown = button(dataSection(), 'Download Markdown')
    expect(markdown.disabled).toBe(false)
    await click(markdown)
    expect(exportMarkdown).toHaveBeenCalledTimes(1)
    expect(savedLinks.map((link) => link.download)).toEqual(['winlog-export-2026-11-13.md'])

    // With the step open, both copies of "Download JSON" are busy.
    await openStep()
    expect(button(step(), 'Downloading…').getAttribute('aria-disabled')).toBe('true')
    expect(button(step(), 'Downloading…').disabled).toBe(false)
    await click(button(step(), 'Downloading…'))
    expect(exportJson).toHaveBeenCalledTimes(1)

    await act(async () => {
      json.resolve(jsonFile())
    })
    expect(button(dataSection(), 'Download JSON').disabled).toBe(false)
    expect(button(step(), 'Download JSON').disabled).toBe(false)
    expect(savedLinks.map((link) => link.download)).toEqual([
      'winlog-export-2026-11-13.md',
      'winlog-export-2026-11-13.json',
    ])
  })

  it('test_fr_d1_failed_download_shows_network_or_general_error', async () => {
    exportJson.mockRejectedValueOnce(new NetworkError())
    // A response without a file name: the client throws UnknownError.
    exportJson.mockRejectedValueOnce(new UnknownError('The export has no file name (Content-Disposition).', 200, null))
    exportMarkdown.mockRejectedValueOnce(new UnknownError('server text', 500, 'internal_error'))
    await renderSettings()

    await click(button(dataSection(), 'Download JSON'))
    expect(dataMessages()).toEqual([NETWORK_MESSAGE])
    expect(within(dataSection()).getByRole('alert').textContent).toBe(NETWORK_MESSAGE)
    expect(button(dataSection(), 'Download JSON').disabled).toBe(false)

    await click(button(dataSection(), 'Download JSON'))
    expect(dataMessages()).toEqual([GENERIC_MESSAGE])

    await click(button(dataSection(), 'Download Markdown'))
    expect(dataMessages()).toEqual([GENERIC_MESSAGE])
    expect(screen.queryByText(/server text/)).toBeNull()
    expect(screen.queryByText(/Content-Disposition/)).toBeNull()
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(savedLinks).toEqual([])
  })

  it('test_fr_d1_download_message_clears_when_the_next_download_starts', async () => {
    exportJson.mockRejectedValueOnce(new NetworkError())
    const markdown = deferred<DownloadedFile>()
    exportMarkdown.mockReturnValue(markdown.promise)
    await renderSettings()
    await click(button(dataSection(), 'Download JSON'))
    expect(dataMessages()).toEqual([NETWORK_MESSAGE])

    await click(button(dataSection(), 'Download Markdown'))

    expect(dataMessages()).toEqual([])
    await act(async () => {
      markdown.resolve(markdownFile())
    })
    expect(dataMessages()).toEqual([])
  })

  it('test_fr_d1_download_message_shows_once_under_the_pair_last_pressed', async () => {
    exportJson.mockRejectedValue(new NetworkError())
    await renderSettings()
    await openStep()

    await click(button(step(), 'Download JSON'))

    expect(messageTexts(step())).toEqual([NETWORK_MESSAGE])
    expect(dataMessages()).toEqual([])
    expect(screen.getAllByText(NETWORK_MESSAGE)).toHaveLength(1)

    await click(button(dataSection(), 'Download JSON'))
    expect(dataMessages()).toEqual([NETWORK_MESSAGE])
    expect(messageTexts(step())).toEqual([])
  })

  it('test_fr_d1_an_expired_login_while_downloading_opens_the_login_page', async () => {
    exportJson.mockImplementation(async () => {
      removeTestSession()
      registeredRedirect()()
      throw new NotAuthenticatedError('server text', 401)
    })
    const { router } = await renderSettings()

    await click(button(dataSection(), 'Download JSON'))

    expect(router.state.location.pathname).toBe('/login')
    expect(screen.queryByText('server text')).toBeNull()
  })

  it('test_fr_d1_waking_up_hint_after_10_seconds_of_downloading', async () => {
    vi.useFakeTimers()
    const json = deferred<DownloadedFile>()
    exportJson.mockReturnValue(json.promise)
    await renderSettings()
    await click(button(dataSection(), 'Download JSON'))

    act(() => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(within(dataSection()).getByText(WAKING_UP).closest('[role="status"]')).toBeTruthy()

    await act(async () => {
      json.resolve(jsonFile())
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
  })
})

describe('the confirmation step (FR-D2)', () => {
  it('test_fr_d2_delete_account_opens_the_step_with_focus_on_its_heading', async () => {
    await renderSettings()
    const opener = deleteAccountButton()
    expect(opener.firstElementChild?.getAttribute('class')).toContain('lucide-trash')

    await openStep()

    const heading = within(step()).getByRole('heading', { level: 3, name: 'Delete your account?' })
    expect(document.activeElement).toBe(heading)
    expect(heading.getAttribute('tabindex')).toBe('-1')
    // The button is hidden while the step is open; the step sits in its place.
    expect(within(accountSection()).queryByRole('button', { name: 'Delete account' })).toBeNull()
    expect(accountSection().contains(step())).toBe(true)
    expect(
      within(step()).getByText(
        "This permanently deletes your account and all your entries, tags and summaries. This can't be undone.",
      ),
    ).toBeTruthy()
    expect(within(step()).getByText('Download your data first if you want to keep it.')).toBeTruthy()
    expect(button(step(), 'Download JSON')).toBeTruthy()
    expect(button(step(), 'Download Markdown')).toBeTruthy()
    expect(deleteAccount).not.toHaveBeenCalled()
  })

  it('test_fr_d2_step_fields_have_password_toggle_and_no_autocorrect', async () => {
    await renderSettings()
    await openStep()

    const password = passwordInput()
    expect(password.type).toBe('password')
    expect(password.getAttribute('autocomplete')).toBe('current-password')
    await type(password, PASSWORD)
    await click(button(step(), 'Show password'))
    expect(passwordInput().type).toBe('text')
    await click(button(step(), 'Hide password'))
    expect(passwordInput().type).toBe('password')

    const confirm = confirmInput()
    expect(confirm.type).toBe('text')
    expect(confirm.getAttribute('autocomplete')).toBe('off')
    expect(confirm.getAttribute('autocorrect')).toBe('off')
    expect(confirm.getAttribute('autocapitalize')).toBe('none')
    expect(confirm.getAttribute('spellcheck')).toBe('false')
  })

  it('test_fr_d2_delete_requires_password_and_typed_confirmation', async () => {
    await renderSettings()
    await openStep()

    expect(deleteMyAccountButton().disabled).toBe(true)
    await type(confirmInput(), 'delete')
    expect(deleteMyAccountButton().disabled).toBe(true)
    await type(confirmInput(), '')
    await type(passwordInput(), PASSWORD)
    expect(deleteMyAccountButton().disabled).toBe(true)

    for (const word of ['delete', 'DELETE', 'Delete', '  delete  ', ' DeLeTe']) {
      await type(confirmInput(), word)
      expect(deleteMyAccountButton().disabled).toBe(false)
    }
    for (const word of ['delet', 'deleted', 'd elete', 'remove', 'delete it', '"delete"']) {
      await type(confirmInput(), word)
      expect(deleteMyAccountButton().disabled).toBe(true)
    }

    // Enter in a field sends nothing while the button is disabled.
    fireEvent.submit(confirmInput().form as HTMLFormElement)
    expect(deleteAccount).not.toHaveBeenCalled()
    await type(confirmInput(), 'delete')
    await type(passwordInput(), '')
    expect(deleteMyAccountButton().disabled).toBe(true)
  })

  it('test_fr_d2_cancel_closes_the_step_empties_the_fields_and_sends_nothing', async () => {
    await renderSettings()
    await openStep()
    await fillStep()
    await click(button(step(), 'Show password'))
    expect(passwordInput().type).toBe('text')

    await click(cancelButton())

    expect(queryStep()).toBeNull()
    expect(document.activeElement).toBe(deleteAccountButton())
    expect(deleteAccount).not.toHaveBeenCalled()

    await openStep()
    expect(passwordInput().value).toBe('')
    expect(passwordInput().type).toBe('password')
    expect(confirmInput().value).toBe('')
    expect(deleteMyAccountButton().disabled).toBe(true)
  })

  it('test_fr_d2_password_is_sent_exactly_as_typed', async () => {
    deleteAccount.mockImplementation(deleteClearingSession)
    await renderSettings()
    await openStep()

    await fillStep('  pass word  ', '  DELETE ')
    await submitDeletion()

    expect(deleteAccount).toHaveBeenCalledTimes(1)
    expect(deleteAccount).toHaveBeenCalledWith({ current_password: '  pass word  ' })
  })

  it('test_fr_d2_busy_while_deleting_and_a_second_tap_sends_nothing', async () => {
    const deletion = deferred<void>()
    deleteAccount.mockReturnValue(deletion.promise)
    await renderSettings()
    await openStep()
    await fillStep()

    await submitDeletion()

    const busy = deleteMyAccountButton()
    expect(busy.textContent).toBe('Deleting…')
    expect(busy.querySelector('.spinner')).not.toBeNull()
    // Busy: announced as unavailable, but not natively disabled, so it keeps focus (#84).
    expect(busy.getAttribute('aria-disabled')).toBe('true')
    expect(busy.disabled).toBe(false)
    expect(passwordInput().readOnly).toBe(true)
    expect(confirmInput().readOnly).toBe(true)
    expect(cancelButton().disabled).toBe(true)
    const downloads = allDownloadButtons()
    expect(downloads).toHaveLength(4)
    for (const element of downloads) {
      expect(element.disabled).toBe(true)
    }

    await click(busy)
    fireEvent.submit(passwordInput().form as HTMLFormElement)
    await click(cancelButton())
    for (const element of downloads) {
      await click(element)
    }
    expect(deleteAccount).toHaveBeenCalledTimes(1)
    expect(exportJson).not.toHaveBeenCalled()
    expect(exportMarkdown).not.toHaveBeenCalled()
    expect(queryStep()).not.toBeNull()
    // Typing does not change a read-only field.
    await type(passwordInput(), 'other')
    expect(passwordInput().value).toBe(PASSWORD)
    // Show/Hide stays usable; it sends nothing.
    await click(button(step(), 'Show password'))
    expect(passwordInput().type).toBe('text')

    await act(async () => {
      deletion.reject(new NetworkError())
    })
    expect(cancelButton().disabled).toBe(false)
    expect(passwordInput().readOnly).toBe(false)
  })

  it('test_fr_d2_wrong_password_shows_message_under_the_field', async () => {
    deleteAccount.mockRejectedValueOnce(new WrongPasswordError('server text', 403))
    deleteAccount.mockImplementationOnce(deleteClearingSession)
    const { router } = await renderSettings()
    await openStep()
    await fillStep('wrong-password')

    await submitDeletion()

    expect(messagesOf(passwordInput())).toEqual([WRONG_PASSWORD])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('true')
    expect(passwordInput().value).toBe('wrong-password')
    expect(confirmInput().value).toBe('delete')
    expect(document.activeElement).toBe(passwordInput())
    expect(screen.queryByText('server text')).toBeNull()
    expect(messageTexts(step())).toEqual([])
    expect(api.getSession()).not.toBeNull()
    expect(router.state.location.pathname).toBe('/settings')

    await type(passwordInput(), PASSWORD)
    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')

    // The user can try again.
    await submitDeletion()
    expect(deleteAccount).toHaveBeenCalledTimes(2)
    expect(deleteAccount).toHaveBeenLastCalledWith({ current_password: PASSWORD })
    expect(router.state.location.pathname).toBe('/login')
  })

  it('test_fr_d2_current_password_validation_error_shows_wrong_password', async () => {
    deleteAccount.mockRejectedValue(
      new ValidationError('server text', 422, [
        { field: 'current_password', reason: 'String should have at most 128 characters' },
      ]),
    )
    await renderSettings()
    await openStep()
    const tooLong = 'x'.repeat(129)
    await fillStep(tooLong)

    await submitDeletion()

    expect(messagesOf(passwordInput())).toEqual([WRONG_PASSWORD])
    expect(passwordInput().value).toBe(tooLong)
    expect(document.activeElement).toBe(passwordInput())
    expect(screen.queryByText(/128 characters/)).toBeNull()
    expect(messageTexts(step())).toEqual([])
    expect(api.getSession()).not.toBeNull()
  })

  it.each([
    ['a network error', new NetworkError(), NETWORK_MESSAGE],
    // #35: the contract's 409 `demo_account_not_deletable` has its own text in the step.
    ['the demo error', new DemoAccountNotDeletableError('server text', 409), DEMO_NOT_DELETABLE],
    [
      'another validation error',
      new ValidationError('server text', 422, [{ field: 'request', reason: 'Invalid JSON' }]),
      GENERIC_MESSAGE,
    ],
    ['a server error', new UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
  ])('test_fr_d2_%s_keeps_the_user_logged_in', async (_name, failure, message) => {
    deleteAccount.mockRejectedValueOnce(failure)
    deleteAccount.mockImplementationOnce(deleteClearingSession)
    const { router } = await renderSettings()
    await openStep()
    await fillStep()

    await submitDeletion()

    expect(messageTexts(step())).toEqual([message])
    expect(within(step()).getAllByRole('alert').some((alert) => alert.textContent === message)).toBe(true)
    expect(screen.queryByText('server text')).toBeNull()
    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().value).toBe(PASSWORD)
    expect(confirmInput().value).toBe('delete')
    expect(api.getSession()).not.toBeNull()
    expect(router.state.location.pathname).toBe('/settings')

    // The message goes when the next attempt starts, and the user can try again.
    await submitDeletion()
    expect(deleteAccount).toHaveBeenCalledTimes(2)
    expect(router.state.location.pathname).toBe('/login')
  })

  it.each([
    [900, 'Too many attempts. Please try again in 15 minutes.'],
    [30, 'Too many attempts. Please try again in 1 minute.'],
    [null, 'Too many attempts. Please try again later.'],
  ])('test_fr_a4_refused_deletion_with_retry_after_%s_shows_its_message_in_the_step', async (seconds, message) => {
    deleteAccount.mockRejectedValueOnce(new TooManyAttemptsError('server text', 429, seconds))
    deleteAccount.mockImplementationOnce(deleteClearingSession)
    const { router } = await renderSettings()
    await openStep()
    await fillStep()
    await submitDeletion()

    // In the step's error slot below the buttons, announced, in the error tone.
    // The step's last message slot is the one below Cancel and Delete my account.
    const slots = step().querySelectorAll<HTMLElement>('.settings-page__messages')
    const messages = slots[slots.length - 1]
    expect(messages.previousElementSibling?.contains(deleteMyAccountButton())).toBe(true)
    expect(messageTexts(messages)).toEqual([message])
    expect(messageTexts(step())).toEqual([message])
    expect(within(messages).getAllByRole('alert').some((alert) => alert.textContent === message)).toBe(true)
    expect(screen.queryByText('server text')).toBeNull()
    // The password was not checked: no wrong-password message and no focus move to the field.
    expect(messagesOf(passwordInput())).toEqual([])
    expect(screen.queryByText(WRONG_PASSWORD)).toBeNull()
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
    expect(document.activeElement).not.toBe(passwordInput())
    // Nothing is lost or disabled; the user stays logged in on this page.
    expect(passwordInput().value).toBe(PASSWORD)
    expect(confirmInput().value).toBe('delete')
    expect(deleteMyAccountButton().disabled).toBe(false)
    expect(api.getSession()).not.toBeNull()
    expect(router.state.location.pathname).toBe('/settings')

    // The message goes when the next attempt starts.
    await submitDeletion()
    expect(deleteAccount).toHaveBeenCalledTimes(2)
    expect(router.state.location.pathname).toBe('/login')
  })

  it('test_fr_a4_cancel_clears_the_too_many_attempts_message', async () => {
    deleteAccount.mockRejectedValueOnce(new TooManyAttemptsError('server text', 429, 900))
    await renderSettings()
    await openStep()
    await fillStep()
    await submitDeletion()
    expect(screen.getByText('Too many attempts. Please try again in 15 minutes.')).toBeTruthy()

    await click(cancelButton())

    expect(queryStep()).toBeNull()
    expect(screen.queryByText(/Too many attempts/)).toBeNull()
  })

  it('test_fr_d2_an_expired_login_while_deleting_opens_the_login_page', async () => {
    deleteAccount.mockImplementation(async () => {
      removeTestSession()
      registeredRedirect()()
      throw new NotAuthenticatedError('server text', 401)
    })
    const { router } = await renderSettings()
    await openStep()
    await fillStep()

    await submitDeletion()

    expect(router.state.location.pathname).toBe('/login')
    expect(screen.queryByText(DELETED_NOTICE)).toBeNull()
    expect(screen.queryByText('server text')).toBeNull()
  })

  it('test_fr_d2_waking_up_hint_after_10_seconds_of_deleting', async () => {
    vi.useFakeTimers()
    const deletion = deferred<void>()
    deleteAccount.mockReturnValue(deletion.promise)
    await renderSettings()
    await openStep()
    await fillStep()
    await submitDeletion()

    act(() => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(within(step()).getByText(WAKING_UP).closest('[role="status"]')).toBeTruthy()
    expect(within(dataSection()).queryByText(WAKING_UP)).toBeNull()

    await act(async () => {
      deletion.reject(new NetworkError())
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
  })
})

describe('after the deletion (FR-D2)', () => {
  it('test_fr_d2_successful_deletion_opens_login_with_account_deleted_notice', async () => {
    deleteAccount.mockImplementation(deleteClearingSession)
    login.mockReturnValue(new Promise(() => {}))
    const { router } = await renderSettings()
    await openStep()
    await fillStep()

    await submitDeletion()

    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.historyAction).toBe('REPLACE')
    expect(api.getSession()).toBeNull()
    expect(screen.getByRole('heading', { level: 1, name: 'Log in' })).toBeTruthy()
    const notice = screen.getByText(DELETED_NOTICE)
    expect(notice.closest('.form__notice')).not.toBeNull()
    expect(notice.closest('[role="status"]')).not.toBeNull()
    expect(screen.queryByText('Account created. Please log in.')).toBeNull()

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'bob@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: PASSWORD } })
    await click(screen.getByRole('button', { name: 'Log in' }))

    expect(screen.queryByText(DELETED_NOTICE)).toBeNull()
  })

  it('test_fr_d2_back_after_deletion_shows_no_app_page_and_login_opens_entries', async () => {
    deleteAccount.mockImplementation(deleteClearingSession)
    login.mockImplementation(async () => {
      saveSession({ token: 'other-token', expiresAt: '2099-01-01T00:00:00Z', demo: false })
      return { token: 'other-token', expires_at: '2099-01-01T00:00:00Z' }
    })
    const router = createMemoryRouter(routes, { initialEntries: ['/review', '/settings'], initialIndex: 1 })
    connectLoginRedirect(router)
    render(<RouterProvider router={router} />)
    await act(async () => {})
    await openStep()
    await fillStep()
    await submitDeletion()
    expect(router.state.location.pathname).toBe('/login')

    // Back: the previous app page opens /login, never the settings page.
    await act(async () => {
      await router.navigate(-1)
    })
    expect(router.state.location.pathname).toBe('/login')
    expect(screen.queryByRole('heading', { level: 1, name: 'Settings' })).toBeNull()
    await act(async () => {
      await router.navigate('/settings')
    })
    expect(router.state.location.pathname).toBe('/login')

    // Logging in from the login page the deletion opened goes to /, not /settings.
    const fresh = createMemoryRouter(routes, { initialEntries: ['/settings'] })
    connectLoginRedirect(fresh)
    cleanup()
    storeTestSession()
    render(<RouterProvider router={fresh} />)
    await act(async () => {})
    await openStep()
    await fillStep()
    await submitDeletion()
    expect(fresh.state.location.pathname).toBe('/login')
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'bob@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: PASSWORD } })
    await click(screen.getByRole('button', { name: 'Log in' }))

    expect(fresh.state.location.pathname).toBe('/')
  })
})

// The demo account on the settings page (FR-X1, #35).
describe('the settings page in a demo session (FR-X1)', () => {
  function storeDemoSession(): void {
    saveSession({ token: 'demo-token', expiresAt: '2099-01-01T00:00:00Z', demo: true })
  }

  it('test_fr_x1_settings_demo_account_section_has_one_sentence_and_no_delete_account', async () => {
    storeDemoSession()
    await renderSettings()

    const section = accountSection()
    expect(within(section).getByRole('heading', { level: 2, name: 'Account' })).toBeTruthy()
    expect(Array.from(section.querySelectorAll('p'), (p) => p.textContent)).toEqual([DEMO_NOT_DELETABLE])
    expect(within(section).queryByRole('button')).toBeNull()
    expect(within(section).queryByText('Deleting your account removes all of your data.')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Delete account' })).toBeNull()
    expect(queryStep()).toBeNull()
    expect(deleteAccount).not.toHaveBeenCalled()
  })

  it('test_fr_x1_settings_demo_your_data_is_unchanged_and_downloads_work', async () => {
    storeDemoSession()
    exportJson.mockResolvedValue(jsonFile())
    exportMarkdown.mockResolvedValue(markdownFile())
    await renderSettings()

    expect(
      within(dataSection()).getByText(
        'Download all your entries and summaries. JSON is complete and machine-readable. Markdown is easy to read.',
      ),
    ).toBeTruthy()
    await click(button(dataSection(), 'Download JSON'))
    await click(button(dataSection(), 'Download Markdown'))

    expect(exportJson).toHaveBeenCalledTimes(1)
    expect(exportMarkdown).toHaveBeenCalledTimes(1)
    expect(await savedContents(0)).toBe(JSON_BODY)
    expect(await savedContents(1)).toBe(MARKDOWN_BODY)
    expect(savedLinks.map((link) => link.download)).toEqual([
      'winlog-export-2026-11-13.json',
      'winlog-export-2026-11-13.md',
    ])
    expect(dataMessages()).toEqual([])
  })

  it('test_fr_x1_settings_demo_error_409_shows_the_demo_sentence_in_the_step', async () => {
    // A session without the demo flag, for example from before the flag was stored.
    deleteAccount.mockRejectedValue(new DemoAccountNotDeletableError('server text', 409))
    const { router } = await renderSettings()
    await openStep()
    await fillStep()

    await submitDeletion()

    expect(messageTexts(step())).toEqual([DEMO_NOT_DELETABLE])
    expect(within(step()).getAllByRole('alert').some((alert) => alert.textContent === DEMO_NOT_DELETABLE)).toBe(true)
    expect(screen.queryByText(GENERIC_MESSAGE)).toBeNull()
    expect(screen.queryByText('server text')).toBeNull()
    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().value).toBe(PASSWORD)
    expect(confirmInput().value).toBe('delete')
    expect(deleteMyAccountButton().textContent).toBe('Delete my account')
    expect(deleteMyAccountButton().disabled).toBe(false)
    expect(api.getSession()).not.toBeNull()
    expect(router.state.location.pathname).toBe('/settings')
  })

  it('test_fr_x1_settings_normal_session_keeps_delete_account', async () => {
    await renderSettings()

    expect(within(accountSection()).getByText('Deleting your account removes all of your data.')).toBeTruthy()
    expect(within(accountSection()).queryByText(DEMO_NOT_DELETABLE)).toBeNull()
    await openStep()
    expect(step()).toBeTruthy()
  })
})

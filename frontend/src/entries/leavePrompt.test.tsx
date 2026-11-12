import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import {
  ENTRY_ID,
  chip,
  entryFrom,
  openFold,
  save,
  storedEntry,
  tagInput,
  textArea,
  type,
} from '../test/entryForm.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession, storeTestSession } from '../test/session.ts'
import { setViewport } from '../test/viewport.ts'

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return {
    ...actual,
    createEntry: vi.fn(),
    getEntry: vi.fn(),
    updateEntry: vi.fn(),
    listTags: vi.fn(),
    logout: vi.fn(),
    setLoginRedirect: vi.fn(actual.setLoginRedirect),
  }
})

const createEntry = vi.mocked(api.createEntry)
const getEntry = vi.mocked(api.getEntry)
const updateEntry = vi.mocked(api.updateEntry)
const listTags = vi.mocked(api.listTags)
const logout = vi.mocked(api.logout)

const EDIT_PATH = `/entries/${ENTRY_ID}/edit`

function dialog(): HTMLDialogElement | null {
  const element = document.querySelector('dialog')
  return element instanceof HTMLDialogElement && element.open ? element : null
}

function openDialog(): HTMLDialogElement {
  const element = dialog()
  if (element === null) {
    throw new Error('the "Discard changes?" dialog is not open')
  }
  return element
}

async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element)
  })
}

function navLink(name: string): HTMLElement {
  return within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name })
}

async function renderAt(path: string) {
  const result = renderRoute(path)
  await act(async () => {})
  return result
}

/** The redirect the API client calls after a "not authenticated" response. */
function registeredRedirect(): () => void {
  const redirect = vi.mocked(api.setLoginRedirect).mock.lastCall?.[0]
  if (redirect === undefined) {
    throw new Error('setLoginRedirect was not called')
  }
  return redirect
}

beforeEach(() => {
  storeTestSession()
  listTags.mockResolvedValue({ tags: [] })
  createEntry.mockImplementation(async (body) => entryFrom(body))
  getEntry.mockResolvedValue(storedEntry())
  updateEntry.mockImplementation(async (id, body) => entryFrom(body, id))
  // Like the real client: logout removes the stored session.
  logout.mockImplementation(async () => removeTestSession())
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
})

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
})

describe('"Discard changes?" on the capture screen', () => {
  it('test_fr_e1_a_navigation_link_with_unsaved_changes_asks_first', async () => {
    const { router } = await renderAt('/entries/new')
    type(textArea(), 'Half-written win')

    await click(navLink('Review'))

    const prompt = openDialog()
    expect(within(prompt).getByRole('heading', { name: 'Discard changes?' })).toBeTruthy()
    expect(within(prompt).getByText("Your changes haven't been saved.")).toBeTruthy()
    const buttons = within(prompt).getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual(['Keep editing', 'Discard'])
    // Both secondary: Save entry stays the only filled plum element.
    expect(buttons.every((button) => button.className.includes('button--secondary'))).toBe(true)
    expect(document.activeElement).toBe(buttons[0])
    expect(router.state.location.pathname).toBe('/entries/new')

    // Keep editing: stay, everything is kept.
    await click(within(prompt).getByRole('button', { name: 'Keep editing' }))
    expect(dialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/entries/new')
    expect(textArea().value).toBe('Half-written win')

    // Discard: leave, nothing is saved.
    await click(navLink('Review'))
    await click(within(openDialog()).getByRole('button', { name: 'Discard' }))
    expect(router.state.location.pathname).toBe('/review')
    expect(createEntry).not.toHaveBeenCalled()
  })

  it('test_fr_e1_escape_keeps_editing', async () => {
    const { router } = await renderAt('/entries/new')
    fireEvent.click(chip('Learning'))
    await click(navLink('Review'))

    await act(async () => {
      fireEvent.keyDown(openDialog(), { key: 'Escape' })
    })

    expect(dialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/entries/new')
    expect(chip('Learning').getAttribute('aria-pressed')).toBe('true')
  })

  it('test_fr_e1_the_back_button_with_unsaved_changes_asks_first', async () => {
    const { router } = await renderAt('/')
    await act(async () => {
      await router.navigate('/entries/new')
    })
    type(textArea(), 'Something')

    await act(async () => {
      await router.navigate(-1)
    })

    expect(openDialog()).toBeTruthy()
    expect(router.state.location.pathname).toBe('/entries/new')
    await click(within(openDialog()).getByRole('button', { name: 'Discard' }))
    expect(router.state.location.pathname).toBe('/')
  })

  it('test_fr_e1_new_entry_in_the_sidebar_with_unsaved_changes_asks_first', async () => {
    setViewport('laptop')
    const { router } = await renderAt('/entries/new')
    type(textArea(), 'Draft')

    await click(navLink('New entry'))

    expect(openDialog()).toBeTruthy()
    await click(within(openDialog()).getByRole('button', { name: 'Discard' }))
    expect(router.state.location.pathname).toBe('/entries/new')
    expect(textArea().value).toBe('')
  })

  it('test_fr_e1_text_left_in_the_tag_input_counts_as_unsaved', async () => {
    await renderAt('/entries/new')
    openFold()
    type(tagInput(), 'half')

    await click(navLink('Review'))

    expect(openDialog()).toBeTruthy()
  })

  it('test_fr_e1_without_unsaved_changes_the_page_is_left_at_once', async () => {
    const { router } = await renderAt('/entries/new')
    type(textArea(), 'Typed')
    type(textArea(), '')

    await click(navLink('Review'))

    expect(dialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/review')
  })

  it('test_fr_e1_leaving_right_after_a_save_never_asks', async () => {
    const { router } = await renderAt('/entries/new')
    type(textArea(), 'Saved win')
    fireEvent.click(chip('Achievement'))
    await save()

    await click(navLink('Review'))

    expect(dialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/review')
  })

  it('test_fr_e1_closing_the_tab_with_unsaved_changes_shows_the_browser_prompt', async () => {
    await renderAt('/entries/new')
    const clean = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(clean)
    expect(clean.defaultPrevented).toBe(false)

    type(textArea(), 'Unsaved')
    const dirty = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirty)
    expect(dirty.defaultPrevented).toBe(true)
  })

  it('test_fr_e1_logging_out_never_asks', async () => {
    const { router } = await renderAt('/entries/new')
    type(textArea(), 'Unsaved')

    await click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('button', { name: 'More' }))
    await click(screen.getByRole('button', { name: 'Log out' }))

    expect(dialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('test_fr_e1_the_login_redirect_never_asks', async () => {
    const { router } = await renderAt('/entries/new')
    type(textArea(), 'Unsaved')
    // As the client does on a 401: remove the session, then call the redirect.
    removeTestSession()

    await act(async () => {
      registeredRedirect()()
    })

    expect(dialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/login')
  })
})

describe('"Discard changes?" on the edit page', () => {
  it('test_fr_e4_cancel_with_unsaved_changes_asks_first', async () => {
    const { router } = await renderAt(EDIT_PATH)
    type(textArea(), 'Changed text')

    await click(screen.getByRole('button', { name: 'Cancel' }))

    expect(openDialog()).toBeTruthy()
    expect(router.state.location.pathname).toBe(EDIT_PATH)
    await click(within(openDialog()).getByRole('button', { name: 'Keep editing' }))
    expect(textArea().value).toBe('Changed text')

    await click(screen.getByRole('button', { name: 'Cancel' }))
    await click(within(openDialog()).getByRole('button', { name: 'Discard' }))
    expect(router.state.location.pathname).toBe('/')
    expect(updateEntry).not.toHaveBeenCalled()
  })

  it('test_fr_e4_a_navigation_link_and_back_with_unsaved_changes_ask_first', async () => {
    const { router } = await renderAt('/')
    await act(async () => {
      await router.navigate(EDIT_PATH)
    })
    fireEvent.click(chip('Learning'))

    await click(navLink('Review'))
    expect(openDialog()).toBeTruthy()
    await click(within(openDialog()).getByRole('button', { name: 'Keep editing' }))

    await act(async () => {
      await router.navigate(-1)
    })
    expect(openDialog()).toBeTruthy()
    expect(router.state.location.pathname).toBe(EDIT_PATH)
  })

  it('test_fr_e4_the_loaded_entry_counts_as_unchanged', async () => {
    const { router } = await renderAt(EDIT_PATH)

    await click(screen.getByRole('button', { name: 'Cancel' }))

    expect(dialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/')
  })

  it('test_fr_e4_leaving_after_saving_never_asks', async () => {
    const { router } = await renderAt(EDIT_PATH)
    type(textArea(), 'Changed text')

    await save()

    expect(dialog()).toBeNull()
    expect(router.state.location.pathname).toBe('/')
  })
})

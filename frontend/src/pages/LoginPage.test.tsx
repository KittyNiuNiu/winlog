import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { saveSession } from '../api/session.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession } from '../test/session.ts'

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return { ...actual, login: vi.fn() }
})

const login = vi.mocked(api.login)

const EMAIL = 'alice@example.com'
const PASSWORD = 'Correct-Horse-7'
const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'

// Like the real client: a successful login stores the session.
async function loginStoringSession(): Promise<api.LoginResult> {
  saveSession({ token: 'new-token', expiresAt: '2099-01-01T00:00:00Z', demo: false })
  return { token: 'new-token', expires_at: '2099-01-01T00:00:00Z' }
}

function emailInput(): HTMLInputElement {
  return screen.getByLabelText('Email') as HTMLInputElement
}

function passwordInput(): HTMLInputElement {
  return screen.getByLabelText('Password') as HTMLInputElement
}

function submitButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^(Log in|Logging in…)$/ }) as HTMLButtonElement
}

function messagesOf(input: HTMLInputElement): string[] {
  const container = document.getElementById(`${input.id}-messages`)
  if (container === null) {
    throw new Error(`no messages for ${input.id}`)
  }
  return Array.from(container.querySelectorAll('p'), (p) => p.textContent ?? '')
}

function type(input: HTMLInputElement, value: string): void {
  fireEvent.change(input, { target: { value } })
}

function fillIn(email: string, password: string): void {
  type(emailInput(), email)
  type(passwordInput(), password)
}

async function submit(): Promise<void> {
  await act(async () => {
    fireEvent.click(submitButton())
  })
}

function formAlert(): HTMLElement {
  const alert = document.querySelector('.form__alert')
  if (!(alert instanceof HTMLElement)) {
    throw new Error('no form alert')
  }
  return alert
}

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
})

describe('login form (FR-A2)', () => {
  it('test_fr_a2_form_has_email_and_password_with_toggle', () => {
    renderRoute('/login')

    expect(screen.getByRole('heading', { level: 1, name: 'Log in' })).toBeTruthy()
    expect(emailInput().type).toBe('email')
    expect(passwordInput().type).toBe('password')
    expect(document.querySelectorAll('input')).toHaveLength(2)

    type(passwordInput(), PASSWORD)
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(passwordInput().type).toBe('text')
    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(passwordInput().type).toBe('password')
  })

  it('test_fr_a2_inputs_have_labels_and_autocomplete_for_password_managers', () => {
    renderRoute('/login')

    expect(emailInput().getAttribute('autocomplete')).toBe('email')
    expect(passwordInput().getAttribute('autocomplete')).toBe('current-password')
    expect(emailInput().labels?.[0]?.textContent).toBe('Email')
    expect(passwordInput().labels?.[0]?.textContent).toBe('Password')
  })

  it('test_fr_a2_links_to_the_registration_page', () => {
    renderRoute('/login')

    expect(screen.getByRole('link', { name: 'Create an account' }).getAttribute('href')).toBe('/register')
  })

  it('test_fr_a2_login_checks_no_password_rule', async () => {
    login.mockImplementation(loginStoringSession)
    renderRoute('/login')
    fillIn(EMAIL, 'short')
    fireEvent.blur(passwordInput())

    expect(messagesOf(passwordInput())).toEqual([])
    await submit()

    expect(login).toHaveBeenCalledWith({ email: EMAIL, password: 'short' })
  })

  it('test_fr_a2_empty_fields_show_messages_and_send_nothing', async () => {
    renderRoute('/login')

    await submit()

    expect(messagesOf(emailInput())).toEqual(['Enter your email address.'])
    expect(messagesOf(passwordInput())).toEqual(['Enter your password.'])
    expect(login).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(emailInput())
  })

  it('test_fr_a2_email_without_at_shows_its_message_when_leaving_the_field', () => {
    renderRoute('/login')
    type(emailInput(), 'alice')
    fireEvent.blur(emailInput())

    expect(messagesOf(emailInput())).toEqual(['Enter an email address with an @, such as name@example.com.'])
  })
})

describe('login errors (FR-A2)', () => {
  it('test_fr_a2_wrong_email_or_password_shows_one_message_above_the_form', async () => {
    login.mockRejectedValue(new api.InvalidCredentialsError('Wrong email or password.', 401))
    const { router } = renderRoute('/login')
    fillIn(EMAIL, 'Wrong-Password-1')

    await submit()

    const alert = formAlert()
    expect(alert.getAttribute('role')).toBe('alert')
    expect(alert.textContent).toBe('Wrong email or password.')
    // Above the form, not under a field.
    const form = document.querySelector('form') as HTMLFormElement
    expect(form.contains(alert)).toBe(false)
    expect(alert.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(messagesOf(emailInput())).toEqual([])
    expect(messagesOf(passwordInput())).toEqual([])
    expect(emailInput().getAttribute('aria-invalid')).toBe('false')
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
    expect(screen.getAllByText('Wrong email or password.')).toHaveLength(1)
    expect(router.state.location.pathname).toBe('/login')
    expect(api.getSession()).toBeNull()
  })

  it('test_fr_a2_server_validation_errors_show_under_the_field_they_name', async () => {
    login.mockRejectedValue(
      new api.ValidationError('The request has invalid fields.', 422, [
        { field: 'email', reason: 'value is not a valid email address: The part after the @-sign is not valid.' },
      ]),
    )
    renderRoute('/login')
    fillIn('alice@invalid', PASSWORD)

    await submit()

    expect(messagesOf(emailInput())).toEqual([
      'value is not a valid email address: The part after the @-sign is not valid.',
    ])
    expect(formAlert().textContent).toBe('')
  })

  it('test_fr_a2_network_error_shows_its_message_and_keeps_the_input', async () => {
    login.mockRejectedValue(new api.NetworkError())
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(formAlert().textContent).toBe(NETWORK_MESSAGE)
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
    expect(submitButton().disabled).toBe(false)
  })

  it.each([
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error')],
    ['a response that is not the contract', new api.UnknownError('Unexpected response (HTTP 502).', 502, null)],
  ])('test_fr_a2_%s_shows_a_generic_message_and_keeps_the_input', async (_case, error) => {
    login.mockRejectedValue(error)
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
  })

  it('test_fr_a2_message_is_cleared_on_the_next_attempt', async () => {
    login.mockRejectedValueOnce(new api.InvalidCredentialsError('Wrong email or password.', 401))
    login.mockReturnValueOnce(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    await submit()
    expect(formAlert().textContent).toBe('Wrong email or password.')

    await submit()

    expect(formAlert().textContent).toBe('')
  })
})

describe('where login leads (FR-A2)', () => {
  it('test_fr_a2_login_opens_entries_by_default', async () => {
    login.mockImplementation(loginStoringSession)
    const { router } = renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(login).toHaveBeenCalledWith({ email: EMAIL, password: PASSWORD })
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Entries' })).toBeTruthy()
  })

  it('test_fr_a2_login_returns_to_the_page_the_visitor_wanted', async () => {
    login.mockImplementation(loginStoringSession)
    const { router } = renderRoute('/summaries/42?tab=text#top')
    expect(router.state.location.pathname).toBe('/login')
    fillIn(EMAIL, PASSWORD)

    await submit()

    const { pathname, search, hash } = router.state.location
    expect(`${pathname}${search}${hash}`).toBe('/summaries/42?tab=text#top')
    expect(screen.getByRole('heading', { level: 1, name: 'Summary' })).toBeTruthy()
  })

  it('test_fr_a2_wanted_page_survives_a_failed_attempt', async () => {
    login.mockRejectedValueOnce(new api.InvalidCredentialsError('Wrong email or password.', 401))
    login.mockImplementationOnce(loginStoringSession)
    const { router } = renderRoute('/settings')
    fillIn(EMAIL, 'Wrong-Password-1')
    await submit()
    type(passwordInput(), PASSWORD)

    await submit()

    expect(router.state.location.pathname).toBe('/settings')
  })
})

describe('login while the request runs (FR-A2)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('test_fr_a2_button_is_disabled_and_shows_progress', async () => {
    login.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(submitButton().disabled).toBe(true)
    expect(submitButton().textContent).toBe('Logging in…')
    expect(submitButton().getAttribute('aria-busy')).toBe('true')
    fireEvent.click(submitButton())
    expect(login).toHaveBeenCalledTimes(1)
  })

  it('test_fr_a2_waking_up_hint_after_10_seconds', async () => {
    let finish: () => void = () => {}
    login.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () => void loginStoringSession().then(resolve)
        }),
    )
    const { router } = renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    await submit()

    await act(async () => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText(WAKING_UP).closest('[role="status"]')).toBeTruthy()
    expect(submitButton().disabled).toBe(true)

    await act(async () => {
      finish()
    })
    expect(router.state.location.pathname).toBe('/')
  })

  it('test_fr_a2_waking_up_hint_starts_again_for_the_next_request', async () => {
    login.mockRejectedValueOnce(new api.NetworkError())
    login.mockReturnValueOnce(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    await act(async () => {
      vi.advanceTimersByTime(5_000)
    })
    await submit()
    expect(formAlert().textContent).toBe(NETWORK_MESSAGE)

    await submit()
    await act(async () => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()
    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText(WAKING_UP)).toBeTruthy()
  })
})

describe('after a failed automatic login (FR-A1)', () => {
  it('shows "Account created. Please log in." until the next attempt', async () => {
    login.mockReturnValue(new Promise(() => {}))
    const { router } = renderRoute('/register')
    await act(async () => {
      await router.navigate('/login', { state: { accountCreated: true } })
    })
    expect(screen.getByText('Account created. Please log in.')).toBeTruthy()
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(screen.queryByText('Account created. Please log in.')).toBeNull()
  })
})

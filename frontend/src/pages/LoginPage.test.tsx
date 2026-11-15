import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { saveSession } from '../api/session.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { REASONS, REJECTED_ADDRESSES, expectNoServerText, validationError } from '../test/serverReasons.ts'
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
// The texts for a server validation error (design note on #72).
const EMAIL_TEXT = 'Enter a valid email address, such as name@example.com.'
const PASSWORD_TEXT = 'Check your password. It can have at most 128 characters.'

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
    // #72 replaces #26's "shown as the backend sends them": the field shows the app's own text.
    login.mockRejectedValue(validationError([{ field: 'email', reason: REASONS.emailNoPeriod }]))
    renderRoute('/login')
    fillIn('alice@invalid', PASSWORD)

    await submit()

    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(formAlert().textContent).toBe('')
    expectNoServerText()
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

// A server validation error shows the app's own text, never the server's (#72): one fixed
// text under each field the answer names, the generic alert above the form for any other
// field or none, and the cursor in the first field with a message (#84).
describe('server validation errors on login (FR-A2, #72)', () => {
  const LONG_PASSWORD = `Ab1!${'x'.repeat(125)}`

  function loginForm(): HTMLFormElement {
    return document.querySelector('form') as HTMLFormElement
  }

  function messagesRegion(input: HTMLInputElement): HTMLElement {
    return document.getElementById(`${input.id}-messages`) as HTMLElement
  }

  it('test_fr_a2_server_email_error_shows_the_apps_own_text', async () => {
    login.mockRejectedValue(validationError([{ field: 'email', reason: REASONS.emailNoPeriod }]))
    renderRoute('/login')
    fillIn('alice@invalid', PASSWORD)
    submitButton().focus()

    await submit()

    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    // As in #26: the error state, the live region and the link from the input to it.
    expect(emailInput().getAttribute('aria-invalid')).toBe('true')
    expect(emailInput().getAttribute('aria-describedby')).toBe('login-email-messages')
    expect(messagesRegion(emailInput()).getAttribute('role')).toBe('alert')
    expect(document.activeElement).toBe(emailInput())
    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
    expect(formAlert().textContent).toBe('')
    expect(emailInput().value).toBe('alice@invalid')
    expect(passwordInput().value).toBe(PASSWORD)
    expectNoServerText()
  })

  it.each(REJECTED_ADDRESSES)(
    'test_fr_a2_server_email_error_for_an_address_the_form_lets_through_shows_the_apps_own_text (%s)',
    async (_name, address, reason) => {
      login.mockRejectedValue(validationError([{ field: 'email', reason }]))
      renderRoute('/login')
      fillIn(address, PASSWORD)
      submitButton().focus()

      await submit()

      // The form's own check let it through: the request was sent.
      expect(login).toHaveBeenCalledWith({ email: address, password: PASSWORD })
      expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
      expect(document.activeElement).toBe(emailInput())
      expect(formAlert().textContent).toBe('')
      expect(emailInput().value).toBe(address)
      expectNoServerText()
    },
  )

  it('test_fr_a2_server_password_error_shows_the_apps_own_text', async () => {
    login.mockRejectedValue(validationError([{ field: 'password', reason: REASONS.loginPasswordTooLong }]))
    renderRoute('/login')
    fillIn(EMAIL, LONG_PASSWORD)
    fireEvent.blur(passwordInput())
    // Login checks no password rule and has no length limit in the browser (#26).
    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().hasAttribute('maxlength')).toBe(false)
    submitButton().focus()

    await submit()

    expect(login).toHaveBeenCalledWith({ email: EMAIL, password: LONG_PASSWORD })
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('true')
    expect(passwordInput().getAttribute('aria-describedby')).toBe('login-password-messages')
    expect(messagesRegion(passwordInput()).getAttribute('role')).toBe('alert')
    expect(document.activeElement).toBe(passwordInput())
    expect(messagesOf(emailInput())).toEqual([])
    expect(formAlert().textContent).toBe('')
    expect(passwordInput().value).toBe(LONG_PASSWORD)
    expectNoServerText()
  })

  it('test_fr_a2_server_password_unicode_error_shows_the_apps_own_text', async () => {
    login.mockRejectedValue(validationError([{ field: 'password', reason: REASONS.loginPasswordUnicode }]))
    renderRoute('/login')
    fillIn(EMAIL, 'Correct-Horse-\ud800')

    await submit()

    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(document.activeElement).toBe(passwordInput())
    expect(formAlert().textContent).toBe('')
    expectNoServerText()
  })

  it.each([
    ['test_fr_a2_server_body_error_shows_the_generic_alert', [{ field: 'body', reason: REASONS.body }]],
    ['test_fr_a2_server_validation_error_naming_no_field_shows_the_generic_alert', []],
  ])('%s', async (_name, fields) => {
    login.mockRejectedValue(validationError(fields))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    submitButton().focus()

    await submit()

    expect(formAlert().getAttribute('role')).toBe('alert')
    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    // No field is marked, and focus stays on "Log in" (#84).
    expect(messagesOf(emailInput())).toEqual([])
    expect(messagesOf(passwordInput())).toEqual([])
    expect(emailInput().getAttribute('aria-invalid')).toBe('false')
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
    expect(document.activeElement).toBe(submitButton())
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
    expectNoServerText()
  })

  it('test_fr_a2_server_error_naming_a_field_twice_shows_one_message', async () => {
    login.mockRejectedValue(
      validationError([
        { field: 'email', reason: REASONS.emailNoPeriod },
        { field: 'password', reason: REASONS.loginPasswordTooLong },
        { field: 'email', reason: REASONS.emailSpace },
        { field: 'password', reason: REASONS.loginPasswordUnicode },
      ]),
    )
    renderRoute('/login')
    fillIn('alice@invalid', LONG_PASSWORD)

    await submit()

    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(screen.getAllByText(EMAIL_TEXT)).toHaveLength(1)
    expect(screen.getAllByText(PASSWORD_TEXT)).toHaveLength(1)
    expectNoServerText()
  })

  it('test_fr_a2_server_email_and_password_errors_show_both_and_move_to_email', async () => {
    login.mockRejectedValue(
      validationError([
        { field: 'password', reason: REASONS.loginPasswordTooLong },
        { field: 'email', reason: REASONS.emailNoPeriod },
      ]),
    )
    renderRoute('/login')
    fillIn('alice@invalid', LONG_PASSWORD)
    // Enter in Password: the cursor leaves it for Email, and its blur check adds nothing.
    passwordInput().focus()

    await act(async () => {
      fireEvent.submit(loginForm())
    })

    expect(document.activeElement).toBe(emailInput())
    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(emailInput().getAttribute('aria-invalid')).toBe('true')
    expect(passwordInput().getAttribute('aria-invalid')).toBe('true')
    expect(formAlert().textContent).toBe('')
    expectNoServerText()
  })

  it('test_fr_a2_server_body_error_with_field_errors_shows_the_alert_and_the_field_messages', async () => {
    login.mockRejectedValue(
      validationError([
        { field: 'body', reason: REASONS.body },
        { field: 'password', reason: REASONS.loginPasswordTooLong },
      ]),
    )
    renderRoute('/login')
    fillIn(EMAIL, LONG_PASSWORD)
    submitButton().focus()

    await submit()

    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(messagesOf(emailInput())).toEqual([])
    expect(document.activeElement).toBe(passwordInput())
    expectNoServerText()
  })

  it('test_fr_a2_changing_a_field_removes_only_its_server_message', async () => {
    login.mockRejectedValue(
      validationError([
        { field: 'email', reason: REASONS.emailNoPeriod },
        { field: 'password', reason: REASONS.loginPasswordTooLong },
        { field: 'body', reason: REASONS.body },
      ]),
    )
    renderRoute('/login')
    fillIn('alice@invalid', LONG_PASSWORD)
    await submit()

    type(emailInput(), 'alice@example.com')

    expect(messagesOf(emailInput())).toEqual([])
    expect(emailInput().getAttribute('aria-invalid')).toBe('false')
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)

    type(passwordInput(), PASSWORD)

    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
  })

  it('test_fr_a2_server_messages_clear_on_the_next_submit_and_show_again', async () => {
    const error = validationError([
      { field: 'email', reason: REASONS.emailNoPeriod },
      { field: 'body', reason: REASONS.body },
    ])
    let fail: () => void = () => {}
    login.mockRejectedValueOnce(error)
    login.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          fail = () => reject(error)
        }),
    )
    renderRoute('/login')
    fillIn('alice@invalid', PASSWORD)
    await submit()
    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])

    await submit()

    expect(messagesOf(emailInput())).toEqual([])
    expect(formAlert().textContent).toBe('')
    await act(async () => {
      fail()
    })
    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    expectNoServerText()
  })
})

describe('too many login attempts (FR-A4)', () => {
  it.each([
    [900, 'Too many attempts. Please try again in 15 minutes.'],
    [61, 'Too many attempts. Please try again in 2 minutes.'],
    [60, 'Too many attempts. Please try again in 1 minute.'],
    [null, 'Too many attempts. Please try again later.'],
  ])('test_fr_a4_refused_login_with_retry_after_%s_shows_its_message_above_the_form', async (seconds, message) => {
    login.mockRejectedValue(new api.TooManyAttemptsError('server text', 429, seconds))
    const { router } = renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await submit()

    // In the form message slot, the place of "Wrong email or password.", announced.
    const alert = formAlert()
    expect(alert.textContent).toBe(message)
    expect(alert.getAttribute('role')).toBe('alert')
    expect(screen.getAllByText(message)).toHaveLength(1)
    expect(screen.queryByText('server text')).toBeNull()
    expect(screen.queryByText('Wrong email or password.')).toBeNull()
    expect(screen.queryByText(GENERIC_MESSAGE)).toBeNull()
    // Nothing is disabled and nothing typed is lost, so the user can try again later.
    expect(messagesOf(emailInput())).toEqual([])
    expect(messagesOf(passwordInput())).toEqual([])
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
    expect(submitButton().disabled).toBe(false)
    expect(router.state.location.pathname).toBe('/login')
    expect(api.getSession()).toBeNull()
  })

  it('test_fr_a4_pressing_log_in_again_shows_the_refreshed_wait', async () => {
    login.mockRejectedValueOnce(new api.TooManyAttemptsError('server text', 429, 900))
    login.mockRejectedValueOnce(new api.TooManyAttemptsError('server text', 429, 300))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await submit()
    expect(formAlert().textContent).toBe('Too many attempts. Please try again in 15 minutes.')

    await submit()
    expect(login).toHaveBeenCalledTimes(2)
    expect(formAlert().textContent).toBe('Too many attempts. Please try again in 5 minutes.')
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

    // Busy: announced as unavailable, but not natively disabled, so it keeps focus (#84).
    expect(submitButton().getAttribute('aria-disabled')).toBe('true')
    expect(submitButton().disabled).toBe(false)
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
    // Busy: announced as unavailable, but not natively disabled, so it keeps focus (#84).
    expect(submitButton().getAttribute('aria-disabled')).toBe('true')
    expect(submitButton().disabled).toBe(false)

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

// Keyboard focus after a login request (#84): a server validation error moves the cursor
// to the first field with a message, email before password; any other error leaves focus
// where it was, and the busy "Log in" keeps it.
describe('keyboard focus after a login request (FR-A2, #84)', () => {
  function loginForm(): HTMLFormElement {
    return document.querySelector('form') as HTMLFormElement
  }

  it.each([
    ['email', [{ field: 'email', reason: 'value is not a valid email address' }], emailInput],
    ['password', [{ field: 'password', reason: 'String should have at least 1 character' }], passwordInput],
    [
      'email before password',
      [
        { field: 'password', reason: 'String should have at least 1 character' },
        { field: 'email', reason: 'value is not a valid email address' },
      ],
      emailInput,
    ],
  ])('test_fr_a2_server_validation_moves_cursor_to_first_field (%s)', async (_case, fields, expected) => {
    login.mockRejectedValue(new api.ValidationError('The request has invalid fields.', 422, fields))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    submitButton().focus()

    await submit()

    expect(document.activeElement).toBe(expected())
  })

  it.each([
    ['wrong email or password', new api.InvalidCredentialsError('Wrong.', 401)],
    ['too many attempts', new api.TooManyAttemptsError('Too many.', 429, 120)],
    ['a network error', new api.NetworkError()],
    ['an unexpected error', new api.UnknownError('Internal error.', 500, 'internal_error')],
    ['a validation error naming no field', new api.ValidationError('The request has invalid fields.', 422, [])],
  ])('test_fr_a2_%s_leaves_focus_on_log_in', async (_case, error) => {
    let fail: () => void = () => {}
    login.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          fail = () => reject(error)
        }),
    )
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    submitButton().focus()

    await submit()
    expect(submitButton().textContent).toBe('Logging in…')
    // Focusable while busy: a natively disabled button would drop focus in a browser.
    expect(submitButton().disabled).toBe(false)
    expect(document.activeElement).toBe(submitButton())
    await act(async () => {
      fail()
    })

    expect(formAlert().textContent).not.toBe('')
    expect(document.activeElement).toBe(submitButton())
  })

  it('test_fr_a2_form_level_error_after_enter_in_a_field_leaves_focus_in_that_field', async () => {
    login.mockRejectedValue(new api.InvalidCredentialsError('Wrong.', 401))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    passwordInput().focus()

    await act(async () => {
      fireEvent.submit(loginForm())
    })

    expect(formAlert().textContent).toBe('Wrong email or password.')
    expect(document.activeElement).toBe(passwordInput())
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

// §9 Design, #77: the login and registration drawing above the heading, below the wordmark.
describe('the login illustration (§9 Design)', () => {
  function illustration(): SVGSVGElement {
    const svgs = document.querySelectorAll<SVGSVGElement>('svg.illustration')
    expect(svgs).toHaveLength(1)
    return svgs[0]
  }

  it('test_design_login_shows_the_login_illustration', () => {
    renderRoute('/login')

    const svg = illustration()
    expect(svg.classList.contains('illustration--login')).toBe(true)
    expect(svg.getAttribute('aria-hidden')).toBe('true')
    expect(svg.getAttribute('focusable')).toBe('false')
    // Below the wordmark, inside the page, right before the heading.
    const heading = screen.getByRole('heading', { level: 1, name: 'Log in' })
    expect(svg.nextElementSibling).toBe(heading)
    expect(screen.getByRole('main').contains(svg)).toBe(true)
    const wordmark = document.querySelector('.wordmark') as HTMLElement
    expect(wordmark.compareDocumentPosition(svg) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // Nothing new to read or reach: the same heading, button and link as before, plus
    // "Try the demo" below the form (#35).
    expect(screen.getAllByRole('heading').map((element) => element.textContent)).toEqual(['Log in'])
    expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual(['Show', 'Log in', 'Try the demo'])
  })

  it('test_design_login_illustration_stays_with_the_account_created_notice_and_an_error', async () => {
    login.mockRejectedValue(new api.InvalidCredentialsError('Wrong email or password.', 401))
    const { router } = renderRoute('/register')
    await act(async () => {
      await router.navigate('/login', { state: { accountCreated: true } })
    })
    expect(screen.getByText('Account created. Please log in.')).toBeTruthy()
    expect(illustration().nextElementSibling?.textContent).toBe('Log in')

    fillIn(EMAIL, 'wrong-password')
    await submit()

    expect(formAlert().textContent).toBe('Wrong email or password.')
    expect(illustration().nextElementSibling?.textContent).toBe('Log in')
  })
})

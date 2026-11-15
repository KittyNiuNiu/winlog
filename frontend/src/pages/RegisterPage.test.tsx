import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { saveSession } from '../api/session.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { REASONS, REJECTED_ADDRESSES, expectNoServerText, validationError } from '../test/serverReasons.ts'
import { removeTestSession } from '../test/session.ts'

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return { ...actual, register: vi.fn(), login: vi.fn() }
})

const register = vi.mocked(api.register)
const login = vi.mocked(api.login)

const EMAIL = 'alice@example.com'
const PASSWORD = 'Correct-Horse-7'
const HINT = 'At least 10 characters, including an uppercase letter, a number and a special character.'
const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'
// The texts for a server validation error (design note on #72).
const EMAIL_TEXT = 'Enter a valid email address, such as name@example.com.'
const PASSWORD_TEXT = "This password can't be used. Choose a different one."

const user = { id: '0b6f3c1e-1d7a-4c5e-9f0a-2b3c4d5e6f70', email: EMAIL, created_at: '2026-11-10T10:00:00Z' }

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
  return screen.getByRole('button', { name: /Create account|Creating account/ }) as HTMLButtonElement
}

/** The messages under a field: the element its aria-describedby names for messages. */
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

describe('registration form (FR-A1)', () => {
  it('test_fr_a1_form_has_email_password_with_toggle_and_hint_but_no_repeat_field', () => {
    renderRoute('/register')

    expect(screen.getByRole('heading', { level: 1, name: 'Create an account' })).toBeTruthy()
    expect(emailInput().type).toBe('email')
    expect(passwordInput().type).toBe('password')
    expect(screen.getByText(HINT)).toBeTruthy()
    // The hint is read with the password field.
    expect(passwordInput().getAttribute('aria-describedby')).toContain(screen.getByText(HINT).id)
    // Exactly two inputs: no "repeat password" field.
    expect(document.querySelectorAll('input')).toHaveLength(2)
    expect(screen.queryByLabelText(/repeat|confirm/i)).toBeNull()
  })

  it('test_fr_a1_password_toggle_shows_and_hides_the_password', () => {
    renderRoute('/register')
    type(passwordInput(), PASSWORD)

    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(passwordInput().type).toBe('text')
    expect(passwordInput().value).toBe(PASSWORD)

    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(passwordInput().type).toBe('password')
  })

  it('test_fr_a1_inputs_have_labels_and_autocomplete_for_password_managers', () => {
    renderRoute('/register')

    expect(emailInput().getAttribute('autocomplete')).toBe('email')
    expect(passwordInput().getAttribute('autocomplete')).toBe('new-password')
    // Visible labels: real <label> elements.
    expect(emailInput().labels?.[0]?.textContent).toBe('Email')
    expect(passwordInput().labels?.[0]?.textContent).toBe('Password')
  })

  it('test_fr_a1_links_to_the_login_page', () => {
    renderRoute('/register')

    expect(screen.getByRole('link', { name: 'Log in' }).getAttribute('href')).toBe('/login')
  })
})

describe('registration checks before sending (FR-A1)', () => {
  it.each([
    ['missing', '', 'Enter your email address.'],
    ['only spaces', '   ', 'Enter your email address.'],
    ['without @', 'alice.example.com', 'Enter an email address with an @, such as name@example.com.'],
  ])('test_fr_a1_email_%s_shows_its_message_when_leaving_the_field', (_case, email, message) => {
    renderRoute('/register')
    type(emailInput(), email)

    expect(messagesOf(emailInput())).toEqual([])
    fireEvent.blur(emailInput())

    expect(messagesOf(emailInput())).toEqual([message])
    expect(emailInput().getAttribute('aria-invalid')).toBe('true')
  })

  it.each([
    ['too short', 'Abcdefg1!', 'Use at least 10 characters.'],
    ['too long', `Ab1!${'x'.repeat(125)}`, 'Use at most 128 characters.'],
    ['no uppercase letter', 'abcdefgh1!', 'Add an uppercase letter.'],
    ['no number', 'Abcdefghi!', 'Add a number (0–9).'],
    ['no special character', 'Abcdefghi1', 'Add a special character, such as ! # - or a space.'],
  ])('test_fr_a1_password_%s_shows_its_message', async (_case, password, message) => {
    renderRoute('/register')
    type(emailInput(), EMAIL)
    type(passwordInput(), password)

    fireEvent.blur(passwordInput())
    expect(messagesOf(passwordInput())).toEqual([message])

    await submit()
    expect(messagesOf(passwordInput())).toEqual([message])
    expect(register).not.toHaveBeenCalled()
  })

  it('test_fr_a1_password_shows_every_requirement_it_breaks', () => {
    renderRoute('/register')
    type(passwordInput(), 'abc')
    fireEvent.blur(passwordInput())

    expect(messagesOf(passwordInput())).toEqual([
      'Use at least 10 characters.',
      'Add an uppercase letter.',
      'Add a number (0–9).',
      'Add a special character, such as ! # - or a space.',
    ])
  })

  it('test_fr_a1_submit_shows_errors_and_sends_nothing', async () => {
    renderRoute('/register')

    await submit()

    expect(messagesOf(emailInput())).toEqual(['Enter your email address.'])
    expect(messagesOf(passwordInput())).toContain('Use at least 10 characters.')
    expect(register).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(emailInput())
  })

  it('test_fr_a1_messages_update_as_the_user_fixes_the_field', () => {
    renderRoute('/register')
    type(passwordInput(), 'abcdefgh1!')
    fireEvent.blur(passwordInput())
    expect(messagesOf(passwordInput())).toEqual(['Add an uppercase letter.'])

    type(passwordInput(), 'Abcdefgh1!')

    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
  })

  it('test_fr_a1_field_messages_are_announced_to_screen_readers', () => {
    renderRoute('/register')
    fireEvent.blur(emailInput())

    const container = document.getElementById(`${emailInput().id}-messages`)
    expect(container?.getAttribute('role')).toBe('alert')
    expect(emailInput().getAttribute('aria-describedby')).toContain(container?.id)
  })

  it('test_fr_a1_login_rule_is_not_applied_to_a_valid_password', async () => {
    register.mockResolvedValue(user)
    login.mockImplementation(loginStoringSession)
    renderRoute('/register')
    fillIn(EMAIL, 'Äbcdefgh1-')

    await submit()

    expect(register).toHaveBeenCalledWith({ email: EMAIL, password: 'Äbcdefgh1-' })
  })
})

describe('registration errors from the server (FR-A1)', () => {
  it('test_fr_a1_email_already_registered_shows_under_email_with_login_link', async () => {
    register.mockRejectedValue(new api.EmailAlreadyRegisteredError('This email is already registered.', 409))
    const { router } = renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(messagesOf(emailInput())).toEqual(['Email already registered. Log in instead'])
    const container = document.getElementById(`${emailInput().id}-messages`) as HTMLElement
    const link = within(container).getByRole('link', { name: 'Log in instead' })
    expect(link.getAttribute('href')).toBe('/login')
    expect(login).not.toHaveBeenCalled()
    expect(router.state.location.pathname).toBe('/register')

    await act(async () => {
      fireEvent.click(link)
    })
    expect(router.state.location.pathname).toBe('/login')
  })

  it('test_fr_a1_email_already_registered_clears_when_the_email_changes', async () => {
    register.mockRejectedValue(new api.EmailAlreadyRegisteredError('This email is already registered.', 409))
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)
    await submit()

    type(emailInput(), 'bob@example.com')

    expect(messagesOf(emailInput())).toEqual([])
  })

  it('test_fr_a1_server_validation_errors_show_under_the_field_they_name', async () => {
    // #72 replaces #26's "shown as the backend sends them": each field shows the app's own text.
    register.mockRejectedValue(
      validationError([
        { field: 'email', reason: REASONS.emailNoPeriod },
        { field: 'password', reason: REASONS.registerPasswordSurrogate },
      ]),
    )
    renderRoute('/register')
    fillIn('alice@invalid', PASSWORD)

    await submit()

    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(formAlert().textContent).toBe('')
    expectNoServerText()
  })

  it('test_fr_a1_server_validation_error_for_another_field_shows_above_the_form', async () => {
    // #72: the generic alert, never the server's reason.
    register.mockRejectedValue(validationError([{ field: 'request', reason: 'Invalid JSON.' }]))
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    expect(screen.queryByText(/Invalid JSON/)).toBeNull()
    expectNoServerText()
  })

  it('test_fr_a1_network_error_shows_its_message_and_keeps_the_input', async () => {
    register.mockRejectedValue(new api.NetworkError())
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(formAlert().getAttribute('role')).toBe('alert')
    expect(formAlert().textContent).toBe(NETWORK_MESSAGE)
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
    expect(submitButton().disabled).toBe(false)
  })

  it('test_fr_a1_unexpected_error_shows_a_generic_message_and_keeps_the_input', async () => {
    register.mockRejectedValue(new api.UnknownError('Internal error.', 500, 'internal_error'))
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
  })

  it('test_fr_a1_request_too_large_shows_a_generic_message_and_keeps_the_input', async () => {
    // #88: a 413 `request_too_large` is an UnknownError, shown as the generic text.
    register.mockRejectedValue(new api.UnknownError('The request body is too large.', 413, 'request_too_large'))
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    expect(screen.queryByText(/too large/)).toBeNull()
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
  })
})

// A server validation error shows the app's own text, never the server's (#72): one fixed
// text under each field the answer names, the generic alert above the form for any other
// field or none, and the cursor in the first field with a message (#84).
describe('server validation errors on registration (FR-A1, #72)', () => {
  // Passes the form's rule: the unpaired surrogate counts as a special character there.
  const SURROGATE_PASSWORD = `${PASSWORD}\ud800`

  function registerForm(): HTMLFormElement {
    return document.querySelector('form') as HTMLFormElement
  }

  function messagesRegion(input: HTMLInputElement): HTMLElement {
    return document.getElementById(`${input.id}-messages`) as HTMLElement
  }

  it('test_fr_a1_server_email_error_shows_the_apps_own_text', async () => {
    register.mockRejectedValue(validationError([{ field: 'email', reason: REASONS.emailNoPeriod }]))
    renderRoute('/register')
    fillIn('alice@invalid', PASSWORD)
    submitButton().focus()

    await submit()

    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    // As in #26: the error state, the live region and the link from the input to it.
    expect(emailInput().getAttribute('aria-invalid')).toBe('true')
    expect(emailInput().getAttribute('aria-describedby')).toBe('register-email-messages')
    expect(messagesRegion(emailInput()).getAttribute('role')).toBe('alert')
    expect(document.activeElement).toBe(emailInput())
    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
    expect(formAlert().textContent).toBe('')
    expect(login).not.toHaveBeenCalled()
    expect(emailInput().value).toBe('alice@invalid')
    expect(passwordInput().value).toBe(PASSWORD)
    expectNoServerText()
  })

  it.each(REJECTED_ADDRESSES)(
    'test_fr_a1_server_email_error_for_an_address_the_form_lets_through_shows_the_apps_own_text (%s)',
    async (_name, address, reason) => {
      register.mockRejectedValue(validationError([{ field: 'email', reason }]))
      renderRoute('/register')
      fillIn(address, PASSWORD)
      submitButton().focus()

      await submit()

      // The form's own check let it through: the request was sent.
      expect(register).toHaveBeenCalledWith({ email: address, password: PASSWORD })
      expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
      expect(document.activeElement).toBe(emailInput())
      expect(formAlert().textContent).toBe('')
      expect(emailInput().value).toBe(address)
      expectNoServerText()
    },
  )

  it('test_fr_a1_server_password_error_shows_the_apps_own_text', async () => {
    register.mockRejectedValue(validationError([{ field: 'password', reason: REASONS.registerPasswordSurrogate }]))
    renderRoute('/register')
    fillIn(EMAIL, SURROGATE_PASSWORD)
    submitButton().focus()

    await submit()

    expect(register).toHaveBeenCalledWith({ email: EMAIL, password: SURROGATE_PASSWORD })
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('true')
    // The hint first, then the message, in visual order.
    expect(passwordInput().getAttribute('aria-describedby')).toBe('register-password-hint register-password-messages')
    expect(messagesRegion(passwordInput()).getAttribute('role')).toBe('alert')
    expect(screen.getByText(HINT)).toBeTruthy()
    expect(document.activeElement).toBe(passwordInput())
    expect(messagesOf(emailInput())).toEqual([])
    expect(formAlert().textContent).toBe('')
    expect(passwordInput().value).toBe(SURROGATE_PASSWORD)
    expectNoServerText()
  })

  it.each([
    ['test_fr_a1_server_body_error_shows_the_generic_alert', [{ field: 'body', reason: REASONS.body }]],
    ['test_fr_a1_server_validation_error_naming_no_field_shows_the_generic_alert', []],
  ])('%s', async (_name, fields) => {
    register.mockRejectedValue(validationError(fields))
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)
    submitButton().focus()

    await submit()

    expect(formAlert().getAttribute('role')).toBe('alert')
    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    // No field is marked, and focus stays on "Create account" (#84).
    expect(messagesOf(emailInput())).toEqual([])
    expect(messagesOf(passwordInput())).toEqual([])
    expect(emailInput().getAttribute('aria-invalid')).toBe('false')
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
    expect(document.activeElement).toBe(submitButton())
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
    expectNoServerText()
  })

  it('test_fr_a1_server_error_naming_a_field_twice_shows_one_message', async () => {
    register.mockRejectedValue(
      validationError([
        { field: 'email', reason: REASONS.emailNoPeriod },
        { field: 'password', reason: REASONS.registerPasswordSurrogate },
        { field: 'email', reason: REASONS.emailSpecialUse },
        { field: 'password', reason: REASONS.registerPasswordSurrogate },
      ]),
    )
    renderRoute('/register')
    fillIn('alice@invalid', SURROGATE_PASSWORD)

    await submit()

    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(screen.getAllByText(EMAIL_TEXT)).toHaveLength(1)
    expect(screen.getAllByText(PASSWORD_TEXT)).toHaveLength(1)
    expectNoServerText()
  })

  it('test_fr_a1_server_email_and_password_errors_show_both_and_move_to_email', async () => {
    register.mockRejectedValue(
      validationError([
        { field: 'password', reason: REASONS.registerPasswordSurrogate },
        { field: 'email', reason: REASONS.emailNoPeriod },
      ]),
    )
    renderRoute('/register')
    fillIn('alice@invalid', SURROGATE_PASSWORD)
    // Enter in Password: the cursor leaves it for Email, and its blur check adds nothing.
    passwordInput().focus()

    await act(async () => {
      fireEvent.submit(registerForm())
    })

    expect(document.activeElement).toBe(emailInput())
    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(emailInput().getAttribute('aria-invalid')).toBe('true')
    expect(passwordInput().getAttribute('aria-invalid')).toBe('true')
    expect(formAlert().textContent).toBe('')
    expectNoServerText()
  })

  it('test_fr_a1_server_body_error_with_field_errors_shows_the_alert_and_the_field_messages', async () => {
    register.mockRejectedValue(
      validationError([
        { field: 'email', reason: REASONS.emailSpace },
        { field: 'body', reason: REASONS.body },
      ]),
    )
    renderRoute('/register')
    fillIn('alice @example.com', PASSWORD)
    submitButton().focus()

    await submit()

    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(messagesOf(passwordInput())).toEqual([])
    expect(document.activeElement).toBe(emailInput())
    expectNoServerText()
  })

  it('test_fr_a1_changing_a_field_removes_only_its_server_message', async () => {
    register.mockRejectedValue(
      validationError([
        { field: 'email', reason: REASONS.emailNoPeriod },
        { field: 'password', reason: REASONS.registerPasswordSurrogate },
        { field: 'body', reason: REASONS.body },
      ]),
    )
    renderRoute('/register')
    fillIn('alice@invalid', SURROGATE_PASSWORD)
    await submit()

    type(passwordInput(), PASSWORD)

    expect(messagesOf(passwordInput())).toEqual([])
    expect(passwordInput().getAttribute('aria-invalid')).toBe('false')
    expect(messagesOf(emailInput())).toEqual([EMAIL_TEXT])
    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)

    type(emailInput(), EMAIL)

    expect(messagesOf(emailInput())).toEqual([])
    expect(emailInput().getAttribute('aria-invalid')).toBe('false')
    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
  })

  it('test_fr_a1_server_messages_clear_on_the_next_submit_and_show_again', async () => {
    const error = validationError([
      { field: 'password', reason: REASONS.registerPasswordSurrogate },
      { field: 'body', reason: REASONS.body },
    ])
    let fail: () => void = () => {}
    register.mockRejectedValueOnce(error)
    register.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          fail = () => reject(error)
        }),
    )
    renderRoute('/register')
    fillIn(EMAIL, SURROGATE_PASSWORD)
    await submit()
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])

    await submit()

    expect(messagesOf(passwordInput())).toEqual([])
    expect(formAlert().textContent).toBe('')
    await act(async () => {
      fail()
    })
    expect(messagesOf(passwordInput())).toEqual([PASSWORD_TEXT])
    expect(formAlert().textContent).toBe(GENERIC_MESSAGE)
    expectNoServerText()
  })
})

describe('registration followed by login (FR-A1)', () => {
  it('test_fr_a1_registration_logs_in_with_the_same_details_and_opens_entries', async () => {
    register.mockResolvedValue(user)
    login.mockImplementation(loginStoringSession)
    const { router } = renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(register).toHaveBeenCalledWith({ email: EMAIL, password: PASSWORD })
    expect(login).toHaveBeenCalledWith({ email: EMAIL, password: PASSWORD })
    expect(register.mock.invocationCallOrder[0]).toBeLessThan(login.mock.invocationCallOrder[0])
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Entries' })).toBeTruthy()
  })

  it.each([
    ['a network error', new api.NetworkError()],
    ['wrong credentials', new api.InvalidCredentialsError('Wrong email or password.', 401)],
    ['a server error', new api.UnknownError('Internal error.', 500, 'internal_error')],
  ])('test_fr_a1_failed_automatic_login_after_%s_opens_login_with_account_created', async (_case, error) => {
    register.mockResolvedValue(user)
    login.mockRejectedValue(error)
    const { router } = renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(router.state.location.pathname).toBe('/login')
    expect(screen.getByRole('heading', { level: 1, name: 'Log in' })).toBeTruthy()
    expect(screen.getByText('Account created. Please log in.').getAttribute('role')).toBe('status')
  })
})

describe('registration while the request runs (FR-A1)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('test_fr_a1_button_is_disabled_and_shows_progress', async () => {
    register.mockReturnValue(new Promise(() => {}))
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    // Busy: announced as unavailable, but not natively disabled, so it keeps focus (#84).
    expect(submitButton().getAttribute('aria-disabled')).toBe('true')
    expect(submitButton().disabled).toBe(false)
    expect(submitButton().textContent).toBe('Creating account…')
    fireEvent.click(submitButton())
    expect(register).toHaveBeenCalledTimes(1)
  })

  it('test_fr_a1_waking_up_hint_after_10_seconds', async () => {
    register.mockResolvedValue(user)
    // The automatic login is slow, as when the server is waking up.
    let finishLogin: () => void = () => {}
    login.mockImplementation(
      () =>
        new Promise((resolve) => {
          finishLogin = () => void loginStoringSession().then(resolve)
        }),
    )
    const { router } = renderRoute('/register')
    fillIn(EMAIL, PASSWORD)
    await submit()

    await act(async () => {
      vi.advanceTimersByTime(9_999)
    })
    expect(screen.queryByText(WAKING_UP)).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByText(WAKING_UP)).toBeTruthy()

    await act(async () => {
      finishLogin()
    })
    expect(router.state.location.pathname).toBe('/')
    expect(screen.queryByText(WAKING_UP)).toBeNull()
  })

  it('test_fr_a1_waking_up_hint_goes_away_when_the_request_fails', async () => {
    let fail: () => void = () => {}
    register.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          fail = () => reject(new api.NetworkError())
        }),
    )
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)
    await submit()
    await act(async () => {
      vi.advanceTimersByTime(10_000)
    })
    expect(screen.getByText(WAKING_UP)).toBeTruthy()

    await act(async () => {
      fail()
    })

    expect(screen.queryByText(WAKING_UP)).toBeNull()
    expect(formAlert().textContent).toBe(NETWORK_MESSAGE)
  })
})

// §9 Design, #77: the same drawing as on the login page, above the heading.
// Keyboard focus after a registration request (#84): a server validation error moves the
// cursor to the first field with a message, email before password; an email already in use
// moves it to the email field (#26); any other error leaves focus where it was.
describe('keyboard focus after a registration request (FR-A1, #84)', () => {
  it.each([
    ['email', [{ field: 'email', reason: 'value is not a valid email address' }], emailInput],
    ['password', [{ field: 'password', reason: 'String should have at most 128 characters' }], passwordInput],
    [
      'email before password',
      [
        { field: 'password', reason: 'String should have at most 128 characters' },
        { field: 'email', reason: 'value is not a valid email address' },
      ],
      emailInput,
    ],
  ])('test_fr_a1_server_validation_moves_cursor_to_first_field (%s)', async (_case, fields, expected) => {
    register.mockRejectedValue(new api.ValidationError('The request has invalid fields.', 422, fields))
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)
    submitButton().focus()

    await submit()

    expect(document.activeElement).toBe(expected())
  })

  it('test_fr_a1_email_already_registered_moves_cursor_to_email', async () => {
    register.mockRejectedValue(new api.EmailAlreadyRegisteredError('This email is already registered.', 409))
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)
    submitButton().focus()

    await submit()

    expect(document.activeElement).toBe(emailInput())
  })

  it.each([
    ['a network error', new api.NetworkError()],
    ['an unexpected error', new api.UnknownError('Internal error.', 500, 'internal_error')],
    ['a validation error naming another field', new api.ValidationError('Invalid.', 422, [{ field: 'body', reason: 'x' }])],
  ])('test_fr_a1_%s_leaves_focus_on_create_account', async (_case, error) => {
    let fail: () => void = () => {}
    register.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          fail = () => reject(error)
        }),
    )
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)
    submitButton().focus()

    await submit()
    expect(submitButton().textContent).toBe('Creating account…')
    // Focusable while busy: a natively disabled button would drop focus in a browser.
    expect(submitButton().disabled).toBe(false)
    expect(document.activeElement).toBe(submitButton())
    await act(async () => {
      fail()
    })

    expect(formAlert().textContent).not.toBe('')
    expect(document.activeElement).toBe(submitButton())
  })
})

describe('the login illustration on registration (§9 Design)', () => {
  function illustration(): SVGSVGElement {
    const svgs = document.querySelectorAll<SVGSVGElement>('svg.illustration')
    expect(svgs).toHaveLength(1)
    return svgs[0]
  }

  it('test_design_register_shows_the_login_illustration', () => {
    renderRoute('/register')

    const svg = illustration()
    expect(svg.classList.contains('illustration--login')).toBe(true)
    expect(svg.getAttribute('aria-hidden')).toBe('true')
    expect(svg.getAttribute('focusable')).toBe('false')
    const heading = screen.getByRole('heading', { level: 1, name: 'Create an account' })
    expect(svg.nextElementSibling).toBe(heading)
    expect(screen.getByRole('main').contains(svg)).toBe(true)
    // Nothing new to read or reach.
    expect(screen.getAllByRole('heading').map((element) => element.textContent)).toEqual(['Create an account'])
    expect(screen.getAllByRole('button').map((button) => button.textContent)).toEqual(['Show', 'Create account'])
  })

  it('test_design_register_illustration_stays_with_an_error', async () => {
    register.mockRejectedValue(new api.NetworkError())
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(formAlert().textContent).toBe(NETWORK_MESSAGE)
    expect(illustration().nextElementSibling?.textContent).toBe('Create an account')
  })
})

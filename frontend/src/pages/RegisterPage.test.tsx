import { act, fireEvent, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { saveSession } from '../api/session.ts'
import { renderRoute } from '../test/renderRoute.tsx'
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
    register.mockRejectedValue(
      new api.ValidationError('The request has invalid fields.', 422, [
        { field: 'email', reason: 'value is not a valid email address: The part after the @-sign is not valid.' },
        { field: 'password', reason: 'Password contains an invalid character (an unpaired surrogate).' },
      ]),
    )
    renderRoute('/register')
    fillIn('alice@invalid', PASSWORD)

    await submit()

    expect(messagesOf(emailInput())).toEqual([
      'value is not a valid email address: The part after the @-sign is not valid.',
    ])
    expect(messagesOf(passwordInput())).toEqual(['Password contains an invalid character (an unpaired surrogate).'])
    expect(formAlert().textContent).toBe('')
  })

  it('test_fr_a1_server_validation_error_for_another_field_shows_above_the_form', async () => {
    register.mockRejectedValue(
      new api.ValidationError('The request has invalid fields.', 422, [{ field: 'request', reason: 'Invalid JSON.' }]),
    )
    renderRoute('/register')
    fillIn(EMAIL, PASSWORD)

    await submit()

    expect(formAlert().textContent).toBe('Invalid JSON.')
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

    expect(submitButton().disabled).toBe(true)
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

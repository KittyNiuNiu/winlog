import { act, fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/index.ts'
import { saveSession } from '../api/session.ts'
import { renderRoute } from '../test/renderRoute.tsx'
import { removeTestSession } from '../test/session.ts'

// "Try the demo" on the login page (FR-X1, #35). The API client is mocked; no request
// reaches a backend and no AI call is made.

vi.mock('../api/index.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/index.ts')>()
  return { ...actual, login: vi.fn(), demoLogin: vi.fn(), listEntries: vi.fn(), listTags: vi.fn(), getSummary: vi.fn() }
})

const login = vi.mocked(api.login)
const demoLogin = vi.mocked(api.demoLogin)

const EMAIL = 'alice@example.com'
const PASSWORD = 'Correct-Horse-7'
const DEMO_UNAVAILABLE = "The demo isn't available right now."
const NETWORK_MESSAGE = "Can't reach Winlog. Check your connection and try again."
const GENERIC_MESSAGE = 'Something went wrong. Please try again.'
const WAKING_UP = 'The server is waking up. This can take up to a minute.'
const ACCOUNT_CREATED = 'Account created. Please log in.'
const WRONG_CREDENTIALS = 'Wrong email or password.'

// Like the real client: a successful demo login stores the token with the demo flag.
async function demoLoginStoringSession(): Promise<api.DemoLoginResult> {
  saveSession({ token: 'demo-token', expiresAt: '2099-01-01T00:00:00Z', demo: true })
  return { token: 'demo-token', expires_at: '2099-01-01T00:00:00Z', demo: true }
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

function emailInput(): HTMLInputElement {
  return screen.getByLabelText('Email') as HTMLInputElement
}

function passwordInput(): HTMLInputElement {
  return screen.getByLabelText('Password') as HTMLInputElement
}

function loginButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^(Log in|Logging in…)$/ }) as HTMLButtonElement
}

function demoButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^(Try the demo|Opening the demo…)$/ }) as HTMLButtonElement
}

function form(): HTMLFormElement {
  return document.querySelector('form') as HTMLFormElement
}

function fieldMessages(input: HTMLInputElement): string[] {
  const container = document.getElementById(`${input.id}-messages`)
  return Array.from(container?.querySelectorAll('p') ?? [], (p) => p.textContent ?? '')
}

/** The non-empty messages directly below "Try the demo". */
function demoMessages(): HTMLElement[] {
  const slots = demoButton().nextElementSibling as HTMLElement
  return Array.from(slots.querySelectorAll<HTMLElement>('.message')).filter((element) => element.textContent !== '')
}

function demoMessageTexts(): string[] {
  return demoMessages().map((element) => element.textContent ?? '')
}

/** The non-empty messages above the form. */
function messagesAboveForm(): string[] {
  return Array.from(document.querySelectorAll('.form__notice, .form__alert'), (element) => element.textContent ?? '').filter(
    (text) => text !== '',
  )
}

function fillIn(email: string, password: string): void {
  fireEvent.change(emailInput(), { target: { value: email } })
  fireEvent.change(passwordInput(), { target: { value: password } })
}

async function pressDemo(): Promise<void> {
  await act(async () => {
    fireEvent.click(demoButton())
  })
}

async function pressLogin(): Promise<void> {
  await act(async () => {
    fireEvent.click(loginButton())
  })
}

afterEach(() => {
  removeTestSession()
  vi.resetAllMocks()
  vi.useRealTimers()
})

describe('"Try the demo" on the login page (FR-X1)', () => {
  it('test_fr_x1_try_demo_is_a_secondary_button_below_the_login_form', () => {
    renderRoute('/login')

    const demo = demoButton()
    expect(demo.textContent).toBe('Try the demo')
    expect(demo.type).toBe('button')
    expect(demo.classList.contains('button--secondary')).toBe(true)
    expect(demo.classList.contains('button--primary')).toBe(false)
    // "Log in" stays the only filled plum element on the page (The One Action Rule).
    expect(document.querySelectorAll('.button--primary')).toHaveLength(1)
    expect(loginButton().classList.contains('button--primary')).toBe(true)
    // Outside the form, after it and before the registration link.
    expect(form().contains(demo)).toBe(false)
    expect(form().compareDocumentPosition(demo) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const registerLink = screen.getByRole('link', { name: 'Create an account' })
    expect(demo.compareDocumentPosition(registerLink) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // Everything above stays in its order: drawing, heading, message slot, form.
    const heading = screen.getByRole('heading', { level: 1, name: 'Log in' })
    expect(document.querySelector('svg.illustration')?.nextElementSibling).toBe(heading)
    const alert = document.querySelector('.form__alert') as HTMLElement
    expect(heading.compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(alert.compareDocumentPosition(form()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(demoMessageTexts()).toEqual([])
  })

  it('test_fr_x1_try_demo_logs_in_and_opens_home', async () => {
    demoLogin.mockImplementation(demoLoginStoringSession)
    vi.mocked(api.listEntries).mockReturnValue(new Promise(() => {}))
    const { router } = renderRoute('/login')

    await pressDemo()

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expect(demoLogin).toHaveBeenCalledWith()
    expect(login).not.toHaveBeenCalled()
    expect(api.getSession()).toEqual({ token: 'demo-token', expiresAt: '2099-01-01T00:00:00Z', demo: true })
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Entries' })).toBeTruthy()
    // /login was replaced in the history, so Back does not return to it.
    expect(router.state.historyAction).toBe('REPLACE')
  })

  it('test_fr_x1_try_demo_opens_the_page_the_visitor_wanted', async () => {
    demoLogin.mockImplementation(demoLoginStoringSession)
    vi.mocked(api.getSummary).mockReturnValue(new Promise(() => {}))
    const { router } = renderRoute('/summaries/42?tab=text#top')
    expect(router.state.location.pathname).toBe('/login')

    await pressDemo()

    const { pathname, search, hash } = router.state.location
    expect(`${pathname}${search}${hash}`).toBe('/summaries/42?tab=text#top')
    expect(router.state.historyAction).toBe('REPLACE')
  })

  it('test_fr_x1_try_demo_checks_no_field_and_keeps_what_was_typed', async () => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')
    fillIn('alice', 'typed-password')

    await pressDemo()

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expect(fieldMessages(emailInput())).toEqual([])
    expect(fieldMessages(passwordInput())).toEqual([])
    expect(emailInput().value).toBe('alice')
    expect(passwordInput().value).toBe('typed-password')
    // The fields stay editable while the demo request runs.
    fireEvent.change(emailInput(), { target: { value: 'alice@' } })
    expect(emailInput().value).toBe('alice@')
  })

  it('test_fr_x1_try_demo_with_empty_fields_shows_no_field_message', async () => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')

    await pressDemo()

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expect(fieldMessages(emailInput())).toEqual([])
    expect(fieldMessages(passwordInput())).toEqual([])
  })

  it.each([
    ['email', emailInput],
    ['password', passwordInput],
  ])('test_fr_x1_enter_in_the_%s_field_submits_the_login_form_not_the_demo', async (_name, input) => {
    login.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    // Enter in a field submits the field's form.
    await act(async () => {
      fireEvent.submit(input().form as HTMLFormElement)
    })

    expect(input().form).toBe(form())
    expect(login).toHaveBeenCalledWith({ email: EMAIL, password: PASSWORD })
    expect(demoLogin).not.toHaveBeenCalled()
  })
})

// QA FAIL 1 on #35: in a real browser, pressing "Try the demo" while a field had focus
// first blurred the field. Its blur check showed a field message that pushed the button
// down between press and release, so the click was lost. userEvent moves focus like a
// browser does (fireEvent.click does not), so these tests cover that path.
describe('"Try the demo" pressed while a field has focus (FR-X1)', () => {
  it.each([
    ['empty_email_field', emailInput, ''],
    ['invalid_email_field', emailInput, 'not-an-email'],
    ['empty_password_field', passwordInput, ''],
    ['filled_password_field', passwordInput, 'typed-password'],
  ])('test_fr_x1_clicking_try_demo_from_%s_runs_no_field_check', async (_name, input, typed) => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    renderRoute('/login')
    await user.click(input())
    if (typed !== '') {
      await user.type(input(), typed)
    }
    expect(document.activeElement).toBe(input())

    await user.click(demoButton())

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expect(login).not.toHaveBeenCalled()
    expect(fieldMessages(emailInput())).toEqual([])
    expect(fieldMessages(passwordInput())).toEqual([])
    expect(input().value).toBe(typed)
    // The press does not move focus, so the field is never blurred.
    expect(document.activeElement).toBe(input())
  })

  it.each([
    ['empty_email_field', emailInput, ''],
    ['invalid_email_field', emailInput, 'not-an-email'],
  ])('test_fr_x1_tapping_try_demo_from_%s_runs_no_field_check', async (_name, input, typed) => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    renderRoute('/login')
    await user.click(input())
    if (typed !== '') {
      await user.type(input(), typed)
    }

    await user.pointer([{ keys: '[TouchA]', target: demoButton() }])

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expect(fieldMessages(emailInput())).toEqual([])
    expect(fieldMessages(passwordInput())).toEqual([])
    expect(input().value).toBe(typed)
  })

  it.each([
    ['enter', '{Enter}'],
    ['space', ' '],
  ])('test_fr_x1_try_demo_from_the_keyboard_with_%s_runs_no_field_check', async (_name, key) => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    renderRoute('/login')
    // Reach "Try the demo" from the registration link below it, so no field is blurred.
    screen.getByRole('link', { name: 'Create an account' }).focus()
    await user.tab({ shift: true })
    expect(document.activeElement).toBe(demoButton())

    await user.keyboard(key)

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expect(fieldMessages(emailInput())).toEqual([])
    expect(fieldMessages(passwordInput())).toEqual([])
  })

  it('test_fr_x1_leaving_a_field_for_another_element_still_checks_it', async () => {
    const user = userEvent.setup()
    renderRoute('/login')

    // "Log in"'s own blur checks are unchanged: leaving the email field checks it.
    await user.click(emailInput())
    await user.type(emailInput(), 'not-an-email')
    await user.click(passwordInput())
    expect(fieldMessages(emailInput())).toEqual(['Enter an email address with an @, such as name@example.com.'])

    await user.click(screen.getByRole('heading', { level: 1, name: 'Log in' }))
    expect(fieldMessages(passwordInput())).toEqual(['Enter your password.'])
    expect(demoLogin).not.toHaveBeenCalled()
  })
})

// QA FAIL 2 on #35: a second press while the demo request runs (two clicks, a
// double-click or two taps) landed on the busy, disabled button. A disabled button runs
// no handler, so the browser moved focus to the page, and the field's blur check showed
// a field message. userEvent moves focus away on a press of a disabled button too.
describe('"Try the demo" pressed twice while a field has focus (FR-X1)', () => {
  const FIELDS = [
    ['empty_email_field', emailInput, ''],
    ['invalid_email_field', emailInput, 'not-an-email'],
    ['empty_password_field', passwordInput, ''],
  ] as const

  async function focusField(user: ReturnType<typeof userEvent.setup>, input: () => HTMLInputElement, typed: string) {
    await user.click(input())
    if (typed !== '') {
      await user.type(input(), typed)
    }
    expect(document.activeElement).toBe(input())
  }

  function expectNoFieldMessages() {
    expect(fieldMessages(emailInput())).toEqual([])
    expect(fieldMessages(passwordInput())).toEqual([])
  }

  it.each(FIELDS)('test_fr_x1_second_press_on_busy_try_demo_from_%s_runs_no_field_check', async (_name, input, typed) => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    renderRoute('/login')
    await focusField(user, input, typed)

    await user.click(demoButton())
    expect(demoButton().disabled).toBe(true)
    await user.click(demoButton())

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expect(login).not.toHaveBeenCalled()
    expectNoFieldMessages()
    expect(input().value).toBe(typed)
  })

  it.each(FIELDS)('test_fr_x1_double_click_on_try_demo_from_%s_runs_no_field_check', async (_name, input, typed) => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    renderRoute('/login')
    await focusField(user, input, typed)

    await user.dblClick(demoButton())

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expectNoFieldMessages()
    expect(input().value).toBe(typed)
  })

  it.each(FIELDS)('test_fr_x1_two_taps_on_try_demo_from_%s_run_no_field_check', async (_name, input, typed) => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    renderRoute('/login')
    await focusField(user, input, typed)

    await user.pointer([{ keys: '[TouchA]', target: demoButton() }])
    await user.pointer([{ keys: '[TouchA]', target: demoButton() }])

    expect(demoLogin).toHaveBeenCalledTimes(1)
    expectNoFieldMessages()
    expect(input().value).toBe(typed)
  })

  it('test_fr_x1_second_press_then_demo_unavailable_shows_only_the_demo_message', async () => {
    const request = deferred<api.DemoLoginResult>()
    demoLogin.mockReturnValue(request.promise)
    const user = userEvent.setup()
    renderRoute('/login')
    await focusField(user, emailInput, 'not-an-email')

    await user.click(demoButton())
    await user.click(demoButton())
    await act(async () => {
      request.reject(new api.NotFoundError('server text', 404))
    })

    expect(demoMessageTexts()).toEqual([DEMO_UNAVAILABLE])
    expectNoFieldMessages()
    expect(emailInput().value).toBe('not-an-email')
    expect(demoLogin).toHaveBeenCalledTimes(1)
  })

  it('test_fr_x1_leaving_a_field_after_a_failed_demo_checks_it_again', async () => {
    demoLogin.mockRejectedValue(new api.NotFoundError('server text', 404))
    const user = userEvent.setup()
    renderRoute('/login')
    await focusField(user, emailInput, 'not-an-email')
    await user.dblClick(demoButton())
    expectNoFieldMessages()

    // Once the demo request has ended, "Log in"'s blur check works as before.
    await user.click(emailInput())
    await user.click(passwordInput())
    expect(fieldMessages(emailInput())).toEqual(['Enter an email address with an @, such as name@example.com.'])
  })
})

describe('"Try the demo" while a request runs (FR-X1)', () => {
  it('test_fr_x1_try_demo_is_busy_and_a_second_press_sends_nothing', async () => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')

    await pressDemo()

    expect(demoButton().textContent).toBe('Opening the demo…')
    expect(demoButton().querySelector('.spinner')).toBeTruthy()
    expect(demoButton().getAttribute('aria-busy')).toBe('true')
    expect(demoButton().disabled).toBe(true)
    await pressDemo()
    expect(demoLogin).toHaveBeenCalledTimes(1)
  })

  it('test_fr_x1_log_in_cannot_start_while_the_demo_request_runs', async () => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await pressDemo()

    expect(loginButton().disabled).toBe(true)
    expect(loginButton().getAttribute('aria-busy')).toBe('false')
    expect(loginButton().textContent).toBe('Log in')
    await pressLogin()
    // Enter in a field cannot start a login either.
    await act(async () => {
      fireEvent.submit(form())
    })
    expect(login).not.toHaveBeenCalled()
  })

  it('test_fr_x1_try_demo_cannot_be_pressed_while_a_login_runs', async () => {
    login.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await pressLogin()

    expect(loginButton().textContent).toBe('Logging in…')
    expect(demoButton().disabled).toBe(true)
    expect(demoButton().getAttribute('aria-busy')).toBe('false')
    expect(demoButton().textContent).toBe('Try the demo')
    await pressDemo()
    expect(demoLogin).not.toHaveBeenCalled()
  })

  it('test_fr_x1_both_buttons_work_again_after_a_failed_demo', async () => {
    demoLogin.mockRejectedValue(new api.NetworkError())
    login.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await pressDemo()

    expect(demoButton().disabled).toBe(false)
    expect(demoButton().textContent).toBe('Try the demo')
    expect(loginButton().disabled).toBe(false)
    await pressLogin()
    expect(login).toHaveBeenCalledTimes(1)
  })

  describe('the waking-up hint', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    it('test_fr_x1_waking_up_hint_below_try_demo_after_10_seconds', async () => {
      const request = deferred<api.DemoLoginResult>()
      demoLogin.mockReturnValue(request.promise)
      vi.mocked(api.listEntries).mockReturnValue(new Promise(() => {}))
      const { router } = renderRoute('/login')

      await pressDemo()
      await act(async () => {
        vi.advanceTimersByTime(9_999)
      })
      expect(screen.queryByText(WAKING_UP)).toBeNull()

      await act(async () => {
        vi.advanceTimersByTime(1)
      })
      // Once, below "Try the demo", in a status region; never below "Log in".
      expect(screen.getAllByText(WAKING_UP)).toHaveLength(1)
      const [hint] = demoMessages()
      expect(hint.textContent).toBe(WAKING_UP)
      expect(hint.getAttribute('role')).toBe('status')
      expect(form().contains(hint)).toBe(false)
      expect((document.querySelector('.form__status') as HTMLElement).textContent).toBe('')

      await act(async () => {
        request.resolve(await demoLoginStoringSession())
      })
      expect(router.state.location.pathname).toBe('/')
    })

    it('test_fr_x1_only_the_running_requests_hint_is_shown', async () => {
      demoLogin.mockRejectedValueOnce(new api.NetworkError())
      login.mockReturnValue(new Promise(() => {}))
      renderRoute('/login')
      fillIn(EMAIL, PASSWORD)
      await pressDemo()

      await pressLogin()
      await act(async () => {
        vi.advanceTimersByTime(10_000)
      })

      // The login's hint, below "Log in"; nothing below "Try the demo".
      expect(screen.getAllByText(WAKING_UP)).toHaveLength(1)
      expect((document.querySelector('.form__status') as HTMLElement).textContent).toBe(WAKING_UP)
      expect(demoMessageTexts()).toEqual([])
    })
  })
})

describe('"Try the demo" errors (FR-X1)', () => {
  it.each([
    ['the demo turned off (404 not_found)', new api.NotFoundError('server text', 404), DEMO_UNAVAILABLE],
    ['a network error', new api.NetworkError(), NETWORK_MESSAGE],
    ['a server error', new api.UnknownError('server text', 500, 'internal_error'), GENERIC_MESSAGE],
    // A 429 without the contract's `too_many_attempts` code (FR-A4, #46) is not the refusal.
    ['a status the contract does not list', new api.UnknownError('server text', 429, null), GENERIC_MESSAGE],
    // FR-A4 (#46): too many demo logins from this visitor.
    [
      'a refused demo login (429 too_many_attempts)',
      new api.TooManyAttemptsError('server text', 429, 3600),
      'Too many attempts. Please try again in 60 minutes.',
    ],
    [
      'a refused demo login with 1 minute left',
      new api.TooManyAttemptsError('server text', 429, 45),
      'Too many attempts. Please try again in 1 minute.',
    ],
    [
      'a refused demo login without a readable Retry-After',
      new api.TooManyAttemptsError('server text', 429, null),
      'Too many attempts. Please try again later.',
    ],
    ['a response that is not the contract', new api.UnknownError('server text', 502, null), GENERIC_MESSAGE],
  ])('test_fr_x1_%s_shows_its_message_below_try_demo', async (_name, error, message) => {
    demoLogin.mockRejectedValue(error)
    const { router } = renderRoute('/login')
    fillIn(EMAIL, PASSWORD)

    await pressDemo()

    // One error, directly below the button, announced to screen readers.
    const messages = demoMessages()
    expect(messages.map((element) => element.textContent)).toEqual([message])
    expect(messages[0].getAttribute('role')).toBe('alert')
    expect(demoButton().nextElementSibling?.contains(messages[0])).toBe(true)
    expect(screen.getAllByText(message)).toHaveLength(1)
    expect(screen.queryByText('server text')).toBeNull()
    expect(messagesAboveForm()).toEqual([])
    expect(router.state.location.pathname).toBe('/login')
    expect(api.getSession()).toBeNull()
    expect(emailInput().value).toBe(EMAIL)
    expect(passwordInput().value).toBe(PASSWORD)
  })
})

describe('too many demo logins (FR-A4)', () => {
  it('test_fr_a4_refused_demo_login_shows_the_message_below_try_demo_not_the_interim_text', async () => {
    demoLogin.mockRejectedValue(new api.TooManyAttemptsError('server text', 429, 1800))
    renderRoute('/login')

    await pressDemo()

    expect(demoMessageTexts()).toEqual(['Too many attempts. Please try again in 30 minutes.'])
    expect(screen.queryByText(GENERIC_MESSAGE)).toBeNull()
    expect(messagesAboveForm()).toEqual([])
    // Both buttons stay pressable.
    expect(demoButton().disabled).toBe(false)
    expect(loginButton().disabled).toBe(false)
  })
})

describe('each action clears the other one\'s message (FR-X1)', () => {
  it('test_fr_x1_starting_a_demo_clears_the_login_error_above_the_form', async () => {
    login.mockRejectedValue(new api.InvalidCredentialsError('server text', 401))
    demoLogin.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    await pressLogin()
    expect(messagesAboveForm()).toEqual([WRONG_CREDENTIALS])

    await pressDemo()

    expect(messagesAboveForm()).toEqual([])
  })

  it('test_fr_x1_starting_a_demo_clears_the_account_created_notice', async () => {
    demoLogin.mockReturnValue(new Promise(() => {}))
    const { router } = renderRoute('/register')
    await act(async () => {
      await router.navigate('/login', { state: { accountCreated: true } })
    })
    expect(messagesAboveForm()).toEqual([ACCOUNT_CREATED])

    await pressDemo()

    expect(messagesAboveForm()).toEqual([])
  })

  it('test_fr_x1_starting_a_login_clears_the_message_below_try_demo', async () => {
    demoLogin.mockRejectedValue(new api.NotFoundError('server text', 404))
    login.mockReturnValue(new Promise(() => {}))
    renderRoute('/login')
    fillIn(EMAIL, PASSWORD)
    await pressDemo()
    expect(demoMessageTexts()).toEqual([DEMO_UNAVAILABLE])

    await pressLogin()

    expect(login).toHaveBeenCalledTimes(1)
    expect(demoMessageTexts()).toEqual([])
  })

  it('test_fr_x1_next_demo_attempt_clears_its_own_message', async () => {
    demoLogin.mockRejectedValueOnce(new api.NetworkError())
    demoLogin.mockReturnValueOnce(new Promise(() => {}))
    renderRoute('/login')
    await pressDemo()
    expect(demoMessageTexts()).toEqual([NETWORK_MESSAGE])

    await pressDemo()

    expect(demoMessageTexts()).toEqual([])
    expect(demoLogin).toHaveBeenCalledTimes(2)
  })
})

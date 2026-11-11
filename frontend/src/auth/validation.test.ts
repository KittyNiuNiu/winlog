import { describe, expect, it } from 'vitest'
import { EMAIL_MISSING, EMAIL_WITHOUT_AT, emailProblem, passwordProblems, type PasswordProblem } from './validation.ts'
import { wantedPage } from './wantedPage.ts'

// The same cases as the backend's password rule tests (#6), so both places agree.
describe('password rule (FR-A1)', () => {
  it.each<[string, string, PasswordProblem[]]>([
    ['exactly 10 characters meeting every requirement', 'Abcdefgh1!', []],
    ['128 characters', `Ab1!${'x'.repeat(124)}`, []],
    ['9 characters', 'Abcdefg1!', ['too_short']],
    ['129 characters', `Ab1!${'x'.repeat(125)}`, ['too_long']],
    ['no uppercase letter', 'abcdefgh1!', ['no_uppercase']],
    ['no digit', 'Abcdefghi!', ['no_digit']],
    ['no special character', 'Abcdefghi1', ['no_special']],
    ['empty', '', ['too_short', 'no_uppercase', 'no_digit', 'no_special']],
    ['a space as the special character', 'Abcdefgh1 x', []],
    ['spaces at the start and end are kept', ' Abcdefg1 ', []],
    ['Ä as the uppercase letter', 'Äbcdefgh1-', []],
    ['Greek, Cyrillic and sharp-s capitals count', 'ΑДẞbcdef1!', []],
    ['Ⓐ is a symbol, not an uppercase letter', 'Ⓐbcdefgh12', ['no_uppercase']],
    ['Ⅰ is a number form, not an uppercase letter', 'Ⅰbcdefgh12', ['no_uppercase']],
    ['titlecase ǅ is a letter but not uppercase', 'ǅbcdefg1xy', ['no_uppercase', 'no_special']],
    ['² is a special character, not a digit', 'Abcdefghi²', ['no_digit']],
    ['a full-width digit is a special character, not a digit', 'Abcdefghi１', ['no_digit']],
  ])('%s', (_name, password, problems) => {
    expect(passwordProblems(password)).toEqual(problems)
  })

  it('counts characters, not UTF-16 units', () => {
    // 10 characters, 12 UTF-16 units: the emoji are outside the Basic Multilingual Plane.
    expect(passwordProblems('A1😀😀abcdef')).toEqual([])
    expect(passwordProblems('A1😀abcdef')).toEqual(['too_short'])
    expect(passwordProblems(`A1${'😀'.repeat(126)}`)).toEqual([])
    expect(passwordProblems(`A1${'😀'.repeat(127)}`)).toEqual(['too_long'])
  })
})

describe('email check (FR-A1)', () => {
  it.each([
    ['', EMAIL_MISSING],
    ['   ', EMAIL_MISSING],
    ['alice', EMAIL_WITHOUT_AT],
    ['alice.example.com', EMAIL_WITHOUT_AT],
    ['alice@example.com', null],
    [' Alice@Example.com ', null],
  ])('%j gives %j', (email, message) => {
    expect(emailProblem(email)).toBe(message)
  })
})

describe('the page to open after login (FR-A2)', () => {
  it.each([
    [undefined, '/'],
    [null, '/'],
    [{}, '/'],
    [{ from: '/review' }, '/review'],
    [{ from: '/summaries/42?x=1#y' }, '/summaries/42?x=1#y'],
    [{ from: '/login' }, '/'],
    [{ from: '/register?x=1' }, '/'],
    [{ from: '//evil.example' }, '/'],
    [{ from: '/\\evil.example' }, '/'],
    [{ from: 'https://evil.example/' }, '/'],
    [{ from: 42 }, '/'],
  ])('%j opens %s', (state, path) => {
    expect(wantedPage(state)).toBe(path)
  })
})

import { act, fireEvent, screen, within } from '@testing-library/react'
import type { Entry, EntryInput } from '../api/index.ts'

// Queries and fixtures for the entry form tests (#27).

export const ENTRY_ID = '3f0c8f5e-5a43-4d8e-9a57-2c1b9c1f0a11'

export function textArea(): HTMLTextAreaElement {
  return screen.getByLabelText('What happened?') as HTMLTextAreaElement
}

export function dateInput(): HTMLInputElement {
  return screen.getByLabelText('Date') as HTMLInputElement
}

export function categoryGroup(): HTMLElement {
  return screen.getByRole('group', { name: 'Category' })
}

export function chip(name: string): HTMLButtonElement {
  return within(categoryGroup()).getByRole('button', { name }) as HTMLButtonElement
}

export function pressedChips(): string[] {
  return within(categoryGroup())
    .getAllByRole('button')
    .filter((button) => button.getAttribute('aria-pressed') === 'true')
    .map((button) => button.textContent ?? '')
}

export function foldButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: 'Add tags and result' }) as HTMLButtonElement
}

export function openFold(): void {
  if (foldButton().getAttribute('aria-expanded') !== 'true') {
    fireEvent.click(foldButton())
  }
}

export function tagInput(): HTMLInputElement {
  return screen.getByRole('combobox', { name: 'Tags' }) as HTMLInputElement
}

export function resultInput(): HTMLTextAreaElement {
  return screen.getByLabelText('Result') as HTMLTextAreaElement
}

export function addedTags(): string[] {
  const list = screen.queryByRole('list', { name: 'Added tags' })
  if (list === null) {
    return []
  }
  return within(list)
    .getAllByRole('listitem')
    .map((item) => item.querySelector('.tag-chip__label')?.textContent ?? '')
}

export function options(): string[] {
  const list = screen.queryByRole('listbox', { name: 'Matching tags' })
  if (list === null) {
    return []
  }
  return within(list)
    .queryAllByRole('option')
    .map((option) => option.textContent ?? '')
}

export function saveButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /^(Save entry|Saving…)$/ }) as HTMLButtonElement
}

/** The messages under a field (by the control's id, or `entry-category`). */
export function messagesOf(id: string): string[] {
  const container = document.getElementById(`${id}-messages`)
  if (container === null) {
    throw new Error(`no messages for ${id}`)
  }
  return Array.from(container.querySelectorAll('p'), (p) => p.textContent ?? '')
}

/** The error message next to Save entry. */
export function formError(): string {
  return document.querySelector('.entry-form__error')?.textContent ?? ''
}

/** The "Entry saved." band, or '' when it is hidden. */
export function savedBand(): string {
  return document.querySelector('.saved-message')?.textContent ?? ''
}

export function justSavedRows(): HTMLElement[] {
  const heading = screen.queryByRole('heading', { level: 2, name: 'Just saved' })
  if (heading === null) {
    return []
  }
  return Array.from(document.querySelectorAll<HTMLElement>('.just-saved .entry-row'))
}

export function type(element: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  fireEvent.change(element, { target: { value } })
}

/** Types a tag and presses a key in the tag input. */
export function key(element: HTMLElement, name: string): void {
  fireEvent.keyDown(element, { key: name })
}

export async function save(): Promise<void> {
  await act(async () => {
    fireEvent.click(saveButton())
  })
}

/** Fills in the three required fields. */
export function fillRequired(text = 'Shipped the export feature', category = 'Achievement'): void {
  type(textArea(), text)
  fireEvent.click(chip(category))
}

let nextId = 1

/** The entry the API returns for a create or update request. */
export function entryFrom(body: EntryInput, id = `00000000-0000-4000-8000-${String(nextId++).padStart(12, '0')}`): Entry {
  const result = body.result_impact ?? null
  return {
    id,
    date: body.date,
    text: body.text,
    category: body.category,
    tags: body.tags ?? [],
    result_impact: result === null || result.trim() === '' ? null : result,
    created_at: '2026-11-12T10:00:00Z',
    updated_at: '2026-11-12T10:00:00Z',
  }
}

export function storedEntry(overrides: Partial<Entry> = {}): Entry {
  return {
    id: ENTRY_ID,
    date: '2026-10-05',
    text: 'Led the incident review',
    category: 'Feedback',
    tags: ['Leadership', 'incident'],
    result_impact: 'Fewer pages at night',
    created_at: '2026-10-05T09:00:00Z',
    updated_at: '2026-10-05T09:00:00Z',
    ...overrides,
  }
}

/** This file's URL, kept in a variable so the bundler does not treat it as an asset. */
const HERE = import.meta.url

interface NodeFs {
  readFileSync(path: URL, encoding: 'utf8'): string
}

/**
 * Adds a stylesheet from src/ to the page, so getComputedStyle sees its rules (Vitest
 * empties the stylesheets the components import). node:fs is loaded by name because the
 * app's TypeScript setup has no Node types.
 */
export async function addStylesheet(pathFromSrc: string): Promise<() => void> {
  const fs = (await import(/* @vite-ignore */ `node:${'fs'}`)) as NodeFs
  const style = document.createElement('style')
  style.textContent = fs.readFileSync(new URL(`../${pathFromSrc}`, HERE), 'utf8')
  document.head.append(style)
  return () => style.remove()
}

import { describe, expect, it } from 'vitest'
import indexHtml from '../index.html?raw'

describe('index.html', () => {
  const doc = new DOMParser().parseFromString(indexHtml, 'text/html')

  it('sets the page title to Winlog', () => {
    expect(doc.title).toBe('Winlog')
  })

  it('declares the page language as English', () => {
    expect(doc.documentElement.getAttribute('lang')).toBe('en')
  })

  it('has a viewport meta tag for mobile screens', () => {
    expect(doc.querySelector('meta[name="viewport"]')?.getAttribute('content')).toBe(
      'width=device-width, initial-scale=1.0',
    )
  })
})

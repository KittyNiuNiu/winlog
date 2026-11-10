// @vitest-environment node
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'

// Runs the project's ESLint config (eslint.config.js; npm test runs in frontend/).
const eslint = new ESLint()

async function fetchRuleMessages(code: string, filePath: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath })
  return result.messages
    .filter((message) => message.ruleId === 'no-restricted-globals' || message.ruleId === 'no-restricted-properties')
    .map((message) => message.message)
}

describe('ESLint rule against fetch outside src/api/', () => {
  it.each([
    "fetch('/entries')\n",
    "window.fetch('/entries')\n",
    "globalThis.fetch('/entries')\n",
    "self.fetch('/entries')\n",
  ])('reports %s in a component', async (code) => {
    const messages = await fetchRuleMessages(code, 'src/components/Example.tsx')
    expect(messages).toEqual(['Call the backend through the API client in src/api/, not with fetch.'].map(
      (text) => expect.stringContaining(text),
    ))
  })

  it('reports fetch in any other file outside src/api/', async () => {
    const messages = await fetchRuleMessages("fetch('/entries')\n", 'src/pages/ExamplePage.ts')
    expect(messages).toHaveLength(1)
  })

  it('allows fetch inside src/api/', async () => {
    const messages = await fetchRuleMessages("globalThis.fetch('/entries')\nfetch('/x')\n", 'src/api/example.ts')
    expect(messages).toEqual([])
  })
})

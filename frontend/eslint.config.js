import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

const FETCH_MESSAGE = 'Call the backend through the API client in src/api/, not with fetch.'

export default defineConfig([
  globalIgnores(['dist', 'viewport-dist', 'viewport-results', 'viewport-screenshots', 'playwright-report', 'e2e-results']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    // All backend calls go through the API client in src/api/ (AGENTS.md), so fetch is
    // forbidden everywhere else.
    files: ['**/*.{ts,tsx}'],
    ignores: ['src/api/**'],
    rules: {
      'no-restricted-globals': ['error', { name: 'fetch', message: FETCH_MESSAGE }],
      'no-restricted-properties': [
        'error',
        ...['window', 'globalThis', 'self'].map((object) => ({
          object,
          property: 'fetch',
          message: FETCH_MESSAGE,
        })),
      ],
    },
  },
])

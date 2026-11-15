// @vitest-environment node
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { build, type Plugin, type PluginOption } from 'vite'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { versionFile, versionJson } from './versionFile.ts'

// version.json names the commit of the static-site build (#102): RENDER_GIT_COMMIT when it is a
// valid commit, otherwise null. The Deploy workflow waits until it names the deployed commit.

const COMMIT = '0123456789abcdef0123456789abcdef01234567'

const INVALID = [
  ['empty', ''],
  ['39 characters', COMMIT.slice(0, 39)],
  ['41 characters', `${COMMIT}0`],
  ['upper case', COMMIT.toUpperCase()],
  ['a g in it', `g${COMMIT.slice(1)}`],
  ['a trailing newline', `${COMMIT}\n`],
  ['a leading space', ` ${COMMIT}`],
  ['a short SHA', COMMIT.slice(0, 7)],
]

const directories: string[] = []

afterEach(async () => {
  vi.unstubAllEnvs()
  vi.resetModules()
  await Promise.all(directories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })))
})

/** Runs `vite build` on an empty page with the given plugins; returns the output directory. */
async function buildWith(plugins: PluginOption[]): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'winlog-version-file-'))
  directories.push(root)
  await writeFile(join(root, 'index.html'), '<!doctype html>\n<title>Test</title>\n')
  const outDir = join(root, 'dist')
  await build({ root, configFile: false, envDir: false, logLevel: 'silent', plugins, build: { outDir } })
  return outDir
}

async function readVersionFile(outDir: string): Promise<unknown> {
  return JSON.parse(await readFile(join(outDir, 'version.json'), 'utf8'))
}

describe('versionJson', () => {
  it('names a valid RENDER_GIT_COMMIT', () => {
    expect(JSON.parse(versionJson(COMMIT))).toEqual({ commit: COMMIT })
  })

  it('names null when RENDER_GIT_COMMIT is not set', () => {
    expect(JSON.parse(versionJson(undefined))).toEqual({ commit: null })
  })

  it.each(INVALID)('names null when RENDER_GIT_COMMIT is not a valid commit (%s)', (_name, value) => {
    expect(JSON.parse(versionJson(value))).toEqual({ commit: null })
  })

  it('is a JSON object with exactly one key, commit', () => {
    expect(versionJson(COMMIT)).toBe(`{"commit":"${COMMIT}"}\n`)
    expect(versionJson(undefined)).toBe('{"commit":null}\n')
  })
})

describe('versionFile', () => {
  it('writes version.json next to index.html during vite build', async () => {
    const outDir = await buildWith([versionFile(COMMIT)])

    expect((await readdir(outDir)).sort()).toEqual(['index.html', 'version.json'])
    expect(await readVersionFile(outDir)).toEqual({ commit: COMMIT })
  })

  it('writes null when there is no commit', async () => {
    expect(await readVersionFile(await buildWith([versionFile(undefined)]))).toEqual({ commit: null })
  })

  it('runs only for vite build, not for the dev server or the tests', () => {
    expect(versionFile(COMMIT).apply).toBe('build')
  })
})

describe('vite.config.ts', () => {
  /** The version file plugin as vite.config.ts sets it up with the current environment. */
  async function configuredPlugin(): Promise<Plugin> {
    vi.resetModules()
    const { default: config } = await import('../vite.config.ts')
    const plugins = (config.plugins ?? []).flat() as Plugin[]
    const [plugin] = plugins.filter((candidate) => candidate?.name === 'winlog-version-file')
    expect(plugin).toBeDefined()
    return plugin
  }

  it('passes RENDER_GIT_COMMIT to the version file', async () => {
    vi.stubEnv('RENDER_GIT_COMMIT', COMMIT)

    expect(await readVersionFile(await buildWith([await configuredPlugin()]))).toEqual({ commit: COMMIT })
  })

  it.each([
    ['not set', undefined],
    ['not a valid commit', COMMIT.toUpperCase()],
  ])('writes null when RENDER_GIT_COMMIT is %s', async (_name, value) => {
    vi.stubEnv('RENDER_GIT_COMMIT', value)

    expect(await readVersionFile(await buildWith([await configuredPlugin()]))).toEqual({ commit: null })
  })
})

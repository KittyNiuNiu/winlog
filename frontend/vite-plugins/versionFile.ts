// version.json: the commit a static-site build was made from (#102).
//
// `vite build` writes dist/version.json, a JSON object with exactly one key, `commit`. It is
// served as a file at /version.json: Render's SPA rewrite in render.yaml applies only where no
// file exists. The Deploy workflow (.github/workflows/deploy.yml) reads it after each deploy and
// waits until it names the commit the workflow deployed, so it can tell the new build from the
// previous one, which Render keeps serving until the new one is live. The app never reads it.
//
// Render sets RENDER_GIT_COMMIT to the deploy's commit, at build time too, for every runtime,
// static sites included (https://render.com/docs/environment-variables). The file names that
// commit when it is valid. Local builds, Docker Compose and CI do not set the variable, and the
// file then names null, as it does for a value that is not a valid commit.
import type { Plugin } from 'vite'

/** A full Git commit SHA: exactly 40 lowercase hexadecimal characters. */
const VALID_COMMIT = /^[0-9a-f]{40}$/

/** The content of version.json for a value of RENDER_GIT_COMMIT (undefined when it is not set). */
export function versionJson(renderGitCommit: string | undefined): string {
  const commit = renderGitCommit !== undefined && VALID_COMMIT.test(renderGitCommit) ? renderGitCommit : null
  return `${JSON.stringify({ commit })}\n`
}

/** Emits version.json into the build output, next to index.html. Only `vite build` runs it. */
export function versionFile(renderGitCommit: string | undefined): Plugin {
  return {
    name: 'winlog-version-file',
    apply: 'build',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'version.json', source: versionJson(renderGitCommit) })
    },
  }
}

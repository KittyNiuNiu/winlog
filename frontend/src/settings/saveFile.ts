import type { DownloadedFile } from '../api/index.ts'

/**
 * How long the object URL stays valid after the click. Some browsers start reading the
 * file only after the click's task has ended, so it is not revoked at once.
 */
export const REVOKE_URL_AFTER_MS = 1_000

/**
 * Hands a downloaded file to the browser, which saves it under the server's file name: an
 * object URL for the contents, a click on a temporary `<a download>`, then the link is
 * removed and the URL revoked. No library needed.
 */
export function saveFile({ contents, filename }: DownloadedFile): void {
  const url = URL.createObjectURL(contents)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.hidden = true
  document.body.append(link)
  try {
    link.click()
  } finally {
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), REVOKE_URL_AFTER_MS)
  }
}

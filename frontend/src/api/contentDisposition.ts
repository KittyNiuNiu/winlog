// Reads the file name from a Content-Disposition header (RFC 6266), for example
// `attachment; filename="winlog-export-2026-11-01.json"`. An RFC 5987 `filename*` value is
// preferred over `filename`, as browsers do. Returns null when there is no usable name.

function baseName(name: string): string | null {
  // A file name, never a path.
  const last = name.split(/[/\\]/).pop()?.trim() ?? ''
  return last === '' || last === '.' || last === '..' ? null : last
}

export function filenameFromContentDisposition(header: string | null): string | null {
  if (header === null) {
    return null
  }

  const extended = /(?:^|;)\s*filename\*\s*=\s*([^;]+)/i.exec(header)
  if (extended) {
    const match = /^[^']*'[^']*'(.+)$/.exec(extended[1].trim())
    if (match) {
      try {
        const name = baseName(decodeURIComponent(match[1]))
        if (name !== null) {
          return name
        }
      } catch {
        // Invalid percent-encoding: fall back to the plain filename.
      }
    }
  }

  const plain = /(?:^|;)\s*filename\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^;\s]+))/i.exec(header)
  if (plain) {
    const name = plain[1] !== undefined ? plain[1].replace(/\\(.)/g, '$1') : plain[2]
    return baseName(name)
  }
  return null
}

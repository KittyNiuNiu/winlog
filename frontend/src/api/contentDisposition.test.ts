import { describe, expect, it } from 'vitest'
import { filenameFromContentDisposition } from './contentDisposition.ts'

describe('filenameFromContentDisposition', () => {
  it.each([
    ['attachment; filename="winlog-export-2026-11-01.json"', 'winlog-export-2026-11-01.json'],
    ['attachment; filename=winlog-export-2026-11-01.md', 'winlog-export-2026-11-01.md'],
    ['attachment;filename="a \\"quoted\\" name.md"', 'a "quoted" name.md'],
    ['ATTACHMENT; FILENAME="upper.json"', 'upper.json'],
    ["attachment; filename=\"plain.md\"; filename*=UTF-8''sch%C3%B6n.md", 'schön.md'],
    ["attachment; filename*=UTF-8''only-extended.json", 'only-extended.json'],
    ["attachment; filename*=UTF-8''%E0%A4%A; filename=\"fallback.json\"", 'fallback.json'],
    ['attachment; filename="../../etc/passwd"', 'passwd'],
  ])('reads %s', (header, expected) => {
    expect(filenameFromContentDisposition(header)).toBe(expected)
  })

  it.each([null, '', 'attachment', 'inline; name="x"', 'attachment; filename=""', 'attachment; filename="../"'])(
    'returns null for %s',
    (header) => {
      expect(filenameFromContentDisposition(header)).toBeNull()
    },
  )
})

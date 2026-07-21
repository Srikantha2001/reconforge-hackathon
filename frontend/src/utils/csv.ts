// Reads only the first line of a CSV file to discover its column names —
// used at design-time (Configure step) so config authoring works against
// real uploaded headers instead of only the seeded pair.
export async function parseCsvHeader(file: File): Promise<string[]> {
  const head = await file.slice(0, 4096).text()
  const firstLine = head.split(/\r?\n/, 1)[0] ?? ''
  return firstLine.split(',').map((c) => c.trim()).filter(Boolean)
}

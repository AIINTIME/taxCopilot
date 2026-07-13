export function createId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`
}

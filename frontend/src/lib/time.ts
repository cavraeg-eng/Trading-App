export function formatDateTimeWithZone(dateInput: Date | string | number | null | undefined) {
  if (dateInput == null) return '—'

  const parsed = dateInput instanceof Date ? dateInput : new Date(dateInput)
  if (Number.isNaN(parsed.getTime())) {
    return typeof dateInput === 'string' ? dateInput : '—'
  }

  const pad = (part: number) => part.toString().padStart(2, '0')
  const timezone = Intl.DateTimeFormat(undefined, { timeZoneName: 'short' })
    .formatToParts(parsed)
    .find((part) => part.type === 'timeZoneName')?.value

  return [
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`,
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}:${pad(parsed.getSeconds())}`,
    timezone,
  ].filter(Boolean).join(' ')
}

export function formatDateOnly(dateInput: Date | string | number | null | undefined) {
  if (dateInput == null) return '—'

  const parsed = dateInput instanceof Date ? dateInput : new Date(dateInput)
  if (Number.isNaN(parsed.getTime())) {
    return typeof dateInput === 'string' ? dateInput : '—'
  }

  const pad = (part: number) => part.toString().padStart(2, '0')
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`
}
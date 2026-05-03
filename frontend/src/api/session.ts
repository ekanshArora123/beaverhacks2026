export interface PhonePayload {
  image_data_urls: string[]
  audio_data_url: string | null
  audio_mime: string | null
  audio_extension: string | null
  text_source_2: string | null
  diagram_source: string | null
  received_at: number
}

const PROGRAM_API_BASE_URL = ((import.meta.env.VITE_PROGRAM_API_URL as string | undefined)?.trim() || 'http://127.0.0.1:5000').replace(/\/+$/, '')

function buildSessionUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${PROGRAM_API_BASE_URL}${normalizedPath}`
}

export async function createSession(): Promise<string> {
  const response = await fetch(buildSessionUrl('/session/new'), { method: 'POST' })
  if (!response.ok) {
    throw new Error(`Failed to create session: ${response.status}`)
  }
  const json = await response.json() as { code?: string }
  if (!json.code) {
    throw new Error('Session response missing code')
  }
  return json.code
}

export async function postSessionInput(code: string, formData: FormData): Promise<{ image_count: number; has_audio: boolean; has_text: boolean }> {
  const response = await fetch(buildSessionUrl(`/session/${code}/input`), {
    method: 'POST',
    body: formData,
  })
  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    throw new Error(`Failed to post session input: ${response.status} ${errorText}`)
  }
  return await response.json() as { image_count: number; has_audio: boolean; has_text: boolean }
}

export async function pollSessionPending(code: string, signal: AbortSignal, timeoutSeconds = 25): Promise<PhonePayload | null> {
  const url = buildSessionUrl(`/session/${code}/pending?timeout=${timeoutSeconds}`)
  const response = await fetch(url, { signal })
  if (response.status === 204) {
    return null
  }
  if (!response.ok) {
    throw new Error(`Failed to poll session: ${response.status}`)
  }
  return await response.json() as PhonePayload
}

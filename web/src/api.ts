import type { ChangePreview, CourseMap, Draft, DraftPatch, EditAction } from './types'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let message = '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
  try {
    const data = (await response.json()) as { message?: unknown }
    if (data && typeof data.message === 'string' && data.message) {
      message = data.message
    }
  } catch {
    // JSON 이 아니면 기본 안내문을 쓴다.
  }
  return new ApiError(message, response.status)
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    throw await parseError(response)
  }
  return (await response.json()) as T
}

export async function createDraft(title: string, goals: string, files: File[]): Promise<Draft> {
  const form = new FormData()
  form.append('title', title)
  if (goals) form.append('goals', goals)
  for (const file of files) form.append('files', file)
  return request<Draft>('/api/drafts', { method: 'POST', body: form })
}

export async function getDraft(id: string): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}`)
}

export async function updateDraft(id: string, patch: DraftPatch): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export async function regenerateDraft(id: string): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/regenerate`, { method: 'POST' })
}

export async function acceptSuggestion(id: string, suggestionId: string): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/suggestions/${suggestionId}/accept`, { method: 'POST' })
}

export async function skipSuggestion(id: string, suggestionId: string): Promise<Draft> {
  return request<Draft>(`/api/drafts/${id}/suggestions/${suggestionId}/skip`, { method: 'POST' })
}

export async function handoff(id: string): Promise<{ text: string }> {
  return request<{ text: string }>(`/api/drafts/${id}/handoff`, { method: 'POST' })
}

// --- M2: 과정 지도 ---

export async function createDesign(draftId: string): Promise<{ design_id: string; map: CourseMap }> {
  return request(`/api/drafts/${draftId}/design`, { method: 'POST' })
}

export async function openExampleDesign(): Promise<{ design_id: string; map: CourseMap }> {
  return request('/api/designs/example', { method: 'POST' })
}

export async function getDesign(designId: string): Promise<CourseMap> {
  return request<CourseMap>(`/api/designs/${designId}`)
}

export async function submitEdits(designId: string, actions: EditAction[]): Promise<CourseMap> {
  return request<CourseMap>(`/api/designs/${designId}/edits`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actions }),
  })
}

export async function requestChange(designId: string, text: string): Promise<ChangePreview> {
  return request<ChangePreview>(`/api/designs/${designId}/change-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

export async function applyChangeRequest(designId: string, requestId: string): Promise<CourseMap> {
  return request<CourseMap>(`/api/designs/${designId}/change-requests/${requestId}/apply`, {
    method: 'POST',
  })
}

export async function discardChangeRequest(
  designId: string,
  requestId: string,
): Promise<{ discarded: boolean }> {
  return request(`/api/designs/${designId}/change-requests/${requestId}/discard`, {
    method: 'POST',
  })
}

export async function confirmDesign(
  designId: string,
): Promise<{ confirmed: boolean; message: string }> {
  return request(`/api/designs/${designId}/confirm`, { method: 'POST' })
}

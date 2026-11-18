export interface Week {
  title: string
  summary: string
}

export interface GradingItem {
  name: string
  weight: number
}

export type SuggestionStatus = 'pending' | 'accepted' | 'skipped'

export interface Suggestion {
  id: string
  text: string
  target: string
  status: SuggestionStatus
}

export interface Draft {
  id: string
  title: string
  intro: string
  goals: string
  outcomes: string[]
  weeks: Week[]
  grading: GradingItem[]
  suggestions: Suggestion[]
  sources_used: string[]
  warnings: string[]
  created_at: string
  updated_at: string
}

export interface DraftPatch {
  title?: string
  intro?: string
  outcomes?: string[]
  weeks?: Week[]
  grading?: GradingItem[]
}

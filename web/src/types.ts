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

// --- M2: 과정 지도 ---

export type NoticeSeverity = 'error' | 'warning'

export interface MapNotice {
  severity: NoticeSeverity
  message: string
  where: string
}

export interface MapItem {
  id: string
  kind: string
  title: string
  minutes: number
  due_day: number | null
  due_label: string | null
  note: string | null
}

export interface MapUnit {
  id: string
  index: number
  title: string
  summary: string
  total_minutes: number
  items: MapItem[]
}

export interface MapOutcome {
  index: number
  label: string
  statement: string
  level: string
}

export interface CourseMapSummary {
  unit_count: number
  outcome_count: number
  grading: string
  max_per_unit_label: string
}

export interface CourseMap {
  design_id: string
  title: string
  confirmed: boolean
  can_confirm: boolean
  summary: CourseMapSummary
  outcomes: MapOutcome[]
  units: MapUnit[]
  notices: MapNotice[]
}

export type EditAction =
  | { action: 'update_unit'; unit_id: string; title?: string; summary?: string }
  | {
      action: 'update_item'
      unit_id: string
      item_id: string
      title?: string
      minutes?: number
      due_day?: number | null
    }
  | { action: 'add_item'; unit_id: string; kind: string; title: string; minutes: number }
  | { action: 'remove_item'; unit_id: string; item_id: string }
  | { action: 'move_item'; unit_id: string; item_id: string; to_unit_id: string }

export interface ChangePreview {
  request_id: string
  summary: string[]
}

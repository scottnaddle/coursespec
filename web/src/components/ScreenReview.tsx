import { useEffect, useState } from 'react'
import {
  acceptSuggestion,
  handoff,
  regenerateDraft,
  skipSuggestion,
  updateDraft,
} from '../api'
import type { Draft, GradingItem, Week } from '../types'

interface ScreenReviewProps {
  draft: Draft
  onUpdated: (draft: Draft) => void
  onStartNew: () => void
}

interface Editable {
  title: string
  intro: string
  outcomes: string[]
  weeks: Week[]
  grading: GradingItem[]
}

function toEditable(draft: Draft): Editable {
  return {
    title: draft.title,
    intro: draft.intro,
    outcomes: [...draft.outcomes],
    weeks: draft.weeks.map((week) => ({ ...week })),
    grading: draft.grading.map((item) => ({ ...item })),
  }
}

export function ScreenReview({ draft, onUpdated, onStartNew }: ScreenReviewProps) {
  const [form, setForm] = useState<Editable>(() => toEditable(draft))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [handoffText, setHandoffText] = useState<string | null>(null)

  // 서버 응답(저장·제안 수락·다시 만들기)이 오면 화면을 그 결과로 맞춘다.
  useEffect(() => {
    setForm(toEditable(draft))
  }, [draft])

  function patch(partial: Partial<Editable>) {
    setForm((prev) => ({ ...prev, ...partial }))
    setNotice(null)
  }

  function setOutcome(index: number, value: string) {
    const outcomes = [...form.outcomes]
    outcomes[index] = value
    patch({ outcomes })
  }

  function addOutcome() {
    patch({ outcomes: [...form.outcomes, ''] })
  }

  function removeOutcome(index: number) {
    patch({ outcomes: form.outcomes.filter((_, i) => i !== index) })
  }

  function setWeek(index: number, field: keyof Week, value: string) {
    const weeks = form.weeks.map((week, i) => (i === index ? { ...week, [field]: value } : week))
    patch({ weeks })
  }

  function addWeek() {
    patch({ weeks: [...form.weeks, { title: '', summary: '' }] })
  }

  function removeWeek(index: number) {
    patch({ weeks: form.weeks.filter((_, i) => i !== index) })
  }

  function setGrade(index: number, field: keyof GradingItem, value: string) {
    const grading = form.grading.map((item, i) =>
      i === index ? { ...item, [field]: field === 'weight' ? Number(value) || 0 : value } : item,
    )
    patch({ grading })
  }

  function addGrade() {
    patch({ grading: [...form.grading, { name: '', weight: 0 }] })
  }

  function removeGrade(index: number) {
    patch({ grading: form.grading.filter((_, i) => i !== index) })
  }

  async function save(): Promise<Draft | null> {
    setSaving(true)
    setError(null)
    try {
      const saved = await updateDraft(draft.id, form)
      onUpdated(saved)
      setNotice('저장했습니다.')
      return saved
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장하지 못했습니다.')
      return null
    } finally {
      setSaving(false)
    }
  }

  async function handleRegenerate() {
    setError(null)
    setNotice(null)
    try {
      const regenerated = await regenerateDraft(draft.id)
      onUpdated(regenerated)
    } catch (err) {
      setError(err instanceof Error ? err.message : '초안을 다시 만들지 못했습니다.')
    }
  }

  async function handleHandoff() {
    setError(null)
    setNotice(null)
    try {
      const saved = await save()
      if (!saved) return
      const result = await handoff(draft.id)
      setHandoffText(result.text)
      setNotice('설계 에이전트에 넘길 초안이 준비되었습니다.')
    } catch (err) {
      setError(err instanceof Error ? err.message : '과정 설계로 넘기지 못했습니다.')
    }
  }

  async function handleAccept(suggestionId: string) {
    setError(null)
    try {
      const updated = await acceptSuggestion(draft.id, suggestionId)
      onUpdated(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : '제안을 반영하지 못했습니다.')
    }
  }

  async function handleSkip(suggestionId: string) {
    setError(null)
    try {
      const updated = await skipSuggestion(draft.id, suggestionId)
      onUpdated(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : '제안을 건너뛰지 못했습니다.')
    }
  }

  return (
    <>
      <div className="h-row">
        <div>
          <h1>
            강의계획서 초안을 확인하고 고쳐 주세요 <span className="badge new">새 기능</span>
          </h1>
          <p className="lede">
            출발점일 뿐입니다. 그대로 쓰지 않아도 됩니다. 학습목표, 주차, 평가를 고친 뒤 과정
            설계로 넘어가세요.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, paddingTop: 4 }}>
          <button className="btn btn-ghost" type="button" onClick={handleRegenerate}>
            초안 다시 만들기
          </button>
          <button className="btn btn-primary" type="button" onClick={handleHandoff}>
            이 초안으로 과정 설계하기
          </button>
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      <div className="split-wide">
        <div className="panel" style={{ overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
          <div className="section">
            <label className="field-label" htmlFor="draft-title">
              과정 이름
            </label>
            <input
              id="draft-title"
              className="input input-lg"
              value={form.title}
              onChange={(event) => patch({ title: event.target.value })}
            />
            <div style={{ height: 10 }} />
            <label className="field-label" htmlFor="draft-intro">
              한 줄 소개
            </label>
            <input
              id="draft-intro"
              className="input"
              value={form.intro}
              onChange={(event) => patch({ intro: event.target.value })}
            />
          </div>

          <div className="section">
            <div className="section-h">
              <h2>학습목표</h2>
              <button className="linkish" type="button" onClick={addOutcome}>
                + 목표 추가
              </button>
            </div>
            {form.outcomes.map((outcome, index) => (
              <div className="lo" key={index}>
                <div className="lo-num" aria-hidden="true">
                  {index + 1}
                </div>
                <input
                  className="input"
                  value={outcome}
                  aria-label={`학습목표 ${index + 1}`}
                  onChange={(event) => setOutcome(index, event.target.value)}
                />
                <button
                  className="x"
                  type="button"
                  aria-label={`학습목표 ${index + 1} 제거`}
                  onClick={() => removeOutcome(index)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <div className="section">
            <div className="section-h">
              <h2>주차 구성</h2>
              <button className="linkish" type="button" onClick={addWeek}>
                + 주차 추가
              </button>
            </div>
            {form.weeks.map((week, index) => (
              <div className="week-ed" key={index}>
                <div className="wk-tag" aria-hidden="true">
                  {index + 1}주
                </div>
                <div className="week-body">
                  <input
                    className="input"
                    value={week.title}
                    aria-label={`${index + 1}주차 제목`}
                    onChange={(event) => setWeek(index, 'title', event.target.value)}
                  />
                  <input
                    className="input"
                    value={week.summary}
                    aria-label={`${index + 1}주차 요약`}
                    placeholder="이 주차에서 다룰 내용"
                    onChange={(event) => setWeek(index, 'summary', event.target.value)}
                  />
                </div>
                <button
                  className="x"
                  type="button"
                  aria-label={`${index + 1}주차 제거`}
                  onClick={() => removeWeek(index)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <div className="section">
            <div className="section-h">
              <h2>평가 비중</h2>
              <span className="hint-inline">
                합계 {form.grading.reduce((sum, item) => sum + (item.weight || 0), 0)}%
              </span>
            </div>
            {form.grading.map((item, index) => (
              <div className="grade" key={index}>
                <input
                  className="input"
                  value={item.name}
                  aria-label={`평가 항목 ${index + 1} 이름`}
                  onChange={(event) => setGrade(index, 'name', event.target.value)}
                />
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={100}
                  value={item.weight}
                  aria-label={`평가 항목 ${index + 1} 비중`}
                  onChange={(event) => setGrade(index, 'weight', event.target.value)}
                />
                <span className="pct">%</span>
                <button
                  className="x"
                  type="button"
                  aria-label={`평가 항목 ${index + 1} 제거`}
                  onClick={() => removeGrade(index)}
                >
                  ×
                </button>
              </div>
            ))}
            <button className="linkish" type="button" onClick={addGrade}>
              + 평가 항목 추가
            </button>
          </div>

          <div className="footer-bar" style={{ padding: '12px 18px 16px' }}>
            <span className="hint-inline">고친 내용은 저장한 뒤 과정 설계로 넘어갑니다.</span>
            <button className="btn btn-ghost" type="button" onClick={save} disabled={saving}>
              {saving ? '저장 중…' : '저장'}
            </button>
          </div>
        </div>

        <div className="col">
          <div className="panel activity">
            <h2>제안</h2>
            <p className="hint">초안을 바꾸지는 않았습니다. 마음에 드는 제안만 넣어 주세요.</p>
            {draft.suggestions.length === 0 && (
              <p className="hint-inline">지금은 제안이 없습니다.</p>
            )}
            {draft.suggestions.map((suggestion, index) => (
              <div className={`suggest ${suggestion.status !== 'pending' ? 'done' : ''}`} key={suggestion.id}>
                <div className="who">
                  {suggestion.target ? `제안 ${index + 1} · ${suggestion.target}` : '참고'}
                </div>
                <p>{suggestion.text}</p>
                {suggestion.status === 'pending' ? (
                  <div className="acts">
                    <button
                      className="btn btn-primary btn-xs"
                      type="button"
                      onClick={() => handleAccept(suggestion.id)}
                    >
                      넣기
                    </button>
                    <button
                      className="btn btn-ghost btn-xs"
                      type="button"
                      onClick={() => handleSkip(suggestion.id)}
                    >
                      건너뛰기
                    </button>
                  </div>
                ) : (
                  <span className="status">
                    {suggestion.status === 'accepted' ? '반영했습니다.' : '건너뛰었습니다.'}
                  </span>
                )}
              </div>
            ))}
          </div>

          {handoffText !== null && (
            <div className="panel" style={{ padding: 14 }}>
              <details>
                <summary className="linkish" style={{ cursor: 'pointer' }}>
                  설계 에이전트에 넘길 텍스트 확인
                </summary>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 8, color: 'var(--sub)' }}>
                  {handoffText}
                </pre>
              </details>
            </div>
          )}

          <button className="btn btn-ghost" type="button" onClick={onStartNew}>
            새 과정 다시 시작하기
          </button>
        </div>
      </div>
    </>
  )
}

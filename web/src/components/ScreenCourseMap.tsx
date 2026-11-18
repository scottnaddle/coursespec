import { useEffect, useState } from 'react'
import {
  applyChangeRequest,
  confirmDesign,
  discardChangeRequest,
  requestChange,
  submitEdits,
} from '../api'
import type { CourseMap, EditAction, MapItem, MapUnit } from '../types'

interface ScreenCourseMapProps {
  map: CourseMap
  onChange: (map: CourseMap) => void
}

const ADDABLE_KINDS = ['읽기', '자료', '퀴즈', '토론', '과제', '설문', '동료평가']

interface ItemDraft {
  id: string
  title: string
  minutes: string
  dueDay: string
  removed: boolean
  moveTo: string
}

interface PendingAdd {
  kind: string
  title: string
  minutes: string
}

interface UnitDraft {
  title: string
  summary: string
  items: ItemDraft[]
  adds: PendingAdd[]
}

function toItemDraft(item: MapItem): ItemDraft {
  return {
    id: item.id,
    title: item.title,
    minutes: String(item.minutes),
    dueDay: item.due_day === null ? '' : String(item.due_day),
    removed: false,
    moveTo: '',
  }
}

function toUnitDraft(unit: MapUnit): UnitDraft {
  return {
    title: unit.title,
    summary: unit.summary,
    items: unit.items.map(toItemDraft),
    adds: [],
  }
}

export function ScreenCourseMap({ map, onChange }: ScreenCourseMapProps) {
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<UnitDraft | null>(null)
  const [saving, setSaving] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [requestText, setRequestText] = useState('')
  const [preview, setPreview] = useState<{ request_id: string; summary: string[] } | null>(null)
  const [dialogBusy, setDialogBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    setEditingId(null)
    setDraft(null)
    setPreview(null)
    setDialogOpen(false)
  }, [map.design_id])

  function startEdit(unit: MapUnit) {
    setError(null)
    setNotice(null)
    setEditingId(unit.id)
    setDraft(toUnitDraft(unit))
  }

  function cancelEdit() {
    setEditingId(null)
    setDraft(null)
  }

  async function saveEdit(unit: MapUnit) {
    if (!draft) return
    setSaving(true)
    setError(null)
    try {
      const actions: EditAction[] = []
      if (draft.title !== unit.title || draft.summary !== unit.summary) {
        actions.push({
          action: 'update_unit',
          unit_id: unit.id,
          title: draft.title,
          summary: draft.summary,
        })
      }
      for (const item of draft.items) {
        const original = unit.items.find((it) => it.id === item.id)
        if (!original) continue
        if (item.removed) {
          actions.push({ action: 'remove_item', unit_id: unit.id, item_id: item.id })
          continue
        }
        if (item.moveTo && item.moveTo !== unit.id) {
          actions.push({
            action: 'move_item',
            unit_id: unit.id,
            item_id: item.id,
            to_unit_id: item.moveTo,
          })
          continue
        }
        const minutes = Number(item.minutes) || 0
        const due = item.dueDay.trim() === '' ? null : Number(item.dueDay)
        if (
          item.title !== original.title ||
          minutes !== original.minutes ||
          due !== original.due_day
        ) {
          actions.push({
            action: 'update_item',
            unit_id: unit.id,
            item_id: item.id,
            title: item.title,
            minutes,
            due_day: due,
          })
        }
      }
      for (const add of draft.adds) {
        actions.push({
          action: 'add_item',
          unit_id: unit.id,
          kind: add.kind,
          title: add.title,
          minutes: Number(add.minutes) || 30,
        })
      }
      if (actions.length === 0) {
        cancelEdit()
        return
      }
      const updated = await submitEdits(map.design_id, actions)
      onChange(updated)
      setEditingId(null)
      setDraft(null)
      setNotice('고친 내용을 적용했습니다.')
    } catch (err) {
      setError(err instanceof Error ? err.message : '고친 내용을 적용하지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  function patchDraft(partial: Partial<UnitDraft>) {
    setDraft((prev) => (prev ? { ...prev, ...partial } : prev))
  }

  function patchItem(itemId: string, partial: Partial<ItemDraft>) {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            items: prev.items.map((it) => (it.id === itemId ? { ...it, ...partial } : it)),
          }
        : prev,
    )
  }

  async function openDialog() {
    setError(null)
    setNotice(null)
    setRequestText('')
    setPreview(null)
    setDialogOpen(true)
  }

  async function handlePreview() {
    if (!requestText.trim()) {
      setError('바꾸고 싶은 내용을 문장으로 적어 주세요.')
      return
    }
    setDialogBusy(true)
    setError(null)
    try {
      const result = await requestChange(map.design_id, requestText.trim())
      setPreview(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : '수정 요청을 이해하지 못했습니다.')
    } finally {
      setDialogBusy(false)
    }
  }

  async function closeDialog(discard: boolean) {
    if (discard && preview) {
      try {
        await discardChangeRequest(map.design_id, preview.request_id)
      } catch {
        // 취소 실패는 조용히 넘긴다. 설계서는 바뀌지 않는다.
      }
    }
    setDialogOpen(false)
    setPreview(null)
    setRequestText('')
  }

  async function handleApplyRequest() {
    if (!preview) return
    setDialogBusy(true)
    setError(null)
    try {
      const updated = await applyChangeRequest(map.design_id, preview.request_id)
      onChange(updated)
      setDialogOpen(false)
      setPreview(null)
      setNotice('요청하신 변경을 적용했습니다.')
    } catch (err) {
      setError(err instanceof Error ? err.message : '변경을 적용하지 못했습니다.')
    } finally {
      setDialogBusy(false)
    }
  }

  async function handleConfirm() {
    setConfirming(true)
    setError(null)
    try {
      const result = await confirmDesign(map.design_id)
      onChange({ ...map, confirmed: true })
      setNotice(result.message)
    } catch (err) {
      setError(err instanceof Error ? err.message : '확정하지 못했습니다.')
    } finally {
      setConfirming(false)
    }
  }

  return (
    <>
      <div className="h-row">
        <div>
          <h1>{map.confirmed ? '설계가 확정되었습니다' : '과정 지도 초안이 준비되었습니다'}</h1>
          <p className="lede">
            강의계획서를 주차별 활동으로 풀어 본 결과입니다. 복잡한 설정 파일은 보여 드리지
            않아요. 확인하신 뒤 확정해 주세요.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, paddingTop: 4 }}>
          <button className="btn btn-ghost" type="button" onClick={openDialog}>
            수정 요청
          </button>
          <button
            className="btn btn-primary"
            type="button"
            onClick={handleConfirm}
            disabled={!map.can_confirm || confirming}
            title={
              map.can_confirm
                ? undefined
                : '빨간 안내의 오류를 고친 뒤에 확정할 수 있습니다.'
            }
          >
            {confirming ? '확정 중…' : '이 설계로 확정'}
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
          {map.confirmed && ' 다음 단계(오픈마익 수업 생성)는 곧 제공됩니다.'}
        </p>
      )}

      {map.notices.length > 0 && (
        <div className="alert-list" role="alert">
          {map.notices.map((item, index) => (
            <p key={index} className={`alert-line ${item.severity}`}>
              <b>{item.where}</b> — {item.message}
              {item.severity === 'error' ? ' (고치신 뒤 확정할 수 있습니다.)' : ''}
            </p>
          ))}
        </div>
      )}

      <div className="meta-row">
        <span className="chip">{map.summary.unit_count}주 과정</span>
        <span className="chip">
          학습목표 <strong>{map.summary.outcome_count}개</strong>
        </span>
        <span className="chip">
          평가 <strong>{map.summary.grading}</strong>
        </span>
        {map.summary.max_per_unit_label && (
          <span className="chip">
            주당 최대 <strong>{map.summary.max_per_unit_label}</strong>
          </span>
        )}
      </div>

      <div className="goals">
        {map.outcomes.map((outcome) => (
          <div className="card goal-card" key={outcome.index}>
            <div className="goal-k">{outcome.label}</div>
            <p>{outcome.statement}</p>
          </div>
        ))}
      </div>

      <div className="weeks-grid">
        {map.units.map((unit) => (
          <div className="card week-card" key={unit.id}>
            <div className="week-head">
              <span className="wn">{unit.index}주차</span>
              <span className="week-mins">{unit.total_minutes}분</span>
            </div>
            {editingId === unit.id && draft ? (
              <div className="unit-edit">
                <label className="field-label" htmlFor={`edit-title-${unit.id}`}>
                  주차 제목
                </label>
                <input
                  id={`edit-title-${unit.id}`}
                  className="input"
                  value={draft.title}
                  onChange={(event) => patchDraft({ title: event.target.value })}
                />
                <label className="field-label" htmlFor={`edit-summary-${unit.id}`}>
                  주차 요약
                </label>
                <input
                  id={`edit-summary-${unit.id}`}
                  className="input"
                  value={draft.summary}
                  onChange={(event) => patchDraft({ summary: event.target.value })}
                />

                <div className="field-label">활동</div>
                {draft.items.map((item) => (
                  <div
                    className={`edit-item${item.removed ? ' removed' : ''}`}
                    key={item.id}
                  >
                    <input
                      className="input"
                      value={item.title}
                      aria-label={`${unit.index}주차 활동 제목`}
                      disabled={item.removed}
                      onChange={(event) => patchItem(item.id, { title: event.target.value })}
                    />
                    <input
                      className="input input-sm"
                      type="number"
                      min={0}
                      value={item.minutes}
                      aria-label={`${unit.index}주차 활동 소요 시간(분)`}
                      disabled={item.removed}
                      onChange={(event) => patchItem(item.id, { minutes: event.target.value })}
                    />
                    <input
                      className="input input-sm"
                      type="number"
                      min={1}
                      placeholder="마감일차"
                      value={item.dueDay}
                      aria-label={`${unit.index}주차 활동 마감일(비우면 없음)`}
                      disabled={item.removed}
                      onChange={(event) => patchItem(item.id, { dueDay: event.target.value })}
                    />
                    <select
                      className="input input-sm"
                      value={item.moveTo}
                      aria-label={`${unit.index}주차 활동을 다른 주차로 이동`}
                      disabled={item.removed}
                      onChange={(event) => patchItem(item.id, { moveTo: event.target.value })}
                    >
                      <option value="">이 주차에 두기</option>
                      {map.units
                        .filter((other) => other.id !== unit.id)
                        .map((other) => (
                          <option key={other.id} value={other.id}>
                            {other.index}주차로 이동
                          </option>
                        ))}
                    </select>
                    <button
                      className="x"
                      type="button"
                      aria-label={`${item.title} 제거`}
                      onClick={() => patchItem(item.id, { removed: !item.removed })}
                    >
                      {item.removed ? '↩' : '×'}
                    </button>
                  </div>
                ))}

                {draft.adds.map((add, index) => (
                  <div className="edit-item added" key={`add-${index}`}>
                    <span className="chip chip-sm">
                      새 {add.kind} — {add.title || '(제목 없음)'} {add.minutes}분
                    </span>
                    <button
                      className="x"
                      type="button"
                      aria-label={`추가한 ${add.kind} 빼기`}
                      onClick={() =>
                        setDraft((prev) =>
                          prev
                            ? { ...prev, adds: prev.adds.filter((_, i) => i !== index) }
                            : prev,
                        )
                      }
                    >
                      ×
                    </button>
                  </div>
                ))}

                <div className="edit-item">
                  <select
                    className="input input-sm"
                    value=""
                    aria-label="추할 활동 유형"
                    onChange={(event) => {
                      const kind = event.target.value
                      if (!kind || !draft) return
                      patchDraft({
                        adds: [...draft.adds, { kind, title: '', minutes: '30' }],
                      })
                    }}
                  >
                    <option value="">+ 활동 유형 선택</option>
                    {ADDABLE_KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {kind} 추가
                      </option>
                    ))}
                  </select>
                  {draft.adds.length > 0 && (
                    <input
                      className="input"
                      value={draft.adds[draft.adds.length - 1].title}
                      placeholder="활동 제목"
                      aria-label="추가할 활동 제목"
                      onChange={(event) =>
                        setDraft((prev) => {
                          if (!prev || prev.adds.length === 0) return prev
                          const adds = [...prev.adds]
                          adds[adds.length - 1] = {
                            ...adds[adds.length - 1],
                            title: event.target.value,
                          }
                          return { ...prev, adds }
                        })
                      }
                    />
                  )}
                </div>

                <div className="edit-actions">
                  <button
                    className="btn btn-primary btn-xs"
                    type="button"
                    onClick={() => void saveEdit(unit)}
                    disabled={saving}
                  >
                    {saving ? '적용 중…' : '저장'}
                  </button>
                  <button className="btn btn-ghost btn-xs" type="button" onClick={cancelEdit}>
                    취소
                  </button>
                </div>
              </div>
            ) : (
              <>
                <h3>{unit.title}</h3>
                {unit.summary && <p className="sum">{unit.summary}</p>}
                {unit.items.map((item) => (
                  <div className="act-item" key={item.id}>
                    <span className={`kind kind-${item.kind}`}>{item.kind}</span>
                    <div>
                      <b>{item.title}</b>
                      <div className="act-meta">
                        {item.minutes}분
                        {item.due_label ? ` · ${item.due_label}` : ''}
                        {item.note ? ` · ${item.note}` : ''}
                      </div>
                    </div>
                  </div>
                ))}
                <button className="linkish" type="button" onClick={() => startEdit(unit)}>
                  이 주차 편집
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      {dialogOpen && (
        <div className="modal-overlay" onClick={() => void closeDialog(true)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="수정 요청"
            onClick={(event) => event.stopPropagation()}
          >
            <h2>수정 요청</h2>
            <p className="hint">
              바꾸고 싶은 내용을 문장으로 적어 주세요. 예: “3주차에 토론 추가”, “2주차
              제목을 …로 바꿔 주세요”. 바뀌는 내용을 먼저 보여 드리고, 확인하면 적용합니다.
            </p>
            <label className="field-label" htmlFor="change-request-text">
              바꾸고 싶은 내용
            </label>
            <textarea
              id="change-request-text"
              className="textarea"
              rows={3}
              value={requestText}
              onChange={(event) => setRequestText(event.target.value)}
            />
            {preview && (
              <div className="panel" style={{ padding: 12 }}>
                <div className="field-label">이렇게 바뀝니다</div>
                <ul className="summary-list">
                  {preview.summary.map((line, index) => (
                    <li key={index}>{line}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="edit-actions">
              {preview ? (
                <>
                  <button
                    className="btn btn-primary btn-xs"
                    type="button"
                    onClick={() => void handleApplyRequest()}
                    disabled={dialogBusy}
                  >
                    적용
                  </button>
                  <button
                    className="btn btn-ghost btn-xs"
                    type="button"
                    onClick={() => void closeDialog(true)}
                  >
                    취소
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="btn btn-primary btn-xs"
                    type="button"
                    onClick={() => void handlePreview()}
                    disabled={dialogBusy}
                  >
                    {dialogBusy ? '확인 중…' : '미리 보기'}
                  </button>
                  <button
                    className="btn btn-ghost btn-xs"
                    type="button"
                    onClick={() => void closeDialog(false)}
                  >
                    닫기
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

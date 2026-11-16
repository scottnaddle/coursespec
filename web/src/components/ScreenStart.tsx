import { useRef, useState } from 'react'
import { createDraft } from '../api'
import type { Draft } from '../types'

const ACCEPT = '.pdf,.docx,.hwp,.hwpx,.txt,.md,.markdown'

interface ScreenStartProps {
  onCreated: (draft: Draft) => void
}

interface Step {
  title: string
  desc: string
  state: 'done' | 'run' | 'wait'
}

export function ScreenStart({ onCreated }: ScreenStartProps) {
  const [title, setTitle] = useState('')
  const [goals, setGoals] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const steps: Step[] = [
    {
      title: '과목과 목표 이해하기',
      desc: '과목 이름과 목표를 바탕으로 과정의 방향을 잡습니다.',
      state: loading ? 'done' : 'done',
    },
    {
      title: '학습목표와 주차를 정리하는 중',
      desc: '학습목표와 주차 구성을 다듬고 있습니다.',
      state: loading ? 'run' : 'wait',
    },
    {
      title: '평가 구성 제안',
      desc: '평가 항목과 비중 초안을 제안합니다.',
      state: 'wait',
    },
  ]

  function addFiles(list: FileList | null) {
    if (!list) return
    setFiles((prev) => [...prev, ...Array.from(list)])
  }

  function removeFile(name: string) {
    setFiles((prev) => prev.filter((file) => file.name !== name))
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!title.trim()) {
      setError('과목 이름을 입력해 주세요. 과목 이름만으로도 초안을 만들 수 있습니다.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const draft = await createDraft(title.trim(), goals.trim(), files)
      onCreated(draft)
    } catch (err) {
      setError(err instanceof Error ? err.message : '초안을 만들지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="h-row">
        <div>
          <h1>
            이번 학기, 무엇을 가르치시나요? <span className="badge new">새 기능</span>
          </h1>
          <p className="lede">
            과목 이름과 가르치고 싶은 점만 적어도 실라버스 수준 강의계획서 초안을 만들어 드려요.
            책·원고·메모가 있으면 더 정확해지지만, 없어도 시작할 수 있습니다.
          </p>
        </div>
      </div>

      <form className="split" onSubmit={handleSubmit} noValidate>
        <div className="col">
          <div className="panel" style={{ padding: '20px 20px 18px' }}>
            <label className="field-label" htmlFor="course-title">
              과목 이름
            </label>
            <input
              id="course-title"
              className="input input-lg"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="예: AI 에이전트 시대의 교육"
              required
            />

            <div style={{ height: 14 }} />

            <label className="field-label" htmlFor="course-goals">
              가르치고 싶은 점 · 목표 <span className="opt">있으면 적어 주세요</span>
            </label>
            <textarea
              id="course-goals"
              className="textarea"
              style={{ minHeight: 118 }}
              value={goals}
              onChange={(event) => setGoals(event.target.value)}
              placeholder="예: 교사 대상 4주 과정으로, 개념·설계·윤리를 다루고 싶습니다."
            />

            <div style={{ height: 16 }} />

            <span className="field-label" id="file-label">
              참고 자료 <span className="opt">선택 · 책, 원고, 간단한 메모</span>
            </span>
            <div className="file-list" role="group" aria-labelledby="file-label">
              {files.map((file) => (
                <div className="file" key={file.name}>
                  <div className="file-ico" aria-hidden="true">
                    파일
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <b>{file.name}</b>
                    <span>선택 자료</span>
                  </div>
                  <button
                    type="button"
                    className="x"
                    aria-label={`${file.name} 제거`}
                    onClick={() => removeFile(file.name)}
                  >
                    ×
                  </button>
                </div>
              ))}

              <label className="drop-mini">
                <span className="plus" aria-hidden="true">
                  ＋
                </span>
                자료를 올리거나, 빈 칸으로 두고 초안만 받아도 됩니다
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={ACCEPT}
                  className="visually-hidden"
                  aria-label="참고 자료 업로드"
                  onChange={(event) => addFiles(event.target.files)}
                />
              </label>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginTop: 18,
                gap: 12,
              }}
            >
              <span className="hint-inline">
                초안은 바로 확정되지 않습니다. 다음 화면에서 고칠 수 있어요.
              </span>
              <button className="btn btn-primary" type="submit" disabled={loading}>
                {loading ? '초안 만드는 중…' : '초안 만들기'}
              </button>
            </div>

            {error && (
              <p className="error" role="alert" style={{ marginTop: 14 }}>
                {error}
              </p>
            )}
          </div>
        </div>

        <div className="panel activity" aria-live="polite">
          <h2>{loading ? '강의계획서 초안을 만드는 중' : '만들어질 초안'}</h2>
          <p className="hint">
            과목과 목표를 바탕으로 학습목표, 주차, 평가 구성을 정리합니다. 올려 주신 자료는 참고만
            합니다.
          </p>
          {steps.map((step) => (
            <div className={`step ${step.state === 'done' ? 'done' : step.state === 'run' ? 'run' : ''}`} key={step.title}>
              <div className="orb" aria-hidden="true">
                {step.state === 'done' ? '✓' : step.state === 'run' ? '' : '3'}
              </div>
              <div className="step-body">
                <b>{step.title}</b>
                <span>{step.desc}</span>
                <span className="meta">
                  {step.state === 'done' ? '완료' : step.state === 'run' ? '진행 중' : '대기'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </form>
    </>
  )
}

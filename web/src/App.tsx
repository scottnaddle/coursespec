import { useState } from 'react'
import { openExampleDesign } from './api'
import { ScreenCourseMap } from './components/ScreenCourseMap'
import { ScreenReview } from './components/ScreenReview'
import { ScreenStart } from './components/ScreenStart'
import { Sidebar, type View } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import type { CourseMap, Draft } from './types'

function crumbFor(view: View, label: string | null): string {
  if (view === 'start') return '새 과정 시작'
  if (view === 'review') return '강의계획서 초안'
  return label ?? '과정 지도'
}

export default function App() {
  const [view, setView] = useState<View>('start')
  const [placeholderLabel, setPlaceholderLabel] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [map, setMap] = useState<CourseMap | null>(null)
  const [exampleError, setExampleError] = useState<string | null>(null)
  const [exampleBusy, setExampleBusy] = useState(false)

  function handleNavigate(next: View, label?: string) {
    setView(next)
    if (label) setPlaceholderLabel(label)
  }

  function handleCreated(created: Draft) {
    setDraft(created)
    setMap(null)
    setView('review')
  }

  function handleUpdated(updated: Draft) {
    setDraft(updated)
  }

  function handleDesigned(designed: CourseMap) {
    setMap(designed)
    setView('map')
  }

  function handleStartNew() {
    setDraft(null)
    setMap(null)
    setView('start')
  }

  async function handleOpenExample() {
    setExampleBusy(true)
    setExampleError(null)
    try {
      const { map: exampleMap } = await openExampleDesign()
      setMap(exampleMap)
      setView('map')
    } catch (err) {
      setExampleError(err instanceof Error ? err.message : '예시 과정을 열지 못했습니다.')
    } finally {
      setExampleBusy(false)
    }
  }

  return (
    <div className="app">
      <Sidebar view={view} courseName={draft?.title ?? map?.title ?? null} onNavigate={handleNavigate} />
      <div className="main">
        <Topbar crumb={crumbFor(view, placeholderLabel)} />
        <div className={view === 'review' ? 'content tight' : 'content'}>
          {view === 'start' && <ScreenStart onCreated={handleCreated} />}

          {view === 'review' &&
            (draft ? (
              <ScreenReview
                key={draft.id}
                draft={draft}
                onUpdated={handleUpdated}
                onStartNew={handleStartNew}
                onDesigned={handleDesigned}
              />
            ) : (
              <div className="panel placeholder" style={{ padding: 20 }}>
                <h2>아직 초안이 없습니다</h2>
                <p>먼저 새 과정 시작에서 과목 이름을 입력해 초안을 만들어 주세요.</p>
              </div>
            ))}

          {view === 'map' &&
            (map ? (
              <ScreenCourseMap key={map.design_id} map={map} onChange={setMap} />
            ) : (
              <div className="panel placeholder" style={{ padding: 20 }}>
                <h2>아직 열린 설계서가 없습니다</h2>
                <p>
                  강의계획서 초안에서 “이 초안으로 과정 설계하기”를 누르시거나, 예시
                  과정을 열어 과정 지도를 확인해 보세요.
                </p>
                {exampleError && (
                  <p className="error" role="alert">
                    {exampleError}
                  </p>
                )}
                <button
                  className="btn btn-ghost"
                  type="button"
                  onClick={() => void handleOpenExample()}
                  disabled={exampleBusy}
                >
                  {exampleBusy ? '여는 중…' : '예시 과정 열기'}
                </button>
              </div>
            ))}

          {view === 'placeholder' && (
            <div className="panel placeholder" style={{ padding: 20 }}>
              <h2>{placeholderLabel ?? '과정 지도'}</h2>
              <p>이 화면은 다음 단계에서 제공됩니다. 지금은 실라버스 초안을 만들고 고칠 수 있어요.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

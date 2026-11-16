import { useState } from 'react'
import { ScreenReview } from './components/ScreenReview'
import { ScreenStart } from './components/ScreenStart'
import { Sidebar, type View } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import type { Draft } from './types'

function crumbFor(view: View, label: string | null): string {
  if (view === 'start') return '새 과정 시작'
  if (view === 'review') return '강의계획서 초안'
  return label ?? '과정 지도'
}

export default function App() {
  const [view, setView] = useState<View>('start')
  const [placeholderLabel, setPlaceholderLabel] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)

  function handleNavigate(next: View, label?: string) {
    setView(next)
    if (label) setPlaceholderLabel(label)
  }

  function handleCreated(created: Draft) {
    setDraft(created)
    setView('review')
  }

  function handleUpdated(updated: Draft) {
    setDraft(updated)
  }

  function handleStartNew() {
    setDraft(null)
    setView('start')
  }

  return (
    <div className="app">
      <Sidebar view={view} courseName={draft?.title ?? null} onNavigate={handleNavigate} />
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
              />
            ) : (
              <div className="panel placeholder" style={{ padding: 20 }}>
                <h2>아직 초안이 없습니다</h2>
                <p>먼저 새 과정 시작에서 과목 이름을 입력해 초안을 만들어 주세요.</p>
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

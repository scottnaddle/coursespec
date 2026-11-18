export type View = 'start' | 'review' | 'map' | 'placeholder'

interface SidebarProps {
  view: View
  courseName: string | null
  onNavigate: (view: View, label?: string) => void
}

const PLACEHOLDER_ITEMS: { view: View; label: string; note: string }[] = [
  { view: 'placeholder', label: '오픈마익 수업', note: '다음 단계에서 제공' },
  { view: 'placeholder', label: 'LMS로 내보내기', note: '다음 단계에서 제공' },
  { view: 'placeholder', label: '변경 검토', note: '다음 단계에서 제공' },
]

export function Sidebar({ view, courseName, onNavigate }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo" aria-hidden="true">
          CS
        </div>
        <div>
          <div className="brand-name">CourseSpec</div>
          <div className="brand-sub">과정 설계 도우미</div>
        </div>
      </div>

      <nav className="nav" aria-label="주요 메뉴">
        <button
          className={view === 'start' ? 'active' : ''}
          onClick={() => onNavigate('start')}
        >
          <span aria-hidden="true">＋</span>
          <span>새 과정 시작</span>
        </button>
        <button
          className={view === 'review' ? 'active' : ''}
          onClick={() => onNavigate('review')}
        >
          <span aria-hidden="true">✎</span>
          <span>강의계획서 초안</span>
        </button>
        <button
          className={view === 'map' ? 'active' : ''}
          onClick={() => onNavigate('map')}
        >
          <span aria-hidden="true">▦</span>
          <span>과정 지도</span>
        </button>
        {PLACEHOLDER_ITEMS.map((item) => (
          <button key={item.label} onClick={() => onNavigate(item.view, item.label)}>
            <span aria-hidden="true">·</span>
            <span>{item.label}</span>
            <span className="pill">다음 단계</span>
          </button>
        ))}
        <div className="nav-off" aria-disabled="true">
          <span aria-hidden="true">·</span>
          <span>학습자 튜터</span>
          <span className="pill">곧 제공</span>
        </div>
      </nav>

      <div className="side-foot">
        <div className="course-chip">
          <b>{courseName ?? 'AI 에이전트 시대의 교육'}</b>
          {courseName ? '초안 작업 중' : '4주 과정 · 예시 강좌'}
        </div>
      </div>
    </aside>
  )
}

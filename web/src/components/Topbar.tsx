interface TopbarProps {
  crumb: string
}

export function Topbar({ crumb }: TopbarProps) {
  return (
    <header className="topbar">
      <div className="crumbs">
        내 과정 <span className="dot" /> <b>{crumb}</b>
      </div>
      <div className="top-actions">
        <div className="user">
          <span className="avatar" aria-hidden="true">
            교
          </span>
          교수님
        </div>
      </div>
    </header>
  )
}

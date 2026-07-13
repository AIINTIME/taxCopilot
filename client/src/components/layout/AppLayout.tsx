import { Outlet } from 'react-router-dom'
import { useState } from 'react'
import { Sidebar } from '../sidebar/Sidebar'
import { TopHeader } from './TopHeader'

export function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <div className={`app-shell ${sidebarCollapsed ? 'is-sidebar-collapsed' : ''}`}>
      <Sidebar isCollapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((value) => !value)} />
      <div className="workspace-shell">
        <TopHeader isSidebarCollapsed={sidebarCollapsed} onToggleSidebar={() => setSidebarCollapsed((value) => !value)} />
        <main className="workspace" aria-label="AI tax copilot workspace">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminProtectedRoute } from './components/auth/AdminProtectedRoute'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AdminLayout } from './components/layout/AdminLayout'
import { AppLayout } from './components/layout/AppLayout'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { AdminDashboardPage } from './pages/AdminDashboardPage'
import { AdminRegisterPage } from './pages/AdminRegisterPage'
import { DashboardPage } from './pages/DashboardPage'
import { DeepResearchPage } from './pages/DeepResearchPage'
import { ItActComparisonPage } from './pages/ItActComparisonPage'
import { LoginPage } from './pages/LoginPage'
import { NewChatPage } from './pages/NewChatPage'
import { NewProjectPage } from './pages/NewProjectPage'
import { ProfilePage } from './pages/ProfilePage'
import { ProjectPage } from './pages/ProjectPage'
import { RegisterPage } from './pages/RegisterPage'
import { SecurityAuditPage } from './pages/SecurityAuditPage'
import { WorkflowPage } from './pages/WorkflowPage'
import { AppStateProvider } from './store/AppState'
import { AdminAuthProvider } from './store/AdminAuthContext'
import { AuthProvider } from './store/AuthContext'

export default function App() {
  return (
    <AuthProvider>
      <AdminAuthProvider>
        <AppStateProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/admin/register" element={<AdminRegisterPage />} />
            <Route element={<AdminProtectedRoute />}>
              <Route element={<AdminLayout />}>
                <Route path="/admin" element={<AdminDashboardPage />} />
                <Route path="/admin/*" element={<AdminDashboardPage />} />
              </Route>
            </Route>
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/new-chat" element={<NewChatPage />} />
                <Route path="/deep-research" element={<DeepResearchPage />} />
                <Route path="/it-act-comparison" element={<ItActComparisonPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/security-audit" element={<SecurityAuditPage />} />
                <Route path="/projects/new" element={<NewProjectPage />} />
                <Route path="/projects/:projectId" element={<ProjectPage />} />
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="/personal-tax" element={<WorkflowPage />} />
                <Route path="/corporate" element={<WorkflowPage />} />
                <Route path="/capital-gains" element={<WorkflowPage />} />
                <Route path="/notices" element={<WorkflowPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Route>
          </Routes>
        </AppStateProvider>
      </AdminAuthProvider>
    </AuthProvider>
  )
}

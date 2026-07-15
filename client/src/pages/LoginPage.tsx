import { Building2, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck, User } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../services/api/authApi'
import type { Organization } from '../services/api/authApi'
import { useAdminAuth } from '../store/useAdminAuth'
import { useAuth } from '../store/useAuth'

type LocationState = {
  from?: { pathname?: string }
}

export function LoginPage() {
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<'user' | 'admin'>(
    searchParams.get('tab') === 'admin' ? 'admin' : 'user',
  )
  const [orgs, setOrgs] = useState<Organization[]>([])
  const [orgId, setOrgId] = useState('')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const { isAuthenticated, login } = useAuth()
  const { isAdminAuthenticated, login: adminLogin } = useAdminAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as LocationState | null
  const returnPath = state?.from?.pathname ?? '/'

  useEffect(() => {
    authApi.getOrganizations().then(setOrgs).catch(() => undefined)
  }, [])

  if (isAuthenticated) return <Navigate to="/" replace />
  if (isAdminAuthenticated) return <Navigate to="/admin" replace />

  function switchTab(next: 'user' | 'admin') {
    setTab(next)
    setError('')
    setEmail('')
    setUsername('')
    setPassword('')
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!orgId) {
      setError('Please select an organization')
      return
    }
    setError('')
    setIsSubmitting(true)

    try {
      if (tab === 'user') {
        await login(email, password, orgId)
        navigate(returnPath, { replace: true })
      } else {
        await adminLogin(username, password, orgId)
        navigate('/admin', { replace: true })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to log in')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel glass-panel" aria-labelledby="login-title">
        <div className="auth-brand">
          <span className="auth-brand__mark">
            <img src="/logo/logo.png" alt="" />
          </span>
          <div>
            <strong>TaxAI</strong>
            <span>Secure workspace</span>
          </div>
        </div>

        <div className="auth-tab-toggle" role="tablist">
          <button
            role="tab"
            aria-selected={tab === 'user'}
            className={`auth-tab ${tab === 'user' ? 'is-active' : ''}`}
            type="button"
            onClick={() => switchTab('user')}
          >
            <User size={15} />
            User
          </button>
          <button
            role="tab"
            aria-selected={tab === 'admin'}
            className={`auth-tab ${tab === 'admin' ? 'is-active' : ''}`}
            type="button"
            onClick={() => switchTab('admin')}
          >
            <ShieldCheck size={15} />
            Admin
          </button>
        </div>

        <div className="auth-heading">
          <h1 id="login-title">Log in</h1>
          <p>{tab === 'user' ? 'Continue to your tax copilot dashboard.' : 'Access the admin console.'}</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>Organization</span>
            <div className="auth-input auth-input--select">
              <Building2 size={18} />
              <select
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                required
              >
                <option value="">Select organization</option>
                {orgs.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.display_name}
                  </option>
                ))}
              </select>
            </div>
          </label>

          {tab === 'user' ? (
            <label>
              <span>Email</span>
              <div className="auth-input">
                <Mail size={18} />
                <input
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </label>
          ) : (
            <label>
              <span>Username</span>
              <div className="auth-input">
                <User size={18} />
                <input
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </div>
            </label>
          )}

          <label>
            <span>Password</span>
            <div className="auth-input">
              <LockKeyhole size={18} />
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button type="button" onClick={() => setShowPassword((v) => !v)} aria-label="Toggle password">
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
          </label>

          {error ? <p className="auth-error">{error}</p> : null}

          <button className="auth-submit" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Logging in...' : 'Log in'}
          </button>
        </form>

        <p className="auth-switch">
          {tab === 'user' ? (
            <>New to TaxAI? <Link to="/register">Create an account</Link></>
          ) : (
            <>Continue to admin panel</>
            // <>New admin? <Link to="/admin/register">Create admin account</Link></>
          )}
        </p>
      </section>
    </main>
  )
}

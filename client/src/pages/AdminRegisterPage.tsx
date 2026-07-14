import { Building2, Eye, EyeOff, LockKeyhole, ShieldCheck, User } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { authApi } from '../services/api/authApi'
import type { Organization } from '../services/api/authApi'
import { useAdminAuth } from '../store/useAdminAuth'

export function AdminRegisterPage() {
  const [orgs, setOrgs] = useState<Organization[]>([])
  const [orgId, setOrgId] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const { isAdminAuthenticated, register } = useAdminAuth()
  const navigate = useNavigate()

  useEffect(() => {
    authApi.getOrganizations().then(setOrgs).catch(() => undefined)
  }, [])

  if (isAdminAuthenticated) return <Navigate to="/admin" replace />

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!orgId) {
      setError('Please select an organization')
      return
    }
    setError('')
    setIsSubmitting(true)

    try {
      await register(username, password, orgId)
      navigate('/admin', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create account')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel glass-panel" aria-labelledby="admin-register-title">
        <div className="auth-brand">
          <span className="auth-brand__mark">
            <img src="/logo/logo.png" alt="" />
          </span>
          <div>
            <strong>TaxAI</strong>
            <span>Admin registration</span>
          </div>
        </div>

        <div className="auth-heading">
          <h1 id="admin-register-title">Create admin account</h1>
          <p>Set up admin access to the TaxAI console.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>Organization</span>
            <div className="auth-input auth-input--select">
              <Building2 size={18} />
              <select value={orgId} onChange={(e) => setOrgId(e.target.value)} required>
                <option value="">Select organization</option>
                {orgs.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.display_name}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label>
            <span>Username</span>
            <div className="auth-input">
              <User size={18} />
              <input
                type="text"
                autoComplete="username"
                value={username}
                minLength={3}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
          </label>

          <label>
            <span>Password</span>
            <div className="auth-input">
              <LockKeyhole size={18} />
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                value={password}
                minLength={8}
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
            <ShieldCheck size={16} />
            {isSubmitting ? 'Creating account...' : 'Create admin account'}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link to="/login?tab=admin">Log in</Link>
        </p>
      </section>
    </main>
  )
}

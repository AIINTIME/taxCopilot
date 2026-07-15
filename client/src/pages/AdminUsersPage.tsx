import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  UserCheck,
  UserRound,
  UserX,
  Users,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { adminApi } from '../services/api/adminApi'
import type { AdminUserItem } from '../services/api/adminApi'
import { useAdminAuth } from '../store/useAdminAuth'

const pageSize = 6

type ActionMode = 'edit' | 'password' | 'status' | null

export function AdminUsersPage() {
  const { accessToken } = useAdminAuth()
  const [users, setUsers] = useState<AdminUserItem[]>([])
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const [actionUser, setActionUser] = useState<AdminUserItem | null>(null)
  const [actionMode, setActionMode] = useState<ActionMode>(null)
  const [editName, setEditName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')

  async function loadUsers() {
    if (!accessToken) return

    setIsLoading(true)
    setError('')
    try {
      setUsers(await adminApi.getUsers(accessToken))
    } catch (err) {
      setUsers([])
      setError(err instanceof Error ? err.message : 'Unable to load users')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void loadUsers()
  }, [accessToken])

  const filteredUsers = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return users

    return users.filter((user) => {
      return (
        user.name.toLowerCase().includes(normalizedQuery) ||
        user.email.toLowerCase().includes(normalizedQuery)
      )
    })
  }, [query, users])

  const pageCount = Math.max(1, Math.ceil(filteredUsers.length / pageSize))
  const visibleUsers = filteredUsers.slice((page - 1) * pageSize, page * pageSize)

  useEffect(() => {
    setPage(1)
  }, [query])

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [page, pageCount])

  function openEdit(user: AdminUserItem) {
    setActionUser(user)
    setActionMode('edit')
    setEditName(user.name)
    setEditEmail(user.email)
    setNewPassword('')
    setError('')
    setMessage('')
  }

  function closeActionModal() {
    setActionUser(null)
    setActionMode(null)
    setEditName('')
    setEditEmail('')
    setNewPassword('')
  }

  function openPasswordReset(user: AdminUserItem) {
    setActionUser(user)
    setActionMode('password')
    setEditName('')
    setEditEmail('')
    setNewPassword('')
    setError('')
    setMessage('')
  }

  function openStatusChange(user: AdminUserItem) {
    setActionUser(user)
    setActionMode('status')
    setEditName('')
    setEditEmail('')
    setNewPassword('')
    setError('')
    setMessage('')
  }

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!accessToken) return

    setIsSubmitting(true)
    setError('')
    setMessage('')

    try {
      const createdUser = await adminApi.createUser(accessToken, { name, email, password })
      setUsers((current) => [createdUser, ...current])
      setName('')
      setEmail('')
      setPassword('')
      setMessage(`Created account for ${createdUser.name}.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create user')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleUpdateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!accessToken || !actionUser) return

    setIsSubmitting(true)
    setError('')
    setMessage('')

    try {
      const updatedUser = await adminApi.updateUser(accessToken, actionUser.id, {
        name: editName,
        email: editEmail,
      })
      setUsers((current) => (
        current.map((user) => (user.id === updatedUser.id ? updatedUser : user))
      ))
      closeActionModal()
      setMessage(`Updated ${updatedUser.name}.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update user')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleSetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!accessToken || !actionUser) return

    setIsSubmitting(true)
    setError('')
    setMessage('')

    try {
      await adminApi.setUserPassword(accessToken, actionUser.id, newPassword)
      closeActionModal()
      setMessage(`Updated password for ${actionUser.name}.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update password')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleSetStatus() {
    if (!accessToken || !actionUser) return

    setIsSubmitting(true)
    setError('')
    setMessage('')

    try {
      const updatedUser = await adminApi.setUserStatus(
        accessToken,
        actionUser.id,
        !actionUser.is_active,
      )
      setUsers((current) => (
        current.map((user) => (user.id === updatedUser.id ? updatedUser : user))
      ))
      closeActionModal()
      setMessage(`${updatedUser.name} is now ${updatedUser.is_active ? 'active' : 'deactivated'}.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update account status')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="admin-users-page">
      <div className="admin-users-toolbar">
        <div>
          <p>Access control</p>
          <h2>User Management</h2>
        </div>
        <div className="admin-users-toolbar__actions">
          <button type="button" onClick={() => void loadUsers()} disabled={isLoading}>
            <RefreshCw size={14} />
            Refresh
          </button>
          <span className="admin-users-count">
            <Users size={15} />
            {filteredUsers.length} users
          </span>
        </div>
      </div>

      <div className="admin-users-layout">
        <div className="admin-users-panel">
          <div className="admin-users-search">
            <Search size={16} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search users by name or email"
            />
          </div>

          {error ? <p className="admin-form-error">{error}</p> : null}
          {message ? (
            <p className="admin-form-success">
              <CheckCircle2 size={14} />
              {message}
            </p>
          ) : null}

          <div className="admin-users-table">
            <div className="admin-users-table__head">
              <span>User</span>
              <span>Email</span>
              <span>Created</span>
              <span>Status</span>
              <span>Actions</span>
            </div>

            {isLoading ? (
              <div className="admin-users-empty">Loading users...</div>
            ) : visibleUsers.length === 0 ? (
              <div className="admin-users-empty">No users match your search.</div>
            ) : (
              visibleUsers.map((user) => (
                <article key={user.id} className="admin-users-row">
                  <div className="admin-users-row__identity">
                    <span className="admin-avatar admin-avatar--sm">
                      {user.name[0]?.toUpperCase() ?? <UserRound size={14} />}
                    </span>
                    <strong>{user.name}</strong>
                  </div>
                  <span>{user.email}</span>
                  <time>{new Date(user.created_at).toLocaleDateString()}</time>
                  <span className={`admin-badge ${user.is_active ? 'admin-badge--green' : 'admin-badge--red'}`}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </span>
                  <div className="admin-users-row__actions">
                    <button type="button" onClick={() => openEdit(user)} title="Edit user">
                      <Pencil size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => openPasswordReset(user)}
                      title="Set password"
                    >
                      <KeyRound size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => openStatusChange(user)}
                      title={user.is_active ? 'Deactivate user' : 'Reactivate user'}
                    >
                      {user.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>

          <div className="admin-users-pagination">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page === 1}
            >
              <ArrowLeft size={14} />
              Previous
            </button>
            <span>
              Page {page} of {pageCount}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
              disabled={page === pageCount}
            >
              Next
              <ArrowRight size={14} />
            </button>
          </div>
        </div>

        <aside className="admin-users-side">
          <form className="admin-users-form" onSubmit={handleCreateUser}>
            <div>
              <p>New account</p>
              <h3>Create User</h3>
            </div>
            <label>
              <span>Name</span>
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                minLength={2}
                maxLength={120}
                required
              />
            </label>
            <label>
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              <span>Temporary password</span>
              <input
                type="text"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={8}
                maxLength={128}
                required
              />
            </label>
            <button type="submit" className="admin-primary-action" disabled={isSubmitting}>
              <Plus size={14} />
              Create user
            </button>
          </form>
        </aside>
      </div>

      {actionUser && actionMode ? (
        <div className="admin-users-modal" role="dialog" aria-modal="true">
          <div className="admin-users-modal__dialog">
            <header>
              <div>
                <p>
                  {actionMode === 'edit'
                    ? 'Edit user'
                    : actionMode === 'password'
                      ? 'Set password'
                      : actionUser.is_active
                        ? 'Deactivate user'
                        : 'Reactivate user'}
                </p>
                <h3>{actionUser.name}</h3>
              </div>
              <button type="button" onClick={closeActionModal} aria-label="Close">
                <X size={16} />
              </button>
            </header>

            {actionMode === 'edit' ? (
              <form className="admin-users-form__inner" onSubmit={handleUpdateUser}>
                <label>
                  <span>Name</span>
                  <input
                    type="text"
                    value={editName}
                    onChange={(event) => setEditName(event.target.value)}
                    minLength={2}
                    maxLength={120}
                    required
                  />
                </label>
                <label>
                  <span>Email</span>
                  <input
                    type="email"
                    value={editEmail}
                    onChange={(event) => setEditEmail(event.target.value)}
                    required
                  />
                </label>
                <button type="submit" className="admin-secondary-action" disabled={isSubmitting}>
                  <Pencil size={14} />
                  Save changes
                </button>
              </form>
            ) : actionMode === 'password' ? (
              <form className="admin-users-form__inner" onSubmit={handleSetPassword}>
                <label>
                  <span>New password</span>
                  <input
                    type="text"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    minLength={8}
                    maxLength={128}
                    required
                  />
                </label>
                <button type="submit" className="admin-secondary-action" disabled={isSubmitting}>
                  <KeyRound size={14} />
                  Set password
                </button>
              </form>
            ) : (
              <div className="admin-users-status-confirm">
                <p>
                  {actionUser.is_active
                    ? 'This user will no longer be able to log in or refresh an existing session.'
                    : 'This user will regain access with their existing password.'}
                </p>
                <button
                  type="button"
                  className={actionUser.is_active ? 'admin-danger-action' : 'admin-secondary-action'}
                  onClick={() => void handleSetStatus()}
                  disabled={isSubmitting}
                >
                  {actionUser.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                  {actionUser.is_active ? 'Deactivate user' : 'Reactivate user'}
                </button>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  )
}

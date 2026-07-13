import { Camera, CheckCircle2, KeyRound, Pencil, Save, Upload, UserRound, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ChangeEvent, DragEvent, FormEvent } from 'react'
import { useAuth } from '../store/useAuth'

export function ProfilePage() {
  const { user, updateProfile, uploadProfilePhoto, changePassword } = useAuth()
  const [name, setName] = useState(user?.name ?? '')
  const [bio, setBio] = useState(user?.bio ?? '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [profileMessage, setProfileMessage] = useState('')
  const [photoMessage, setPhotoMessage] = useState('')
  const [passwordMessage, setPasswordMessage] = useState('')
  const [profileError, setProfileError] = useState('')
  const [photoError, setPhotoError] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [isSavingProfile, setIsSavingProfile] = useState(false)
  const [isUploadingPhoto, setIsUploadingPhoto] = useState(false)
  const [isSavingPassword, setIsSavingPassword] = useState(false)
  const [isPhotoModalOpen, setIsPhotoModalOpen] = useState(false)
  const [isPhotoDragging, setIsPhotoDragging] = useState(false)

  useEffect(() => {
    setName(user?.name ?? '')
    setBio(user?.bio ?? '')
  }, [user])

  const initials =
    user?.name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('') || 'U'

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setProfileError('')
    setProfileMessage('')
    setIsSavingProfile(true)

    try {
      await updateProfile({
        name,
        bio: bio.trim() || null,
      })
      setProfileMessage('Profile updated')
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : 'Unable to update profile')
    } finally {
      setIsSavingProfile(false)
    }
  }

  async function uploadPhoto(file: File) {
    if (!file) return

    setPhotoError('')
    setPhotoMessage('')

    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setPhotoError('Use a JPEG, PNG, or WebP image')
      return
    }

    if (file.size > 2 * 1024 * 1024) {
      setPhotoError('Profile photo must be 2 MB or smaller')
      return
    }

    setIsUploadingPhoto(true)
    try {
      await uploadProfilePhoto(file)
      setPhotoMessage('Photo uploaded')
      setIsPhotoModalOpen(false)
      setIsPhotoDragging(false)
    } catch (error) {
      setPhotoError(error instanceof Error ? error.message : 'Unable to upload photo')
    } finally {
      setIsUploadingPhoto(false)
    }
  }

  async function handlePhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (file) await uploadPhoto(file)
  }

  function handlePhotoDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    if (!isUploadingPhoto) setIsPhotoDragging(true)
  }

  function handlePhotoDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
    setIsPhotoDragging(false)
  }

  async function handlePhotoDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setIsPhotoDragging(false)
    if (isUploadingPhoto) return

    const file = event.dataTransfer.files?.[0]
    if (file) await uploadPhoto(file)
  }

  async function handlePasswordSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPasswordError('')
    setPasswordMessage('')

    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match')
      return
    }

    setIsSavingPassword(true)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPasswordMessage('Password changed')
    } catch (error) {
      setPasswordError(error instanceof Error ? error.message : 'Unable to change password')
    } finally {
      setIsSavingPassword(false)
    }
  }

  return (
    <section className="profile-page">
      <div className="profile-hero">
        <div className="profile-avatar profile-avatar--large">
          {user?.profile_photo_url ? <img src={user.profile_photo_url} alt="" /> : <span>{initials}</span>}
        </div>
        <div>
          <p>Account settings</p>
          <h1>Profile management</h1>
          <span>{user?.email}</span>
        </div>
      </div>

      <div className="profile-layout">
        <form className="profile-card glass-panel" onSubmit={handleProfileSubmit}>
          <header>
            <div>
              <Camera size={20} />
            </div>
            <div>
              <h2>Public profile</h2>
              <p>Manage the identity shown inside your workspace.</p>
            </div>
          </header>

          <label>
            <span>Name</span>
            <input value={name} minLength={2} onChange={(event) => setName(event.target.value)} required />
          </label>

          <div className="profile-photo-field">
            <div className="profile-photo-field__avatar">
              <div className="profile-avatar profile-avatar--editable">
                {user?.profile_photo_url ? <img src={user.profile_photo_url} alt="" /> : <span>{initials}</span>}
                <button
                  type="button"
                  className="profile-photo-edit"
                  aria-label="Change profile photo"
                  onClick={() => {
                    setPhotoError('')
                    setPhotoMessage('')
                    setIsPhotoModalOpen(true)
                  }}
                >
                  <Pencil size={13} />
                </button>
              </div>
            </div>
            <div>
              <span>Profile photo</span>
              <small>Use the pencil button to upload a JPEG, PNG, or WebP image up to 2 MB.</small>
            </div>
          </div>

          {photoError ? <p className="profile-error">{photoError}</p> : null}
          {photoMessage ? (
            <p className="profile-success">
              <CheckCircle2 size={16} />
              {photoMessage}
            </p>
          ) : null}

          <label>
            <span>Bio</span>
            <textarea
              value={bio}
              maxLength={500}
              rows={5}
              onChange={(event) => setBio(event.target.value)}
              placeholder="A short note about your role, tax focus, or team."
            />
          </label>

          {profileError ? <p className="profile-error">{profileError}</p> : null}
          {profileMessage ? (
            <p className="profile-success">
              <CheckCircle2 size={16} />
              {profileMessage}
            </p>
          ) : null}

          <button className="profile-save" type="submit" disabled={isSavingProfile}>
            <Save size={17} />
            {isSavingProfile ? 'Saving...' : 'Save profile'}
          </button>
        </form>

        <form className="profile-card glass-panel" onSubmit={handlePasswordSubmit}>
          <header>
            <div>
              <KeyRound size={20} />
            </div>
            <div>
              <h2>Password</h2>
              <p>Confirm your current password before setting a new one.</p>
            </div>
          </header>

          <label>
            <span>Current password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              required
            />
          </label>

          <label>
            <span>New password</span>
            <input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              minLength={8}
              onChange={(event) => setNewPassword(event.target.value)}
              required
            />
          </label>

          <label>
            <span>Confirm new password</span>
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              minLength={8}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
            />
          </label>

          {passwordError ? <p className="profile-error">{passwordError}</p> : null}
          {passwordMessage ? (
            <p className="profile-success">
              <CheckCircle2 size={16} />
              {passwordMessage}
            </p>
          ) : null}

          <button className="profile-save" type="submit" disabled={isSavingPassword}>
            <UserRound size={17} />
            {isSavingPassword ? 'Changing...' : 'Change password'}
          </button>
        </form>
      </div>

      {isPhotoModalOpen ? (
        <div className="profile-photo-modal" role="presentation">
          <div className="profile-photo-dialog glass-panel" role="dialog" aria-modal="true" aria-labelledby="photo-modal-title">
            <header>
              <div>
                <h2 id="photo-modal-title">Update profile photo</h2>
                <p>Drag an image here or choose one from your device.</p>
              </div>
              <button
                type="button"
                className="profile-photo-close"
                aria-label="Close photo upload"
                onClick={() => {
                  setIsPhotoModalOpen(false)
                  setIsPhotoDragging(false)
                }}
              >
                <X size={18} />
              </button>
            </header>

            <label
              className={`profile-photo-dropzone ${isPhotoDragging ? 'is-dragging' : ''}`}
              onDragOver={handlePhotoDragOver}
              onDragLeave={handlePhotoDragLeave}
              onDrop={handlePhotoDrop}
            >
              <Upload size={26} />
              <strong>{isUploadingPhoto ? 'Uploading...' : 'Drop photo here'}</strong>
              <span>JPEG, PNG, or WebP. Max 2 MB.</span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={handlePhotoChange}
                disabled={isUploadingPhoto}
              />
            </label>

            {photoError ? <p className="profile-error">{photoError}</p> : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}

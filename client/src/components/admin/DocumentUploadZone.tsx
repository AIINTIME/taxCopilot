import { Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { adminApi } from '../../services/api/adminApi'

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md']
const MAX_BYTES = 50 * 1024 * 1024

type QueueItem = {
  name: string
  status: 'uploading' | 'done' | 'error'
  error?: string
}

type DocumentUploadZoneProps = {
  onUploaded: () => void
}

function extensionOf(filename: string) {
  const index = filename.lastIndexOf('.')
  return index === -1 ? '' : filename.slice(index).toLowerCase()
}

function validate(file: File): string | null {
  if (!ACCEPTED_EXTENSIONS.includes(extensionOf(file.name))) {
    return `Unsupported file type. Supported: ${ACCEPTED_EXTENSIONS.join(', ')}`
  }
  if (file.size > MAX_BYTES) {
    return 'File exceeds 50MB limit'
  }
  return null
}

export function DocumentUploadZone({ onUploaded }: DocumentUploadZoneProps) {
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const isUploading = queue.some((item) => item.status === 'uploading')

  async function handleFiles(files: FileList) {
    const fileList = Array.from(files)
    setQueue(fileList.map((file) => ({ name: file.name, status: 'uploading' })))

    function updateAt(index: number, patch: Partial<QueueItem>) {
      setQueue((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)))
    }

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i]
      const validationError = validate(file)
      if (validationError) {
        updateAt(i, { status: 'error', error: validationError })
        continue
      }

      try {
        await adminApi.uploadDocument(file)
        updateAt(i, { status: 'done' })
      } catch (err) {
        updateAt(i, { status: 'error', error: err instanceof Error ? err.message : 'Upload failed' })
      }
    }

    onUploaded()
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsDragging(false)
    if (event.dataTransfer.files.length > 0) void handleFiles(event.dataTransfer.files)
  }

  function handleInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    if (event.target.files && event.target.files.length > 0) void handleFiles(event.target.files)
    event.target.value = ''
  }

  return (
    <div
      className={`admin-upload-area ${isDragging ? 'is-dragging' : ''}`}
      onDragOver={(event) => {
        event.preventDefault()
        setIsDragging(true)
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
    >
      <Upload size={28} />
      <p>{isUploading ? 'Uploading…' : 'Drag and drop a file here, or click to browse'}</p>
      <small>Supports PDF, DOCX, TXT, MD (Max 50MB)</small>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS.join(',')}
        onChange={handleInputChange}
        style={{ display: 'none' }}
      />
      <button
        type="button"
        className="admin-upload-btn"
        disabled={isUploading}
        onClick={() => inputRef.current?.click()}
      >
        <Upload size={14} />
        {isUploading ? 'Uploading…' : 'Upload Document'}
      </button>
      {queue.length > 0 && (
        <div className="admin-upload-status-list">
          {queue.map((item, index) => (
            <p
              key={index}
              className={item.status === 'error' ? 'admin-upload-error' : 'admin-upload-status-line'}
            >
              {item.name} — {item.status === 'error' ? item.error : item.status}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

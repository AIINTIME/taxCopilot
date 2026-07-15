import { FileText } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { DocumentUploadZone } from '../components/admin/DocumentUploadZone'
import { adminApi } from '../services/api/adminApi'
import type { DocumentListItem } from '../services/api/adminApi'

function statusBadgeClass(status: DocumentListItem['status']) {
  if (status === 'EMBEDDED') return 'admin-badge admin-badge--green'
  if (status === 'FAILED') return 'admin-badge admin-badge--red'
  return 'admin-badge admin-badge--yellow'
}

export function AdminDocumentsPage() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([])

  const refresh = useCallback(() => {
    adminApi.listDocuments().then(setDocuments).catch(() => undefined)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return (
    <div className="admin-dashboard">
      <div className="admin-card">
        <div className="admin-card__header">
          <h2>
            <FileText size={16} />
            Upload Document
          </h2>
        </div>
        <DocumentUploadZone onUploaded={refresh} />
      </div>

      <div className="admin-card">
        <div className="admin-card__header">
          <h2>
            <FileText size={16} />
            All Documents
          </h2>
        </div>
        {documents.length === 0 ? (
          <p className="admin-empty">No documents uploaded yet.</p>
        ) : (
          <div className="admin-user-list">
            {documents.map((doc) => (
              <div key={doc.id} className="admin-user-item">
                <FileText size={16} style={{ flexShrink: 0, color: '#64748b' }} />
                <div>
                  <strong>{doc.filename}</strong>
                  <span>
                    {doc.chunks_embedded} chunks · uploaded by {doc.uploaded_by} ·{' '}
                    {new Date(doc.created_at).toLocaleString()}
                  </span>
                </div>
                <span className={statusBadgeClass(doc.status)}>{doc.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

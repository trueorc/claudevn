import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react'
import { useToasts } from '../../contexts/ToastContext'
import './Toast.css'

const icons = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

function Toast({ toast, onClose }) {
  const Icon = icons[toast.variant] || Info

  return (
    <div className={`toast toast-${toast.variant}`}>
      <Icon size={18} className="toast-icon" />
      <span className="toast-message">{toast.message}</span>
      <button className="toast-close" onClick={onClose}>
        <X size={14} />
      </button>
    </div>
  )
}

export function ToastContainer() {
  const { toasts, removeToast } = useToasts()

  if (toasts.length === 0) return null

  return (
    <div className="toast-container">
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          toast={toast}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </div>
  )
}

export default Toast

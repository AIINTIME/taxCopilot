import { useContext } from 'react'
import { AppStateContext } from './appStateContext'

export function useAppState() {
  const value = useContext(AppStateContext)
  if (!value) {
    throw new Error('useAppState must be used inside AppStateProvider')
  }

  return value
}

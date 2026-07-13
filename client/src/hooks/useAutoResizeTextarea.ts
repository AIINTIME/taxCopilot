import { useLayoutEffect, type RefObject } from 'react'

export function useAutoResizeTextarea(ref: RefObject<HTMLTextAreaElement | null>, value: string) {
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return

    element.style.height = '0px'
    element.style.height = `${Math.min(element.scrollHeight, 220)}px`
  }, [ref, value])
}

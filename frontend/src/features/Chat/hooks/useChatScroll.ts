import { useEffect, useRef } from 'react'

/**
 * Auto-scroll hook. Keeps a container element scrolled to the bottom whenever
 * the dependency (e.g. message count) changes.
 *
 * @param dep - Value that triggers a scroll when it changes.
 * @returns Ref to attach to the scrollable container element.
 */
export function useChatScroll<T>(dep: T) {
	const ref = useRef<HTMLDivElement>(null)

	useEffect(() => {
		if (ref.current) {
			ref.current.scrollTop = ref.current.scrollHeight
		}
	}, [dep])

	return ref
}

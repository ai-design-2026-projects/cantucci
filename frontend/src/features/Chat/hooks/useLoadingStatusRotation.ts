import { useState, useEffect, useRef } from 'react'
import { LOADING_MESSAGES, LOADING_EXPRESSIONS, LOADING_ROTATE_MS } from '@/lib/constants'
import type { MascotExpression } from '@/components/mascot'

/**
 * Rotates through loading status messages and matching mascot expressions
 * at a fixed interval while isLoading is true.
 *
 * @param isLoading - When true, the rotation timer runs.
 * @param isError   - When true, forces the 'sad' expression.
 * @returns Current loading message and mascot expression.
 */
export function useLoadingStatusRotation(isLoading: boolean, isError: boolean): {
	message: string
	expression: MascotExpression
} {
	const [index, setIndex] = useState(0)
	const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

	useEffect(() => {
		if (isLoading) {
			setIndex(0)
			timerRef.current = setInterval(() => {
				setIndex((i) => (i + 1) % LOADING_MESSAGES.length)
			}, LOADING_ROTATE_MS)
		} else {
			if (timerRef.current) {
				clearInterval(timerRef.current)
				timerRef.current = null
			}
		}
		return () => {
			if (timerRef.current) clearInterval(timerRef.current)
		}
	}, [isLoading])

	if (isError) {
		return { message: 'Poppy ran into a problem…', expression: 'sad' }
	}

	return {
		message: LOADING_MESSAGES[index],
		expression: LOADING_EXPRESSIONS[index] as MascotExpression,
	}
}

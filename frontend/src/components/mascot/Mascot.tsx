import { motion } from 'framer-motion'

export type MascotExpression = 'happy' | 'focused' | 'excited' | 'sleepy' | 'sad'
export type MascotSize = 'sm' | 'md' | 'lg'

interface MascotProps {
  expression?: MascotExpression
  size?: MascotSize
  className?: string
}

const SIZES: Record<MascotSize, number> = { sm: 32, md: 56, lg: 120 }

/** Eye shapes per expression: [leftEye, rightEye] as path d strings (relative to eye center) */
const EYES: Record<MascotExpression, { left: string; right: string; offsetY: number }> = {
  happy: {
    left: 'M-5,-3 Q-2,-7 1,-3 Q-2,0 -5,-3 Z',
    right: 'M-1,-3 Q2,-7 5,-3 Q2,0 -1,-3 Z',
    offsetY: 0,
  },
  focused: {
    left: 'M-5,-1 L1,-1',
    right: 'M-1,-1 L5,-1',
    offsetY: 0,
  },
  excited: {
    left: 'M-5,-4 A5,5 0 0,1 1,-4 A5,5 0 0,1 -5,-4 Z',
    right: 'M-1,-4 A5,5 0 0,1 5,-4 A5,5 0 0,1 -1,-4 Z',
    offsetY: -2,
  },
  sleepy: {
    left: 'M-5,0 Q-2,-2 1,0',
    right: 'M-1,0 Q2,-2 5,0',
    offsetY: 3,
  },
  sad: {
    left: 'M-5,-3 Q-2,-1 1,-3',
    right: 'M-1,-3 Q2,-1 5,-3',
    offsetY: 2,
  },
}

/** Mouth path per expression */
const MOUTHS: Record<MascotExpression, string> = {
  happy: 'M-8,0 Q0,8 8,0',
  focused: 'M-6,0 Q0,3 6,0',
  excited: 'M-9,0 Q0,12 9,0',
  sleepy: 'M-6,0 L6,0',
  sad: 'M-8,0 Q0,-8 8,0',
}

/** Eyebrow y-offset nudge (positive = lower = less raised) per expression */
const EYEBROW_Y: Record<MascotExpression, number> = {
  happy: 0,
  focused: 4,
  excited: -3,
  sleepy: 5,
  sad: 2,
}

const TRANSITION = { duration: 0.3, ease: 'easeInOut' as const }

/**
 * Poppy the Popcorn Bucket mascot, rendered as inline SVG with Framer Motion
 * animated expression changes.
 *
 * @param expression - Current emotional state.
 * @param size       - One of 'sm' (32px), 'md' (56px), 'lg' (120px).
 * @param className  - Additional class names.
 * @returns Animated SVG mascot element.
 */
export function Mascot({ expression = 'happy', size = 'md', className }: MascotProps) {
  const px = SIZES[size]
  const eyes = EYES[expression]
  const mouth = MOUTHS[expression]
  const eyebrowY = EYEBROW_Y[expression]

  return (
    <svg
      width={px}
      height={px}
      viewBox="0 0 80 90"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      {/* Popcorn bucket body */}
      <rect x="10" y="42" width="60" height="44" rx="6" fill="var(--color-primary)" />
      {/* Bucket stripes */}
      <rect x="25" y="42" width="8" height="44" fill="white" opacity="0.25" />
      <rect x="47" y="42" width="8" height="44" fill="white" opacity="0.25" />
      {/* Bucket top rim */}
      <rect x="8" y="38" width="64" height="8" rx="4" fill="var(--color-accent)" />

      {/* Popcorn puffs */}
      <circle cx="20" cy="30" r="13" fill="#fff9e8" />
      <circle cx="38" cy="22" r="16" fill="#fff9e8" />
      <circle cx="58" cy="28" r="13" fill="#fff9e8" />
      <circle cx="12" cy="38" r="10" fill="#fff9e8" />
      <circle cx="66" cy="36" r="10" fill="#fff9e8" />
      {/* Popcorn shading */}
      <circle cx="20" cy="30" r="13" fill="#f4c842" opacity="0.35" />
      <circle cx="38" cy="22" r="16" fill="#f4c842" opacity="0.3" />
      <circle cx="58" cy="28" r="13" fill="#f4c842" opacity="0.35" />

      {/* Face group — translated vertically for expression */}
      <g transform="translate(0, 58)">
        {/* Left eyebrow */}
        <motion.line
          x1="22" y1={-14 + eyebrowY} x2="32" y2={-16 + eyebrowY}
          stroke="var(--color-text)" strokeWidth="2" strokeLinecap="round"
          animate={{ y1: -14 + eyebrowY, y2: -16 + eyebrowY }}
          transition={TRANSITION}
        />
        {/* Right eyebrow */}
        <motion.line
          x1="48" y1={-16 + eyebrowY} x2="58" y2={-14 + eyebrowY}
          stroke="var(--color-text)" strokeWidth="2" strokeLinecap="round"
          animate={{ y1: -16 + eyebrowY, y2: -14 + eyebrowY }}
          transition={TRANSITION}
        />

        {/* Left eye */}
        <g transform={`translate(27, ${-6 + eyes.offsetY})`}>
          <motion.path
            d={eyes.left}
            stroke="var(--color-text)"
            strokeWidth="2.5"
            strokeLinecap="round"
            fill="var(--color-text)"
            animate={{ d: eyes.left }}
            transition={TRANSITION}
          />
        </g>

        {/* Right eye */}
        <g transform={`translate(53, ${-6 + eyes.offsetY})`}>
          <motion.path
            d={eyes.right}
            stroke="var(--color-text)"
            strokeWidth="2.5"
            strokeLinecap="round"
            fill="var(--color-text)"
            animate={{ d: eyes.right }}
            transition={TRANSITION}
          />
        </g>

        {/* Cheeks (shown for happy/excited) */}
        {(expression === 'happy' || expression === 'excited') && (
          <>
            <circle cx="20" cy="0" r="5" fill="var(--color-primary)" opacity="0.35" />
            <circle cx="60" cy="0" r="5" fill="var(--color-primary)" opacity="0.35" />
          </>
        )}

        {/* Tear drops for sad expression */}
        {expression === 'sad' && (
          <>
            <ellipse cx="27" cy="2" rx="1.5" ry="3" fill="#93c5fd" opacity="0.8" />
            <ellipse cx="53" cy="2" rx="1.5" ry="3" fill="#93c5fd" opacity="0.8" />
          </>
        )}

        {/* Mouth */}
        <motion.path
          d={`M${40 + mouth.slice(1)}`}
          stroke="var(--color-text)"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
          animate={{ d: `M${40 + mouth.slice(1)}` }}
          transition={TRANSITION}
        />
      </g>
    </svg>
  )
}

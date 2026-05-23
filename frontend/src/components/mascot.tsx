import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'

export type MascotExpression = 'happy' | 'focused' | 'excited' | 'sleepy' | 'sad'
export type MascotSize = 'sm' | 'md' | 'lg'

interface MascotProps {
  expression?: MascotExpression
  size?: MascotSize
  className?: string
}

const SIZES: Record<MascotSize, number> = { sm: 32, md: 56, lg: 120 }

type Pose = 'idle' | 'bob' | 'celebrate' | 'slumped'

const EXPRESSION_TO_POSE: Record<MascotExpression, Pose> = {
  happy:   'idle',
  focused: 'bob',
  excited: 'celebrate',
  sleepy:  'slumped',
  sad:     'slumped',
}

function BucketBody() {
  return (
    <>
      <defs>
        <clipPath id="bc">
          <path d="M 10 32 Q 8 68 18 74 L 62 74 Q 72 68 70 32 Z" />
        </clipPath>
      </defs>
      <path d="M 10 32 Q 8 68 18 74 L 62 74 Q 72 68 70 32 Z" fill="white" />
      <rect x="10" y="30" width="11" height="46" fill="#CC2929" clipPath="url(#bc)" />
      <rect x="31" y="30" width="11" height="46" fill="#CC2929" clipPath="url(#bc)" />
      <rect x="52" y="30" width="11" height="46" fill="#CC2929" clipPath="url(#bc)" />
      <rect x="7" y="28" width="66" height="6" rx="3" fill="#B02020" />
    </>
  )
}

function Popcorn() {
  return (
    <>
      <circle cx="22" cy="22" r="7.5" fill="#F5D35E" />
      <circle cx="40" cy="17" r="9" fill="#F5D35E" />
      <circle cx="58" cy="22" r="7.5" fill="#F5D35E" />
      <circle cx="31" cy="16" r="6" fill="#EAC94A" />
      <circle cx="49" cy="16" r="6" fill="#EAC94A" />
    </>
  )
}

function EyesNormal() {
  return (
    <>
      <circle cx="32" cy="52" r="4.5" fill="#1a1a1c" />
      <circle cx="48" cy="52" r="4.5" fill="#1a1a1c" />
      <circle cx="33.5" cy="50.2" r="1.5" fill="white" />
      <circle cx="49.5" cy="50.2" r="1.5" fill="white" />
    </>
  )
}

function EyesWide() {
  return (
    <>
      <circle cx="32" cy="52" r="6" fill="#1a1a1c" />
      <circle cx="48" cy="52" r="6" fill="#1a1a1c" />
      <circle cx="34" cy="50" r="2" fill="white" />
      <circle cx="50" cy="50" r="2" fill="white" />
    </>
  )
}

function EyesSleepy() {
  return (
    <>
      <path d="M 27.5 54 Q 32 48 36.5 54 Z" fill="#1a1a1c" />
      <path d="M 43.5 54 Q 48 48 52.5 54 Z" fill="#1a1a1c" />
    </>
  )
}

function MouthSmile() {
  return <path d="M 30 62 Q 40 68 50 62" stroke="#1a1a1c" fill="none" strokeWidth="2" strokeLinecap="round" />
}

function MouthGrin() {
  return <path d="M 28 61 Q 40 70 52 61" stroke="#1a1a1c" fill="none" strokeWidth="2.5" strokeLinecap="round" />
}

function MouthSad() {
  return <path d="M 30 66 Q 40 60 50 66" stroke="#1a1a1c" fill="none" strokeWidth="2" strokeLinecap="round" />
}

function ArmsIdle() {
  return (
    <>
      <path d="M 9 52 Q 3 45 5 37" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M 71 52 Q 77 45 75 37" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
    </>
  )
}

function ArmsHighRaised() {
  return (
    <>
      <path d="M 9 50 Q 0 34 6 20" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M 71 50 Q 80 34 74 20" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
    </>
  )
}

function ArmsDown() {
  return (
    <>
      <path d="M 9 52 Q 4 60 8 68" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M 71 52 Q 76 60 72 68" stroke="#333" fill="none" strokeWidth="2.5" strokeLinecap="round" />
    </>
  )
}

function Sparkles() {
  return (
    <>
      <circle cx="6" cy="18" r="2" fill="#F5D35E" />
      <circle cx="74" cy="18" r="2" fill="#F5D35E" />
      <path d="M 6 12 L 6 24 M 0 18 L 12 18" stroke="#F5D35E" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M 74 12 L 74 24 M 68 18 L 80 18" stroke="#F5D35E" strokeWidth="1.5" strokeLinecap="round" />
    </>
  )
}

const BASE_SVG = { viewBox: '0 0 80 90', xmlns: 'http://www.w3.org/2000/svg', fill: 'none' } as const

function IdleSvg() {
  return (
    <svg {...BASE_SVG}>
      <Popcorn /><BucketBody /><EyesNormal /><MouthSmile /><ArmsIdle />
    </svg>
  )
}

function CelebrateSvg() {
  return (
    <svg {...BASE_SVG}>
      <Sparkles /><Popcorn /><BucketBody /><EyesWide /><MouthGrin /><ArmsHighRaised />
    </svg>
  )
}

function SlumpedSvg() {
  return (
    <svg {...BASE_SVG}>
      <Popcorn /><BucketBody /><EyesSleepy /><MouthSad /><ArmsDown />
    </svg>
  )
}

/**
 * Animated popcorn-bucket mascot with five emotional expressions.
 *
 * @param expression - Emotional state driving the visual pose (default: "happy").
 * @param size       - Render size: "sm" (32px), "md" (56px), "lg" (120px).
 * @param className  - Optional extra wrapper classes.
 * @returns Framer-motion animated SVG popcorn bucket.
 */
export function Mascot({ expression = 'happy', size = 'sm', className }: MascotProps) {
  const pose = EXPRESSION_TO_POSE[expression]
  const px = SIZES[size]
  const isBob = pose === 'bob'

  return (
    <motion.div
      className={cn('shrink-0 select-none', className)}
      style={{ width: px, height: px }}
      animate={isBob ? { y: [0, -6, 0] } : undefined}
      transition={isBob ? { duration: 1.4, repeat: Infinity, ease: 'easeInOut' } : undefined}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={expression}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.9 }}
          transition={{ duration: 0.2 }}
          style={{ width: px, height: px }}
        >
          {(pose === 'idle' || pose === 'bob') && <IdleSvg />}
          {pose === 'celebrate' && <CelebrateSvg />}
          {pose === 'slumped' && <SlumpedSvg />}
        </motion.div>
      </AnimatePresence>
    </motion.div>
  )
}

/**
 * Fixed-position ambient mascot shown while a conversation is active.
 *
 * @returns Floating decorative mascot anchored to bottom-right.
 */
export function FloatingMascot() {
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40">
      <Mascot expression="happy" size="md" className="opacity-90" />
    </div>
  )
}

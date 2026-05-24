import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'

export type MascotExpression = 'happy' | 'focused' | 'excited' | 'sleepy' | 'sad'
export type MascotSize = 'sm' | 'md' | 'lg'

const SIZES: Record<MascotSize, number> = { sm: 32, md: 56, lg: 120 }

type Pose = 'idle' | 'bob' | 'celebrate' | 'slumped'

const EXPRESSION_TO_POSE: Record<MascotExpression, Pose> = {
    happy: 'idle',
    focused: 'bob',
    excited: 'celebrate',
    sleepy: 'slumped',
    sad: 'slumped',
}

// ─── SVG sub-components ───────────────────────────────────────────────────────

function BucketBody({ clipId }: { clipId: string }) {
    return (
        <>
            <defs>
                <clipPath id={clipId}>
                    <path d="M 10 32 Q 8 68 18 74 L 62 74 Q 72 68 70 32 Z" />
                </clipPath>
            </defs>
            <path d="M 10 32 Q 8 68 18 74 L 62 74 Q 72 68 70 32 Z" fill="white" />
            <rect x="10" y="30" width="8"  height="46" fill="#CC2929" clipPath={`url(#${clipId})`} />
            <rect x="21" y="30" width="6"  height="46" fill="#CC2929" clipPath={`url(#${clipId})`} />
            <rect x="32" y="30" width="6"  height="46" fill="#CC2929" clipPath={`url(#${clipId})`} />
            <rect x="43" y="30" width="6"  height="46" fill="#CC2929" clipPath={`url(#${clipId})`} />
            <rect x="54" y="30" width="6"  height="46" fill="#CC2929" clipPath={`url(#${clipId})`} />
            <rect x="62" y="30" width="8"  height="46" fill="#CC2929" clipPath={`url(#${clipId})`} />
            <rect x="16" y="70" width="48" height="5" rx="1.5" fill="#B02020" />
            <rect x="7"  y="28" width="66" height="6"  rx="3" fill="#B02020" />
        </>
    )
}

function Popcorn() {
    return (
        <>
            <circle cx="18" cy="28" r="7"   fill="#F5D35E" />
            <circle cx="30" cy="21" r="8"   fill="#EAC94A" />
            <circle cx="44" cy="16" r="9.5" fill="#F5D35E" />
            <circle cx="58" cy="21" r="8"   fill="#EAC94A" />
            <circle cx="24" cy="22" r="5.5" fill="#F0D060" />
            <circle cx="37" cy="19" r="6.5" fill="#F5D35E" />
            <circle cx="51" cy="17" r="7"   fill="#EAC94A" />
            <circle cx="64" cy="23" r="5.5" fill="#F0D060" />
			<circle cx="40" cy="30" r="5.5" fill="#F0D060" />
			<circle cx="50" cy="30" r="5.5" fill="#F0D060" />
        </>
    )
}

function EyesNormal() {
    return (
        <>
            <ellipse cx="32" cy="51" rx="5" ry="7"   fill="white" stroke="#1a1a1c" strokeWidth="1.5" />
            <circle  cx="32" cy="54" r="3.5"          fill="#1a1a1c" />
            <ellipse cx="48" cy="51" rx="5" ry="7"   fill="white" stroke="#1a1a1c" strokeWidth="1.5" />
            <circle  cx="48" cy="54" r="3.5"          fill="#1a1a1c" />
        </>
    )
}

function EyesWide() {
    return (
        <>
            <ellipse cx="32" cy="50" rx="6" ry="8" fill="white" stroke="#1a1a1c" strokeWidth="1.5" />
            <circle  cx="32" cy="52" r="5"          fill="#1a1a1c" />
            <ellipse cx="48" cy="50" rx="6" ry="8" fill="white" stroke="#1a1a1c" strokeWidth="1.5" />
            <circle  cx="48" cy="52" r="5"          fill="#1a1a1c" />
        </>
    )
}

function EyesSleepy() {
    return (
        <>
            <path d="M 27 53 Q 32 46 37 53 Z" fill="#f5e6c8" stroke="#1a1a1c" strokeWidth="1.2" strokeLinecap="round" />
            <path d="M 43 53 Q 48 46 53 53 Z" fill="#f5e6c8" stroke="#1a1a1c" strokeWidth="1.2" strokeLinecap="round" />
        </>
    )
}

function MouthSmile() {
    return <path d="M 30 62 Q 40 68 50 62" stroke="#1a1a1c" fill="none" strokeWidth="2"   strokeLinecap="round" />
}

function MouthGrin() {
    return <path d="M 28 61 Q 40 70 52 61" stroke="#1a1a1c" fill="none" strokeWidth="2.5" strokeLinecap="round" />
}

function MouthSleepy() {
    return <circle cx="40" cy="64" r="4.5" fill="#1a1a1c" />
}

function Sparkles() {
    return (
        <>
            <circle cx="6"  cy="18" r="2" fill="#F5D35E" />
            <circle cx="74" cy="18" r="2" fill="#F5D35E" />
            <path d="M 6 12 L 6 24 M 0 18 L 12 18"   stroke="#F5D35E" strokeWidth="1.5" strokeLinecap="round" fill="none" />
            <path d="M 74 12 L 74 24 M 68 18 L 80 18" stroke="#F5D35E" strokeWidth="1.5" strokeLinecap="round" fill="none" />
        </>
    )
}

function Zzz() {
    return (
        <>
            <text x="62" y="20" fontFamily="sans-serif" fontSize="11" fontWeight="700" fill="#aaa">Z</text>
            <text x="66" y="10" fontFamily="sans-serif" fontSize="14" fontWeight="700" fill="#aaa" >Z</text>
            <text x="68" y="0" fontFamily="sans-serif" fontSize="17" fontWeight="700" fill="#aaa">Z</text>
        </>
    )
}

const BASE_SVG_PROPS = { viewBox: '0 0 80 90', xmlns: 'http://www.w3.org/2000/svg', fill: 'none' } as const


/**
 * HAPPY / FOCUSED — gentle continuous float up-down.
 * On top of this the outer <Mascot> wrapper adds a bob when focused.
 */
function IdleSvg() {
    return (
        <svg {...BASE_SVG_PROPS}>
            {/* Popcorn kernels bob very slightly, offset from body */}
            <motion.g
                animate={{ y: [0, -1.5, 0] }}
                transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
            >
                <Popcorn />
            </motion.g>
            <BucketBody clipId="bc-idle" />
            {/* Eyes blink every ~3 s */}
            <motion.g
                animate={{ scaleY: [1, 1, 0.05, 1, 1] }}
                transition={{ duration: 0.35, repeat: Infinity, repeatDelay: 2.8, ease: 'easeInOut' }}
                style={{ transformOrigin: '40px 53px' }}
            >
                <EyesNormal />
            </motion.g>
            <MouthSmile />
        </svg>
    )
}

/**
 * EXCITED — whole body jumps, sparkles pulse, flying popcorn shoots outward.
 */
function CelebrateSvg() {
    return (
        <svg {...BASE_SVG_PROPS}>
            {/* Pulsing sparkles */}
            <motion.g
                animate={{ scale: [1, 1.35, 1], opacity: [0.7, 1, 0.7] }}
                transition={{ duration: 0.7, repeat: Infinity, ease: 'easeInOut' }}
                style={{ transformOrigin: '40px 18px' }}
            >
                <Sparkles />
            </motion.g>

            {/* Flying popcorn — shoot out then return */}
            <motion.circle
                cx="4" cy="38" r="5" fill="#F5D35E"
                animate={{ x: [-0, -6], y: [0, -5], opacity: [1, 0.3] }}
                transition={{ duration: 0.6, repeat: Infinity, repeatType: 'reverse', ease: 'easeOut' }}
            />
            <motion.circle
                cx="76" cy="35" r="5" fill="#EAC94A"
                animate={{ x: [0, 6], y: [0, -5], opacity: [1, 0.3] }}
                transition={{ duration: 0.6, repeat: Infinity, repeatType: 'reverse', ease: 'easeOut' }}
            />
            <motion.circle
                cx="8" cy="12" r="4" fill="#F0D060"
                animate={{ x: [0, -5], y: [0, -6], opacity: [1, 0] }}
                transition={{ duration: 0.5, repeat: Infinity, repeatType: 'reverse', ease: 'easeOut', delay: 0.15 }}
            />
            <motion.circle
                cx="72" cy="12" r="4" fill="#F5D35E"
                animate={{ x: [0, 5], y: [0, -6], opacity: [1, 0] }}
                transition={{ duration: 0.5, repeat: Infinity, repeatType: 'reverse', ease: 'easeOut', delay: 0.15 }}
            />

            {/* Popcorn shakes side-to-side */}
            <motion.g
                animate={{ rotate: [-4, 4, -4] }}
                transition={{ duration: 0.4, repeat: Infinity, ease: 'easeInOut' }}
                style={{ transformOrigin: '40px 22px' }}
            >
                <Popcorn />
            </motion.g>

            <BucketBody clipId="bc-celebrate" />

            {/* Eyes grow big rhythmically */}
            <motion.g
                animate={{ scaleY: [1, 1.15, 1] }}
                transition={{ duration: 0.4, repeat: Infinity, ease: 'easeInOut' }}
                style={{ transformOrigin: '40px 53px' }}
            >
                <EyesWide />
            </motion.g>
            <MouthGrin />
        </svg>
    )
}

/**
 * SLEEPY — slow whole-body droop, Zzz float upward and fade, mouth pulses gently.
 */
function SlumpedSvg() {
    return (
        <svg {...BASE_SVG_PROPS}>
            {/* Zzz drift upward and fade */}


            <Popcorn />
			
            <BucketBody clipId="bc-slumped" />
            {/* Eyelids droop a tiny bit in a slow cycle */}
            <motion.g
                animate={{ scaleY: [1, 0.85, 1] }}
                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                style={{ transformOrigin: '40px 53px' }}
            >
                <EyesSleepy />
            </motion.g>

            {/* Mouth "snore" pulse */}
            <motion.g
                animate={{ scale: [1, 1.3, 1], opacity: [1, 1, 1] }}
                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                style={{ transformOrigin: '40px 64px' }}
            >
                <MouthSleepy />
            </motion.g>
            <motion.g
                animate={{ y: [0, -10], opacity: [0.9, 0] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: 'easeIn' }}
            >
                <Zzz />
            </motion.g>
        </svg>
    )
}

/**
 * Animated popcorn-bucket mascot with five emotional expressions.
 *
 * Animations per pose
 * -------------------
 *  idle      — gentle float, periodic eye blink
 *  bob       — same as idle + continuous vertical bob on the wrapper
 *  celebrate — body jump, sparkle pulse, flying popcorn, eye grow
 *  slumped   — Zzz drift & fade, eyelid droop cycle, snore-mouth pulse
 *
 * @param expression - Emotional state (default: "happy").
 * @param size       - "sm" 32px | "md" 56px | "lg" 120px.
 * @param className  - Extra wrapper classes.
 */
export function Mascot({
    expression = 'happy',
    size = 'sm',
    className,
}: {
    expression?: MascotExpression
    size?: MascotSize
    className?: string
}) {
    const pose = EXPRESSION_TO_POSE[expression]
    const px   = SIZES[size]
    const isBob = pose === 'bob'
    const isCelebrate = pose === 'celebrate'

    return (
        <motion.div
            className={cn('shrink-0 select-none', className)}
            style={{ width: px, height: px }}
            // bob: up-down float
            animate={
                isBob       ? { y: [0, -6, 0] } :
                isCelebrate ? { y: [0, -10, 0, -6, 0] } :
                undefined
            }
            transition={
                isBob       ? { duration: 1.4, repeat: Infinity, ease: 'easeInOut' } :
                isCelebrate ? { duration: 0.5, repeat: Infinity, ease: 'easeOut' } :
                undefined
            }
        >
            <AnimatePresence mode="wait">
                <motion.div
                    key={expression}
                    initial={{ opacity: 0, scale: 0.85 }}
                    animate={{ opacity: 1,  scale: 1 }}
                    exit={   { opacity: 0,  scale: 0.85 }}
                    transition={{ duration: 0.22 }}
                    style={{ width: px, height: px }}
                >
                    {(pose === 'idle' || pose === 'bob') && <IdleSvg />}
                    {pose === 'celebrate' && <CelebrateSvg />}
                    {pose === 'slumped'   && <SlumpedSvg />}
                </motion.div>
            </AnimatePresence>
        </motion.div>
    )
}

/**
 * Fixed-position ambient mascot shown while a conversation is active.
 */
export function FloatingMascot() {
    return (
        <div className="pointer-events-none fixed bottom-4 right-4 z-40">
            <Mascot expression="happy" size="md" className="opacity-90" />
        </div>
    )
}
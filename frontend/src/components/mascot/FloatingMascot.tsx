import { motion } from 'framer-motion'
import { Mascot } from './Mascot'

/**
 * Persistent floating Poppy mascot in the bottom-right corner.
 * Gentle idle bob animation. Hidden on welcome and auth pages.
 *
 * @returns Fixed-positioned animated mascot element.
 */
export function FloatingMascot() {
  return (
    <motion.div
      className="fixed bottom-6 right-6 z-40 cursor-default select-none"
      animate={{ y: [0, -6, 0] }}
      transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }}
    >
      <Mascot expression="happy" size="sm" />
    </motion.div>
  )
}

import { Mascot } from '@/components/mascot/Mascot'

/**
 * Placeholder shown in the right panel when no cluster snapshot is loaded yet.
 *
 * @returns Empty state with sleepy Poppy and guidance copy.
 */
export function EmptySnapshotState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-6">
      <Mascot expression="sleepy" size="lg" />
      <p className="text-base font-display text-[var(--color-text)]">No snapshot yet</p>
      <p className="text-sm text-[var(--color-muted)] max-w-[200px] leading-relaxed">
        Chat with Poppy to create your first cluster snapshot
      </p>
    </div>
  )
}

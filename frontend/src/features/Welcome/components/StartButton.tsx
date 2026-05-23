import { Button } from '@/components/button'

interface StartButtonProps {
  onClick: () => void
  isLoading: boolean
}

/**
 * Primary CTA button on the welcome screen.
 *
 * @param onClick   - Called when the user clicks to start a conversation.
 * @param isLoading - Shows a loading label while the conversation is being created.
 * @returns Styled start button.
 */
export function StartButton({ onClick, isLoading }: StartButtonProps) {
  return (
    <Button
      onClick={onClick}
      disabled={isLoading}
      size="lg"
      className="px-10 text-base"
    >
      {isLoading ? 'Starting…' : 'Start with Poppy'}
    </Button>
  )
}

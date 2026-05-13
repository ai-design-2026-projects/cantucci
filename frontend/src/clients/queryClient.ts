import { QueryClient } from "@tanstack/react-query";

/**
 * Shared TanStack Query client.
 *
 * staleTime=30s avoids redundant refetches for session/turn data which
 * only changes via explicit mutations.  retry=1 handles transient flakes
 * without masking real errors.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

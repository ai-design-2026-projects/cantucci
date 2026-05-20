import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  createSession,
  deleteSession,
  listSessions,
} from "@/features/session/services/sessionService";
import { useSessionStore } from "@/store/sessionStore";
import { useClusterStore } from "@/store/clusterStore";
import { useUiStore } from "@/store/uiStore";
import { useClusterSnapshotStore } from "@/store/clusterSnapshotStore";
import { cn } from "@/lib/utils";
import type { SessionDto } from "@/utils/types";

interface SessionListItemProps {
  summary: SessionDto;
  isActive: boolean;
  onDeleteConfirmed: (id: string) => void;
}

function SessionListItem({ summary, isActive, onDeleteConfirmed }: SessionListItemProps) {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <>
      <div
        className={cn(
          "group relative w-[245px] flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer text-sm transition-colors",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        )}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={() => navigate(`/sessions/${summary.session_id}`)}
      >
        <span className="flex-1 truncate min-w-0">
          {summary.first_user_message ?? "New conversation"}
        </span>
        {hovered && (
          <button
            type="button"
            aria-label="Delete session"
            className="shrink-0 rounded p-0.5 hover:text-destructive transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              setConfirmOpen(true);
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete session?</DialogTitle>
            <DialogDescription>
              This will permanently delete the conversation and all its turns. This cannot be
              undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmOpen(false);
                onDeleteConfirmed(summary.session_id);
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * Persistent left-rail session history panel.
 *
 * Renders a "New Session" button at the top and a scrollable list of the
 * authenticated user's sessions below. Clicking a row navigates to
 * /sessions/:sessionId. The active session row is highlighted based on the
 * current URL param. Delete button appears on hover and requires confirmation.
 *
 * Only mounted for authenticated users (enforced by AppShell).
 */
export function SessionSidebar() {
  const { sessionId: activeSessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { reset: resetSession } = useSessionStore();
  const { reset: resetCluster } = useClusterStore();
  const { reset: resetUi } = useUiStore();
  const { reset: resetClusterSnapshot } = useClusterSnapshotStore();

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["sessions", "list"],
    queryFn: listSessions,
  });

  const createMutation = useMutation({
    mutationFn: createSession,
    onSuccess: (data) => {
      queryClient.setQueryData(["session", data.session_id], data);
      queryClient.invalidateQueries({ queryKey: ["sessions", "list"] });
      navigate(`/sessions/${data.session_id}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: ["session", id] });
      queryClient.invalidateQueries({ queryKey: ["sessions", "list"] });
      if (id === activeSessionId) {
        resetSession();
        resetCluster();
        resetUi();
        resetClusterSnapshot();
        navigate("/");
      }
    },
  });

  return (
    <div className="flex flex-col h-full py-2">
      <div className="px-2 pb-2">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2 font-normal"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
        >
          <Plus className="h-4 w-4 shrink-0" />
          New Session
        </Button>
      </div>

      <ScrollArea className="flex-1 px-2">
        {isLoading ? (
          <p className="px-1 py-2 text-xs text-muted-foreground">Loading…</p>
        ) : sessions.length === 0 ? (
          <p className="px-1 py-2 text-xs text-muted-foreground">No sessions yet.</p>
        ) : (
          <div className="space-y-0.5">
            {sessions.map((s) => (
              <SessionListItem
                key={s.session_id}
                summary={s}
                isActive={s.session_id === activeSessionId}
                onDeleteConfirmed={(id) => deleteMutation.mutate(id)}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

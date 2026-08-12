import { useState, useCallback, useEffect } from "react";
import type { DiagnosisResponse } from "../types/diagnosis";

/* ------------------------------------------------------------------ */
/* Shared chat message types (mirroring Dashboard)                     */
/* ------------------------------------------------------------------ */
export interface UserMessage {
    role: "user";
    content: string;
}

export interface AssistantMessage {
    role: "assistant";
    data: DiagnosisResponse;
}

export interface ErrorMessage {
    role: "error";
    error: string;
    retryTelemetry: string;
}

// Loading is transient and never persisted
export interface LoadingMessage {
    role: "loading";
}

export type ChatMessage = UserMessage | AssistantMessage | ErrorMessage | LoadingMessage;

/** Only persistable message types (loading is transient) */
type PersistableMessage = UserMessage | AssistantMessage | ErrorMessage;

/* ------------------------------------------------------------------ */
/* Session model                                                       */
/* ------------------------------------------------------------------ */
export interface ChatSession {
    id: string;
    title: string;
    messages: PersistableMessage[];
    createdAt: number; // epoch ms
    updatedAt: number;
}

/* ------------------------------------------------------------------ */
/* localStorage helpers                                                */
/* ------------------------------------------------------------------ */
const STORAGE_KEY_PREFIX = "kuberca_sessions_";

function storageKey(userId: string): string {
    return `${STORAGE_KEY_PREFIX}${userId}`;
}

function loadSessions(userId: string): ChatSession[] {
    try {
        const raw = localStorage.getItem(storageKey(userId));
        if (!raw) return [];
        return JSON.parse(raw) as ChatSession[];
    } catch {
        return [];
    }
}

function saveSessions(userId: string, sessions: ChatSession[]): void {
    try {
        localStorage.setItem(storageKey(userId), JSON.stringify(sessions));
    } catch {
        // localStorage quota exceeded — silently ignore
    }
}

function generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Derive a short title from the first user message */
function deriveTitle(messages: PersistableMessage[]): string {
    const first = messages.find((m) => m.role === "user");
    if (!first) return "New Analysis";
    const text = (first as UserMessage).content;
    return text.length > 50 ? text.slice(0, 50) + "…" : text;
}

/* ================================================================== */
/* Hook                                                                */
/* ================================================================== */
export function useChatSessions(userId: string | null | undefined) {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [activeId, setActiveId] = useState<string | null>(null);

    // Load sessions when userId changes
    useEffect(() => {
        if (!userId) {
            setSessions([]);
            setActiveId(null);
            return;
        }
        const loaded = loadSessions(userId);
        setSessions(loaded);
    }, [userId]);

    // Persist whenever sessions change
    useEffect(() => {
        if (userId) {
            saveSessions(userId, sessions);
        }
    }, [sessions, userId]);

    /** Get messages for the active session (including transient loading) */
    const activeSession = sessions.find((s) => s.id === activeId) ?? null;

    /** Save / update messages for the active session.
     *  Filters out loading messages before persisting.
     *  Creates a new session if none is active. */
    const saveMessages = useCallback(
        (messages: ChatMessage[]) => {
            const persistable = messages.filter((m) => m.role !== "loading") as PersistableMessage[];
            if (persistable.length === 0) return;

            setSessions((prev) => {
                if (activeId) {
                    // Update existing session
                    return prev.map((s) =>
                        s.id === activeId
                            ? { ...s, messages: persistable, title: deriveTitle(persistable), updatedAt: Date.now() }
                            : s
                    );
                } else {
                    // Create a new session
                    const newSession: ChatSession = {
                        id: generateId(),
                        title: deriveTitle(persistable),
                        messages: persistable,
                        createdAt: Date.now(),
                        updatedAt: Date.now(),
                    };
                    // Use setTimeout to avoid state update in render
                    setTimeout(() => setActiveId(newSession.id), 0);
                    return [newSession, ...prev];
                }
            });
        },
        [activeId]
    );

    /** Start a new chat (no deletion of history) */
    const startNewChat = useCallback(() => {
        setActiveId(null);
    }, []);

    /** Switch to a past session */
    const switchSession = useCallback((sessionId: string) => {
        setActiveId(sessionId);
    }, []);

    /** Delete a single session */
    const deleteSession = useCallback(
        (sessionId: string) => {
            setSessions((prev) => prev.filter((s) => s.id !== sessionId));
            if (activeId === sessionId) {
                setActiveId(null);
            }
        },
        [activeId]
    );

    /** Sorted sessions — newest first */
    const sortedSessions = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);

    return {
        sessions: sortedSessions,
        activeId,
        activeSession,
        saveMessages,
        startNewChat,
        switchSession,
        deleteSession,
    };
}

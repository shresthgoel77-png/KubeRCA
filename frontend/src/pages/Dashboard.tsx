import { useState, useRef, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useUser, useClerk } from "@clerk/clerk-react";
import { diagnose, NetworkError, TimeoutError, ApiError, ValidationError } from "../services/api";
import type { DiagnosisResponse, Severity } from "../types/diagnosis";
import { useChatSessions } from "../hooks/useChatSessions";
import { useHealthCheck } from "../hooks/useHealthCheck";
import ChatErrorBoundary from "../components/ChatErrorBoundary";
import type { ChatMessage, ErrorMessage } from "../hooks/useChatSessions";

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */
const MAX_TELEMETRY_CHARS = 10_000;
const SLOW_INFERENCE_MS = 10_000; // show "still working" after 10s

/* ------------------------------------------------------------------ */
/* Logo mark                                                           */
/* ------------------------------------------------------------------ */
const LogoMark = ({ className = "" }: { className?: string }) => (
    <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <path d="M60 8L104 32V72L60 112L16 72V32L60 8Z" stroke="currentColor" strokeWidth="3" fill="none" opacity="0.6" />
        <path d="M60 24L88 60L60 96L32 60L60 24Z" stroke="currentColor" strokeWidth="2" fill="currentColor" fillOpacity="0.08" />
        <circle cx="60" cy="44" r="5" fill="currentColor" />
        <circle cx="44" cy="64" r="4.5" fill="currentColor" />
        <circle cx="76" cy="64" r="4.5" fill="currentColor" />
        <circle cx="60" cy="80" r="4" fill="currentColor" opacity="0.7" />
    </svg>
);

/* ------------------------------------------------------------------ */
/* Severity badge                                                      */
/* ------------------------------------------------------------------ */
const severityConfig: Record<Severity, { bg: string; text: string; label: string }> = {
    "SEV-1": { bg: "bg-red-500/15", text: "text-red-400", label: "SEV-1 · Critical" },
    "SEV-2": { bg: "bg-orange-500/15", text: "text-orange-400", label: "SEV-2 · Warning" },
    "SEV-3": { bg: "bg-yellow-500/15", text: "text-yellow-400", label: "SEV-3 · Low" },
};

const SeverityBadge = ({ severity }: { severity: Severity }) => {
    const cfg = severityConfig[severity];
    return (
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${cfg.bg} ${cfg.text}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {cfg.label}
        </span>
    );
};

/* ------------------------------------------------------------------ */
/* Confidence bar                                                      */
/* ------------------------------------------------------------------ */
const ConfidenceBar = ({ value }: { value: number }) => {
    const pct = Math.round(value * 100);
    const color = pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
    return (
        <div className="flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-700">
                <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${pct}%` }} />
            </div>
            <span className="text-sm font-semibold text-slate-200 tabular-nums">{pct}%</span>
        </div>
    );
};

/* ------------------------------------------------------------------ */
/* Thinking indicator with slow-inference escalation                   */
/* ------------------------------------------------------------------ */
const ThinkingIndicator = ({ startedAt }: { startedAt: number }) => {
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        const id = setInterval(() => setElapsed(Date.now() - startedAt), 1000);
        return () => clearInterval(id);
    }, [startedAt]);

    const isSlow = elapsed > SLOW_INFERENCE_MS;

    return (
        <div className="flex items-start gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-400">
                <LogoMark className="h-5 w-5" />
            </div>
            <div className="rounded-2xl rounded-tl-sm bg-slate-800 px-5 py-4">
                <div className="flex items-center gap-1.5">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400" style={{ animationDelay: "0ms" }} />
                    <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400" style={{ animationDelay: "200ms" }} />
                    <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400" style={{ animationDelay: "400ms" }} />
                </div>
                <p className="mt-2 text-xs text-slate-500">
                    {isSlow
                        ? `Still working (${Math.floor(elapsed / 1000)}s) — the model runs locally and may need extra time for long inputs.`
                        : "Analyzing telemetry — this may take up to 30 s…"}
                </p>
            </div>
        </div>
    );
};

/* ------------------------------------------------------------------ */
/* Diagnosis card                                                      */
/* ------------------------------------------------------------------ */
const DiagnosisCard = ({ data }: { data: DiagnosisResponse }) => (
    <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-400">
            <LogoMark className="h-5 w-5" />
        </div>
        <div className="min-w-0 max-w-2xl space-y-4 rounded-2xl rounded-tl-sm border border-slate-700/50 bg-slate-800/60 px-6 py-5">
            <div className="flex flex-wrap items-center gap-4">
                <SeverityBadge severity={data.severity} />
                <div className="flex-1 min-w-[140px]">
                    <ConfidenceBar value={data.confidence} />
                </div>
            </div>
            <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Failure</h4>
                <p className="text-sm leading-relaxed text-slate-200">{data.failure}</p>
            </div>
            <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Root Cause</h4>
                <p className="text-sm leading-relaxed text-slate-100 font-medium">{data.root_cause}</p>
            </div>
            {data.evidence.length > 0 && (
                <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Evidence</h4>
                    <ul className="space-y-1.5">
                        {data.evidence.map((item, i) => (
                            <li key={i} className="flex items-start gap-2 text-sm text-slate-400">
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-500/60" />
                                <span className="font-mono text-xs leading-relaxed">{item}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    </div>
);

/* ------------------------------------------------------------------ */
/* Error bubble                                                        */
/* ------------------------------------------------------------------ */
const ErrorBubble = ({ error, onRetry }: { error: string; onRetry: () => void }) => (
    <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500/10 text-red-400">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
        </div>
        <div className="rounded-2xl rounded-tl-sm border border-red-500/20 bg-red-500/5 px-5 py-4">
            <p className="text-sm text-red-300">{error}</p>
            <button onClick={onRetry} className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/20">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
                </svg>
                Retry
            </button>
        </div>
    </div>
);

/* ------------------------------------------------------------------ */
/* User bubble                                                         */
/* ------------------------------------------------------------------ */
const UserBubble = ({ content }: { content: string }) => (
    <div className="flex justify-end">
        <div className="max-w-2xl rounded-2xl rounded-tr-sm bg-cyan-600/15 px-5 py-3">
            <p className="whitespace-pre-wrap text-sm text-slate-200 font-mono">{content}</p>
        </div>
    </div>
);

/* ------------------------------------------------------------------ */
/* Backend-down banner                                                 */
/* ------------------------------------------------------------------ */
const HealthBanner = ({ onRetry, isChecking }: { onRetry: () => void; isChecking: boolean }) => (
    <div className="flex items-center justify-between gap-3 border-b border-red-500/20 bg-red-500/5 px-4 py-2.5">
        <div className="flex items-center gap-2 text-sm text-red-300">
            <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500" />
            </span>
            Backend unavailable — the inference server is not responding. Diagnosis requests will fail.
        </div>
        <button
            onClick={onRetry}
            disabled={isChecking}
            className="shrink-0 rounded-md bg-red-500/10 px-3 py-1 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-50"
        >
            {isChecking ? "Checking…" : "Retry"}
        </button>
    </div>
);

/* ================================================================== */
/* DASHBOARD                                                           */
/* ================================================================== */
const Dashboard = () => {
    const [telemetry, setTelemetry] = useState("");
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [inferenceStartedAt, setInferenceStartedAt] = useState<number>(0);
    const { isSignedIn, user } = useUser();
    const { openSignIn } = useClerk();
    const scrollRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const { isAvailable, isChecking, recheckNow } = useHealthCheck();

    const {
        sessions,
        activeId,
        activeSession,
        saveMessages,
        startNewChat,
        switchSession,
        deleteSession,
    } = useChatSessions(user?.id);

    // Load session messages when switching
    useEffect(() => {
        if (activeSession) {
            setMessages(activeSession.messages);
            setIsLoading(false);
        }
    }, [activeId]);

    // Auto-scroll
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, isLoading]);

    // Persist to localStorage
    useEffect(() => {
        if (messages.length > 0 && !isLoading) {
            saveMessages(messages);
        }
    }, [messages, isLoading, saveMessages]);

    const runDiagnosis = useCallback(async (input: string) => {
        setIsLoading(true);
        setInferenceStartedAt(Date.now());
        try {
            const result = await diagnose(input);
            setMessages((prev) => {
                const filtered = prev.filter((m) => m.role !== "loading");
                return [...filtered, { role: "assistant", data: result }];
            });
        } catch (err: unknown) {
            let errorMsg = "An unexpected error occurred.";
            if (err instanceof TimeoutError) {
                errorMsg = "The request timed out after 30 seconds. The backend may be under heavy load — please try again.";
            } else if (err instanceof NetworkError) {
                errorMsg = "Could not reach the backend. Please check that the server is running and try again.";
            } else if (err instanceof ApiError) {
                errorMsg = (err as ApiError).message;
            } else if (err instanceof ValidationError) {
                errorMsg = "The backend returned an unexpected response format. This may indicate a model output parsing failure.";
                console.error("[Dashboard] ValidationError details:", err);
            }
            setMessages((prev) => {
                const filtered = prev.filter((m) => m.role !== "loading");
                return [...filtered, { role: "error", error: errorMsg, retryTelemetry: input }];
            });
        } finally {
            setIsLoading(false);
            setInferenceStartedAt(0);
        }
    }, []);

    /* ---- Derived state ---- */
    const charCount = telemetry.length;
    const isOverLimit = charCount > MAX_TELEMETRY_CHARS;
    const canSend = telemetry.trim().length > 0 && !isLoading && !isOverLimit;

    const handleSend = useCallback(() => {
        if (!canSend) return;
        if (!isSignedIn) {
            openSignIn();
            return;
        }
        setMessages((prev) => [...prev, { role: "user", content: telemetry.trim() }, { role: "loading" }]);
        const input = telemetry.trim();
        setTelemetry("");
        if (textareaRef.current) textareaRef.current.style.height = "auto";
        runDiagnosis(input);
    }, [telemetry, canSend, isSignedIn, openSignIn, runDiagnosis]);

    const handleRetry = useCallback((retryInput: string) => {
        setMessages((prev) => {
            const filtered = prev.filter((m) => m.role !== "error" || (m as ErrorMessage).retryTelemetry !== retryInput);
            return [...filtered, { role: "loading" }];
        });
        runDiagnosis(retryInput);
    }, [runDiagnosis]);

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleNewAnalysis = () => {
        startNewChat();
        setMessages([]);
        setTelemetry("");
        setIsLoading(false);
    };

    const handleSwitchSession = (sessionId: string) => {
        if (sessionId === activeId) return;
        switchSession(sessionId);
    };

    const hasMessages = messages.length > 0;

    const timeAgo = (ts: number): string => {
        const diff = Date.now() - ts;
        const mins = Math.floor(diff / 60_000);
        if (mins < 1) return "just now";
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        const days = Math.floor(hrs / 24);
        return `${days}d ago`;
    };

    return (
        <div className="flex h-screen bg-slate-950 text-slate-300 font-sans antialiased">
            {/* ---- Sidebar ---- */}
            <aside className="flex w-64 flex-col border-r border-slate-800 bg-slate-900 transition-all">
                <div className="flex items-center gap-3 p-4">
                    <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
                        <LogoMark className="h-6 w-6 text-cyan-400" />
                        <span className="font-semibold text-slate-100 tracking-tight">KubeRCA</span>
                    </Link>
                </div>

                <div className="p-3">
                    <button onClick={handleNewAnalysis} className="flex w-full items-center gap-2 rounded-md border border-slate-700 bg-transparent px-3 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-800">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                        </svg>
                        New Analysis
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-3">
                    <h3 className="mb-2 px-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">History</h3>
                    {sessions.length === 0 ? (
                        <div className="px-2 text-sm text-slate-500 italic">No recent investigations</div>
                    ) : (
                        <ul className="space-y-1">
                            {sessions.map((session) => (
                                <li key={session.id}>
                                    <button
                                        onClick={() => handleSwitchSession(session.id)}
                                        className={`group flex w-full items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors ${activeId === session.id
                                                ? "bg-slate-800 text-slate-100"
                                                : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"
                                            }`}
                                    >
                                        <span className="min-w-0 flex-1 truncate">{session.title}</span>
                                        <div className="flex shrink-0 items-center gap-1">
                                            <span className="text-[10px] text-slate-600">{timeAgo(session.updatedAt)}</span>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    deleteSession(session.id);
                                                }}
                                                className="hidden rounded p-0.5 text-slate-600 hover:bg-red-500/10 hover:text-red-400 group-hover:block"
                                                title="Delete session"
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                                </svg>
                                            </button>
                                        </div>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>

                <div className="border-t border-slate-800 p-4">
                    <button
                        className="flex w-full items-center gap-3 text-sm text-slate-400 hover:text-slate-200"
                        onClick={() => !isSignedIn && openSignIn()}
                    >
                        <div className={`flex h-8 w-8 items-center justify-center rounded-full ${isSignedIn ? "bg-cyan-500/20 text-cyan-400" : "bg-slate-800"}`}>
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                            </svg>
                        </div>
                        {isSignedIn ? "Authenticated User" : "Guest User"}
                    </button>
                </div>
            </aside>

            {/* ---- Main ---- */}
            <main className="flex flex-1 flex-col relative min-w-0">
                {/* Header */}
                <header className="flex h-14 items-center justify-between border-b border-white/5 px-4 backdrop-blur-md sticky top-0 z-10">
                    <div className="flex items-center" />
                    <button className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-800 hover:text-white">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                        </svg>
                        Share
                    </button>
                </header>

                {/* Health banner */}
                {isAvailable === false && (
                    <HealthBanner onRetry={recheckNow} isChecking={isChecking} />
                )}

                {/* Chat Area — wrapped in ErrorBoundary */}
                <ChatErrorBoundary>
                    <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-8">
                        {!hasMessages ? (
                            <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center text-center">
                                <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-500/10 text-cyan-400">
                                    <LogoMark className="h-10 w-10" />
                                </div>
                                <h1 className="mb-3 text-3xl font-semibold text-slate-100">How can I help you diagnose?</h1>
                                <p className="max-w-md text-slate-400">
                                    Paste your Kubernetes telemetry logs, events, or describe symptom behavior. The model will analyze it and pinpoint the root cause.
                                </p>
                            </div>
                        ) : (
                            <div className="mx-auto max-w-3xl space-y-6">
                                {messages.map((msg, i) => {
                                    switch (msg.role) {
                                        case "user":
                                            return <UserBubble key={i} content={msg.content} />;
                                        case "assistant":
                                            return <DiagnosisCard key={i} data={msg.data} />;
                                        case "error":
                                            return <ErrorBubble key={i} error={msg.error} onRetry={() => handleRetry(msg.retryTelemetry)} />;
                                        case "loading":
                                            return <ThinkingIndicator key={i} startedAt={inferenceStartedAt} />;
                                        default:
                                            return null;
                                    }
                                })}
                            </div>
                        )}
                    </div>
                </ChatErrorBoundary>

                {/* Input */}
                <div className="w-full shrink-0 bg-gradient-to-t from-slate-950 px-4 pb-6 pt-4">
                    <div className="mx-auto max-w-3xl relative">
                        <div className={`relative flex w-full flex-col overflow-hidden rounded-xl border bg-slate-800 transition-all ${isOverLimit
                                ? "border-red-500/60 focus-within:border-red-500 focus-within:ring-1 focus-within:ring-red-500"
                                : "border-slate-700 focus-within:border-slate-500 focus-within:ring-1 focus-within:ring-slate-500"
                            }`}>
                            <textarea
                                ref={textareaRef}
                                value={telemetry}
                                onChange={(e) => setTelemetry(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Paste logs, events, or describe Kubernetes issue..."
                                disabled={isLoading}
                                className="w-full resize-none border-0 bg-transparent py-4 pl-4 pr-12 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-0 sm:text-sm min-h-[56px] max-h-72 overflow-y-auto block disabled:opacity-50"
                                rows={1}
                                style={{ height: "auto" }}
                                onInput={(e) => {
                                    const target = e.target as HTMLTextAreaElement;
                                    target.style.height = "auto";
                                    target.style.height = `${Math.min(target.scrollHeight, 288)}px`;
                                }}
                            />
                            <button
                                onClick={handleSend}
                                disabled={!canSend}
                                className="absolute bottom-2 right-2 flex h-8 w-8 items-center justify-center rounded-md bg-cyan-500 text-white transition-opacity disabled:opacity-30 hover:bg-cyan-400"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4 transform -rotate-90">
                                    <path d="M3.478 2.404a.75.75 0 00-.926.941l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.404z" />
                                </svg>
                            </button>
                        </div>

                        {/* Footer row: char count warning + disclaimer */}
                        <div className="mt-2 flex items-center justify-between text-xs">
                            {charCount > 0 ? (
                                <span className={isOverLimit ? "font-medium text-red-400" : "text-slate-600"}>
                                    {charCount.toLocaleString()} / {MAX_TELEMETRY_CHARS.toLocaleString()} chars
                                    {isOverLimit && " — too long, please shorten your input"}
                                </span>
                            ) : (
                                <span />
                            )}
                            <span className="text-slate-500">
                                KubeRCA can make mistakes. Verify critical findings.
                            </span>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default Dashboard;

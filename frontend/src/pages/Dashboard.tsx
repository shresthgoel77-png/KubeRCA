import { useState } from "react";
import { Link } from "react-router-dom";
import { useUser, useClerk } from "@clerk/clerk-react";

/* Reusing abstract KubeRCA logo mark */
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

const Dashboard = () => {
    const [telemetry, setTelemetry] = useState("");
    const { isSignedIn } = useUser();
    const { openSignIn } = useClerk();

    const handleSend = () => {
        if (!telemetry.trim()) return;

        // Auth Gate: Open sign-in if guest. State (telemetry input) is natively preserved!
        if (!isSignedIn) {
            openSignIn();
            return;
        }

        console.log("Simulating telemetry send to backend: ", telemetry);
        setTelemetry("");
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="flex h-screen bg-slate-950 text-slate-300 font-sans antialiased">
            {/* ---------------- Sidebar ---------------- */}
            <aside className="flex w-64 flex-col border-r border-slate-800 bg-slate-900 transition-all">
                <div className="flex items-center gap-3 p-4">
                    <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
                        <LogoMark className="h-6 w-6 text-cyan-400" />
                        <span className="font-semibold text-slate-100 tracking-tight">KubeRCA</span>
                    </Link>
                </div>

                <div className="p-3">
                    <button className="flex w-full items-center gap-2 rounded-md border border-slate-700 bg-transparent px-3 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-800">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                        </svg>
                        New Analysis
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-3">
                    <h3 className="mb-2 px-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">History</h3>
                    <div className="px-2 text-sm text-slate-500 italic">No recent investigations</div>
                </div>

                <div className="border-t border-slate-800 p-4">
                    <button
                        className="flex w-full items-center gap-3 text-sm text-slate-400 hover:text-slate-200"
                        onClick={() => !isSignedIn && openSignIn()}
                    >
                        <div className={`flex h-8 w-8 items-center justify-center rounded-full ${isSignedIn ? 'bg-cyan-500/20 text-cyan-400' : 'bg-slate-800'}`}>
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                            </svg>
                        </div>
                        {isSignedIn ? "Authenticated User" : "Guest User"}
                    </button>
                </div>
            </aside>

            {/* ---------------- Main Content ---------------- */}
            <main className="flex flex-1 flex-col relative min-w-0">
                {/* Header */}
                <header className="flex h-14 items-center justify-between border-b border-white/5 px-4 backdrop-blur-md sticky top-0 z-10">
                    <div className="flex items-center">
                        {/* Left side empty for mobile menu toggle later if needed */}
                    </div>
                    <button className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-800 hover:text-white">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                        </svg>
                        Share
                    </button>
                </header>

                {/* Scrollable Center Area (Empty State) */}
                <div className="flex-1 overflow-y-auto px-4 py-8">
                    <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center text-center">
                        <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-500/10 text-cyan-400">
                            <LogoMark className="h-10 w-10" />
                        </div>
                        <h1 className="mb-3 text-3xl font-semibold text-slate-100">How can I help you diagnose?</h1>
                        <p className="max-w-md text-slate-400">
                            Paste your Kubernetes telemetry logs, events, or describe symptom behavior. The model will analyze it and pinpoint the root cause.
                        </p>
                    </div>
                </div>

                {/* Input Form at Bottom */}
                <div className="w-full shrink-0 bg-gradient-to-t from-slate-950 px-4 pb-6 pt-4">
                    <div className="mx-auto max-w-3xl relative">
                        <div className="relative flex w-full flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-800 focus-within:border-slate-500 focus-within:ring-1 focus-within:ring-slate-500 transition-all">
                            <textarea
                                value={telemetry}
                                onChange={(e) => setTelemetry(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Paste logs, events, or describe Kubernetes issue..."
                                className="w-full resize-none border-0 bg-transparent py-4 pl-4 pr-12 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-0 sm:text-sm min-h-[56px] max-h-72 overflow-y-auto block"
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
                                disabled={!telemetry.trim()}
                                className="absolute bottom-2 right-2 flex h-8 w-8 items-center justify-center rounded-md bg-cyan-500 text-white transition-opacity disabled:opacity-30 hover:bg-cyan-400"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4 transform -rotate-90">
                                    <path d="M3.478 2.404a.75.75 0 00-.926.941l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.404z" />
                                </svg>
                            </button>
                        </div>
                        <div className="mt-2 text-center text-xs text-slate-500">
                            KubeRCA can make mistakes. Consider verifying critical findings before taking destructive action.
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default Dashboard;

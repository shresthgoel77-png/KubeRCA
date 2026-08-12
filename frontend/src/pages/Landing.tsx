import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useInView, useScroll, useTransform } from "framer-motion";

/* ------------------------------------------------------------------ */
/* Custom abstract logo mark – geometric Kubernetes-inspired SVG      */
/* ------------------------------------------------------------------ */
const LogoMark = ({ className = "" }: { className?: string }) => (
    <svg
        viewBox="0 0 120 120"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
    >
        {/* Outer hexagonal ring */}
        <path
            d="M60 8L104 32V72L60 112L16 72V32L60 8Z"
            stroke="url(#logoGrad1)"
            strokeWidth="2"
            fill="none"
            opacity="0.6"
        />
        {/* Inner rotating diamond */}
        <path
            d="M60 24L88 60L60 96L32 60L60 24Z"
            stroke="url(#logoGrad2)"
            strokeWidth="1.5"
            fill="url(#logoGrad2)"
            fillOpacity="0.08"
        />
        {/* Central node cluster */}
        <circle cx="60" cy="44" r="4" fill="url(#logoGrad1)" />
        <circle cx="44" cy="64" r="3.5" fill="url(#logoGrad2)" />
        <circle cx="76" cy="64" r="3.5" fill="url(#logoGrad2)" />
        <circle cx="60" cy="80" r="3" fill="url(#logoGrad1)" opacity="0.7" />
        {/* Connector lines between nodes */}
        <line x1="60" y1="48" x2="44" y2="61" stroke="url(#logoGrad1)" strokeWidth="1" opacity="0.5" />
        <line x1="60" y1="48" x2="76" y2="61" stroke="url(#logoGrad1)" strokeWidth="1" opacity="0.5" />
        <line x1="44" y1="67" x2="60" y2="77" stroke="url(#logoGrad2)" strokeWidth="1" opacity="0.4" />
        <line x1="76" y1="67" x2="60" y2="77" stroke="url(#logoGrad2)" strokeWidth="1" opacity="0.4" />
        {/* Central pulse dot */}
        <circle cx="60" cy="60" r="2" fill="#22d3ee">
            <animate attributeName="r" values="2;3.5;2" dur="2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="1;0.4;1" dur="2s" repeatCount="indefinite" />
        </circle>
        <defs>
            <linearGradient id="logoGrad1" x1="16" y1="8" x2="104" y2="112">
                <stop stopColor="#22d3ee" />
                <stop offset="1" stopColor="#8b5cf6" />
            </linearGradient>
            <linearGradient id="logoGrad2" x1="32" y1="24" x2="88" y2="96">
                <stop stopColor="#8b5cf6" />
                <stop offset="1" stopColor="#22d3ee" />
            </linearGradient>
        </defs>
    </svg>
);

/* ------------------------------------------------------------------ */
/* Animated grid background                                           */
/* ------------------------------------------------------------------ */
const GridBackground = () => (
    <div className="pointer-events-none fixed inset-0 overflow-hidden">
        {/* Dot grid */}
        <div
            className="absolute inset-0 opacity-[0.03]"
            style={{
                backgroundImage: `radial-gradient(circle, #94a3b8 1px, transparent 1px)`,
                backgroundSize: "32px 32px",
            }}
        />
        {/* Gradient orbs */}
        <div className="absolute -top-1/4 left-1/4 h-[600px] w-[600px] rounded-full bg-cyan-500/[0.07] blur-[120px]" />
        <div className="absolute -bottom-1/4 right-1/4 h-[500px] w-[500px] rounded-full bg-violet-500/[0.07] blur-[120px]" />
    </div>
);

/* ------------------------------------------------------------------ */
/* Feature card component                                             */
/* ------------------------------------------------------------------ */
interface FeatureCardProps {
    icon: React.ReactNode;
    title: string;
    description: string;
    delay?: number;
}

const FeatureCard = ({ icon, title, description, delay = 0 }: FeatureCardProps) => {
    const ref = useRef(null);
    const isInView = useInView(ref, { once: true, margin: "-80px" });

    return (
        <motion.div
            ref={ref}
            initial={{ opacity: 0, y: 30 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.6, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="group relative rounded-2xl border border-slate-800/60 bg-slate-900/40 p-8 backdrop-blur-sm transition-colors duration-300 hover:border-slate-700/80 hover:bg-slate-800/30"
        >
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-violet-500/20 text-cyan-400 transition-colors duration-300 group-hover:from-cyan-500/30 group-hover:to-violet-500/30">
                {icon}
            </div>
            <h3 className="mb-3 text-lg font-semibold text-slate-100">{title}</h3>
            <p className="text-sm leading-relaxed text-slate-400">{description}</p>
        </motion.div>
    );
};

/* ------------------------------------------------------------------ */
/* Stat pill component                                                */
/* ------------------------------------------------------------------ */
const StatPill = ({ value, label }: { value: string; label: string }) => (
    <div className="flex flex-col items-center gap-1 px-6">
        <span className="bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-3xl font-bold text-transparent md:text-4xl">
            {value}
        </span>
        <span className="text-xs tracking-wider text-slate-500 uppercase">{label}</span>
    </div>
);

/* ------------------------------------------------------------------ */
/* Terminal mockup for social proof                                    */
/* ------------------------------------------------------------------ */
const TerminalMockup = () => {
    const ref = useRef(null);
    const isInView = useInView(ref, { once: true, margin: "-60px" });

    const lines = [
        { prefix: "$", text: "kubectl get pods -n production", color: "text-slate-300" },
        { prefix: "", text: "NAME                        READY   STATUS             RESTARTS", color: "text-slate-500" },
        { prefix: "", text: "api-server-7b5d4f8c9-x2k4l  1/1    CrashLoopBackOff   14", color: "text-rose-400" },
        { prefix: "", text: "worker-6c8f9d2e1-m8n3j      0/1    OOMKilled          8", color: "text-amber-400" },
        { prefix: "", text: "", color: "" },
        { prefix: "⚡", text: " KubeRCA diagnosing...", color: "text-cyan-400" },
        { prefix: "", text: "", color: "" },
        { prefix: "✓", text: " Root Cause: Memory limit (256Mi) insufficient for payload spike", color: "text-emerald-400" },
        { prefix: "", text: "  Confidence: 0.92  |  Severity: SEV-2", color: "text-slate-400" },
        { prefix: "", text: '  Evidence: ["OOMKilled x8 in 2h", "RSS peak 312Mi > limit 256Mi"]', color: "text-slate-500" },
    ];

    return (
        <motion.div
            ref={ref}
            initial={{ opacity: 0, y: 40 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.8, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="mx-auto w-full max-w-3xl overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-950/80 shadow-2xl shadow-black/40 backdrop-blur-sm"
        >
            {/* Title bar */}
            <div className="flex items-center gap-2 border-b border-slate-800/60 px-4 py-3">
                <div className="h-3 w-3 rounded-full bg-rose-400/70" />
                <div className="h-3 w-3 rounded-full bg-amber-400/70" />
                <div className="h-3 w-3 rounded-full bg-emerald-400/70" />
                <span className="ml-3 text-xs text-slate-500 font-mono">kuberca — diagnosis output</span>
            </div>
            {/* Terminal body */}
            <div className="p-6 font-mono text-xs leading-6 sm:text-sm">
                {lines.map((line, i) => (
                    <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -10 }}
                        animate={isInView ? { opacity: 1, x: 0 } : {}}
                        transition={{ duration: 0.3, delay: 0.3 + i * 0.08 }}
                        className={line.color}
                    >
                        {line.prefix && (
                            <span className="mr-2 text-slate-600">{line.prefix}</span>
                        )}
                        {line.text}
                    </motion.div>
                ))}
                <motion.span
                    className="mt-1 inline-block h-4 w-2 bg-cyan-400"
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.8, repeat: Infinity, repeatType: "reverse" }}
                />
            </div>
        </motion.div>
    );
};

/* ================================================================== */
/* LANDING PAGE                                                       */
/* ================================================================== */
const Landing = () => {
    const navigate = useNavigate();
    const heroRef = useRef<HTMLDivElement>(null);
    const { scrollYProgress } = useScroll();
    const heroOpacity = useTransform(scrollYProgress, [0, 0.25], [1, 0]);
    const heroY = useTransform(scrollYProgress, [0, 0.25], [0, -60]);

    /* Preload Google Fonts */
    useEffect(() => {
        const link = document.createElement("link");
        link.href =
            "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap";
        link.rel = "stylesheet";
        document.head.appendChild(link);
        return () => {
            document.head.removeChild(link);
        };
    }, []);

    return (
        <div className="relative min-h-screen bg-slate-950 text-slate-100">
            <GridBackground />

            {/* ---- Navbar ---- */}
            <nav className="fixed top-0 right-0 left-0 z-50 border-b border-slate-800/40 bg-slate-950/70 backdrop-blur-xl">
                <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
                    <div className="flex items-center gap-3">
                        <LogoMark className="h-8 w-8" />
                        <span className="text-lg font-bold tracking-tight">KubeRCA</span>
                    </div>
                    <div className="hidden items-center gap-8 text-sm text-slate-400 md:flex">
                        <a href="#features" className="transition-colors hover:text-slate-100">Features</a>
                        <a href="#demo" className="transition-colors hover:text-slate-100">Demo</a>
                    </div>
                    <button
                        onClick={() => navigate("/dashboard")}
                        className="rounded-lg bg-gradient-to-r from-cyan-500 to-violet-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-cyan-500/20 transition-all duration-200 hover:shadow-cyan-500/30 hover:brightness-110 active:scale-95"
                    >
                        Try Now
                    </button>
                </div>
            </nav>

            {/* ---- Hero ---- */}
            <motion.section
                ref={heroRef}
                style={{ opacity: heroOpacity, y: heroY }}
                className="relative flex min-h-screen flex-col items-center justify-center px-6 pt-16 text-center"
            >
                {/* Badge */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.2 }}
                    className="mb-8 inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 backdrop-blur-sm"
                >
                    <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                    </span>
                    AI-powered root-cause analysis
                </motion.div>

                {/* Logo */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.8, delay: 0.1, ease: [0.25, 0.46, 0.45, 0.94] }}
                    className="mb-10"
                >
                    <LogoMark className="mx-auto h-24 w-24 drop-shadow-[0_0_40px_rgba(34,211,238,0.25)] md:h-28 md:w-28" />
                </motion.div>

                {/* Headline */}
                <motion.h1
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, delay: 0.3 }}
                    className="max-w-4xl text-4xl leading-[1.1] font-extrabold tracking-tight sm:text-5xl md:text-7xl"
                >
                    Diagnose Kubernetes failures{" "}
                    <span className="bg-gradient-to-r from-cyan-400 via-violet-400 to-cyan-400 bg-clip-text text-transparent">
                        in seconds
                    </span>
                </motion.h1>

                {/* Subheading */}
                <motion.p
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, delay: 0.5 }}
                    className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-400 md:text-xl"
                >
                    Paste your telemetry. Get the root cause, confidence score, and
                    severity — powered by a fine-tuned LLM that understands your cluster.
                </motion.p>

                {/* CTA */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, delay: 0.7 }}
                    className="mt-10 flex flex-wrap items-center justify-center gap-4"
                >
                    <button
                        onClick={() => navigate("/dashboard")}
                        className="group relative rounded-xl bg-gradient-to-r from-cyan-500 to-violet-500 px-8 py-3.5 text-base font-semibold text-white shadow-xl shadow-cyan-500/20 transition-all duration-200 hover:shadow-cyan-500/30 hover:brightness-110 active:scale-[0.97]"
                    >
                        <span className="relative z-10 flex items-center gap-2">
                            Try Now
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 transition-transform group-hover:translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                            </svg>
                        </span>
                    </button>
                    <a
                        href="#demo"
                        className="rounded-xl border border-slate-700 px-8 py-3.5 text-base font-medium text-slate-300 transition-all duration-200 hover:border-slate-600 hover:bg-slate-800/40"
                    >
                        See it in action
                    </a>
                </motion.div>

                {/* Scroll hint */}
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 1.5, duration: 1 }}
                    className="absolute bottom-10"
                >
                    <motion.div
                        animate={{ y: [0, 8, 0] }}
                        transition={{ duration: 2, repeat: Infinity }}
                        className="flex flex-col items-center gap-2 text-slate-600"
                    >
                        <span className="text-xs tracking-widest uppercase">Scroll</span>
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                        </svg>
                    </motion.div>
                </motion.div>
            </motion.section>

            {/* ---- Stats bar ---- */}
            <section className="relative border-y border-slate-800/40 bg-slate-900/30 py-12 backdrop-blur-sm">
                <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-8 md:divide-x md:divide-slate-800">
                    <StatPill value="< 30s" label="Diagnosis Time" />
                    <StatPill value="0.9+" label="Avg Confidence" />
                    <StatPill value="3" label="Severity Tiers" />
                    <StatPill value="100%" label="Open Source" />
                </div>
            </section>

            {/* ---- Features ---- */}
            <section id="features" className="relative py-24 md:py-32">
                <div className="mx-auto max-w-7xl px-6">
                    <div className="mb-16 text-center">
                        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
                            Why{" "}
                            <span className="bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent">
                                KubeRCA
                            </span>
                        </h2>
                        <p className="mx-auto mt-4 max-w-xl text-slate-400">
                            From raw telemetry to actionable root cause — no dashboards to configure,
                            no runbooks to maintain.
                        </p>
                    </div>

                    <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                        <FeatureCard
                            delay={0}
                            icon={
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                                </svg>
                            }
                            title="Fine-Tuned for K8s"
                            description="Purpose-built on Qwen 2.5 with a curated Kubernetes incident dataset — not a generic chatbot guessing at your YAML."
                        />
                        <FeatureCard
                            delay={0.1}
                            icon={
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                                </svg>
                            }
                            title="Seconds, Not Hours"
                            description="Paste raw logs, events, or kubectl output. Get a structured diagnosis with confidence score and severity in under 30 seconds."
                        />
                        <FeatureCard
                            delay={0.2}
                            icon={
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
                                </svg>
                            }
                            title="Evidence-Grounded"
                            description="Every diagnosis cites specific evidence from your telemetry. No hallucinated logs, no invented error messages."
                        />
                        <FeatureCard
                            delay={0.3}
                            icon={
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 14.25v2.25m3-4.5v4.5m3-6.75v6.75m3-9v9M6 20.25h12A2.25 2.25 0 0 0 20.25 18V6A2.25 2.25 0 0 0 18 3.75H6A2.25 2.25 0 0 0 3.75 6v12A2.25 2.25 0 0 0 6 20.25Z" />
                                </svg>
                            }
                            title="Structured Output"
                            description="Returns machine-readable JSON with failure summary, root cause, confidence (0-1), evidence array, and SEV-1/2/3 severity."
                        />
                        <FeatureCard
                            delay={0.4}
                            icon={
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 9.563C9 9.252 9.252 9 9.563 9h4.874c.311 0 .563.252.563.563v4.874c0 .311-.252.563-.563.563H9.564A.562.562 0 0 1 9 14.437V9.564Z" />
                                </svg>
                            }
                            title="Self-Hosted & Private"
                            description="Runs entirely on your infrastructure. Your telemetry never leaves your network — no cloud API keys required."
                        />
                        <FeatureCard
                            delay={0.5}
                            icon={
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M14.25 9.75 16.5 12l-2.25 2.25m-4.5 0L7.5 12l2.25-2.25M6 20.25h12A2.25 2.25 0 0 0 20.25 18V6A2.25 2.25 0 0 0 18 3.75H6A2.25 2.25 0 0 0 3.75 6v12A2.25 2.25 0 0 0 6 20.25Z" />
                                </svg>
                            }
                            title="REST API First"
                            description="Clean FastAPI backend with a single POST /diagnose endpoint. Integrate into your CI/CD, Slack bots, or PagerDuty workflows."
                        />
                    </div>
                </div>
            </section>

            {/* ---- Demo terminal ---- */}
            <section id="demo" className="relative py-24 md:py-32">
                <div className="mx-auto max-w-7xl px-6">
                    <div className="mb-16 text-center">
                        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">See it in action</h2>
                        <p className="mx-auto mt-4 max-w-xl text-slate-400">
                            Real output from the KubeRCA model analyzing a production incident.
                        </p>
                    </div>
                    <TerminalMockup />
                </div>
            </section>

            {/* ---- Bottom CTA ---- */}
            <section className="relative py-24 md:py-32">
                <div className="mx-auto max-w-3xl px-6 text-center">
                    <motion.div
                        initial={{ opacity: 0, y: 30 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.7 }}
                    >
                        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl md:text-5xl">
                            Stop guessing.{" "}
                            <span className="bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text text-transparent">
                                Start diagnosing.
                            </span>
                        </h2>
                        <p className="mx-auto mt-6 max-w-xl text-lg text-slate-400">
                            Paste your Kubernetes telemetry and let the model do the rest.
                        </p>
                        <button
                            onClick={() => navigate("/dashboard")}
                            className="mt-10 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-500 px-10 py-4 text-lg font-semibold text-white shadow-xl shadow-cyan-500/20 transition-all duration-200 hover:shadow-cyan-500/30 hover:brightness-110 active:scale-[0.97]"
                        >
                            Get Started
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                            </svg>
                        </button>
                    </motion.div>
                </div>
            </section>

            {/* ---- Footer ---- */}
            <footer className="border-t border-slate-800/40 py-10">
                <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-6 sm:flex-row">
                    <div className="flex items-center gap-2 text-sm text-slate-500">
                        <LogoMark className="h-5 w-5" />
                        <span>KubeRCA</span>
                        <span className="text-slate-700">·</span>
                        <span>Open Source Kubernetes RCA</span>
                    </div>
                    <span className="text-xs text-slate-700">
                        Built with Qwen 2.5 · FastAPI · React
                    </span>
                </div>
            </footer>
        </div>
    );
};

export default Landing;

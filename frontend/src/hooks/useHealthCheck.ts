import { useState, useEffect, useRef, useCallback } from "react";
import { checkHealth } from "../services/api";

const POLL_INTERVAL_MS = 30_000; // 30 seconds
const INITIAL_DELAY_MS = 0; // check immediately on mount

/**
 * Periodically polls GET /health and exposes the backend status.
 * Returns { isAvailable, isChecking, lastCheckedAt, recheckNow }.
 */
export function useHealthCheck() {
    const [isAvailable, setIsAvailable] = useState<boolean | null>(null); // null = not yet checked
    const [isChecking, setIsChecking] = useState(false);
    const [lastCheckedAt, setLastCheckedAt] = useState<number | null>(null);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const check = useCallback(async () => {
        setIsChecking(true);
        try {
            const ok = await checkHealth();
            setIsAvailable(ok);
        } catch {
            setIsAvailable(false);
        } finally {
            setIsChecking(false);
            setLastCheckedAt(Date.now());
        }
    }, []);

    useEffect(() => {
        // Initial check
        const initTimer = setTimeout(check, INITIAL_DELAY_MS);

        // Periodic polling
        timerRef.current = setInterval(check, POLL_INTERVAL_MS);

        return () => {
            clearTimeout(initTimer);
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [check]);

    return { isAvailable, isChecking, lastCheckedAt, recheckNow: check };
}

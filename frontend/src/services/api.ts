import type { DiagnosisResponse } from '../types/diagnosis';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const DEFAULT_TIMEOUT_MS = 30 * 1000;

export class NetworkError extends Error {
    constructor(message = 'Network error occurred') {
        super(message);
        this.name = 'NetworkError';
    }
}

export class TimeoutError extends Error {
    constructor(message = `Request timed out after ${DEFAULT_TIMEOUT_MS / 1000}s`) {
        super(message);
        this.name = 'TimeoutError';
    }
}

export class ApiError extends Error {
    public status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
        this.name = 'ApiError';
    }
}

export class ValidationError extends Error {
    constructor(message = 'Invalid response payload shape') {
        super(message);
        this.name = 'ValidationError';
    }
}

/** Helper function with AbortController for network requests */
function fetchWithTimeout(url: string, options: RequestInit = {}): Promise<Response> {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

    return fetch(url, {
        ...options,
        signal: controller.signal
    })
        .catch((error) => {
            // Differentiate AbortError vs real Network failures natively
            if (error.name === 'AbortError') {
                throw new TimeoutError();
            }
            throw new NetworkError(error.message);
        })
        .finally(() => {
            clearTimeout(id);
        });
}

/** Check health of model and backend */
export async function checkHealth(): Promise<boolean> {
    try {
        const response = await fetchWithTimeout(`${API_BASE_URL}/health`);
        if (!response.ok) return false;
        const body = await response.json();
        return body.status === 'ok';
    } catch {
        return false;
    }
}

/** Type guard validator ensuring the API output strictly matches our frontend interfaces */
function isDiagnosisResponse(data: any): data is DiagnosisResponse {
    if (!data || typeof data !== 'object') return false;
    if (typeof data.failure !== 'string') return false;
    if (typeof data.root_cause !== 'string') return false;
    if (typeof data.confidence !== 'number') return false;
    if (!Array.isArray(data.evidence) || !data.evidence.every((e: any) => typeof e === 'string')) return false;
    if (!['SEV-1', 'SEV-2', 'SEV-3'].includes(data.severity)) return false;
    return true;
}

/** Process telemetry via the single model endpoint */
export async function diagnose(telemetry: string): Promise<DiagnosisResponse> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/diagnose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telemetry }),
    });

    if (!response.ok) {
        let errorDetail = response.statusText;
        try {
            const errorBody = await response.json();
            if (errorBody.detail) {
                errorDetail = typeof errorBody.detail === 'string' ? errorBody.detail : JSON.stringify(errorBody.detail);
            }
        } catch { /* proceed with fallback string */ }
        throw new ApiError(response.status, `Backend returned ${response.status}: ${errorDetail}`);
    }

    let data;
    try {
        data = await response.json();
    } catch (e: any) {
        throw new ValidationError('Failed to parse JSON response: ' + e.message);
    }

    if (!isDiagnosisResponse(data)) {
        throw new ValidationError('Response JSON shape does not match DiagnosisResponse interface');
    }

    return data;
}

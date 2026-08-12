export type Severity = "SEV-1" | "SEV-2" | "SEV-3";

export interface DiagnosisResponse {
    failure: string;
    root_cause: string;
    confidence: number;
    evidence: string[]; // Note: using string[] to exactly mirror backend's List[str]
    severity: Severity;
}

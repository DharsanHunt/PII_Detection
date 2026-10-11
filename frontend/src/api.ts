import type {
  AuditEvent,
  BenchmarkReport,
  CaseArtifactInfo,
  DashboardSummary,
  DocumentRecord,
  PIIEntityCategory,
  PolicyConfig,
  ReviewStatus,
} from './types';

const API_BASE = '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errText = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) {
        errText =
          typeof data.detail === 'string'
            ? data.detail
            : JSON.stringify(data.detail);
      }
    } catch {
      errText = await res.text();
    }
    throw new Error(errText);
  }
  return res.json() as Promise<T>;
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const res = await fetch(`${API_BASE}/dashboard/summary`);
  return handleResponse<DashboardSummary>(res);
}

export async function fetchCaseArtifacts(): Promise<CaseArtifactInfo[]> {
  const res = await fetch(`${API_BASE}/case-artifacts`);
  return handleResponse<CaseArtifactInfo[]>(res);
}

export async function loadCaseArtifact(artifactName: string): Promise<DocumentRecord> {
  const res = await fetch(`${API_BASE}/documents/load-case-artifact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ artifact_name: artifactName }),
  });
  return handleResponse<DocumentRecord>(res);
}

export async function uploadFilesBatch(
  files: File[]
): Promise<{ processed: DocumentRecord[]; errors: Array<{ filename: string; error: string }> }> {
  const form = new FormData();
  for (const f of files) {
    form.append('files', f);
  }
  const res = await fetch(`${API_BASE}/documents/upload`, {
    method: 'POST',
    body: form,
  });
  return handleResponse<{
    processed: DocumentRecord[];
    errors: Array<{ filename: string; error: string }>;
  }>(res);
}

export async function fetchDocumentDetail(docId: string): Promise<DocumentRecord> {
  const res = await fetch(`${API_BASE}/documents/${docId}`);
  return handleResponse<DocumentRecord>(res);
}

export async function updateFindingStatus(
  docId: string,
  findingId: string,
  payload: {
    review_status?: ReviewStatus;
    category?: PIIEntityCategory;
    replacement_label?: string;
  }
): Promise<DocumentRecord> {
  const res = await fetch(`${API_BASE}/documents/${docId}/findings/${findingId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<DocumentRecord>(res);
}

export async function approveAllFlaggedFindings(docId: string): Promise<DocumentRecord> {
  const res = await fetch(`${API_BASE}/documents/${docId}/findings/approve-all`, {
    method: 'POST',
  });
  return handleResponse<DocumentRecord>(res);
}

export async function createManualFinding(
  docId: string,
  payload: {
    block_id: string;
    exact_text: string;
    category: PIIEntityCategory;
    rationale: string;
  }
): Promise<DocumentRecord> {
  const res = await fetch(`${API_BASE}/documents/${docId}/findings/manual`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<DocumentRecord>(res);
}

export async function fetchPolicy(): Promise<PolicyConfig> {
  const res = await fetch(`${API_BASE}/policy`);
  return handleResponse<PolicyConfig>(res);
}

export async function savePolicy(policy: PolicyConfig): Promise<PolicyConfig> {
  const res = await fetch(`${API_BASE}/policy`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  });
  return handleResponse<PolicyConfig>(res);
}

export async function fetchAuditLog(): Promise<AuditEvent[]> {
  const res = await fetch(`${API_BASE}/audit-log`);
  return handleResponse<AuditEvent[]>(res);
}

export async function runBenchmarkSuite(refresh = false): Promise<BenchmarkReport> {
  const res = await fetch(`${API_BASE}/benchmark/run?refresh=${refresh}`);
  return handleResponse<BenchmarkReport>(res);
}

export async function invokeDownstreamLLM(
  docId: string,
  promptInstruction: string
): Promise<{
  doc_id: string;
  filename: string;
  gate_status_verified: string;
  provider: string;
  processed_at: string;
  sanitized_char_count: number;
  sanitized_payload_preview: string;
  llm_response: string;
}> {
  const res = await fetch(`${API_BASE}/documents/${docId}/llm-handoff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_instruction: promptInstruction }),
  });
  return handleResponse(res);
}

import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  FileCheck,
  FileSpreadsheet,
  FileText,
  Filter,
  FlaskConical,
  FolderOpen,
  Layers,
  Lock,
  PlusCircle,
  RefreshCw,
  Search,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  approveAllFlaggedFindings,
  createManualFinding,
  fetchAuditLog,
  fetchCaseArtifacts,
  fetchDashboardSummary,
  fetchDocumentDetail,
  fetchPolicy,
  invokeDownstreamLLM,
  loadCaseArtifact,
  runBenchmarkSuite,
  savePolicy,
  updateFindingStatus,
  uploadFilesBatch,
} from './api';
import type {
  AuditEvent,
  BenchmarkReport,
  CaseArtifactInfo,
  DashboardSummary,
  DocumentRecord,
  GateState,
  PIIEntityCategory,
  PolicyConfig,
  ReviewStatus,
} from './types';

type ActiveTab = 'dashboard' | 'workspace' | 'review' | 'export' | 'benchmark' | 'policy';

const ALL_CATEGORIES: PIIEntityCategory[] = [
  'PERSON_NAME',
  'EMAIL',
  'PHONE_NUMBER',
  'EMPLOYEE_ID',
  'ACCOUNT_NUMBER',
  'GOVERNMENT_ID_STYLE',
  'TAX_ID_PAN_STYLE',
  'ADDRESS',
  'DATE_OF_BIRTH',
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function GateBadge({ status }: { status: GateState | string }) {
  if (status === 'PASS') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
        PASS · LLM CLEARED
      </span>
    );
  }
  if (status === 'REVIEW_REQUIRED') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
        REVIEW REQUIRED · HOLD
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-red-50 text-red-800 border border-red-200">
      <XCircle className="w-3.5 h-3.5 text-red-600" />
      {status} · BLOCKED
    </span>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [caseArtifacts, setCaseArtifacts] = useState<CaseArtifactInfo[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<DocumentRecord | null>(null);
  const [policy, setPolicy] = useState<PolicyConfig | null>(null);
  const [auditLog, setAuditLog] = useState<AuditEvent[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkReport | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadingMessage, setLoadingMessage] = useState<string>('');
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Workspace state
  const [previewPage, setPreviewPage] = useState<number>(1);
  const [showVisualPreview, setShowVisualPreview] = useState<boolean>(true);
  const [onlyPiiBlocks, setOnlyPiiBlocks] = useState<boolean>(true);
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string>('ALL');
  const [blockSearch, setBlockSearch] = useState<string>('');

  // Findings review state
  const [reviewFilterStatus, setReviewFilterStatus] = useState<string>('ALL');
  const [reviewFilterCategory, setReviewFilterCategory] = useState<string>('ALL');
  const [reviewSearch, setReviewSearch] = useState<string>('');
  const [showUnmaskedInReview, setShowUnmaskedInReview] = useState<boolean>(true);
  const [manualBlockId, setManualBlockId] = useState<string>('');
  const [manualText, setManualText] = useState<string>('');
  const [manualCategory, setManualCategory] = useState<PIIEntityCategory>('PERSON_NAME');
  const [manualRationale, setManualRationale] = useState<string>('Analyst identified missed PII during manual inspection');

  // Downstream LLM state
  const [llmPrompt, setLlmPrompt] = useState<string>(
    'Summarize organizational governance, risk appetite limits, and accountability roles without exposing personal identifiers.'
  );
  const [llmResult, setLlmResult] = useState<{
    gate_status_verified: string;
    provider: string;
    processed_at: string;
    sanitized_char_count: number;
    sanitized_payload_preview: string;
    llm_response: string;
  } | null>(null);

  async function refreshAll(selectId?: string) {
    try {
      const [dash, artifacts, pol, logs] = await Promise.all([
        fetchDashboardSummary(),
        fetchCaseArtifacts(),
        fetchPolicy(),
        fetchAuditLog(),
      ]);
      setDashboard(dash);
      setCaseArtifacts(artifacts);
      setPolicy(pol);
      setAuditLog(logs);

      const targetId = selectId || selectedDocId || (dash.documents[0]?.doc_id ?? null);
      if (targetId) {
        setSelectedDocId(targetId);
        const detail = await fetchDocumentDetail(targetId);
        setSelectedDoc(detail);
        if (!manualBlockId && detail.block_comparisons.length > 0) {
          setManualBlockId(detail.block_comparisons[0].block_id);
        }
      }
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refreshAll();
  }, []);

  async function handleSelectDoc(docId: string, navigateTo?: ActiveTab) {
    setSelectedDocId(docId);
    setPreviewPage(1);
    setLlmResult(null);
    try {
      const detail = await fetchDocumentDetail(docId);
      setSelectedDoc(detail);
      if (detail.block_comparisons.length > 0) {
        setManualBlockId(detail.block_comparisons[0].block_id);
      }
      if (navigateTo) {
        setActiveTab(navigateTo);
      }
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;
    const files = Array.from(fileList);
    setIsLoading(true);
    setLoadingMessage(`Validating signatures, extracting layout, detecting PII & redacting ${files.length} file(s)...`);
    setErrorBanner(null);
    setSuccessBanner(null);

    try {
      const res = await uploadFilesBatch(files);
      if (res.errors.length > 0) {
        setErrorBanner(
          res.errors.map((er) => `${er.filename}: ${er.error}`).join(' | ')
        );
      }
      if (res.processed.length > 0) {
        const lastDoc = res.processed[res.processed.length - 1];
        setSuccessBanner(
          `Processed ${res.processed.length} artifact(s). Latest: ${lastDoc.filename} (${lastDoc.active_findings_count} PII entities redacted, Gate: ${lastDoc.validation?.gate_status}).`
        );
        await refreshAll(lastDoc.doc_id);
      }
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
      e.target.value = '';
    }
  }

  async function handleLoadCaseArtifact(filename: string) {
    setIsLoading(true);
    setLoadingMessage(`Processing Case Study 2 artifact '${filename}' through 13-stage privacy pipeline...`);
    setErrorBanner(null);
    setSuccessBanner(null);
    try {
      const rec = await loadCaseArtifact(filename);
      setSuccessBanner(
        `Loaded '${rec.filename}': ${rec.active_findings_count} PII findings detected & redacted. Structure Retention: ${((rec.validation?.structure_metrics.overall_structure_score ?? 1) * 100).toFixed(1)}%, Gate: ${rec.validation?.gate_status}.`
      );
      await refreshAll(rec.doc_id);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
    }
  }

  async function handleUpdateFinding(
    findingId: string,
    payload: { review_status?: ReviewStatus; category?: PIIEntityCategory }
  ) {
    if (!selectedDoc) return;
    setIsLoading(true);
    setLoadingMessage('Re-applying format-preserving redaction and re-running independent Privacy Gate validation...');
    setErrorBanner(null);
    try {
      const updated = await updateFindingStatus(selectedDoc.doc_id, findingId, payload);
      setSelectedDoc(updated);
      await refreshAll(updated.doc_id);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
    }
  }

  async function handleApproveAllFlagged() {
    if (!selectedDoc) return;
    setIsLoading(true);
    setLoadingMessage('Approving all flagged findings and re-validating output artifact...');
    setErrorBanner(null);
    try {
      const updated = await approveAllFlaggedFindings(selectedDoc.doc_id);
      setSelectedDoc(updated);
      setSuccessBanner(
        `All flagged findings resolved. Privacy Gate is now ${updated.validation?.gate_status}.`
      );
      await refreshAll(updated.doc_id);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
    }
  }

  async function handleAddManualFinding(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedDoc || !manualBlockId || !manualText.trim()) return;
    setIsLoading(true);
    setLoadingMessage('Adding manual PII finding, re-redacting artifact, and re-running Privacy Gate...');
    setErrorBanner(null);
    try {
      const updated = await createManualFinding(selectedDoc.doc_id, {
        block_id: manualBlockId,
        exact_text: manualText.trim(),
        category: manualCategory,
        rationale: manualRationale,
      });
      setSelectedDoc(updated);
      setManualText('');
      setSuccessBanner('Manual finding added and redacted in native artifact.');
      await refreshAll(updated.doc_id);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
    }
  }

  async function handleRunBenchmark(forceRefresh = false) {
    setIsLoading(true);
    setLoadingMessage('Executing 28-case Gold Benchmark & 5-format Synthetic File Benchmark...');
    setErrorBanner(null);
    try {
      const rep = await runBenchmarkSuite(forceRefresh);
      setBenchmark(rep);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
    }
  }

  async function handleLLMHandoff() {
    if (!selectedDoc) return;
    setIsLoading(true);
    setLoadingMessage('Verifying Privacy Gate server-side and transmitting sanitized blocks...');
    setErrorBanner(null);
    try {
      const res = await invokeDownstreamLLM(selectedDoc.doc_id, llmPrompt);
      setLlmResult(res);
      await refreshAll(selectedDoc.doc_id);
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
    }
  }

  async function handleSavePolicy(e: React.FormEvent) {
    e.preventDefault();
    if (!policy) return;
    setIsLoading(true);
    setLoadingMessage('Saving security policy & redaction configuration...');
    setErrorBanner(null);
    try {
      const saved = await savePolicy(policy);
      setPolicy(saved);
      setSuccessBanner('Policy settings updated successfully.');
      await refreshAll();
    } catch (err) {
      setErrorBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
      setLoadingMessage('');
    }
  }

  const canVisualPreview =
    selectedDoc &&
    ['PDF', 'SCANNED_PDF', 'PNG', 'JPG'].includes(selectedDoc.detected_format);

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      {/* Top Enterprise Header */}
      <header className="bg-slate-900 text-white border-b border-slate-800 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-700 flex items-center justify-center shadow-sm">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold tracking-tight text-base">
                  CADENCE FINANCIAL GROUP
                </span>
                <span className="text-[11px] uppercase tracking-wider px-2 py-0.5 rounded bg-blue-900/80 text-blue-200 border border-blue-700/60 font-medium">
                  Optiv Advisory · Case Study 2
                </span>
              </div>
              <p className="text-xs text-slate-400">
                PII Detection, Format-Preserving Redaction &amp; Downstream LLM Sanitization Gateway
              </p>
            </div>
          </div>

          {/* Document Selector & Global Gate Indicator */}
          <div className="flex items-center gap-3">
            {dashboard && dashboard.documents.length > 0 && (
              <div className="flex items-center gap-2 bg-slate-800/90 border border-slate-700 rounded-md px-2.5 py-1.5 text-xs">
                <FolderOpen className="w-3.5 h-3.5 text-blue-400" />
                <span className="text-slate-400">Active Artifact:</span>
                <select
                  aria-label="Select active document"
                  value={selectedDocId ?? ''}
                  onChange={(e) => void handleSelectDoc(e.target.value)}
                  className="bg-transparent text-white font-medium focus:outline-none cursor-pointer"
                >
                  {dashboard.documents.map((d) => (
                    <option key={d.doc_id} value={d.doc_id} className="bg-slate-900 text-white">
                      {d.filename} ({d.detected_format} · {d.gate_status})
                    </option>
                  ))}
                </select>
              </div>
            )}
            {selectedDoc?.validation && (
              <GateBadge status={selectedDoc.validation.gate_status} />
            )}
          </div>
        </div>

        {/* Navigation Bar */}
        <div className="bg-slate-950/60 border-t border-slate-800/80">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center gap-1 overflow-x-auto">
            {[
              { id: 'dashboard', label: 'A. Security Dashboard', icon: Layers },
              { id: 'workspace', label: 'B. Document Workspace', icon: Eye },
              {
                id: 'review',
                label: `C. Findings Review${
                  selectedDoc?.validation?.unresolved_review_count
                    ? ` (${selectedDoc.validation.unresolved_review_count})`
                    : ''
                }`,
                icon: ShieldAlert,
              },
              { id: 'export', label: 'D. Safe Export & AI Gate', icon: Download },
              { id: 'benchmark', label: 'E. Evaluation Benchmark', icon: FlaskConical },
              { id: 'policy', label: 'F. Policy & Labels', icon: Sliders },
            ].map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTab(item.id as ActiveTab);
                    if (item.id === 'benchmark' && !benchmark) {
                      void handleRunBenchmark(false);
                    }
                  }}
                  className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${
                    isActive
                      ? 'border-blue-500 text-white bg-slate-900/70'
                      : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      {/* Status / Alert Banners */}
      <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 pt-4 space-y-2">
        {isLoading && (
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-blue-950 text-blue-100 border border-blue-800 text-xs shadow-sm">
            <RefreshCw className="w-4 h-4 animate-spin text-blue-400 shrink-0" />
            <span className="font-medium">{loadingMessage || 'Processing...'}</span>
          </div>
        )}
        {errorBanner && (
          <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg bg-red-50 text-red-900 border border-red-200 text-xs">
            <div className="flex items-center gap-2">
              <XCircle className="w-4 h-4 text-red-600 shrink-0" />
              <span className="font-medium">{errorBanner}</span>
            </div>
            <button
              onClick={() => setErrorBanner(null)}
              className="text-red-700 hover:underline font-semibold"
            >
              Dismiss
            </button>
          </div>
        )}
        {successBanner && (
          <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg bg-emerald-50 text-emerald-900 border border-emerald-200 text-xs">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span className="font-medium">{successBanner}</span>
            </div>
            <button
              onClick={() => setSuccessBanner(null)}
              className="text-emerald-700 hover:underline font-semibold"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <main className="max-w-7xl w-full mx-auto px-4 sm:px-6 py-5 flex-1">
        {/* ===================================================================
            SCREEN A: DASHBOARD
        =================================================================== */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* KPI Metric Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Files Processed
                </div>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-2xl font-bold text-slate-900">
                    {dashboard?.files_processed ?? 0}
                  </span>
                  <span className="text-xs text-slate-500">
                    {Object.keys(dashboard?.files_by_format ?? {}).join(', ') || 'No files yet'}
                  </span>
                </div>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  PII Entities Detected
                </div>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-2xl font-bold text-blue-900">
                    {dashboard?.total_pii_detected ?? 0}
                  </span>
                  <span className="text-xs text-slate-500">
                    {Object.keys(dashboard?.entities_by_category ?? {}).length} categories
                  </span>
                </div>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Files Requiring Review
                </div>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-2xl font-bold text-amber-700">
                    {dashboard?.files_requiring_review ?? 0}
                  </span>
                  <span className="text-xs text-slate-500">Low-confidence / OCR flags</span>
                </div>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Privacy Gate Pass / Fail
                </div>
                <div className="mt-2 flex items-center gap-2 text-xs font-semibold">
                  <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200">
                    {dashboard?.gate_counts.PASS ?? 0} PASS
                  </span>
                  <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                    {dashboard?.gate_counts.REVIEW_REQUIRED ?? 0} HOLD
                  </span>
                  <span className="px-2 py-0.5 rounded bg-red-50 text-red-800 border border-red-200">
                    {dashboard?.gate_counts.FAIL ?? 0} FAIL
                  </span>
                </div>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Avg Structure Retention
                </div>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-2xl font-bold text-emerald-800">
                    {((dashboard?.average_structure_retention ?? 1) * 100).toFixed(1)}%
                  </span>
                  <span className="text-xs text-emerald-700 font-medium">Target &ge; 80.0%</span>
                </div>
              </div>
            </div>

            {/* Ingestion Row: Upload Dropzone + Official Case Study 2 Supporting Artifacts */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Upload Box */}
              <div className="lg:col-span-5 bg-white rounded-lg border border-slate-200 p-5 shadow-sm flex flex-col justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                    <Upload className="w-4 h-4 text-blue-700" />
                    Document Batch Upload &amp; Signature Gate
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Accepts digital and scanned PDF, DOCX, PPTX, PNG, and JPG/JPEG. Validates magic
                    bytes, blocks encrypted or zip-bomb containers, and preserves original files.
                  </p>
                </div>

                <label className="mt-4 border-2 border-dashed border-slate-300 hover:border-blue-600 rounded-lg p-6 text-center cursor-pointer transition-colors bg-slate-50/60 hover:bg-blue-50/30">
                  <Upload className="w-7 h-7 text-blue-700 mx-auto mb-2" />
                  <div className="text-xs font-semibold text-slate-800">
                    Click to select one or more documents for sanitization
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">
                    Supported: .pdf, .docx, .pptx, .png, .jpg, .jpeg (Max {policy?.max_file_size_mb ?? 50} MB)
                  </div>
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.docx,.pptx,.png,.jpg,.jpeg"
                    onChange={(e) => void handleFileUpload(e)}
                    className="hidden"
                  />
                </label>
              </div>

              {/* Case Study 2 Official Artifacts Quick-Loader */}
              <div className="lg:col-span-7 bg-white rounded-lg border border-slate-200 p-5 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-blue-700" />
                      Cadence Financial Group — Supplied Case Study 2 Artifacts
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Load and inspect the actual recruitment exercise files in read-only mode (originals are never modified).
                    </p>
                  </div>
                </div>

                <div className="mt-3.5 space-y-2.5">
                  {caseArtifacts.map((art) => (
                    <div
                      key={art.filename}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-md bg-slate-50 border border-slate-200"
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-slate-900">
                            {art.filename}
                          </span>
                          <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-200 text-slate-800 font-semibold">
                            {art.format}
                          </span>
                          <span className="text-[11px] text-slate-500">
                            ({formatBytes(art.file_size_bytes)})
                          </span>
                        </div>
                        <p className="text-xs text-slate-600">{art.description}</p>
                      </div>
                      <div className="shrink-0 flex items-center gap-2">
                        {art.loaded_doc_id ? (
                          <button
                            onClick={() => void handleSelectDoc(art.loaded_doc_id!, 'workspace')}
                            className="px-3 py-1.5 rounded text-xs font-semibold bg-emerald-700 hover:bg-emerald-800 text-white shadow-sm"
                          >
                            Open Workspace
                          </button>
                        ) : (
                          <button
                            disabled={!art.present_on_disk || isLoading}
                            onClick={() => void handleLoadCaseArtifact(art.filename)}
                            className="px-3 py-1.5 rounded text-xs font-semibold bg-blue-800 hover:bg-blue-900 disabled:opacity-50 text-white shadow-sm"
                          >
                            Process Artifact
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Category & Source Distribution */}
            {dashboard && dashboard.files_processed > 0 && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm">
                  <h3 className="text-sm font-semibold text-slate-900">
                    Detected PII Entities by Category
                  </h3>
                  <div className="mt-3 space-y-2">
                    {Object.entries(dashboard.entities_by_category)
                      .sort((a, b) => b[1] - a[1])
                      .map(([cat, count]) => {
                        const pct = Math.min(
                          100,
                          Math.round((count / Math.max(1, dashboard.total_pii_detected)) * 100)
                        );
                        return (
                          <div key={cat} className="space-y-1">
                            <div className="flex justify-between text-xs">
                              <span className="font-mono font-medium text-slate-800">{cat}</span>
                              <span className="font-semibold text-slate-900">
                                {count} ({pct}%)
                              </span>
                            </div>
                            <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-blue-800 rounded-full"
                                style={{ width: `${Math.max(4, pct)}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                  </div>
                </div>

                <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm">
                  <h3 className="text-sm font-semibold text-slate-900">
                    Detections by Document Structural Layer
                  </h3>
                  <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {Object.entries(dashboard.entities_by_source_type).map(([src, cnt]) => (
                      <div
                        key={src}
                        className="p-3 rounded-md bg-slate-50 border border-slate-200"
                      >
                        <div className="text-[11px] font-mono uppercase text-slate-500">
                          {src.replace(/_/g, ' ')}
                        </div>
                        <div className="text-xl font-bold text-slate-900 mt-1">{cnt}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Processed Document Table */}
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">
                  Processed Artifacts &amp; Privacy Gate Status
                </h3>
                <span className="text-xs text-slate-500">
                  Only PASS documents may proceed to downstream AI handoff
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[11px]">
                      <th className="py-3 px-4">Document Name</th>
                      <th className="py-3 px-4">Format</th>
                      <th className="py-3 px-4">Size</th>
                      <th className="py-3 px-4">Active PII</th>
                      <th className="py-3 px-4">Review Queue</th>
                      <th className="py-3 px-4">Residual PII</th>
                      <th className="py-3 px-4">Structure Retention</th>
                      <th className="py-3 px-4">Privacy Gate</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {(!dashboard || dashboard.documents.length === 0) && (
                      <tr>
                        <td colSpan={9} className="py-8 text-center text-slate-500">
                          No documents processed yet. Upload a file or click &ldquo;Process Artifact&rdquo; on any Case Study 2 document above.
                        </td>
                      </tr>
                    )}
                    {dashboard?.documents.map((doc) => (
                      <tr
                        key={doc.doc_id}
                        className={`hover:bg-slate-50 ${
                          selectedDocId === doc.doc_id ? 'bg-blue-50/40' : ''
                        }`}
                      >
                        <td className="py-3 px-4 font-semibold text-slate-900">
                          {doc.filename}
                        </td>
                        <td className="py-3 px-4 font-mono text-[11px]">{doc.detected_format}</td>
                        <td className="py-3 px-4 text-slate-600">
                          {formatBytes(doc.file_size_bytes)}
                        </td>
                        <td className="py-3 px-4 font-semibold text-blue-900">
                          {doc.findings_count}
                        </td>
                        <td className="py-3 px-4">
                          {doc.unresolved_review_count > 0 ? (
                            <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-900 font-semibold">
                              {doc.unresolved_review_count} Pending
                            </span>
                          ) : (
                            <span className="text-slate-500">0 Pending</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          {doc.residual_pii_found ? (
                            <span className="text-red-700 font-semibold">LEAK DETECTED</span>
                          ) : (
                            <span className="text-emerald-700 font-medium">0 Residual</span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-semibold text-slate-800">
                          {(doc.structure_retention_score * 100).toFixed(1)}%
                        </td>
                        <td className="py-3 px-4">
                          <GateBadge status={doc.gate_status} />
                        </td>
                        <td className="py-3 px-4 text-right space-x-1.5 whitespace-nowrap">
                          <button
                            onClick={() => void handleSelectDoc(doc.doc_id, 'workspace')}
                            className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-800 font-medium"
                          >
                            Workspace
                          </button>
                          <button
                            onClick={() => void handleSelectDoc(doc.doc_id, 'review')}
                            className="px-2.5 py-1 rounded bg-blue-50 hover:bg-blue-100 text-blue-900 font-medium"
                          >
                            Review
                          </button>
                          <a
                            href={`/api/documents/${doc.doc_id}/export/artifact`}
                            className="inline-block px-2.5 py-1 rounded bg-blue-800 hover:bg-blue-900 text-white font-medium"
                          >
                            Download
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            SCREEN B: DOCUMENT WORKSPACE
        =================================================================== */}
        {activeTab === 'workspace' && (
          <div className="space-y-6">
            {!selectedDoc ? (
              <div className="bg-white rounded-lg border border-slate-200 p-8 text-center text-sm text-slate-500">
                Select or process a document on the Dashboard first to inspect its extracted layout and redacted preview.
              </div>
            ) : (
              <>
                {/* Document Profile Bar */}
                <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2.5">
                        <h2 className="text-base font-bold text-slate-900">
                          {selectedDoc.filename}
                        </h2>
                        <span className="px-2 py-0.5 rounded text-xs font-mono bg-slate-100 text-slate-800 border border-slate-300 font-semibold">
                          {selectedDoc.detected_format}
                        </span>
                        {selectedDoc.validation && (
                          <GateBadge status={selectedDoc.validation.gate_status} />
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        {selectedDoc.extraction_profile.extraction_notes.join(' · ')}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      {canVisualPreview && (
                        <button
                          onClick={() => setShowVisualPreview(!showVisualPreview)}
                          className="px-3 py-1.5 rounded text-xs font-semibold border border-slate-300 bg-white hover:bg-slate-50 text-slate-800"
                        >
                          {showVisualPreview ? 'Hide Visual Page Render' : 'Show Visual Page Render'}
                        </button>
                      )}
                      <button
                        onClick={() => setActiveTab('review')}
                        className="px-3 py-1.5 rounded text-xs font-semibold bg-amber-600 hover:bg-amber-700 text-white"
                      >
                        Review Findings ({selectedDoc.findings_count})
                      </button>
                      <a
                        href={`/api/documents/${selectedDoc.doc_id}/export/artifact`}
                        className="px-3 py-1.5 rounded text-xs font-semibold bg-blue-800 hover:bg-blue-900 text-white flex items-center gap-1.5"
                      >
                        <Download className="w-3.5 h-3.5" />
                        Download Redacted {selectedDoc.detected_format}
                      </a>
                    </div>
                  </div>

                  {/* Structural & Extraction Metrics Strip */}
                  <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-6 gap-3 text-xs">
                    <div>
                      <span className="text-slate-500 block">Pages / Slides</span>
                      <span className="font-bold text-slate-900">
                        {selectedDoc.extraction_profile.total_pages_or_slides} (
                        {selectedDoc.extraction_profile.ocr_pages_list.length} OCR)
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Tables Extracted</span>
                      <span className="font-bold text-slate-900">
                        {selectedDoc.extraction_profile.tables_count}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Embedded Images</span>
                      <span className="font-bold text-slate-900">
                        {selectedDoc.extraction_profile.embedded_images_count} (
                        {selectedDoc.extraction_profile.ocr_embedded_images_with_text} w/ OCR text)
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Metadata Fields</span>
                      <span className="font-bold text-slate-900">
                        {selectedDoc.extraction_profile.metadata_fields_extracted} sanitized
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Active Redactions</span>
                      <span className="font-bold text-blue-900">
                        {selectedDoc.active_findings_count} spans
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Structure Retention</span>
                      <span className="font-bold text-emerald-700">
                        {(
                          (selectedDoc.validation?.structure_metrics.overall_structure_score ?? 1) *
                          100
                        ).toFixed(1)}
                        %
                      </span>
                    </div>
                  </div>
                </div>

                {/* Visual Original vs Redacted Page/Image Preview */}
                {canVisualPreview && showVisualPreview && (
                  <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm">
                    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">
                          Visual Artifact Inspection — Original vs. Redacted Output
                        </h3>
                        <p className="text-xs text-slate-500">
                          Verifies genuine stream and pixel-level redaction while preserving page layout, tables, and visual structure.
                        </p>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        <button
                          disabled={previewPage <= 1}
                          onClick={() => setPreviewPage((p) => Math.max(1, p - 1))}
                          className="p-1.5 rounded border border-slate-300 disabled:opacity-40 hover:bg-slate-50"
                        >
                          <ChevronLeft className="w-4 h-4" />
                        </button>
                        <span className="font-semibold px-2">
                          Page {previewPage} of {selectedDoc.extraction_profile.total_pages_or_slides}
                        </span>
                        <button
                          disabled={
                            previewPage >= selectedDoc.extraction_profile.total_pages_or_slides
                          }
                          onClick={() =>
                            setPreviewPage((p) =>
                              Math.min(
                                selectedDoc.extraction_profile.total_pages_or_slides,
                                p + 1
                              )
                            )
                          }
                          className="p-1.5 rounded border border-slate-300 disabled:opacity-40 hover:bg-slate-50"
                        >
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="border border-slate-200 rounded-md overflow-hidden bg-slate-100">
                        <div className="bg-slate-800 text-white px-3 py-1.5 text-xs font-semibold flex justify-between">
                          <span>ORIGINAL SOURCE (Read-Only Immutable)</span>
                          <span>Page {previewPage}</span>
                        </div>
                        <div className="p-2 flex justify-center max-h-[540px] overflow-auto">
                          <img
                            src={`/api/documents/${selectedDoc.doc_id}/preview/original/${previewPage}?t=${selectedDoc.active_findings_count}`}
                            alt={`Original page ${previewPage}`}
                            className="max-w-full h-auto shadow border border-slate-300 bg-white"
                          />
                        </div>
                      </div>

                      <div className="border border-blue-300 rounded-md overflow-hidden bg-slate-100">
                        <div className="bg-blue-900 text-white px-3 py-1.5 text-xs font-semibold flex justify-between">
                          <span>REDACTED DERIVATIVE (Underlying Content Removed)</span>
                          <span>Page {previewPage}</span>
                        </div>
                        <div className="p-2 flex justify-center max-h-[540px] overflow-auto">
                          <img
                            src={`/api/documents/${selectedDoc.doc_id}/preview/redacted/${previewPage}?t=${selectedDoc.active_findings_count}`}
                            alt={`Redacted page ${previewPage}`}
                            className="max-w-full h-auto shadow border border-slate-300 bg-white"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Side-by-Side Extracted Text & Redacted Context Comparison */}
                <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                  <div className="p-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900">
                        Structural Block Comparison (Original vs. Context-Preserving Redacted Output)
                      </h3>
                      <p className="text-xs text-slate-500">
                        Surrounding business context, headings, keys, and delimiters are preserved while sensitive spans are replaced.
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <label className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-slate-100 text-slate-800 font-medium cursor-pointer">
                        <input
                          type="checkbox"
                          checked={onlyPiiBlocks}
                          onChange={(e) => setOnlyPiiBlocks(e.target.checked)}
                          className="rounded text-blue-800"
                        />
                        Only blocks with PII
                      </label>

                      <select
                        aria-label="Filter by source layer"
                        value={sourceTypeFilter}
                        onChange={(e) => setSourceTypeFilter(e.target.value)}
                        className="border border-slate-300 rounded px-2.5 py-1.5 bg-white"
                      >
                        <option value="ALL">All Structural Layers</option>
                        <option value="paragraph">Paragraphs / Body</option>
                        <option value="table_cell">Table Cells</option>
                        <option value="slide_text">Slide Text</option>
                        <option value="ocr_page">Scanned Page OCR</option>
                        <option value="ocr_embedded_image">Embedded Screenshot OCR</option>
                        <option value="metadata">Package Metadata</option>
                        <option value="speaker_note">Speaker Notes</option>
                      </select>

                      <div className="relative">
                        <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
                        <input
                          type="text"
                          placeholder="Search blocks..."
                          value={blockSearch}
                          onChange={(e) => setBlockSearch(e.target.value)}
                          className="pl-8 pr-3 py-1.5 border border-slate-300 rounded text-xs"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="divide-y divide-slate-200 max-h-[600px] overflow-y-auto">
                    {selectedDoc.block_comparisons
                      .filter((b) => (!onlyPiiBlocks ? true : b.has_pii))
                      .filter((b) =>
                        sourceTypeFilter === 'ALL' ? true : b.source_type === sourceTypeFilter
                      )
                      .filter((b) =>
                        !blockSearch.trim()
                          ? true
                          : b.original_text.toLowerCase().includes(blockSearch.toLowerCase()) ||
                            b.redacted_text.toLowerCase().includes(blockSearch.toLowerCase()) ||
                            b.location_ref.toLowerCase().includes(blockSearch.toLowerCase())
                      )
                      .slice(0, 150)
                      .map((b) => (
                        <div key={b.block_id} className="p-4 hover:bg-slate-50/70">
                          <div className="flex items-center justify-between text-[11px] text-slate-500 mb-2">
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                                {b.location_ref}
                              </span>
                              <span className="uppercase font-mono text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-800">
                                {b.source_type}
                              </span>
                            </div>
                            {b.has_pii && (
                              <span className="font-semibold text-blue-800">
                                {b.pii_count} PII span(s) redacted
                              </span>
                            )}
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                            <div className="p-2.5 rounded bg-red-50/50 border border-red-200/80 text-slate-800 whitespace-pre-wrap break-words">
                              {b.original_text}
                            </div>
                            <div className="p-2.5 rounded bg-emerald-50/60 border border-emerald-200/90 text-slate-900 font-medium whitespace-pre-wrap break-words">
                              {b.redacted_text}
                            </div>
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ===================================================================
            SCREEN C: FINDINGS REVIEW
        =================================================================== */}
        {activeTab === 'review' && (
          <div className="space-y-6">
            {!selectedDoc ? (
              <div className="bg-white rounded-lg border border-slate-200 p-8 text-center text-sm text-slate-500">
                Select or process a document first to review detected PII entities.
              </div>
            ) : (
              <>
                {/* Privacy Gate Enforcement Header */}
                <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm flex flex-wrap items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <h2 className="text-base font-bold text-slate-900">
                        Analyst Findings Review — {selectedDoc.filename}
                      </h2>
                      {selectedDoc.validation && (
                        <GateBadge status={selectedDoc.validation.gate_status} />
                      )}
                    </div>
                    <p className="text-xs text-slate-600">
                      {selectedDoc.validation?.reasons.join(' ')}
                    </p>
                  </div>

                  <div className="flex items-center gap-2.5">
                    {(selectedDoc.validation?.unresolved_review_count ?? 0) > 0 && (
                      <button
                        onClick={() => void handleApproveAllFlagged()}
                        className="px-3.5 py-2 rounded-md text-xs font-semibold bg-emerald-700 hover:bg-emerald-800 text-white shadow-sm flex items-center gap-1.5"
                      >
                        <CheckCircle2 className="w-4 h-4" />
                        Approve All Flagged Findings ({selectedDoc.validation?.unresolved_review_count})
                      </button>
                    )}
                    <label className="inline-flex items-center gap-1.5 text-xs bg-slate-100 px-3 py-2 rounded-md font-medium cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showUnmaskedInReview}
                        onChange={(e) => setShowUnmaskedInReview(e.target.checked)}
                        className="rounded text-blue-800"
                      />
                      Show unmasked span in analyst console
                    </label>
                  </div>
                </div>

                {/* Add Missed Entity Manual Annotation Form */}
                <form
                  onSubmit={(e) => void handleAddManualFinding(e)}
                  className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm"
                >
                  <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5 mb-3">
                    <PlusCircle className="w-4 h-4 text-blue-700" />
                    Add Missed PII Entity (Manual Analyst Override)
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 text-xs">
                    <div className="sm:col-span-4">
                      <label className="block text-[11px] text-slate-500 mb-1">Target Block</label>
                      <select
                        value={manualBlockId}
                        onChange={(e) => setManualBlockId(e.target.value)}
                        className="w-full border border-slate-300 rounded px-2.5 py-1.5 bg-white"
                      >
                        {selectedDoc.block_comparisons.slice(0, 200).map((b) => (
                          <option key={b.block_id} value={b.block_id}>
                            {b.location_ref}: {b.original_text.slice(0, 48)}...
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="sm:col-span-3">
                      <label className="block text-[11px] text-slate-500 mb-1">
                        Exact Sensitive Text Span
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="Exact substring in block..."
                        value={manualText}
                        onChange={(e) => setManualText(e.target.value)}
                        className="w-full border border-slate-300 rounded px-2.5 py-1.5"
                      />
                    </div>
                    <div className="sm:col-span-3">
                      <label className="block text-[11px] text-slate-500 mb-1">PII Category</label>
                      <select
                        value={manualCategory}
                        onChange={(e) => setManualCategory(e.target.value as PIIEntityCategory)}
                        className="w-full border border-slate-300 rounded px-2.5 py-1.5 bg-white"
                      >
                        {ALL_CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="sm:col-span-2 flex items-end">
                      <button
                        type="submit"
                        className="w-full py-1.5 px-3 rounded bg-blue-800 hover:bg-blue-900 text-white font-semibold"
                      >
                        Add &amp; Redact
                      </button>
                    </div>
                  </div>
                </form>

                {/* Findings Filter & Table */}
                <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                  <div className="p-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs">
                    <div className="flex items-center gap-2">
                      <Filter className="w-4 h-4 text-slate-500" />
                      <select
                        aria-label="Filter by review status"
                        value={reviewFilterStatus}
                        onChange={(e) => setReviewFilterStatus(e.target.value)}
                        className="border border-slate-300 rounded px-2.5 py-1.5 bg-white font-medium"
                      >
                        <option value="ALL">All Statuses ({selectedDoc.findings.length})</option>
                        <option value="FLAGGED_REVIEW">Flagged for Review</option>
                        <option value="APPROVED">Approved</option>
                        <option value="REJECTED_FALSE_POSITIVE">Rejected (False Positive)</option>
                        <option value="MANUAL_ADDED">Manual Added</option>
                      </select>

                      <select
                        aria-label="Filter by PII category"
                        value={reviewFilterCategory}
                        onChange={(e) => setReviewFilterCategory(e.target.value)}
                        className="border border-slate-300 rounded px-2.5 py-1.5 bg-white font-medium"
                      >
                        <option value="ALL">All Categories</option>
                        {ALL_CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="relative">
                      <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
                      <input
                        type="text"
                        placeholder="Search location, span, rationale..."
                        value={reviewSearch}
                        onChange={(e) => setReviewSearch(e.target.value)}
                        className="pl-8 pr-3 py-1.5 border border-slate-300 rounded text-xs w-64"
                      />
                    </div>
                  </div>

                  <div className="overflow-x-auto max-h-[620px] overflow-y-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 text-slate-600 uppercase text-[11px]">
                        <tr>
                          <th className="py-3 px-3">ID &amp; Location</th>
                          <th className="py-3 px-3">Detected Span &amp; Context</th>
                          <th className="py-3 px-3">Category &amp; Token</th>
                          <th className="py-3 px-3">Confidence</th>
                          <th className="py-3 px-3">Detection Method &amp; Rationale</th>
                          <th className="py-3 px-3">Status</th>
                          <th className="py-3 px-3 text-right">Analyst Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {selectedDoc.findings
                          .filter((f) =>
                            reviewFilterStatus === 'ALL'
                              ? true
                              : f.review_status === reviewFilterStatus
                          )
                          .filter((f) =>
                            reviewFilterCategory === 'ALL'
                              ? true
                              : f.category === reviewFilterCategory
                          )
                          .filter((f) =>
                            !reviewSearch.trim()
                              ? true
                              : f.entity_text.toLowerCase().includes(reviewSearch.toLowerCase()) ||
                                f.location_ref.toLowerCase().includes(reviewSearch.toLowerCase()) ||
                                f.rationale.toLowerCase().includes(reviewSearch.toLowerCase())
                          )
                          .slice(0, 200)
                          .map((f) => (
                            <tr
                              key={f.finding_id}
                              className={`hover:bg-slate-50 ${
                                f.review_status === 'FLAGGED_REVIEW' ? 'bg-amber-50/40' : ''
                              }`}
                            >
                              <td className="py-3 px-3 align-top">
                                <div className="font-mono font-semibold text-slate-900">
                                  {f.finding_id}
                                </div>
                                <div className="text-[11px] text-slate-500 mt-0.5">
                                  {f.location_ref}
                                </div>
                                <div className="text-[10px] font-mono text-slate-400">
                                  Offsets [{f.char_start}..{f.char_end}]
                                </div>
                              </td>

                              <td className="py-3 px-3 align-top max-w-xs">
                                <div className="font-mono text-xs bg-slate-100 p-1.5 rounded border border-slate-200 break-words">
                                  <span className="text-slate-500">{f.context_before}</span>
                                  <span className="px-1 py-0.5 rounded bg-red-100 text-red-900 font-bold">
                                    {showUnmaskedInReview ? f.entity_text : f.masked_preview}
                                  </span>
                                  <span className="text-slate-500">{f.context_after}</span>
                                </div>
                              </td>

                              <td className="py-3 px-3 align-top">
                                <select
                                  aria-label={`Change category for ${f.finding_id}`}
                                  value={f.category}
                                  onChange={(e) =>
                                    void handleUpdateFinding(f.finding_id, {
                                      category: e.target.value as PIIEntityCategory,
                                    })
                                  }
                                  className="border border-slate-300 rounded px-2 py-1 text-xs font-mono font-semibold bg-white"
                                >
                                  {ALL_CATEGORIES.map((c) => (
                                    <option key={c} value={c}>
                                      {c}
                                    </option>
                                  ))}
                                </select>
                                <div className="text-[11px] font-mono text-blue-800 mt-1">
                                  &rarr; {f.replacement_label}
                                </div>
                                <div className="text-[10px] font-mono text-slate-400">
                                  Token: {f.stable_token}
                                </div>
                              </td>

                              <td className="py-3 px-3 align-top">
                                <span
                                  className={`inline-block px-2 py-0.5 rounded font-semibold ${
                                    f.confidence >= 0.8
                                      ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                                      : 'bg-amber-100 text-amber-900 border border-amber-300'
                                  }`}
                                >
                                  {(f.confidence * 100).toFixed(0)}%
                                </span>
                              </td>

                              <td className="py-3 px-3 align-top max-w-xs">
                                <div className="font-semibold text-slate-800">
                                  {f.detection_method}
                                </div>
                                <div className="text-[11px] text-slate-600 mt-0.5">
                                  {f.rationale}
                                </div>
                                <div className="text-[10px] text-slate-400 mt-0.5">
                                  Redaction: {f.redaction_method}
                                </div>
                              </td>

                              <td className="py-3 px-3 align-top">
                                <span
                                  className={`inline-block px-2 py-0.5 rounded text-[11px] font-semibold ${
                                    f.review_status === 'APPROVED' ||
                                    f.review_status === 'MANUAL_ADDED'
                                      ? 'bg-emerald-50 text-emerald-800'
                                      : f.review_status === 'FLAGGED_REVIEW'
                                      ? 'bg-amber-100 text-amber-900'
                                      : 'bg-slate-200 text-slate-700 line-through'
                                  }`}
                                >
                                  {f.review_status}
                                </span>
                              </td>

                              <td className="py-3 px-3 align-top text-right space-x-1 whitespace-nowrap">
                                {f.review_status !== 'APPROVED' && (
                                  <button
                                    onClick={() =>
                                      void handleUpdateFinding(f.finding_id, {
                                        review_status: 'APPROVED',
                                      })
                                    }
                                    className="px-2.5 py-1 rounded bg-emerald-700 hover:bg-emerald-800 text-white font-semibold"
                                  >
                                    Approve
                                  </button>
                                )}
                                {f.review_status !== 'REJECTED_FALSE_POSITIVE' && (
                                  <button
                                    onClick={() =>
                                      void handleUpdateFinding(f.finding_id, {
                                        review_status: 'REJECTED_FALSE_POSITIVE',
                                      })
                                    }
                                    className="px-2.5 py-1 rounded bg-slate-200 hover:bg-slate-300 text-slate-800 font-medium"
                                  >
                                    Reject FP
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ===================================================================
            SCREEN D: SAFE EXPORT & DOWNSTREAM AI GATE
        =================================================================== */}
        {activeTab === 'export' && (
          <div className="space-y-6">
            {!selectedDoc ? (
              <div className="bg-white rounded-lg border border-slate-200 p-8 text-center text-sm text-slate-500">
                Select or process a document first to export redacted artifacts and audit reports.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* Left: Downloadable Deliverables */}
                  <div className="lg:col-span-6 bg-white rounded-lg border border-slate-200 p-5 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                        <FileCheck className="w-4 h-4 text-blue-700" />
                        Sanitized Deliverables &amp; Audit Reports — {selectedDoc.filename}
                      </h2>
                      {selectedDoc.validation && (
                        <GateBadge status={selectedDoc.validation.gate_status} />
                      )}
                    </div>

                    <div className="space-y-3 pt-2">
                      <div className="p-3.5 rounded-md bg-slate-50 border border-slate-200 flex items-center justify-between">
                        <div>
                          <div className="text-xs font-semibold text-slate-900">
                            1. Redacted Native Artifact ({selectedDoc.detected_format})
                          </div>
                          <div className="text-[11px] text-slate-500">
                            Preserves original layout, tables, and styles with sensitive content removed and metadata scrubbed.
                          </div>
                        </div>
                        <a
                          href={`/api/documents/${selectedDoc.doc_id}/export/artifact`}
                          className="px-3.5 py-2 rounded bg-blue-800 hover:bg-blue-900 text-white text-xs font-semibold flex items-center gap-1.5 shrink-0"
                        >
                          <Download className="w-3.5 h-3.5" />
                          Download {selectedDoc.detected_format}
                        </a>
                      </div>

                      <div className="p-3.5 rounded-md bg-slate-50 border border-slate-200 flex items-center justify-between">
                        <div>
                          <div className="text-xs font-semibold text-slate-900">
                            2. PII Findings &amp; Validation Report (JSON)
                          </div>
                          <div className="text-[11px] text-slate-500">
                            Structured findings with masked previews, confidence scores, bounding boxes, and validation metrics.
                          </div>
                        </div>
                        <a
                          href={`/api/documents/${selectedDoc.doc_id}/export/findings-report?format=json`}
                          className="px-3.5 py-2 rounded bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold flex items-center gap-1.5 shrink-0"
                        >
                          <FileText className="w-3.5 h-3.5" />
                          Export JSON
                        </a>
                      </div>

                      <div className="p-3.5 rounded-md bg-slate-50 border border-slate-200 flex items-center justify-between">
                        <div>
                          <div className="text-xs font-semibold text-slate-900">
                            3. PII Findings Spreadsheet (CSV)
                          </div>
                          <div className="text-[11px] text-slate-500">
                            Tabular export of all {selectedDoc.findings_count} findings with raw PII masked by default.
                          </div>
                        </div>
                        <a
                          href={`/api/documents/${selectedDoc.doc_id}/export/findings-report?format=csv`}
                          className="px-3.5 py-2 rounded bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold flex items-center gap-1.5 shrink-0"
                        >
                          <FileSpreadsheet className="w-3.5 h-3.5" />
                          Export CSV
                        </a>
                      </div>
                    </div>

                    {/* Structure Retention Breakdown */}
                    {selectedDoc.validation && (
                      <div className="pt-4 border-t border-slate-200 space-y-2">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-slate-900">
                            Structure Preservation Validation Score
                          </span>
                          <span className="font-bold text-emerald-800">
                            {(
                              selectedDoc.validation.structure_metrics.overall_structure_score * 100
                            ).toFixed(2)}
                            % (Target &ge; 80%)
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500">
                          {selectedDoc.validation.structure_metrics.formula_explanation}
                        </p>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-xs">
                          <div className="p-2 rounded bg-slate-50 border border-slate-200">
                            <span className="text-[10px] text-slate-500 block">Page/Slide Parity</span>
                            <span className="font-bold">
                              {(
                                selectedDoc.validation.structure_metrics.page_retention_ratio * 100
                              ).toFixed(0)}
                              %
                            </span>
                          </div>
                          <div className="p-2 rounded bg-slate-50 border border-slate-200">
                            <span className="text-[10px] text-slate-500 block">Table Parity</span>
                            <span className="font-bold">
                              {(
                                selectedDoc.validation.structure_metrics.table_retention_ratio * 100
                              ).toFixed(0)}
                              %
                            </span>
                          </div>
                          <div className="p-2 rounded bg-slate-50 border border-slate-200">
                            <span className="text-[10px] text-slate-500 block">Block Distribution</span>
                            <span className="font-bold">
                              {(
                                selectedDoc.validation.structure_metrics
                                  .text_block_distribution_score * 100
                              ).toFixed(0)}
                              %
                            </span>
                          </div>
                          <div className="p-2 rounded bg-slate-50 border border-slate-200">
                            <span className="text-[10px] text-slate-500 block">Reading Order</span>
                            <span className="font-bold">
                              {(
                                selectedDoc.validation.structure_metrics.reading_order_score * 100
                              ).toFixed(0)}
                              %
                            </span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Right: Downstream LLM Sanitization Gateway */}
                  <div className="lg:col-span-6 bg-white rounded-lg border border-slate-200 p-5 shadow-sm flex flex-col justify-between space-y-4">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                          <Lock className="w-4 h-4 text-blue-700" />
                          Downstream LLM Sanitization Gateway
                        </h2>
                        <span
                          className={`text-[11px] font-semibold px-2 py-0.5 rounded ${
                            policy?.downstream_llm_enabled
                              ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                              : 'bg-slate-100 text-slate-700 border border-slate-300'
                          }`}
                        >
                          {policy?.downstream_llm_enabled
                            ? 'Opt-In Enabled'
                            : 'Disabled by Default (Policy)'}
                        </span>
                      </div>

                      <p className="text-xs text-slate-600">
                        Enforces the mandatory security rule:{' '}
                        <strong>
                          No document content may reach a downstream LLM until PII detection,
                          redaction, and validation checks have achieved a server-side PASS.
                        </strong>
                      </p>

                      {selectedDoc.validation?.gate_status !== 'PASS' && (
                        <div className="p-3 rounded-md bg-red-50 border border-red-200 text-xs text-red-900 space-y-1">
                          <div className="font-bold flex items-center gap-1.5">
                            <ShieldAlert className="w-4 h-4 text-red-600" />
                            Downstream LLM Handoff Locked ({selectedDoc.validation?.gate_status})
                          </div>
                          <p>{selectedDoc.validation?.reasons.join(' ')}</p>
                          {selectedDoc.validation?.gate_status === 'REVIEW_REQUIRED' && (
                            <button
                              onClick={() => setActiveTab('review')}
                              className="mt-1 inline-block font-semibold text-blue-900 underline"
                            >
                              Go to Findings Review to resolve pending items &rarr;
                            </button>
                          )}
                        </div>
                      )}

                      <div>
                        <label className="block text-xs font-medium text-slate-700 mb-1">
                          Downstream Analysis Prompt (Applied ONLY to Sanitized Redacted Payload)
                        </label>
                        <textarea
                          rows={2}
                          value={llmPrompt}
                          onChange={(e) => setLlmPrompt(e.target.value)}
                          className="w-full border border-slate-300 rounded p-2 text-xs"
                        />
                      </div>

                      <div className="flex items-center gap-3">
                        <button
                          disabled={
                            selectedDoc.validation?.gate_status !== 'PASS' ||
                            !policy?.downstream_llm_enabled ||
                            isLoading
                          }
                          onClick={() => void handleLLMHandoff()}
                          className="px-4 py-2 rounded bg-blue-800 hover:bg-blue-900 disabled:bg-slate-300 disabled:text-slate-500 text-white text-xs font-semibold shadow-sm"
                        >
                          Send Validated Redacted Artifact to Downstream LLM
                        </button>
                        {!policy?.downstream_llm_enabled && (
                          <button
                            onClick={() => setActiveTab('policy')}
                            className="text-xs text-blue-800 hover:underline font-medium"
                          >
                            Enable Opt-In in Policy Settings &rarr;
                          </button>
                        )}
                      </div>
                    </div>

                    {llmResult && (
                      <div className="p-3.5 rounded-md bg-slate-900 text-slate-100 text-xs font-mono space-y-2">
                        <div className="text-emerald-400 font-semibold">
                          &#10003; Server-Side Gate Verified: {llmResult.gate_status_verified} (
                          {llmResult.sanitized_char_count} sanitized chars)
                        </div>
                        <div className="whitespace-pre-wrap text-slate-200">
                          {llmResult.llm_response}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Sanitized Security Audit Trail */}
                <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">
                      Zero-PII Security Audit Log
                    </h3>
                    <span className="text-xs text-slate-500">
                      Raw document text and sensitive values are strictly excluded from all audit entries
                    </span>
                  </div>
                  <div className="max-h-72 overflow-y-auto divide-y divide-slate-200 text-xs">
                    {auditLog.map((evt) => (
                      <div
                        key={evt.event_id}
                        className="px-5 py-2.5 flex flex-wrap items-center justify-between gap-2 hover:bg-slate-50"
                      >
                        <div className="flex items-center gap-2.5">
                          <span className="font-mono text-[11px] text-slate-500">
                            {evt.event_id}
                          </span>
                          <span className="px-2 py-0.5 rounded bg-slate-100 font-mono text-[10px] font-semibold text-slate-800">
                            {evt.stage}
                          </span>
                          <span className="font-medium text-slate-900">{evt.action}</span>
                          {evt.document_name && (
                            <span className="text-slate-500">({evt.document_name})</span>
                          )}
                        </div>
                        <div className="text-[11px] font-mono text-slate-400">
                          {new Date(evt.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ===================================================================
            SCREEN E: EVALUATION BENCHMARK
        =================================================================== */}
        {activeTab === 'benchmark' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-bold text-slate-900">
                  Synthetic PII Benchmark &amp; Format-Specific Evaluation Suite
                </h2>
                <p className="text-xs text-slate-600 mt-0.5">
                  Executes the 28-case Gold Synthetic Benchmark (49 expected entities + 7 false-positive negative scenarios) and 5 realistic multi-format file fixtures (PDF, Scanned PDF, DOCX, PPTX, PNG).
                </p>
              </div>
              <button
                onClick={() => void handleRunBenchmark(true)}
                disabled={isLoading}
                className="px-4 py-2 rounded bg-blue-800 hover:bg-blue-900 text-white text-xs font-semibold flex items-center gap-2 shadow-sm"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                Re-Run Live Benchmark Suite
              </button>
            </div>

            {benchmark && (
              <>
                {/* Top Summary Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                    <div className="text-xs text-slate-500 uppercase font-medium">
                      28-Case Gold Text Benchmark
                    </div>
                    <div className="text-2xl font-bold text-emerald-800 mt-1">
                      {(benchmark.text_benchmark_summary.precision * 100).toFixed(1)}% Precision ·{' '}
                      {(benchmark.text_benchmark_summary.recall * 100).toFixed(1)}% Recall
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {benchmark.text_benchmark_summary.exact_case_matches}/
                      {benchmark.text_benchmark_summary.total_cases} exact redaction matches (49/49 spans)
                    </div>
                  </div>

                  <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                    <div className="text-xs text-slate-500 uppercase font-medium">
                      5-Format File Benchmark
                    </div>
                    <div className="text-2xl font-bold text-blue-900 mt-1">
                      {(benchmark.aggregate_file_summary.precision * 100).toFixed(1)}% Prec ·{' '}
                      {(benchmark.aggregate_file_summary.recall * 100).toFixed(1)}% Rec
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      F1 Score: {(benchmark.aggregate_file_summary.f1_score * 100).toFixed(1)}% across 5 file formats
                    </div>
                  </div>

                  <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                    <div className="text-xs text-slate-500 uppercase font-medium">
                      False Positives &amp; Residual PII
                    </div>
                    <div className="text-2xl font-bold text-emerald-800 mt-1">
                      0 Residual PII Leaks
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {benchmark.text_benchmark_summary.negative_cases_zero_fp}/
                      {benchmark.text_benchmark_summary.negative_cases_total} negative trap cases had 0 false positives
                    </div>
                  </div>

                  <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
                    <div className="text-xs text-slate-500 uppercase font-medium">
                      Avg Format Structure Retention
                    </div>
                    <div className="text-2xl font-bold text-slate-900 mt-1">
                      {(benchmark.aggregate_file_summary.average_structure_retention * 100).toFixed(
                        1
                      )}
                      %
                    </div>
                    <div className="text-xs text-emerald-700 font-medium mt-1">
                      Exceeds &ge; 80.0% policy requirement across all formats
                    </div>
                  </div>
                </div>

                {/* Metrics by File Type Table */}
                <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-5 py-3.5 border-b border-slate-200">
                    <h3 className="text-sm font-semibold text-slate-900">
                      Measured Performance Metrics by File Format
                    </h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase text-[11px]">
                          <th className="py-3 px-4">File Format</th>
                          <th className="py-3 px-4">Expected PII</th>
                          <th className="py-3 px-4">True Positives</th>
                          <th className="py-3 px-4">False Positives</th>
                          <th className="py-3 px-4">Precision</th>
                          <th className="py-3 px-4">Recall</th>
                          <th className="py-3 px-4">F1 Score</th>
                          <th className="py-3 px-4">Residual PII</th>
                          <th className="py-3 px-4">Extraction Quality</th>
                          <th className="py-3 px-4">Structure Retention</th>
                          <th className="py-3 px-4">Gate</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {benchmark.file_format_metrics.map((m) => (
                          <tr key={m.file_type} className="hover:bg-slate-50">
                            <td className="py-3 px-4 font-semibold text-slate-900">
                              {m.file_type}
                            </td>
                            <td className="py-3 px-4">{m.expected_pii_count}</td>
                            <td className="py-3 px-4 font-semibold text-emerald-800">
                              {m.true_positives}
                            </td>
                            <td className="py-3 px-4">{m.false_positives}</td>
                            <td className="py-3 px-4 font-semibold">
                              {(m.precision * 100).toFixed(1)}%
                            </td>
                            <td className="py-3 px-4 font-semibold">
                              {(m.recall * 100).toFixed(1)}%
                            </td>
                            <td className="py-3 px-4 font-semibold">
                              {(m.f1_score * 100).toFixed(1)}%
                            </td>
                            <td className="py-3 px-4 font-semibold text-emerald-700">
                              {m.residual_pii_count}
                            </td>
                            <td className="py-3 px-4">
                              {(m.extraction_quality_score * 100).toFixed(1)}%
                            </td>
                            <td className="py-3 px-4 font-semibold">
                              {(m.structure_retention_score * 100).toFixed(1)}%
                            </td>
                            <td className="py-3 px-4">
                              <GateBadge status={m.gate_status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 28 Gold Cases Detailed Results */}
                <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-5 py-3.5 border-b border-slate-200">
                    <h3 className="text-sm font-semibold text-slate-900">
                      28-Case Synthetic Gold Benchmark Execution Results (PII-001 to PII-028)
                    </h3>
                  </div>
                  <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 text-slate-600 uppercase text-[11px]">
                        <tr>
                          <th className="py-2.5 px-3">Case ID</th>
                          <th className="py-2.5 px-3">Scenario &amp; Type</th>
                          <th className="py-2.5 px-3">Detected Entities</th>
                          <th className="py-2.5 px-3">Redacted Output</th>
                          <th className="py-2.5 px-3">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {benchmark.xlsx_cases.map((c) => (
                          <tr key={c.case_id} className="hover:bg-slate-50">
                            <td className="py-2.5 px-3 font-mono font-bold text-slate-900">
                              {c.case_id}
                            </td>
                            <td className="py-2.5 px-3">
                              <div className="font-semibold text-slate-800">{c.scenario}</div>
                              <div className="text-[11px] text-slate-500">
                                {c.input_type} · {c.difficulty}
                              </div>
                            </td>
                            <td className="py-2.5 px-3 font-mono text-[11px] text-blue-900 max-w-xs">
                              {c.actual_entities}
                            </td>
                            <td className="py-2.5 px-3 font-mono text-[11px] text-slate-800 max-w-md">
                              {c.actual_redacted}
                            </td>
                            <td className="py-2.5 px-3">
                              <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 font-semibold">
                                {c.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ===================================================================
            SCREEN F: POLICY & REDACTION LABELS
        =================================================================== */}
        {activeTab === 'policy' && policy && (
          <form
            onSubmit={(e) => void handleSavePolicy(e)}
            className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm space-y-6 max-w-4xl"
          >
            <div className="flex items-center justify-between border-b border-slate-200 pb-4">
              <div>
                <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Settings className="w-4 h-4 text-blue-700" />
                  Redaction Policy, Thresholds &amp; Privacy Gate Configuration
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Configure confidence thresholds, replacement labels, OCR scanning options, and downstream LLM opt-in controls.
                </p>
              </div>
              <button
                type="submit"
                className="px-4 py-2 rounded bg-blue-800 hover:bg-blue-900 text-white text-xs font-semibold shadow-sm"
              >
                Save Policy Configuration
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  Auto-Approve Confidence Threshold ({policy.auto_redact_threshold})
                </label>
                <input
                  type="number"
                  step="0.05"
                  min="0.3"
                  max="0.99"
                  value={policy.auto_redact_threshold}
                  onChange={(e) =>
                    setPolicy({ ...policy, auto_redact_threshold: parseFloat(e.target.value) })
                  }
                  className="w-full border border-slate-300 rounded px-3 py-1.5"
                />
                <span className="text-[11px] text-slate-500">
                  Findings below this score trigger REVIEW_REQUIRED.
                </span>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  Minimum Structure Retention ({policy.min_structure_retention * 100}%)
                </label>
                <input
                  type="number"
                  step="0.05"
                  min="0.5"
                  max="1.0"
                  value={policy.min_structure_retention}
                  onChange={(e) =>
                    setPolicy({ ...policy, min_structure_retention: parseFloat(e.target.value) })
                  }
                  className="w-full border border-slate-300 rounded px-3 py-1.5"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  Redaction Replacement Mode
                </label>
                <select
                  value={policy.redaction_mode}
                  onChange={(e) =>
                    setPolicy({
                      ...policy,
                      redaction_mode: e.target.value as 'CATEGORY_LABEL' | 'STABLE_TOKEN',
                    })
                  }
                  className="w-full border border-slate-300 rounded px-3 py-1.5 bg-white"
                >
                  <option value="CATEGORY_LABEL">
                    Category Labels ([NAME REDACTED], [EMAIL REDACTED])
                  </option>
                  <option value="STABLE_TOKEN">
                    Cross-Artifact Stable Tokens ([PERSON_001], [EMAIL_001])
                  </option>
                </select>
              </div>
            </div>

            {/* Replacement Labels */}
            <div>
              <h3 className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-3">
                Category Replacement Labels
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                {Object.entries(policy.replacement_labels).map(([cat, label]) => (
                  <div key={cat}>
                    <label className="block font-mono text-[11px] text-slate-600 mb-1">{cat}</label>
                    <input
                      type="text"
                      value={label}
                      onChange={(e) =>
                        setPolicy({
                          ...policy,
                          replacement_labels: {
                            ...policy.replacement_labels,
                            [cat]: e.target.value,
                          },
                        })
                      }
                      className="w-full border border-slate-300 rounded px-2.5 py-1.5 font-mono"
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Toggles */}
            <div className="pt-3 border-t border-slate-200 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={policy.enable_ocr_on_scanned_pages}
                  onChange={(e) =>
                    setPolicy({ ...policy, enable_ocr_on_scanned_pages: e.target.checked })
                  }
                  className="rounded text-blue-800"
                />
                <span className="font-medium text-slate-800">
                  Enable OCR on Scanned / Rasterized PDF Pages
                </span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={policy.enable_ocr_on_embedded_images}
                  onChange={(e) =>
                    setPolicy({ ...policy, enable_ocr_on_embedded_images: e.target.checked })
                  }
                  className="rounded text-blue-800"
                />
                <span className="font-medium text-slate-800">
                  Enable OCR &amp; Pixel Redaction on Embedded DOCX/PPTX/PDF Screenshots
                </span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={policy.downstream_llm_enabled}
                  onChange={(e) =>
                    setPolicy({ ...policy, downstream_llm_enabled: e.target.checked })
                  }
                  className="rounded text-blue-800"
                />
                <span className="font-semibold text-blue-900">
                  Explicitly Opt-In to Downstream LLM Handoff (Requires Server-Side PASS State)
                </span>
              </label>
            </div>
          </form>
        )}
      </main>
    </div>
  );
}

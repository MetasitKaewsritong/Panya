export const formatTimeAgo = (timestamp) => {
  if (!timestamp) return '';
  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now - time;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay === 1) return 'yesterday';
  if (diffDay < 7) return `${diffDay}d ago`;
  return time.toLocaleDateString();
};

export const DEFAULT_COLLECTION = 'plcnext';

export const getApiBaseUrl = () => {
  const configured = String(import.meta.env.VITE_API_URL || '').trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  if (typeof window === 'undefined') {
    return '';
  }
  return `${window.location.protocol}//${window.location.hostname}:5000`;
};

export const buildDocumentViewerUrl = ({ sourceId, source, collection, page } = {}) => {
  const resolvedSourceId = String(sourceId || '').trim();
  const resolvedSource = String(source || '').trim();

  if (!resolvedSourceId && !resolvedSource) {
    return null;
  }

  const params = new URLSearchParams();
  if (resolvedSourceId) {
    params.set('source_id', resolvedSourceId);
  }
  if (resolvedSource) {
    params.set('source', resolvedSource);
  }

  params.set('collection', String(collection || DEFAULT_COLLECTION));

  const normalizedPage = Number(page);
  if (Number.isFinite(normalizedPage) && normalizedPage > 0) {
    params.set('page', String(Math.round(normalizedPage)));
  }

  return `${getApiBaseUrl()}/api/document-pages/view?${params.toString()}`;
};

export const formatTime = (timestamp) => {
  if (!timestamp) return '';
  const time = new Date(timestamp);
  return time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

export const fixMarkdownTable = (text) => {
  if (!text || !text.includes('|')) return text;

  const lines = text.split('\n');
  const fixedLines = [];
  
  for (const line of lines) {
    if (line.includes('| ---') && line.split('|').length > 8) {
      const parts = line.split('|').map(p => p.trim()).filter(p => p);
      const sepIndices = [];
      parts.forEach((p, i) => {
        if (/^-+$/.test(p)) sepIndices.push(i);
      });
      
      if (sepIndices.length > 0) {
        const numCols = sepIndices[0];
        if (numCols > 0) {
          const rows = [];
          for (let i = 0; i < parts.length; i += numCols) {
            const rowParts = parts.slice(i, i + numCols);
            if (rowParts.length === numCols) {
              rows.push('| ' + rowParts.join(' | ') + ' |');
            }
          }
          if (rows.length > 0) {
            fixedLines.push(rows.join('\n'));
            continue;
          }
        }
      }
    }
    fixedLines.push(line);
  }
  return fixedLines.join('\n');
};

export const stripQualityMetrics = (text) => {
  if (!text) return text;

  const lines = String(text).split('\n');
  const result = [];
  let skipSection = false;

  const isHorizontalRule = (line) => {
    const trimmed = line.trim();
    return trimmed === '---' || trimmed === '***' || trimmed === '___';
  };

  const markers = [
    'response quality metrics',
    '📊 response quality metrics',
    'overall quality',
    'answer relevancy',
    'answer match',
    'faithfulness',
    'context precision',
    'context recall',
    'referenced documents',
    '📚 referenced documents'
  ];

  for (const line of lines) {
    const lower = line.toLowerCase();

    if (markers.some(marker => lower.includes(marker))) {
      if (result.length > 0 && isHorizontalRule(result[result.length - 1])) {
        result.pop();
      }
      skipSection = true;
      continue;
    }

    if (skipSection) {
      const isMetricLine = markers.some(marker => lower.includes(marker))
        || lower.includes('%')
        || lower.includes('.pdf')
        || lower.includes('pages')
        || line.trim().startsWith('•')
        || line.trim().startsWith('-')
        || isHorizontalRule(line);

      if (isMetricLine || line.trim() === '') {
        continue;
      }
      skipSection = false;
    }
    result.push(line);
  }
  return result.join('\n');
};

export const RAGAS_METRIC_KEYS = [
  "faithfulness",
  "answer_relevancy",
  "answer_match",
  "context_precision",
  "context_recall",
];

export const RAGAS_METRIC_LABELS = {
  faithfulness: "Faithfulness",
  answer_relevancy: "Answer Relevancy",
  answer_match: "Answer Match",
  context_precision: "Context Precision",
  context_recall: "Context Recall",
};

export const formatRagasMetric = (value) => {
  if (value === null || value === undefined) return "N/A";
  const num = Number(value);
  if (Number.isNaN(num)) return "N/A";
  return `${(num * 100).toFixed(1)}%`;
};

export const formatSeconds = (value) => {
  if (value === null || value === undefined) return "N/A";
  const num = Number(value);
  if (Number.isNaN(num)) return "N/A";
  return `${num.toFixed(num >= 10 ? 1 : 2)}s`;
};

export const toPositivePageNumber = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return null;
  return Math.round(num);
};

export const formatResponseMode = (mode) => {
  const value = String(mode || "").toLowerCase();
  if (value === "vision") return "Vision";
  if (value === "text") return "Text";
  return null;
};

export const formatIntentLabel = (value) => {
  if (!value) return null;
  return String(value)
    .split("_")
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

export const formatIntentSourceLabel = (value) => {
  const normalized = String(value || "").toLowerCase();
  if (!normalized) return null;
  if (normalized === "intent_llm_structured") return "Parsed Scope";
  if (normalized.startsWith("fallback")) return "Fallback Scope";
  return formatIntentLabel(value) || value;
};

export const formatModelLabel = (value) => {
  if (!value) return null;
  return String(value)
    .replace(/\s+User'?s Manual\s*\(Hardware\)\s*$/i, "")
    .replace(/\s+Manual\s*\(Hardware\)\s*$/i, "")
    .trim();
};

export const getIntentSummaryRows = (message) => {
  const details = message?.intentDetails || {};
  const rows = [];

  const brand = details.matched_brand || details.brand;
  const model = formatModelLabel(details.matched_model_subbrand || details.model_input);
  const intent = formatIntentLabel(details.intent);
  const topic = details.topic || "";
  const query = message?.intentQuery || details.normalized_query || "";
  const status = details.status || "";

  if (brand) rows.push({ label: "Brand", value: brand });
  if (model) rows.push({ label: "Model", value: model });
  if (intent) rows.push({ label: "Intent", value: intent });
  if (topic) rows.push({ label: "Topic", value: topic });
  if (query) rows.push({ label: "Search Query", value: query });
  if (status && status !== "ok") {
    rows.push({ label: "Status", value: formatIntentLabel(status) || status });
  }

  return rows;
};

export const getScopeChipRows = (message) => {
  const rows = getIntentSummaryRows(message);
  return rows.filter((row) => ["Brand", "Model", "Intent"].includes(row.label));
};

export const getIntentDetailRows = (message) => {
  const rows = getIntentSummaryRows(message);
  return rows.filter((row) => !["Brand", "Model", "Intent"].includes(row.label));
};

export const shouldShowVisionFallback = (message) => {
  const requested = String(message?.requestedMode || "").toLowerCase();
  const response = String(message?.responseMode || "").toLowerCase();
  return requested === "vision" && response !== "vision" && Boolean(message?.modeFallbackReason);
};

export const getSelectedSourceGroups = (message) => {
  const details = Array.isArray(message?.sourceDetails) ? message.sourceDetails : [];
  const groups = new Map();

  for (const item of details) {
    if (!item) continue;

    const source = item.source || item.source_id || "Unknown document";
    const sourceId = item.source_id || source;
    const collection = item.collection || message?.collection || DEFAULT_COLLECTION;
    const key = `${sourceId}::${item.brand || ""}::${item.model_subbrand || ""}::${collection}`;
    const page = toPositivePageNumber(item.page);
    const score = Number(item.score);
    const existing = groups.get(key) || {
      key,
      source,
      sourceId,
      collection,
      pages: [],
      pageSet: new Set(),
      primaryPage: page,
      score: Number.isFinite(score) ? score : null,
    };

    if (page !== null && !existing.pageSet.has(page)) {
      existing.pageSet.add(page);
      existing.pages.push(page);
      if (existing.primaryPage === null || existing.primaryPage === undefined) {
        existing.primaryPage = page;
      }
    }

    if (Number.isFinite(score) && (existing.score === null || score > existing.score)) {
      existing.score = score;
      if (page !== null) {
        existing.primaryPage = page;
      }
    }

    groups.set(key, existing);
  }

  if (!groups.size) {
    const sources = Array.isArray(message?.sources) ? message.sources : [];
    return [...new Set(sources.filter(Boolean))].map((source) => ({
      key: source,
      source,
      sourceId: source,
      collection: message?.collection || DEFAULT_COLLECTION,
      pages: [],
      primaryPage: 1,
      score: null,
    }));
  }

  return [...groups.values()]
    .map((group) => ({
      key: group.key,
      source: group.source,
      sourceId: group.sourceId,
      collection: group.collection,
      pages: [...group.pages].sort((a, b) => a - b),
      primaryPage: group.primaryPage ?? group.pages[0] ?? 1,
      score: group.score,
    }))
    .sort((a, b) => {
      if (a.score !== null && b.score !== null && a.score !== b.score) {
        return b.score - a.score;
      }
      if (a.score !== null) return -1;
      if (b.score !== null) return 1;
      return a.source.localeCompare(b.source);
    });
};

export const mapServerMessage = (message) => ({
  text: message.content,
  sender: message.role === "user" ? "user" : "bot",
  timestamp: message.created_at,
  collection: message.metadata?.collection || DEFAULT_COLLECTION,
  processingTime: message.metadata?.processing_time,
  retrievalTime: message.metadata?.retrieval_time,
  llmTime: message.metadata?.llm_time,
  contextCount: message.metadata?.context_count ?? null,
  sources: message.metadata?.sources || [],
  sourceDetails: Array.isArray(message.metadata?.source_details) ? message.metadata.source_details : [],
  ragas: message.metadata?.ragas || null,
  ragasStatus: message.metadata?.ragas_status || null,
  responseMode: message.metadata?.response_mode || null,
  requestedMode: message.metadata?.requested_mode || null,
  modeFallbackReason: message.metadata?.mode_fallback_reason || null,
  answerSupportStatus: message.metadata?.answer_support_status || null,
  intentQuery: message.metadata?.intent_query || null,
  intentSource: message.metadata?.intent_source || null,
  intentDetails: message.metadata?.intent_details || null,
});

export const formatModeFallbackReason = (reason) => {
  const value = String(reason || "").toLowerCase();
  if (value === "no_selected_docs") return "No relevant pages were selected.";
  if (value === "no_page_images") return "Page images could not be loaded.";
  if (value === "vision_not_found") return "The vision model could not answer from the pages.";
  if (value === "vision_prepare_error") return "The page-image context could not be prepared.";
  if (value === "vision_invoke_error") return "The vision model request failed.";
  return value ? `Fallback reason: ${value}` : "";
};

export const getModeSummary = (message) => {
  if (String(message?.answerSupportStatus || "").toLowerCase() !== "supported") {
    return null;
  }

  const requested = String(message?.requestedMode || "").toLowerCase();
  const response = String(message?.responseMode || "").toLowerCase();

  if (requested === "vision" && response === "vision") {
    return {
      label: "Used page images",
      tone: "vision",
    };
  }

  if (requested === "vision" && response !== "vision") {
    return {
      label: "Vision fallback",
      tone: "fallback",
    };
  }

  if (response === "text") {
    return {
      label: "Used text context",
      tone: "text",
    };
  }

  return null;
};

export const getModeChipClassName = (tone) => {
  if (tone === "vision") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (tone === "fallback") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
};

export const shouldShowDetails = (message) => {
  return Boolean(
    getIntentDetailRows(message).length ||
    (message?.ragasStatus && message.ragasStatus !== "disabled") ||
    message?.intentSource ||
    shouldShowVisionFallback(message) ||
    getSelectedSourceGroups(message).length ||
    (message?.llmTime !== null && message?.llmTime !== undefined) ||
    (message?.processingTime !== null && message?.processingTime !== undefined)
  );
};

export const getQualitySummary = (message) => {
  if (!message?.ragasStatus || message.ragasStatus === "disabled") return null;
  if (message.ragasStatus === "pending") return "Evaluating answer quality...";
  if (message.ragasStatus === "error") return "Quality evaluation could not be completed.";

  const faithfulness = formatRagasMetric(message.ragas?.faithfulness);
  const relevancy = formatRagasMetric(message.ragas?.answer_relevancy);
  const answerMatch = formatRagasMetric(message.ragas?.answer_match);
  return `Faithfulness ${faithfulness} | Answer relevancy ${relevancy} | Answer match ${answerMatch}`;
};

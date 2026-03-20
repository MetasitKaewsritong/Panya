import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { LoaderCircle, Check, Copy, CornerDownLeft } from 'lucide-react';
import {
  formatTime,
  fixMarkdownTable,
  stripQualityMetrics,
  getModeSummary,
  getModeChipClassName,
  getScopeChipRows,
  shouldShowDetails,
  getQualitySummary,
  getIntentDetailRows,
  formatIntentSourceLabel,
  formatSeconds,
  getSelectedSourceGroups,
  buildDocumentViewerUrl,
  RAGAS_METRIC_KEYS,
  RAGAS_METRIC_LABELS,
  formatRagasMetric,
  shouldShowVisionFallback,
  formatModeFallbackReason,
  formatResponseMode
} from '../../utils/formatters';

export default function MessageBubble({ 
  m, 
  index, 
  copiedMessageId, 
  copyToClipboard, 
  setInput, 
  inputRef 
}) {
  return (
    <div className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[85%] px-5 py-3.5 rounded-2xl shadow-sm text-[15px] leading-relaxed break-words overflow-hidden
          ${m.sender === "user"
            ? "bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-br-sm"
            : "bg-white text-gray-800 border border-gray-100 rounded-bl-sm prose prose-sm max-w-none"
          }`}
        style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
      >
        {m.sender === "bot" ? (
          m.isCancelled ? (
            <span className="text-red-500 font-medium text-sm">{m.text}</span>
          ) : m.isStreaming && !m.text ? (
            <div className="flex items-center gap-3 text-gray-500 text-sm">
              <LoaderCircle size={18} className="animate-spin text-blue-500" />
              <span className="font-medium">
                {String(m.requestedMode || "").toLowerCase() === "vision"
                  ? "Reading selected manual pages..."
                  : "Thinking..."}
              </span>
            </div>
          ) : (
            <ReactMarkdown
              components={{
                code({ inline, className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || '');
                  return !inline && match ? (
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match[1]}
                      PreTag="div"
                      className="rounded-lg text-sm my-2"
                      {...props}
                    >
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  ) : (
                    <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                      {children}
                    </code>
                  );
                },
                p({ children }) {
                  return <p className="mb-2 last:mb-0">{children}</p>;
                },
                ul({ children }) {
                  return <ul className="list-disc ml-4 mb-2">{children}</ul>;
                },
                ol({ children }) {
                  return <ol className="list-decimal ml-4 mb-2">{children}</ol>;
                },
                li({ children }) {
                  return <li className="mb-1">{children}</li>;
                },
                strong({ children }) {
                  return <strong className="font-semibold">{children}</strong>;
                },
                a({ href, children }) {
                  return <a href={href} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">{children}</a>;
                },
                table({ children }) {
                  return (
                    <div className="overflow-x-auto my-3">
                      <table className="min-w-full border-collapse border border-gray-300 text-sm">
                        {children}
                      </table>
                    </div>
                  );
                },
                thead({ children }) {
                  return <thead className="bg-gray-100">{children}</thead>;
                },
                tbody({ children }) {
                  return <tbody>{children}</tbody>;
                },
                tr({ children }) {
                  return <tr className="border-b border-gray-200">{children}</tr>;
                },
                th({ children }) {
                  return (
                    <th className="border border-gray-300 px-3 py-2 text-left font-semibold bg-gray-50">
                      {children}
                    </th>
                  );
                },
                td({ children }) {
                  return (
                    <td className="border border-gray-300 px-3 py-2">
                      {children}
                    </td>
                  );
                },
                hr() {
                  return null;
                }
              }}
            >
              {fixMarkdownTable(stripQualityMetrics(typeof m.text === 'string' ? m.text : String(m.text || '')))}
            </ReactMarkdown>
          )
        ) : (
          m.text
        )}
      </div>

      {m.sender === "bot" && (
        <div className="mt-1 flex max-w-[85%] flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {getModeSummary(m) && (
              <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium ${getModeChipClassName(getModeSummary(m).tone)}`}>
                {getModeSummary(m).label}
              </span>
            )}
            {getScopeChipRows(m).map((row) => (
              <span
                key={`${row.label}-${row.value}`}
                className="inline-flex rounded-full border border-blue-100 bg-blue-50 px-2.5 py-1 text-[11px] font-medium text-blue-700"
              >
                <span className="mr-1 text-blue-500">{row.label}:</span>
                <span className="max-w-[36ch] truncate">{row.value}</span>
              </span>
            ))}
          </div>

          {shouldShowDetails(m) && (
            <details className="rounded-xl border border-gray-200 bg-white/80 px-3 py-2 text-[12px] text-gray-700">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                <span className="font-medium text-gray-700">Details</span>
                <span className="text-[11px] text-gray-400">
                  {getQualitySummary(m) || "Scope, timing, and retrieval info"}
                </span>
              </summary>

              <div className="mt-3 flex flex-col gap-3 border-t border-gray-100 pt-3">
                {(getIntentDetailRows(m).length > 0 || m.intentSource) && (
                  <div className="rounded-lg border border-blue-100 bg-blue-50/60 px-3 py-2">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-blue-700">
                        Scope
                      </div>
                      {formatIntentSourceLabel(m.intentSource) && (
                        <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">
                          {formatIntentSourceLabel(m.intentSource)}
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-1 gap-y-2">
                      {getIntentDetailRows(m).map((row) => (
                        <div key={`${row.label}-${row.value}`} className="flex flex-col gap-0.5">
                          <span className="text-[10px] font-semibold uppercase tracking-wide text-blue-700">{row.label}</span>
                          <span className="break-words text-[12px] text-blue-950">{row.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {((m.llmTime !== null && m.llmTime !== undefined) || (m.processingTime !== null && m.processingTime !== undefined) || m.contextCount !== null) && (
                  <div className="rounded-lg border border-gray-200 bg-white px-3 py-2">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                      Response
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                      <div className="flex items-center justify-between gap-2 text-[11px] text-gray-700">
                        <span>Answer Time</span>
                        <span className="font-semibold text-gray-900">
                          {formatSeconds(m.llmTime ?? m.processingTime)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2 text-[11px] text-gray-700">
                        <span>Selected Pages</span>
                        <span className="font-semibold text-gray-900">
                          {getSelectedSourceGroups(m).reduce((count, group) => count + group.pages.length, 0) || (m.contextCount ?? 0)}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {m.ragasStatus && m.ragasStatus !== "disabled" && (
                  <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                        Quality Checks
                        {m.ragasStatus === "pending" ? " (Pending)" : ""}
                      </div>
                      {formatResponseMode(m.responseMode) && (
                        <span className="rounded bg-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-700">
                          {formatResponseMode(m.responseMode)}
                          {shouldShowVisionFallback(m) ? " fallback" : ""}
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                      {RAGAS_METRIC_KEYS.map((key) => (
                        <div
                          key={key}
                          className="flex items-center justify-between gap-2 text-[11px] text-gray-700"
                        >
                          <span>{RAGAS_METRIC_LABELS[key]}</span>
                          <span className="font-semibold text-gray-900">
                            {formatRagasMetric(m.ragas?.[key])}
                          </span>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 text-[11px] text-gray-500">
                      Answer Match compares the reply against the expected answer when ground truth is available. Context Precision and Context Recall also require ground truth.
                    </div>
                    {shouldShowVisionFallback(m) && (
                      <div className="mt-2 rounded-md border border-amber-100 bg-amber-50 px-2.5 py-2 text-[11px] text-amber-800">
                        {formatModeFallbackReason(m.modeFallbackReason) || "Vision was requested, but this reply used text context."}
                      </div>
                    )}
                  </div>
                )}

                {getSelectedSourceGroups(m).length > 0 && (
                  <div className="rounded-lg border border-gray-200 bg-white px-3 py-2">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                      Selected Documents
                    </div>
                    <div className="flex flex-col gap-2">
                      {getSelectedSourceGroups(m).map((group) => (
                        <div
                          key={group.key}
                          className="rounded-md border border-gray-200 bg-gray-50 px-2.5 py-2"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="break-words text-[11px] font-medium text-gray-900">
                              <a
                                href={buildDocumentViewerUrl({
                                  sourceId: group.sourceId,
                                  source: group.source,
                                  collection: group.collection,
                                  page: group.primaryPage || group.pages[0] || 1,
                                })}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="hover:text-blue-600 hover:underline"
                              >
                                {group.source}
                              </a>
                            </div>
                            {group.score !== null && (
                              <span className="shrink-0 text-[10px] font-medium text-gray-500">
                                Score {group.score.toFixed(3)}
                              </span>
                            )}
                          </div>
                          <div className="mt-1 flex flex-wrap gap-1.5">
                            {group.pages.length > 0 ? (
                              group.pages.map((page) => (
                                <a
                                  key={`${group.key}-page-${page}`}
                                  href={buildDocumentViewerUrl({
                                    sourceId: group.sourceId,
                                    source: group.source,
                                    collection: group.collection,
                                    page,
                                  })}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="rounded-full border border-blue-200 bg-white px-2 py-0.5 text-[10px] font-medium text-blue-600 cursor-pointer hover:bg-blue-50 transition-colors"
                                >
                                  Page {page}
                                </a>
                              ))
                            ) : (
                              <span className="text-[10px] text-gray-500">Page N/A</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </details>
          )}
        </div>
      )}

      <div className={`flex items-center gap-2 mt-1 ${m.sender === "user" ? "flex-row-reverse" : ""}`}>
        {m.timestamp && (
          <span className="text-[10px] text-gray-400 px-1">
            {formatTime(m.timestamp)}
          </span>
        )}
        <button
          onClick={(e) => { e.currentTarget.blur(); copyToClipboard(stripQualityMetrics(m.text), index); }}
          className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-all"
          title={copiedMessageId === index ? "Copied!" : "Copy message"}
        >
          {copiedMessageId === index ? (
            <Check size={14} className="text-green-500" />
          ) : (
            <Copy size={14} />
          )}
        </button>
        <button
          onClick={(e) => {
            e.currentTarget.blur();
            setInput(stripQualityMetrics(m.text));
            inputRef.current?.focus();
          }}
          className="p-1 rounded hover:bg-blue-100 text-gray-400 hover:text-blue-600 transition-all"
          title="Copy to chatbar"
        >
          <CornerDownLeft size={14} />
        </button>
      </div>
    </div>
  );
}

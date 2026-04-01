/**
 * TracePanel — collapsible pipeline visualization for the multi-agent trace.
 *
 * Rendered below each DM message bubble when "Show Traces" is enabled.
 * All labels are in English regardless of game language (developer-facing).
 *
 * Pipeline layout (when expanded):
 *
 *   ┌─ Router ─────────────────────┐
 *   │ intent=question          1ms │
 *   └──────────────────────────────┘
 *             ↓
 *   ┌─ Judge ──────────────────────┐
 *   │ 不是 · conf 0.87        45ms │
 *   │ 890 in + 45 out              │
 *   └──────────────────────────────┘
 *             ↓
 *   ...
 *   Total: 773ms · 1,992 tok · ¥0.002
 */

import { useState } from 'react';
import type { AgentTrace, TraceStep } from '../api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AGENT_LABEL: Record<string, string> = {
  router:   'Router',
  judge:    'Judge',
  narrator: 'Narrator',
  safety:   'Safety',
  npc:      'NPC',
};

// Approximate USD → CNY conversion for display only
const USD_TO_CNY = 7.2;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function latencyColor(ms: number): string {
  if (ms > 500) return 'trace-step--slow';
  return 'trace-step--fast';
}

function stepModifier(step: TraceStep): string {
  if (step.agent === 'safety') {
    return step.metadata['safe'] === false ? 'trace-step--error' : 'trace-step--ok';
  }
  return latencyColor(step.latency_ms);
}

function fmt(n: number): string {
  return n.toLocaleString();
}

// ---------------------------------------------------------------------------
// Single step card
// ---------------------------------------------------------------------------

function StepCard({ step, showArrow }: { step: TraceStep; showArrow: boolean }) {
  const mod = stepModifier(step);
  const hasTokens = step.tokens_in > 0 || step.tokens_out > 0;
  const agentLabel = AGENT_LABEL[step.agent] ?? step.agent;

  // Safety pass/fail indicator
  let safetyTag: string | null = null;
  if (step.agent === 'safety') {
    safetyTag = step.metadata['safe'] === false ? 'BLOCKED' : 'PASS';
  }

  return (
    <>
      <div className={`trace-step ${mod}`}>
        <div className="trace-step-header">
          <span className="trace-step-agent">{agentLabel}</span>
          {safetyTag && (
            <span className={`trace-safety-tag trace-safety-tag--${step.metadata['safe'] === false ? 'fail' : 'pass'}`}>
              {safetyTag}
            </span>
          )}
          <span className="trace-step-latency">{Math.round(step.latency_ms)}ms</span>
        </div>

        <div className="trace-step-output">{step.output_summary}</div>

        {hasTokens && (
          <div className="trace-step-tokens">
            {fmt(step.tokens_in)} in + {fmt(step.tokens_out)} out
          </div>
        )}
      </div>

      {showArrow && <div className="trace-arrow" aria-hidden="true">↓</div>}
    </>
  );
}

// ---------------------------------------------------------------------------
// TracePanel (exported)
// ---------------------------------------------------------------------------

interface TracePanelProps {
  trace: AgentTrace;
}

export function TracePanel({ trace }: TracePanelProps) {
  const [open, setOpen] = useState(false);

  const costCNY = trace.total_cost_usd * USD_TO_CNY;
  const costStr = costCNY < 0.001 ? '<¥0.001' : `¥${costCNY.toFixed(3)}`;

  return (
    <div className="trace-panel">
      {/* Collapsed toggle row */}
      <button
        className="trace-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={open ? 'Collapse agent trace' : 'Expand agent trace'}
      >
        <span className="trace-toggle-chevron">{open ? '▾' : '▸'}</span>
        <span className="trace-toggle-label">trace</span>
        <span className="trace-toggle-summary">
          {Math.round(trace.total_latency_ms)}ms
          {' · '}
          {fmt(trace.total_tokens)} tok
          {' · '}
          {costStr}
        </span>
      </button>

      {/* Expanded pipeline */}
      {open && (
        <div className="trace-body">
          {trace.steps.map((step, i) => (
            <StepCard
              key={`${step.agent}-${i}`}
              step={step}
              showArrow={i < trace.steps.length - 1}
            />
          ))}

          <div className="trace-total">
            Total: {Math.round(trace.total_latency_ms)}ms
            {' | '}
            {fmt(trace.total_tokens)} tokens
            {' | '}
            {costStr}
          </div>
        </div>
      )}
    </div>
  );
}

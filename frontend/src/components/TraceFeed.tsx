/**
 * TraceFeed — live collapsible drawer showing the agent decision trace feed.
 *
 * Streams traces from GET /api/rooms/{roomId}/traces/live (SSE).
 * Each entry shows all spans with latency bars and token counts.
 * Safety BLOCK highlights the whole entry in red.
 *
 * Always developer-facing; rendered only when showTraces is true.
 */

import { useState } from 'react';
import type { AgentTrace, TraceStep } from '../api';
import { useTraceStream } from '../hooks/useTraceStream';

// ---------------------------------------------------------------------------
// Per-agent config
// ---------------------------------------------------------------------------

const AGENT_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  router:   { label: 'Router',   icon: '🔀', color: '#60a5fa' },
  judge:    { label: 'Judge',    icon: '⚖️', color: '#fbbf24' },
  narrator: { label: 'Narrator', icon: '📖', color: '#4ade80' },
  safety:   { label: 'Safety',   icon: '🛡️', color: '#f87171' },
  npc:      { label: 'NPC',      icon: '🎭', color: '#a78bfa' },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function fmtTok(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function isBlocked(trace: AgentTrace): boolean {
  return trace.steps.some((s) => s.agent === 'safety' && s.metadata['safe'] === false);
}

// ---------------------------------------------------------------------------
// Latency bar (width proportional to span's share of total)
// ---------------------------------------------------------------------------

function LatencyBar({ ms, totalMs }: { ms: number; totalMs: number }) {
  const pct = totalMs > 0 ? Math.max(4, (ms / totalMs) * 100) : 4;
  return (
    <div className="tf-bar-track">
      <div className="tf-bar-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// One span row
// ---------------------------------------------------------------------------

function SpanRow({ step, totalMs }: { step: TraceStep; totalMs: number }) {
  const cfg = AGENT_CONFIG[step.agent] ?? { label: step.agent, icon: '•', color: '#888' };
  const blocked = step.agent === 'safety' && step.metadata['safe'] === false;

  return (
    <div className={`tf-span${blocked ? ' tf-span--blocked' : ''}`}>
      <span className="tf-span-icon">{cfg.icon}</span>
      <span className="tf-span-agent" style={{ color: cfg.color }}>{cfg.label}</span>
      <span className="tf-span-decision">{step.output_summary}</span>
      <LatencyBar ms={step.latency_ms} totalMs={totalMs} />
      <span className="tf-span-ms">{fmtMs(step.latency_ms)}</span>
      <span className="tf-span-tok">{fmtTok(step.tokens_in + step.tokens_out)}tok</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// One trace entry (collapsed/expanded)
// ---------------------------------------------------------------------------

function TraceEntry({ trace, index }: { trace: AgentTrace; index: number }) {
  const [open, setOpen] = useState(index === 0); // newest expanded by default
  const blocked = isBlocked(trace);
  const totalMs = trace.total_latency_ms;

  return (
    <div className={`tf-entry${blocked ? ' tf-entry--blocked' : ''}`}>
      <button className="tf-entry-header" onClick={() => setOpen((v) => !v)}>
        <span className="tf-entry-chevron">{open ? '▾' : '▸'}</span>
        <span className="tf-entry-label">
          {blocked && <span className="tf-blocked-badge">BLOCKED</span>}
          {trace.player_message.slice(0, 40)}{trace.player_message.length > 40 ? '…' : ''}
        </span>
        <span className="tf-entry-meta">
          {fmtMs(totalMs)}
          <span className="tf-entry-sep">·</span>
          {fmtTok(trace.total_tokens)}tok
          <span className="tf-entry-sep">·</span>
          ¥{(trace.total_cost_usd * 7.2).toFixed(4)}
        </span>
      </button>

      {open && (
        <div className="tf-spans">
          {trace.steps.map((step, i) => (
            <SpanRow key={`${step.agent}-${i}`} step={step} totalMs={totalMs} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TraceFeed (exported)
// ---------------------------------------------------------------------------

interface TraceFeedProps {
  roomId: string;
  showTraces: boolean;
}

export function TraceFeed({ roomId, showTraces }: TraceFeedProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const traces = useTraceStream(roomId, showTraces);

  if (!showTraces) return null;

  const hasBlocked = traces.some(isBlocked);

  return (
    <div className={`tf-drawer${drawerOpen ? ' tf-drawer--open' : ''}`}>
      {/* Drawer toggle bar */}
      <button
        className={`tf-drawer-toggle${hasBlocked ? ' tf-drawer-toggle--alert' : ''}`}
        onClick={() => setDrawerOpen((v) => !v)}
      >
        <span className="tf-drawer-chevron">{drawerOpen ? '▾' : '▴'}</span>
        <span className="tf-drawer-title">🔍 Agent Trace</span>
        <span className="tf-drawer-count">
          {traces.length > 0 ? `${traces.length} trace${traces.length !== 1 ? 's' : ''}` : 'waiting…'}
        </span>
        {hasBlocked && <span className="tf-drawer-blocked-badge">⚠ BLOCKED</span>}
      </button>

      {/* Feed */}
      {drawerOpen && (
        <div className="tf-feed">
          {traces.length === 0 ? (
            <div className="tf-empty">No traces yet — send a message to generate one.</div>
          ) : (
            traces.map((trace, i) => (
              <TraceEntry key={trace.message_id} trace={trace} index={i} />
            ))
          )}
        </div>
      )}
    </div>
  );
}

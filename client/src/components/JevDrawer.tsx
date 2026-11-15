import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  Send,
  Wrench,
  X,
  XCircle,
} from "lucide-react";
import { api } from "../lib/api";
import type { CameraState, JevMessage, JevToolTrace } from "../types/nam";
import type { PickedObject } from "./MarsViewport";

interface JevDrawerProps {
  camera: CameraState;
  visibleLayers: string[];
  pickedObject: PickedObject | null;
  onExecuteIntent: (intent: Record<string, unknown>) => void;
  onClose: () => void;
}

export const JevDrawer: React.FC<JevDrawerProps> = ({
  camera,
  visibleLayers,
  pickedObject,
  onExecuteIntent,
  onClose,
}) => {
  const [messages, setMessages] = useState<JevMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "I am JEV, the NAM v2 planetary intelligence assistant backed by 24 grounded tools. Every scientific answer cites tool outputs or abstains honestly — ask me to fly anywhere on Mars, inspect water ice, compare sites, or plan a storm evacuation.",
    },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [examples, setExamples] = useState<string[]>([]);
  const [tools, setTools] = useState<Array<Record<string, unknown>>>([]);
  const [showTools, setShowTools] = useState(false);
  const [expandedTraces, setExpandedTraces] = useState<Record<string, boolean>>({});
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.jevExamples().then((r) => setExamples(r.commands || [])).catch(() => {});
    api.jevTools().then((r) => setTools(r.tools || [])).catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (textOverride?: string) => {
    const q = (textOverride ?? input).trim();
    if (!q || streaming) return;
    if (!textOverride) setInput("");

    const userMsg: JevMessage = { id: `u-${Date.now()}`, role: "user", content: q };
    const asstId = `a-${Date.now() + 1}`;
    const asstMsg: JevMessage = {
      id: asstId,
      role: "assistant",
      content: "",
      traces: [],
      citations: [],
      intents: [],
    };
    setMessages((prev) => [...prev, userMsg, asstMsg]);
    setStreaming(true);

    try {
      await api.jevChatStream(
        q,
        {
          camera,
          visible_layers: visibleLayers,
          picked: pickedObject
            ? { id: pickedObject.id, kind: pickedObject.kind, name: pickedObject.name, lat: pickedObject.lat, lon: pickedObject.lon }
            : null,
        },
        {
          onToolStart: (tr) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId ? { ...m, traces: [...(m.traces || []), tr] } : m
              )
            );
          },
          onToolEnd: (tr) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId
                  ? {
                      ...m,
                      traces: (m.traces || []).map((t) =>
                        t.id === tr.id ? { ...t, ok: tr.ok, error: tr.error } : t
                      ),
                    }
                  : m
              )
            );
          },
          onToken: (chunk) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === asstId ? { ...m, content: m.content + chunk } : m))
            );
          },
          onIntent: (intent) => {
            onExecuteIntent(intent);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId ? { ...m, intents: [...(m.intents || []), intent] } : m
              )
            );
          },
          onDone: (payload) => {
            const cites = Array.isArray(payload.citations) ? (payload.citations as string[]) : [];
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId
                  ? {
                      ...m,
                      citations: cites,
                      sim: Boolean(payload.sim),
                      abstained: Boolean(payload.abstained),
                    }
                  : m
              )
            );
          },
        }
      );
    } catch (e) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === asstId
            ? { ...m, content: `Error calling JEV: ${e instanceof Error ? e.message : String(e)}` }
            : m
        )
      );
    } finally {
      setStreaming(false);
    }
  };

  const explainView = async () => {
    if (streaming) return;
    setStreaming(true);
    const id = `exp-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: `u-${id}`, role: "user", content: "Explain what I am looking at right now." },
    ]);
    try {
      const res = await api.jevExplain(
        { lat: camera.lat, lon: camera.lon, altitude_km: camera.altitudeKm },
        visibleLayers,
        pickedObject ? { name: pickedObject.name, kind: pickedObject.kind, lat: pickedObject.lat, lon: pickedObject.lon } : null
      );
      setMessages((prev) => [
        ...prev,
        {
          id,
          role: "assistant",
          content: String(res.explanation || res.summary || JSON.stringify(res, null, 2)),
          citations: Array.isArray(res.citations) ? (res.citations as string[]) : [],
          sim: true,
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id, role: "assistant", content: `Explain failed: ${String(e)}` },
      ]);
    } finally {
      setStreaming(false);
    }
  };

  return (
    <aside className="jev-drawer glass">
      <div className="drawer-head">
        <div className="row">
          <Bot size={16} color="#38bdf8" />
          <span>JEV AI Planetary Assistant</span>
          <span className="badge badge-cyan">{tools.length || 24} Tools</span>
        </div>
        <div className="row">
          <button
            className={`btn btn-xs ${showTools ? "btn-active" : ""}`}
            onClick={() => setShowTools((v) => !v)}
            title="Inspect all 24 JEV tool schemas"
          >
            <Wrench size={12} /> Tools
          </button>
          <button className="btn btn-xs btn-ghost" onClick={onClose}>
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Explain What I Am Looking At + Quick Review Commands */}
      <div style={{ padding: "8px 10px", borderBottom: "1px solid var(--panel-border)" }}>
        <div className="row" style={{ marginBottom: 6 }}>
          <button className="btn btn-xs btn-cyan" style={{ flex: 1 }} onClick={explainView} disabled={streaming}>
            <Eye size={12} /> Explain What I Am Looking At
          </button>
        </div>
        <div style={{ display: "flex", gap: 4, overflowX: "auto", paddingBottom: 2 }}>
          {examples.slice(0, 8).map((cmd, idx) => (
            <button
              key={idx}
              className="btn btn-xs"
              style={{ flexShrink: 0, maxWidth: 210, overflow: "hidden", textOverflow: "ellipsis" }}
              onClick={() => sendMessage(cmd)}
              title={cmd}
              disabled={streaming}
            >
              {cmd.length > 32 ? `${cmd.slice(0, 32)}…` : cmd}
            </button>
          ))}
        </div>
      </div>

      {showTools ? (
        <div className="drawer-body">
          <div className="small muted">
            Typed JEV tool registry (zero fabricated sources; all calls logged inline):
          </div>
          {tools.map((t, idx) => (
            <div key={idx} className="card">
              <div className="card-title">
                <span className="mono" style={{ fontSize: 11.5, color: "#7dd3fc" }}>
                  {String(t.name)}
                </span>
                <span className="badge badge-muted">schema</span>
              </div>
              <div className="small muted">{String(t.description || "")}</div>
            </div>
          ))}
        </div>
      ) : (
        <>
          {/* Chat Stream */}
          <div ref={scrollRef} className="drawer-body">
            {messages.map((m) => (
              <div
                key={m.id}
                style={{
                  alignSelf: m.role === "user" ? "flex-end" : "stretch",
                  maxWidth: m.role === "user" ? "86%" : "100%",
                  background:
                    m.role === "user" ? "rgba(228, 111, 59, 0.2)" : "rgba(255, 255, 255, 0.04)",
                  border:
                    m.role === "user"
                      ? "1px solid rgba(228, 111, 59, 0.4)"
                      : "1px solid rgba(255, 255, 255, 0.09)",
                  borderRadius: 10,
                  padding: "8px 10px",
                }}
              >
                {/* Inline Tool-Activity Trace */}
                {m.traces && m.traces.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <button
                      className="btn btn-xs btn-ghost"
                      style={{ padding: "0 4px", height: 20, color: "#7dd3fc" }}
                      onClick={() =>
                        setExpandedTraces((prev) => ({ ...prev, [m.id]: !prev[m.id] }))
                      }
                    >
                      {expandedTraces[m.id] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      Tool Trace ({m.traces.length} calls)
                    </button>
                    {expandedTraces[m.id] && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
                        {m.traces.map((tr: JevToolTrace) => (
                          <div
                            key={tr.id}
                            className="mono small"
                            style={{
                              padding: "4px 6px",
                              borderRadius: 6,
                              background: "rgba(0,0,0,0.35)",
                              border: "1px solid rgba(255,255,255,0.08)",
                            }}
                          >
                            <div className="row" style={{ justifyContent: "space-between" }}>
                              <span style={{ color: "#38bdf8" }}>{tr.tool}</span>
                              {tr.ok === true && <CheckCircle2 size={12} color="#34d399" />}
                              {tr.ok === false && <XCircle size={12} color="#ef4444" />}
                            </div>
                            <div className="muted" style={{ fontSize: 10, wordBreak: "break-all" }}>
                              {JSON.stringify(tr.args)}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.48, fontSize: 12.5 }}>
                  {m.content || (streaming ? "Calling tools…" : "")}
                </div>

                {/* Globe intents executed */}
                {m.intents && m.intents.length > 0 && (
                  <div className="row-wrap" style={{ marginTop: 6 }}>
                    {m.intents.map((it, idx) => (
                      <span key={idx} className="badge badge-obs">
                        Globe: {String(it.action || it.type || "intent")}
                      </span>
                    ))}
                  </div>
                )}

                {/* Citations */}
                {m.citations && m.citations.length > 0 && (
                  <div
                    className="small muted"
                    style={{
                      marginTop: 6,
                      paddingTop: 5,
                      borderTop: "1px solid rgba(255,255,255,0.08)",
                    }}
                  >
                    <strong>Sources:</strong> {m.citations.join(" · ")}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Input Composer */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage();
            }}
            style={{
              padding: "8px 10px",
              borderTop: "1px solid var(--panel-border)",
              display: "flex",
              gap: 6,
            }}
          >
            <input
              className="input"
              placeholder="Ask JEV about Mars, routes, water, storms…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={streaming}
            />
            <button type="submit" className="btn btn-primary" disabled={streaming || !input.trim()}>
              <Send size={13} />
            </button>
          </form>
        </>
      )}
    </aside>
  );
};

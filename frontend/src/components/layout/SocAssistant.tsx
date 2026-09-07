import { useEffect, useRef, useState } from 'react';
import { Bot, Send, Shield, X } from 'lucide-react';
import * as api from '../../services/api';
import type { ChatMessage } from '../../types';

const QUICK_ACTIONS = [
  "Summarize today's threats",
  'Show critical alerts',
  'List MITRE techniques detected',
  'What should I investigate first?',
];

const MODE_SUBTITLE = api.isMockMode() ? 'Mock Mode' : 'Live Backend';

interface Props {
  open: boolean;
  userName: string;
  onClose: () => void;
}

export default function SocAssistant({ open, userName, onClose }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: api.isMockMode()
        ? `Hello ${userName}. I'm the SOC Assistant running in mock mode. Ask me about today's threats, critical alerts, MITRE techniques, or what to investigate first.`
        : `Hello ${userName}. I'm the SOC Assistant, connected to the live backend. Ask me about today's threats, critical alerts, MITRE techniques, or what to investigate first.`,
      timestamp: Date.now(),
    },
  ]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, thinking]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || thinking) return;
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: 'user', content: trimmed, timestamp: Date.now() };
    setMessages((m) => [...m, userMsg]);
    setInput('');
    setThinking(true);
    try {
      const reply = await api.assistantChat(trimmed);
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: 'assistant', content: reply, timestamp: Date.now() }]);
    } catch {
      setMessages((m) => [
        ...m,
        { id: `e-${Date.now()}`, role: 'assistant', content: 'Sorry, the assistant is unavailable right now.', timestamp: Date.now() },
      ]);
    } finally {
      setThinking(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-md flex-col border-l border-slate-700/60 bg-slate-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/50 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/10 ring-1 ring-cyan-500/40">
              <Bot className="h-4.5 w-4.5 text-cyan-400" />
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-100">SOC Assistant</div>
              <div className="text-[10px] uppercase tracking-wider text-cyan-400">{MODE_SUBTITLE}</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-800 hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Quick actions */}
        <div className="flex flex-wrap gap-1.5 border-b border-slate-700/50 px-4 py-2.5">
          {QUICK_ACTIONS.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              disabled={thinking}
              className="rounded-full bg-slate-800/70 px-3 py-1 text-[11px] text-slate-300 ring-1 ring-slate-700/60 hover:bg-slate-700/70 hover:text-cyan-300 disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'rounded-br-sm bg-cyan-500/15 text-cyan-100 ring-1 ring-cyan-500/30'
                    : 'rounded-bl-sm bg-slate-800 text-slate-200 ring-1 ring-slate-700/50'
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {thinking && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-xl rounded-bl-sm bg-slate-800 px-3.5 py-2.5 text-sm text-slate-400 ring-1 ring-slate-700/50">
                <Shield className="h-3.5 w-3.5 animate-pulse text-cyan-400" />
                Analyzing threat data...
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-center gap-2 border-t border-slate-700/50 p-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the SOC Assistant..."
            className="flex-1 rounded-lg border border-slate-700/60 bg-slate-800/60 px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-cyan-500/60"
          />
          <button
            type="submit"
            disabled={thinking || !input.trim()}
            className="rounded-lg bg-cyan-500/15 p-2.5 text-cyan-400 ring-1 ring-cyan-500/40 hover:bg-cyan-500/25 disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
}

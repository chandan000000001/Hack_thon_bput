import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUpRight,
  Fingerprint,
  Globe,
  Image as ImageIcon,
  KeyRound,
  Mail,
  Radar,
  ShieldCheck,
} from 'lucide-react';
import { useAuthStore } from '../store/authStore';

/* ------------------------------------------------------------------ */
/* Motion helpers                                                      */
/* ------------------------------------------------------------------ */

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

function Reveal({
  children,
  className = '',
  delay = 0,
  fromX = 36,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  fromX?: number;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const reduced = usePrefersReducedMotion();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (reduced) {
      setVisible(true);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.disconnect();
          }
        }
      },
      { threshold: 0.12 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [reduced]);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateX(0px)' : `translateX(${fromX}px)`,
        transition: reduced
          ? 'none'
          : 'opacity 750ms ease, transform 750ms cubic-bezier(0.22, 1, 0.36, 1)',
        transitionDelay: reduced ? '0ms' : `${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Cursor trail — faint risograph green dots on a fixed canvas         */
/* ------------------------------------------------------------------ */

function CursorTrail() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (reduced) return;
    if (!window.matchMedia('(pointer: fine)').matches) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = window.innerWidth;
    let height = window.innerHeight;
    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width;
      canvas.height = height;
    };
    resize();
    window.addEventListener('resize', resize);

    type Dot = { x: number; y: number; r: number; life: number };
    const dots: Dot[] = [];
    let lastSpawn = 0;

    const onMove = (e: PointerEvent) => {
      const now = performance.now();
      if (now - lastSpawn < 26) return;
      lastSpawn = now;
      dots.push({ x: e.clientX, y: e.clientY, r: 1.5 + Math.random() * 2.5, life: 1 });
      if (dots.length > 140) dots.shift();
    };
    window.addEventListener('pointermove', onMove);

    let raf = 0;
    const tick = () => {
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#34d399';
      for (let i = dots.length - 1; i >= 0; i--) {
        const dot = dots[i];
        dot.life -= 0.018;
        if (dot.life <= 0) {
          dots.splice(i, 1);
          continue;
        }
        ctx.globalAlpha = dot.life * 0.26;
        ctx.beginPath();
        ctx.arc(dot.x, dot.y, dot.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onMove);
    };
  }, [reduced]);

  if (reduced) return null;
  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-40"
    />
  );
}

/* ------------------------------------------------------------------ */
/* Static, factual project content                                     */
/* ------------------------------------------------------------------ */

const PIPELINE_LINE =
  'Detection -> Classification -> Risk Assessment -> Explanation -> Alert -> Recommended Response';

const STATUS_ROWS: { name: string; detail: string; value: string; live: boolean }[] = [
  {
    name: 'Backend API (FastAPI + Supabase)',
    detail: 'REST detection API backed by Supabase auth, database and storage',
    value: 'LIVE',
    live: true,
  },
  {
    name: 'Detection modules',
    detail: 'Phishing, URL, impersonation, deepfake, account takeover, network/API',
    value: '6 of 6 COMPLETE',
    live: false,
  },
  {
    name: 'Trained ML models',
    detail:
      'XGBoost email F1 0.9900 · XGBoost URL held-out F1 1.0000 (small-sample caveat) · PyTorch CNN deepfake F1 0.9100 · XGBoost network F1 0.9944',
    value: '4',
    live: false,
  },
  {
    name: 'Explainable AI',
    detail: 'OpenRouter narratives + MITRE ATT&CK mapping',
    value: 'COMPLETE',
    live: false,
  },
  {
    name: 'Risk scoring',
    detail: '0-100 with Safe / Low / Medium / High / Critical bands',
    value: 'COMPLETE',
    live: false,
  },
  {
    name: 'Roles and auth',
    detail: 'viewer / analyst / admin with signup and password reset',
    value: 'COMPLETE',
    live: false,
  },
  {
    name: 'Dashboard',
    detail: 'React SOC command center with Supabase Realtime',
    value: 'LIVE',
    live: true,
  },
  {
    name: 'Evaluation harness',
    detail:
      'Public datasets: URLhaus, Cisco Umbrella Top-1M, UCI SMS Spam, CIFAKE, KDD subset, plus synthetic sets',
    value: 'COMPLETE',
    live: false,
  },
  {
    name: 'Deliverables',
    detail: 'PDF minimum deliverables covered',
    value: '12 of 12',
    live: false,
  },
];

const MODULES: {
  index: string;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  indicators: string[];
}[] = [
  {
    index: '01',
    title: 'AI-Powered Phishing Detection',
    icon: Mail,
    description:
      'Analyses emails, SMS, social messages and QR-code references for social engineering before they reach a human.',
    indicators: ['Urgency', 'Impersonation', 'Suspicious domains', 'Credential requests'],
  },
  {
    index: '02',
    title: 'Malicious URL & Website Detection',
    icon: Globe,
    description:
      'Screens links and sites for deception patterns, from look-alike domains to manipulated redirects and fake login pages.',
    indicators: ['Look-alike domains', 'URL manipulation', 'Malicious redirects', 'Fake login pages'],
  },
  {
    index: '03',
    title: 'Digital Impersonation Detection',
    icon: Fingerprint,
    description:
      'Detects messages and profiles pretending to be trusted people and institutions across channels.',
    indicators: [
      'Government officials',
      'Senior management',
      'Teachers',
      'Financial institutions',
      'Brands',
      'Known contacts',
    ],
  },
  {
    index: '04',
    title: 'Deepfake Detection',
    icon: ImageIcon,
    description:
      'Examines images, video and voice for synthetic media using ELA forensics plus a trained CNN, producing an authenticity score.',
    indicators: ['Images', 'Video', 'Voice', 'ELA forensics + trained CNN', 'Authenticity score'],
  },
  {
    index: '05',
    title: 'Credential Theft & Account Takeover',
    icon: KeyRound,
    description:
      'Watches authentication behaviour for takeover attempts against user accounts.',
    indicators: ['Failed login bursts', 'Password spraying', 'Impossible travel', 'Unknown devices'],
  },
  {
    index: '06',
    title: 'Intelligent Cyber Threat Detection',
    icon: Radar,
    description:
      'Correlates network and API activity to surface technical threats and abnormal behaviour.',
    indicators: [
      'Suspicious network traffic',
      'API abuse',
      'Data exfiltration',
      'Insider threats',
    ],
  },
];

const SEVERITIES: { label: string; band: string; hex: string }[] = [
  { label: 'SAFE', band: '0-20', hex: '#10b981' },
  { label: 'LOW', band: '21-40', hex: '#eab308' },
  { label: 'MEDIUM', band: '41-60', hex: '#f59e0b' },
  { label: 'HIGH', band: '61-80', hex: '#f97316' },
  { label: 'CRITICAL', band: '81-100', hex: '#ef4444' },
];

const ARCHITECTURE_FLOW = [
  'React SOC Dashboard',
  'FastAPI Detection API',
  'Supabase (Auth, Postgres, Storage, Realtime)',
  'OpenRouter Explainable AI',
  'Trained Models (XGBoost, PyTorch CNN)',
];

/* ------------------------------------------------------------------ */
/* Shared pieces                                                       */
/* ------------------------------------------------------------------ */

function CallToActions({ showDashboard }: { showDashboard: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <Link
        to="/login?mode=signup"
        className="group inline-flex items-center gap-2 bg-emerald-500 px-8 py-4 font-mono text-sm font-bold tracking-widest text-stone-950 hover:bg-emerald-400"
      >
        SIGN UP
        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
      </Link>
      <Link
        to="/login?mode=signin"
        className="inline-flex items-center gap-2 border border-emerald-500/60 px-8 py-4 font-mono text-sm font-bold tracking-widest text-emerald-300 hover:border-emerald-400 hover:bg-emerald-500/10"
      >
        LOGIN
      </Link>
      {showDashboard && (
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-2 border border-stone-600 px-8 py-4 font-mono text-sm font-bold tracking-widest text-stone-200 hover:border-stone-400 hover:bg-stone-800/50"
        >
          OPEN DASHBOARD
          <ArrowUpRight className="h-4 w-4" />
        </Link>
      )}
    </div>
  );
}

function SectionHeading({ number, title }: { number: string; title: string }) {
  return (
    <div className="mb-12 flex items-baseline gap-4 border-b border-stone-800 pb-6">
      <span className="font-mono text-sm font-bold text-red-500">{number}</span>
      <h2 className="font-display text-xl font-bold uppercase tracking-[0.25em] text-stone-100">
        {title}
      </h2>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Landing page                                                        */
/* ------------------------------------------------------------------ */

export default function Landing() {
  const reduced = usePrefersReducedMotion();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // Drag-to-scroll state for the severity film strip
  const stripRef = useRef<HTMLDivElement | null>(null);
  const dragState = useRef({ isDown: false, startX: 0, startScroll: 0 });

  const onStripPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = stripRef.current;
    if (!el) return;
    dragState.current = { isDown: true, startX: e.clientX, startScroll: el.scrollLeft };
    el.setPointerCapture(e.pointerId);
  };
  const onStripPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = stripRef.current;
    if (!el || !dragState.current.isDown) return;
    el.scrollLeft = dragState.current.startScroll - (e.clientX - dragState.current.startX);
  };
  const onStripPointerEnd = () => {
    dragState.current.isDown = false;
  };

  return (
    <div className={reduced ? 'lg-still relative min-h-screen bg-stone-950 text-stone-100' : 'relative min-h-screen bg-stone-950 text-stone-100'}>
      <style>{`
        .font-display {
          font-family: Georgia, 'Iowan Old Style', 'Palatino Linotype', 'Times New Roman', serif;
        }
        .font-script {
          font-family: 'Segoe Script', 'Bradley Hand', 'Brush Script MT', 'Apple Chancery', cursive;
        }
        @keyframes landingLetterIn {
          0% { opacity: 0; transform: translateY(0.35em) rotate(5deg) scale(0.92); filter: blur(12px); }
          60% { filter: blur(0); }
          100% { opacity: 1; transform: translateY(0) rotate(0deg) scale(1); filter: blur(0); }
        }
        .landing-letter {
          opacity: 0;
          animation: landingLetterIn 700ms cubic-bezier(0.22, 1, 0.36, 1) forwards;
        }
        .lg-still .landing-letter { animation: none; opacity: 1; }
        .lg-still * { transition: none !important; animation: none !important; }
      `}</style>

      <CursorTrail />

      {/* Slim editorial masthead */}
      <header className="sticky top-0 z-30 border-b border-stone-800/80 bg-stone-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <span className="font-mono text-xs font-bold tracking-[0.3em] text-stone-100">
            CYBERGUARD<span className="text-red-500"> /</span>
            <span className="ml-2 font-normal text-[#a47148]">PROJECT MONOGRAPH</span>
          </span>
          <Link
            to="/login?mode=signin"
            className="font-mono text-xs tracking-[0.2em] text-emerald-400 hover:text-emerald-300"
          >
            LOGIN →
          </Link>
        </div>
      </header>

      {/* ---------------------------------------------------------- */}
      {/* SECTION 1 — HERO                                            */}
      {/* ---------------------------------------------------------- */}
      <section className="relative mx-auto flex min-h-[92vh] max-w-6xl flex-col justify-center px-6 py-24">
        <Reveal>
          <p className="font-display mb-8 text-lg italic tracking-wide text-[#a47148]">
            Public Edition — Project Status Monograph
          </p>
        </Reveal>

        <h1
          aria-label="CYBERGUARD"
          className="font-display select-none whitespace-nowrap font-bold leading-[0.9] tracking-tight"
          style={{ fontSize: 'clamp(2.25rem, 10.5vw, 9.5rem)' }}
        >
          {'CYBER'.split('').map((ch, i) => (
            <span
              key={`cyber-${i}`}
              aria-hidden="true"
              className="landing-letter inline-block text-stone-50"
              style={{ animationDelay: `${100 + i * 70}ms` }}
            >
              {ch}
            </span>
          ))}
          {'GUARD'.split('').map((ch, i) => (
            <span
              key={`guard-${i}`}
              aria-hidden="true"
              className="landing-letter inline-block text-transparent"
              style={{
                animationDelay: `${450 + i * 70}ms`,
                WebkitTextStroke: '2px #10b981',
              }}
            >
              {ch}
            </span>
          ))}
        </h1>

        <Reveal delay={900}>
          <p className="font-display mt-10 max-w-3xl text-xl leading-relaxed text-stone-200 md:text-2xl">
            AI-Powered Cyber Threat, Phishing &amp; Digital Impersonation Detection and Response
            System
          </p>
        </Reveal>

        <Reveal delay={1050} className="mt-12">
          <CallToActions showDashboard={isAuthenticated} />
        </Reveal>

        <Reveal delay={1200}>
          <p className="mt-10 font-mono text-xs tracking-[0.2em] text-[#a47148]">
            Domain: Cybersecurity + Artificial Intelligence
          </p>
        </Reveal>
      </section>

      {/* ---------------------------------------------------------- */}
      {/* SECTION 2 — PROJECT STATUS BOARD                            */}
      {/* ---------------------------------------------------------- */}
      <section className="border-t border-stone-800/80 bg-stone-950 px-6 py-28">
        <div className="mx-auto max-w-6xl">
          <Reveal>
            <SectionHeading number="01" title="Project Status" />
          </Reveal>

          <div className="divide-y divide-stone-800/70 border-y border-stone-800/70">
            {STATUS_ROWS.map((row, i) => (
              <Reveal key={row.name} delay={i * 60} fromX={24}>
                <div className="grid grid-cols-1 gap-2 py-6 md:grid-cols-[2fr_3fr_auto] md:items-baseline md:gap-8">
                  <div className="font-display text-base font-bold text-stone-50">{row.name}</div>
                  <div className="font-mono text-xs leading-relaxed text-stone-400">
                    {row.detail}
                  </div>
                  <div className="flex items-center gap-3 md:justify-end">
                    <span
                      className={`inline-block px-2.5 py-1 font-mono text-[11px] font-bold tracking-widest ${
                        row.live
                          ? 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/50'
                          : 'bg-stone-800/80 text-stone-100 ring-1 ring-stone-600/70'
                      }`}
                    >
                      {row.live ? '● ' : ''}
                      {row.value}
                    </span>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- */}
      {/* SECTION 3 — MODULE SPREADS (sticky pages sliding over each   */}
      {/* other, content revealed with cross-fade + horizontal slide)  */}
      {/* ---------------------------------------------------------- */}
      <section className="relative">
        <div className="sticky top-0 z-0 border-b border-stone-800/80 bg-stone-950 px-6 pb-10 pt-24">
          <div className="mx-auto max-w-6xl">
            <SectionHeading number="02" title="Detection Modules — Six Spreads" />
          </div>
        </div>

        {MODULES.map((mod, i) => {
          const Icon = mod.icon;
          const slideFrom = i % 2 === 0 ? 48 : -48;
          return (
            <div
              key={mod.index}
              className="sticky top-16 z-10 flex min-h-[88vh] items-center border-t border-stone-800/60 bg-stone-950 px-6 py-20"
            >
              <div className="mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-12 lg:grid-cols-[auto_1fr]">
                <Reveal fromX={slideFrom}>
                  <div className="flex items-start gap-6">
                    <span
                      aria-hidden="true"
                      className="font-display select-none text-[10rem] font-bold leading-none text-transparent"
                      style={{
                        fontSize: 'clamp(5rem, 14vw, 12rem)',
                        WebkitTextStroke: '1.5px #7f5539',
                      }}
                    >
                      {mod.index}
                    </span>
                  </div>
                </Reveal>

                <Reveal fromX={-slideFrom} delay={120}>
                  <div>
                    <div className="mb-6 flex items-center gap-3">
                      <Icon className="h-6 w-6 text-emerald-400" />
                      <span className="font-mono text-[11px] uppercase tracking-[0.3em] text-[#a47148]">
                        Module {mod.index} / 06
                      </span>
                    </div>
                    <h3
                      className="font-display font-bold leading-tight text-stone-50"
                      style={{ fontSize: 'clamp(1.75rem, 4.5vw, 3.5rem)' }}
                    >
                      {mod.title}
                    </h3>
                    <p className="mt-6 max-w-2xl text-base leading-relaxed text-stone-300 md:text-lg">
                      {mod.description}
                    </p>
                    <div className="mt-8 flex flex-wrap gap-2">
                      {mod.indicators.map((indicator) => (
                        <span
                          key={indicator}
                          className="border border-stone-700/70 bg-stone-900/60 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-stone-300"
                        >
                          {indicator}
                        </span>
                      ))}
                    </div>
                    <p className="mt-10 border-t border-stone-800 pt-5 font-mono text-[11px] tracking-wide text-emerald-400/90">
                      {PIPELINE_LINE}
                    </p>
                  </div>
                </Reveal>
              </div>
            </div>
          );
        })}
      </section>

      {/* ---------------------------------------------------------- */}
      {/* SECTION 4 — SEVERITY FILM STRIP                             */}
      {/* ---------------------------------------------------------- */}
      <section className="border-t border-stone-800/80 bg-stone-950 px-6 py-28">
        <div className="mx-auto max-w-6xl">
          <Reveal>
            <SectionHeading number="03" title="Risk Scoring — Severity Bands" />
          </Reveal>

          <Reveal delay={120}>
            <p className="mb-10 max-w-2xl font-mono text-xs leading-relaxed text-stone-400">
              Every detection is scored 0-100 and mapped to one of five response bands. Drag the
              strip to scrub.
            </p>
          </Reveal>

          <Reveal delay={200}>
            <div
              ref={stripRef}
              onPointerDown={onStripPointerDown}
              onPointerMove={onStripPointerMove}
              onPointerUp={onStripPointerEnd}
              onPointerLeave={onStripPointerEnd}
              className="flex cursor-grab select-none gap-6 overflow-x-auto pb-4 active:cursor-grabbing"
            >
              {SEVERITIES.map((sev) => (
                <div key={sev.label} className="w-60 flex-shrink-0 md:w-72">
                  <div
                    className="flex h-44 items-end p-5 md:h-52"
                    style={{ backgroundColor: sev.hex }}
                  >
                    <span className="font-display text-2xl font-bold tracking-widest text-stone-950">
                      {sev.label}
                    </span>
                  </div>
                  <div className="mt-3 flex items-baseline justify-between font-mono text-xs">
                    <span className="text-[#a47148]">SCORE</span>
                    <span className="font-bold text-stone-100">{sev.band}</span>
                  </div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ---------------------------------------------------------- */}
      {/* SECTION 5 — ARCHITECTURE STRIP                              */}
      {/* ---------------------------------------------------------- */}
      <section className="border-t border-stone-800/80 bg-stone-950 px-6 py-28">
        <div className="mx-auto max-w-6xl">
          <Reveal>
            <SectionHeading number="04" title="Architecture" />
          </Reveal>

          <Reveal delay={120}>
            <div className="overflow-x-auto border border-stone-800 bg-stone-900/40 p-8">
              <p className="whitespace-nowrap font-mono text-sm tracking-wide text-stone-200">
                {ARCHITECTURE_FLOW.map((node, i) => (
                  <span key={node}>
                    <span className={i % 2 === 0 ? 'text-emerald-300' : 'text-stone-100'}>
                      {node}
                    </span>
                    {i < ARCHITECTURE_FLOW.length - 1 && (
                      <span className="mx-4 text-red-500/70">-&gt;</span>
                    )}
                  </span>
                ))}
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ---------------------------------------------------------- */}
      {/* SECTION 6 — FOOTER                                          */}
      {/* ---------------------------------------------------------- */}
      <footer className="border-t border-stone-800/80 bg-stone-950 px-6 pb-16 pt-28">
        <div className="mx-auto max-w-6xl">
          <Reveal>
            <SectionHeading number="05" title="Colophon" />
          </Reveal>

          <Reveal delay={100}>
            <p className="font-display max-w-3xl text-lg leading-relaxed text-stone-200">
              Built by <span className="font-script text-[#c08552]">Chandan</span> — Network
              Security Engineer, Red Team, AI Security Research.
            </p>
          </Reveal>

          <Reveal delay={180}>
            <p className="mt-6 max-w-3xl font-mono text-xs leading-relaxed text-stone-400">
              Demonstrates three mandatory scenarios: phishing/social engineering, digital
              impersonation/deepfake, technical cyber threat/abnormal behaviour.
            </p>
          </Reveal>

          <Reveal delay={260} className="mt-12">
            <CallToActions showDashboard={isAuthenticated} />
          </Reveal>

          <Reveal delay={320}>
            <div className="mt-20 flex items-end justify-between border-t border-stone-800 pt-8">
              <span className="font-mono text-xs tracking-[0.3em] text-stone-500">
                CYBERGUARD — {new Date().getFullYear()}
              </span>
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
            </div>
          </Reveal>
        </div>
      </footer>
    </div>
  );
}

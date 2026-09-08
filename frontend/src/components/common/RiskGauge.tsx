import { getSeverityFromScore } from '../../services/mockEngine';
import { SEVERITY_COLORS } from '../../theme';
import { SEVERITY_STYLES } from './SeverityBadge';

const SIZES = {
  sm: { box: 64, stroke: 6, text: 'text-sm' },
  md: { box: 100, stroke: 8, text: 'text-xl' },
  lg: { box: 140, stroke: 10, text: 'text-3xl' },
};

export default function RiskGauge({ score, size = 'md' }: { score: number; size?: 'sm' | 'md' | 'lg' }) {
  const { box, stroke, text } = SIZES[size];
  const radius = (box - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const offset = circumference * (1 - clamped / 100);
  const severity = getSeverityFromScore(clamped);
  const color = SEVERITY_COLORS[severity];

  return (
    <div className="flex flex-col items-center">
      <svg width={box} height={box} className="-rotate-90">
        <circle
          cx={box / 2}
          cy={box / 2}
          r={radius}
          fill="none"
          stroke="#262626"
          strokeWidth={stroke}
        />
        <circle
          cx={box / 2}
          cy={box / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 700ms ease, stroke 300ms ease' }}
        />
      </svg>
      <div className="flex flex-col items-center" style={{ marginTop: -(box / 2 + stroke * 1.2) }}>
        <span className={`${text} font-bold`} style={{ color }}>
          {clamped}
        </span>
      </div>
      <span
        className={`mt-3 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ring-1 ${SEVERITY_STYLES[severity].bg} ${SEVERITY_STYLES[severity].text} ${SEVERITY_STYLES[severity].ring}`}
      >
        {severity}
      </span>
    </div>
  );
}

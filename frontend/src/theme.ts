import type { Severity } from './types';

/**
 * CYBERGUARD monochrome theme — strict black / white / red palette.
 *
 * Severity ramp (0-100 risk bands):
 *   safe     #e4e4e7  zinc-200, black text
 *   low      #71717a  zinc-500, white text
 *   medium   #f87171  red-400,  black text
 *   high     #dc2626  red-600,  white text
 *   critical #ef4444  red-500,  white text + subtle pulse ring
 *
 * Surfaces: page #050505 · panels #0a0a0a · cards #101010 · borders #262626
 * Text: primary #fafafa · secondary #a3a3a3 · accent red-600 (hover red-500)
 */

export type RampKey = Severity;

export interface RampEntry {
  /** Swatch / series color. */
  hex: string;
  /** Text color to place on top of `hex`. */
  textOn: 'black' | 'white';
}

export const SEVERITY_RAMP: Record<RampKey, RampEntry> = {
  safe: { hex: '#e4e4e7', textOn: 'black' },
  low: { hex: '#71717a', textOn: 'white' },
  medium: { hex: '#f87171', textOn: 'black' },
  high: { hex: '#dc2626', textOn: 'white' },
  critical: { hex: '#ef4444', textOn: 'white' },
};

/** Severity → swatch color (chart series, gauge arcs, table swatches). */
export const SEVERITY_COLORS: Record<RampKey, string> = {
  safe: '#e4e4e7',
  low: '#71717a',
  medium: '#f87171',
  high: '#dc2626',
  critical: '#ef4444',
};

/** Recharts palette: grid/tooltip chrome + ordered series colors (red + white/gray neutrals). */
export const CHART_COLORS = {
  grid: '#262626',
  axis: '#a3a3a3',
  tick: '#fafafa',
  tooltipBg: '#101010',
  tooltipBorder: '#262626',
  series: ['#dc2626', '#ef4444', '#fafafa', '#a3a3a3', '#71717a', '#f87171'],
} as const;

/** General accent tokens. */
export const ACCENT = {
  primary: '#dc2626', // red-600
  primaryHover: '#ef4444', // red-500
  bg: '#050505',
  panel: '#0a0a0a',
  card: '#101010',
  border: '#262626',
  textPrimary: '#fafafa',
  textSecondary: '#a3a3a3',
} as const;

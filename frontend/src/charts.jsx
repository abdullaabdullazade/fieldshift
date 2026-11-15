import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { fmt } from './lib.jsx'

// categorical order (validated: lightness band, chroma, CVD, normal-vision floor all PASS on #fcfcfb)
export const CAT = ['#F57C1F', '#1F6FB2', '#2FA35B', '#8E44AD', '#C0392B', '#0097A7']
export const NAVY = '#2B2A2E'
export const GRID = '#EEE9E2'
export const AXIS = { fontSize: 12, fill: '#6B6A70', fontFamily: 'Inter' }

// sequential orange ramp (light -> dark) and diverging blue <-> grey <-> orange
const SEQ = ['#FFF1E5', '#FDD3AE', '#F9AE6E', '#F57C1F', '#C0540A', '#7A3305']
export function seqColor(v, min, max) {
  if (v === undefined || v === null) return '#E3E8ED'
  const t = max === min ? 0.5 : (v - min) / (max - min)
  return SEQ[Math.max(0, Math.min(SEQ.length - 1, Math.floor(t * (SEQ.length - 0.001))))]
}
const DIV = ['#1F4E8C', '#5D8CC4', '#AFC4DC', '#E5E7EA', '#F6C49A', '#EE8A3C', '#B5520B']
export function divColor(v, absMax) {
  if (v === undefined || v === null) return '#E3E8ED'
  const t = absMax ? Math.max(-1, Math.min(1, v / absMax)) : 0
  return DIV[Math.round((t + 1) / 2 * (DIV.length - 1))]
}
export const SEQ_RAMP = `linear-gradient(90deg, ${SEQ.join(',')})`
export const DIV_RAMP = `linear-gradient(90deg, ${DIV.join(',')})`

function Tip({ active, payload, label, unit = '', digits = 1, labelFmt }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: '#fff', border: '1px solid #E7E2DB', borderRadius: 12, padding: '8px 12px',
      boxShadow: '0 12px 32px rgba(14,14,15,.10)', fontSize: 13 }}>
      <div style={{ fontWeight: 600, marginBottom: 4, color: '#0E0E0F' }}>{labelFmt ? labelFmt(label) : label}</div>
      {payload.filter((p) => p.value !== null && p.value !== undefined && !String(p.dataKey).startsWith('_')).map((p) => (
        <div key={p.dataKey} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: p.color || p.stroke || p.fill }} />
          <span style={{ color: '#6B6A70' }}>{p.name}:</span>
          <b>{Array.isArray(p.value) ? `${fmt(p.value[0], digits)}–${fmt(p.value[1], digits)}` : fmt(p.value, digits)}{unit}</b>
        </div>
      ))}
    </div>
  )
}

export function AnomalyChart({ data }) {
  const rows = data.map((d, i) => {
    const w = data.slice(Math.max(0, i - 9), i + 1)
    return { ...d, avg10: w.reduce((s, x) => s + x.anomaly, 0) / w.length }
  })
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={rows} margin={{ top: 10, right: 8, left: -14, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="year" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} interval={4} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="°" />
        <ReferenceLine y={0} stroke="#B5B0AA" />
        <Tooltip content={<Tip unit=" °C" digits={2} />} cursor={{ fill: 'rgba(11,46,89,.05)' }} />
        <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
        <Bar animationDuration={900} animationEasing="ease-out" dataKey="anomaly" name="Anomaly vs 1981–2010" fill="#F57C1F" radius={[3, 3, 0, 0]}>
          {rows.map((d) => <Cell key={d.year} fill={d.anomaly > 0 ? '#F57C1F' : '#1F6FB2'} />)}
        </Bar>
        <Line animationDuration={900} animationEasing="ease-out" dataKey="avg10" name="10-year average" stroke={NAVY} strokeWidth={2} dot={false} type="monotone" />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export function HotDaysChart({ observed, projection }) {
  const obs = observed.map((d) => ({ year: d.year, obs: d.hot35 }))
  const proj = (projection || []).map((d) => ({ year: d.year, proj: d.hot35 }))
  const rows = [...obs, ...proj]
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={rows} margin={{ top: 10, right: 8, left: -14, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="year" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} type="number"
          domain={['dataMin', 'dataMax']} tickCount={8} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip content={<Tip unit=" days" digits={1} />} />
        <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
        <Line animationDuration={900} animationEasing="ease-out" dataKey="obs" name="Observed (NASA POWER)" stroke="#F57C1F" strokeWidth={2} dot={false} connectNulls />
        <Line animationDuration={900} animationEasing="ease-out" dataKey="proj" name="Projected (NASA NEX-GDDP-CMIP6)" stroke={NAVY} strokeWidth={2} dot={false}
          strokeDasharray="6 4" connectNulls />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function YieldChart({ series, forecast, name, refName = 'Azerbaijan average' }) {
  const rows = series.map((s) => ({ year: s.year, y: s.yield, nat: s.nat_yield }))
  const last = rows.filter((r) => r.y).at(-1)
  for (const f of forecast || []) rows.push({ year: f.year, f: f.pred, band: [f.lo, f.hi] })
  if (last && forecast?.length) {
    const i = rows.findIndex((r) => r.year === last.year)
    rows[i] = { ...rows[i], f: last.y, band: [last.y, last.y] }
  }
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={rows} margin={{ top: 10, right: 8, left: -10, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="year" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip content={<Tip unit=" c/ha" />} />
        <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
        <Area animationDuration={900} animationEasing="ease-out" dataKey="band" name="Forecast range" fill="#F57C1F" fillOpacity={0.15} stroke="none" />
        <Line animationDuration={900} animationEasing="ease-out" dataKey="nat" name={refName} stroke="#B5B0AA" strokeWidth={2} dot={false} strokeDasharray="4 4" />
        <Line animationDuration={900} animationEasing="ease-out" dataKey="y" name={name} stroke={NAVY} strokeWidth={2} dot={{ r: 3 }} connectNulls />
        <Line animationDuration={900} animationEasing="ease-out" dataKey="f" name="Forecast" stroke="#F57C1F" strokeWidth={2} strokeDasharray="6 4" dot={{ r: 4 }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export function MultiLine({ rows, keys, unit = '', height = 320, refKey, refName }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 10, right: 8, left: -10, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="year" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip content={<Tip unit={unit} />} />
        <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
        {refKey && <Line animationDuration={900} animationEasing="ease-out" dataKey={refKey} name={refName} stroke="#B5B0AA" strokeWidth={2} dot={false} strokeDasharray="4 4" />}
        {keys.map((k, i) => <Line key={k.key} dataKey={k.key} name={k.name} stroke={CAT[i % CAT.length]} strokeWidth={2}
          dot={false} connectNulls />)}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function MonthlyChart({ rows }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={rows} margin={{ top: 10, right: 8, left: -10, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="m" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="°" />
        <Tooltip content={<Tip unit=" °C" />} />
        <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
        <Line animationDuration={900} animationEasing="ease-out" dataKey="p" name="1981–2010" stroke={CAT[1]} strokeWidth={2} dot={false} />
        <Line animationDuration={900} animationEasing="ease-out" dataKey="n" name="2016–2025" stroke={CAT[0]} strokeWidth={2} dot={{ r: 3 }} />
        <Line animationDuration={900} animationEasing="ease-out" dataKey="f" name="2041–2050 (NEX-GDDP-CMIP6)" stroke={NAVY} strokeWidth={2} strokeDasharray="6 4" dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export function HBars({ rows, valueKey, labelKey, unit = '', color = '#F2561D', height }) {
  return (
    <ResponsiveContainer width="100%" height={height || Math.max(200, rows.length * 30)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 24, left: 10, bottom: 0 }} barCategoryGap={4}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey={labelKey} tick={AXIS} tickLine={false} axisLine={false} width={130} />
        <Tooltip content={<Tip unit={unit} digits={1} />} cursor={{ fill: 'rgba(11,46,89,.05)' }} />
        <Bar animationDuration={900} animationEasing="ease-out" dataKey={valueKey} name={unit.trim() || valueKey} fill={color} fillOpacity={0.85} barSize={12} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

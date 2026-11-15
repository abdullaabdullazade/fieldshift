import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const P = {
  pin: <><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></>,
  sat: <><rect x="9" y="9" width="6" height="6" rx="1" /><path d="M3 7l4 4M7 3l4 4M13 17l4 4M17 13l4 4M15 9l2-2M9 15l-2 2" /></>,
  brain: <><path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 3 3h0V4z" /><path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-3 3V4z" /></>,
  sprout: <><path d="M12 20v-8" /><path d="M12 12c0-4 3-6 7-6 0 4-3 6-7 6z" /><path d="M12 14c0-3-2.5-5-6-5 0 3 2.5 5 6 5z" /></>,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
  bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21a2 2 0 0 0 4 0" /></>,
  chart: <><path d="M3 3v18h18" /><rect x="7" y="12" width="3" height="6" /><rect x="12" y="8" width="3" height="10" /><rect x="17" y="5" width="3" height="13" /></>,
  thermo: <><path d="M14 14.8V4a2 2 0 0 0-4 0v10.8a4 4 0 1 0 4 0z" /></>,
  drop: <><path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" /></>,
  snow: <><path d="M12 2v20M4.9 4.9l14.2 14.2M2 12h20M4.9 19.1L19.1 4.9" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  chev: <><path d="m6 9 6 6 6-6" /></>,
  check: <><path d="M20 6 9 17l-5-5" /></>,
  chat: <><path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-6.4A8 8 0 1 1 21 12z" /></>,
  users: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6" /></>,
  star: <><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z" /></>,
  phone: <><rect x="6" y="2" width="12" height="20" rx="2.5" /><path d="M11 18h2" /></>,
  map: <><path d="M9 3L3 6v15l6-3 6 3 6-3V3l-6 3-6-3z" /><path d="M9 3v15M15 6v15" /></>,
  menu: <><path d="M3 6h18M3 12h18M3 18h18" /></>,
  wind: <><path d="M3 8h11a3 3 0 1 0-3-3M3 16h15a3 3 0 1 1-3 3M3 12h7" /></>,
  plus: <><path d="M12 5v14M5 12h14" /></>,
  up: <><path d="M12 19V5M5 12l7-7 7 7" /></>,
  db: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>,
  leaf: <><path d="M5 19c0-9 6-14 15-14 0 9-5 15-14 15" /><path d="M5 19l7-7" /></>,
  fire: <path d="M12 22c4 0 7-2.8 7-7 0-3.5-2.3-6-4-8 .2 2-.6 3.5-2 4 0-3-1.5-6-4-8 .3 3-3 5.5-3 10 0 4.2 2.6 9 6 9z" />,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  play: <path d="M7 4.5v15l13-7.5z" fill="currentColor" stroke="none" />,
  pause: <><rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none" /><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none" /></>,
  alert: <><path d="M12 3.5 2.5 20h19z" /><path d="M12 10v4.5" /><circle cx="12" cy="17.3" r=".6" fill="currentColor" /></>,
  msg: <><path d="M4 4h16v12H8l-4 4z" /></>,
}

export function Icon({ n, s = 22, className = '', ...rest }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true" {...rest}>{P[n]}</svg>
  )
}

export function Title({ dark, orange, as: H = 'h2', kicker }) {
  return (
    <div>
      {kicker && <div className="kicker" style={{ marginBottom: 14 }}>{kicker}</div>}
      <H className="t"><span className="d">{dark}</span>{orange && <> <span className="o">{orange}</span></>}</H>
    </div>
  )
}

export function Stars({ value = 0, count }) {
  const v = Math.round(value || 0)
  return (
    <span className="stars" title={value ? `${Number(value).toFixed(2)} / 5` : 'No reviews yet'}>
      {[1, 2, 3, 4, 5].map((i) => <span key={i} className={i <= v ? '' : 'off'}>★</span>)}
      {count !== undefined && <span className="muted small" style={{ marginLeft: 6 }}>
        {value ? Number(value).toFixed(1) : '—'} ({count})</span>}
    </span>
  )
}

export function StarInput({ value, onChange }) {
  const [hover, setHover] = useState(0)
  return (
    <div className="stars-input" onMouseLeave={() => setHover(0)}>
      {[1, 2, 3, 4, 5].map((i) => (
        <button type="button" key={i} className={i <= (hover || value) ? 'on' : ''} aria-label={`${i} ulduz`}
          onMouseEnter={() => setHover(i)} onClick={() => onChange(i)}>★</button>
      ))}
    </div>
  )
}

export const DemoTag = () => <span className="tag demo" title="Sample profile for presentations, not a real person">Demo</span>

export const Spinner = () => <div className="spinner" role="status" aria-label="Loading" />
export const ErrorBox = ({ error }) => error ? <div className="err">{error.message || String(error)}</div> : null

export function Score({ v }) {
  return <div className="score" style={{ '--p': v }}><span>{v}</span></div>
}

export function Bar({ v, max = 100, cls = '' }) {
  return <div className={`bar ${cls}`}><i style={{ width: `${Math.max(0, Math.min(100, (v / max) * 100))}%` }} /></div>
}

export function CountUp({ v, ms = 1000 }) {
  const m = typeof v === 'number' ? [String(v), '', '', String(v), ''] : String(v ?? '').match(/^([^\d]*?)([+\-−]?)([\d,]+(?:\.\d+)?)(.*)$/s)
  const target = m ? parseFloat(m[3].replace(/,/g, '')) : null
  const dec = m && m[3].includes('.') ? m[3].split('.')[1].length : 0
  const ref = useRef(null)
  const [shown, setShown] = useState(target === null ? v : 0)
  useEffect(() => {
    if (target === null || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) { setShown(target ?? v); return undefined }
    let raf, start
    const run = () => {
      const tick = (t) => {
        start ??= t
        const k = Math.min(1, (t - start) / ms)
        setShown(target * (1 - Math.pow(1 - k, 3)))
        if (k < 1) raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)
    }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { run(); io.disconnect() } }, { threshold: 0.3 })
    if (ref.current) io.observe(ref.current)
    return () => { io.disconnect(); cancelAnimationFrame(raf) }
  }, [target, ms]) // eslint-disable-line react-hooks/exhaustive-deps
  if (target === null) return <span>{v}</span>
  const txt = Number(shown).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec })
  return <span ref={ref}>{m[1]}{m[2]}{txt}{m[4]}</span>
}

export function Stat({ v, l, cls = '' }) {
  return <div className={`stat ${cls}`}><div className="v num"><CountUp v={v} /></div><div className="l">{l}</div></div>
}

/* Field Shift mark: a river wave under a satellite, on the brand orange. Self-contained SVG (no wrapper styles). */
export function Logo({ s = 36, className = '' }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg className={`fs-logo ${className}`} width={s} height={s} viewBox="0 0 40 40" role="img" aria-label="Field Shift" style={{ flex: 'none', display: 'block' }}>
      <defs>
        <linearGradient id={`lg${id}`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#FF8A4C" /><stop offset="1" stopColor="#E5482D" /></linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#lg${id})`} />
      <rect x=".5" y=".5" width="39" height="39" rx="10.5" fill="none" stroke="rgba(255,255,255,.22)" />
      <circle cx="27" cy="12.5" r="3.6" fill="#fff" />
      <circle cx="27" cy="12.5" r="6.4" fill="none" stroke="#fff" strokeWidth="1.6" opacity=".45" />
      <path d="M8 24.5c3.2 0 3.2-3 6.4-3s3.2 3 6.4 3 3.2-3 6.4-3 3.2 3 4.8 3" fill="none" stroke="#fff" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8 30.5c3.2 0 3.2-3 6.4-3s3.2 3 6.4 3 3.2-3 6.4-3 3.2 3 4.8 3" fill="none" stroke="#fff" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" opacity=".5" />
    </svg>
  )
}

export function Modal({ children, onClose }) {
  // portal to <body>: page wrappers animate with transform, which would trap position:fixed inside them
  return createPortal(
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>, document.body)
}

/* ---------------------------------------------------------------- Select
   Custom listbox: button trigger, popup in a portal (never clipped by modals/cards), type-to-search,
   arrow keys / Enter / Escape, optional groups and right-aligned hints. options: [{ value, label, group?, hint? }] */
export function Select({ value, onChange, options, placeholder = 'Select…', label, size, searchable, style, id, width }) {
  const [open, setOpen] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [q, setQ] = useState('')
  const [act, setAct] = useState(0)
  const [pos, setPos] = useState(null)
  const btn = useRef(null), list = useRef(null), search = useRef(null)
  const uid = useId()
  const canSearch = searchable ?? options.length > 8
  const cur = options.find((o) => String(o.value) === String(value))
  const shown = useMemo(() => {
    const n = q.trim().toLowerCase()
    return n ? options.filter((o) => String(o.label).toLowerCase().includes(n) || String(o.group || '').toLowerCase().includes(n)) : options
  }, [q, options])

  const place = useCallback(() => {
    const r = btn.current?.getBoundingClientRect()
    if (!r) return
    const h = Math.min(360, 60 + options.length * 36)
    const below = window.innerHeight - r.bottom - 12
    const up = below < Math.min(h, 240) && r.top > below
    setPos({ left: r.left, width: Math.max(r.width, 220), top: up ? undefined : r.bottom + 6, bottom: up ? window.innerHeight - r.top + 6 : undefined,
      maxHeight: Math.max(180, up ? r.top - 18 : below) })
  }, [options.length])

  useLayoutEffect(() => { if (open) { place(); setMounted(true) } }, [open, place])
  useEffect(() => {
    if (open) return undefined
    const t = setTimeout(() => setMounted(false), 180)  // let the close animation finish
    return () => clearTimeout(t)
  }, [open])
  useEffect(() => {
    if (!open) return undefined
    const close = (e) => { if (!btn.current?.contains(e.target) && !list.current?.contains(e.target)) setOpen(false) }
    const re = () => place()
    document.addEventListener('mousedown', close)
    window.addEventListener('resize', re); window.addEventListener('scroll', re, true)
    setAct(Math.max(0, shown.findIndex((o) => String(o.value) === String(value))))
    setTimeout(() => (canSearch ? search.current : list.current)?.focus(), 0)
    return () => { document.removeEventListener('mousedown', close); window.removeEventListener('resize', re); window.removeEventListener('scroll', re, true) }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!open) setQ('') }, [open])
  useEffect(() => { setAct(0) }, [q])
  useEffect(() => { list.current?.querySelector(`[data-i="${act}"]`)?.scrollIntoView({ block: 'nearest' }) }, [act])

  const choose = (o) => { onChange(o.value); setOpen(false); btn.current?.focus() }
  const key = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setAct((a) => Math.min(shown.length - 1, a + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setAct((a) => Math.max(0, a - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (shown[act]) choose(shown[act]) }
    else if (e.key === 'Escape' || e.key === 'Tab') { setOpen(false); if (e.key === 'Escape') btn.current?.focus() }
  }
  let lastGroup = null
  return (
    <div className="sel" style={{ ...(width ? { width } : {}), ...style }}>
      <button type="button" id={id} ref={btn} className={`sel-btn ${size === 'sm' ? 'sm' : ''}`} aria-haspopup="listbox" aria-expanded={open}
        aria-controls={`${uid}-l`} aria-label={label} onClick={() => setOpen(!open)}
        onKeyDown={(e) => { if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key) && !open) { e.preventDefault(); setOpen(true) } }}>
        <span className={`v ${cur ? '' : 'ph'}`}>{cur ? cur.label : placeholder}</span>
        <Icon n="chev" s={16} className="chev" />
      </button>
      {mounted && pos && createPortal(
        <div className={`sel-pop ${open ? '' : 'out'} ${pos.bottom !== undefined ? 'up' : ''}`} style={{ left: pos.left, top: pos.top, bottom: pos.bottom, width: pos.width, maxHeight: pos.maxHeight }} ref={list} tabIndex={-1} onKeyDown={key}>
          {canSearch && <input ref={search} className="sel-search" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search options" />}
          <div className="sel-list" role="listbox" id={`${uid}-l`} aria-label={label}>
            {shown.map((o, i) => {
              const head = o.group && o.group !== lastGroup ? <div className="sel-group" key={`g-${o.group}`}>{o.group}</div> : null
              lastGroup = o.group
              const on = String(o.value) === String(value)
              return [head, (
                <div key={String(o.value)} data-i={i} role="option" aria-selected={on} className={`sel-opt ${i === act ? 'act' : ''} ${on ? 'on' : ''}`}
                  onMouseEnter={() => setAct(i)} onClick={() => choose(o)}>
                  <span className="tick">{on && <Icon n="check" s={16} />}</span>{o.label}{o.hint && <span className="hint">{o.hint}</span>}
                </div>)]
            })}
            {!shown.length && <div className="sel-none">No matches</div>}
          </div>
        </div>, document.body)}
    </div>
  )
}

/* Content swap: re-animates its children whenever `k` changes and dims stale content while new data loads. */
export function Swap({ k, loading, children }) {
  return <div key={k} className={`swap ${loading ? 'stale' : ''}`}>{children}</div>
}

export function Seg({ value, onChange, options, label }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map(([v, l]) => <button type="button" key={String(v)} role="radio" aria-checked={value === v} className={value === v ? 'on' : ''} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  )
}

export function Switch({ checked, onChange, children }) {
  return (
    <label className="switch"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /><span className="tr" />{children}</label>
  )
}

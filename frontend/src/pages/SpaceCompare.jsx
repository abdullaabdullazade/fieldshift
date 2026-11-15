import { useMemo, useRef, useState } from 'react'
import { MONTHS } from '../lib.jsx'
import { Select, Seg } from '../ui.jsx'
import { useGeo } from './MapPage.jsx'

// "Then vs now from space": the same place, same month, two years apart, straight from NASA GIBS (WMS GetMap).
const WMS = 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi'
const LAYERS = {
  ndvi: { layer: 'MODIS_Terra_L3_NDVI_Monthly', fmt: 'image/png', first: 2001, day: '01',
    label: 'Vegetation (MODIS Terra NDVI, monthly)' },
  rgb: { layer: 'MODIS_Terra_CorrectedReflectance_TrueColor', fmt: 'image/jpeg', first: 2001, day: '15',
    label: 'True colour (MODIS Terra, one day)' },
}

function bounds(geom) {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90
  const walk = (c) => (typeof c[0] === 'number'
    ? (x0 = Math.min(x0, c[0]), x1 = Math.max(x1, c[0]), y0 = Math.min(y0, c[1]), y1 = Math.max(y1, c[1]))
    : c.forEach(walk))
  walk(geom.coordinates)
  return [x0, y0, x1, y1]
}

export default function SpaceCompare({ r }) {
  const geo = useGeo(r.iso3 && r.iso3 !== 'AZE' ? `country/${r.iso3}` : 'country/AZE')
  const feat = geo?.features.find((f) => (f.properties.id || f.properties.iso3) === r.id)
  const latest = r.satellite?.ndvi?.date ? new Date(r.satellite.ndvi.date) : new Date(Date.now() - 45 * 864e5)
  const [kind, setKind] = useState('ndvi')
  const [month, setMonth] = useState(latest.getUTCMonth() + 1)
  const nowYear = month <= latest.getUTCMonth() + 1 ? latest.getUTCFullYear() : latest.getUTCFullYear() - 1
  const [past, setPast] = useState(2001)
  const [cut, setCut] = useState(50)
  const box = useRef(null)
  const L = LAYERS[kind]

  // frame: the unit's polygon (or a box around its centre), padded, with the right aspect for its latitude
  const frame = useMemo(() => {
    let [x0, y0, x1, y1] = feat ? bounds(feat.geometry) : [r.lon - 0.3, r.lat - 0.25, r.lon + 0.3, r.lat + 0.25]
    const k = Math.cos(((y0 + y1) / 2) * Math.PI / 180)
    let w = (x1 - x0) * k, h = y1 - y0
    const pad = Math.max(w, h) * 0.08
    w += 2 * pad; h += 2 * pad
    if (w < h * 1.3) w = h * 1.3                       // landscape frame
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2
    const bb = [cx - w / 2 / k, cy - h / 2, cx + w / 2 / k, cy + h / 2]
    const W = 900, H = Math.round(W * h / w)
    return { bb, W, H }
  }, [feat, r.lat, r.lon])

  const outline = useMemo(() => {
    if (!feat) return ''
    const [x0, y0, x1, y1] = frame.bb
    const px = ([x, y]) => `${((x - x0) / (x1 - x0) * frame.W).toFixed(1)},${((y1 - y) / (y1 - y0) * frame.H).toFixed(1)}`
    const rings = feat.geometry.type === 'Polygon' ? feat.geometry.coordinates : feat.geometry.coordinates.flat()
    return rings.map((ring) => 'M' + ring.map(px).join('L') + 'Z').join('')
  }, [feat, frame])

  const url = (year) => `${WMS}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=${L.layer}&STYLES=&SRS=EPSG:4326` +
    `&BBOX=${frame.bb.map((v) => v.toFixed(4)).join(',')}&WIDTH=${frame.W}&HEIGHT=${frame.H}&FORMAT=${encodeURIComponent(L.fmt)}` +
    `&TRANSPARENT=TRUE&TIME=${year}-${String(month).padStart(2, '0')}-${L.day}`
  const years = []
  for (let y = L.first; y < nowYear; y++) years.push({ value: y, label: String(y) })
  const drag = (e) => {
    const el = box.current
    if (!el) return
    const x = (e.touches ? e.touches[0].clientX : e.clientX) - el.getBoundingClientRect().left
    setCut(Math.max(0, Math.min(100, (x / el.clientWidth) * 100)))
  }

  return (
    <div className="card">
      <div className="between"><h3>Then vs now, from space</h3><span className="xs muted">NASA GIBS · drag the line to compare</span></div>
      <div className="row" style={{ marginTop: 12, gap: 10, flexWrap: 'wrap' }}>
        <Seg value={kind} onChange={setKind} label="Image" options={[['ndvi', 'Vegetation'], ['rgb', 'True colour']]} />
        <Select value={month} onChange={setMonth} width={130} label="Month"
          options={MONTHS.map((m, i) => ({ value: i + 1, label: m }))} />
        <Select value={past} onChange={setPast} width={110} label="Past year" options={years} />
        <span className="small muted">vs <b>{MONTHS[month - 1]} {nowYear}</b></span>
      </div>
      <div ref={box} className="swipe" style={{ aspectRatio: `${frame.W} / ${frame.H}` }}
        onMouseMove={(e) => e.buttons === 1 && drag(e)} onMouseDown={drag} onTouchStart={drag} onTouchMove={drag}>
        <img src={url(nowYear)} alt={`${r.name} ${MONTHS[month - 1]} ${nowYear}`} loading="lazy" />
        <div className="swipe-past" style={{ clipPath: `inset(0 ${100 - cut}% 0 0)` }}>
          <img src={url(past)} alt={`${r.name} ${MONTHS[month - 1]} ${past}`} loading="lazy" />
        </div>
        {outline && <svg viewBox={`0 0 ${frame.W} ${frame.H}`} preserveAspectRatio="none"><path d={outline} /></svg>}
        <div className="swipe-line" style={{ left: `${cut}%` }}><span /></div>
        <b className="swipe-tag l">{past}</b><b className="swipe-tag r">{nowYear}</b>
      </div>
      <p className="xs faint" style={{ marginTop: 8 }}>{L.label}. {kind === 'ndvi'
        ? 'Darker green = denser, healthier vegetation; brown = bare or dry land. Same month in both years, so seasons do not mislead.'
        : 'A single day (15th of the month): clouds or snow on that day can hide the ground; try another year or month.'}
        {' '}Outline: {r.level === 'province' ? 'province' : 'district'} boundary.</p>
    </div>
  )
}

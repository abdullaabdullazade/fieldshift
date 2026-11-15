import { useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, WMSTileLayer, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { Link, useSearchParams } from 'react-router-dom'
import { DIV_RAMP, SEQ_RAMP, divColor, seqColor } from '../charts.jsx'
import { api, fmt, sign, useApi, useCatalog } from '../lib.jsx'
import { Icon, Select, Seg, Spinner, Stars, Swap, Title } from '../ui.jsx'

// where: which views a layer makes sense in (az = Azerbaijan districts, country = provinces, world = countries)
export const LAYERS = [
  { id: 'suitability', label: 'Crop suitability (now)', crop: true, irr: true, g: 'Crops' },
  { id: 'suit_change', label: 'Suitability change by 2041–50', crop: true, irr: true, div: true, g: 'Crops' },
  { id: 'yield', label: 'Yield (official)', crop: true, year: true, g: 'Crops', where: ['az', 'world'] },
  { id: 'production', label: 'Production (official)', crop: true, year: true, g: 'Crops', where: ['az', 'world'] },
  { id: 'warming', label: 'Warming since 1980s', div: true, g: 'Climate change' },
  { id: 'hot35', label: 'Change in days >35°C', div: true, g: 'Climate change' },
  { id: 'frost', label: 'Change in frost days', div: true, g: 'Climate change' },
  { id: 'precip', label: 'Change in annual rainfall', div: true, g: 'Climate change' },
  { id: 'ph', label: 'Soil pH (0–30 cm)', g: 'Soil' },
  { id: 'soc', label: 'Soil organic carbon', g: 'Soil' },
  { id: 'ndvi_anom', label: 'Vegetation vs normal (MODIS NDVI change)', div: true, g: 'NASA satellite (now)' },
  { id: 'ndvi', label: 'Vegetation index (MODIS NDVI)', g: 'NASA satellite (now)' },
  { id: 'smap', label: 'Root-zone soil moisture (SMAP)', g: 'NASA satellite (now)' },
  { id: 'smap_anom', label: 'Soil moisture vs normal (SMAP)', div: true, g: 'NASA satellite (now)' },
  { id: 'rain7', label: 'Rain, last 7 days (GPM IMERG)', g: 'NASA satellite (now)' },
  { id: 'rating', label: 'Buyer rating of farmers', g: 'Community', where: ['az', 'country'] },
  { id: 'farmers', label: 'Registered farmers', g: 'Community', where: ['az', 'country'] },
]

const geoCache = new Map()   // small LRU: browsing many countries must not keep every outline in memory
export function useGeo(key = 'country/AZE') {
  const [geo, setGeo] = useState(geoCache.get(key) || null)
  useEffect(() => {
    let alive = true
    const hit = geoCache.get(key)
    if (hit) { geoCache.delete(key); geoCache.set(key, hit); setGeo(hit); return }
    setGeo(null)
    fetch(`/api/geo/${key}`).then((r) => r.json()).then((g) => {
      geoCache.set(key, g)
      while (geoCache.size > 4) geoCache.delete(geoCache.keys().next().value)
      if (alive) setGeo(g)
    }).catch(() => {})
    return () => { alive = false }
  }, [key])
  return geo
}

const fid = (f) => f.properties.id || f.properties.iso3
const NEAR_BOUNDS = [[28, 20], [58, 118]]
const WORLD_BOUNDS = [[-48, -165], [74, 178]]

function Fit({ geo, view }) {
  const map = useMap()
  useEffect(() => {
    if (!geo) return
    if (view === 'near') map.fitBounds(NEAR_BOUNDS, { animate: true })
    else if (view === 'world') map.fitBounds(WORLD_BOUNDS, { animate: true })
    else map.fitBounds(L.geoJSON(geo).getBounds(), { padding: [12, 12], animate: true, maxZoom: 9 })
  }, [geo, view, map])
  return null
}

export default function MapPage() {
  const [sp, setSp] = useSearchParams()
  const view = sp.get('view') || 'az'                     // az | near | world
  const country = view === 'az' ? null : (sp.get('c') || null)   // drilled-in country (ISO3)
  const level = view === 'az' ? 'az' : country ? 'country' : 'world'
  const avail = LAYERS.filter((l) => !l.where || l.where.includes(level))
  const layer = avail.find((l) => l.id === sp.get('layer'))?.id || 'suitability'
  const crop = sp.get('crop') || 'bugda'
  const irrigated = sp.get('irr') !== '0'
  const year = sp.get('year') || ''
  const Lr = LAYERS.find((l) => l.id === layer)
  const set = (patch) => {
    const n = new URLSearchParams(sp)
    Object.entries(patch).forEach(([k, v]) => (v === '' || v === null ? n.delete(k) : n.set(k, v)))
    setSp(n, { replace: true })
  }
  const { crops } = useCatalog()
  const { data: countries } = useApi('/countries')
  const geoKey = level === 'az' ? 'country/AZE' : level === 'country' ? `country/${country}` : 'world'
  const geo = useGeo(geoKey)
  const scope = level === 'az' ? 'AZE' : level === 'country' ? country : 'world'
  const q = `/map?scope=${scope}&layer=${layer}&crop=${crop}&irrigated=${irrigated}${year && Lr.year ? `&year=${year}` : ''}`
  const { data } = useApi(q)
  const [sel, setSel] = useState(null)
  const [detail, setDetail] = useState(null)
  const { data: sat } = useApi('/satellite')
  const overlayId = sp.get('sat') || ''
  const overlay = sat?.overlays.find((o) => o.id === overlayId)
  const [opacity, setOpacity] = useState(0.85)
  useEffect(() => { setSel(null); setDetail(null) }, [geoKey])
  useEffect(() => {
    if (!sel) return
    setDetail(null)
    ;(level === 'world' ? api(`/countries/${sel}`) : api(`/rayons/${sel}`)).then(setDetail).catch(() => setDetail(null))
  }, [sel, level])

  const vals = useMemo(() => data?.values || {}, [data])
  const nums = Object.values(vals).filter((v) => v !== null)
  const min = Math.min(...nums), max = Math.max(...nums)
  // robust colour scale: 95th percentile of |value| so a few extreme polygons don't wash out the rest
  const absSorted = nums.map(Math.abs).sort((a, b) => a - b)
  const absMax = Math.max(absSorted[Math.floor(absSorted.length * 0.95)] ?? 0, 0.0001)
  const mag = Math.max(...nums.map(Math.abs), 0)
  const dg = mag < 1 ? 3 : mag < 10 ? 2 : 1
  const fv = (v) => fmt(v, dg)
  const color = (id) => (Lr.div ? divColor(vals[id], absMax) : seqColor(vals[id], min, max))
  const gj = useRef(null)
  const live = useRef({})
  live.current = { color, sel, view, overlay: !!overlay }
  const styleOf = (f) => {
    const { color: c, sel: s, view: v, overlay: ov } = live.current
    const id = fid(f)
    const dim = v === 'near' && !country && !['near', 'home'].includes(f.properties.group)
    if (ov) return { fillColor: '#000', fillOpacity: id === s ? 0.12 : 0, weight: id === s ? 2.5 : 1, color: id === s ? '#F2561D' : '#FFFFFF', opacity: 0.85 }
    return { fillColor: c ? c(id) : '#E3E8ED', weight: id === s ? 2.5 : 0.7, color: id === s ? '#0E0E0F' : '#FAF6F1',
      fillOpacity: dim ? 0.25 : 0.9 }
  }
  useEffect(() => {
    gj.current?.eachLayer((lyr) => {
      const f = lyr.feature, v = vals[fid(f)]
      lyr.setStyle(styleOf(f))
      lyr.setTooltipContent(`<b>${f.properties.name}</b><br>${v !== undefined ? fv(v) + ' ' + (data?.unit || '') : 'no data'}`)
    })
  }, [data, sel, geo, view, overlayId, sat]) // eslint-disable-line react-hooks/exhaustive-deps
  const names = useMemo(() => Object.fromEntries((geo?.features || []).map((f) => [fid(f), f.properties.name])), [geo])
  const rankable = useMemo(() => {
    let e = Object.entries(vals)
    if (view === 'near' && !country && countries) {
      const near = new Set(countries.filter((c) => c.grp !== 'world').map((c) => c.iso3))
      e = e.filter(([k]) => near.has(k))
    }
    return e.sort((a, b) => b[1] - a[1])
  }, [vals, view, country, countries])
  const cropName = crops.find((c) => c.id === crop)?.name
  const cropOpts = crops.filter((c) => !(layer.startsWith('suit') && !c.eco))
  const cname = country && (countries || []).find((c) => c.iso3 === country)?.name
  const unitWord = level === 'world' ? 'countries' : level === 'country' ? 'provinces' : 'districts'
  const open = (id) => {
    if (level === 'world') { if (id === 'AZE') set({ view: 'az', c: '' }); else set({ c: id }) }
    else setSel(id)
  }
  const maxYear = level === 'world' ? 2024 : 2025

  return (
    <>
      <div className="section-head" style={{ marginTop: 0 }}>
        <Title dark={level === 'az' ? 'District map.' : level === 'country' ? `${cname || country}.` : view === 'near' ? 'Near Azerbaijan.' : 'World map.'}
          orange={level === 'az' ? 'Real data per polygon.' : level === 'country' ? 'Province by province.' : 'Country by country.'} />
        <Seg label="View" value={view} onChange={(v) => set({ view: v, c: '' })}
          options={[['az', 'Azerbaijan'], ['near', 'Near Azerbaijan'], ['world', 'World']]} />
      </div>
      {level !== 'az' && (
        <div className="row small" style={{ marginBottom: 14 }}>
          <button className="chip" onClick={() => set({ c: '' })}>{view === 'near' ? 'Near Azerbaijan' : 'World'}</button>
          {country && <><Icon n="chev" s={14} style={{ transform: 'rotate(-90deg)' }} /><span className="b">{cname || country}</span></>}
          <span className="muted" style={{ marginLeft: 8 }}>
            {level === 'world' ? 'Click a country to open its provinces.' : 'Click a province for its profile, crops, climate and weather.'}</span>
        </div>
      )}
      <div className="map-shell">
        <aside className="card stack">
          <div>
            <label className="f">Layer</label>
            <Select id="layer" label="Layer" value={layer} onChange={(v) => set({ layer: v })} searchable={false}
              options={avail.map((l) => ({ value: l.id, label: l.id === 'yield' && level === 'world' ? 'Yield (FAOSTAT)' : l.id === 'production' && level === 'world' ? 'Production (FAOSTAT)' : l.label, group: l.g }))} />
          </div>
          {Lr.crop && <div>
            <label className="f">Crop</label>
            <Select id="crop" label="Crop" value={crop} onChange={(v) => set({ crop: v })}
              options={cropOpts.map((c) => ({ value: c.id, label: c.name, group: c.grp }))} />
          </div>}
          {Lr.year && <div>
            <label className="f">Year</label>
            <Select id="year" label="Year" value={String(year || data?.year || '')} onChange={(v) => set({ year: v })}
              options={Array.from({ length: 26 }, (_, i) => maxYear - i).map((y) => ({ value: String(y), label: String(y) }))} />
          </div>}
          {Lr.irr && <Seg label="Water" value={irrigated ? '1' : '0'} onChange={(v) => set({ irr: v })} options={[['1', 'Irrigated'], ['0', 'Rain-fed']]} />}
          <div>
            <label className="f">NASA satellite image</label>
            <Select label="NASA satellite image" value={overlayId} onChange={(v) => set({ sat: v })} searchable={false}
              options={[{ value: '', label: 'Off (data layer only)' }, ...[...(sat?.overlays || [])].sort((a, b) => !!a.nrt - !!b.nrt).map((o) => ({ value: o.id, label: o.label, hint: o.date,
                group: o.nrt ? 'Near real time (hours old)' : 'Latest daily / monthly' }))]} />
            {overlay && <div style={{ marginTop: 8 }}>
              <input type="range" min="0.2" max="1" step="0.05" value={opacity} onChange={(e) => setOpacity(+e.target.value)} aria-label="Image opacity" style={{ width: '100%', accentColor: 'var(--or)' }} />
              {overlay.legend && <img src={overlay.legend} alt={`${overlay.label} legend`} style={{ width: '100%', marginTop: 4 }} />}
              {overlay.points && <div className="xs" style={{ marginTop: 4 }}><span className="fire-dot" /> fire detection, bigger = stronger · <span className="fire-dot grey" /> same spot on 3+ days: likely gas flare / industry</div>}
              <div className="xs muted">{overlay.wms ? overlay.attribution : overlay.points ? 'NASA FIRMS (VIIRS + MODIS)' : 'NASA GIBS'} · {overlay.date} · polygons show outlines only</div>
            </div>}
          </div>
          <div>
            <div className="legend"><span className="num">{nums.length ? fv(Lr.div ? -absMax : min) : ''}</span>
              <span className="ramp" style={{ background: Lr.div ? DIV_RAMP : SEQ_RAMP }} />
              <span className="num">{nums.length ? fv(Lr.div ? absMax : max) : ''}</span></div>
            <div className="xs muted" style={{ marginTop: 4 }}>{data?.unit}{data?.year ? ` · ${data.year}` : ''}{data?.source ? ` · ${data.source}` : ''}
              {level === 'world' && !data?.source ? ' · country mean of provinces' : ''} · grey = no data</div>
          </div>
          {sel && detail ? (
            <Swap k={sel}>{level === 'world' ? <CountryCard c={detail} v={vals[sel]} fv={fv} unit={data?.unit} onClose={() => setSel(null)} onOpen={() => open(sel)} />
              : <UnitCard d={detail} id={sel} v={vals[sel]} fv={fv} unit={data?.unit} onClose={() => setSel(null)} />}</Swap>
          ) : (
            <div>
              <div className="xs muted">Top 5 {unitWord}{Lr.crop ? ` · ${cropName}` : ''}</div>
              {rankable.slice(0, 5).map(([id, v], i) => (
                <button key={id} onClick={() => setSel(id)} className="rank-row">
                  <span><span className="faint num" style={{ display: 'inline-block', width: 20 }}>{i + 1}</span>{names[id] || id}</span><b className="num">{fv(v)}</b></button>))}
              {rankable.length > 5 && <>
                <div className="xs muted" style={{ marginTop: 16 }}>Lowest 3</div>
                {rankable.slice(-3).reverse().map(([id, v]) => (
                  <button key={id} onClick={() => setSel(id)} className="rank-row">
                    <span>{names[id] || id}</span><b className="num">{fv(v)}</b></button>))}
              </>}
            </div>
          )}
        </aside>
        <div className="map-box">
          {!geo ? <Spinner /> : (
            <MapContainer center={[40.3, 47.7]} zoom={6} minZoom={2} preferCanvas worldCopyJump style={{ height: '100%' }} scrollWheelZoom>
              {sat?.base && <TileLayer className="nasa-base" opacity={0.2} attribution="Base map: NASA GIBS (OSM land/water, ODbL)" url={sat.base.land} maxNativeZoom={9} maxZoom={16} />}
              {overlay?.url && <TileLayer key={overlay.id + overlay.date} url={overlay.url} maxNativeZoom={overlay.maxNativeZoom} maxZoom={16}
                opacity={opacity} attribution="Imagery: NASA GIBS / EOSDIS" />}
              {overlay?.wms && <WMSTileLayer key={overlay.id + overlay.date} url={overlay.wms.url} layers={overlay.wms.layers} format="image/png"
                transparent version="1.3.0" params={{ time: overlay.wms.time }} opacity={opacity} attribution={overlay.attribution} />}
              <Fit geo={geo} view={level === 'world' ? view : 'fit'} />
              <GeoJSON key={geoKey} ref={gj} data={geo} style={styleOf} onEachFeature={(f, lyr) => {
                lyr.bindTooltip('', { sticky: true, className: 'rt' })
                lyr.on('click', () => setSel(fid(f)))
                lyr.on('dblclick', () => open(fid(f)))
                lyr.on('mouseover', () => lyr.setStyle({ weight: 2, color: '#0E0E0F' }))
                lyr.on('mouseout', () => lyr.setStyle(styleOf(f)))
              }} />
              {overlay?.points && <FirePoints opacity={opacity} />}
            </MapContainer>
          )}
        </div>
      </div>
      <p className="src">{level === 'az'
        ? 'Boundaries: geoBoundaries ADM2 (CC BY-SA 3.0). Ağdərə has no separate polygon (merged into neighbours) but has data on its page.'
        : 'Boundaries: geoBoundaries ADM1 (gbOpen). Climate: NASA POWER per province; projections: NASA NEX-GDDP-CMIP6; soil: SoilGrids; yields: FAOSTAT (country level).'}
        {' '}Base map: NASA GIBS (OpenStreetMap land/water, ODbL).</p>
    </>
  )
}

// NASA FIRMS detections in the visible box, reloaded after every pan / zoom
function FirePoints({ opacity }) {
  const [pts, setPts] = useState(null)
  const map = useMap()
  const load = () => {
    const b = map.getBounds()
    api(`/fires?s=${b.getSouth().toFixed(2)}&w=${b.getWest().toFixed(2)}&n=${b.getNorth().toFixed(2)}&e=${b.getEast().toFixed(2)}`)
      .then(setPts).catch(() => setPts(null))
  }
  useMapEvents({ moveend: load })
  useEffect(load, []) // eslint-disable-line react-hooks/exhaustive-deps
  if (!pts) return null
  return pts.points.map((p, i) => (
    <CircleMarker key={i} center={[p.lat, p.lon]} radius={Math.min(3 + Math.sqrt(p.frp || 0) / 2, 11)} interactive
      pathOptions={p.days >= 3 ? { color: '#3A3A3A', weight: 0.8, fillColor: '#8A8F98', fillOpacity: opacity * 0.8, opacity }
        : { color: '#7A1B00', weight: 0.8, fillColor: '#FF3B0A', fillOpacity: opacity, opacity }}>
      <Tooltip className="rt">{p.sat} · {p.acq.slice(0, 10)} {p.acq.slice(11, 16)} UTC<br />power {p.frp} MW · {p.conf} confidence
        {p.days >= 3 && <><br />seen on {p.days} of the last 10 days: likely gas flare / industry</>}</Tooltip>
    </CircleMarker>))
}

function UnitCard({ d, id, v, fv, unit, onClose }) {
  const province = d.level === 'province'
  return (
    <div className="card tight" style={{ background: 'var(--fog)', border: 0 }}>
      <div className="between"><h3>{d.name}</h3><button className="chip" onClick={onClose} aria-label="Close">✕</button></div>
      <div className="xs muted">{province ? `${d.econ} · province` : `${d.econ} economic region · ${d.name_az}`}</div>
      <div className="num" style={{ fontFamily: 'var(--display)', fontSize: 30, fontWeight: 500, letterSpacing: '-.03em', color: 'var(--ink)', marginTop: 8 }}>
        {v !== undefined ? fv(v) : '—'} <span className="small muted">{unit}</span></div>
      <div className="small" style={{ marginTop: 6 }}>Warming: <b>{sign(d.compare.tmean.delta)}°C</b>{d.soil ? <> · Soil pH <b>{fmt(d.soil.ph)}</b></> : null}</div>
      <div className="small">Farmers: <b>{d.farmers}</b> · <Stars value={d.rating.avg} count={d.rating.count} /></div>
      <Link to={`/r/${id}`} className="btn sm" style={{ marginTop: 12 }}>Open {province ? 'province' : 'district'} <Icon n="up" s={14} style={{ transform: 'rotate(90deg)' }} /></Link>
    </div>
  )
}

function CountryCard({ c, v, fv, unit, onClose, onOpen }) {
  return (
    <div className="card tight" style={{ background: 'var(--fog)', border: 0 }}>
      <div className="between"><h3>{c.name}</h3><button className="chip" onClick={onClose} aria-label="Close">✕</button></div>
      <div className="xs muted">{(c.subregion && c.subregion !== 'Undefined') ? c.subregion : c.continent} · {c.units.length} {c.iso3 === 'AZE' ? 'districts' : 'provinces'}{c.grp === 'near' ? ' · Near Azerbaijan' : ''}</div>
      <div className="num" style={{ fontFamily: 'var(--display)', fontSize: 30, fontWeight: 500, letterSpacing: '-.03em', color: 'var(--ink)', marginTop: 8 }}>
        {v !== undefined ? fv(v) : '—'} <span className="small muted">{unit}</span></div>
      <div className="small" style={{ marginTop: 6 }}>Warming: <b>{sign(c.compare.tmean.delta)}°C</b> · days &gt;35°C: <b>{sign(c.compare.hot35.delta, 0)}</b></div>
      {c.future?.t !== null && c.future?.t !== undefined && <div className="small">2041–50 mean: <b>{fmt(c.future.t)}°C</b> (now {fmt(c.compare.tmean.now)}°C)</div>}
      {c.top_crops?.length > 0 && <div className="xs muted" style={{ marginTop: 6 }}>Top crops ({c.stat_year}): {c.top_crops.slice(0, 4).map((t) => t.name).join(', ')}</div>}
      <button className="btn sm" style={{ marginTop: 12 }} onClick={onOpen}>{c.iso3 === 'AZE' ? 'Open districts' : 'Explore provinces'} <Icon n="up" s={14} style={{ transform: 'rotate(90deg)' }} /></button>
    </div>
  )
}

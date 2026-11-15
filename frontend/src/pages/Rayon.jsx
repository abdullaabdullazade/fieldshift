import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { HotDaysChart, MonthlyChart, YieldChart } from '../charts.jsx'
import { MONTHS, doy, fmt, fmt0, sign, useApi } from '../lib.jsx'
import { Bar, ErrorBox, Icon, Score, Seg, Spinner, Stars, Stat, Swap } from '../ui.jsx'
import { FarmerCard } from './Farmers.jsx'
import SpaceCompare from './SpaceCompare.jsx'

const TABS = [['overview', 'Overview'], ['crops', 'Crop recommendations'], ['yields', 'Yields & forecast'],
  ['climate', 'Climate'], ['weather', 'Live weather'], ['farmers', 'Farmers']]

export default function Rayon() {
  const { id } = useParams()
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'overview'
  const { data: r, error } = useApi(`/rayons/${id}`)
  if (error) return <ErrorBox error={error} />
  if (!r) return <Spinner />
  return (
    <>
      <div className="kicker">{r.level === 'province' ? <><Link to={`/map?view=world&c=${r.iso3}`}>{r.econ}</Link>&nbsp;· province</> : `${r.econ} economic region`}</div>
      <div className="between" style={{ marginTop: 12 }}>
        <h1 className="t" style={{ fontSize: 'clamp(36px,5vw,64px)' }}><span className="d">{r.name}</span></h1>
        <div className="row">
          <Stars value={r.rating.avg} count={r.rating.count} />
          <Link to={`/chat?rayon=${r.id}`} className="btn ghost sm"><Icon n="chat" s={16} />Ask AI about {r.name}</Link>
        </div>
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>{r.name_az} · {fmt(r.lat, 3)}°N {fmt(r.lon, 3)}°E{r.area_km2 ? ` · ≈${fmt0(r.area_km2)} km²` : ''}</p>
      <div className="tabs" style={{ marginTop: 22 }}>
        {TABS.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setSp({ tab: k }, { replace: true })}>{l}</button>)}
      </div>
      <Swap k={tab}>
      {tab === 'overview' && <Overview r={r} />}
      {tab === 'crops' && <Crops id={id} province={r.level === 'province'} country={r.econ} />}
      {tab === 'yields' && <Yields id={id} name={r.level === 'province' ? r.econ : r.name} province={r.level === 'province'} />}
      {tab === 'climate' && <Climate id={id} />}
      {tab === 'weather' && <Weather id={id} />}
      {tab === 'farmers' && <DistrictFarmers id={id} name={r.name} />}
      </Swap>
    </>
  )
}

function SatelliteNow({ s, fires: fr }) {
  const nd = s.ndvi, sm = s.smap, rn = s.rain7
  const ndA = nd?.normal ? (nd.value / nd.normal - 1) * 100 : null
  const smA = sm?.normal != null ? sm.value - sm.normal : null
  const word = (x, lo, hi) => (x == null ? '' : x < lo ? 'below normal' : x > hi ? 'above normal' : 'near normal')
  return (
    <div className="card">
      <div className="between"><h3>NASA satellites, now</h3><span className="xs muted">via NASA GIBS · refreshed twice a day</span></div>
      <div className="grid g4" style={{ marginTop: 12 }}>
        {nd && <div className="stat"><div className={`v num ${ndA < -8 ? 'red' : ndA > 8 ? 'green' : ''}`}>{fmt(nd.value, 2)}</div>
          <div className="l">Vegetation index (MODIS NDVI), {new Date(nd.date).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })}:
            {' '}<b>{sign(ndA, 0)}%</b> vs the same month of the last {nd.n_normal} years ({word(ndA, -8, 8)})</div></div>}
        {sm && <div className="stat blue"><div className="v num">{fmt(sm.value, 2)} <span className="small muted">m³/m³</span></div>
          <div className="l">Root-zone soil moisture (SMAP L4), {sm.date}: <b>{sign(smA, 2)}</b> vs the same day of {sm.n_normal} earlier years ({word(smA, -0.02, 0.02)})</div></div>}
        {rn && <div className="stat green"><div className="v num">{fmt(rn.value, 1)} <span className="small muted">mm</span></div>
          <div className="l">Rain in the last 7 days to {rn.date} (GPM IMERG satellite precipitation)</div></div>}
        {fr?.latest && <div className={`stat ${fr.count ? 'red' : 'green'}`}><div className="v num">{fr.count}</div>
          <div className="l">Active fires in the last 24 h within {fr.radius_km} km of the centre (NASA FIRMS, VIIRS + MODIS)
            {fr.count ? <>; nearest {fr.nearest_km} km, strongest {fmt(fr.max_frp, 0)} MW</> : ''}{fr.industrial ? ` (plus ${fr.industrial} at permanent industrial hot spots)` : ''}. Updated {fr.latest.slice(0, 16).replace('T', ' ')} UTC.
            {' '}<Link className="or b" to={fr.iso3 === 'AZE' ? '/map?view=az&sat=fires' : `/map?view=world&c=${fr.iso3}&sat=fires`}>See on map</Link></div></div>}
      </div>
    </div>
  )
}

function Overview({ r }) {
  const c = r.compare
  const rowsT = [
    ['Mean temperature', 'tmean', '°C', 1], ['Days above 35°C', 'hot35', 'days', 0], ['Frost days', 'frost', 'days', 0],
    ['Frost-free season', 'ffs', 'days', 0], ['Growing degree-days (Apr–Oct)', 'gdd', '°C·d', 0],
    ['Annual rainfall', 'precip', 'mm', 0], ['Root-zone soil wetness', 'gwetroot', '0–1', 2]]
  return (
    <div className="stack">
      <div className="grid g4">
        <Stat v={`${sign(c.tmean.delta)}°C`} l="warmer than 1981–1990" />
        <Stat v={sign(c.hot35.delta, 0)} l="more days above 35°C per year" />
        <Stat cls="blue" v={sign(c.frost.delta, 0)} l="change in frost days per year" />
        <Stat cls="green" v={`${doy(Math.round(c.last_frost.now))}`} l={`last spring frost (was ${doy(Math.round(c.last_frost.past))})`} />
      </div>
      {((r.satellite && Object.keys(r.satellite).length > 0) || r.fires?.latest) && <SatelliteNow s={r.satellite || {}} fires={{ ...r.fires, iso3: r.iso3 }} />}
      <SpaceCompare r={r} />
      <div className="grid g2">
        <div className="card">
          <h3>Past vs now (NASA POWER)</h3>
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr><th>Metric</th><th className="r">1981–1990</th><th className="r">2016–2025</th><th className="r">Change</th></tr></thead>
            <tbody>{rowsT.map(([l, k, u, d]) => (
              <tr key={k}><td>{l} <span className="faint xs">{u}</span></td><td className="r num">{fmt(c[k].past, d)}</td>
                <td className="r num">{fmt(c[k].now, d)}</td><td className="r num b">{sign(c[k].delta, d)}</td></tr>))}</tbody>
          </table></div>
          <div className="src">Daily MERRA-2 data at the district centre, averaged per decade.</div>
        </div>
        <div className="card">
          <h3>Soil (SoilGrids 2.0, 0–30 cm, district mean)</h3>
          <div className="grid g3" style={{ marginTop: 14 }}>
            <Stat cls="blue" v={fmt(r.soil.ph)} l="pH (H₂O)" />
            <Stat v={fmt(r.soil.soc)} l="Organic carbon, g/kg" />
            <Stat cls="green" v={fmt(r.soil.nitrogen, 2)} l="Nitrogen, g/kg" />
          </div>
          <div style={{ marginTop: 18 }}>
            <div className="small b">Texture: {r.soil.texture}</div>
            <div style={{ display: 'flex', height: 22, borderRadius: 8, overflow: 'hidden', marginTop: 8, gap: 2 }}>
              <div style={{ width: `${r.soil.clay}%`, background: '#C0540A' }} title="Clay" />
              <div style={{ width: `${r.soil.silt}%`, background: '#F9AE6E' }} title="Silt" />
              <div style={{ width: `${r.soil.sand}%`, background: '#FDD3AE' }} title="Sand" />
            </div>
            <div className="row xs muted" style={{ marginTop: 6 }}>
              <span>■ <b style={{ color: '#C0540A' }}>Clay</b> {fmt0(r.soil.clay)}%</span>
              <span>■ <b style={{ color: '#E08A3C' }}>Silt</b> {fmt0(r.soil.silt)}%</span>
              <span>■ <b style={{ color: '#C9975F' }}>Sand</b> {fmt0(r.soil.sand)}%</span>
              <span>CEC {fmt(r.soil.cec)} cmol/kg</span>
            </div>
          </div>
        </div>
      </div>
      <div className="card">
        <h3>{r.stat_scope === 'country' ? `Main crops in ${r.econ} (${r.stat_year}, FAOSTAT, country level)` : `Main crops in ${r.name} (${r.stat_year}, official)`}</h3>
        {r.top_crops.length ? <div className="tbl-wrap"><table className="tbl" style={{ marginTop: 10 }}>
          <thead><tr><th>Crop</th><th className="r">Production, t</th><th className="r">Yield, c/ha</th><th className="r">{r.stat_scope === 'country' ? 'World avg, c/ha' : 'National, c/ha'}</th><th className="r">{r.stat_scope === 'country' ? 'vs world' : 'vs national'}</th></tr></thead>
          <tbody>{r.top_crops.map((t) => (
            <tr key={t.crop_id}><td className="b">{t.name}</td><td className="r num">{fmt0(t.production)}</td><td className="r num">{fmt(t.yield)}</td>
              <td className="r num">{fmt(t.nat_yield)}</td>
              <td className={`r num b ${t.yield >= t.nat_yield ? 'green' : 'red'}`}>{t.nat_yield ? `${sign((t.yield / t.nat_yield - 1) * 100, 0)}%` : '—'}</td></tr>))}</tbody>
        </table></div> : <p className="muted">No production reported{r.stat_scope === 'country' ? ' in FAOSTAT' : ' for this district'}.</p>}
        <div className="src">Source: AzStat regional tables (stat.gov.az).</div>
      </div>
    </div>
  )
}

function Crops({ id, province, country }) {
  const [irr, setIrr] = useState(true)
  const { data, error, stamp, loading } = useApi(`/rayons/${id}/recommendations?irrigated=${irr}`)
  return (
    <div className="stack">
      <div className="between">
        <p className="muted" style={{ maxWidth: 760 }}>Score = 45% climate & soil suitability today (FAO ECOCROP on NASA climate
          + SoilGrids pH) + 35% {province ? `${country}'s FAOSTAT yield vs the world average (last 5 years, country level)` : "this district's real yield vs the national average (2021–2025)"} + 20% suitability in 2041–2050 (NASA NEX-GDDP-CMIP6).</p>
        <Seg label="Water" value={irr} onChange={setIrr} options={[[true, 'Irrigated'], [false, 'Rain-fed']]} />
      </div>
      <ErrorBox error={error} />
      {!data ? <Spinner /> : (
        <Swap k={stamp} loading={loading}><div className="grid g2">
          {data.map((c, i) => (
            <div key={c.crop_id} className="card tight row" style={{ flexWrap: 'nowrap', gap: 16, alignItems: 'flex-start', borderColor: i < 3 ? '#F6C4AE' : undefined }}>
              <Score v={c.score} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="between"><h3>{i + 1}. {c.name}</h3><span className="tag grey">{c.group}</span></div>
                <div className="grid g3" style={{ gap: 10, marginTop: 10 }}>
                  <div><div className="xs muted">Temperature</div><Bar v={c.temp} /></div>
                  <div><div className="xs muted">Rainfall</div><Bar v={c.rain} cls="navy" /></div>
                  <div><div className="xs muted">Soil pH</div><Bar v={c.ph} cls="green" /></div>
                </div>
                <div className="xs muted" style={{ marginTop: 8 }}>
                  Suitability {c.suit_past ?? '—'} (1981–2010) → <b>{c.suit_now}</b> now → {c.suit_2045 ?? 'n/a'} (2041–50)
                  {!c.perennial && c.best_month ? ` · sow from ${MONTHS[c.best_month - 1]}` : ''}
                </div>
                <div className="xs" style={{ marginTop: 4 }}>
                  {c.grown_here ? <span>{province ? `${country} yield` : 'Local yield'} <b>{fmt(c.yield_avg)} c/ha</b>, <b className={c.yield_rel >= 1 ? 'green' : 'red'}>{fmt0(c.yield_rel * 100)}%</b> of {province ? 'world average (FAOSTAT)' : 'national'}</span>
                    : <span className="faint">{province ? `No FAOSTAT record for ${country}: unproven in the country` : 'Not in official statistics for this district: unproven locally'}</span>}
                </div>
              </div>
            </div>))}
        </div></Swap>
      )}
    </div>
  )
}

function Yields({ id, name, province }) {
  const [crop, setCrop] = useState('')
  const { data, error, stamp, loading } = useApi(`/rayons/${id}/yields?crop=${crop || 'bugda'}`)
  useEffect(() => { if (data && !crop && data.crops.length && !data.crops.find((c) => c.id === 'bugda')) setCrop(data.crops[0].id) }, [data, crop])
  const m = data?.model
  return (
    <div className="stack">
      <ErrorBox error={error} />
      {!data ? <Spinner /> : (
        <>
          <div className="chips">{data.crops.map((c) => (
            <button key={c.id} className={`chip ${(crop || 'bugda') === c.id ? 'on' : ''}`} onClick={() => setCrop(c.id)}>{c.name}</button>))}</div>
          <Swap k={stamp} loading={loading}><div className="card">
            <h3>Yield in {name}{province ? ' (country level)' : ''}, centners per hectare</h3>
            {data.series.length ? <YieldChart series={data.series} forecast={data.forecast} name={name} refName={province ? 'World average (FAOSTAT)' : 'Azerbaijan average'} />
              : <p className="muted">No data.</p>}
            <div className="src">{province ? 'FAOSTAT country-level yields; province-level official yields are not published consistently outside Azerbaijan.' : 'Official yields: AzStat. Forecast for seasons not yet published.'}</div>
          </div>
          {m && (
            <div className="card">
              <h3>How good is this forecast?</h3>
              <p className="small muted" style={{ marginTop: 6 }}>Back-tested honestly: model chosen on 2016–2019, then scored on
                {' '}{m.n_test} district-years from 2020–2025 it never saw.</p>
              <div className="grid g4" style={{ marginTop: 14 }}>
                <Stat v={m.method === 'gbm_climate' ? 'Climate ML' : 'Persistence'} l="method that won validation" cls={m.method === 'gbm_climate' ? '' : 'blue'} />
                <Stat v={`${fmt(m.mae)} c/ha`} l="average error, 2020–2025" />
                <Stat cls="blue" v={`${fmt(m.baseline_mae)} c/ha`} l="error of 'same as last year'" />
                <Stat cls="green" v={`±${fmt0(m.rel_band * 100)}%`} l="range covering 80% of outcomes" />
              </div>
              <p className="note small" style={{ marginTop: 14 }}>
                {m.method === 'gbm_climate'
                  ? 'Gradient boosting on NASA growing-season anomalies (heat days, rainfall, soil wetness, frost) beat the naive baseline here.'
                  : 'For this crop, climate-based ML did not beat "next year ≈ this year" on validation, so we show the honest baseline with its measured error range instead of a fancier but worse model.'}
              </p>
            </div>
          )}
        </Swap></>
      )}
    </div>
  )
}

function Climate({ id }) {
  const { data, error } = useApi(`/rayons/${id}/climate`)
  if (error) return <ErrorBox error={error} />
  if (!data) return <Spinner />
  const by = (p) => data.monthly.filter((m) => m.period === p)
  const rows = MONTHS.map((m, i) => ({ m, p: by('1981-2010')[i]?.tmean, n: by('2016-2025')[i]?.tmean, f: by('2041-2050')[i]?.tmean }))
  const annual = data.annual.filter((a) => !a.partial)
  return (
    <div className="grid g2">
      <div className="card">
        <h3>Monthly mean temperature</h3>
        <MonthlyChart rows={rows} />
        <div className="src">NASA POWER; 2041–2050 from NASA NEX-GDDP-CMIP6 (SSP2-4.5, 5 models), delta-corrected to NASA POWER 1995–2014.</div>
      </div>
      <div className="card">
        <h3>Days above 35°C per year</h3>
        <HotDaysChart observed={annual} projection={data.projection} />
      </div>
      <div className="card" style={{ gridColumn: '1 / -1' }}>
        <h3>Monthly normals (table view)</h3>
        <div className="tbl-wrap"><table className="tbl" style={{ marginTop: 10 }}>
          <thead><tr><th>Period</th>{MONTHS.map((m) => <th key={m} className="r">{m}</th>)}</tr></thead>
          <tbody>
            {[['1981-2010', 'tmean', 'T mean °C', 1], ['2016-2025', 'tmean', 'T mean °C', 1], ['2041-2050', 'tmean', 'T mean °C', 1],
              ['2016-2025', 'tmin', 'T min °C', 1], ['2016-2025', 'precip', 'Rain mm', 0], ['2016-2025', 'gwetroot', 'Soil wetness', 2]].map(([p, k, l, d]) => (
              <tr key={p + k}><td className="b">{l} <span className="faint xs">{p}</span></td>{MONTHS.map((_, i) => <td key={i} className="r num">{fmt(by(p)[i]?.[k], d)}</td>)}</tr>))}
          </tbody>
        </table></div>
      </div>
    </div>
  )
}

export function WeatherStrip({ f }) {
  const d = f.daily
  const today = localToday()
  return (
    <div className="wx">
      {d.time.map((t, i) => {
        if (t < today || d.temperature_2m_max[i] === null) return null
        const risk = d.temperature_2m_min[i] <= 0 || d.temperature_2m_max[i] >= 35 || d.precipitation_sum[i] >= 20 || d.wind_gusts_10m_max[i] >= 60
        const dt = new Date(t)
        return (
          <div key={t} className={`d ${risk ? 'risk' : ''}`}>
            <div className="xs b muted">{dt.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}</div>
            <div className="hi num">{fmt0(d.temperature_2m_max[i])}°</div>
            <div className="lo num">{fmt0(d.temperature_2m_min[i])}°</div>
            <div className="xs">{d.sky?.[i]}</div>
            <div className="xs muted"><Icon n="drop" s={11} /> {fmt(d.precipitation_sum[i])} mm · {d.precipitation_probability_max[i] ?? '—'}%</div>
            <div className="xs muted"><Icon n="wind" s={11} /> {fmt0(d.wind_gusts_10m_max[i])} km/h</div>
          </div>)
      })}
    </div>
  )
}

export const localToday = () => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}` }

function Weather({ id }) {
  const { data: f, error } = useApi(`/rayons/${id}/forecast`)
  if (error) return <ErrorBox error={error} />
  if (!f) return <Spinner />
  const c = f.current
  const d = f.daily
  const today = localToday()
  const idx = d.time.map((t, i) => (t >= today && d.temperature_2m_max[i] !== null ? i : -1)).filter((i) => i >= 0)
  const frost = idx.filter((i) => d.temperature_2m_min[i] <= 0).length
  const hot = idx.filter((i) => d.temperature_2m_max[i] >= 35).length
  const rain = idx.slice(0, 7).reduce((s, i) => s + (d.precipitation_sum[i] || 0), 0)
  const et0 = idx.slice(0, 7).reduce((s, i) => s + (d.et0_fao_evapotranspiration[i] || 0), 0)
  return (
    <div className="stack">
      <div className="grid g5">
        <Stat v={`${fmt(c.temperature_2m)}°C`} l={`now · humidity ${c.relative_humidity_2m}%`} />
        <Stat cls="blue" v={frost} l="frost nights in 16 days" />
        <Stat v={hot} l="days ≥35°C in 16 days" />
        <Stat cls="green" v={`${fmt(rain)} mm`} l="rain, next 7 days" />
        <Stat cls="blue" v={`${fmt0(Math.max(0, et0 - rain))} mm`} l="7-day water deficit (ET₀ − rain)" />
      </div>
      <div className="card"><h3>16-day forecast</h3><div style={{ marginTop: 12 }}><WeatherStrip f={f} /></div>
        <div className="src">Open-Meteo best-match (ECMWF IFS, DWD ICON, NOAA GFS). Orange days carry frost, heat, heavy rain or wind risk.
          Updated {new Date(f.fetched_at * 1000).toLocaleTimeString('en-GB')}.</div></div>
    </div>
  )
}

function DistrictFarmers({ id, name }) {
  const { data, error } = useApi(`/farmers?rayon=${id}`)
  if (error) return <ErrorBox error={error} />
  if (!data) return <Spinner />
  return data.length ? <div className="grid g2">{data.map((u) => <FarmerCard key={u.id} u={u} />)}</div> : (
    <div className="card empty"><Icon n="users" s={36} /><p style={{ marginTop: 10 }}>No farmers from {name} yet.</p>
      <Link to="/account" className="btn" style={{ marginTop: 14 }}>Register your farm</Link></div>)
}

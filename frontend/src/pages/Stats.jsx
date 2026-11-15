import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CAT, HBars, MultiLine } from '../charts.jsx'
import { fmt, fmt0, sign, useApi, useCatalog } from '../lib.jsx'
import { ErrorBox, Select, Seg, Spinner, Stars, Stat, Swap, Title } from '../ui.jsx'

const CATS = ['Leader', 'Good', 'Average', 'Low']
const CAT_TXT = { Leader: 'Top 25%', Good: '25–50%', Average: '50–75%', Low: 'Bottom 25%: separate category' }

export default function Stats() {
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'regions'
  const crop = sp.get('crop') || 'bugda'
  const set = (o) => setSp({ tab, crop, ...o }, { replace: true })
  const { crops } = useCatalog()
  return (
    <>
      <div className="section-head" style={{ marginTop: 0 }}>
        <Title dark="Statistics." orange="Who grows what best." />
        <p className="muted" style={{ maxWidth: 480 }}>Official AzStat yields for every Azerbaijani district, 2000–2025, and FAOSTAT
          yields for every country. Most productive on top; the least productive shown as their own category.</p>
      </div>
      <div className="tabs">
        {[['regions', 'District leaderboard'], ['crop', 'Ranking by crop'], ['cropstats', 'Crop statistics'], ['compare', 'Compare districts'],
          ['world', 'World ranking'], ['countries', 'Compare countries']].map(([k, l]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => set({ tab: k })}>{l}</button>))}
      </div>
      {tab !== 'regions' && (
        <div className="row" style={{ marginBottom: 18 }}>
          <Select label="Crop" width={280} value={crop} onChange={(v) => set({ crop: v })}
            options={crops.map((c) => ({ value: c.id, label: c.name, group: c.grp }))} />
        </div>)}
      <Swap k={tab}>
        {tab === 'regions' && <Leaderboard />}
        {tab === 'crop' && <CropRanking crop={crop} />}
        {tab === 'cropstats' && <CropStats crop={crop} />}
        {tab === 'compare' && <Compare crop={crop} />}
        {tab === 'world' && <WorldRanking crop={crop} />}
        {tab === 'countries' && <CompareCountries crop={crop} />}
      </Swap>
    </>
  )
}

function Grouped({ rows, render, noun = 'districts' }) {
  return CATS.map((c) => {
    const rs = rows.filter((r) => r.category === c)
    if (!rs.length) return null
    return (
      <div key={c} className="card" style={{ marginBottom: 18, borderColor: c === 'Low' ? '#F3C1C1' : c === 'Leader' ? '#BFE3CD' : undefined }}>
        <div className="between"><h3><span className={`cat ${c}`}>{c}</span> <span className="small muted" style={{ marginLeft: 6 }}>{CAT_TXT[c]}</span></h3>
          <span className="small muted">{rs.length} {noun}</span></div>
        <div className="tbl-wrap" style={{ marginTop: 12 }}>{render(rs)}</div>
      </div>)
  })
}

function Leaderboard() {
  const { data, error } = useApi('/stats/regions')
  if (error) return <ErrorBox error={error} />
  if (!data) return <Spinner />
  return (
    <>
      <p className="note" style={{ marginBottom: 18 }}>Productivity index = average of (district yield ÷ national yield) over every crop the district grows,
        {' '}{data.from_year}–{data.to_year}. 1.00 = national level. Buyer rating comes from reviews of farmers in that district; reviews on Demo profiles are sample data.</p>
      <Grouped rows={data.rows} render={(rs) => (
        <table className="tbl"><thead><tr><th>#</th><th>District</th><th>Region</th><th className="r">Index</th><th className="r">Crops</th><th className="r">Production, t</th><th>Buyer rating</th></tr></thead>
          <tbody>{rs.map((r) => (
            <tr key={r.rayon_id}><td className="b">{r.rank}</td><td><Link to={`/r/${r.rayon_id}`} className="b">{r.name}</Link></td>
              <td className="muted">{r.econ}</td><td className={`r num b ${r.idx >= 1 ? 'green' : 'red'}`}>{fmt(r.idx, 2)}</td>
              <td className="r num">{r.ncrops}</td><td className="r num">{fmt0(r.prod)}</td>
              <td><Stars value={r.rating.avg} count={r.rating.count} /></td></tr>))}</tbody></table>)} />
    </>
  )
}

function CropRanking({ crop }) {
  const [metric, setMetric] = useState('yield')
  const [year, setYear] = useState('')
  const { data, error, stamp, loading } = useApi(`/stats/ranking?crop=${crop}&metric=${metric}${year ? `&year=${year}` : ''}`)
  return (
    <>
      <div className="row" style={{ marginBottom: 16 }}>
        <Seg label="Metric" value={metric} onChange={setMetric} options={[['yield', 'By yield (c/ha)'], ['production', 'By production (t)']]} />
        <Select label="Year" width={120} value={String(year || data?.year || '')} onChange={setYear} options={Array.from({ length: 26 }, (_, i) => 2025 - i).map((y) => ({ value: String(y), label: String(y) }))} />
      </div>
      <ErrorBox error={error} />
      {!data ? <Spinner /> : !data.rows.length ? <div className="card empty">No districts reported this crop in {data.year}.</div> : (
        <Swap k={stamp} loading={loading}>
          <div className="grid g4" style={{ marginBottom: 18 }}>
            <Stat v={fmt(data.national?.yield)} l={`national yield ${data.year}, c/ha`} />
            <Stat cls="blue" v={fmt0(data.national?.production)} l="national production, t" />
            <Stat cls="green" v={data.rows[0].name} l={`#1 by ${metric}`} />
            <Stat v={data.rows.length} l="districts reporting" />
          </div>
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>Top 15 districts by {metric}</h3>
            <HBars rows={data.rows.slice(0, 15)} valueKey={metric} labelKey="name" unit={metric === 'yield' ? ' c/ha' : ' t'} />
          </div>
          <Grouped rows={data.rows} render={(rs) => (
            <table className="tbl"><thead><tr><th>#</th><th>District</th><th className="r">Yield, c/ha</th><th className="r">vs prev. year</th><th className="r">Production, t</th><th>Buyer rating</th></tr></thead>
              <tbody>{rs.map((r) => (
                <tr key={r.rayon_id}><td className="b">{r.rank}</td><td><Link to={`/r/${r.rayon_id}?tab=yields`} className="b">{r.name}</Link> <span className="xs faint">{r.econ}</span></td>
                  <td className="r num">{fmt(r.yield)}</td>
                  <td className={`r num b ${r.change > 0 ? 'green' : r.change < 0 ? 'red' : ''}`}>{r.change !== null ? `${sign(r.change * 100, 0)}%` : '—'}</td>
                  <td className="r num">{fmt0(r.production)}</td><td><Stars value={r.rating.avg} count={r.rating.count} /></td></tr>))}</tbody></table>)} />
          <div className="src">Source: AzStat, all farm categories. Quartile categories are relative to districts reporting this crop.</div>
        </Swap>
      )}
    </>
  )
}

function CropStats({ crop }) {
  const { data, error, stamp, loading } = useApi(`/stats/crop/${crop}`)
  if (error) return <ErrorBox error={error} />
  if (!data) return <Spinner />
  return <Swap k={stamp} loading={loading}><CropStatsBody data={data} /></Swap>
}

function CropStatsBody({ data }) {
  const nat = data.national.filter((n) => n.yield)
  const first = nat.find((n) => n.year >= 2005) || nat[0], last = nat.at(-1)
  const m = data.model, s = data.suitability
  return (
    <div className="stack">
      <div className="grid g4">
        <Stat v={fmt(last?.yield)} l={`national yield ${last?.year}, c/ha`} />
        <Stat cls={last?.yield >= first?.yield ? 'green' : 'blue'} v={first ? `${sign((last.yield / first.yield - 1) * 100, 0)}%` : '—'} l={`yield change since ${first?.year}`} />
        <Stat cls="blue" v={fmt0(last?.production)} l="production, t" />
        <Stat v={s?.now !== null && s?.now !== undefined ? `${fmt0(s.past * 100)} → ${fmt0(s.now * 100)} → ${s.future !== null ? fmt0(s.future * 100) : '—'}` : 'n/a'}
          l="avg climate suitability: 1981–2010 → now → 2041–50" />
      </div>
      <div className="grid g2">
        <div className="card"><h3>National yield, c/ha</h3>
          <MultiLine rows={nat} keys={[{ key: 'yield', name: data.crop.name }]} unit=" c/ha" /></div>
        <div className="card"><h3>Production by economic region (latest year), t</h3>
          <HBars rows={data.econ} valueKey="production" labelKey="econ" unit=" t" color={CAT[1]} /></div>
      </div>
      {m && <div className="card"><h3>Forecast model, back-tested on 2020–2025</h3>
        <p className="small muted" style={{ marginTop: 6 }}>Method: <b>{m.method === 'gbm_climate' ? 'gradient boosting on NASA climate anomalies' : 'persistence (climate ML did not beat it on validation)'}</b>.
          Mean absolute error {fmt(m.mae)} c/ha vs {fmt(m.baseline_mae)} c/ha for "same as last year", over {m.n_test} district-years.</p></div>}
      {data.crop.eco && <div className="card"><h3>FAO ECOCROP requirements: {data.crop.eco.name}</h3>
        <div className="grid g4" style={{ marginTop: 12 }}>
          <Stat v={`${data.crop.eco.TOPMN}–${data.crop.eco.TOPMX}°C`} l={`optimal temperature (limits ${data.crop.eco.TMIN}–${data.crop.eco.TMAX}°C)`} />
          <Stat cls="blue" v={`${fmt0(data.crop.eco.ROPMN)}–${fmt0(data.crop.eco.ROPMX)} mm`} l="optimal season rainfall" />
          <Stat cls="green" v={`${data.crop.eco.PHOPMN}–${data.crop.eco.PHOPMX}`} l="optimal soil pH" />
          <Stat v={`${data.crop.eco.GMIN}–${data.crop.eco.GMAX} d`} l={`growing cycle · killed below ${data.crop.eco.KTMP}°C`} />
        </div></div>}
    </div>
  )
}

function Compare({ crop }) {
  const { rayons } = useCatalog()
  const [ids, setIds] = useState(['berde', 'imisli', 'seki', 'lenkeran'])
  const { data, error, stamp, loading } = useApi(`/stats/compare?rayons=${ids.join(',')}&crop=${crop}`)
  const rows = useMemo(() => {
    if (!data) return []
    const years = new Map()
    data.national.forEach((n) => years.set(n.year, { year: n.year, nat: n.yield }))
    data.rayons.forEach((r) => r.series.forEach((s) => { const y = years.get(s.year) || { year: s.year }; y[r.id] = s.yield; years.set(s.year, y) }))
    return [...years.values()].sort((a, b) => a.year - b.year)
  }, [data])
  return (
    <div className="stack">
      <div className="chips">
        {ids.map((id, i) => (
          <span key={id} className="chip on" style={{ background: CAT[i], borderColor: CAT[i] }}>
            {rayons.find((r) => r.id === id)?.name || id}
            <button onClick={() => setIds(ids.filter((x) => x !== id))} style={{ background: 'none', border: 0, color: '#fff', marginLeft: 6, cursor: 'pointer' }} aria-label="Remove">✕</button>
          </span>))}
        {ids.length < 6 && <Select label="Add district" size="sm" width={200} value="" placeholder="+ Add district" onChange={(v) => setIds([...ids, v])}
          options={rayons.filter((r) => !ids.includes(r.id)).map((r) => ({ value: r.id, label: r.name, group: r.econ }))} />}
      </div>
      <ErrorBox error={error} />
      {!data ? <Spinner /> : (
        <Swap k={stamp} loading={loading}>
          <div className="card"><h3>Yield, c/ha</h3>
            <MultiLine rows={rows} keys={data.rayons.map((r) => ({ key: r.id, name: r.name }))} refKey="nat" refName="Azerbaijan" unit=" c/ha" /></div>
          <div className="card"><h3>Side by side</h3>
            <div className="tbl-wrap"><table className="tbl" style={{ marginTop: 10 }}>
              <thead><tr><th>Metric</th>{data.rayons.map((r) => <th key={r.id} className="r">{r.name}</th>)}</tr></thead>
              <tbody>
                {[['Yield 2025, c/ha', (r) => fmt(r.series.find((s) => s.year === 2025)?.yield)],
                  ['Climate suitability (irrigated)', (r) => (r.suit ? fmt0(r.suit.irrigated * 100) : '—')],
                  ['Warming since 1980s, °C', (r) => sign(r.compare.tmean.delta)],
                  ['Days >35°C now', (r) => fmt0(r.compare.hot35.now)],
                  ['Frost days now', (r) => fmt0(r.compare.frost.now)],
                  ['Annual rain now, mm', (r) => fmt0(r.compare.precip.now)],
                  ['Soil pH', (r) => fmt(r.soil.ph)], ['Soil organic C, g/kg', (r) => fmt(r.soil.soc)],
                  ['Buyer rating', (r) => (r.rating.avg ? `${fmt(r.rating.avg)} ★ (${r.rating.count})` : '—')]].map(([l, f]) => (
                  <tr key={l}><td className="b">{l}</td>{data.rayons.map((r) => <td key={r.id} className="r num">{f(r)}</td>)}</tr>))}
              </tbody></table></div></div>
        </Swap>)}
    </div>
  )
}

function WorldRanking({ crop }) {
  const [metric, setMetric] = useState('yield')
  const [year, setYear] = useState('')
  const [only, setOnly] = useState('all')
  const { data, error, stamp, loading } = useApi(`/stats/world?crop=${crop}&metric=${metric}${year ? `&year=${year}` : ''}`)
  const rows = (data?.rows || []).filter((r) => only === 'all' || r.grp !== 'world')
  const az = data?.rows.find((r) => r.iso3 === 'AZE')
  return (
    <>
      <div className="row" style={{ marginBottom: 16 }}>
        <Seg label="Metric" value={metric} onChange={setMetric} options={[['yield', 'By yield (c/ha)'], ['production', 'By production (t)']]} />
        <Seg label="Countries" value={only} onChange={setOnly} options={[['all', 'All countries'], ['near', 'Near Azerbaijan']]} />
        <Select label="Year" width={120} value={String(year || data?.year || '')} onChange={setYear}
          options={Array.from({ length: 30 }, (_, i) => 2024 - i).map((y) => ({ value: String(y), label: String(y) }))} />
      </div>
      <ErrorBox error={error} />
      {!data ? <Spinner /> : !data.rows.length ? <div className="card empty">No FAOSTAT data for this crop in {data.year}.</div> : (
        <Swap k={stamp} loading={loading}>
          <div className="grid g4" style={{ marginBottom: 18 }}>
            <Stat v={data.rows.length} l={`countries reporting (${data.year})`} />
            <Stat cls="green" v={data.rows[0].name} l={`#1 by ${metric}`} />
            <Stat cls="blue" v={fmt(data.median)} l={`world median, ${metric === 'yield' ? 'c/ha' : 't'}`} />
            <Stat cls="or" v={az ? `#${az.rank}` : '—'} l={az ? `Azerbaijan: ${fmt(az[metric])} ${metric === 'yield' ? 'c/ha' : 't'} · ${az.category}` : 'Azerbaijan not reported'} />
          </div>
          <div className="card" style={{ marginBottom: 18 }}>
            <h3>Top 15 {only === 'near' ? 'near Azerbaijan' : 'in the world'} by {metric}</h3>
            <HBars rows={rows.slice(0, 15)} valueKey={metric} labelKey="name" unit={metric === 'yield' ? ' c/ha' : ' t'} />
          </div>
          <Grouped noun="countries" rows={rows} render={(rs) => (
            <table className="tbl"><thead><tr><th>#</th><th>Country</th><th className="r">Yield, c/ha</th><th className="r">vs prev. year</th><th className="r">Production, t</th><th className="r">Area, ha</th></tr></thead>
              <tbody>{rs.map((r) => (
                <tr key={r.iso3} style={r.iso3 === 'AZE' ? { background: 'var(--or-soft)' } : undefined}>
                  <td className="b">{r.rank}</td>
                  <td><Link to={r.iso3 === 'AZE' ? '/map' : `/map?view=world&c=${r.iso3}`} className="b">{r.name}</Link>{' '}
                    {r.grp !== 'world' && <span className="tag f" style={{ fontSize: 10.5, padding: '1px 7px' }}>{r.iso3 === 'AZE' ? 'Home' : 'Near'}</span>}
                    <span className="xs faint"> {r.continent}</span></td>
                  <td className="r num">{fmt(r.yield)}</td>
                  <td className={`r num b ${r.change > 0 ? 'green' : r.change < 0 ? 'red' : ''}`}>{r.change !== null ? `${sign(r.change * 100, 0)}%` : '—'}</td>
                  <td className="r num">{fmt0(r.production)}</td><td className="r num">{fmt0(r.area)}</td></tr>))}</tbody></table>)} />
          <div className="src">Source: FAOSTAT (FAO), Crops and livestock products. Categories are quartiles among reporting countries.</div>
        </Swap>
      )}
    </>
  )
}

function CompareCountries({ crop }) {
  const { data: countries } = useApi('/countries')
  const [ids, setIds] = useState(['AZE', 'GEO', 'ARM', 'TUR', 'IRN'])
  const { data, error, stamp, loading } = useApi(`/stats/countries/compare?iso3=${ids.join(',')}&crop=${crop}`)
  const rows = useMemo(() => {
    if (!data) return []
    const years = new Map()
    data.world.forEach((n) => years.set(n.year, { year: n.year, world: n.yield }))
    data.countries.forEach((c) => c.series.forEach((s) => { const y = years.get(s.year) || { year: s.year }; y[c.iso3] = s.yield; years.set(s.year, y) }))
    return [...years.values()].sort((a, b) => a.year - b.year)
  }, [data])
  const name = (i) => countries?.find((c) => c.iso3 === i)?.name || i
  return (
    <div className="stack">
      <div className="chips">
        {ids.map((id, i) => (
          <span key={id} className="chip on" style={{ background: CAT[i], borderColor: CAT[i] }}>{name(id)}
            <button onClick={() => setIds(ids.filter((x) => x !== id))} style={{ background: 'none', border: 0, color: '#fff', marginLeft: 6, cursor: 'pointer' }} aria-label="Remove">✕</button></span>))}
        {ids.length < 6 && countries && <Select label="Add country" size="sm" width={220} value="" placeholder="+ Add country" onChange={(v) => setIds([...ids, v])}
          options={countries.filter((c) => !ids.includes(c.iso3)).map((c) => ({ value: c.iso3, label: c.name, group: c.grp === 'home' || c.grp === 'near' ? 'Near Azerbaijan' : c.continent }))} />}
      </div>
      <ErrorBox error={error} />
      {!data ? <Spinner /> : (
        <Swap k={stamp} loading={loading}>
          <div className="card"><h3>Yield, c/ha (FAOSTAT)</h3>
            <MultiLine rows={rows} keys={data.countries.map((c) => ({ key: c.iso3, name: c.name }))} refKey="world" refName="World average" unit=" c/ha" /></div>
          <div className="card"><h3>Side by side</h3>
            <div className="tbl-wrap"><table className="tbl" style={{ marginTop: 10 }}>
              <thead><tr><th>Metric</th>{data.countries.map((c) => <th key={c.iso3} className="r">{c.name}</th>)}</tr></thead>
              <tbody>
                {[['Latest yield, c/ha', (c) => fmt(c.series.at(-1)?.yield)],
                  ['Climate suitability (irrigated, avg of provinces)', (c) => (c.suit?.irrigated != null ? fmt0(c.suit.irrigated * 100) : '—')],
                  ['Warming since 1980s, °C', (c) => sign(c.compare.tmean.delta)],
                  ['Days >35°C now', (c) => fmt0(c.compare.hot35.now)],
                  ['Days >35°C, 2041–50', (c) => fmt0(c.future?.hot)],
                  ['Mean temp 2041–50, °C', (c) => fmt(c.future?.t)],
                  ['Annual rain now, mm', (c) => fmt0(c.compare.precip.now)]].map(([l, f]) => (
                  <tr key={l}><td className="b">{l}</td>{data.countries.map((c) => <td key={c.iso3} className="r num">{f(c)}</td>)}</tr>))}
              </tbody></table></div>
            <div className="src">Climate: NASA POWER and NEX-GDDP-CMIP6, averaged over each country's provinces. Yields: FAOSTAT.</div></div>
        </Swap>)}
    </div>
  )
}

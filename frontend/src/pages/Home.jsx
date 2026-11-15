import { Link } from 'react-router-dom'
import { AnomalyChart, HBars, HotDaysChart } from '../charts.jsx'
import { doy, fmt, fmt0, sign, useApi } from '../lib.jsx'
import { Icon, Spinner, Stat, Title } from '../ui.jsx'

function HeroArt() {
  return (
    <svg viewBox="0 0 520 460" width="100%" role="img" aria-label="Satellite over farm fields">
      <ellipse cx="260" cy="60" rx="190" ry="34" fill="none" stroke="#F57C1F" strokeDasharray="4 6" opacity=".6" />
      <g className="hero-sat"><g transform="translate(300 40) rotate(-20)">
        <rect x="-60" y="-14" width="44" height="28" fill="#2B2A2E" rx="2" />
        <rect x="16" y="-14" width="44" height="28" fill="#2B2A2E" rx="2" />
        <rect x="-14" y="-18" width="28" height="36" fill="#F57C1F" rx="4" />
        <path d="M-50 -14v28M-38-14v28M-26-14v28M26-14v28M38-14v28M50-14v28" stroke="#fff" strokeWidth="1" opacity=".5" />
      </g></g>
      <path className="hero-beam" d="M296 70 L160 330 L420 330 Z" fill="#F57C1F" opacity=".12" />
      <g transform="translate(260 340)">
        <path d="M0 -70 L150 0 L0 70 L-150 0 Z" fill="#E7ECEF" />
        <path d="M0 -70 L75 -35 L0 0 L-75 -35 Z" fill="#2FA35B" />
        <path d="M75 -35 L150 0 L75 35 L0 0 Z" fill="#2B2A2E" />
        <path d="M-75 -35 L0 0 L-75 35 L-150 0 Z" fill="#F9AE6E" />
        <path d="M0 0 L75 35 L0 70 L-75 35 Z" fill="#F57C1F" />
        <path d="M-120 -14 L-30 28M-100 -24 L-10 18M-60 30 L30 -12" stroke="#fff" strokeWidth="2" opacity=".5" />
      </g>
      <rect x="236" y="190" width="32" height="120" fill="#F57C1F" />
      <rect x="268" y="200" width="16" height="110" fill="#C0540A" />
      <circle className="hero-ping" cx="380" cy="210" r="26" fill="none" stroke="#F57C1F" strokeWidth="2" />
      <circle cx="380" cy="210" r="26" fill="#fff" stroke="#F57C1F" strokeWidth="3" />
      <path d="M380 196 l12 22 h-24 z" fill="#F57C1F" />
      <rect x="378.5" y="203" width="3" height="8" fill="#fff" /><circle cx="380" cy="214" r="1.6" fill="#fff" />
    </svg>
  )
}

export default function Home() {
  const { data: o, error } = useApi('/overview')
  const { data: meta } = useApi('/meta')
  const P = o?.past, N = o?.now
  const pct = (a, b) => (a ? ((b - a) / a) * 100 : null)
  return (
    <>
      <section className="hero">
        <div>
          <div className="kicker">NASA Space Apps Challenge 2026 · Team Earthly</div>
          <h1 className="t" style={{ marginTop: 20 }}>Adapting farms <span className="o">with NASA data.</span></h1>
          <p className="lead" style={{ marginTop: 22 }}>
            Field Shift helps farmers in Azerbaijan choose the right crops from soil, four decades of climate change and
            future potential, then watches every district and sends practical alerts when the weather turns.
          </p>
          <div className="row" style={{ marginTop: 30 }}>
            <Link to="/map" className="btn">Explore the map <Icon n="map" s={17} /></Link>
            <Link to="/account" className="btn ghost">Create a farm account</Link>
          </div>
          {meta && <div className="row small muted" style={{ marginTop: 34, gap: 22 }}>
            <span><b className="num" style={{ color: 'var(--ink)' }}>{meta.counts.rayons}</b> districts</span>
            <span><b className="num" style={{ color: 'var(--ink)' }}>{meta.counts.crops}</b> crops</span>
            <span><b className="num" style={{ color: 'var(--ink)' }}>{fmt0(meta.counts.yield_rows)}</b> official yield records</span>
            <span>NASA climate <b className="num" style={{ color: 'var(--ink)' }}>1981–{meta.power_end}</b></span>
          </div>}
        </div>
        <div className="peach" style={{ padding: 24 }}><HeroArt /></div>
      </section>

      <section className="section grid g2" style={{ alignItems: 'center' }}>
        <div>
          <Title dark="The problem." orange="Farmers decide by guessing." />
          <div className="stack" style={{ marginTop: 26 }}>
            {[['sprout', <>Farmers don't know which crops <b>suit their soil</b></>],
              ['thermo', <>The climate is shifting, so <b>past experience</b> is no longer enough</>],
              ['bell', <>Unexpected weather and <b>forecast errors</b> destroy crops</>]].map(([i, t], k) => (
              <div key={k} className="row" style={{ gap: 16, flexWrap: 'nowrap', paddingBottom: 14, borderBottom: '1px solid var(--line)' }}>
                <div className="ibox"><Icon n={i} s={22} /></div><p style={{ fontSize: 16, flex: 1, color: 'var(--ink)' }}>{t}</p>
              </div>))}
          </div>
        </div>
        <div className="dark">
          <p style={{ fontSize: 24, fontWeight: 500 }}>Today, farmers decide</p>
          <div className="big" style={{ marginTop: 8 }}>by guessing,<br /><span>not by data.</span></div>
          <p className="muted" style={{ marginTop: 26 }}>Result: lost harvests, wasted water and fertilizer, lower income.</p>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <Title dark="The past." orange="What NASA data shows." />
          <p className="muted" style={{ maxWidth: 420 }}>1981–1990 vs 2016–2025, averaged over all {meta?.counts.rayons || 72} districts
            of Azerbaijan (NASA POWER daily data).</p>
        </div>
        {error && <div className="err">{error.message}</div>}
        {!o ? <Spinner /> : (
          <>
            <div className="grid g5">
              <Stat cls="or" v={`${sign(N.tmean - P.tmean)}°C`} l="warmer on average" />
              <Stat v={`${sign(pct(P.hot35, N.hot35), 0)}%`} l={`days above 35°C (${fmt0(P.hot35)} → ${fmt0(N.hot35)})`} />
              <Stat cls="blue" v={`${sign(pct(P.frost, N.frost), 0)}%`} l={`frost days (${fmt0(P.frost)} → ${fmt0(N.frost)})`} />
              <Stat cls="green" v={`${sign(N.ffs - P.ffs, 0)} d`} l="longer frost-free season" />
              <Stat v={`${o.warm_years_since_2004}/${o.years_since_2004}`} l="years since 2004 warmer than the 1981–2010 norm" />
            </div>
            <div className="grid g2" style={{ marginTop: 18 }}>
              <div className="card">
                <h3>Annual temperature vs 1981–2010 norm</h3>
                <p className="small muted">Average of all districts. The shift is steady, not random.</p>
                <AnomalyChart data={o.anomaly_series} />
                <div className="src">Source: NASA POWER daily point data (MERRA-2), our calculations.</div>
              </div>
              <div className="card">
                <h3>Heat-stress days (&gt;35°C): past and future</h3>
                <p className="small muted">Observed 1981–{o.anomaly_series.at(-1)?.year}, then NASA NEX-GDDP-CMIP6 projection (SSP2-4.5).</p>
                <HotDaysChart observed={o.anomaly_series} projection={o.projection} />
                <div className="src">Source: NASA POWER; NASA NEX-GDDP-CMIP6, SSP2-4.5, 5-model mean (MRI-ESM2-0, MPI-ESM1-2-HR, ACCESS-CM2, EC-Earth3, GFDL-ESM4).</div>
              </div>
            </div>
            <div className="grid g4" style={{ marginTop: 18 }}>
              {[['1', 'Heat stress is rising', `Days above 35°C up ${fmt0(pct(P.hot35, N.hot35))}%. Heat during flowering cuts yields of wheat, potato and vegetables.`],
                ['2', 'Spring arrives earlier', `Last spring frost moved from ${doy(Math.round(P.last_frost))} to ${doy(Math.round(N.last_frost))}. Early blooming means one late frost can wipe out orchards.`],
                ['3', 'Season is longer and warmer', `Frost-free season +${fmt0(N.ffs - P.ffs)} days, growing degree-days ${sign(pct(P.gdd, N.gdd), 0)}%. New crops become possible.`],
                ['4', 'Old calendars fail', 'Planting dates and crop choices based on past experience no longer match the climate.']].map(([n, h, t]) => (
                <div key={n} className="card tight"><div className="step-n">0{n}</div><h3 style={{ fontSize: 15, marginTop: 6 }}>{h}</h3>
                  <p className="small muted" style={{ marginTop: 8 }}>{t}</p></div>))}
            </div>
          </>
        )}
      </section>

      <section className="section">
        <Title dark="How it works." orange="Six steps." />
        <p className="lead" style={{ marginTop: 14 }}>From satellite data to an actionable tip on the farmer's phone, in six steps.</p>
        <div className="grid g3" style={{ marginTop: 24 }}>
          {[['pin', 'Select region', 'Mark your farm on the map', '/map'],
            ['sat', 'NASA data', 'Soil, climate, vegetation since 1981', '/data'],
            ['brain', 'AI analysis', 'Historical trends + forecast', '/stats'],
            ['sprout', 'Crop recommendation', 'Suitability score for every crop', '/map'],
            ['eye', 'Continuous monitoring', 'Live 16-day forecast, checked every 3 h', '/alerts'],
            ['bell', 'Alert + advice', 'SMS with practical steps when risk hits', '/alerts']].map(([i, h, t, to], k) => (
            <Link key={h} to={to} className="card row" style={{ gap: 16, flexWrap: 'nowrap' }}>
              <div className="ibox"><Icon n={i} s={26} /></div>
              <div><div className="step-n">0{k + 1}</div><h3>{h}</h3><p className="small muted">{t}</p></div>
            </Link>))}
        </div>
      </section>

      <BeyondAzerbaijan />

      {o && (
        <section className="section grid g2">
          <div className="card">
            <h3>What Azerbaijan grows most ({o.stat_year})</h3>
            <div className="tbl-wrap" style={{ marginTop: 12 }}>
              <table className="tbl">
                <thead><tr><th>Crop</th><th className="r">Production, t</th><th className="r">Yield, c/ha</th><th className="r">vs 2005</th></tr></thead>
                <tbody>{o.top_crops.map((c) => (
                  <tr key={c.crop_id}><td className="b">{c.name}</td><td className="r num">{fmt0(c.production)}</td>
                    <td className="r num">{fmt(c.yield)}</td>
                    <td className={`r num b ${c.y2005 && c.yield > c.y2005 ? 'green' : 'red'}`}>{c.y2005 ? `${sign(((c.yield - c.y2005) / c.y2005) * 100, 0)}%` : '—'}</td></tr>))}
                </tbody>
              </table>
            </div>
            <div className="src">Source: State Statistical Committee of Azerbaijan (stat.gov.az), all farm categories.</div>
          </div>
          <div className="dark" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div className="kicker" style={{ color: '#A9A6A2' }}>For every district</div>
            <div className="big" style={{ marginTop: 14 }}>From data to harvest:<br /><span>powered by NASA & AI.</span></div>
            <p className="muted" style={{ marginTop: 18 }}>Farmers list their farms and contacts, buyers rate them, everyone
              sees which districts lead in each crop.</p>
            <div className="row" style={{ marginTop: 22 }}>
              <Link to="/stats" className="btn">See rankings</Link>
              <Link to="/farmers" className="btn ghost" style={{ color: '#fff', borderColor: '#4A4847' }}>Find farmers</Link>
            </div>
          </div>
        </section>
      )}
    </>
  )
}

function BeyondAzerbaijan() {
  const { data: w } = useApi('/world/overview')
  if (!w) return null
  const near = w.near.filter((r) => r.warming !== null)
  const az = near.find((r) => r.iso3 === 'AZE')
  return (
    <section className="section">
      <div className="section-head">
        <Title dark="Beyond Azerbaijan." orange="The same NASA data, worldwide." />
        <p className="muted" style={{ maxWidth: 440 }}>Azerbaijan keeps district-level official statistics. Every other country gets
          province-level NASA climate, 2050 projections, soil and crop suitability, with FAOSTAT yields at country level.</p>
      </div>
      <div className="grid g4">
        <Stat v={fmt0(w.counts.countries)} l="countries covered" />
        <Stat cls="blue" v={fmt0(w.counts.provinces)} l="provinces with their own profile" />
        <Stat cls="or" v={`${sign(w.world_mean_warming)}°C`} l="average warming since the 1980s, all provinces" />
        <Stat cls="green" v={fmt0(w.counts.faostat_countries)} l="countries with FAOSTAT crop yields" />
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>Near Azerbaijan: warming since the 1980s, °C</h3>
          <p className="small muted">Mean over each country's provinces, 1981–90 vs 2016–25 (NASA POWER).</p>
          <HBars rows={near.map((r) => ({ name: r.name, v: +r.warming.toFixed(2) }))} valueKey="v" labelKey="name" unit=" °C" />
        </div>
        <div className="card">
          <h3>Hot days now and in 2041–50</h3>
          <div className="tbl-wrap"><table className="tbl" style={{ marginTop: 10 }}>
            <thead><tr><th>Country</th><th className="r">Days &gt;35°C, 1981–90</th><th className="r">2016–25</th><th className="r">2041–50</th><th className="r">Mean °C 2041–50</th></tr></thead>
            <tbody>{near.map((r) => (
              <tr key={r.iso3} style={r.iso3 === 'AZE' ? { background: 'var(--or-soft)' } : undefined}>
                <td><Link className="b" to={r.iso3 === 'AZE' ? '/map' : `/map?view=near&c=${r.iso3}`}>{r.name}</Link></td>
                <td className="r num">{fmt0(r.h_past)}</td><td className="r num">{fmt0(r.h_now)}</td>
                <td className="r num b">{fmt0(r.h_2045)}</td><td className="r num">{fmt(r.t_2045)}</td></tr>))}</tbody>
          </table></div>
          <div className="src">NASA POWER; NASA NEX-GDDP-CMIP6 SSP2-4.5 ensemble, delta-corrected per province.</div>
        </div>
      </div>
      <div className="row" style={{ marginTop: 18 }}>
        <Link to="/map?view=near" className="btn">Explore Near Azerbaijan <Icon n="map" s={17} /></Link>
        <Link to="/map?view=world" className="btn ghost">World map</Link>
        <Link to="/stats?tab=world" className="btn ghost">World crop rankings</Link>
        {az && <span className="small muted">Azerbaijan: {sign(az.warming)}°C since the 1980s.</span>}
      </div>
    </section>
  )
}

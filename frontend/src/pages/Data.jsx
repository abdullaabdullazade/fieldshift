import { fmt, fmt0, useApi } from '../lib.jsx'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Icon, Spinner, Title } from '../ui.jsx'
import { useLang } from '../i18n.jsx'

export default function Data() {
  const { data: m } = useApi('/meta')
  const { t, lang } = useLang()
  const { data: grace } = useApi('/kur/grace')
  if (!m) return <Spinner />
  return (
    <>
      <Title dark={lang === 'az' ? 'Data və metod.' : 'Data & methods.'} orange={lang === 'az' ? 'Hər rəqəmin mənbəyi var.' : 'Every number has a source.'} />
      <div className="card" style={{ marginTop: 22 }}>
        <h3>{lang === 'az' ? 'Kürə duzlu su modeli' : 'Kür salt-water model'}</h3>
        <p className="small" style={{ marginTop: 10 }}>{t('method')}</p>
        <p className="small muted" style={{ marginTop: 10 }}>
          {lang === 'az'
            ? 'Çayın gücü S = axın / 334 m³/san (2020–2026 medianı), NASA SWOT son 12 gündə keçibsə km 13 → km 51 meyli / 1.7 m ilə 50/50 qarışdırılır. Şimal-şərq küləyi U = külək · cos(istiqamət − 45°). Duzlu suyun çatdığı yer L = 5.67 km · S⁻² · (1 + U/6), ən çox 60 km; aralıq 0.6L–1.6L. Nasos km ≤ L: qırmızı; ≤ 1.6L və ya sabah qırmızı: narıncı; əks halda yaşıl. Kənd ölçmələri (EC ≥ 3 dS/m = duzlu) modeli üstələyir.'
            : 'River strength S = discharge / 334 m³/s (2020–2026 median), blended 50/50 with the NASA SWOT slope km 13 → km 51 / 1.7 m when SWOT passed in the last 12 days. North-east wind U = wind · cos(direction − 45°). Salt front L = 5.67 km · S⁻² · (1 + U/6), capped at 60 km; range 0.6L–1.6L. Pump km ≤ L: red; ≤ 1.6L or red tomorrow: orange; otherwise green. Village measurements (EC ≥ 3 dS/m = salty) override the model.'}
        </p>
      </div>
      {grace && <div className="card" style={{ marginTop: 16 }}>
        <h3>{lang === 'az' ? 'Kür–Araz hövzəsi su itirir (NASA GRACE)' : 'The Kür–Araz basin is losing water (NASA GRACE)'}</h3>
        <p className="small muted" style={{ marginTop: 8 }}>{lang === 'az'
          ? `GRACE peykləri Yerin cazibəsini ölçür: hövzədə su azalanda cazibə də azalır. ${grace.start.slice(0, 4)}–${grace.end.slice(0, 4)}: ildə ${fmt(Math.abs(grace.trend_cm_per_year), 1)} sm, cəmi ${fmt(Math.abs(grace.change_cm), 1)} sm su qatı.`
          : `GRACE satellites weigh the basin by its gravity: less water, weaker pull. ${grace.start.slice(0, 4)}–${grace.end.slice(0, 4)}: ${fmt(Math.abs(grace.trend_cm_per_year), 1)} cm of water per year, ${fmt(Math.abs(grace.change_cm), 1)} cm in total.`}</p>
        <div style={{ height: 220, marginTop: 12 }}>
          <ResponsiveContainer>
            <AreaChart data={grace.series} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
              <XAxis dataKey="date" tickFormatter={(d) => d.slice(0, 4)} minTickGap={40} tick={{ fill: '#A1A1AA', fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#71717A', fontSize: 12 }} axisLine={false} tickLine={false} unit=" cm" />
              <Tooltip contentStyle={{ background: '#18181B', border: '1px solid #27272A', borderRadius: 10, color: '#fff' }} formatter={(v) => [`${v} cm`, 'GRACE']} />
              <Area dataKey="cm" stroke="#FF6A1A" fill="rgba(255,106,26,.18)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>}
      <h2 className="t" style={{ marginTop: 40, fontSize: 28 }}>{lang === 'az' ? 'Mənbələr' : 'Sources'}</h2>
      <div className="grid g4" style={{ marginTop: 24 }}>
        {[['Azerbaijani districts', m.counts.rayons], ['countries', m.counts.countries], ['world provinces', fmt0(m.counts.provinces)], ['crops', m.counts.crops],
          ['AzStat yield records', fmt0(m.counts.yield_rows)], ['FAOSTAT country-crop-years', fmt0(m.counts.country_yield_rows)], ['place-years of NASA climate', fmt0(m.counts.climate_years)],
          ['provinces with 2050 projection', fmt0(m.world_provinces_climate ?? 0)]].map(([l, v]) => (
          <div key={l} className="stat"><div className="v num">{v}</div><div className="l">{l}</div></div>))}
      </div>
      <div className="card" style={{ marginTop: 24 }}>
        <h3>How the data gets here</h3>
        <div className="grid g4" style={{ marginTop: 12 }}>
          {[['1. NASA servers', 'POWER API, NEX-GDDP-CMIP6 on NCCS THREDDS, GIBS satellite imagery. All open, no login.'],
            ['2. Download & cut', 'Only our points and polygons are requested (point API, NetCDF subset, WMS image of the area).'],
            ['3. Turn into numbers', 'Daily values become monthly/yearly climate; satellite pixel colours are decoded back to NDVI, soil moisture, mm of rain.'],
            ['4. Into the app', 'Stored per district / province in one database; satellites refresh twice a day, forecasts every 3 hours.']].map(([h, t]) => (
            <div key={h} className="stat"><div className="b small">{h}</div><div className="l" style={{ marginTop: 6 }}>{t}</div></div>))}
        </div>
      </div>
      <div className="grid g2" style={{ marginTop: 24 }}>
        {m.sources.map((s) => (
          <div key={s.name} className="card row" style={{ flexWrap: 'nowrap', gap: 16, alignItems: 'flex-start' }}>
            <div className="ibox navy"><Icon n="db" s={24} /></div>
            <div style={{ minWidth: 0, overflowWrap: 'anywhere' }}><h3>{s.name} {s.nasa ? <span className="tag f" style={{ fontSize: 10.5, padding: '1px 7px' }}>NASA</span> : null}</h3>
              <p className="small muted">{s.what}</p>
              {s.how && <p className="small" style={{ marginTop: 6 }}><b>How we get it:</b> {s.how}</p>}
              <p className="xs" style={{ marginTop: 6 }}><b>Licence:</b> {s.license}</p>
              <div className="links">
                {(s.links || []).map(([l, u]) => <a key={u} href={u} target="_blank" rel="noreferrer">{l} ↗</a>)}
                <a href={s.url} target="_blank" rel="noreferrer">Data access point ↗</a>
              </div>
              <p className="xs faint" style={{ wordBreak: 'break-all', marginTop: 4 }}>{s.url}</p></div>
          </div>))}
      </div>
      {m.exports?.length > 0 && <div className="card" style={{ marginTop: 24 }}>
        <div className="between"><h3>Download our processed data (CSV)</h3><span className="xs muted">Open data, same licences as the sources above</span></div>
        <div className="tbl-wrap"><table className="tbl" style={{ marginTop: 10 }}>
          <thead><tr><th>Table</th><th>What it holds</th><th className="r">Rows</th><th /></tr></thead>
          <tbody>{m.exports.map((e) => (
            <tr key={e.table}><td className="b">{e.table}</td><td className="small">{e.what}</td><td className="r num">{fmt0(e.rows)}</td>
              <td className="r"><a className="or b small" href={`/api/export/${e.table}.csv`} download>CSV ↓</a></td></tr>))}</tbody>
        </table></div>
      </div>}
      <div className="grid g2" style={{ marginTop: 32 }}>
        <div className="card stack">
          <h3>Crop suitability</h3>
          <p className="small">FAO ECOCROP limits (temperature, rainfall, pH, season length) applied to each district's monthly NASA
            climate. For each possible sowing month we score the growing window; perennials and autumn-sown wheat/barley may go dormant
            in winter, but frost below the crop's killing temperature cuts the score. Soil pH from SoilGrids adjusts the score. The same
            model runs on 1981–2010, 2016–2025 and on CMIP6 2041–2050 climate.</p>
          <h3>Recommendation score</h3>
          <p className="small">45% suitability now + 35% the district's real yield vs the national average (AzStat, 2021–2025) + 20%
            suitability in 2041–2050. Crops with no local official record get a neutral-low evidence score.</p>
        </div>
        <div className="card stack">
          <h3>Yield forecasts</h3>
          <p className="small">For each crop we compare a gradient-boosting model on NASA growing-season anomalies with the naive
            "same as last year" baseline, choose on 2016–2019 and report error on 2020–2025. The chosen method forecasts {m.stat_last_year + 1}
            {' '}and {m.stat_last_year + 2}, with a range covering 80% of past errors.</p>
          <h3>Future climate</h3>
          <p className="small">NASA NEX-GDDP-CMIP6 (0.25°, daily, SSP2-4.5): mean of {m.projection_models?.length || 5} models
            ({(m.projection_models || []).join(', ')}) at every district centre, delta-corrected per month against NASA POWER
            1995–2014. Available for {m.projection_rayons} of {m.counts.rayons} districts.</p>
          <h3>Beyond Azerbaijan</h3>
          <p className="small">Every other country is split into provinces (geoBoundaries ADM1, {fmt0(m.counts.provinces)} units in
            {' '}{m.counts.countries} countries). Each province gets the same pipeline as an Azerbaijani district: NASA POWER daily
            climate at its representative point (southern-hemisphere seasons shifted by six months), SoilGrids means over its
            polygon, ECOCROP suitability and NEX-GDDP-CMIP6 projections (5 models, 2° sampling, delta-corrected to NASA POWER).
            The climate point is moved off mountain ridges to farmland elevation (20th percentile of the province, NOAA ETOPO1),
            and NASA POWER temperatures are lapse-rate corrected (6.5 °C/km, capped at 1.5 km) from the ~50 km MERRA-2 cell to
            that elevation; Azerbaijan's districts get the same correction.
            Official yields below country level are not published consistently worldwide, so yields come from FAOSTAT at country
            level{m.faostat_last_year ? ` (through ${m.faostat_last_year})` : ''}.</p>
          <h3>NASA satellites, now</h3>
          <p className="small">NASA GIBS images of MODIS NDVI (monthly, 1 km), SMAP L4 root-zone soil moisture (daily) and GPM IMERG
            precipitation (daily) are decoded back to values through their published colour maps and averaged over every district
            (1 km grid) and province (0.1° grid). NDVI is compared with the same month of the previous 5 years, soil moisture with
            the same day since 2016; rain is the last 7 days. Refreshed twice a day. When both satellites show drier than normal
            conditions, farms there get a "satellite drought" alert.</p>
          <h3>Alerts</h3>
          <p className="small">Every 3 hours each farm is checked for frost, heat ≥35°C, heavy rain ≥20 mm/day, gusts ≥60 km/h and dry
            spells in the next 7 days, for forecast misses (temperature off by ≥4°C or rain by ≥15 mm) and for NASA FIRMS fire
            detections within 10 km in the last 24 hours (high risk within 3 km). Hot spots seen at the same ~1 km spot on 3 or
            more of the last 10 days (gas flares, refineries) are shown grey and never alerted. SMS is simulated.</p>
          <h3>How fresh is each satellite layer?</h3>
          <p className="small">Meteosat clouds: last full hour. FIRMS fires: about 3 hours after the pass. LANCE (MODIS true colour,
            land surface temperature): about 3 hours. GPM IMERG Early 30-minute rain: about 4–6 hours. SMAP L4 soil moisture:
            2–3 days. MODIS NDVI: monthly.</p>
        </div>
      </div>
      <p className="src">Database built {m.built_at}. NASA POWER through {m.power_end}; AzStat through {m.stat_last_year}.</p>
    </>
  )
}

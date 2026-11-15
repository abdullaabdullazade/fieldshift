import { useEffect, useState } from 'react'
import { CircleMarker, GeoJSON, MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { Link } from 'react-router-dom'
import { ago, api, useApi, useAuth, useCatalog } from '../lib.jsx'
import { ErrorBox, Icon, Modal, Select, Seg, Spinner, Switch, Title } from '../ui.jsx'
import { useGeo } from './MapPage.jsx'
import { useLang } from '../i18n.jsx'

export default function Account() {
  const { user, ready } = useAuth()
  if (!ready) return <Spinner />
  return user ? <Profile /> : <Auth />
}

function Auth() {
  const { login } = useAuth()
  const { t, lang } = useLang()
  const [mode, setMode] = useState('login')
  const [f, setF] = useState({ name: '', id: '', phone: '', email: '', password: '', role: 'farmer' })
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault(); setErr(null); setBusy(true)
    try {
      const r = mode === 'login' ? await api('/auth/login', { method: 'POST', body: { email: f.id, password: f.password } })
        : await api('/auth/register', { method: 'POST', body: { name: f.name, phone: f.phone, email: f.email, password: f.password, role: f.role } })
      await login(r.token)
    } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  const az = lang === 'az'
  return (
    <div className="grid g2" style={{ alignItems: 'center' }}>
      <div>
        <Title dark={mode === 'login' ? (az ? 'Xoş gəldin.' : 'Welcome back.') : (az ? 'Hesab yarat.' : 'Create an account.')}
          orange={mode === 'login' ? (az ? 'Daxil ol.' : 'Sign in to continue.') : (az ? '1 dəqiqə çəkir.' : 'It takes a minute.')} />
        <p className="lead" style={{ marginTop: 16 }}>{az
          ? 'Sahəni və nasosunu qeyd et — Kürün suyu nasosunun yanında duzlu olanda SMS alırsan.'
          : 'Add your field and pump — get an SMS when the Kür water at your pump turns salty.'}</p>
      </div>
      <form className="card stack" onSubmit={submit} style={{ padding: 30 }}>
        <Seg label="Mode" value={mode} onChange={setMode} options={[['login', t('r_login')], ['register', t('r_new')]]} />
        {mode === 'register' ? <>
          <div><label className="f" htmlFor="n">{t('r_name')}</label><input id="n" className="input" required minLength={2} value={f.name} onChange={set('name')} /></div>
          <div><label className="f" htmlFor="p">{t('r_phone')}</label><input id="p" className="input" inputMode="tel" required placeholder="+994 50 123 45 67" value={f.phone} onChange={set('phone')} /></div>
          <div><label className="f" htmlFor="e">Email <span className="faint">({az ? 'istəyə bağlı' : 'optional'})</span></label><input id="e" type="email" className="input" value={f.email} onChange={set('email')} autoComplete="email" /></div>
        </> : <div><label className="f" htmlFor="i">{az ? 'Telefon və ya email' : 'Phone or email'}</label><input id="i" className="input" required value={f.id} onChange={set('id')} autoComplete="username" /></div>}
        <div><label className="f" htmlFor="pw">{t('r_pass')}</label><input id="pw" type="password" className="input" required minLength={mode === 'register' ? 8 : 1} value={f.password} onChange={set('password')} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></div>
        <ErrorBox error={err} />
        <button className="btn" disabled={busy}>{mode === 'login' ? t('r_login') : t('r_go')}</button>
      </form>
    </div>
  )
}

function Profile() {
  const { user, logout, refresh } = useAuth()
  const [f, setF] = useState({ name: user.name, phone: user.phone || '', bio: user.bio || '', whatsapp: user.whatsapp || '',
    telegram: user.telegram || '', show_phone: !!user.show_phone, sms_alerts: !!user.sms_alerts })
  const [msg, setMsg] = useState(null)
  const [edit, setEdit] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const save = async (e) => {
    e.preventDefault(); setMsg(null)
    try { await api('/me', { method: 'PUT', body: f }); await refresh(); setMsg({ ok: 'Saved' }) } catch (x) { setMsg({ err: x.message }) }
  }
  const del = async (id) => { await api(`/me/farms/${id}`, { method: 'DELETE' }); refresh() }
  return (
    <>
      <div className="between">
        <Title dark="My account" />
        <div className="row">{user.role === 'farmer' && <Link to={`/farmers/${user.id}`} className="btn ghost sm">View public profile</Link>}
          <button className="btn light sm" onClick={logout}>Sign out</button></div>
      </div>
      <div className="grid g2" style={{ marginTop: 26, alignItems: 'start' }}>
        <form className="card stack" onSubmit={save}>
          <h3>Profile & contacts <span className="tag grey" style={{ marginLeft: 8 }}>{user.role}</span></h3>
          <div><label className="f" htmlFor="pn">Name</label><input id="pn" className="input" value={f.name} onChange={set('name')} /></div>
          <div className="grid g2">
            <div><label className="f" htmlFor="pp">Phone</label><input id="pp" className="input" value={f.phone} onChange={set('phone')} placeholder="+994…" /></div>
            <div><label className="f" htmlFor="pw">WhatsApp</label><input id="pw" className="input" value={f.whatsapp} onChange={set('whatsapp')} placeholder="+994…" /></div>
          </div>
          <div><label className="f" htmlFor="pt">Telegram username</label><input id="pt" className="input" value={f.telegram} onChange={set('telegram')} placeholder="@username" /></div>
          {user.role === 'farmer' && <div><label className="f" htmlFor="pb">About your farm (shown to buyers)</label>
            <textarea id="pb" className="input" maxLength={1000} value={f.bio} onChange={set('bio')} placeholder="What you grow, how you sell, delivery…" /></div>}
          <Switch checked={f.show_phone} onChange={(v) => setF({ ...f, show_phone: v })}>Show my phone number publicly</Switch>
          <Switch checked={f.sms_alerts} onChange={(v) => setF({ ...f, sms_alerts: v })}>SMS for high-risk alerts <span className="faint">(simulated)</span></Switch>
          {msg?.ok && <div className="ok">{msg.ok}</div>}{msg?.err && <div className="err">{msg.err}</div>}
          <button className="btn">Save</button>
        </form>
        {user.role === 'farmer' ? (
          <div className="card stack">
            <div className="between"><h3>My farms</h3><button className="btn sm" onClick={() => setEdit({})}><Icon n="plus" s={16} />Add farm</button></div>
            {user.farms.length ? user.farms.map((fm) => (
              <div key={fm.id} className="between" style={{ padding: '12px 0', borderBottom: '1px solid var(--line)' }}>
                <div><b>{fm.name}</b> · <Link to={`/r/${fm.rayon_id}`} className="or b">{fm.rayon}</Link>{fm.iso3 !== 'AZE' ? <span className="muted">, {fm.country}</span> : null}
                  <div className="xs muted">{fm.crops.length} crops{fm.area_ha ? ` · ${fm.area_ha} ha` : ''}{fm.lat ? ` · ${fm.lat.toFixed(3)}, ${fm.lon.toFixed(3)}` : ' · district centre'}</div></div>
                <div className="row"><button className="chip" onClick={() => setEdit(fm)}>Edit</button><button className="chip" onClick={() => del(fm.id)}>Delete</button></div>
              </div>)) : <p className="muted small">Add your first farm to get crop advice and weather alerts for it.</p>}
          </div>
        ) : (
          <div className="card"><h3>Buyer account</h3><p className="muted small" style={{ marginTop: 8 }}>Browse <Link to="/farmers" className="or b">farmers</Link> by district and crop, contact them and leave reviews.</p></div>
        )}
      </div>
      {user.role === 'farmer' && <LatestAlerts key={user.farms.length} user={user} />}
      {edit && <FarmModal farm={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); refresh() }} />}
    </>
  )
}

function LatestAlerts({ user }) {
  const { data: alerts, error } = useApi('/me/alerts')
  const list = (alerts || []).slice(0, 4)
  return (
    <div className="card stack" style={{ marginTop: 18 }}>
      <div className="between"><h3>Latest alerts {user.unread > 0 && <span className="tag f" style={{ marginLeft: 6 }}>{user.unread} new</span>}</h3>
        <Link to="/alerts" className="small or b">All alerts & forecasts</Link></div>
      <ErrorBox error={error} />
      {!alerts ? <Spinner /> : list.length ? list.map((a) => (
        <div key={a.id} className={`alert ${a.severity === 'medium' ? 'orta' : ''} ${a.read ? '' : 'unread'}`} style={{ padding: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="between" style={{ gap: 8 }}><b className="small">{a.title}</b><span className="xs muted">{a.farm} · {ago(a.created_at)}</span></div>
            <div className="xs muted" style={{ marginTop: 4 }}>{a.advice}</div>
          </div>
        </div>)) : <p className="muted small">{user.farms.length ? 'No alerts yet. Your farms are checked every 3 hours.' : 'Add a farm to start getting alerts.'}</p>}
    </div>
  )
}

function Picker({ pos, onPick }) {
  useMapEvents({ click: (e) => onPick([e.latlng.lat, e.latlng.lng]) })
  return pos ? <CircleMarker center={pos} radius={9} pathOptions={{ color: '#fff', weight: 3, fillColor: '#F57C1F', fillOpacity: 1 }} /> : null
}

export function inPoly(pt, geom) {
  const [x, y] = [pt[1], pt[0]]
  const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates
  return polys.some((poly) => {
    let inside = false
    const ring = poly[0]
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j]
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
    }
    return inside
  })
}

function FitTo({ geo }) {
  const map = useMap()
  useEffect(() => { if (geo) map.fitBounds(L.geoJSON(geo).getBounds(), { padding: [8, 8], maxZoom: 9 }) }, [geo, map])
  return null
}

function FarmModal({ farm, onClose, onSaved }) {
  const { crops } = useCatalog()
  const { data: countries } = useApi('/countries')
  const { data: sat } = useApi('/satellite')
  const [iso, setIso] = useState(farm.iso3 || 'AZE')
  const { data: units } = useApi(`/rayons?scope=${iso}`)
  const geo = useGeo(`country/${iso}`)
  const [f, setF] = useState({ name: farm.name || '', rayon_id: farm.rayon_id || '', area_ha: farm.area_ha || '',
    irrigated: farm.irrigated ?? true, crops: farm.crops || [], lat: farm.lat || null, lon: farm.lon || null })
  const [err, setErr] = useState(null)
  const az = iso === 'AZE'
  const pick = ([lat, lon]) => {
    const hit = geo?.features.find((ft) => inPoly([lat, lon], ft.geometry))
    setF((s) => ({ ...s, lat: +lat.toFixed(5), lon: +lon.toFixed(5), rayon_id: hit ? hit.properties.id : s.rayon_id }))
  }
  const changeCountry = (v) => { setIso(v); setF((s) => ({ ...s, rayon_id: '', lat: null, lon: null })) }
  const save = async (e) => {
    e.preventDefault()
    if (!f.rayon_id) { setErr(new Error(`Choose a ${az ? 'district' : 'province'} or click your field on the map`)); return }
    const body = { ...f, area_ha: f.area_ha === '' ? null : Number(f.area_ha) }
    try { await api(farm.id ? `/me/farms/${farm.id}` : '/me/farms', { method: farm.id ? 'PUT' : 'POST', body }); onSaved() } catch (x) { setErr(x) }
  }
  const toggle = (id) => setF({ ...f, crops: f.crops.includes(id) ? f.crops.filter((c) => c !== id) : [...f.crops, id] })
  return (
    <Modal onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <h3>{farm.id ? 'Edit farm' : 'Add farm'}</h3>
        <div className="grid g2">
          <div><label className="f" htmlFor="fn">Farm name</label><input id="fn" className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div><label className="f">Country</label>
            <Select label="Country" value={iso} onChange={changeCountry}
              options={(countries || []).map((c) => ({ value: c.iso3, label: c.name, group: c.grp === 'world' ? c.continent : 'Azerbaijan & neighbours' }))} /></div>
        </div>
        <div>
          <label className="f">Location: click your field on the map</label>
          <div style={{ height: 260, borderRadius: 12, overflow: 'hidden', border: '1px solid var(--line)' }}>
            <MapContainer center={f.lat ? [f.lat, f.lon] : [40.3, 47.7]} zoom={f.lat ? 10 : 6} style={{ height: '100%' }}>
              {sat?.truecolor && <TileLayer attribution="Imagery: NASA GIBS (VIIRS, HLS Landsat/Sentinel-2)" url={sat.truecolor} maxNativeZoom={9} maxZoom={16} />}
              {(sat?.hls || []).map((u) => <TileLayer key={u} url={u} maxNativeZoom={12} maxZoom={16} />)}
              {sat?.base && <TileLayer url={sat.base.features} maxNativeZoom={13} maxZoom={16} />}
              {sat?.base && <TileLayer url={sat.base.labels} maxNativeZoom={13} maxZoom={16} />}
              {geo && <GeoJSON key={iso} data={geo} style={(ft) => ({ weight: 1, color: '#FFFFFF', opacity: 0.7, fillOpacity: ft.properties.id === f.rayon_id ? 0.18 : 0, fillColor: '#F2561D' })} />}
              {geo && !f.lat && <FitTo geo={geo} />}
              <Picker pos={f.lat ? [f.lat, f.lon] : null} onPick={pick} />
            </MapContainer>
          </div>
        </div>
        <div className="grid g2">
          <div><label className="f" htmlFor="fr">{az ? 'District' : 'Province'}</label>
            <Select id="fr" label={az ? 'District' : 'Province'} value={f.rayon_id} placeholder={az ? 'Choose district' : 'Choose province'} onChange={(v) => setF({ ...f, rayon_id: v })}
              options={(units || []).map((r) => ({ value: r.id, label: r.name, group: az ? r.econ : undefined }))} /></div>
          <div><label className="f" htmlFor="fa">Area, ha</label><input id="fa" type="number" min="0" step="0.1" className="input" value={f.area_ha} onChange={(e) => setF({ ...f, area_ha: e.target.value })} /></div>
        </div>
        <Switch checked={f.irrigated} onChange={(v) => setF({ ...f, irrigated: v })}>Irrigated land</Switch>
        <div><label className="f">Crops you grow</label>
          <div className="chips">{crops.map((c) => <button type="button" key={c.id} className={`chip ${f.crops.includes(c.id) ? 'on' : ''}`} onClick={() => toggle(c.id)}>{c.name}</button>)}</div></div>
        <ErrorBox error={err} />
        <div className="row"><button className="btn">Save farm</button><button type="button" className="btn light" onClick={onClose}>Cancel</button></div>
      </form>
    </Modal>
  )
}

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ago, api, useApi, useAuth } from '../lib.jsx'
import { ErrorBox, Icon, Spinner, Title } from '../ui.jsx'
import { WeatherStrip } from './Rayon.jsx'

const KIND_ICON = { frost: 'snow', heat: 'sun', 'heavy rain': 'drop', wind: 'wind', drought: 'thermo', 'forecast error': 'chart', 'satellite drought': 'sat', fire: 'fire' }

export default function Alerts() {
  const { user, ready, refresh } = useAuth()
  const { data: alerts, error, reload } = useApi(user ? '/me/alerts' : null)
  const { data: sms, reload: reloadSms } = useApi(user ? '/me/sms' : null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)
  useEffect(() => { if (user?.unread) api('/me/alerts/read', { method: 'POST' }).then(refresh) }, [alerts]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!ready) return <Spinner />
  if (!user) return <div className="card empty"><Icon n="bell" s={40} /><p style={{ marginTop: 10 }}>Sign in and add a farm to get alerts.</p>
    <Link to="/account" className="btn" style={{ marginTop: 14 }}>Sign in</Link></div>
  const check = async () => {
    setBusy(true); setNote(null)
    try { const r = await api('/me/alerts/check', { method: 'POST' }); setNote((r.created ? `${r.created} new alert(s)` : 'No new risks in the next 7 days') + (r.failed?.length ? `. Forecast unavailable right now for: ${r.failed.join(', ')}; it will be retried automatically.` : '')); reload(); reloadSms() } catch (e) { setNote(e.message) } finally { setBusy(false) }
  }
  return (
    <>
      <div className="between">
        <Title dark="Early warning." orange="Every farm, every 3 hours." />
        <div className="row"><button className="btn" onClick={check} disabled={busy || !user.farms.length}><Icon n="eye" s={18} />{busy ? 'Checking…' : 'Check my farms now'}</button></div>
      </div>
      <p className="lead" style={{ marginTop: 14 }}>The app checks every farm against the live 16-day forecast every 3 hours and compares
        earlier forecasts with what actually happened. High-risk alerts also go out as SMS.</p>
      {note && <div className="ok" style={{ marginTop: 14 }}>{note}</div>}
      {!user.farms.length && <div className="card" style={{ marginTop: 18 }}>You have no farms yet. <Link to="/account" className="or b">Add a farm</Link> to start monitoring.</div>}
      <div className="split" style={{ marginTop: 26 }}>
        <div className="stack">
          <ErrorBox error={error} />
          {user.farms.map((f) => <FarmForecast key={f.id} farm={f} />)}
          <h3 style={{ marginTop: 10 }}>Alert history</h3>
          {!alerts ? <Spinner /> : alerts.length ? alerts.map((a) => (
            <div key={a.id} className={`alert ${a.severity === 'medium' ? 'orta' : ''} ${a.read ? '' : 'unread'}`}>
              <div className="ibox" style={{ width: 44, height: 44, background: a.severity === 'high' ? 'var(--or)' : '#F2B33D' }}><Icon n={KIND_ICON[a.kind] || 'bell'} s={22} /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="between"><b>{a.title}</b><span className="xs muted">{a.farm} · {ago(a.created_at)}</span></div>
                <p className="small muted" style={{ marginTop: 4 }}>{a.body}</p>
                <div className="adv">Advice: {a.advice}</div>
                <div className="xs faint" style={{ marginTop: 6 }}>Risk: {a.severity}{a.sms_status ? ` · SMS: ${a.sms_status}` : ''}</div>
              </div>
            </div>)) : <div className="card empty">No alerts yet. Quiet weather ahead for your farms.</div>}
        </div>
        <div>
          <div className="phone">
            <div className="notch" />
            <div className="ph-head">Messages · FieldShift<div className="xs faint">{user.phone || 'no phone number set'}</div></div>
            <div className="ph-body">
              {sms?.length ? sms.map((m) => (
                <div key={m.id} className="bubble">{m.body}<div className="meta">{ago(m.created_at)} · {m.status}</div></div>
              )) : <p className="xs faint" style={{ textAlign: 'center', marginTop: 40 }}>No SMS yet. High-risk alerts appear here.</p>}
            </div>
          </div>
          <p className="xs faint" style={{ textAlign: 'center', marginTop: 22 }}>SMS delivery is simulated: messages are generated exactly
            as they would be sent, but no real gateway is used.</p>
        </div>
      </div>
    </>
  )
}

function FarmForecast({ farm }) {
  const { data } = useApi(`/rayons/${farm.rayon_id}/forecast`)
  return (
    <div className="card">
      <div className="between"><h3>{farm.name} · {farm.rayon}</h3><Link to={`/r/${farm.rayon_id}?tab=weather`} className="small or b">Details</Link></div>
      <div style={{ marginTop: 12 }}>{data ? <WeatherStrip f={{ ...data, daily: { ...data.daily } }} /> : <Spinner />}</div>
    </div>
  )
}

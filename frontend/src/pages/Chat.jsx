import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, getToken, useApi, useAuth } from '../lib.jsx'
import { Icon, Spinner, Title } from '../ui.jsx'

// Minimal, safe markdown for assistant replies: **bold**, *italic*, `code`, headings, bullet/numbered lists.
// Builds React elements only (no innerHTML), so model output can never inject markup.
function inline(text) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**') && p.length > 4) return <b key={i}>{p.slice(2, -2)}</b>
    if (p.startsWith('`') && p.endsWith('`') && p.length > 2) return <code key={i}>{p.slice(1, -1)}</code>
    if (p.startsWith('*') && p.endsWith('*') && p.length > 2) return <i key={i}>{p.slice(1, -1)}</i>
    return p
  })
}
function Md({ text }) {
  const out = []
  let list = null
  const flush = () => { if (list) { out.push(list.ordered ? <ol key={out.length}>{list.items}</ol> : <ul key={out.length}>{list.items}</ul>); list = null } }
  let table = null
  const flushT = () => {
    if (!table) return
    const [head, ...body] = table
    out.push(<div key={`t${out.length}`} className="md-tw"><table className="md-t"><thead><tr>{head.map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead>
      <tbody>{body.map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>)}</tbody></table></div>)
    table = null
  }
  text.split('\n').forEach((line, i) => {
    const t = line.trim()
    if (t.startsWith('|')) {
      flush()
      if (/^\|[\s:|-]+\|?$/.test(t)) return          // separator row
      const cells = t.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      table = table ? [...table, cells] : [cells]
      return
    }
    flushT()
    const b = t.match(/^[-*•]\s+(.*)/), n = t.match(/^\d+[.)]\s+(.*)/), h = t.match(/^#{1,4}\s+(.*)/)
    if (b || n) {
      const ordered = !!n
      if (!list || list.ordered !== ordered) { flush(); list = { ordered, items: [] } }
      list.items.push(<li key={i}>{inline((b || n)[1])}</li>)
      return
    }
    flush()
    if (!t) return
    if (h) out.push(<p key={i} className="md-h">{inline(h[1])}</p>)
    else if (/^-{3,}$/.test(t)) out.push(<hr key={i} />)
    else out.push(<p key={i}>{inline(t)}</p>)
  })
  flush(); flushT()
  return <div className="md">{out}</div>
}

const THINK = ['Understanding your question', 'Choosing data sources', 'Planning the analysis']

function Thinking() {
  const [k, setK] = useState(0)
  useEffect(() => { const t = setInterval(() => setK((x) => (x + 1) % THINK.length), 1600); return () => clearInterval(t) }, [])
  return (
    <div className="think">
      <span className="orb"><i /><i /><i /></span>
      <span className="shimmer" key={k}>{THINK[k]}…</span>
    </div>
  )
}

function Steps({ steps, live }) {
  const [open, setOpen] = useState(true)
  useEffect(() => { if (!live && steps.length) setOpen(false) }, [live]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!steps.length) return null
  return (
    <div className="steps">
      {!live && <button className="steps-toggle" onClick={() => setOpen(!open)}>
        <Icon n="db" s={14} /> Checked {steps.length} data source{steps.length > 1 ? 's' : ''} <Icon n="chev" s={14} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />
      </button>}
      {open && steps.map((st) => (
        <div key={st.id} className={`step ${st.status}`}>
          <span className="st-ic">{st.status === 'run' ? <span className="st-spin" /> : st.status === 'ok' ? <Icon n="check" s={13} /> : '!'}</span>
          <div><div className="st-l">{st.label}{st.detail && <span className="st-d"> · {st.detail}</span>}</div><div className="st-s">{st.src}</div></div>
        </div>))}
    </div>
  )
}

function AssistantMsg({ m }) {
  const waiting = m.live && !m.content
  const running = m.steps?.some((st) => st.status === 'run')
  return (
    <div className="msg assistant" style={m.err ? { background: 'var(--red-soft)', color: 'var(--red)' } : undefined}>
      <Steps steps={m.steps || []} live={m.live} />
      {waiting && !running && <Thinking />}
      {m.content && <div className={m.live ? 'typing' : ''}><Md text={m.content} /></div>}
    </div>
  )
}

const SUGGEST = [
  'Which crops suit Imishli best on irrigated land?',
  'Is there frost risk in Shaki in the next two weeks?',
  'How has wheat yield in Barda changed since 2015?',
  'Which districts lead in hazelnut yield?',
]

export default function Chat() {
  const { user, ready } = useAuth()
  const [sp] = useSearchParams()
  const rayon = sp.get('rayon')
  const { data: meta } = useApi('/meta')
  const { data: hist } = useApi(user ? '/chat/history' : null)
  const [msgs, setMsgs] = useState([])
  const [text, setText] = useState(rayon ? `What should I plant in ${rayon} next season?` : '')
  const [busy, setBusy] = useState(false)
  const box = useRef(null)
  const stick = useRef(true)   // follow new text only while the reader is at the bottom
  useEffect(() => { if (hist) setMsgs(hist) }, [hist])
  useEffect(() => {
    const el = box.current
    if (el && stick.current) el.scrollTop = el.scrollHeight   // scroll the message list only, never the page
  }, [msgs, busy])
  const onScroll = () => {
    const el = box.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }
  if (!ready) return <Spinner />
  const patch = (fn) => setMsgs((x) => { const c = [...x]; c[c.length - 1] = fn({ ...c[c.length - 1] }); return c })
  const send = async (m) => {
    const q = (m ?? text).trim()
    if (!q || busy) return
    stick.current = true
    setMsgs((x) => [...x, { role: 'user', content: q }, { role: 'assistant', content: '', steps: [], live: true }]); setText(''); setBusy(true)
    try {
      const r = await fetch('/api/chat/stream', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Auth-Token': getToken() },
        body: JSON.stringify({ message: q, rayon_id: rayon }) })
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || `Error ${r.status}`) }
      const reader = r.body.getReader(), dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let nl
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl); buf = buf.slice(nl + 1)
          if (!line.trim()) continue
          const ev = JSON.parse(line)
          if (ev.t === 'step') patch((mm) => ({ ...mm, steps: [...mm.steps, { ...ev, status: 'run' }] }))
          else if (ev.t === 'step_done') patch((mm) => ({ ...mm, steps: mm.steps.map((st) => (st.id === ev.id ? { ...st, status: ev.ok ? 'ok' : 'err' } : st)) }))
          else if (ev.t === 'token') patch((mm) => ({ ...mm, content: mm.content + ev.v }))
          else if (ev.t === 'reset') patch((mm) => ({ ...mm, content: '' }))
          else if (ev.t === 'error') throw new Error(ev.v)
        }
      }
      patch((mm) => ({ ...mm, live: false }))
    } catch (e) { patch((mm) => ({ ...mm, live: false, err: true, content: mm.content || `⚠ ${e.message}` })) } finally { setBusy(false) }
  }
  const clear = async () => { await api('/chat/history', { method: 'DELETE' }); setMsgs([]) }
  return (
    <div className="split">
      <div className="card chat">
        <div className="between" style={{ paddingBottom: 12, borderBottom: '1px solid var(--line)' }}>
          <h3><Icon n="brain" s={20} className="or" /> AI agronomist</h3>
          {user && msgs.length > 0 && <button className="chip" onClick={clear}>Clear chat</button>}
        </div>
        {!user ? <div className="empty"><p>Sign in to chat with the AI agronomist.</p><Link to="/account" className="btn" style={{ marginTop: 14 }}>Sign in</Link></div> : (
          <>
            <div className="msgs" ref={box} onScroll={onScroll}>
              {!msgs.length && <div className="empty"><Icon n="chat" s={36} /><p style={{ marginTop: 8 }}>Ask about crops, yields, climate or weather for any district.</p></div>}
              {msgs.map((m, i) => (m.role === 'user'
                ? <div key={i} className="msg user">{m.content}</div>
                : <AssistantMsg key={i} m={m} />))}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); send() }}>
              <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your question…" maxLength={2000} disabled={meta && !meta.ai_chat} />
              <button className="btn" disabled={busy || !text.trim() || (meta && !meta.ai_chat)}>Send</button>
            </form>
          </>)}
      </div>
      <div className="stack">
        <Title dark="Ask the data." />
        <p className="small muted">The assistant (DeepSeek) answers from Field Shift's own database: NASA climate, official yields,
          soil, crop requirements and the live forecast. It names its source and says when data is missing.</p>
        {meta && !meta.ai_chat && <div className="err">AI chat is switched off on this server (no DEEPSEEK_API_KEY).</div>}
        {user && SUGGEST.map((s) => <button key={s} className="card tight" style={{ textAlign: 'left', cursor: 'pointer', width: '100%' }} onClick={() => send(s)} disabled={busy}>
          <span className="small b">{s}</span></button>)}
      </div>
    </div>
  )
}

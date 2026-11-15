import { useEffect, useState } from 'react'
import { useReveal } from './motion.js'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './lib.jsx'
import { useLang } from './i18n.jsx'
import KurApp from './pages/KurApp.jsx'
import Landing from './pages/Landing.jsx'
import Monitor from './pages/Monitor.jsx'
import { Icon, Logo } from './ui.jsx'
import Home from './pages/Home.jsx'
import MapPage from './pages/MapPage.jsx'
import Rayon from './pages/Rayon.jsx'
import Stats from './pages/Stats.jsx'
import Farmers, { Farmer } from './pages/Farmers.jsx'
import Account from './pages/Account.jsx'
import Alerts from './pages/Alerts.jsx'
import Chat from './pages/Chat.jsx'
import Feedback from './pages/Feedback.jsx'
import Data from './pages/Data.jsx'

// the Kür salt-water tool is the product; the older crop-planning pages stay reachable by URL
const NAV = [['/', 'nav_home'], ['/account', 'nav_account']]   // /data stays reachable by URL for judges

export default function App() {
  const { user } = useAuth()
  const { t, lang, setLang } = useLang()
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => { setOpen(false); if (!loc.hash) window.scrollTo(0, 0) }, [loc.pathname, loc.hash])
  useReveal(loc.pathname)
  if (loc.pathname === '/') return <Landing />
  if (loc.pathname === '/app') return <KurApp />
  if (loc.pathname === '/monitor') return <Monitor />
  return (
    <>
      <header className="top">
        <div className="wrap">
          <Link to="/" className="brand"><Logo s={32} />Field<span>Shift</span></Link>
          <nav className={`main ${open ? 'open' : ''}`}>
            {NAV.map(([to, l]) => <NavLink key={to} to={to} end>{t(l)}</NavLink>)}
          </nav>
          <div className="userbox">
            <button className="lang" onClick={() => setLang(lang === 'az' ? 'en' : 'az')} aria-label="Language">{lang === 'az' ? 'EN' : 'AZ'}</button>
            {user ? (
              <>
                <Link to="/#farm" className="bell" aria-label="Alerts"><Icon n="bell" s={18} />
                  {user.unread > 0 && <b>{user.unread}</b>}</Link>
                <Link to="/account" className="btn light sm"><span className="uname">{user.name.split(' ')[0]}</span>
                  <Icon n="users" s={16} /></Link>
              </>
            ) : <Link to="/account" className="btn sm">{t('sign_in')}</Link>}
            <button className="menu-btn" aria-label="Menu" onClick={() => setOpen(!open)}><Icon n="menu" s={20} /></button>
          </div>
        </div>
      </header>
      <main>
        <div className="wrap page" key={loc.pathname}>
          <Routes>
            <Route path="/" element={<KurApp />} />
            <Route path="/about" element={<Home />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/r/:id" element={<Rayon />} />
            <Route path="/stats" element={<Stats />} />
            <Route path="/farmers" element={<Farmers />} />
            <Route path="/farmers/:id" element={<Farmer />} />
            <Route path="/account" element={<Account />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/feedback" element={<Feedback />} />
            <Route path="/data" element={<Data />} />
            <Route path="*" element={<div className="empty"><h2 className="t"><span className="d">404</span></h2>
              <p>Page not found. <Link to="/" className="or b">Home</Link></p></div>} />
          </Routes>
        </div>
      </main>
      <footer className="foot">
        <div className="wrap">
          <div><b>Field Shift</b> · Team Earthly · NASA Space Apps Challenge 2026</div>
          <div className="faint">NASA SWOT · NASA POWER · NASA GIBS</div>
        </div>
      </footer>
    </>
  )
}

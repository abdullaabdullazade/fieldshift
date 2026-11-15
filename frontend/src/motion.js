import { useEffect } from 'react'

// Scroll reveal: cards, stats and panels fade up as they enter the viewport, staggered among siblings.
// A MutationObserver catches content that renders after data loads.
const SEL = '.card, .stat, .alert, .dark, .peach, .map-box, .phone'

export function useReveal(key) {
  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) }
    }, { rootMargin: '0px 0px -40px 0px', threshold: 0.05 })
    const scan = (root) => {
      root.querySelectorAll?.(SEL).forEach((el) => {
        if (el.classList.contains('rv') || el.closest('.modal, .sel-pop, .swap, .land') || el.parentElement?.closest('.rv')) return
        const sibs = [...el.parentElement.children].filter((c) => c.matches(SEL))
        el.style.setProperty('--d', `${Math.min(sibs.indexOf(el), 8) * 55}ms`)
        el.classList.add('rv')
        io.observe(el)
      })
    }
    const main = document.querySelector('main')
    if (!main) return undefined
    scan(main)
    const mo = new MutationObserver((ms) => ms.forEach((m) => m.addedNodes.forEach((n) => n.nodeType === 1 && scan(n.parentElement || n))))
    mo.observe(main, { childList: true, subtree: true })
    return () => {
      io.disconnect(); mo.disconnect()
      // elements tagged by this observer but not yet revealed would stay hidden forever: hand them to the next scan
      document.querySelectorAll('.rv:not(.in)').forEach((el) => el.classList.remove('rv'))
    }
  }, [key])
}

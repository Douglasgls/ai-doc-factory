import React, { useEffect, useRef, useState } from 'react'

interface RevealProps {
  children: React.ReactNode
  className?: string
  delayMs?: number
}

export const Reveal: React.FC<RevealProps> = ({ children, className = '', delayMs = 0 }) => {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.14 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delayMs}ms` }}
      className={`transition-all duration-700 ease-out motion-reduce:transition-none motion-reduce:opacity-100 motion-reduce:translate-y-0 ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
      } ${className}`}
    >
      {children}
    </div>
  )
}

interface CountUpProps {
  target: number
  decimals?: number
  prefix?: string
  suffix?: string
  durationMs?: number
}

export const CountUp: React.FC<CountUpProps> = ({
  target,
  decimals = 0,
  prefix = '',
  suffix = '',
  durationMs = 900,
}) => {
  const ref = useRef<HTMLSpanElement>(null)
  const [valor, setValor] = useState(0)
  const [iniciado, setIniciado] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIniciado(true)
          if (reduced) setValor(target)
          observer.disconnect()
        }
      },
      { threshold: 0.3 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [target])

  useEffect(() => {
    if (!iniciado) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let frame = 0
    const inicio = performance.now()
    const tick = (agora: number) => {
      const p = Math.min(1, (agora - inicio) / durationMs)
      const eased = 1 - Math.pow(1 - p, 3)
      setValor(target * eased)
      if (p < 1) frame = requestAnimationFrame(tick)
      else setValor(target)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [iniciado, target, durationMs])

  const formatado =
    decimals > 0
      ? valor.toFixed(decimals).replace('.', ',')
      : Math.round(valor).toString()

  return (
    <span ref={ref}>
      {prefix}
      {formatado}
      {suffix}
    </span>
  )
}


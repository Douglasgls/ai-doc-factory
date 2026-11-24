import React, { useState } from 'react'
import { formatarDuracao, minutosParaHorario } from '../utils/perfisJornadaFormato'
import { blocosDoDia, descricaoDoDia, diferencas, type Faixa, type ParametrosDia } from '../utils/reguaDia'

const X0 = 20
const LARGURA = 600
const PX_MIN = LARGURA / 1440
const Y_TRILHA = 30
const ALTURA = 26
const TICKS = [0, 3, 6, 9, 12, 15, 18, 21, 24]

const x = (min: number) => X0 + min * PX_MIN

const Rect: React.FC<{ f: Faixa; className: string; y?: number; h?: number; extra?: React.SVGProps<SVGRectElement> }> = ({
  f,
  className,
  y = Y_TRILHA,
  h = ALTURA,
  extra,
}) => <rect x={x(f.de)} y={y} width={(f.ate - f.de) * PX_MIN} height={h} rx={3} className={className} {...extra} />

const Amostra: React.FC<{ className: string; tracejado?: boolean }> = ({ className, tracejado }) => (
  <span
    aria-hidden="true"
    className={`inline-block w-3.5 h-3.5 rounded-sm align-[-2px] mr-1.5 ${className} ${tracejado ? 'border border-dashed' : ''}`}
  />
)

interface Props {
  atual: ParametrosDia
  /** Valores do Padrão; null quando a régua já é a do Padrão. */
  padrao: ParametrosDia | null
}

/** A régua do dia: 24h com o período noturno sombreado e um dia de exemplo a partir das 08:00. */
export const ReguaDoDia: React.FC<Props> = ({ atual, padrao }) => {
  const [mostrarPadrao, setMostrarPadrao] = useState(false)
  const b = blocosDoDia(atual)
  const dif = padrao ? diferencas(atual, padrao) : null
  const temDif = !!dif && (dif.jornada || dif.extras || dif.noturno)
  const bp = padrao && temDif ? blocosDoDia(padrao) : null

  const aria = `${descricaoDoDia(atual)}.`
  const contorno = 'fill-none stroke-[#2d0a33] dark:stroke-white'
  const inicioJornada = b.trabalho[0]?.de
  const fimJornada = b.trabalho[b.trabalho.length - 1]?.ate

  const alternar = temDif
    ? {
        tabIndex: 0,
        onMouseEnter: () => setMostrarPadrao(true),
        onMouseLeave: () => setMostrarPadrao(false),
        onFocus: () => setMostrarPadrao(true),
        onBlur: () => setMostrarPadrao(false),
        onClick: () => setMostrarPadrao((v) => !v),
      }
    : {}

  return (
    <figure className="m-0">
      <div
        {...alternar}
        className="overflow-x-auto rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3e0b48] dark:focus-visible:outline-[#f38df9]"
      >
        <svg
          role="img"
          aria-label={aria}
          viewBox="0 0 640 92"
          className="w-full min-w-[520px] max-w-[760px] h-auto"
          xmlns="http://www.w3.org/2000/svg"
        >
          <rect x={X0} y={Y_TRILHA} width={LARGURA} height={ALTURA} rx={3} className="fill-[#f4e8f7] dark:fill-[#2a1733]" />
          {b.noturno.map((f, i) => (
            <Rect key={`n${i}`} f={f} className="fill-[#4338ca]/25 dark:fill-[#a5b4fc]/25" />
          ))}
          {b.trabalho.map((f, i) => (
            <Rect key={`t${i}`} f={f} className="fill-[#3e0b48] dark:fill-[#9917a2]" />
          ))}
          {b.extras && <Rect f={b.extras} className="fill-[#c77fd0] dark:fill-[#6b2a75]" />}

          {bp && mostrarPadrao && (
            <g aria-hidden="true" className="transition-opacity motion-reduce:transition-none">
              {dif?.noturno && bp.noturno.map((f, i) => (
                <Rect key={`pn${i}`} f={f} y={Y_TRILHA - 5} h={ALTURA + 10} className={contorno} extra={{ strokeDasharray: '4 3', strokeWidth: 1.5 }} />
              ))}
              {dif?.jornada && bp.trabalho.length > 0 && (
                <Rect
                  f={{ de: bp.trabalho[0].de, ate: bp.trabalho[bp.trabalho.length - 1].ate }}
                  y={Y_TRILHA - 5}
                  h={ALTURA + 10}
                  className={contorno}
                  extra={{ strokeDasharray: '4 3', strokeWidth: 1.5 }}
                />
              )}
              {dif?.extras && bp.extras && (
                <Rect f={bp.extras} y={Y_TRILHA - 5} h={ALTURA + 10} className={contorno} extra={{ strokeDasharray: '4 3', strokeWidth: 1.5 }} />
              )}
              <text x={X0} y={14} fontSize={12} className="fill-[#2d0a33] dark:fill-white">
                Contorno tracejado: Padrão
              </text>
            </g>
          )}

          {inicioJornada !== undefined && (
            <text x={x(inicioJornada)} y={Y_TRILHA - 8} fontSize={12} className="fill-[#6e6378] dark:fill-[#a093a8] tabular-nums">
              {minutosParaHorario(inicioJornada)}
            </text>
          )}
          {fimJornada !== undefined && !(mostrarPadrao && temDif) && (
            <text x={x(fimJornada)} y={Y_TRILHA - 8} fontSize={12} textAnchor="end" className="fill-[#6e6378] dark:fill-[#a093a8] tabular-nums">
              {minutosParaHorario(fimJornada)}
            </text>
          )}

          {TICKS.map((h) => (
            <g key={h}>
              <line x1={x(h * 60)} x2={x(h * 60)} y1={Y_TRILHA + ALTURA} y2={Y_TRILHA + ALTURA + 6} className="stroke-[#877991] dark:stroke-[#a093a8]" />
              <text
                x={x(h * 60)}
                y={Y_TRILHA + ALTURA + 22}
                fontSize={12}
                textAnchor={h === 0 ? 'start' : h === 24 ? 'end' : 'middle'}
                className="fill-[#6e6378] dark:fill-[#a093a8] tabular-nums"
              >
                {String(h).padStart(2, '0')}h
              </text>
            </g>
          ))}
        </svg>
      </div>
      <figcaption className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-[#6e6378] dark:text-[#a093a8] tabular-nums">
        <span>
          <Amostra className="bg-[#3e0b48] dark:bg-[#9917a2]" />
          Jornada de {formatarDuracao(atual.jornada)}
          {atual.intervalo > 0 && <>, com {formatarDuracao(atual.intervalo)} de intervalo</>}
        </span>
        {atual.extras > 0 && (
          <span>
            <Amostra className="bg-[#c77fd0] dark:bg-[#6b2a75]" />
            Limite de horas extras: {formatarDuracao(atual.extras)}
          </span>
        )}
        <span>
          <Amostra className="bg-[#4338ca]/25 dark:bg-[#a5b4fc]/25" />
          Período noturno: {minutosParaHorario(atual.noturnoInicio)} às {minutosParaHorario(atual.noturnoFim)}
        </span>
        {temDif && <span>Passe o mouse ou toque para ver o Padrão.</span>}
      </figcaption>
    </figure>
  )
}

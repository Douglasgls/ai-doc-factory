import React from 'react'
import '../styles/brand.css'

interface EviDocsBrandProps {
  className?: string
  sizeClass?: string
}

export const EviDocsBrand: React.FC<EviDocsBrandProps> = ({
  className = '',
  sizeClass = 'text-3xl sm:text-4xl',
}) => {
  return (
    <div
      className={`brand-container ${sizeClass} ${className}`}
      aria-label="EviDocs"
      role="img"
    >
      {/* Camada 1: Aura suave */}
      <span className="brand-aura" aria-hidden="true">
        EviDocs
      </span>

      {/* Camada 2: Reflexo luminoso estreito */}
      <span className="brand-sweep" aria-hidden="true">
        EviDocs
      </span>

      {/* Camada 3: Texto principal */}
      <span className="brand-main" aria-hidden="true">
        <span className="brand-evi">Evi</span>
        <span className="brand-docs">Docs</span>
      </span>
    </div>
  )
}

export default EviDocsBrand

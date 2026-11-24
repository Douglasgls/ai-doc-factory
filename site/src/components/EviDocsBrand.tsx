import React from 'react'

interface EviDocsBrandProps {
  className?: string
  sizeClass?: string
}

export const EviDocsBrand: React.FC<EviDocsBrandProps> = ({
  className = '',
  sizeClass = 'text-2xl',
}) => {
  return (
    <span
      className={`brand relative inline-flex items-baseline font-extrabold tracking-tight select-none ${sizeClass} ${className}`}
      aria-label="EviDocs"
    >
      <span className="brand-aura absolute inset-0 pointer-events-none select-none" aria-hidden="true">
        EviDocs
      </span>
      <span className="brand-sweep absolute inset-0 pointer-events-none select-none" aria-hidden="true">
        EviDocs
      </span>
      <span className="brand-evi relative z-[1]">Evi</span>
      <span className="brand-docs relative z-[1]">Docs</span>
    </span>
  )
}


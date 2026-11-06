import React from 'react'

export const BackgroundWave: React.FC = () => {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
      {/* Curved abstract dynamic wave backdrop */}
      <svg
        className="absolute top-0 right-0 w-[140vw] sm:w-[110vw] lg:w-[90vw] h-[120vh] -translate-y-12 translate-x-1/4 opacity-70 dark:opacity-40 transition-opacity duration-300"
        viewBox="0 0 1200 1000"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M300 -100 C 650 150, 750 400, 500 700 C 350 880, 200 950, 50 1100 L 1400 1100 L 1400 -100 Z"
          fill="url(#wave-gradient)"
        />
        <path
          d="M480 -120 C 780 120, 920 450, 680 750 C 520 950, 360 1020, 150 1150 L 1400 1150 L 1400 -120 Z"
          fill="url(#wave-gradient-light)"
          opacity="0.5"
        />
        <defs>
          <linearGradient id="wave-gradient" x1="400" y1="0" x2="1000" y2="1000" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#c084fc" stopOpacity="0.12" />
            <stop offset="50%" stopColor="#d946ef" stopOpacity="0.06" />
            <stop offset="100%" stopColor="#a855f7" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="wave-gradient-light" x1="600" y1="0" x2="1200" y2="1000" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#e879f9" stopOpacity="0.08" />
            <stop offset="100%" stopColor="#a855f7" stopOpacity="0.0" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  )
}


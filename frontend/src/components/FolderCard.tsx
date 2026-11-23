import React from 'react'
import { Car, Hash, IdCard, Home, FileText, Briefcase } from 'lucide-react'
import type { DocumentCategory } from '../types'

interface FolderCardProps {
  category: DocumentCategory
  isSelected?: boolean
  onClick: (category: DocumentCategory) => void
}

export const FolderCard: React.FC<FolderCardProps> = ({
  category,
  isSelected = false,
  onClick,
}) => {
  const getIcon = () => {
    const iconClass = "w-5 h-5 transition-transform duration-200 group-hover:scale-105"
    switch (category.icon) {
      case 'car':
        return <Car className={iconClass} />
      case 'hash':
        return <Hash className={iconClass} />
      case 'idcard':
        return <IdCard className={iconClass} />
      case 'home':
        return <Home className={iconClass} />
      case 'file':
        return <FileText className={iconClass} />
      case 'briefcase':
        return <Briefcase className={iconClass} />
      default:
        return <FileText className={iconClass} />
    }
  }

  const hasDocuments = category.count > 0

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${category.name}: ${category.count > 0 ? `${category.count} documento${category.count > 1 ? 's' : ''}` : 'sem documentos'}`}
      onClick={() => onClick(category)}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onClick(category)
        }
      }}
      className="group relative cursor-pointer transition-all duration-200 select-none flex flex-col h-full w-full rounded-2xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9333ea]"
    >
      {/* Folder Tab (Aba superior da pasta) */}
      <div className="relative pl-0 w-full shrink-0">
        <div
          className={`w-[48%] h-3.5 rounded-t-xl transition-all duration-200 -mb-[1px] relative z-10 ${
            isSelected
              ? 'bg-white dark:bg-[#1a1120] border-t-2 border-l-2 border-r-2 border-[#c026d3]'
              : 'bg-white dark:bg-[#1a1120] border-t border-l border-r border-[#ebe5ef] dark:border-[#2f1e39] group-hover:border-t-2 group-hover:border-l-2 group-hover:border-r-2 group-hover:border-[#c026d3]'
          }`}
        />
      </div>

      {/* Folder Body (Corpo da pasta com dimensões padronizadas e uniformes) */}
      <div
        className={`w-full h-[155px] rounded-b-2xl rounded-tr-2xl p-5 pt-4 transition-all duration-200 flex flex-col justify-between relative z-0 ${
          isSelected
            ? 'bg-white dark:bg-[#1a1120] border-2 border-[#c026d3] shadow-[0_0_20px_rgba(192,38,211,0.22)]'
            : 'bg-white dark:bg-[#1a1120] border border-[#ebe5ef] dark:border-[#2f1e39] shadow-xs group-hover:border-2 group-hover:border-[#c026d3] group-hover:shadow-[0_0_20px_rgba(192,38,211,0.22)]'
        }`}
      >
        {/* Category Icon Badge */}
        <div
          className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 transition-all duration-200 ${
            isSelected
              ? 'bg-[#b833ca] text-white shadow-xs'
              : 'bg-[#f7edf9] text-[#9333ea] dark:bg-[#281530] dark:text-[#d67bf3] group-hover:bg-[#b833ca] group-hover:text-white group-hover:shadow-xs'
          }`}
        >
          {getIcon()}
        </div>

        {/* Title & Document Count */}
        <div className="mt-2 min-h-[48px] flex flex-col justify-end">
          <h4 className="text-base font-bold text-[#2d0a33] dark:text-[#f8f5fc] leading-snug line-clamp-2 group-hover:text-[#9333ea] dark:group-hover:text-[#f38df9] transition-colors">
            {category.name}
          </h4>
          <p
            className={`text-sm mt-0.5 ${
              hasDocuments
                ? 'text-[#6e6378] dark:text-[#9f91a6]'
                : 'text-[#a197a9] dark:text-[#5f5367]'
            }`}
          >
            {hasDocuments
              ? `${category.count} documento${category.count > 1 ? 's' : ''}`
              : 'Sem documentos'}
          </p>
        </div>
      </div>
    </div>
  )
}

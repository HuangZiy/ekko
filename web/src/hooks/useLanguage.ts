import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

type Language = 'en' | 'zh'

export function useLanguage() {
  const { i18n } = useTranslation()
  const [language, setLanguage] = useState<Language>((i18n.language?.startsWith('zh') ? 'zh' : 'en') as Language)

  const toggleLanguage = useCallback(() => {
    const next: Language = language === 'en' ? 'zh' : 'en'
    void i18n.changeLanguage(next)
    setLanguage(next)
  }, [language, i18n])

  return { language, toggleLanguage } as const
}

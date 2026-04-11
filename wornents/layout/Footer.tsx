import type { Dictionary } from '@/lib/i18n'
import styles from './Footer.module.css'

interface FooterProps {
  dict: Dictionary
}

export function Footer({ dict }: FooterProps) {
  const year = new Date().getFullYear()
  const copyright = dict.foer.copyright.replace('{year}', String(year))

  return (
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        <span>{copyright}</span>
        <div className={styles.footerLinks}>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.footerLink}
          >
            GitHub
          </a>
          <a href="/feed.xml" className={styles.footerLink}>
            {dict.footer.rss}
          </a>
        </div>
      </div>
    </footer>
  )
}

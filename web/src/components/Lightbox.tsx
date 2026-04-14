import { useState, useEffect, useCallback } from 'react'
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react'

interface MediaItem {
  url: string
  type: 'image' | 'video'
}

interface LightboxProps {
  /** @deprecated Use `media` instead */
  images?: string[]
  media?: MediaItem[]
  initialIndex: number
  onClose: () => void
}

export function Lightbox({ images, media, initialIndex, onClose }: LightboxProps) {
  // Support both legacy `images` prop and new `media` prop
  const items: MediaItem[] = media
    ? media
    : (images || []).map(url => ({ url, type: 'image' as const }))

  const [index, setIndex] = useState(initialIndex)
  const [scale, setScale] = useState(1)

  const currentItem = items[index]
  const isVideo = currentItem?.type === 'video'

  const goNext = useCallback(() => {
    setIndex(i => (i + 1) % items.length)
    setScale(1)
  }, [items.length])

  const goPrev = useCallback(() => {
    setIndex(i => (i - 1 + items.length) % items.length)
    setScale(1)
  }, [items.length])

  const zoomIn = useCallback(() => setScale(s => Math.min(s + 0.5, 4)), [])
  const zoomOut = useCallback(() => setScale(s => Math.max(s - 0.5, 0.5)), [])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight') goNext()
      else if (e.key === 'ArrowLeft') goPrev()
      else if (e.key === '+' || e.key === '=') zoomIn()
      else if (e.key === '-') zoomOut()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose, goNext, goPrev, zoomIn, zoomOut])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    if (e.deltaY < 0) zoomIn()
    else zoomOut()
  }, [zoomIn, zoomOut])

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80"
      onClick={onClose}
    >
      {/* Toolbar */}
      <div
        className="absolute top-4 right-4 flex items-center gap-2 z-10"
        onClick={e => e.stopPropagation()}
      >
        <span className="text-white/70 text-sm">
          {index + 1} / {items.length}
        </span>
        {!isVideo && (
          <>
            <button
              onClick={zoomOut}
              className="p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
              title="Zoom out"
            >
              <ZoomOut size={18} />
            </button>
            <button
              onClick={zoomIn}
              className="p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
              title="Zoom in"
            >
              <ZoomIn size={18} />
            </button>
          </>
        )}
        <button
          onClick={onClose}
          className="p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
          title="Close (Esc)"
        >
          <X size={18} />
        </button>
      </div>

      {/* Navigation arrows */}
      {items.length > 1 && (
        <>
          <button
            className="absolute left-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-10"
            onClick={e => { e.stopPropagation(); goPrev() }}
          >
            <ChevronLeft size={24} />
          </button>
          <button
            className="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors z-10"
            onClick={e => { e.stopPropagation(); goNext() }}
          >
            <ChevronRight size={24} />
          </button>
        </>
      )}

      {/* Media content */}
      <div
        className="max-w-[90vw] max-h-[90vh] overflow-auto"
        onClick={e => e.stopPropagation()}
        onWheel={!isVideo ? handleWheel : undefined}
      >
        {isVideo ? (
          <video
            key={currentItem.url}
            src={currentItem.url}
            controls
            autoPlay
            className="max-w-[90vw] max-h-[85vh]"
            style={{ outline: 'none' }}
          />
        ) : (
          <img
            src={currentItem?.url}
            alt={`Screenshot ${index + 1}`}
            className="transition-transform duration-200"
            style={{ transform: `scale(${scale})`, transformOrigin: 'center center' }}
            draggable={false}
          />
        )}
      </div>
    </div>
  )
}

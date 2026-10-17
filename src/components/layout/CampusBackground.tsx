'use client'

import { usePathname } from 'next/navigation'

const BGS = [
  '/campus1.jpg',
  '/campus2.jpg',
  '/campus3.jpg',
  '/campus4.jpg',
  '/campus5.png',
  '/campus6.png',
]

function hashPath(path: string): number {
  let h = 0
  for (let i = 0; i < path.length; i++) h = ((h << 5) - h) + path.charCodeAt(i) | 0
  return Math.abs(h)
}

export default function CampusBackground() {
  const pathname = usePathname()
  const idx = hashPath(pathname) % BGS.length
  const bg = BGS[idx]

  return (
    <div
      className="fixed inset-0 pointer-events-none"
      style={{
        backgroundImage: `url(${bg})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        backgroundAttachment: 'fixed',
        opacity: 0.18,
        zIndex: 0,
      }}
    />
  )
}

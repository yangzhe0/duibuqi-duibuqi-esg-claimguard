import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import type { Evidence } from '../types'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

type Props = {
  url: string
  evidence: Evidence | null
  requestedPage: number
}

export function PdfEvidenceViewer({ url, evidence, requestedPage }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null)
  const [page, setPage] = useState(requestedPage || 1)
  const [rendering, setRendering] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setDocument(null)
    setError('')
    const task = pdfjsLib.getDocument(url)
    task.promise
      .then((loaded) => {
        if (!cancelled) setDocument(loaded)
      })
      .catch((reason: Error) => !cancelled && setError(reason.message))
    return () => {
      cancelled = true
      task.destroy()
    }
  }, [url])

  useEffect(() => {
    if (requestedPage > 0) setPage(requestedPage)
  }, [requestedPage])

  useEffect(() => {
    if (!document || !canvasRef.current) return
    let cancelled = false
    setRendering(true)
    document
      .getPage(Math.min(Math.max(page, 1), document.numPages))
      .then((pdfPage) => {
        if (cancelled || !canvasRef.current) return
        const baseViewport = pdfPage.getViewport({ scale: 1 })
        const available = Math.min(860, Math.max(360, window.innerWidth * 0.42))
        const scale = available / baseViewport.width
        const viewport = pdfPage.getViewport({ scale })
        const canvas = canvasRef.current
        const ratio = window.devicePixelRatio || 1
        canvas.width = Math.floor(viewport.width * ratio)
        canvas.height = Math.floor(viewport.height * ratio)
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`
        const context = canvas.getContext('2d')!
        return pdfPage.render({ canvas, canvasContext: context, viewport, transform: [ratio, 0, 0, ratio, 0, 0] }).promise
      })
      .then(() => !cancelled && setRendering(false))
      .catch((reason: Error) => {
        if (!cancelled) {
          setError(reason.message)
          setRendering(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [document, page])

  const box = evidence?.page_no === page && evidence.bbox.length === 4 ? evidence.bbox : null
  const overlayStyle = box
    ? {
        left: `${box[0] / 10}%`,
        top: `${box[1] / 10}%`,
        width: `${(box[2] - box[0]) / 10}%`,
        height: `${(box[3] - box[1]) / 10}%`,
      }
    : undefined

  return (
    <section className="pdf-viewer">
      <header className="pdf-toolbar">
        <div>
          <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)} aria-label="上一页">←</button>
          <span>第 {page} / {document?.numPages || '—'} 页</span>
          <button disabled={!document || page >= document.numPages} onClick={() => setPage((value) => value + 1)} aria-label="下一页">→</button>
        </div>
        <span className="viewer-status">{rendering ? '正在渲染' : box ? '证据已定位' : '原文预览'}</span>
      </header>
      <div className="pdf-stage">
        {error ? <div className="empty-state">PDF 加载失败：{error}</div> : null}
        {!document && !error ? <div className="document-skeleton" /> : null}
        <div className="canvas-wrap">
          <canvas ref={canvasRef} />
          {box ? <div className="evidence-overlay" style={overlayStyle}><span>证据</span></div> : null}
        </div>
      </div>
    </section>
  )
}

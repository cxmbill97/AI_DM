import { useEffect, useRef, useState } from 'react';
import type { PuzzleUploadResponse } from '../api';
import { uploadPuzzle } from '../api';
import { useT } from '../i18n';

interface PuzzleUploadModalProps {
  lang: string;
  onClose: () => void;
  onSuccess: (puzzleId: string, title: string) => void;
}

type Stage = 'idle' | 'uploading' | 'preview' | 'error';

const UPLOAD_STEPS = ['step_extract', 'step_parse', 'step_validate'] as const;

export function PuzzleUploadModal({ lang, onClose, onSuccess }: PuzzleUploadModalProps) {
  const { t } = useT();
  const [stage, setStage] = useState<Stage>('idle');
  const [dragOver, setDragOver] = useState(false);
  const [preview, setPreview] = useState<PuzzleUploadResponse | null>(null);
  const [error, setError] = useState('');
  const [stepIdx, setStepIdx] = useState(0);
  const [rawJson, setRawJson] = useState('');
  const [showRaw, setShowRaw] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const stepTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (stage === 'uploading') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStepIdx(0);
      stepTimerRef.current = setInterval(() => {
        setStepIdx((prev) => Math.min(prev + 1, UPLOAD_STEPS.length - 1));
      }, 700);
    } else {
      if (stepTimerRef.current) { clearInterval(stepTimerRef.current); stepTimerRef.current = null; }
    }
    return () => { if (stepTimerRef.current) clearInterval(stepTimerRef.current); };
  }, [stage]);

  async function handleFile(file: File) {
    setStage('uploading');
    setError('');
    setRawJson('');
    setShowRaw(false);
    try {
      const result = await uploadPuzzle(file, lang);
      setPreview(result);
      setStage('preview');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      try {
        const detail = JSON.parse(msg) as { last_json?: string };
        if (detail.last_json) setRawJson(detail.last_json);
      } catch { /* not JSON */ }
      setStage('error');
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="upload-overlay" onClick={onClose}>
      <div className="upload-modal" onClick={(e) => e.stopPropagation()}>
        <div className="upload-modal-header">
          <h2 className="upload-modal-title">{t('upload.puzzle_title')}</h2>
          <button className="upload-modal-close" onClick={onClose}>✕</button>
        </div>

        {stage === 'idle' && (
          <div
            className={`upload-dropzone${dragOver ? ' upload-dropzone--over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="upload-dropzone-icon">📄</div>
            <p className="upload-dropzone-hint">{t('upload.drop_hint')}</p>
            <p className="upload-dropzone-sub">{t('upload.size_hint')}</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              style={{ display: 'none' }}
              onChange={handleInputChange}
            />
          </div>
        )}

        {stage === 'uploading' && (
          <div className="upload-progress">
            <div className="upload-spinner" />
            <ol className="upload-steps">
              {UPLOAD_STEPS.map((step, i) => (
                <li key={step} className={`upload-step${i <= stepIdx ? ' upload-step--done' : ''}`}>
                  {t(`upload.${step}`)}
                </li>
              ))}
            </ol>
          </div>
        )}

        {stage === 'preview' && preview && (
          <div className="upload-preview">
            {preview.warning && <p className="upload-warning">⚠ {preview.warning}</p>}
            <h3 className="upload-preview-title">{preview.title}</h3>
            <div className="upload-preview-meta">
              <span className="tag-badge">{preview.difficulty}</span>
              <span className="tag-badge">{preview.key_fact_count} key facts</span>
              <span className="tag-badge">{preview.clue_count} clues</span>
              {preview.tags.map((tag) => <span key={tag} className="tag-badge">{tag}</span>)}
            </div>
            <div className="upload-preview-actions">
              <button className="btn btn-ghost" onClick={onClose}>{t('upload.cancel')}</button>
              <button className="btn btn-primary" onClick={() => onSuccess(preview.puzzle_id, preview.title)}>
                {t('upload.confirm')}
              </button>
            </div>
          </div>
        )}

        {stage === 'error' && (
          <div className="upload-error">
            <p className="error-text">{error}</p>
            {rawJson && (
              <details>
                <summary className="upload-raw-toggle" onClick={() => setShowRaw(!showRaw)}>
                  {t('upload.show_raw')}
                </summary>
                {showRaw && <pre className="upload-raw-json">{rawJson}</pre>}
              </details>
            )}
            <div className="upload-preview-actions">
              <button className="btn btn-ghost" onClick={onClose}>{t('upload.cancel')}</button>
              <button className="btn btn-primary" onClick={() => setStage('idle')}>{t('upload.retry')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

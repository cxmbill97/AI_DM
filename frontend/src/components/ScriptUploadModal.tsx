import { useEffect, useRef, useState } from 'react';
import type { ScriptUploadResponse } from '../api';
import { uploadScript } from '../api';
import { useT } from '../i18n';

interface ScriptUploadModalProps {
  lang: string;
  onClose: () => void;
  onSuccess: (scriptId: string, title: string) => void;
}

type Stage = 'idle' | 'uploading' | 'preview' | 'error';

// Cosmetic progress steps shown during upload
const UPLOAD_STEPS = ['step_extract', 'step_parse', 'step_validate'] as const;

export function ScriptUploadModal({ lang, onClose, onSuccess }: ScriptUploadModalProps) {
  const { t } = useT();
  const [stage, setStage] = useState<Stage>('idle');
  const [dragOver, setDragOver] = useState(false);
  const [preview, setPreview] = useState<ScriptUploadResponse | null>(null);
  const [error, setError] = useState<string>('');
  const [stepIdx, setStepIdx] = useState(0);
  const [rawJson, setRawJson] = useState<string>('');
  const [showRaw, setShowRaw] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const stepTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Advance cosmetic step indicator during upload
  useEffect(() => {
    if (stage === 'uploading') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStepIdx(0);
      stepTimerRef.current = setInterval(() => {
        setStepIdx((prev) => Math.min(prev + 1, UPLOAD_STEPS.length - 1));
      }, 700);
    } else {
      if (stepTimerRef.current) {
        clearInterval(stepTimerRef.current);
        stepTimerRef.current = null;
      }
    }
    return () => {
      if (stepTimerRef.current) clearInterval(stepTimerRef.current);
    };
  }, [stage]);

  async function handleFile(file: File) {
    setStage('uploading');
    setError('');
    setRawJson('');
    setShowRaw(false);
    try {
      const result = await uploadScript(file, lang);
      setPreview(result);
      setStage('preview');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
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

  function handleConfirm() {
    if (preview) {
      onSuccess(preview.script_id, preview.title);
    }
  }

  function handleRetry() {
    setStage('idle');
    setPreview(null);
    setError('');
    setRawJson('');
    setShowRaw(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-box script-upload-modal">
        <div className="modal-header">
          <h2 className="modal-title">{t('upload.title')}</h2>
          <button className="modal-close" onClick={onClose} aria-label="close">✕</button>
        </div>

        {/* IDLE — drop zone */}
        {stage === 'idle' && (
          <div
            className={`upload-dropzone${dragOver ? ' drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
          >
            <span className="upload-icon">📄</span>
            <p className="upload-hint">{t('upload.drop_hint')}</p>
            <p className="upload-size-hint">{t('upload.size_hint')}</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              style={{ display: 'none' }}
              onChange={handleInputChange}
            />
          </div>
        )}

        {/* UPLOADING — progress steps */}
        {stage === 'uploading' && (
          <div className="upload-progress">
            <div className="upload-spinner" />
            <p className="upload-parsing-label">{t('upload.parsing')}</p>
            <ul className="upload-steps">
              {UPLOAD_STEPS.map((key, idx) => (
                <li key={key} className={`upload-step ${idx <= stepIdx ? 'done' : 'pending'}`}>
                  <span className="step-icon">{idx <= stepIdx ? '✓' : '○'}</span>
                  {t(`upload.${key}`)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* PREVIEW — parsed script summary */}
        {stage === 'preview' && preview && (
          <div className="upload-preview">
            <h3 className="preview-title">{preview.title}</h3>
            <div className="preview-meta">
              <span>{preview.player_count}P</span>
              <span className="sep">·</span>
              <span>{preview.difficulty}</span>
              <span className="sep">·</span>
              <span>{preview.game_mode}</span>
            </div>
            <div className="preview-chars">
              {preview.character_names.map((name) => (
                <span key={name} className="char-chip">{name}</span>
              ))}
            </div>
            <div className="preview-stats">
              <span>{preview.phase_count} phases</span>
              <span className="sep">·</span>
              <span>{preview.clue_count} clues</span>
            </div>
            {preview.warning && (
              <div className="upload-warning">{t('upload.warning_truncated')}</div>
            )}
            <div className="preview-actions">
              <button className="btn btn-primary" onClick={handleConfirm}>{t('upload.confirm')}</button>
              <button className="btn btn-outline" onClick={onClose}>{t('upload.cancel')}</button>
            </div>
          </div>
        )}

        {/* ERROR */}
        {stage === 'error' && (
          <div className="upload-error">
            <p className="error-title">{t('upload.error_title')}</p>
            <p className="error-msg">{error}</p>
            {rawJson && (
              <details className="raw-output">
                <summary onClick={() => setShowRaw(!showRaw)}>{t('upload.raw_output')}</summary>
                {showRaw && <pre className="raw-json">{rawJson}</pre>}
              </details>
            )}
            <div className="error-actions">
              <button className="btn btn-primary" onClick={handleRetry}>{t('upload.retry')}</button>
              <button className="btn btn-outline" onClick={onClose}>{t('upload.cancel')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

import { FileAudio, FileImage, FileVideo, UploadCloud } from 'lucide-react';
import { useRef, useState } from 'react';

const MB = 1024 * 1024;

interface Props {
  accept: string;
  maxSize: number;
  onFile: (file: File) => void;
}

function iconForFile(file: File) {
  if (file.type.startsWith('image/')) return FileImage;
  if (file.type.startsWith('audio/')) return FileAudio;
  if (file.type.startsWith('video/')) return FileVideo;
  return FileVideo;
}

export default function FileUpload({ accept, maxSize, onFile }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validate = (file: File): string | null => {
    const okTypes = accept.split(',').map((a) => a.trim());
    const typeOk = okTypes.some((t) => (t.endsWith('/*') ? file.type.startsWith(t.slice(0, -1)) : file.type === t));
    if (!typeOk) return `Unsupported file type: ${file.type || 'unknown'}. Accepted: ${accept}`;
    if (file.size > maxSize) return `File too large (${(file.size / MB).toFixed(1)} MB). Max: ${maxSize / MB} MB`;
    return null;
  };

  const handleFile = (file: File) => {
    const err = validate(file);
    if (err) {
      setError(err);
      setSelected(null);
      return;
    }
    setError(null);
    setSelected(file);
    onFile(file);
  };

  const SelectedIcon = selected ? iconForFile(selected) : FileVideo;

  return (
    <div>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) handleFile(file);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragOver
            ? 'border-cyan-500 bg-cyan-500/10'
            : 'border-slate-700 bg-slate-800/30 hover:border-slate-500 hover:bg-slate-800/50'
        }`}
      >
        <UploadCloud className="h-8 w-8 text-cyan-400" />
        <p className="mt-3 text-sm font-medium text-slate-200">Drop media file here or click to browse</p>
        <p className="mt-1 text-xs text-slate-500">
          Accepted: image/*, audio/*, video/* — Max size: {maxSize / MB} MB
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
            e.target.value = '';
          }}
        />
      </div>

      {error && (
        <p className="mt-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>
      )}

      {selected && (
        <div className="mt-3 flex items-center gap-3 rounded-xl border border-slate-700/50 bg-slate-800/40 p-3">
          {selected.type.startsWith('image/') ? (
            <img src={URL.createObjectURL(selected)} alt="preview" className="h-12 w-12 rounded-lg object-cover" />
          ) : (
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-slate-700/50">
              <SelectedIcon className="h-5 w-5 text-cyan-400" />
            </div>
          )}
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-100">{selected.name}</div>
            <div className="font-mono text-[11px] text-slate-500">
              {(selected.size / 1024).toFixed(1)} KB — {selected.type || 'unknown type'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

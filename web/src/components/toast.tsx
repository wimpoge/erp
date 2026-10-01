"use client";

import { CheckCircle2, AlertTriangle, Info } from "lucide-react";
import { createContext, ReactNode, useCallback, useContext, useState } from "react";

type Tone = "success" | "error" | "info";
type Toast = { id: number; tone: Tone; message: string };

const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => {});

export const useToast = () => useContext(ToastContext);

const icons = {
  success: <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />,
  error: <AlertTriangle className="h-5 w-5 shrink-0 text-rose-400" />,
  info: <Info className="h-5 w-5 shrink-0 text-sky-400" />,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-2), { id, tone, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 6000 : 3000);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-50 lg:bottom-6 flex flex-col items-center gap-2 px-4 print:hidden" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto flex max-w-md items-start gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm text-white shadow-lg">
            {icons[t.tone]}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

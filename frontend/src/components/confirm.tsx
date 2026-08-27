import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

type ConfirmOptions = {
  title: string;
  body?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

const ConfirmContext = createContext<((options: ConfirmOptions) => Promise<boolean>) | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const okRef = useRef<HTMLButtonElement>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setPending({ ...options, resolve })),
    [],
  );

  useEffect(() => {
    if (pending) okRef.current?.focus();
  }, [pending]);

  const settle = (ok: boolean) => {
    pending?.resolve(ok);
    setPending(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <div
          className="scrim"
          onMouseDown={(e) => e.target === e.currentTarget && settle(false)}
          onKeyDown={(e) => {
            if (e.key === "Escape") settle(false);
            if (e.key === "Enter") settle(true);
          }}
        >
          <div
            className="dialog narrow"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
          >
            <div className="dialog-head">
              <h2 className="dialog-title" id="confirm-title">{pending.title}</h2>
              {pending.body && <div className="dialog-lede">{pending.body}</div>}
            </div>
            <div className="dialog-foot">
              <button className="btn" onClick={() => settle(false)}>
                {pending.cancelLabel ?? "Cancel"}
              </button>
              <button
                ref={okRef}
                className={pending.destructive ? "btn btn-danger" : "btn btn-primary"}
                onClick={() => settle(true)}
              >
                {pending.confirmLabel ?? "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm must be used inside <ConfirmProvider>");
  return confirm;
}

/** Shorthand for the delete case, which is most of them. */
export function useConfirmDelete() {
  const confirm = useConfirm();
  return useMemo(
    () => (what: string, detail?: string) =>
      confirm({
        title: `Delete ${what}?`,
        body: detail ?? "This cannot be undone.",
        confirmLabel: "Delete",
        destructive: true,
      }),
    [confirm],
  );
}

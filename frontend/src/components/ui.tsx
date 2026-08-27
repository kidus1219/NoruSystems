import { useEffect, useState, type ReactNode } from "react";

import type { AttendanceStatus } from "../api/types";

export function Card({ title, note, actions, children }: {
  title?: string; note?: string; actions?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {note && <p className="card-note">{note}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

export function Busy({ text = "Loading" }: { text?: string }) {
  return <div className="busy"><i />{text}</div>;
}

export function Blank({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="blank"><b>{title}</b>{children}</div>;
}

const TONE: Record<AttendanceStatus, string> = {
  present: "ok",
  late: "warn",
  absent: "bad",
  on_leave: "off",
  holiday: "off",
};

const WORDING: Record<AttendanceStatus, string> = {
  present: "Present",
  late: "Late",
  absent: "Absent",
  on_leave: "On leave",
  holiday: "Holiday",
};

export function Tag({ status }: { status: AttendanceStatus | null | undefined }) {
  if (!status) return <span className="tag off">Not recorded</span>;
  return (
    <span className={`tag ${TONE[status]}`}>
      <span className="dot" />
      {WORDING[status]}
    </span>
  );
}

export function Who({ name, sub }: { name: string; sub?: string }) {
  const initials = name.split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  return (
    <div className="who">
      <span className="mark">{initials}</span>
      <div>
        <div className="who-name">{name}</div>
        {sub && <div className="who-sub">{sub}</div>}
      </div>
    </div>
  );
}

export function Bar({ value, tone = "var(--ok)" }: { value: number; tone?: string }) {
  return (
    <div className="bar">
      <span style={{ width: `${Math.min(Math.max(value, 0), 100)}%`, background: tone }} />
    </div>
  );
}

export function Dialog({ title, lede, onClose, children, footer }: {
  title: string; lede?: string; onClose: () => void; children: ReactNode; footer: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="dialog-head">
          <h2 className="dialog-title">{title}</h2>
          {lede && <p className="dialog-lede">{lede}</p>}
        </div>
        <div className="dialog-body">{children}</div>
        <div className="dialog-foot">{footer}</div>
      </div>
    </div>
  );
}

export function Alert({ fields }: { fields: Record<string, string[]> | null }) {
  if (!fields) return null;
  const hideName = (key: string) => key === "detail" || key === "non_field_errors";
  return (
    <div className="alert">
      {Object.entries(fields).map(([key, messages]) => (
        <div key={key}>
          {!hideName(key) && <b>{key.replace(/_/g, " ")}: </b>}
          {messages.join(" ")}
        </div>
      ))}
    </div>
  );
}

export function useSnack() {
  const [snack, setSnack] = useState<{ text: string; bad: boolean } | null>(null);

  useEffect(() => {
    if (!snack) return;
    const timer = setTimeout(() => setSnack(null), 3500);
    return () => clearTimeout(timer);
  }, [snack]);

  return {
    say: (text: string, bad = false) => setSnack({ text, bad }),
    snack: snack ? <div className={`snack${snack.bad ? " bad" : ""}`}>{snack.text}</div> : null,
  };
}

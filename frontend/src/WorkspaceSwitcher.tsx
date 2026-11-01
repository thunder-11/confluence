import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Network } from "lucide-react";

// The local, single-user installation currently exposes one workspace.
// List actual workspaces here rather than presenting fictional choices.
const workspaces = [{ id: "local", name: "Local workspace", description: "DSA / Multi-agent systems" }];

export default function WorkspaceSwitcher() {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState("local");
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const current = workspaces.find((w) => w.id === selected) || workspaces[0];

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"]')?.focus();
    const outside = (e: PointerEvent) => {
      if (e.target instanceof Node && !root.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  return (
    <div className="workspace-switcher" ref={root} onBlur={(e) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
    }} onKeyDown={(e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!open) setOpen(true);
        else root.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"]')?.focus();
      }
    }}>
      <button ref={trigger} className="workspace" type="button"
        aria-label={`Select workspace: ${current.name}`} aria-haspopup="menu"
        aria-expanded={open} aria-controls="workspace-options"
        onClick={() => setOpen(!open)}>
        <span className="workspace-symbol"><Network size={17} /></span>
        <span className="workspace-copy" title={`${current.name} — ${current.description}`}>{current.name}<small>{current.description}</small></span>
        <ChevronDown size={14} className={open ? "workspace-chevron expanded" : "workspace-chevron"} />
      </button>
      {open && <div className="workspace-options" id="workspace-options" role="menu" aria-label="Select workspace">
        <div className="workspace-menu-label" role="presentation">Workspaces</div>
        {workspaces.map((workspace) => <button key={workspace.id} type="button"
          role="menuitemradio" aria-checked={selected === workspace.id}
          className="workspace-option" onClick={() => {
            setSelected(workspace.id);
            setOpen(false);
            trigger.current?.focus();
          }}>
          <Network size={16} />
          <span>{workspace.name}<small>{workspace.description}</small></span>
          {selected === workspace.id && <Check size={15} />}
        </button>)}
        <p className="workspace-menu-note" role="presentation">One local workspace is configured on this computer.</p>
      </div>}
    </div>
  );
}

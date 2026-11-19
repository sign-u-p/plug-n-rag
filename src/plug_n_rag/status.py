"""`plug-n-rag status`: freshness, model, errors, learned values, estimated savings."""

from __future__ import annotations

import sqlite3

from . import gitops, tuning
from .config import Layout
from .embed import model_id_for
from .index_store import read_meta
from .sync import pending_count
from .util import fmt_int, read_json


def _model_label(model_id: str) -> str:
    if not model_id:
        return "unbekannt"
    prov, _, rest = model_id.partition(":")
    name, _, rev = rest.partition("@")
    prov_de = {"local": "lokal", "voyage": "Voyage AI", "fake": "Test-Embedder"}.get(prov, prov)
    rev_s = f", Revision {rev[:8]}" if rev and prov == "local" else ""
    return f"{prov_de} · {name}{rev_s}"


def status(layout: Layout, *, check_remote: bool = True) -> str:
    cfg = layout.config
    kind = "Vault" if layout.mode == "vault" else "Sammlung"
    where = "im Ordner" if layout.location == "inside" else f"außerhalb ({layout.state_dir})"
    lines = [f"plug-n-rag · {kind} „{layout.root.name}“ · Index {where}"]
    meta = read_meta(layout.index_dir) or {}
    want = model_id_for(cfg)
    todo, total = pending_count(layout)
    lines.append(f"Dateien: {fmt_int(total)} durchsuchbar, davon {fmt_int(total - todo)} semantisch indexiert"
                 + (f", {fmt_int(todo)} ausstehend" if todo else ""))
    if meta.get("model") and meta["model"] != want:
        lines.append(f"⚠ Index passt nicht zum Modell: Index {_model_label(meta['model'])}, "
                     f"eingestellt {_model_label(want)}. Nur Stichwortsuche bis /plug-n-rag:reindex.")
    else:
        lines.append(f"Modell: {_model_label(want)} ✓")
    pend = read_json(layout.cache_dir / "pending.json", {}) or {}
    if pend.get("embed_error"):
        lines.append(f"⚠ Embedding zuletzt nicht möglich: {pend['embed_error']}")
    if pend.get("too_large"):
        lines.append("⚠ Zu groß (über 100 MB), nicht indexiert: " + ", ".join(pend["too_large"][:5]))
    try:
        conn = sqlite3.connect(str(layout.db_path))
        n_notes = conn.execute("SELECT count(*) FROM notes").fetchone()[0]
        n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        vec_ext = conn.execute("SELECT value FROM meta WHERE key='vec_ext'").fetchone()
        conn.close()
        engine = "sqlite-vec" if vec_ext and vec_ext[0] == "1" else "NumPy (sqlite-vec nicht ladbar)"
        lines.append(f"Suchdatenbank: {fmt_int(n_notes)} Dateien, {fmt_int(n_chunks)} Abschnitte, Vektorsuche über {engine}")
    except sqlite3.Error:
        lines.append("Suchdatenbank: noch nicht gebaut (entsteht beim nächsten Abgleich)")
    errors = read_json(layout.cache_dir / "errors.json", {}) or {}
    if errors:
        lines.append(f"Fehler bei {len(errors)} Dateien:")
        for path, msg in list(errors.items())[:8]:
            lines.append(f"  {path}: {msg}")
    else:
        lines.append("Fehler: keine")
    if gitops.inside_repo(layout.root) if layout.location == "inside" else False:
        url = gitops.remote_url(layout.root)
        if not url:
            lines.append("Git: lokales Repo ohne GitHub-Verbindung (keine Cloud-Sitzungen möglich)")
        else:
            vis = gitops.repo_visibility(layout.root) if check_remote else None
            if vis == "public":
                lines.append("⚠ Git: Das Repo ist ÖFFENTLICH. Notizen und Index sind für alle sichtbar. "
                             "Dringend auf privat stellen.")
            elif vis in ("private", "internal"):
                lines.append("Git: Repo auf GitHub, privat ✓")
            else:
                lines.append("Git: Repo mit Remote, Sichtbarkeit nicht prüfbar (GitHub-CLI fehlt oder nicht angemeldet)")
    lines.append("Token-Steuerung (" + tuning.tuning_location_note(layout) + "):")
    lines += ["  " + ln for ln in tuning.describe(layout)]
    n, delivered, full = tuning.savings(layout)
    if n and full:
        pct = max(0, round(100 * (1 - delivered / full)))
        lines.append(f"Ersparnis (Schätzung): {fmt_int(n)} Suchen lieferten {fmt_int(delivered)} Tokens statt "
                     f"{fmt_int(full)} Tokens beim vollständigen Lesen der Trefferdateien (−{pct} %).")
    return "\n".join(lines)

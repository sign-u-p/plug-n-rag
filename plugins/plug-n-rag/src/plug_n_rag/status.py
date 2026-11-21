"""`plug-n-rag status`: freshness, model, errors, learned values, estimated savings."""

from __future__ import annotations

import sqlite3

from . import gitops, tuning
from .config import Layout
from .embed import model_id_for
from .index_store import read_meta
from .sync import pending_count
from .i18n import tr
from .util import fmt_int, plural, read_json


def _model_label(model_id: str) -> str:
    if not model_id:
        return tr("unbekannt", "unknown")
    prov, _, rest = model_id.partition(":")
    name, _, rev = rest.partition("@")
    prov_name = {"local": tr("lokal", "local"), "voyage": "Voyage AI", "fake": tr("Test-Embedder", "test embedder")}.get(prov, prov)
    rev_s = f", Revision {rev[:8]}" if rev and prov == "local" else ""
    return f"{prov_name} · {name}{rev_s}"


def status(layout: Layout, *, check_remote: bool = True) -> str:
    cfg = layout.config
    kind = "Vault" if layout.mode == "vault" else tr("Sammlung", "Collection")
    where = tr("im Ordner", "in the folder") if layout.location == "inside" \
        else tr(f"außerhalb ({layout.state_dir})", f"outside ({layout.state_dir})")
    lines = [tr(f"plug-n-rag · {kind} „{layout.root.name}“ · Index {where}",
                f"plug-n-rag · {kind} “{layout.root.name}” · index {where}")]
    meta = read_meta(layout.index_dir) or {}
    want = model_id_for(cfg)
    todo, total = pending_count(layout)
    lines.append(tr(f"Dateien: {fmt_int(total)} durchsuchbar, davon {fmt_int(total - todo)} semantisch indexiert",
                    f"Files: {fmt_int(total)} searchable, {fmt_int(total - todo)} of them indexed by meaning")
                 + (tr(f", {fmt_int(todo)} ausstehend", f", {fmt_int(todo)} pending") if todo else ""))
    if meta.get("model") and meta["model"] != want:
        lines.append(tr(f"⚠ Index passt nicht zum Modell: Index {_model_label(meta['model'])}, "
                        f"eingestellt {_model_label(want)}. Nur Stichwortsuche bis /plug-n-rag:reindex.",
                        f"⚠ Index does not match the model: index {_model_label(meta['model'])}, "
                        f"configured {_model_label(want)}. Keyword search only until /plug-n-rag:reindex."))
    from .readiness import MODEL_ERROR, MODEL_LOADING, MODEL_MISSING, readiness, status_line

    ready = readiness(layout)
    if not (meta.get("model") and meta["model"] != want):
        here = ready.reason not in (MODEL_LOADING, MODEL_MISSING, MODEL_ERROR)
        lines.append(tr("Modell: ", "Model: ") + _model_label(want)
                     + (" ✓" if here else tr(" (noch nicht auf diesem Rechner)", " (not on this computer yet)")))
    lines.append(status_line(ready))
    pend = read_json(layout.cache_dir / "pending.json", {}) or {}
    if pend.get("embed_error"):
        lines.append(tr("⚠ Embedding zuletzt nicht möglich: ", "⚠ Embedding failed last time: ") + pend["embed_error"])
    if pend.get("too_large"):
        lines.append(tr("⚠ Zu groß (über 100 MB), nicht indexiert: ", "⚠ Too large (over 100 MB), not indexed: ")
                     + ", ".join(pend["too_large"][:5]))
    try:
        conn = sqlite3.connect(str(layout.db_path))
        n_notes = conn.execute("SELECT count(*) FROM notes").fetchone()[0]
        n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        vec_ext = conn.execute("SELECT value FROM meta WHERE key='vec_ext'").fetchone()
        conn.close()
        engine = "sqlite-vec" if vec_ext and vec_ext[0] == "1" else tr("NumPy (sqlite-vec nicht ladbar)",
                                                                         "NumPy (sqlite-vec not loadable)")
        lines.append(tr(f"Suchdatenbank: {fmt_int(n_notes)} Dateien, {fmt_int(n_chunks)} Abschnitte, Vektorsuche über {engine}",
                        f"Search database: {fmt_int(n_notes)} files, {fmt_int(n_chunks)} sections, vector search via {engine}"))
    except sqlite3.Error:
        lines.append(tr("Suchdatenbank: noch nicht gebaut (entsteht beim nächsten Abgleich)",
                        "Search database: not built yet (created at the next sync)"))
    if pend.get("awaiting"):
        n = len(pend["awaiting"])
        files = ", ".join(pend["awaiting"][:5]) + (" …" if n > 5 else "")
        lines.append(tr(f"Hinweis: {n} eingescannte {'Datei wartet' if n == 1 else 'Dateien warten'} auf Aufnahme "
                        f"(/plug-n-rag:aufnehmen): {files}",
                        f"Note: {n} scanned {'file waits' if n == 1 else 'files wait'} for ingestion "
                        f"(/plug-n-rag:ingest): {files}"))
    errors = read_json(layout.cache_dir / "errors.json", {}) or {}
    if errors:
        lines.append(tr(f"Fehler bei {len(errors)} Dateien:", f"Errors in {len(errors)} files:"))
        for path, msg in list(errors.items())[:8]:
            lines.append(f"  {path}: {msg}")
    else:
        lines.append(tr("Fehler: keine", "Errors: none"))
    if gitops.inside_repo(layout.root) if layout.location == "inside" else False:
        url = gitops.remote_url(layout.root)
        if not url:
            lines.append(tr("Git: lokales Repo ohne GitHub-Verbindung (keine Cloud-Sitzungen möglich)",
                            "Git: local repo without GitHub connection (no cloud sessions possible)"))
        else:
            vis = gitops.repo_visibility(layout.root) if check_remote else None
            if vis == "public":
                lines.append(tr("⚠ Git: Das Repo ist ÖFFENTLICH. Notizen und Index sind für alle sichtbar. "
                                "Dringend auf privat stellen.",
                                "⚠ Git: The repo is PUBLIC. Notes and index are visible to everyone. "
                                "Make it private urgently."))
            elif vis in ("private", "internal"):
                lines.append(tr("Git: Repo auf GitHub, privat ✓", "Git: repo on GitHub, private ✓"))
            else:
                lines.append(tr("Git: Repo mit Remote, Sichtbarkeit nicht prüfbar (GitHub-CLI fehlt oder nicht angemeldet)",
                                "Git: repo with remote, visibility not checkable (GitHub CLI missing or not signed in)"))
    from . import __version__
    from . import update as up

    vline = tr(f"Version: {__version__}", f"Version: {__version__}")
    if check_remote and up.mode(cfg) != "aus":
        info = up.check()
        if info.newer:
            vline += tr(f" · neu verfügbar: {info.latest} (`plug-n-rag aktualisieren`)",
                        f" · new version available: {info.latest} (`plug-n-rag update`)")
        elif info.latest:
            vline += tr(" · aktuell ✓", " · up to date ✓")
    lines.append(vline)
    lines.append(tr("Token-Steuerung (", "Token steering (") + tuning.tuning_location_note(layout) + "):")
    lines += ["  " + ln for ln in tuning.describe(layout)]
    n, delivered, full = tuning.savings(layout)
    if n and full:
        pct = max(0, round(100 * (1 - delivered / full)))
        lines.append(tr(f"Ersparnis (Schätzung): {fmt_int(n)} Suchen lieferten {fmt_int(delivered)} Tokens statt "
                        f"{fmt_int(full)} Tokens beim vollständigen Lesen der Trefferdateien (−{pct} %).",
                        f"Savings (estimate): {plural(n, 'search', 'searches')} delivered {fmt_int(delivered)} tokens instead of "
                        f"{fmt_int(full)} tokens for reading all hit files completely (−{pct}%)."))
    return "\n".join(lines)

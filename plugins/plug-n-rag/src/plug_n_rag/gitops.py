"""Careful git helpers. Never force, never reset, never resolve conflicts in notes.

The only automatic conflict handling: index files (derived data) with conflicts are
discarded and recomputed, as SPEC requires.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .config import Layout

HOOK_MARKER = "# plug-n-rag pre-commit"


def git(root: Path, *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          timeout=timeout, env=env)


def is_repo(root: Path) -> bool:
    if not shutil.which("git"):
        return False
    try:
        r = git(root, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and Path(r.stdout.strip()).resolve() == root.resolve()


def inside_repo(root: Path) -> bool:
    try:
        return git(root, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False


def remote_url(root: Path) -> str | None:
    try:
        r = git(root, "remote", "get-url", "origin")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def github_slug(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def repo_visibility(root: Path) -> str | None:
    """'private', 'public' or None if unknown (no gh CLI, not on GitHub, not logged in)."""
    slug = github_slug(remote_url(root))
    if not slug or not shutil.which("gh"):
        return None
    try:
        r = subprocess.run(["gh", "repo", "view", slug, "--json", "visibility", "-q", ".visibility"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    v = r.stdout.strip().lower()
    return v if v in ("private", "public", "internal") else None


def status_porcelain(root: Path) -> list[str]:
    r = git(root, "status", "--porcelain")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def unmerged(root: Path) -> list[str]:
    r = git(root, "diff", "--name-only", "--diff-filter=U")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def has_upstream(root: Path) -> bool:
    r = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    return r.returncode == 0


def pull(root: Path, timeout: float = 25) -> str | None:
    """`git pull --rebase` if safe. Returns a short German note for the user, or None."""
    if not remote_url(root) or not has_upstream(root):
        return None
    if unmerged(root):
        return "Git: Es gibt ungelöste Konflikte. Bitte mit Claude gemeinsam klären."
    dirty = [ln for ln in status_porcelain(root) if not ln[3:].startswith(".plug-n-rag/")]
    if dirty:
        return "Git: Neuester Stand nicht geholt, weil es ungesicherte Änderungen gibt."
    try:
        r = git(root, "pull", "--rebase", "--quiet", timeout=timeout)
    except subprocess.TimeoutExpired:
        return "Git: Abholen des neuesten Stands hat zu lange gedauert, übersprungen."
    if r.returncode != 0:
        if (root / ".git" / "rebase-merge").exists() or (root / ".git" / "rebase-apply").exists():
            conflicted = unmerged(root)
            if conflicted and all(p.startswith(".plug-n-rag/index/") for p in conflicted):
                return resolve_index_conflicts_rebase(root, conflicted)
            git(root, "rebase", "--abort")
            return "Git: Konflikt beim Abholen, nichts verändert. Bitte gemeinsam klären."
        return "Git: Neuester Stand konnte nicht geholt werden (offline?)."
    return None


def resolve_index_conflicts_rebase(root: Path, paths: list[str]) -> str:
    """Index files are derived data: drop conflicted ones, continue; sync recomputes them."""
    for p in paths:
        try:
            (root / p).unlink()
        except OSError:
            pass
        git(root, "rm", "--cached", "--quiet", "--", p)
    env_ok = git(root, "-c", "core.editor=true", "rebase", "--continue")
    if env_ok.returncode != 0:
        git(root, "rebase", "--abort")
        return "Git: Konflikt beim Abholen, nichts verändert. Bitte gemeinsam klären."
    return f"Git: {len(paths)} Index-Dateien mit Konflikt verworfen, werden neu berechnet."


def commit_paths(root: Path, paths: list[str], message: str) -> bool:
    existing = [p for p in paths if (root / p).exists() or git(root, "ls-files", "--", p).stdout.strip()]
    if not existing:
        return False
    git(root, "add", "-A", "--", *existing)
    staged = git(root, "diff", "--cached", "--name-only", "--", *existing).stdout.strip()
    if not staged:
        return False
    r = git(root, "commit", "--quiet", "-m", message, "--", *existing)
    return r.returncode == 0


def commit_all(root: Path, message: str) -> bool:
    if not status_porcelain(root):
        return False
    git(root, "add", "-A")
    return git(root, "commit", "--quiet", "-m", message).returncode == 0


def push(root: Path) -> bool:
    if not remote_url(root) or not has_upstream(root):
        return False
    try:
        return git(root, "push", "--quiet", timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def index_paths(layout: Layout) -> list[str]:
    """Everything shareable plug-n-rag owns: the .plug-n-rag folder (plus the old root config)."""
    base = layout.state_dir.relative_to(layout.root).as_posix()
    return [base] + ([layout.config_path.name] if layout.legacy else [])


def install_precommit(root: Path, launcher: str) -> str:
    """Install (or chain) a pre-commit hook that runs sync and stages index files."""
    hooks = root / ".git" / "hooks"
    if not hooks.is_dir():
        return "Kein Git-Repo gefunden."
    path = hooks / "pre-commit"
    body = f"""{HOOK_MARKER}
# Hält den Index von plug-n-rag im selben Commit wie die Notizen. Blockiert nie.
PNR="{launcher}"
if [ -x "$PNR" ]; then
  "$PNR" sync --quiet >/dev/null 2>&1 || true
  git add -A -- .plug-n-rag >/dev/null 2>&1 || true
  if [ -f plug-n-rag.yml ]; then git add -- plug-n-rag.yml >/dev/null 2>&1 || true; fi
fi
"""
    if path.exists():
        old = path.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARKER in old:
            new = re.sub(r'PNR="[^"]*"', f'PNR="{launcher}"', old)
            path.write_text(new, encoding="utf-8")
            return "Git-Hook aktualisiert."
        backup = hooks / "pre-commit.vor-plug-n-rag"
        if not backup.exists():
            shutil.copy2(path, backup)
        content = ("#!/bin/sh\n" + body +
                   f'# vorheriger Hook, gesichert als {backup.name}\n'
                   f'if [ -x "{backup}" ]; then exec "{backup}" "$@"; fi\n')
    else:
        content = "#!/bin/sh\n" + body
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return "Git-Hook installiert."


SECRET_RE = re.compile(r"(pa-[A-Za-z0-9_\-]{30,}|sk-ant-[A-Za-z0-9_\-]{20,}|gh[pousr]_[A-Za-z0-9]{30,})")


def default_branch(root: Path) -> str:
    try:
        r = git(root, "ls-remote", "--symref", "origin", "HEAD", timeout=30)
        for line in r.stdout.splitlines():
            if line.startswith("ref: refs/heads/"):
                return line.split("refs/heads/", 1)[1].split()[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "main"


def current_branch(root: Path) -> str:
    return git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def staged_secrets(root: Path) -> list[str]:
    diff = git(root, "diff", "--cached", "-U0").stdout
    hits = []
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and SECRET_RE.search(line):
            hits.append(current or "?")
    return sorted(set(hits))


def publish_to_main(layout: Layout, message: str, resync=None) -> str:
    """Commit everything, bring in the newest main, push to main. Never force, never rewrite.

    ``resync`` is called to recompute index files when only those conflict.
    """
    root = layout.root
    if not remote_url(root):
        return "Kein GitHub-Repo verbunden, nichts zu übernehmen."
    if unmerged(root):
        return "Es gibt ungelöste Konflikte. Bitte zuerst gemeinsam klären."
    target = default_branch(root)
    branch = current_branch(root)
    lines = []
    if status_porcelain(root):
        git(root, "add", "-A")
        secrets = staged_secrets(root)
        if secrets:
            git(root, "reset", "-q")
            return ("Abgebrochen: In " + ", ".join(secrets) + " steht etwas, das wie ein API-Key aussieht. "
                    "Bitte entfernen; Keys gehören nie ins Repo.")
        if git(root, "commit", "--quiet", "-m", message).returncode == 0:
            lines.append(f"Commit: „{message}“")
    for attempt in range(2):
        f = git(root, "fetch", "--quiet", "origin", target, timeout=60)
        if f.returncode != 0:
            return "\n".join(lines + [f"Neuester Stand von {target} konnte nicht geholt werden (offline?)."])
        m = git(root, "merge", "--no-edit", "--quiet", f"origin/{target}", timeout=60)
        if m.returncode != 0:
            conflicted = unmerged(root)
            if conflicted and all(p.startswith(".plug-n-rag/index/") for p in conflicted):
                for p in conflicted:
                    git(root, "checkout", "--theirs", "--", p)
                if resync is not None:
                    resync()
                git(root, "add", "-A", "--", ".plug-n-rag")
                git(root, "commit", "--quiet", "--no-edit")
                lines.append(f"{len(conflicted)} Index-Dateien mit Konflikt neu berechnet.")
            else:
                git(root, "merge", "--abort")
                names = ", ".join(conflicted[:8]) or "unbekannt"
                return "\n".join(lines + [
                    f"Nicht übernommen: Diese Notizen wurden hier und auf {target} unterschiedlich geändert: "
                    f"{names}. Bitte gemeinsam entscheiden, welche Fassung gilt. Es wurde nichts verändert."])
        p = git(root, "push", "--quiet", "origin", f"HEAD:{target}", timeout=90)
        if p.returncode == 0:
            if branch not in (target, "HEAD"):
                git(root, "push", "--quiet", "origin", f"HEAD:{branch}", timeout=90)
            lines.append(f"Auf {target} übernommen" + (f" (vom Branch {branch})" if branch != target else "") + ".")
            return "\n".join(lines)
        if attempt == 0:
            continue
        err = (p.stderr or "").strip().splitlines()[-1:] or ["unbekannter Fehler"]
        hint = " Vermutlich ist der Branch geschützt; dann über einen Pull Request zusammenführen." \
            if "protected" in (p.stderr or "").lower() else ""
        return "\n".join(lines + [f"Push nach {target} abgelehnt: {err[0]}.{hint}"])
    return "\n".join(lines)

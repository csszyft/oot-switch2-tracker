"""Fast GitHub & Gitee pure-code hot updater for OoT Switch 2 Tracker."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_GITHUB_REPO = "csszyft/oot-switch2-tracker"
DEFAULT_GITEE_REPO = "csszyf/oot-switch2-tracker"
DEFAULT_BRANCH = "main"
DEFAULT_TIMEOUT = 3.0

MANAGED_FILES = [
    "launcher.py",
    "auto_updater.py",
    "triforce_icon.py",
    "overlay_hud.py",
    "tracker_engine.py",
    "save_reader.py",
    "gamepad_ctrl.py",
    "amiibo_helper.py",
    "win_proc.py",
    "portable_config.py",
    "oot_world_db.json",
    "启动时之笛助手.bat",
    "启动时之笛助手_调试终端.bat",
]

PROTECTED_USER_FILES = {
    "tracker_config.json",
    "amiibo_daily_log.json",
    "version.json",
}
ALLOWED_EXTS = {".py", ".json", ".ico", ".bat"}
_UA = "OoT-Switch2-Tracker-Updater/1.2"


@dataclass
class UpstreamProbe:
    source: str          # "gitee" | "github"
    ok: bool
    latency_ms: float = 0.0
    manifest: dict[str, Any] | None = None
    raw_base: str = ""
    commit_sha: str = ""
    error: str = ""


@dataclass
class UpdateResult:
    status: str          # "up_to_date" | "updated" | "offline" | "disabled" | "error"
    source: str = ""
    local_version: str = "0.0.0"
    local_build: int = 0
    remote_version: str = ""
    remote_build: int = 0
    notes: str = ""
    updated_files: list[str] = field(default_factory=list)
    total_bytes: int = 0
    latency_ms: float = 0.0
    probe_summary: list[str] = field(default_factory=list)
    error: str = ""


def parse_version(ver_str: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", str(ver_str or "0"))]
    return tuple(nums) if nums else (0,)


def is_safe_rel_path(rel: str, app_dir: Path) -> bool:
    if not rel or not isinstance(rel, str):
        return False
    norm = rel.replace("\\", "/")
    if norm.startswith("/") or ":" in norm:
        return False
    parts = norm.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    if norm in PROTECTED_USER_FILES:
        return False
    if Path(norm).suffix.lower() not in ALLOWED_EXTS:
        return False
    try:
        base = app_dir.resolve()
        target = (base / norm).resolve()
        return target.is_relative_to(base) and target != base
    except Exception:
        return False


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def load_local_manifest(app_dir: Path) -> dict[str, Any]:
    p = app_dir / "version.json"
    if not p.is_file():
        return {"version": "0.0.0", "build": 0, "notes": "", "files": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"version": "0.0.0", "build": 0, "notes": "", "files": {}}


def build_manifest(app_dir: Path, version: str, build: int | None = None, notes: str = "") -> dict[str, Any]:
    if build is None:
        build = int(time.strftime("%Y%m%d%H%M"))
    files_map: dict[str, dict[str, Any]] = {}
    for rel in MANAGED_FILES:
        fp = app_dir / rel
        if fp.is_file():
            files_map[rel] = {
                "sha256": file_sha256(fp),
                "size": fp.stat().st_size,
            }
    return {
        "version": str(version),
        "build": int(build),
        "notes": str(notes),
        "files": files_map,
    }


def _make_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def _http_get(url: str, timeout: float, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": accept,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_make_ssl_context()) as resp:
        return resp.read()


def _encode_raw_url(raw_base: str, rel_path: str, cache_bust: int | None = None) -> str:
    base = raw_base.rstrip("/")
    rel_enc = urllib.parse.quote(rel_path.replace("\\", "/").lstrip("/"), safe="/")
    url = f"{base}/{rel_enc}"
    if cache_bust is not None:
        url = f"{url}?t={cache_bust}"
    return url


def _validate_manifest_obj(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    ver = str(obj.get("version") or "").strip()
    files = obj.get("files")
    if not ver or not isinstance(files, dict) or not files:
        return None
    return obj


def _probe_gitee(repo: str, branch: str, timeout: float) -> UpstreamProbe:
    t0 = time.perf_counter()
    if not repo:
        return UpstreamProbe("gitee", False, error="not configured")
    raw_base = f"https://gitee.com/{repo}/raw/{branch}"
    ts = int(time.time())
    try:
        raw_bytes = _http_get(_encode_raw_url(raw_base, "version.json", ts), timeout=timeout, accept="application/json")
        manifest = _validate_manifest_obj(json.loads(raw_bytes.decode("utf-8-sig")))
        if not manifest:
            return UpstreamProbe("gitee", False, (time.perf_counter() - t0) * 1000, error="invalid version.json")
        return UpstreamProbe(
            "gitee", True, (time.perf_counter() - t0) * 1000, manifest=manifest, raw_base=raw_base
        )
    except urllib.error.HTTPError as e:
        return UpstreamProbe("gitee", False, (time.perf_counter() - t0) * 1000, error=f"HTTP {e.code}")
    except Exception as e:
        return UpstreamProbe("gitee", False, (time.perf_counter() - t0) * 1000, error=str(e)[:80])


def _probe_github(repo: str, branch: str, timeout: float) -> UpstreamProbe:
    t0 = time.perf_counter()
    if not repo:
        return UpstreamProbe("github", False, error="not configured")
    commit_sha = ""
    api_url = f"https://api.github.com/repos/{repo}/commits/{urllib.parse.quote(branch, safe='')}"
    try:
        api_bytes = _http_get(api_url, timeout=min(2.0, timeout), accept="application/vnd.github+json")
        api_obj = json.loads(api_bytes.decode("utf-8"))
        sha = str(api_obj.get("sha") or "")
        if len(sha) >= 7:
            commit_sha = sha
    except Exception:
        commit_sha = ""

    candidates: list[str] = []
    if commit_sha:
        candidates.append(f"https://raw.githubusercontent.com/{repo}/{commit_sha}")
    candidates.append(f"https://raw.githubusercontent.com/{repo}/{branch}")
    candidates.append(f"https://github.com/{repo}/raw/{branch}")

    last_err = ""
    ts = int(time.time())
    for base in candidates:
        try:
            cb = None if (commit_sha and commit_sha in base) else ts
            raw_bytes = _http_get(_encode_raw_url(base, "version.json", cb), timeout=timeout, accept="application/json")
            manifest = _validate_manifest_obj(json.loads(raw_bytes.decode("utf-8-sig")))
            if manifest:
                return UpstreamProbe(
                    "github",
                    True,
                    (time.perf_counter() - t0) * 1000,
                    manifest=manifest,
                    raw_base=base,
                    commit_sha=commit_sha,
                )
            last_err = "invalid version.json"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
        except Exception as e:
            last_err = str(e)[:80]
    return UpstreamProbe("github", False, (time.perf_counter() - t0) * 1000, error=last_err or "unreachable")


def probe_upstreams(cfg: dict[str, Any] | None = None) -> list[UpstreamProbe]:
    cfg = cfg or {}
    gh_repo = str(cfg.get("github_repo", DEFAULT_GITHUB_REPO) or "").strip()
    gt_repo = str(cfg.get("gitee_repo", DEFAULT_GITEE_REPO) or "").strip()
    branch = str(cfg.get("update_branch", DEFAULT_BRANCH) or DEFAULT_BRANCH).strip()
    timeout = max(1.0, min(10.0, float(cfg.get("update_timeout_sec", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT)))

    tasks: list[tuple[Callable[..., UpstreamProbe], tuple[Any, ...]]] = []
    if gt_repo:
        tasks.append((_probe_gitee, (gt_repo, branch, timeout)))
    if gh_repo:
        tasks.append((_probe_github, (gh_repo, branch, timeout)))
    if not tasks:
        return []

    probes: list[UpstreamProbe] = []
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futs = [pool.submit(fn, *args) for fn, args in tasks]
        for fut in as_completed(futs):
            try:
                probes.append(fut.result())
            except Exception as e:
                probes.append(UpstreamProbe("unknown", False, error=str(e)[:80]))
    return probes


def _pick_best_probe(probes: list[UpstreamProbe]) -> UpstreamProbe | None:
    valid = [p for p in probes if p.ok and p.manifest is not None]
    if not valid:
        return None
    valid.sort(
        key=lambda p: (
            parse_version(str(p.manifest.get("version", "0"))),
            int(p.manifest.get("build", 0) or 0),
            -p.latency_ms,
        ),
        reverse=True,
    )
    return valid[0]


def _compute_needed_files(
    app_dir: Path,
    local_manifest: dict[str, Any],
    remote_manifest: dict[str, Any],
    force: bool = False,
) -> tuple[bool, list[tuple[str, dict[str, Any]]]]:
    loc_ver = str(local_manifest.get("version") or "0.0.0")
    loc_build = int(local_manifest.get("build", 0) or 0)
    rem_ver = str(remote_manifest.get("version") or "0.0.0")
    rem_build = int(remote_manifest.get("build", 0) or 0)

    is_newer = (parse_version(rem_ver), rem_build) > (parse_version(loc_ver), loc_build)
    remote_files = remote_manifest.get("files") or {}
    needed: list[tuple[str, dict[str, Any]]] = []

    for rel, meta in remote_files.items():
        if not is_safe_rel_path(rel, app_dir) or not isinstance(meta, dict):
            continue
        exp_sha = str(meta.get("sha256") or "").lower()
        if not exp_sha:
            continue
        target = app_dir / rel
        if not target.is_file():
            needed.append((rel, meta))
            continue
        if is_newer or force:
            try:
                if file_sha256(target) != exp_sha:
                    needed.append((rel, meta))
            except Exception:
                needed.append((rel, meta))
    return is_newer, needed


def _download_verified_file(
    rel: str,
    meta: dict[str, Any],
    bases: list[str],
    timeout: float,
) -> bytes:
    exp_sha = str(meta.get("sha256") or "").lower()
    exp_size = int(meta.get("size", 0) or 0)
    ts = int(time.time())
    last_err = "download failed"
    for base in bases:
        try:
            # Skip cache-buster when base already pins an immutable commit SHA
            cb = None if re.search(r"/[0-9a-f]{40}$", base) else ts
            data = _http_get(_encode_raw_url(base, rel, cb), timeout=max(timeout, 6.0))
            if exp_size > 0 and len(data) != exp_size:
                last_err = f"{rel}: size mismatch ({len(data)} != {exp_size})"
                continue
            got_sha = bytes_sha256(data)
            if got_sha != exp_sha:
                last_err = f"{rel}: sha256 mismatch"
                continue
            return data
        except Exception as e:
            last_err = f"{rel}: {e}"
    raise RuntimeError(last_err)


def check_and_apply_updates(
    app_dir: Path,
    cfg: dict[str, Any] | None = None,
    *,
    force: bool = False,
    apply_updates: bool = True,
    cancel_event: threading.Event | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> UpdateResult:
    cfg = cfg or {}
    local_manifest = load_local_manifest(app_dir)
    loc_ver = str(local_manifest.get("version") or "0.0.0")
    loc_build = int(local_manifest.get("build", 0) or 0)

    if not force and not bool(cfg.get("auto_update", True)):
        return UpdateResult(status="disabled", local_version=loc_ver, local_build=loc_build)

    if cancel_event and cancel_event.is_set():
        return UpdateResult(status="cancelled", local_version=loc_ver, local_build=loc_build)

    if on_progress:
        on_progress("正在并行检测 GitHub / Gitee 上游代码版本…")

    probes = probe_upstreams(cfg)
    if cancel_event and cancel_event.is_set():
        return UpdateResult(status="cancelled", local_version=loc_ver, local_build=loc_build)
    summary = [
        f"{p.source}: {'OK ' + str(int(p.latency_ms)) + 'ms' if p.ok else p.error}"
        for p in probes
    ]
    winner = _pick_best_probe(probes)
    if winner is None or winner.manifest is None:
        return UpdateResult(
            status="offline",
            local_version=loc_ver,
            local_build=loc_build,
            probe_summary=summary,
            error=" / ".join(summary) or "no upstream available",
        )

    rem_manifest = winner.manifest
    rem_ver = str(rem_manifest.get("version") or loc_ver)
    rem_build = int(rem_manifest.get("build", 0) or 0)
    rem_notes = str(rem_manifest.get("notes") or "")

    is_newer, needed = _compute_needed_files(app_dir, local_manifest, rem_manifest, force=force)
    if not needed:
        if is_newer and apply_updates:
            try:
                tmp_v = app_dir / ".version.json.tmp"
                tmp_v.write_text(json.dumps(rem_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
                os.replace(tmp_v, app_dir / "version.json")
                loc_ver, loc_build = rem_ver, rem_build
            except Exception:
                pass
        return UpdateResult(
            status="up_to_date",
            source=winner.source,
            local_version=loc_ver,
            local_build=loc_build,
            remote_version=rem_ver,
            remote_build=rem_build,
            notes=rem_notes,
            latency_ms=winner.latency_ms,
            probe_summary=summary,
        )

    if not apply_updates:
        total_b = sum(int(m.get("size", 0) or 0) for _, m in needed)
        return UpdateResult(
            status="update_available",
            source=winner.source,
            local_version=loc_ver,
            local_build=loc_build,
            remote_version=rem_ver,
            remote_build=rem_build,
            notes=rem_notes,
            updated_files=[rel for rel, _ in needed],
            total_bytes=total_b,
            latency_ms=winner.latency_ms,
            probe_summary=summary,
        )

    # Order raw base URLs: winner first, then any other valid probe with matching remote version/build
    bases = [winner.raw_base]
    for p in probes:
        if (
            p is not winner
            and p.ok
            and p.manifest is not None
            and p.raw_base
            and str(p.manifest.get("version")) == rem_ver
            and int(p.manifest.get("build", 0) or 0) == rem_build
        ):
            bases.append(p.raw_base)

    total_b = sum(int(m.get("size", 0) or 0) for _, m in needed)
    if on_progress:
        src_zh = "Gitee" if winner.source == "gitee" else "GitHub"
        on_progress(f"发现 {src_zh} 新版本 v{rem_ver}（{len(needed)} 个文件 / {max(1, total_b // 1024)} KB），正在下载校验…")

    timeout = max(2.0, float(cfg.get("update_timeout_sec", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT))
    staging_dir = app_dir / ".update_staging"
    try:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        downloaded: dict[str, bytes] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(needed))) as pool:
            fut_map = {
                pool.submit(_download_verified_file, rel, meta, bases, timeout): rel
                for rel, meta in needed
            }
            for fut in as_completed(fut_map):
                rel = fut_map[fut]
                downloaded[rel] = fut.result()

        if cancel_event and cancel_event.is_set():
            return UpdateResult(status="cancelled", local_version=loc_ver, local_build=loc_build)

        # Write all verified files into staging first, then atomically replace target files
        for rel, data in downloaded.items():
            tmp_fp = staging_dir / rel.replace("/", "__")
            tmp_fp.write_bytes(data)
            target = app_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp_fp, target)

        # Update version.json strictly LAST after every file succeeded
        ver_tmp = staging_dir / "version.json"
        ver_tmp.write_text(json.dumps(rem_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(ver_tmp, app_dir / "version.json")

        return UpdateResult(
            status="updated",
            source=winner.source,
            local_version=loc_ver,
            local_build=loc_build,
            remote_version=rem_ver,
            remote_build=rem_build,
            notes=rem_notes,
            updated_files=[rel for rel, _ in needed],
            total_bytes=sum(len(v) for v in downloaded.values()),
            latency_ms=winner.latency_ms,
            probe_summary=summary,
        )
    except Exception as e:
        return UpdateResult(
            status="error",
            source=winner.source,
            local_version=loc_ver,
            local_build=loc_build,
            remote_version=rem_ver,
            remote_build=rem_build,
            probe_summary=summary,
            error=str(e),
        )
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OoT Switch 2 Tracker pure-code updater / manifest tool")
    parser.add_argument("--write-manifest", metavar="VERSION", help="Generate version.json in script directory")
    parser.add_argument("--build", type=int, default=None, help="Numeric build ID (default YYYYMMDDHH)")
    parser.add_argument("--notes", default="", help="Release/update summary text")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    if args.write_manifest:
        m = build_manifest(here, args.write_manifest, build=args.build, notes=args.notes)
        (here / "version.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote version.json: v{m['version']} (build {m['build']}, {len(m['files'])} files)")
    else:
        from portable_config import APP_DIR, load_config
        res = check_and_apply_updates(APP_DIR, load_config(), on_progress=print)
        print(res)

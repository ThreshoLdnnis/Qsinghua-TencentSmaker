"""Build an isolated static demo and ZIP for EdgeOne Makers direct upload.

Usage: python scripts/export_static_demo.py --output-dir /path/to/new-directory
The output directory must not already exist. Source files are never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


def npm_command() -> list[str]:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise RuntimeError("npm is required. Install Node.js 22 or later first.")
    node = shutil.which("node")
    bundled_cli = Path(npm).parent / "node_modules/npm/bin/npm-cli.js"
    if node and bundled_cli.is_file():
        return [node, str(bundled_cli)]
    return [npm]


def copy_frontend(source: Path, destination: Path) -> None:
    excluded = {"node_modules", ".next", ".git", "out", ".turbo", ".cache", ".npmrc"}

    def ignore(directory: str, names: list[str]) -> set[str]:
        parent = Path(directory)
        ignored = {name for name in names if name in excluded or name.startswith(".env")}
        if parent == source / "src/app":
            ignored.add("api")
        for name in names:
            if name not in ignored and (parent / name).is_symlink():
                raise RuntimeError(f"Refusing to copy a linked source path: {parent / name}")
        return ignored

    shutil.copytree(source, destination, ignore=ignore)


def repair_segment_aliases(export: Path) -> list[str]:
    """Provide flat RSC payload paths expected by ordinary static hosting."""
    aliases = []
    for directory in sorted(export.rglob("__next.*")):
        if not directory.is_dir():
            continue
        for source in sorted(directory.rglob("*.txt")):
            name = directory.name + "." + source.relative_to(directory).as_posix().replace("/", ".")
            target = directory.parent / name
            content = source.read_bytes()
            if target.exists():
                if target.read_bytes() != content:
                    raise RuntimeError(f"Conflicting RSC segment alias: {target}")
            else:
                target.write_bytes(content)
            aliases.append(target.relative_to(export).as_posix())
    return aliases


def export_demo(output: Path) -> dict[str, object]:
    repository = Path(__file__).resolve().parents[1]
    frontend = repository / "frontend"
    output = output.expanduser().resolve()
    if output.exists():
        raise RuntimeError(f"Output already exists; choose a new directory: {output}")
    if output == repository or output.is_relative_to(frontend):
        raise RuntimeError("Output must be outside the source frontend directory.")
    npm = npm_command()
    output.mkdir(parents=True, exist_ok=False)
    stage = output / "frontend"
    copy_frontend(frontend, stage)
    (stage / "src/app/page.tsx").write_text(
        'import { AccountShell } from "@/components/account-shell";\n\n'
        'export default function Page() {\n'
        '  return <AccountShell liveEnabled={false} />;\n'
        '}\n', encoding="utf-8",
    )
    (stage / "next.config.ts").write_text(
        'import type { NextConfig } from "next";\n\n'
        'const config: NextConfig = {\n'
        '  output: "export",\n'
        '  images: { unoptimized: true },\n'
        '  agentRules: false,\n'
        '  devIndicators: false,\n'
        '  poweredByHeader: false,\n'
        '};\n\n'
        'export default config;\n', encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["NEXT_TELEMETRY_DISABLED"] = "1"
    subprocess.run(npm + ["ci", "--no-audit", "--no-fund"], cwd=stage, env=environment, check=True)
    subprocess.run(npm + ["run", "build"], cwd=stage, env=environment, check=True)
    export = stage / "out"
    aliases = repair_segment_aliases(export)
    if not (export / "index.html").is_file() or not (export / "__next.__PAGE__.txt").is_file():
        raise RuntimeError("Static export is missing its homepage or navigation payload.")
    if "本地演示" not in (export / "index.html").read_text(encoding="utf-8"):
        raise RuntimeError("Static homepage must visibly identify the local demo.")
    if (export / "api").exists():
        raise RuntimeError("Static demo must not contain API endpoints.")

    files = sorted(path for path in export.rglob("*") if path.is_file())
    manifest = []
    for path in files:
        relative = path.relative_to(export)
        if path.is_symlink() or any(part.startswith(".") for part in relative.parts):
            raise RuntimeError(f"Unexpected private or linked output path: {relative}")
        content = path.read_bytes()
        manifest.append({"path": relative.as_posix(), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})

    archive = output / "lovestone-static-demo.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for path in files:
            package.write(path, path.relative_to(export).as_posix())
    with zipfile.ZipFile(archive) as package:
        if "index.html" not in package.namelist() or package.testzip() is not None:
            raise RuntimeError("Static ZIP verification failed.")

    report = {
        "mode": "local_demo", "live_backend": False,
        "archive": str(archive), "export_directory": str(export),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "file_count": len(files), "windows_segment_aliases": aliases,
        "files": manifest,
    }
    (output / "deployment-manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {key: value for key, value in report.items() if key != "files"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export LoveStone as a labelled local demo for static hosting.")
    parser.add_argument("--output-dir", required=True, type=Path, help="New output directory; an existing directory is refused.")
    arguments = parser.parse_args()
    print(json.dumps(export_demo(arguments.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

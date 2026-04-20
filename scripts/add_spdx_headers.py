#!/usr/bin/env python3
"""Add SPDX license headers to all NVIDIA-authored source files.

Handles Python, Shell, YAML, and Terraform files.
Preserves shebangs and skips files that already have SPDX headers.
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

HEADER_LINES = [
    "# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.",
    "# SPDX-License-Identifier: LicenseRef-NvidiaProprietary",
    "",
    "# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual",
    "# property and proprietary rights in and to this material, related",
    "# documentation and any modifications thereto. Any use, reproduction,",
    "# disclosure or distribution of this material and related documentation",
    "# without an express license agreement from NVIDIA CORPORATION or",
    "# its affiliates is strictly prohibited.",
]

HEADER_TEXT = "\n".join(HEADER_LINES) + "\n"

SKIP_PATHS = {
    ".pre-commit-config.yaml",
    ".coderabbit.yaml",
}


def _git_ls_files() -> list[str]:
    """List all tracked + untracked-but-not-ignored files via git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("git is required to enumerate repository files") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"git ls-files failed: {exc.stderr.strip() or exc}") from exc

    return [line for line in result.stdout.splitlines() if line]


def find_files() -> list[Path]:
    """Find all NVIDIA-authored source files that need SPDX headers.

    Uses ``git ls-files`` so that .gitignore patterns (e.g. .terraform/)
    are automatically respected.
    """
    files: list[Path] = []

    for rel_str in _git_ls_files():
        rel = Path(rel_str)

        if rel.as_posix() in SKIP_PATHS:
            continue

        if rel.parts and rel.parts[0] == ".github":
            continue

        ext = rel.suffix

        if ext in (".py", ".sh", ".tf"):
            files.append(REPO_ROOT / rel)
        elif ext in (".yaml", ".yml"):
            parts = rel.parts
            if len(parts) >= 2 and parts[0] in ("isvctl", "isvtest", "isvreporter"):
                files.append(REPO_ROOT / rel)

    return sorted(files)


def has_spdx_header(content: str) -> bool:
    """Check if file already contains SPDX header."""
    return "SPDX-FileCopyrightText" in content or "SPDX-License-Identifier" in content


def add_header(filepath: Path) -> bool:
    """Add SPDX header to a file. Returns True if modified."""
    content = filepath.read_text(encoding="utf-8")

    if has_spdx_header(content):
        return False

    if not content.strip():
        filepath.write_text(HEADER_TEXT + "\n", encoding="utf-8")
        return True

    lines = content.split("\n")
    first_line = lines[0] if lines else ""

    if first_line.startswith("#!"):
        new_content = first_line + "\n" + HEADER_TEXT + "\n" + "\n".join(lines[1:])
    else:
        new_content = HEADER_TEXT + "\n" + content

    filepath.write_text(new_content, encoding="utf-8")
    return True


def check_headers(files: list[Path]) -> int:
    """Check files for missing SPDX headers without modifying them. Returns count of missing."""
    missing = 0
    for fpath in files:
        rel = fpath.relative_to(REPO_ROOT)
        try:
            content = fpath.read_text(encoding="utf-8")
            if not has_spdx_header(content):
                missing += 1
                print(f"  ! {rel} -- missing SPDX header")
        except Exception as e:
            missing += 1
            print(f"  ! {rel} ERROR: {e}", file=sys.stderr)
    return missing


def main() -> int:
    """Add SPDX headers to all source files, or check with --check."""
    parser = argparse.ArgumentParser(description="Manage SPDX license headers.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for missing headers without modifying files (exit 1 if any are missing).",
    )
    args = parser.parse_args()

    files = find_files()
    print(f"Found {len(files)} source files to check\n")

    if args.check:
        missing = check_headers(files)
        if missing:
            print(
                f"\n{missing} file(s) missing SPDX headers. Run 'make update-spdx-headers' to fix."
            )
            return 1
        print("\nAll files have SPDX headers.")
        return 0

    modified = 0
    skipped = 0
    errors = 0

    for fpath in files:
        rel = fpath.relative_to(REPO_ROOT)
        try:
            if add_header(fpath):
                modified += 1
                print(f"  + {rel}")
            else:
                skipped += 1
                print(f"  . {rel} (already has SPDX header)")
        except Exception as e:
            errors += 1
            print(f"  ! {rel} ERROR: {e}", file=sys.stderr)

    print(f"\nDone: {modified} modified, {skipped} skipped, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

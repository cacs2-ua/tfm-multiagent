from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from .loader import load_company_pack
from .scaffold import create_company_pack_skeleton
from .versioning import PLATFORM_VERSION


def _zip_folder(src_dir: Path, out_zip: Path) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src_dir.rglob("*"):
            arcname = p.relative_to(src_dir)
            zf.write(p, arcname.as_posix())


def cmd_create(args: argparse.Namespace) -> int:
    root = create_company_pack_skeleton(
        out_dir=args.out,
        company_id=args.company_id,
        company_name=args.company_name,
        sector=args.sector,
        primary_language=args.lang,
    )
    print(f"✅ Created company pack skeleton at: {root}")
    print(f"➡️  Add PDFs into: {root / 'docs'}")
    print("➡️  Validate with: python -m company_pack validate --pack " + str(root))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    pack, tmp = load_company_pack(args.pack, platform_version=PLATFORM_VERSION, keep_temp=args.keep_temp)
    print("✅ Company pack VALID")
    print(f"  Company ID:   {pack.manifest.company_id}")
    print(f"  Company Name: {pack.manifest.company_name}")
    print(f"  Pack Version: {pack.manifest.pack_version}")
    print(f"  Sector:       {pack.metadata.sector}")
    print(f"  Language:     {pack.metadata.primary_language}")
    print(f"  PDFs found:   {len(pack.list_pdfs())}")
    print(f"  Plugins enabled: {pack.plugins.enabled}")
    if tmp is not None and not args.keep_temp:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    pack, tmp = load_company_pack(args.pack, platform_version=PLATFORM_VERSION, keep_temp=args.keep_temp)
    print("=== Company Pack Inspect ===")
    print(f"Root: {pack.root}")
    print(f"Company: {pack.manifest.company_name} ({pack.manifest.company_id})")
    print(f"Sector: {pack.metadata.sector}")
    print(f"Tone: style={pack.metadata.tone.style}, verbosity={pack.metadata.tone.verbosity}, empathy={pack.metadata.tone.empathy}")
    print(f"Rules routing keys: {list(pack.rules.routing.keys())}")
    print(f"Answer policy keys: {list(pack.rules.answer_policy.keys())}")
    print(f"Plugins enabled: {pack.plugins.enabled}")
    print(f"Prompts agents: {list(pack.prompts.raw.get('agents', {}).keys())}")
    print(f"Prompt templates: {list(pack.prompts.templates().keys())}")

    pdfs = pack.list_pdfs()
    for i, p in enumerate(pdfs[:10], start=1):
        print(f"PDF {i}: {p.name}")
    if len(pdfs) > 10:
        print(f"... and {len(pdfs) - 10} more")
    if tmp is not None and not args.keep_temp:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


def cmd_zip(args: argparse.Namespace) -> int:
    src = Path(args.pack).expanduser().resolve()
    if not src.exists() or not src.is_dir():
        print("ERROR: --pack must be an existing folder pack.", file=sys.stderr)
        return 2

    out_zip = Path(args.out).expanduser().resolve()
    _zip_folder(src, out_zip)
    print(f"✅ Zipped pack: {out_zip}")
    print("➡️  Validate zip with: python -m company_pack validate --pack " + str(out_zip))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="company_pack", description="Company Pack tooling")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Create a new company pack skeleton")
    p_create.add_argument("--out", required=True, help="Output folder for the company pack")
    p_create.add_argument("--company-id", required=True, help="Unique company identifier")
    p_create.add_argument("--company-name", required=True, help="Company display name")
    p_create.add_argument("--sector", default="generic", help="Sector/category (e.g., retail, telecom)")
    p_create.add_argument("--lang", default="en", help="Primary language (e.g., en, es)")
    p_create.set_defaults(func=cmd_create)

    p_val = sub.add_parser("validate", help="Validate a company pack folder or zip")
    p_val.add_argument("--pack", required=True, help="Path to pack folder or .zip")
    p_val.add_argument("--keep-temp", action="store_true", help="Keep extracted temp dir for zips")
    p_val.set_defaults(func=cmd_validate)

    p_ins = sub.add_parser("inspect", help="Print a readable summary of the pack")
    p_ins.add_argument("--pack", required=True, help="Path to pack folder or .zip")
    p_ins.add_argument("--keep-temp", action="store_true", help="Keep extracted temp dir for zips")
    p_ins.set_defaults(func=cmd_inspect)

    p_zip = sub.add_parser("zip", help="Zip a folder pack into a .zip file")
    p_zip.add_argument("--pack", required=True, help="Path to pack folder")
    p_zip.add_argument("--out", required=True, help="Output zip path, e.g., packs/acme.zip")
    p_zip.set_defaults(func=cmd_zip)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

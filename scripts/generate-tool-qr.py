"""Generate static printable QR codes for each machine in machine_docs/.

For every subdirectory found in machine_docs/, this script generates a
qr_<Name>.png file inside that same folder.  The QR encodes the URL a phone
needs to open in order to automatically pre-select that machine's documentation
context when pairing with the laptop app.

Encoded URL format:
    <base-url>/mobile?tool=<folder-name>

Usage:
    # Dev — QR opens localhost (only useful for same-machine testing)
    python scripts/generate-tool-qr.py

    # LAN — replace with the IP Vite prints
    python scripts/generate-tool-qr.py --base-url http://192.168.1.42:5173

    # ngrok — for printing physical labels (works on any network)
    python scripts/generate-tool-qr.py --base-url https://<id>.ngrok-free.app

The generated PNG is 600x600 px by default, suitable for printing at ~2x2 in.
Use --size to change the pixel dimensions.
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

try:
    import qrcode
    from qrcode.image.pil import PilImage
except ImportError:
    sys.exit(
        "Missing dependency: run  pip install 'qrcode[pil]'  then retry."
    )

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MACHINE_DOCS_DIR = _REPO_ROOT / "machine_docs"

_DEFAULT_BASE_URL = "http://localhost:5173"


def _iter_machine_folders() -> list[str]:
    if not _MACHINE_DOCS_DIR.exists():
        return []
    return sorted(
        entry.name
        for entry in _MACHINE_DOCS_DIR.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


def _generate_qr(url: str, output_path: Path, box_size: int) -> None:
    qr: qrcode.QRCode = qrcode.QRCode(
        version=None,          # auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img: PilImage = qr.make_image(fill_color="black", back_color="white")
    img.save(str(output_path))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate static tool QR codes for machine_docs/ folders."
    )
    parser.add_argument(
        "--base-url",
        default=_DEFAULT_BASE_URL,
        metavar="URL",
        help=f"Frontend origin to embed in QR URLs (default: {_DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=10,
        metavar="BOX_SIZE",
        help="QR box size in pixels per module (default: 10 → ~400px image at typical version)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Only list the machines that would have QRs generated, then exit.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    folders = _iter_machine_folders()

    if not folders:
        print(f"No machine folders found in {_MACHINE_DOCS_DIR}.")
        print("Add a subdirectory (e.g. machine_docs/Dremel_3000/) and re-run.")
        return

    if args.list:
        print(f"Found {len(folders)} machine folder(s) in {_MACHINE_DOCS_DIR}:")
        for name in folders:
            url = f"{base_url}/mobile?tool={quote(name)}"
            print(f"  {name}  →  {url}")
        return

    print(f"Generating QR codes (base URL: {base_url})")
    for name in folders:
        url = f"{base_url}/mobile?tool={quote(name)}"
        out_path = _MACHINE_DOCS_DIR / name / f"qr_{name}.png"
        _generate_qr(url, out_path, box_size=args.size)
        print(f"  ✓ {name}")
        print(f"    URL : {url}")
        print(f"    File: {out_path.relative_to(_REPO_ROOT)}")

    print(f"\nDone. {len(folders)} QR image(s) written.")
    print("Tip: re-run with --base-url <ngrok-https-url> before printing physical labels.")


if __name__ == "__main__":
    main()

"""
Focused test script for textToVoice.py / TTSRunner.

Runs standalone — no need for the full GeminiSequenceBackend stack.
API key is loaded automatically from keys.env (debug mode).

Usage
-----
  # From repo root:
  python backend/ApiScripts/test_textToVoice.py

  # Custom text:
  python backend/ApiScripts/test_textToVoice.py "Hello, this is a test."

  # Custom voice / model:
  python backend/ApiScripts/test_textToVoice.py --voice puck --model gemini-2.5-flash-preview-tts

Options
-------
  --voice  VOICE   Built-in voice name (e.g. charon, puck, aoede)
  --model  MODEL   Gemini TTS model string
  --help           Show this message
"""

import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the ApiScripts package importable when running as a standalone script
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent
sys.path.insert(0, str(_THIS_DIR))
sys.path.insert(0, str(_BACKEND_DIR))

from textToVoice import TTSRunner  # noqa: E402  (import after path manipulation)

# ---------------------------------------------------------------------------
# Where the test saves its result summary
# ---------------------------------------------------------------------------
RESULTS_DIR = _BACKEND_DIR / "generated_audio"
RESULTS_LOG = RESULTS_DIR / "test_results.json"


def run_test(
    text: str,
    voice: str | None = None,
    model: str | None = None,
) -> dict:
    print("=" * 70)
    print("TTS UNIT TEST  (textToVoice.TTSRunner)")
    print("=" * 70)
    print(f"\n  Input text : {text[:80]}{'...' if len(text) > 80 else ''}")
    print(f"  Voice      : {voice or '(default)'}")
    print(f"  Model      : {model or '(default)'}")
    print()

    runner = TTSRunner(debug=True, voice_name=voice, voice_model=model)

    print(f"\n  voice_model : {runner.voice_model}")
    print(f"  voice_name  : {runner.voice_name}")
    print(f"  output_dir  : {runner.output_dir}")
    print()

    start = time.time()
    result = runner.run_third_prompt(instruction_text=text)
    elapsed = time.time() - start

    audio_path = Path(result["audio_path"])
    file_size = audio_path.stat().st_size if audio_path.exists() else 0

    result["elapsed_seconds"] = round(elapsed, 2)
    result["file_size_bytes"] = file_size
    result["test_timestamp"] = int(time.time())

    print("\n" + "-" * 70)
    print("RESULT")
    print("-" * 70)
    print(f"  Audio file  : {audio_path}")
    print(f"  MIME type   : {result['audio_mime_type']}")
    print(f"  File size   : {file_size:,} bytes ({file_size / 1024:.1f} KB)")
    print(f"  Elapsed     : {elapsed:.2f} s")

    # Save result summary alongside the audio
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if RESULTS_LOG.exists():
        try:
            existing = json.loads(RESULTS_LOG.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append(result)
    RESULTS_LOG.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\n  Results log : {RESULTS_LOG}")
    print("=" * 70)
    print("TEST PASSED ✓")
    print("=" * 70)

    return result


def main() -> None:
    text: str | None = None
    voice: str | None = None
    model: str | None = None

    args = sys.argv[1:]
    if args and args[0] in ("--help", "-h"):
        print(__doc__)
        return

    i = 0
    text_parts: list[str] = []
    while i < len(args):
        if args[i] == "--voice" and i + 1 < len(args):
            voice = args[i + 1]
            i += 2
        elif args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        else:
            text_parts.append(args[i])
            i += 1

    if text_parts:
        text = " ".join(text_parts)

    if text is None:
        text = (
            "Hello technician. This is an automated test of the text-to-voice module. "
            "Please verify that the audio playback is clear and the voice sounds natural."
        )

    try:
        run_test(text=text, voice=voice, model=model)
    except Exception as exc:
        print(f"\n[TEST] ✗ FAILED — {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

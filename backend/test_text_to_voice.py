"""
Test script for text-to-voice functionality.
Run from terminal: python backend/test_text_to_voice.py
"""

import os
import sys
from pathlib import Path

# Add backend directory to path
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from AIBackend import GeminiSequenceBackend
except ImportError:
    print("ERROR: Could not import GeminiSequenceBackend")
    sys.exit(1)


def play_audio(audio_path: Path) -> None:
    """Play audio file using Windows default player."""
    print(f"\n[TEST] Attempting to play audio: {audio_path}")
    
    if not audio_path.exists():
        print(f"[TEST] ✗ Audio file not found: {audio_path}")
        return
    
    try:
        # Windows: use os.startfile to open with default audio player
        os.startfile(str(audio_path))
        print(f"[TEST] ✓ Opened audio in default player")
    except Exception as e:
        print(f"[TEST] ✗ Could not play audio: {e}")
        print(f"[TEST] You can manually play the file at: {audio_path}")


def test_text_to_voice(test_text: str = None, voice_model: str = None, voice_name: str = None) -> None:
    """Test the text-to-voice conversion."""
    
    # Default test text
    if test_text is None:
        test_text = (
            "Hello technician. This is a test of the text-to-voice system. "
            "Please check the circuit breaker on panel B, then verify the voltage "
            "reading on the multimeter. Safety first!"
        )
    
    print("=" * 70)
    print("TEXT-TO-VOICE TEST")
    print("=" * 70)
    print(f"\n[TEST] Input text:\n{test_text}\n")
    print("-" * 70)
    
    try:
        # Create backend instance
        print("\n[TEST] Creating GeminiSequenceBackend instance...")
        backend = GeminiSequenceBackend()
        
        # Override models if provided
        if voice_model:
            backend.voice_model = voice_model
            print(f"[TEST] Using custom voice model: {voice_model}")
        else:
            print(f"[TEST] Using default voice model: {backend.voice_model}")
        
        if voice_name:
            backend.voice_name = voice_name
            print(f"[TEST] Using custom voice: {voice_name}")
        else:
            print(f"[TEST] Using default voice: {backend.voice_name}")
        
        print(f"[TEST] Output directory: {backend.output_dir}")
        print("\n" + "-" * 70)
        
        # Run text-to-voice conversion
        print("\n[TEST] Starting text-to-voice conversion...\n")
        result = backend.run_third_prompt(instruction_text=test_text)
        
        print("\n" + "-" * 70)
        print("\n[TEST] ✓ Conversion completed successfully!")
        print("\n[TEST] Result:")
        print(f"  - Voice Model: {result.get('voice_model')}")
        print(f"  - Audio Path: {result.get('audio_path')}")
        print(f"  - MIME Type: {result.get('audio_mime_type')}")
        print(f"  - Text Length: {len(result.get('instruction_text', ''))} characters")
        
        # Play the audio
        audio_path = Path(result.get('audio_path'))
        if audio_path.exists():
            file_size = audio_path.stat().st_size
            print(f"  - File Size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
            
            print("\n" + "=" * 70)
            play_audio(audio_path)
            print("=" * 70)
        
        return result
        
    except Exception as e:
        print("\n" + "=" * 70)
        print(f"[TEST] ✗ ERROR: {type(e).__name__}: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point with command-line argument support."""
    
    # Simple command-line argument parsing
    test_text = None
    voice_model = None
    voice_name = None
    
    # Check for custom text in arguments
    if len(sys.argv) > 1:
        # If arguments provided, treat them as custom text
        if sys.argv[1] in ["--help", "-h"]:
            print("Usage: python backend/test_text_to_voice.py [OPTIONS] [TEXT]")
            print("\nOptions:")
            print("  --model MODEL    Specify voice model (default: from config)")
            print("  --voice VOICE    Specify voice name (default: from config)")
            print("  --help, -h       Show this help message")
            print("\nExamples:")
            print('  python backend/test_text_to_voice.py "Hello world"')
            print('  python backend/test_text_to_voice.py --voice puck "Test message"')
            return
        
        args = sys.argv[1:]
        i = 0
        text_parts = []
        
        while i < len(args):
            if args[i] == "--model" and i + 1 < len(args):
                voice_model = args[i + 1]
                i += 2
            elif args[i] == "--voice" and i + 1 < len(args):
                voice_name = args[i + 1]
                i += 2
            else:
                text_parts.append(args[i])
                i += 1
        
        if text_parts:
            test_text = " ".join(text_parts)
    
    # Run the test
    test_text_to_voice(test_text=test_text, voice_model=voice_model, voice_name=voice_name)


if __name__ == "__main__":
    main()

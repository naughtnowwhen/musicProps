#!/usr/bin/env python3
"""
AeroTone Interactive Demo - Keyboard-Controlled Propeller Organ

Play the AeroTone using your computer keyboard!

Keyboard Layout (like a piano):
  W E   T Y U
 A S D F G H J

 A  = A2  (110 Hz)
 W  = A#2
 S  = B2
 D  = C3
 R  = C#3
 F  = D3
 T  = D#3
 G  = E3
 H  = F3
 U  = F#3
 J  = G3
 I  = G#3

Controls:
  Q = Quit
  SPACE = All notes off
  1-9 = Adjust master volume

Usage:
    python demo_interactive.py

Note: This demo requires a terminal that supports raw keyboard input.
On macOS/Linux this should work. On Windows you may need additional setup.
"""

import sys
import time
import threading
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed. Run: pip install sounddevice")
    sys.exit(1)

# Add project to path
sys.path.insert(0, '.')

from aerotone.voice import PropellerVoice
from aerotone.propeller import NOTES

# Key to note mapping (piano-style layout)
KEY_MAP = {
    'a': 'A2',
    'w': 'A#2',
    's': 'B2',
    'd': 'C3',
    'r': 'C#3',
    'f': 'D3',
    't': 'D#3',
    'g': 'E3',
    'h': 'F3',
    'u': 'F#3',
    'j': 'G3',
    'i': 'G#3',
}


class AeroToneDemo:
    """Interactive demo controller"""

    def __init__(self):
        self.sample_rate = 44100
        self.block_size = 512  # Lower for less latency

        # Create voices - one per note
        self.voices = {}
        for key, note in KEY_MAP.items():
            self.voices[key] = PropellerVoice(sample_rate=self.sample_rate)

        self.active_keys = set()
        self.master_volume = 0.8
        self.running = True

        # Pre-spin all motors slightly for faster response
        for voice in self.voices.values():
            voice.motor.omega = 50.0  # Small initial spin

    def key_down(self, key):
        """Handle key press"""
        key = key.lower()
        if key in self.voices and key not in self.active_keys:
            self.active_keys.add(key)
            note = KEY_MAP[key]
            self.voices[key].set_target_note(note)
            return f"ON:  {note}"
        return None

    def key_up(self, key):
        """Handle key release"""
        key = key.lower()
        if key in self.active_keys:
            self.active_keys.discard(key)
            voice = self.voices[key]
            voice.active = False
            voice.controller.set_target(0)
            return f"OFF: {KEY_MAP.get(key, '?')}"
        return None

    def all_off(self):
        """All notes off"""
        for key in list(self.active_keys):
            self.key_up(key)

    def audio_callback(self, outdata, frames, time_info, status):
        """Audio stream callback"""
        if status:
            print(f"\nAudio status: {status}")

        output = np.zeros(frames)

        # Mix active voices
        active_count = 0
        for key in list(self.active_keys):
            if key in self.voices:
                voice = self.voices[key]
                output += voice.generate_audio(frames)
                active_count += 1

        # Also update inactive voices (they need to spin down)
        for key, voice in self.voices.items():
            if key not in self.active_keys:
                voice.generate_audio(frames)  # Update physics

        # Normalize and apply master volume
        if active_count > 0:
            output /= np.sqrt(active_count)
        output *= self.master_volume

        outdata[:, 0] = np.clip(output, -1.0, 1.0)

    def print_status(self):
        """Print current status"""
        active = [KEY_MAP[k] for k in sorted(self.active_keys)]
        if active:
            freqs = [NOTES[n] for n in active]
            print(f"\rPlaying: {', '.join(active)} | "
                  f"Frequencies: {', '.join(f'{f:.1f}' for f in freqs)} Hz | "
                  f"Vol: {int(self.master_volume*100)}%   ",
                  end='', flush=True)
        else:
            print(f"\rNo notes playing. Vol: {int(self.master_volume*100)}%"
                  "                              ",
                  end='', flush=True)


def get_keyboard_input_unix():
    """Get raw keyboard input on Unix systems"""
    import termios
    import tty
    import select

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        while True:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch = sys.stdin.read(1)
                yield ('down', ch)
            else:
                yield (None, None)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main():
    print("\n" + "=" * 60)
    print("  AEROTONE MODEL 12 - Interactive Demo")
    print("=" * 60)
    print("""
Keyboard Layout (like a piano):
  W E   T Y U I
 A S D F G H J

 A  = A2  (110 Hz)    W  = A#2
 S  = B2              R  = C#3
 D  = C3              T  = D#3
 F  = D3              U  = F#3
 G  = E3              I  = G#3
 H  = F3
 J  = G3

Controls:
  Q = Quit
  SPACE = All notes off
  1-9 = Set volume (10%-90%)
  0 = Volume 100%

Press any note key to begin...
""")

    demo = AeroToneDemo()

    # Start audio stream
    try:
        stream = sd.OutputStream(
            samplerate=demo.sample_rate,
            channels=1,
            blocksize=demo.block_size,
            callback=demo.audio_callback
        )
        stream.start()
    except Exception as e:
        print(f"ERROR starting audio: {e}")
        return

    print("\nAudio started. Play some notes!")
    print("-" * 60)

    try:
        for event_type, key in get_keyboard_input_unix():
            if event_type == 'down':
                if key == 'q' or key == '\x03':  # q or Ctrl+C
                    print("\n\nQuitting...")
                    break
                elif key == ' ':
                    demo.all_off()
                    print("\nAll notes off")
                elif key in '0123456789':
                    demo.master_volume = int(key) / 10.0 if key != '0' else 1.0
                elif key in KEY_MAP:
                    result = demo.key_down(key)
                    # Simple toggle for this demo (press again to stop)
                    if result is None:
                        demo.key_up(key)

                demo.print_status()

    except KeyboardInterrupt:
        print("\n\nInterrupted")
    finally:
        stream.stop()
        stream.close()

    print("\nThanks for playing the AeroTone!")


if __name__ == '__main__':
    # Check for Unix system
    if sys.platform == 'win32':
        print("This interactive demo requires Unix/macOS.")
        print("For Windows, use demo_simple.py instead.")
        sys.exit(1)

    main()

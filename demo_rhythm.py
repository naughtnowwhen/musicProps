#!/usr/bin/env python3
"""
AeroTone Rhythm Demo - AUTHENTIC IRIS CIRCUIT VERSION

Demonstrates rhythmic articulation using the SPICE-level iris circuit.

The IRIS APERTURE physically opens and closes to control volume:
  - Expression pedal voltage (0-10V) controls servo position
  - 555 timer generates PWM carrier for servo
  - BJT driver (BD139/BD140) powers the servo motor
  - Servo motor has mechanical inertia (realistic response time!)
  - Iris blades physically block/allow sound

This is AUTHENTIC to the 1979 electromechanical design - no digital
amplitude tricks. The servo motor's mechanical response creates
natural attack/release characteristics.

Caching: Audio is cached after first run. Use --no-cache to regenerate.
"""

import sys
import os
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed")
    sys.exit(1)

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.propeller import NOTES

# Cache
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.audio_cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'rhythm_demo.npz')


class AuthenticRhythmGenerator:
    """
    Generates rhythmic patterns using authentic SPICE iris control.

    The iris aperture is controlled by a servo motor driven by:
      - Expression pedal → voltage
      - 555 timer → PWM carrier
      - BJT H-bridge → servo power
      - Servo motor → iris blade position

    The servo motor's mechanical response (inertia, friction) creates
    natural attack and release characteristics - no digital tricks!
    """

    def __init__(self, voice, sample_rate=44100, tempo_bpm=100):
        self.voice = voice
        self.sample_rate = sample_rate
        self.tempo_bpm = tempo_bpm
        self.beat_duration = 60.0 / tempo_bpm
        self.chunk_size = int(sample_rate * 0.002)  # 2ms chunks for responsive iris

    def _generate_with_iris(self, duration_s, expression_value):
        """
        Generate audio with iris at specified expression level.

        expression_value: 0.0 = iris closed (silent)
                         1.0 = iris fully open (full volume)
        """
        # Set expression pedal position
        if hasattr(self.voice, 'iris_circuit') and self.voice.iris_circuit:
            self.voice.iris_circuit.set_expression(expression_value)
        elif hasattr(self.voice, 'expression') and self.voice.expression:
            self.voice.expression.set_expression(expression_value)

        samples = int(duration_s * self.sample_rate)
        audio = []

        for i in range(0, samples, self.chunk_size):
            n = min(self.chunk_size, samples - i)
            audio.append(self.voice.generate_audio(n))

        return np.concatenate(audio) if audio else np.array([])

    def generate_articulated_note(self, freq, note_duration, gap_duration,
                                  open_time=0.03, close_time=0.03):
        """
        Generate one articulated note using iris open/close.

        The servo motor response creates natural attack/release.

        Args:
            freq: Note frequency
            note_duration: How long the note sounds
            gap_duration: Silent gap after note
            open_time: Time to ramp iris open (servo response)
            close_time: Time to ramp iris closed
        """
        self.voice.set_target_frequency(freq)

        audio = []

        # === NOTE PORTION ===
        # Ramp iris open (attack)
        open_samples = int(open_time * self.sample_rate)
        steps = max(1, open_samples // self.chunk_size)
        for i in range(steps):
            expr = (i + 1) / steps  # 0 -> 1
            chunk = self._generate_with_iris(self.chunk_size / self.sample_rate, expr)
            audio.append(chunk)

        # Sustain with iris fully open
        sustain_time = note_duration - open_time - close_time
        if sustain_time > 0:
            audio.append(self._generate_with_iris(sustain_time, 1.0))

        # Ramp iris closed (release)
        close_samples = int(close_time * self.sample_rate)
        steps = max(1, close_samples // self.chunk_size)
        for i in range(steps):
            expr = 1.0 - ((i + 1) / steps)  # 1 -> 0
            chunk = self._generate_with_iris(self.chunk_size / self.sample_rate, expr)
            audio.append(chunk)

        # === GAP PORTION (iris closed) ===
        if gap_duration > 0:
            audio.append(self._generate_with_iris(gap_duration, 0.0))

        return np.concatenate(audio) if audio else np.array([])

    def generate_repeated_notes(self, freq, count, subdivision='quarter',
                               open_ms=30, close_ms=40, gap_ratio=0.15):
        """
        Generate repeated notes with authentic iris articulation.

        Args:
            freq: Note frequency
            count: Number of notes
            subdivision: 'quarter', 'eighth', 'sixteenth', 'triplet'
            open_ms: Iris open time (servo response for attack)
            close_ms: Iris close time (servo response for release)
            gap_ratio: Fraction of note as silent gap
        """
        durations = {
            'whole': 4.0, 'half': 2.0, 'quarter': 1.0,
            'eighth': 0.5, 'sixteenth': 0.25, 'triplet': 1.0/3.0,
        }

        note_beats = durations.get(subdivision, 1.0)
        total_duration = note_beats * self.beat_duration

        gap_duration = total_duration * gap_ratio
        note_duration = total_duration - gap_duration

        # Ensure open/close times fit within note
        open_time = min(open_ms / 1000, note_duration * 0.4)
        close_time = min(close_ms / 1000, note_duration * 0.4)

        self.voice.set_target_frequency(freq)

        audio = []
        for _ in range(count):
            note_audio = self.generate_articulated_note(
                freq, note_duration, gap_duration,
                open_time=open_time, close_time=close_time
            )
            audio.append(note_audio)

        return np.concatenate(audio) if audio else np.array([])


def warm_up_voice(voice, freq, steps=2000):
    """Pre-spin propeller and open iris"""
    voice.set_target_frequency(freq)

    # Set iris fully open during warmup
    if hasattr(voice, 'iris_circuit') and voice.iris_circuit:
        voice.iris_circuit.set_expression(1.0)
    elif hasattr(voice, 'expression') and voice.expression:
        voice.expression.set_expression(1.0)

    for _ in range(steps):
        voice.update_physics(0.001)


def generate_demo():
    """Generate the full rhythm demonstration with authentic iris control"""
    sample_rate = 44100
    tempo_bpm = 60  # Relaxed tempo - gives iris servo time to respond

    # Enable SPICE-level iris circuit for authentic behavior
    params = SpiceVoiceParams(
        use_circuit_iris=True,
        expression_duck_enabled=False,  # We're controlling expression directly
    )

    sections = {}

    print(f"\n[1/5] Generating quarter notes ({tempo_bpm} BPM) - SPICE iris...")
    voice = SpiceVoice(params=params, sample_rate=sample_rate)
    warm_up_voice(voice, NOTES['A2'])

    gen = AuthenticRhythmGenerator(voice, sample_rate, tempo_bpm)

    # 8 quarter notes - relaxed iris movement (1 second each)
    sections['quarter'] = gen.generate_repeated_notes(
        NOTES['A2'], count=8, subdivision='quarter',
        open_ms=50, close_ms=80, gap_ratio=0.10
    )

    print("[2/5] Generating eighth notes - comfortable iris cycling...")
    voice = SpiceVoice(params=params, sample_rate=sample_rate)
    warm_up_voice(voice, NOTES['D3'])
    gen = AuthenticRhythmGenerator(voice, sample_rate, tempo_bpm)

    # 16 eighth notes (500ms each)
    sections['eighth'] = gen.generate_repeated_notes(
        NOTES['D3'], count=16, subdivision='eighth',
        open_ms=40, close_ms=60, gap_ratio=0.12
    )

    print("[3/5] Generating sixteenth notes - still comfortable at 60 BPM...")
    voice = SpiceVoice(params=params, sample_rate=sample_rate)
    warm_up_voice(voice, NOTES['E3'])
    gen = AuthenticRhythmGenerator(voice, sample_rate, tempo_bpm)

    # 32 sixteenth notes (250ms each - plenty of time!)
    sections['sixteenth'] = gen.generate_repeated_notes(
        NOTES['E3'], count=32, subdivision='sixteenth',
        open_ms=25, close_ms=40, gap_ratio=0.15
    )

    print("[4/5] Generating triplets - swing feel...")
    voice = SpiceVoice(params=params, sample_rate=sample_rate)
    warm_up_voice(voice, NOTES['G3'])
    gen = AuthenticRhythmGenerator(voice, sample_rate, tempo_bpm)

    # 24 triplets (333ms each)
    sections['triplet'] = gen.generate_repeated_notes(
        NOTES['G3'], count=24, subdivision='triplet',
        open_ms=30, close_ms=50, gap_ratio=0.12
    )

    print("[5/5] Generating rhythmic melody - authentic iris control...")
    voice = SpiceVoice(params=params, sample_rate=sample_rate)
    warm_up_voice(voice, NOTES['A2'])

    # Same tempo for melody
    gen = AuthenticRhythmGenerator(voice, sample_rate, tempo_bpm=tempo_bpm)

    melody = [
        ('A2', 'quarter'), ('A2', 'quarter'), ('C#3', 'eighth'), ('D3', 'eighth'), ('E3', 'half'),
        ('E3', 'quarter'), ('E3', 'quarter'), ('D3', 'eighth'), ('C#3', 'eighth'), ('A2', 'half'),
        ('A2', 'eighth'), ('B2', 'eighth'), ('C#3', 'eighth'), ('D3', 'eighth'),
        ('E3', 'eighth'), ('F#3', 'eighth'), ('G#3', 'eighth'), ('A3', 'eighth'),
        ('A3', 'whole'),
    ]

    melody_audio = []
    for note, subdivision in melody:
        freq = NOTES[note]

        # Let pitch settle slightly between notes
        voice.set_target_frequency(freq)
        for _ in range(30):
            voice.update_physics(0.001)

        note_audio = gen.generate_repeated_notes(
            freq, count=1, subdivision=subdivision,
            open_ms=30, close_ms=50, gap_ratio=0.10
        )
        melody_audio.append(note_audio)

    sections['melody'] = np.concatenate(melody_audio)

    return sections


def main():
    use_cache = '--no-cache' not in sys.argv

    print("=" * 70)
    print("  AEROTONE RHYTHM DEMO")
    print("  Authentic SPICE-Level Iris Aperture Control")
    print("=" * 70)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    print("""
AUTHENTIC ELECTROMECHANICAL ARTICULATION:

The iris aperture is controlled by real circuit simulation:

  Expression Pedal (10k pot)
       │
       ▼
  Envelope Generator (RC timing)
       │
       ▼
  555 Timer (PWM carrier @ ~45Hz)
       │
       ▼
  PWM Comparator (LM339)
       │
       ▼
  BJT H-Bridge (BD139/BD140)
       │
       ▼
  Servo Motor (DC motor + gearbox + feedback pot)
       │
       ▼
  Iris Aperture (9-blade mechanical iris)
       │
       ▼
  SOUND OUTPUT

The servo motor's mechanical response (inertia, friction, gearbox)
creates NATURAL attack/release characteristics - no digital tricks!

Different subdivisions challenge the servo's response speed.
""")

    sample_rate = 44100

    # Check cache
    sections = None
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            data = np.load(CACHE_FILE, allow_pickle=True)
            sections = {name: data[name] for name in ['quarter', 'eighth', 'sixteenth', 'triplet', 'melody']}
            print("[Loaded from cache]\n")
        except:
            sections = None

    if sections is None:
        sections = generate_demo()

        # Save to cache
        os.makedirs(CACHE_DIR, exist_ok=True)
        np.savez(CACHE_FILE, **sections)
        print("\n[Saved to cache]")

    # Normalize all sections
    def normalize(audio, target=0.8):
        peak = np.max(np.abs(audio))
        return audio / peak * target if peak > 0 else audio

    # Playback
    print("\n" + "=" * 70)
    print("PLAYBACK")
    print("=" * 70)

    section_info = [
        ('quarter', "QUARTER NOTES (60 BPM)", "A2 - 1 second per note, relaxed"),
        ('eighth', "EIGHTH NOTES", "D3 - 500ms per note, comfortable"),
        ('sixteenth', "SIXTEENTH NOTES", "E3 - 250ms per note, still clean"),
        ('triplet', "TRIPLETS", "G3 - 333ms per note, swing feel"),
        ('melody', "RHYTHMIC MELODY", "Pitch changes + iris articulation"),
    ]

    for i, (name, title, desc) in enumerate(section_info):
        audio = sections[name]
        duration = len(audio) / sample_rate

        print(f"\n{i+1}. {title}")
        print(f"   {desc}")
        print(f"   Duration: {duration:.1f}s")

        sd.play(normalize(audio), sample_rate)
        sd.wait()

    print("\n" + "=" * 70)
    print("AUTHENTIC IRIS BEHAVIOR")
    print("=" * 70)
    print("""
What you heard was REAL electromechanical simulation:

  - Servo motor can't move instantly (inertia)
  - Faster subdivisions challenge the servo's response
  - The 555 timer PWM creates ~45Hz control signal
  - BJT driver has switching characteristics
  - Gearbox ratio affects speed vs torque

Complete silence = iris fully closed (0% aperture)
Full volume = iris fully open (100% aperture)

This is how a 1979 electromechanical instrument would actually behave!
""")


if __name__ == '__main__':
    main()

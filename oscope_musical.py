#!/usr/bin/env python3
"""
Musical Oscilloscope Captures

Captures waveforms during ACTUAL MUSIC PLAYBACK showing:
- Note transitions and pitch changes
- PLL tracking and lock acquisition
- Dynamic loop filter response
- Motor acceleration/deceleration

This shows the circuit doing real work, not just sitting idle!
"""

import numpy as np
import matplotlib.pyplot as plt
import os

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench

os.makedirs('oscope_output', exist_ok=True)


def note_to_freq(note_name):
    """Convert note name to frequency"""
    notes = {
        'C3': 130.81, 'D3': 146.83, 'E3': 164.81, 'F3': 174.61,
        'G3': 196.00, 'A3': 220.00, 'B3': 246.94,
        'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
        'G4': 392.00, 'A4': 440.00, 'B4': 493.88,
        'C5': 523.25,
    }
    return notes.get(note_name, 220.0)


class MusicalOscilloscope:
    """Capture oscilloscope traces during musical performance"""

    def __init__(self):
        self.params = SpiceVoiceParams(enable_thermal=False)
        self.voice = SpiceVoice(params=self.params, sample_rate=44100)
        self.bench = TestBench(self.voice)
        self.sample_rate = 44100

    def capture_during_playback(self, probe_points, duration,
                                 note_sequence=None, continuous_sweep=None):
        """
        Capture multiple probe points simultaneously during musical playback.

        Args:
            probe_points: List of probe point names
            duration: Total capture duration in seconds
            note_sequence: List of (time, note_name) tuples for discrete notes
            continuous_sweep: Dict with 'start_freq', 'end_freq' for pitch sweep
        """
        num_samples = int(duration * self.sample_rate)
        captures = {point: np.zeros(num_samples) for point in probe_points}
        times = np.linspace(0, duration, num_samples)

        # Build frequency timeline
        if note_sequence:
            freq_timeline = self._build_note_timeline(note_sequence, duration)
        elif continuous_sweep:
            freq_timeline = np.linspace(
                continuous_sweep['start_freq'],
                continuous_sweep['end_freq'],
                num_samples
            )
        else:
            freq_timeline = np.ones(num_samples) * 220.0

        dt = 1.0 / self.sample_rate

        for i in range(num_samples):
            # Update target frequency
            self.voice.set_target_frequency(freq_timeline[i])

            # Run physics
            self.voice.update_physics(dt)

            # Capture all probe points
            for point in probe_points:
                captures[point][i] = self.bench.probe(point)

        return times, captures, freq_timeline

    def _build_note_timeline(self, note_sequence, duration):
        """Build frequency array from note sequence"""
        num_samples = int(duration * self.sample_rate)
        freq_timeline = np.zeros(num_samples)

        # Sort by time
        sorted_notes = sorted(note_sequence, key=lambda x: x[0])

        for i, (time, note) in enumerate(sorted_notes):
            start_idx = int(time * self.sample_rate)
            if i + 1 < len(sorted_notes):
                end_idx = int(sorted_notes[i + 1][0] * self.sample_rate)
            else:
                end_idx = num_samples
            freq_timeline[start_idx:end_idx] = note_to_freq(note)

        return freq_timeline


def create_musical_oscope_plot(times, captures, freq_timeline, title, filename):
    """Create a multi-channel oscilloscope display showing musical dynamics"""

    fig, axes = plt.subplots(6, 1, figsize=(16, 14), facecolor='#000000')
    fig.suptitle(title, color='#00ff00', fontsize=16, fontweight='bold', y=0.98)

    colors = {
        'loop_filter_cap_voltage': '#ffff00',
        'motor_voltage': '#ff8800',
        'motor_rpm': '#ff4444',
        'pickup_raw': '#00ffff',
        'cd4046_pin4_vco_out': '#00ff00',
        'cond_comparator_out': '#ff00ff',
    }

    labels = {
        'loop_filter_cap_voltage': 'Loop Filter (Control Voltage)',
        'motor_voltage': 'Motor Drive Voltage',
        'motor_rpm': 'Motor RPM',
        'pickup_raw': 'Pickup Signal (Raw)',
        'cd4046_pin4_vco_out': 'VCO Output',
        'cond_comparator_out': 'Feedback Pulses',
    }

    times_ms = times * 1000  # Convert to ms

    # Plot target frequency on top
    ax = axes[0]
    ax.set_facecolor('#001100')
    ax.plot(times_ms, freq_timeline, color='#ffffff', linewidth=2, alpha=0.9)
    ax.set_ylabel('Target\nFreq (Hz)', color='#ffffff', fontsize=9)
    ax.tick_params(colors='#00aa00', labelsize=7)
    ax.grid(True, color='#004400', alpha=0.5)
    ax.set_title('Target Frequency (Musical Input)', color='#ffffff', fontsize=10, loc='left')
    for spine in ax.spines.values():
        spine.set_color('#004400')

    # Plot each capture
    plot_order = ['loop_filter_cap_voltage', 'motor_voltage', 'motor_rpm',
                  'pickup_raw', 'cond_comparator_out']

    for ax, point in zip(axes[1:], plot_order):
        ax.set_facecolor('#001100')

        data = captures[point]
        color = colors.get(point, '#00ff00')

        # Plot with glow effect
        ax.plot(times_ms, data, color=color, linewidth=0.8, alpha=0.4)
        ax.plot(times_ms, data, color='#ffffff', linewidth=0.3, alpha=0.6)

        ax.set_ylabel(labels.get(point, point).replace(' ', '\n'),
                     color=color, fontsize=8)
        ax.tick_params(colors='#00aa00', labelsize=7)
        ax.grid(True, color='#004400', alpha=0.5)

        # Add stats
        vpp = np.max(data) - np.min(data)
        vavg = np.mean(data)
        stats = f"Vpp={vpp:.2f}  Avg={vavg:.2f}"
        ax.text(0.99, 0.95, stats, transform=ax.transAxes, color='#00aa00',
                fontsize=7, ha='right', va='top', fontfamily='monospace')

        for spine in ax.spines.values():
            spine.set_color('#004400')

    axes[-1].set_xlabel('Time (ms)', color='#00ff00', fontsize=10)

    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    plt.savefig(filename, dpi=150, facecolor='#000000', edgecolor='none')
    print(f"  Saved: {filename}")
    plt.close()


def main():
    print("=" * 60)
    print("  MUSICAL OSCILLOSCOPE - Dynamic Circuit Captures")
    print("=" * 60)

    oscope = MusicalOscilloscope()

    # Probe points to capture
    probes = [
        'loop_filter_cap_voltage',
        'motor_voltage',
        'motor_rpm',
        'pickup_raw',
        'cd4046_pin4_vco_out',
        'cond_comparator_out',
    ]

    # ================================================================
    # CAPTURE 1: Melodic phrase - quick note changes
    # ================================================================
    print("\n[1] Capturing melodic phrase (C-E-G-C arpeggio)...")

    # Warm up first
    oscope.voice.set_target_frequency(261.63)  # C4
    for _ in range(int(44100 * 0.3)):
        oscope.voice.update_physics(1/44100)

    melody = [
        (0.0, 'C4'),    # C
        (0.15, 'E4'),   # E
        (0.30, 'G4'),   # G
        (0.45, 'C5'),   # C octave up
        (0.60, 'G4'),   # Back down
        (0.75, 'E4'),
        (0.90, 'C4'),
    ]

    times, captures, freqs = oscope.capture_during_playback(
        probes, duration=1.0, note_sequence=melody
    )

    create_musical_oscope_plot(
        times, captures, freqs,
        "Capture 1: Arpeggio (C-E-G-C) - Note Transitions",
        "oscope_output/musical_1_arpeggio.png"
    )

    # ================================================================
    # CAPTURE 2: Pitch bend / slide
    # ================================================================
    print("\n[2] Capturing pitch bend (A3 to A4 slide)...")

    # Reset and warm up at A3
    oscope.voice.set_target_frequency(220.0)
    for _ in range(int(44100 * 0.3)):
        oscope.voice.update_physics(1/44100)

    times, captures, freqs = oscope.capture_during_playback(
        probes, duration=0.8,
        continuous_sweep={'start_freq': 220.0, 'end_freq': 440.0}
    )

    create_musical_oscope_plot(
        times, captures, freqs,
        "Capture 2: Pitch Bend (A3→A4 Octave Slide)",
        "oscope_output/musical_2_pitch_bend.png"
    )

    # ================================================================
    # CAPTURE 3: Fast trill
    # ================================================================
    print("\n[3] Capturing fast trill (E4-F4 alternation)...")

    oscope.voice.set_target_frequency(329.63)  # E4
    for _ in range(int(44100 * 0.2)):
        oscope.voice.update_physics(1/44100)

    # Fast trill - alternating notes
    trill = []
    for i in range(16):
        t = i * 0.04  # 25Hz trill rate
        note = 'E4' if i % 2 == 0 else 'F4'
        trill.append((t, note))

    times, captures, freqs = oscope.capture_during_playback(
        probes, duration=0.64, note_sequence=trill
    )

    create_musical_oscope_plot(
        times, captures, freqs,
        "Capture 3: Fast Trill (E4↔F4 @ 25Hz)",
        "oscope_output/musical_3_trill.png"
    )

    # ================================================================
    # CAPTURE 4: Big interval jump
    # ================================================================
    print("\n[4] Capturing interval jump (C3 to C5 - 2 octaves)...")

    oscope.voice.set_target_frequency(130.81)  # C3
    for _ in range(int(44100 * 0.3)):
        oscope.voice.update_physics(1/44100)

    jump = [
        (0.0, 'C3'),    # Low C
        (0.25, 'C5'),   # Jump up 2 octaves!
        (0.50, 'C3'),   # Back down
        (0.75, 'C5'),   # Up again
    ]

    times, captures, freqs = oscope.capture_during_playback(
        probes, duration=1.0, note_sequence=jump
    )

    create_musical_oscope_plot(
        times, captures, freqs,
        "Capture 4: Big Interval Jump (C3↔C5 - 2 Octaves)",
        "oscope_output/musical_4_interval_jump.png"
    )

    # ================================================================
    # CAPTURE 5: Vibrato simulation
    # ================================================================
    print("\n[5] Capturing vibrato (A4 with ~6Hz modulation)...")

    oscope.voice.set_target_frequency(440.0)  # A4
    for _ in range(int(44100 * 0.2)):
        oscope.voice.update_physics(1/44100)

    # Create vibrato - sinusoidal frequency modulation
    duration = 0.8
    num_samples = int(duration * 44100)
    vibrato_rate = 6.0  # Hz
    vibrato_depth = 15.0  # Hz deviation
    center_freq = 440.0

    t = np.linspace(0, duration, num_samples)
    vibrato_freqs = center_freq + vibrato_depth * np.sin(2 * np.pi * vibrato_rate * t)

    # Manual capture with vibrato
    captures = {point: np.zeros(num_samples) for point in probes}
    dt = 1.0 / 44100

    for i in range(num_samples):
        oscope.voice.set_target_frequency(vibrato_freqs[i])
        oscope.voice.update_physics(dt)
        for point in probes:
            captures[point][i] = oscope.bench.probe(point)

    create_musical_oscope_plot(
        t, captures, vibrato_freqs,
        "Capture 5: Vibrato (A4 ± 15Hz @ 6Hz rate)",
        "oscope_output/musical_5_vibrato.png"
    )

    print("\n" + "=" * 60)
    print("  MUSICAL CAPTURES COMPLETE")
    print("=" * 60)
    print("""
These captures show the AeroTone circuit responding to real musical input:

1. ARPEGGIO - Watch the loop filter step up with each note change
2. PITCH BEND - Smooth ramp as PLL tracks continuous frequency change
3. TRILL - Rapid oscillation between two notes, testing PLL bandwidth
4. INTERVAL JUMP - Extreme frequency change, see motor acceleration
5. VIBRATO - Periodic modulation, classic musical expression

The loop filter voltage directly shows how the PLL is working -
each note change causes a step or ramp as it acquires lock!
""")


if __name__ == '__main__':
    main()

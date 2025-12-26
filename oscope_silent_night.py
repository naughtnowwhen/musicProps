#!/usr/bin/env python3
"""
Silent Night - Oscilloscope Capture

Full 30+ second capture of Silent Night showing the AeroTone
circuit responding to a real musical piece.
"""

import numpy as np
import matplotlib.pyplot as plt
import os

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench

os.makedirs('oscope_output', exist_ok=True)


# Note frequencies (A4 = 440Hz standard tuning)
NOTES = {
    'R': 0,      # Rest
    'C3': 130.81, 'D3': 146.83, 'E3': 164.81, 'F3': 174.61,
    'G3': 196.00, 'A3': 220.00, 'B3': 246.94,
    'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
    'G4': 392.00, 'A4': 440.00, 'B4': 493.88,
    'C5': 523.25, 'D5': 587.33, 'E5': 659.25, 'F5': 698.46,
    'G5': 783.99,
}


def create_silent_night_melody():
    """
    Silent Night melody with timing.
    Returns list of (time_in_seconds, note_name, duration) tuples.

    Tempo: ~54 BPM (dotted quarter = 54, so quarter ~= 81 BPM)
    Time signature: 6/8 (compound duple)

    For simplicity, using 6/8 feel where dotted quarter ~= 1.1 seconds
    """

    # Tempo: dotted quarter note = ~55 BPM
    # So dotted quarter = 60/55 = 1.09 seconds
    # Quarter note = 0.73 seconds
    # Eighth note = 0.36 seconds

    dq = 1.1    # dotted quarter
    q = 0.73    # quarter
    e = 0.36    # eighth
    h = 1.46    # half
    dh = 2.2    # dotted half (full measure in 6/8)

    melody = []
    t = 0.0

    # Key of C major, starting on G4
    # Format: (note, duration)

    # "Si-lent night" - G. A G | E.
    notes_and_durations = [
        # Measure 1-2: "Silent night"
        ('G4', dq - e), ('A4', e), ('G4', q),  # Si - lent
        ('E4', dh),                              # night

        # Measure 3-4: "Holy night"
        ('G4', dq - e), ('A4', e), ('G4', q),  # Ho - ly
        ('E4', dh),                              # night

        # Measure 5-6: "All is calm"
        ('D5', dq), ('D5', q),                  # All is
        ('B4', dh),                              # calm

        # Measure 7-8: "All is bright"
        ('C5', dq), ('C5', q),                  # All is
        ('G4', dh),                              # bright

        # Measure 9-10: "Round yon virgin"
        ('A4', dq), ('A4', dq - e), ('C5', e),  # Round yon vir-
        ('B4', q), ('A4', q),                    # -gin

        # Measure 11-12: "Mother and child"
        ('G4', dq - e), ('A4', e), ('G4', q),  # Mo-ther and
        ('E4', dh),                              # child

        # Measure 13-14: "Holy infant so"
        ('A4', dq), ('A4', dq - e), ('C5', e),  # Ho-ly in-fant
        ('B4', q), ('A4', q),                    # so

        # Measure 15-16: "Tender and mild"
        ('G4', dq - e), ('A4', e), ('G4', q),  # ten-der and
        ('E4', dh),                              # mild

        # Measure 17-18: "Sleep in heavenly"
        ('D5', dq), ('D5', dq - e), ('F5', e),  # Sleep in hea-
        ('D5', q), ('B4', q),                    # ven-ly

        # Measure 19-20: "peace" (first time)
        ('C5', dh),                              # peace
        ('E5', dh),                              # (held)

        # Measure 21-22: "Sleep in heavenly"
        ('C5', dq - e), ('G4', e), ('E4', q),   # Sleep in hea-
        ('G4', dq - e), ('F4', e), ('D4', q),   # ven-ly

        # Measure 23-24: "peace" (final)
        ('C4', dh * 1.5),                        # peace (held long)
    ]

    for note, duration in notes_and_durations:
        melody.append((t, note, duration))
        t += duration

    return melody, t  # Return melody and total duration


def capture_silent_night():
    """Capture oscilloscope traces during Silent Night playback"""

    print("=" * 60)
    print("  SILENT NIGHT - Oscilloscope Capture")
    print("=" * 60)

    melody, total_duration = create_silent_night_melody()
    print(f"\nMelody duration: {total_duration:.1f} seconds")
    print(f"Total notes: {len(melody)}")

    # Initialize voice
    print("\nInitializing circuit...")
    params = SpiceVoiceParams(enable_thermal=False)
    voice = SpiceVoice(params=params, sample_rate=44100)
    bench = TestBench(voice)

    # Warm up at first note
    first_freq = NOTES[melody[0][1]]
    voice.set_target_frequency(first_freq)
    print(f"Warming up at {melody[0][1]} ({first_freq:.1f} Hz)...")
    for _ in range(int(44100 * 0.5)):
        voice.update_physics(1/44100)

    # Probe points
    probes = [
        'loop_filter_cap_voltage',
        'motor_voltage',
        'motor_rpm',
        'pickup_raw',
        'cond_comparator_out',
    ]

    # Capture
    print(f"\nCapturing {total_duration:.1f} seconds of Silent Night...")
    sample_rate = 44100
    num_samples = int(total_duration * sample_rate)

    captures = {p: np.zeros(num_samples) for p in probes}
    freq_timeline = np.zeros(num_samples)
    times = np.linspace(0, total_duration, num_samples)

    # Build frequency timeline from melody
    note_idx = 0
    for i in range(num_samples):
        t = i / sample_rate

        # Find current note
        while note_idx < len(melody) - 1:
            next_time = melody[note_idx + 1][0]
            if t >= next_time:
                note_idx += 1
            else:
                break

        note_name = melody[note_idx][1]
        freq = NOTES.get(note_name, 220.0)
        if freq == 0:  # Rest
            freq = NOTES.get(melody[max(0, note_idx-1)][1], 220.0)  # Hold previous

        freq_timeline[i] = freq

    # Run simulation and capture
    dt = 1.0 / sample_rate
    last_percent = -1

    for i in range(num_samples):
        # Progress indicator
        percent = int(100 * i / num_samples)
        if percent != last_percent and percent % 10 == 0:
            print(f"  {percent}% complete...")
            last_percent = percent

        voice.set_target_frequency(freq_timeline[i])
        voice.update_physics(dt)

        for p in probes:
            captures[p][i] = bench.probe(p)

    print("  100% complete!")

    return times, captures, freq_timeline, melody, total_duration


def create_full_song_plot(times, captures, freq_timeline, melody, duration):
    """Create comprehensive oscilloscope plot of the full song"""

    fig, axes = plt.subplots(6, 1, figsize=(20, 14), facecolor='#000000')
    fig.suptitle('Silent Night - Full Oscilloscope Capture',
                 color='#00ff00', fontsize=18, fontweight='bold', y=0.98)

    # Color scheme
    colors = {
        'freq': '#ffffff',
        'loop_filter_cap_voltage': '#ffff00',
        'motor_voltage': '#ff8800',
        'motor_rpm': '#ff4444',
        'pickup_raw': '#00ffff',
        'cond_comparator_out': '#ff00ff',
    }

    labels = [
        ('Target Frequency', 'freq', freq_timeline),
        ('Loop Filter (Control)', 'loop_filter_cap_voltage', captures['loop_filter_cap_voltage']),
        ('Motor Voltage', 'motor_voltage', captures['motor_voltage']),
        ('Motor RPM', 'motor_rpm', captures['motor_rpm']),
        ('Pickup Signal', 'pickup_raw', captures['pickup_raw']),
        ('Feedback Pulses', 'cond_comparator_out', captures['cond_comparator_out']),
    ]

    for ax, (label, key, data) in zip(axes, labels):
        ax.set_facecolor('#001100')

        color = colors.get(key, '#00ff00')

        # Downsample for plotting if needed (every Nth point)
        N = max(1, len(times) // 4000)
        t_plot = times[::N]
        d_plot = data[::N]

        ax.plot(t_plot, d_plot, color=color, linewidth=0.5, alpha=0.8)

        ax.set_ylabel(label, color=color, fontsize=9)
        ax.tick_params(colors='#00aa00', labelsize=7)
        ax.grid(True, color='#004400', alpha=0.3, linewidth=0.5)

        for spine in ax.spines.values():
            spine.set_color('#004400')

    axes[-1].set_xlabel('Time (seconds)', color='#00ff00', fontsize=11)

    # Add lyrics/notes annotations on top plot
    ax_top = axes[0]
    lyrics = [
        (0, "Si-"), (1.1, "lent"), (2.2, "night,"),
        (4.4, "Ho-"), (5.5, "ly"), (6.6, "night,"),
        (8.8, "All"), (9.9, "is"), (11.0, "calm,"),
        (13.2, "All"), (14.3, "is"), (15.4, "bright,"),
        (17.6, "Round"), (18.7, "yon"), (19.8, "vir-"), (20.5, "gin"),
    ]

    for t, lyric in lyrics:
        if t < duration:
            ax_top.axvline(t, color='#004400', linewidth=0.5, alpha=0.5)

    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    plt.savefig('oscope_output/silent_night_full.png', dpi=150,
                facecolor='#000000', edgecolor='none')
    print("\nSaved: oscope_output/silent_night_full.png")
    plt.close()


def create_detail_plots(times, captures, freq_timeline, melody, duration):
    """Create zoomed detail plots of interesting sections"""

    sections = [
        {
            'name': 'Opening - "Silent Night, Holy Night"',
            'start': 0,
            'end': 8.8,
            'filename': 'silent_night_detail_1_opening.png'
        },
        {
            'name': '"All is Calm, All is Bright"',
            'start': 8.8,
            'end': 17.6,
            'filename': 'silent_night_detail_2_calm_bright.png'
        },
        {
            'name': '"Round Yon Virgin, Mother and Child"',
            'start': 17.6,
            'end': 26.4,
            'filename': 'silent_night_detail_3_virgin.png'
        },
        {
            'name': '"Sleep in Heavenly Peace"',
            'start': max(0, duration - 12),
            'end': duration,
            'filename': 'silent_night_detail_4_peace.png'
        },
    ]

    for section in sections:
        start_idx = int(section['start'] * 44100)
        end_idx = min(int(section['end'] * 44100), len(times))

        if start_idx >= end_idx:
            continue

        fig, axes = plt.subplots(5, 1, figsize=(16, 12), facecolor='#000000')
        fig.suptitle(f"Silent Night: {section['name']}",
                     color='#00ff00', fontsize=14, fontweight='bold', y=0.98)

        t_sec = times[start_idx:end_idx]

        plot_data = [
            ('Target Freq (Hz)', freq_timeline[start_idx:end_idx], '#ffffff'),
            ('Loop Filter (V)', captures['loop_filter_cap_voltage'][start_idx:end_idx], '#ffff00'),
            ('Motor Voltage (V)', captures['motor_voltage'][start_idx:end_idx], '#ff8800'),
            ('Motor RPM', captures['motor_rpm'][start_idx:end_idx], '#ff4444'),
            ('Pickup Raw (V)', captures['pickup_raw'][start_idx:end_idx], '#00ffff'),
        ]

        for ax, (label, data, color) in zip(axes, plot_data):
            ax.set_facecolor('#001100')

            # Downsample for clarity
            N = max(1, len(t_sec) // 2000)
            ax.plot(t_sec[::N], data[::N], color=color, linewidth=0.8, alpha=0.9)

            ax.set_ylabel(label, color=color, fontsize=9)
            ax.tick_params(colors='#00aa00', labelsize=7)
            ax.grid(True, color='#004400', alpha=0.4)

            for spine in ax.spines.values():
                spine.set_color('#004400')

        axes[-1].set_xlabel('Time (seconds)', color='#00ff00', fontsize=10)

        plt.tight_layout(rect=[0, 0.02, 1, 0.96])
        plt.savefig(f"oscope_output/{section['filename']}", dpi=150,
                    facecolor='#000000', edgecolor='none')
        print(f"Saved: oscope_output/{section['filename']}")
        plt.close()


def main():
    # Capture the song
    times, captures, freq_timeline, melody, duration = capture_silent_night()

    # Create full song plot
    print("\nGenerating full song oscilloscope plot...")
    create_full_song_plot(times, captures, freq_timeline, melody, duration)

    # Create detail plots
    print("\nGenerating detail plots for key sections...")
    create_detail_plots(times, captures, freq_timeline, melody, duration)

    print("\n" + "=" * 60)
    print("  SILENT NIGHT CAPTURE COMPLETE")
    print("=" * 60)
    print(f"""
Captured {duration:.1f} seconds of Silent Night

Files generated:
  - silent_night_full.png        (complete song overview)
  - silent_night_detail_1_opening.png    ("Silent night, holy night")
  - silent_night_detail_2_calm_bright.png ("All is calm, all is bright")
  - silent_night_detail_3_virgin.png     ("Round yon virgin")
  - silent_night_detail_4_peace.png      ("Sleep in heavenly peace")

Watch the loop filter voltage - it steps up and down with each note,
showing the PLL tracking the melody in real time!
""")


if __name__ == '__main__':
    main()

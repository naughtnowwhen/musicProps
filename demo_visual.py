#!/usr/bin/env python3
"""
AeroTone Visual Demo - Real-time displays with audio

Shows:
  - RPM gauge (analog meter style)
  - Waveform display (oscilloscope)
  - Spectrum analyzer
  - Status panel

Uses matplotlib for visualization and sounddevice for audio.

Usage:
    python demo_visual.py [note]
"""

import sys
import time
import threading
import numpy as np

try:
    import sounddevice as sd
    import matplotlib
    matplotlib.use('TkAgg')  # Use TkAgg for better real-time updates
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge, Circle
    from matplotlib.collections import PatchCollection
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    print("Run: pip install sounddevice matplotlib")
    sys.exit(1)

sys.path.insert(0, '.')

from aerotone.voice import PropellerVoice
from aerotone.propeller import NOTES


class AnalogMeter:
    """Analog meter visualization"""

    def __init__(self, ax, title="RPM", min_val=0, max_val=3000):
        self.ax = ax
        self.min_val = min_val
        self.max_val = max_val

        ax.set_xlim(-1.2, 1.2)
        ax.set_ylim(-0.2, 1.2)
        ax.set_aspect('equal')
        ax.axis('off')
        ax.set_title(title, fontsize=14, fontweight='bold')

        # Draw meter background
        theta = np.linspace(np.pi, 0, 100)
        x = np.cos(theta)
        y = np.sin(theta)
        ax.plot(x, y, 'k-', linewidth=2)
        ax.plot([-1, 1], [0, 0], 'k-', linewidth=2)

        # Draw tick marks
        for val in np.linspace(min_val, max_val, 7):
            angle = np.pi - (val - min_val) / (max_val - min_val) * np.pi
            x1, y1 = 0.85 * np.cos(angle), 0.85 * np.sin(angle)
            x2, y2 = 1.0 * np.cos(angle), 1.0 * np.sin(angle)
            ax.plot([x1, x2], [y1, y2], 'k-', linewidth=1)
            # Label
            xl, yl = 0.7 * np.cos(angle), 0.7 * np.sin(angle)
            ax.text(xl, yl, f'{int(val)}', ha='center', va='center', fontsize=8)

        # Needle (will be updated)
        self.needle, = ax.plot([0, 0], [0, 0.8], 'r-', linewidth=3)

        # Center hub
        circle = Circle((0, 0), 0.05, color='black')
        ax.add_patch(circle)

        # Value display
        self.value_text = ax.text(0, -0.1, '0', ha='center', va='top',
                                  fontsize=12, fontweight='bold')

    def update(self, value):
        """Update meter needle and display"""
        # Clamp value
        value = np.clip(value, self.min_val, self.max_val)

        # Calculate needle angle
        angle = np.pi - (value - self.min_val) / (self.max_val - self.min_val) * np.pi
        x = 0.8 * np.cos(angle)
        y = 0.8 * np.sin(angle)

        self.needle.set_data([0, x], [0, y])
        self.value_text.set_text(f'{value:.0f}')


class VisualDemo:
    """Visual demo with audio"""

    def __init__(self, note='A2'):
        self.sample_rate = 44100
        self.block_size = 1024
        self.note = note
        self.freq = NOTES[note]

        # Create voice
        self.voice = PropellerVoice(sample_rate=self.sample_rate)
        self.voice.set_target_note(note)

        # Audio buffer for visualization
        self.audio_buffer = np.zeros(4096)
        self.buffer_lock = threading.Lock()

        # Setup figure
        self.fig = plt.figure(figsize=(12, 8))
        self.fig.suptitle(f'AeroTone Visual Demo - {note} ({self.freq:.1f} Hz)',
                         fontsize=16, fontweight='bold')

        # Create subplots
        gs = self.fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

        # RPM Meter
        ax_rpm = self.fig.add_subplot(gs[0, 0])
        self.rpm_meter = AnalogMeter(ax_rpm, "Motor RPM", 0, 3000)

        # Frequency Meter
        ax_freq = self.fig.add_subplot(gs[0, 1])
        self.freq_meter = AnalogMeter(ax_freq, "Frequency (Hz)", 0, 250)

        # Status panel
        self.ax_status = self.fig.add_subplot(gs[0, 2])
        self.ax_status.axis('off')
        self.status_text = self.ax_status.text(0.1, 0.9, '', fontsize=10,
                                               family='monospace',
                                               verticalalignment='top',
                                               transform=self.ax_status.transAxes)

        # Waveform
        self.ax_wave = self.fig.add_subplot(gs[1, 0:2])
        self.ax_wave.set_xlim(0, 2048)
        self.ax_wave.set_ylim(-1, 1)
        self.ax_wave.set_xlabel('Samples')
        self.ax_wave.set_ylabel('Amplitude')
        self.ax_wave.set_title('Waveform (Oscilloscope)')
        self.ax_wave.grid(True, alpha=0.3)
        self.wave_line, = self.ax_wave.plot([], [], 'g-', linewidth=1)

        # Spectrum
        self.ax_spec = self.fig.add_subplot(gs[1, 2])
        self.ax_spec.set_xlim(0, 1000)
        self.ax_spec.set_ylim(-60, 0)
        self.ax_spec.set_xlabel('Frequency (Hz)')
        self.ax_spec.set_ylabel('dB')
        self.ax_spec.set_title('Spectrum')
        self.ax_spec.grid(True, alpha=0.3)
        self.spec_line, = self.ax_spec.plot([], [], 'b-', linewidth=1)

        # Mark target frequency
        self.ax_spec.axvline(x=self.freq, color='r', linestyle='--', alpha=0.5,
                            label=f'Target: {self.freq:.1f} Hz')
        self.ax_spec.legend(loc='upper right')

        self.running = True

    def audio_callback(self, outdata, frames, time_info, status):
        """Audio callback"""
        if status:
            print(f"Audio: {status}")

        audio = self.voice.generate_audio(frames)
        outdata[:, 0] = audio

        # Update buffer for visualization
        with self.buffer_lock:
            self.audio_buffer = np.roll(self.audio_buffer, -frames)
            self.audio_buffer[-frames:] = audio

    def update_display(self):
        """Update all displays"""
        state = self.voice.get_state()

        # Update meters
        self.rpm_meter.update(state['current_rpm'])
        self.freq_meter.update(state['current_frequency'])

        # Update status
        locked = "LOCKED" if state['is_locked'] else "Hunting"
        status = f"""Target:    {state['target_frequency']:.2f} Hz
Current:   {state['current_frequency']:.2f} Hz
Error:     {state['frequency_error_hz']:+.2f} Hz
           ({state['frequency_error_cents']:+.1f} cents)
Status:    {locked}

Motor:
  Voltage:    {state['motor_voltage']:.1f} V
  Current:    {state['motor_current']:.2f} A
  Temp:       {state['motor_temperature']:.1f} C

Propeller:
  Torque:     {state['propeller_torque']*1000:.3f} mN-m
  Thrust:     {state['propeller_thrust']*1000:.1f} mN"""
        self.status_text.set_text(status)

        # Update waveform
        with self.buffer_lock:
            wave_data = self.audio_buffer[-2048:].copy()
        self.wave_line.set_data(np.arange(len(wave_data)), wave_data)

        # Update spectrum
        with self.buffer_lock:
            spec_data = self.audio_buffer.copy()

        # Compute FFT
        window = np.hanning(len(spec_data))
        fft = np.fft.rfft(spec_data * window)
        freqs = np.fft.rfftfreq(len(spec_data), 1/self.sample_rate)

        # Convert to dB
        magnitude = np.abs(fft)
        magnitude[magnitude < 1e-10] = 1e-10
        db = 20 * np.log10(magnitude / np.max(magnitude))

        # Filter to display range
        mask = freqs < 1000
        self.spec_line.set_data(freqs[mask], db[mask])

    def run(self, duration=30):
        """Run the demo"""
        print(f"\nStarting visual demo for {duration} seconds...")
        print("Close the window or press Ctrl+C to stop.\n")

        # Pre-spin motor
        for _ in range(500):
            self.voice.update_physics(0.001)

        # Start audio
        stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            blocksize=self.block_size,
            callback=self.audio_callback
        )
        stream.start()

        # Animation loop
        plt.ion()
        plt.show()

        start_time = time.time()
        try:
            while self.running and (time.time() - start_time < duration):
                self.update_display()
                self.fig.canvas.draw()
                self.fig.canvas.flush_events()
                plt.pause(0.05)

        except KeyboardInterrupt:
            print("\nStopped by user")
        finally:
            stream.stop()
            stream.close()
            plt.ioff()

        print("\nDemo complete!")


def main():
    note = 'A2'
    if len(sys.argv) > 1:
        note = sys.argv[1].upper()
        if note not in NOTES:
            print(f"Unknown note: {note}")
            print(f"Available: {', '.join(NOTES.keys())}")
            return

    demo = VisualDemo(note)
    demo.run(duration=60)


if __name__ == '__main__':
    main()

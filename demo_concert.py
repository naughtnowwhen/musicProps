#!/usr/bin/env python3
"""
AeroTone Concert-Scale Demo

Demonstrates the full concert-level power stage:
  - 500W motor capability
  - 48V DC bus
  - MOSFET H-bridge with PWM
  - Thermal management
  - Current limiting

This simulates what a concert-hall or outdoor installation would use.
Listen for the same musical behavior, but with monitoring of the
power electronics (current, temperature, efficiency).

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

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.audio_cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'concert_scale.npy')

from aerotone.concert_voice import ConcertVoice, get_concert_specs
from aerotone.propeller import NOTES
from aerotone.weather import Weather, TurbulentWeather


def print_specs():
    """Print concert voice specifications"""
    specs = get_concert_specs()
    print("""
┌─────────────────────────────────────────────────────────────┐
│              CONCERT-SCALE SPECIFICATIONS                   │
├─────────────────────────────────────────────────────────────┤
│  Propeller:     {diameter}mm diameter, {blades} blades               │
│  Motor:         {power}W rated, {voltage}V DC bus                      │
│  Current:       {current}A max continuous                          │
│  Frequency:     {f_lo}-{f_hi} Hz (A2-A3)                          │
│  RPM Range:     {rpm_lo}-{rpm_hi}                                   │
│  PWM:           {pwm} Hz (inaudible)                          │
│  Est. SPL:      {spl} dB at 1m                                 │
│  Weight:        ~{weight}kg per voice                              │
└─────────────────────────────────────────────────────────────┘
""".format(
        diameter=specs['propeller_diameter_mm'],
        blades=specs['propeller_blades'],
        power=specs['motor_power_w'],
        voltage=specs['bus_voltage_v'],
        current=specs['max_current_a'],
        f_lo=specs['frequency_range_hz'][0],
        f_hi=specs['frequency_range_hz'][1],
        rpm_lo=specs['rpm_range'][0],
        rpm_hi=specs['rpm_range'][1],
        pwm=specs['pwm_frequency_hz'],
        spl=specs['estimated_spl_db'],
        weight=specs['weight_kg'],
    ))


def run_spinup_test(voice, note='A2'):
    """Test motor spinup with power monitoring"""
    freq = NOTES[note]
    sample_rate = 44100

    print(f"\n{'='*60}")
    print(f"SPINUP TEST: {note} ({freq:.0f} Hz)")
    print(f"{'='*60}")
    print()
    print("Time     RPM      Freq     Error    Current  Temp   Duty")
    print("-" * 60)

    voice.set_target_frequency(freq)

    # Spinup monitoring
    times = []
    currents = []
    temps = []

    for i in range(50):  # 5 seconds at 100ms steps
        t = i * 0.1

        # Run physics for 100ms
        for _ in range(100):
            voice.update_physics(0.001)

        state = voice.get_state()

        times.append(t)
        currents.append(state['motor_current'])
        temps.append(state['t_junction'])

        if i % 5 == 0:  # Print every 500ms
            status = "LOCKED" if state['is_locked'] else f"{state['frequency_error_hz']:+.1f}Hz"
            print(f"{t:5.1f}s   {state['motor_rpm']:6.0f}   "
                  f"{state['prop_frequency']:5.1f}Hz  {status:8s}  "
                  f"{state['motor_current']:5.1f}A   {state['t_junction']:4.1f}°C  "
                  f"{state['duty_cycle']*100:4.1f}%")

    print()
    print(f"Peak current: {max(currents):.1f}A")
    print(f"Final temp:   {temps[-1]:.1f}°C")
    print(f"Efficiency:   {state['efficiency']*100:.1f}%")

    return voice


def generate_scale(voice, sample_rate=44100):
    """Generate a scale with power monitoring"""
    scale = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3', 'A3']
    note_duration = 0.85
    gliss_duration = 0.12

    print(f"\n{'='*60}")
    print("SCALE RUN WITH POWER MONITORING")
    print(f"{'='*60}")

    all_audio = []
    samples_per_ms = sample_rate // 1000

    def generate_segment(duration_s):
        samples = int(duration_s * sample_rate)
        chunk_size = samples_per_ms * 5
        audio = []
        for i in range(0, samples, chunk_size):
            n = min(chunk_size, samples - i)
            audio.append(voice.generate_audio(n))
        return np.concatenate(audio)

    def glissando(start_freq, end_freq, duration_s):
        samples = int(duration_s * sample_rate)
        chunk_size = samples_per_ms * 5
        audio = []
        for i in range(0, samples, chunk_size):
            t = i / samples
            freq = start_freq * ((end_freq / start_freq) ** t)
            voice.set_target_frequency(freq)
            n = min(chunk_size, samples - i)
            audio.append(voice.generate_audio(n))
        return np.concatenate(audio)

    print("\nAscending:")
    for i, note in enumerate(scale):
        freq = NOTES[note]
        voice.set_target_frequency(freq)

        state = voice.get_state()
        print(f"  {i+1}. {note:4s} ({freq:5.0f} Hz)  "
              f"I={state['motor_current']:5.1f}A  "
              f"T={state['t_junction']:4.1f}°C  "
              f"η={state['efficiency']*100:4.1f}%")

        all_audio.append(generate_segment(note_duration))

        if i < len(scale) - 1:
            next_freq = NOTES[scale[i + 1]]
            all_audio.append(glissando(freq, next_freq, gliss_duration))

    # Hold at top
    all_audio.append(generate_segment(1.0))

    print("\nDescending:")
    for i in range(len(scale) - 1, -1, -1):
        note = scale[i]
        freq = NOTES[note]
        voice.set_target_frequency(freq)

        state = voice.get_state()
        print(f"  {i+1}. {note:4s} ({freq:5.0f} Hz)  "
              f"I={state['motor_current']:5.1f}A  "
              f"T={state['t_junction']:4.1f}°C")

        all_audio.append(generate_segment(note_duration))

        if i > 0:
            next_freq = NOTES[scale[i - 1]]
            all_audio.append(glissando(freq, next_freq, gliss_duration))

    # Final hold
    all_audio.append(generate_segment(1.0))

    return np.concatenate(all_audio)


def main():
    use_cache = '--no-cache' not in sys.argv

    print("=" * 70)
    print("  AEROTONE CONCERT-SCALE DEMO")
    print("  500W Motor | 48V Bus | MOSFET H-Bridge | 400mm Propeller")
    print("=" * 70)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    print_specs()

    sample_rate = 44100

    # Check cache first
    audio = None
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            audio = np.load(CACHE_FILE)
            print("\n[Loaded from cache]")
        except:
            pass

    if audio is None:
        # Create concert voice
        print("Initializing concert voice...")
        voice = ConcertVoice(sample_rate=sample_rate)

        # Show component count
        components = voice.get_component_count()
        print(f"\nComponent count:")
        print(f"  Power amplifier:     {components['power_amp']} components")
        print(f"  PLL/Control:         {components['pll_control']} components")
        print(f"  Signal conditioning: {components['signal_conditioning']} components")
        print(f"  Total electronic:    {components['total_electronic']} components")

        # Spinup test
        voice = run_spinup_test(voice, 'A2')

        # Check for faults
        state = voice.get_state()
        if state['fault'] != 'NONE':
            print(f"\n⚠️  FAULT DETECTED: {state['fault']}")
            return

        print("\n" + "=" * 60)
        print("GENERATING SCALE...")
        print("=" * 60)

        # Generate scale
        audio = generate_scale(voice, sample_rate)

        # Normalize
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.8

        # Save to cache
        os.makedirs(CACHE_DIR, exist_ok=True)
        np.save(CACHE_FILE, audio)
        print("\n[Saved to cache]")

        # Final stats
        state = voice.get_state()
        print(f"\nFinal state:")
        print(f"  Motor temperature:   {state['t_junction']:.1f}°C")
        print(f"  Heatsink temp:       {state['t_heatsink']:.1f}°C")
        print(f"  Fan active:          {'Yes' if state['fan_on'] else 'No'}")
        print(f"  Power dissipation:   {state['power_dissipation']:.1f}W")

    print(f"\nGenerated {len(audio)/sample_rate:.1f}s of audio")

    # Play
    print("\n" + "=" * 60)
    print("PLAYBACK")
    print("=" * 60)
    print("\nPlaying concert-scale simulation...")
    print("(Same audio synthesis, but power stage is fully modeled)")

    sd.play(audio, sample_rate)
    sd.wait()

    print("\nDone!")
    print("""
The concert voice has the same musical behavior as the desktop version,
but includes full power electronics simulation:

  - MOSFET H-bridge switching at 20kHz
  - Current sensing and limiting
  - Thermal dynamics (junction → heatsink → ambient)
  - Overcurrent and overtemperature protection
  - Gate drivers with deadtime (shoot-through prevention)

In a real build, this would drive a 400mm propeller at ~100-105 dB,
suitable for concert halls or outdoor venues.
""")


if __name__ == '__main__':
    main()

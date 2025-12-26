#!/usr/bin/env python3
"""
FAULT TROUBLESHOOTER INTERFACE (Blind Side)

This is the ONLY interface the troubleshooter should use.
It provides probe access but NO visibility into what fault was injected.

Usage:
    python fault_challenge/troubleshoot.py <challenge_id>

The troubleshooter must diagnose the fault using only:
- Probe measurements
- Circuit knowledge
- Systematic reasoning
"""

import os
import sys
import json
import base64
import readline  # For better input handling

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench


class TroubleshootingSession:
    """
    Interactive troubleshooting session.

    Provides ONLY measurement capabilities - no access to fault details.
    """

    def __init__(self, challenge_id):
        self.challenge_id = challenge_id
        self.voice = None
        self.bench = None
        self.measurements = []
        self.diagnosis = None

        # Load the challenge (re-inject fault without revealing what it is)
        self._load_challenge()

    def _load_challenge(self):
        """Load challenge and inject fault WITHOUT revealing it"""

        answer_file = f'fault_challenge/answers/{self.challenge_id}.ans'
        if not os.path.exists(answer_file):
            print(f"Error: Challenge {self.challenge_id} not found")
            sys.exit(1)

        # Read the encoded answer to get fault_id (but don't print it!)
        with open(answer_file, 'r') as f:
            lines = f.readlines()
            encoded = lines[-1]

        answer_json = base64.b64decode(encoded.encode()).decode()
        answer = json.loads(answer_json)
        fault_id = answer['fault_id']

        # Create circuit with the fault
        params = SpiceVoiceParams(enable_thermal=False)
        self.voice = SpiceVoice(params=params, sample_rate=44100)

        # Import and inject (the troubleshooter shouldn't see this)
        from challenge_generator import inject_fault
        inject_fault(self.voice, fault_id)

        # Warm up
        self.voice.set_target_frequency(220.0)
        for _ in range(int(44100 * 0.5)):
            self.voice.update_physics(1/44100)

        self.bench = TestBench(self.voice)

        print(f"Challenge {self.challenge_id} loaded.")
        print("Circuit is running. A fault has been injected.")
        print("Use the probe commands to diagnose the problem.")
        print()

    def run_interactive(self):
        """Run interactive troubleshooting session"""

        print("=" * 60)
        print("  TROUBLESHOOTING SESSION")
        print("=" * 60)
        print("""
Available commands:
  probe <point>          - Read instantaneous value
  vdc <point>            - Measure DC voltage (averaged)
  vac <point>            - Measure AC voltage (RMS)
  freq <point>           - Measure frequency
  wave <point> [dur]     - Capture waveform (default 0.1s)
  list                   - List all probe points
  list <category>        - List probe points by category
  run <freq>             - Set target frequency and run
  history                - Show measurement history
  diagnose               - Submit your diagnosis
  hint                   - Get a hint (costs points!)
  help                   - Show this help
  quit                   - Exit session
""")

        while True:
            try:
                cmd = input("\nprobe> ").strip()
                if not cmd:
                    continue

                parts = cmd.split()
                action = parts[0].lower()

                if action == 'quit' or action == 'exit':
                    print("Exiting without diagnosis.")
                    break

                elif action == 'help':
                    self._show_help()

                elif action == 'list':
                    category = parts[1] if len(parts) > 1 else None
                    self._list_probes(category)

                elif action == 'probe':
                    if len(parts) < 2:
                        print("Usage: probe <point>")
                        continue
                    self._probe(parts[1])

                elif action == 'vdc':
                    if len(parts) < 2:
                        print("Usage: vdc <point>")
                        continue
                    self._measure_vdc(parts[1])

                elif action == 'vac':
                    if len(parts) < 2:
                        print("Usage: vac <point>")
                        continue
                    self._measure_vac(parts[1])

                elif action == 'freq':
                    if len(parts) < 2:
                        print("Usage: freq <point>")
                        continue
                    self._measure_freq(parts[1])

                elif action == 'wave':
                    if len(parts) < 2:
                        print("Usage: wave <point> [duration]")
                        continue
                    dur = float(parts[2]) if len(parts) > 2 else 0.1
                    self._capture_waveform(parts[1], dur)

                elif action == 'run':
                    if len(parts) < 2:
                        print("Usage: run <frequency>")
                        continue
                    self._run_at_frequency(float(parts[1]))

                elif action == 'history':
                    self._show_history()

                elif action == 'diagnose':
                    self._submit_diagnosis()
                    break

                elif action == 'hint':
                    self._get_hint()

                else:
                    print(f"Unknown command: {action}")
                    print("Type 'help' for available commands")

            except KeyboardInterrupt:
                print("\nUse 'quit' to exit")
            except Exception as e:
                print(f"Error: {e}")

    def _probe(self, point):
        """Read instantaneous probe value"""
        try:
            value = self.bench.probe(point)
            print(f"  {point}: {value:.4f}")
            self.measurements.append(('probe', point, value))
        except ValueError as e:
            print(f"  Error: {e}")

    def _measure_vdc(self, point):
        """Measure DC voltage"""
        try:
            m = self.bench.measure_vdc(point)
            print(f"  {point}: {m.value:.4f} VDC")
            self.measurements.append(('vdc', point, m.value))
        except Exception as e:
            print(f"  Error: {e}")

    def _measure_vac(self, point):
        """Measure AC voltage"""
        try:
            m = self.bench.measure_vac(point)
            print(f"  {point}: {m.value:.4f} VAC (RMS)")
            self.measurements.append(('vac', point, m.value))
        except Exception as e:
            print(f"  Error: {e}")

    def _measure_freq(self, point):
        """Measure frequency"""
        try:
            m = self.bench.measure_frequency(point)
            print(f"  {point}: {m.value:.2f} Hz")
            self.measurements.append(('freq', point, m.value))
        except Exception as e:
            print(f"  Error: {e}")

    def _capture_waveform(self, point, duration):
        """Capture and analyze waveform"""
        try:
            w = self.bench.capture_waveform(point, duration)
            print(f"  Waveform capture: {point}")
            print(f"    Duration: {w.duration*1000:.1f} ms")
            print(f"    Vmin: {w.v_min:.4f} V")
            print(f"    Vmax: {w.v_max:.4f} V")
            print(f"    Vpp:  {w.v_pp:.4f} V")
            print(f"    Vavg: {w.v_avg:.4f} V")
            print(f"    Vac RMS: {w.v_ac_rms:.4f} V")
            print(f"    Frequency: {w.frequency:.2f} Hz")
            print(f"    Duty cycle: {w.duty_cycle*100:.1f}%")
            self.measurements.append(('waveform', point, {
                'vpp': w.v_pp, 'vavg': w.v_avg, 'freq': w.frequency
            }))
        except Exception as e:
            print(f"  Error: {e}")

    def _run_at_frequency(self, freq):
        """Set target frequency and run for a bit"""
        print(f"  Setting target frequency to {freq} Hz...")
        self.voice.set_target_frequency(freq)
        for _ in range(int(44100 * 0.5)):
            self.voice.update_physics(1/44100)
        print(f"  Circuit running at target {freq} Hz")

        # Show some basic status
        rpm = self.voice.motor.omega * 60 / (2 * np.pi)
        bpf = rpm * self.voice.params.prop_num_blades / 60
        print(f"  Motor RPM: {rpm:.0f}")
        print(f"  Blade passage freq: {bpf:.1f} Hz")

    def _list_probes(self, category=None):
        """List available probe points"""
        points = self.bench.get_probe_points()

        categories = {
            'power': ['v_supply', 'v_logic', 'gnd'],
            'cd4046': [p for p in points if p.startswith('cd4046')],
            'pll': [p for p in points if 'vco' in p or 'phase' in p or 'sig_in' in p or 'comp_in' in p],
            'filter': [p for p in points if 'loop_filter' in p],
            'hbridge': [p for p in points if 'hbridge' in p or 'sense' in p],
            'motor': [p for p in points if p.startswith('motor') or p.startswith('driver')],
            'pickup': [p for p in points if 'pickup' in p],
            'conditioner': [p for p in points if 'cond' in p],
        }

        if category and category in categories:
            print(f"\n  {category.upper()} probe points:")
            for p in categories[category]:
                print(f"    {p}")
        elif category:
            # Search for matching points
            matches = [p for p in points if category.lower() in p.lower()]
            if matches:
                print(f"\n  Probe points matching '{category}':")
                for p in matches:
                    print(f"    {p}")
            else:
                print(f"  No probe points matching '{category}'")
        else:
            print(f"\n  Total probe points: {len(points)}")
            print("  Categories: power, cd4046, pll, filter, hbridge, motor, pickup, conditioner")
            print("  Use 'list <category>' to see points in a category")
            print("  Use 'list <keyword>' to search for specific points")

    def _show_history(self):
        """Show measurement history"""
        if not self.measurements:
            print("  No measurements taken yet.")
            return

        print("\n  Measurement History:")
        print("  " + "-" * 50)
        for i, (mtype, point, value) in enumerate(self.measurements, 1):
            if isinstance(value, dict):
                print(f"  {i}. [{mtype}] {point}: Vpp={value.get('vpp', 0):.3f}V, freq={value.get('freq', 0):.1f}Hz")
            else:
                print(f"  {i}. [{mtype}] {point}: {value:.4f}")

    def _show_help(self):
        """Show detailed help"""
        print("""
TROUBLESHOOTING GUIDE
=====================

SYSTEMATIC APPROACH:
1. Start with power supply - verify V_supply and V_logic
2. Check the PLL - VCO control, phase comparator outputs
3. Check loop filter - input vs output, ripple/noise
4. Check motor driver - control voltage, motor voltage, current
5. Check feedback path - pickup signal, conditioner output

EXPECTED VALUES (healthy circuit):
- V_supply: 12.0V
- V_logic: 15.0V
- Loop filter output: ~7.5V at 220Hz target
- Motor voltage: ~6V at 220Hz
- Motor RPM: ~1100 at 220Hz

COMMON FAULTS TO LOOK FOR:
- Capacitor: excessive ripple, voltage drift
- Transistor: low output voltage, asymmetric drive
- Op-amp: excessive noise, saturation, rail-to-rail clipping
- Resistor: open (infinite impedance) or short (zero impedance)
- Diode: open (no conduction) or short (always conducting)
- IC: degraded performance, limited range

COMMANDS:
- probe/vdc/vac/freq: Take measurements
- wave: Capture and analyze waveform (shows Vpp, frequency, etc.)
- run <freq>: Change operating frequency
- diagnose: Submit your diagnosis when ready
""")

    def _get_hint(self):
        """Provide a hint (for training purposes)"""
        print("""
  HINT: Focus on these key diagnostic points:

  1. loop_filter_cap_voltage - is it stable or drifting?
  2. motor_voltage vs motor_current - is the ratio normal?
  3. cond_opamp_out - is it within ±12V rails?
  4. Compare VDC and VAC readings - high AC on DC signals = noise

  (Using hints reduces your troubleshooting score)
""")

    def _submit_diagnosis(self):
        """Submit diagnosis and check answer"""
        print("\n" + "=" * 60)
        print("  SUBMIT DIAGNOSIS")
        print("=" * 60)
        print("""
Based on your measurements, what is the faulty component?

Examples:
- "Loop filter capacitor C1"
- "H-bridge transistor Q1"
- "Signal conditioner op-amp U2"
- "Feedback resistor R3"
""")
        diagnosis = input("\nYour diagnosis: ").strip()

        if not diagnosis:
            print("No diagnosis submitted.")
            return

        self.diagnosis = diagnosis

        # Verify answer
        from challenge_generator import verify_answer
        is_correct, answer = verify_answer(self.challenge_id, diagnosis)

        print("\n" + "=" * 60)
        if is_correct:
            print("  ✓ CORRECT!")
        else:
            print("  ✗ INCORRECT")
        print("=" * 60)

        print(f"\nYour diagnosis: {diagnosis}")
        print(f"Actual fault: {answer['fault_name']}")
        print(f"Component: {answer['component']}")
        print(f"\nDescription: {answer['description']}")
        print(f"\nExpected symptoms:")
        for s in answer['symptoms']:
            print(f"  - {s}")

        print(f"\nMeasurements taken: {len(self.measurements)}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python troubleshoot.py <challenge_id>")
        print("\nTo create a new challenge, run:")
        print("  python fault_challenge/challenge_generator.py")
        sys.exit(1)

    challenge_id = sys.argv[1]
    session = TroubleshootingSession(challenge_id)
    session.run_interactive()


if __name__ == '__main__':
    main()

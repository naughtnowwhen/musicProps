#!/usr/bin/env python3
"""
ISOLATED CHALLENGE SYSTEM

Stores answers OUTSIDE the project directory in a hidden location.
A Claude session started in the project folder won't find it.

Answer location: ~/.aerotone_faults/.{random_uuid}/
  - Outside project tree
  - Hidden with dot prefix
  - Random UUID name
  - Claude would have to explicitly know to look there

Usage:
    # CREATOR (knows where answers go)
    python isolated_challenge.py create

    # TROUBLESHOOTER (only gets token, can't find answer)
    python isolated_challenge.py probe <token>
"""

import os
import sys
import uuid
import json
import random
import hashlib
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench


# ============================================================
# ANSWER STORAGE - OUTSIDE PROJECT DIRECTORY
# ============================================================
# This is in the user's home directory, NOT in the project
# A Claude session in the project won't naturally explore here

HIDDEN_VAULT = Path.home() / '.aerotone_faults'


def _get_vault_path(token: str) -> Path:
    """
    Get the hidden vault path for a token.

    The path is derived via hash so even knowing the token
    doesn't directly reveal the folder name.
    """
    salt = "aerotone_isolated_v1"
    h = hashlib.sha256(f"{salt}:{token}".encode()).hexdigest()
    # Create an obscure folder name that looks like system junk
    folder_name = f".{h[:8]}_{h[8:12]}_cache"
    return HIDDEN_VAULT / folder_name


# ============================================================
# FAULT DEFINITIONS
# ============================================================

class FaultInjector:
    """Injects faults into voice circuits"""

    FAULTS = {
        'CAP_LEAK': {
            'name': 'Leaky Electrolytic Capacitor',
            'component': 'Loop Filter Capacitor (C1)',
            'hint': 'Check for voltage drift or excessive ripple on loop filter',
        },
        'TRANS_BURN': {
            'name': 'Burned H-Bridge Transistor',
            'component': 'H-Bridge Transistor (Q1)',
            'hint': 'Check motor voltage vs control voltage ratio',
        },
        'OPAMP_NOISE': {
            'name': 'Noisy/Damaged Op-Amp',
            'component': 'Signal Conditioner Op-Amp (U2)',
            'hint': 'Check for noise or rail exceedance on conditioner output',
        },
        'DIODE_SHORT': {
            'name': 'Shorted Flyback Diode',
            'component': 'H-Bridge Flyback Diode (D2)',
            'hint': 'Check motor current vs voltage relationship',
        },
        'RES_OPEN': {
            'name': 'Open Current Sense Resistor',
            'component': 'Sense Resistor (R5)',
            'hint': 'Check if current measurements are always zero',
        },
    }

    @classmethod
    def inject(cls, voice, fault_code):
        """Inject a specific fault"""
        if fault_code == 'CAP_LEAK':
            cls._inject_leaky_cap(voice)
        elif fault_code == 'TRANS_BURN':
            cls._inject_burned_trans(voice)
        elif fault_code == 'OPAMP_NOISE':
            cls._inject_noisy_opamp(voice)
        elif fault_code == 'DIODE_SHORT':
            cls._inject_shorted_diode(voice)
        elif fault_code == 'RES_OPEN':
            cls._inject_open_resistor(voice)

    @staticmethod
    def _inject_leaky_cap(voice):
        original = voice.loop_filter.update
        def faulty(input_voltage, dt, high_z=False):
            result = original(input_voltage, dt, high_z=high_z)
            mid = voice.params.vdd / 2
            leak = (voice.loop_filter.output_voltage - mid) * 0.12 * dt * 100
            voice.loop_filter.output_voltage -= leak
            voice.loop_filter.output_voltage += np.random.randn() * 0.02
            return voice.loop_filter.output_voltage
        voice.loop_filter.update = faulty

    @staticmethod
    def _inject_burned_trans(voice):
        original = voice.driver.update
        def faulty(dt, motor_back_emf=0.0):
            result = original(dt, motor_back_emf)
            if voice.driver.motor_voltage > 0:
                voice.driver.motor_voltage = max(0, voice.driver.motor_voltage - 2.5)
            return result
        voice.driver.update = faulty

    @staticmethod
    def _inject_noisy_opamp(voice):
        original = voice.conditioner.update
        drift = [0.0]
        def faulty(dt, input_voltage):
            original(dt, input_voltage)
            voice.conditioner.amplified_voltage += np.random.randn() * 0.6
            drift[0] += np.random.randn() * 0.003
            drift[0] = np.clip(drift[0], -1.5, 1.5)
            voice.conditioner.amplified_voltage += drift[0]
            if abs(voice.conditioner.amplified_voltage) > 11:
                voice.conditioner.amplified_voltage *= 1.12
        voice.conditioner.update = faulty

    @staticmethod
    def _inject_shorted_diode(voice):
        original = voice.driver.update
        def faulty(dt, motor_back_emf=0.0):
            result = original(dt, motor_back_emf)
            voice.driver.motor_voltage *= 0.58
            voice.driver.motor_current *= 1.55
            return result
        voice.driver.update = faulty

    @staticmethod
    def _inject_open_resistor(voice):
        original = voice.driver.update
        def faulty(dt, motor_back_emf=0.0):
            result = original(dt, motor_back_emf)
            voice.driver.motor_current = 0.0
            return result
        voice.driver.update = faulty


# ============================================================
# CHALLENGE CREATOR (Knows where answers are stored)
# ============================================================

def create_challenge(difficulty='medium') -> str:
    """
    Create a new challenge.

    Returns a token. The answer is stored OUTSIDE the project.
    """
    # Generate token (this is what troubleshooter gets)
    token = uuid.uuid4().hex[:12]

    # Select fault
    if difficulty == 'easy':
        codes = ['CAP_LEAK', 'TRANS_BURN', 'OPAMP_NOISE']
    else:
        codes = list(FaultInjector.FAULTS.keys())

    fault_code = random.choice(codes)
    fault_info = FaultInjector.FAULTS[fault_code]

    # Save answer in hidden vault OUTSIDE project
    vault_path = _get_vault_path(token)
    vault_path.mkdir(parents=True, exist_ok=True)

    answer = {
        'token': token,
        'fault_code': fault_code,
        'fault_name': fault_info['name'],
        'component': fault_info['component'],
        'created': datetime.now().isoformat(),
    }

    with open(vault_path / 'answer.json', 'w') as f:
        json.dump(answer, f)

    # Also save fault_code so prober can recreate
    with open(vault_path / 'fault_code', 'w') as f:
        f.write(fault_code)

    print("=" * 60)
    print("  CHALLENGE CREATED")
    print("=" * 60)
    print(f"  Token: {token}")
    print(f"  Difficulty: {difficulty}")
    print()
    print("  Answer stored OUTSIDE project directory at:")
    print(f"  {vault_path}")
    print()
    print("  The troubleshooter should NOT be told this location!")
    print("  They only get the token and must use probe commands.")
    print("=" * 60)

    return token


# ============================================================
# PROBE INTERFACE (What the blind troubleshooter uses)
# ============================================================

class IsolatedProbe:
    """
    Probe interface for blind troubleshooting.

    The troubleshooter creates this with a token.
    They can probe the circuit but cannot access the answer.
    """

    def __init__(self, token: str):
        self.token = token
        self._vault = _get_vault_path(token)

        if not self._vault.exists():
            raise ValueError(f"Challenge not found: {token}")

        # Load fault code and create circuit
        with open(self._vault / 'fault_code', 'r') as f:
            fault_code = f.read().strip()

        # Create faulty circuit
        params = SpiceVoiceParams(enable_thermal=False)
        self._voice = SpiceVoice(params=params, sample_rate=44100)
        FaultInjector.inject(self._voice, fault_code)

        # Warm up
        self._voice.set_target_frequency(220.0)
        for _ in range(int(44100 * 0.5)):
            self._voice.update_physics(1/44100)

        self._bench = TestBench(self._voice)
        self._log = []

    # === PROBE METHODS (All the troubleshooter can do) ===

    def probes(self, filter=None) -> list:
        """List available probe points"""
        points = self._bench.get_probe_points()
        if filter:
            points = [p for p in points if filter.lower() in p.lower()]
        return points

    def vdc(self, point: str) -> float:
        """Measure DC voltage"""
        m = self._bench.measure_vdc(point)
        self._log.append(f"vdc({point}) = {m.value:.4f}V")
        return round(m.value, 4)

    def vac(self, point: str) -> float:
        """Measure AC voltage RMS"""
        m = self._bench.measure_vac(point)
        self._log.append(f"vac({point}) = {m.value:.4f}V")
        return round(m.value, 4)

    def freq(self, point: str) -> float:
        """Measure frequency"""
        m = self._bench.measure_frequency(point)
        self._log.append(f"freq({point}) = {m.value:.2f}Hz")
        return round(m.value, 2)

    def wave(self, point: str, dur: float = 0.1) -> dict:
        """Capture waveform"""
        w = self._bench.capture_waveform(point, dur)
        result = {
            'vpp': round(w.v_pp, 4),
            'vavg': round(w.v_avg, 4),
            'vac_rms': round(w.v_ac_rms, 4),
            'freq': round(w.frequency, 2),
            'vmin': round(w.v_min, 4),
            'vmax': round(w.v_max, 4),
        }
        self._log.append(f"wave({point}) = Vpp:{result['vpp']}, freq:{result['freq']}Hz")
        return result

    def run(self, freq: float):
        """Set target frequency"""
        self._voice.set_target_frequency(freq)
        for _ in range(int(44100 * 0.3)):
            self._voice.update_physics(1/44100)
        rpm = self._voice.motor.omega * 60 / (2 * np.pi)
        print(f"  Running at {freq}Hz target, motor at {rpm:.0f} RPM")

    def status(self) -> dict:
        """Get circuit status"""
        rpm = self._voice.motor.omega * 60 / (2 * np.pi)
        return {
            'target_freq': self._voice.target_frequency,
            'motor_rpm': round(rpm, 1),
            'measurements': len(self._log),
        }

    def diagnose(self, answer: str) -> dict:
        """Submit diagnosis"""
        # Load actual answer
        with open(self._vault / 'answer.json', 'r') as f:
            actual = json.load(f)

        correct = (
            actual['component'].lower() in answer.lower() or
            actual['fault_name'].lower() in answer.lower() or
            actual['fault_code'].lower() in answer.lower()
        )

        return {
            'correct': correct,
            'your_answer': answer,
            'actual_fault': actual['fault_name'],
            'actual_component': actual['component'],
            'measurements_taken': len(self._log),
        }

    def show_log(self):
        """Show measurement log"""
        print(f"\n  Measurements taken ({len(self._log)}):")
        for entry in self._log:
            print(f"    {entry}")


# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Isolated Fault Challenge')
    parser.add_argument('command', choices=['create', 'probe', 'demo'])
    parser.add_argument('token', nargs='?', help='Challenge token (for probe)')
    parser.add_argument('--difficulty', default='medium', choices=['easy', 'medium', 'hard'])
    args = parser.parse_args()

    if args.command == 'create':
        create_challenge(args.difficulty)

    elif args.command == 'probe':
        if not args.token:
            print("Usage: isolated_challenge.py probe <token>")
            sys.exit(1)

        probe = IsolatedProbe(args.token)
        print(f"Loaded challenge: {args.token}")
        print(f"Probes available: {len(probe.probes())}")
        print("\nUse: probe.vdc('point'), probe.wave('point'), probe.diagnose('answer')")
        print("Example: probe.vdc('loop_filter_out')")

        # Drop into interactive mode
        import code
        code.interact(local={'probe': probe})

    elif args.command == 'demo':
        print("Creating challenge...")
        token = create_challenge('medium')
        print(f"\nNow troubleshoot with: python isolated_challenge.py probe {token}")


if __name__ == '__main__':
    main()

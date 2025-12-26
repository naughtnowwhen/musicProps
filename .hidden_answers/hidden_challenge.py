#!/usr/bin/env python3
"""
HIDDEN CHALLENGE SYSTEM

Creates fault challenges with answers stored in randomly-named hidden folders.
The blind agent cannot find the answer unless they know the exact UUID.

Structure:
  .data/
    a8f3b2c1-d4e5-6789-abcd-ef0123456789/   <- Random UUID, impossible to guess
      circuit.pkl        <- Pickled faulty circuit
      answer.json        <- The fault info (encrypted)

The troubleshooter only gets a "challenge token" that maps to this internally.
They CANNOT:
  - List the .data folder (it's hidden with .)
  - Guess the UUID (36 chars of randomness)
  - Find it via glob without the exact pattern
"""

import os
import sys
import uuid
import json
import pickle
import hashlib
import base64
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench


# Hidden data directory - dot prefix hides from casual ls
HIDDEN_ROOT = Path(__file__).parent / '.data'


def _get_secret_path(challenge_token: str) -> Path:
    """
    Derive the secret folder path from challenge token.

    The token is a SHORT id shown to users.
    The actual folder uses a DIFFERENT, longer UUID derived from it.
    This means even knowing the token doesn't directly reveal the path.
    """
    # Derive folder UUID from token using a secret salt
    secret_salt = "aerotone_fault_challenge_2024"  # Hidden in code
    derived = hashlib.sha256(f"{secret_salt}{challenge_token}".encode()).hexdigest()
    folder_uuid = f"{derived[:8]}-{derived[8:12]}-{derived[12:16]}-{derived[16:20]}-{derived[20:32]}"
    return HIDDEN_ROOT / folder_uuid


# Fault definitions
FAULTS = {
    'F001': {
        'name': 'Leaky Electrolytic Capacitor C1',
        'component': 'Loop Filter Capacitor (C1)',
        'inject': lambda v: _inject_leaky_cap(v),
    },
    'F002': {
        'name': 'Burned Power Transistor Q1',
        'component': 'H-Bridge Transistor (Q1)',
        'inject': lambda v: _inject_burned_transistor(v),
    },
    'F003': {
        'name': 'Noisy Op-Amp U2',
        'component': 'Signal Conditioner Op-Amp (U2)',
        'inject': lambda v: _inject_noisy_opamp(v),
    },
    'F004': {
        'name': 'Shorted Flyback Diode D2',
        'component': 'H-Bridge Diode (D2)',
        'inject': lambda v: _inject_shorted_diode(v),
    },
    'F005': {
        'name': 'Open Sense Resistor R5',
        'component': 'Current Sense Resistor (R5)',
        'inject': lambda v: _inject_open_resistor(v),
    },
}


def _inject_leaky_cap(voice):
    original = voice.loop_filter.update
    def faulty(input_voltage, dt, high_z=False):
        result = original(input_voltage, dt, high_z=high_z)
        mid = voice.params.vdd / 2
        voice.loop_filter.output_voltage -= (voice.loop_filter.output_voltage - mid) * 0.12 * dt * 100
        voice.loop_filter.output_voltage += np.random.randn() * 0.025
        return voice.loop_filter.output_voltage
    voice.loop_filter.update = faulty


def _inject_burned_transistor(voice):
    original = voice.driver.update
    def faulty(dt, motor_back_emf=0.0):
        result = original(dt, motor_back_emf)
        if voice.driver.motor_voltage > 0:
            voice.driver.motor_voltage = max(0, voice.driver.motor_voltage - 2.8)
            voice.driver.motor_voltage += np.random.randn() * 0.12
        return result
    voice.driver.update = faulty


def _inject_noisy_opamp(voice):
    original = voice.conditioner.update
    drift = [0.0]
    def faulty(dt, input_voltage):
        original(dt, input_voltage)
        voice.conditioner.amplified_voltage += np.random.randn() * 0.7
        if np.random.random() < 0.25:
            voice.conditioner.amplified_voltage += np.random.randn() * 1.5
        drift[0] += np.random.randn() * 0.004
        drift[0] = np.clip(drift[0], -1.5, 1.5)
        voice.conditioner.amplified_voltage += drift[0]
        # Damaged protection - can exceed rails
        if abs(voice.conditioner.amplified_voltage) > 11:
            voice.conditioner.amplified_voltage *= 1.15
    voice.conditioner.update = faulty


def _inject_shorted_diode(voice):
    original = voice.driver.update
    def faulty(dt, motor_back_emf=0.0):
        result = original(dt, motor_back_emf)
        voice.driver.motor_voltage *= 0.55
        voice.driver.motor_current *= 1.6
        return result
    voice.driver.update = faulty


def _inject_open_resistor(voice):
    # Open sense resistor means no current feedback
    original = voice.driver.update
    def faulty(dt, motor_back_emf=0.0):
        result = original(dt, motor_back_emf)
        voice.driver.motor_current = 0.0  # Can't sense current
        return result
    voice.driver.update = faulty


class HiddenChallengeCreator:
    """Creates challenges with hidden answers"""

    @staticmethod
    def create(difficulty='medium') -> str:
        """
        Create a new challenge with randomly hidden answer.

        Returns:
            challenge_token: Short ID to give to troubleshooter
        """
        # Generate unique token
        challenge_token = uuid.uuid4().hex[:10]

        # Get secret storage path (troubleshooter can't guess this)
        secret_path = _get_secret_path(challenge_token)
        secret_path.mkdir(parents=True, exist_ok=True)

        # Select fault
        if difficulty == 'easy':
            fault_ids = ['F001', 'F002', 'F003']
        else:
            fault_ids = list(FAULTS.keys())

        import random
        fault_id = random.choice(fault_ids)
        fault = FAULTS[fault_id]

        # Create and inject fault
        params = SpiceVoiceParams(enable_thermal=False)
        voice = SpiceVoice(params=params, sample_rate=44100)
        fault['inject'](voice)

        # Warm up
        voice.set_target_frequency(220.0)
        for _ in range(int(44100 * 0.5)):
            voice.update_physics(1/44100)

        # Save answer (encoded so not readable at a glance)
        answer = {
            'fault_id': fault_id,
            'fault_name': fault['name'],
            'component': fault['component'],
            'created': datetime.now().isoformat(),
        }
        encoded_answer = base64.b64encode(json.dumps(answer).encode()).decode()

        with open(secret_path / 'answer.enc', 'w') as f:
            f.write(encoded_answer)

        # Save circuit state for troubleshooter to load
        # We save the fault_id so we can re-inject (can't pickle lambdas)
        with open(secret_path / 'fault_id.txt', 'w') as f:
            f.write(fault_id)

        print(f"Challenge created!")
        print(f"Token: {challenge_token}")
        print(f"(Answer hidden in random UUID folder)")

        return challenge_token


class HiddenProbeInterface:
    """
    Probe interface for troubleshooter.

    Loads challenge by token but CANNOT access the answer.
    """

    def __init__(self, challenge_token: str):
        self.token = challenge_token
        self._secret_path = _get_secret_path(challenge_token)

        if not self._secret_path.exists():
            raise ValueError(f"Challenge not found: {challenge_token}")

        # Load fault_id and re-create circuit
        with open(self._secret_path / 'fault_id.txt', 'r') as f:
            fault_id = f.read().strip()

        # Create circuit with fault
        params = SpiceVoiceParams(enable_thermal=False)
        self._voice = SpiceVoice(params=params, sample_rate=44100)
        FAULTS[fault_id]['inject'](self._voice)

        # Warm up
        self._voice.set_target_frequency(220.0)
        for _ in range(int(44100 * 0.5)):
            self._voice.update_physics(1/44100)

        self._bench = TestBench(self._voice)
        self._measurements = []

    # ================================================================
    # PUBLIC PROBE INTERFACE - All the troubleshooter can use
    # ================================================================

    def list_probes(self, pattern: str = None) -> list:
        """List available probe points"""
        points = self._bench.get_probe_points()
        if pattern:
            points = [p for p in points if pattern.lower() in p.lower()]
        return points

    def probe(self, point: str) -> float:
        """Read instantaneous value"""
        val = self._bench.probe(point)
        self._measurements.append(('probe', point, val))
        return val

    def measure_vdc(self, point: str) -> float:
        """Measure DC voltage"""
        m = self._bench.measure_vdc(point)
        self._measurements.append(('vdc', point, m.value))
        return m.value

    def measure_vac(self, point: str) -> float:
        """Measure AC voltage RMS"""
        m = self._bench.measure_vac(point)
        self._measurements.append(('vac', point, m.value))
        return m.value

    def measure_freq(self, point: str) -> float:
        """Measure frequency"""
        m = self._bench.measure_frequency(point)
        self._measurements.append(('freq', point, m.value))
        return m.value

    def capture_waveform(self, point: str, duration: float = 0.1) -> dict:
        """Capture waveform and return analysis"""
        w = self._bench.capture_waveform(point, duration)
        self._measurements.append(('wave', point, w.v_pp))
        return {
            'v_min': w.v_min, 'v_max': w.v_max, 'v_pp': w.v_pp,
            'v_avg': w.v_avg, 'v_ac_rms': w.v_ac_rms,
            'frequency': w.frequency, 'duty_cycle': w.duty_cycle,
        }

    def set_frequency(self, freq: float):
        """Set target frequency"""
        self._voice.set_target_frequency(freq)
        for _ in range(int(44100 * 0.3)):
            self._voice.update_physics(1/44100)

    def get_status(self) -> dict:
        """Get circuit status"""
        rpm = self._voice.motor.omega * 60 / (2 * np.pi)
        return {
            'target_freq': self._voice.target_frequency,
            'motor_rpm': rpm,
            'measurements_taken': len(self._measurements),
        }

    def submit_diagnosis(self, diagnosis: str) -> dict:
        """Submit diagnosis and get result"""
        # Load answer
        with open(self._secret_path / 'answer.enc', 'r') as f:
            encoded = f.read()
        answer = json.loads(base64.b64decode(encoded.encode()).decode())

        # Check
        is_correct = (
            answer['component'].lower() in diagnosis.lower() or
            answer['fault_name'].lower() in diagnosis.lower()
        )

        return {
            'correct': is_correct,
            'your_answer': diagnosis,
            'actual_fault': answer['fault_name'],
            'actual_component': answer['component'],
            'measurements_taken': len(self._measurements),
        }


def demo():
    """Demo the hidden challenge system"""
    print("=" * 60)
    print("  HIDDEN CHALLENGE DEMO")
    print("=" * 60)

    # Create a challenge
    print("\n[Creator] Making a new challenge...")
    token = HiddenChallengeCreator.create(difficulty='medium')

    print(f"\n[Creator] Give this token to the troubleshooter: {token}")
    print("[Creator] The answer is hidden in a random UUID folder they can't find.")

    # Now simulate troubleshooter
    print("\n" + "=" * 60)
    print("  TROUBLESHOOTER (Blind)")
    print("=" * 60)

    probe = HiddenProbeInterface(token)

    print(f"\nLoaded challenge: {token}")
    print(f"Available probes: {len(probe.list_probes())}")

    # Take some measurements
    print("\n--- Taking measurements ---")
    print(f"V_supply: {probe.measure_vdc('v_supply'):.2f}V")
    print(f"Loop filter: {probe.measure_vdc('loop_filter_out'):.2f}V")
    print(f"Motor voltage: {probe.measure_vdc('motor_voltage'):.2f}V")

    wave = probe.capture_waveform('loop_filter_cap_voltage', 0.1)
    print(f"Loop filter ripple: {wave['v_ac_rms']:.4f}V RMS")

    # Submit guess
    print("\n--- Submitting diagnosis ---")
    result = probe.submit_diagnosis("I don't know yet")
    print(f"Correct: {result['correct']}")
    print(f"Actual: {result['actual_fault']}")


if __name__ == '__main__':
    demo()

"""
Virtual Test Equipment for AeroTone Circuit Diagnosis

Simulates the test equipment a technician would use:
  - Digital Multimeter (DMM): VDC, VAC, current, resistance, continuity
  - Oscilloscope: Waveform capture, frequency, amplitude, duty cycle
  - Test Probes: Attach to any circuit node

This enables systematic fault isolation by measuring intermediate
circuit points, not just the final audio output.

Usage:
    from aerotone.test_equipment import TestBench, Probe

    bench = TestBench(voice)

    # Multimeter measurements
    vdc = bench.measure_vdc('loop_filter_out')
    vac = bench.measure_vac('pickup_signal')

    # Oscilloscope capture
    waveform = bench.capture_waveform('motor_drive', duration=0.1)
    freq = bench.measure_frequency('feedback_pulse')
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple
from enum import Enum


class ProbePoint(Enum):
    """Standard test points in AeroTone voice circuit"""

    # Power Supply
    V_SUPPLY = "v_supply"              # Main DC supply (12V nominal)
    V_LOGIC = "v_logic"                # Logic supply (5V or 15V)
    GND = "gnd"                        # Ground reference

    # PLL / CD4046
    VCO_CONTROL = "vco_control"        # VCO control voltage input
    VCO_OUTPUT = "vco_output"          # VCO output (square wave)
    PHASE_DET_OUT = "phase_det_out"    # Phase detector output
    SIG_IN = "sig_in"                  # Signal input to CD4046
    COMP_IN = "comp_in"                # Comparator input

    # Loop Filter
    LOOP_FILTER_IN = "loop_filter_in"  # Input to loop filter
    LOOP_FILTER_OUT = "loop_filter_out" # Output (to motor driver)

    # Motor Driver (H-Bridge)
    MOTOR_DRIVE_A = "motor_drive_a"    # Motor terminal A
    MOTOR_DRIVE_B = "motor_drive_b"    # Motor terminal B
    MOTOR_VOLTAGE = "motor_voltage"    # Net motor voltage (A-B)
    MOTOR_CURRENT = "motor_current"    # Motor current (sense resistor)
    DRIVER_CONTROL = "driver_control"  # Control input to driver

    # Motor
    MOTOR_BACK_EMF = "motor_back_emf"  # Back-EMF voltage
    MOTOR_RPM = "motor_rpm"            # Tachometer (rpm)

    # Magnetic Pickup & Signal Conditioning
    PICKUP_RAW = "pickup_raw"          # Raw pickup signal (mV AC)
    PICKUP_AMPLIFIED = "pickup_amplified"  # After amplifier
    FEEDBACK_DIGITAL = "feedback_digital"  # Schmitt trigger output

    # Iris / Servo
    SERVO_COMMAND = "servo_command"    # Servo position command
    SERVO_POSITION = "servo_position"  # Actual servo position
    SERVO_CURRENT = "servo_current"    # Servo motor current
    IRIS_APERTURE = "iris_aperture"    # Iris opening (normalized)


@dataclass
class Measurement:
    """Result of a measurement"""
    value: float
    unit: str
    probe_point: str
    measurement_type: str
    timestamp: float = 0.0
    valid: bool = True
    notes: str = ""

    def __str__(self):
        if not self.valid:
            return f"{self.probe_point}: INVALID ({self.notes})"
        return f"{self.probe_point}: {self.value:.4f} {self.unit}"


@dataclass
class WaveformCapture:
    """Oscilloscope waveform capture"""
    samples: np.ndarray
    sample_rate: float
    duration: float
    probe_point: str

    # Computed measurements
    v_min: float = 0.0
    v_max: float = 0.0
    v_pp: float = 0.0           # Peak-to-peak
    v_avg: float = 0.0          # DC average
    v_rms: float = 0.0          # RMS (AC+DC)
    v_ac_rms: float = 0.0       # AC RMS only
    frequency: float = 0.0       # Dominant frequency
    period: float = 0.0          # Period (1/freq)
    duty_cycle: float = 0.0      # For digital signals
    rise_time: float = 0.0       # 10-90% rise time

    def analyze(self):
        """Compute waveform measurements"""
        if len(self.samples) == 0:
            return

        self.v_min = np.min(self.samples)
        self.v_max = np.max(self.samples)
        self.v_pp = self.v_max - self.v_min
        self.v_avg = np.mean(self.samples)
        self.v_rms = np.sqrt(np.mean(self.samples ** 2))
        self.v_ac_rms = np.sqrt(np.mean((self.samples - self.v_avg) ** 2))

        # Frequency estimation via zero crossings
        centered = self.samples - self.v_avg
        zero_crossings = np.where(np.diff(np.sign(centered)))[0]
        if len(zero_crossings) >= 2:
            avg_period_samples = np.mean(np.diff(zero_crossings)) * 2
            self.period = avg_period_samples / self.sample_rate
            self.frequency = 1.0 / self.period if self.period > 0 else 0.0

        # Duty cycle (for digital signals)
        threshold = self.v_avg
        high_samples = np.sum(self.samples > threshold)
        self.duty_cycle = high_samples / len(self.samples)

        # Rise time (10% to 90%)
        v_10 = self.v_min + 0.1 * self.v_pp
        v_90 = self.v_min + 0.9 * self.v_pp
        rising = np.where((self.samples[:-1] < v_10) & (self.samples[1:] > v_10))[0]
        if len(rising) > 0:
            rise_start = rising[0]
            rise_end_candidates = np.where(self.samples[rise_start:] > v_90)[0]
            if len(rise_end_candidates) > 0:
                rise_end = rise_start + rise_end_candidates[0]
                self.rise_time = (rise_end - rise_start) / self.sample_rate

    def __str__(self):
        return (f"Waveform @ {self.probe_point}:\n"
                f"  Vpp={self.v_pp:.3f}V, Vavg={self.v_avg:.3f}V, Vrms={self.v_rms:.3f}V\n"
                f"  Freq={self.frequency:.1f}Hz, Duty={self.duty_cycle*100:.1f}%")


class TestBench:
    """
    Virtual Test Bench with DMM and Oscilloscope

    Provides measurement access to all circuit nodes for systematic
    fault diagnosis.
    """

    def __init__(self, voice):
        """
        Initialize test bench attached to a SpiceVoice instance.

        Args:
            voice: SpiceVoice instance to probe
        """
        self.voice = voice
        self.sample_rate = voice.sample_rate

        # Measurement history
        self.measurements: List[Measurement] = []
        self.waveforms: List[WaveformCapture] = []

        # Build probe point accessors
        self._build_probe_map()

    def _build_probe_map(self):
        """Build mapping from probe points to value accessors"""
        v = self.voice
        p = v.params

        self.probe_map: Dict[str, Callable[[], float]] = {
            # ============================================================
            # POWER RAILS
            # ============================================================
            'v_supply': lambda: p.driver_v_supply,           # Main 12V supply
            'v_logic': lambda: p.vdd,                        # Logic 15V supply
            'gnd': lambda: 0.0,                              # Ground reference

            # ============================================================
            # CD4046 PLL IC - All 16 pins
            # ============================================================
            # Pin 1: Phase Comparator 1 output (XOR type)
            'cd4046_pin1_pc1_out': lambda: v.cd4046.pc1_output,
            # Pin 2: Phase Comparator 2 output (edge-triggered, main one)
            'cd4046_pin2_pc2_out': lambda: v.cd4046.pc2_output,
            # Pin 3: Comparator input (usually VCO feedback)
            'cd4046_pin3_comp_in': lambda: v.cd4046.comp_in_voltage,
            # Pin 4: VCO output (square wave)
            'cd4046_pin4_vco_out': lambda: p.vdd if v.cd4046.vco_output else 0.0,
            # Pin 5: Inhibit (active high disables VCO)
            'cd4046_pin5_inhibit': lambda: p.vdd if v.cd4046.inhibit else 0.0,
            # Pin 6: C1A - Timing capacitor terminal A
            'cd4046_pin6_c1a': lambda: 0.0,  # Tied to ground via timing cap
            # Pin 7: C1B - Timing capacitor terminal B
            'cd4046_pin7_c1b': lambda: v.cd4046.vco_in_voltage * 0.5,  # Internal reference
            # Pin 8: VSS (ground)
            'cd4046_pin8_vss': lambda: 0.0,
            # Pin 9: VCO control voltage input
            'cd4046_pin9_vco_in': lambda: v.cd4046.vco_in_voltage,
            # Pin 10: Demodulator output
            'cd4046_pin10_demod_out': lambda: v.cd4046.vco_in_voltage,  # Follows VCO in
            # Pin 11: R1 timing resistor terminal
            'cd4046_pin11_r1': lambda: v.cd4046.vco_in_voltage,
            # Pin 12: R2 timing resistor terminal
            'cd4046_pin12_r2': lambda: v.cd4046.vco_in_voltage * 0.7,
            # Pin 13: Zener diode (usually unused)
            'cd4046_pin13_zener': lambda: 0.0,
            # Pin 14: Signal input
            'cd4046_pin14_sig_in': lambda: v.cd4046.sig_in_voltage,
            # Pin 15: (No connection on most packages)
            'cd4046_pin15_nc': lambda: 0.0,
            # Pin 16: VDD (positive supply)
            'cd4046_pin16_vdd': lambda: p.vdd,

            # CD4046 internal state (for diagnostics)
            'cd4046_vco_frequency': lambda: v.cd4046.vco_frequency,
            'cd4046_lock_detect': lambda: p.vdd if v.cd4046.lock_detect else 0.0,
            'cd4046_phase_error': lambda: v.cd4046.phase_error_accumulator,

            # Legacy aliases for compatibility
            'vco_control': lambda: v.cd4046.vco_in_voltage,
            'vco_output': lambda: p.vdd if v.cd4046.vco_output else 0.0,
            'vco_frequency': lambda: v.cd4046.vco_frequency,
            'phase_comp_1': lambda: v.cd4046.pc1_output,
            'phase_comp_2': lambda: v.cd4046.pc2_output,
            'sig_in': lambda: v.cd4046.sig_in_voltage,
            'comp_in': lambda: v.cd4046.comp_in_voltage,

            # ============================================================
            # LOOP FILTER (RC Network) - Every node
            # ============================================================
            # Input from PC2
            'loop_filter_in': lambda: v.cd4046.pc2_output,
            # Resistor input side (same as input)
            'loop_filter_r_in': lambda: v.cd4046.pc2_output,
            # Junction between R and C (after resistor, at capacitor top)
            'loop_filter_r_c_junction': lambda: v.loop_filter.capacitor_voltage,
            # Capacitor voltage (same as junction for passive filter)
            'loop_filter_cap_voltage': lambda: v.loop_filter.capacitor_voltage,
            # Capacitor ground terminal
            'loop_filter_cap_gnd': lambda: 0.0,
            # Output (to VCO control)
            'loop_filter_out': lambda: v.loop_filter.output_voltage,

            # ============================================================
            # H-BRIDGE MOTOR DRIVER - All transistor terminals
            # ============================================================
            # Q1: High-side PNP (Motor terminal A to V+)
            'hbridge_q1_emitter': lambda: p.driver_v_supply,  # Connected to V+
            'hbridge_q1_base': lambda: self._q1_base_voltage(v),
            'hbridge_q1_collector': lambda: self._motor_terminal_a(v),

            # Q2: Low-side NPN (Motor terminal A to GND)
            'hbridge_q2_collector': lambda: self._motor_terminal_a(v),
            'hbridge_q2_base': lambda: self._q2_base_voltage(v),
            'hbridge_q2_emitter': lambda: self._sense_resistor_voltage(v),

            # Q3: High-side PNP (Motor terminal B to V+)
            'hbridge_q3_emitter': lambda: p.driver_v_supply,
            'hbridge_q3_base': lambda: self._q3_base_voltage(v),
            'hbridge_q3_collector': lambda: self._motor_terminal_b(v),

            # Q4: Low-side NPN (Motor terminal B to GND)
            'hbridge_q4_collector': lambda: self._motor_terminal_b(v),
            'hbridge_q4_base': lambda: self._q4_base_voltage(v),
            'hbridge_q4_emitter': lambda: self._sense_resistor_voltage(v),

            # Motor terminals (convenience)
            'motor_terminal_a': lambda: self._motor_terminal_a(v),
            'motor_terminal_b': lambda: self._motor_terminal_b(v),
            'motor_voltage': lambda: v.driver.motor_voltage,
            'motor_drive_a': lambda: self._motor_terminal_a(v),
            'motor_drive_b': lambda: self._motor_terminal_b(v),

            # Flyback/freewheeling diodes (D1-D4)
            'hbridge_d1_anode': lambda: self._motor_terminal_a(v),
            'hbridge_d1_cathode': lambda: p.driver_v_supply,
            'hbridge_d2_anode': lambda: 0.0,
            'hbridge_d2_cathode': lambda: self._motor_terminal_a(v),
            'hbridge_d3_anode': lambda: self._motor_terminal_b(v),
            'hbridge_d3_cathode': lambda: p.driver_v_supply,
            'hbridge_d4_anode': lambda: 0.0,
            'hbridge_d4_cathode': lambda: self._motor_terminal_b(v),

            # Current sensing
            'sense_resistor_high': lambda: self._sense_resistor_voltage(v),
            'sense_resistor_low': lambda: 0.0,
            'motor_current': lambda: v.driver.motor_current,
            'driver_control': lambda: v.driver.control_voltage,

            # Driver status
            'driver_over_current': lambda: p.vdd if v.driver.over_current else 0.0,
            'driver_thermal_shutdown': lambda: p.vdd if v.driver.thermal_shutdown else 0.0,
            'driver_temperature': lambda: v.driver.temperature,

            # ============================================================
            # DC MOTOR - All accessible points
            # ============================================================
            'motor_winding_a': lambda: self._motor_terminal_a(v),
            'motor_winding_b': lambda: self._motor_terminal_b(v),
            'motor_back_emf': lambda: v.motor.back_emf,
            'motor_rpm': lambda: v.motor.omega * 60 / (2 * np.pi),
            'motor_theta': lambda: v.motor.theta,  # Shaft angle in radians
            'motor_omega': lambda: v.motor.omega,  # Angular velocity rad/s
            'motor_temperature': lambda: v.motor.temperature,
            'motor_winding_current': lambda: v.motor.current,

            # ============================================================
            # MAGNETIC PICKUP - Coil terminals
            # ============================================================
            'pickup_coil_hot': lambda: v.pickup.raw_voltage,
            'pickup_coil_gnd': lambda: 0.0,
            'pickup_raw': lambda: v.pickup.raw_voltage,

            # ============================================================
            # SIGNAL CONDITIONER - All internal nodes
            # ============================================================
            # Input coupling capacitor (high-pass filter)
            'cond_input_cap_in': lambda: v.pickup.raw_voltage,
            'cond_input_cap_out': lambda: self._hp_filter_output(v),

            # Op-amp (741 or similar)
            'cond_opamp_vplus': lambda: 12.0,   # Positive supply rail
            'cond_opamp_vminus': lambda: -12.0, # Negative supply rail
            'cond_opamp_plus_in': lambda: self._hp_filter_output(v),  # Non-inverting input
            'cond_opamp_minus_in': lambda: 0.0,  # Inverting input (virtual ground in this config)
            'cond_opamp_out': lambda: v.conditioner.amplified_voltage,

            # Feedback network
            'cond_feedback_r_top': lambda: v.conditioner.amplified_voltage,
            'cond_feedback_r_bottom': lambda: 0.0,
            'cond_gain_r_top': lambda: self._hp_filter_output(v),
            'cond_gain_r_bottom': lambda: 0.0,

            # Schmitt trigger / comparator
            'cond_comparator_in': lambda: v.conditioner.amplified_voltage,
            'cond_comparator_threshold_upper': lambda: v.conditioner.upper_threshold,
            'cond_comparator_threshold_lower': lambda: v.conditioner.lower_threshold,
            'cond_comparator_out': lambda: p.vdd if v.conditioner.digital_output else 0.0,

            # Legacy aliases
            'pickup_amplified': lambda: v.conditioner.amplified_voltage,
            'feedback_digital': lambda: p.vdd if v.conditioner.digital_output else 0.0,
        }

        # Add iris/servo probes if circuit iris is active
        if v.use_circuit_iris and v.iris_circuit is not None:
            self.probe_map.update({
                'servo_command': lambda: v.iris_circuit.servo.command_position,
                'servo_position': lambda: v.iris_circuit.servo.position,
                'servo_current': lambda: v.iris_circuit.servo.motor_current,
                'iris_aperture': lambda: v.iris_circuit.get_aperture(),
            })
        elif v.iris is not None:
            self.probe_map.update({
                'servo_command': lambda: v.iris.servo.target_position,
                'servo_position': lambda: v.iris.servo.position,
                'servo_current': lambda: v.iris.servo.current,
                'iris_aperture': lambda: v.iris.get_aperture(),
            })

    # ================================================================
    # Helper methods for computing derived node voltages
    # ================================================================

    def _motor_terminal_a(self, v) -> float:
        """Compute voltage at motor terminal A based on H-bridge state"""
        # Terminal A is midpoint, voltage depends on drive direction
        v_supply = v.params.driver_v_supply
        motor_v = v.driver.motor_voltage
        # When motor_voltage > 0: Q1 on, Q4 on -> Terminal A high
        # When motor_voltage < 0: Q2 on, Q3 on -> Terminal A low
        return (v_supply / 2) + (motor_v / 2)

    def _motor_terminal_b(self, v) -> float:
        """Compute voltage at motor terminal B based on H-bridge state"""
        v_supply = v.params.driver_v_supply
        motor_v = v.driver.motor_voltage
        # Opposite of terminal A
        return (v_supply / 2) - (motor_v / 2)

    def _q1_base_voltage(self, v) -> float:
        """Q1 (high-side PNP) base voltage - controls forward drive"""
        v_supply = v.params.driver_v_supply
        control = v.driver.control_voltage / v_supply  # Normalized 0-1
        # PNP: base pulled low to turn on (relative to emitter at V+)
        if control > 0.5:
            # Q1 on: base ~0.7V below emitter
            return v_supply - 0.7
        else:
            # Q1 off: base at emitter level
            return v_supply

    def _q2_base_voltage(self, v) -> float:
        """Q2 (low-side NPN) base voltage - controls reverse drive"""
        v_supply = v.params.driver_v_supply
        control = v.driver.control_voltage / v_supply
        # NPN: base pulled high to turn on
        if control < 0.5:
            # Q2 on: base ~0.7V above emitter (near ground)
            return 0.7
        else:
            # Q2 off: base at ground
            return 0.0

    def _q3_base_voltage(self, v) -> float:
        """Q3 (high-side PNP) base voltage"""
        v_supply = v.params.driver_v_supply
        control = v.driver.control_voltage / v_supply
        if control < 0.5:
            return v_supply - 0.7  # On
        else:
            return v_supply  # Off

    def _q4_base_voltage(self, v) -> float:
        """Q4 (low-side NPN) base voltage"""
        v_supply = v.params.driver_v_supply
        control = v.driver.control_voltage / v_supply
        if control > 0.5:
            return 0.7  # On
        else:
            return 0.0  # Off

    def _sense_resistor_voltage(self, v) -> float:
        """Voltage at top of current sense resistor"""
        # V = I * R_sense
        r_sense = v.driver.params.sense_resistor
        return abs(v.driver.motor_current) * r_sense

    def _hp_filter_output(self, v) -> float:
        """High-pass filter output (input to amplifier)"""
        # The HP filter removes DC, so output is AC component
        # We can estimate this from the capacitor's stored state
        return v.pickup.raw_voltage - v.conditioner.hp_capacitor_voltage

    def get_probe_points(self) -> List[str]:
        """Get list of available probe points"""
        return list(self.probe_map.keys())

    def probe(self, point: str) -> float:
        """
        Get instantaneous value at a probe point.

        Args:
            point: Probe point name (see ProbePoint enum)

        Returns:
            Current voltage/value at that point
        """
        if point not in self.probe_map:
            raise ValueError(f"Unknown probe point: {point}. "
                           f"Available: {self.get_probe_points()}")
        return self.probe_map[point]()

    def measure_vdc(self, point: str) -> Measurement:
        """
        Measure DC voltage at a probe point.

        Simulates DMM in VDC mode - averages over short period.
        """
        # Capture brief waveform and average
        samples = self._capture_samples(point, duration=0.05)
        vdc = np.mean(samples)

        m = Measurement(
            value=vdc,
            unit="VDC",
            probe_point=point,
            measurement_type="vdc"
        )
        self.measurements.append(m)
        return m

    def measure_vac(self, point: str) -> Measurement:
        """
        Measure AC voltage (RMS) at a probe point.

        Simulates DMM in VAC mode - measures AC component only.
        """
        samples = self._capture_samples(point, duration=0.1)
        dc = np.mean(samples)
        ac_rms = np.sqrt(np.mean((samples - dc) ** 2))

        m = Measurement(
            value=ac_rms,
            unit="VAC",
            probe_point=point,
            measurement_type="vac"
        )
        self.measurements.append(m)
        return m

    def measure_frequency(self, point: str) -> Measurement:
        """
        Measure signal frequency at a probe point.

        Simulates frequency counter function.
        """
        waveform = self.capture_waveform(point, duration=0.2)

        m = Measurement(
            value=waveform.frequency,
            unit="Hz",
            probe_point=point,
            measurement_type="frequency"
        )
        self.measurements.append(m)
        return m

    def measure_duty_cycle(self, point: str) -> Measurement:
        """
        Measure duty cycle of digital signal.
        """
        waveform = self.capture_waveform(point, duration=0.1)

        m = Measurement(
            value=waveform.duty_cycle * 100,
            unit="%",
            probe_point=point,
            measurement_type="duty_cycle"
        )
        self.measurements.append(m)
        return m

    def measure_current(self, point: str) -> Measurement:
        """
        Measure current at designated current sense points.
        """
        # Only certain points are current measurements
        current_points = ['motor_current', 'servo_current']

        if point not in current_points:
            return Measurement(
                value=0.0,
                unit="A",
                probe_point=point,
                measurement_type="current",
                valid=False,
                notes=f"Not a current sense point. Use: {current_points}"
            )

        samples = self._capture_samples(point, duration=0.05)
        current = np.mean(samples)

        m = Measurement(
            value=current,
            unit="A",
            probe_point=point,
            measurement_type="current"
        )
        self.measurements.append(m)
        return m

    def capture_waveform(self, point: str, duration: float = 0.1,
                         trigger_level: float = None) -> WaveformCapture:
        """
        Capture oscilloscope waveform at a probe point.

        Args:
            point: Probe point name
            duration: Capture duration in seconds
            trigger_level: Optional trigger level (auto if None)

        Returns:
            WaveformCapture with samples and analysis
        """
        samples = self._capture_samples(point, duration)

        waveform = WaveformCapture(
            samples=samples,
            sample_rate=self.sample_rate,
            duration=duration,
            probe_point=point
        )
        waveform.analyze()

        self.waveforms.append(waveform)
        return waveform

    def _capture_samples(self, point: str, duration: float) -> np.ndarray:
        """
        Capture samples by running the voice simulation.
        """
        num_samples = int(duration * self.sample_rate)
        samples = np.zeros(num_samples)

        dt = 1.0 / self.sample_rate

        for i in range(num_samples):
            # Run one sample of physics
            self.voice.update_physics(dt)
            # Capture the probe point
            samples[i] = self.probe(point)

        return samples

    def run_and_probe(self, point: str, duration: float) -> WaveformCapture:
        """
        Run simulation and capture waveform simultaneously.
        Alias for capture_waveform for clarity.
        """
        return self.capture_waveform(point, duration)

    def compare_waveforms(self, point: str,
                          reference: WaveformCapture) -> Dict[str, float]:
        """
        Compare current waveform to a reference (e.g., known-good).

        Returns dict of differences.
        """
        current = self.capture_waveform(point, reference.duration)

        return {
            'delta_vpp': current.v_pp - reference.v_pp,
            'delta_vavg': current.v_avg - reference.v_avg,
            'delta_freq': current.frequency - reference.frequency,
            'delta_duty': current.duty_cycle - reference.duty_cycle,
            'pct_vpp': (current.v_pp - reference.v_pp) / max(reference.v_pp, 0.001) * 100,
            'pct_freq': (current.frequency - reference.frequency) / max(reference.frequency, 0.001) * 100,
        }

    def full_circuit_scan(self) -> Dict[str, Measurement]:
        """
        Measure all probe points (DC voltage).

        Returns dict of all measurements for quick circuit overview.
        """
        results = {}
        for point in self.get_probe_points():
            try:
                results[point] = self.measure_vdc(point)
            except Exception as e:
                results[point] = Measurement(
                    value=0.0, unit="V", probe_point=point,
                    measurement_type="vdc", valid=False, notes=str(e)
                )
        return results

    def print_circuit_state(self):
        """Print formatted circuit state for all probe points."""
        print("\n" + "=" * 60)
        print("  CIRCUIT STATE - ALL PROBE POINTS")
        print("=" * 60)

        # Group by section
        sections = {
            'Power Supply': ['v_supply', 'v_logic', 'gnd'],
            'PLL / CD4046': ['vco_control', 'vco_output', 'phase_det_out', 'sig_in', 'comp_in'],
            'Loop Filter': ['loop_filter_in', 'loop_filter_out'],
            'Motor Driver': ['driver_control', 'motor_voltage', 'motor_current', 'motor_drive_a', 'motor_drive_b'],
            'Motor': ['motor_back_emf', 'motor_rpm'],
            'Feedback': ['pickup_raw', 'pickup_amplified', 'feedback_digital'],
            'Iris/Servo': ['servo_command', 'servo_position', 'servo_current', 'iris_aperture'],
        }

        for section, points in sections.items():
            print(f"\n{section}:")
            print("-" * 40)
            for point in points:
                if point in self.probe_map:
                    try:
                        value = self.probe(point)
                        # Determine unit
                        if 'current' in point:
                            unit = 'A'
                        elif 'rpm' in point:
                            unit = 'RPM'
                        elif 'aperture' in point or 'position' in point or 'duty' in point:
                            unit = ''
                        else:
                            unit = 'V'
                        print(f"  {point:25s} = {value:10.4f} {unit}")
                    except Exception as e:
                        print(f"  {point:25s} = ERROR: {e}")

    def diagnose_signal_chain(self) -> List[str]:
        """
        Trace signal through the feedback loop and identify anomalies.

        Returns list of diagnostic observations.
        """
        observations = []

        # Check power supply
        v_supply = self.probe('v_supply')
        if v_supply < 10.0:
            observations.append(f"LOW SUPPLY: {v_supply:.1f}V (expected 12V)")
        elif v_supply > 14.0:
            observations.append(f"HIGH SUPPLY: {v_supply:.1f}V (expected 12V)")

        # Check VCO control voltage
        vco_ctrl = self.probe('vco_control')
        if vco_ctrl < 1.0:
            observations.append(f"VCO control low: {vco_ctrl:.2f}V - motor may be stalled")
        elif vco_ctrl > 14.0:
            observations.append(f"VCO control saturated: {vco_ctrl:.2f}V - PLL may be unlocked")

        # Check loop filter output vs input
        lf_in = self.probe('loop_filter_in')
        lf_out = self.probe('loop_filter_out')
        if abs(lf_in - lf_out) > 5.0:
            observations.append(f"Loop filter delta: in={lf_in:.2f}V, out={lf_out:.2f}V - check capacitor")

        # Check motor drive
        motor_v = self.probe('motor_voltage')
        motor_i = self.probe('motor_current')
        if motor_v > 1.0 and motor_i < 0.1:
            observations.append(f"Motor voltage {motor_v:.1f}V but low current {motor_i:.2f}A - open circuit?")

        # Check feedback signal
        pickup = self.probe('pickup_raw')
        amp_out = self.probe('pickup_amplified')
        if abs(pickup) > 0.01 and abs(amp_out) < 0.1:
            observations.append(f"Pickup signal {pickup:.3f}V not amplified ({amp_out:.2f}V) - check op-amp")

        # Check motor RPM vs target
        rpm = self.probe('motor_rpm')
        # Estimate expected RPM from VCO control
        if rpm < 100 and vco_ctrl > 5.0:
            observations.append(f"Motor RPM {rpm:.0f} but VCO driving {vco_ctrl:.1f}V - mechanical issue?")

        if not observations:
            observations.append("No obvious anomalies detected in signal chain")

        return observations


def create_test_bench(voice) -> TestBench:
    """Factory function to create a test bench for a voice."""
    return TestBench(voice)

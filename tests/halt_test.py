#!/usr/bin/env python3
"""
AeroTone HALT (Highly Accelerated Life Testing) Framework

HALT is about finding design limits and failure modes quickly by:
  1. Step-stressing individual parameters until failure
  2. Combining stresses to find interaction effects
  3. Documenting failure modes and design margins

Stress Axes for AeroTone:
  - THERMAL: Ambient temperature (-40°C to +85°C and beyond)
  - VOLTAGE: Supply voltage (below and above spec)
  - MECHANICAL: Motor load/stall conditions
  - OPERATIONAL: Extreme frequency transitions

Output:
  - Operating Limits (OL): Where degradation begins
  - Destruct Limits (DL): Where permanent damage occurs
  - Design Margin: DL - OL for each axis
  - Failure Mode Catalog: What breaks and why

Usage:
    python -m tests.halt_test [--quick] [--verbose]
"""

import sys
import os
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.thermal import ThermalStatus


class StressAxis(Enum):
    """Stress dimensions for HALT testing"""
    THERMAL_HOT = "thermal_hot"
    THERMAL_COLD = "thermal_cold"
    VOLTAGE_HIGH = "voltage_high"
    VOLTAGE_LOW = "voltage_low"
    MECHANICAL_STALL = "mechanical_stall"
    OPERATIONAL_RAPID = "operational_rapid"


@dataclass
class FailureMode:
    """Documented failure mode from HALT"""
    stress_axis: StressAxis
    stress_level: float
    component: str
    failure_type: str  # 'operating_limit', 'destruct_limit'
    description: str
    thermal_state: Optional[dict] = None


@dataclass
class StressProfile:
    """Configuration for a step-stress test"""
    axis: StressAxis
    start_value: float
    end_value: float
    step_size: float
    dwell_time: float  # seconds at each step
    units: str = ""


@dataclass
class HALTResults:
    """Results from a complete HALT run"""
    operating_limits: Dict[StressAxis, float] = field(default_factory=dict)
    destruct_limits: Dict[StressAxis, float] = field(default_factory=dict)
    failure_modes: List[FailureMode] = field(default_factory=list)
    design_margins: Dict[StressAxis, float] = field(default_factory=dict)

    def calculate_margins(self):
        """Calculate design margins from limits"""
        for axis in self.operating_limits:
            if axis in self.destruct_limits:
                ol = self.operating_limits[axis]
                dl = self.destruct_limits[axis]
                self.design_margins[axis] = abs(dl - ol)


class HALTTestBench:
    """
    HALT Test Bench for AeroTone Voice Card

    Performs step-stress testing on individual axes, then combined stresses.
    Documents all failure modes encountered.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.results = HALTResults()

        # Nominal operating specs (for reference)
        self.specs = {
            'ambient_temp_min': 0.0,      # °C
            'ambient_temp_max': 40.0,     # °C
            'supply_voltage': 12.0,       # V
            'supply_tolerance': 0.10,     # ±10%
        }

    def log(self, msg: str):
        if self.verbose:
            print(msg)

    def create_voice(self, ambient_temp: float = 25.0,
                     supply_voltage: float = 12.0,
                     fast_thermal: bool = True) -> SpiceVoice:
        """Create a fresh voice instance with specified conditions"""
        params = SpiceVoiceParams(
            enable_thermal=True,
            ambient_temp=ambient_temp,
            driver_v_supply=supply_voltage,
        )
        voice = SpiceVoice(params=params, sample_rate=44100)

        if fast_thermal:
            # Reduce thermal masses for faster HALT testing
            # This simulates smaller/cheaper components
            voice.motor_thermal.params.thermal_mass = 2.0  # Was 50
            voice.motor_thermal.params.warning_temp = 80.0  # More realistic
            voice.motor_thermal.params.max_temp = 100.0
            voice.motor_thermal.params.damage_threshold = 110.0
            voice.motor_thermal.params.destruction_temp = 130.0

            for t in voice.transistor_thermals:
                t.params.thermal_mass = 0.5  # Was 2
                t.params.warning_temp = 80.0
                t.params.max_temp = 100.0

            voice.servo_thermal.params.thermal_mass = 1.0  # Was 15
            voice.servo_thermal.params.warning_temp = 50.0
            voice.servo_thermal.params.max_temp = 60.0

        return voice

    def run_functional_test(self, voice: SpiceVoice,
                           duration: float = 2.0,
                           stress_motor: bool = False) -> Tuple[bool, str]:
        """
        Run a basic functional test.

        Returns:
            (passed, reason): Whether function is normal, and any issues
        """
        # Play a simple scale
        test_freqs = [110, 147, 165, 196, 220]  # A2 to A3

        issues = []
        dt = 0.01  # 10ms timestep

        for freq in test_freqs:
            voice.set_target_frequency(freq)

            # Run for a short time
            time_per_freq = duration / len(test_freqs)
            elapsed = 0.0

            while elapsed < time_per_freq:
                voice.update_physics(dt)
                elapsed += dt

                # Apply additional motor stress if requested
                # (simulates high load or partial stall)
                if stress_motor:
                    voice.motor.omega *= 0.7  # Partial load

            # Check thermal status
            if voice.thermal_system:
                for name, node in voice.thermal_system.nodes.items():
                    if node.status == ThermalStatus.WARNING:
                        issues.append(f"{name} thermal warning @ {node.temperature:.0f}C")
                    elif node.status in [ThermalStatus.CRITICAL,
                                        ThermalStatus.DAMAGED,
                                        ThermalStatus.DESTROYED]:
                        return False, f"{name} thermal failure: {node.status.value} @ {node.temperature:.0f}C"

            # Check if motor is responding (omega should be non-zero)
            if voice.motor.omega < 1.0:
                issues.append(f"Motor not responding at {freq}Hz")

        if issues:
            return True, f"Degraded: {'; '.join(issues)}"
        return True, "Normal operation"

    def step_stress_thermal_hot(self, start: float = 25.0,
                                 end: float = 120.0,
                                 step: float = 5.0,
                                 dwell: float = 5.0) -> None:
        """
        Step-stress test: High temperature

        Ramps ambient temperature up until failure.
        """
        self.log("\n" + "=" * 70)
        self.log("HALT STEP-STRESS: THERMAL (HOT)")
        self.log("=" * 70)
        self.log(f"Range: {start}°C to {end}°C, Step: {step}°C, Dwell: {dwell}s")
        self.log("-" * 70)

        operating_limit = None
        destruct_limit = None

        temp = start
        while temp <= end:
            voice = self.create_voice(ambient_temp=temp)

            # At higher temps, apply motor stress to generate more heat
            stress = temp >= 50.0
            passed, status = self.run_functional_test(voice, duration=dwell, stress_motor=stress)

            # Check for thermal damage
            is_damaged = False
            damaged_component = None
            if voice.thermal_system:
                for name, node in voice.thermal_system.nodes.items():
                    if node.status == ThermalStatus.DESTROYED:
                        is_damaged = True
                        damaged_component = name
                        destruct_limit = temp
                        break
                    elif node.status == ThermalStatus.DAMAGED:
                        is_damaged = True
                        damaged_component = name
                        if destruct_limit is None:
                            destruct_limit = temp

            # Log status
            status_char = "✓" if passed and "Degraded" not in status else "⚠" if passed else "✗"
            hottest = voice.thermal_system.get_hottest() if voice.thermal_system else None
            hottest_str = f"(hottest: {hottest.name}={hottest.temperature:.1f}°C)" if hottest else ""

            self.log(f"  {status_char} {temp:5.1f}°C: {status} {hottest_str}")

            # Track operating limit (first degradation)
            if operating_limit is None and "Degraded" in status:
                operating_limit = temp
                self.results.failure_modes.append(FailureMode(
                    stress_axis=StressAxis.THERMAL_HOT,
                    stress_level=temp,
                    component="system",
                    failure_type="operating_limit",
                    description=status,
                ))

            # Track destruct limit
            if is_damaged:
                self.log(f"  *** DESTRUCT LIMIT REACHED: {damaged_component} damaged at {temp}°C ***")
                self.results.failure_modes.append(FailureMode(
                    stress_axis=StressAxis.THERMAL_HOT,
                    stress_level=temp,
                    component=damaged_component,
                    failure_type="destruct_limit",
                    description=f"{damaged_component} thermal damage",
                    thermal_state=voice.thermal_system.get_state() if voice.thermal_system else None,
                ))
                break

            if not passed:
                if destruct_limit is None:
                    destruct_limit = temp
                break

            temp += step

        # Record limits
        if operating_limit:
            self.results.operating_limits[StressAxis.THERMAL_HOT] = operating_limit
        if destruct_limit:
            self.results.destruct_limits[StressAxis.THERMAL_HOT] = destruct_limit

        self.log("-" * 70)
        self.log(f"Operating Limit: {operating_limit}°C" if operating_limit else "Operating Limit: Not reached")
        self.log(f"Destruct Limit: {destruct_limit}°C" if destruct_limit else "Destruct Limit: Not reached")

    def step_stress_thermal_cold(self, start: float = 25.0,
                                  end: float = -60.0,
                                  step: float = -5.0,
                                  dwell: float = 5.0) -> None:
        """
        Step-stress test: Low temperature

        Cold affects:
        - Motor oil viscosity (increased friction)
        - Battery capacity
        - LCD contrast (if any)
        - Component parameter shifts
        """
        self.log("\n" + "=" * 70)
        self.log("HALT STEP-STRESS: THERMAL (COLD)")
        self.log("=" * 70)
        self.log(f"Range: {start}°C to {end}°C, Step: {step}°C, Dwell: {dwell}s")
        self.log("-" * 70)

        operating_limit = None
        destruct_limit = None

        temp = start
        while temp >= end:
            voice = self.create_voice(ambient_temp=temp)

            # At cold temperatures, motor friction increases
            # Simulate by increasing motor damping
            cold_factor = max(0.0, (25.0 - temp) / 50.0)  # 0 at 25°C, 1 at -25°C
            voice.motor.params.damping *= (1.0 + cold_factor * 3.0)  # Up to 4x damping

            passed, status = self.run_functional_test(voice, duration=dwell)

            status_char = "✓" if passed and "Degraded" not in status else "⚠" if passed else "✗"
            self.log(f"  {status_char} {temp:5.1f}°C: {status}")

            if operating_limit is None and "Degraded" in status:
                operating_limit = temp
                self.results.failure_modes.append(FailureMode(
                    stress_axis=StressAxis.THERMAL_COLD,
                    stress_level=temp,
                    component="motor",
                    failure_type="operating_limit",
                    description="Increased friction causes sluggish response",
                ))

            if not passed:
                destruct_limit = temp
                self.results.failure_modes.append(FailureMode(
                    stress_axis=StressAxis.THERMAL_COLD,
                    stress_level=temp,
                    component="motor",
                    failure_type="destruct_limit",
                    description="Motor unable to overcome friction",
                ))
                break

            temp += step

        if operating_limit:
            self.results.operating_limits[StressAxis.THERMAL_COLD] = operating_limit
        if destruct_limit:
            self.results.destruct_limits[StressAxis.THERMAL_COLD] = destruct_limit

        self.log("-" * 70)
        self.log(f"Operating Limit: {operating_limit}°C" if operating_limit else "Operating Limit: Not reached")
        self.log(f"Destruct Limit: {destruct_limit}°C" if destruct_limit else "Destruct Limit: Not reached")

    def step_stress_voltage_high(self, start: float = 12.0,
                                  end: float = 20.0,
                                  step: float = 0.5,
                                  dwell: float = 3.0) -> None:
        """
        Step-stress test: High voltage

        Overvoltage causes:
        - Increased power dissipation in regulators
        - Higher motor current/speed
        - Component overstress
        """
        self.log("\n" + "=" * 70)
        self.log("HALT STEP-STRESS: VOLTAGE (HIGH)")
        self.log("=" * 70)
        self.log(f"Range: {start}V to {end}V, Step: {step}V, Dwell: {dwell}s")
        self.log("-" * 70)

        operating_limit = None
        destruct_limit = None

        voltage = start
        while voltage <= end:
            voice = self.create_voice(supply_voltage=voltage)

            # Higher voltage = more heat in voltage regulators
            # Simulate by adjusting thermal parameters
            if voice.thermal_system and hasattr(voice, 'motor_thermal'):
                # More current at higher voltage = more I²R losses
                voltage_factor = (voltage / 12.0) ** 2
                voice.motor_thermal.params.thermal_resistance /= voltage_factor

            passed, status = self.run_functional_test(voice, duration=dwell)

            # Check for overvoltage damage
            is_damaged = False
            if voice.thermal_system:
                for name, node in voice.thermal_system.nodes.items():
                    if node.status in [ThermalStatus.DAMAGED, ThermalStatus.DESTROYED]:
                        is_damaged = True
                        destruct_limit = voltage
                        break

            status_char = "✓" if passed and "Degraded" not in status else "⚠" if passed else "✗"
            self.log(f"  {status_char} {voltage:5.1f}V: {status}")

            if operating_limit is None and "Degraded" in status:
                operating_limit = voltage
                self.results.failure_modes.append(FailureMode(
                    stress_axis=StressAxis.VOLTAGE_HIGH,
                    stress_level=voltage,
                    component="regulator",
                    failure_type="operating_limit",
                    description="Regulator thermal stress",
                ))

            if is_damaged or not passed:
                if destruct_limit is None:
                    destruct_limit = voltage
                self.results.failure_modes.append(FailureMode(
                    stress_axis=StressAxis.VOLTAGE_HIGH,
                    stress_level=voltage,
                    component="driver" if not is_damaged else "thermal",
                    failure_type="destruct_limit",
                    description="Component overvoltage failure",
                ))
                break

            voltage += step

        if operating_limit:
            self.results.operating_limits[StressAxis.VOLTAGE_HIGH] = operating_limit
        if destruct_limit:
            self.results.destruct_limits[StressAxis.VOLTAGE_HIGH] = destruct_limit

        self.log("-" * 70)
        self.log(f"Operating Limit: {operating_limit}V" if operating_limit else "Operating Limit: Not reached")
        self.log(f"Destruct Limit: {destruct_limit}V" if destruct_limit else "Destruct Limit: Not reached")

    def step_stress_voltage_low(self, start: float = 12.0,
                                 end: float = 6.0,
                                 step: float = -0.5,
                                 dwell: float = 3.0) -> None:
        """
        Step-stress test: Low voltage (brownout)

        Undervoltage causes:
        - Motor unable to reach target speed
        - Control loop instability
        - Regulator dropout
        """
        self.log("\n" + "=" * 70)
        self.log("HALT STEP-STRESS: VOLTAGE (LOW)")
        self.log("=" * 70)
        self.log(f"Range: {start}V to {end}V, Step: {step}V, Dwell: {dwell}s")
        self.log("-" * 70)

        operating_limit = None
        destruct_limit = None

        voltage = start
        while voltage >= end:
            voice = self.create_voice(supply_voltage=voltage)

            passed, status = self.run_functional_test(voice, duration=dwell)

            # At low voltage, motor may not reach target
            motor_deficit = False
            if voice.motor.omega < 10:  # Very low speed
                motor_deficit = True
                status = "Motor undervoltage - insufficient torque"
                passed = False

            status_char = "✓" if passed and "Degraded" not in status else "⚠" if passed else "✗"
            self.log(f"  {status_char} {voltage:5.1f}V: {status}")

            if operating_limit is None and ("Degraded" in status or motor_deficit):
                operating_limit = voltage
                self.results.failure_modes.append(FailureMode(
                    stress_axis=StressAxis.VOLTAGE_LOW,
                    stress_level=voltage,
                    component="motor",
                    failure_type="operating_limit",
                    description="Motor speed regulation degraded",
                ))

            if not passed:
                destruct_limit = voltage
                self.results.failure_modes.append(FailureMode(
                    stress_axis=StressAxis.VOLTAGE_LOW,
                    stress_level=voltage,
                    component="motor",
                    failure_type="destruct_limit",
                    description="Motor cannot maintain rotation",
                ))
                break

            voltage += step

        if operating_limit:
            self.results.operating_limits[StressAxis.VOLTAGE_LOW] = operating_limit
        if destruct_limit:
            self.results.destruct_limits[StressAxis.VOLTAGE_LOW] = destruct_limit

        self.log("-" * 70)
        self.log(f"Operating Limit: {operating_limit}V" if operating_limit else "Operating Limit: Not reached")
        self.log(f"Destruct Limit: {destruct_limit}V" if destruct_limit else "Destruct Limit: Not reached")

    def step_stress_mechanical_stall(self, dwell: float = 10.0) -> None:
        """
        Step-stress test: Mechanical stall

        Simulates blocked propeller - motor stalls under load.
        Measures time to thermal damage.
        """
        self.log("\n" + "=" * 70)
        self.log("HALT STEP-STRESS: MECHANICAL (STALL)")
        self.log("=" * 70)
        self.log(f"Simulating blocked propeller for up to {dwell}s")
        self.log("-" * 70)

        voice = self.create_voice()

        # Use smaller thermal mass for faster testing
        if voice.thermal_system:
            voice.motor_thermal.params.thermal_mass = 2.0  # Faster heating

        voice.set_target_frequency(220.0)

        # Spin up briefly
        for _ in range(100):
            voice.update_physics(0.001)

        # Now stall it
        elapsed = 0.0
        dt = 0.01
        operating_limit = None
        destruct_limit = None

        while elapsed < dwell:
            # Force stall
            voice.motor.omega *= 0.05

            voice.update_physics(dt)
            elapsed += dt

            # Report every second
            if int(elapsed * 10) % 10 == 0 and elapsed > 0:
                motor = voice.motor_thermal
                status_str = motor.status.value
                self.log(f"  [{elapsed:5.1f}s] Motor: {motor.temperature:.1f}°C ({status_str})")

                if motor.status == ThermalStatus.WARNING and operating_limit is None:
                    operating_limit = elapsed
                    self.results.failure_modes.append(FailureMode(
                        stress_axis=StressAxis.MECHANICAL_STALL,
                        stress_level=elapsed,
                        component="motor",
                        failure_type="operating_limit",
                        description=f"Thermal warning at {motor.temperature:.1f}°C after {elapsed:.1f}s stall",
                    ))

                if motor.status == ThermalStatus.DAMAGED:
                    destruct_limit = elapsed
                    self.results.failure_modes.append(FailureMode(
                        stress_axis=StressAxis.MECHANICAL_STALL,
                        stress_level=elapsed,
                        component="motor",
                        failure_type="destruct_limit",
                        description=f"Motor damaged at {motor.temperature:.1f}°C after {elapsed:.1f}s stall",
                    ))
                    self.log(f"  *** MOTOR DAMAGED after {elapsed:.1f}s stall ***")
                    break

                if motor.status == ThermalStatus.DESTROYED:
                    destruct_limit = elapsed
                    self.log(f"  *** MOTOR DESTROYED after {elapsed:.1f}s stall ***")
                    break

        if operating_limit:
            self.results.operating_limits[StressAxis.MECHANICAL_STALL] = operating_limit
        if destruct_limit:
            self.results.destruct_limits[StressAxis.MECHANICAL_STALL] = destruct_limit

        self.log("-" * 70)
        self.log(f"Time to Warning: {operating_limit:.1f}s" if operating_limit else "Time to Warning: Not reached")
        self.log(f"Time to Damage: {destruct_limit:.1f}s" if destruct_limit else "Time to Damage: Not reached")

    def combined_stress_test(self, ambient_temp: float = 50.0,
                             supply_voltage: float = 14.0,
                             duration: float = 10.0) -> None:
        """
        Combined stress test: Multiple stresses simultaneously

        This often reveals failure modes not seen in single-axis testing.
        """
        self.log("\n" + "=" * 70)
        self.log("HALT COMBINED STRESS TEST")
        self.log("=" * 70)
        self.log(f"Conditions: Temp={ambient_temp}°C, Voltage={supply_voltage}V")
        self.log(f"Duration: {duration}s with rapid frequency changes")
        self.log("-" * 70)

        voice = self.create_voice(ambient_temp=ambient_temp,
                                  supply_voltage=supply_voltage)

        # Rapid transitions stress test
        freqs = [110, 220, 165, 330, 147, 294]
        freq_idx = 0

        elapsed = 0.0
        dt = 0.01
        transition_timer = 0.0

        while elapsed < duration:
            # Change frequency rapidly
            transition_timer += dt
            if transition_timer > 0.2:  # Every 200ms
                freq_idx = (freq_idx + 1) % len(freqs)
                voice.set_target_frequency(freqs[freq_idx])
                transition_timer = 0.0

            voice.update_physics(dt)
            elapsed += dt

            # Report every 2 seconds
            if int(elapsed * 10) % 20 == 0 and elapsed > 0:
                hottest = voice.thermal_system.get_hottest()
                self.log(f"  [{elapsed:5.1f}s] Hottest: {hottest.name}={hottest.temperature:.1f}°C "
                        f"({hottest.status.value})")

                if hottest.status == ThermalStatus.DESTROYED:
                    self.log(f"  *** FAILURE: {hottest.name} destroyed under combined stress ***")
                    self.results.failure_modes.append(FailureMode(
                        stress_axis=StressAxis.THERMAL_HOT,  # Primary stress
                        stress_level=ambient_temp,
                        component=hottest.name,
                        failure_type="destruct_limit",
                        description=f"Combined stress failure: T={ambient_temp}°C, V={supply_voltage}V",
                    ))
                    break

        self.log("-" * 70)
        self.log("Combined stress test complete")
        if voice.thermal_system:
            self.log(voice.thermal_system.get_summary())

    def generate_report(self) -> str:
        """Generate final HALT report"""
        self.results.calculate_margins()

        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("  HALT TEST REPORT - AEROTONE VOICE CARD")
        lines.append("=" * 70)

        # Operating Specifications
        lines.append("\nOPERATING SPECIFICATIONS:")
        lines.append(f"  Ambient Temperature: {self.specs['ambient_temp_min']}°C to {self.specs['ambient_temp_max']}°C")
        lines.append(f"  Supply Voltage: {self.specs['supply_voltage']}V ±{self.specs['supply_tolerance']*100:.0f}%")

        # Limits Found
        lines.append("\nLIMITS DISCOVERED:")
        lines.append("-" * 50)
        lines.append(f"  {'Stress Axis':<25} {'Operating':<12} {'Destruct':<12} {'Margin':<12}")
        lines.append("-" * 50)

        for axis in StressAxis:
            ol = self.results.operating_limits.get(axis, None)
            dl = self.results.destruct_limits.get(axis, None)
            margin = self.results.design_margins.get(axis, None)

            ol_str = f"{ol:.1f}" if ol is not None else "N/A"
            dl_str = f"{dl:.1f}" if dl is not None else "N/A"
            margin_str = f"{margin:.1f}" if margin is not None else "N/A"

            lines.append(f"  {axis.value:<25} {ol_str:<12} {dl_str:<12} {margin_str:<12}")

        # Failure Modes
        lines.append("\nFAILURE MODE CATALOG:")
        lines.append("-" * 50)

        for i, fm in enumerate(self.results.failure_modes, 1):
            lines.append(f"\n  {i}. {fm.failure_type.upper()}: {fm.stress_axis.value}")
            lines.append(f"     Component: {fm.component}")
            lines.append(f"     Stress Level: {fm.stress_level}")
            lines.append(f"     Description: {fm.description}")

        # Design Recommendations
        lines.append("\nDESIGN RECOMMENDATIONS:")
        lines.append("-" * 50)

        # Analyze margins and make recommendations
        hot_ol = self.results.operating_limits.get(StressAxis.THERMAL_HOT)
        if hot_ol and hot_ol < 60:
            lines.append("  - Consider larger heatsinks for high-temperature operation")

        cold_ol = self.results.operating_limits.get(StressAxis.THERMAL_COLD)
        if cold_ol and cold_ol > -20:
            lines.append("  - Motor may need low-temperature lubricant for cold operation")

        stall_dl = self.results.destruct_limits.get(StressAxis.MECHANICAL_STALL)
        if stall_dl and stall_dl < 30:
            lines.append("  - Add thermal cutoff or current limiting for stall protection")

        lines.append("\n" + "=" * 70)

        return "\n".join(lines)

    def run_full_halt(self, quick: bool = False) -> None:
        """Run complete HALT sequence"""
        self.log("\n" + "#" * 70)
        self.log("#  AEROTONE HALT (Highly Accelerated Life Testing)")
        self.log("#  Finding design limits and failure modes")
        self.log("#" * 70)

        if quick:
            self.log("\n[QUICK MODE - Reduced dwell times]")
            dwell = 2.0
        else:
            dwell = 5.0

        # Step-stress tests
        self.step_stress_thermal_hot(dwell=dwell)
        self.step_stress_thermal_cold(dwell=dwell)
        self.step_stress_voltage_high(dwell=dwell)
        self.step_stress_voltage_low(dwell=dwell)
        self.step_stress_mechanical_stall(dwell=30.0 if not quick else 10.0)

        # Combined stress
        self.combined_stress_test(duration=10.0 if not quick else 5.0)

        # Generate report
        report = self.generate_report()
        self.log(report)


def main():
    quick = '--quick' in sys.argv
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    bench = HALTTestBench(verbose=True)
    bench.run_full_halt(quick=quick)


if __name__ == '__main__':
    main()

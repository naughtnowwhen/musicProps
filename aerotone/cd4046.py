"""
CD4046 CMOS Phase-Locked Loop IC Model

This is a detailed behavioral model of the CD4046B PLL IC,
matching the actual component used in 1970s-80s electronics.

Pin Configuration (14-pin DIP):
  Pin 1:  PHASE OUT (Phase Comparator I output)
  Pin 2:  PC1 OUT (Phase Comparator I output - same as pin 1)
  Pin 3:  COMP IN (Comparator input - feedback from VCO)
  Pin 4:  VCO OUT (VCO output - square wave)
  Pin 5:  INH (Inhibit - stops VCO when high)
  Pin 6:  C1A (Timing capacitor terminal A)
  Pin 7:  C1B (Timing capacitor terminal B - usually grounded)
  Pin 8:  VSS (Ground)
  Pin 9:  VCO IN (VCO control voltage input)
  Pin 10: SF OUT (Source follower output)
  Pin 11: R1 (Timing resistor for VCO)
  Pin 12: R2 (Offset resistor for VCO - sets minimum freq)
  Pin 13: PC2 OUT (Phase Comparator II output)
  Pin 14: SIG IN (Signal input to phase comparators)
  Pin 16: VDD (Positive supply, typically 5-15V)

Phase Comparator I (XOR type):
  - Simple XOR of SIG_IN and COMP_IN
  - Output is square wave at 2× frequency when locked
  - Average DC level = VDD/2 when locked
  - Good for sine wave inputs

Phase Comparator II (Edge-triggered):
  - Uses rising edges of both inputs
  - Three-state output: High, Low, or High-Z
  - When SIG_IN leads: output goes HIGH until COMP_IN edge
  - When COMP_IN leads: output goes LOW until SIG_IN edge
  - When locked: high-impedance (requires loop filter to hold voltage)
  - Better for square wave inputs, zero static phase error

VCO:
  - Frequency determined by R1, R2, C1, and control voltage
  - f_center = 1 / (R1 * C1) approximately
  - f_min set by R2 (if present)
  - Linear V-to-f characteristic over operating range
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional
from .circuit import Component, Node


@dataclass
class CD4046Params:
    """CD4046 operating parameters"""

    # Supply voltage
    vdd: float = 15.0     # Positive supply (V)
    vss: float = 0.0      # Negative supply / ground (V)

    # VCO timing components
    c1: float = 100e-9    # Timing capacitor (F) - 100nF
    r1: float = 10e3      # Timing resistor (Ω) - 10kΩ
    r2: float = 100e3     # Offset resistor (Ω) - 100kΩ, or None

    # VCO characteristics (derived from R, C)
    # These will be computed from components

    # Internal delays and thresholds
    propagation_delay: float = 50e-9  # seconds
    input_threshold: float = 0.5      # Fraction of VDD


class CD4046(Component):
    """
    CD4046 CMOS Phase-Locked Loop IC

    This model includes:
      - Phase Comparator I (XOR)
      - Phase Comparator II (edge-triggered, three-state)
      - VCO with voltage-controlled frequency
      - Lock detect logic
    """

    def __init__(self, name: str, params: CD4046Params = None):
        super().__init__(name)
        self.params = params or CD4046Params()

        # Calculate VCO frequency range from components
        self._calculate_vco_range()

        # Internal state
        self.vco_phase = 0.0           # VCO phase accumulator (radians)
        self.vco_output = False        # VCO output state (digital)
        self.vco_frequency = 0.0       # Current VCO frequency

        # Input edge detection
        self.sig_in_last = False
        self.comp_in_last = False

        # Phase comparator states
        self.pc1_output = 0.0          # PC1 output voltage
        self.pc2_output = 0.0          # PC2 output voltage
        self.pc2_state = 'high_z'      # 'high', 'low', 'high_z'

        # Input voltages (updated externally)
        self.sig_in_voltage = 0.0      # Pin 14
        self.comp_in_voltage = 0.0     # Pin 3 (usually connected to VCO_OUT)
        self.vco_in_voltage = 0.0      # Pin 9 (control voltage from loop filter)
        self.inhibit = False           # Pin 5

        # Lock detection
        self.lock_detect = False
        self.phase_error_accumulator = 0.0

    def _calculate_vco_range(self):
        """Calculate VCO frequency range from timing components"""
        p = self.params

        # CD4046 VCO frequency approximation:
        # f_max ≈ 1 / (R1 * C1)  (when VCO_IN = VDD)
        # f_min ≈ 1 / (R2 * C1)  (when VCO_IN = 0, if R2 present)

        # More accurate formula from datasheet:
        # f = (VCO_IN / VDD) * f_max + f_offset

        if p.c1 > 0 and p.r1 > 0:
            # Maximum frequency (VCO_IN = VDD)
            self.f_max = 1.0 / (p.r1 * p.c1)
        else:
            self.f_max = 1000  # Default 1kHz

        if p.r2 and p.r2 > 0:
            # Minimum frequency offset
            self.f_min = 1.0 / (p.r2 * p.c1)
        else:
            self.f_min = 0.0

        # VCO gain (Hz per volt)
        self.kvco = (self.f_max - self.f_min) / (p.vdd - p.vss)

    def set_timing_components(self, r1: float, c1: float, r2: float = None):
        """Update timing components and recalculate VCO range"""
        self.params.r1 = r1
        self.params.c1 = c1
        self.params.r2 = r2
        self._calculate_vco_range()

    def _voltage_to_digital(self, voltage: float) -> bool:
        """Convert analog voltage to digital level"""
        threshold = self.params.vss + (self.params.vdd - self.params.vss) * self.params.input_threshold
        return voltage > threshold

    def _digital_to_voltage(self, state: bool) -> float:
        """Convert digital level to output voltage"""
        return self.params.vdd if state else self.params.vss

    def update(self, dt: float):
        """Update CD4046 state for one timestep"""
        p = self.params

        if self.inhibit:
            self.vco_output = False
            self.vco_frequency = 0.0
            return

        # === VCO ===
        # Convert control voltage to frequency
        # Linear relationship: f = f_min + (V_control / VDD) * (f_max - f_min)
        v_control = np.clip(self.vco_in_voltage, p.vss, p.vdd)
        v_normalized = (v_control - p.vss) / (p.vdd - p.vss)
        self.vco_frequency = self.f_min + v_normalized * (self.f_max - self.f_min)

        # Update VCO phase
        self.vco_phase += 2 * np.pi * self.vco_frequency * dt

        # VCO output is square wave
        self.vco_output = (self.vco_phase % (2 * np.pi)) < np.pi

        # === Edge Detection ===
        sig_in = self._voltage_to_digital(self.sig_in_voltage)
        comp_in = self._voltage_to_digital(self.comp_in_voltage)

        sig_rising = sig_in and not self.sig_in_last
        comp_rising = comp_in and not self.comp_in_last

        # === Phase Comparator I (XOR) ===
        # Simple XOR of the two inputs
        pc1_digital = sig_in != comp_in
        self.pc1_output = self._digital_to_voltage(pc1_digital)

        # === Phase Comparator II (Edge-triggered flip-flop) ===
        # This is the commonly used one for PLLs
        # Rising edge of SIG_IN sets output HIGH
        # Rising edge of COMP_IN sets output LOW
        # When both see edges close together, goes to high-Z

        if sig_rising and comp_rising:
            # Both edges simultaneously - go to high-Z
            self.pc2_state = 'high_z'
        elif sig_rising:
            # SIG_IN leads - pump UP (charge the loop filter)
            self.pc2_state = 'high'
        elif comp_rising:
            # COMP_IN leads - pump DOWN (discharge the loop filter)
            self.pc2_state = 'low'
        # Otherwise maintain current state

        # Convert PC2 state to output voltage
        if self.pc2_state == 'high':
            self.pc2_output = p.vdd
        elif self.pc2_state == 'low':
            self.pc2_output = p.vss
        else:  # high_z
            # High impedance - output floats
            # In real circuit, loop filter cap holds voltage
            # We represent this as mid-rail for now
            self.pc2_output = (p.vdd + p.vss) / 2

        # === Lock Detection ===
        # Accumulate phase error over time
        if self.pc2_state == 'high_z':
            self.phase_error_accumulator *= 0.99  # Decay toward lock
        else:
            self.phase_error_accumulator += abs(v_normalized - 0.5) * dt

        self.lock_detect = self.phase_error_accumulator < 0.01

        # Update edge detection memory
        self.sig_in_last = sig_in
        self.comp_in_last = comp_in

    def get_vco_output_voltage(self) -> float:
        """Get VCO output as voltage (Pin 4)"""
        return self._digital_to_voltage(self.vco_output)

    def get_pc1_output(self) -> float:
        """Get Phase Comparator I output voltage (Pin 2)"""
        return self.pc1_output

    def get_pc2_output(self) -> float:
        """Get Phase Comparator II output voltage (Pin 13)"""
        return self.pc2_output

    def get_pc2_state(self) -> str:
        """Get Phase Comparator II state ('high', 'low', 'high_z')"""
        return self.pc2_state

    def is_locked(self) -> bool:
        """Is the PLL locked?"""
        return self.lock_detect

    def get_state(self) -> dict:
        """Return complete IC state"""
        return {
            'vco_frequency': self.vco_frequency,
            'vco_output': self.vco_output,
            'vco_phase': self.vco_phase,
            'pc1_output': self.pc1_output,
            'pc2_output': self.pc2_output,
            'pc2_state': self.pc2_state,
            'lock_detect': self.lock_detect,
            'vco_in_voltage': self.vco_in_voltage,
            'f_min': self.f_min,
            'f_max': self.f_max,
            'kvco': self.kvco,
        }


class LoopFilter:
    """
    Passive/Active loop filter for PLL.

    Common configurations:
      1. Passive RC: R in series with C to ground
      2. Active (integrator): Op-amp with R input and C feedback

    The loop filter converts the phase detector pulses into
    a smooth DC control voltage for the VCO.

    This is a simplified behavioral model - for full accuracy,
    use the component-level circuit simulation.
    """

    def __init__(self, filter_type: str = 'passive_rc',
                 r1: float = 10e3, c1: float = 100e-9,
                 r2: float = None, c2: float = None):
        """
        Initialize loop filter.

        Args:
            filter_type: 'passive_rc', 'lag_lead', or 'active_pi'
            r1, c1: Primary filter components
            r2, c2: Secondary components (for higher-order filters)
        """
        self.filter_type = filter_type
        self.r1 = r1
        self.c1 = c1
        self.r2 = r2
        self.c2 = c2

        # State
        self.capacitor_voltage = 0.0
        self.output_voltage = 0.0

        # Time constants
        self.tau1 = r1 * c1
        if r2 and c2:
            self.tau2 = r2 * c2
        else:
            self.tau2 = None

    def update(self, input_voltage: float, dt: float,
               high_z: bool = False) -> float:
        """
        Update filter and return output voltage.

        Args:
            input_voltage: Input from phase detector
            dt: Time step
            high_z: If True, input is high-impedance (hold mode)

        Returns:
            Filtered output voltage
        """
        if self.filter_type == 'passive_rc':
            if high_z:
                # High-Z input: capacitor holds voltage (slight decay)
                leak = 0.9999  # Very slow discharge
                self.capacitor_voltage *= leak
            else:
                # RC filter: V_c approaches V_in with time constant tau
                alpha = dt / (self.tau1 + dt)
                self.capacitor_voltage += alpha * (input_voltage - self.capacitor_voltage)

            self.output_voltage = self.capacitor_voltage

        elif self.filter_type == 'lag_lead':
            # Lag-lead filter for better stability
            # Two cascaded RC sections
            alpha1 = dt / (self.tau1 + dt)

            if not high_z:
                self.capacitor_voltage += alpha1 * (input_voltage - self.capacitor_voltage)

            self.output_voltage = self.capacitor_voltage

        return self.output_voltage

    def get_voltage(self) -> float:
        """Get current output voltage"""
        return self.output_voltage

    def reset(self, voltage: float = 0.0):
        """Reset filter state"""
        self.capacitor_voltage = voltage
        self.output_voltage = voltage


class PLLSystem:
    """
    Complete PLL system with CD4046 and loop filter.

    This combines the CD4046 IC with external loop filter components
    to create a working phase-locked loop.
    """

    def __init__(self, name: str = "pll"):
        self.name = name

        # Create CD4046 with default timing
        self.cd4046 = CD4046(f"{name}_ic")

        # Create loop filter
        self.loop_filter = LoopFilter(
            filter_type='passive_rc',
            r1=47e3,     # 47kΩ
            c1=100e-9    # 100nF
        )

        # Configuration
        self.use_pc2 = True  # Use Phase Comparator II (better for square waves)

        # External connections
        self.reference_frequency = 0.0
        self.reference_phase = 0.0

    def set_reference(self, frequency: float):
        """Set reference frequency in Hz"""
        self.reference_frequency = frequency

    def set_vco_timing(self, r1: float, c1: float, r2: float = None):
        """Set VCO timing components"""
        self.cd4046.set_timing_components(r1, c1, r2)

    def set_loop_filter(self, r1: float, c1: float):
        """Set loop filter components"""
        self.loop_filter = LoopFilter('passive_rc', r1, c1)

    def update(self, dt: float):
        """Update the complete PLL system"""
        # Generate reference signal
        self.reference_phase += 2 * np.pi * self.reference_frequency * dt
        ref_voltage = 15.0 if (self.reference_phase % (2 * np.pi)) < np.pi else 0.0

        # Feed reference to CD4046 signal input
        self.cd4046.sig_in_voltage = ref_voltage

        # Connect VCO output to comparator input (internal feedback)
        self.cd4046.comp_in_voltage = self.cd4046.get_vco_output_voltage()

        # Get phase detector output
        if self.use_pc2:
            pd_output = self.cd4046.get_pc2_output()
            high_z = self.cd4046.get_pc2_state() == 'high_z'
        else:
            pd_output = self.cd4046.get_pc1_output()
            high_z = False

        # Update loop filter
        control_voltage = self.loop_filter.update(pd_output, dt, high_z)

        # Feed control voltage to VCO
        self.cd4046.vco_in_voltage = control_voltage

        # Update CD4046
        self.cd4046.update(dt)

    def get_vco_frequency(self) -> float:
        """Get current VCO frequency"""
        return self.cd4046.vco_frequency

    def get_control_voltage(self) -> float:
        """Get loop filter output (VCO control voltage)"""
        return self.loop_filter.get_voltage()

    def is_locked(self) -> bool:
        """Is the PLL locked to reference?"""
        return self.cd4046.is_locked()

    def get_state(self) -> dict:
        """Get complete system state"""
        return {
            'reference_frequency': self.reference_frequency,
            'vco_frequency': self.cd4046.vco_frequency,
            'control_voltage': self.loop_filter.get_voltage(),
            'locked': self.is_locked(),
            'cd4046': self.cd4046.get_state(),
        }

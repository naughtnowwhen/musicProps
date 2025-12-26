"""
Motor Driver and Magnetic Pickup Circuits for AeroTone

Contains:
  - H-Bridge motor driver (using discrete transistors)
  - Magnetic pickup signal conditioning
  - Current sensing
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

from .circuit import Component, BJT_NPN, BJT_PNP, Diode, Resistor


@dataclass
class HBridgeParams:
    """H-Bridge driver parameters"""

    # Supply
    v_supply: float = 12.0        # Motor supply voltage

    # Transistors (TIP31/TIP32 style)
    transistor_vce_sat: float = 0.7   # Saturation voltage drop
    transistor_beta: float = 50       # Current gain

    # Current limiting
    current_limit: float = 2.0    # Amps
    sense_resistor: float = 0.5   # Ohms (for current sensing)

    # Protection diodes
    diode_vf: float = 0.7         # Forward voltage drop

    # PWM (if used)
    pwm_frequency: float = 20000  # Hz - above audible


class HBridgeDriver(Component):
    """
    H-Bridge motor driver using discrete transistors.

    Topology (simplified):
                     +V_supply
                        │
              ┌─────────┼─────────┐
              │         │         │
           [Q1 PNP]     │     [Q3 PNP]
              │         │         │
              ├────[Motor]────────┤
              │         │         │
           [Q2 NPN]     │     [Q4 NPN]
              │         │         │
              └────┬────┴────┬────┘
                   │         │
                 [Rs]      [Rs]
                   │         │
                  GND       GND

    Control:
      - Q1+Q4 ON, Q2+Q3 OFF: Motor forward
      - Q2+Q3 ON, Q1+Q4 OFF: Motor reverse
      - All OFF: Coast
      - Q1+Q3 or Q2+Q4 ON: Brake (short motor)

    This model uses a control voltage (0-12V) to set motor drive level,
    which would come from the PLL loop filter.
    """

    def __init__(self, name: str, params: HBridgeParams = None):
        super().__init__(name)
        self.params = params or HBridgeParams()

        # State
        self.control_voltage = 0.0   # Input from PLL (0 to Vdd)
        self.motor_voltage = 0.0     # Output to motor
        self.motor_current = 0.0     # Sensed current

        # PWM state (if using PWM mode)
        self.pwm_phase = 0.0
        self.use_pwm = False

        # Protection state
        self.over_current = False
        self.thermal_shutdown = False

        # Temperature (simplified thermal model)
        self.temperature = 25.0

    def set_control_voltage(self, voltage: float):
        """
        Set control voltage (from PLL loop filter).

        For linear mode: 0V = stop, 6V = half speed, 12V = full speed
        The control voltage is mapped to motor drive.
        """
        self.control_voltage = np.clip(voltage, 0, self.params.v_supply)

    def update(self, dt: float, motor_back_emf: float = 0.0):
        """
        Update H-bridge state.

        Args:
            dt: Time step
            motor_back_emf: Motor back-EMF voltage (for current calculation)
        """
        p = self.params

        if self.thermal_shutdown or self.over_current:
            self.motor_voltage = 0.0
            self.motor_current = 0.0
            return

        # Convert control voltage to motor voltage
        # Linear drive: V_motor ∝ V_control
        # Account for transistor saturation drops
        v_drop = 2 * p.transistor_vce_sat  # Two transistors in series

        # Effective motor voltage (control scaled to motor supply)
        v_control_normalized = self.control_voltage / p.v_supply
        self.motor_voltage = v_control_normalized * (p.v_supply - v_drop)

        # Calculate expected current (V = I*R + back_emf, simplified)
        # In reality this comes from motor model, but we can estimate
        if self.motor_voltage > motor_back_emf:
            self.motor_current = (self.motor_voltage - motor_back_emf) / 2.0  # Rough estimate
        else:
            self.motor_current = 0.0

        # Current limiting
        if self.motor_current > p.current_limit:
            self.motor_current = p.current_limit
            self.motor_voltage = motor_back_emf + self.motor_current * 2.0

        # Thermal update (simplified)
        power = self.motor_voltage * self.motor_current * 0.1  # Transistor dissipation
        thermal_rise = power * 5.0  # °C/W thermal resistance
        self.temperature += (25.0 + thermal_rise - self.temperature) * dt / 30.0

        if self.temperature > 150:
            self.thermal_shutdown = True

    def get_motor_voltage(self) -> float:
        """Get output voltage to motor"""
        return self.motor_voltage

    def get_motor_current(self) -> float:
        """Get motor current"""
        return self.motor_current

    def get_state(self) -> dict:
        """Get driver state"""
        return {
            'control_voltage': self.control_voltage,
            'motor_voltage': self.motor_voltage,
            'motor_current': self.motor_current,
            'temperature': self.temperature,
            'over_current': self.over_current,
            'thermal_shutdown': self.thermal_shutdown,
        }


@dataclass
class MagneticPickupParams:
    """Magnetic pickup parameters"""

    # Pickup characteristics
    coil_resistance: float = 500      # Ohms (typical for small pickup)
    coil_inductance: float = 0.1      # Henries
    sensitivity: float = 0.1          # V/(rad/s) at nominal gap

    # Magnet and geometry
    pole_pieces: int = 1              # Number of poles (1 for simple hub magnet)
    air_gap: float = 0.002            # meters (2mm nominal)

    # Signal conditioning
    load_resistance: float = 10e3     # Input impedance of next stage


class MagneticPickup(Component):
    """
    Variable reluctance magnetic pickup (tachometer sensor).

    Senses the passing of a magnet on the propeller hub.
    Produces a sine-wave-like output at the rotation frequency
    (or multiples if multiple magnets).

    Output voltage is proportional to rate of change of flux,
    which means V ∝ ω (angular velocity).

    Signal chain:
      Hub magnet → Pickup coil → Signal conditioning → Comparator → Digital pulse

    The output needs conditioning before feeding to the CD4046:
      - Amplification (pickup output is millivolts)
      - Zero-crossing detection or comparator
      - Schmitt trigger for noise immunity
    """

    def __init__(self, name: str, params: MagneticPickupParams = None):
        super().__init__(name)
        self.params = params or MagneticPickupParams()

        # State
        self.rotor_angle = 0.0           # Current rotor position (rad)
        self.angular_velocity = 0.0       # rad/s

        # Output
        self.raw_voltage = 0.0           # Raw pickup voltage
        self.conditioned_voltage = 0.0   # After signal conditioning
        self.digital_output = False      # After comparator

        # Noise
        self.noise_amplitude = 0.001     # Volts RMS

    def update(self, dt: float, rotor_angle: float, angular_velocity: float):
        """
        Update pickup output based on rotor position and speed.

        Args:
            dt: Time step
            rotor_angle: Rotor angle in radians
            angular_velocity: Rotor angular velocity in rad/s
        """
        self.rotor_angle = rotor_angle
        self.angular_velocity = angular_velocity
        p = self.params

        # Magnetic flux variation with angle (sinusoidal for single magnet)
        # Φ = Φ_max * cos(θ * pole_pieces)
        # V = -dΦ/dt = Φ_max * pole_pieces * ω * sin(θ * pole_pieces)

        # Peak voltage proportional to angular velocity
        v_peak = p.sensitivity * angular_velocity * p.pole_pieces

        # Sinusoidal output
        self.raw_voltage = v_peak * np.sin(rotor_angle * p.pole_pieces)

        # Add noise
        noise = np.random.randn() * self.noise_amplitude
        self.raw_voltage += noise

    def get_raw_voltage(self) -> float:
        """Get raw pickup coil voltage (before conditioning)"""
        return self.raw_voltage

    def get_state(self) -> dict:
        """Get pickup state"""
        return {
            'raw_voltage': self.raw_voltage,
            'angular_velocity': self.angular_velocity,
            'rotor_angle': self.rotor_angle,
        }


class SignalConditioner(Component):
    """
    Signal conditioning for magnetic pickup.

    Stages:
      1. High-pass filter (remove DC offset)
      2. Amplifier (boost millivolt signal)
      3. Comparator with hysteresis (Schmitt trigger)

    Converts the analog sine wave from the pickup into
    clean digital pulses for the CD4046.
    """

    def __init__(self, name: str,
                 gain: float = 100,
                 hysteresis: float = 0.5,
                 threshold: float = 0.0):
        super().__init__(name)

        self.gain = gain                 # Voltage gain
        self.hysteresis = hysteresis     # Schmitt trigger hysteresis (V)
        self.threshold = threshold       # Comparator threshold (V)

        # High-pass filter state
        self.hp_capacitor_voltage = 0.0
        self.hp_tau = 0.01               # 10ms time constant (16 Hz corner)

        # Output
        self.amplified_voltage = 0.0
        self.digital_output = False

        # Schmitt trigger thresholds
        self.upper_threshold = threshold + hysteresis / 2
        self.lower_threshold = threshold - hysteresis / 2

    def update(self, dt: float, input_voltage: float):
        """
        Process input signal through conditioning chain.

        Args:
            dt: Time step
            input_voltage: Raw pickup voltage
        """
        # High-pass filter (AC coupling)
        # Removes any DC offset from the pickup
        alpha = dt / (self.hp_tau + dt)
        hp_out = input_voltage - self.hp_capacitor_voltage
        self.hp_capacitor_voltage += alpha * (input_voltage - self.hp_capacitor_voltage)

        # Amplification
        self.amplified_voltage = hp_out * self.gain

        # Clamp to reasonable range (op-amp saturation)
        self.amplified_voltage = np.clip(self.amplified_voltage, -12, 12)

        # Schmitt trigger comparator
        if self.digital_output:
            # Currently high - go low if below lower threshold
            if self.amplified_voltage < self.lower_threshold:
                self.digital_output = False
        else:
            # Currently low - go high if above upper threshold
            if self.amplified_voltage > self.upper_threshold:
                self.digital_output = True

    def get_digital_output(self) -> bool:
        """Get digital output state"""
        return self.digital_output

    def get_output_voltage(self) -> float:
        """Get digital output as voltage (0 or 15V for CD4046)"""
        return 15.0 if self.digital_output else 0.0

    def get_state(self) -> dict:
        """Get conditioner state"""
        return {
            'amplified_voltage': self.amplified_voltage,
            'digital_output': self.digital_output,
        }

"""
Propeller Aerodynamics Model for AeroTone

Simulates the aerodynamic behavior of a multi-blade propeller
in a ducted shroud, including:
  - Drag torque (load on motor)
  - Thrust (affects acoustic output)
  - Blade passage frequency

Propeller aerodynamics (simplified):
  Torque ∝ ρ * n² * D⁵ * Cq  (where n = rev/s, D = diameter)
  Thrust ∝ ρ * n² * D⁴ * Ct

For our musical application, we care most about:
  1. Load torque (affects motor response)
  2. Blade passage frequency (the musical tone)
  3. Acoustic spectrum characteristics
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class PropellerParams:
    """Propeller physical parameters"""

    # Geometry
    num_blades: int = 12             # Number of blades (12 for moderate RPM)
    diameter: float = 0.10           # meters (100mm)
    hub_diameter: float = 0.02       # meters (20mm hub)

    # Mass properties
    mass: float = 0.020              # kg (20 grams for plastic prop)
    inertia: float = 2e-5            # kg·m² - moment of inertia

    # Aerodynamic coefficients (simplified)
    drag_coefficient: float = 0.02   # Dimensionless - torque coefficient
    thrust_coefficient: float = 0.05 # Dimensionless - thrust coefficient

    # Blade profile effects on tone
    harmonic_rolloff: float = 1.8    # Higher = faster harmonic decay
    blade_asymmetry: float = 0.02    # Imbalance factor (0 = perfect)

    # Trailing edge treatment
    has_serrations: bool = True      # Owl-wing style serrations
    serration_noise_reduction: float = 0.7  # Factor (1.0 = no effect)


class Propeller:
    """
    Propeller aerodynamic simulation.

    Computes load torque and blade passage frequency for motor coupling.
    """

    # Air properties at sea level, 20°C (standard atmosphere)
    STANDARD_AIR_DENSITY = 1.225  # kg/m³

    def __init__(self, params: PropellerParams = None):
        self.params = params or PropellerParams()

        # State
        self.omega = 0.0       # rad/s (set by motor)
        self.thrust = 0.0      # N
        self.torque = 0.0      # N·m (drag torque on motor)

        # Weather-affected air density (can be modified externally)
        self._air_density = self.STANDARD_AIR_DENSITY

    @property
    def air_density(self) -> float:
        """Current air density in kg/m³"""
        return self._air_density

    @air_density.setter
    def air_density(self, value: float):
        """Set air density (affected by weather)"""
        self._air_density = value

    @property
    def rpm(self) -> float:
        """Rotational speed in RPM"""
        return self.omega * 60.0 / (2.0 * np.pi)

    @property
    def rps(self) -> float:
        """Rotational speed in rev/s"""
        return self.omega / (2.0 * np.pi)

    @property
    def blade_passage_frequency(self) -> float:
        """
        Blade passage frequency - the fundamental musical tone.

        BPF = (RPM × num_blades) / 60 = rps × num_blades
        """
        return self.rps * self.params.num_blades

    @property
    def tip_speed(self) -> float:
        """Blade tip speed in m/s"""
        return self.omega * self.params.diameter / 2.0

    def update(self, motor_omega: float):
        """
        Update propeller state based on motor angular velocity.

        Args:
            motor_omega: Motor angular velocity in rad/s
        """
        self.omega = motor_omega
        p = self.params

        # Compute aerodynamic forces using simplified propeller theory
        # Torque = Cq * ρ * n² * D⁵
        # Thrust = Ct * ρ * n² * D⁴

        n = self.rps  # rev/s
        d = p.diameter

        # Torque (load on motor) - scales with n²
        # Added constant term for bearing friction
        bearing_friction = 1e-5 * self.omega  # Linear friction component
        aero_torque = (p.drag_coefficient * self._air_density *
                       n**2 * d**5)
        self.torque = aero_torque + bearing_friction

        # Thrust (affects acoustic amplitude)
        self.thrust = (p.thrust_coefficient * self._air_density *
                       n**2 * d**4)

    def get_load_torque(self) -> float:
        """Return load torque for motor simulation"""
        return self.torque

    def get_inertia(self) -> float:
        """Return moment of inertia for motor simulation"""
        return self.params.inertia

    def get_acoustic_params(self) -> dict:
        """
        Return parameters for acoustic synthesis.

        These inform the sound generator about the propeller's
        acoustic characteristics.
        """
        return {
            'bpf': self.blade_passage_frequency,
            'num_blades': self.params.num_blades,
            'thrust': self.thrust,
            'tip_speed': self.tip_speed,
            'harmonic_rolloff': self.params.harmonic_rolloff,
            'has_serrations': self.params.has_serrations,
            'serration_factor': self.params.serration_noise_reduction,
            'asymmetry': self.params.blade_asymmetry,
        }

    def get_state(self) -> dict:
        """Return current state as dictionary"""
        return {
            'omega': self.omega,
            'rpm': self.rpm,
            'bpf': self.blade_passage_frequency,
            'torque': self.torque,
            'thrust': self.thrust,
            'tip_speed': self.tip_speed,
        }


def rpm_for_frequency(target_freq: float, num_blades: int = 12) -> float:
    """
    Calculate required RPM for a target blade passage frequency.

    Args:
        target_freq: Desired frequency in Hz
        num_blades: Number of propeller blades

    Returns:
        Required RPM
    """
    # BPF = (RPM × num_blades) / 60
    # RPM = (BPF × 60) / num_blades
    return (target_freq * 60.0) / num_blades


def frequency_for_rpm(rpm: float, num_blades: int = 12) -> float:
    """
    Calculate blade passage frequency for a given RPM.

    Args:
        rpm: Rotational speed in RPM
        num_blades: Number of propeller blades

    Returns:
        Blade passage frequency in Hz
    """
    return (rpm * num_blades) / 60.0


# Musical note frequencies for one octave (A2 to A3)
NOTES = {
    'A2':  110.00,
    'A#2': 116.54,
    'Bb2': 116.54,
    'B2':  123.47,
    'C3':  130.81,
    'C#3': 138.59,
    'Db3': 138.59,
    'D3':  146.83,
    'D#3': 155.56,
    'Eb3': 155.56,
    'E3':  164.81,
    'F3':  174.61,
    'F#3': 185.00,
    'Gb3': 185.00,
    'G3':  196.00,
    'G#3': 207.65,
    'Ab3': 207.65,
    'A3':  220.00,  # Octave above A2
}


def note_to_rpm(note: str, num_blades: int = 12) -> float:
    """
    Convert musical note name to required RPM.

    Args:
        note: Note name (e.g., 'A2', 'C#3')
        num_blades: Number of propeller blades

    Returns:
        Required RPM for the note
    """
    freq = NOTES.get(note.upper())
    if freq is None:
        raise ValueError(f"Unknown note: {note}")
    return rpm_for_frequency(freq, num_blades)

"""
Concert-Scale AeroTone Voice

A single voice channel scaled for concert-level acoustic output.

Differences from desktop SpiceVoice:
  - 400mm propeller (vs 100mm) → 16× more air moved
  - 500W motor (vs 25W) → 20× more power
  - 48V DC bus (vs 12V) → higher voltage, more efficient
  - Power amplifier with MOSFETs (vs simple H-bridge)
  - ~100-110 dB output (vs 70-80 dB)

Signal chain:
  Crystal Ref → PLL Control → Power Amp → Motor → Propeller → Sound
                    ↑                                  ↓
                    └──────── Magnetic Pickup ─────────┘
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

from .motor import DCMotor, MotorParams
from .propeller import Propeller, PropellerParams, NOTES
from .acoustics import PropellerSynth
from .cd4046 import CD4046, CD4046Params, LoopFilter
from .driver import MagneticPickup, MagneticPickupParams, SignalConditioner
from .power_amp import PowerAmplifier, PowerAmpParams
from .weather import Weather


@dataclass
class ConcertMotorParams:
    """
    Concert-scale DC motor parameters.

    Based on a ~500W brushed DC motor suitable for 48V operation.
    Think industrial servo motor or large RC car motor.
    """
    # Electrical
    resistance: float = 0.2          # Ω - lower for high current
    inductance: float = 0.3e-3       # H (0.3mH)
    ke: float = 0.15                 # V/(rad/s) - back-EMF constant
    kt: float = 0.15                 # N·m/A - torque constant

    # Mechanical
    inertia: float = 5e-4            # kg·m² - larger rotor
    damping: float = 1e-4            # N·m/(rad/s)

    # Limits
    max_voltage: float = 48.0        # V
    max_current: float = 20.0        # A continuous


@dataclass
class ConcertPropellerParams:
    """
    Concert-scale propeller parameters.

    400mm (16") diameter, 12 blades.
    Larger = more air displacement = more sound.
    """
    num_blades: int = 12
    diameter: float = 0.40           # 400mm (16 inches)
    hub_diameter: float = 0.08       # 80mm hub
    mass: float = 0.5                # kg (500g - solid construction)
    inertia: float = 2e-3            # kg·m² - much larger than desktop
    drag_coefficient: float = 0.025  # Slightly higher for larger prop
    thrust_coefficient: float = 0.06


@dataclass
class ConcertVoiceParams:
    """Complete concert voice parameters"""

    # Power
    bus_voltage: float = 48.0
    max_power: float = 500.0         # Watts

    # Control loop (gentler gains for high-power system)
    proportional_gain: float = 0.10  # Lower for less aggressive response
    integral_gain: float = 0.3       # Slower integral buildup
    derivative_gain: float = 0.02    # D term for faster response

    # Loop filter (slower for stability with larger inertia)
    loop_r1: float = 150e3           # 150kΩ
    loop_c1: float = 22e-6           # 22µF (τ = 3.3 seconds)

    # VCO timing (same frequency range as desktop)
    vco_r1: float = 10e3
    vco_c1: float = 100e-9
    vco_r2: float = 100e3

    # Power amp
    pwm_frequency: float = 20000     # 20kHz
    current_limit: float = 15.0      # A (conservative for thermal)


class ConcertVoice:
    """
    Concert-scale propeller voice.

    This is the full-power version with:
      - 500W motor capability
      - MOSFET H-bridge power stage
      - 400mm propeller
      - Thermal management
      - Current limiting

    Suitable for:
      - Concert halls
      - Outdoor venues
      - Art installations
      - Sound design studios
    """

    def __init__(self, params: ConcertVoiceParams = None, sample_rate: int = 44100):
        self.params = params or ConcertVoiceParams()
        self.sample_rate = sample_rate
        p = self.params

        # === Motor (concert scale) ===
        motor_params = MotorParams(
            resistance=0.2,
            inductance=0.3e-3,
            ke=0.15,
            kt=0.15,
            inertia=5e-4,
            damping=1e-4,
            max_voltage=p.bus_voltage,
            max_current=p.current_limit,
        )
        self.motor = DCMotor(motor_params)

        # === Propeller (concert scale) ===
        prop_params = PropellerParams(
            num_blades=12,
            diameter=0.40,
            inertia=2e-3,
            drag_coefficient=0.025,
            thrust_coefficient=0.06,
        )
        self.propeller = Propeller(prop_params)
        self.motor.load_inertia = self.propeller.get_inertia()

        # === Power Amplifier ===
        pa_params = PowerAmpParams(
            v_bus=p.bus_voltage,
            current_limit=p.current_limit,
            pwm_frequency=p.pwm_frequency,
            control_voltage_max=10.0,
        )
        self.power_amp = PowerAmplifier("PA1", pa_params)

        # === PLL / Control ===
        cd4046_params = CD4046Params(
            vdd=15.0,
            vss=0.0,
            c1=p.vco_c1,
            r1=p.vco_r1,
            r2=p.vco_r2,
        )
        self.cd4046 = CD4046("U1", cd4046_params)

        self.loop_filter = LoopFilter(
            filter_type='passive_rc',
            r1=p.loop_r1,
            c1=p.loop_c1,
        )

        # === Magnetic Pickup ===
        pickup_params = MagneticPickupParams(
            sensitivity=0.1,      # Higher for larger prop
            pole_pieces=1,
        )
        self.pickup = MagneticPickup("TACH", pickup_params)

        self.conditioner = SignalConditioner(
            "COND",
            gain=100,
            hysteresis=0.5,
        )

        # === Acoustic Synthesizer ===
        # Concert scale - louder base level
        self.synth = PropellerSynth(sample_rate)

        # === Control State ===
        self.target_frequency = 0.0
        self.reference_phase = 0.0
        self.active = False

        # PID state
        self.freq_error_integral = 0.0
        self.freq_error_last = 0.0
        self.filtered_derivative = 0.0

        self.proportional_gain = p.proportional_gain
        self.integral_gain = p.integral_gain
        self.derivative_gain = p.derivative_gain
        self.integral_limit = 8.0

        # Weather (optional)
        self.weather = None

        # Simulation
        self.circuit_dt = 1e-5  # 100kHz
        self.circuit_accumulator = 0.0

    def set_target_frequency(self, frequency: float):
        """Set target blade passage frequency"""
        self.target_frequency = frequency
        self.active = frequency > 0

    def set_target_note(self, note: str):
        """Set target by note name"""
        freq = NOTES.get(note.upper())
        if freq:
            self.set_target_frequency(freq)

    def set_weather(self, weather: Weather = None):
        """Enable weather effects"""
        self.weather = weather
        if weather is None:
            self.propeller.air_density = self.propeller.STANDARD_AIR_DENSITY

    def _update_circuit(self, dt: float):
        """Update all components for one timestep"""
        if not self.active:
            self.power_amp.enable(False)
            self.motor.set_voltage(0)
            self.motor.update(dt)
            return

        self.power_amp.enable(True)

        # === Reference Signal ===
        self.reference_phase += 2 * np.pi * self.target_frequency * dt
        if self.reference_phase > 2 * np.pi:
            self.reference_phase -= 2 * np.pi
        ref_voltage = 15.0 if self.reference_phase < np.pi else 0.0

        # === Feedback ===
        feedback_voltage = self.conditioner.get_output_voltage()

        # === PLL ===
        self.cd4046.sig_in_voltage = ref_voltage
        self.cd4046.comp_in_voltage = feedback_voltage
        self.cd4046.update(dt)

        # === Frequency Error / PID ===
        actual_freq = self.propeller.blade_passage_frequency
        freq_error = self.target_frequency - actual_freq

        # P term
        p_term = freq_error * self.proportional_gain

        # I term
        self.freq_error_integral += freq_error * dt * self.integral_gain
        self.freq_error_integral = np.clip(self.freq_error_integral,
                                           -self.integral_limit, self.integral_limit)
        i_term = self.freq_error_integral

        # D term
        d_term = 0.0
        if self.derivative_gain > 0 and dt > 0:
            raw_derivative = (freq_error - self.freq_error_last) / dt
            alpha = 0.1
            self.filtered_derivative = (alpha * raw_derivative +
                                        (1 - alpha) * self.filtered_derivative)
            d_term = self.filtered_derivative * self.derivative_gain
            self.freq_error_last = freq_error

        # Combined control voltage
        error_voltage = 7.5 + p_term + i_term + d_term  # Bias at mid-range
        error_voltage = np.clip(error_voltage, 0, 15)

        # === Loop Filter ===
        control_voltage = self.loop_filter.update(error_voltage, dt, high_z=False)

        # Scale to power amp range (0-15V PLL → 0-10V power amp)
        pa_control = control_voltage * (10.0 / 15.0)

        # === Weather ===
        if self.weather is not None:
            self.weather.update(dt)
            self.propeller.air_density = self.weather.get_air_density()

        # === Power Amplifier ===
        self.power_amp.set_control_voltage(pa_control)
        self.power_amp.update(dt, self.motor.back_emf, self.motor.current)

        # === Motor ===
        self.motor.set_voltage(self.power_amp.get_motor_voltage())
        self.propeller.update(self.motor.omega)
        self.motor.load_torque = self.propeller.get_load_torque()
        self.motor.update(dt)

        # === Pickup ===
        blade_angle = self.motor.theta * self.propeller.params.num_blades
        blade_omega = self.motor.omega * self.propeller.params.num_blades
        self.pickup.update(dt, blade_angle, blade_omega)

        # === Conditioner ===
        self.conditioner.update(dt, self.pickup.get_raw_voltage())

        # === Acoustic Output ===
        acoustic_params = self.propeller.get_acoustic_params()
        self.synth.set_operating_point(
            bpf=acoustic_params['bpf'],
            thrust=max(acoustic_params['thrust'], 0.1) if self.active else 0,
            num_blades=acoustic_params['num_blades'],
        )

    def update_physics(self, dt: float):
        """Update physics for given time step"""
        self.circuit_accumulator += dt

        while self.circuit_accumulator >= self.circuit_dt:
            self._update_circuit(self.circuit_dt)
            self.circuit_accumulator -= self.circuit_dt

    def generate_audio(self, num_samples: int) -> np.ndarray:
        """Generate audio samples"""
        audio_dt = num_samples / self.sample_rate
        self.update_physics(audio_dt)
        return self.synth.generate(num_samples)

    @property
    def current_frequency(self) -> float:
        return self.propeller.blade_passage_frequency

    @property
    def current_rpm(self) -> float:
        return self.motor.rpm

    @property
    def is_locked(self) -> bool:
        if self.target_frequency == 0:
            return False
        error_pct = abs(self.current_frequency - self.target_frequency) / self.target_frequency
        return error_pct < 0.005

    def get_state(self) -> dict:
        """Get complete state"""
        pa_state = self.power_amp.get_state()
        weather_info = {}
        if self.weather:
            ws = self.weather.get_state()
            weather_info = {
                'weather_density': ws['density'],
                'weather_variation_pct': ws['variation_percent'],
            }

        return {
            # Target
            'target_frequency': self.target_frequency,
            'active': self.active,

            # Actual
            'prop_frequency': self.propeller.blade_passage_frequency,
            'motor_rpm': self.motor.rpm,
            'frequency_error_hz': self.current_frequency - self.target_frequency,
            'is_locked': self.is_locked,

            # Power
            'bus_voltage': pa_state['bus_voltage'],
            'motor_voltage': pa_state['motor_voltage'],
            'motor_current': self.motor.current,
            'power_in': pa_state['bus_voltage'] * abs(self.motor.current),
            'power_dissipation': pa_state['power_dissipation'],
            'efficiency': pa_state['efficiency'],

            # Thermal
            't_junction': pa_state['t_junction'],
            't_heatsink': pa_state['t_heatsink'],
            'fan_on': pa_state['fan_on'],

            # Protection
            'fault': pa_state['fault'],

            # Control
            'duty_cycle': pa_state['duty_cycle'],
            'control_voltage': pa_state['control_voltage'],

            # Propeller
            'prop_torque': self.propeller.torque,
            'prop_thrust': self.propeller.thrust,
            'air_density': self.propeller.air_density,

            **weather_info,
        }

    def get_component_count(self) -> dict:
        """Get total component count"""
        pa_components = self.power_amp.get_component_count()

        return {
            'power_amp': pa_components['total'],
            'pll_control': 8,        # CD4046 + loop filter + misc
            'signal_conditioning': 7,
            'motor': 1,
            'propeller': 1,
            'pickup': 1,
            'total_electronic': pa_components['total'] + 15,
            'total': pa_components['total'] + 18,
        }

    def reset(self):
        """Reset all state"""
        self.motor.omega = 0.0
        self.motor.current = 0.0
        self.motor.theta = 0.0
        self.propeller.omega = 0.0
        self.loop_filter.reset()
        self.reference_phase = 0.0
        self.freq_error_integral = 0.0
        self.freq_error_last = 0.0
        self.filtered_derivative = 0.0
        self.circuit_accumulator = 0.0
        self.power_amp.clear_fault()
        self.synth.reset()
        if self.weather:
            self.weather.reset()


def get_concert_specs() -> dict:
    """Get concert voice specifications for documentation"""
    return {
        'propeller_diameter_mm': 400,
        'propeller_blades': 5,
        'motor_power_w': 500,
        'bus_voltage_v': 48,
        'max_current_a': 20,
        'frequency_range_hz': (110, 220),  # A2 to A3
        'rpm_range': (1320, 2640),
        'estimated_spl_db': 105,
        'pwm_frequency_hz': 20000,
        'weight_kg': 25,  # Estimate for single voice assembly
    }

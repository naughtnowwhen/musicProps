"""
Iris Aperture Volume Control for AeroTone

A mechanical iris (like a camera aperture) controls acoustic output
independent of propeller RPM. This enables expressive dynamics without
affecting pitch.

Physical model:
  - Multi-blade iris mechanism with min/max diameter
  - RC hobby servo for actuation (or DC motor with position feedback)
  - Acoustic attenuation based on aperture area
  - Frequency-dependent rolloff at small apertures
  - Turbulence self-noise at very small openings

Electronics:
  - Servo: PWM control (1-2ms pulse width at 50Hz)
  - Position feedback: internal potentiometer
  - Control voltage input: 0-5V maps to full range

This is the key to musical expression - volume ducking during
pitch transitions creates perceived note boundaries.
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class ServoParams:
    """RC servo motor parameters (typical hobby servo like SG90/MG996R)"""

    # Electrical
    operating_voltage: float = 5.0      # V (4.8-6V typical)
    stall_current: float = 0.8          # A at stall
    idle_current: float = 0.01          # A when holding position

    # Mechanical
    max_torque: float = 0.15            # N·m (1.5 kg·cm typical)
    max_speed: float = 10.0             # rad/s (~60°/0.1s = 100ms for 60°)
    gear_ratio: float = 200.0           # Internal gearing

    # Position control (internal to servo)
    position_gain: float = 50.0         # Internal P gain
    position_deadband: float = 0.01     # rad (~0.5°) - stops hunting

    # Potentiometer feedback
    pot_resistance: float = 5e3         # 5kΩ typical
    pot_range: float = np.pi            # ~180° mechanical range

    # Mechanical dynamics
    output_inertia: float = 1e-6        # kg·m² (output shaft + load)
    friction: float = 0.001             # N·m/(rad/s)
    backlash: float = 0.02              # rad (~1°) gear backlash


class ServoMotor:
    """
    RC Servo Motor model.

    Simulates a hobby servo with:
      - PWM input (1-2ms pulse = 0-180°)
      - Internal position control loop
      - Potentiometer feedback
      - Mechanical dynamics
    """

    def __init__(self, name: str, params: ServoParams = None):
        self.name = name
        self.params = params or ServoParams()

        # State
        self.position = 0.0             # rad (0 = closed, π = full open)
        self.velocity = 0.0             # rad/s
        self.target_position = 0.0      # rad (from PWM input)

        # Electrical state
        self.current = 0.0              # A
        self.pwm_input = 0.0            # 0-1 normalized (maps to 1-2ms)

        # Internal motor state (inside gearbox)
        self.motor_omega = 0.0          # rad/s (motor shaft, pre-gearbox)

    def set_pwm(self, pwm: float):
        """
        Set PWM input (normalized 0-1).

        In real servos:
          - 1.0ms pulse = 0° (closed)
          - 1.5ms pulse = 90° (center)
          - 2.0ms pulse = 180° (full open)

        We normalize: 0.0 = closed, 1.0 = full open
        """
        self.pwm_input = np.clip(pwm, 0.0, 1.0)
        self.target_position = self.pwm_input * self.params.pot_range

    def set_position_normalized(self, pos: float):
        """Set target position (0-1 normalized)"""
        self.set_pwm(pos)

    def update(self, dt: float):
        """Update servo dynamics for one timestep"""
        p = self.params

        # Position error
        error = self.target_position - self.position

        # Deadband (prevents hunting around target)
        if abs(error) < p.position_deadband:
            error = 0.0

        # Internal position controller (P control, typical for hobby servos)
        # This generates a motor drive signal
        motor_drive = error * p.position_gain

        # Clamp to max torque
        motor_drive = np.clip(motor_drive, -1.0, 1.0)

        # Motor torque (simplified DC motor model inside servo)
        motor_torque = motor_drive * p.max_torque

        # Friction
        friction_torque = p.friction * self.velocity

        # Net torque on output shaft
        net_torque = motor_torque - friction_torque - np.sign(self.velocity) * 0.001

        # Acceleration (F = ma, τ = Iα)
        acceleration = net_torque / p.output_inertia

        # Velocity limiting (servo has max speed)
        self.velocity += acceleration * dt
        self.velocity = np.clip(self.velocity, -p.max_speed, p.max_speed)

        # Position update
        self.position += self.velocity * dt
        self.position = np.clip(self.position, 0.0, p.pot_range)

        # Current draw (proportional to torque + idle)
        self.current = p.idle_current + abs(motor_drive) * (p.stall_current - p.idle_current)

    def get_position_normalized(self) -> float:
        """Get current position (0-1)"""
        return self.position / self.params.pot_range

    def get_state(self) -> dict:
        return {
            'position_rad': self.position,
            'position_normalized': self.get_position_normalized(),
            'velocity': self.velocity,
            'target': self.target_position,
            'current': self.current,
        }


@dataclass
class IrisParams:
    """Iris aperture parameters"""

    # Geometry
    max_diameter: float = 0.080         # m (80mm fully open)
    min_diameter: float = 0.008         # m (8mm minimum - not fully closed)
    num_blades: int = 9                 # Blade count (more = rounder opening)

    # Duct geometry (affects acoustics)
    duct_length: float = 0.10           # m (100mm duct section)
    duct_diameter: float = 0.10         # m (100mm duct ID)

    # Acoustic properties
    max_attenuation_db: float = 40.0    # dB at minimum aperture
    hf_rolloff_factor: float = 2.0      # Extra HF attenuation at small apertures

    # Turbulence noise
    turbulence_onset: float = 0.15      # Aperture ratio where turbulence starts
    turbulence_amplitude: float = 0.02  # Max turbulence noise level

    # Servo specs (use defaults or override)
    servo_params: ServoParams = None


class IrisAperture:
    """
    Mechanical iris aperture for volume control.

    Acoustic model:
      - Attenuation ∝ 40·log₁₀(diameter_ratio) dB
      - Additional HF rolloff at small apertures (acts as low-pass)
      - Turbulence noise at very small openings

    The iris is driven by an RC servo, giving realistic response times
    (~100-200ms for full travel) and mechanical behavior.
    """

    def __init__(self, name: str, params: IrisParams = None):
        self.name = name
        self.params = params or IrisParams()
        p = self.params

        # Create servo actuator
        servo_params = p.servo_params or ServoParams()
        self.servo = ServoMotor(f"{name}_servo", servo_params)

        # Acoustic state
        self.attenuation_db = 0.0       # Current attenuation in dB
        self.attenuation_linear = 1.0   # Linear gain (0-1)
        self.hf_attenuation = 1.0       # Additional HF rolloff
        self.turbulence_level = 0.0     # Turbulence noise amplitude

        # For HF rolloff filter
        self.lp_state = 0.0             # Simple 1-pole lowpass state

    def set_aperture(self, normalized: float):
        """
        Set aperture opening (0 = nearly closed, 1 = fully open).

        This commands the servo to move to the target position.
        Actual aperture follows with servo dynamics.
        """
        self.servo.set_position_normalized(normalized)

    def get_aperture(self) -> float:
        """Get current aperture (0-1 normalized)"""
        return self.servo.get_position_normalized()

    def get_diameter(self) -> float:
        """Get current aperture diameter in meters"""
        p = self.params
        aperture = self.get_aperture()
        return p.min_diameter + aperture * (p.max_diameter - p.min_diameter)

    def update(self, dt: float):
        """Update iris mechanics and acoustics"""
        p = self.params

        # Update servo position
        self.servo.update(dt)

        # Current aperture and diameter
        aperture = self.get_aperture()
        diameter = self.get_diameter()

        # === Acoustic attenuation ===
        # Based on area ratio (diameter²)
        # dB = 20·log₁₀(I₁/I₂) = 20·log₁₀(A₁/A₂) = 40·log₁₀(d₁/d₂)

        diameter_ratio = diameter / p.max_diameter
        area_ratio = diameter_ratio ** 2

        # Prevent log(0)
        area_ratio = max(area_ratio, 1e-6)

        # Attenuation in dB (0 dB at full open, negative at smaller apertures)
        self.attenuation_db = 20.0 * np.log10(area_ratio)

        # Clamp to max attenuation
        self.attenuation_db = max(self.attenuation_db, -p.max_attenuation_db)

        # Convert to linear gain
        self.attenuation_linear = 10.0 ** (self.attenuation_db / 20.0)

        # === High-frequency rolloff ===
        # Small apertures act as low-pass filter (larger λ passes, smaller blocked)
        # This creates the "darker" tone when closing, like organ swell
        if aperture < 0.5:
            # Increasing HF attenuation as aperture closes
            self.hf_attenuation = 0.3 + 0.7 * (aperture / 0.5) ** p.hf_rolloff_factor
        else:
            self.hf_attenuation = 1.0

        # === Turbulence noise ===
        # At small apertures, airflow becomes turbulent
        if aperture < p.turbulence_onset:
            # Turbulence increases as aperture decreases
            turb_factor = 1.0 - (aperture / p.turbulence_onset)
            self.turbulence_level = turb_factor * p.turbulence_amplitude
        else:
            self.turbulence_level = 0.0

    def process_audio(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Apply iris acoustic effects to audio.

        Effects:
          1. Volume attenuation based on aperture area (with smooth interpolation)
          2. High-frequency rolloff (darker tone when closing)
          3. Turbulence noise at small apertures
        """
        # Smooth attenuation interpolation to avoid clicks
        if not hasattr(self, '_last_attenuation'):
            self._last_attenuation = self.attenuation_linear

        if len(audio) > 0:
            ramp = np.linspace(self._last_attenuation, self.attenuation_linear, len(audio))
            output = audio * ramp
            self._last_attenuation = self.attenuation_linear
        else:
            output = audio * self.attenuation_linear

        # Apply HF rolloff (simple 1-pole lowpass)
        if self.hf_attenuation < 0.99:
            # Cutoff frequency based on HF attenuation
            # Lower hf_attenuation = lower cutoff
            cutoff = 1000 + 19000 * self.hf_attenuation  # 1kHz - 20kHz
            alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff / sample_rate)

            for i in range(len(output)):
                self.lp_state += alpha * (output[i] - self.lp_state)
                output[i] = self.lp_state

        # Add turbulence noise
        if self.turbulence_level > 0.001:
            # Pink-ish noise (more realistic than white)
            noise = np.random.randn(len(output)) * self.turbulence_level
            # Simple lowpass on noise
            noise_filtered = np.zeros_like(noise)
            state = 0.0
            alpha = 0.1
            for i in range(len(noise)):
                state += alpha * (noise[i] - state)
                noise_filtered[i] = state
            output += noise_filtered

        return output

    def get_state(self) -> dict:
        return {
            'aperture': self.get_aperture(),
            'diameter_mm': self.get_diameter() * 1000,
            'attenuation_db': self.attenuation_db,
            'attenuation_linear': self.attenuation_linear,
            'hf_attenuation': self.hf_attenuation,
            'turbulence_level': self.turbulence_level,
            'servo': self.servo.get_state(),
        }


@dataclass
class ExpressionControllerParams:
    """Expression controller parameters"""

    # Auto-duck during transitions
    duck_enabled: bool = True
    duck_depth: float = 0.4             # How much to duck at valley (0.4 = 40% reduction)
    duck_threshold: float = 1.0         # Hz - minimum transition size to trigger duck
    duck_attack: float = 0.05           # s - time to reach peak duck
    duck_release: float = 0.12          # s - time to release from peak

    # Manual expression smoothing
    expression_smoothing: float = 0.05  # s - time constant for pedal input

    # Output range
    min_output: float = 0.05            # Don't fully close (avoids pops)
    max_output: float = 1.0


class ExpressionController:
    """
    Expression controller for iris aperture.

    ENVELOPE DUCK MODE:
    When pitch target changes, applies a time-based duck envelope:
      - Ramps to peak duck over attack time
      - Ramps back to zero over release time
      - Creates consistent articulation regardless of motor response

    This ensures every note transition gets a volume valley.
    """

    def __init__(self, params: ExpressionControllerParams = None):
        self.params = params or ExpressionControllerParams()

        # Manual expression input (0-1)
        self.expression_input = 1.0     # Default: fully open
        self.expression_smooth = 1.0    # Smoothed value

        # Envelope duck state
        self.duck_amount = 0.0          # Current duck (0 = none, 1 = full duck)
        self.target_frequency = 0.0     # Current target
        self.envelope_time = 0.0        # Time since transition started
        self.envelope_active = False    # Are we in a duck envelope?
        self.last_frequency = 0.0       # For tracking

        # Output
        self.output = 1.0               # Final iris command (0-1)

    def set_expression(self, value: float):
        """Set manual expression input (0-1, like a pedal)"""
        self.expression_input = np.clip(value, 0.0, 1.0)

    def set_target(self, target_freq: float):
        """
        Notify controller of new target frequency.

        Call this when the pitch target changes to start a duck envelope.
        """
        if abs(target_freq - self.target_frequency) > self.params.duck_threshold:
            # New transition - start duck envelope
            self.target_frequency = target_freq
            self.envelope_time = 0.0
            self.envelope_active = True

    def trigger_duck(self):
        """
        Manually trigger a duck envelope.

        Use this for rhythmic articulation - creates note separation
        without requiring a pitch change. Essential for repeated notes.
        """
        self.envelope_time = 0.0
        self.envelope_active = True

    def update(self, dt: float, current_frequency: float):
        """
        Update expression controller.

        Args:
            dt: Time step
            current_frequency: Current actual pitch frequency
        """
        p = self.params

        # === Smooth manual expression ===
        alpha = 1.0 - np.exp(-dt / max(p.expression_smoothing, 0.001))
        self.expression_smooth += alpha * (self.expression_input - self.expression_smooth)

        # === Envelope duck during transitions ===
        if p.duck_enabled and self.envelope_active:
            self.envelope_time += dt

            total_time = p.duck_attack + p.duck_release

            if self.envelope_time < p.duck_attack:
                # Attack phase: ramp up to peak
                t = self.envelope_time / p.duck_attack
                # Smooth curve (sine quarter wave)
                self.duck_amount = np.sin(t * np.pi / 2) * p.duck_depth

            elif self.envelope_time < total_time:
                # Release phase: ramp down from peak
                t = (self.envelope_time - p.duck_attack) / p.duck_release
                # Smooth curve (cosine quarter wave)
                self.duck_amount = np.cos(t * np.pi / 2) * p.duck_depth

            else:
                # Envelope complete
                self.envelope_active = False
                self.duck_amount = 0.0

        else:
            # No envelope, decay any remaining duck
            self.duck_amount *= 0.9

        self.last_frequency = current_frequency

        # === Combine manual expression and auto-duck ===
        duck_multiplier = 1.0 - self.duck_amount
        combined = self.expression_smooth * duck_multiplier

        # Apply output range limits
        self.output = p.min_output + combined * (p.max_output - p.min_output)

    def get_output(self) -> float:
        """Get final iris aperture command (0-1)"""
        return self.output

    def get_state(self) -> dict:
        return {
            'expression_input': self.expression_input,
            'expression_smooth': self.expression_smooth,
            'duck_amount': self.duck_amount,
            'envelope_time': self.envelope_time,
            'envelope_active': self.envelope_active,
            'output': self.output,
        }

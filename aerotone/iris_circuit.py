"""
SPICE-Level Iris Aperture Control for AeroTone

Circuit-level emulation of the iris volume control system with real
component values, matching the fidelity of the motor control circuits.

Circuit topology (1979-era components):

1. EXPRESSION INPUT
   - 10kΩ linear potentiometer (expression pedal)
   - Voltage divider: 0-5V control voltage

2. ENVELOPE GENERATOR (auto-duck)
   - Note change detector (edge detect via RC differentiator)
   - Attack/release shaper (dual RC with diode steering)
   - LM358 op-amp buffer

3. MIXER
   - Analog multiplier/VCA effect
   - Expression × (1 - duck_envelope)
   - Op-amp summer

4. SERVO PWM GENERATOR
   - 555 timer generating 50Hz carrier
   - LM339 comparator for pulse width modulation
   - 1-2ms pulse width range (0° to 180°)

5. SERVO DRIVER
   - BD139/BD140 complementary pair (or small H-bridge)
   - Current limiting resistors
   - Flyback diodes

6. POSITION FEEDBACK
   - 5kΩ potentiometer in servo
   - Voltage follower buffer
   - Error amplifier (servo internal)
"""

import numpy as np
from dataclasses import dataclass


# =============================================================================
# EXPRESSION PEDAL (Potentiometer)
# =============================================================================

@dataclass
class ExpressionPedalParams:
    """Expression pedal potentiometer parameters"""
    resistance: float = 10e3        # 10kΩ linear pot
    wiper_resistance: float = 50.0  # Wiper contact resistance
    v_supply: float = 5.0           # Pedal powered from 5V rail
    travel_range: float = 1.0       # Mechanical travel (normalized)
    taper: str = 'linear'           # 'linear' or 'log'


class ExpressionPedal:
    """
    Expression pedal as a potentiometer voltage divider.

    Circuit:
        V+ ──┬── R_top ──┬── Wiper ──┬── R_bottom ──┬── GND
             │           │           │              │
            5V          Vout        Rwiper         0V
    """

    def __init__(self, name: str, params: ExpressionPedalParams = None):
        self.name = name
        self.params = params or ExpressionPedalParams()

        # State
        self.position = 1.0         # 0-1 (heel=0, toe=1)
        self.output_voltage = self.params.v_supply

    def set_position(self, pos: float):
        """Set pedal position (0 = heel/min, 1 = toe/max)"""
        self.position = np.clip(pos, 0.0, 1.0)

    def update(self, dt: float):
        """Update output voltage based on position"""
        p = self.params

        # Apply taper curve
        if p.taper == 'log':
            # Attempt attempt attempt audio taper: 10% rotation = 50% resistance
            effective_pos = self.position ** 2.2
        else:
            effective_pos = self.position

        # Voltage divider output
        # Vout = V+ × (R_bottom / (R_top + R_bottom))
        # R_bottom = position × total_resistance
        r_bottom = effective_pos * p.resistance
        r_top = (1.0 - effective_pos) * p.resistance

        # Include wiper resistance
        total_r = r_top + p.wiper_resistance + r_bottom
        if total_r > 0:
            self.output_voltage = p.v_supply * (r_bottom / total_r)
        else:
            self.output_voltage = 0.0

    def get_voltage(self) -> float:
        return self.output_voltage


# =============================================================================
# ENVELOPE GENERATOR (Attack/Release Shaper)
# =============================================================================

@dataclass
class EnvelopeGeneratorParams:
    """RC envelope generator parameters"""

    # Attack RC network
    r_attack: float = 10e3          # 10kΩ attack resistor
    c_attack: float = 4.7e-6        # 4.7µF attack capacitor
    # τ_attack = R×C = 47ms

    # Release RC network
    r_release: float = 22e3         # 22kΩ release resistor
    c_release: float = 10e-6        # 10µF release capacitor (shared with attack)
    # τ_release = R×C = 220ms

    # Diode parameters (1N4148 style)
    diode_vf: float = 0.6           # Forward voltage drop

    # Op-amp buffer (LM358)
    opamp_slew_rate: float = 0.5e6  # V/s
    opamp_vsat_high: float = 4.8    # Positive saturation
    opamp_vsat_low: float = 0.1     # Negative saturation

    # Trigger threshold
    trigger_voltage: float = 2.5    # Schmitt trigger threshold

    # Peak envelope voltage
    v_peak: float = 5.0             # Maximum envelope output


class EnvelopeGenerator:
    """
    RC-based attack/release envelope generator.

    When triggered, generates a voltage envelope with:
    - Fast attack (capacitor charges through R_attack + diode)
    - Slower release (capacitor discharges through R_release)

    Circuit:
                          D1 (attack)
        Trigger ──┬──────>|────┬────┐
                  │             │    │
                  │    R_attack │    │ C_envelope
                  │             │    │
                  └── R_release─┴────┴──── Output
                                          (to buffer)

    The diode steers current so charge is fast (through R_attack)
    and discharge is slow (through R_release only).
    """

    def __init__(self, name: str, params: EnvelopeGeneratorParams = None):
        self.name = name
        self.params = params or EnvelopeGeneratorParams()

        # Capacitor state (voltage across envelope cap)
        self.cap_voltage = 0.0

        # Trigger state
        self.trigger_active = False
        self.last_trigger = False

        # Output (buffered)
        self.output_voltage = 0.0

    def trigger(self):
        """Fire the envelope (called on note change)"""
        self.trigger_active = True

    def update(self, dt: float):
        """Update envelope capacitor voltage"""
        p = self.params

        if self.trigger_active:
            # ATTACK: Capacitor charges toward V_peak
            # Through R_attack + diode (fast)
            # τ = R_attack × C_attack
            tau_attack = p.r_attack * p.c_attack

            # Target voltage (minus diode drop)
            v_target = p.v_peak - p.diode_vf

            # RC charge equation: V(t) = V_target × (1 - e^(-t/τ))
            # Differential form: dV/dt = (V_target - V) / τ
            dv = (v_target - self.cap_voltage) / tau_attack * dt
            self.cap_voltage += dv

            # Check if we've reached peak (within 95%)
            if self.cap_voltage >= v_target * 0.95:
                self.trigger_active = False

        else:
            # RELEASE: Capacitor discharges toward 0
            # Through R_release only (slow)
            # τ = R_release × C_release
            tau_release = p.r_release * p.c_release

            # RC discharge: dV/dt = -V / τ
            dv = -self.cap_voltage / tau_release * dt
            self.cap_voltage += dv

        # Clamp
        self.cap_voltage = np.clip(self.cap_voltage, 0.0, p.v_peak)

        # Buffer through op-amp (with slew limiting)
        target_out = self.cap_voltage
        max_slew = p.opamp_slew_rate * dt

        delta = target_out - self.output_voltage
        if abs(delta) > max_slew:
            delta = np.sign(delta) * max_slew
        self.output_voltage += delta

        # Clamp to op-amp rails
        self.output_voltage = np.clip(
            self.output_voltage,
            p.opamp_vsat_low,
            p.opamp_vsat_high
        )

    def get_voltage(self) -> float:
        """Get buffered envelope voltage"""
        return self.output_voltage

    def get_normalized(self) -> float:
        """Get envelope as 0-1 value"""
        return self.output_voltage / self.params.v_peak


# =============================================================================
# ANALOG MIXER (Expression × Duck)
# =============================================================================

@dataclass
class AnalogMixerParams:
    """Analog mixer/VCA parameters"""

    # Input scaling resistors
    r_expression: float = 10e3      # Expression input resistor
    r_envelope: float = 10e3        # Envelope input resistor
    r_feedback: float = 10e3        # Feedback resistor

    # Op-amp (LM358)
    opamp_gain_bandwidth: float = 1e6   # 1 MHz GBW
    opamp_vsat_high: float = 4.8
    opamp_vsat_low: float = 0.1

    # Output scaling
    v_ref: float = 5.0              # Reference for inversion


class AnalogMixer:
    """
    Mixes expression pedal with duck envelope.

    Output = Expression × (1 - Duck_envelope)

    Implemented as:
    1. Inverting envelope: V_inv = Vref - V_envelope
    2. Analog multiply (simplified as voltage-controlled divider)

    For true analog multiply, would use:
    - AD633 analog multiplier, or
    - Gilbert cell, or
    - PWM-based VCA

    We model the effective transfer function.
    """

    def __init__(self, name: str, params: AnalogMixerParams = None):
        self.name = name
        self.params = params or AnalogMixerParams()

        # Inputs
        self.expression_voltage = 5.0
        self.envelope_voltage = 0.0

        # Output
        self.output_voltage = 5.0

    def set_expression(self, voltage: float):
        self.expression_voltage = voltage

    def set_envelope(self, voltage: float):
        self.envelope_voltage = voltage

    def update(self, dt: float):
        """Compute mixed output"""
        p = self.params

        # Duck amount (0-1 from envelope)
        duck = self.envelope_voltage / p.v_ref
        duck = np.clip(duck, 0.0, 1.0)

        # Multiply: output = expression × (1 - duck)
        # This reduces volume when envelope is high
        multiplier = 1.0 - duck

        self.output_voltage = self.expression_voltage * multiplier

        # Clamp to op-amp rails
        self.output_voltage = np.clip(
            self.output_voltage,
            p.opamp_vsat_low,
            p.opamp_vsat_high
        )

    def get_voltage(self) -> float:
        return self.output_voltage


# =============================================================================
# 555 TIMER (Servo PWM Carrier)
# =============================================================================

@dataclass
class Timer555Params:
    """555 timer parameters for servo PWM generation"""

    # Timing resistors and capacitor (astable mode)
    r_a: float = 10e3               # 10kΩ
    r_b: float = 68e3               # 68kΩ
    c_timing: float = 220e-9        # 220nF
    # f ≈ 1.44 / ((R_A + 2×R_B) × C) ≈ 45 Hz (close to 50Hz servo rate)

    # Supply
    v_supply: float = 5.0

    # Output levels
    v_out_high: float = 4.5         # Output high (Vcc - 0.5)
    v_out_low: float = 0.2          # Output low


class Timer555:
    """
    555 timer in astable mode generating servo carrier frequency.

    Circuit (astable):
        Vcc ──┬── R_A ──┬── R_B ──┬──── Discharge (pin 7)
              │         │         │
              │        ─┴─       ─┴─ Threshold (pin 6)
              │        Trigger (pin 2)
              │         │
              │         C
              │         │
             GND ──────┴─────────────

    Generates ~50Hz square wave for servo timing reference.
    """

    def __init__(self, name: str, params: Timer555Params = None):
        self.name = name
        self.params = params or Timer555Params()

        # Internal state
        self.cap_voltage = 0.0
        self.output_high = False
        self.phase = 0.0

        # Calculate frequency
        p = self.params
        self.frequency = 1.44 / ((p.r_a + 2 * p.r_b) * p.c_timing)
        self.period = 1.0 / self.frequency

        # Duty cycle: t_high / period
        # t_high = 0.693 × (R_A + R_B) × C
        # t_low = 0.693 × R_B × C
        t_high = 0.693 * (p.r_a + p.r_b) * p.c_timing
        t_low = 0.693 * p.r_b * p.c_timing
        self.duty_cycle = t_high / (t_high + t_low)

        # Output
        self.output_voltage = p.v_out_low

    def update(self, dt: float):
        """Update 555 oscillator state"""
        p = self.params

        # Advance phase
        self.phase += dt / self.period
        if self.phase >= 1.0:
            self.phase -= 1.0

        # Output based on phase and duty cycle
        if self.phase < self.duty_cycle:
            self.output_high = True
            self.output_voltage = p.v_out_high
        else:
            self.output_high = False
            self.output_voltage = p.v_out_low

    def get_voltage(self) -> float:
        return self.output_voltage

    def get_phase(self) -> float:
        """Get current phase (0-1) for PWM comparison"""
        return self.phase


# =============================================================================
# PWM COMPARATOR (Pulse Width Modulation)
# =============================================================================

@dataclass
class PWMComparatorParams:
    """LM339 comparator for PWM generation"""

    # Ramp generator (sawtooth from 555 timing cap)
    v_ramp_min: float = 0.5         # Ramp minimum
    v_ramp_max: float = 4.5         # Ramp maximum

    # Servo pulse width range
    pw_min: float = 0.001           # 1ms = 0° position
    pw_max: float = 0.002           # 2ms = 180° position

    # Comparator parameters (LM339)
    v_sat_high: float = 4.8
    v_sat_low: float = 0.1
    response_time: float = 1e-6    # 1µs response


class PWMComparator:
    """
    Generates servo PWM signal by comparing control voltage to ramp.

    Circuit:
        Control voltage ──┬──(+)
                          │    LM339 ──── PWM out
        Ramp from 555 ────┴──(-)

    When control > ramp: output high
    When control < ramp: output low

    Higher control voltage = longer pulse = larger servo angle
    """

    def __init__(self, name: str, params: PWMComparatorParams = None):
        self.name = name
        self.params = params or PWMComparatorParams()

        # Inputs
        self.control_voltage = 2.5  # Mid position
        self.ramp_phase = 0.0       # 0-1 from 555

        # Output
        self.output_voltage = 0.0
        self.pulse_active = False

    def set_control(self, voltage: float):
        """Set position control voltage (0-5V)"""
        self.control_voltage = np.clip(voltage, 0.0, 5.0)

    def set_ramp_phase(self, phase: float):
        """Set ramp phase from 555 timer"""
        self.ramp_phase = phase

    def update(self, dt: float):
        """Update comparator output"""
        p = self.params

        # Generate ramp voltage from phase
        ramp_voltage = p.v_ramp_min + self.ramp_phase * (p.v_ramp_max - p.v_ramp_min)

        # Compare: output high when ramp is below control
        # This creates a pulse at the start of each cycle
        # Pulse width proportional to control voltage
        if ramp_voltage < self.control_voltage:
            self.pulse_active = True
            self.output_voltage = p.v_sat_high
        else:
            self.pulse_active = False
            self.output_voltage = p.v_sat_low

    def get_voltage(self) -> float:
        return self.output_voltage

    def get_pulse_active(self) -> bool:
        return self.pulse_active


# =============================================================================
# SERVO DRIVER (H-Bridge with BJTs)
# =============================================================================

@dataclass
class ServoDriverParams:
    """Servo motor driver parameters (BJT H-bridge)"""

    # BJT parameters (BD139/BD140 complementary pair)
    beta: float = 100               # Current gain
    vce_sat: float = 0.3            # Saturation voltage
    vbe: float = 0.7                # Base-emitter voltage

    # Base resistors
    r_base: float = 1e3             # 1kΩ base resistor

    # Current limiting
    r_sense: float = 0.5            # 0.5Ω current sense
    i_limit: float = 0.5            # 500mA limit for small servo

    # Supply
    v_supply: float = 5.0

    # Flyback diodes (1N4001)
    diode_vf: float = 0.7


class ServoDriver:
    """
    BJT H-bridge driver for servo motor.

    Uses BD139 (NPN) and BD140 (PNP) in complementary configuration.

    Simplified model - full H-bridge would have 4 transistors,
    but servo motors typically have internal H-bridge and just
    need PWM drive signal.

    We model the effective drive voltage to the servo motor.
    """

    def __init__(self, name: str, params: ServoDriverParams = None):
        self.name = name
        self.params = params or ServoDriverParams()

        # Input
        self.pwm_input = 0.0        # PWM signal voltage

        # Output
        self.drive_voltage = 0.0    # Voltage to servo
        self.drive_current = 0.0    # Current draw

        # Transistor states
        self.q1_on = False          # High-side switch
        self.q2_on = False          # Low-side switch (for brake)

    def set_pwm(self, voltage: float):
        """Set PWM input signal"""
        self.pwm_input = voltage

    def update(self, dt: float, motor_current: float = 0.0):
        """Update driver output"""
        p = self.params

        # PWM threshold (TTL levels)
        pwm_threshold = 2.0

        if self.pwm_input > pwm_threshold:
            # PWM high - drive active
            self.q1_on = True

            # Output voltage (Vcc - Vce_sat)
            self.drive_voltage = p.v_supply - p.vce_sat

            # Current through sense resistor
            self.drive_current = min(motor_current, p.i_limit)

        else:
            # PWM low - no drive
            self.q1_on = False
            self.drive_voltage = 0.0
            self.drive_current = 0.0

    def get_voltage(self) -> float:
        return self.drive_voltage

    def get_current(self) -> float:
        return self.drive_current


# =============================================================================
# SERVO MOTOR WITH FEEDBACK POT
# =============================================================================

@dataclass
class ServoMotorCircuitParams:
    """Servo motor with position feedback potentiometer

    These are tuned for a FAST servo suitable for musical articulation.
    Balances speed with stability - no oscillation.
    Response time: ~25-35ms for full 180° travel.
    """

    # Motor parameters (fast brushless motor)
    motor_resistance: float = 1.5       # Ω
    motor_inductance: float = 0.1e-3    # H
    motor_ke: float = 0.003             # V/(rad/s)
    motor_kt: float = 0.012             # Nm/A - good torque

    # Mechanical (lightweight, well-damped)
    inertia: float = 2e-8               # kg·m² (light but not extreme)
    friction: float = 8e-6              # Nm/(rad/s) - some damping helps stability
    gear_ratio: float = 30              # Moderate ratio

    # Position limits
    angle_min: float = 0.0              # rad
    angle_max: float = np.pi            # rad (180°)

    # Feedback potentiometer
    pot_resistance: float = 5e3         # 5kΩ
    pot_v_supply: float = 5.0           # Pot reference voltage

    # Internal position controller (inside servo)
    kp: float = 150.0                   # Moderate gain - stable but responsive
    deadband: float = 0.008             # rad - reasonable deadband


class ServoMotorCircuit:
    """
    Servo motor with internal DC motor, gearbox, and feedback pot.

    The servo's internal controller compares:
    - Command pulse width (1-2ms = 0-180°)
    - Feedback pot position

    And drives the motor to minimize error.

    We model this as the actual components would behave.
    """

    def __init__(self, name: str, params: ServoMotorCircuitParams = None):
        self.name = name
        self.params = params or ServoMotorCircuitParams()

        # Motor electrical state
        self.motor_current = 0.0
        self.motor_voltage = 0.0
        self.back_emf = 0.0

        # Mechanical state
        self.position = 0.0             # Output shaft angle (rad)
        self.velocity = 0.0             # Output shaft velocity (rad/s)
        self.motor_omega = 0.0          # Motor shaft velocity (rad/s)

        # Command (from PWM pulse width)
        self.command_position = 0.0     # Desired position (rad)

        # Feedback pot voltage
        self.feedback_voltage = 0.0

    def set_command_from_pulse(self, pulse_width: float):
        """
        Set command position from PWM pulse width.

        Args:
            pulse_width: Pulse width in seconds (0.001 to 0.002)
        """
        p = self.params

        # Map pulse width to angle
        # 1ms = 0°, 2ms = 180°
        pw_min = 0.001
        pw_max = 0.002

        normalized = (pulse_width - pw_min) / (pw_max - pw_min)
        normalized = np.clip(normalized, 0.0, 1.0)

        self.command_position = p.angle_min + normalized * (p.angle_max - p.angle_min)

    def set_command_normalized(self, pos: float):
        """Set command position (0-1)"""
        p = self.params
        pos = np.clip(pos, 0.0, 1.0)
        self.command_position = p.angle_min + pos * (p.angle_max - p.angle_min)

    def update(self, dt: float, supply_voltage: float = 5.0):
        """Update servo motor physics

        Note: Real RC servos have internal power supply to their motor.
        The external PWM signal only tells the servo WHERE to go.
        The internal position controller continuously drives the motor
        to match the commanded position.

        We always use pot_v_supply (5V) as the internal motor supply.
        """
        p = self.params

        # === FEEDBACK POT ===
        # Voltage proportional to position
        pos_normalized = (self.position - p.angle_min) / (p.angle_max - p.angle_min)
        pos_normalized = np.clip(pos_normalized, 0.0, 1.0)
        self.feedback_voltage = pos_normalized * p.pot_v_supply

        # === INTERNAL POSITION CONTROLLER ===
        # Simple P controller with deadband
        error = self.command_position - self.position

        if abs(error) < p.deadband:
            drive_signal = 0.0
        else:
            drive_signal = error * p.kp
            drive_signal = np.clip(drive_signal, -1.0, 1.0)

        # === MOTOR ELECTRICAL ===
        # The servo's internal H-bridge is powered from the servo supply (5V)
        # The drive signal direction and magnitude come from the position error
        internal_supply = p.pot_v_supply  # Servo always has 5V power
        self.motor_voltage = drive_signal * internal_supply

        # Back-EMF
        self.back_emf = p.motor_ke * self.motor_omega

        # Motor current: V = I*R + L*dI/dt + Ke*ω
        # Simplified (ignore inductance for servo speeds)
        if p.motor_resistance > 0:
            self.motor_current = (self.motor_voltage - self.back_emf) / p.motor_resistance
        else:
            self.motor_current = 0.0

        # === MOTOR MECHANICAL ===
        # Torque
        motor_torque = p.motor_kt * self.motor_current

        # Friction
        friction_torque = p.friction * self.motor_omega

        # Motor acceleration
        net_torque = motor_torque - friction_torque
        motor_accel = net_torque / p.inertia

        # Motor velocity
        self.motor_omega += motor_accel * dt

        # Output velocity (through gearbox)
        self.velocity = self.motor_omega / p.gear_ratio

        # Output position
        self.position += self.velocity * dt

        # Position limits
        if self.position < p.angle_min:
            self.position = p.angle_min
            self.velocity = 0.0
            self.motor_omega = 0.0
        elif self.position > p.angle_max:
            self.position = p.angle_max
            self.velocity = 0.0
            self.motor_omega = 0.0

    def get_position_normalized(self) -> float:
        """Get position as 0-1"""
        p = self.params
        return (self.position - p.angle_min) / (p.angle_max - p.angle_min)

    def get_feedback_voltage(self) -> float:
        return self.feedback_voltage


# =============================================================================
# COMPLETE IRIS CIRCUIT
# =============================================================================

@dataclass
class IrisCircuitParams:
    """Complete iris control circuit parameters"""

    # Expression pedal
    pedal_resistance: float = 10e3

    # Envelope generator
    env_r_attack: float = 12e3          # 12kΩ → ~56ms attack with 4.7µF
    env_c: float = 4.7e-6               # 4.7µF envelope cap
    env_r_release: float = 27e3         # 27kΩ → ~127ms release

    # 555 timer (servo PWM carrier)
    timer_r_a: float = 10e3
    timer_r_b: float = 68e3
    timer_c: float = 220e-9             # ~45Hz

    # Servo
    servo_angle_range: float = np.pi    # 180° range

    # Iris geometry (for acoustic model)
    iris_max_diameter: float = 0.080    # 80mm
    iris_min_diameter: float = 0.008    # 8mm

    # Duck depth
    duck_depth: float = 0.45            # 45% reduction at peak


class IrisCircuit:
    """
    Complete SPICE-level iris control circuit.

    Signal flow:
        Expression Pedal (pot) ──┐
                                 │
        Note Change ─→ Envelope ─┴─→ Mixer ─→ PWM Gen ─→ Driver ─→ Servo
                       Generator                                      │
                                                                      │
        Feedback Pot ←────────────────────────────────────────────────┘

    All components modeled with real component values.
    """

    def __init__(self, name: str = "IRIS", params: IrisCircuitParams = None):
        self.name = name
        self.params = params or IrisCircuitParams()
        p = self.params

        # === Create subcircuits ===

        # Expression pedal
        pedal_params = ExpressionPedalParams(
            resistance=p.pedal_resistance,
        )
        self.pedal = ExpressionPedal(f"{name}_PEDAL", pedal_params)

        # Envelope generator
        env_params = EnvelopeGeneratorParams(
            r_attack=p.env_r_attack,
            c_attack=p.env_c,
            r_release=p.env_r_release,
            c_release=p.env_c,
        )
        self.envelope = EnvelopeGenerator(f"{name}_ENV", env_params)

        # Mixer
        self.mixer = AnalogMixer(f"{name}_MIX")

        # 555 Timer
        timer_params = Timer555Params(
            r_a=p.timer_r_a,
            r_b=p.timer_r_b,
            c_timing=p.timer_c,
        )
        self.timer = Timer555(f"{name}_555", timer_params)

        # PWM Comparator
        self.pwm = PWMComparator(f"{name}_PWM")

        # Servo Driver
        self.driver = ServoDriver(f"{name}_DRV")

        # Servo Motor
        servo_params = ServoMotorCircuitParams(
            angle_max=p.servo_angle_range,
        )
        self.servo = ServoMotorCircuit(f"{name}_SERVO", servo_params)

        # === Acoustic model ===
        self.attenuation_db = 0.0
        self.attenuation_linear = 1.0

        # State
        self.last_target_freq = 0.0

    def set_expression(self, value: float):
        """Set expression pedal position (0-1)"""
        self.pedal.set_position(value)

    def trigger_duck(self):
        """Trigger the duck envelope (call on note change)"""
        self.envelope.trigger()

    def notify_frequency_change(self, new_freq: float, threshold: float = 5.0):
        """
        Notify of frequency change to trigger duck.

        Args:
            new_freq: New target frequency
            threshold: Minimum Hz change to trigger
        """
        if abs(new_freq - self.last_target_freq) > threshold:
            self.trigger_duck()
            self.last_target_freq = new_freq

    def update(self, dt: float):
        """Update all circuit components"""
        p = self.params

        # === Update components ===

        # Expression pedal
        self.pedal.update(dt)

        # Envelope generator
        self.envelope.update(dt)

        # Mixer (expression × duck)
        self.mixer.set_expression(self.pedal.get_voltage())
        # Scale envelope by duck depth
        duck_voltage = self.envelope.get_voltage() * p.duck_depth
        self.mixer.set_envelope(duck_voltage)
        self.mixer.update(dt)

        # 555 Timer (PWM carrier)
        self.timer.update(dt)

        # PWM Comparator
        self.pwm.set_control(self.mixer.get_voltage())
        self.pwm.set_ramp_phase(self.timer.get_phase())
        self.pwm.update(dt)

        # Servo Driver
        self.driver.set_pwm(self.pwm.get_voltage())
        self.driver.update(dt, self.servo.motor_current)

        # Servo Motor
        # Map PWM to position command
        self.servo.set_command_normalized(self.mixer.get_voltage() / 5.0)
        self.servo.update(dt, self.driver.get_voltage())

        # === Calculate acoustic attenuation ===
        aperture = self.servo.get_position_normalized()
        diameter = p.iris_min_diameter + aperture * (p.iris_max_diameter - p.iris_min_diameter)

        # dB = 20 × log₁₀(area_ratio) = 40 × log₁₀(diameter_ratio)
        diameter_ratio = diameter / p.iris_max_diameter
        area_ratio = diameter_ratio ** 2
        area_ratio = max(area_ratio, 1e-6)

        self.attenuation_db = 20.0 * np.log10(area_ratio)
        self.attenuation_db = max(self.attenuation_db, -40.0)
        self.attenuation_linear = 10.0 ** (self.attenuation_db / 20.0)

    def get_aperture(self) -> float:
        """Get iris aperture (0-1)"""
        return self.servo.get_position_normalized()

    def get_attenuation_linear(self) -> float:
        """Get volume attenuation as linear gain (0-1)"""
        return self.attenuation_linear

    def get_attenuation_db(self) -> float:
        """Get volume attenuation in dB (negative = quieter)"""
        return self.attenuation_db

    def process_audio(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Apply iris attenuation to audio with smooth interpolation.

        To avoid clicks/pops from sudden attenuation changes, we interpolate
        from the previous attenuation to the current one across the audio chunk.
        This simulates the mechanical iris smoothly opening/closing.
        """
        if not hasattr(self, '_last_attenuation'):
            self._last_attenuation = self.attenuation_linear

        # Interpolate attenuation across the chunk for smooth transitions
        if len(audio) > 0:
            # Create a linear ramp from last attenuation to current
            ramp = np.linspace(self._last_attenuation, self.attenuation_linear, len(audio))
            output = audio * ramp
            self._last_attenuation = self.attenuation_linear
            return output

        return audio * self.attenuation_linear

    def get_state(self) -> dict:
        """Get complete circuit state"""
        return {
            # Inputs
            'pedal_position': self.pedal.position,
            'pedal_voltage': self.pedal.get_voltage(),

            # Envelope
            'envelope_voltage': self.envelope.get_voltage(),
            'envelope_active': self.envelope.trigger_active,

            # Mixer
            'mixer_output': self.mixer.get_voltage(),

            # PWM
            'timer_frequency': self.timer.frequency,
            'pwm_active': self.pwm.get_pulse_active(),

            # Servo
            'servo_position': self.servo.get_position_normalized(),
            'servo_current': self.servo.motor_current,

            # Acoustic
            'aperture': self.get_aperture(),
            'attenuation_db': self.attenuation_db,
            'attenuation_linear': self.attenuation_linear,
        }

    def get_component_values(self) -> dict:
        """Get all component values for documentation"""
        p = self.params
        return {
            'R_pedal': p.pedal_resistance,
            'R_attack': p.env_r_attack,
            'R_release': p.env_r_release,
            'C_envelope': p.env_c,
            'R_555_A': p.timer_r_a,
            'R_555_B': p.timer_r_b,
            'C_555': p.timer_c,
            'f_PWM': self.timer.frequency,
            'tau_attack': p.env_r_attack * p.env_c,
            'tau_release': p.env_r_release * p.env_c,
        }

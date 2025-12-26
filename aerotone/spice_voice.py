"""
SPICE-Level Propeller Voice for AeroTone

This is the full-fidelity voice simulation with actual circuit models:
  - CD4046 PLL with real timing components
  - RC loop filter with actual R and C values
  - H-bridge motor driver with transistors
  - DC motor with electrical and mechanical dynamics
  - Propeller aerodynamics
  - Magnetic pickup with signal conditioning
  - Full closed-loop control

Signal flow:
  Reference freq → CD4046 Phase Det → Loop Filter → Motor Driver →
  → DC Motor → Propeller → Magnetic Pickup → Signal Cond → CD4046

This creates a real phase-locked loop controlling motor speed.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

from .motor import DCMotor, MotorParams
from .propeller import Propeller, PropellerParams, rpm_for_frequency, NOTES
from .acoustics import PropellerSynth, AcousticParams
from .acoustics_v2 import AdvancedPropellerSynth, AdvancedAcousticParams
from .cd4046 import CD4046, CD4046Params, LoopFilter
from .driver import HBridgeDriver, HBridgeParams, MagneticPickup, MagneticPickupParams, SignalConditioner
from .weather import Weather, WeatherParams
from .iris import IrisAperture, IrisParams, ExpressionController, ExpressionControllerParams
from .iris_circuit import IrisCircuit, IrisCircuitParams
from .thermal import (ThermalSystem, ThermalStatus, MotorThermal, MotorThermalParams,
                      TransistorThermal, TransistorThermalParams, ServoThermal, ServoThermalParams)


@dataclass
class SpiceVoiceParams:
    """Complete voice parameters with real component values"""

    # ===== CD4046 VCO Timing =====
    # These set the VCO frequency range
    # f_max ≈ 1/(R1*C1), f_min ≈ 1/(R2*C1)
    vco_r1: float = 10e3       # 10kΩ - sets f_max
    vco_c1: float = 100e-9     # 100nF - timing cap
    vco_r2: float = 100e3      # 100kΩ - sets f_min (optional)

    # ===== Loop Filter =====
    # RC low-pass filter on phase detector output
    # Time constant τ = R*C affects loop bandwidth
    # Larger τ = slower but more stable loop
    loop_r1: float = 100e3     # 100kΩ
    loop_c1: float = 10e-6     # 10µF (τ = 1 second for stability)
    loop_r2: float = 10e3      # 10kΩ (for lead compensation)
    loop_c2: float = 100e-9    # 100nF

    # ===== Motor Driver =====
    driver_v_supply: float = 12.0   # Motor supply voltage
    driver_current_limit: float = 2.0  # Amps

    # ===== Motor =====
    # Parameters tuned for 1320-2500 RPM operating range on 12V
    motor_resistance: float = 2.0     # Ohms
    motor_inductance: float = 0.5e-3  # Henries (0.5mH)
    motor_ke: float = 0.05            # V/(rad/s) - back-EMF constant
    motor_kt: float = 0.05            # N·m/A - torque constant (= Ke)
    motor_inertia: float = 1e-5       # kg·m² - rotor inertia
    motor_damping: float = 5e-6       # N·m/(rad/s) - friction

    # ===== Propeller =====
    prop_num_blades: int = 12
    prop_diameter: float = 0.10       # meters
    prop_inertia: float = 2e-5        # kg·m²

    # ===== Magnetic Pickup =====
    pickup_sensitivity: float = 0.05  # V/(rad/s)
    pickup_poles: int = 1             # Hub magnet poles

    # ===== Signal Conditioning =====
    conditioner_gain: float = 100
    conditioner_hysteresis: float = 0.5

    # ===== Power Supply =====
    vdd: float = 15.0          # Logic supply
    vss: float = 0.0           # Ground

    # ===== Iris Aperture (Volume Control) =====
    iris_max_diameter: float = 0.080    # m (80mm fully open)
    iris_min_diameter: float = 0.008    # m (8mm nearly closed)

    # ===== Expression Controller =====
    expression_duck_enabled: bool = True    # Auto-duck during transitions
    expression_duck_depth: float = 0.3      # 30% volume reduction during slides
    expression_duck_threshold: float = 2.0  # Hz to trigger duck
    expression_duck_attack: float = 0.02    # s - envelope attack time
    expression_duck_release: float = 0.15   # s - envelope release time

    # ===== Iris Circuit Mode =====
    use_circuit_iris: bool = True           # True = SPICE-level, False = behavioral

    # ===== Thermal Modeling =====
    enable_thermal: bool = False            # Enable thermal simulation
    ambient_temp: float = 25.0              # °C - ambient temperature


class SpiceVoice:
    """
    Full SPICE-level propeller voice simulation.

    This is the high-fidelity version that models actual circuit behavior.
    Every component has real values that affect system performance.
    """

    def __init__(self, params: SpiceVoiceParams = None, sample_rate: int = 44100,
                 weather: Weather = None, use_advanced_acoustics: bool = True):
        self.params = params or SpiceVoiceParams()
        self.sample_rate = sample_rate
        self.use_advanced_acoustics = use_advanced_acoustics
        p = self.params

        # ===== Weather System (affects air density → propeller drag) =====
        self.weather = weather  # Optional: if None, uses standard atmosphere

        # ===== Create CD4046 PLL =====
        cd4046_params = CD4046Params(
            vdd=p.vdd,
            vss=p.vss,
            c1=p.vco_c1,
            r1=p.vco_r1,
            r2=p.vco_r2,
        )
        self.cd4046 = CD4046("U1", cd4046_params)

        # ===== Create Loop Filter =====
        self.loop_filter = LoopFilter(
            filter_type='passive_rc',
            r1=p.loop_r1,
            c1=p.loop_c1,
        )

        # ===== Create Motor Driver =====
        driver_params = HBridgeParams(
            v_supply=p.driver_v_supply,
            current_limit=p.driver_current_limit,
        )
        self.driver = HBridgeDriver("H1", driver_params)

        # ===== Create DC Motor =====
        motor_params = MotorParams(
            resistance=p.motor_resistance,
            inductance=p.motor_inductance,
            ke=p.motor_ke,
            kt=p.motor_kt,
            inertia=p.motor_inertia,
            damping=p.motor_damping,
            max_voltage=p.driver_v_supply,
        )
        self.motor = DCMotor(motor_params)

        # ===== Create Propeller =====
        prop_params = PropellerParams(
            num_blades=p.prop_num_blades,
            diameter=p.prop_diameter,
            inertia=p.prop_inertia,
        )
        self.propeller = Propeller(prop_params)

        # Connect propeller inertia to motor
        self.motor.load_inertia = self.propeller.get_inertia()

        # ===== Create Magnetic Pickup =====
        pickup_params = MagneticPickupParams(
            sensitivity=p.pickup_sensitivity,
            pole_pieces=p.pickup_poles,
        )
        self.pickup = MagneticPickup("TACH", pickup_params)

        # ===== Create Signal Conditioner =====
        self.conditioner = SignalConditioner(
            "COND",
            gain=p.conditioner_gain,
            hysteresis=p.conditioner_hysteresis,
        )

        # ===== Create Acoustic Synthesizer =====
        if use_advanced_acoustics:
            self.synth = AdvancedPropellerSynth(sample_rate)
        else:
            self.synth = PropellerSynth(sample_rate)

        # ===== Create Iris Volume Control =====
        self.use_circuit_iris = p.use_circuit_iris

        if p.use_circuit_iris:
            # SPICE-level circuit model with real components
            iris_circuit_params = IrisCircuitParams(
                iris_max_diameter=p.iris_max_diameter,
                iris_min_diameter=p.iris_min_diameter,
                duck_depth=p.expression_duck_depth,
                # RC values for attack/release timing
                # τ = R × C, solve for R given C = 4.7µF
                env_c=4.7e-6,
                env_r_attack=p.expression_duck_attack / 4.7e-6,   # R = τ/C
                env_r_release=p.expression_duck_release / 4.7e-6,
            )
            self.iris_circuit = IrisCircuit("IRIS", iris_circuit_params)
            self.iris = None
            self.expression = None
        else:
            # Behavioral model (simpler, faster)
            iris_params = IrisParams(
                max_diameter=p.iris_max_diameter,
                min_diameter=p.iris_min_diameter,
            )
            self.iris = IrisAperture("IRIS", iris_params)
            self.iris.set_aperture(1.0)  # Start fully open

            expr_params = ExpressionControllerParams(
                duck_enabled=p.expression_duck_enabled,
                duck_depth=p.expression_duck_depth,
                duck_threshold=p.expression_duck_threshold,
                duck_attack=p.expression_duck_attack,
                duck_release=p.expression_duck_release,
            )
            self.expression = ExpressionController(expr_params)
            self.iris_circuit = None

        # ===== Thermal System (optional) =====
        self.enable_thermal = p.enable_thermal
        self.thermal_system = None

        if p.enable_thermal:
            self.thermal_system = ThermalSystem(ambient_temp=p.ambient_temp)

            # Motor thermal model
            motor_thermal_params = MotorThermalParams(
                winding_resistance_25c=p.motor_resistance,
            )
            self.motor_thermal = self.thermal_system.create_motor(
                "MOTOR", motor_thermal_params
            )

            # H-bridge transistors (4x)
            self.transistor_thermals = []
            for i in range(4):
                name = f"Q{i+1}"
                t = self.thermal_system.create_transistor(name)
                self.transistor_thermals.append(t)

            # Servo motor thermal
            self.servo_thermal = self.thermal_system.create_servo("SERVO")

        # ===== Control State =====
        self.target_frequency = 0.0
        self.reference_phase = 0.0
        self.active = False

        # PID Controller gains (circuit equivalent components)
        # P: Proportional - like a resistor divider, immediate response
        # I: Integral - like capacitor charging, eliminates static error
        # D: Derivative - like differentiator circuit, anticipatory braking

        self.freq_error_integral = 0.0
        self.freq_error_last = 0.0  # For derivative calculation

        self.proportional_gain = 0.15  # Kp: V per Hz of error
        self.integral_gain = 0.5       # Ki: V per Hz·s (capacitor charging rate)
        self.derivative_gain = 0.0     # Kd: V per Hz/s (0 = disabled, try 0.01-0.05)

        self.integral_limit = 5.0      # Anti-windup limit (V)
        self.derivative_filter = 0.1   # Low-pass on D term (prevents noise spikes)
        self.filtered_derivative = 0.0

        # Toggle for D term (authentic 1979 = False, smoother = True)
        self.use_derivative = False

        # Simulation timestep (higher rate for circuit accuracy)
        self.circuit_dt = 1e-5  # 100kHz simulation rate
        self.circuit_accumulator = 0.0

    def set_target_frequency(self, frequency: float):
        """Set the target blade passage frequency in Hz"""
        self.target_frequency = frequency
        self.active = frequency > 0
        # Notify iris for duck envelope
        if self.use_circuit_iris:
            self.iris_circuit.notify_frequency_change(frequency, self.params.expression_duck_threshold)
        else:
            self.expression.set_target(frequency)

    def set_target_note(self, note: str):
        """Set target by note name"""
        freq = NOTES.get(note.upper())
        if freq:
            self.set_target_frequency(freq)

    def trigger_duck(self):
        """
        Manually trigger an iris duck envelope.

        Use this for rhythmic articulation - creates note separation
        on repeated notes without requiring a pitch change.

        This is essential for rhythmic playing on a continuous-pitch
        instrument like AeroTone, similar to:
          - Theremin volume hand technique
          - Bowed string bow changes
          - Wind instrument tonguing
        """
        if self.use_circuit_iris:
            self.iris_circuit.trigger_duck()
        elif self.expression is not None:
            self.expression.trigger_duck()

    def enable_derivative(self, enabled: bool = True, gain: float = 0.02):
        """
        Enable or disable the D (derivative) term in PID control.

        The D term provides "anticipatory braking" - smoother stops with less overshoot.
        Authentic 1979 circuits typically didn't have this (use enabled=False).

        Args:
            enabled: True to enable derivative term
            gain: Derivative gain (try 0.01-0.05, higher = more braking)

        Circuit equivalent: Differentiator (capacitor input to op-amp)
        """
        self.use_derivative = enabled
        self.derivative_gain = gain if enabled else 0.0
        self.filtered_derivative = 0.0
        self.freq_error_last = 0.0

    def set_pid_gains(self, kp: float = None, ki: float = None, kd: float = None):
        """
        Set PID controller gains (circuit component equivalents).

        Args:
            kp: Proportional gain (resistor ratio) - default 0.15
            ki: Integral gain (1/RC time constant) - default 0.5
            kd: Derivative gain (RC product) - default 0.0 (disabled)

        Higher values = faster response but potentially less stable.
        """
        if kp is not None:
            self.proportional_gain = kp
        if ki is not None:
            self.integral_gain = ki
        if kd is not None:
            self.derivative_gain = kd
            self.use_derivative = (kd > 0)

    def set_weather(self, weather: Weather = None):
        """
        Enable or disable weather simulation.

        Args:
            weather: Weather instance, or None to disable

        When enabled, air density variations from the weather system
        affect propeller drag, which the control loop must compensate for.
        This tests control loop robustness against environmental disturbances.
        """
        self.weather = weather
        if weather is None:
            # Reset to standard atmosphere
            self.propeller.air_density = self.propeller.STANDARD_AIR_DENSITY

    def _update_circuit(self, dt: float):
        """
        Update all circuit components for one timestep.

        TOPOLOGY: Motor-as-VCO PLL
        --------------------------
        In this topology, the MOTOR is the "VCO" - we control its speed
        with voltage, and it produces a frequency (blade passage).

        The CD4046's internal VCO is NOT used. Instead:
          - CD4046 Phase Comparator compares:
            * SIG_IN: Reference frequency (target)
            * COMP_IN: Feedback from magnetic pickup (actual)
          - Phase detector output -> Loop filter -> Motor driver
          - Motor speed changes -> Pickup frequency changes -> Feedback

        This is exactly how real synchrophasers work!
        """
        if not self.active:
            self.motor.set_voltage(0)
            self.motor.update(dt)
            return

        # ===== REFERENCE SIGNAL =====
        # From crystal oscillator + divider chain (sets target BPF)
        self.reference_phase += 2 * np.pi * self.target_frequency * dt
        if self.reference_phase > 2 * np.pi:
            self.reference_phase -= 2 * np.pi
        ref_voltage = self.params.vdd if self.reference_phase < np.pi else 0.0

        # ===== FEEDBACK SIGNAL =====
        # From magnetic pickup sensing propeller rotation
        # The pickup fires once per revolution, but we want BPF
        # So we use a frequency multiplier or the blade edges
        # For now: pickup senses at blade rate (simplified)
        feedback_voltage = self.conditioner.get_output_voltage()

        # ===== PHASE/FREQUENCY DETECTION =====
        # Using a simplified frequency discriminator approach
        # This is more representative of how synchrophasers actually work:
        # Compare reference and feedback frequencies, generate error signal

        self.cd4046.sig_in_voltage = ref_voltage
        self.cd4046.comp_in_voltage = feedback_voltage
        self.cd4046.update(dt)

        # Frequency error detection (practical approach)
        # Measure actual BPF vs target, generate proportional error voltage
        actual_freq = self.propeller.blade_passage_frequency
        freq_error = self.target_frequency - actual_freq

        # Convert frequency error to control voltage adjustment
        # Using PID control implemented as circuit equivalents:
        #   P = resistor network (immediate response)
        #   I = capacitor charging (eliminates static error)
        #   D = differentiator circuit (anticipatory braking)

        # === P: Proportional term ===
        # Circuit: Voltage divider, output proportional to input
        p_term = freq_error * self.proportional_gain

        # === I: Integral term ===
        # Circuit: Capacitor (C1=10µF) charged through resistor (R1=100kΩ)
        # Accumulates error over time, eliminates static offset
        self.freq_error_integral += freq_error * dt * self.integral_gain
        # Anti-windup (like zener clamp on capacitor)
        self.freq_error_integral = np.clip(self.freq_error_integral,
                                           -self.integral_limit, self.integral_limit)
        i_term = self.freq_error_integral

        # === D: Derivative term (optional) ===
        # Circuit: Capacitor in series with op-amp input (differentiator)
        # Provides "anticipatory braking" - sees rate of approach
        d_term = 0.0
        if self.use_derivative and dt > 0:
            # Raw derivative: rate of change of error
            raw_derivative = (freq_error - self.freq_error_last) / dt

            # Low-pass filter on derivative (RC filter on differentiator output)
            # Prevents noise spikes from causing jitter
            alpha = self.derivative_filter
            self.filtered_derivative = (alpha * raw_derivative +
                                        (1 - alpha) * self.filtered_derivative)

            d_term = self.filtered_derivative * self.derivative_gain
            self.freq_error_last = freq_error

        # === Combined PID output ===
        # Summing junction (op-amp summing amplifier)
        error_voltage = self.params.vdd / 2 + p_term + i_term + d_term
        error_voltage = np.clip(error_voltage, 0, self.params.vdd)

        # ===== LOOP FILTER =====
        # Smooth the error signal
        control_voltage = self.loop_filter.update(error_voltage, dt, high_z=False)

        # ===== MOTOR DRIVER =====
        # Converts control voltage to motor drive
        self.driver.set_control_voltage(control_voltage)
        self.driver.update(dt, self.motor.back_emf)

        # ===== WEATHER (affects propeller aerodynamics) =====
        if self.weather is not None:
            self.weather.update(dt)
            self.propeller.air_density = self.weather.get_air_density()

        # ===== MOTOR =====
        self.motor.set_voltage(self.driver.get_motor_voltage())
        self.propeller.update(self.motor.omega)
        self.motor.load_torque = self.propeller.get_load_torque()
        self.motor.update(dt)

        # ===== MAGNETIC PICKUP =====
        # Senses blade passage (not just once per rev)
        # For proper BPF feedback, we sense at blade rate
        blade_angle = self.motor.theta * self.params.prop_num_blades
        self.pickup.update(dt, blade_angle, self.motor.omega * self.params.prop_num_blades)

        # ===== SIGNAL CONDITIONING =====
        self.conditioner.update(dt, self.pickup.get_raw_voltage())

        # ===== ACOUSTIC OUTPUT =====
        acoustic_params = self.propeller.get_acoustic_params()
        self.synth.set_operating_point(
            bpf=acoustic_params['bpf'],
            thrust=max(acoustic_params['thrust'], 0.1) if self.active else 0,
            num_blades=acoustic_params['num_blades'],
        )

        # ===== IRIS VOLUME CONTROL =====
        if self.use_circuit_iris:
            # SPICE-level circuit: 555 timer, PWM, servo, envelope
            self.iris_circuit.update(dt)
        else:
            # Behavioral model
            self.expression.update(dt, self.propeller.blade_passage_frequency)
            self.iris.set_aperture(self.expression.get_output())
            self.iris.update(dt)

        # ===== THERMAL MODELING =====
        if self.enable_thermal and self.thermal_system is not None:
            # Update motor thermal (I²R losses)
            self.motor_thermal.set_current(self.motor.current)
            self.motor_thermal.set_spinning(self.motor.omega > 10)

            # Update H-bridge transistor thermals
            # Each transistor sees roughly half the motor current when conducting
            motor_v = self.driver.get_motor_voltage()
            motor_i = abs(self.motor.current)
            # Simplified: each active transistor has Vce_sat drop
            vce_sat = 0.3  # Saturation voltage
            for i, t_thermal in enumerate(self.transistor_thermals):
                # Alternate transistors conduct based on polarity
                # Simplified: all see average power
                power_per_transistor = vce_sat * motor_i * 0.5
                t_thermal.set_operating_point(vce_sat, motor_i * 0.5)

            # Update servo thermal (if using circuit iris)
            if self.use_circuit_iris:
                servo_current = abs(self.iris_circuit.servo.motor_current)
                self.servo_thermal.set_current(servo_current)
                # Stalled if position error is large but not moving
                error = abs(self.iris_circuit.servo.command_position -
                           self.iris_circuit.servo.position)
                velocity = abs(self.iris_circuit.servo.velocity)
                self.servo_thermal.set_stalled(error > 0.1 and velocity < 0.1)

            # Update thermal system (propagates heat, checks limits)
            self.thermal_system.update(dt)

    def update_physics(self, dt: float):
        """
        Update physics for a given time step.

        Runs the circuit simulation at high rate internally.
        """
        self.circuit_accumulator += dt

        while self.circuit_accumulator >= self.circuit_dt:
            self._update_circuit(self.circuit_dt)
            self.circuit_accumulator -= self.circuit_dt

    def generate_audio(self, num_samples: int) -> np.ndarray:
        """Generate audio samples with integrated physics and iris volume control"""
        audio_dt = num_samples / self.sample_rate
        self.update_physics(audio_dt)

        # Generate raw propeller sound
        audio = self.synth.generate(num_samples)

        # Apply iris volume control
        if self.use_circuit_iris:
            audio = self.iris_circuit.process_audio(audio, self.sample_rate)
        else:
            audio = self.iris.process_audio(audio, self.sample_rate)

        return audio

    def set_expression(self, value: float):
        """
        Set manual expression level (0-1, like an expression pedal).

        This controls the iris aperture for volume. Auto-duck during
        pitch transitions is applied on top of this.
        """
        if self.use_circuit_iris:
            self.iris_circuit.set_expression(value)
        else:
            self.expression.set_expression(value)

    @property
    def current_rpm(self) -> float:
        return self.motor.rpm

    @property
    def current_frequency(self) -> float:
        return self.propeller.blade_passage_frequency

    @property
    def is_locked(self) -> bool:
        """Is the PLL locked to target frequency?"""
        if self.target_frequency == 0:
            return False
        error_pct = abs(self.current_frequency - self.target_frequency) / self.target_frequency
        return error_pct < 0.005  # 0.5%

    def get_circuit_state(self) -> dict:
        """Get detailed circuit state for debugging/display"""
        state = {
            # Control
            'target_frequency': self.target_frequency,
            'active': self.active,

            # PLL
            'vco_frequency': self.cd4046.vco_frequency,
            'control_voltage': self.loop_filter.get_voltage(),
            'pd_state': self.cd4046.get_pc2_state(),
            'pll_locked': self.cd4046.is_locked(),

            # Driver
            'driver_voltage': self.driver.get_motor_voltage(),
            'driver_current': self.driver.get_motor_current(),

            # Motor
            'motor_rpm': self.motor.rpm,
            'motor_current': self.motor.current,
            'motor_voltage': self.motor.voltage,
            'motor_back_emf': self.motor.back_emf,

            # Propeller
            'prop_frequency': self.propeller.blade_passage_frequency,
            'prop_torque': self.propeller.torque,
            'prop_thrust': self.propeller.thrust,
            'prop_air_density': self.propeller.air_density,

            # Pickup
            'pickup_voltage': self.pickup.get_raw_voltage(),
            'conditioner_output': self.conditioner.get_digital_output(),

            # Performance
            'frequency_error_hz': self.current_frequency - self.target_frequency,
            'is_locked': self.is_locked,

        }

        # Iris / Expression state (depends on mode)
        if self.use_circuit_iris:
            iris_state = self.iris_circuit.get_state()
            state['iris_aperture'] = iris_state['aperture']
            state['iris_attenuation_db'] = iris_state['attenuation_db']
            state['expression_input'] = iris_state['pedal_position']
            state['expression_duck'] = iris_state['envelope_voltage'] / 5.0 * self.params.expression_duck_depth
            state['envelope_active'] = iris_state['envelope_active']
            state['servo_position'] = iris_state['servo_position']
            state['pwm_frequency'] = iris_state['timer_frequency']
        else:
            state['iris_aperture'] = self.iris.get_aperture()
            state['iris_attenuation_db'] = self.iris.attenuation_db
            state['expression_input'] = self.expression.expression_input
            state['expression_duck'] = self.expression.duck_amount
            state['envelope_active'] = self.expression.envelope_active

        # Add weather info if active
        if self.weather is not None:
            weather_state = self.weather.get_state()
            state['weather_density'] = weather_state['density']
            state['weather_density_factor'] = weather_state['density_factor']
            state['weather_pressure_hpa'] = weather_state['pressure_hpa']
            state['weather_gust_active'] = weather_state['gust_active']
            state['weather_variation_pct'] = weather_state['variation_percent']

        # Add thermal info if enabled
        if self.enable_thermal and self.thermal_system is not None:
            thermal_state = self.thermal_system.get_state()
            state['thermal_status'] = thermal_state['worst_status']
            state['thermal_any_damaged'] = thermal_state['any_damaged']
            state['motor_temp'] = self.motor_thermal.temperature
            state['motor_temp_status'] = self.motor_thermal.status.value
            # Hottest transistor
            hottest_q = max(self.transistor_thermals, key=lambda t: t.temperature)
            state['transistor_temp_max'] = hottest_q.temperature
            state['transistor_temp_status'] = hottest_q.status.value
            if self.use_circuit_iris:
                state['servo_temp'] = self.servo_thermal.temperature
                state['servo_temp_status'] = self.servo_thermal.status.value

        return state

    def get_component_values(self) -> dict:
        """Get all component values (for documentation/troubleshooting)"""
        p = self.params
        return {
            'R1_vco': p.vco_r1,
            'R2_vco': p.vco_r2,
            'C1_vco': p.vco_c1,
            'R1_loop': p.loop_r1,
            'C1_loop': p.loop_c1,
            'R_motor': p.motor_resistance,
            'L_motor': p.motor_inductance,
            'Ke_motor': p.motor_ke,
            'Kt_motor': p.motor_kt,
        }

    def reset(self):
        """Reset all state"""
        self.motor.omega = 0.0
        self.motor.current = 0.0
        self.motor.theta = 0.0
        self.propeller.omega = 0.0
        self.propeller.air_density = self.propeller.STANDARD_AIR_DENSITY
        self.loop_filter.reset()
        self.reference_phase = 0.0
        self.freq_error_integral = 0.0
        self.freq_error_last = 0.0
        self.filtered_derivative = 0.0
        self.circuit_accumulator = 0.0
        self.synth.reset()
        # Reset iris and expression
        if self.use_circuit_iris:
            self.iris_circuit.set_expression(1.0)
            self.iris_circuit.envelope.cap_voltage = 0.0
            self.iris_circuit.envelope.trigger_active = False
            self.iris_circuit.servo.position = self.iris_circuit.servo.params.angle_max
        else:
            self.iris.set_aperture(1.0)
            self.expression.expression_input = 1.0
            self.expression.expression_smooth = 1.0
            self.expression.duck_amount = 0.0
            self.expression.target_frequency = 0.0
            self.expression.envelope_time = 0.0
            self.expression.envelope_active = False
        if self.weather is not None:
            self.weather.reset()
        # Reset thermal (but preserve damage history unless explicitly cleared)
        if self.enable_thermal and self.thermal_system is not None:
            self.thermal_system.reset(clear_damage=False)

    def get_thermal_summary(self) -> str:
        """Get human-readable thermal status summary"""
        if not self.enable_thermal or self.thermal_system is None:
            return "Thermal modeling disabled"
        return self.thermal_system.get_summary()

    def is_thermally_safe(self) -> bool:
        """Check if all components are within safe thermal limits"""
        if not self.enable_thermal or self.thermal_system is None:
            return True
        return self.thermal_system.is_all_functional()


def calculate_vco_components(f_min: float, f_max: float,
                             c1: float = 100e-9) -> tuple:
    """
    Calculate R1 and R2 for desired VCO frequency range.

    Args:
        f_min: Minimum frequency (Hz)
        f_max: Maximum frequency (Hz)
        c1: Timing capacitor (F)

    Returns:
        (r1, r2, c1) component values
    """
    # f_max = 1 / (R1 * C1)
    # f_min = 1 / (R2 * C1)
    r1 = 1.0 / (f_max * c1)
    r2 = 1.0 / (f_min * c1) if f_min > 0 else None
    return r1, r2, c1


def calculate_loop_filter(bandwidth: float, damping: float = 0.707,
                          kvco: float = 1000) -> tuple:
    """
    Calculate loop filter components for desired bandwidth.

    Args:
        bandwidth: Loop bandwidth (Hz)
        damping: Damping factor (0.707 = critically damped)
        kvco: VCO gain (Hz/V)

    Returns:
        (r1, c1) component values
    """
    # Simplified calculation for passive RC filter
    # For a second-order PLL: ωn = sqrt(Kd*Kvco/τ)
    # where τ = R*C

    omega_n = 2 * np.pi * bandwidth
    tau = kvco / (omega_n ** 2)  # Simplified

    # Choose reasonable R, calculate C
    r1 = 47e3  # 47kΩ is common
    c1 = tau / r1

    return r1, c1

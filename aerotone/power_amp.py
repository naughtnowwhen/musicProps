"""
Power Amplifier Stage for Concert-Scale AeroTone

This module models the high-power electronics needed to drive large motors
for concert-level acoustic output:

  - MOSFET H-bridge (4× power MOSFETs like IRFP260)
  - Gate drivers with bootstrap (IR2110-style)
  - PWM generation (20kHz, above audible)
  - Current sensing and limiting
  - Thermal modeling with heatsink
  - Protection circuits (overcurrent, overtemp, shoot-through)

Signal chain:
  Control voltage (0-10V from PLL) → PWM generator → Gate drivers →
  → MOSFET H-bridge → Motor (48V, up to 20A)

Power ratings:
  - Bus voltage: 48V DC
  - Continuous current: 15A (720W)
  - Peak current: 25A (1.2kW)
  - Switching frequency: 20kHz
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class FaultType(Enum):
    """Power amplifier fault conditions"""
    NONE = 0
    OVERCURRENT = 1
    OVERTEMP = 2
    SHOOT_THROUGH = 3
    UNDERVOLTAGE = 4
    GATE_FAULT = 5


@dataclass
class PowerMOSFETParams:
    """Power MOSFET parameters (e.g., IRFP260N)"""

    # On-state
    rds_on: float = 0.04          # Ω - on resistance at 25°C
    rds_on_temp_coeff: float = 0.005  # Ω/°C - temperature coefficient

    # Switching
    turn_on_delay: float = 15e-9   # seconds
    rise_time: float = 75e-9       # seconds
    turn_off_delay: float = 45e-9  # seconds
    fall_time: float = 45e-9       # seconds

    # Gate
    vgs_threshold: float = 4.0     # V - gate threshold
    gate_charge: float = 180e-9    # C - total gate charge

    # Thermal
    max_tj: float = 175            # °C - max junction temp
    rth_jc: float = 0.4            # °C/W - junction to case

    # Ratings
    vds_max: float = 200           # V
    id_max: float = 50             # A continuous at 25°C
    id_pulse: float = 200          # A pulse


@dataclass
class GateDriverParams:
    """Gate driver parameters (e.g., IR2110)"""

    # Output drive
    high_side_output_current: float = 2.0   # A peak
    low_side_output_current: float = 2.0    # A peak

    # Timing
    turn_on_propagation: float = 120e-9     # seconds
    turn_off_propagation: float = 94e-9     # seconds
    deadtime: float = 520e-9                # seconds (built-in)

    # Bootstrap
    bootstrap_voltage: float = 15.0         # V
    bootstrap_cap: float = 1e-6             # F (1µF typical)

    # Protection
    undervoltage_lockout: float = 8.5       # V


@dataclass
class PowerAmpParams:
    """Complete power amplifier parameters"""

    # Power bus
    v_bus: float = 48.0              # V DC bus voltage
    v_bus_min: float = 40.0          # V minimum before UVLO

    # Current limits
    current_limit: float = 20.0      # A - continuous limit
    current_peak: float = 30.0       # A - peak/transient limit
    current_sense_gain: float = 50   # V/V - sense amplifier gain
    sense_resistor: float = 0.005    # Ω - current sense shunt

    # PWM
    pwm_frequency: float = 20000     # Hz - switching frequency
    min_duty: float = 0.02           # Minimum duty cycle
    max_duty: float = 0.98           # Maximum duty cycle

    # Thermal (sized for 500W continuous)
    heatsink_rth: float = 0.15       # °C/W - large heatsink for concert use
    ambient_temp: float = 25.0       # °C
    fan_threshold: float = 45.0      # °C - turn on fan early
    shutdown_temp: float = 100.0     # °C - thermal shutdown (higher with big heatsink)

    # Control
    control_voltage_max: float = 10.0  # V - max control input


class PowerMOSFET:
    """
    Power MOSFET model with thermal effects.

    Models:
      - On-resistance (temperature dependent)
      - Switching losses
      - Conduction losses
      - Junction temperature
    """

    def __init__(self, name: str, params: PowerMOSFETParams = None):
        self.name = name
        self.params = params or PowerMOSFETParams()

        # State
        self.gate_voltage = 0.0
        self.drain_current = 0.0
        self.is_on = False

        # Thermal
        self.junction_temp = 25.0
        self.power_dissipation = 0.0

        # Switching state machine
        self.switching_state = 'off'  # off, turning_on, on, turning_off
        self.switching_timer = 0.0

    @property
    def rds_on_actual(self) -> float:
        """Temperature-adjusted on-resistance"""
        p = self.params
        temp_factor = 1 + p.rds_on_temp_coeff * (self.junction_temp - 25)
        return p.rds_on * max(1.0, temp_factor)

    def set_gate(self, voltage: float):
        """Set gate voltage"""
        self.gate_voltage = voltage

    def update(self, dt: float, drain_voltage: float, load_current: float):
        """
        Update MOSFET state.

        Args:
            dt: Time step
            drain_voltage: Voltage across drain-source when off
            load_current: Current through device when on
        """
        p = self.params

        # Gate threshold logic
        gate_on = self.gate_voltage > p.vgs_threshold

        # Simple switching model (ignoring detailed timing for now)
        self.is_on = gate_on

        if self.is_on:
            self.drain_current = load_current
            # Conduction losses: I²R
            self.power_dissipation = load_current ** 2 * self.rds_on_actual
        else:
            self.drain_current = 0.0
            self.power_dissipation = 0.0

        # Add switching losses (simplified)
        # P_sw = 0.5 * V * I * (t_rise + t_fall) * f_sw
        # This is averaged over time, added during transitions

    def get_voltage_drop(self) -> float:
        """Voltage drop across MOSFET when on"""
        if self.is_on:
            return self.drain_current * self.rds_on_actual
        return 0.0


class GateDriver:
    """
    Half-bridge gate driver (IR2110 style).

    Drives high-side and low-side MOSFETs with:
      - Level shifting for high side
      - Bootstrap supply
      - Deadtime insertion
      - Undervoltage lockout
    """

    def __init__(self, name: str, params: GateDriverParams = None):
        self.name = name
        self.params = params or GateDriverParams()

        # Inputs
        self.hin = False  # High-side input
        self.lin = False  # Low-side input

        # Outputs
        self.ho = 0.0     # High-side output voltage
        self.lo = 0.0     # Low-side output voltage

        # Bootstrap
        self.bootstrap_voltage = params.bootstrap_voltage if params else 15.0
        self.bootstrap_charged = True

        # State
        self.fault = False
        self.deadtime_active = False
        self.deadtime_timer = 0.0

        # Previous states for edge detection
        self.hin_last = False
        self.lin_last = False

    def set_inputs(self, hin: bool, lin: bool):
        """Set gate driver inputs"""
        self.hin = hin
        self.lin = lin

    def update(self, dt: float, vcc: float, vs_voltage: float = 0.0):
        """
        Update gate driver outputs.

        Args:
            dt: Time step
            vcc: Logic supply voltage
            vs_voltage: High-side source voltage (for bootstrap)
        """
        p = self.params

        # Undervoltage lockout
        if vcc < p.undervoltage_lockout:
            self.ho = 0.0
            self.lo = 0.0
            self.fault = True
            return

        self.fault = False

        # Deadtime insertion
        # Detect edges
        hin_rising = self.hin and not self.hin_last
        lin_rising = self.lin and not self.lin_last
        hin_falling = not self.hin and self.hin_last
        lin_falling = not self.lin and self.lin_last

        # If any edge, start deadtime
        if hin_rising or lin_rising or hin_falling or lin_falling:
            self.deadtime_active = True
            self.deadtime_timer = p.deadtime

        # Count down deadtime
        if self.deadtime_active:
            self.deadtime_timer -= dt
            if self.deadtime_timer <= 0:
                self.deadtime_active = False

        # Output logic with deadtime
        if self.deadtime_active:
            # During deadtime, both outputs low (prevent shoot-through)
            self.ho = 0.0
            self.lo = 0.0
        else:
            # Normal operation
            self.ho = (vs_voltage + self.bootstrap_voltage) if self.hin else vs_voltage
            self.lo = p.bootstrap_voltage if self.lin else 0.0

        # Bootstrap charging (when low-side on)
        if self.lin and not self.hin:
            self.bootstrap_charged = True

        # Save for edge detection
        self.hin_last = self.hin
        self.lin_last = self.lin


class PWMGenerator:
    """
    PWM generator for motor control.

    Converts control voltage to PWM duty cycle.
    Generates complementary outputs for H-bridge.
    """

    def __init__(self, frequency: float = 20000, deadtime: float = 500e-9):
        self.frequency = frequency
        self.period = 1.0 / frequency
        self.deadtime = deadtime

        # State
        self.phase = 0.0
        self.duty_cycle = 0.0

        # Outputs (active high)
        self.pwm_a = False   # High-side A / Low-side B
        self.pwm_b = False   # High-side B / Low-side A

        # For center-aligned PWM
        self.counting_up = True
        self.counter = 0.0

    def set_duty_cycle(self, duty: float):
        """Set duty cycle (0.0 to 1.0)"""
        self.duty_cycle = np.clip(duty, 0.0, 1.0)

    def set_control_voltage(self, voltage: float, v_max: float = 10.0):
        """Set duty cycle from control voltage"""
        self.duty_cycle = np.clip(voltage / v_max, 0.0, 1.0)

    def update(self, dt: float):
        """
        Update PWM outputs.

        Uses center-aligned PWM for reduced harmonics.
        """
        # Update counter (triangle wave, center-aligned)
        counter_delta = dt / (self.period / 2)

        if self.counting_up:
            self.counter += counter_delta
            if self.counter >= 1.0:
                self.counter = 1.0
                self.counting_up = False
        else:
            self.counter -= counter_delta
            if self.counter <= 0.0:
                self.counter = 0.0
                self.counting_up = True

        # Compare with duty cycle
        # PWM A is on when counter < duty
        # PWM B is complementary (on when counter >= duty)
        self.pwm_a = self.counter < self.duty_cycle
        self.pwm_b = not self.pwm_a

    def get_outputs(self) -> tuple:
        """Get PWM outputs as (pwm_a, pwm_b)"""
        return self.pwm_a, self.pwm_b


class CurrentSenseAmp:
    """
    Current sense amplifier (e.g., INA240).

    Measures motor current through low-side shunt resistor.
    Provides overcurrent detection.
    """

    def __init__(self, sense_resistor: float = 0.005, gain: float = 50):
        self.sense_resistor = sense_resistor  # Ω
        self.gain = gain                       # V/V

        # Output
        self.output_voltage = 0.0
        self.measured_current = 0.0

        # Filtering (for noise rejection)
        self.filter_tau = 10e-6   # 10µs filter
        self.filtered_voltage = 0.0

        # Overcurrent detection
        self.overcurrent_threshold = 2.5  # V (corresponds to I_limit)
        self.overcurrent = False

    def update(self, dt: float, current: float):
        """
        Update current measurement.

        Args:
            dt: Time step
            current: Actual motor current (A)
        """
        # Sense voltage across shunt
        v_sense = abs(current) * self.sense_resistor

        # Amplify
        self.output_voltage = v_sense * self.gain

        # Filter
        alpha = dt / (self.filter_tau + dt)
        self.filtered_voltage += alpha * (self.output_voltage - self.filtered_voltage)

        # Calculate current
        self.measured_current = self.filtered_voltage / self.gain / self.sense_resistor

        # Overcurrent detection
        self.overcurrent = self.filtered_voltage > self.overcurrent_threshold


class ThermalModel:
    """
    Thermal model for power stage.

    Models heat flow:
      Junction → Case → Heatsink → Ambient
    """

    def __init__(self,
                 rth_jc: float = 0.4,      # Junction to case (°C/W)
                 rth_ch: float = 0.1,      # Case to heatsink (°C/W)
                 rth_ha: float = 0.15,     # Heatsink to ambient (°C/W) - large heatsink
                 cth_j: float = 0.5,       # Junction thermal capacitance (J/°C)
                 cth_h: float = 200.0):    # Heatsink thermal capacitance (J/°C) - large mass

        self.rth_jc = rth_jc
        self.rth_ch = rth_ch
        self.rth_ha = rth_ha
        self.cth_j = cth_j
        self.cth_h = cth_h

        # Temperatures
        self.t_junction = 25.0
        self.t_case = 25.0
        self.t_heatsink = 25.0
        self.t_ambient = 25.0

        # Fan
        self.fan_on = False
        self.fan_rth_reduction = 0.5  # Fan reduces rth_ha by 50%

    def update(self, dt: float, power_dissipation: float, ambient: float = 25.0):
        """
        Update thermal state.

        Args:
            dt: Time step
            power_dissipation: Total power dissipated in junction (W)
            ambient: Ambient temperature (°C)
        """
        self.t_ambient = ambient

        # Effective heatsink thermal resistance
        rth_ha_eff = self.rth_ha * (self.fan_rth_reduction if self.fan_on else 1.0)

        # Heat flow equations (simplified RC thermal network)
        # Q = ΔT / Rth
        # dT/dt = Q / Cth

        # Junction to case
        q_jc = (self.t_junction - self.t_case) / self.rth_jc

        # Case to heatsink
        q_ch = (self.t_case - self.t_heatsink) / self.rth_ch

        # Heatsink to ambient
        q_ha = (self.t_heatsink - self.t_ambient) / rth_ha_eff

        # Temperature changes
        # Junction: gains power_dissipation, loses q_jc
        dt_junction = (power_dissipation - q_jc) * dt / self.cth_j
        self.t_junction += dt_junction

        # Heatsink: gains q_ch (approximately), loses q_ha
        dt_heatsink = (q_ch - q_ha) * dt / self.cth_h
        self.t_heatsink += dt_heatsink

        # Case tracks between junction and heatsink
        self.t_case = self.t_junction - q_jc * self.rth_jc


class PowerAmplifier:
    """
    Complete power amplifier stage.

    Integrates:
      - PWM generator
      - Gate drivers (×2 for full H-bridge)
      - Power MOSFETs (×4)
      - Current sensing
      - Thermal management
      - Protection logic

    Topology:
                      +48V Bus
                         │
              ┌──────────┼──────────┐
              │          │          │
           [Q1 HS]       │       [Q3 HS]
              │          │          │
              ├────[MOTOR]──────────┤
              │          │          │
           [Q2 LS]       │       [Q4 LS]
              │          │          │
              └────┬─────┴─────┬────┘
                   │           │
                [SHUNT]     [SHUNT]
                   │           │
                  GND         GND
    """

    def __init__(self, name: str = "PA1", params: PowerAmpParams = None):
        self.name = name
        self.params = params or PowerAmpParams()
        p = self.params

        # === PWM Generator ===
        self.pwm = PWMGenerator(
            frequency=p.pwm_frequency,
            deadtime=520e-9
        )

        # === Gate Drivers ===
        gate_params = GateDriverParams()
        self.gate_driver_a = GateDriver(f"{name}_GD_A", gate_params)
        self.gate_driver_b = GateDriver(f"{name}_GD_B", gate_params)

        # === Power MOSFETs ===
        mosfet_params = PowerMOSFETParams()
        self.q1_hs = PowerMOSFET(f"{name}_Q1", mosfet_params)  # High-side A
        self.q2_ls = PowerMOSFET(f"{name}_Q2", mosfet_params)  # Low-side A
        self.q3_hs = PowerMOSFET(f"{name}_Q3", mosfet_params)  # High-side B
        self.q4_ls = PowerMOSFET(f"{name}_Q4", mosfet_params)  # Low-side B

        # === Current Sensing ===
        self.current_sense = CurrentSenseAmp(
            sense_resistor=p.sense_resistor,
            gain=p.current_sense_gain
        )

        # === Thermal Model ===
        self.thermal = ThermalModel(
            rth_jc=0.4,    # Per MOSFET
            rth_ha=p.heatsink_rth
        )

        # === State ===
        self.control_voltage = 0.0
        self.motor_voltage = 0.0
        self.motor_current = 0.0
        self.bus_voltage = p.v_bus

        # === Protection ===
        self.fault = FaultType.NONE
        self.fault_latched = False
        self.enabled = True

        # === Statistics ===
        self.total_power_dissipation = 0.0
        self.efficiency = 0.0

    def set_control_voltage(self, voltage: float):
        """
        Set control voltage from PLL loop filter.

        Args:
            voltage: Control voltage (0 to 10V typically)
        """
        self.control_voltage = np.clip(voltage, 0, self.params.control_voltage_max)

    def set_bus_voltage(self, voltage: float):
        """Set DC bus voltage"""
        self.bus_voltage = voltage

    def enable(self, state: bool = True):
        """Enable or disable the power stage"""
        self.enabled = state
        if not state:
            self.fault_latched = False
            self.fault = FaultType.NONE

    def clear_fault(self):
        """Clear latched fault"""
        self.fault_latched = False
        self.fault = FaultType.NONE

    def update(self, dt: float, motor_back_emf: float = 0.0,
               motor_current: float = 0.0):
        """
        Update power amplifier state.

        Args:
            dt: Time step
            motor_back_emf: Motor back-EMF voltage
            motor_current: Actual motor current (for current sensing)
        """
        p = self.params

        # === Protection Checks ===
        if self.fault_latched:
            self._shutdown()
            return

        # Undervoltage
        if self.bus_voltage < p.v_bus_min:
            self.fault = FaultType.UNDERVOLTAGE
            self.fault_latched = True
            self._shutdown()
            return

        # Overtemperature
        if self.thermal.t_junction > p.shutdown_temp:
            self.fault = FaultType.OVERTEMP
            self.fault_latched = True
            self._shutdown()
            return

        # Overcurrent
        if self.current_sense.overcurrent:
            self.fault = FaultType.OVERCURRENT
            # Don't latch - allow recovery
            self._limit_current()

        if not self.enabled:
            self._shutdown()
            return

        # === PWM Generation ===
        # Convert control voltage to duty cycle
        duty = self.control_voltage / p.control_voltage_max
        duty = np.clip(duty, p.min_duty, p.max_duty)
        self.pwm.set_duty_cycle(duty)
        self.pwm.update(dt)

        pwm_a, pwm_b = self.pwm.get_outputs()

        # === Gate Drivers ===
        # Driver A controls Q1 (HS) and Q2 (LS)
        # Driver B controls Q3 (HS) and Q4 (LS)
        # For forward drive: Q1+Q4 on, Q2+Q3 off when pwm_a=True
        #                   Q2+Q3 on, Q1+Q4 off when pwm_b=True

        self.gate_driver_a.set_inputs(hin=pwm_a, lin=pwm_b)
        self.gate_driver_b.set_inputs(hin=pwm_b, lin=pwm_a)

        self.gate_driver_a.update(dt, vcc=15.0, vs_voltage=0.0)
        self.gate_driver_b.update(dt, vcc=15.0, vs_voltage=0.0)

        # === MOSFET Switching ===
        self.q1_hs.set_gate(self.gate_driver_a.ho)
        self.q2_ls.set_gate(self.gate_driver_a.lo)
        self.q3_hs.set_gate(self.gate_driver_b.ho)
        self.q4_ls.set_gate(self.gate_driver_b.lo)

        # Update MOSFETs
        self.q1_hs.update(dt, self.bus_voltage, motor_current)
        self.q2_ls.update(dt, self.bus_voltage, motor_current)
        self.q3_hs.update(dt, self.bus_voltage, motor_current)
        self.q4_ls.update(dt, self.bus_voltage, motor_current)

        # === Calculate Motor Voltage ===
        # When Q1+Q4 on: V_motor = V_bus - Vds_Q1 - Vds_Q4
        # When Q2+Q3 on: V_motor = -(V_bus - Vds_Q2 - Vds_Q3)

        if self.q1_hs.is_on and self.q4_ls.is_on:
            drops = self.q1_hs.get_voltage_drop() + self.q4_ls.get_voltage_drop()
            self.motor_voltage = self.bus_voltage - drops
        elif self.q2_ls.is_on and self.q3_hs.is_on:
            drops = self.q2_ls.get_voltage_drop() + self.q3_hs.get_voltage_drop()
            self.motor_voltage = -(self.bus_voltage - drops)
        else:
            # Freewheeling or deadtime
            self.motor_voltage = 0.0

        # Average motor voltage (for DC motor, PWM averages out)
        # Use duty cycle for average
        avg_voltage = duty * (self.bus_voltage - 0.1)  # 0.1V for drops
        self.motor_voltage = avg_voltage

        # === Current Sensing ===
        self.current_sense.update(dt, motor_current)
        self.motor_current = motor_current

        # === Power Dissipation ===
        # Sum of all MOSFET conduction losses
        p_q1 = self.q1_hs.power_dissipation
        p_q2 = self.q2_ls.power_dissipation
        p_q3 = self.q3_hs.power_dissipation
        p_q4 = self.q4_ls.power_dissipation

        self.total_power_dissipation = p_q1 + p_q2 + p_q3 + p_q4

        # Add switching losses (simplified estimate)
        # P_sw ≈ f_sw * V * I * (t_rise + t_fall)
        t_sw = 120e-9  # Total switching time
        p_switching = p.pwm_frequency * self.bus_voltage * abs(motor_current) * t_sw
        self.total_power_dissipation += p_switching

        # === Thermal Update ===
        self.thermal.update(dt, self.total_power_dissipation, p.ambient_temp)

        # Fan control
        self.thermal.fan_on = self.thermal.t_heatsink > p.fan_threshold

        # Update junction temps on MOSFETs
        self.q1_hs.junction_temp = self.thermal.t_junction
        self.q2_ls.junction_temp = self.thermal.t_junction
        self.q3_hs.junction_temp = self.thermal.t_junction
        self.q4_ls.junction_temp = self.thermal.t_junction

        # === Efficiency Calculation ===
        p_out = abs(self.motor_voltage * motor_current)
        p_in = self.bus_voltage * abs(motor_current)
        if p_in > 0:
            self.efficiency = p_out / p_in
        else:
            self.efficiency = 0.0

    def _shutdown(self):
        """Emergency shutdown - all gates off"""
        self.motor_voltage = 0.0
        self.q1_hs.is_on = False
        self.q2_ls.is_on = False
        self.q3_hs.is_on = False
        self.q4_ls.is_on = False

    def _limit_current(self):
        """Reduce duty cycle to limit current"""
        # Reduce control voltage proportionally
        if self.motor_current > self.params.current_limit:
            reduction = self.params.current_limit / self.motor_current
            self.pwm.set_duty_cycle(self.pwm.duty_cycle * reduction)

    def get_motor_voltage(self) -> float:
        """Get output voltage to motor"""
        return self.motor_voltage

    def get_state(self) -> dict:
        """Get complete power amplifier state"""
        return {
            'control_voltage': self.control_voltage,
            'motor_voltage': self.motor_voltage,
            'motor_current': self.motor_current,
            'duty_cycle': self.pwm.duty_cycle,
            'bus_voltage': self.bus_voltage,
            'power_dissipation': self.total_power_dissipation,
            'efficiency': self.efficiency,
            't_junction': self.thermal.t_junction,
            't_heatsink': self.thermal.t_heatsink,
            'fan_on': self.thermal.fan_on,
            'fault': self.fault.name,
            'enabled': self.enabled,
            'q1_on': self.q1_hs.is_on,
            'q2_on': self.q2_ls.is_on,
            'q3_on': self.q3_hs.is_on,
            'q4_on': self.q4_ls.is_on,
        }

    def get_component_count(self) -> dict:
        """Get component count for this power amp stage"""
        return {
            'mosfets': 4,
            'gate_drivers': 2,
            'shunt_resistors': 2,
            'bootstrap_caps': 2,
            'bootstrap_diodes': 2,
            'bulk_caps': 2,
            'sense_amp': 1,
            'comparator': 1,
            'logic_ics': 1,
            'total': 17,
        }

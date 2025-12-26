"""
DC Motor Model for AeroTone

Simulates a brushed DC motor with back-EMF, friction, and inertia.
Period-appropriate for 1979: simple brushed DC motor.

Motor equations:
  V = I*R + L*dI/dt + Ke*omega  (electrical)
  J*d(omega)/dt = Kt*I - B*omega - T_load  (mechanical)

Where:
  V = applied voltage
  I = armature current
  R = armature resistance
  L = armature inductance
  Ke = back-EMF constant (V/(rad/s))
  Kt = torque constant (N·m/A), equals Ke for ideal motor
  J = moment of inertia (motor + propeller)
  B = viscous damping coefficient
  omega = angular velocity (rad/s)
  T_load = load torque from propeller
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class MotorParams:
    """DC Motor parameters - typical small brushed motor circa 1979"""

    # Electrical
    resistance: float = 2.0          # Ohms - armature resistance
    inductance: float = 0.001        # Henries - armature inductance
    ke: float = 0.01                 # V/(rad/s) - back-EMF constant
    kt: float = 0.01                 # N·m/A - torque constant (= ke for ideal)

    # Mechanical
    inertia: float = 5e-6            # kg·m² - rotor inertia (prop adds more)
    damping: float = 1e-6            # N·m/(rad/s) - viscous friction

    # Limits
    max_voltage: float = 12.0        # V - maximum applied voltage
    max_current: float = 3.0         # A - current limit

    # Thermal (simplified)
    thermal_resistance: float = 5.0  # °C/W - thermal resistance to ambient
    max_temp: float = 85.0           # °C - maximum winding temperature


class DCMotor:
    """
    Brushed DC motor simulation.

    State variables:
      - current: armature current (A)
      - omega: angular velocity (rad/s)
      - theta: angular position (rad)
      - temperature: winding temperature (°C)
    """

    def __init__(self, params: MotorParams = None):
        self.params = params or MotorParams()

        # State
        self.current = 0.0      # A
        self.omega = 0.0        # rad/s
        self.theta = 0.0        # rad
        self.temperature = 25.0 # °C (ambient)

        # Input
        self.voltage = 0.0      # Applied voltage

        # External load
        self.load_torque = 0.0  # N·m from propeller
        self.load_inertia = 0.0 # kg·m² from propeller

    @property
    def rpm(self) -> float:
        """Angular velocity in RPM"""
        return self.omega * 60.0 / (2.0 * np.pi)

    @rpm.setter
    def rpm(self, value: float):
        """Set angular velocity from RPM"""
        self.omega = value * 2.0 * np.pi / 60.0

    @property
    def total_inertia(self) -> float:
        """Total moment of inertia (motor + load)"""
        return self.params.inertia + self.load_inertia

    @property
    def back_emf(self) -> float:
        """Back-EMF voltage"""
        return self.params.ke * self.omega

    @property
    def torque(self) -> float:
        """Electrical torque produced"""
        return self.params.kt * self.current

    @property
    def power_dissipated(self) -> float:
        """Power dissipated as heat (I²R)"""
        return self.current ** 2 * self.params.resistance

    def set_voltage(self, voltage: float):
        """Set applied voltage (clamped to limits)"""
        self.voltage = np.clip(voltage, -self.params.max_voltage,
                               self.params.max_voltage)

    def update(self, dt: float):
        """
        Update motor state using forward Euler integration.

        Args:
            dt: time step in seconds
        """
        p = self.params

        # Electrical dynamics: L * dI/dt = V - I*R - Ke*omega
        if p.inductance > 0:
            di_dt = (self.voltage - self.current * p.resistance -
                     self.back_emf) / p.inductance
            self.current += di_dt * dt
        else:
            # Quasi-static (no inductance): I = (V - Ke*omega) / R
            self.current = (self.voltage - self.back_emf) / p.resistance

        # Current limiting
        self.current = np.clip(self.current, -p.max_current, p.max_current)

        # Mechanical dynamics: J * d(omega)/dt = Kt*I - B*omega - T_load
        torque_net = (self.torque - p.damping * self.omega - self.load_torque)
        domega_dt = torque_net / self.total_inertia
        self.omega += domega_dt * dt

        # Can't go negative (no regenerative braking in this simple model)
        self.omega = max(0.0, self.omega)

        # Update position
        self.theta += self.omega * dt
        self.theta = self.theta % (2.0 * np.pi)  # Wrap to [0, 2π)

        # Simple thermal model (first-order lag)
        power = self.power_dissipated
        temp_rise = power * p.thermal_resistance
        target_temp = 25.0 + temp_rise
        tau_thermal = 30.0  # seconds - thermal time constant
        self.temperature += (target_temp - self.temperature) * dt / tau_thermal

    def get_state(self) -> dict:
        """Return current state as dictionary"""
        return {
            'current': self.current,
            'omega': self.omega,
            'rpm': self.rpm,
            'theta': self.theta,
            'voltage': self.voltage,
            'back_emf': self.back_emf,
            'torque': self.torque,
            'temperature': self.temperature,
            'load_torque': self.load_torque,
        }


class SimplePIDController:
    """
    Simple PID controller for motor speed control.

    This is a placeholder before implementing the full CD4046 PLL.
    In the real AeroTone, this would be a phase-locked loop.
    """

    def __init__(self, kp: float = 0.05, ki: float = 0.5, kd: float = 0.001):
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.integral = 0.0
        self.last_error = 0.0
        self.target_rpm = 0.0

        # Anti-windup
        self.integral_limit = 50.0

    def set_target(self, target_rpm: float):
        """Set target RPM"""
        self.target_rpm = target_rpm

    def update(self, current_rpm: float, dt: float) -> float:
        """
        Compute control output.

        Returns:
            Control voltage (0 to 12V)
        """
        error = self.target_rpm - current_rpm

        # Proportional
        p_term = self.kp * error

        # Integral with anti-windup
        self.integral += error * dt
        self.integral = np.clip(self.integral, -self.integral_limit,
                                self.integral_limit)
        i_term = self.ki * self.integral

        # Derivative
        d_term = self.kd * (error - self.last_error) / dt if dt > 0 else 0
        self.last_error = error

        # Sum and clamp to valid voltage range
        output = p_term + i_term + d_term
        return np.clip(output, 0.0, 12.0)

    def reset(self):
        """Reset controller state"""
        self.integral = 0.0
        self.last_error = 0.0

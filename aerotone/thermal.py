"""
Thermal Modeling for AeroTone

Models heat generation, dissipation, and temperature-dependent behavior
for realistic circuit simulation and failure mode detection.

Thermal physics:
  - Heat generation: P = I²R (resistive) or P = V×I (dissipation)
  - Heat flow: Q = ΔT / R_th (thermal resistance)
  - Temperature rise: dT/dt = (P_in - P_out) / C_th (thermal mass)

Temperature-dependent effects:
  - Copper resistance: R(T) = R_25 × (1 + α × (T - 25°C))
  - Transistor gain decreases at high temperature
  - Component ratings define maximum safe temperatures

This enables:
  - Realistic long-term operation modeling
  - Over-stress detection (burnt components)
  - Test bench failure scenarios
  - Component rating validation
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum


class ThermalStatus(Enum):
    """Component thermal status"""
    NORMAL = "normal"           # Within safe operating range
    WARNING = "warning"         # Approaching limits (>80% of max)
    CRITICAL = "critical"       # Near damage threshold (>95% of max)
    DAMAGED = "damaged"         # Exceeded max, permanent damage
    DESTROYED = "destroyed"     # Catastrophic failure


@dataclass
class ThermalParams:
    """Base thermal parameters for any component"""

    # Thermal characteristics
    thermal_mass: float = 1.0           # J/°C (heat capacity)
    thermal_resistance: float = 10.0    # °C/W (to ambient)

    # Temperature limits
    max_temp: float = 150.0             # °C - maximum safe temperature
    warning_temp: float = 100.0         # °C - warning threshold
    ambient_temp: float = 25.0          # °C - ambient/heatsink temp

    # Damage modeling
    damage_threshold: float = 150.0     # °C - permanent damage begins
    destruction_temp: float = 200.0     # °C - catastrophic failure

    # Temperature coefficient (for resistance)
    temp_coefficient: float = 0.00393   # 1/°C (copper = 0.00393)


class ThermalNode:
    """
    Basic thermal simulation node.

    Models a component as a thermal mass that:
      - Receives heat from power dissipation
      - Dissipates heat to ambient through thermal resistance
      - Has temperature-dependent characteristics

    Thermal equivalent circuit:

        P_dissipated       R_thermal
           ─┬─────────────/\/\/\──────┬─── T_ambient
            │                         │
           ─┴─                       ─┴─
           ─┬─ C_thermal             GND
            │   (thermal mass)
            │
          T_component
    """

    def __init__(self, name: str, params: ThermalParams = None):
        self.name = name
        self.params = params or ThermalParams()

        # State
        self.temperature = self.params.ambient_temp
        self.power_dissipated = 0.0

        # Damage accumulation
        self.damage_integral = 0.0      # Accumulated thermal damage
        self.status = ThermalStatus.NORMAL
        self.peak_temperature = self.params.ambient_temp
        self.time_over_limit = 0.0      # Seconds spent over max

        # History (for diagnostics)
        self.temp_history: List[float] = []
        self.max_history_len = 1000

    def set_power(self, power: float):
        """Set instantaneous power dissipation in Watts"""
        self.power_dissipated = max(0.0, power)

    def update(self, dt: float, ambient_temp: float = None):
        """
        Update temperature for one timestep.

        Args:
            dt: Time step in seconds
            ambient_temp: Ambient temperature (uses default if None)
        """
        p = self.params

        if ambient_temp is not None:
            current_ambient = ambient_temp
        else:
            current_ambient = p.ambient_temp

        # Heat flow to ambient: Q = ΔT / R_thermal
        delta_t = self.temperature - current_ambient
        heat_flow_out = delta_t / p.thermal_resistance  # Watts

        # Net heat: P_in - P_out
        net_heat = self.power_dissipated - heat_flow_out  # Watts

        # Temperature change: dT = Q × dt / C_thermal
        temp_change = net_heat * dt / p.thermal_mass
        self.temperature += temp_change

        # Clamp to physical limits (can't go below ambient passively)
        # (Active cooling could go below, but we don't model that)

        # Track peak
        if self.temperature > self.peak_temperature:
            self.peak_temperature = self.temperature

        # Update status
        self._update_status(dt)

        # Record history
        self.temp_history.append(self.temperature)
        if len(self.temp_history) > self.max_history_len:
            self.temp_history.pop(0)

    def _update_status(self, dt: float):
        """Update thermal status and damage accumulation"""
        p = self.params

        if self.status == ThermalStatus.DESTROYED:
            return  # No recovery from destruction

        if self.temperature >= p.destruction_temp:
            self.status = ThermalStatus.DESTROYED
            return

        if self.temperature >= p.damage_threshold:
            self.status = ThermalStatus.DAMAGED
            # Accumulate damage (time-temperature integral)
            excess = self.temperature - p.damage_threshold
            self.damage_integral += excess * dt
            self.time_over_limit += dt
            return

        if self.temperature >= p.max_temp * 0.95:
            self.status = ThermalStatus.CRITICAL
            self.time_over_limit += dt
            return

        if self.temperature >= p.warning_temp:
            self.status = ThermalStatus.WARNING
            return

        self.status = ThermalStatus.NORMAL

    def get_resistance_factor(self) -> float:
        """
        Get resistance multiplier due to temperature.

        Copper resistance increases with temperature:
        R(T) = R_25 × (1 + α × (T - 25))

        Returns:
            Multiplier to apply to room-temperature resistance
        """
        p = self.params
        delta_t = self.temperature - 25.0
        return 1.0 + p.temp_coefficient * delta_t

    def is_functional(self) -> bool:
        """Is the component still functional?"""
        return self.status not in [ThermalStatus.DESTROYED]

    def reset(self, ambient_temp: float = None):
        """Reset to ambient temperature"""
        if ambient_temp is not None:
            self.temperature = ambient_temp
            self.params.ambient_temp = ambient_temp
        else:
            self.temperature = self.params.ambient_temp

        self.power_dissipated = 0.0
        self.status = ThermalStatus.NORMAL
        self.peak_temperature = self.temperature
        self.time_over_limit = 0.0
        # Note: damage_integral is NOT reset (permanent damage)
        self.temp_history.clear()

    def get_state(self) -> dict:
        return {
            'name': self.name,
            'temperature': self.temperature,
            'power_dissipated': self.power_dissipated,
            'status': self.status.value,
            'peak_temperature': self.peak_temperature,
            'time_over_limit': self.time_over_limit,
            'damage_integral': self.damage_integral,
            'resistance_factor': self.get_resistance_factor(),
            'is_functional': self.is_functional(),
        }


# =============================================================================
# COMPONENT-SPECIFIC THERMAL MODELS
# =============================================================================

@dataclass
class MotorThermalParams(ThermalParams):
    """DC Motor thermal parameters"""

    # Motor-specific
    winding_resistance_25c: float = 2.0     # Ω at 25°C
    thermal_mass: float = 50.0              # J/°C (motor has significant mass)
    thermal_resistance: float = 5.0         # °C/W (some airflow from rotation)

    # Temperature limits (motor windings)
    max_temp: float = 130.0                 # °C - Class B insulation
    warning_temp: float = 100.0             # °C
    damage_threshold: float = 150.0         # °C - insulation breakdown
    destruction_temp: float = 180.0         # °C - winding failure

    # Copper windings
    temp_coefficient: float = 0.00393       # Copper


class MotorThermal(ThermalNode):
    """
    DC Motor thermal model.

    Heat generated by:
      - I²R losses in windings (primary)
      - Brush friction (minor)
      - Core losses (minor at our frequencies)

    Cooling from:
      - Convection (enhanced when spinning)
      - Conduction to mounting
    """

    def __init__(self, name: str, params: MotorThermalParams = None):
        self.motor_params = params or MotorThermalParams()
        super().__init__(name, self.motor_params)

        # Motor-specific state
        self.current = 0.0
        self.is_spinning = False

    def set_current(self, current: float):
        """Set motor current in Amps"""
        self.current = abs(current)

    def set_spinning(self, spinning: bool):
        """Set whether motor is spinning (affects cooling)"""
        self.is_spinning = spinning

    def update(self, dt: float, ambient_temp: float = None):
        """Update motor temperature"""
        p = self.motor_params

        # Calculate winding resistance at current temperature
        r_winding = p.winding_resistance_25c * self.get_resistance_factor()

        # Power dissipation: P = I²R
        self.power_dissipated = self.current ** 2 * r_winding

        # Adjust thermal resistance based on spinning (airflow cooling)
        if self.is_spinning:
            # Spinning motor has better cooling (fan effect)
            effective_r_thermal = p.thermal_resistance * 0.6
        else:
            # Stalled motor - worst case cooling
            effective_r_thermal = p.thermal_resistance * 1.5

        # Temporarily adjust params for base class update
        original_r_th = self.params.thermal_resistance
        self.params.thermal_resistance = effective_r_thermal

        super().update(dt, ambient_temp)

        self.params.thermal_resistance = original_r_th

    def get_winding_resistance(self) -> float:
        """Get current winding resistance (temperature-adjusted)"""
        return self.motor_params.winding_resistance_25c * self.get_resistance_factor()

    def get_state(self) -> dict:
        state = super().get_state()
        state.update({
            'current': self.current,
            'is_spinning': self.is_spinning,
            'winding_resistance': self.get_winding_resistance(),
            'i2r_losses': self.power_dissipated,
        })
        return state


@dataclass
class TransistorThermalParams(ThermalParams):
    """Power transistor thermal parameters"""

    # TO-220 or TO-3 package typical values
    thermal_mass: float = 2.0               # J/°C (small but significant)

    # Thermal resistances (°C/W)
    r_junction_case: float = 1.5            # Junction to case (from datasheet)
    r_case_heatsink: float = 0.5            # Case to heatsink (with compound)
    r_heatsink_ambient: float = 5.0         # Heatsink to ambient

    # Junction temperature limits
    max_temp: float = 150.0                 # °C - typical silicon max Tj
    warning_temp: float = 100.0             # °C
    damage_threshold: float = 150.0         # °C - parameter degradation
    destruction_temp: float = 175.0         # °C - junction failure

    # Secondary breakdown (not fully modeled)
    max_power: float = 50.0                 # W - absolute max with heatsink

    def __post_init__(self):
        # Compute total thermal resistance from path components
        self.thermal_resistance = (self.r_junction_case +
                                   self.r_case_heatsink +
                                   self.r_heatsink_ambient)


class TransistorThermal(ThermalNode):
    """
    Power transistor (BJT/MOSFET) thermal model.

    Models junction temperature based on:
      - Power dissipation: P = Vce × Ic (or Vds × Id)
      - Thermal path: Junction → Case → Heatsink → Ambient

    Temperature affects:
      - Current gain (β decreases at high temp for BJT)
      - On-resistance (increases for MOSFET)
      - Leakage current (increases exponentially)
    """

    def __init__(self, name: str, params: TransistorThermalParams = None):
        self.transistor_params = params or TransistorThermalParams()
        # Set thermal_resistance from the property
        base_params = ThermalParams(
            thermal_mass=self.transistor_params.thermal_mass,
            thermal_resistance=self.transistor_params.thermal_resistance,
            max_temp=self.transistor_params.max_temp,
            warning_temp=self.transistor_params.warning_temp,
            damage_threshold=self.transistor_params.damage_threshold,
            destruction_temp=self.transistor_params.destruction_temp,
        )
        super().__init__(name, base_params)

        # Transistor-specific
        self.vce = 0.0          # Collector-emitter voltage
        self.ic = 0.0           # Collector current
        self.beta_25c = 100.0   # Current gain at 25°C

    def set_operating_point(self, vce: float, ic: float):
        """Set transistor operating point"""
        self.vce = abs(vce)
        self.ic = abs(ic)

        # Power dissipation
        self.power_dissipated = self.vce * self.ic

    def get_beta(self) -> float:
        """
        Get current gain adjusted for temperature.

        BJT beta typically decreases at high temperature
        (though there's a complex relationship - increases
        then decreases)
        """
        # Simplified model: beta decreases above 100°C
        if self.temperature > 100:
            reduction = (self.temperature - 100) / 100  # 1% per °C above 100
            return self.beta_25c * (1.0 - reduction * 0.5)
        return self.beta_25c

    def is_in_soa(self) -> bool:
        """Check if operating within Safe Operating Area"""
        p = self.transistor_params

        # Simple SOA check (real SOA is more complex)
        if self.power_dissipated > p.max_power:
            return False
        if self.temperature > p.max_temp:
            return False
        return True

    def get_state(self) -> dict:
        state = super().get_state()
        state.update({
            'vce': self.vce,
            'ic': self.ic,
            'beta': self.get_beta(),
            'in_soa': self.is_in_soa(),
        })
        return state


@dataclass
class RegulatorThermalParams(ThermalParams):
    """Voltage regulator thermal parameters (78xx/79xx series)"""

    # TO-220 package
    thermal_mass: float = 3.0               # J/°C

    # Thermal resistances
    r_junction_case: float = 3.0            # °C/W (78xx typical)
    r_case_heatsink: float = 0.5            # °C/W
    r_heatsink_ambient: float = 4.0         # °C/W (small heatsink)

    # Limits
    max_temp: float = 125.0                 # °C - internal thermal shutdown
    warning_temp: float = 100.0             # °C
    damage_threshold: float = 150.0         # °C
    destruction_temp: float = 175.0         # °C

    # Regulator specs
    dropout_voltage: float = 2.0            # V - minimum Vin - Vout
    thermal_shutdown_temp: float = 150.0    # °C - internal protection

    def __post_init__(self):
        # Compute total thermal resistance from path components
        self.thermal_resistance = (self.r_junction_case +
                                   self.r_case_heatsink +
                                   self.r_heatsink_ambient)


class RegulatorThermal(ThermalNode):
    """
    Linear voltage regulator thermal model.

    Power dissipation:
      P = (Vin - Vout) × Iload

    Linear regulators dissipate excess voltage as heat,
    making them prone to thermal issues under high load
    or high input voltage.
    """

    def __init__(self, name: str, v_out: float,
                 params: RegulatorThermalParams = None):
        self.regulator_params = params or RegulatorThermalParams()
        base_params = ThermalParams(
            thermal_mass=self.regulator_params.thermal_mass,
            thermal_resistance=self.regulator_params.thermal_resistance,
            max_temp=self.regulator_params.max_temp,
            warning_temp=self.regulator_params.warning_temp,
            damage_threshold=self.regulator_params.damage_threshold,
            destruction_temp=self.regulator_params.destruction_temp,
        )
        super().__init__(name, base_params)

        self.v_out = v_out
        self.v_in = v_out + 3.0     # Default headroom
        self.i_load = 0.0

        # Thermal shutdown state
        self.thermal_shutdown = False

    def set_operating_point(self, v_in: float, i_load: float):
        """Set regulator operating point"""
        self.v_in = v_in
        self.i_load = abs(i_load)

        # Power dissipation
        v_drop = self.v_in - self.v_out
        if v_drop < 0:
            v_drop = 0
        self.power_dissipated = v_drop * self.i_load

    def update(self, dt: float, ambient_temp: float = None):
        """Update with thermal shutdown modeling"""
        super().update(dt, ambient_temp)

        p = self.regulator_params

        # Check thermal shutdown
        if self.temperature >= p.thermal_shutdown_temp:
            self.thermal_shutdown = True
        elif self.temperature < p.thermal_shutdown_temp - 20:
            # Hysteresis on recovery
            self.thermal_shutdown = False

    def get_output_voltage(self) -> float:
        """Get actual output voltage (0 if shutdown)"""
        if self.thermal_shutdown or not self.is_functional():
            return 0.0

        # Check dropout
        if self.v_in < self.v_out + self.regulator_params.dropout_voltage:
            return self.v_in - self.regulator_params.dropout_voltage

        return self.v_out

    def get_state(self) -> dict:
        state = super().get_state()
        state.update({
            'v_in': self.v_in,
            'v_out_nominal': self.v_out,
            'v_out_actual': self.get_output_voltage(),
            'i_load': self.i_load,
            'thermal_shutdown': self.thermal_shutdown,
        })
        return state


@dataclass
class ServoThermalParams(ThermalParams):
    """Servo motor thermal parameters"""

    thermal_mass: float = 15.0              # J/°C (small motor + gearbox)
    thermal_resistance: float = 8.0         # °C/W

    max_temp: float = 80.0                  # °C - servo motors run cooler
    warning_temp: float = 60.0              # °C
    damage_threshold: float = 100.0         # °C - gear/motor damage
    destruction_temp: float = 120.0         # °C

    # Servo specific
    stall_current: float = 0.8              # A
    motor_resistance: float = 5.0           # Ω


class ServoThermal(ThermalNode):
    """
    Servo motor thermal model.

    Servos can overheat when:
      - Stalled against mechanical stop
      - Continuous high-speed operation
      - Fighting against external load
    """

    def __init__(self, name: str, params: ServoThermalParams = None):
        self.servo_params = params or ServoThermalParams()
        super().__init__(name, self.servo_params)

        self.current = 0.0
        self.is_stalled = False

    def set_current(self, current: float):
        """Set servo motor current"""
        self.current = abs(current)

    def set_stalled(self, stalled: bool):
        """Set stall condition (worse cooling, higher current)"""
        self.is_stalled = stalled

    def update(self, dt: float, ambient_temp: float = None):
        """Update servo temperature"""
        p = self.servo_params

        # I²R losses
        self.power_dissipated = self.current ** 2 * p.motor_resistance

        # Worse cooling when stalled (no air movement, sustained load)
        if self.is_stalled:
            original_r = self.params.thermal_resistance
            self.params.thermal_resistance = original_r * 1.5
            super().update(dt, ambient_temp)
            self.params.thermal_resistance = original_r
        else:
            super().update(dt, ambient_temp)


# =============================================================================
# THERMAL SYSTEM (manages all thermal nodes)
# =============================================================================

class ThermalSystem:
    """
    Complete thermal management system for AeroTone voice.

    Manages all thermal nodes and provides:
      - Unified ambient temperature
      - System-wide thermal status
      - Damage detection and logging
      - Thermal event history
    """

    def __init__(self, ambient_temp: float = 25.0):
        self.ambient_temp = ambient_temp
        self.nodes: Dict[str, ThermalNode] = {}

        # System status
        self.worst_status = ThermalStatus.NORMAL
        self.any_damaged = False
        self.any_destroyed = False

        # Event log
        self.events: List[dict] = []
        self.max_events = 100

        # Time tracking
        self.total_time = 0.0

    def add_node(self, node: ThermalNode):
        """Add a thermal node to the system"""
        self.nodes[node.name] = node

    def create_motor(self, name: str, params: MotorThermalParams = None) -> MotorThermal:
        """Create and add a motor thermal model"""
        motor = MotorThermal(name, params)
        self.add_node(motor)
        return motor

    def create_transistor(self, name: str, params: TransistorThermalParams = None) -> TransistorThermal:
        """Create and add a transistor thermal model"""
        transistor = TransistorThermal(name, params)
        self.add_node(transistor)
        return transistor

    def create_regulator(self, name: str, v_out: float,
                         params: RegulatorThermalParams = None) -> RegulatorThermal:
        """Create and add a regulator thermal model"""
        regulator = RegulatorThermal(name, v_out, params)
        self.add_node(regulator)
        return regulator

    def create_servo(self, name: str, params: ServoThermalParams = None) -> ServoThermal:
        """Create and add a servo thermal model"""
        servo = ServoThermal(name, params)
        self.add_node(servo)
        return servo

    def set_ambient(self, temp: float):
        """Set ambient temperature for all nodes"""
        self.ambient_temp = temp

    def update(self, dt: float):
        """Update all thermal nodes"""
        self.total_time += dt

        old_statuses = {name: node.status for name, node in self.nodes.items()}

        # Update each node
        for node in self.nodes.values():
            node.update(dt, self.ambient_temp)

        # Check for status changes (events)
        for name, node in self.nodes.items():
            if node.status != old_statuses[name]:
                self._log_event(name, old_statuses[name], node.status)

        # Update system status
        self._update_system_status()

    def _log_event(self, name: str, old_status: ThermalStatus, new_status: ThermalStatus):
        """Log a thermal status change event"""
        event = {
            'time': self.total_time,
            'component': name,
            'old_status': old_status.value,
            'new_status': new_status.value,
            'temperature': self.nodes[name].temperature,
        }
        self.events.append(event)

        if len(self.events) > self.max_events:
            self.events.pop(0)

    def _update_system_status(self):
        """Update overall system thermal status"""
        self.worst_status = ThermalStatus.NORMAL
        self.any_damaged = False
        self.any_destroyed = False

        status_priority = {
            ThermalStatus.NORMAL: 0,
            ThermalStatus.WARNING: 1,
            ThermalStatus.CRITICAL: 2,
            ThermalStatus.DAMAGED: 3,
            ThermalStatus.DESTROYED: 4,
        }

        for node in self.nodes.values():
            if status_priority[node.status] > status_priority[self.worst_status]:
                self.worst_status = node.status

            if node.status == ThermalStatus.DAMAGED:
                self.any_damaged = True
            if node.status == ThermalStatus.DESTROYED:
                self.any_destroyed = True

    def get_hottest(self) -> Optional[ThermalNode]:
        """Get the hottest component"""
        if not self.nodes:
            return None
        return max(self.nodes.values(), key=lambda n: n.temperature)

    def get_by_status(self, status: ThermalStatus) -> List[ThermalNode]:
        """Get all nodes with given status"""
        return [n for n in self.nodes.values() if n.status == status]

    def is_all_functional(self) -> bool:
        """Are all components still functional?"""
        return all(n.is_functional() for n in self.nodes.values())

    def reset(self, clear_damage: bool = False):
        """Reset all nodes to ambient"""
        for node in self.nodes.values():
            node.reset(self.ambient_temp)
            if clear_damage:
                node.damage_integral = 0.0
                node.status = ThermalStatus.NORMAL

        self.worst_status = ThermalStatus.NORMAL
        self.any_damaged = False
        self.any_destroyed = False
        self.events.clear()
        self.total_time = 0.0

    def get_state(self) -> dict:
        """Get complete thermal system state"""
        return {
            'ambient_temp': self.ambient_temp,
            'total_time': self.total_time,
            'worst_status': self.worst_status.value,
            'any_damaged': self.any_damaged,
            'any_destroyed': self.any_destroyed,
            'all_functional': self.is_all_functional(),
            'node_count': len(self.nodes),
            'hottest': self.get_hottest().name if self.get_hottest() else None,
            'hottest_temp': self.get_hottest().temperature if self.get_hottest() else 0,
            'nodes': {name: node.get_state() for name, node in self.nodes.items()},
            'recent_events': self.events[-10:] if self.events else [],
        }

    def get_summary(self) -> str:
        """Get human-readable thermal summary"""
        lines = []
        lines.append(f"Thermal System - Ambient: {self.ambient_temp:.1f}°C")
        lines.append(f"Overall Status: {self.worst_status.value.upper()}")
        lines.append("-" * 50)

        for name, node in sorted(self.nodes.items()):
            status_icon = {
                ThermalStatus.NORMAL: "✓",
                ThermalStatus.WARNING: "⚠",
                ThermalStatus.CRITICAL: "🔥",
                ThermalStatus.DAMAGED: "✗",
                ThermalStatus.DESTROYED: "💀",
            }.get(node.status, "?")

            lines.append(f"  {status_icon} {name}: {node.temperature:.1f}°C "
                        f"({node.power_dissipated:.2f}W) - {node.status.value}")

        return "\n".join(lines)

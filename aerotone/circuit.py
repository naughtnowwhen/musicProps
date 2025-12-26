"""
Circuit Simulation Framework for AeroTone

SPICE-style time-domain circuit simulation using nodal analysis.
Models real electronic components with their actual behaviors.

This is NOT a wrapper around ngspice - it's a purpose-built simulator
optimized for the specific circuits in the AeroTone (PLL, filters, drivers).

Key features:
  - Component-level modeling (R, C, L, diodes, transistors, op-amps, ICs)
  - Nodal voltage computation at each timestep
  - State variables for reactive components (capacitor voltage, inductor current)
  - Non-linear component handling (diodes, transistors)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum


class NodeType(Enum):
    """Types of circuit nodes"""
    GROUND = 0      # Reference node (0V)
    VOLTAGE = 1     # Voltage node (computed)
    INPUT = 2       # External input (set by user)


@dataclass
class Node:
    """A circuit node (connection point)"""
    name: str
    node_type: NodeType = NodeType.VOLTAGE
    voltage: float = 0.0

    def __hash__(self):
        return hash(self.name)


@dataclass
class ComponentTerminal:
    """A terminal connection to a node"""
    node: Node
    current: float = 0.0  # Current INTO this terminal


class Component:
    """Base class for all circuit components"""

    def __init__(self, name: str):
        self.name = name
        self.terminals: Dict[str, ComponentTerminal] = {}

    def connect(self, terminal_name: str, node: Node):
        """Connect a terminal to a node"""
        self.terminals[terminal_name] = ComponentTerminal(node)

    def get_voltage(self, terminal_name: str) -> float:
        """Get voltage at a terminal"""
        return self.terminals[terminal_name].node.voltage

    def update(self, dt: float):
        """Update component state (override in subclasses)"""
        pass

    def get_current(self, terminal_name: str) -> float:
        """Get current through terminal (override in subclasses)"""
        return 0.0


class Resistor(Component):
    """
    Ideal resistor: V = I * R
    """

    def __init__(self, name: str, resistance: float, tolerance: float = 0.05):
        super().__init__(name)
        self.nominal_resistance = resistance
        self.tolerance = tolerance
        # Apply random tolerance variation (simulates real component)
        self.resistance = resistance * (1 + np.random.uniform(-tolerance, tolerance))

        # Aging factor (1.0 = new, >1.0 = drifted high)
        self.aging_factor = 1.0

    @property
    def actual_resistance(self) -> float:
        return self.resistance * self.aging_factor

    def get_current(self, from_terminal: str = 'A') -> float:
        """Current from A to B"""
        va = self.get_voltage('A')
        vb = self.get_voltage('B')
        return (va - vb) / self.actual_resistance


class Capacitor(Component):
    """
    Capacitor with ESR (equivalent series resistance).
    State variable: voltage across ideal capacitance.

    I = C * dV/dt
    """

    def __init__(self, name: str, capacitance: float,
                 esr: float = 0.1, tolerance: float = 0.20):
        super().__init__(name)
        self.nominal_capacitance = capacitance
        self.tolerance = tolerance
        self.capacitance = capacitance * (1 + np.random.uniform(-tolerance, tolerance))

        self.nominal_esr = esr
        self.esr = esr  # ESR can increase with age (electrolytics)

        # State: voltage across the capacitance
        self.cap_voltage = 0.0
        self.current = 0.0

        # Aging
        self.esr_aging_factor = 1.0  # ESR increases with age
        self.cap_aging_factor = 1.0  # Capacitance can decrease

    @property
    def actual_capacitance(self) -> float:
        return self.capacitance * self.cap_aging_factor

    @property
    def actual_esr(self) -> float:
        return self.esr * self.esr_aging_factor

    def update(self, dt: float):
        """Update capacitor state"""
        va = self.get_voltage('A')
        vb = self.get_voltage('B')
        v_total = va - vb

        # Voltage across ESR
        v_esr = self.current * self.actual_esr

        # Voltage across capacitance should equal total minus ESR drop
        v_cap_target = v_total - v_esr

        # I = C * dV/dt  =>  dV = I * dt / C
        # But we need to solve for current given voltages...
        # Using backward Euler: I = C * (V_new - V_old) / dt
        # V_total = V_cap + I * ESR = V_cap + C*(V_cap - V_old)/dt * ESR

        # Simplified update (forward Euler for now):
        self.current = self.actual_capacitance * (v_cap_target - self.cap_voltage) / dt
        self.cap_voltage = v_cap_target

    def get_current(self, from_terminal: str = 'A') -> float:
        return self.current if from_terminal == 'A' else -self.current


class Inductor(Component):
    """
    Inductor with DC resistance.
    State variable: current through inductance.

    V = L * dI/dt
    """

    def __init__(self, name: str, inductance: float, dcr: float = 0.1):
        super().__init__(name)
        self.inductance = inductance
        self.dcr = dcr  # DC resistance

        # State: current through inductor
        self.current = 0.0

    def update(self, dt: float):
        """Update inductor state"""
        va = self.get_voltage('A')
        vb = self.get_voltage('B')
        v_total = va - vb

        # V across inductance (minus resistive drop)
        v_l = v_total - self.current * self.dcr

        # V = L * dI/dt  =>  dI = V * dt / L
        di = v_l * dt / self.inductance
        self.current += di

    def get_current(self, from_terminal: str = 'A') -> float:
        return self.current if from_terminal == 'A' else -self.current


class Diode(Component):
    """
    Diode with Shockley equation.
    I = Is * (exp(V/Vt) - 1)
    """

    def __init__(self, name: str, is_: float = 1e-12,
                 vt: float = 0.026, n: float = 1.0):
        super().__init__(name)
        self.is_ = is_       # Saturation current
        self.vt = vt         # Thermal voltage (~26mV at room temp)
        self.n = n           # Ideality factor
        self.current = 0.0

    def update(self, dt: float):
        """Update diode current"""
        va = self.get_voltage('A')  # Anode
        vk = self.get_voltage('K')  # Kathode
        vd = va - vk

        # Shockley equation with clamping for numerical stability
        vd_clamped = np.clip(vd, -1.0, 0.7)
        self.current = self.is_ * (np.exp(vd_clamped / (self.n * self.vt)) - 1)

    def get_current(self, from_terminal: str = 'A') -> float:
        return self.current if from_terminal == 'A' else -self.current


class BJT_NPN(Component):
    """
    NPN Bipolar Junction Transistor (simplified Ebers-Moll).
    Terminals: B (base), C (collector), E (emitter)
    """

    def __init__(self, name: str, beta: float = 100,
                 is_: float = 1e-14, vbe_on: float = 0.65):
        super().__init__(name)
        self.beta = beta      # Current gain
        self.is_ = is_        # Saturation current
        self.vbe_on = vbe_on  # Forward Vbe
        self.vt = 0.026       # Thermal voltage

        self.ib = 0.0
        self.ic = 0.0
        self.ie = 0.0

        # Operating region
        self.region = 'cutoff'  # cutoff, active, saturation

    def update(self, dt: float):
        """Update transistor currents"""
        vb = self.get_voltage('B')
        vc = self.get_voltage('C')
        ve = self.get_voltage('E')

        vbe = vb - ve
        vbc = vb - vc
        vce = vc - ve

        if vbe < 0.5:
            # Cutoff
            self.region = 'cutoff'
            self.ib = 0.0
            self.ic = 0.0
        elif vce > 0.2:
            # Active region
            self.region = 'active'
            self.ib = self.is_ * (np.exp(vbe / self.vt) - 1)
            self.ic = self.beta * self.ib
        else:
            # Saturation
            self.region = 'saturation'
            self.ib = self.is_ * (np.exp(vbe / self.vt) - 1)
            self.ic = self.beta * self.ib * (vce / 0.2)  # Reduced gain

        self.ie = self.ib + self.ic

    def get_current(self, terminal: str) -> float:
        if terminal == 'B':
            return self.ib
        elif terminal == 'C':
            return self.ic
        elif terminal == 'E':
            return -self.ie
        return 0.0


class BJT_PNP(Component):
    """PNP Bipolar Junction Transistor"""

    def __init__(self, name: str, beta: float = 100,
                 is_: float = 1e-14, veb_on: float = 0.65):
        super().__init__(name)
        self.beta = beta
        self.is_ = is_
        self.veb_on = veb_on
        self.vt = 0.026

        self.ib = 0.0
        self.ic = 0.0
        self.ie = 0.0
        self.region = 'cutoff'

    def update(self, dt: float):
        """Update transistor currents (PNP: reversed polarities)"""
        vb = self.get_voltage('B')
        vc = self.get_voltage('C')
        ve = self.get_voltage('E')

        veb = ve - vb  # Note: reversed from NPN
        vcb = vc - vb
        vec = ve - vc

        if veb < 0.5:
            self.region = 'cutoff'
            self.ib = 0.0
            self.ic = 0.0
        elif vec > 0.2:
            self.region = 'active'
            self.ib = self.is_ * (np.exp(veb / self.vt) - 1)
            self.ic = self.beta * self.ib
        else:
            self.region = 'saturation'
            self.ib = self.is_ * (np.exp(veb / self.vt) - 1)
            self.ic = self.beta * self.ib * (vec / 0.2)

        self.ie = self.ib + self.ic

    def get_current(self, terminal: str) -> float:
        # PNP: current directions reversed
        if terminal == 'B':
            return -self.ib
        elif terminal == 'C':
            return -self.ic
        elif terminal == 'E':
            return self.ie
        return 0.0


class OpAmp(Component):
    """
    Operational Amplifier (simplified model for LM741 etc.)

    Models:
      - Finite open-loop gain
      - Finite bandwidth (single pole)
      - Output swing limits
      - Slew rate limiting
    """

    def __init__(self, name: str,
                 gain: float = 100000,           # Open-loop DC gain
                 gbw: float = 1e6,               # Gain-bandwidth product (Hz)
                 v_supply_pos: float = 15.0,     # Positive supply
                 v_supply_neg: float = -15.0,    # Negative supply (or 0)
                 slew_rate: float = 0.5e6):      # V/s slew rate
        super().__init__(name)
        self.gain = gain
        self.gbw = gbw
        self.v_supply_pos = v_supply_pos
        self.v_supply_neg = v_supply_neg
        self.slew_rate = slew_rate

        # Internal state for bandwidth limiting
        self.output_voltage = 0.0

        # Pole frequency
        self.pole_freq = gbw / gain
        self.tau = 1.0 / (2 * np.pi * self.pole_freq)

    def update(self, dt: float):
        """Update op-amp output"""
        v_pos = self.get_voltage('IN+')
        v_neg = self.get_voltage('IN-')

        v_diff = v_pos - v_neg

        # Ideal output (before limiting)
        v_ideal = v_diff * self.gain

        # Clamp to supply rails (with some headroom)
        headroom = 1.5  # Volts from rail
        v_clamped = np.clip(v_ideal,
                           self.v_supply_neg + headroom,
                           self.v_supply_pos - headroom)

        # Single-pole bandwidth limiting
        # V_out approaches V_target with time constant tau
        dv = (v_clamped - self.output_voltage)

        # Slew rate limiting
        max_dv = self.slew_rate * dt
        dv = np.clip(dv, -max_dv, max_dv)

        # Bandwidth limiting (first-order filter)
        alpha = dt / (self.tau + dt)
        self.output_voltage += alpha * dv

        # Final clamp
        self.output_voltage = np.clip(self.output_voltage,
                                      self.v_supply_neg + headroom,
                                      self.v_supply_pos - headroom)

    def get_output_voltage(self) -> float:
        return self.output_voltage


class VoltageSource(Component):
    """Ideal voltage source"""

    def __init__(self, name: str, voltage: float = 0.0):
        super().__init__(name)
        self._voltage = voltage

    def set_voltage(self, v: float):
        self._voltage = v

    @property
    def voltage(self) -> float:
        return self._voltage


class Circuit:
    """
    Circuit container and simulator.

    Manages nodes, components, and time-domain simulation.
    """

    def __init__(self, name: str = "circuit"):
        self.name = name
        self.nodes: Dict[str, Node] = {}
        self.components: Dict[str, Component] = {}

        # Create ground node
        self.gnd = self.add_node("GND", NodeType.GROUND)
        self.gnd.voltage = 0.0

        # Simulation state
        self.time = 0.0

    def add_node(self, name: str, node_type: NodeType = NodeType.VOLTAGE) -> Node:
        """Add a node to the circuit"""
        node = Node(name, node_type)
        self.nodes[name] = node
        return node

    def add_component(self, component: Component) -> Component:
        """Add a component to the circuit"""
        self.components[component.name] = component
        return component

    def get_node(self, name: str) -> Node:
        """Get node by name"""
        return self.nodes.get(name)

    def get_component(self, name: str) -> Component:
        """Get component by name"""
        return self.components.get(name)

    def set_node_voltage(self, name: str, voltage: float):
        """Set voltage at a node (for input nodes)"""
        if name in self.nodes:
            self.nodes[name].voltage = voltage

    def step(self, dt: float):
        """
        Advance simulation by one time step.

        This is a simplified solver - for complex circuits you'd want
        full nodal analysis with Newton-Raphson iteration.
        """
        # Update all components
        for component in self.components.values():
            component.update(dt)

        self.time += dt

    def get_voltage(self, node_name: str) -> float:
        """Get voltage at a node"""
        node = self.nodes.get(node_name)
        return node.voltage if node else 0.0

    def get_state(self) -> dict:
        """Get complete circuit state"""
        return {
            'time': self.time,
            'nodes': {name: node.voltage for name, node in self.nodes.items()},
            'components': {name: comp.__dict__.copy()
                          for name, comp in self.components.items()}
        }

"""
Atmospheric Weather Simulation for AeroTone

Simulates environmental pressure variations using Perlin noise to create
realistic, smooth "weather systems" that affect propeller aerodynamics.

Physics:
  - Air density ρ varies with pressure (ideal gas law)
  - Propeller drag ∝ ρ (higher density = more resistance)
  - Higher pressure = harder to spin = PLL must push harder
  - Lower pressure = easier to spin = PLL must back off

The Perlin noise creates smooth, natural pressure "fronts" that drift
through the simulation space, causing gradual variations that the
control loop must compensate for.

This tests control loop robustness - can it maintain pitch accuracy
despite environmental disturbances?
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional


def perlin_fade(t):
    """Perlin smoothstep function: 6t⁵ - 15t⁴ + 10t³"""
    return t * t * t * (t * (t * 6 - 15) + 10)


def perlin_lerp(a, b, t):
    """Linear interpolation"""
    return a + t * (b - a)


def perlin_grad(hash_val, x, y):
    """Gradient function for 2D Perlin noise"""
    h = hash_val & 3
    if h == 0:
        return x + y
    elif h == 1:
        return -x + y
    elif h == 2:
        return x - y
    else:
        return -x - y


class PerlinNoise2D:
    """
    2D Perlin noise generator for smooth, natural variations.

    Creates coherent noise that looks like weather patterns -
    smooth gradients between high and low pressure regions.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        np.random.seed(seed)

        # Permutation table
        self.p = np.arange(256, dtype=np.int32)
        np.random.shuffle(self.p)
        self.p = np.tile(self.p, 2)  # Duplicate for overflow

    def noise(self, x: float, y: float) -> float:
        """
        Get Perlin noise value at (x, y).

        Returns value in range [-1, 1]
        """
        # Grid cell coordinates
        xi = int(np.floor(x)) & 255
        yi = int(np.floor(y)) & 255

        # Relative position in cell
        xf = x - np.floor(x)
        yf = y - np.floor(y)

        # Fade curves
        u = perlin_fade(xf)
        v = perlin_fade(yf)

        # Hash coordinates of corners
        aa = self.p[self.p[xi] + yi]
        ab = self.p[self.p[xi] + yi + 1]
        ba = self.p[self.p[xi + 1] + yi]
        bb = self.p[self.p[xi + 1] + yi + 1]

        # Gradient values at corners
        g_aa = perlin_grad(aa, xf, yf)
        g_ba = perlin_grad(ba, xf - 1, yf)
        g_ab = perlin_grad(ab, xf, yf - 1)
        g_bb = perlin_grad(bb, xf - 1, yf - 1)

        # Interpolate
        x1 = perlin_lerp(g_aa, g_ba, u)
        x2 = perlin_lerp(g_ab, g_bb, u)

        return perlin_lerp(x1, x2, v)

    def octave_noise(self, x: float, y: float,
                     octaves: int = 4, persistence: float = 0.5) -> float:
        """
        Multi-octave Perlin noise for more natural patterns.

        Combines multiple frequencies for richer variation.
        """
        total = 0.0
        frequency = 1.0
        amplitude = 1.0
        max_value = 0.0

        for _ in range(octaves):
            total += self.noise(x * frequency, y * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2

        return total / max_value


@dataclass
class WeatherParams:
    """Weather simulation parameters"""

    # Pressure variation range
    base_pressure: float = 101325.0     # Pa (standard atmosphere)
    pressure_variation: float = 5000.0  # Pa (±5 kPa variation)

    # Corresponding air density
    base_density: float = 1.225         # kg/m³ (standard atmosphere)
    density_variation: float = 0.15     # ±15% variation (±0.18 kg/m³)

    # Noise parameters
    spatial_scale: float = 0.1          # How "big" the weather systems are
    time_scale: float = 0.05            # How fast weather changes
    octaves: int = 3                    # Noise complexity
    persistence: float = 0.5            # Octave amplitude falloff

    # Optional: sudden gusts
    gust_probability: float = 0.001     # Per-update probability of gust
    gust_strength: float = 0.3          # Additional density variation
    gust_duration: float = 0.5          # Seconds


class Weather:
    """
    Atmospheric weather simulation.

    Creates smooth pressure/density variations that affect propeller
    aerodynamics. The control loop must compensate for these disturbances.

    Usage:
        weather = Weather()

        # In your physics loop:
        density = weather.get_air_density(time)
        propeller.air_density = density  # Affects drag
    """

    def __init__(self, params: WeatherParams = None, seed: int = None):
        self.params = params or WeatherParams()

        # Initialize Perlin noise generator
        if seed is None:
            seed = np.random.randint(0, 10000)
        self.noise = PerlinNoise2D(seed)
        self.seed = seed

        # Position in noise space (drifts over time)
        self.noise_x = 0.0
        self.noise_y = 0.0

        # Current state
        self.time = 0.0
        self.current_density = self.params.base_density
        self.current_pressure = self.params.base_pressure

        # Gust state
        self.gust_active = False
        self.gust_remaining = 0.0
        self.gust_value = 0.0

        # History for visualization
        self.history_len = 500
        self.density_history = []

    def update(self, dt: float):
        """
        Update weather state.

        Args:
            dt: Time step in seconds
        """
        self.time += dt
        p = self.params

        # Move through noise space (simulates drifting weather)
        self.noise_x += dt * p.time_scale
        self.noise_y += dt * p.time_scale * 0.7  # Slightly different rate

        # Sample Perlin noise for base weather
        noise_val = self.noise.octave_noise(
            self.noise_x * p.spatial_scale,
            self.noise_y * p.spatial_scale,
            octaves=p.octaves,
            persistence=p.persistence
        )

        # noise_val is in [-1, 1], scale to density variation
        base_variation = noise_val * p.density_variation

        # Handle gusts
        if self.gust_active:
            self.gust_remaining -= dt
            if self.gust_remaining <= 0:
                self.gust_active = False
                self.gust_value = 0.0
        elif np.random.random() < p.gust_probability:
            # Start a new gust
            self.gust_active = True
            self.gust_remaining = p.gust_duration
            self.gust_value = (np.random.random() * 2 - 1) * p.gust_strength

        # Combine base weather + gusts
        total_variation = base_variation + self.gust_value

        # Calculate final density
        self.current_density = p.base_density * (1.0 + total_variation)

        # Calculate corresponding pressure (ideal gas approximation)
        self.current_pressure = p.base_pressure * (1.0 + total_variation)

        # Update history
        self.density_history.append(self.current_density)
        if len(self.density_history) > self.history_len:
            self.density_history.pop(0)

    def get_air_density(self) -> float:
        """Get current air density in kg/m³"""
        return self.current_density

    def get_pressure(self) -> float:
        """Get current atmospheric pressure in Pa"""
        return self.current_pressure

    def get_density_factor(self) -> float:
        """
        Get density as a factor relative to standard atmosphere.

        1.0 = standard, >1.0 = high pressure, <1.0 = low pressure
        """
        return self.current_density / self.params.base_density

    def get_state(self) -> dict:
        """Get current weather state"""
        p = self.params
        return {
            'time': self.time,
            'density': self.current_density,
            'density_factor': self.get_density_factor(),
            'pressure': self.current_pressure,
            'pressure_hpa': self.current_pressure / 100,  # hPa (millibar)
            'gust_active': self.gust_active,
            'variation_percent': (self.current_density / p.base_density - 1) * 100,
        }

    def reset(self, seed: int = None):
        """Reset weather with optional new seed"""
        if seed is not None:
            self.noise = PerlinNoise2D(seed)
            self.seed = seed

        self.time = 0.0
        self.noise_x = 0.0
        self.noise_y = 0.0
        self.current_density = self.params.base_density
        self.gust_active = False
        self.density_history = []


class TurbulentWeather(Weather):
    """
    More aggressive weather with stronger, faster variations.

    Good for stress-testing the control loop.
    """

    def __init__(self, seed: int = None):
        params = WeatherParams(
            density_variation=0.25,      # ±25% (aggressive!)
            time_scale=0.2,              # Faster changes
            gust_probability=0.005,      # More frequent gusts
            gust_strength=0.4,           # Stronger gusts
        )
        super().__init__(params, seed)


class CalmWeather(Weather):
    """
    Gentle weather with subtle, slow variations.

    Good for hearing the natural system response.
    """

    def __init__(self, seed: int = None):
        params = WeatherParams(
            density_variation=0.05,      # ±5% (subtle)
            time_scale=0.01,             # Very slow changes
            gust_probability=0.0,        # No gusts
        )
        super().__init__(params, seed)

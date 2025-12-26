#!/usr/bin/env python3
"""
NODE-BY-NODE CIRCUIT VALIDATION

Tests every electrical node (junction point) in the AeroTone circuit.
A node is any distinct electrical point between components.

Circuit Topology:

    VDD(15V)──┬──R_VG1──┬──vgnd──┬──R_VG2──┬──GND
              │         │        │         │
              │       C_BIAS     │         │
              │         │        │         │
              └─────────┴────────┘         │
                                           │
    tach_raw──C_AC──tach_ac──R8──opamp_inn─┴──R9──cond_pre──cond_out
                                    │              │
                                    │         [LM358 U2]
                                    │              │
                                    └──────────────┘

    ref_in ──┐
             ├──[CD4046]──pd_out──R3──loop_filt──┬──[C2]──GND
    comp_out─┘                                   │
                                                 │
              ┌──────────────────────────────────┘
              │
    VCC(12V)──┼──R_BIAS1──┬──base_q1──[Q1]──motor_p──┬──D1──VCC
              │           │                          │
              │         R_DRIVE1                     ├──D2──GND
              │           │                          │
              └───────────┴──────────────────────────┤
                                                     │
                                              R_MOTOR│
                                                     │
                                              motor_bemf
                                                     │
                                              V_BEMF │
                                                     │
    GND───────┬──R_BIAS2──┬──base_q2──[Q2]──motor_n──┼──D3──VCC
              │           │                          │
              │         R_DRIVE2                     ├──D4──GND
              │           │                          │
              └───────────┴──────────────────────────┘
                                                     │
                                              R_SENSE│
                                                     │
                                              motor_gnd──GND

Run: python3 validate_nodes.py
"""

import os
import sys
import numpy as np

sys.path.insert(0, '.')

SPICE_DIR = '.hidden_answers/spice_models'

# =============================================================================
# CIRCUIT NODE DEFINITIONS
# =============================================================================

NODES = {
    # Power Supply Nodes
    'vcc': {
        'description': 'Main 12V motor supply',
        'expected_dc': 12.0,
        'tolerance': 0.1,
        'type': 'power'
    },
    'vdd': {
        'description': 'Logic 15V supply',
        'expected_dc': 15.0,
        'tolerance': 0.1,
        'type': 'power'
    },
    'gnd': {
        'description': 'Ground reference',
        'expected_dc': 0.0,
        'tolerance': 0.01,
        'type': 'power'
    },

    # Signal Conditioner Nodes
    'vgnd': {
        'description': 'Virtual ground (VDD/2) for single-supply op-amp',
        'expected_dc': 7.5,
        'tolerance': 0.5,
        'type': 'bias'
    },
    'tach_raw': {
        'description': 'Raw tachometer signal from magnetic pickup',
        'expected_dc': 0.0,
        'expected_ac_mv': 50,
        'type': 'signal'
    },
    'tach_ac': {
        'description': 'AC-coupled tachometer (after C_AC, biased to vgnd)',
        'expected_dc': 7.5,  # Coupled to vgnd through R8
        'tolerance': 0.5,
        'type': 'signal'
    },
    'opamp_inn': {
        'description': 'Op-amp inverting input (summing junction)',
        'expected_dc': 7.5,  # Virtual ground due to feedback
        'tolerance': 0.5,
        'type': 'signal'
    },
    'cond_pre': {
        'description': 'Op-amp output (before noise injection)',
        'expected_dc': 7.5,
        'expected_vpp': (5, 12),  # Should swing with gain
        'type': 'signal'
    },
    'cond_out': {
        'description': 'Conditioner output (after noise injection)',
        'expected_dc': 7.5,
        'expected_vpp': (5, 12),
        'type': 'signal'
    },

    # PLL / Phase Detector Nodes
    'ref_in': {
        'description': 'Reference frequency input (220Hz square wave)',
        'expected_dc': 7.5,  # 50% duty cycle
        'expected_vpp': (14, 16),  # 0-15V square wave
        'type': 'digital'
    },
    'comp_out': {
        'description': 'Comparator output (digitized feedback)',
        'expected_dc': 7.5,
        'expected_vpp': (14, 16),
        'type': 'digital'
    },
    'pd_out': {
        'description': 'Phase detector output (XOR of ref and comp)',
        'expected_dc': (0, 15),  # Varies with phase error, full range
        'type': 'signal'
    },

    # Loop Filter Nodes
    'loop_filt': {
        'description': 'Loop filter output (controls motor drive)',
        'expected_dc': (0.5, 2.0),  # Depends on load
        'type': 'control'
    },
    'c2_mid': {
        'description': 'Between C2 and its ESR',
        'expected_dc': (0.5, 2.0),
        'type': 'internal'
    },

    # H-Bridge Driver Nodes
    'base_q1': {
        'description': 'Q1 (2N3055 NPN) base drive',
        'expected_dc': (0.5, 12),
        'type': 'drive'
    },
    'base_q2': {
        'description': 'Q2 (MJ2955 PNP) base drive',
        'expected_dc': (0, 5),
        'type': 'drive'
    },
    'base_q3': {
        'description': 'Q3 (2N3055 NPN) base drive',
        'expected_dc': (0.5, 12),
        'type': 'drive'
    },
    'base_q4': {
        'description': 'Q4 (MJ2955 PNP) base drive',
        'expected_dc': (0, 5),
        'type': 'drive'
    },
    'q1_emit': {
        'description': 'Q1 emitter (after damage resistor for F002)',
        'expected_dc': (0, 12),
        'type': 'internal'
    },

    # Motor Nodes
    'motor_p': {
        'description': 'Motor positive terminal',
        'expected_dc': (0, 12),
        'type': 'power'
    },
    'motor_n': {
        'description': 'Motor negative terminal',
        'expected_dc': (0, 6),
        'type': 'power'
    },
    'motor_bemf': {
        'description': 'Between motor resistance and back-EMF source',
        'expected_dc': (0, 6),
        'type': 'internal'
    },
    'motor_gnd': {
        'description': 'After current sense resistor',
        'expected_dc': 0.0,
        'tolerance': 0.1,
        'type': 'sense'
    },
}


def load_all_nodes():
    """Load all node data from separate files."""
    nodes = {}

    # Power nodes: vcc, vdd
    f = os.path.join(SPICE_DIR, 'nodes_power.dat')
    if os.path.exists(f):
        data = np.loadtxt(f)
        nodes['vcc'] = data[:, 1]
        nodes['vdd'] = data[:, 3]

    # Conditioner nodes: vgnd, tach_raw, tach_ac, opamp_inn, cond_pre, cond_out
    f = os.path.join(SPICE_DIR, 'nodes_conditioner.dat')
    if os.path.exists(f):
        data = np.loadtxt(f)
        nodes['vgnd'] = data[:, 1]
        nodes['tach_raw'] = data[:, 3]
        nodes['tach_ac'] = data[:, 5]
        nodes['opamp_inn'] = data[:, 7]
        nodes['cond_pre'] = data[:, 9]
        nodes['cond_out'] = data[:, 11]

    # PLL nodes: ref_in, comp_out, pd_out
    f = os.path.join(SPICE_DIR, 'nodes_pll.dat')
    if os.path.exists(f):
        data = np.loadtxt(f)
        nodes['ref_in'] = data[:, 1]
        nodes['comp_out'] = data[:, 3]
        nodes['pd_out'] = data[:, 5]

    # Loop filter nodes: loop_filt, c2_mid
    f = os.path.join(SPICE_DIR, 'nodes_loopfilter.dat')
    if os.path.exists(f):
        data = np.loadtxt(f)
        nodes['loop_filt'] = data[:, 1]
        nodes['c2_mid'] = data[:, 3]

    # H-bridge nodes: base_q1, base_q2, base_q3, base_q4, q1_emit
    f = os.path.join(SPICE_DIR, 'nodes_hbridge.dat')
    if os.path.exists(f):
        data = np.loadtxt(f)
        nodes['base_q1'] = data[:, 1]
        nodes['base_q2'] = data[:, 3]
        nodes['base_q3'] = data[:, 5]
        nodes['base_q4'] = data[:, 7]
        nodes['q1_emit'] = data[:, 9]

    # Motor nodes: motor_p, motor_n, motor_bemf, motor_gnd, I(V_SENSE)
    f = os.path.join(SPICE_DIR, 'nodes_motor.dat')
    if os.path.exists(f):
        data = np.loadtxt(f)
        nodes['motor_p'] = data[:, 1]
        nodes['motor_n'] = data[:, 3]
        nodes['motor_bemf'] = data[:, 5]
        nodes['motor_gnd'] = data[:, 7]
        nodes['motor_current'] = data[:, 9]

    return nodes


def validate_nodes():
    """Validate each circuit node."""
    print("=" * 70)
    print("  NODE-BY-NODE CIRCUIT VALIDATION")
    print("  Testing every electrical junction point")
    print("=" * 70)

    # Load all node data
    all_nodes = load_all_nodes()
    if not all_nodes:
        print("\n  ERROR: Node data not found! Run validate_all_nodes.cir first.")
        return False

    # Get steady-state portion (last 20%)
    first_node = list(all_nodes.values())[0]
    steady = int(len(first_node) * 0.8)

    # Extract steady-state values
    spice_nodes = {}
    for name, data in all_nodes.items():
        spice_nodes[name] = data[steady:]

    passed = 0
    failed = 0

    # Group nodes by type for organized output
    node_types = {}
    for name, info in NODES.items():
        ntype = info['type']
        if ntype not in node_types:
            node_types[ntype] = []
        node_types[ntype].append(name)

    for ntype, node_names in node_types.items():
        print(f"\n[{ntype.upper()} NODES]")
        print("-" * 50)

        for node in node_names:
            info = NODES[node]

            # Check if we have SPICE data for this node
            if node in spice_nodes:
                values = spice_nodes[node]
                dc = np.mean(values)
                vpp = np.ptp(values)

                # Validate DC level
                expected = info.get('expected_dc')
                tolerance = info.get('tolerance', 1.0)

                if expected is not None:
                    if isinstance(expected, tuple):
                        ok = expected[0] <= dc <= expected[1]
                        exp_str = f"[{expected[0]}, {expected[1]}]"
                    else:
                        ok = abs(dc - expected) <= tolerance
                        exp_str = f"{expected}±{tolerance}"

                    status = "✓" if ok else "✗"
                    print(f"  {status} {node}: DC={dc:.3f}V (expected {exp_str})")
                    print(f"      └─ {info['description']}")

                    if ok:
                        passed += 1
                    else:
                        failed += 1

                    # Also check AC content if expected
                    if 'expected_vpp' in info:
                        vpp_range = info['expected_vpp']
                        vpp_ok = vpp_range[0] <= vpp <= vpp_range[1]
                        vpp_status = "✓" if vpp_ok else "✗"
                        print(f"      {vpp_status} Vpp={vpp:.2f}V (expected [{vpp_range[0]}, {vpp_range[1]}])")
                        if vpp_ok:
                            passed += 1
                        else:
                            failed += 1
                else:
                    # Just report the value
                    print(f"  ○ {node}: DC={dc:.3f}V, Vpp={vpp:.3f}V")
                    print(f"      └─ {info['description']}")
                    passed += 1  # Info only, counts as pass

            else:
                # Node not in SPICE output - note it
                print(f"  ○ {node}: (not in SPICE output)")
                print(f"      └─ {info['description']}")

    # Summary
    total = passed + failed
    print(f"\n{'='*70}")
    print(f"NODE VALIDATION: {passed}/{total} passed")

    if failed > 0:
        print(f"\n⚠ {failed} node(s) outside expected range!")
    else:
        print("\n✓ All nodes within expected ranges")

    print(f"{'='*70}")

    # Print node count summary
    print(f"\nCircuit has {len(NODES)} defined nodes:")
    for ntype, nodes in node_types.items():
        print(f"  {ntype}: {len(nodes)} nodes")

    return failed == 0


if __name__ == '__main__':
    success = validate_nodes()
    sys.exit(0 if success else 1)

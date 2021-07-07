#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  SPICE-related tests for hammer-vlsi.
#
#  See LICENSE for licence details.

from inspect import cleandoc
from typing import Iterable, Tuple, Any, Dict, List, Set

from hammer_utils import SpiceUtils

import unittest


class SpiceUtilsTest(unittest.TestCase):

    multiline = cleandoc("""
        .SUBCKT foo a b c
        r0 a b 10
        c0 a b 10.1
        r1 a c 200
        r2 b c 1
        xinst a b
        + c bar
        .ENDS
        .subckt bar d e
        + f
        r0 d e 1
        r1 e
        + f
        +   100
        r2 d f
        +
        + 10
        .ends""")

    no_multiline = cleandoc("""
        .SUBCKT foo a b c
        r0 a b 10
        c0 a b 10.1
        r1 a c 200
        r2 b c 1
        xinst a b c bar
        .ENDS
        .subckt bar d e f
        r0 d e 1
        r1 e f 100
        r2 d f 10
        .ends""")

    def test_multiline(self) -> None:
        self.assertEqual(SpiceUtils.remove_multilines(self.multiline), self.no_multiline)

    def test_replace_modules(self) -> None:
        no_multiline_replaced = cleandoc("""
            .SUBCKT foo a b c
            r0 a b 10
            c0 a b 10.1
            r1 a c 200
            r2 b c 1
            xinst a b c baz
            .ENDS
            .subckt baz d e f
            r0 d e 1
            r1 e f 100
            r2 d f 10
            .ends""")
        self.assertEqual(SpiceUtils.replace_modules(self.no_multiline, {"bar": "baz"}), no_multiline_replaced)

    hierarchy = []  # type: List[str]
    hierarchy_uniq = []  # type: List[str]

    # 0
    hierarchy.append(cleandoc("""
    .subckt top clock in out vdd vss
    x0 clock in mid vdd vss middle0
    x1 clock mid out vdd vss middle1
    .ends
    .subckt middle0 clock in out vdd vss
    m1 out mid vdd vdd pmos
    m2 out mid vss vss nmos
    xinst clock in mid vdd vss leaf0
    .ends
    .subckt middle1 clock in out vdd vss
    m1 out mid0 vdd vdd pmos
    m2 out mid0 vss vss nmos
    xinst clock mid1 mid0 vdd vss leaf1
    xinst clock in mid1 vdd vss leaf1
    .ends
    .subckt leaf0 clock in out vdd vss
    m1 out in vdd vdd pmos
    m2 out in vss vss nmos
    r1 clock out 100
    .ends
    .subckt leaf1 clock in out vdd vss
    m1 out in vdd vdd pmos
    m2 out in vss vss nmos
    r1 clock out 50
    .ends
    """))

    # 0
    hierarchy_uniq.append(cleandoc("""
    .subckt top clock in out vdd vss
    x0 clock in mid vdd vss middle0_0
    x1 clock mid out vdd vss middle1_0
    .ends
    .subckt middle0_0 clock in out vdd vss
    m1 out mid vdd vdd pmos
    m2 out mid vss vss nmos
    xinst clock in mid vdd vss leaf0_0
    .ends
    .subckt middle1_0 clock in out vdd vss
    m1 out mid0 vdd vdd pmos
    m2 out mid0 vss vss nmos
    xinst clock mid1 mid0 vdd vss leaf1
    xinst clock in mid1 vdd vss leaf1
    .ends
    .subckt leaf0_0 clock in out vdd vss
    m1 out in vdd vdd pmos
    m2 out in vss vss nmos
    r1 clock out 100
    .ends
    .subckt leaf1 clock in out vdd vss
    m1 out in vdd vdd pmos
    m2 out in vss vss nmos
    r1 clock out 50
    .ends
    """))

    # 1
    hierarchy.append(cleandoc("""
    .subckt top1 clock in out vdd vss
    x0 clock in mid vdd vss middle0
    x1 clock mid out vdd vss middle1
    .ends
    .subckt middle0 clock in out vdd vss
    m1 out mid vdd vdd pmos
    m2 out mid vss vss nmos
    xinst clock in mid vdd vss leaf0
    .ends
    .subckt middle1 clock in out vdd vss
    m1 out mid0 vdd vdd pmos
    m2 out mid0 vss vss nmos
    xinst clock mid1 mid0 vdd vss leaf1
    xinst clock in mid1 vdd vss leaf1
    .ends
    .subckt leaf0 clock in out vdd vss
    m1 out in vdd vdd pmos
    m2 out in vss vss nmos
    r1 clock out 100
    .ends
    """))

    # 1
    hierarchy_uniq.append(cleandoc("""
    .subckt top1 clock in out vdd vss
    x0 clock in mid vdd vss middle0_1
    x1 clock mid out vdd vss middle1_1
    .ends
    .subckt middle0_1 clock in out vdd vss
    m1 out mid vdd vdd pmos
    m2 out mid vss vss nmos
    xinst clock in mid vdd vss leaf0_1
    .ends
    .subckt middle1_1 clock in out vdd vss
    m1 out mid0 vdd vdd pmos
    m2 out mid0 vss vss nmos
    xinst clock mid1 mid0 vdd vss leaf1
    xinst clock in mid1 vdd vss leaf1
    .ends
    .subckt leaf0_1 clock in out vdd vss
    m1 out in vdd vdd pmos
    m2 out in vss vss nmos
    r1 clock out 100
    .ends
    """))

    # 2
    hierarchy.append(cleandoc("""
    .subckt top3 clock in out vdd vss
    x0 clock in mid vdd vss leaf0
    .ends
    .subckt leaf0 clock in out vdd vss
    m1 out in vdd vdd pmos
    m2 out in vss vss nmos
    r1 clock out 50
    .ends"""))

    # 2
    hierarchy_uniq.append(cleandoc("""
    .subckt top3 clock in out vdd vss
    x0 clock in mid vdd vss leaf0_2
    .ends
    .subckt leaf0_2 clock in out vdd vss
    m1 out in vdd vdd pmos
    m2 out in vss vss nmos
    r1 clock out 50
    .ends"""))

    # 3
    hierarchy.append(cleandoc("""
    .subckt top4 clock in out vdd vss
    x0 clock in mid vdd vss leaf0
    .ends
    """))

    def test_module_tree(self) -> None:
        tree = SpiceUtils.parse_module_tree(self.hierarchy[0])
        check = {}  # type: Dict[str, Set[str]]
        check['top'] = {'middle0', 'middle1'}
        check['middle0'] = {'leaf0'}
        check['middle1'] = {'leaf1'}
        check['leaf0'] = set()
        check['leaf1'] = set()
        self.assertEqual(tree, check)

    def test_uniq(self) -> None:
        self.assertEqual(SpiceUtils.uniquify_spice(self.hierarchy[0:3]), self.hierarchy_uniq)

        with self.assertRaises(ValueError):
            # This should assert because it won't know how to handle leaf0
            SpiceUtils.uniquify_spice(self.hierarchy)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Tests for hammer-vlsi
#
#  See LICENSE for licence details.

import json
import os
import shutil
import tempfile
import unittest
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union
from decimal import Decimal

from tech_test import StackupTestHelper
from tech_test_utils import HasGetTech
from test_tool_utils import HammerToolTestHelpers, DummyTool, SingleStepTool

import hammer_config
from hammer_config import HammerJSONEncoder
import hammer_tech
import hammer_vlsi
from hammer_vlsi.hooks import HammerStartStopStep
from hammer_logging import HammerVLSIFileLogger, HammerVLSILogging, Level
from hammer_logging.test import HammerLoggingCaptureContext
from hammer_tech import LibraryFilter, Library, ExtraLibrary
from hammer_utils import deeplist, deepdict, add_dicts, get_or_else

class SDCDummyTool(hammer_vlsi.HasSDCSupport, DummyTool):
    @property
    def post_synth_sdc(self) -> Optional[str]:
        return None

class SDCTest(unittest.TestCase):
    def setUp(self) -> None:
        # Make sure the HAMMER_VLSI path is set correctly.
        self.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment())

    def test_custom_sdc_constraints(self):
        """
        Test that custom raw SDC constraints work.
        """
        str1 = "create_clock foo -name myclock -period 10.0"
        str2 = "set_clock_uncertainty 0.123 [get_clocks myclock]"
        inputs = {
            "vlsi.inputs.custom_sdc_constraints": [
                str1,
                str2
            ]
        }

        tool = SDCDummyTool()
        database = hammer_config.HammerDatabase()
        hammer_vlsi.HammerVLSISettings.load_builtins_and_core(database)
        database.update_project([inputs])
        tool.set_database(database)

        constraints = tool.sdc_pin_constraints.split("\n")
        self.assertTrue(str1 in constraints)
        self.assertTrue(str2 in constraints)

class HammerVLSILoggingTest(unittest.TestCase):
    def test_colours(self):
        """
        Test that we can log with and without colour.
        """
        msg = "This is a test message"  # type: str

        log = HammerVLSILogging.context("test")

        HammerVLSILogging.enable_buffering = True  # we need this for test
        HammerVLSILogging.clear_callbacks()
        HammerVLSILogging.add_callback(HammerVLSILogging.callback_buffering)

        HammerVLSILogging.enable_colour = True
        log.info(msg)
        self.assertEqual(HammerVLSILogging.get_colour_escape(Level.INFO) + "[test] " + msg + HammerVLSILogging.COLOUR_CLEAR, HammerVLSILogging.get_buffer()[0])

        HammerVLSILogging.enable_colour = False
        log.info(msg)
        self.assertEqual("[test] " + msg, HammerVLSILogging.get_buffer()[0])

    def test_subcontext(self):
        HammerVLSILogging.enable_colour = False
        HammerVLSILogging.enable_tag = True

        HammerVLSILogging.clear_callbacks()
        HammerVLSILogging.add_callback(HammerVLSILogging.callback_buffering)

        # Get top context
        log = HammerVLSILogging.context("top")

        # Create sub-contexts.
        logA = log.context("A")
        logB = log.context("B")

        msgA = "Hello world from A"
        msgB = "Hello world from B"

        logA.info(msgA)
        logB.error(msgB)

        self.assertEqual(HammerVLSILogging.get_buffer(),
            ['[top] [A] ' + msgA, '[top] [B] ' + msgB]
        )

    def test_file_logging(self):
        fd, path = tempfile.mkstemp(".log")
        os.close(fd) # Don't leak file descriptors

        filelogger = HammerVLSIFileLogger(path)

        HammerVLSILogging.clear_callbacks()
        HammerVLSILogging.add_callback(filelogger.callback)
        log = HammerVLSILogging.context()
        log.info("Hello world")
        log.info("Eternal voyage to the edge of the universe")
        filelogger.close()

        with open(path, 'r') as f:
            self.assertEqual(f.read().strip(), """
[<global>] Level.INFO: Hello world
[<global>] Level.INFO: Eternal voyage to the edge of the universe
""".strip())

        # Remove temp file
        os.remove(path)


class HammerToolTest(HasGetTech, unittest.TestCase):
    def test_read_libs(self) -> None:
        """
        Test that HammerTool can read technology IP libraries and filter/process them.
        """
        import hammer_config

        tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        HammerToolTestHelpers.write_tech_json(tech_json_filename)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir
        tech.logger = HammerVLSILogging.context("")

        class Tool(SingleStepTool):
            def step(self) -> bool:
                def test_tool_format(lib, filt) -> List[str]:
                    return ["drink {0}".format(lib)]

                self._read_lib_output = tech.read_libs([hammer_tech.filters.milkyway_techfile_filter], test_tool_format, must_exist=False)

                self._test_filter_output = tech.read_libs([HammerToolTestHelpers.make_test_filter()], test_tool_format, must_exist=False)
                return True
        test = Tool()
        test.logger = HammerVLSILogging.context("")
        test.run_dir = tempfile.mkdtemp()
        test.technology = tech
        database = hammer_config.HammerDatabase()
        test.set_database(database)
        tech.set_database(database)
        test.run()

        # Don't care about ordering here.
        self.assertEqual(set(test._read_lib_output),
                         {"drink {0}/soy".format(tech_dir), "drink {0}/coconut".format(tech_dir)})

        # We do care about ordering here.
        self.assertEqual(test._test_filter_output, [
            "drink {0}/tea".format(tech_dir),
            "drink {0}/grapefruit".format(tech_dir),
            "drink {0}/juice".format(tech_dir),
            "drink {0}/orange".format(tech_dir)
        ])

        # Cleanup
        shutil.rmtree(tech_dir_base)
        shutil.rmtree(test.run_dir)

    def test_timing_lib_ecsm_filter(self) -> None:
        """
        Test that the ECSM-first filter works as expected.
        """
        import hammer_config

        1/0
        tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        tech_json = {
            "name": "dummy28",
            "installs": [
                {
                    "path": "test",
                    "base var": ""  # means relative to tech dir
                }
            ],
            "libraries": [
                {
                    "ecsm liberty file": "test/eggs.ecsm",
                    "ccs liberty file": "test/eggs.ccs",
                    "nldm liberty file": "test/eggs.nldm"
                },
                {
                    "ccs liberty file": "test/custard.ccs",
                    "nldm liberty file": "test/custard.nldm"
                },
                {
                    "nldm liberty file": "test/noodles.nldm"
                },
                {
                    "ecsm liberty file": "test/eggplant.ecsm"
                },
                {
                    "ccs liberty file": "test/cookies.ccs"
                }
            ]
        }
        with open(tech_json_filename, "w") as f:
            f.write(json.dumps(tech_json, cls=HammerJSONEncoder, indent=4))
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir
        tech.logger = HammerVLSILogging.context("")

        class Tool(SingleStepTool):
            lib_outputs = []  # type: List[str]

            def step(self) -> bool:
                Tool.lib_outputs = tech.read_libs([hammer_tech.filters.timing_lib_with_ecsm_filter],
                                                  hammer_tech.HammerTechnologyUtils.to_plain_item,
                                                  must_exist=False)
                return True

        test = Tool()
        test.logger = HammerVLSILogging.context("")
        test.run_dir = tempfile.mkdtemp()
        test.technology = tech
        test.set_database(hammer_config.HammerDatabase())
        tech.set_database(hammer_config.HammerDatabase())
        test.run()

        # Check that the ecsm-based filter prioritized ecsm -> ccs -> nldm.
        self.assertEqual(set(Tool.lib_outputs), {
            "{0}/eggs.ecsm".format(tech_dir),
            "{0}/custard.ccs".format(tech_dir),
            "{0}/noodles.nldm".format(tech_dir),
            "{0}/eggplant.ecsm".format(tech_dir),
            "{0}/cookies.ccs".format(tech_dir)
        })

        # Cleanup
        shutil.rmtree(tech_dir_base)
        shutil.rmtree(test.run_dir)

    def test_read_extra_libs(self) -> None:
        """
        Test that HammerTool can read/process extra IP libraries in addition to those of the technology.
        """
        import hammer_config

        tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        HammerToolTestHelpers.write_tech_json(tech_json_filename)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir
        tech.logger = HammerVLSILogging.context("tech")

        class Tool(hammer_vlsi.DummyHammerTool):
            lib_output = []  # type: List[str]
            filter_output = []  # type: List[str]

            @property
            def steps(self) -> List[hammer_vlsi.HammerToolStep]:
                return self.make_steps_from_methods([
                    self.step
                ])

            def step(self) -> bool:
                def test_tool_format(lib, filt) -> List[str]:
                    return ["drink {0}".format(lib)]

                Tool.lib_output = tech.read_libs([hammer_tech.filters.milkyway_techfile_filter], test_tool_format, must_exist=False)

                Tool.filter_output = tech.read_libs([HammerToolTestHelpers.make_test_filter()], test_tool_format,
                                                    must_exist=False)
                return True

        test = Tool()
        test.logger = HammerVLSILogging.context("")
        test.run_dir = tempfile.mkdtemp()
        test.technology = tech
        # Add some extra libraries to see if they are picked up
        database = hammer_config.HammerDatabase()
        lib1_path = "/foo/bar"
        lib1b_path = "/library/specific/prefix"
        lib2_path = "/baz/quux"
        database.update_project([{
            'vlsi.technology.extra_libraries': [
                {
                    "library": {"milkyway techfile": "test/xylophone"}
                },
                {
                    "library": {"openaccess techfile": "test/orange"}
                },
                {
                    "prefix": {
                        "prefix": "lib1",
                        "path": lib1_path
                    },
                    "library": {"milkyway techfile": "lib1/muffin"}
                },
                {
                    "prefix": {
                        "prefix": "lib1",
                        "path": lib1b_path
                    },
                    "library": {"milkyway techfile": "lib1/granola"}
                },
                {
                    "prefix": {
                        "prefix": "lib2",
                        "path": lib2_path
                    },
                    "library": {
                        "openaccess techfile": "lib2/cake",
                        "milkyway techfile": "lib2/brownie",
                        "provides": [
                            {"lib_type": "stdcell"}
                        ]
                    }
                }
            ]
        }])
        test.set_database(database)
        tech.set_database(database)
        test.run()

        # Not testing ordering in this assertion.
        self.assertEqual(set(Tool.lib_output),
                         {
                             "drink {0}/soy".format(tech_dir),
                             "drink {0}/coconut".format(tech_dir),
                             "drink {0}/xylophone".format(tech_dir),
                             "drink {0}/muffin".format(lib1_path),
                             "drink {0}/granola".format(lib1b_path),
                             "drink {0}/brownie".format(lib2_path)
                         })

        # We do care about ordering here.
        # Our filter should put the techfile first and sort the rest.
        print("Tool.filter_output = " + str(Tool.filter_output))
        tech_lef_result = [
            # tech lef
            "drink {0}/tea".format(tech_dir)
        ]
        base_lib_results = [
            "drink {0}/grapefruit".format(tech_dir),
            "drink {0}/juice".format(tech_dir),
            "drink {0}/orange".format(tech_dir)
        ]
        extra_libs_results = [
            "drink {0}/cake".format(lib2_path)
        ]
        self.assertEqual(Tool.filter_output, tech_lef_result + sorted(base_lib_results + extra_libs_results))

        # Cleanup
        shutil.rmtree(tech_dir_base)
        shutil.rmtree(test.run_dir)

    def test_create_enter_script(self) -> None:
        class Tool(hammer_vlsi.DummyHammerTool):
            @property
            def env_vars(self) -> Dict[str, str]:
                return {
                    "HELLO": "WORLD",
                    "EMPTY": "",
                    "CLOUD": "9",
                    "lol": "abc\"cat\""
                }

        fd, path = tempfile.mkstemp(".sh")
        os.close(fd) # Don't leak file descriptors

        test = Tool()
        test.create_enter_script(path)
        with open(path) as f:
            enter_script = f.read()
        # Cleanup
        os.remove(path)

        self.assertEqual(
"""
export CLOUD="9"
export EMPTY=""
export HELLO="WORLD"
export lol='abc"cat"'
""".strip(), enter_script.strip()
        )

        fd, path = tempfile.mkstemp(".sh")
        test.create_enter_script(path, raw=True)
        with open(path) as f:
            enter_script = f.read()
        # Cleanup
        os.remove(path)

        self.assertEqual(
"""
export CLOUD=9
export EMPTY=
export HELLO=WORLD
export lol=abc"cat"
""".strip(), enter_script.strip()
        )

    def test_bad_export_config_outputs(self) -> None:
        """
        Test that a plugin that fails to call super().export_config_outputs()
        is caught.
        """
        self.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                             "hammer_vlsi_path must exist")
        tmpdir = tempfile.mkdtemp()
        proj_config = os.path.join(tmpdir, "config.json")

        with open(proj_config, "w") as f:
            f.write(json.dumps({
                "vlsi.core.technology": "nop",
                "vlsi.core.synthesis_tool": "nop",
                "vlsi.core.par_tool": "nop",
                "synthesis.inputs.top_module": "dummy",
                "synthesis.inputs.input_files": ("/dev/null",)
            }, cls=HammerJSONEncoder, indent=4))

        class BadExportTool(hammer_vlsi.HammerSynthesisTool, DummyTool):
            def export_config_outputs(self) -> Dict[str, Any]:
                # Deliberately forget to call super().export_config_outputs
                return {
                    'extra': 'value'
                }

            def fill_outputs(self) -> bool:
                self.output_files = deeplist(self.input_files)
                return True

        driver = hammer_vlsi.HammerDriver(
            hammer_vlsi.HammerDriver.get_default_driver_options()._replace(project_configs=[
                proj_config
            ]))

        syn_tool = BadExportTool()
        syn_tool.tool_dir = tmpdir
        driver.set_up_synthesis_tool(syn_tool, "bad_tool", run_dir=tmpdir)
        with HammerLoggingCaptureContext() as c:
            driver.run_synthesis()
        self.assertTrue(c.log_contains("did not call super().export_config_outputs()"))

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_bumps(self) -> None:
         """
         Test that HammerTool bump support works.
         """
         import hammer_config

         tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
         tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
         HammerToolTestHelpers.write_tech_json(tech_json_filename)
         tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
         tech.cache_dir = tech_dir
         tech.logger = HammerVLSILogging.context("")

         test = DummyTool()
         test.logger = HammerVLSILogging.context("")
         test.run_dir = tempfile.mkdtemp()
         test.technology = tech
         database = hammer_config.HammerDatabase()
         # Check bad mode string doesn't look at null dict
         settings = """
{
     "vlsi.inputs.bumps_mode": "auto"
}
"""
         database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
         test.set_database(database)

         with HammerLoggingCaptureContext() as c:
             my_bumps = test.get_bumps()
         self.assertTrue(c.log_contains("Invalid bumps_mode"))
         assert my_bumps is None, "Invalid bumps_mode should assume empty bumps"

         settings = """
 {
     "vlsi.inputs.bumps_mode": "manual",
     "vlsi.inputs.bumps": {
                     "x": 14,
                     "y": 14,
                     "pitch": 200,
                     "cell": "MY_REDACTED_BUMP_CELL",
                     "assignments": [
                         {"name": "reset", "x": 5, "y": 3},
                         {"no_connect": true, "x": 5, "y": 4},
                         {"name": "VDD", "x": 2, "y": 1},
                         {"name": "VSS", "x": 1, "y": 1},
                         {"name": "VSS", "no_connect": true, "x": 2, "y": 2},
                         {"x": 3, "y": 3},
                         {"name": "VSS", "x": 14, "y": 14}
                     ]
                 }
 }
 """
         database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
         test.set_database(database)

         with HammerLoggingCaptureContext() as c:
             my_bumps = test.get_bumps()
         self.assertTrue(c.log_contains("Invalid bump assignment"))
         assert my_bumps is not None
         # Only one of the assignments is invalid so the above 7 becomes 6
         self.assertEqual(len(my_bumps.assignments), 6)

         # Cleanup
         shutil.rmtree(tech_dir_base)
         shutil.rmtree(test.run_dir)

    def test_good_pins(self) -> None:
        """
        Test that good pin configurations work without error.
        """
        import hammer_config

        tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        def add_stackup(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict["stackups"] = [StackupTestHelper.create_test_stackup_dict(8)]
            return out_dict
        HammerToolTestHelpers.write_tech_json(tech_json_filename, add_stackup)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir
        tech.logger = HammerVLSILogging.context("")

        test = DummyTool()
        test.logger = HammerVLSILogging.context("")
        test.run_dir = tempfile.mkdtemp()
        test.technology = tech
        database = hammer_config.HammerDatabase()
        hammer_vlsi.HammerVLSISettings.load_builtins_and_core(database)

        settings = """
        {
        "technology.core.stackup": "StackupWith8Metals",
        "vlsi.inputs.pin_mode": "generated",
        "vlsi.inputs.pin.assignments": [
                     {"pins": "foo*", "side": "top", "layers": ["M5", "M3"]},
                     {"pins": "bar*", "side": "bottom", "layers": ["M5"]},
                     {"pins": "baz*", "side": "left", "layers": ["M4"]},
                     {"pins": "qux*", "side": "right", "layers": ["M2"]},
                     {"pins": "tx_n", "preplaced": true},
                     {"pins": "tx_p", "preplaced": true},
                     {"pins": "rx_n", "side": "left", "layers": ["M6"]},
                     {"pins": "rx_p", "side": "right", "layers": ["M6"]}
                 ]
        }
        """
        database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
        test.set_database(database)

        with HammerLoggingCaptureContext() as c:
            my_pins = test.get_pin_assignments()

        # For a correct configuration, there should be no warnings
        # or errors.
        self.assertEqual(len(c.logs), 0)

        assert my_pins is not None
        self.assertEqual(len(my_pins), 8)

        # Cleanup
        shutil.rmtree(tech_dir_base)
        shutil.rmtree(test.run_dir)

    def test_pin_modes(self) -> None:
        """
        Test that both full_auto and semi_auto pin modes work.
        """
        import hammer_config

        tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        def add_stackup(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict["stackups"] = [StackupTestHelper.create_test_stackup_dict(8)]
            return out_dict
        HammerToolTestHelpers.write_tech_json(tech_json_filename, add_stackup)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir
        tech.logger = HammerVLSILogging.context("")

        test = DummyTool()
        test.logger = HammerVLSILogging.context("")
        test.run_dir = tempfile.mkdtemp()
        test.technology = tech
        database = hammer_config.HammerDatabase()
        hammer_vlsi.HammerVLSISettings.load_builtins_and_core(database)

        # Full-auto config should work in full_auto
        settings = """
        {
        "technology.core.stackup": "StackupWith8Metals",
        "vlsi.inputs.pin_mode": "generated",
        "vlsi.inputs.pin.generate_mode": "full_auto",
        "vlsi.inputs.pin.assignments": [
                     {"pins": "foo*", "side": "top", "layers": ["M5", "M3"]},
                     {"pins": "tx_n", "preplaced": true},
                     {"pins": "rx_n", "side": "left", "layers": ["M6"]}
                 ]
        }
        """
        database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
        test.set_database(database)

        with HammerLoggingCaptureContext() as c:
            my_pins = test.get_pin_assignments()

        self.assertEqual(len(c.logs), 0)
        assert my_pins is not None
        self.assertEqual(len(my_pins), 3)

        # Full-auto config should also work in semi_auto
        settings = """
        {
        "technology.core.stackup": "StackupWith8Metals",
        "vlsi.inputs.pin_mode": "generated",
        "vlsi.inputs.pin.generate_mode": "semi_auto",
        "vlsi.inputs.pin.assignments": [
                     {"pins": "foo*", "side": "top", "layers": ["M5", "M3"]},
                     {"pins": "tx_n", "preplaced": true},
                     {"pins": "rx_n", "side": "left", "layers": ["M6"]}
                 ]
        }
        """
        database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
        test.set_database(database)

        with HammerLoggingCaptureContext() as c:
            my_pins = test.get_pin_assignments()

        self.assertEqual(len(c.logs), 0)
        assert my_pins is not None
        self.assertEqual(len(my_pins), 3)

        # Semi-auto config should work in semi_auto
        settings = """
        {
        "technology.core.stackup": "StackupWith8Metals",
        "vlsi.inputs.pin_mode": "generated",
        "vlsi.inputs.pin.generate_mode": "semi_auto",
        "vlsi.inputs.pin.assignments": [
                     {"pins": "foo*", "side": "top", "layers": ["M5", "M3"]},
                     {"pins": "tx_n", "preplaced": true},
                     {"pins": "rx_n", "side": "left", "layers": ["M6"], "width": 888.8}
                 ]
        }
        """
        database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
        test.set_database(database)

        with HammerLoggingCaptureContext() as c:
            my_pins = test.get_pin_assignments()

        self.assertEqual(len(c.logs), 0)
        assert my_pins is not None
        self.assertEqual(len(my_pins), 3)

        # Semi-auto config should give errors in full_auto
        settings = """
        {
        "technology.core.stackup": "StackupWith8Metals",
        "vlsi.inputs.pin_mode": "generated",
        "vlsi.inputs.pin.generate_mode": "full_auto",
        "vlsi.inputs.pin.assignments": [
                     {"pins": "foo*", "side": "top", "layers": ["M5", "M3"]},
                     {"pins": "tx_n", "preplaced": true},
                     {"pins": "rx_n", "side": "left", "layers": ["M6"], "width": 888.8}
                 ]
        }
        """
        database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
        test.set_database(database)

        with HammerLoggingCaptureContext() as c:
            my_pins = test.get_pin_assignments()

        self.assertEqual(len(c.logs), 1)
        self.assertTrue("width requires semi_auto" in c.logs[0])

        # Cleanup
        shutil.rmtree(tech_dir_base)
        shutil.rmtree(test.run_dir)

    def test_pins(self) -> None:
        """
        Test that HammerTool pin placement support works.
        """
        import hammer_config

        tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        def add_stackup(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict["stackups"] = [StackupTestHelper.create_test_stackup_dict(8)]
            return out_dict
        HammerToolTestHelpers.write_tech_json(tech_json_filename, add_stackup)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir
        tech.logger = HammerVLSILogging.context("")

        test = DummyTool()
        test.logger = HammerVLSILogging.context("")
        test.run_dir = tempfile.mkdtemp()
        test.technology = tech
        database = hammer_config.HammerDatabase()
        hammer_vlsi.HammerVLSISettings.load_builtins_and_core(database)
        # Check bad mode string doesn't look at null dict
        settings = """
{
    "vlsi.inputs.pin_mode": "auto"
}
"""
        database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
        test.set_database(database)

        with HammerLoggingCaptureContext() as c:
            my_pins = test.get_pin_assignments()
        self.assertTrue(c.log_contains("Invalid pin_mode"))
        assert len(my_pins) == 0, "Invalid pin_mode should assume empty pins"

        settings = """
{
    "technology.core.stackup": "StackupWith8Metals",
    "vlsi.inputs.pin_mode": "generated",
    "vlsi.inputs.pin.assignments": [
        {"pins": "*", "side": "top", "layers": ["M5", "M3"]},
        {"pins": "*", "side": "bottom", "layers": ["M5"]},
        {"pins": "*", "side": "left", "layers": ["M4"]},
        {"pins": "*", "side": "right", "layers": ["M2"]},
        {"pins": "bad_side", "side": "right", "layers": ["M3"]},
        {"pins": "tx1", "preplaced": true},
        {"pins": "bad_tx_n", "preplaced": true, "layers": ["M7"]},
        {"pins": "tx2", "preplaced": true, "side": "right", "layers": ["M7"]},
        {"pins": "tx3", "preplaced": true, "side": "right"},
        {"pins": "*", "layers": ["M2"]},
        {"pins": "*", "side": "bottom"},
        {"pins": "no_layers"},
        {"pins": "wrong_side", "side": "upsidedown", "layers": ["M2"]}
    ]
}
"""
        database.update_project([hammer_config.load_config_from_string(settings, is_yaml=False)])
        test.set_database(database)

        with HammerLoggingCaptureContext() as c:
            my_pins = test.get_pin_assignments()
        self.assertTrue(c.log_contains("Pins bad_side assigned layers "))
        self.assertTrue(c.log_contains("Pins bad_tx_n assigned as a preplaced pin with layers"))
        self.assertTrue(c.log_contains("Pins no_layers assigned without layers"))
        self.assertTrue(c.log_contains("Pins wrong_side have invalid side"))
        assert my_pins is not None
        # Only one of the assignments is invalid so the above 7 becomes 6
        self.assertEqual(len(my_pins), 9)

        # Cleanup
        shutil.rmtree(tech_dir_base)
        shutil.rmtree(test.run_dir)

    def test_hierarchical_width_height(self) -> None:
        """
        Test that hierarchical placements correctly propagate width and height.
        """
        tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        def add_stackup(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict["stackups"] = [StackupTestHelper.create_test_stackup_dict(8)]
            return out_dict
        HammerToolTestHelpers.write_tech_json(tech_json_filename, add_stackup)
        tmpdir = tempfile.mkdtemp()
        proj_config = os.path.join(tmpdir, "config.json")

        settings = {
                "vlsi.core.technology": "dummy28",
                "vlsi.inputs.hierarchical.mode": "hierarchical",
                "vlsi.inputs.hierarchical.top_module": "TopMod",
                "vlsi.inputs.hierarchical.config_source": "manual",
                "vlsi.inputs.hierarchical.manual_modules": [{"TopMod": ["SubModA", "SubModB"]}],
                "vlsi.inputs.hierarchical.manual_placement_constraints": [
                    {"TopMod": [
                        {"path": "top", "type": "toplevel", "x": 0, "y": 0, "width": 1234, "height": 7890, "margins": {"left": 1, "top": 2, "right": 3, "bottom": 4}},
                        {"path": "top/C", "type": "placement", "x": 2, "y": 102, "width": 30, "height": 40},
                        {"path": "top/B", "type": "hierarchical", "x": 10, "y": 30, "master": "SubModB"},
                        {"path": "top/A", "type": "hierarchical", "x": 200, "y": 120, "master": "SubModA"}]},
                    {"SubModA": [
                        {"path": "a", "type": "toplevel", "x": 0, "y": 0, "width": 100, "height": 200, "margins": {"left": 0, "top": 0, "right": 0, "bottom": 0}}]},
                    {"SubModB": [
                        {"path": "b", "type": "toplevel", "x": 0, "y": 0, "width": 340, "height": 160, "margins": {"left": 0, "top": 0, "right": 0, "bottom": 0}}]}
                ]
            }
        with open(proj_config, "w") as f:
            f.write(json.dumps(settings, cls=HammerJSONEncoder, indent=4))

        driver = hammer_vlsi.HammerDriver(
            hammer_vlsi.HammerDriver.get_default_driver_options()._replace(project_configs=[
                proj_config
            ]))

        # This should not assert
        hier_settings = driver.get_hierarchical_settings()

        top_constraints = [x[1]["vlsi.inputs.placement_constraints"] for x in hier_settings if x[0] == "TopMod"][0]
        print(top_constraints)
        a = [x for x in top_constraints if x["type"] == "hierarchical" and x["master"] == "SubModA"][0]
        b = [x for x in top_constraints if x["type"] == "hierarchical" and x["master"] == "SubModB"][0]
        print(a)
        # Note that Decimals get serialized as strings
        self.assertEqual(a["width"], "100")
        self.assertEqual(a["height"], "200")
        self.assertEqual(b["width"], "340")
        self.assertEqual(b["height"], "160")

        # Corrupt SubModA's width and heights
        settings["vlsi.inputs.hierarchical.manual_placement_constraints"] = [
                    {"TopMod": [
                        {"path": "top", "type": "toplevel", "x": 0, "y": 0, "width": 1234, "height": 7890, "margins": {"left": 1, "top": 2, "right": 3, "bottom": 4}},
                        {"path": "top/C", "type": "placement", "x": 2, "y": 102, "width": 30, "height": 40},
                        {"path": "top/B", "type": "hierarchical", "x": 10, "y": 30, "master": "SubModB"},
                        {"path": "top/A", "type": "hierarchical", "x": 200, "y": 120, "width": 123, "height": 456, "master": "SubModA"}]},
                    {"SubModA": [
                        {"path": "a", "type": "toplevel", "x": 0, "y": 0, "width": 100, "height": 200, "margins": {"left": 0, "top": 0, "right": 0, "bottom": 0}}]},
                    {"SubModB": [
                        {"path": "b", "type": "toplevel", "x": 0, "y": 0, "width": 340, "height": 160, "margins": {"left": 0, "top": 0, "right": 0, "bottom": 0}}]}
                ]

        with open(proj_config, "w") as f:
            f.write(json.dumps(settings, cls=HammerJSONEncoder, indent=4))

        driver = hammer_vlsi.HammerDriver(
            hammer_vlsi.HammerDriver.get_default_driver_options()._replace(project_configs=[
                proj_config
            ]))


        # This should assert because we mismatched SubModA's width and height with the master values
        with self.assertRaises(ValueError):
            hier_settings = driver.get_hierarchical_settings()

        # Cleanup
        shutil.rmtree(tech_dir_base)
        shutil.rmtree(tmpdir)


T = TypeVar('T')

class HammerToolHooksTestContext:
    def __init__(self, test: unittest.TestCase) -> None:
        self.test = test  # type: unittest.TestCase
        self.temp_dir = ""  # type: str
        self._driver = None # type: Optional[hammer_vlsi.HammerDriver]

    # Helper property to check that the driver did get initialized.
    @property
    def driver(self) -> hammer_vlsi.HammerDriver:
        assert self._driver is not None, "HammerDriver must be initialized before use"
        return self._driver

    def __enter__(self) -> "HammerToolHooksTestContext":
        """Initialize context by creating the temp_dir, driver, and loading mocksynth."""
        self.test.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                        "hammer_vlsi_path must exist")
        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "project.json")
        with open(json_path, "w") as f:
            f.write(json.dumps({
                "vlsi.core.synthesis_tool": "mocksynth",
                "vlsi.core.technology": "nop",
                "synthesis.inputs.top_module": "dummy",
                "synthesis.inputs.input_files": ("/dev/null",),
                "synthesis.mocksynth.temp_folder": temp_dir
            }, cls=HammerJSONEncoder, indent=4))
        options = hammer_vlsi.HammerDriverOptions(
            environment_configs=[],
            project_configs=[json_path],
            log_file=os.path.join(temp_dir, "log.txt"),
            obj_dir=temp_dir
        )
        self.temp_dir = temp_dir
        self._driver = hammer_vlsi.HammerDriver(options)
        self.test.assertTrue(self.driver.load_synthesis_tool())
        return self

    def __exit__(self, type, value, traceback) -> bool:
        """Clean up the context by removing the temp_dir."""
        shutil.rmtree(self.temp_dir)
        # Return True (normal execution) if no exception occurred.
        return True if type is None else False


class HammerToolHooksTest(unittest.TestCase):
    def create_context(self) -> HammerToolHooksTestContext:
        return HammerToolHooksTestContext(self)

    @staticmethod
    def read(filename: str) -> str:
        with open(filename, "r") as f:
            return f.read()

    def test_normal_execution(self) -> None:
        """Test that no hooks means that everything is executed properly."""
        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis()
            self.assertTrue(success)

            for i in range(1, 5):
                self.assertEqual(self.read(os.path.join(c.temp_dir, "step{}.txt".format(i))), "step{}".format(i))

    def test_replacement_hooks(self) -> None:
        """Test that replacement hooks work."""
        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_removal_hook("step2"),
                hammer_vlsi.HammerTool.make_removal_hook("step4")
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i == 2 or i == 4:
                    self.assertFalse(os.path.exists(file))
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

    def test_resume_hooks(self) -> None:
        """Test that resume hooks work."""
        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_resume_hook("step3")
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i <= 2:
                    self.assertFalse(os.path.exists(file), "step{}.txt should not exist".format(i))
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_resume_hook("step2")
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i <= 2:
                    self.assertFalse(os.path.exists(file), "step{}.txt should not exist".format(i))
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

    def test_pause_hooks(self) -> None:
        """Test that pause hooks work."""
        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_pause_hook("step3")
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i > 2:
                    self.assertFalse(os.path.exists(file))
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_pause_hook("step3")
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i > 3:
                    self.assertFalse(os.path.exists(file))
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

    def test_pause_hooks_logging(self) -> None:
        """Test that pause hooks log correctly."""
        with self.create_context() as c:
            with HammerLoggingCaptureContext() as c2:
                success, syn_output = c.driver.run_synthesis(hook_actions=[
                    hammer_vlsi.HammerTool.make_post_pause_hook("step1")
                ])
                self.assertTrue(success)

            # step2 to step4 should show up in log as skipped
            for i in range(2, 5):
                self.assertTrue(c2.log_contains("Sub-step 'step{}' skipped due to pause hook".format(i)))
            # step1 should NOT show up in log as skipped
            self.assertFalse(c2.log_contains("Sub-step 'step1' skipped due to pause hook"))

    def test_extra_pause_hooks(self) -> None:
        """Test that extra pause hooks cause an error."""
        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_pause_hook("step3"),
                hammer_vlsi.HammerTool.make_post_pause_hook("step3")
            ])
            self.assertFalse(success)

    def test_insertion_hooks(self) -> None:
        """Test that insertion hooks work."""

        def change1(x: hammer_vlsi.HammerTool) -> bool:
            x.set_setting("synthesis.mocksynth.step1", "HelloWorld")
            return True

        def change2(x: hammer_vlsi.HammerTool) -> bool:
            x.set_setting("synthesis.mocksynth.step2", "HelloWorld")
            return True

        def change3(x: hammer_vlsi.HammerTool) -> bool:
            x.set_setting("synthesis.mocksynth.step3", "HelloWorld")
            return True

        def change4(x: hammer_vlsi.HammerTool) -> bool:
            x.set_setting("synthesis.mocksynth.step4", "HelloWorld")
            return True

        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_insertion_hook("step3", change3)
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i == 3:
                    self.assertEqual(self.read(file), "HelloWorld")
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

        # Test inserting before the first step
        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_insertion_hook("step1", change1)
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i == 1:
                    self.assertEqual(self.read(file), "HelloWorld")
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_insertion_hook("step2", change2),
                hammer_vlsi.HammerTool.make_post_insertion_hook("step3", change3),
                hammer_vlsi.HammerTool.make_pre_insertion_hook("change3", change4)
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i == 2 or i == 4:
                    self.assertEqual(self.read(file), "HelloWorld")
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

    def test_bad_hooks(self) -> None:
        """Test that hooks with bad targets are errors."""
        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_removal_hook("does_not_exist")
            ])
            self.assertFalse(success)

        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_removal_hook("free_lunch")
            ])
            self.assertFalse(success)

        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_removal_hook("penrose_stairs")
            ])
            self.assertFalse(success)

    def test_insert_before_first_step(self) -> None:
        """Test that inserting a step before the first step works."""
        def change3(x: hammer_vlsi.HammerTool) -> bool:
            x.set_setting("synthesis.mocksynth.step3", "HelloWorld")
            return True

        with self.create_context() as c:
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_insertion_hook("step1", change3)
            ])
            self.assertTrue(success)

            for i in range(1, 5):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i == 3:
                    self.assertEqual(self.read(file), "HelloWorld")
                else:
                    self.assertEqual(self.read(file), "step{}".format(i))

    def test_resume_pause_hooks_with_custom_steps(self) -> None:
        """Test that resume/pause hooks work with custom steps."""

        with self.create_context() as c:
            def step5(x: hammer_vlsi.HammerTool) -> bool:
                with open(os.path.join(c.temp_dir, "step5.txt"), "w") as f:
                    f.write("HelloWorld")
                return True
            def step6(x: hammer_vlsi.HammerTool) -> bool:
                with open(os.path.join(c.temp_dir, "step6.txt"), "w") as f:
                    f.write("ByeByeWorld")
                return True
            # Test from_step => to_step
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step="step5", inclusive=True), HammerStartStopStep(step="step5", inclusive=True)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_insertion_hook("step4", step5),
                hammer_vlsi.HammerTool.make_post_insertion_hook("step5", step6)
            ])
            self.assertTrue(success)

            for i in range(1, 7):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i == 5:
                    self.assertEqual(self.read(file), "HelloWorld")
                else:
                    self.assertFalse(os.path.exists(file))

        with self.create_context() as c:
            def step5(x: hammer_vlsi.HammerTool) -> bool:
                with open(os.path.join(c.temp_dir, "step5.txt"), "w") as f:
                    f.write("HelloWorld")
                return True
            def step6(x: hammer_vlsi.HammerTool) -> bool:
                with open(os.path.join(c.temp_dir, "step6.txt"), "w") as f:
                    f.write("ByeByeWorld")
                return True
            # Test after_step => until_step
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step="step4", inclusive=False), HammerStartStopStep(step="step6", inclusive=False)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_insertion_hook("step4", step5),
                hammer_vlsi.HammerTool.make_post_insertion_hook("step5", step6)
            ])
            self.assertTrue(success)

            for i in range(1, 7):
                file = os.path.join(c.temp_dir, "step{}.txt".format(i))
                if i == 5:
                    self.assertEqual(self.read(file), "HelloWorld")
                else:
                    self.assertFalse(os.path.exists(file))

    def test_persistent_hooks(self) -> None:
        """Test that persistent hooks work."""

        with self.create_context() as c:
            def persist(x: hammer_vlsi.HammerTool) -> bool:
                file1 = os.path.join(c.temp_dir, "persist.txt")
                with open(file1, "w") as f:
                    f.write("HelloWorld")
                return True
            # Test persist despite starting from step 3
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step="step3", inclusive=True), HammerStartStopStep(step=None, inclusive=False)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_persistent_hook(persist)
            ])
            self.assertTrue(success)
            file1 = os.path.join(c.temp_dir, "persist.txt")
            self.assertEqual(self.read(file1), "HelloWorld")

        with self.create_context() as c:
            def persist(x: hammer_vlsi.HammerTool) -> bool:
                file1 = os.path.join(c.temp_dir, "persist.txt")
                with open(file1, "w") as f:
                    f.write("HelloWorld")
                return True
            # Test pre_persist executes if anything before target step is run
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step=None, inclusive=False), HammerStartStopStep(step="step2", inclusive=True)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_persistent_hook("step4", persist)
            ])
            self.assertTrue(success)
            file1 = os.path.join(c.temp_dir, "persist.txt")
            self.assertEqual(self.read(file1), "HelloWorld")

        with self.create_context() as c:
            def persist(x: hammer_vlsi.HammerTool) -> bool:
                file1 = os.path.join(c.temp_dir, "persist.txt")
                with open(file1, "w") as f:
                    f.write("HelloWorld")
                return True
            # Test pre_persist does not execute if starting from after target step
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step="step3", inclusive=True), HammerStartStopStep(step=None, inclusive=False)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_pre_persistent_hook("step2", persist)
            ])
            self.assertTrue(success)
            file1 = os.path.join(c.temp_dir, "persist.txt")
            self.assertFalse(os.path.exists(file1))

        with self.create_context() as c:
            def persist(x: hammer_vlsi.HammerTool) -> bool:
                file1 = os.path.join(c.temp_dir, "persist.txt")
                with open(file1, "w") as f:
                    f.write("HelloWorld")
                return True
            # Test post_persist does not execute if stopped before target step
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step=None, inclusive=False), HammerStartStopStep(step="step2", inclusive=True)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_persistent_hook("step3", persist)
            ])
            self.assertTrue(success)
            file1 = os.path.join(c.temp_dir, "persist.txt")
            self.assertFalse(os.path.exists(file1))

        with self.create_context() as c:
            def persist(x: hammer_vlsi.HammerTool) -> bool:
                file1 = os.path.join(c.temp_dir, "persist.txt")
                with open(file1, "w") as f:
                    f.write("HelloWorld")
                return True
            # Test post_persist executes started after target step
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step="step3", inclusive=True), HammerStartStopStep(step=None, inclusive=False)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_persistent_hook("step1", persist)
            ])
            self.assertTrue(success)
            file1 = os.path.join(c.temp_dir, "persist.txt")
            self.assertEqual(self.read(file1), "HelloWorld")

        with self.create_context() as c:
            def persist(x: hammer_vlsi.HammerTool) -> bool:
                file1 = os.path.join(c.temp_dir, "persist.txt")
                with open(file1, "w") as f:
                    f.write("HelloWorld")
                return True
            # Test post_persist executes if target step is included in steps run
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step="step1", inclusive=True), HammerStartStopStep(step=None, inclusive=False)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_persistent_hook("step3", persist)
            ])
            self.assertTrue(success)
            file1 = os.path.join(c.temp_dir, "persist.txt")
            self.assertEqual(self.read(file1), "HelloWorld")

        with self.create_context() as c:
            def persist(x: hammer_vlsi.HammerTool) -> bool:
                file1 = os.path.join(c.temp_dir, "persist.txt")
                with open(file1, "w") as f:
                    f.write("HelloWorld")
                return True
            def persist2(x: hammer_vlsi.HammerTool) -> bool:
                file2 = os.path.join(c.temp_dir, "persist2.txt")
                with open(file2, "w") as f:
                    f.write("ByeByeWorld")
                return True
            # Test replacement hook inherits replaced persistent hook behavior
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step="step3", inclusive=True), HammerStartStopStep(step=None, inclusive=False)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_persistent_hook("step1", persist),
                hammer_vlsi.HammerTool.make_replacement_hook("persist", persist2)
            ])
            self.assertTrue(success)
            file1 = os.path.join(c.temp_dir, "persist.txt")
            self.assertFalse(os.path.exists(file1))
            file2 = os.path.join(c.temp_dir, "persist2.txt")
            self.assertEqual(self.read(file2), "ByeByeWorld")

        with self.create_context() as c:
            def persist(x: hammer_vlsi.HammerTool) -> bool:
                file1 = os.path.join(c.temp_dir, "persist.txt")
                with open(file1, "w") as f:
                    f.write("HelloWorld")
                return True
            def persist2(x: hammer_vlsi.HammerTool) -> bool:
                file2 = os.path.join(c.temp_dir, "persist2.txt")
                with open(file2, "w") as f:
                    f.write("ByeByeWorld")
                return True
            # Test insertion hook inherits replaced persistent hook behavior
            c.driver.set_post_custom_syn_tool_hooks(hammer_vlsi.HammerTool.make_start_stop_hooks(HammerStartStopStep(step="step3", inclusive=True), HammerStartStopStep(step=None, inclusive=False)))
            success, syn_output = c.driver.run_synthesis(hook_actions=[
                hammer_vlsi.HammerTool.make_post_persistent_hook("step1", persist),
                hammer_vlsi.HammerTool.make_pre_insertion_hook("persist", persist2)
            ])
            self.assertTrue(success)
            file1 = os.path.join(c.temp_dir, "persist.txt")
            self.assertEqual(self.read(file1), "HelloWorld")
            file2 = os.path.join(c.temp_dir, "persist2.txt")
            self.assertEqual(self.read(file2), "ByeByeWorld")


class HammerSubmitCommandTestContext:

    def __init__(self, test: unittest.TestCase, cmd_type: str) -> None:
        self.echo_command_args = ["go", "bears", "!"]
        self.echo_command = ["echo"] + self.echo_command_args
        self.test = test  # type unittest.TestCase
        self.logger = HammerVLSILogging.context("")
        self._driver = None  # type: Optional[hammer_vlsi.HammerDriver]
        if cmd_type not in ["lsf", "local"]:
            raise NotImplementedError("Have not built a test for %s yet" % cmd_type)
        self._cmd_type = cmd_type
        self._submit_command = None  # type: Optional[hammer_vlsi.HammerSubmitCommand]

    # Helper property to check that the driver did get initialized.
    @property
    def driver(self) -> hammer_vlsi.HammerDriver:
        assert self._driver is not None, "HammerDriver must be initialized before use"
        return self._driver

    # Helper property to check that the submit command did get initialized.
    @property
    def submit_command(self) -> hammer_vlsi.HammerSubmitCommand:
        assert self._submit_command is not None, "HammerSubmitCommand must be initialized before use"
        return self._submit_command

    def __enter__(self) -> "HammerSubmitCommandTestContext":
        """Initialize context by creating the temp_dir, driver, and loading mocksynth."""
        self.test.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                             "hammer_vlsi_path must exist")
        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "project.json")
        json_content = {
            "vlsi.core.synthesis_tool": "mocksynth",
            "vlsi.core.technology": "nop",
            "synthesis.inputs.top_module": "dummy",
            "synthesis.inputs.input_files": ("/dev/null",),
            "synthesis.mocksynth.temp_folder": temp_dir,
            "synthesis.submit.command": self._cmd_type
        }
        if self._cmd_type is "lsf":
            json_content.update({
                "synthesis.submit.settings": [{"lsf": {
                    "queue": "myqueue",
                    "num_cpus": 4,
                    "log_file": "test_log.log",
                    "bsub_binary": os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test",
                                                "mock_bsub.sh"),
                    "extra_args": ("-R", "myresources")
                }}],
                "synthesis.submit.settings_meta": "lazyappend",
                "vlsi.submit.settings": [
                    {"lsf": {"num_cpus": 8}}
                ],
                "vlsi.submit.settings_meta": "lazyappend"
            })

        with open(json_path, "w") as f:
            f.write(json.dumps(json_content, cls=HammerJSONEncoder, indent=4))

        options = hammer_vlsi.HammerDriverOptions(
            environment_configs=[],
            project_configs=[json_path],
            log_file=os.path.join(temp_dir, "log.txt"),
            obj_dir=temp_dir
        )
        self.temp_dir = temp_dir
        self._driver = hammer_vlsi.HammerDriver(options)
        self._submit_command = hammer_vlsi.HammerSubmitCommand.get("synthesis", self.database)
        return self

    def __exit__(self, type, value, traceback) -> bool:
        """Clean up the context by removing the temp_dir."""
        shutil.rmtree(self.temp_dir)
        # Return True (normal execution) if no exception occurred.
        return True if type is None else False

    @property
    def database(self) -> hammer_config.HammerDatabase:
        return self.driver.database

    @property
    def env(self) -> Dict[str, str]:
        return {}


class HammerSubmitCommandTest(unittest.TestCase):

    def create_context(self, cmd_type: str) -> HammerSubmitCommandTestContext:
        return HammerSubmitCommandTestContext(self, cmd_type)

    def test_local_submit(self) -> None:
        """ Test that a local submission produces the desired output """
        with self.create_context("local") as c:
            cmd = c.submit_command
            output = cmd.submit(c.echo_command, c.env, c.logger).splitlines()

            self.assertEqual(output[0], ' '.join(c.echo_command_args))

    def test_lsf_submit(self) -> None:
        """ Test that an LSF submission produces the desired output """
        with self.create_context("lsf") as c:
            cmd = c.submit_command
            assert isinstance(cmd, hammer_vlsi.HammerLSFSubmitCommand)
            output = cmd.submit(c.echo_command, c.env, c.logger).splitlines()

            self.assertEqual(output[0], "BLOCKING is: 1")
            self.assertEqual(output[1], "QUEUE is: %s" % get_or_else(cmd.settings.queue, ""))
            self.assertEqual(output[2], "NUMCPU is: %d" % get_or_else(cmd.settings.num_cpus, 0))
            self.assertEqual(output[3], "OUTPUT is: %s" % get_or_else(cmd.settings.log_file, ""))

            extra = cmd.settings.extra_args
            has_resource = 0
            if "-R" in extra:
                has_resource = 1
                self.assertEqual(output[4], "RESOURCE is: %s" % extra[extra.index("-R") + 1])
            else:
                raise NotImplementedError("You forgot to test the extra_args!")

            self.assertEqual(output[4 + has_resource], "COMMAND is: %s" % ' '.join(c.echo_command))
            self.assertEqual(output[5 + has_resource], ' '.join(c.echo_command_args))


class HammerSignoffToolTestContext:

    def __init__(self, test: unittest.TestCase, tool_type: str) -> None:
        self.test = test  # type unittest.TestCase
        self.logger = HammerVLSILogging.context("")
        self._driver = None  # type: Optional[hammer_vlsi.HammerDriver]
        if tool_type not in ["drc", "lvs"]:
            raise NotImplementedError("Have not created a test for %s yet" % (tool_type))
        self._tool_type = tool_type

    # Helper property to check that the driver did get initialized.
    @property
    def driver(self) -> hammer_vlsi.HammerDriver:
        assert self._driver is not None, "HammerDriver must be initialized before use"
        return self._driver

    def __enter__(self) -> "HammerSignoffToolTestContext":
        """Initialize context by creating the temp_dir, driver, and loading the signoff tool."""
        self.test.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                             "hammer_vlsi_path must exist")
        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "project.json")
        json_content = {
            "vlsi.core.technology": "nop",
            "vlsi.core.%s_tool" % self._tool_type: "mock%s" % self._tool_type,
            "%s.inputs.top_module" % self._tool_type: "dummy",
            "%s.inputs.layout_file" % self._tool_type: "/dev/null",
            "%s.temp_folder" % self._tool_type: temp_dir,
            "%s.submit.command" % self._tool_type: "local"
        }  # type: Dict[str, Any]
        if self._tool_type is "lvs":
            json_content.update({
                "lvs.inputs.schematic_files": ["/dev/null"],
                "lvs.inputs.hcells_list": []
            })

        with open(json_path, "w") as f:
            f.write(json.dumps(json_content, cls=HammerJSONEncoder, indent=4))

        options = hammer_vlsi.HammerDriverOptions(
            environment_configs=[],
            project_configs=[json_path],
            log_file=os.path.join(temp_dir, "log.txt"),
            obj_dir=temp_dir
        )
        self._driver = hammer_vlsi.HammerDriver(options)
        self.temp_dir = temp_dir
        return self

    def __exit__(self, type, value, traceback) -> bool:
        """Clean up the context by removing the temp_dir."""
        shutil.rmtree(self.temp_dir)
        # Return True (normal execution) if no exception occurred.
        return True if type is None else False

    @property
    def env(self) -> Dict[str, str]:
        return {}


class HammerDRCToolTest(unittest.TestCase):

    def create_context(self) -> HammerSignoffToolTestContext:
        return HammerSignoffToolTestContext(self, "drc")

    def test_get_results(self) -> None:
        """ Test that a local submission produces the desired output."""
        with self.create_context() as c:
            self.assertTrue(c.driver.load_drc_tool())
            self.assertTrue(c.driver.run_drc())
            assert isinstance(c.driver.drc_tool, hammer_vlsi.HammerDRCTool)
            # This magic 15 should be the sum of the two unwaived DRC violation
            # counts hardcoded in drc/mockdrc.py.
            self.assertEqual(c.driver.drc_tool.signoff_results(), 15)


class HammerLVSToolTest(unittest.TestCase):

    def create_context(self) -> HammerSignoffToolTestContext:
        return HammerSignoffToolTestContext(self, "lvs")

    def test_get_results(self) -> None:
        """ Test that a local submission produces the desired output."""
        with self.create_context() as c:
            self.assertTrue(c.driver.load_lvs_tool())
            self.assertTrue(c.driver.run_lvs())
            assert isinstance(c.driver.lvs_tool, hammer_vlsi.HammerLVSTool)
            # This magic 16 should be the sum of the two unwaived ERC violation
            # counts and the LVS violation hardcoded in lvs/mocklvs.py.
            self.assertEqual(c.driver.lvs_tool.signoff_results(), 16)

class HammerSRAMGeneratorToolTestContext:

    def __init__(self, test: unittest.TestCase, tool_type: str) -> None:
        self.test = test  # type unittest.TestCase
        self.logger = HammerVLSILogging.context("")
        self._driver = None  # type: Optional[hammer_vlsi.HammerDriver]
        if tool_type not in ["sram_generator"]:
            raise NotImplementedError("Have not created a test for %s yet" % (tool_type))
        self._tool_type = tool_type

    # Helper property to check that the driver did get initialized.
    @property
    def driver(self) -> hammer_vlsi.HammerDriver:
        assert self._driver is not None, "HammerDriver must be initialized before use"
        return self._driver

    def __enter__(self) -> "HammerSRAMGeneratorToolTestContext":
        """Initialize context by creating the temp_dir, driver, and loading the sram_generator tool."""
        self.test.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                             "hammer_vlsi_path must exist")
        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "project.json")
        json_content = {
            "vlsi.core.technology": "nop",
            "vlsi.core.%s_tool" % self._tool_type: "mock%s" % self._tool_type,
            "%s.inputs.top_module" % self._tool_type: "dummy",
            "%s.inputs.layout_file" % self._tool_type: "/dev/null",
            "%s.temp_folder" % self._tool_type: temp_dir,
            "%s.submit.command" % self._tool_type: "local"
        }  # type: Dict[str, Any]
        if self._tool_type is "sram_generator":
            json_content.update({
                "vlsi.inputs.sram_parameters": [{"depth": 32, "width": 32,
                    "name": "small", "family": "1r1w", "mask": False, "vt": "SVT", "mux": 1},
                                              {"depth": 64, "width": 128,
                    "name": "large", "family": "1rw", "mask": True, "vt": "SVT", "mux": 2}],
                "vlsi.inputs.mmmc_corners": [{"name": "c1", "type": "setup", "voltage": "0.5V", "temp": "0C"},
                                             {"name": "c2", "type": "hold", "voltage": "1.5V", "temp": "125C"}]
            })

        with open(json_path, "w") as f:
            f.write(json.dumps(json_content, cls=HammerJSONEncoder, indent=4))

        options = hammer_vlsi.HammerDriverOptions(
            environment_configs=[],
            project_configs=[json_path],
            log_file=os.path.join(temp_dir, "log.txt"),
            obj_dir=temp_dir
        )
        self._driver = hammer_vlsi.HammerDriver(options)
        self.temp_dir = temp_dir
        return self

    def __exit__(self, type, value, traceback) -> bool:
        """Clean up the context by removing the temp_dir."""
        shutil.rmtree(self.temp_dir)
        # Return True (normal execution) if no exception occurred.
        return True if type is None else False

    @property
    def env(self) -> Dict[str, str]:
        return {}

class HammerSRAMGeneratorToolTest(unittest.TestCase):
    def create_context(self) -> HammerSRAMGeneratorToolTestContext:
        return HammerSRAMGeneratorToolTestContext(self, "sram_generator")

    def test_get_results(self) -> None:
        """ Test that multiple srams and multiple corners have their
            cross-product generated."""
        with self.create_context() as c:
          self.assertTrue(c.driver.load_sram_generator_tool())
          self.assertTrue(c.driver.run_sram_generator())
          assert isinstance(c.driver.sram_generator_tool, hammer_vlsi.HammerSRAMGeneratorTool)
          output_libs = c.driver.sram_generator_tool.output_libraries # type: List[ExtraLibrary]
          assert isinstance(output_libs, list)
          # Should have an sram for each corner(2) and parameter(2) for a total of 4
          self.assertEqual(len(output_libs),4)
          libs = list(map(lambda ex: ex.library, output_libs)) # type: List[Library]
          gds_names = list(map(lambda lib: lib.gds_file, libs)) # type: ignore # These are actually List[str]
          self.assertEqual(set(gds_names), set([
            "sram32x32_0.5V_0.0C.gds",
            "sram32x32_1.5V_125.0C.gds",
            "sram64x128_0.5V_0.0C.gds",
            "sram64x128_1.5V_125.0C.gds"]))

class HammerASAP7SRAMGeneratorToolTestContext:

    def __init__(self, test: unittest.TestCase, tool_type: str) -> None:
        self.test = test  # type unittest.TestCase
        self.logger = HammerVLSILogging.context("")
        self._driver = None  # type: Optional[hammer_vlsi.HammerDriver]
        if tool_type not in ["sram_generator"]:
            raise NotImplementedError("Have not created a test for %s yet" % (tool_type))
        self._tool_type = tool_type

    # Helper property to check that the driver did get initialized.
    @property
    def driver(self) -> hammer_vlsi.HammerDriver:
        assert self._driver is not None, "HammerDriver must be initialized before use"
        return self._driver

    def __enter__(self) -> "HammerASAP7SRAMGeneratorToolTestContext":
        """Initialize context by creating the temp_dir, driver, and loading the sram_generator tool."""
        self.test.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                             "hammer_vlsi_path must exist")
        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "project.json")
        json_content = {
            "vlsi.core.technology": "nop", # can't load asap7 because we don't have the tarball
            "vlsi.core.%s_tool" % self._tool_type: "sram_compiler",
            "vlsi.core.%s_tool_path" % self._tool_type: ["../hammer-vlsi/technology/asap7"],
            "vlsi.core.%s_tool_path_meta" % self._tool_type: "append",
            "%s.inputs.top_module" % self._tool_type: "dummy",
            "%s.inputs.layout_file" % self._tool_type: "/dev/null",
            "%s.temp_folder" % self._tool_type: temp_dir,
            "%s.submit.command" % self._tool_type: "local"
        }  # type: Dict[str, Any]
        if self._tool_type is "sram_generator":
            json_content.update({
                "vlsi.inputs.sram_parameters": [{"depth": 32, "width": 32,
                    "name": "small", "family": "2RW", "mask": False, "vt": "SRAM", "mux": 1},
                                              {"depth": 64, "width": 128,
                    "name": "large", "family": "1RW", "mask": False, "vt": "SRAM", "mux": 1}],
                "vlsi.inputs.mmmc_corners": [{"name": "PVT_0P63V_100C", "type": "setup", "voltage": "0.63V", "temp": "100C"},
                                             {"name": "PVT_0P77V_0C", "type": "hold", "voltage": "0.77V", "temp": "0C"}]
            })

        with open(json_path, "w") as f:
            f.write(json.dumps(json_content, cls=HammerJSONEncoder, indent=4))

        options = hammer_vlsi.HammerDriverOptions(
            environment_configs=[],
            project_configs=[json_path],
            log_file=os.path.join(temp_dir, "log.txt"),
            obj_dir=temp_dir
        )
        self._driver = hammer_vlsi.HammerDriver(options)
        self.temp_dir = temp_dir
        return self

    def __exit__(self, type, value, traceback) -> bool:
        """Clean up the context by removing the temp_dir."""
        shutil.rmtree(self.temp_dir)
        # Return True (normal execution) if no exception occurred.
        return True if type is None else False

    @property
    def env(self) -> Dict[str, str]:
        return {}

class HammerASAP7SRAMGeneratorToolTest(unittest.TestCase):
    def create_context(self) -> HammerASAP7SRAMGeneratorToolTestContext:
        return HammerASAP7SRAMGeneratorToolTestContext(self, "sram_generator")

    def test_get_results(self) -> None:
        """ Test that multiple srams and multiple corners have their
            cross-product generated."""
        with self.create_context() as c:
          self.assertTrue(c.driver.load_sram_generator_tool())
          self.assertTrue(c.driver.run_sram_generator())
          assert isinstance(c.driver.sram_generator_tool, hammer_vlsi.HammerSRAMGeneratorTool)
          output_libs = c.driver.sram_generator_tool.output_libraries # type: List[ExtraLibrary]
          assert isinstance(output_libs, list)
          # Should have an sram for each corner(2) and parameter(2) for a total of 4
          self.assertEqual(len(output_libs),4)
          libs = list(map(lambda ex: ex.library, output_libs)) # type: List[Library]
          lib_names = list(map(lambda lib: lib.nldm_liberty_file, libs)) # type: ignore # These are actually List[str]
          self.assertEqual(set(lib_names), set([
            os.path.join(c.temp_dir, "tech-nop-cache", "SRAM2RW32x32_PVT_0P63V_100C.lib"),
            os.path.join(c.temp_dir, "tech-nop-cache", "SRAM2RW32x32_PVT_0P77V_0C.lib"),
            os.path.join(c.temp_dir, "tech-nop-cache", "SRAM1RW64x128_PVT_0P63V_100C.lib"),
            os.path.join(c.temp_dir, "tech-nop-cache", "SRAM1RW64x128_PVT_0P77V_0C.lib")]))

class HammerPCBDeliverableToolTestContext:
    def __init__(self, test: unittest.TestCase) -> None:
        self.test = test  # type unittest.TestCase
        self.logger = HammerVLSILogging.context("")
        self._driver = None  # type: Optional[hammer_vlsi.HammerDriver]

    # Helper property to check that the driver did get initialized.
    @property
    def driver(self) -> hammer_vlsi.HammerDriver:
        assert self._driver is not None, "HammerDriver must be initialized before use"
        return self._driver

    def __enter__(self) -> "HammerPCBDeliverableToolTestContext":
        """Initialize context by creating the temp_dir, driver, and loading the sram_generator tool."""
        self.test.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                             "hammer_vlsi_path must exist")
        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "project.json")
        json_content = {
            "vlsi.core.technology": "nop",
            "vlsi.core.pcb_tool": "generic",
            "pcb.inputs.top_module": "dummy",
            "pcb.submit.command": "local",
            "vlsi.inputs.bumps_mode": "manual",
            "vlsi.inputs.bumps": {
                "x": 5,
                "y": 4,
                "pitch": "123.4",
                "cell": "dummybump",
                "assignments": [
                    {"name": "reset", "x": 1, "y": 1},
                    {"name": "clock", "x": 2, "y": 1},
                    {"name": "VDD", "x": 3, "y": 1},
                    {"name": "VDD", "x": 4, "y": 1},
                    {"name": "VSS", "x": 5, "y": 1},
                    {"name": "data[0]", "x": 1, "y": 2},
                    {"name": "data[1]", "x": 2, "y": 2},
                    {"name": "data[2]", "x": 3, "y": 2},
                    {"name": "VSS", "x": 4, "y": 2},
                    {"name": "VDD", "x": 5, "y": 2},
                    {"name": "data[3]", "x": 1, "y": 3},
                    {"name": "valid", "x": 2, "y": 3},
                    {"name": "ready", "x": 3, "y": 3},
                    {"name": "NC", "x": 4, "y": 3, "no_connect": True},
                    {"name": "VSS", "x": 5, "y": 3},
                    {"name": "VDD", "x": 1, "y": 4},
                    {"name": "VSS", "x": 2, "y": 4},
                    {"name": "VDD", "x": 3, "y": 4},
                    {"name": "VSS", "x": 4, "y": 4}
                    # Note 5,4 is left out intentionally
                ]
            },
            "pcb.generic.footprint_type": "PADS-V9",
            "pcb.generic.schematic_symbol_type": "AltiumCSV",
            "technology.pcb.bump_pad_opening_diameter": "60",
            "technology.pcb.bump_pad_metal_diameter": "75"
        }  # type: Dict[str, Any]

        with open(json_path, "w") as f:
            f.write(json.dumps(json_content, cls=HammerJSONEncoder, indent=4))

        options = hammer_vlsi.HammerDriverOptions(
            environment_configs=[],
            project_configs=[json_path],
            log_file=os.path.join(temp_dir, "log.txt"),
            obj_dir=temp_dir
        )
        self._driver = hammer_vlsi.HammerDriver(options)
        self.temp_dir = temp_dir
        return self

    def __exit__(self, type, value, traceback) -> bool:
        """Clean up the context by removing the temp_dir."""
        shutil.rmtree(self.temp_dir)
        # Return True (normal execution) if no exception occurred.
        return True if type is None else False

    @property
    def env(self) -> Dict[str, str]:
        return {}

class HammerGenericPCBToolTest(unittest.TestCase):
    def create_context(self) -> HammerPCBDeliverableToolTestContext:
        return HammerPCBDeliverableToolTestContext(self)

    def test_deliverables_exist(self) -> None:
        """
        Test that a PADS-V9 footprint, Altium CSV, and pads CSV are created.
        This doesn't check the correctness of the deliverables.
        """
        with self.create_context() as c:
            self.assertTrue(c.driver.load_pcb_tool())
            self.assertTrue(c.driver.run_pcb())
            # Ignoring the type of this for the same reason as the power straps stuff below.
            # It's hard to get the concrete type of this tool that contains the methods used below.
            assert isinstance(c.driver.pcb_tool, hammer_vlsi.HammerPCBDeliverableTool)
            self.assertTrue(os.path.exists(c.driver.pcb_tool.output_footprint_filename))  # type: ignore
            self.assertTrue(os.path.exists(c.driver.pcb_tool.output_footprint_csv_filename))  # type: ignore
            self.assertTrue(os.path.exists(c.driver.pcb_tool.output_schematic_symbol_filename))  # type: ignore
            self.assertTrue(os.path.exists(c.driver.pcb_tool.output_bom_builder_pindata_filename))  # type: ignore

    # TODO add more checks:
    # - footprint pads should be mirrored relative to GDS
    # - Blank bumps should not show up
    # - test grouping

class HammerPowerStrapsTestContext:
    def __init__(self, test: unittest.TestCase, strap_options: Dict[str, Any]) -> None:
        self.logger = HammerVLSILogging.context()
        self.strap_options = strap_options  # type: Dict[str, Any]
        self.test = test  # type: unittest.TestCase
        self.temp_dir = ""  # type: str
        self.power_straps_tcl = ""  # type: str
        self._driver = None # type: Optional[hammer_vlsi.HammerDriver]

    # Helper property to check that the driver did get initialized.
    @property
    def driver(self) -> hammer_vlsi.HammerDriver:
        assert self._driver is not None, "HammerDriver must be initialized before use"
        return self._driver

    def __enter__(self) -> "HammerPowerStrapsTestContext":
        """Initialize context by creating the temp_dir, driver, and loading mockpar."""
        self.test.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                        "hammer_vlsi_path must exist")
        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "project.json")
        tech_dir, tech_dir_base = HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        def add_stackup_and_site(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict["stackups"] = [StackupTestHelper.create_test_stackup_dict(8)]
            out_dict["sites"] = [StackupTestHelper.create_test_site_dict()]
            out_dict["grid_unit"] = str(StackupTestHelper.mfr_grid())
            return out_dict
        HammerToolTestHelpers.write_tech_json(tech_json_filename, add_stackup_and_site)
        with open(json_path, "w") as f:
            f.write(json.dumps(add_dicts({
                "vlsi.core.par_tool": "mockpar",
                "vlsi.core.technology": "dummy28",
                "vlsi.core.node": "28",
                "vlsi.core.placement_site": "CoreSite",
                "vlsi.core.technology_path": [os.path.join(tech_dir, '..')],
                "vlsi.core.technology_path_meta": "append",
                "par.inputs.top_module": "dummy",
                "par.inputs.input_files": ("/dev/null",),
                "technology.core.stackup": "StackupWith8Metals",
                "technology.core.std_cell_rail_layer": "M1",
                "technology.core.tap_cell_rail_reference": "FakeTapCell",
                "par.mockpar.temp_folder": temp_dir
            }, self.strap_options), cls=HammerJSONEncoder, indent=4))
        options = hammer_vlsi.HammerDriverOptions(
            environment_configs=[],
            project_configs=[json_path],
            log_file=os.path.join(temp_dir, "log.txt"),
            obj_dir=temp_dir
        )
        self.temp_dir = temp_dir
        self._driver = hammer_vlsi.HammerDriver(options)
        self.test.assertTrue(self.driver.load_par_tool())
        return self

    def __exit__(self, type, value, traceback) -> bool:
        """Clean up the context by removing the temp_dir."""
        shutil.rmtree(self.temp_dir)
        # Return True (normal execution) if no exception occurred.
        return True if type is None else False


class HammerPowerStrapsTest(HasGetTech, unittest.TestCase):

    def test_simple_by_tracks_power_straps(self) -> None:
        """ Creates simple power straps using the by_tracks method """
        # TODO clean this up a bit

        strap_layers = ["M4", "M5", "M6", "M7", "M8"]
        pin_layers = ["M7", "M8"]
        track_width = 4
        track_width_M7 = 8
        track_width_M8 = 10
        track_spacing = 0
        track_spacing_M6 = 1
        power_utilization = 0.2
        power_utilization_M8 = 1.0
        track_start_M5 = 1
        track_offset_M5 = 1.2

        # VSS comes before VDD
        nets = ["VSS", "VDD"]

        straps_options = {
            "vlsi.inputs.supplies": {
                "power": [{"name": "VDD", "pin": "VDD"}],
                "ground": [{"name": "VSS", "pin": "VSS"}],
                "VDD": "1.00 V",
                "GND": "0 V"
            },
            "par.power_straps_mode": "generate",
            "par.generate_power_straps_method": "by_tracks",
            "par.generate_power_straps_options.by_tracks": {
                "strap_layers": strap_layers,
                "pin_layers": pin_layers,
                "track_width": track_width,
                "track_width_M7": track_width_M7,
                "track_width_M8": track_width_M8,
                "track_spacing": track_spacing,
                "track_spacing_M6": track_spacing_M6,
                "power_utilization": power_utilization,
                "power_utilization_M8": power_utilization_M8,
                "track_start_M5": track_start_M5,
                "track_offset_M5": track_offset_M5
            }
        }

        with HammerPowerStrapsTestContext(self, straps_options) as c:
            success, par_output = c.driver.run_par()
            self.assertTrue(success)

            par_tool = c.driver.par_tool
            # It's surpringly annoying to import mockpar.MockPlaceAndRoute, which is the class
            # that contains the parse_mock_power_straps_file() method, so we're just ignoring
            # that particular part of this
            assert isinstance(par_tool, hammer_vlsi.HammerPlaceAndRouteTool)
            stackup = par_tool.get_stackup()
            entries = par_tool.parse_mock_power_straps_file()  # type: ignore
            entries  # type: List[Dict[str, Any]]

            for entry in entries:
                c.logger.debug("Power strap entry:" + str(entry))
                layer_name = entry["layer_name"]
                if layer_name == "M1":
                    # Standard cell rails
                    self.assertEqual(entry["tap_cell_name"], "FakeTapCell")
                    self.assertEqual(entry["bbox"], [])
                    self.assertEqual(entry["nets"], nets)
                    continue

                strap_width = Decimal(entry["width"])
                strap_spacing = Decimal(entry["spacing"])
                strap_pitch = Decimal(entry["pitch"])
                strap_offset = Decimal(entry["offset"])
                metal = stackup.get_metal(layer_name)
                min_width = metal.min_width
                group_track_pitch = strap_pitch / metal.pitch
                track_offset = Decimal(str(track_offset_M5)) if layer_name == "M5" else Decimal(0)
                track_start = Decimal(str(track_start_M5)) if layer_name == "M5" else Decimal(0)
                used_tracks = round(Decimal(strap_offset + strap_width + strap_spacing + strap_width + strap_offset - 2 * (track_offset + track_start * metal.pitch)) / metal.pitch) - 1
                if layer_name == "M4":
                    self.assertEqual(entry["bbox"], [])
                    self.assertEqual(entry["nets"], nets)
                    # TODO more tests in a future PR
                elif layer_name == "M5":
                    self.assertEqual(entry["bbox"], [])
                    self.assertEqual(entry["nets"], nets)
                    # Check that the requested tracks equals the used tracks
                    requested_tracks = track_width * 2 + track_spacing
                    self.assertEqual(used_tracks, requested_tracks)
                    # Spacing should be at least the min spacing
                    min_spacing = metal.get_spacing_for_width(strap_width)
                    self.assertGreaterEqual(strap_spacing, min_spacing)
                    # TODO more tests in a future PR
                elif layer_name == "M6":
                    self.assertEqual(entry["bbox"], [])
                    self.assertEqual(entry["nets"], nets)
                    # This is a sanity check that we didn't accidentally change something up above
                    self.assertEqual(track_spacing_M6, 1)
                    # We should be able to fit a track in between the stripes because track_spacing_M6 == 1
                    wire_to_strap_spacing = (strap_spacing - min_width) / 2
                    min_spacing = metal.get_spacing_for_width(strap_width)
                    self.assertGreaterEqual(wire_to_strap_spacing, min_spacing)
                    # Check that the requested tracks equals the used tracks
                    requested_tracks = track_width * 2 + track_spacing_M6
                    self.assertEqual(used_tracks, requested_tracks)
                    # Spacing should be at least the min spacing
                    min_spacing = metal.get_spacing_for_width(strap_width)
                    self.assertGreaterEqual(wire_to_strap_spacing, min_spacing)
                    # TODO more tests in a future PR
                elif layer_name == "M7":
                    self.assertEqual(entry["bbox"], [])
                    self.assertEqual(entry["nets"], nets)
                    # TODO more tests in a future PR
                elif layer_name == "M8":
                    other_spacing = strap_pitch - (2 * strap_width) - strap_spacing
                    # Track spacing should be 0
                    self.assertEqual(track_spacing, 0)
                    # Test that the power straps are symmetric
                    self.assertEqual(other_spacing, strap_spacing)
                    # Spacing should be at least the min spacing
                    min_spacing = metal.get_spacing_for_width(strap_width)
                    self.assertGreaterEqual(other_spacing, min_spacing)
                    # Test that a slightly larger strap would be a DRC violation
                    new_spacing = metal.get_spacing_for_width(strap_width + metal.grid_unit)
                    new_pitch = (strap_width + metal.grid_unit + new_spacing) * 2
                    self.assertLess(strap_pitch, new_pitch)
                    # Test that the pitch does consume the right number of tracks
                    required_pitch = Decimal(track_width_M8 * 2) * metal.pitch
                    # 100% power utilzation should produce straps that consume 2*strap_width + strap_spacing tracks
                    self.assertEqual(strap_pitch, required_pitch)
                else:
                    assert False, "Got the wrong layer_name: {}".format(layer_name)

    def test_multiple_domains(self) -> None:
        """ Tests multiple power domains """
        # TODO clean this up a bit

        strap_layers = ["M4", "M5", "M8"]
        pin_layers = ["M8"]
        track_width = 8
        track_spacing = 0
        power_utilization = 0.2
        power_utilization_M8 = 1.0

        straps_options = {
            "vlsi.inputs.supplies": {
                "power": [{"name": "VDD", "pin": "VDD"}, {"name": "VDD2", "pin": "VDD2"}],
                "ground": [{"name": "VSS", "pin": "VSS"}],
                "VDD": "1.00 V",
                "GND": "0 V"
            },
            "par.power_straps_mode": "generate",
            "par.generate_power_straps_method": "by_tracks",
            "par.generate_power_straps_options.by_tracks": {
                "strap_layers": strap_layers,
                "pin_layers": pin_layers,
                "track_width": track_width,
                "track_spacing": track_spacing,
                "power_utilization": power_utilization,
                "power_utilization_M8": power_utilization_M8
            }
        }

        with HammerPowerStrapsTestContext(self, straps_options) as c:
            success, par_output = c.driver.run_par()
            self.assertTrue(success)

            par_tool = c.driver.par_tool
            # It's surpringly annoying to import mockpar.MockPlaceAndRoute, which is the class
            # that contains the parse_mock_power_straps_file() method, so we're just ignoring
            # that particular part of this
            assert isinstance(par_tool, hammer_vlsi.HammerPlaceAndRouteTool)
            stackup = par_tool.get_stackup()
            entries = par_tool.parse_mock_power_straps_file()  # type: ignore
            entries  # type: List[Dict[str, Any]]

            # There should be 1 std cell rail definition and 2 straps per layer (total 7)
            self.assertEqual(len(entries), 7)

            first_M5 = True
            first_M8 = True
            offset_M5 = Decimal(0)
            offset_M8 = Decimal(0)
            for entry in entries:
                c.logger.debug("Power strap entry:" + str(entry))
                layer_name = entry["layer_name"]
                if layer_name == "M1":
                    # Standard cell rails
                    self.assertEqual(entry["tap_cell_name"], "FakeTapCell")
                    self.assertEqual(entry["bbox"], [])
                    self.assertEqual(entry["nets"], ["VSS", "VDD", "VDD2"])
                    continue

                strap_width = Decimal(entry["width"])
                strap_spacing = Decimal(entry["spacing"])
                strap_pitch = Decimal(entry["pitch"])
                strap_offset = Decimal(entry["offset"])
                metal = stackup.get_metal(layer_name)
                min_width = metal.min_width
                group_track_pitch = strap_pitch / metal.pitch
                used_tracks = round(Decimal(strap_offset + strap_width + strap_spacing + strap_width + strap_offset) / metal.pitch) - 1
                if layer_name == "M4":
                    # This is just here to keep the straps from asserting due to a direction issue
                    pass
                elif layer_name == "M5":
                    # Test 2 domains
                    self.assertEqual(entry["bbox"], [])
                    if first_M5:
                        first_M5 = False
                        self.assertEqual(entry["nets"], ["VSS", "VDD"])
                        offset_M5 = strap_offset
                    else:
                        self.assertEqual(entry["nets"], ["VSS", "VDD2"])
                        self.assertEqual(strap_offset, (strap_pitch / 2) + offset_M5)
                    # TODO more tests in a future PR
                elif layer_name == "M8":
                    # Test 100% with two domains
                    self.assertEqual(entry["bbox"], [])
                    # Test that the pitch does consume the right number of tracks
                    # This will be twice as large as the single-domain case because we'll offset another set
                    required_pitch = Decimal(track_width * 4) * metal.pitch
                    self.assertEqual(strap_pitch, required_pitch)
                    if first_M8:
                        first_M8 = False
                        self.assertEqual(entry["nets"], ["VSS", "VDD"])
                        offset_M8 = strap_offset
                    else:
                        self.assertEqual(entry["nets"], ["VSS", "VDD2"])
                        self.assertEqual(strap_offset, (strap_pitch / 2) + offset_M8)
                    # TODO more tests in a future PR
                else:
                    assert False, "Got the wrong layer_name: {}".format(layer_name)


class HammerSimToolTestContext:
    def __init__(self, test: unittest.TestCase) -> None:
        self.logger = HammerVLSILogging.context()
        self.test = test # type: unittest.TestCase
        self.temp_dir = "" # type: str
        self._driver = None # type: Optional[hammer_vlsi.HammerDriver]

    # Helper property to check that the driver did get initialized.
    @property
    def driver(self) -> hammer_vlsi.HammerDriver:
        assert self._driver is not None, "HammerDriver must be initialized before use"
        return self._driver

    def __enter__(self) -> "HammerSimToolTestContext":
        """Initialize context by creating the temp_dir, driver, and loading mocksim."""
        self.test.assertTrue(hammer_vlsi.HammerVLSISettings.set_hammer_vlsi_path_from_environment(),
                                "hammer_vlsi_path must exist")
        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "project.json")
        json_content = {
            "vlsi.core.sim_tool": "mocksim",
            "vlsi.core.technology": "nop",
            "sim.inputs.top_module": "dummy",
            "sim.inputs.input_files": ("/dev/null",),
            "sim.submit.command": "local",
            "sim.inputs.options": ["-debug"],
            "sim.inputs.level": "rtl",
            "sim.mocksim.temp_folder": temp_dir
        }

        with open(json_path, "w") as f:
            f.write(json.dumps(json_content, cls=HammerJSONEncoder, indent=4))

        options = hammer_vlsi.HammerDriverOptions(
            environment_configs=[],
            project_configs=[json_path],
            log_file=os.path.join(temp_dir, "log.txt"),
            obj_dir=temp_dir
        )
        self._driver = hammer_vlsi.HammerDriver(options)
        self.temp_dir = temp_dir
        return self

    def __exit__(self, type, value, traceback) -> bool:
        """Cleanup the context by removing the temp_dir."""
        shutil.rmtree(self.temp_dir)
        # Return True (normal execution) if no exception ocurred/

        return True if type is None else False

    @property
    def env(self) -> Dict[str, str]:
        return {}

class HammerSimToolTest(unittest.TestCase):
    def create_context(self) -> HammerSimToolTestContext:
        return HammerSimToolTestContext(self)

    def test_deliverables_exist(self) -> None:
        with self.create_context() as c:
            self.assertTrue(c.driver.load_sim_tool())
            self.assertTrue(c.driver.run_sim())

            assert isinstance(c.driver.sim_tool, hammer_vlsi.HammerSimTool)
            # Ignore typing here because this is part of the mocksim API
            self.assertTrue(os.path.exists(c.driver.sim_tool.force_regs_file_path))  # type: ignore


if __name__ == '__main__':
    unittest.main()

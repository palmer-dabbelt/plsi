#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Tests for hammer_tech.
#
#  See LICENSE for licence details.

import json
import os
import shutil
import unittest

from hammer_vlsi import HammerVLSISettings
import test
from typing import Any, Dict, List, Optional

from hammer_logging import HammerVLSILogging
import hammer_tech
from hammer_tech import LibraryFilter, Stackup, Metal, WidthSpacingTuple
from hammer_utils import deepdict


class HammerTechnologyTest(unittest.TestCase):
    """
    Tests for the Hammer technology library (hammer_tech).
    """

    # Workaround for not being able to mix-in test.HasGetTech directly
    def get_tech(self, tech_opt: Optional[hammer_tech.HammerTechnology]) -> hammer_tech.HammerTechnology:
        return test.HasGetTech.get_tech(self, tech_opt) # type: ignore

    def setUp(self) -> None:
        # Make sure the HAMMER_VLSI path is set correctly.
        self.assertTrue(HammerVLSISettings.set_hammer_vlsi_path_from_environment())

    def test_filters_with_extra_extraction(self) -> None:
        """
        Test that filters whose extraction functions return extra (non-path)
        metadata.
        """

        # pylint: disable=too-many-locals

        import hammer_config

        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")

        def add_named_library(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict["libraries"].append({
                "name": "abcdef",
                "milkyway techfile": "test/abcdef.tf"
            })
            return out_dict

        test.HammerToolTestHelpers.write_tech_json(tech_json_filename, add_named_library)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        def filter_func(lib: hammer_tech.Library) -> bool:
            return lib.milkyway_techfile is not None

        def paths_func(lib: hammer_tech.Library) -> List[str]:
            assert lib.milkyway_techfile is not None
            return [lib.milkyway_techfile]

        def extraction_func(lib: hammer_tech.Library, paths: List[str]) -> List[str]:
            assert len(paths) == 1
            if lib.name is None:
                name = ""
            else:
                name = str(lib.name)
            return [json.dumps({"path": paths[0], "name": name}, indent=4)]

        def sort_func(lib: hammer_tech.Library):
            assert lib.milkyway_techfile is not None
            return lib.milkyway_techfile

        test_filter = LibraryFilter.new("metatest", "Test filter that extracts metadata",
                                        is_file=True, filter_func=filter_func,
                                        paths_func=paths_func,
                                        extraction_func=extraction_func,
                                        sort_func=sort_func)

        database = hammer_config.HammerDatabase()
        tech.set_database(database)
        raw = tech.process_library_filter(pre_filts=[], filt=test_filter,
                                          must_exist=False,
                                          output_func=hammer_tech.HammerTechnologyUtils.to_plain_item)

        # Disable false positive from pylint
        outputs = list(map(lambda s: json.loads(s), raw))  # pylint: disable=unnecessary-lambda
        self.assertEqual(outputs,
                         [
                             {"path": tech.prepend_dir_path("test/abcdef.tf"), "name": "abcdef"},
                             {"path": tech.prepend_dir_path("test/coconut"), "name": ""},
                             {"path": tech.prepend_dir_path("test/soy"), "name": ""}
                         ])

        # Cleanup
        shutil.rmtree(tech_dir_base)

    def test_process_library_filter_removes_duplicates(self) -> None:
        """
        Test that process_library_filter removes duplicates.
        """
        import hammer_config

        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")

        def add_duplicates(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict["libraries"].append({
                "name": "abcdef",
                "gds file": "test/abcdef.gds"
            })
            out_dict["libraries"].append({
                "name": "abcdef2",
                "gds file": "test/abcdef.gds"
            })
            return out_dict

        test.HammerToolTestHelpers.write_tech_json(tech_json_filename, add_duplicates)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        database = hammer_config.HammerDatabase()
        tech.set_database(database)
        outputs = tech.process_library_filter(pre_filts=[], filt=hammer_tech.filters.gds_filter,
                                              must_exist=False,
                                              output_func=lambda str, _: [str])

        self.assertEqual(outputs, ["{0}/abcdef.gds".format(tech_dir)])

        # Cleanup
        shutil.rmtree(tech_dir_base)

    @staticmethod
    def add_tarballs(in_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper method to take an input .tech.json and transform it for
        tarball tests.
        It replaces the source files with a single tarball and replaces
        the libraries with a single library that uses said tarball.
        :param in_dict: Input tech schema
        :return: Output tech schema for tarball tests
        """
        out_dict = deepdict(in_dict)
        del out_dict["installs"]
        out_dict["tarballs"] = [{
            "path": "foobar.tar.gz",
            "homepage": "http://www.example.com/tarballs",
            "base var": "technology.dummy28.tarball_dir"
        }]
        out_dict["libraries"] = [{
            "name": "abcdef",
            "gds file": "foobar.tar.gz/test.gds"
        }]
        return out_dict

    def test_tarballs_not_extracted(self) -> None:
        """
        Test that tarballs that are not pre-extracted work fine.
        """
        import hammer_config

        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")

        # Add defaults to specify tarball_dir.
        with open(os.path.join(tech_dir, "defaults.json"), "w") as f:
            f.write(json.dumps({
                "technology.dummy28.tarball_dir": tech_dir
            }))

        test.HammerToolTestHelpers.write_tech_json(tech_json_filename, self.add_tarballs)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        database = hammer_config.HammerDatabase()
        database.update_technology(tech.get_config())
        HammerVLSISettings.load_builtins_and_core(database)
        tech.set_database(database)
        outputs = tech.process_library_filter(pre_filts=[], filt=hammer_tech.filters.gds_filter,
                                              must_exist=False,
                                              output_func=lambda str, _: [str])

        self.assertEqual(outputs, ["{0}/extracted/foobar.tar.gz/test.gds".format(tech_dir)])

        # Cleanup
        shutil.rmtree(tech_dir_base)

    def test_tarballs_pre_extracted(self) -> None:
        """
        Test that tarballs that are pre-extracted also work as expected.
        """
        import hammer_config

        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")

        # Add defaults to specify tarball_dir.
        with open(os.path.join(tech_dir, "defaults.json"), "w") as f:
            f.write(json.dumps({
                "technology.dummy28.tarball_dir": tech_dir,
                "vlsi.technology.extracted_tarballs_dir": tech_dir_base
            }))

        test.HammerToolTestHelpers.write_tech_json(tech_json_filename, self.add_tarballs)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        database = hammer_config.HammerDatabase()
        database.update_technology(tech.get_config())
        HammerVLSISettings.load_builtins_and_core(database)
        tech.set_database(database)
        outputs = tech.process_library_filter(pre_filts=[], filt=hammer_tech.filters.gds_filter,
                                              must_exist=False,
                                              output_func=lambda str, _: [str])

        self.assertEqual(outputs, ["{0}/foobar.tar.gz/test.gds".format(tech_dir_base)])

        # Cleanup
        shutil.rmtree(tech_dir_base)

    def test_tarballs_pre_extracted_tech_specific(self) -> None:
        """
        Test that tarballs that are pre-extracted and specified using a
        tech-specific setting work.
        """
        import hammer_config

        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")

        # Add defaults to specify tarball_dir.
        with open(os.path.join(tech_dir, "defaults.json"), "w") as f:
            f.write(json.dumps({
                "technology.dummy28.tarball_dir": tech_dir,
                "vlsi.technology.extracted_tarballs_dir": "/should/not/be/used",
                "technology.dummy28.extracted_tarballs_dir": tech_dir_base
            }))

        test.HammerToolTestHelpers.write_tech_json(tech_json_filename, self.add_tarballs)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        database = hammer_config.HammerDatabase()
        database.update_technology(tech.get_config())
        HammerVLSISettings.load_builtins_and_core(database)
        tech.set_database(database)
        outputs = tech.process_library_filter(pre_filts=[], filt=hammer_tech.filters.gds_filter,
                                              must_exist=False,
                                              output_func=lambda str, _: [str])

        self.assertEqual(outputs, ["{0}/foobar.tar.gz/test.gds".format(tech_dir_base)])

        # Cleanup
        shutil.rmtree(tech_dir_base)

    def test_extra_prefixes(self) -> None:
        """
        Test that extra_prefixes works properly as a property.
        """
        lib = hammer_tech.library_from_json('{"openaccess techfile": "test/oa"}')  # type: hammer_tech.Library

        prefixes_orig = [hammer_tech.PathPrefix(prefix="test", path="/tmp/test")]

        prefixes = [hammer_tech.PathPrefix(prefix="test", path="/tmp/test")]
        lib.extra_prefixes = prefixes
        # Check that we get the original back even after mutating the original list.
        prefixes.append(hammer_tech.PathPrefix(prefix="bar", path="/tmp/bar"))
        self.assertEqual(lib.extra_prefixes, prefixes_orig)

        prefixes2 = lib.extra_prefixes
        # Check that we don't mutate the copy stored in the lib if we mutate after getting it
        prefixes2.append(hammer_tech.PathPrefix(prefix="bar", path="/tmp/bar"))
        self.assertEqual(lib.extra_prefixes, prefixes_orig)

    def test_prepend_dir_path(self) -> None:
        """
        Test that the technology library can prepend directories correctly.
        """
        tech_json = {
            "name": "My Technology Library",
            "installs": [
                {
                    "path": "test",
                    "base var": ""  # means relative to tech dir
                }
            ],
            "libraries": []
        }

        tech_dir = "/tmp/path"  # should not be used
        tech = hammer_tech.HammerTechnology.load_from_json("dummy28", json.dumps(tech_json, indent=2), tech_dir)

        # Check that a tech-provided prefix works fine
        self.assertEqual("{0}/water".format(tech_dir), tech.prepend_dir_path("test/water"))
        self.assertEqual("{0}/fruit".format(tech_dir), tech.prepend_dir_path("test/fruit"))

        # Check that a non-existent prefix gives an error
        with self.assertRaises(ValueError):
            tech.prepend_dir_path("badprefix/file")

        # Check that a lib's custom prefix works
        from hammer_tech import ExtraLibrary
        lib = ExtraLibrary(
            library=hammer_tech.library_from_json("""{"milkyway techfile": "custom/chair"}"""),
            prefix=hammer_tech.PathPrefix(
                prefix="custom",
                path="/tmp/custom"
            )
        ).store_into_library()  # type: hammer_tech.Library
        self.assertEqual("{0}/hat".format("/tmp/custom"), tech.prepend_dir_path("custom/hat", lib))

    def test_yaml_tech_file(self) -> None:
        """
        Test that we can load a yaml tech plugin
        """
        tech_yaml = """
name: My Technology Library
installs:
    - path: test
      base var: ""  # means relative to tech dir
libraries: []
        """
        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")

        tech_yaml_filename = os.path.join(tech_dir, "dummy28.tech.yml")
        with open(tech_yaml_filename, "w") as f:  # pylint: disable=invalid-name
            f.write(tech_yaml)
        tech_opt = hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir)
        self.assertFalse(tech_opt is None, "Unable to load technology")

        # Cleanup
        shutil.rmtree(tech_dir_base)

    def test_gds_map_file(self) -> None:
        """
        Test that GDS map file support works as expected.
        """
        import hammer_config

        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")

        def add_gds_map(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict.update({"gds map file": "test/gds_map_file"})
            return out_dict

        test.HammerToolTestHelpers.write_tech_json(tech_json_filename, add_gds_map)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        tool = test.DummyTool()
        tool.technology = tech
        database = hammer_config.HammerDatabase()
        tool.set_database(database)

        # Test that empty for gds_map_mode results in no map file.
        database.update_project([{
            'par.inputs.gds_map_mode': 'empty',
            'par.inputs.gds_map_file': None
        }])
        self.assertEqual(tool.get_gds_map_file(), None)

        # Test that manual mode for gds_map_mode works.
        database.update_project([{
            'par.inputs.gds_map_mode': 'manual',
            'par.inputs.gds_map_file': '/tmp/foo/bar'
        }])
        self.assertEqual(tool.get_gds_map_file(), '/tmp/foo/bar')

        # Test that auto mode for gds_map_mode works if the technology has a map file.
        database.update_project([{
            'par.inputs.gds_map_mode': 'auto',
            'par.inputs.gds_map_file': None
        }])
        self.assertEqual(tool.get_gds_map_file(), '{tech}/gds_map_file'.format(tech=tech_dir))

        # Cleanup
        shutil.rmtree(tech_dir_base)

        # Create a new technology with no GDS map file.
        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")

        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        test.HammerToolTestHelpers.write_tech_json(tech_json_filename)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        tool.technology = tech

        # Test that auto mode for gds_map_mode works if the technology has no map file.
        database.update_project([{
            'par.inputs.gds_map_mode': 'auto',
            'par.inputs.gds_map_file': None
        }])
        self.assertEqual(tool.get_gds_map_file(), None)

        # Cleanup
        shutil.rmtree(tech_dir_base)

    def test_dont_use_list(self) -> None:
        """
        Test that "don't use" list support works as expected.
        """
        import hammer_config

        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")

        def add_dont_use_list(in_dict: Dict[str, Any]) -> Dict[str, Any]:
            out_dict = deepdict(in_dict)
            out_dict.update({"dont use list": ["cell1", "cell2"]})
            return out_dict

        test.HammerToolTestHelpers.write_tech_json(tech_json_filename, add_dont_use_list)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        tool = test.DummyTool()
        tool.technology = tech
        database = hammer_config.HammerDatabase()
        tool.set_database(database)

        # Test that manual mode for dont_use_mode works.
        database.update_project([{
            'vlsi.inputs.dont_use_mode': 'manual',
            'vlsi.inputs.dont_use_list': ['cell1']
        }])
        self.assertEqual(tool.get_dont_use_list(), ['cell1'])

        # Test that auto mode for dont_use_mode works if the technology has a "don't use" list.
        database.update_project([{
            'vlsi.inputs.dont_use_mode': 'auto',
            'vlsi.inputs.dont_use_list': []
        }])

        self.assertEqual(tool.get_dont_use_list(), tool.technology.config.dont_use_list)

        # Test that append mode for dont_use_mode works if the everyone has a "don't use" list.
        database.update_project([{
            'vlsi.inputs.dont_use_mode': 'append',
            'vlsi.inputs.dont_use_list': ['cell3']
        }])

        self.assertEqual(tool.get_dont_use_list(), ['cell1', 'cell2', 'cell3'])

        # Cleanup
        shutil.rmtree(tech_dir_base)

        # Create a new technology with no dont use list
        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")

        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")
        test.HammerToolTestHelpers.write_tech_json(tech_json_filename)
        tech = self.get_tech(hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir))
        tech.cache_dir = tech_dir

        tool.technology = tech

        # Test that auto mode for don't use list works if the technology has no don't use list file.
        database.update_project([{
            'vlsi.inputs.dont_use_mode': 'auto',
            'vlsi.inputs.dont_use_list': []
        }])
        self.assertEqual(tool.get_dont_use_list(), [])

        # Cleanup
        shutil.rmtree(tech_dir_base)

    def test_macro_sizes(self) -> None:
        """
        Test that getting macro sizes works as expected.
        """
        import hammer_config

        tech_dir, tech_dir_base = test.HammerToolTestHelpers.create_tech_dir("dummy28")
        tech_json_filename = os.path.join(tech_dir, "dummy28.tech.json")

        def add_lib_with_lef(d: Dict[str, Any]) -> Dict[str, Any]:
            with open(os.path.join(tech_dir, 'my_vendor_lib.lef'), 'w') as f:
                f.write("""VERSION 5.8 ;
BUSBITCHARS "[]" ;
DIVIDERCHAR "/" ;

MACRO my_awesome_macro
  CLASS BLOCK ;
  ORIGIN -0.435 607.525 ;
  FOREIGN my_awesome_macro 0.435 -607.525 ;
  SIZE 810.522 BY 607.525 ;
  SYMMETRY X Y R90 ;
END my_awesome_macro

END LIBRARY
                """)
            r = deepdict(d)
            r['libraries'].append({
                'name': 'my_vendor_lib',
                'lef file': 'test/my_vendor_lib.lef'
            })
            return r

        test.HammerToolTestHelpers.write_tech_json(tech_json_filename, add_lib_with_lef)
        tech_opt = hammer_tech.HammerTechnology.load_from_dir("dummy28", tech_dir)
        if tech_opt is None:
            self.assertTrue(False, "Unable to load technology")
            return
        else:
            tech = tech_opt  # type: hammer_tech.HammerTechnology
        tech.cache_dir = tech_dir

        tech.logger = HammerVLSILogging.context("")

        database = hammer_config.HammerDatabase()
        tech.set_database(database)

        # Test that macro sizes can be read out of the LEF.
        self.assertEqual(tech.get_macro_sizes(), [
            hammer_tech.MacroSize(library='my_vendor_lib', name='my_awesome_macro',
                                  width=810.522, height=607.525)
        ])

        # Cleanup
        shutil.rmtree(tech_dir_base)

class StackupTestHelper:

    # TODO when the manufacturing grid concept exists, update this
    @staticmethod
    def mfr_grid() -> float:
        return 0.001

    @staticmethod
    def snap(f: float) -> float:
        return float(round(f / StackupTestHelper.mfr_grid())) * StackupTestHelper.mfr_grid()

    @staticmethod
    def index_to_min_width_fn(index: int) -> float:
        assert index > 0
        return StackupTestHelper.snap(0.05 * (1 if (index < 3) else (2 if (index < 5) else 5)))

    @staticmethod
    def index_to_min_pitch_fn(index: int) -> float:
        return StackupTestHelper.snap((StackupTestHelper.index_to_min_width_fn(index) * 9.0) / 5.0)

    @staticmethod
    def index_to_offset_fn(index: int) -> float:
        return StackupTestHelper.snap(0.04)

    @staticmethod
    def create_wst_list(index: int) -> List[Dict[str, float]]:
        base_w = StackupTestHelper.index_to_min_width_fn(index)
        base_s = StackupTestHelper.index_to_min_pitch_fn(index) - base_w
        wst = []
        for x in range(5):
            wst.append({"width_at_least": StackupTestHelper.snap(float(x) * base_w * 3),
                        "min_spacing": StackupTestHelper.snap(float(x+1) * base_s) })
        return wst

    @staticmethod
    def create_test_metal(index: int) -> Dict[str, Any]:
        output = {} # type: Dict[str, Any]
        output["name"] = "M{}".format(index)
        output["index"] = index
        output["direction"] = "vertical" if (index % 2 == 1) else "horizontal"
        output["min_width"] = StackupTestHelper.index_to_min_width_fn(index)
        output["pitch"] = StackupTestHelper.index_to_min_pitch_fn(index)
        output["offset"] = StackupTestHelper.index_to_offset_fn(index)
        output["power_strap_widths_and_spacings"] = StackupTestHelper.create_wst_list(index)
        return output

    @staticmethod
    def create_test_stackup_dict(num_metals: int) -> Dict[str, Any]:
        output = {} # type: Dict[str, Any]
        output["name"] = "StackupWith{}Metals".format(num_metals)
        output["metals"] = []
        for x in range(num_metals):
            output["metals"].append(StackupTestHelper.create_test_metal(x+1))
        return output

    @staticmethod
    def create_test_stackup_list() -> List["Stackup"]:
        output = []
        for x in range(5,8):
            output.append(Stackup.from_setting(StackupTestHelper.create_test_stackup_dict(x)))
            for m in output[-1].metals:
                assert m.grid_unit == StackupTestHelper.mfr_grid(), "FIXME: the unit grid is different between the tests and metals"
        return output


class StackupTest(unittest.TestCase):
    """
    Tests for the Stackup APIs in stackup.py
    """

    # Test that a T W T wire is correctly sized
    # This will pass if the wide wire does not have a spacing DRC violation to surrounding minimum-sized wires and is within a single unit grid
    # This method is not allowed to round the wire, so simply adding a manufacturing grid should suffice to "fail" DRC
    def test_twt_wire(self) -> None:
        # Generate multiple stackups, but we'll only use the largest for this test
        stackup = StackupTestHelper.create_test_stackup_list()[-1]
        for m in stackup.metals:
            # Try with 1 track (this should return a minimum width wire)
            w, s, o = m.get_width_spacing_start_twt(1)
            self.assertEqual(w, m.min_width)
            self.assertEqual(s, m.snap(m.pitch - w))

            # e.g. 2 tracks:
            # | | | |
            # T  W  T
            # e.g. 4 tracks:
            # | | | | | |
            # T  --W--  T
            for num_tracks in range(2,40):
                w, s, o = m.get_width_spacing_start_twt(num_tracks)
                # Check that the resulting spacing is the min spacing
                self.assertTrue(s >= m.get_spacing_for_width(w))
                # Check that there is no DRC
                self.assertGreaterEqual(m.snap(m.pitch * (num_tracks + 1)), m.snap(m.min_width + s*2 + w))
                # Check that if we increase the width slightly we get a DRC violation
                w = m.snap(w + (m.grid_unit*2))
                s = m.get_spacing_for_width(w)
                self.assertLess(m.snap(m.pitch * (num_tracks + 1)), m.snap(m.min_width + s*2 + w))

    # Test that a T W W T wire is correctly sized
    # This will pass if the wide wire does not have a spacing DRC violation to surrounding minimum-sized wires and is within a single unit grid
    # This method is not allowed to round the wire, so simply adding a manufacturing grid should suffice to "fail" DRC
    def test_twwt_wire(self) -> None:
        # Generate multiple stackups, but we'll only use the largest for this test
        stackup = StackupTestHelper.create_test_stackup_list()[-1]
        for m in stackup.metals:
            # Try with 1 track (this should return a minimum width wire)
            w, s, o = m.get_width_spacing_start_twwt(1)
            self.assertEqual(w, m.min_width)
            self.assertEqual(s, m.snap(m.pitch - w))

            # e.g. 2 tracks:
            # | | | | | |
            # T  W   W  T
            # e.g. 4 tracks:
            # | | | | | | | | | |
            # T  --W--   --W--  T
            for num_tracks in range(2,40):
                w, s, o = m.get_width_spacing_start_twwt(num_tracks)
                # Check that the resulting spacing is the min spacing
                self.assertGreaterEqual(s, m.get_spacing_for_width(w))
                # Check that there is no DRC
                self.assertGreaterEqual(m.snap(m.pitch * (2*num_tracks + 1)), m.snap(m.min_width + s*3 + w*2))
                # Check that if we increase the width slightly we get a DRC violation
                w = w + (m.grid_unit*2)
                s = m.get_spacing_for_width(w)
                self.assertLess(m.snap(m.pitch * (2*num_tracks + 1)), m.snap(m.min_width + s*3 + w*2))


    def test_min_spacing_for_width(self) -> None:
        # Generate multiple stackups, but we'll only use the largest for this test
        stackup = StackupTestHelper.create_test_stackup_list()[-1]
        for m in stackup.metals:
            # generate some widths:
            for x in [1.0, 2.0, 3.4, 4.5, 5.25, 50.2]:
                # coerce to a manufacturing grid, this is just a test data point
                w = m.snap(x * m.min_width)
                s = m.get_spacing_for_width(w)
                for wst in m.power_strap_widths_and_spacings:
                    if w >= wst.width_at_least:
                        self.assertGreaterEqual(s, wst.min_spacing)

    def test_get_spacing_from_pitch(self) -> None:
        # Generate multiple stackups, but we'll only use the largest for this test
        stackup = StackupTestHelper.create_test_stackup_list()[-1]
        for m in stackup.metals:
            # generate some widths:
            for x in range(0, 100000, 5):
                # Generate a test data point
                p = m.snap((m.grid_unit * x) + m.pitch)
                s = m.min_spacing_from_pitch(p)
                w = m.snap(p - s)
                # Check that we don't violate DRC
                self.assertGreaterEqual(p, m.snap(w + m.get_spacing_for_width(w)))
                # Check that the wire is as large as possible by growing it
                w = m.snap(w + (m.grid_unit*2))
                self.assertLess(p, m.snap(w + m.get_spacing_for_width(w)))

if __name__ == '__main__':
    unittest.main()

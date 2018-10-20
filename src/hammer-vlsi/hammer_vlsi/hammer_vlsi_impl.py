#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  hammer_vlsi_impl.py
#  hammer-vlsi implementation file. Users should import hammer_vlsi instead.
#
#  Copyright 2017-2018 Edward Wang <edward.c.wang@compdigitec.com>

from abc import abstractmethod
from enum import Enum
from functools import reduce
import importlib
from numbers import Number
import os
import sys
from typing import Callable, Iterable, List, NamedTuple, Optional, Dict, Any, Union

from hammer_utils import reverse_dict, deepdict, optional_map

from .constraints import *


class HierarchicalMode(Enum):
    Flat = 1
    Leaf = 2
    Hierarchical = 3
    Top = 4

    @classmethod
    def __mapping(cls) -> Dict[str, "HierarchicalMode"]:
        return {
            "flat": HierarchicalMode.Flat,
            "leaf": HierarchicalMode.Leaf,
            "hierarchical": HierarchicalMode.Hierarchical,
            "top": HierarchicalMode.Top
        }

    @staticmethod
    def from_str(x: str) -> "HierarchicalMode":
        try:
            return HierarchicalMode.__mapping()[x]
        except KeyError:
            raise ValueError("Invalid string for HierarchicalMode: " + str(x))

    def __str__(self) -> str:
        return reverse_dict(HierarchicalMode.__mapping())[self]

    def is_nonleaf_hierarchical(self) -> bool:
        """
        Helper function that returns True if this mode is a non-leaf hierarchical mode (i.e. any block with
        hierarchical sub-blocks).
        """
        return self == HierarchicalMode.Hierarchical or self == HierarchicalMode.Top

class HammerToolPauseException(Exception):
    """
    Internal hammer-vlsi exception raised to indicate that a step has stopped execution of the tool.
    This is not necessarily an error condition.
    """
    pass


import hammer_tech


class HammerVLSISettings:
    """
    Static class which holds global hammer-vlsi settings.
    """
    hammer_vlsi_path = ""  # type: str

    @staticmethod
    def get_config() -> dict:
        """Export settings as a config dictionary."""
        return {
            "vlsi.builtins.hammer_vlsi_path": HammerVLSISettings.hammer_vlsi_path
        }

    @classmethod
    def set_hammer_vlsi_path_from_environment(cls) -> bool:
        """
        Try to set hammer_vlsi_path from the environment variable HAMMER_VLSI.

        :return: True if successfully set, False otherwise
        """
        if "HAMMER_VLSI" not in os.environ:
            return False
        else:
            cls.hammer_vlsi_path = os.environ["HAMMER_VLSI"]
            return True


# Library filter containing a filtering function, identifier tag, and a
# short human-readable description.
class LibraryFilter(NamedTuple('LibraryFilter', [
    ('tag', str),
    ('description', str),
    # Is the resulting string intended to be a file?
    ('is_file', bool),
    # Function to extract desired string(s) out of the library.
    ('extraction_func', Callable[[hammer_tech.Library], List[str]]),
    # Additional filter function to use to exclude possible libraries.
    ('filter_func', Optional[Callable[[hammer_tech.Library], bool]]),
    # Sort function to control the order in which outputs are listed
    ('sort_func', Optional[Callable[[hammer_tech.Library], Union[Number, str, tuple]]]),
    # List of functions to call on the list-level (the list of elements generated by func) before output and
    # post-processing.
    ('extra_post_filter_funcs', List[Callable[[List[str]], List[str]]])
])):
    __slots__ = ()

    @staticmethod
    def new(
            tag: str, description: str, is_file: bool,
            extraction_func: Callable[[hammer_tech.Library], List[str]],
            filter_func: Optional[Callable[[hammer_tech.Library], bool]] = None,
            sort_func: Optional[Callable[[hammer_tech.Library], Union[Number, str, tuple]]] = None,
            extra_post_filter_funcs: List[Callable[[List[str]], List[str]]] = []) -> "LibraryFilter":
        """Convenience "constructor" with some default arguments."""
        return LibraryFilter(
            tag, description, is_file,
            extraction_func,
            filter_func,
            sort_func,
            list(extra_post_filter_funcs)
        )


from .hammer_tool import HammerTool, HammerToolStep

class DummyHammerTool(HammerTool):
    """
    This is a dummy implementation of HammerTool that does nothing.
    It has no config, and no particular sense of versioning.
    It is present for nop tools and as a testing aid.
    """

    def tool_config_prefix(self) -> str:
        return ""

    def version_number(self, version: str) -> int:
        return 1

    @property
    def steps(self) -> List[HammerToolStep]:
        return []

class HammerSynthesisTool(HammerTool):
    @abstractmethod
    def fill_outputs(self) -> bool:
        pass

    def export_config_outputs(self) -> Dict[str, Any]:
        outputs = deepdict(super().export_config_outputs())
        outputs["synthesis.outputs.output_files"] = self.output_files
        outputs["synthesis.inputs.input_files"] = self.input_files
        outputs["synthesis.inputs.top_module"] = self.top_module
        return outputs

    ### Generated interface HammerSynthesisTool ###
    ### Inputs ###

    @property
    def input_files(self) -> List[str]:
        """
        Get the input collection of source RTL files (e.g. *.v).

        :return: The input collection of source RTL files (e.g. *.v).
        """
        try:
            return self.attr_getter("_input_files", None)
        except AttributeError:
            raise ValueError("Nothing set for the input collection of source RTL files (e.g. *.v) yet")

    @input_files.setter
    def input_files(self, value: List[str]) -> None:
        """Set the input collection of source RTL files (e.g. *.v)."""
        if not (isinstance(value, List)):
            raise TypeError("input_files must be a List[str]")
        self.attr_setter("_input_files", value)

    @property
    def top_module(self) -> str:
        """
        Get the top-level module.

        :return: The top-level module.
        """
        try:
            return self.attr_getter("_top_module", None)
        except AttributeError:
            raise ValueError("Nothing set for the top-level module yet")

    @top_module.setter
    def top_module(self, value: str) -> None:
        """Set the top-level module."""
        if not (isinstance(value, str)):
            raise TypeError("top_module must be a str")
        self.attr_setter("_top_module", value)

    ### Outputs ###

    @property
    def output_files(self) -> List[str]:
        """
        Get the output collection of mapped (post-synthesis) RTL files.

        :return: The output collection of mapped (post-synthesis) RTL files.
        """
        try:
            return self.attr_getter("_output_files", None)
        except AttributeError:
            raise ValueError("Nothing set for the output collection of mapped (post-synthesis) RTL files yet")

    @output_files.setter
    def output_files(self, value: List[str]) -> None:
        """Set the output collection of mapped (post-synthesis) RTL files."""
        if not (isinstance(value, List)):
            raise TypeError("output_files must be a List[str]")
        self.attr_setter("_output_files", value)

    @property
    def output_sdc(self) -> str:
        """
        Get the (optional) output post-synthesis SDC constraints file.

        :return: The (optional) output post-synthesis SDC constraints file.
        """
        try:
            return self.attr_getter("_output_sdc", None)
        except AttributeError:
            raise ValueError("Nothing set for the (optional) output post-synthesis SDC constraints file yet")

    @output_sdc.setter
    def output_sdc(self, value: str) -> None:
        """Set the (optional) output post-synthesis SDC constraints file."""
        if not (isinstance(value, str)):
            raise TypeError("output_sdc must be a str")
        self.attr_setter("_output_sdc", value)


class HammerPlaceAndRouteTool(HammerTool):
    @abstractmethod
    def fill_outputs(self) -> bool:
        pass

    def export_config_outputs(self) -> Dict[str, Any]:
        outputs = deepdict(super().export_config_outputs())
        outputs["par.outputs.output_ilms"] = list(map(lambda s: s.to_setting(), self.output_ilms))
        return outputs

    ### Generated interface HammerPlaceAndRouteTool ###
    ### Inputs ###

    @property
    def input_files(self) -> List[str]:
        """
        Get the input post-synthesis netlist files.

        :return: The input post-synthesis netlist files.
        """
        try:
            return self.attr_getter("_input_files", None)
        except AttributeError:
            raise ValueError("Nothing set for the input post-synthesis netlist files yet")

    @input_files.setter
    def input_files(self, value: List[str]) -> None:
        """Set the input post-synthesis netlist files."""
        if not (isinstance(value, List)):
            raise TypeError("input_files must be a List[str]")
        self.attr_setter("_input_files", value)

    @property
    def top_module(self) -> str:
        """
        Get the top RTL module.

        :return: The top RTL module.
        """
        try:
            return self.attr_getter("_top_module", None)
        except AttributeError:
            raise ValueError("Nothing set for the top RTL module yet")

    @top_module.setter
    def top_module(self, value: str) -> None:
        """Set the top RTL module."""
        if not (isinstance(value, str)):
            raise TypeError("top_module must be a str")
        self.attr_setter("_top_module", value)

    @property
    def post_synth_sdc(self) -> Optional[str]:
        """
        Get the (optional) input post-synthesis SDC constraint file.

        :return: The (optional) input post-synthesis SDC constraint file.
        """
        try:
            return self.attr_getter("_post_synth_sdc", None)
        except AttributeError:
            return None

    @post_synth_sdc.setter
    def post_synth_sdc(self, value: Optional[str]) -> None:
        """Set the (optional) input post-synthesis SDC constraint file."""
        if not (isinstance(value, str) or (value is None)):
            raise TypeError("post_synth_sdc must be a Optional[str]")
        self.attr_setter("_post_synth_sdc", value)

    ### Outputs ###

    @property
    def output_ilms(self) -> List[ILMStruct]:
        """
        Get the (optional) output ILM information for hierarchical mode.

        :return: The (optional) output ILM information for hierarchical mode.
        """
        try:
            return self.attr_getter("_output_ilms", None)
        except AttributeError:
            raise ValueError("Nothing set for the (optional) output ILM information for hierarchical mode yet")

    @output_ilms.setter
    def output_ilms(self, value: List[ILMStruct]) -> None:
        """Set the (optional) output ILM information for hierarchical mode."""
        if not (isinstance(value, List)):
            raise TypeError("output_ilms must be a List[ILMStruct]")
        self.attr_setter("_output_ilms", value)


class HasSDCSupport(HammerTool):
    """Mix-in trait with functions useful for tools with SDC-style
    constraints."""
    @property
    def sdc_clock_constraints(self) -> str:
        """Generate TCL fragments for top module clock constraints."""
        output = [] # type: List[str]

        clocks = self.get_clock_ports()
        for clock in clocks:
            # TODO: FIXME This assumes that library units are always in ns!!!
            if clock.port is not None:
                output.append("create_clock {0} -name {1} -period {2}".format(clock.port, clock.name, clock.period.value_in_units("ns")))
            else:
                output.append("create_clock {0} -name {0} -period {1}".format(clock.name, clock.period.value_in_units("ns")))
            if clock.uncertainty is not None:
                output.append("set_clock_uncertainty {1} [get_clocks {0}]".format(clock.name, clock.uncertainty.value_in_units("ns")))

        output.append("\n")
        return "\n".join(output)

    @property
    def sdc_pin_constraints(self) -> str:
        """Generate a fragment for I/O pin constraints."""
        output = []  # type: List[str]

        default_output_load = float(self.get_setting("vlsi.inputs.default_output_load"))

        # Specify default load.
        output.append("set_load {load} [all_outputs]".format(
            load=default_output_load
        ))

        # Also specify loads for specific pins.
        for load in self.get_output_load_constraints():
            output.append("set_load {load} [get_port \"{name}\"]".format(
                load=load.load,
                name=load.name
            ))
        return "\n".join(output)

    @property
    @abstractmethod
    def post_synth_sdc(self) -> Optional[str]:
        """
        Get the (optional) input post-synthesis SDC constraint file.

        :return: The (optional) input post-synthesis SDC constraint file.
        """
        pass


class CadenceTool(HasSDCSupport, HammerTool):
    """Mix-in trait with functions useful for Cadence-based tools."""

    @property
    def config_dirs(self) -> List[str]:
        # Override this to pull in Cadence-common configs.
        return [self.get_setting("cadence.common_path")] + super().config_dirs

    @property
    def env_vars(self) -> Dict[str, str]:
        """
        Get the list of environment variables required for this tool.
        Note to subclasses: remember to include variables from super().env_vars!
        """
        # Use the base extra_env_variables and ensure that our custom variables are on top.
        list_of_vars = self.get_setting("cadence.extra_env_vars")  # type: List[Dict[str, Any]]
        assert isinstance(list_of_vars, list)

        cadence_vars = {
            "CDS_LIC_FILE": self.get_setting("cadence.CDS_LIC_FILE"),
            "CADENCE_HOME": self.get_setting("cadence.cadence_home")
        }

        def update_dict(old: dict, new: dict) -> dict:
            tmp = deepdict(old)
            tmp.update(new)
            return tmp

        return reduce(update_dict, [dict(super().env_vars)] + list_of_vars + [cadence_vars], {})

    def version_number(self, version: str) -> int:
        """
        Assumes versions look like MAJOR_ISRMINOR and we will have less than 100 minor versions.
        """
        main_version = int(version.split("_")[0]) # type: int
        minor_version = 0 # type: int
        if "_" in version:
            minor_version = int(version.split("_")[1][3:])
        return main_version * 100 + minor_version

    def get_timing_libs(self, corner: Optional[MMMCCorner] = None) -> str:
        """
        Helper function to get the list of ASCII timing .lib files in space separated format.
        Note that Cadence tools support ECSM, so we can use the ECSM-based filter.

        :param corner: Optional corner to consider. If supplied, this will use filter_for_mmmc to select libraries that
        match a given corner (voltage/temperature).
        :return: List of lib files separated by spaces
        """
        pre_filters = optional_map(corner, lambda c: [self.filter_for_mmmc(voltage=c.voltage,
                                                                           temp=c.temp)])  # type: Optional[List[Callable[[hammer_tech.Library],bool]]]

        lib_args = self.read_libs([self.timing_lib_with_ecsm_filter], self.to_plain_item, pre_filters=pre_filters)
        return " ".join(lib_args)

    def get_mmmc_qrc(self, corner: MMMCCorner) -> str:
        lib_args = self.read_libs([self.qrc_tech_filter],self.to_plain_item, pre_filters=[
            self.filter_for_mmmc(voltage=corner.voltage, temp=corner.temp)])
        return " ".join(lib_args)

    def get_qrc_tech(self) -> str:
        """
        Helper function to get the list of rc corner tech files in space separated format.

        :return: List of qrc tech files separated by spaces
        """
        lib_args = self.read_libs([
            self.qrc_tech_filter
        ], self.to_plain_item)
        return " ".join(lib_args)

    def generate_mmmc_script(self) -> str:
        """
        Output for the mmmc.tcl script.
        Innovus (init_design) requires that the timing script be placed in a separate file.

        :return: Contents of the mmmc script.
        """
        mmmc_output = []  # type: List[str]

        def append_mmmc(cmd: str) -> None:
            self.verbose_tcl_append(cmd, mmmc_output)

        # Create an Innovus constraint mode.
        constraint_mode = "my_constraint_mode"
        sdc_files = []  # type: List[str]

        # Generate constraints
        clock_constraints_fragment = os.path.join(self.run_dir, "clock_constraints_fragment.sdc")
        with open(clock_constraints_fragment, "w") as f:
            f.write(self.sdc_clock_constraints)
        sdc_files.append(clock_constraints_fragment)

        # Generate port constraints.
        pin_constraints_fragment = os.path.join(self.run_dir, "pin_constraints_fragment.sdc")
        with open(pin_constraints_fragment, "w") as f:
            f.write(self.sdc_pin_constraints)
        sdc_files.append(pin_constraints_fragment)

        # Add the post-synthesis SDC, if present.
        post_synth_sdc = self.post_synth_sdc
        if post_synth_sdc is not None:
            sdc_files.append(post_synth_sdc)

        # TODO: add floorplanning SDC
        if len(sdc_files) > 0:
            sdc_files_arg = "-sdc_files [list {sdc_files}]".format(
                sdc_files=" ".join(sdc_files)
            )
        else:
            blank_sdc = os.path.join(self.run_dir, "blank.sdc")
            self.run_executable(["touch", blank_sdc])
            sdc_files_arg = "-sdc_files {{ {} }}".format(blank_sdc)
        append_mmmc("create_constraint_mode -name {name} {sdc_files_arg}".format(
            name=constraint_mode,
            sdc_files_arg=sdc_files_arg
        ))

        corners = self.get_mmmc_corners()  # type: List[MMMCCorner]
        # In parallel, create the delay corners
        if corners:
            setup_corner = corners[0]  # type: MMMCCorner
            hold_corner = corners[0]  # type: MMMCCorner
            # TODO(colins): handle more than one corner and do something with extra corners
            for corner in corners:
                if corner.type is MMMCCornerType.Setup:
                    setup_corner = corner
                if corner.type is MMMCCornerType.Hold:
                    hold_corner = corner

            # First, create Innovus library sets
            append_mmmc("create_library_set -name {name} -timing [list {list}]".format(
                name="{n}.setup_set".format(n=setup_corner.name),
                list=self.get_timing_libs(setup_corner)
            ))
            append_mmmc("create_library_set -name {name} -timing [list {list}]".format(
                name="{n}.hold_set".format(n=hold_corner.name),
                list=self.get_timing_libs(hold_corner)
            ))
            # Skip opconds for now
            # Next, create Innovus timing conditions
            append_mmmc("create_timing_condition -name {name} -library_sets [list {list}]".format(
                name="{n}.setup_cond".format(n=setup_corner.name),
                list="{n}.setup_set".format(n=setup_corner.name)
            ))
            append_mmmc("create_timing_condition -name {name} -library_sets [list {list}]".format(
                name="{n}.hold_cond".format(n=hold_corner.name),
                list="{n}.hold_set".format(n=hold_corner.name)
            ))
            # Next, create Innovus rc corners from qrc tech files
            append_mmmc("create_rc_corner -name {name} -temperature {tempInCelsius} {qrc}".format(
                name="{n}.setup_rc".format(n=setup_corner.name),
                tempInCelsius=str(setup_corner.temp.value),
                qrc="-qrc_tech {}".format(self.get_mmmc_qrc(setup_corner)) if self.get_mmmc_qrc(setup_corner) != '' else ''
            ))
            append_mmmc("create_rc_corner -name {name} -temperature {tempInCelsius} {qrc}".format(
                name="{n}.hold_rc".format(n=hold_corner.name),
                tempInCelsius=str(hold_corner.temp.value),
                qrc="-qrc_tech {}".format(self.get_mmmc_qrc(hold_corner)) if self.get_mmmc_qrc(hold_corner) != '' else ''
            ))
            # Next, create an Innovus delay corner.
            append_mmmc(
                "create_delay_corner -name {name}_delay -timing_condition {name}_cond -rc_corner {name}_rc".format(
                    name="{n}.setup".format(n=setup_corner.name)
                ))
            append_mmmc(
                "create_delay_corner -name {name}_delay -timing_condition {name}_cond -rc_corner {name}_rc".format(
                    name="{n}.hold".format(n=hold_corner.name)
                ))
            # Next, create the analysis views
            append_mmmc("create_analysis_view -name {name}_view -delay_corner {name}_delay -constraint_mode {constraint}".format(
                name="{n}.setup".format(n=setup_corner.name), constraint=constraint_mode))
            append_mmmc("create_analysis_view -name {name}_view -delay_corner {name}_delay -constraint_mode {constraint}".format(
                name="{n}.hold".format(n=hold_corner.name), constraint=constraint_mode))
            # Finally, apply the analysis view.
            append_mmmc("set_analysis_view -setup {{ {setup_view} }} -hold {{ {hold_view} }}".format(
                setup_view="{n}.setup_view".format(n=setup_corner.name),
                hold_view="{n}.hold_view".format(n=hold_corner.name)
            ))
        else:
            # First, create an Innovus library set.
            library_set_name = "my_lib_set"
            append_mmmc("create_library_set -name {name} -timing [list {list}]".format(
                name=library_set_name,
                list=self.get_timing_libs()
            ))
            # Next, create an Innovus timing condition.
            timing_condition_name = "my_timing_condition"
            append_mmmc("create_timing_condition -name {name} -library_sets [list {list}]".format(
                name=timing_condition_name,
                list=library_set_name
            ))
            # extra junk: -opcond ...
            rc_corner_name = "rc_cond"
            append_mmmc("create_rc_corner -name {name} -temperature {tempInCelsius} {qrc}".format(
                name=rc_corner_name,
                tempInCelsius=120,  # TODO: this should come from tech config
                qrc="-qrc_tech {}".format(self.get_qrc_tech()) if self.get_qrc_tech() != '' else ''
            ))
            # Next, create an Innovus delay corner.
            delay_corner_name = "my_delay_corner"
            append_mmmc(
                "create_delay_corner -name {name} -timing_condition {timing_cond} -rc_corner {rc}".format(
                    name=delay_corner_name,
                    timing_cond=timing_condition_name,
                    rc=rc_corner_name
                ))
            # extra junk: -rc_corner my_rc_corner_maybe_worst
            # Next, create an Innovus analysis view.
            analysis_view_name = "my_view"
            append_mmmc("create_analysis_view -name {name} -delay_corner {corner} -constraint_mode {constraint}".format(
                name=analysis_view_name, corner=delay_corner_name, constraint=constraint_mode))
            # Finally, apply the analysis view.
            # TODO: introduce different views of setup/hold and true multi-corner
            append_mmmc("set_analysis_view -setup {{ {setup_view} }} -hold {{ {hold_view} }}".format(
                setup_view=analysis_view_name,
                hold_view=analysis_view_name
            ))

        return "\n".join(mmmc_output)

    def generate_dont_use_commands(self) -> List[str]:
        """
        Generate a list of dont_use commands for Cadence tools.
        """

        def map_cell(in_cell: str) -> str:
            # "*/" is needed for "get_db lib_cells <cell_expression>"
            if in_cell.startswith("*/"):
                mapped_cell = in_cell  # type: str
            else:
                mapped_cell = "*/" + in_cell

            # Check for cell existence first to avoid Genus erroring out.
            get_db_str = "[get_db lib_cells {mapped_cell}]".format(mapped_cell=mapped_cell)
            return """
puts "set_dont_use {get_db_str}"
if {{ {get_db_str} ne "" }} {{
    set_dont_use {get_db_str}
}} else {{
    puts "WARNING: cell {mapped_cell} was not found for set_dont_use"
}}
            """.format(get_db_str=get_db_str, mapped_cell=mapped_cell)

        return list(map(map_cell, self.get_dont_use_list()))

class SynopsysTool(HasSDCSupport, HammerTool):
    """Mix-in trait with functions useful for Synopsys-based tools."""
    @property
    def env_vars(self) -> Dict[str, str]:
        """
        Get the list of environment variables required for this tool.
        Note to subclasses: remember to include variables from super().env_vars!
        """
        result = dict(super().env_vars)
        result.update({
            "SNPSLMD_LICENSE_FILE": self.get_setting("synopsys.SNPSLMD_LICENSE_FILE"),
            # TODO: this is actually a Mentor Graphics licence, not sure why the old dc scripts depend on it.
            "MGLS_LICENSE_FILE": self.get_setting("synopsys.MGLS_LICENSE_FILE")
        })
        return result

    def version_number(self, version: str) -> int:
        """
        Assumes versions look like NAME-YYYY.MM-SPMINOR.
        Assumes less than 100 minor versions.
        """
        date = "-".join(version.split("-")[1:])  # type: str
        year = int(date.split(".")[0])  # type: int
        month = int(date.split(".")[1][:2])  # type: int
        minor_version = 0  # type: int
        if "-" in date:
            minor_version = int(date.split("-")[1][2:])
        return (year * 100 + month) * 100 + minor_version

    def get_synopsys_rm_tarball(self, product: str, settings_key: str = "") -> str:
        """Locate reference methodology tarball.

        :param product: Either "DC" or "ICC"
        :param settings_key: Key to retrieve the version for the product. Leave blank for DC and ICC.
        """
        key = self.tool_config_prefix() + "." + "version" # type: str

        synopsys_rm_tarball = os.path.join(self.get_setting("synopsys.rm_dir"), "%s-RM_%s.tar" % (product, self.get_setting(key)))
        if not os.path.exists(synopsys_rm_tarball):
            # TODO: convert these to logger calls
            raise FileNotFoundError("Expected reference methodology tarball not found at %s. Use the Synopsys RM generator <https://solvnet.synopsys.com/rmgen> to generate a DC reference methodology. If these tarballs have been pre-downloaded, you can set synopsys.rm_dir instead of generating them yourself." % (synopsys_rm_tarball))
        else:
            return synopsys_rm_tarball

def load_tool(tool_name: str, path: Iterable[str]) -> HammerTool:
    """
    Load the given tool.
    See the hammer-vlsi README for how it works.

    :param tool_name: Name of the tool
    :param path: List of paths to get
    :return: HammerTool of the given tool
    """
    # Temporarily add to the import path.
    for p in path:
        sys.path.insert(0, p)
    try:
        mod = importlib.import_module(tool_name)
    except ImportError:
        raise ValueError("No such tool " + tool_name)
    # Now restore the original import path.
    for _ in path:
        sys.path.pop(0)
    try:
        tool_class = getattr(mod, "tool")
    except AttributeError:
        raise ValueError("No such tool " + tool_name + ", or tool does not follow the hammer-vlsi tool library format")

    if not issubclass(tool_class, HammerTool):
        raise ValueError("Tool must be a HammerTool")

    # Set the tool directory.
    tool = tool_class()
    tool.tool_dir = os.path.dirname(os.path.abspath(mod.__file__))
    return tool


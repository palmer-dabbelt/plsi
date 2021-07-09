#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  hammer-vlsi plugin for generic PCB deliverables. This can generate
#  footprints, schematic symbols, and CSVs for visualizing the bump map.
#
#  See LICENSE for licence details.

import os
import datetime
import re
from typing import List, Dict, Tuple
from decimal import Decimal
from hammer_utils import um2mm

from hammer_vlsi import HammerPCBDeliverableTool, HammerToolStep, BumpsPinNamingScheme, BumpsDefinition, BumpAssignment

class GenericPCBDeliverableTool(HammerPCBDeliverableTool):

    def tool_config_prefix(self) -> str:
        return "pcb.generic"

    def version_number(self, version: str) -> int:
        return 1

    def fill_outputs(self) -> bool:
        self.output_footprints = [self.output_footprint_filename]
        self.output_schematic_symbols = [self.output_schematic_symbol_filename]
        return True

    @property
    def steps(self) -> List[HammerToolStep]:
        steps = [
            self.create_footprint_csv,
            self.create_footprint,
            self.create_bom_builder_pindata_txt,
            self.create_mechanical_drawing,
            self.create_schematic_symbols
        ]
        return self.make_steps_from_methods(steps)

    @property
    def output_footprint_filename(self) -> str:
        # change this when supporting other types
        return os.path.join(self.run_dir, "{top}-pads.d".format(top=self.top_module))

    @property
    def output_footprint_csv_filename(self) -> str:
        return os.path.join(self.run_dir, "{top}-pads.csv".format(top=self.top_module))

    @property
    def output_mechanical_drawing_filename(self) -> str:
        # change this when supporting other types
        return os.path.join(self.run_dir, "{top}-pads.svg".format(top=self.top_module))

    @property
    def output_schematic_symbol_filename(self) -> str:
        # change this when supporting other types
        return os.path.join(self.run_dir, "{top}-symbol.csv".format(top=self.top_module))

    @property
    def output_bom_builder_pindata_filename(self) -> str:
        return os.path.join(self.run_dir, "{top}-pindata.txt".format(top=self.top_module))

    @property
    def footprint_name(self) -> str:
        return "TESTCHIP-{}".format(self.top_module)

    @property
    def bump_pad_opening_diameter(self) -> Decimal:
        """
        Get the diameter of the PCB footprint pad opening in post-shrink um.
        """
        diameter = self.get_setting("technology.pcb.bump_pad_opening_diameter")
        if diameter is None:
            raise ValueError("Must provide a technology.pcb.bump_pad_opening_diameter if generating PCB deliverables.")
        else:
            return Decimal(str(diameter))

    @property
    def bump_pad_metal_diameter(self) -> Decimal:
        """
        Get the diameter of the PCB footprint pad metal in post-shrink um.
        """
        diameter = self.get_setting("technology.pcb.bump_pad_metal_diameter")
        if diameter is None:
            raise ValueError("Must provide a technology.pcb.bump_pad_metal_diameter if generating PCB deliverables.")
        else:
            return Decimal(str(diameter))

    def get_bumps_and_assignments(self) -> Tuple[BumpsDefinition, List[BumpAssignment]]:
        """
        Helper method to get non-Optional versions of the bumps definition and bumps assignment list.
        """
        bumps = self.get_bumps()
        if bumps is None:
            raise ValueError("There must be a bumps definition in order to generate to generate PCB deliverables!")
        assert isinstance(bumps, BumpsDefinition)

        assignments = bumps.assignments
        if assignments is None:
            raise ValueError("There must be at least 1 bump in order to generate PCB deliverables!")
        assert isinstance(assignments, list)

        if bumps.x < 1 or bumps.y < 1 or len(bumps.assignments) < 1:
            raise ValueError("There must be at least 1 bump in order to generate PCB deliverables!")

        return (bumps, assignments)

    def create_bom_builder_pindata_txt(self) -> bool:
        """
        Creates a PINDATA.txt file that is consumed by the BOMBuilder tool to create a package.
        BOMBuilder is part of the PartSync tool suite: http://www.partsync.com/
        """

        bumps, assignments = self.get_bumps_and_assignments()
        naming_scheme = self.naming_scheme

        # Sort the bumps
        sorted_assignments = naming_scheme.sort_by_name(bumps, assignments)

        # Use post-shrink pitch
        pitch = self.technology.get_post_shrink_length(bumps.pitch)

        # There is no meaningful verion for this file
        # Set the units to metric (mm)
        output = "VER 0.0\nUNIT M\n"
        x_offset = ((1 - bumps.x) * pitch) / 2  # type: Decimal
        y_offset = ((1 - bumps.y) * pitch) / 2  # type: Decimal
        for bump in sorted_assignments:
            # note that the flip-chip mirroring happens here
            name = naming_scheme.name_bump(bumps, bump)
            x = um2mm(Decimal(str(bumps.x - bump.x)) * pitch + x_offset, 3)
            y = um2mm(Decimal(str(bump.y - 1)) * pitch + y_offset, 3)
            # Fields in order (with valid options):
            # Name
            # X position (mm)
            # Y position (mm)
            # Shape (RND or RECT)
            # Width (mm)
            # Height (mm)
            # Side (TOP or BOT)
            # Connection offset X (mm)
            # Connection offset Y (mm)
            # Lead type (0 = signal pin, 1 = mounting hole, 2 = shield)
            # Hole lock (T = true, F = false)
            # Plated/Not Plated (P = Plated, N = Not plated)
            output += "{name:<6} {x:>10.3f} {y:>10.3f} RND {w:0.3f} {w:0.3f} NONE SMT TOP 0 0 0 F P\n".format(name=name, x=x, y=y, w=um2mm(self.bump_pad_metal_diameter, 3))

        with open(self.output_bom_builder_pindata_filename, "w") as f:
            f.write(output)

        return True

    def create_footprint_csv(self) -> bool:
        """
        Create a CSV of the bump map to be easily read into your spreadsheet editor of choice.
        This will fail silently with non-integer bump assignment coordinates (they'll be ignored).

        :return: True if successful
        """

        bumps, assignments = self.get_bumps_and_assignments()

        output = ""
        for y in range(bumps.y,0,-1):
            for x in range(1,bumps.x+1):
                # This is a pretty inefficient algorithm for this task
                matches = [z for z in bumps.assignments if z.x == x and z.y == y]
                if len(matches) > 0:
                    output += str(matches[0].name)
                output += ","
            output += "\n"

        with open(self.output_footprint_csv_filename, "w") as f:
            f.write(output)

        return True

    def create_footprint(self) -> bool:
        """
        Create the footprint type requested by pcb.generic.footprint_type. Currently only supports PADS-V9,
        and does not correctly output soldermask or solderpaste openings.

        :return: True if successful
        """
        footprint_type = str(self.get_setting("pcb.generic.footprint_type"))
        if footprint_type != "PADS-V9":
            raise NotImplementedError("Unsupported footprint type: {}".format(footprint_type))

        bumps, assignments = self.get_bumps_and_assignments()

        # Use post-shrink pitch
        pitch = self.technology.get_post_shrink_length(bumps.pitch)

        # Here is a good ref for the PADS V9 format:
        # ftp://ftp.freecalypso.org/pub/CAD/PADS/pdfdocs/Plib_ASCII.pdf

        # for now, let's make the outline 4 pitches larger than the bump array
        outline_width = ((bumps.x + 3) * pitch)
        outline_height = ((bumps.y + 3) * pitch)

        output = "*PADS-LIBRARY-PCB-DECALS-V9*\n\n"
        # Fields in order from left to right
        # name
        # coordinate units type (M=metric, mm)
        # origin x
        # origin y
        # number of attributes (0)
        # number of labels (0)
        # number of drawing pieces (1: the outline)
        # number of free text strings (0)
        # number of terminals (number of bumps)
        # number of pad stack definitions (1)
        # maxlayers mode (0 = standard)
        output += "{top} M 0 0 0 0 1 0 {terminals} 1 0\n".format(top=self.footprint_name, terminals=len(bumps.assignments))

        # create the timestamp
        output += datetime.datetime.now().strftime("TIMESTAMP %Y.%m.%d.%H.%M.%S\n")

        # create the outline
        # 6 points, 0.1 mm wide, layer 1, solid line
        output += "OPEN 6 0.1 1 -1\n"

        # we'll dog-ear the outline to indicate the reference bump in the top left
        # x and y are in mm, not um
        output += "{x} {y}\n".format(x=um2mm(-outline_width/2, 3),           y=um2mm(-outline_height/2, 3))
        output += "{x} {y}\n".format(x=um2mm(-outline_width/2, 3),           y=um2mm( outline_height/2 - 2*pitch, 3))
        output += "{x} {y}\n".format(x=um2mm(-outline_width/2 + 2*pitch, 3), y=um2mm( outline_height/2, 3))
        output += "{x} {y}\n".format(x=um2mm( outline_width/2, 3),           y=um2mm( outline_height/2, 3))
        output += "{x} {y}\n".format(x=um2mm( outline_width/2, 3),           y=um2mm(-outline_height/2, 3))
        output += "{x} {y}\n".format(x=um2mm(-outline_width/2, 3),           y=um2mm(-outline_height/2, 3))

        # create all of the terminals
        x_offset = ((1 - bumps.x) * pitch) / 2  # type: Decimal
        y_offset = ((1 - bumps.y) * pitch) / 2  # type: Decimal
        naming_scheme = self.naming_scheme
        for bump in bumps.assignments:
            # note that the flip-chip mirroring happens here
            x = um2mm(Decimal(str(bumps.x - bump.x)) * pitch + x_offset, 3)
            y = um2mm(Decimal(str(bump.y - 1)) * pitch + y_offset, 3)
            label = naming_scheme.name_bump(bumps, bump)
            output += "T{x} {y} {x} {y} {label}\n".format(x=x, y=y, label=label)

        # create the pad definition
        # 0=default pad
        # 3=num layer lines
        # P=plated
        # 0=drill diameter (0=no drill)
        output += "PAD 0 3 P 0\n"
        # -2=top layer
        # diameter
        # R=round pad
        output += "-2 {dia} R\n".format(dia=um2mm(self.bump_pad_opening_diameter, 3))
        # -1=all inner layers
        # 0=no pad
        # R=round pad
        output += "-1 0 R\n"
        # 0=bottom layer
        # 0=no pad
        # R=round pad
        output += "0 0 R\n"

        output += "\n*END*"

        with open(self.output_footprint_filename, "w") as f:
            f.write(output)

        return True

    def create_mechanical_drawing(self) -> bool:
        """
        Create an SVG-based mechanical drawing of the bump-out.

        :return: True if successful
        """

        bumps, assignments = self.get_bumps_and_assignments()

        # Use post-shrink pitch

        # TODO fixme this is just copied/pasted from eagle
        die_w_um = self.technology.get_post_shrink_length(Decimal(7500))
        die_h_um = die_w_um

        # Some input values and a conversion factor
        canvas_w_px = Decimal(10000)
        margin_px = Decimal(10)
        die_w_px = canvas_w_px - (2*margin_px)
        px_per_um = die_w_px / die_w_um

        # Calculate the rest of the canvas size
        die_h_px = die_h_um * px_per_um
        canvas_h_px = die_h_px + (2*margin_px)

        # Some other things we need to calculate
        pitch_um = self.technology.get_post_shrink_length(bumps.pitch)
        pitch_px = pitch_um * px_per_um
        opening_um = self.bump_pad_opening_diameter
        opening_px = opening_um * px_per_um

        offset_px = margin_px + opening_px / Decimal(2)

        # Header
        output = """<?xml version="1.0"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">""".format(width=canvas_w_px,height=canvas_h_px)

        # Styles
        output += """
<defs><style type="text/css">
circle {
    stroke: #000000;
    fill: #ffffff;
    stroke-width: 3;
}
rect {
    stroke: #000000;
    fill: #ffffff;
    stroke-width: 3;
}
path {
    stroke: none;
    fill: #000000;
}
</style></defs>
"""

        # Die
        output += "<rect x=\"{x}\" y=\"{y}\" width=\"{w}\" height=\"{h}\" />\n".format(x=margin_px, y=margin_px, w=die_w_px, h=die_h_px)

        # A1 marker
        x0 = die_w_px - pitch_px
        x1 = die_w_px
        y0 = 2*margin_px
        y1 = y0 + pitch_px
        output += "<path d=\"M{x0} {y0} L{x1} {y0} L{x1} {y1} Z\" />\n".format(x0=x0, x1=x1, y0=y0, y1=y1)

        for bump in assignments:
            x = offset_px + bump.x * pitch_px
            y = canvas_h_px - (offset_px + bump.y * pitch_px)
            r = opening_px * Decimal("0.5") # radius
            l = opening_px * Decimal("0.9") # 90% of the diameter
            name = bump.name
            classes = "" # none for now
            output += "<circle cx=\"{x}\" cy=\"{y}\" r=\"{r}\" class=\"{classes}\" />\n".format(x=x, y=y, r=r, classes=classes)
            output += "<text x=\"{x}\" y=\"{y}\" textLength=\"{l}\" text-anchor=\"middle\" alignment-baseline=\"middle\" lengthAdjust=\"spacingAndGlyphs\">{name}</text>\n".format(x=x, y=y, l=l, name=name)

        output += "</svg>\n"

        with open(self.output_mechanical_drawing_filename, "w") as f:
            f.write(output)

        return True


    def create_schematic_symbols(self) -> bool:
        """
        Create the schematic symbol type requested by pcb.generic.schematic_symbol_type. Currently only supports
        AltiumCSV, which is a format Altium allows to be copy-and-pasted into the schematic symbol wizard.
        This will divide the pins into groups based on their "group" field.

        :return: True if successful
        """
        schematic_symbol_type = str(self.get_setting("pcb.generic.schematic_symbol_type"))
        if schematic_symbol_type != "AltiumCSV":
            raise NotImplementedError("Unsupported schematic symbool type: {}".format(schematic_symbol_type))

        bumps, assignments = self.get_bumps_and_assignments()

        naming_scheme = self.naming_scheme
        groups = {}  # type: Dict[str, List[BumpAssignment]]

        for a in assignments:
            group = a.group
            if a.group is None:
                # TODO make me smarter
                if a.name in ["VDD", "VSS"]:
                    group = a.name
                else:
                    group = "ungrouped"
            assert isinstance(group, str)


            if group not in groups:
                groups[group] = [a]
            else:
                # Cap each group at 50
                while group in groups and len(groups[group]) >= 50:
                    match = re.match("^(.*)_(\d+)$", group)
                    if match:
                        old = int(match.group(2))
                        group = match.group(1) + "_{new}".format(new=old+1)
                    else:
                        group = group + "_1"

                if group not in groups:
                    groups[group] = [a]
                else:
                    groups[group].append(a)

        group_names = sorted([n for n in groups])
        num_rows = max([len(v) for k,v in groups.items()])

        output = ""
        # Build the headers
        for group in group_names:
            output += "{group},,,,,,,,".format(group=group)
        output += "\n"
        # Now the column headers
        for group in group_names:
            output += "Position,Group,Display Name,Designator,Electrical Type,Description,Side,,"
        output += "\n"

        for i in range(num_rows):
            for group in group_names:
                if len(groups[group]) > i:
                    bump = groups[group][i]
                    # TODO(johnwright) Use the Verilog to make Passive actually have a meaningful direction
                    output += "{pos},,{name},{des},Passive,,Left,,".format(pos=i+1,name=bump.name,des=naming_scheme.name_bump(bumps, bump))
                else:
                    output += ",,,,,,,,"
            output += "\n"

        with open(self.output_schematic_symbol_filename, "w") as f:
            f.write(output)


        return True


tool = GenericPCBDeliverableTool

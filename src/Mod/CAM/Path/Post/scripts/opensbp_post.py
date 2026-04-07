# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2025 sliptonic <shopinthewoods@gmail.com>

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

"""
OpenSBP Post Processor for ShopBot Controllers

This is a new-style postprocessor that uses the hook methods pattern to override
specific command handling for the OpenSBP dialect used by ShopBot controllers.

OpenSBP uses commands like:
  - MX, MY, MZ - Move (feed) single axis
  - M2, M3 - Move (feed) multiple axes
  - JX, JY, JZ - Jog (rapid) single axis
  - J2, J3 - Jog (rapid) multiple axes
  - CG - Circular interpolation (arcs)
  - TR - Set spindle RPM
  - MS, JS - Set move/jog speeds

This postprocessor demonstrates how to override only the necessary hook methods
without reimplementing the entire convert_command_to_gcode function.

FIXME: axis-modal may have occured, use self.machine_state to recover params
"""

from typing import Any, Dict

from Path.Post.Processor import PostProcessor

import FreeCAD
import Path
import Constants

translate = FreeCAD.Qt.translate

DEBUG = False


# Set logging level based on DEBUG flag
def _setup_logging():
    if DEBUG:
        Path.Log.setLevel(Path.Log.Level.DEBUG, Path.Log.thisModule())
        Path.Log.trackModule(Path.Log.thisModule())
    else:
        Path.Log.setLevel(Path.Log.Level.INFO, Path.Log.thisModule())


_setup_logging()

# Define types
Values = Dict[str, Any]

POST_TYPE = "machine"


class OpenSBPPost(PostProcessor):
    """
    OpenSBP postprocessor for ShopBot controllers.

    OpenSBP can use most gcodes (see GCodeKnow), with a few translated to opensbp
    """

    # This list is specific to shopbot, do not use Mod/CAM/Constants.py
    # from https://shopbottools.com/wp-content/uploads/2024/01/SBG-00142-User-Guide-20150317.pdf
    # It includes commands that Operations shouldn't generate (cf. Constants.GCODE_NON_CONFORMING)
    # It may include commands that Post/Processor.py shouldn't generate (cf. Constants.GCODE_SUPPORTED and Constants.MCODE_SUPPORTED and Constants.GCODE_NON_CONFORMING)
    # Compatible should just pass-through
    GCodeNative = set(
        "G0 G00 G1 G01 G4 G04 G20 G21 G28 G29 G38.2 G92 M0 M00 M1 M01 M2 M02 M3 M03 M5 M05 M8 M08 M9 M09 M10 M11 M30".split(
            " "
        )
    )
    # Suppressed/Tolerated
    # because G54 is a default Job value, but shopbot has no concept
    # G98/G99/G80 should have been consumed by drillcycleexpander FIXME
    GCodeSuppressed = set("G54 G98 G99 G80".split(" "))

    # Unsupported
    GCodeUnsupported = set(
        "G40 G41 G42 G43 "
        "G55 G56 G57 G58 G59 G59.1 G59.2 G59.3 G59.4 G59.5 G59.6 G59.7 G59.8 G59.9 "  # work-offsets
        "G74 "
        "G93 G94 G95 "  # opensbp only does units/sec
        "G96 G97 "  # spindle control?
        # "G98 G99 "  # canned-retract FIXME: check that we do one of these
        "M4 ".rstrip().split(" ")  # ccw speed. We could support this
    )

    # Others require translation
    GCodeTranslate = set("G2 G02 G3 G03 G73 M6 M06 M7".split(" "))
    GCodeKnown = GCodeTranslate | GCodeNative | GCodeSuppressed
    if GCodeKnown & GCodeUnsupported:
        raise Exception(
            f"Internal: you screwed up and have a value in both GCodeKnown & GCodeUnsupported: {GCodeKnown & GCodeUnsupported}"
        )

    # gcodes that are supported but shouldn't be used by CAM or Post/Processing
    GCodeDontUse = GCodeKnown - set(
        Constants.GCODE_SUPPORTED + Constants.MCODE_SUPPORTED + Constants.GCODE_NON_CONFORMING
    )

    # What we should support
    GCodeSupported = GCodeKnown - GCodeDontUse - GCodeUnsupported

    print(f"#== sbp native gcode {sorted(GCodeNative)}")
    print(
        f"#== sbp non-gcode {sorted(set(Constants.GCODE_SUPPORTED + Constants.MCODE_SUPPORTED + Constants.GCODE_NON_CONFORMING) - GCodeNative)}"
    )
    print(
        f"#== sbp unsupported {sorted(set(Constants.GCODE_SUPPORTED + Constants.MCODE_SUPPORTED + Constants.GCODE_NON_CONFORMING) - GCodeKnown)}"
    )
    print(f"#== sbp don't use {sorted(GCodeDontUse)}")
    print(f"#== sbp useable {sorted(GCodeKnown - GCodeDontUse)}")

    @classmethod
    def get_common_property_schema(cls):
        """Override common properties with OpenSBP-specific defaults."""
        common_props = super().get_common_property_schema()

        # Override defaults for OpenSBP
        for prop in common_props:
            if prop["name"] == "file_extension":
                prop["default"] = "sbp"
            elif prop["name"] == "preamble":
                prop["default"] = (
                    "'OpenSBP output from FreeCAD\n"
                    "'NOTE: In OpenSBP, M3 is a 3-axis MOVE command, NOT spindle control\n"
                    "'Spindle control is via TR (speed) and C6/C7 (on/off) commands"
                )
            elif prop["name"] == "postamble":
                prop["default"] = "C7\n'End of program"
            elif prop["name"] == "supported_commands":
                prop["default"] = "\n".join(cls.GCodeSupported)
            elif prop["name"] == "drill_cycles_to_translate":
                prop["default"] = "\n".join(
                    Constants.GCODE_DRILL_EXTENDED + Constants.GCODE_MOVE_DRILL
                )

        return common_props

    @classmethod
    def get_property_schema(cls):
        """Return schema for OpenSBP-specific configurable properties."""
        return [
            {
                "name": "automatic_tool_changer",
                "type": "bool",
                "label": translate("CAM", "Automatic Tool Changer"),
                "default": False,
                "help": translate(
                    "CAM",
                    "Enable if machine has automatic tool changer. "
                    "If disabled, tool changes will pause for manual intervention.",
                ),
            },
            {
                "name": "automatic_spindle",
                "type": "bool",
                "label": translate("CAM", "Automatic Spindle Control"),
                "default": False,
                "help": translate(
                    "CAM",
                    "Enable if machine has automatic spindle speed control. "
                    "If disabled, spindle commands will prompt for manual adjustment.",
                ),
            },
            # FIXME: should be a general option
            {
                "name": "suppressed_commands",
                "type": "text",
                "label": translate("CAM", "Suppressed (tolerated) G-code Commands"),
                "default": "\n".join(cls.GCodeSuppressed),
                "help": translate(
                    "CAM",
                    "List of G-code commands tolerated but suppressed by this post-processor (one per line). "
                    "Commands this list will be filtered out",
                ),
            },
        ]

    def __init__(
        self,
        job,
        tooltip=translate("CAM", "OpenSBP post processor for ShopBot controllers"),
        tooltipargs=[],
        units="Metric",
    ) -> None:
        super().__init__(
            job=job,
            tooltip=tooltip,
            tooltipargs=tooltipargs,
            units=units,
        )
        Path.Log.debug("OpenSBP post processor initialized.")

        # Track current speeds for OpenSBP (separate XY and Z speeds)
        self._current_move_speed_xy = None
        self._current_move_speed_z = None
        self._current_jog_speed_xy = None
        self._current_jog_speed_z = None

    def _apply_job_property_overrides(self):
        super()._apply_job_property_overrides()

        # FIXME: should be able to remove output-options, and override them (hidden in init and a separate class)
        # G-Code MUST have line-numbers (native must NOT)
        self._machine.output.formatting.line_numbers = True

        self._machine.output.formatting.line_number_start = 1
        self._machine.output.formatting.line_increment = 1

        # FIXME: what is the right way to set defaults?
        self._machine.output.output_tool_length_offset = False
        self.values["OUTPUT_TOOL_LENGTH_OFFSET"] = False

        self._machine.output.duplicates.parameters = False

        self._machine.processing.filter_inefficient_moves = False

    def init_values(self, values: Values) -> None:
        """Initialize values that are used throughout the postprocessor."""
        super().init_values(values)

        # OpenSBP-specific settings
        values["MACHINE_NAME"] = "ShopBot"
        values["POSTPROCESSOR_FILE_NAME"] = __name__

        # Load configuration from machine properties if available
        if self._machine and hasattr(self._machine, "postprocessor_properties"):
            props = self._machine.postprocessor_properties
            values["AUTOMATIC_TOOL_CHANGER"] = props.get("automatic_tool_changer", False)
            values["AUTOMATIC_SPINDLE"] = props.get("automatic_spindle", False)
        else:
            values["AUTOMATIC_TOOL_CHANGER"] = False
            values["AUTOMATIC_SPINDLE"] = False

    def convert_command_to_gcode(self, command: Path.Command) -> str:
        print(f"#== SBP convert({command})..")

        # FIXME: should be in Processor class
        if command.Name in self._machine.postprocessor_properties.get("suppressed_commands").split(
            "\n"
        ):
            print(f"#== Suppress {command}")
            Path.Log.debug(f"opensbp suppressed {command}")
            return None

        # FIXME: should be in Processor class
        if command.Name not in self.GCodeSupported and not command.Name.startswith("("):
            raise ValueError(
                f"opensbp does not support {command.toGCode()}. Supported: {self.GCodeSupported}"
            )

        return super().convert_command_to_gcode(command)

    def _convert_comment(self, command):
        """
        Convert comments to OpenSBP format (single quote prefix).
        """
        # Extract comment text
        comment_text = (
            command.Name[1:-1]
            if command.Name.startswith("(") and command.Name.endswith(")")
            else command.Name[1:]
        )

        # OpenSBP uses single quote for comments
        return f"'{comment_text}"

    def _convert_arc_move(self, command):
        """
        Convert arc moves (G2/G3) that change Z to OpenSBP CG command.
        Non-changing-Z is passed through as G2/G3.

        OpenSBP CG format: CG,,X,Y,I,J,T,direction[,plunge]
        where:
        - direction is 1 for CW (G2) or -1 for CCW (G3)
        - plunge is optional Z movement (relative, sign inverted)

        Note: ShopBot only supports arcs in XY plane with I,J offsets.
        If Z is present, it's converted to a helical arc with plunge parameter.
        NB: Plunge is relative, so we need the current Z position
        """
        params = command.Parameters

        # We may be axis-modal
        machine_state_params = self.machine_state.getState()
        params.update(
            {
                p: machine_state_params[p]
                for p in "XYZF"
                if params.get(p, None) is None and machine_state_params[p] is not None
            }
        )

        AllowedParameters = set("XYZIJFN")

        if illegal := [x for x in params if x not in AllowedParameters]:
            # FIXME: what is the right way to report error? How to include context?
            raise ValueError(
                f"Only XYZIFJN allowed for a {command.Name}, saw {illegal} in {command}"
            )
        if missing := [x for x in AllowedParameters - {"N"} if x not in params]:
            raise ValueError(
                f"Requires XYZIFJ for a {command.Name}, missing {missing} in {command} (and in machine-state {self.machine_state})"
            )

        # Leave as G-Code
        if params["Z"] == self.machine_state.Z:
            return super()._convert_arc_move(command)

        # Get unit conversion function
        def get_value(val):
            if self._machine and hasattr(self._machine, "output"):
                from Machine.models.machine import OutputUnits

                if self._machine.output.units == OutputUnits.IMPERIAL:
                    return val / 25.4
            return val

        # Determine direction
        direction = "1" if command.Name in ["G2", "G02"] else "-1"

        # Extract arc parameters
        # params can be modal (except IJZ)
        param_keys = list("XY")
        param_values = [
            get_value(params.get(p, getattr(self.machine_state, p))) for p in param_keys
        ]
        print(f"CG params: {param_values}")
        required = [p for i, p in enumerate(param_keys) if param_values[i] is None]
        required += [p for p in "IJZ" if params.get(p, None) is None]
        if required:
            raise ValueError(
                f"Helixes require {''.join(param_keys)} (including previous modal values), missing {required} in {command}"
            )

        x_val, y_val = param_values
        i_val, j_val = params["I"], params["J"]
        z_val = params["Z"]

        output = []

        # Helical arc - need to calculate plunge
        # Get current Z from modal state (default to 0 if not set)
        current_z = self.machine_state.Z
        if current_z is None:
            # FIXME: we could actually generate a calculate based on machine's actual Z variable...
            raise ValueError(f"Helixes require a previous Z (from some movement) for {command}")
        plunge = get_value(current_z - z_val)  # Relative, inverted sign

        # Set move speed if feed rate is specified
        # F is in mm/sec (FreeCAD base units); ShopBot also expects per-second.
        if "F" in params:
            speed = get_value(params["F"])
            # Only output if speed changed
            # FIXME: project xy|z
            if self._current_move_speed_xy != speed or self._current_move_speed_z != speed:
                output.append(
                    f"MS,{self.format_parameter('F',speed)},{self.format_parameter('F',speed)}"
                )
                self._current_move_speed_xy = speed
                self._current_move_speed_z = speed

        output.append(
            f"CG,,{self.format_parameter('X',x_val)},{self.format_parameter('Y',y_val)},{self.format_parameter('X',i_val)},{self.format_parameter('Y',j_val)},T,{direction},{self.format_parameter('Z',plunge)}"
        )

        return "\n".join(output) if output else None

    def _convert_tool_change(self, command):
        """
        Convert tool change (M6) to OpenSBP tool commands.

        Supports both automatic and manual tool changers based on configuration.
        """
        params = command.Parameters
        tool_num = int(params.get("T", 0))

        output = []

        print(f"#== tool-change {command.toGCode()}")
        # Check if automatic tool changer is enabled
        has_atc = self._machine.postprocessor_properties.get("automatic_tool_changer", False)

        # If the toolchange was generated by a ToolController, we have the name
        # but, if it was elsewhere, we may not
        # FIXME: can we look up the Tool name?
        tool_name = command.Annotations.get(
            "label", str(tool_num)
        )  # FIXME: we want the Tool name, not tc name
        # FIXME: sanitize tool_name for string

        if has_atc:
            # Automatic tool changer
            output.append(f"&ToolName={tool_name}")
            output.append(f"&Tool={tool_num}")  # FIXME: we want the Tool name, not tc name
        else:
            # Manual tool change - pause and prompt
            output.append(f"'Manual tool change to T{tool_num}: {tool_name}")
            output.append(f"&ToolName={tool_name}")
            output.append(f"&Tool={tool_num}")
            output.append("PAUSE")

        return "\n".join(output)

    def _convert_spindle_command(self, command):
        """
        Convert spindle commands (M3/M4/M5) to OpenSBP TR command.

        Supports both automatic and manual spindle control based on configuration.
        """
        params = command.Parameters
        if self._machine and hasattr(self._machine, "postprocessor_properties"):
            has_auto_spindle = self._machine.postprocessor_properties.get(
                "automatic_spindle", False
            )
        else:
            has_auto_spindle = False

        if command.Name in ["M5", "M05"]:
            # Spindle off
            if has_auto_spindle:
                return "TR,0\nC7"
            else:
                return "'Turn spindle OFF manually\n>PAUSE"

        # Spindle on (M3/M4)
        rpm = int(params.get("S", 0))

        output = []

        if has_auto_spindle:
            # Automatic spindle control
            output.append(f"TR,{rpm}")
            output.append("C6")  # Start spindle
            output.append("PAUSE 2")  # Wait for spindle to reach speed
        else:
            # Manual spindle control - prompt user
            output.append(f"'Set spindle to {rpm} RPM and start manually")
            output.append("PAUSE")

        return "\n".join(output)

    def _optimize_gcode(self, header_lines, gcode_lines) -> str:
        # There may be opensbp in the stream
        # so, you can't know the state for modal and axis-modal
        # FIXME: this override goes away when Processor's does
        was_c = self._machine.output.duplicates.commands
        was_p = self._machine.output.duplicates.parameters
        was_eff = self._machine.processing.filter_inefficient_moves

        try:
            self._machine.output.duplicates.commands = True
            self._machine.output.duplicates.parameters = True
            self._machine.processing.filter_inefficient_moves = False
            return super()._optimize_gcode(header_lines, gcode_lines)
        finally:
            self._machine.output.duplicates.commands = was_c
            self._machine.output.duplicates.parameters = was_p
            self._machine.processing.filter_inefficient_moves = was_eff

    @property
    def tooltip(self):
        tooltip: str = """
        This is a postprocessor file for the CAM workbench.
        It is used to take a pseudo-gcode fragment from a CAM object
        and output OpenSBP code suitable for ShopBot CNC controllers.

        OpenSBP uses native commands like MX, MY, M2, M3 for moves,
        CG for arcs, TR for spindle speed, etc.
        """
        return tooltip


# Class alias for PostProcessorFactory
# The factory looks for a class with title-cased postname (e.g., "Opensbp")
Opensbp = OpenSBPPost


# Factory function for creating the postprocessor
def create(job, **kwargs):
    """
    Factory function to create an OpenSBP postprocessor instance.
    """
    return OpenSBPPost(job, **kwargs)

# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 sliptonic <shopinthewoods@gmail.com>
# SPDX-FileNotice: Part of the FreeCAD project.

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
Standalone drill cycle expander for FreeCAD Path.Command objects.

This module provides a clean API for expanding canned drill cycles without
coupling to the postprocessing infrastructure.
"""

from typing import List, Optional

import Path
from Constants import GCODE_EXPANDABLE_DRILL

debug = True
if debug:
    Path.Log.setLevel(Path.Log.Level.DEBUG, Path.Log.thisModule())
    Path.Log.trackModule(Path.Log.thisModule())
else:
    Path.Log.setLevel(Path.Log.Level.INFO, Path.Log.thisModule())


class DrillCycleExpander:
    """Expands canned drill cycles (Path.Command) into basic G-code movements."""

    # We might have a different list
    EXPANDABLE_CYCLES = GCODE_EXPANDABLE_DRILL

    def __init__(
        self,
        retract_mode: str = "G98",
        initial_position: Optional[dict] = None,
        chipbreaking_amount: None | float = None,  # only G73, default 5%, a distance
    ):
        """
        Initialize the expander.

        Args:
            retract_mode: "G98" (return to initial Z) or "G99" (return to R plane)
            initial_position: Initial position dict with X, Y, Z keys
        """
        self.retract_mode = retract_mode
        self.current_position = (
            initial_position if initial_position else {"X": 0.0, "Y": 0.0, "Z": 0.0}
        )
        self.chipbreaking_amount = chipbreaking_amount

    def expand_command(self, command: Path.Command) -> List[Path.Command]:
        """
        Expand a single drill cycle command into basic movements.

        Args:
            command: Path.Command object (e.g., Path.Command("G81", {"X": 10.0, "Y": 10.0, "Z": -5.0, "R": 2.0, "F": 100.0}))

        Returns:
            List of expanded Path.Command objects
        """
        cmd_name = command.Name.upper()
        params = command.Parameters

        # Handle modal commands - filter them out after processing
        if cmd_name == "G98":
            self.retract_mode = "G98"
            return []  # Filter out after processing
        elif cmd_name == "G99":
            self.retract_mode = "G99"
            return []  # Filter out after processing
        elif cmd_name == "G90":
            return []  # Filter out after processing
        elif cmd_name == "G80":
            # Cancel drill cycle - filter out since cycles are already expanded
            return []

        # Handle drill cycles
        if cmd_name in self.EXPANDABLE_CYCLES:
            result = self._expand_drill_cycle(command)
            Path.Log.debug(f"Expanded drill cycle: {command} -> {result}")
            return result

        # Update position for non-drill commands
        if cmd_name in ("G0", "G00", "G1", "G01"):
            for axis in ("X", "Y", "Z"):
                if axis in params:
                    self.current_position[axis] = params[axis]

        # Pass through other commands unchanged
        Path.Log.debug(f"Passing through command: {command}")
        return [command]

    def _expand_drill_cycle(self, command: Path.Command) -> List[Path.Command]:
        """Expand a drill cycle into basic movements.
        As per ADR-002, we are in Path.Command world, so no G91, and not modal
        Does not support repeat-on-move-till-G80 (modal repeat drill)
        Does not support L
        Needs a Z-start position
        Q is peck amount, a distance not position
        R is a position
            R must always be above surface: initial move is a G0
        Z is a position
        P is dwell
        chip-break is a position (R), or chipbreaking_amount|5% for G73
        peck-return-to-bottom-clearance (fast-move) is hard-coded delta.
        """
        cmd_name = command.Name.upper()

        # Required parameters
        missing_axis = [
            a for a in "XYZ" if a not in command.Parameters or command.Parameters[a] is None
        ]
        if missing_axis:
            # should be an internal error only
            raise Exception(
                f"Drill-cycle-expand requires X,Y & Z axis: {command} saw {missing_axis}"
            )
        missing_param = [
            p for p in "RF" if p not in command.Parameters or command.Parameters[p] is None
        ]
        if command.Name in ["G83", "G73"] and (
            "Q" not in command.Parameters or command.Parameters["Q"] is None
        ):
            missing_param.append("Q")
        if command.Name in ["G82"] and (
            "P" not in command.Parameters or command.Parameters["P"] is None
        ):
            missing_param.append("P")
        if missing_param:
            # should be an internal error only
            raise Exception(
                f"Drill-cycle-expand requires {' & '.join(missing_param)} parameter: {command}"
            )

        # DEBUG to be removed in next PR
        def bad(param, *which_commands):
            if command.Name in which_commands and param in command.Parameters:
                return param
            else:
                return None

        if b := (bad("Q", "G81", "G82") or bad("P", "G73", "G81", "G83")):
            raise Exception(f"Unexpected param {b} for {command}")

        # Extract parameters
        drill_x = command.Parameters["X"]
        drill_y = command.Parameters["Y"]
        drill_z = command.Parameters["Z"]
        retract_z = command.Parameters["R"]
        feedrate = command.Parameters["F"]

        # Store initial Z for G98 mode
        initial_z = self.current_position["Z"]

        # Determine final retract height
        if self.retract_mode == "G98":
            final_retract = max(initial_z, retract_z)
        else:  # G99
            final_retract = retract_z

        # Error check
        if retract_z < drill_z:
            # Return empty list or could raise exception
            return []

        # Preliminary moves should match the linuxcnc documentation
        # https://linuxcnc.org/docs/html/gcode/g-code.html#gcode:preliminary-motion

        expanded = []

        # Preliminary motion: If Z < R, move Z to R once (LinuxCNC spec)
        if self.current_position["Z"] < retract_z:
            expanded.append(
                Path.Command(
                    "G0",
                    {
                        "X": self.current_position["X"],
                        "Y": self.current_position["Y"],
                        "Z": retract_z,
                    },
                )
            )
            self.current_position["Z"] = retract_z

        # Move to XY position at current Z height (which should be R)
        if drill_x != self.current_position.get("X", None) or drill_y != self.current_position.get(
            "Y", None
        ):
            expanded.append(
                Path.Command("G0", {"X": drill_x, "Y": drill_y, "Z": self.current_position["Z"]})
            )
            self.current_position["X"] = drill_x
            self.current_position["Y"] = drill_y

        # Ensure Z is at R position (might already be there from preliminary motion)
        if self.current_position["Z"] != retract_z:
            expanded.append(
                Path.Command(
                    "G0",
                    {
                        "X": self.current_position["X"],
                        "Y": self.current_position["Y"],
                        "Z": retract_z,
                    },
                )
            )
            self.current_position["Z"] = retract_z

        # Perform the drilling operation
        if cmd_name in ("G81", "G82"):
            expanded.extend(self._expand_g81_g82(command, drill_z, final_retract, feedrate))
        elif cmd_name in ("G73", "G83"):
            expanded.extend(
                self._expand_g73_g83(command, drill_z, retract_z, final_retract, feedrate)
            )

        return expanded

    def _expand_g81_g82(
        self,
        command: Path.Command,
        drill_z: float,
        final_retract: float,
        feedrate: Optional[float],
    ) -> List[Path.Command]:
        """Expand G81 (simple drill) or G82 (drill with dwell)."""
        expanded = []

        cmd_name = command.Name
        params = command.Parameters

        # Feed to depth
        move_params = {
            "X": self.current_position["X"],
            "Y": self.current_position["Y"],
            "Z": drill_z,
        }
        if feedrate:
            move_params["F"] = feedrate
        expanded.append(Path.Command("G1", move_params))
        self.current_position["Z"] = drill_z

        # Dwell for G82
        if cmd_name == "G82" and "P" in params:
            expanded.append(Path.Command("G4", {"P": params["P"]}))

        # Retract
        expanded.append(
            Path.Command(
                "G0",
                {
                    "X": self.current_position["X"],
                    "Y": self.current_position["Y"],
                    "Z": final_retract,
                },
            )
        )
        self.current_position["Z"] = final_retract

        return expanded

    def _expand_g73_g83(
        self,
        command: Path.Command,
        drill_z: float,
        retract_z: float,
        final_retract: float,
        feedrate: Optional[float],
    ) -> List[Path.Command]:
        """Expand G73 (chip breaking) or G83 (peck drilling)."""
        expanded = []

        cmd_name = command.Name
        params = command.Parameters

        peck_depth = params.get("Q", abs(drill_z - retract_z))  # G81/G82 have no Q
        current_depth = retract_z
        # for G73, Explicit or Small clearance amount
        clearance = (
            (current_depth + self.chipbreaking_amount)
            if self.chipbreaking_amount is not None
            else (peck_depth * 0.05)
        )

        while current_depth > drill_z:
            # Calculate next peck depth
            next_depth = max(current_depth - peck_depth, drill_z)

            # If not first peck, rapid to clearance above previous depth
            if current_depth != retract_z and cmd_name == "G83":
                clearance_depth = current_depth + clearance
                expanded.append(
                    Path.Command(
                        "G0",
                        {
                            "X": self.current_position["X"],
                            "Y": self.current_position["Y"],
                            "Z": clearance_depth,
                        },
                    )
                )

            # Feed to next depth
            move_params = {
                "X": self.current_position["X"],
                "Y": self.current_position["Y"],
                "Z": next_depth,
            }
            if feedrate:
                move_params["F"] = feedrate
            expanded.append(Path.Command("G1", move_params))
            self.current_position["Z"] = next_depth

            # Retract based on cycle type
            if cmd_name == "G73":
                if next_depth == drill_z:  # FIXME: should be covered by final retract after if/else
                    # Final peck - retract to R
                    expanded.append(
                        Path.Command(
                            "G0",
                            {
                                "X": self.current_position["X"],
                                "Y": self.current_position["Y"],
                                "Z": retract_z,
                            },
                        )
                    )
                else:
                    # Chip breaking - small retract
                    chip_break_height = next_depth + clearance
                    expanded.append(
                        Path.Command(
                            "G0",
                            {
                                "X": self.current_position["X"],
                                "Y": self.current_position["Y"],
                                "Z": chip_break_height,
                            },
                        )
                    )
            elif cmd_name == "G83":
                # Full retract to R plane
                expanded.append(
                    Path.Command(
                        "G0",
                        {
                            "X": self.current_position["X"],
                            "Y": self.current_position["Y"],
                            "Z": retract_z,
                        },
                    )
                )

            current_depth = next_depth

        # Final retract
        if self.current_position["Z"] != final_retract:
            expanded.append(
                Path.Command(
                    "G0",
                    {
                        "X": self.current_position["X"],
                        "Y": self.current_position["Y"],
                        "Z": final_retract,
                    },
                )
            )
            self.current_position["Z"] = final_retract

        return expanded

    def _update_position(self, cmd: Path.Command) -> None:
        """
        Update the current position based on a movement command.

        Args:
            cmd: The command to update position from
        """
        if "X" in cmd.Parameters:
            self.current_position["X"] = cmd.Parameters["X"]
        if "Y" in cmd.Parameters:
            self.current_position["Y"] = cmd.Parameters["Y"]
        if "Z" in cmd.Parameters:
            self.current_position["Z"] = cmd.Parameters["Z"]

    def expand_commands(self, commands: List[Path.Command]) -> List[Path.Command]:
        """
        Expand a list of Path.Command objects.

        Args:
            commands: List of Path.Command objects

        Returns:
            List of expanded Path.Command objects
        """
        expanded = []
        for cmd in commands:
            expanded.extend(self.expand_command(cmd))
        return expanded

    def expand_path(self, path: Path.Path) -> Path.Path:
        """
        Expand drill cycles in a Path object.

        Args:
            path: Path.Path object containing commands

        Returns:
            New Path.Path object with expanded commands
        """
        expanded_commands = self.expand_commands(path.Commands)
        return Path.Path(expanded_commands)

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
from Path.Base.MachineState import MachineState
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
        machine_state: MachineState,  # we mutate
        chipbreaking_amount: None | float = None,  # only G73, default 5%, a distance
    ):
        """
        Initialize the expander.

        Args:
            MachineState, including ReturnMode (G98/G99), and required initial axis XYZ, and F and G0F
        """
        self.machine_state = machine_state
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
        if cmd_name in ["G98", "G99"]:
            self.machine_state.addCommand(command)
            return []  # Filter out after processing
        elif cmd_name == "G90":
            return []  # Filter out after processing
        elif cmd_name == "G80":
            # Cancel drill cycle - filter out since cycles are already expanded
            return []

        # Handle drill cycles
        if cmd_name in self.EXPANDABLE_CYCLES:
            try:
                result = self._expand_drill_cycle(command)
            except Exception as e:
                raise Exception(f"During {command}") from e

            Path.Log.debug(f"Expanded drill cycle: {command} -> {result}")
            return result

        # Update position for non-drill commands
        self.machine_state.addCommand(command)

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

        missing_state = [
            a for a in ("Z", "ReturnMode", "G0F") if getattr(self.machine_state, a) is None
        ]
        if missing_state:
            # should be an internal error only
            raise Exception(
                f"Drill-cycle-expand.machine_state (starting state) requires Z, G0F, and ReturnMode: {command}, {self.machine_state} missing {missing_state}"
            )

        missing_axis = [
            a for a in "XYZ" if a not in command.Parameters or command.Parameters[a] is None
        ]
        if missing_axis:
            # should be an internal error only
            raise Exception(
                f"Drill-cycle-expand requires X,Y & Z axis: {command}, missing {missing_axis}"
            )
        missing_param = [p for p in "RF" if command.Parameters.get(p, None) is None]
        if command.Name in ["G83", "G73"] and command.Parameters.get("Q", None) is None:
            missing_param.append("Q")
        if command.Name in ["G82"] and command.Parameters.get("P", None) is None:
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

        # Store initial Z for G98 (Z-return) mode
        initial_z = self.machine_state.Z

        # Determine final retract height
        if self.machine_state.ReturnMode == "Z":
            final_retract = max(initial_z, retract_z)
        else:  # G99 (R)
            final_retract = retract_z

        # Error check
        if retract_z < drill_z:
            # Return empty list or could raise exception
            return []

        # Preliminary moves should match the linuxcnc documentation
        # https://linuxcnc.org/docs/html/gcode/g-code.html#gcode:preliminary-motion

        expanded = []

        # Preliminary motion: If Z < R, move Z to R once (LinuxCNC spec)
        if self.machine_state.Z < retract_z:
            prelim = Path.Command(
                "G0",
                {
                    "X": self.machine_state.X,
                    "Y": self.machine_state.Y,
                    "Z": retract_z,
                    "F": self.machine_state.G0F,
                },
            )
            expanded.append(prelim)
            self.machine_state.addCommand(prelim)

        # Move to XY position at current Z height (which should be R)
        if drill_x != self.machine_state.X or drill_y != self.machine_state.Y:
            prelim = Path.Command(
                "G0",
                {
                    "X": drill_x,
                    "Y": drill_y,
                    "Z": self.machine_state.Z,
                    "F": self.machine_state.G0F,
                },
            )
            expanded.append(prelim)
            self.machine_state.addCommand(prelim)

        # Ensure Z is at R position (might already be there from preliminary motion)
        if self.machine_state.Z != retract_z:
            prelim = Path.Command(
                "G0",
                {
                    "X": self.machine_state.X,
                    "Y": self.machine_state.Y,
                    "Z": retract_z,
                    "F": self.machine_state.G0F,
                },
            )
            expanded.append(prelim)
            self.machine_state.addCommand(prelim)

        # Perform the drilling operation
        # machine_state is tracked inside these two
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
            "X": self.machine_state.X,
            "Y": self.machine_state.Y,
            "Z": drill_z,
        }
        if feedrate:
            move_params["F"] = feedrate
        new_command = Path.Command("G1", move_params)
        expanded.append(new_command)
        self.machine_state.addCommand(new_command)

        # Dwell for G82
        if cmd_name == "G82" and "P" in params:
            dwell_command = Path.Command("G4", {"P": params["P"]})
            expanded.append(dwell_command)
            self.machine_state.addCommand(dwell_command)

        # Retract
        retract_command = Path.Command(
            "G0",
            {
                "X": self.machine_state.X,
                "Y": self.machine_state.Y,
                "Z": final_retract,
                "F": self.machine_state.G0F,
            },
        )
        expanded.append(retract_command)
        self.machine_state.addCommand(retract_command)

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
                down_command = Path.Command(
                    "G0",
                    {
                        "X": self.machine_state.X,
                        "Y": self.machine_state.Y,
                        "Z": clearance_depth,
                        "F": self.machine_state.G0F,
                    },
                )
                expanded.append(down_command)
                self.machine_state.addCommand(down_command)

            # Feed to next depth
            move_params = {
                "X": self.machine_state.X,
                "Y": self.machine_state.Y,
                "Z": next_depth,
            }
            if feedrate:
                move_params["F"] = feedrate
            feed_command = Path.Command("G1", move_params)
            expanded.append(feed_command)
            self.machine_state.addCommand(feed_command)

            # Retract based on cycle type
            if cmd_name == "G73":
                if next_depth == drill_z:  # should be covered by final retract after if/else
                    # Final peck - retract to R
                    retract_command = Path.Command(
                        "G0",
                        {
                            "X": self.machine_state.X,
                            "Y": self.machine_state.Y,
                            "Z": retract_z,
                            "F": self.machine_state.G0F,
                        },
                    )
                    expanded.append(retract_command)
                    self.machine_state.addCommand(retract_command)
                else:
                    # Chip breaking - small retract
                    chip_break_height = next_depth + clearance
                    chip_command = Path.Command(
                        "G0",
                        {
                            "X": self.machine_state.X,
                            "Y": self.machine_state.Y,
                            "Z": chip_break_height,
                            "F": self.machine_state.G0F,
                        },
                    )
                    expanded.append(chip_command)
                    self.machine_state.addCommand(chip_command)

            elif cmd_name == "G83":
                # Full retract to R plane
                retract_command = Path.Command(
                    "G0",
                    {
                        "X": self.machine_state.X,
                        "Y": self.machine_state.Y,
                        "Z": retract_z,
                        "F": self.machine_state.G0F,
                    },
                )
                expanded.append(retract_command)
                self.machine_state.addCommand(retract_command)

            current_depth = next_depth

        # Final retract
        if self.machine_state.Z != final_retract:
            final_command = Path.Command(
                "G0",
                {
                    "X": self.machine_state.X,
                    "Y": self.machine_state.Y,
                    "Z": final_retract,
                    "F": self.machine_state.G0F,
                },
            )
            expanded.append(final_command)
            self.machine_state.addCommand(final_command)

        return expanded

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

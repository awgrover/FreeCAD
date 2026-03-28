# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2206 awgrover <awgrover@gmail.com>                      *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import unittest

import FreeCAD
import Path
from Path.Post.UtilsParse import drill_translate, drill_translate_gcode
from Path.Post.UtilsParse import CAMParameterRequiredError, CAMValueError

from CAMTests.PathTestUtils import PathTestBase


class TestDrillTranslate(PathTestBase):
    def setUp(self):
        #self.doc = FreeCAD.newDocument("TestPathUtils")
        pass

    def tearDown(self):
        #FreeCAD.closeDocument("TestPathUtils")
        pass

    def assertAtLeastPathCommandIn(self, p1, p2_list, msg=None):
        """The p1.Parameters should also be in a p2 and match.
        And if p1.Name is not "", it should match that p2
        """
        # FIXME: should we put this in PathTestUtils.py?
        
        for p2 in p2_list:
            if p1.Name == "" or p1.Name == p2.Name:
                fail = False
                for k,v in p1.Parameters.items():
                    if k not in p2.Parameters or v != p2.Parameters[k]:
                        fail = True
                        break
                if not fail:
                    return
        self.assertIn( p1, p2_list, msg)

    def test_arg_check(self):
        """...."""
        command = Path.Command()
        command.setFromGCode("G81 X10.0 Y10.0 R9.0 Z0 L2")

        motion = "G90"
        modal_state = {}
        retract = "" # bad

        with self.assertRaises(CAMValueError) as cm:
            result = drill_translate(command, motion, modal_state, retract)
        self.assertIn("expects a drill_retract_mode", str(cm.exception))

        retract = "G98"
        modal_state = {"F":100, "Z":0}
        command.setFromGCode("G81 X10.0 Y10.0 R4.0 Z5")
        with self.assertRaises(CAMValueError) as cm:
            result = drill_translate(command, motion, modal_state, retract)
        self.assertIn("R >= Z", str(cm.exception))

    def test_drill_doesnt_translate(self):
        """just returns un-handled gcodes"""
        command = Path.Command()
        command.setFromGCode("G1 X10.0 Y10.0")

        motion = "G90"
        modal_state = {}
        retract = "G98"

        result = [x.toGCode() for x in drill_translate(command, motion, modal_state, retract)]
        lines = "\n".join(result)

        self.assertIn( "G1 X10", lines ) # enough to id the line
        self.assertEqual( len(result), 1 )

    def test_to_absolute(self):
        """...."""
        command = Path.Command()
        command.setFromGCode("G81 X10.0 Y10.0 F100 R9.0 Z2")

        motion = "G91" # relative
        modal_state = {"X":0,"Y":0,"Z":10}
        retract = "G98"

        result = [x.toGCode() for x in drill_translate(command, motion, modal_state, retract)]

        self.assertIn( "G90", result ) # enough to id the line
        self.assertTrue( len(result) > 1, "Expected it to expand!" )

    def test_drill_translate81(self):
        """Test code paths for G81, compare with previous string-mode drill_translate output"""
        # try to excercise all code-paths
        for motion in ["G90", "G91"]:
            for retract in ["G98", "G99"]:
                command = Path.Command()
                command.setFromGCode("G81 X10.0 Y10.0 Z0 F100 R9.0")

                modal_state = {"Z":20} # needs Z for initial move
                if motion == "G91":
                    modal_state.update( {"X":0, "Y":0})

                gcode_style, legacy = self.legacy_drill_translate( command, modal_state=modal_state, retract=retract, motion_mode=motion )
                print(f"##tup {legacy}")
                eol="\n"
                print(f"##tup legacy===\n{eol.join([x.toGCode() for x in legacy]) }\n===")

                result = drill_translate(command, motion, modal_state, retract)
                as_strings = [x.toGCode() for x in result]
                lines = "\n".join(as_strings)

                self.maxDiff = None
                # Using toGCode() (string) to compare
                self.assertEqual(
                    lines,
                    # FIXME: previous drill_translate did not reset G91!
                    "\n".join([x.toGCode() for x in legacy]) + ("\nG91" if motion == "G91" else ""),
                    f"For mode {motion}, retract {retract}"
                )

    def test_drill_translate82(self):
        """Test code paths for G82, compare with previous string-mode drill_translate output"""
        for motion in ["G90", "G91"]:
            for retract in ["G98", "G99"]:
                print(f"#tup G82 mode {motion}, retract {retract}" )

                command = Path.Command()
                command.setFromGCode("G82 X10.0 Y10.0 Z0 F100 R9.0 P4")

                modal_state = {"Z":20} # needs Z for initial move
                if motion == "G91":
                    modal_state.update( {"X":0, "Y":0})

                gcode_style, legacy = self.legacy_drill_translate( command, modal_state=modal_state, retract=retract, motion_mode=motion )
                print(f"##tup {legacy}")
                eol="\n"
                print(f"##tup legacy===\n{eol.join([x.toGCode() for x in legacy]) }\n===")

                result = drill_translate(command, motion, modal_state, retract)
                as_strings = [x.toGCode() for x in result]
                lines = "\n".join(as_strings)

                self.maxDiff = None
                self.assertEqual(
                    lines,
                    # FIXME: previous drill_translate did not reset G91!
                    "\n".join([x.toGCode() for x in legacy]) + ("\nG91" if motion == "G91" else ""),
                    f"For mode {motion}, retract {retract}"
                )

    def legacy_drill_translate(self, command, motion_mode="G90", retract="G98", modal_state={}, chipbreaking_amount=None):
        # for comparison during development: DEBUG
        # returns [ Path.Commands ]

        from Path.Post.UtilsParse import drill_translate_legacy

        def gtop(gcode_str):
            p = Path.Command()
            p.setFromGCode(gcode_str)
            return p

        mock_values = {
            "MOTION_MODE": motion_mode,
            "COMMAND_SPACE": " ",
            "UNIT_FORMAT": "mm",
            "UNIT_SPEED_FORMAT": "mm/s",
            "AXIS_PRECISION": 3,
            "FEED_PRECISION": 3,
            "OUTPUT_LINE_NUMBERS": False,
            "COMMENT_SYMBOL" : "(",
            "CHIPBREAKING_AMOUNT" : chipbreaking_amount,
        }
        mock_modal_state = {  # self._modal_state, # FIXME: not being tracked
            "Z": 0,
            "X": 0,
            "Y": 0,
            "Z": 0,
            "F": 1000,
        }
        mock_modal_state.update( modal_state )

        params = command.Parameters

        gcode_str_list = []
        print(f"#t call str style w/ command {command} -> {command.Name} {command.Parameters}")
        drill_translate_gcode(
            mock_values,
            gcode_str_list,
            command.Name,
            params,
            motion_location = mock_modal_state,
            drill_retract_mode = retract,
        )
        commands_str = [gtop(g) for g in gcode_str_list]

        gcode_str_list = []
        print(f"#t call legacy w/ command {command} -> {command.Name} {command.Parameters}")
        drill_translate_legacy(
            mock_values,
            gcode_str_list,
            command.Name,
            params,
            motion_location = mock_modal_state,
            drill_retract_mode = retract,
        )
        commands_legacy = [gtop(g) for g in gcode_str_list]

        return commands_str, commands_legacy

        return commands_str, commands_legacy

    def test_drill_translate83(self):
        """Test code paths for G83, compare with previous string-mode drill_translate output"""
        # try to excercise all code-paths
        for motion in ["G90", "G91"]:
            for retract in ["G98", "G99"]:
                print(f"#tup G83 mode {motion}, retract {retract}" )
                command = Path.Command()
                command.setFromGCode("G83 X10.0 Y10.0 Z0 F100 R9.0 Q4")

                modal_state = {"Z":20} # needs Z for initial move
                if motion == "G91":
                    modal_state.update( {"X":0, "Y":0})

                gcode_style, legacy = self.legacy_drill_translate( command, modal_state=modal_state, retract=retract, motion_mode=motion )
                print(f"##tup {legacy}")
                eol="\n"
                print(f"##tup legacy===\n{eol.join([x.toGCode() for x in legacy]) }\n===")

                result = drill_translate(command, motion, modal_state, retract)
                as_strings = [x.toGCode() for x in result]
                lines = "\n".join(as_strings)

                self.maxDiff = None
                # FIXME: Path.Command doesn't implement .__eq__? I got failures when the .Name and .Parameters where the same
                # Using toGCode() (string) to compare
                self.assertEqual( 
                    lines, 
                    # FIXME: previous drill_translate did not reset G91!
                    "\n".join([x.toGCode() for x in legacy]) + ("\nG91" if motion == "G91" else ""), 
                    f"For legacy, mode {motion}, retract {retract}" 
                )

                # We also check that the string-gcode version gives the same result
                self.assertEqual( 
                    lines, 
                    "\n".join([x.toGCode() for x in gcode_style]),
                    f"For _gcode, mode {motion}, retract {retract}" 
                )


    def test_drill_translate73(self):
        """Test code paths for G73, compare with previous string-mode drill_translate output"""
        # try to excercise all code-paths
        for motion in ["G90", "G91"]:
            for retract in ["G98", "G99"]:
                print(f"#tup G83 mode {motion}, retract {retract}" )
                command = Path.Command()
                command.setFromGCode("G73 X10.0 Y10.0 Z0 F100 R9.0 Q4")

                chipbreaking_amount = FreeCAD.Units.Quantity(2.0, FreeCAD.Units.Length) # mm
                modal_state = {"Z":20} # needs Z for initial move
                if motion == "G91":
                    modal_state.update( {"X":0, "Y":0})

                gcode_style, legacy = self.legacy_drill_translate( 
                    command, 
                    modal_state=modal_state, 
                    retract=retract, 
                    motion_mode=motion,
                    chipbreaking_amount=chipbreaking_amount
                )
                print(f"##tup {legacy}")
                eol="\n"
                print(f"##tup legacy===\n{eol.join([x.toGCode() for x in legacy]) }\n===")

                result = drill_translate(command, motion, modal_state, retract, chipbreaking_amount=chipbreaking_amount)
                as_strings = [x.toGCode() for x in result]
                lines = "\n".join(as_strings)

                self.maxDiff = None
                # FIXME: Path.Command doesn't implement .__eq__? I got failures when the .Name and .Parameters where the same
                # Using toGCode() (string) to compare
                self.assertEqual( 
                    lines, 
                    # FIXME: previous drill_translate did not reset G91!
                    "\n".join([x.toGCode() for x in legacy]) + ("\nG91" if motion == "G91" else ""), 
                    f"For mode {motion}, retract {retract}" 
                )

    @unittest.expectedFailure
    def test_todo(self):
        assertTrue(False, "todo")
        # test with linenumbers on esp. vs _gcode vs _legacy
        # eh? some kind of clipping: if drill_retract_mode == "G98" and motion_z >= retract_z: retract_z = motion_z


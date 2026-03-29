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
from Path.Post.UtilsParse import drill_translate 
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
        gcode = Path.Command()
        gcode.setFromGCode("G81 X10.0 Y10.0 R9.0 Z0 L2")

        motion = "G90"
        modal_state = {}
        retract = "" # bad

        with self.assertRaises(CAMValueError) as cm:
            result = drill_translate(gcode, motion, modal_state, retract)
        self.assertIn("expects a drill_retract_mode", str(cm.exception))

        retract = "G98"
        modal_state = {"F":100, "Z":0}
        gcode.setFromGCode("G81 X10.0 Y10.0 R4.0 Z5")
        with self.assertRaises(CAMValueError) as cm:
            result = drill_translate(gcode, motion, modal_state, retract)
        self.assertIn("R >= Z", str(cm.exception))

    def test_drill_doesnt_translate(self):
        """just returns un-handled gcodes"""
        gcode = Path.Command()
        gcode.setFromGCode("G1 X10.0 Y10.0")

        motion = "G90"
        modal_state = {}
        retract = "G98"

        result = [x.toGCode() for x in drill_translate(gcode, motion, modal_state, retract)]
        lines = "\n".join(result)

        self.assertIn( "G1 X10", lines ) # enough to id the line
        self.assertEqual( len(result), 1 )

    def test_to_absolute(self):
        """...."""
        gcode = Path.Command()
        gcode.setFromGCode("G81 X10.0 Y10.0 F100 R9.0 Z2")

        motion = "G91" # relative
        modal_state = {"X":0,"Y":0,"Z":10}
        retract = "G98"

        result = [x.toGCode() for x in drill_translate(gcode, motion, modal_state, retract)]

        self.assertIn( "G90", result ) # enough to id the line
        self.assertTrue( len(result) > 1, "Expected it to expand!" )

    def test_drill_translate81(self):
        """...."""
        gcode = Path.Command()
        gcode.setFromGCode("G81 X10.0 Y10.0 Z0 F100 R9.0")

        motion = "G90"
        modal_state = {"Z":20}
        retract = "G98"

        result = drill_translate(gcode, motion, modal_state, retract)
        as_strings = [x.toGCode() for x in result]
        lines = "\n".join(as_strings)

        # at least these
        self.assertAtLeastPathCommandIn( Path.Command("G0", {"X":10}), result )
        self.assertAtLeastPathCommandIn( Path.Command("G1", {"Z":0}), result )
        self.assertNotIn( "G4 ", lines)
        self.assertTrue( len(result) > 1, "Expected it to expand!" )

    def test_drill_translate82(self):
        """...."""
        gcode = Path.Command()
        gcode.setFromGCode("G82 X10.0 Y10.0 Z0 F100 R9.0 P4")

        motion = "G90"
        modal_state = {"Z":20}
        retract = "G98"

        result = drill_translate(gcode, motion, modal_state, retract)
        as_strings = [x.toGCode() for x in result]
        lines = "\n".join(as_strings)

        # at least these
        self.assertAtLeastPathCommandIn( Path.Command("G0", {"X":10}), result )
        self.assertAtLeastPathCommandIn( Path.Command("G1", {"Z":0}), result )
        self.assertAtLeastPathCommandIn( Path.Command("G4",{"P":4}), result )

    def test_drill_translate83(self):
        """...."""
        gcode = Path.Command()
        gcode.setFromGCode("G83 X10.0 Y10.0 Z0 F100 R9.0 Q4")

        motion = "G90"
        modal_state = {"Z":20}
        retract = "G98"

        result = drill_translate(gcode, motion, modal_state, retract)
        as_strings = [x.toGCode() for x in result]
        lines = "\n".join(as_strings)

        # at least these
        self.assertAtLeastPathCommandIn( Path.Command("G0", {"X":10}), result )
        self.assertAtLeastPathCommandIn( Path.Command("G1", {"Z":0}), result )

    @unittest.expectedFailure
    def test_todo(self):
        assertTrue(False, "todo")
        # test retract g98 (z) vs g99 (r)
        # eh? some kind of clipping: if drill_retract_mode == "G98" and motion_z >= retract_z: retract_z = motion_z


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

import FreeCAD
import Path
from Path.Post.UtilsParse import drill_translate 

from CAMTests.PathTestUtils import PathTestBase


class TestPathUtilsParse(PathTestBase):
    def setUp(self):
        #self.doc = FreeCAD.newDocument("TestPathUtils")
        pass

    def tearDown(self):
        #FreeCAD.closeDocument("TestPathUtils")
        pass

    def test_drill_translate(self):
        """...."""
        gcode = Path.Command()
        gcode.setFromGCode("G81 X10.0 Y10.0 R9.0 Z0 L2")

        modal_state = {}
        retract = None

        result = [Path.toGCode(x) for x in drill_translate(gcode, modal_state, retract)]
        print(f"#TT rez {result}")

        self.assertEqual( result, [] )

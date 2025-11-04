# -*- coding: utf-8 -*-
# ***************************************************************************
# *   Copyright (c) 2022 sliptonic <shopinthewoods@gmail.com>               *
# *   Copyright (c) 2023 Larry Woestman <LarryWoestman2@gmail.com>          *
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
import CAMTests.PathTestUtils as PathTestUtils
from importlib import reload
from Path.Post.scripts import opensbp_post as postprocessor

Path.Log.setLevel(Path.Log.Level.DEBUG, Path.Log.thisModule())
Path.Log.trackModule(Path.Log.thisModule())


class TestOpenSBPPost(PathTestUtils.PathTestBase):
    """NB: the post-processor has globals, 
        which are not reset for each .assertX,
        e.g. for the arguments.
        So, you have to deal with state, e.g. --inches is persistent till the next testX()
    """

    @classmethod
    def setUpClass(cls):
        """setUpClass()...
        This method is called upon instantiation of this test class.  Add code
        and objects here that are needed for the duration of the test() methods
        in this class.  In other words, set up the 'global' test environment
        here; use the `setUp()` method to set up a 'local' test environment.
        This method does not have access to the class `self` reference, but it
        is able to call static methods within this same class.
        """

        # Open existing FreeCAD document with test geometry
        FreeCAD.newDocument("Unnamed")

    @classmethod
    def tearDownClass(cls):
        """tearDownClass()...
        This method is called prior to destruction of this test class.  Add
        code and objects here that cleanup the test environment after the
        test() methods in this class have been executed.  This method does
        not have access to the class `self` reference.  This method is able
        to call static methods within this same class.
        """
        # Close geometry document without saving
        FreeCAD.closeDocument(FreeCAD.ActiveDocument.Name)

    # Setup and tear down methods called before and after each unit test
    def setUp(self):
        """setUp()...
        This method is called prior to each `test()` method.  Add code and
        objects here that are needed for multiple `test()` methods.
        """
        self.doc = FreeCAD.ActiveDocument
        self.con = FreeCAD.Console
        self.docobj = FreeCAD.ActiveDocument.addObject("Path::Feature", "testpath")
        reload(
            postprocessor
        )  # technical debt.  This shouldn't be necessary but here to bypass a bug

    def tearDown(self):
        """tearDown()...
        This method is called after each test() method. Add cleanup instructions here.
        Such cleanup instructions will likely undo those in the setUp() method.
        """
        FreeCAD.ActiveDocument.removeObject("testpath")

    def compare_first_command(self, path_string, expected, args, debug=False):
        """Perform a test with a single comparison to the first (command) line of the output."""
        nl = "\n"
        if path_string:
            self.docobj.Path = Path.Path([Path.Command(path_string)])
        else:
            self.docobj.Path = Path.Path([])

        # opensbp is terse, no header/preamble/comments, so 1st line is 1st command
        first_command = 0

        postables = [self.docobj]
        gcode = postprocessor.export(postables, "-", args)
        if debug:
            print(f"--------{nl}{gcode}--------{nl}")

        if expected==None:
            self.assertEqual(gcode, "")
        else:
            lines = gcode.splitlines()
            self.assertGreater( len(lines), first_command ) # need at least first_command+1 lines
            self.assertEqual(lines[first_command], expected)

    def test000(self):
        """Test Output Generation.
        Empty path.  Produces only the preamble and postable.
        """

        self.docobj.Path = Path.Path([])
        postables = [self.docobj]

        # Test generating with header
        # Header contains a time stamp that messes up unit testing.
        # Only test length of result.
        args = "--no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        # has .export been upgraded to return the gcode?
        self.assertNotEqual(gcode, None)
        self.assertEqual(len(gcode.splitlines()), 3)

        # Test without header
        # opensbp is terse!
        expected = ""

        self.docobj.Path = Path.Path([])
        postables = [self.docobj]

        args = "--no-header --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        self.assertEqual(gcode, expected)

        # With comments
        expected="""'(begin preamble)
'(begin operation: testpath)
'(Path: testpath)
'(finish operation: testpath)
'(begin postamble)
"""
        args = "--no-header --comments --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        self.assertEqual(gcode, expected)

    def test010(self):
        """Test command Generation.
        Test Precision
        Test imperial / inches
        """

        # default is metric-mm (internal default)
        self.compare_first_command(
            "G0 X10 Y20 Z30", # simple move
            "J3,10.0000,20.0000,30.0000",
            "--no-header --no-show-editor"
        )

        self.compare_first_command(
            "G0 X10 Y20 Z30",
            "J3,10.00,20.00,30.00",
            "--no-header --precision=2 --no-show-editor",
        )

    def test030(self):
        """
        Test Pre-amble
        """

        self.docobj.Path = Path.Path([])
        postables = [self.docobj]

        expected="""JZ,50.0000
MX,20.0000
"""
        args = "--no-header --preamble='G0 Z50\nG1 X20' --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        self.assertEqual(gcode, expected)

    def test040(self):
        """
        Test Post-amble
        """
        self.docobj.Path = Path.Path([])
        postables = [self.docobj]

        expected="""JZ,55.0000
MX,22.0000
"""
        args = "--no-header --postamble='G0 Z55\nG1 X22' --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        self.assertEqual(gcode, expected)

    def test050(self):
        """
        Test inches
        """

        # inches
        self.compare_first_command(
            "G0 X10 Y20 Z30", # simple move
            "J3,0.3937,0.7874,1.1811",
            "--no-header --no-show-editor --inches"
        )
        self.compare_first_command(
            "G0 X10 Y20 Z30", # simple move
            "J3,0.39,0.79,1.18",
            "--no-header --no-show-editor --inches --precision 2"
        )

    def test060(self):
        """
        Test test modal
        Suppress the command name if the same as previous
        """
        c = Path.Command("G0 X10 Y20 Z30")
        c1 = Path.Command("G0 X10 Y30 Z30")

        self.docobj.Path = Path.Path([c, c1])
        postables = [self.docobj]

        args = "--no-header --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        expected = "J3,10.0000,20.0000,30.0000"
        self.assertEqual(gcode, expected)

    def test070(self):
        """
        Suppress the axis coordinate if the same as previous
        """
        # diff y
        c = Path.Command("G0 X10 Y20 Z30")
        c1 = Path.Command("G0 X10 Y30 Z30")

        self.docobj.Path = Path.Path([c, c1])
        postables = [self.docobj]

        args = "--no-header --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        expected = """J3,10.0000,20.0000,30.0000
JY,30.0000
"""
        self.assertEqual(gcode, expected)

        # diff z
        c1 = Path.Command("G0 X10 Y20 Z40")

        self.docobj.Path = Path.Path([c, c1])
        postables = [self.docobj]

        args = "--no-header --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        expected = """J3,10.0000,20.0000,30.0000
JZ,40.0000
"""
        self.assertEqual(gcode, expected)

    def test080(self):
        """
        Test tool change
        """
        c = Path.Command("M6 T2")
        c2 = Path.Command("M3 S3000")
        self.docobj.Path = Path.Path([c, c2])
        postables = [self.docobj]

        args = "--no-header --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        expect="""&ToolName=2
&Tool=2
'Change tool to 2
PAUSE
TR,3000
'Change spindle speed to 3000
PAUSE
"""
        self.assertEqual(gcode, expect)

    def test090(self):
        """
        Test comment
        """
        expected="""'(begin preamble)
'(begin operation: testpath)
'(Path: testpath)
'comment
'(finish operation: testpath)
'(begin postamble)
"""
        c = Path.Command("(comment)")
        self.docobj.Path = Path.Path([c])
        postables = [self.docobj]
        args = "--no-header --comments  --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        self.assertEqual(gcode, expected)

    def test100(self):
        """Test A, B, & C axis output for values between 0 and 90 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A40 B50",
            "M5,10.0000,20.0000,30.0000,40.0000,50.0000",
            #"G1 X10.000 Y20.000 Z30.000 A40.000 B50.000 C60.000 ",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A40 B50 C10",
            None, # we don't do C
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A40 B50",
            "M5,0.3937,0.7874,1.1811,40.0000,50.0000",
            "--no-header --inches --no-show-editor",
        )

    def test105(self):
        """Test A, B axis output for distance, not degrees"""

        # only noticeable for --inches

        self.compare_first_command(
            "G1 X10 Y20 Z30 A40 B50",
            "M5,0.3937,0.7874,1.1811,40.0000,50.0000",
            "--no-header --inches --no-show-editor",
        )

        self.compare_first_command(
            "G1 X10 Y20 Z30 A40 B50",
            "M5,0.3937,0.7874,1.1811,1.5748,1.9685",
            "--no-header --no-show-editor --inches --ab-is-distance",
        )

    def test110(self):
        """Test A, B, & C axis output for 89 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A89 B89",
            "M5,10.0000,20.0000,30.0000,89.0000,89.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A89 B89",
            "M5,0.3937,0.7874,1.1811,89.0000,89.0000",
            "--no-header --inches --no-show-editor",
        )

    # 90+ is broken

    def test120(self):
        """Test A, B axis output for 90 degrees"""

        # BREAKS:
        # parses the gcode to {'A': 0.0, 'B': 90.0, 'X': 10.0, 'Y': 20.0, 'Z': 30.0}
        # Note the A==0

        self.compare_first_command(
            "G1 X10 Y20 Z30 A90 B90",
            "M5,10.0000,20.0000,30.0000,90.0000,90.0000",
            "--no-header --no-show-editor",
            debug=True
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A90 B90",
            "M5,0.3937,0.7874,1.1811,90.0000,90.0000",
            "--no-header --inches --no-show-editor",
        )

    def test130(self):
        """Test A, B, & C axis output for 91 degrees"""

        self.compare_first_command(
            "G1 X10 Y20 Z30 A91 B91",
            "M5,10.0000,20.0000,30.0000,91.0000,91.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A91 B91 C91",
            "M5,0.3937,0.7874,1.1811,91.0000,91.0000",
            "--no-header --inches --no-show-editor",
        )

    def test140(self):
        """Test A, B, & C axis output for values between 90 and 180 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A100 B110",
            "M5,10.0000,20.0000,30.0000,100.0000,110.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A100 B110",
            "M5,0.3937,0.7874,1.1811,100.0000,110.0000",
            "--no-header --inches --no-show-editor",
        )

    def test150(self):
        """Test A, B, & C axis output for values between 180 and 360 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A240 B250",
            "M5,10.0000,20.0000,30.0000,240.0000,250.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A240 B250 C260",
            "M5,0.3937,0.7874,1.1811,240.0000,250.0000",
            "--no-header --inches --no-show-editor",
        )

    def test160(self):
        """Test A, B, & C axis output for values greater than 360 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A440 B450",
            "M5,10.0000,20.0000,30.0000,440.0000,450.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A440 B450 C460",
            "M5,0.3937,0.7874,1.1811,440.0000,450.0000",
            "--no-header --inches --no-show-editor",
        )

    def test170(self):
        """Test A, B, & C axis output for values between 0 and -90 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A-40 B-50",
            "M5,10.0000,20.0000,30.0000,-40.0000,-50.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A-40 B-50",
            "M5,0.3937,0.7874,1.1811,-40.0000,-50.0000",
            "--no-header --inches --no-show-editor",
        )

    def test180(self):
        """Test A, B, & C axis output for values between -90 and -180 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A-100 B-110",
            "M5,10.0000,20.0000,30.0000,-100.0000,-110.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A-100 B-110",
            "M5,0.3937,0.7874,1.1811,-100.0000,-110.0000",
            "--no-header --inches --no-show-editor",
        )

    def test190(self):
        """Test A, B, & C axis output for values between -180 and -360 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A-240 B-250",
            "M5,10.0000,20.0000,30.0000,-240.0000,-250.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A-240 B-250",
            "M5,0.3937,0.7874,1.1811,-240.0000,-250.0000",
            "--no-header --inches --no-show-editor",
        )

    def test200(self):
        """Test A, B, & C axis output for values below -360 degrees"""
        self.compare_first_command(
            "G1 X10 Y20 Z30 A-440 B-450",
            "M5,10.0000,20.0000,30.0000,-440.0000,-450.0000",
            "--no-header --no-show-editor",
        )
        self.compare_first_command(
            "G1 X10 Y20 Z30 A-440 B-450",
            "M5,0.3937,0.7874,1.1811,-440.0000,-450.0000",
            "--no-header --inches --no-show-editor",
        )

# -*- coding: utf-8 -*-
# ***************************************************************************
# *   Copyright (c) 2022 sliptonic <shopinthewoods@gmail.com>               *
# *   Copyright (c) 2023 Larry Woestman <LarryWoestman2@gmail.com>          *
# *   Copyright (c) 2025 Alan Grover <awgrover@gmail.com>
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

import re

import unittest
import FreeCAD
from FreeCAD import Units

import Path
from CAMTests import PathTestUtils
from importlib import reload
from Path.Post.scripts import refactored_opensbp_post as postprocessor
from Path.Post.Processor import PostProcessorFactory


Path.Log.setLevel(Path.Log.Level.DEBUG, Path.Log.thisModule())
Path.Log.trackModule(Path.Log.thisModule())


class TestRefactoredOpenSBPPost(PathTestUtils.PathTestBase):
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
        cls.doc = FreeCAD.open(FreeCAD.getHomePath() + "/Mod/CAM/CAMTests/boxtest.fcstd")
        cls.job = cls.doc.getObject("Job")

        # we only fixup the first tool-controller for feed rates
        # but we setup setupsheet which will get all the tools for rapid
        tool_controller = cls.job.Tools.Group[0]
        base_speed = 700
        if tool_controller.HorizFeed.Value == 0.0:
            tool_controller.HorizFeed = Units.Quantity(base_speed, "mm/min")
        if tool_controller.VertFeed.Value == 0.0:
            tool_controller.VertFeed = Units.Quantity(base_speed/2, "mm/min")
        setup_sheet = cls.job.SetupSheet
        if setup_sheet.HorizRapid.Value == 0.0:
            setup_sheet.HorizRapid = Units.Quantity(base_speed * 3, "mm/min")
        if setup_sheet.VertRapid.Value == 0.0:
            setup_sheet.VertRapid = Units.Quantity((base_speed *3)/2, "mm/min")
        cls.doc.recompute()
        #settings = { p:getattr(tool_controller, p) for p in ['HorizFeed','VertFeed','HorizRapid','VertRapid'] }
        #print(f"### tc setup {settings}")

        cls.post = PostProcessorFactory.get_post_processor(cls.job, "refactored_opensbp")
        for op in cls.job.Operations.Group:
            if op.Label == "Profile":
                # remember the "Profile" operation
                cls.profile_op = op
                return

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
        for name in FreeCAD.listDocuments().keys():
            FreeCAD.closeDocument(name)
        FreeCAD.ConfigSet("SuppressRecomputeRequiredDialog", "")

    # Setup and tear down methods called before and after each unit test
    def setUp(self):
        """setUp()...
        This method is called prior to each `test()` method.  Add code and
        objects here that are needed for multiple `test()` methods.
        """
        self.maxDiff = None
        self.doc.UnitSystem = 'Metric small parts & CNC (mm, mm/min)'
        #reload(
        #    postprocessor
        #)  # technical debt.  This shouldn't be necessary but here to bypass a bug

        self.post.reinitialize()

        postprocessor.UNDER_UNITTEST = True # because we don't setup a tool-controller in these tests

    def tearDown(self):
        """tearDown()...
        This method is called after each test() method. Add cleanup instructions here.
        Such cleanup instructions will likely undo those in the setUp() method.
        """
        if FreeCAD.ActiveDocument and FreeCAD.ActiveDocument.findObjects(Name="testpath"):
            FreeCAD.ActiveDocument.removeObject("testpath")

    def compare_multi(self, *args, remove=None, debug=False ):
        """Actually as if: ( *gcode, options, expected, debug=True )
        `*gcode` is all str (gcodes), or None to use extant self.job
        `remove` is a pattern to remove lines from both expected and generated
        """

        if isinstance(args[0],str):
            self.profile_op.Path = Path.Path([ Path.Command(x) for x in args[:-2]])
        post_args = args[-2]
        expected = args[-1]

        #print(f"###test multi path str {args[:-2]}")
        #print(f"###test in gcode {[p.toGCode() for p in self.profile_op.Path.Commands]}")
        self.job.PostProcessorArgs = post_args

        rez = self.post.export()
        if rez is None:
            raise Exception("Error processing arguments")
        else:
            dumy, gcode = rez[0]
        #print(f"### gcode {gcode}")

        if debug:
            nl="\n"
            print(f"--------{nl}{gcode}--------{nl}")
        if remove:
            expected = '\n'.join( (x for x in expected.split('\n') if not re.match(remove,x)) )
            gcode =    nl.join((x for x in gcode.split(nl) if not re.match(remove,x)))
        #print(f"###E---{expected}---")
        #print(f"###G---{gcode}---")
        self.assertEqual(expected, gcode) # most other tests have this reversed, and the diff reads wrong to me

    def test000(self):
        """Test Output Generation.
        Empty path.  Produces only the preamble and postable.
        """

        self.profile_op.Path = Path.Path([])

        # Test generating with header
        # Header contains a time stamp that messes up unit testing.
        self.compare_multi( None,
            "--no-show-editor",
            """'(Exported by FreeCAD)
'(Post Processor: refactored_opensbp_post)
'  --no-show-editor
'(Cam File: boxtest.fcstd)
'Job: Job
'(Begin preamble)
SA
'(Output Time: this is removed
&WASUNITS=%(25)
'Units metric
VD,,,1
'(Begin operation: Fixture)
'(Machine units: mm/min)
'(Path: Fixture)
'( G54 )
'(Finish operation: Fixture)
'(Begin operation: TC: Default Tool)
'(Machine units: mm/min)
'(Path: TC: Default Tool)
'(TC: Default Tool)
'(Begin toolchange)
&Tool=1
'Change tool to #1: TC: Default Tool, Endmill
PAUSE
&ToolName="TC Default Tool Endmill"
'set speeds: TC: Default Tool
MS,700.000,700.000,350.000
JS,2100.000,2100.000,1050.000
'(Finish operation: TC: Default Tool)
'(Begin operation: Profile)
'(Machine units: mm/min)
'(Path: Profile)
'(Finish operation: Profile)
'(Begin postamble)
VD,,,&WASUNITS
""",
        remove=r"'\(Output Time:",
        debug=True
        )

        # Test without header

        self.compare_multi( None,
            "--no-header --no-comments --no-show-editor",
            """SA
&WASUNITS=%(25)
VD,,,1
&Tool=1
'Change tool to #1: TC: Default Tool, Endmill
PAUSE
&ToolName="TC Default Tool Endmill"
MS,700.000,700.000,350.000
JS,2100.000,2100.000,1050.000
VD,,,&WASUNITS
"""
        )

    def wrap(self, expected):
        # wraps in std prefix, postfix
        return f"""SA
&WASUNITS=%(25)
VD,,,1
&Tool=1
'Change tool to #1: TC: Default Tool, Endmill
PAUSE
&ToolName="TC Default Tool Endmill"
MS,700.000,700.000,350.000
JS,2100.000,2100.000,1050.000
{expected.rstrip()}
VD,,,&WASUNITS
"""

    def test010(self):
        """Test command Generation.
        Test Precision
        Test imperial / inches
        """

        # default is metric-mm (internal default)
        self.compare_multi(
            "G0 X10 Y20 Z30", # simple rapid
            "--no-header --no-comments --no-show-editor --metric --no-abort-on-unknown",
            self.wrap("""JS,561.249,1122.497,0.000,0.000 FIXME XY is together, z separate
J3,10.000,20.000,30.000
"""),
        )

        self.compare_multi(
            "G0 X10 Y20 Z30",
            "--no-header --no-comments --precision=2 --no-show-editor",
            self.wrap("""JS,561.25,1122.50,841.87,0.00,0.00
J3,10.00,20.00,30.00
"""),
        )

        self.compare_multi(
            "G0 X10 Y20 Z30",
            "--no-header --no-comments --inches --no-show-editor",
            """&WASUNITS=%(25)
VD,,,0
J3,0.3937,0.7874,1.1811
VD,,,&WASUNITS
""",
        )
        self.compare_multi(
            "G0 X10 Y20 Z30",
            "--no-header --no-comments --inches --precision=2 --no-show-editor",
            """&WASUNITS=%(25)
VD,,,0
J3,0.39,0.79,1.18
VD,,,&WASUNITS
"""
        )

        # override as --metric
        self.compare_multi(
            "G0 X10 Y20 Z30",
            "--no-header --no-comments --metric --precision=3 --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
J3,10.000,20.000,30.000
VD,,,&WASUNITS
"""
        )

    def test030(self):
        """
        Test Pre-amble
        """

        self.job.Path = Path.Path([])
        postables = [self.job]

        expected="""&WASUNITS=%(25)
VD,,,1
JZ,50.000
MX,20.000
VD,,,&WASUNITS
"""
        args = "--no-header --no-comments --preamble='G0 Z50\nG1 X20' --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        self.assertEqual(gcode, expected)

    def test040(self):
        """
        Test Post-amble
        """
        self.job.Path = Path.Path([])
        postables = [self.job]

        expected="""&WASUNITS=%(25)
VD,,,1
JZ,55.000
MX,22.000
VD,,,&WASUNITS
"""
        args = "--no-header --no-comments --postamble='G0 Z55\nG1 X22' --no-show-editor"
        gcode = postprocessor.export(postables, "-", args)
        self.assertEqual(gcode, expected)

    def test050(self):
        """
        Test inches
        """

        # inches
        self.compare_multi(
            "G0 X10 Y20 Z30", # simple move
            "--no-header --no-comments --no-show-editor --inches",
            """&WASUNITS=%(25)
VD,,,0
J3,0.3937,0.7874,1.1811
VD,,,&WASUNITS
"""
        )
        self.compare_multi(
            "G0 X10 Y20 Z30", # simple move
            "--no-header --no-comments --no-show-editor --inches --precision 2",
            """&WASUNITS=%(25)
VD,,,0
J3,0.39,0.79,1.18
VD,,,&WASUNITS
"""
        )

    def test060(self):
        """
        Test test modal
        Suppress the command name if the same as previous
        """
        c = "G0 X10 Y20 Z30"

        self.compare_multi( c, c,
            "--no-header --no-comments --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
J3,10.000,20.000,30.000
J3,10.000,20.000,30.000
VD,,,&WASUNITS
"""
        )
        self.compare_multi( c, c,
            "--no-header --no-comments --modal --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
J3,10.000,20.000,30.000
VD,,,&WASUNITS
"""
        )

    def test070(self):
        """
        Suppress the axis coordinate if the same as previous
        """

        # w/o axis-modal
        c="G0 X10 Y20 Z30"
        self.compare_multi( c, "G0 X10 Y30 Z30",
            "--no-header --no-comments --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
J3,10.000,20.000,30.000
J3,10.000,30.000,30.000
VD,,,&WASUNITS
"""
        )

        # diff y
        self.compare_multi( 
            c, 
            # absolute xy same
            "G0 X10 Y30 Z30", 
            # relative, xy same
            "G91", "G0 X0 Y31 Z0",
            "--no-header --no-comments --axis-modal --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
J3,10.000,20.000,30.000
JY,30.000
SR 'RELATIVE
JY,31.000
VD,,,&WASUNITS
"""
        )

        # diff z
        self.compare_multi( c, "G0 X10 Y20 Z40",
            "--no-header --no-comments --axis-modal --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
J3,10.000,20.000,30.000
JZ,40.000
VD,,,&WASUNITS
"""
        )

    def test080(self):
        """
        Test tool change, and spindle
        """

        # both tool and spindle: manual
        gcode_in = [ "M6 T2", "M3 S3000", "M6 T3" ]
        self.compare_multi( *gcode_in,
            "--no-header --no-comments --comments --no-show-editor",
            """'(use default machine units (document units were metric))
&WASUNITS=%(25)
VD,,,1
'(begin operation: testpath)
'(Path: testpath)
'(tool change)
&Tool=2
'(First change tool, should already be #2: 2)
&ToolName="2"
TR,3000
'Change spindle speed to 3000
PAUSE
'(tool change)
&Tool=3
'Change tool to #3: 3
PAUSE
&ToolName="3"
'(finish operation: testpath)
VD,,,&WASUNITS
""",
        )

        # both tool and spindle: auto
        self.compare_multi( *gcode_in,
            "--toolchanger --no-comments --spindle-controller --no-header --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
&Tool=2
C9 'toolchanger
&ToolName="2"
TR,3000
C6 'spindle-controller
PAUSE 3
&Tool=3
C9 'toolchanger
&ToolName="3"
VD,,,&WASUNITS
"""
        )
        # auto-spindle with wait
        self.compare_multi( *gcode_in,
            "--toolchanger --no-comments --spindle-controller --wait-for-spindle 2 --no-header --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
&Tool=2
C9 'toolchanger
&ToolName="2"
TR,3000
C6 'spindle-controller
PAUSE 2
&Tool=3
C9 'toolchanger
&ToolName="3"
VD,,,&WASUNITS
"""
        )

    
    def test090(self):
        """
        Test comment
        """

        # we've always been no-comments default
        self.compare_multi( "(comment)",
            "--no-header --no-comments --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
VD,,,&WASUNITS
"""
        )

        self.compare_multi( "(comment)",
            "--no-header --no-comments --comments --no-show-editor",
            """'(use default machine units (document units were metric))
&WASUNITS=%(25)
VD,,,1
'(begin operation: testpath)
'(Path: testpath)
'comment
'(finish operation: testpath)
VD,,,&WASUNITS
"""
        )

        self.compare_multi( "(comment)",
            "--no-header --no-comments --no-comments --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
VD,,,&WASUNITS
"""
        )

    def test100(self):
        """Test A, B axis output for values between 0 and 90 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A40 B50",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,40.000,50.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A40 B50",
            "--no-header --no-comments --inches --no-show-editor",
            """&WASUNITS=%(25)
VD,,,0
M5,0.3937,0.7874,1.1811,40.0000,50.0000
VD,,,&WASUNITS
"""
        )

    def test105(self):
        """Test A, B axis output for distance, not degrees"""

        # only noticeable for --inches

        self.compare_multi(
            "G1 X10 Y20 Z30 A40 B50",
            "--no-header --no-comments --inches --no-show-editor",
            """&WASUNITS=%(25)
VD,,,0
M5,0.3937,0.7874,1.1811,40.0000,50.0000
VD,,,&WASUNITS
"""
        )

        self.compare_multi(
            "G1 X10 Y20 Z30 A40 B50",
            "--no-header --no-comments --no-show-editor --inches --ab-is-distance",
            """&WASUNITS=%(25)
VD,,,0
M5,0.3937,0.7874,1.1811,1.5748,1.9685
VD,,,&WASUNITS
"""
        )

    def test110(self):
        """Test A, B, & C axis output for 89 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A89 B89",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,89.000,89.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A89 B89",
            "--no-header --no-comments --inches --no-show-editor",
            """&WASUNITS=%(25)
VD,,,0
M5,0.3937,0.7874,1.1811,89.0000,89.0000
VD,,,&WASUNITS
"""
        )

    # FIXME: the use of getPathWithPlacement() causes a yaw-pitch calculation which gives odd AB values
    # so, tests disabled
    # no-other post-procesor tests AB (except linuxcnc which does not do getPathWithPlacement())

    @unittest.expectedFailure
    def test120(self):
        """Test A, B axis output for 90 degrees"""

        # BREAKS:
        # parses the gcode to {'A': 0.0, 'B': 90.0, 'X': 10.0, 'Y': 20.0, 'Z': 30.0}
        # Note the A==0

        self.compare_multi(
            "G1 X10 Y20 Z30 A90 B90",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,90.000,90.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A90 B90",
            "--no-header --no-comments --inches --no-show-editor",
            self.wrap("M5,0.3937,0.7874,1.1811,90.0000,90.0000"),
        )

    @unittest.expectedFailure
    def test130(self):
        """Test A, B, & C axis output for 91 degrees"""

        self.compare_multi(
            "G1 X10 Y20 Z30 A91 B91",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,91.000,91.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A91 B91",
            "--no-header --no-comments --inches --no-show-editor",
            self.wrap("M5,0.3937,0.7874,1.1811,91.0000,91.0000"),
        )

    @unittest.expectedFailure
    def test140(self):
        """Test A, B, & C axis output for values between 90 and 180 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A100 B110",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,100.000,110.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A100 B110",
            "--no-header --no-comments --inches --no-show-editor",
            self.wrap("M5,0.3937,0.7874,1.1811,100.0000,110.0000"),
        )

    @unittest.expectedFailure
    def test150(self):
        """Test A, B, & C axis output for values between 180 and 360 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A240 B250",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,240.000,250.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A240 B250",
            "--no-header --no-comments --inches --no-show-editor",
            self.wrap("M5,0.3937,0.7874,1.1811,240.0000,250.0000"),
        )

    @unittest.expectedFailure
    def test160(self):
        """Test A, B, & C axis output for values greater than 360 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A440 B450",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,440.000,450.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A440 B450",
            "--no-header --no-comments --inches --no-show-editor",
            self.wrap("M5,0.3937,0.7874,1.1811,440.0000,450.0000"),
        )

    def test170(self):
        """Test A, B, & C axis output for values between 0 and -90 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A-40 B-50",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,-40.000,-50.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A-40 B-50",
            "--no-header --no-comments --inches --no-show-editor",
            """&WASUNITS=%(25)
VD,,,0
M5,0.3937,0.7874,1.1811,-40.0000,-50.0000
VD,,,&WASUNITS
"""
        )

    @unittest.expectedFailure
    def test180(self):
        """Test A, B, & C axis output for values between -90 and -180 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A-100 B-110",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,-100.000,-110.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A-100 B-110",
            "--no-header --no-comments --inches --no-show-editor",
            self.wrap("M5,0.3937,0.7874,1.1811,-100.0000,-110.0000"),
        )

    @unittest.expectedFailure
    def test190(self):
        """Test A, B, & C axis output for values between -180 and -360 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A-240 B-250",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,-240.000,-250.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A-240 B-250",
            "--no-header --no-comments --inches --no-show-editor",
            self.wrap("M5,0.3937,0.7874,1.1811,-240.0000,-250.0000"),
        )

    @unittest.expectedFailure
    def test200(self):
        """Test A, B, & C axis output for values below -360 degrees"""
        self.compare_multi(
            "G1 X10 Y20 Z30 A-440 B-450",
            "--no-header --no-comments --no-show-editor",
            self.wrap("M5,10.000,20.000,30.000,-440.000,-450.000"),
        )
        self.compare_multi(
            "G1 X10 Y20 Z30 A-440 B-450",
            "--no-header --no-comments --inches --no-show-editor",
            self.wrap("M5,0.3937,0.7874,1.1811,-440.0000,-450.0000"),
        )

    def test210(self):
        """Test return-to"""

        # return-to is before postamble
        self.compare_multi("",
            "--no-comments --postamble 'G0 X1 Y2 Z3' --return-to='12,34,56' --no-header --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
J3,12.000,34.000,56.000
J3,1.000,2.000,3.000
VD,,,&WASUNITS
"""
        )

        # allow empty ,
        self.compare_multi("",
            "--no-comments --postamble 'G0 X1 Y2 Z3' --return-to=',34,56' --no-header --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
J3,34.000,56.000
J3,1.000,2.000,3.000
VD,,,&WASUNITS
"""
        )

    def test220(self):
        """Test native-pre/postamble"""

        # return-to is before postamble
        self.compare_multi("",
            "--no-comments --postamble 'G0 X1 Y2 Z3' --native-postamble 'verbatim-post' --native-preamble 'verbatim-pre' --no-header --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
verbatim-pre
J3,1.000,2.000,3.000
VD,,,&WASUNITS
verbatim-post
"""
        )

    def test240(self):
        """Test relative & --modal"""

        c = "G0 X10 Y20 Z30"

        self.compare_multi( "G91", c, c, "G90", c, c,
            "--no-header --no-comments --modal --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
SR 'RELATIVE
J3,10.000,20.000,30.000
J3,10.000,20.000,30.000
SA 'ABSOLUTE
J3,10.000,20.000,30.000
VD,,,&WASUNITS
"""
        )

    def test250(self):
        """Test G54"""

        c = "G0 X10 Y20 Z30"

        self.compare_multi( "G54",
            "--no-header --comments --no-show-editor",
            """'(use default machine units (document units were metric))
&WASUNITS=%(25)
VD,,,1
'(begin operation: testpath)
'(Path: testpath)
'G54 has no effect
'(finish operation: testpath)
VD,,,&WASUNITS
"""
        )
    
    def test260(self):
        """Test Arc"""
 
        c = "G2 X10 Y20 Z40 I1 J2 F99"

        self.compare_multi( 
            "G0 Z5", # the CG plunge is relative, so start from non-0 to test
            "G2 X10 Y20 Z40 I1 J2 F99", # helical segment
            "G0 Z5",
            "G2 Z40 I1 J2 F98", # helical circle
            "G0 Z5",
            "G2 X50 Y60 I1 J2 F89", # segment
            "--no-header --no-comments --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
JZ,5.000
MS,99.000,99.000
CG,,10.000,20.000,1.000,2.000,T,1,35.000,,,,3,1,0 ' Z40.000
JZ,5.000
MS,98.000,98.000
CG,,,,1.000,2.000,T,1,35.000,,,,3,1,0 ' Z40.000
JZ,5.000
MS,89.000,
CG,,50.000,60.000,1.000,2.000,T,1,0,,,,0,1,0
VD,,,&WASUNITS
"""
        )

    def test270(self):
        """Test M00 w/prompt (pause)"""
 
        self.compare_multi( 
            "(With Prompt)", "M0",
            "--no-header --comments --no-show-editor",
            """'(use default machine units (document units were metric))
&WASUNITS=%(25)
VD,,,1
'(begin operation: testpath)
'(Path: testpath)
'With Prompt
PAUSE
'(finish operation: testpath)
VD,,,&WASUNITS
"""
        )

        self.compare_multi( 
            # Include the preceding comment even if no-comments
            "(With Prompt)", "M0",
            "--no-header --no-comments --no-show-editor",
            """&WASUNITS=%(25)
VD,,,1
'With Prompt
PAUSE
VD,,,&WASUNITS
"""
        )

        self.compare_multi( 
            "(Doesn't count as prompt)","G0 X0", "M0", # no prompt
            "--no-header --comments --no-show-editor",
            """'(use default machine units (document units were metric))
&WASUNITS=%(25)
VD,,,1
'(begin operation: testpath)
'(Path: testpath)
'Doesn't count as prompt
JX,0.000
'Continue?
PAUSE
'(finish operation: testpath)
VD,,,&WASUNITS
"""
        )

    def test270(self): 
        """Test drilling"""
        self.maxDiff = 1024*1024

        # We'll trust the other variations (gcode generation tested in TestRefactoredTestPostGCodes.py)
        self.compare_multi( 
            "G73 X1 Y2 Z0 R5 Q1.5 F123",
            "--no-header --comments --no-show-editor",
            """'(use default machine units (document units were metric))
&WASUNITS=%(25)
VD,,,1
'(begin operation: testpath)
'(Path: testpath)
'translate drill [1] G73 F123.000000 Q1.500000 R5.000000 X1.000000 Y2.000000 Z0.000000
JZ,5.000
J2,1.000,2.000
MS,,123.000
MZ,3.500
JZ,3.750
JZ,3.575
MS,,123.000
MZ,2.000
JZ,2.250
JZ,2.075
MS,,123.000
MZ,0.500
JZ,0.750
JZ,0.575
MS,,123.000
MZ,0.000
JZ,5.000
'end translate drill [1] G73
'(finish operation: testpath)
VD,,,&WASUNITS
""",
        )


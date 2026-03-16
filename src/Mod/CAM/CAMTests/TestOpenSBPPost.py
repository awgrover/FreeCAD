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
Tests for the OpenSBP post-processor (opensbp_post.py).

OpenSBP is the native command dialect used by ShopBot CNC controllers.
It differs significantly from G-code: moves use MX/MY/MZ/M2/M3 and
JX/JY/JZ/J2/J3 instead of G0/G1, arcs use CG instead of G2/G3, etc.
"""

import Path
import CAMTests.PathTestUtils as PathTestUtils
import CAMTests.PostTestMocks as PostTestMocks
from Path.Post.Processor import PostProcessorFactory
from Machine.models.machine import Machine, Toolhead, ToolheadType, OutputUnits


Path.Log.setLevel(Path.Log.Level.DEBUG, Path.Log.thisModule())
Path.Log.trackModule(Path.Log.thisModule())


class TestOpenSBPPost(PathTestUtils.PathTestBase):
    """Test OpenSBP-specific features of the opensbp_post.py postprocessor.

    OpenSBP uses native ShopBot commands instead of standard G-code.
    These tests verify command conversion for the major command categories.
    """

    @classmethod
    def setUpClass(cls):
        cls.job, cls.profile_op, cls.tool_controller = (
            PostTestMocks.create_default_job_with_operation()
        )
        cls.post = PostProcessorFactory.get_post_processor(cls.job, "opensbp")

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.maxDiff = None
        self.post.reinitialize()
        self.post._machine = Machine.create_3axis_config()
        self.post._machine.name = "Test ShopBot Machine"
        toolhead = Toolhead(
            name="Default Toolhead",
            toolhead_type=ToolheadType.ROTARY,
            min_rpm=0,
            max_rpm=24000,
            max_power_kw=3.0,
        )
        self.post._machine.toolheads = [toolhead]
        # Reset tracked speeds before each test
        self.post._current_move_speed_xy = None
        self.post._current_move_speed_z = None
        self.post._current_jog_speed_xy = None
        self.post._current_jog_speed_z = None

    def tearDown(self):
        pass

    # -------------------------------------------------------------------------
    # File extension and defaults
    # -------------------------------------------------------------------------

    def test_default_file_extension(self):
        """Default output file extension is 'sbp'."""
        schema = self.post.get_common_property_schema()
        ext = next((p["default"] for p in schema if p["name"] == "file_extension"), None)
        self.assertEqual(ext, "sbp")

    def test_default_preamble_contains_opensbp_comment(self):
        """Default preamble starts with an OpenSBP comment line."""
        schema = self.post.get_common_property_schema()
        preamble = next((p["default"] for p in schema if p["name"] == "preamble"), None)
        self.assertIsNotNone(preamble)
        self.assertIn("OpenSBP", preamble)

    def test_default_postamble_contains_spindle_off(self):
        """Default postamble ends program with spindle-off command >C7."""
        schema = self.post.get_common_property_schema()
        postamble = next((p["default"] for p in schema if p["name"] == "postamble"), None)
        self.assertIsNotNone(postamble)
        self.assertIn(">C7", postamble)

    # -------------------------------------------------------------------------
    # Comment conversion
    # -------------------------------------------------------------------------

    def test_comment_parentheses_converted(self):
        """
        G-code comments in parentheses are converted to OpenSBP single-quote style.

        BEFORE: (This is a comment)
        AFTER:  'This is a comment
        """
        command = Path.Command("(This is a comment)")
        result = self.post._convert_comment(command)
        self.assertEqual(result, "'This is a comment")

    # -------------------------------------------------------------------------
    # Rapid move (G0) → Jog commands
    # -------------------------------------------------------------------------

    def test_rapid_x_only_produces_jx(self):
        """
        G0 X-only move → >JX

        BEFORE: G0 X10
        AFTER:  >JX,10.0000
        """
        command = Path.Command("G0", {"X": 10.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">JX,10.0000", result)
        self.assertNotIn("J2", result)
        self.assertNotIn("J3", result)

    def test_rapid_y_only_produces_jy(self):
        """G0 Y-only move → >JY"""
        command = Path.Command("G0", {"Y": 20.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">JY,20.0000", result)

    def test_rapid_z_only_produces_jz(self):
        """G0 Z-only move → >JZ"""
        command = Path.Command("G0", {"Z": 5.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">JZ,5.0000", result)

    def test_rapid_xy_produces_j2(self):
        """
        G0 XY move → >J2

        BEFORE: G0 X10 Y20
        AFTER:  >J2,10.0000,20.0000
        """
        command = Path.Command("G0", {"X": 10.0, "Y": 20.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">J2,10.0000,20.0000", result)

    def test_rapid_xyz_produces_j3(self):
        """
        G0 XYZ move → >J3

        BEFORE: G0 X10 Y20 Z5
        AFTER:  >J3,10.0000,20.0000,5.0000
        """
        command = Path.Command("G0", {"X": 10.0, "Y": 20.0, "Z": 5.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">J3,10.0000,20.0000,5.0000", result)

    def test_rapid_xz_produces_j3_with_empty_y(self):
        """
        G0 XZ move → >J3 with empty Y field

        BEFORE: G0 X10 Z5
        AFTER:  >J3,10.0000,,5.0000
        """
        command = Path.Command("G0", {"X": 10.0, "Z": 5.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">J3,10.0000,,5.0000", result)

    def test_rapid_yz_produces_j3_with_empty_x(self):
        """
        G0 YZ move → >J3 with empty X field

        BEFORE: G0 Y20 Z5
        AFTER:  >J3,,20.0000,5.0000
        """
        command = Path.Command("G0", {"Y": 20.0, "Z": 5.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">J3,,20.0000,5.0000", result)

    def test_rapid_no_gcode_in_output(self):
        """Rapid move output must not contain G0 or G00."""
        command = Path.Command("G0", {"X": 10.0, "Y": 20.0, "Z": 5.0})
        result = self.post._convert_rapid_move(command)
        self.assertNotIn("G0", result)
        self.assertNotIn("G00", result)

    # -------------------------------------------------------------------------
    # Linear move (G1) → Move commands
    # -------------------------------------------------------------------------

    def test_linear_x_only_produces_mx(self):
        """
        G1 X-only move → >MX

        BEFORE: G1 X10
        AFTER:  >MX,10.0000
        """
        command = Path.Command("G1", {"X": 10.0})
        result = self.post._convert_linear_move(command)
        self.assertIn(">MX,10.0000", result)

    def test_linear_y_only_produces_my(self):
        """G1 Y-only move → >MY"""
        command = Path.Command("G1", {"Y": 20.0})
        result = self.post._convert_linear_move(command)
        self.assertIn(">MY,20.0000", result)

    def test_linear_z_only_produces_mz(self):
        """G1 Z-only move → >MZ"""
        command = Path.Command("G1", {"Z": -5.0})
        result = self.post._convert_linear_move(command)
        self.assertIn(">MZ,-5.0000", result)

    def test_linear_xy_produces_m2(self):
        """
        G1 XY move → >M2

        BEFORE: G1 X10 Y20
        AFTER:  >M2,10.0000,20.0000
        """
        command = Path.Command("G1", {"X": 10.0, "Y": 20.0})
        result = self.post._convert_linear_move(command)
        self.assertIn(">M2,10.0000,20.0000", result)

    def test_linear_xyz_produces_m3(self):
        """
        G1 XYZ move → >M3

        BEFORE: G1 X10 Y20 Z-5
        AFTER:  >M3,10.0000,20.0000,-5.0000
        """
        command = Path.Command("G1", {"X": 10.0, "Y": 20.0, "Z": -5.0})
        result = self.post._convert_linear_move(command)
        self.assertIn(">M3,10.0000,20.0000,-5.0000", result)

    def test_linear_xz_produces_m3_with_empty_y(self):
        """
        G1 XZ move → >M3 with empty Y field

        BEFORE: G1 X10 Z-5
        AFTER:  >M3,10.0000,,-5.0000
        """
        command = Path.Command("G1", {"X": 10.0, "Z": -5.0})
        result = self.post._convert_linear_move(command)
        self.assertIn(">M3,10.0000,,-5.0000", result)

    def test_linear_no_gcode_in_output(self):
        """Linear move output must not contain G1 or G01."""
        command = Path.Command("G1", {"X": 10.0, "Y": 20.0, "Z": -5.0, "F": 500.0})
        result = self.post._convert_linear_move(command)
        self.assertNotIn("G1", result)
        self.assertNotIn("G01", result)

    # -------------------------------------------------------------------------
    # Speed commands (MS / JS)
    # -------------------------------------------------------------------------

    def test_linear_with_feedrate_outputs_ms_command(self):
        """
        G1 with F parameter outputs >MS speed command before the move.

        F in Path.Command is in FreeCAD base units: mm/sec.
        ShopBot MS expects mm/sec — no time-unit conversion needed.

        BEFORE: G1 X10 F500   (500 mm/sec)
        AFTER:  >MS,500.0000,
                >MX,10.0000
        """
        command = Path.Command("G1", {"X": 10.0, "F": 500.0})
        result = self.post._convert_linear_move(command)
        self.assertIn(">MS,", result)
        self.assertIn(">MX,10.0000", result)
        # MS must appear before the move
        self.assertLess(result.index(">MS"), result.index(">MX"))

    def test_rapid_with_feedrate_outputs_js_command(self):
        """G0 with F parameter outputs >JS speed command before the jog."""
        command = Path.Command("G0", {"X": 10.0, "F": 500.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">JS,", result)

    def test_speed_not_repeated_when_unchanged(self):
        """
        Speed command is suppressed when the speed has not changed.

        Issue two identical-speed moves; only the first should emit >MS.
        """
        command1 = Path.Command("G1", {"X": 10.0, "F": 500.0})
        command2 = Path.Command("G1", {"X": 20.0, "F": 500.0})
        result1 = self.post._convert_linear_move(command1)
        result2 = self.post._convert_linear_move(command2)
        self.assertIn(">MS,", result1)
        self.assertNotIn(">MS,", result2)

    def test_speed_emitted_when_changed(self):
        """Speed command is emitted again when feedrate changes."""
        command1 = Path.Command("G1", {"X": 10.0, "F": 500.0})
        command2 = Path.Command("G1", {"X": 20.0, "F": 1000.0})
        self.post._convert_linear_move(command1)
        result2 = self.post._convert_linear_move(command2)
        self.assertIn(">MS,", result2)

    def test_speed_value_metric_passthrough(self):
        """
        F value is passed through unchanged for metric output.

        F in Path.Command is mm/sec; ShopBot MS expects mm/sec.
        No time-unit conversion (no ×60 or ÷60).

        BEFORE: G1 X10 F250   (250 mm/sec)
        AFTER:  >MS,250.0000,
                >MX,10.0000
        """
        command = Path.Command("G1", {"X": 10.0, "F": 250.0})
        result = self.post._convert_linear_move(command)
        self.assertIn(">MS,250.0000,", result)

    def test_speed_value_imperial_conversion(self):
        """
        F value is divided by 25.4 for imperial output.

        F=25.4 mm/sec → 1.0 in/sec for ShopBot imperial output.

        BEFORE: G1 X10 F25.4  (25.4 mm/sec)
        AFTER:  >MS,1.0000,
                >MX,1.0000    (X also converted: 25.4mm → 1.0 in)
        """
        self.post._machine.output.units = OutputUnits.IMPERIAL
        command = Path.Command("G1", {"X": 25.4, "F": 25.4})
        result = self.post._convert_linear_move(command)
        self.assertIn(">MS,1.0000,", result)

    def test_js_speed_value_metric_passthrough(self):
        """
        Jog speed (JS) is also passed through unchanged for metric output.

        BEFORE: G0 X10 F300   (300 mm/sec jog speed)
        AFTER:  >JS,300.0000,
                >JX,10.0000
        """
        command = Path.Command("G0", {"X": 10.0, "F": 300.0})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">JS,300.0000,", result)

    # -------------------------------------------------------------------------
    # Arc moves (G2/G3) → CG command
    # -------------------------------------------------------------------------

    def test_arc_cw_g2_direction_1(self):
        """
        CW arc (G2) → >CG with direction 1, T (true path) compensation.

        BEFORE: G2 X10 Y0 I5 J0
        AFTER:  >CG,,10.0000,0.0000,5.0000,0.0000,T,1
        """
        command = Path.Command("G2", {"X": 10.0, "Y": 0.0, "I": 5.0, "J": 0.0})
        result = self.post._convert_arc_move(command)
        self.assertIn(">CG,", result)
        self.assertIn(",T,", result)
        self.assertIn(",1", result)
        self.assertNotIn(",-1", result)

    def test_arc_ccw_g3_direction_minus1(self):
        """
        CCW arc (G3) → >CG with direction -1, T (true path) compensation.

        BEFORE: G3 X10 Y0 I5 J0
        AFTER:  >CG,,10.0000,0.0000,5.0000,0.0000,T,-1
        """
        command = Path.Command("G3", {"X": 10.0, "Y": 0.0, "I": 5.0, "J": 0.0})
        result = self.post._convert_arc_move(command)
        self.assertIn(",T,", result)
        self.assertIn(",-1", result)

    def test_arc_xy_plane_format(self):
        """
        Simple XY arc uses >CG format without plunge parameter.

        BEFORE: G2 X10 Y5 I5 J0
        AFTER:  >CG,,10.0000,5.0000,5.0000,0.0000,L,1
        """
        command = Path.Command("G2", {"X": 10.0, "Y": 5.0, "I": 5.0, "J": 0.0})
        result = self.post._convert_arc_move(command)
        # Should be exactly 8 comma-separated fields (no plunge)
        lines = result.strip().splitlines()
        cg_line = next(l for l in lines if l.startswith(">CG"))
        fields = cg_line.split(",")
        self.assertEqual(len(fields), 8, f"Expected 8 fields in CG command, got: {cg_line}")

    def test_helical_arc_includes_plunge(self):
        """
        Helical arc (G2/G3 with Z) adds a plunge parameter as the 9th field.

        BEFORE: G2 X10 Y0 I5 J0 Z-5 (current Z=0)
        AFTER:  >CG,,10.0000,0.0000,5.0000,0.0000,L,1,5.0000
        """
        self.post._modal_state = {"Z": 0.0}
        command = Path.Command("G2", {"X": 10.0, "Y": 0.0, "I": 5.0, "J": 0.0, "Z": -5.0})
        result = self.post._convert_arc_move(command)
        lines = result.strip().splitlines()
        cg_line = next(l for l in lines if l.startswith(">CG"))
        fields = cg_line.split(",")
        self.assertEqual(len(fields), 9, f"Expected 9 fields for helical arc, got: {cg_line}")

    def test_arc_no_gcode_in_output(self):
        """Arc output must not contain G2 or G3."""
        command = Path.Command("G2", {"X": 10.0, "Y": 0.0, "I": 5.0, "J": 0.0})
        result = self.post._convert_arc_move(command)
        self.assertNotIn("G2", result)
        self.assertNotIn("G3", result)

    # -------------------------------------------------------------------------
    # Tool change (M6)
    # -------------------------------------------------------------------------

    def test_tool_change_manual_includes_pause(self):
        """
        Manual tool change (no ATC) emits PAUSE for operator intervention.

        BEFORE: M6 T2
        AFTER:  'Manual tool change to T2
                >&ToolName=2
                >&Tool=2
                >PAUSE
        """
        self.post.values["AUTOMATIC_TOOL_CHANGER"] = False
        command = Path.Command("M6", {"T": 2})
        result = self.post._convert_tool_change(command)
        self.assertIn(">PAUSE", result)
        self.assertIn(">&Tool=2", result)

    def test_tool_change_automatic_no_pause(self):
        """
        Automatic tool change (ATC enabled) does not emit PAUSE.

        BEFORE: M6 T3
        AFTER:  >&ToolName=3
                >&Tool=3
        """
        self.post.values["AUTOMATIC_TOOL_CHANGER"] = True
        command = Path.Command("M6", {"T": 3})
        result = self.post._convert_tool_change(command)
        self.assertIn(">&Tool=3", result)
        self.assertNotIn(">PAUSE", result)

    def test_tool_change_sets_tool_name(self):
        """Tool change always sets >&ToolName variable."""
        self.post.values["AUTOMATIC_TOOL_CHANGER"] = False
        command = Path.Command("M6", {"T": 5})
        result = self.post._convert_tool_change(command)
        self.assertIn(">&ToolName=5", result)

    # -------------------------------------------------------------------------
    # Spindle commands (M3/M4/M5)
    # -------------------------------------------------------------------------

    def test_spindle_on_manual_emits_pause(self):
        """
        M3 without automatic spindle control emits manual prompt and PAUSE.

        BEFORE: M3 S18000
        AFTER:  'Set spindle to 18000 RPM and start manually
                >PAUSE
        """
        self.post.values["AUTOMATIC_SPINDLE"] = False
        command = Path.Command("M3", {"S": 18000})
        result = self.post._convert_spindle_command(command)
        self.assertIn(">PAUSE", result)
        self.assertIn("18000", result)

    def test_spindle_on_automatic_emits_tr_and_c6(self):
        """
        M3 with automatic spindle control emits TR (speed), C6 (on), and PAUSE (wait).

        BEFORE: M3 S18000
        AFTER:  >TR,18000
                >C6
                >PAUSE 2
        """
        self.post.values["AUTOMATIC_SPINDLE"] = True
        command = Path.Command("M3", {"S": 18000})
        result = self.post._convert_spindle_command(command)
        self.assertIn(">TR,18000", result)
        self.assertIn(">C6", result)
        self.assertIn(">PAUSE 2", result)

    def test_spindle_off_manual_emits_pause(self):
        """
        M5 without automatic spindle emits manual prompt and PAUSE.

        BEFORE: M5
        AFTER:  'Turn spindle OFF manually
                >PAUSE
        """
        self.post.values["AUTOMATIC_SPINDLE"] = False
        command = Path.Command("M5", {})
        result = self.post._convert_spindle_command(command)
        self.assertIn(">PAUSE", result)

    def test_spindle_off_automatic_emits_tr0_and_c7(self):
        """
        M5 with automatic spindle control emits TR,0 and C7 (spindle off).

        BEFORE: M5
        AFTER:  >TR,0
                >C7
        """
        self.post.values["AUTOMATIC_SPINDLE"] = True
        command = Path.Command("M5", {})
        result = self.post._convert_spindle_command(command)
        self.assertIn(">TR,0", result)
        self.assertIn(">C7", result)

    def test_spindle_no_gcode_in_output(self):
        """Spindle output must not contain M3, M4, or M5."""
        self.post.values["AUTOMATIC_SPINDLE"] = True
        command = Path.Command("M3", {"S": 18000})
        result = self.post._convert_spindle_command(command)
        self.assertNotIn("M3", result)
        self.assertNotIn("M4", result)
        self.assertNotIn("M5", result)

    # -------------------------------------------------------------------------
    # Dwell (G4)
    # -------------------------------------------------------------------------

    def test_dwell_produces_pause_with_time(self):
        """
        G4 dwell → >PAUSE <seconds>

        BEFORE: G4 P2.5
        AFTER:  >PAUSE 2.50
        """
        command = Path.Command("G4", {"P": 2.5})
        result = self.post._convert_dwell(command)
        self.assertIn(">PAUSE", result)
        self.assertIn("2.50", result)

    def test_dwell_no_gcode_in_output(self):
        """Dwell output must not contain G4."""
        command = Path.Command("G4", {"P": 1.0})
        result = self.post._convert_dwell(command)
        self.assertNotIn("G4", result)

    # -------------------------------------------------------------------------
    # Suppressed commands
    # -------------------------------------------------------------------------

    def test_fixture_commands_suppressed(self):
        """
        G54–G59 fixture offsets are suppressed (return None).

        OpenSBP has no work coordinate system concept.
        """
        for fixture in ["G54", "G55", "G56", "G57", "G58", "G59"]:
            command = Path.Command(fixture, {})
            result = self.post._convert_fixture(command)
            self.assertIsNone(result, f"{fixture} should be suppressed")

    def test_modal_commands_suppressed(self):
        """
        Standard G-code modal setup commands are suppressed (return None).

        OpenSBP doesn't use G20/G21 (units), G43, G80, G90, etc.
        """
        for modal in ["G20", "G21", "G43", "G80", "G90", "G91"]:
            command = Path.Command(modal, {})
            result = self.post._convert_modal_command(command)
            self.assertIsNone(result, f"{modal} should be suppressed")

    # -------------------------------------------------------------------------
    # Unit conversion (imperial output)
    # -------------------------------------------------------------------------

    def test_linear_move_imperial_conversion(self):
        """
        With imperial output units, coordinate values are divided by 25.4.

        BEFORE: G1 X25.4 Y50.8 (metric input)
        AFTER:  >M2,1.0000,2.0000
        """
        self.post._machine.output.units = OutputUnits.IMPERIAL
        command = Path.Command("G1", {"X": 25.4, "Y": 50.8})
        result = self.post._convert_linear_move(command)
        self.assertIn(">M2,1.0000,2.0000", result)

    def test_rapid_move_imperial_conversion(self):
        """With imperial output, rapid move coordinates are divided by 25.4."""
        self.post._machine.output.units = OutputUnits.IMPERIAL
        command = Path.Command("G0", {"X": 25.4, "Z": 25.4})
        result = self.post._convert_rapid_move(command)
        self.assertIn(">J3,1.0000,,1.0000", result)

    # -------------------------------------------------------------------------
    # Full export sanity check
    # -------------------------------------------------------------------------

    def test_full_export_contains_no_gcode_moves(self):
        """
        Full export of a simple profile must not contain G0 or G1 move commands.
        """
        self.post._machine.output.comments.enabled = False
        self.post._machine.output.output_header = False
        self.profile_op.Path = Path.Path(
            [
                Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 5.0}),
                Path.Command("G1", {"X": 10.0, "Y": 0.0, "Z": -1.0, "F": 500.0}),
                Path.Command("G0", {"Z": 5.0}),
            ]
        )
        results = self.post.export2()
        output = "\n".join(g for _, g in results)
        # No bare G0/G1 move lines (comments mentioning "G0" are OK to skip
        # checking here; we look for actual command lines)
        import re

        move_lines = [l for l in output.splitlines() if re.match(r"^\s*G[01]\b", l.strip())]
        self.assertEqual(move_lines, [], f"Unexpected G-code move lines: {move_lines}")

    def test_full_export_contains_opensbp_moves(self):
        """
        Full export of a simple profile contains OpenSBP move commands.
        """
        self.post._machine.output.comments.enabled = False
        self.post._machine.output.output_header = False
        self.profile_op.Path = Path.Path(
            [
                Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 5.0}),
                Path.Command("G1", {"X": 10.0, "Y": 0.0, "Z": -1.0, "F": 500.0}),
                Path.Command("G0", {"Z": 5.0}),
            ]
        )
        results = self.post.export2()
        output = "\n".join(g for _, g in results)
        # At least one jog and one move command expected
        self.assertRegex(output, r">J[XYZ23]|>J3")
        self.assertRegex(output, r">M[XYZ23]|>M3")

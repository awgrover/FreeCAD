# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2014 sliptonic <shopinthewoods@gmail.com>               *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful,            *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Lesser General Public License for more details.                   *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with FreeCAD; if not, write to the Free Software        *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

from builtins import open as pyopen
import re
import argparse
import datetime
import shlex
import FreeCAD
import Path
import Path.Post.Utils as PostUtils
from PathScripts import PathUtils


TOOLTIP = """
This is an postprocessor file for the Path workbench. It will output path data
in a format suitable for OpenSBP controllers like shopbot.  This postprocessor,
once placed in the appropriate PathScripts folder, can be used directly from
inside FreeCAD, via the GUI importer or via python scripts with:

import Path
Path.write(object,"/path/to/file.ncc","post_opensbp")
"""

"""
ToDo
    arc. have an implementation
    drilling.  Have outline, copy from estlcam_post or rrf_post
    fixtures/coordinate-systems. have outline.

"""

now = datetime.datetime.now()

PRECISION = 3 # default is metric
SKIP_UNKNOWN = [] # gcodes to skip if --abort-on-unknown

parser = argparse.ArgumentParser(prog="opensbp", add_help=False)
parser.add_argument("--header", action=argparse.BooleanOptionalAction, help="include header output. deafault=True", default=True)
parser.add_argument("--comments", action=argparse.BooleanOptionalAction, help="output comments (default=False)")
# opensbp can't do --line-numbers
parser.add_argument(
    "--show-editor",
    action=argparse.BooleanOptionalAction,
    help="don't pop up editor before writing output",
    default=True
)
# no default so that --inches/--metric can set the default for that mode
parser.add_argument("--precision", help=f"number of digits of precision, default={PRECISION}")
parser.add_argument(
    "--preamble",
    help='set g-code commands to be issued before the first command, multi-line g-code w/ \\n, default=None',
)
parser.add_argument("--return-to", help="Move to x,y,z,a,b coordinates at the end (before postamble), e.g --return-to 0,0. empty for an axis, or omit trailing to not move in that axis. default is don't return-to")
parser.add_argument(
    "--postamble",
    help='set g-code commands to be issued after the last command, multi-line g-code w/ \\n, default=None',
)
parser.add_argument(
    "--native-postamble",
    help='verbatim opensbp commands to be issued after the last command, multi-line w/ \\n. After postamble. Consider a "Cn" or "FB". default=None',
)
parser.add_argument(
    # nb, no default (so --inches and allow --inches --metric)
    "--metric", action="store_true", help="Convert output for US imperial mode, default"
)
parser.add_argument(
    # this should probably be True for most shopbot installations
    "--inches", action="store_true", help="Convert output for US imperial mode, default=metric", default=False
)
parser.add_argument("--axis-modal", action=argparse.BooleanOptionalAction, help="Shorten output when axis-values don't change", default=False)
parser.add_argument("--modal", action=argparse.BooleanOptionalAction, help="Shorten output when a modal command repeats for no effect", default=False)
parser.add_argument(
    # this should probably be True for most shopbot installations
    "--ab-is-distance", action="store_true", help="A & B axis are distances, default=degrees"
)
parser.add_argument("--abort-on-unknown", action=argparse.BooleanOptionalAction, help="Generate an error and fail if an unknown gcode is seen. default=True", default=True)
parser.add_argument("--skip-unknown", help="if --abort-on-unknown, allow these gcodes, change them to a comment. E.g. --skip-unknown G55,G56")
parser.add_argument("--toolchanger", action=argparse.BooleanOptionalAction, help="Use auto-tool-changer (macro C9), default=manual", default=False)
parser.add_argument("--spindle-controller", action=argparse.BooleanOptionalAction, help="Has software controlled spindle speed, default=manual", default=False)
parser.add_argument("--wait-for-spindle", type=int, help="How long to wait after a spindle-speed change, only if --spindle-controller. Default=3", default=3)
parser.add_argument("--gcode-comments", action=argparse.BooleanOptionalAction, help="Add the original gcode as a comment, for debugging", default=False)


Arguments = None # updated at export() time with parser.parse_args

TOOLTIP_ARGS = parser.format_help()

ALLOWED_AXIS = ["X", "Y", "Z", "A", "B"]  # also used for --modal optimization
CurrentState = {}


def getMetricValue(val):
    return val


def getImperialValue(val):
    return val / 25.4


GetValue = getMetricValue
FloatPrecision = None # setup in processArguments


def processArguments(argstring):

    global PRECISION
    global SKIP_UNKNOWN
    global GetValue
    global FloatPrecision
    global Arguments

    Arguments = parser.parse_args(shlex.split(argstring))

    # GetValue has a default when it gets here, so if no arg, then we stay metric
    if Arguments.inches:
        GetValue = getImperialValue
        PRECISION = 4
    # nb: as override when --inches
    if Arguments.metric:
        GetValue = getMetricValue
        PRECISION = 3

    if Arguments.precision is not None:
        PRECISION = int(Arguments.precision)

    FloatPrecision = f".{PRECISION}f"

    if Arguments.skip_unknown is not None:
        SKIP_UNKNOWN = Arguments.skip_unknown.split(',')
        

def set_speeds_before_tool_change(obj):
    # on tool change, expicitly set speeds to compensate for missing F parameters on early movements
    # Only call us for isinstance(obj.Proxy, ToolController)

    gcode = ''

    # Shouldn't happen in real use, but happens during unit-testing
    if 'UNDER_UNITTEST' in globals() and obj is None:
        return ''

    gcode += comment(f"(set speeds: {obj.Label})", True)
    vs = []

    has_speed = False # skip VS if no speeds

    if obj.HorizFeed != 0.0:
        has_speed = True
        vs.append( format( GetValue(FreeCAD.Units.Quantity(obj.HorizFeed.getValueAs('mm/s')).Value),'.4f') )
    else:
        vs.append('')
        gcode += comment("(no HorizFeed)", True)
    if obj.HorizFeed != 0.0:
        has_speed = True
        vs.append( format( GetValue(FreeCAD.Units.Quantity(obj.VertFeed.getValueAs('mm/s')).Value),'.4f') )
    else:
        vs.append('')
        gcode += comment("(no VertFeed)", True)

    # fixme: where to get values?
    vs.append('') # a-move-speed
    vs.append('') # b-move-speed

    if obj.HorizRapid != 0.0:
        vs.append( format( GetValue(FreeCAD.Units.Quantity(obj.HorizRapid.getValueAs('mm/s')).Value),'.4f') )
        has_speed = True
    else:
        vs.append('')
        gcode += comment("(no HorizRapid)", True)

    if obj.VertRapid != 0.0:
        vs.append( format( GetValue(FreeCAD.Units.Quantity(obj.VertRapid.getValueAs('mm/s')).Value),'.4f') )
        has_speed = True
    else:
        vs.append('')
        gcode += comment("(no VertRapid)", True)

    if has_speed:
        gcode += f'VS,{ ",".join(vs)}\n'

    return gcode

def export(objectslist, filename, argstring):
    global CurrentState

    processArguments(argstring)

    for obj in objectslist:
        if not hasattr(obj, "Path"):
            print( f"the object {obj.Name if 'Name' in dir(obj) else obj.__class__.__name__} is not a path. Please select only path and Compounds." )
            # Other postprocessors skip it
            return ''

    CurrentState = {
        "X": 0,
        "Y": 0,
        "Z": 0,
        "A": 0,
        "B": 0,
        "C": None, "U": None, "V": None, "W": None, # axis not available
        "F": 0,
        "S": 0,
        "JSXY": 0,
        "JSZ": 0,
        "MSXY": 0,
        "MSZ": 0,
        "Tool" : None, # None on first time, then the number
        "ToolController" : None, # a toolcontroller object from the document
        "Absolute" : True, # G91 puts in relative
        "Operation" : None, # updated in parse_list_of_commands() when we start each operation
    }
    print("postprocessing...")
    gcode = ""

    # write header
    if Arguments.header:
        # not using comment(), the option overrides --comments for the header
        gcode += "'Exported by FreeCAD\n"
        gcode += "'Post Processor: " + __name__ + "\n"
        gcode += "'Output Time:" + str(now) + "\n"

    def str_to_gcode(s):
        # one gcode
        # e.g. str_to_gcode("G0 X50")
        pc = Path.Command()
        try:
            pc.setFromGCode(s)
        except ValueError as e:
            # can't tell if it is really 'Badly formatted GCode argument', so just add our gcode to the message
            raise ValueError(f"for gcode: {s}") from e
        return pc

    if Arguments.preamble:
        gcode += comment('(begin preamble)',True)
        preamble_lines = Arguments.preamble.replace('\\n','\n').splitlines(False)
        preamble_commands = [ str_to_gcode(x) for x  in preamble_lines ]
        gcode += parse_list_of_commands( preamble_commands )

    for obj in objectslist:
        # Order: Fixture, ToolControl, Path, repeat

        # so we can get speeds and tool-name etc deeper in the objects
        if hasattr(obj, "Proxy") and isinstance(obj.Proxy, Path.Tool.Controller.ToolController):
            CurrentState['ToolController'] = obj # .Tool.Label is the tool name

        # do the pre_op
        if hasattr(obj, "Proxy") and isinstance(obj.Proxy, Path.Op.Base.ObjectOp):
            CurrentState['Operation'] = obj
        gcode += comment(f"(begin operation: {obj.Label})", True)

        gcode += parse(obj)

        # do the post_op
        gcode += comment(f"(finish operation: {obj.Label})", True)

    if Arguments.return_to:
        # x,y,z,a,b
        # can omit any trailing ones which won't change
        # can use empty to mean "don't change". e.g. --return-to ,0 # means only y to zero
        possible_axis = ['X','Y','Z','A','B']
        try:
            coords = [
                f"{possible_axis[i]}{float(x)}"
                for i,x in enumerate(Arguments.return_to.split(','))
                if x != ''
            ]
        except ValueError as e:
            print(f"{e}\nExpected float-values in --return-to '{Arguments.return_to}'")
        else:
            gcode += comment(f"(return-to)", True)
            return_to_gcode= f"G0 {' '.join(coords)}"
            return_to = str_to_gcode( return_to_gcode )
            gcode += parse_list_of_commands( [return_to] )

    if Arguments.postamble:
        gcode += comment('(begin postamble)',True)
        postamble_lines = Arguments.postamble.replace('\\n','\n').splitlines(False)
        postamble_commands = [ str_to_gcode(x) for x  in postamble_lines ]
        gcode += parse_list_of_commands( postamble_commands )

    if Arguments.native_postamble:
        comment('(native postamble)',True)
        post_lines = Arguments.native_postamble.replace('\\n','\n')
        if not post_lines.endswith("\n"):
            post_lines += "\n"
        gcode += post_lines

    if Arguments.show_editor:
        dia = PostUtils.GCodeEditorDialog()
        dia.editor.setText(gcode)
        result = dia.exec_()
        if result:
            final = dia.editor.toPlainText()
        else:
            final = gcode
    else:
        final = gcode

    print("done postprocessing.")

    # Write the output
    if filename != "-":
        with pyopen(filename, "w") as gfile:
            gfile.write(final)

    return final


def gcodecomment(command,prefix=''):
    # return the gcode as a trailing comment if appropriate
    return f" '{prefix}{command.toGCode()}" if Arguments.gcode_comments else ''

def move(command):
    txt = ""

    axis = ""
    # we don't do CUVW
    for p in ("C", "U", "V", "W"):
        if p in command.Parameters:
            print(f"ERROR: We can't do axis {p} (or any of CUVW)")
            return '' # this skips speed change!

    for p in ALLOWED_AXIS : # we don't do CUVW
        if p in command.Parameters:
            if Arguments.axis_modal:
                if (
                    (CurrentState['Absolute'] and command.Parameters[p] != CurrentState[p])
                    or (not CurrentState['Absolute'] and command.Parameters[p] != 0)
                ):
                    axis += p
            else:
                axis += p

    # Handle speed change
    if "F" in command.Parameters:
        if command.Name in {"G1", "G01"}:  # move
            movetype = "MS"
        else:  # jog
            movetype = "JS"

        speed = command.Parameters["F"]
        zspeed = ""
        xyspeed = ""
        if "Z" in axis:
            speed_key = "{}Z".format(movetype)
            speed_val = GetValue(speed)
            if CurrentState[speed_key] != speed_val:
                CurrentState[speed_key] = speed_val
                zspeed = "{:f}".format(speed_val)
        if ("X" in axis) or ("Y" in axis):
            speed_key = "{}XY".format(movetype)
            speed_val = GetValue(speed)
            if CurrentState[speed_key] != speed_val:
                CurrentState[speed_key] = speed_val
                xyspeed = "{:f}".format(speed_val)

        if "A" in axis or "B" in axis:
            print("WARNING: we aren't handling speed for A and B axis...")

        if zspeed or xyspeed:
            txt += f"{movetype},{xyspeed},{zspeed}{gcodecomment(command)}\n"

    # Actual move

    if command.Name in {"G0", "G00"}:
        pref = "J"
    else:
        pref = "M"

    txt_len_before_move = len(txt) # for detection to do +gcodecomment and \n

    if len(axis) == 1:
        # axis string is key and command-second-letter
        txt += pref + axis
        if axis in {'A','B'} and not Arguments.ab_is_distance:
            txt += "," + format(command.Parameters[axis], FloatPrecision)
        else:
            txt += "," + format(GetValue(command.Parameters[axis]), FloatPrecision)
    elif axis == "XY":
        txt += pref + "2"
        txt += "," + format(GetValue(command.Parameters["X"]), FloatPrecision)
        txt += "," + format(GetValue(command.Parameters["Y"]), FloatPrecision)
    elif axis in { "XZ", "YZ", "XYZ" }:
        # anything plus Z requires the 3 arg version
        txt += pref + "3"
        for key in ('X','Y','Z'):
            txt += "," + format(GetValue(command.Parameters[key]), FloatPrecision) if key in axis else ''
    elif ('A' in axis or 'B' in axis) and len(axis)>1 and not next( ( c for c in 'CUVW' if c in axis), None):
        # AB+ needs "5" version (carefully excluding CUVW)
        # we could optimize to an M4 if just A
        txt += pref + "5"
        for key in ('X','Y','Z','A','B'):
            if key in {'A','B'} and not Arguments.ab_is_distance:
                txt += "," + format(command.Parameters[key], FloatPrecision) if key in axis else ''
            else:
                txt += "," + format(GetValue(command.Parameters[key]), FloatPrecision) if key in axis else ''
    elif axis == "":
        print("warning: skipping duplicate move.")
    else:
        print(CurrentState)
        print(command)
        print(f"I don't know how to handle '{axis}' for a move.")

    # common line endings
    if len(txt) != txt_len_before_move:
        txt += gcodecomment(command)
        txt += "\n"

    return txt


def arc(command):
    if command.Name == "G2":  # CW
        dirstring = "1"
    else:  # G3 means CCW
        dirstring = "-1"
    txt = "CG,,"
    txt += format(GetValue(command.Parameters["X"]), FloatPrecision) + ","
    txt += format(GetValue(command.Parameters["Y"]), FloatPrecision) + ","
    txt += format(GetValue(command.Parameters["I"]), FloatPrecision) + ","
    txt += format(GetValue(command.Parameters["J"]), FloatPrecision) + ","
    txt += "T" + ","
    txt += dirstring
    txt += "\n"
    return txt


def tool_change(command):
    txt = ""
    txt += comment("(tool change)", True)
    tool_number = int(command.Parameters['T'])
    tool_name = CurrentState['ToolController'].Tool.Label if CurrentState['ToolController'] else str(tool_number)

    txt += f"&Tool={tool_number}{gcodecomment(command)}\n"
    if Arguments.toolchanger:
        txt += "C9 'toolchanger\n"
    else:

        # assume the first tool is already installed (for manual)
        if CurrentState['Tool'] is None:
            txt += comment(f"(First change tool, should already be #{tool_number}: {tool_name})",True)
        else:
            txt += f"'Change tool to #{tool_number}: {tool_name}\n" # prompt
            txt += "PAUSE\n" # causes a modal to ask "ok?"
        CurrentState['Tool'] = tool_number
    # after C9
    # Don't know actual rules for strings, but need to quote lest a & gets interpreted
    tool_name = re.sub(r'[^A-Za-z0-9/_ .-]', '', tool_name)
    txt += f'&ToolName="{tool_name}"\n'


    # As of FreeCAD 1.0.2, early movements don't emit a F, so there is no "current" speed
    # Since a tool-change is issued 1st (and when appropriate), we'll set the current speed here
    txt += set_speeds_before_tool_change(CurrentState['ToolController'])

    return txt


def comment(command, keepparens=False, force=False):
    # comments from gcode are stripped of ()
    # comments we generate include ()

    # from gcode stream, it's a Path.Command
    # from internal use, it's a str
    if isinstance(command, Path.Command):
        command = command.Name

    if Arguments.comments or force:
        return f"'{command if keepparens else command[1:-1]}\n"
    else:
        print("a comment", command)
        return ''

def absolute_positions(command):
    CurrentState['Absolute'] = True
    return comment("Absolute Positions", True) + "SA 'ABSOLUTE\n"

    
def relative_positions(command):
    CurrentState['Absolute'] = False
    return comment("Relative Positions", True) + "SR 'RELATIVE\n"

def spindle(command):
    txt = ""
    if command.Name == "M3":  # CW
        pass
    else:
        pass
    txt += f"TR,{int(command.Parameters['S'])}\n"
    if Arguments.spindle_controller:
        txt += "C6 'spindle-controller\n"
        if Arguments.wait_for_spindle > 0:
            txt += f"PAUSE {Arguments.wait_for_spindle}\n"
    else:
        txt += f"'Change spindle speed to {int(command.Parameters['S'])}\n" # prompt
        txt += "PAUSE\n" # causes a modal to ask "ok?"

    return txt

def coordinate_system(command):
    txt = ''

    gpart = command.Name

    # Parsing for all of them, but we only support G54
    if gpart == "G54.1":
        which = int(command.Parameters['P'])
    elif m := re.match(r'G5([45678])', gpart):
        which = int(m.group(1)) - 3 # starts at 1
    elif gpart == "G59":
        if 'P' in command.Parameters:
            which = int(command.Parameters['P'])
        else:
            which = 6
    elif m := re.match(r'G59\.([123])', gpart):
        which = 6 + int(m.group(1))

    if which != 1:
        print(f"Warning: {command.toGCode()} not supported (only G54 / coord-system 1)")

    else:
        txt += comment(f"G54 has no effect{gcodecomment(command)}", True)
    
    return txt
        

# Supported Commands
scommands = {
    "G0": { "fn" : move },
    "G1": { "fn" : move },
    "G2": { "fn" : arc },
    "G3": { "fn" : arc },
    "M6": { "fn" : tool_change },
    "M3": { "fn" : spindle },
    "G00": { "fn" : move },
    "G01": { "fn" : move },
    "G02": { "fn" : arc },
    "G03": { "fn" : arc },
    "M06": { "fn" : tool_change },
    "M03": { "fn" : spindle },
    "G91" : { "fn" : relative_positions },
    "G90" : { "fn" : absolute_positions },
    "G54" : { "fn" : coordinate_system },

    "comment": { "fn" : comment },
}

def parse(pathobj):
    output = ""
    # Above list controls the order of parameters

    if hasattr(pathobj, "Group"):  # We have a compound or project.
        output += comment(f"(compound: {pathobj.Label})", True)
        for p in pathobj.Group:
            output += parse(p)
    else:  # parsing simple path

        # groups might contain non-path things like stock.
        if not hasattr(pathobj, "Path"):
            return output

        output += comment(f"(Path: {pathobj.Label})", True)

        # FIXME: the use of getPathWithPlacement() causes a yaw-pitch calculation which gives odd AB values
        # so, tests disabled for those
        # no-other post-procesor tests AB (except linuxcnc which does not do getPathWithPlacement())

        output += parse_list_of_commands( PathUtils.getPathWithPlacement(pathobj).Commands )

    return output

def parse_list_of_commands(commands):
    output = ""
    last_gcode = ''
    for c in commands:

        command = c.Name
        if command.startswith("("):
            command = 'comment'

        if command in scommands:
            # skip duplicate commands
            if Arguments.modal and c.toGCode() == last_gcode:
                # Don't elide movements if relative motion, it isn't a noop!
                if set(ALLOWED_AXIS) & set( c.Parameters.keys() ):
                    if CurrentState['Absolute']:
                        continue
                # non-movements don't care about relative
                else:
                    continue
            last_gcode = c.toGCode()

            output += scommands[command]['fn'](c)
            if c.Parameters:
                CurrentState.update(c.Parameters)
        elif command == '':
            # skip empties
            pass
        else:
            opname = CurrentState['Operation'].Label if CurrentState['Operation'] else ''
            if Arguments.abort_on_unknown and command not in SKIP_UNKNOWN:
                message = f"gcode not handled in operation {opname}: {c.toGCode()}"
                FreeCAD.Console.PrintError(message+"\n")
                raise NotImplementedError(message)
            else:
                output += comment(f"not handled: {c.toGCode()}", True, force=True)
                FreeCAD.Console.PrintWarning(f"Skipped unknown gcode {'in '+opname if opname else ''}: {c.toGCode()}\n")

    return output

# print(__name__ + " gcode postprocessor loaded.")

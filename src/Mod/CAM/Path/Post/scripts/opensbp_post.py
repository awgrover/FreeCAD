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
import argparse
import datetime
import shlex
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
DONE:
    uses native commands
    handles feed and jog moves
    handles XY, Z, and XYZ feed speeds
    handles arcs
    support for inch output
ToDo
    comments may not format correctly
    drilling.  Haven't looked at it.
    many other things

"""

now = datetime.datetime.now()

PRECISION = 4

parser = argparse.ArgumentParser(prog="opensbp", add_help=False)
parser.add_argument("--no-header", action="store_true", help="suppress header output")
parser.add_argument("--comments", action="store_true", help="output comments (default=False)", default=False)
#parser.add_argument("--line-numbers", action="store_true", help="prefix with line numbers")
parser.add_argument(
    "--no-show-editor",
    action="store_true",
    help="don't pop up editor before writing output",
)
parser.add_argument("--precision", default=str(PRECISION), help=f"number of digits of precision, default={PRECISION}")
parser.add_argument(
    "--preamble",
    help='set g-code commands to be issued before the first command, multi-line g-code w/ \\n, default=None',
)
parser.add_argument(
    "--postamble",
    help='set g-code commands to be issued after the last command, multi-line g-code w/ \\n, default=None',
)
parser.add_argument(
    # this should probably be True for most shopbot installations
    "--inches", action="store_true", help="Convert output for US imperial mode, default=metric"
)
parser.add_argument(
    # this should probably be True for most shopbot installations
    "--ab-is-distance", action="store_true", help="A & B axis are distances, default=degrees"
)

TOOLTIP_ARGS = parser.format_help()

OUTPUT_COMMENTS = False
OUTPUT_HEADER = True
SHOW_EDITOR = True
DEGREES_FOR_AB = True # False will treat as metric/inches
COMMAND_SPACE = ","

# Preamble text will appear at the beginning of the GCODE output file.
PREAMBLE = """"""
# Postamble text will appear following the last operation.
POSTAMBLE = """"""

# Pre operation text will be inserted before every operation
PRE_OPERATION = """"""

# Post operation text will be inserted after every operation
POST_OPERATION = """"""

# Tool Change commands will be inserted before a tool change
TOOL_CHANGE = """"""


CurrentState = {}


def getMetricValue(val):
    return val


def getImperialValue(val):
    return val / 25.4


GetValue = getMetricValue
FloatPrecision = None # setup in processArguments


def processArguments(argstring):

    global OUTPUT_COMMENTS
    global OUTPUT_HEADER
    global SHOW_EDITOR
    global PRECISION
    global PREAMBLE
    global POSTAMBLE
    global GetValue
    global FloatPrecision
    global DEGREES_FOR_AB

    args = parser.parse_args(shlex.split(argstring))

    if args.comments:
        OUTPUT_COMMENTS = True
    if args.inches:
        GetValue = getImperialValue
    if args.no_header:
        OUTPUT_HEADER = False
    if args.no_show_editor:
        SHOW_EDITOR = False
    if args.precision is not None:
        PRECISION = int(args.precision)
    FloatPrecision = f".{PRECISION}f" # always set
    if args.preamble is not None:
        PREAMBLE = args.preamble.replace('\\n','\n')
    if args.postamble is not None:
        POSTAMBLE = args.postamble.replace('\\n','\n')
    if args.ab_is_distance:
        DEGREES_FOR_AB = False

def export(objectslist, filename, argstring):
    global CurrentState

    processArguments(argstring)

    for obj in objectslist:
        if not hasattr(obj, "Path"):
            print( f"the object {obj.Name} is not a path. Please select only path and Compounds." )
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
    }
    print("postprocessing...")
    gcode = ""

    # write header
    if OUTPUT_HEADER:
        # not using comment(), the option overrides --comments for the header
        gcode += linenumber() + "'Exported by FreeCAD\n"
        gcode += linenumber() + "'Post Processor: " + __name__ + "\n"
        gcode += linenumber() + "'Output Time:" + str(now) + "\n"

    # Write the preamble
    gcode += comment("(begin preamble)", True)

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

    if PREAMBLE:
        preamble_lines = PREAMBLE.replace('\\n','\n').splitlines(False)
        preamble_commands = [ str_to_gcode(x) for x  in preamble_lines ]
        gcode += parse_list_of_commands( preamble_commands )

    for obj in objectslist:

        # do the pre_op
        gcode += comment(f"(begin operation: {obj.Label})", True)
        for line in PRE_OPERATION.splitlines(True):
            gcode += linenumber() + line

        gcode += parse(obj)

        # do the post_op
        gcode += comment(f"(finish operation: {obj.Label})", True)
        for line in POST_OPERATION.splitlines(True):
            gcode += linenumber() + line

    # do the post_amble
    gcode += comment("(begin postamble)", True)

    if POSTAMBLE:
        postamble_lines = POSTAMBLE.replace('\\n','\n').splitlines(False)
        postamble_commands = [ str_to_gcode(x) for x  in postamble_lines ]
        gcode += parse_list_of_commands( postamble_commands )

    if SHOW_EDITOR:
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


def move(command):
    txt = ""

    # if 'F' in command.Parameters:
    #     txt += feedrate(command)

    axis = ""
    for p in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W"): # can't do CUVW
        if p in command.Parameters:
            if command.Parameters[p] != CurrentState[p]:
                axis += p

    if "F" in command.Parameters:
        speed = command.Parameters["F"]
        if command.Name in {"G1", "G01"}:  # move
            movetype = "MS"
        else:  # jog
            movetype = "JS"
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
            txt += "{},{},{}\n".format(movetype, xyspeed, zspeed)

    if command.Name in {"G0", "G00"}:
        pref = "J"
    else:
        pref = "M"

    if len(axis) == 1:
        # axis string is key and command-second-letter
        txt += pref + axis
        if axis in {'A','B'} and DEGREES_FOR_AB:
            txt += "," + format(command.Parameters[axis], FloatPrecision)
        else:
            txt += "," + format(GetValue(command.Parameters[axis]), FloatPrecision)
        txt += "\n"
    elif axis == "XY":
        txt += pref + "2"
        txt += "," + format(GetValue(command.Parameters["X"]), FloatPrecision)
        txt += "," + format(GetValue(command.Parameters["Y"]), FloatPrecision)
        txt += "\n"
    elif axis in { "XZ", "YZ", "XYZ" }:
        # anything plus Z requires the 3 arg version
        txt += pref + "3"
        for key in ('X','Y','Z'):
            txt += "," + format(GetValue(command.Parameters[key]), FloatPrecision) if key in axis else ''
        txt += "\n"
    elif ('A' in axis or 'B' in axis) and len(axis)>1 and not next( ( c for c in 'CUVW' if c in axis), None):
        # AB+ needs "5" version (carefully excluding CUVW)
        # we could optimize to an M4 if just A
        txt += pref + "5"
        for key in ('X','Y','Z','A','B'):
            if key in {'A','B'} and DEGREES_FOR_AB:
                txt += "," + format(command.Parameters[key], FloatPrecision) if key in axis else ''
            else:
                txt += "," + format(GetValue(command.Parameters[key]), FloatPrecision) if key in axis else ''
        txt += "\n"
    elif axis == "":
        print("warning: skipping duplicate move.")
    else:
        print(CurrentState)
        print(command)
        print(f"I don't know how to handle '{axis}' for a move.")

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
    for line in TOOL_CHANGE.splitlines(True):
        txt += line
    txt += "&ToolName=" + str(int(command.Parameters["T"]))
    txt += "\n"
    txt += f"&Tool={int(command.Parameters['T'])}\n"
    txt += f"'Change tool to {int(command.Parameters['T'])}\n" # prompt
    txt += "PAUSE\n" # causes a modal to ask "ok?"
    return txt


def comment(command, keepparens=False):
    # comments from gcode are stripped of ()
    # comments we generate include ()
    if OUTPUT_COMMENTS:
        return f"'{command if keepparens else command[1:-1]}\n"
    else:
        print("a comment", command)
        return ''


def spindle(command):
    txt = ""
    if command.Name == "M3":  # CW
        pass
    else:
        pass
    txt += f"TR,{int(command.Parameters['S'])}\n"
    #txt += "C6\n" a custom cut 6, from the menu
    txt += f"'Change spindle speed to {int(command.Parameters['S'])}\n" # prompt
    txt += "PAUSE\n" # causes a modal to ask "ok?"

    return txt


# Supported Commands
scommands = {
    "G0": move,
    "G1": move,
    "G2": arc,
    "G3": arc,
    "M6": tool_change,
    "M3": spindle,
    "G00": move,
    "G01": move,
    "G02": arc,
    "G03": arc,
    "M06": tool_change,
    "M03": spindle,
    "message": comment,
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
        output += parse_list_of_commands( PathUtils.getPathWithPlacement(pathobj).Commands )
    return output

def parse_list_of_commands(commands):
    output = ""
    for c in commands:
        command = c.Name
        if command in scommands:
            output += scommands[command](c)
            if c.Parameters:
                CurrentState.update(c.Parameters)
        elif command.startswith("("):
            output += comment(command)
        else:
            print("I don't know what the command: ", end="")
            print(command + " means.  Maybe I should support it.")
    return output


def linenumber():
    return ""


# print(__name__ + " gcode postprocessor loaded.")

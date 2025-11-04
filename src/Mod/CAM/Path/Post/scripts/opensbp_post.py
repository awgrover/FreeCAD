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

import argparse
import datetime
import shlex
import Path
import Path.Post.Utils as PostUtils
import PathScripts.PathUtils as PathUtils
from builtins import open as pyopen


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

TOOLTIP_ARGS = parser.format_help()

OUTPUT_COMMENTS = False
OUTPUT_HEADER = True
SHOW_EDITOR = True
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

    args = parser.parse_args(shlex.split(argstring))

    if args.comments:
        OUTPUT_COMMENTS = True
    if args.inches:
        GetValue = getImperialValue
    if args.no_header:
        OUTPUT_HEADER = False
    if args.no_show_editor:
        SHOW_EDITOR = False
    if args.precision != None:
        PRECISION = int(args.precision)
    FloatPrecision = f".{PRECISION}f" # always set
    if args.preamble != None:
        PREAMBLE = args.preamble.replace('\\n','\n')
    if args.postamble != None:
        POSTAMBLE = args.postamble.replace('\\n','\n')

def export(objectslist, filename, argstring):
    global CurrentState

    processArguments(argstring)

    for obj in objectslist:
        if not hasattr(obj, "Path"):
            s = "the object " + obj.Name
            s += " is not a path. Please select only path and Compounds."
            print(s)
            return

    CurrentState = {
        "X": 0,
        "Y": 0,
        "Z": 0,
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
        gcode += linenumber() + "'Exported by FreeCAD\n"
        gcode += linenumber() + "'Post Processor: " + __name__ + "\n"
        gcode += linenumber() + "'Output Time:" + str(now) + "\n"

    # Write the preamble
    if OUTPUT_COMMENTS:
        gcode += linenumber() + "'(begin preamble)\n"

    def str_to_gcode(s):
        # one gcode
        # e.g. str_to_gcode("G0 X50")
        pc = Path.Command()
        print(f"### pc.setFromGCode('{s}')")
        try:
            pc.setFromGCode(s)
        except ValueError as e:
            # can't tell if it is really 'Badly formatted GCode argument', so just add our gcode to the message
            raise ValueError(f"{e.args[0]}: {s}", *(e.args[1:]))
        return pc

    if PREAMBLE:
        preamble_lines = PREAMBLE.replace('\\n','\n').splitlines(False)
        preamble_commands = [ str_to_gcode(x) or pc for x  in preamble_lines ]
        gcode += parse_list_of_commands( preamble_commands )

    for obj in objectslist:

        # do the pre_op
        if OUTPUT_COMMENTS:
            gcode += linenumber() + "'(begin operation: " + obj.Label + ")\n"
        for line in PRE_OPERATION.splitlines(True):
            gcode += linenumber() + line

        gcode += parse(obj)

        # do the post_op
        if OUTPUT_COMMENTS:
            gcode += linenumber() + "'(finish operation: " + obj.Label + ")\n"
        for line in POST_OPERATION.splitlines(True):
            gcode += linenumber() + line

    # do the post_amble
    if OUTPUT_COMMENTS:
        gcode += "'(begin postamble)\n"

    if POSTAMBLE:
        postamble_lines = POSTAMBLE.replace('\\n','\n').splitlines(False)
        postamble_commands = [ str_to_gcode(x) or pc for x  in postamble_lines ]
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
    if not filename == "-":
        gfile = pyopen(filename, "w")
        gfile.write(final)
        gfile.close()

    return final


def move(command):
    txt = ""

    # if 'F' in command.Parameters:
    #     txt += feedrate(command)

    axis = ""
    for p in ["X", "Y", "Z"]:
        if p in command.Parameters:
            if command.Parameters[p] != CurrentState[p]:
                axis += p

    if "F" in command.Parameters:
        speed = command.Parameters["F"]
        if command.Name in ["G1", "G01"]:  # move
            movetype = "MS"
        else:  # jog
            movetype = "JS"
        zspeed = ""
        xyspeed = ""
        if "Z" in axis:
            speedKey = "{}Z".format(movetype)
            speedVal = GetValue(speed)
            if CurrentState[speedKey] != speedVal:
                CurrentState[speedKey] = speedVal
                zspeed = "{:f}".format(speedVal)
        if ("X" in axis) or ("Y" in axis):
            speedKey = "{}XY".format(movetype)
            speedVal = GetValue(speed)
            if CurrentState[speedKey] != speedVal:
                CurrentState[speedKey] = speedVal
                xyspeed = "{:f}".format(speedVal)
        if zspeed or xyspeed:
            txt += "{},{},{}\n".format(movetype, xyspeed, zspeed)

    if command.Name in ["G0", "G00"]:
        pref = "J"
    else:
        pref = "M"

    if axis == "X":
        txt += pref + "X"
        txt += "," + format(GetValue(command.Parameters["X"]), FloatPrecision)
        txt += "\n"
    elif axis == "Y":
        txt += pref + "Y"
        txt += "," + format(GetValue(command.Parameters["Y"]), FloatPrecision)
        txt += "\n"
    elif axis == "Z":
        txt += pref + "Z"
        txt += "," + format(GetValue(command.Parameters["Z"]), FloatPrecision)
        txt += "\n"
    elif axis == "XY":
        txt += pref + "2"
        txt += "," + format(GetValue(command.Parameters["X"]), FloatPrecision)
        txt += "," + format(GetValue(command.Parameters["Y"]), FloatPrecision)
        txt += "\n"
    elif axis == "XZ":
        txt += pref + "3"
        txt += "," + format(GetValue(command.Parameters["X"]), FloatPrecision)
        txt += ","
        txt += "," + format(GetValue(command.Parameters["Z"]), FloatPrecision)
        txt += "\n"
    elif axis == "XYZ":
        txt += pref + "3"
        txt += "," + format(GetValue(command.Parameters["X"]), FloatPrecision)
        txt += "," + format(GetValue(command.Parameters["Y"]), FloatPrecision)
        txt += "," + format(GetValue(command.Parameters["Z"]), FloatPrecision)
        txt += "\n"
    elif axis == "YZ":
        txt += pref + "3"
        txt += ","
        txt += "," + format(GetValue(command.Parameters["Y"]), FloatPrecision)
        txt += "," + format(GetValue(command.Parameters["Z"]), FloatPrecision)
        txt += "\n"
    elif axis == "":
        print("warning: skipping duplicate move.")
    else:
        print(CurrentState)
        print(command)
        print("I don't know how to handle '{}' for a move.".format(axis))

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
    if OUTPUT_COMMENTS:
        txt += "'a tool change happens now\n"
    for line in TOOL_CHANGE.splitlines(True):
        txt += line
    txt += "&ToolName=" + str(int(command.Parameters["T"]))
    txt += "\n"
    txt += f"&Tool={int(command.Parameters['T'])}\n"
    txt += f"'Change tool to {int(command.Parameters['T'])}\n"
    txt += "PAUSE\n" # causes a modal to ask "ok?"
    return txt


def comment(command):
    print("a comment", command)
    return


def spindle(command):
    txt = ""
    if command.Name == "M3":  # CW
        pass
    else:
        pass
    txt += f"TR,{int(command.Parameters['S'])}\n"
    #txt += "C6\n" a custom cut 6, from the menu
    txt += f"'Change spindle speed to {int(command.Parameters['S'])}\n"
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
        if OUTPUT_COMMENTS:
            output += linenumber() + "'(compound: " + pathobj.Label + ")\n"
        for p in pathobj.Group:
            output += parse(p)
    else:  # parsing simple path
        # groups might contain non-path things like stock.
        if not hasattr(pathobj, "Path"):
            return output
        if OUTPUT_COMMENTS:
            output += linenumber() + "'(Path: " + pathobj.Label + ")\n"
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
            output += "' " + command + "\n"
        else:
            print("I don't know what the command: ", end="")
            print(command + " means.  Maybe I should support it.")
    return output


def linenumber():
    return ""


# print(__name__ + " gcode postprocessor loaded.")

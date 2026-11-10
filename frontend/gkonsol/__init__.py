"""gkonsol: the GEE-Assist command line.

A terminal panel at the bottom of the signed-in window, like the one in VS Code. Its
commands are its own: they run inside GEE-Assist, not in Windows Terminal, PowerShell
or cmd. See docs/GKONSOL.md for every command.

The parts:

* ``text``      styled text and drawings made of characters (progress bars, charts, tables)
* ``parser``    splitting a command line into words and options
* ``command``   command definitions and the registry
* ``effects``   what a long-running command can wait for (a background task, a pause, an answer)
* ``runner``    runs one command at a time and delivers what it waited for
* ``output``    what commands print to
* ``history``   the commands typed before, kept between sessions
* ``shell``     reads a typed line, runs the command, completes words with Tab
* ``commands``  the commands themselves
* ``panel``     the Qt widgets of the terminal panel
"""

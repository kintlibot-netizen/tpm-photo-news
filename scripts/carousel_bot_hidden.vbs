' TPM Carousel Bot, started by the Windows task "TPM Carousel Bot" with no window at all.
' It runs scripts\carousel_bot.py with the project's Python in a hidden console, so the Claude, git and Chromium
' steps it starts stay hidden too. No prompt, no pause. The log is logs\carousel-bot.log.
' --no-claude: Claude is never called; only stories with a written plan (data\plans) are built.
Option Explicit
Dim fso, shell, root, python, script
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
python = root & "\.venv\Scripts\python.exe"
If Not fso.FileExists(python) Then python = "python"
script = root & "\scripts\carousel_bot.py"
shell.CurrentDirectory = root
shell.Run """" & python & """ """ & script & """ --no-claude", 0, True

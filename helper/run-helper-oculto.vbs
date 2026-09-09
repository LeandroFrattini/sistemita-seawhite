' Arranca el ayudante SIN ventana. Lo usa la tarea programada.
Dim sh, fso, here, py
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)

py = here & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then py = "pythonw"

sh.CurrentDirectory = here
sh.Run """" & py & """ """ & here & "\lineup_mailer.py""", 0, False

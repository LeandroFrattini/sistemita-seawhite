' Arranca la app SIN ventana negra. Lo usa la tarea programada.
Dim sh, fso, here
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)

Dim py
py = here & "\.venv\Scripts\python.exe"
If Not fso.FileExists(py) Then py = "python"

sh.CurrentDirectory = here
sh.Run """" & py & """ -m uvicorn app.main:app --host 0.0.0.0 --port 8010", 0, False

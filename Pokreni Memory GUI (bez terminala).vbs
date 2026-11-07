' Pokrece memorijski GUI bez terminala.
'
' "Pokreni Memory GUI.bat" ostaje kakav je -- on je i dalje nacin da se vidi
' ispis uzivo i da se instalira Python ako ga nema. Ovo je isti posao bez
' prozora: pythonw.exe ne otvara konzolu, a cmd koji ga pokrece radi sakriven
' (drugi argument Run-a je 0) samo zato da bi ispis mogao da se preusmeri.
'
' Ispis se NE gubi: sve ide u Debug\memory_gui_last_run.log. Bez toga bi GUI
' koji pukne pri pokretanju nestao bez ijedne poruke -- a to je najgori nacin
' da nesto ne radi.

Option Explicit

Dim fso, shell, base, pythonw, logPath, command

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = FindPythonw(fso, shell)

If pythonw = "" Then
    ' Nema sta da se pokrene tiho. BAT zna da nadje/instalira Python, ali za to
    ' mora nesto da pita -- a pitanje u sakrivenom prozoru je zaglavljen program.
    ' Zato se ovde predaje njemu, vidljivo.
    shell.Run """" & base & "\Pokreni Memory GUI.bat""", 1, False
    WScript.Quit 0
End If

If Not fso.FolderExists(base & "\Debug") Then
    fso.CreateFolder base & "\Debug"
End If
logPath = base & "\Debug\memory_gui_last_run.log"

shell.CurrentDirectory = base
command = "cmd /c """"" & pythonw & """ """ & base & "\memory_gui.py"" > """ _
    & logPath & """ 2>&1"""
shell.Run command, 0, False

' Isti redosled koji trazi python_for_windows.bat: 3.11 na Windows 10/11, 3.8
' na Windows 7. Trazi se pythonw.exe pored python.exe -- standardna instalacija
' ih drzi zajedno.
Function FindPythonw(fso, shell)
    Dim programs, candidates, i

    FindPythonw = ""
    programs = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\"
    candidates = Array( _
        programs & "Python311\pythonw.exe", _
        programs & "Python38\pythonw.exe")

    For i = 0 To UBound(candidates)
        If fso.FileExists(candidates(i)) Then
            FindPythonw = candidates(i)
            Exit Function
        End If
    Next
End Function

import subprocess

script = """
Add-Type -AssemblyName System.Speech
try {
    $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    $engine.SetInputToDefaultAudioDevice()
    $grammar = New-Object System.Speech.Recognition.DictationGrammar
    $engine.LoadGrammar($grammar)
    Write-Output "Mic audio device ready"
} catch {
    Write-Output "Error: $_"
}
"""

res = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
print("Return code:", res.returncode)
print("Output:", res.stdout.strip())

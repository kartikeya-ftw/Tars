import subprocess

script = """
Add-Type -AssemblyName System.Speech
try {
    $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
    $engine.SetInputToDefaultAudioDevice()
    $grammar = New-Object System.Speech.Recognition.DictationGrammar
    $engine.LoadGrammar($grammar)
    # Recognize with 4-second timeout
    $res = $engine.Recognize([System.TimeSpan]::FromSeconds(4))
    if ($res) {
        Write-Output "HEARD: $($res.Text)"
    } else {
        Write-Output "TIMEOUT (No speech detected in 4s)"
    }
} catch {
    Write-Output "ERROR: $_"
}
"""

print("Testing STT recognition engine timeout...")
res = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
print("Return code:", res.returncode)
print("Output:", res.stdout.strip())

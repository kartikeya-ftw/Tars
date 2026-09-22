import subprocess
import time

def speak(text: str):
    # Escape quotes
    safe_text = text.replace('"', '""').replace("'", "''")
    ps_cmd = f"""
    Add-Type -AssemblyName System.Speech
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    # Try to pick a male voice like David
    try {{
        $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Male)
    }} catch {{}}
    $s.Rate = 0
    $s.Speak("{safe_text}")
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True)

print("Testing speak...")
t0 = time.time()
speak("Greetings, Cooper. Tactical Automated Robot System voice module online.")
print(f"Spoke in {time.time() - t0:.2f} seconds.")

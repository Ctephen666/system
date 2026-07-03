"""Local wake-word acknowledgement TTS.

This module is intentionally small and optional: on Windows it uses the
system SAPI voice through pywin32; on unsupported platforms it quietly falls
back to logging so the wake flow is not blocked.
"""

from __future__ import annotations

import sys
import subprocess
import threading

from src.logging import get_logger

logger = get_logger()


def _wake_log(event: str, **fields) -> str:
    parts = [f"事件={event}"]
    parts.extend(f"{key}={value}" for key, value in fields.items() if value is not None)
    return "[WakeWord] " + " | ".join(parts)


class WakeAckTTS:
    """Non-blocking local TTS for short wake acknowledgements."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def speak(self, text: str) -> bool:
        """Speak text in a daemon thread and return whether playback was started."""
        text = (text or "").strip()
        if not text:
            return False

        if sys.platform != "win32":
            logger.info(_wake_log("本地TTS不可用", 原因="仅支持 Windows"))
            return False

        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.debug(_wake_log("本地TTS跳过", 原因="上一段仍在播放"))
                return False

            self._thread = threading.Thread(
                target=self._speak_windows_sapi,
                args=(text,),
                daemon=True,
                name="WakeAckTTS",
            )
            self._thread.start()
            return True

    def _speak_windows_sapi(self, text: str) -> None:
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                voice.Speak(text)
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            logger.warning(_wake_log("本地TTS失败", 引擎="pywin32 SAPI", 后续动作="尝试 System.Speech", 错误=e))
            self._speak_windows_system_speech(text)

    def _speak_windows_system_speech(self, text: str) -> None:
        try:
            script = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Speak([Console]::In.ReadToEnd())"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception as e:
            logger.warning(_wake_log("本地TTS失败", 引擎="System.Speech", 错误=e))


_wake_ack_tts = WakeAckTTS()


def speak_wake_ack(text: str) -> bool:
    """Start local wake acknowledgement TTS if the platform supports it."""
    return _wake_ack_tts.speak(text)

"""Utilidades de teste (só biblioteca padrão)."""
import wave


def wav(path, segundos: float, taxa: int = 8000, canais: int = 1) -> str:
    """Grava um WAV 16 bits em silêncio com a duração pedida (para testar a leitura da duração)."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(b"\x00\x00" * canais * int(taxa * segundos))
    return str(path)

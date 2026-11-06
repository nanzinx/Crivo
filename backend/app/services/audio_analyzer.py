"""Extração de metadados acústicos básicos do arquivo (sem dependência de ffmpeg)."""
from pathlib import Path


def analyze(path: str | Path) -> dict:
    p = Path(path)
    out: dict = {"tamanho_bytes": p.stat().st_size if p.exists() else 0}
    try:
        from mutagen import File as MFile

        mf = MFile(str(p))
        if mf is not None and mf.info is not None:
            out["duracao_segundos"] = round(float(mf.info.length), 2)
            out["bitrate"] = getattr(mf.info, "bitrate", None)
            out["canais"] = getattr(mf.info, "channels", None)
            out["sample_rate"] = getattr(mf.info, "sample_rate", None)
    except Exception as e:  # arquivo corrompido
        out["erro_leitura"] = str(e)
    d = out.get("duracao_segundos") or 0
    out["audio_muito_curto"] = d < 3.0
    return out

"""Análise local do áudio, sem IA e sem custo: duração, canais e quanto de fala existe (VAD).

A detecção de fala é propositalmente CONSERVADORA: na dúvida, considera que há fala, para a ligação
seguir para a IA. Só áudio realmente sem atividade é tratado como mudo. Ruído forte, música ou tom
de chamada contam como "fala" aqui; quem decide o que é cada coisa é a IA.
"""
from pathlib import Path

from ..config import settings

TAXA = 8000  # telefonia
QUADRO = 240  # 30 ms
MAX_SEGUNDOS = 30 * 60  # analisa no máximo 30 min


def _decodificar(path: str):
    """Devolve array int16 (amostras, canais) a 8 kHz. Usa PyAV (FFmpeg embutido)."""
    import av
    import numpy as np

    with av.open(path) as cont:
        stream = next(s for s in cont.streams if s.type == "audio")
        canais = min(2, stream.codec_context.channels or 1)
        res = av.AudioResampler(format="s16", layout="stereo" if canais == 2 else "mono", rate=TAXA)
        partes, total = [], 0
        for frame in cont.decode(stream):
            for f in res.resample(frame):
                a = f.to_ndarray().reshape(-1, canais)  # s16 intercalado
                partes.append(a)
                total += len(a)
            if total > MAX_SEGUNDOS * TAXA:
                break
        for f in res.resample(None):  # esvazia o resampler
            partes.append(f.to_ndarray().reshape(-1, canais))
    if not partes:
        raise ValueError("áudio sem amostras")
    return np.concatenate(partes)


def _atividade(x) -> "np.ndarray":  # noqa: F821
    """Máscara booleana por quadro de 30 ms: True onde há atividade sonora acima do chiado de fundo."""
    import numpy as np

    n = len(x) // QUADRO
    if n == 0:
        return np.zeros(0, dtype=bool)
    q = x[: n * QUADRO].astype(np.float64).reshape(n, QUADRO)
    db = 20 * np.log10(np.sqrt((q ** 2).mean(axis=1)) / 32768 + 1e-9)
    # Limiar = chiado de fundo + 10 dB, preso entre -55 e -40 dBFS:
    # - nada acima de -40 dBFS é tratado como silêncio (voz baixa, ruído e tons seguem para a IA);
    # - uma ligação inteira de fala contínua não "sobe o piso" a ponto de ser descartada;
    # - abaixo de -55 dBFS é sempre silêncio (chiado de linha digital).
    limiar = min(max(float(np.percentile(db, 10)) + 10.0, -55.0), -40.0)
    ativo = db > limiar
    # descarta estalos isolados (< 90 ms)
    viz = np.convolve(ativo.astype(int), np.ones(3, dtype=int), mode="same")
    return ativo & (viz >= 2)


def _canais_separados(x) -> bool:
    """Estéreo de verdade (operador num canal, cliente no outro)? Se os dois canais são quase
    iguais, é um mono duplicado e não dá para dizer quem falou."""
    import numpy as np

    a, b = x[:, 0].astype(np.float64), x[:, 1].astype(np.float64)
    if a.std() < 1 or b.std() < 1:  # um lado praticamente zerado: são canais distintos
        return True
    return abs(float(np.corrcoef(a, b)[0, 1])) < 0.9


def analyze(path: str | Path) -> dict:
    p = Path(path)
    out: dict = {"tamanho_bytes": p.stat().st_size if p.exists() else 0, "vad": False}
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

    if settings.vad_ativo and out["tamanho_bytes"]:
        try:
            x = _decodificar(str(p))
            mascaras = [_atividade(x[:, c]) for c in range(x.shape[1])]
            geral = mascaras[0] if len(mascaras) == 1 else (mascaras[0] | mascaras[1])
            seg = QUADRO / TAXA
            out["canais"] = x.shape[1]
            out["duracao_segundos"] = out.get("duracao_segundos") or round(len(x) / TAXA, 2)
            out["fala_segundos"] = round(float(geral.sum()) * seg, 2)
            if len(mascaras) == 2 and _canais_separados(x):
                out["fala_por_canal"] = [round(float(m.sum()) * seg, 2) for m in mascaras]
            out["vad"] = True
            out.pop("erro_leitura", None)
        except Exception as e:  # não decodificou: sem VAD, a ligação segue para a IA
            out["erro_vad"] = str(e)[:200]

    out["audio_muito_curto"] = (out.get("duracao_segundos") or 0) < 3.0
    return out

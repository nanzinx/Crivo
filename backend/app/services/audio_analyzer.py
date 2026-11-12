"""Tratamento local do áudio, sem IA e sem custo.

1. `analyze`: duração, canais e quanto de fala existe (VAD), inclusive por lado no estéreo.
2. `preparar_para_transcricao`: monta o que será enviado para a IA, pagando menos minutos:
   - corta silêncio e espera longos (a transcrição é cobrada por duração);
   - no estéreo com as pontas separadas, gera um áudio por lado (operador / cliente), cada um
     sem o silêncio de quando o outro fala. Assim sabemos quem disse o quê sem pedir à IA.

Tudo aqui é propositalmente CONSERVADOR: na dúvida, considera que há fala e mantém o trecho.
Ruído forte, música ou tom de chamada contam como "fala"; quem decide o que é cada coisa é a IA.
"""
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..config import settings

log = logging.getLogger("audio")

TAXA = 16000  # taxa de trabalho (a mesma que os modelos de transcrição usam por dentro)
QUADRO = 480  # 30 ms
MAX_SEGUNDOS = 30 * 60  # analisa no máximo 30 min
LIMITE_BYTES = 24 * 1024 * 1024  # a API de transcrição aceita arquivos de até 25 MB


# --------------------------------------------------------------------------- leitura e medição
def carregar(path: str):
    """Devolve array int16 (amostras, canais) a 16 kHz. Usa PyAV (FFmpeg embutido)."""
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


def _nivel_db(x):
    """Nível (dBFS) de cada quadro de 30 ms."""
    import numpy as np

    n = len(x) // QUADRO
    if n == 0:
        return np.zeros(0)
    q = x[: n * QUADRO].astype(np.float64).reshape(n, QUADRO)
    return 20 * np.log10(np.sqrt((q ** 2).mean(axis=1)) / 32768 + 1e-9)


def _sem_estalos(ativo):
    import numpy as np

    viz = np.convolve(ativo.astype(int), np.ones(3, dtype=int), mode="same")
    return ativo & (viz >= 2)  # descarta estalos isolados (< 90 ms)


def _atividade(x):
    """Onde há FALA (para medir): atividade sonora claramente acima do chiado de fundo.

    Limiar = chiado + 10 dB, preso entre -55 e -40 dBFS:
    - nada acima de -40 dBFS é tratado como silêncio (voz baixa, ruído e tons seguem para a IA);
    - uma ligação inteira de fala contínua não "sobe o piso" a ponto de ser descartada;
    - abaixo de -55 dBFS é sempre silêncio (chiado de linha digital).
    """
    import numpy as np

    db = _nivel_db(x)
    if not len(db):
        return np.zeros(0, dtype=bool)
    limiar = min(max(float(np.percentile(db, 10)) + 10.0, -55.0), -40.0)
    return _sem_estalos(db > limiar)


def _nao_e_silencio(x):
    """Onde NÃO dá para garantir silêncio (para cortar): bem mais sensível que `_atividade`.

    Só é considerado silêncio o que fica colado no chiado de fundo (até 5 dB acima, limite entre
    -60 e -45 dBFS). Qualquer coisa acima disso é mantida, com 90 ms de folga de cada lado.
    """
    import numpy as np

    db = _nivel_db(x)
    if not len(db):
        return np.zeros(0, dtype=bool)
    limiar = min(max(float(np.percentile(db, 10)) + 5.0, -60.0), -45.0)
    return np.convolve((db > limiar).astype(int), np.ones(7, dtype=int), mode="same") > 0


def _canais_separados(x) -> bool:
    """Estéreo de verdade (operador num canal, cliente no outro)? Se os dois canais são quase
    iguais, é um mono duplicado e não dá para dizer quem falou."""
    import numpy as np

    a, b = x[:, 0].astype(np.float64), x[:, 1].astype(np.float64)
    if a.std() < 1 or b.std() < 1:  # um lado praticamente zerado: são canais distintos
        return True
    return abs(float(np.corrcoef(a, b)[0, 1])) < 0.9


def _mono(x):
    import numpy as np

    return x[:, 0] if x.shape[1] == 1 else x.astype(np.int32).mean(axis=1).astype(np.int16)


# --------------------------------------------------------------------------- corte de silêncio
def _manter(ocupado, pausa_min_s: float, margem_s: float):
    """Máscara por quadro do que fica: tudo, menos o miolo dos silêncios de pelo menos `pausa_min_s`
    (de cada um sobra `margem_s` em cada ponta, para as palavras não grudarem)."""
    import numpy as np

    manter = np.ones(len(ocupado), dtype=bool)
    seg = QUADRO / TAXA
    pausa, margem = int(round(pausa_min_s / seg)), int(round(margem_s / seg))
    i, n = 0, len(ocupado)
    while i < n:
        if ocupado[i]:
            i += 1
            continue
        j = i
        while j < n and not ocupado[j]:
            j += 1
        if j - i >= pausa:
            manter[i + margem: j - margem] = False
        i = j
    return manter


def _cortar(x, pausa_min_s: float, margem_s: float):
    """Remove o miolo dos silêncios longos de um canal (array 1-D int16)."""
    import numpy as np

    manter = _manter(_nao_e_silencio(x), pausa_min_s, margem_s)
    n = len(manter) * QUADRO
    return np.concatenate([x[:n][np.repeat(manter, QUADRO)], x[n:]])


def _gravar_flac(x, sufixo: str) -> str:
    """Grava um canal (int16, 16 kHz) num FLAC temporário (sem perda, bem menor que WAV)."""
    import av

    fd, path = tempfile.mkstemp(prefix="crivo_", suffix=f"_{sufixo}.flac")
    os.close(fd)
    try:
        with av.open(path, "w", format="flac") as cont:
            st = cont.add_stream("flac", rate=TAXA)
            st.layout, st.format = "mono", "s16"
            frame = av.AudioFrame.from_ndarray(x.reshape(1, -1), format="s16", layout="mono")
            frame.sample_rate = TAXA
            for pkt in st.encode(frame):
                cont.mux(pkt)
            for pkt in st.encode(None):
                cont.mux(pkt)
        if os.path.getsize(path) > LIMITE_BYTES:
            raise ValueError("arquivo tratado maior que o limite de envio")
    except Exception:
        os.remove(path)
        raise
    return path


@dataclass
class Parte:
    """Um áudio a transcrever. `lado` é ATENDENTE/CLIENTE no estéreo separado, ou None (ligação inteira)."""

    lado: str | None
    arquivo: str | None  # None = este lado não tem fala: nada a transcrever
    segundos: float  # duração enviada (é o que se paga)
    segundos_original: float  # duração da gravação
    temporario: bool = False


def limpar(partes: list[Parte]) -> None:
    for p in partes:
        if p.temporario and p.arquivo:
            try:
                os.remove(p.arquivo)
            except OSError:
                pass


# pausas: na ligação inteira só se corta espera longa (>= 2 s). Em um lado isolado do estéreo o
# silêncio é o tempo em que o OUTRO fala, então o corte pode ser mais curto (>= 0,8 s).
_PAUSA_INTEIRA, _MARGEM_INTEIRA = 2.0, 0.5
_PAUSA_LADO, _MARGEM_LADO = 0.8, 0.3


def preparar_para_transcricao(path: str) -> list[Parte]:
    """Decide o que enviar para a transcrição. Em qualquer problema, devolve o arquivo original."""
    try:
        x = carregar(path)
    except Exception as e:
        log.info("sem pré-processamento para %s: %s", path, e)
        return [Parte(None, path, 0.0, 0.0)]
    total = len(x) / TAXA
    if total >= MAX_SEGUNDOS:  # gravação maior que o limite de análise: não mexe, para não perder o final
        return [Parte(None, path, total, total)]
    try:
        if x.shape[1] == 2 and settings.transcricao_por_canal and _canais_separados(x):
            partes = []
            for canal in (0, 1):
                lado = "ATENDENTE" if canal == settings.argus_canal_operador else "CLIENTE"
                c = x[:, canal]
                if float(_atividade(c).sum()) * QUADRO / TAXA < settings.vad_fala_minima_segundos:
                    partes.append(Parte(lado, None, 0.0, total))
                    continue
                cortado = _cortar(c, _PAUSA_LADO, _MARGEM_LADO)
                partes.append(Parte(lado, _gravar_flac(cortado, lado), len(cortado) / TAXA, total, True))
            if any(p.arquivo for p in partes):
                return partes
            limpar(partes)
        if settings.cortar_silencio:
            mono = _mono(x)
            cortado = _cortar(mono, _PAUSA_INTEIRA, _MARGEM_INTEIRA)
            if len(cortado) <= 0.9 * len(mono):  # só vale recodificar se economizar pelo menos 10%
                return [Parte(None, _gravar_flac(cortado, "inteira"), len(cortado) / TAXA, total, True)]
    except Exception:
        log.exception("falha ao preparar %s; enviando o arquivo original", path)
    return [Parte(None, path, total, total)]


# --------------------------------------------------------------------------- análise
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
            x = carregar(str(p))
            mascaras = [_atividade(x[:, c]) for c in range(x.shape[1])]
            geral = mascaras[0] if len(mascaras) == 1 else (mascaras[0] | mascaras[1])
            seg = QUADRO / TAXA
            out["canais"] = x.shape[1]
            out["duracao_segundos"] = out.get("duracao_segundos") or round(len(x) / TAXA, 2)
            out["fala_segundos"] = round(float(geral.sum()) * seg, 2)
            if len(mascaras) == 2 and _canais_separados(x):
                out["fala_por_canal"] = [round(float(m.sum()) * seg, 2) for m in mascaras]
            # quanto sobraria depois do corte de silêncio (estimativa, não grava nada)
            manter = _manter(_nao_e_silencio(_mono(x)), _PAUSA_INTEIRA, _MARGEM_INTEIRA)
            out["duracao_apos_corte"] = round(float(manter.sum()) * seg + (len(x) % QUADRO) / TAXA, 2)
            out["vad"] = True
            out.pop("erro_leitura", None)
        except Exception as e:  # não decodificou: sem VAD, a ligação segue para a IA
            out["erro_vad"] = str(e)[:200]

    out["audio_muito_curto"] = (out.get("duracao_segundos") or 0) < 3.0
    return out

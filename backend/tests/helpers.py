"""Utilidades de teste: gera áudios sintéticos e substitui a IA."""
import wave

import numpy as np

from app.config import settings
from app.services import ai_qualifier

SR = 8000


def wav(path, canais: list[np.ndarray]):
    """Grava um WAV 8 kHz/16 bits com 1 ou 2 canais (arrays float -1..1)."""
    data = np.stack(canais, axis=1) if len(canais) > 1 else canais[0][:, None]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())
    return str(path)


def silencio(seg: float) -> np.ndarray:
    return np.random.default_rng(1).normal(0, 0.0005, int(seg * SR))  # chiado de linha bem baixo


def fala(seg_total: float, inicio: float, dur: float, seed=2) -> np.ndarray:
    """Silêncio com um trecho de 'voz' (ruído forte) entre inicio e inicio+dur."""
    x = silencio(seg_total).copy()
    a, b = int(inicio * SR), int((inicio + dur) * SR)
    x[a:b] = np.random.default_rng(seed).normal(0, 0.2, b - a)
    return x


class IAFalsa:
    """Substitui a OpenAI nos testes."""

    def __init__(self, monkeypatch, resposta=None, tokens=(1200, 100), falha_classificacao=False):
        self.transcricoes = self.classificacoes = 0
        self.arquivos: list[str] = []  # caminhos enviados para transcrição
        self.textos: list[str] = []  # textos enviados para classificação
        self.fala_por_arquivo = None  # opcional: função caminho -> texto
        monkeypatch.setattr(settings, "openai_api_key", "sk-teste")
        monkeypatch.setattr(ai_qualifier, "_cliente_openai", lambda: object())
        monkeypatch.setattr(ai_qualifier, "transcrever_audio", self._transcrever)
        monkeypatch.setattr(ai_qualifier, "_classificar_texto", self._classificar)
        self.resposta = resposta or ai_qualifier.RespostaIA(
            categoria="SEM_INTERESSE", subcategoria="CLIENTE_CALMO", confianca=0.9, resumo="recusou",
            evidencia="não tenho interesse")
        self.tokens, self.falha = tokens, falha_classificacao

    def _transcrever(self, client, path, modelo=None):
        self.transcricoes += 1
        self.arquivos.append(str(path))
        if self.fala_por_arquivo:
            return self.fala_por_arquivo(str(path))
        return "alô, não tenho interesse, obrigado"

    def _classificar(self, client, texto, nome, tel, dur, modelo=None):
        self.classificacoes += 1
        self.textos.append(texto)
        if self.falha:
            raise RuntimeError("429 rate limit")
        return self.resposta, *self.tokens

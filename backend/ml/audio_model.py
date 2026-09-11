"""Audio anti-spoofing model v1 — LCNN-style CNN over log-Mel crops.

Architecture (Light CNN / MFM as in the ASVspoof 2019 countermeasure
literature, trimmed for CPU quick training):

    CNN branch   [1, 80, T] -> [Conv2d -> MFM -> MaxPool] x5 -> BN2d ->
                 global mean+std pool -> 128-dim
    helper branch 6 handcrafted statistics -> Linear(6 -> 32) -> ReLU
    fused head    Linear(160 -> 64) -> ReLU -> Dropout -> Linear(64 -> 1) logit

Single logit trained with class-weighted BCEWithLogitsLoss (0 = bona fide,
1 = fake/spoof). The helper branch is standardised with the training-set
mean/std that ship inside the artifact, so inference never needs a separate
scaler file.

The same class is used by ml/train_audio_v1.py and
app/services/ml_inference.py (deployment), guaranteeing train/serve parity.
"""

from __future__ import annotations

import torch
import torch.nn as nn

HANDCRAFT_DIM = 6


def mfm(x: torch.Tensor) -> torch.Tensor:
    """Max-Feature-Map: max over channel pairs (halves the channel count)."""
    if x.size(1) % 2 != 0:
        raise ValueError(f"MFM needs an even channel count, got {x.size(1)}")
    half = x.size(1) // 2
    return torch.max(x[:, :half], x[:, half:])


class LCNNBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, kernel_size, padding, pool):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, padding=padding)
        self.pool = nn.MaxPool2d(pool)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.pool(mfm(torch.relu(self.conv(x))))


class AudioLCNNV1(nn.Module):
    """LCNN-style log-Mel CNN fused with a 6-dim handcrafted-statistics branch."""

    def __init__(self, handcraft_dim: int = HANDCRAFT_DIM, dropout: float = 0.3):
        super().__init__()
        self.blocks = nn.Sequential(
            LCNNBlock(1, 64, (5, 5), 2, (2, 2)),        # -> [32, 40, T/2]
            LCNNBlock(32, 64, (1, 3), (0, 1), (2, 2)),  # -> [32, 20, T/4]
            LCNNBlock(32, 96, (3, 3), 1, (2, 2)),       # -> [48, 10, T/8]
            LCNNBlock(48, 96, (1, 3), (0, 1), (2, 2)),  # -> [48, 5, T/16]
            LCNNBlock(48, 128, (3, 3), 1, (2, 2)),      # -> [64, 2, T/32]
        )
        self.bn = nn.BatchNorm2d(64)  # over the feature map — safe for any batch size
        self.handcraft_branch = nn.Sequential(
            nn.Linear(handcraft_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 32),
            nn.ReLU(),
        )
        self.head = nn.Sequential(
            nn.Linear(64 * 2 + 32, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1),
        )

    def forward(self, logmel: torch.Tensor, handcraft: torch.Tensor) -> torch.Tensor:
        """logmel [B, 1, 80, T] (normalised dB), handcraft [B, 6] (standardised)."""
        x = self.bn(self.blocks(logmel))
        mean = x.mean(dim=(2, 3))
        std = x.std(dim=(2, 3)).clamp_min(1e-6)
        features = torch.cat([mean, std, self.handcraft_branch(handcraft)], dim=1)
        return self.head(features).squeeze(-1)


def load_audio_artifact(path):
    """Load an artifact saved by train_audio_v1 (state_dict + scaler stats).

    Returns (model, handcraft_mean, handcraft_std).
    """
    bundle = torch.load(path, map_location="cpu", weights_only=False)
    state = bundle.get("state_dict", bundle)
    model = AudioLCNNV1()
    model.load_state_dict(state)
    model.eval()
    return (
        model,
        bundle.get("handcraft_mean"),
        bundle.get("handcraft_std"),
    )

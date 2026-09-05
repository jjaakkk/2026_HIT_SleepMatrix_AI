"""Compact U-Net for six-class body-region segmentation on 44x24 frames.

The architecture follows the encoder-decoder design commonly used for
pressure-mat body-part segmentation in the referenced literature, scaled down
for the small 44x24 sensor grid so that training and inference run on CPU:

- two downsampling stages (44x24 -> 22x12 -> 11x6),
- a dilated bottleneck that keeps a large receptive field over the body axis,
- skip connections that restore the exact region boundaries.
"""

from __future__ import annotations

import torch
from torch import nn

from .partition import NUM_CLASSES


class ConvBlock(nn.Module):
    """Two ``conv 3x3 -> batchnorm -> relu`` layers with unchanged size."""

    def __init__(self, in_channels: int, out_channels: int, dilation: int = 1) -> None:
        super().__init__()
        padding = dilation
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=padding, dilation=dilation, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=padding, dilation=dilation, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class BodyPartitionUNet(nn.Module):
    """U-Net mapping ``(batch, 1, 44, 24)`` to ``(batch, 6, 44, 24)`` logits."""

    def __init__(self, in_channels: int = 1, num_classes: int = NUM_CLASSES, base_channels: int = 24) -> None:
        super().__init__()
        c = base_channels
        self.enc1 = ConvBlock(in_channels, c)
        self.enc2 = ConvBlock(c, c * 2)
        self.bottleneck = ConvBlock(c * 2, c * 4, dilation=2)
        self.dec2 = ConvBlock(c * 4 + c * 2, c * 2)
        self.dec1 = ConvBlock(c * 2 + c, c)
        self.head = nn.Conv2d(c, num_classes, kernel_size=1)
        self.pool = nn.MaxPool2d(2)
        self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        skip1 = self.enc1(x)
        skip2 = self.enc2(self.pool(skip1))
        coded = self.bottleneck(self.pool(skip2))
        up2 = torch.cat([self.up(coded), skip2], dim=1)
        up1 = torch.cat([self.up(self.dec2(up2)), skip1], dim=1)
        return self.head(self.dec1(up1))


def count_parameters(model: nn.Module) -> int:
    """Number of trainable parameters, reported in the training summary."""

    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)

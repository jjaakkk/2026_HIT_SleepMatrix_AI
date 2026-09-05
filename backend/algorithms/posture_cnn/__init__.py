"""基于二维卷积神经网络的四分类睡姿识别模块。"""

from .model import PostureCNN, build_model

__all__ = ["PostureCNN", "build_model"]

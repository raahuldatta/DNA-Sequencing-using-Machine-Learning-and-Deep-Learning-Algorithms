"""
Machine Learning and Deep Learning models for DNA Sequence Classification.
Includes standard ML classifiers (Decision Tree, Random Forest, Naive Bayes, Linear SVM)
and Deep Learning architectures (1D-CNN and DNA Transformer).
"""

from typing import Optional, Union, Dict, Any
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC


def create_ml_model(model_name: str, **kwargs) -> Any:
    """
    Factory function to instantiate Machine Learning classifiers.

    Args:
        model_name: One of ['naive_bayes', 'random_forest', 'decision_tree', 'svm']
        **kwargs: Additional hyperparameters passed to estimator.

    Returns:
        Configured scikit-learn estimator.
    """
    name = model_name.lower().replace(" ", "_")
    if name in ["naive_bayes", "nb", "multinomial_nb"]:
        alpha = kwargs.pop("alpha", 0.1)
        return MultinomialNB(alpha=alpha, **kwargs)
    elif name in ["random_forest", "rf"]:
        n_estimators = kwargs.pop("n_estimators", 50)
        random_state = kwargs.pop("random_state", 42)
        n_jobs = kwargs.pop("n_jobs", -1)
        max_features = kwargs.pop("max_features", "sqrt")
        return RandomForestClassifier(
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=random_state,
            n_jobs=n_jobs,
            **kwargs,
        )
    elif name in ["decision_tree", "dt"]:
        random_state = kwargs.pop("random_state", 42)
        return DecisionTreeClassifier(random_state=random_state, **kwargs)
    elif name in ["svm", "svc", "linear_svc"]:
        C = kwargs.pop("C", 0.5)
        kwargs.pop("kernel", None)
        random_state = kwargs.pop("random_state", 42)
        return LinearSVC(C=C, random_state=random_state, max_iter=2000, **kwargs)
    else:
        raise ValueError(f"Unknown ML model name: {model_name}")


class DNA_CNN1D(nn.Module):
    """
    1D Convolutional Neural Network for DNA Sequence Classification.
    Accepts input tensor of shape (batch_size, seq_len, 4) or (batch_size, 4, seq_len).
    """

    def __init__(
        self,
        seq_len: int = 50,
        in_channels: int = 4,
        num_classes: int = 7,
        num_filters: int = 32,
        kernel_size: int = 12,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.seq_len = seq_len
        self.in_channels = in_channels

        # Conv Block 1
        self.conv1 = nn.Conv1d(
            in_channels=in_channels,
            out_channels=num_filters,
            kernel_size=kernel_size,
            padding=kernel_size // 2,
        )
        self.bn1 = nn.BatchNorm1d(num_filters)
        self.pool1 = nn.MaxPool1d(kernel_size=4, stride=4)
        self.drop1 = nn.Dropout(dropout)

        # Conv Block 2
        self.conv2 = nn.Conv1d(
            in_channels=num_filters,
            out_channels=num_filters * 2,
            kernel_size=5,
            padding=2,
        )
        self.bn2 = nn.BatchNorm1d(num_filters * 2)
        self.pool2 = nn.MaxPool1d(kernel_size=2, stride=2)
        self.drop2 = nn.Dropout(dropout)

        # Compute flattened size dynamically
        with torch.no_grad():
            dummy = torch.zeros(1, in_channels, seq_len)
            x = self.pool1(F.relu(self.bn1(self.conv1(dummy))))
            x = self.pool2(F.relu(self.bn2(self.conv2(x))))
            flattened_dim = x.view(1, -1).size(1)

        self.fc1 = nn.Linear(flattened_dim, 64)
        self.bn_fc = nn.BatchNorm1d(64)
        self.drop_fc = nn.Dropout(dropout)
        self.classifier = nn.Linear(64, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 3 and x.size(2) == self.in_channels:
            x = x.transpose(1, 2)

        x = self.drop1(self.pool1(F.relu(self.bn1(self.conv1(x)))))
        x = self.drop2(self.pool2(F.relu(self.bn2(self.conv2(x)))))
        x = torch.flatten(x, 1)
        x = self.drop_fc(F.relu(self.bn_fc(self.fc1(x))))
        logits = self.classifier(x)
        return logits


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for sequence tokens."""

    def __init__(self, d_model: int, max_len: int = 500, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        seq_len = x.size(1)
        x = x + self.pe[:, :seq_len]
        return self.dropout(x)


class DNATransformer(nn.Module):
    """
    Transformer / Multi-Head Self-Attention Architecture for DNA Sequence Classification.
    Accepts input tensor of shape (batch_size, seq_len, 4).
    """

    def __init__(
        self,
        seq_len: int = 50,
        in_dim: int = 4,
        d_model: int = 64,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 128,
        num_classes: int = 7,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.in_dim = in_dim
        self.embedding = nn.Linear(in_dim, d_model)
        self.pos_encoder = PositionalEncoding(
            d_model=d_model, max_len=seq_len + 10, dropout=dropout
        )

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=num_layers
        )

        self.classifier = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 3 and x.size(1) == self.in_dim and x.size(2) != self.in_dim:
            x = x.transpose(1, 2)

        x = self.embedding(x)
        x = self.pos_encoder(x)
        x = self.transformer_encoder(x)

        pooled = torch.mean(x, dim=1)
        logits = self.classifier(pooled)
        return logits

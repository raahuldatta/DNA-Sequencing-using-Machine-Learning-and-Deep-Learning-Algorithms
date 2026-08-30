"""
End-to-end Pipeline, Cross-Validation, Cross-Species evaluation,
and Persistence utilities for DNA Sequence Classification.
"""

from typing import List, Dict, Tuple, Any, Optional, Union
import os
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

from .preprocessing import (
    GENE_FAMILY_MAPPING,
    get_kmers,
    sequence_to_kmer_sentence,
    one_hot_encode_sequence,
)
from .models import create_ml_model, DNA_CNN1D, DNATransformer


def evaluate_predictions(
    y_true: Union[np.ndarray, List[int]],
    y_pred: Union[np.ndarray, List[int]],
) -> Dict[str, Any]:
    """Computes comprehensive classification metrics."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, average="weighted", zero_division=0)
    rec = recall_score(y_true, y_pred, average="weighted", zero_division=0)
    f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(GENE_FAMILY_MAPPING))))

    return {
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "confusion_matrix": cm,
    }


def plot_confusion_matrix(
    cm: np.ndarray,
    title: str = "Confusion Matrix",
    save_path: Optional[str] = None,
    cmap: str = "YlGnBu",
    normalize: bool = False,
) -> plt.Figure:
    """
    Plots a confusion matrix heatmap for all 7 gene families.
    """
    fig, ax = plt.subplots(figsize=(8, 6))
    display_cm = cm.astype("float") / cm.sum(axis=1)[:, np.newaxis] if normalize else cm
    fmt = ".2f" if normalize else "d"

    labels = [f"{k}: {v[:12]}.." for k, v in GENE_FAMILY_MAPPING.items()]
    sns.heatmap(
        display_cm,
        annot=True,
        fmt=fmt,
        cmap=cmap,
        xticklabels=list(range(len(GENE_FAMILY_MAPPING))),
        yticklabels=list(range(len(GENE_FAMILY_MAPPING))),
        ax=ax,
    )
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Predicted Class", fontsize=12)
    ax.set_ylabel("Actual Class", fontsize=12)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    return fig


class DNAPipeline:
    """
    Complete Scikit-Learn DNA Classification Pipeline encapsulating
    k-mer tokenization, CountVectorizer, and the classifier.
    """

    def __init__(
        self,
        model_name: str = "naive_bayes",
        k: int = 6,
        ngram_range: Tuple[int, int] = (4, 4),
        **model_kwargs,
    ):
        self.model_name = model_name
        self.k = k
        self.ngram_range = ngram_range
        self.model_kwargs = model_kwargs
        self.vectorizer = CountVectorizer(ngram_range=ngram_range)
        self.classifier = create_ml_model(model_name, **model_kwargs)
        self.is_fitted = False

    def _prepare_sentences(self, sequences: Union[List[str], np.ndarray, pd.Series]) -> List[str]:
        sentences = []
        for s in sequences:
            if " " in str(s):
                # Already a k-mer space-separated sentence
                sentences.append(str(s))
            else:
                sentences.append(sequence_to_kmer_sentence(str(s), k=self.k))
        return sentences

    def fit(self, sequences: Union[List[str], np.ndarray], y: np.ndarray):
        sentences = self._prepare_sentences(sequences)
        X = self.vectorizer.fit_transform(sentences)
        self.classifier.fit(X, y)
        self.is_fitted = True
        return self

    def predict(self, sequences: Union[List[str], np.ndarray]) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Pipeline must be fitted before predicting.")
        sentences = self._prepare_sentences(sequences)
        X = self.vectorizer.transform(sentences)
        return self.classifier.predict(X)

    def predict_proba(self, sequences: Union[List[str], np.ndarray]) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Pipeline must be fitted before predicting.")
        sentences = self._prepare_sentences(sequences)
        X = self.vectorizer.transform(sentences)
        if hasattr(self.classifier, "predict_proba"):
            return self.classifier.predict_proba(X)
        elif hasattr(self.classifier, "decision_function"):
            df = self.classifier.decision_function(X)
            # Softmax on decision function
            exp = np.exp(df - np.max(df, axis=1, keepdims=True))
            return exp / exp.sum(axis=1, keepdims=True)
        else:
            raise NotImplementedError("Classifier does not support probability output.")

    def predict_single(self, sequence: str) -> Dict[str, Any]:
        """Predicts gene family for a single raw DNA sequence."""
        pred_class = int(self.predict([sequence])[0])
        probas = self.predict_proba([sequence])[0]
        return {
            "predicted_class": pred_class,
            "gene_family": GENE_FAMILY_MAPPING.get(pred_class, "Unknown"),
            "confidence": float(probas[pred_class]),
            "class_probabilities": {
                int(k): float(probas[k]) for k in range(len(probas))
            },
        }

    def cross_validate(
        self,
        sequences: Union[List[str], np.ndarray],
        y: np.ndarray,
        n_splits: int = 5,
        random_state: int = 42,
    ) -> Dict[str, Any]:
        """
        Executes Stratified K-Fold Cross Validation without data leakage
        (vectorizer is fit strictly on training folds).
        """
        sentences = np.array(self._prepare_sentences(sequences))
        y = np.asarray(y)
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)

        fold_results = []
        for fold, (train_idx, val_idx) in enumerate(skf.split(sentences, y)):
            # Fit vectorizer only on train fold
            cv = CountVectorizer(ngram_range=self.ngram_range)
            X_train = cv.fit_transform(sentences[train_idx])
            X_val = cv.transform(sentences[val_idx])

            clf = create_ml_model(self.model_name, **self.model_kwargs)
            clf.fit(X_train, y[train_idx])
            val_preds = clf.predict(X_val)

            metrics = evaluate_predictions(y[val_idx], val_preds)
            metrics["fold"] = fold + 1
            fold_results.append(metrics)

        accs = [r["accuracy"] for r in fold_results]
        f1s = [r["f1"] for r in fold_results]
        precs = [r["precision"] for r in fold_results]
        recs = [r["recall"] for r in fold_results]

        return {
            "folds": fold_results,
            "mean_accuracy": float(np.mean(accs)),
            "std_accuracy": float(np.std(accs)),
            "mean_f1": float(np.mean(f1s)),
            "std_f1": float(np.std(f1s)),
            "mean_precision": float(np.mean(precs)),
            "std_precision": float(np.std(precs)),
            "mean_recall": float(np.mean(recs)),
            "std_recall": float(np.std(recs)),
        }

    def save(self, filepath: str):
        """Saves the complete pipeline to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        joblib.dump(self, filepath)

    @classmethod
    def load(cls, filepath: str) -> "DNAPipeline":
        """Loads a saved pipeline from disk."""
        return joblib.load(filepath)


def train_and_evaluate_dl_model(
    model: nn.Module,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    epochs: int = 30,
    batch_size: int = 32,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    device: Optional[torch.device] = None,
) -> Tuple[Dict[str, List[float]], Dict[str, Any]]:
    """
    Trains a PyTorch Deep Learning model on DNA sequences using Cross-Entropy Loss.
    """
    if device is None:
        device = torch.device(
            "mps"
            if torch.backends.mps.is_available()
            else ("cuda" if torch.cuda.is_available() else "cpu")
        )

    model = model.to(device)
    train_dataset = TensorDataset(
        torch.tensor(X_train, dtype=torch.float32),
        torch.tensor(y_train, dtype=torch.long),
    )
    val_dataset = TensorDataset(
        torch.tensor(X_val, dtype=torch.float32),
        torch.tensor(y_val, dtype=torch.long),
    )

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(
        model.parameters(), lr=lr, weight_decay=weight_decay
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5
    )

    history = {
        "train_loss": [],
        "train_acc": [],
        "val_loss": [],
        "val_acc": [],
    }

    best_val_loss = float("inf")
    best_weights = None

    for epoch in range(epochs):
        model.train()
        train_loss, train_correct, total_train = 0.0, 0, 0
        for bx, by in train_loader:
            bx, by = bx.to(device), by.to(device)
            optimizer.zero_grad()
            logits = model(bx)
            loss = criterion(logits, by)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * bx.size(0)
            preds = torch.argmax(logits, dim=1)
            train_correct += (preds == by).sum().item()
            total_train += bx.size(0)

        # Validation
        model.eval()
        val_loss, val_correct, total_val = 0.0, 0, 0
        with torch.no_grad():
            for bx, by in val_loader:
                bx, by = bx.to(device), by.to(device)
                logits = model(bx)
                loss = criterion(logits, by)
                val_loss += loss.item() * bx.size(0)
                preds = torch.argmax(logits, dim=1)
                val_correct += (preds == by).sum().item()
                total_val += bx.size(0)

        epoch_train_loss = train_loss / total_train
        epoch_train_acc = train_correct / total_train
        epoch_val_loss = val_loss / total_val
        epoch_val_acc = val_correct / total_val

        history["train_loss"].append(epoch_train_loss)
        history["train_acc"].append(epoch_train_acc)
        history["val_loss"].append(epoch_val_loss)
        history["val_acc"].append(epoch_val_acc)

        scheduler.step(epoch_val_loss)

        if epoch_val_loss < best_val_loss:
            best_val_loss = epoch_val_loss
            best_weights = model.state_dict().copy()

    if best_weights is not None:
        model.load_state_dict(best_weights)

    # Evaluate on Validation set
    final_metrics = evaluate_dl_model(model, X_val, y_val, batch_size=batch_size, device=device)
    return history, final_metrics


def evaluate_dl_model(
    model: nn.Module,
    X: np.ndarray,
    y: np.ndarray,
    batch_size: int = 32,
    device: Optional[torch.device] = None,
) -> Dict[str, Any]:
    """Evaluates a PyTorch DL model on test sequences."""
    if device is None:
        device = torch.device(
            "mps"
            if torch.backends.mps.is_available()
            else ("cuda" if torch.cuda.is_available() else "cpu")
        )
    model = model.to(device)
    model.eval()

    dataset = TensorDataset(
        torch.tensor(X, dtype=torch.float32),
        torch.tensor(y, dtype=torch.long),
    )
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)

    all_preds = []
    all_probs = []
    with torch.no_grad():
        for bx, _ in loader:
            bx = bx.to(device)
            logits = model(bx)
            probs = F.softmax(logits, dim=1).cpu().numpy()
            preds = np.argmax(probs, axis=1)
            all_preds.extend(preds)
            all_probs.extend(probs)

    all_preds = np.array(all_preds)
    all_probs = np.array(all_probs)
    metrics = evaluate_predictions(y, all_preds)
    metrics["predictions"] = all_preds
    metrics["probabilities"] = all_probs
    return metrics

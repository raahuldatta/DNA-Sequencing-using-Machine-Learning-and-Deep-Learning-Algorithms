#!/usr/bin/env python3
"""
DNA Sequence Classification Main Execution & CLI Pipeline.
Executes Machine Learning & Deep Learning workflows, cross-species evaluation,
generates publication-quality figures, and exposes CLI inference for arbitrary DNA sequences.
"""

import os
import sys
import argparse
import time
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import torch

from src.preprocessing import (
    GENE_FAMILY_MAPPING,
    load_tsv_dataset,
    load_raw_sequences_and_labels,
    one_hot_encode_sequence,
)
from src.models import (
    create_ml_model,
    DNA_CNN1D,
    DNATransformer,
)
from src.pipeline import (
    DNAPipeline,
    evaluate_predictions,
    plot_confusion_matrix,
    train_and_evaluate_dl_model,
    evaluate_dl_model,
)

# Configure Matplotlib backend & style
os.environ["MPLCONFIGDIR"] = os.environ.get("MPLCONFIGDIR", "/tmp/matplotlib")


def train_ml_models(human_sentences, human_y, chimp_sentences, chimp_y, dog_sentences, dog_y):
    """Trains and cross-validates ML models, evaluating cross-species generalization."""
    print("=" * 70, flush=True)
    print(" 1. MACHINE LEARNING BENCHMARK & CROSS-VALIDATION", flush=True)
    print("=" * 70, flush=True)

    models = {
        "Multinomial Naive Bayes": ("naive_bayes", {"alpha": 0.1}),
        "Random Forest": ("random_forest", {"n_estimators": 50, "random_state": 42, "max_features": "sqrt"}),
        "Decision Tree": ("decision_tree", {"random_state": 42, "max_depth": 30}),
    }

    ml_results = {}
    pipelines = {}

    for name, (model_key, kwargs) in models.items():
        print(f"\nEvaluating {name}...", flush=True)
        pipeline = DNAPipeline(model_name=model_key, k=6, ngram_range=(4, 4), **kwargs)

        # 5-fold cross validation on Human data
        cv_res = pipeline.cross_validate(human_sentences, human_y, n_splits=5)
        print(f"  [Human 5-Fold CV] Mean Accuracy: {cv_res['mean_accuracy'] * 100:.2f}% ± {cv_res['std_accuracy'] * 100:.2f}% | Mean F1: {cv_res['mean_f1'] * 100:.2f}%", flush=True)

        # Fit on full human dataset
        pipeline.fit(human_sentences, human_y)
        pipelines[name] = pipeline

        # Cross-species evaluation
        chimp_preds = pipeline.predict(chimp_sentences)
        chimp_metrics = evaluate_predictions(chimp_y, chimp_preds)
        print(f"  [Chimpanzee Zero-Shot Transfer] Accuracy: {chimp_metrics['accuracy'] * 100:.2f}% | F1: {chimp_metrics['f1'] * 100:.2f}%", flush=True)

        dog_preds = pipeline.predict(dog_sentences)
        dog_metrics = evaluate_predictions(dog_y, dog_preds)
        print(f"  [Dog Zero-Shot Transfer] Accuracy: {dog_metrics['accuracy'] * 100:.2f}% | F1: {dog_metrics['f1'] * 100:.2f}%", flush=True)

        ml_results[name] = {
            "cv_accuracy": cv_res["mean_accuracy"],
            "cv_f1": cv_res["mean_f1"],
            "chimp_accuracy": chimp_metrics["accuracy"],
            "dog_accuracy": dog_metrics["accuracy"],
            "pipeline": pipeline,
        }

    # Save best ML model (Multinomial Naive Bayes)
    best_pipeline = pipelines["Multinomial Naive Bayes"]
    best_pipeline.save("dna_model_pipeline.joblib")
    import pickle
    with open("finalized_model.sav", "wb") as f:
        pickle.dump(best_pipeline.classifier, f)
    print("\nSaved full pipeline to 'dna_model_pipeline.joblib' and classifier to 'finalized_model.sav'.", flush=True)

    # Generate Confusion Matrix for Best Model
    from sklearn.model_selection import train_test_split
    X_train_s, X_test_s, y_train_s, y_test_s = train_test_split(
        human_sentences, human_y, test_size=0.20, random_state=42, stratify=human_y
    )
    nb_eval_pipe = DNAPipeline(model_name="naive_bayes", k=6, ngram_range=(4, 4), alpha=0.1)
    nb_eval_pipe.fit(X_train_s, y_train_s)

    human_test_preds = nb_eval_pipe.predict(X_test_s)
    cm_human = evaluate_predictions(y_test_s, human_test_preds)["confusion_matrix"]
    plot_confusion_matrix(cm_human, title="Human DNA Classification (Naive Bayes)", save_path="cm_human.png")

    chimp_preds_nb = nb_eval_pipe.predict(chimp_sentences)
    cm_chimp = evaluate_predictions(chimp_y, chimp_preds_nb)["confusion_matrix"]
    plot_confusion_matrix(cm_chimp, title="Chimpanzee Transfer Classification (Naive Bayes)", save_path="cm_chimp.png")

    dog_preds_nb = nb_eval_pipe.predict(dog_sentences)
    cm_dog = evaluate_predictions(dog_y, dog_preds_nb)["confusion_matrix"]
    plot_confusion_matrix(cm_dog, title="Dog Transfer Classification (Naive Bayes)", save_path="cm_dog.png")

    return ml_results, best_pipeline


def train_dl_models(X_h_seq, y_h_seq, X_c_seq, y_c_seq, X_d_seq, y_d_seq):
    """Trains 1D-CNN and DNA Transformer architectures with cross-species transfer."""
    print("\n" + "=" * 70, flush=True)
    print(" 2. DEEP LEARNING BENCHMARK (1D-CNN & DNA TRANSFORMER)", flush=True)
    print("=" * 70, flush=True)

    from sklearn.model_selection import train_test_split
    X_train, X_val, y_train, y_val = train_test_split(
        X_h_seq, y_h_seq, test_size=0.25, random_state=42, stratify=y_h_seq
    )

    device = torch.device("mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu"))
    print(f"Using compute device: {device}", flush=True)

    # 1. 1D Convolutional Neural Network
    print("\n[Training 1D-CNN]...", flush=True)
    cnn_model = DNA_CNN1D(seq_len=50, in_channels=4, num_classes=7, num_filters=32, kernel_size=12, dropout=0.3)
    cnn_hist, cnn_val_metrics = train_and_evaluate_dl_model(
        cnn_model, X_train, y_train, X_val, y_val, epochs=25, batch_size=32, lr=1e-3, device=device
    )
    print(f"  [Human Validation] Accuracy: {cnn_val_metrics['accuracy'] * 100:.2f}% | F1: {cnn_val_metrics['f1'] * 100:.2f}%", flush=True)

    chimp_cnn_metrics = evaluate_dl_model(cnn_model, X_c_seq, y_c_seq, device=device)
    print(f"  [Chimpanzee Transfer] Accuracy: {chimp_cnn_metrics['accuracy'] * 100:.2f}% | F1: {chimp_cnn_metrics['f1'] * 100:.2f}%", flush=True)

    dog_cnn_metrics = evaluate_dl_model(cnn_model, X_d_seq, y_d_seq, device=device)
    print(f"  [Dog Transfer] Accuracy: {dog_cnn_metrics['accuracy'] * 100:.2f}% | F1: {dog_cnn_metrics['f1'] * 100:.2f}%", flush=True)

    torch.save(cnn_model.state_dict(), "dna_cnn1d.pt")

    # 2. DNA Transformer
    print("\n[Training DNA Transformer / Self-Attention]...", flush=True)
    trans_model = DNATransformer(seq_len=50, in_dim=4, d_model=64, nhead=4, num_layers=2, dim_feedforward=128, num_classes=7, dropout=0.2)
    trans_hist, trans_val_metrics = train_and_evaluate_dl_model(
        trans_model, X_train, y_train, X_val, y_val, epochs=25, batch_size=32, lr=1e-3, device=device
    )
    print(f"  [Human Validation] Accuracy: {trans_val_metrics['accuracy'] * 100:.2f}% | F1: {trans_val_metrics['f1'] * 100:.2f}%", flush=True)

    chimp_trans_metrics = evaluate_dl_model(trans_model, X_c_seq, y_c_seq, device=device)
    print(f"  [Chimpanzee Transfer] Accuracy: {chimp_trans_metrics['accuracy'] * 100:.2f}% | F1: {chimp_trans_metrics['f1'] * 100:.2f}%", flush=True)

    dog_trans_metrics = evaluate_dl_model(trans_model, X_d_seq, y_d_seq, device=device)
    print(f"  [Dog Transfer] Accuracy: {dog_trans_metrics['accuracy'] * 100:.2f}% | F1: {dog_trans_metrics['f1'] * 100:.2f}%", flush=True)

    torch.save(trans_model.state_dict(), "dna_transformer.pt")

    # Plot Confusion Matrix for Transformer on Human
    plot_confusion_matrix(trans_val_metrics["confusion_matrix"], title="Human DNA (DNA Transformer)", save_path="cm_dl_transformer.png")

    dl_results = {
        "1D-CNN": {
            "val_accuracy": cnn_val_metrics["accuracy"],
            "chimp_accuracy": chimp_cnn_metrics["accuracy"],
            "dog_accuracy": dog_cnn_metrics["accuracy"],
        },
        "DNA Transformer": {
            "val_accuracy": trans_val_metrics["accuracy"],
            "chimp_accuracy": chimp_trans_metrics["accuracy"],
            "dog_accuracy": dog_trans_metrics["accuracy"],
        },
    }

    return dl_results


def plot_overall_comparison(ml_results, dl_results):
    """Plots comparative performance chart of all ML and DL models."""
    models = []
    human_accs = []
    chimp_accs = []
    dog_accs = []

    for name, res in ml_results.items():
        models.append(name)
        human_accs.append(res["cv_accuracy"] * 100)
        chimp_accs.append(res["chimp_accuracy"] * 100)
        dog_accs.append(res["dog_accuracy"] * 100)

    for name, res in dl_results.items():
        models.append(name)
        human_accs.append(res["val_accuracy"] * 100)
        chimp_accs.append(res["chimp_accuracy"] * 100)
        dog_accs.append(res["dog_accuracy"] * 100)

    x = np.arange(len(models))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 6))
    rects1 = ax.bar(x - width, human_accs, width, label="Human (Validation/CV)", color="#2b5c8f")
    rects2 = ax.bar(x, chimp_accs, width, label="Chimpanzee (Cross-Species)", color="#38a169")
    rects3 = ax.bar(x + width, dog_accs, width, label="Dog (Cross-Species)", color="#dd6b20")

    ax.set_ylabel("Accuracy (%)", fontsize=13, fontweight="bold")
    ax.set_title("DNA Sequence Classification & Cross-Species Transfer Benchmark", fontsize=15, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=15, ha="right", fontsize=11, fontweight="bold")
    ax.set_ylim(0, 105)
    ax.legend(loc="lower right", frameon=True, fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.7)

    for rects in [rects1, rects2, rects3]:
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f"{height:.1f}%",
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center", va="bottom", fontsize=9, rotation=0)

    plt.tight_layout()
    fig.savefig("model_comparison.png", dpi=300)
    print("\nSaved overall comparison chart to 'model_comparison.png'.", flush=True)


def run_pipeline():
    """Executes full data loading, ML training, DL training, and comparison."""
    # 1. Load tabular TSV datasets
    print("Loading tabular TSV datasets...", flush=True)
    _, human_sentences, human_y = load_tsv_dataset("human_data.txt")
    _, chimp_sentences, chimp_y = load_tsv_dataset("chimp_data.txt")
    _, dog_sentences, dog_y = load_tsv_dataset("dog_data.txt")

    # 2. Load sequence text files
    print("Loading raw sequence files...", flush=True)
    X_h_seq, y_h_seq, _ = load_raw_sequences_and_labels("human_sequence.txt", "human_labels.txt")
    X_c_seq, y_c_seq, _ = load_raw_sequences_and_labels("chimp_sequence.txt", "chimp_labels.txt")
    X_d_seq, y_d_seq, _ = load_raw_sequences_and_labels("dog_sequence.txt", "dog_labels.txt")

    # 3. ML Benchmark
    ml_results, best_pipeline = train_ml_models(
        human_sentences, human_y, chimp_sentences, chimp_y, dog_sentences, dog_y
    )

    # 4. DL Benchmark
    dl_results = train_dl_models(
        X_h_seq, y_h_seq, X_c_seq, y_c_seq, X_d_seq, y_d_seq
    )

    # 5. Model Comparison Plot
    plot_overall_comparison(ml_results, dl_results)

    print("\n" + "=" * 70, flush=True)
    print(" EXECUTION COMPLETED SUCCESSFULLY", flush=True)
    print("=" * 70, flush=True)


def predict_sequence_cli(sequence: str, model_path: str = "dna_model_pipeline.joblib"):
    """CLI inference for predicting gene family of a DNA sequence."""
    if not os.path.exists(model_path):
        print(f"Model file '{model_path}' not found. Training first...", flush=True)
        run_pipeline()

    pipeline = DNAPipeline.load(model_path)
    result = pipeline.predict_single(sequence)

    print("\n" + "=" * 60, flush=True)
    print(" DNA SEQUENCE PREDICTION RESULT", flush=True)
    print("=" * 60, flush=True)
    print(f"Input Sequence: {sequence[:40]}... (Length: {len(sequence)} bp)", flush=True)
    print(f"Predicted Class: {result['predicted_class']}", flush=True)
    print(f"Gene Family:     {result['gene_family']}", flush=True)
    print(f"Confidence:      {result['confidence'] * 100:.2f}%", flush=True)
    print("-" * 60, flush=True)
    print("Class Probabilities:", flush=True)
    for cls_id, prob in sorted(result["class_probabilities"].items()):
        cls_name = GENE_FAMILY_MAPPING.get(cls_id, "Unknown")
        bar = "█" * int(prob * 30)
        print(f"  Class {cls_id} ({cls_name[:24]:<24}): {prob * 100:6.2f}% {bar}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DNA Sequence Machine Learning & Deep Learning Classifier")
    parser.add_argument("--train", action="store_true", help="Train all ML and DL models and generate benchmark plots")
    parser.add_argument("--predict", type=str, default=None, help="Predict the gene family for a given DNA sequence string")
    parser.add_argument("--model-path", type=str, default="dna_model_pipeline.joblib", help="Path to saved model pipeline")

    args = parser.parse_args()

    if args.predict:
        predict_sequence_cli(args.predict, model_path=args.model_path)
    else:
        run_pipeline()

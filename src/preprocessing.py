"""
Data preprocessing and sequence encoding utilities for DNA sequence classification.
"""

from typing import List, Tuple, Dict, Optional, Union
import numpy as np
import pandas as pd

GENE_FAMILY_MAPPING = {
    0: "G-protein coupled receptors",
    1: "Tyrosine kinase",
    2: "Tyrosine phosphatase",
    3: "Synthetase",
    4: "Synthase",
    5: "Ion channel",
    6: "Transcription factor",
}

BASE_TO_INDEX = {
    "A": 0, "a": 0,
    "C": 1, "c": 1,
    "G": 2, "g": 2,
    "T": 3, "t": 3,
}


def get_kmers(sequence: str, k: int = 6) -> List[str]:
    """
    Splits a DNA sequence string into overlapping k-mers (default size 6: hexamers).

    Args:
        sequence: Raw DNA sequence string (e.g. 'ATGCGT...')
        k: Length of each k-mer (default: 6)

    Returns:
        List of lowercase k-mer strings.
    """
    cleaned_seq = sequence.strip().lower()
    if len(cleaned_seq) < k:
        return [cleaned_seq] if cleaned_seq else []
    return [cleaned_seq[i : i + k] for i in range(len(cleaned_seq) - k + 1)]


def sequence_to_kmer_sentence(sequence: str, k: int = 6) -> str:
    """
    Converts a DNA sequence string into a space-separated sentence of k-mer words.
    """
    kmers = get_kmers(sequence, k=k)
    return " ".join(kmers)


def load_tsv_dataset(
    filepath: str, k: int = 6
) -> Tuple[pd.DataFrame, List[str], np.ndarray]:
    """
    Loads tabular DNA dataset (TSV formatted with 'sequence' and 'class' columns),
    cleans sequences, generates k-mer words, and returns dataframe, texts, and labels.

    Args:
        filepath: Path to the TSV file (e.g. 'human_data.txt')
        k: k-mer length (default: 6)

    Returns:
        (df, kmer_sentences, y_labels)
    """
    df = pd.read_table(filepath)
    if "sequence" not in df.columns or "class" not in df.columns:
        raise ValueError(
            f"File {filepath} must contain 'sequence' and 'class' columns."
        )

    # Clean whitespace and drop missing values
    df = df.dropna(subset=["sequence", "class"]).copy()
    df["sequence"] = df["sequence"].astype(str).str.strip().str.upper()
    df["class"] = df["class"].astype(int)

    # Generate k-mer sentences
    kmer_sentences = [
        sequence_to_kmer_sentence(seq, k=k) for seq in df["sequence"]
    ]
    y_labels = df["class"].values

    return df, kmer_sentences, y_labels


def one_hot_encode_sequence(
    sequence: str, max_len: Optional[int] = None
) -> np.ndarray:
    """
    Encodes a single DNA sequence into a one-hot representation of shape (L, 4).
    Bases: A -> [1,0,0,0], C -> [0,1,0,0], G -> [0,0,1,0], T -> [0,0,0,1].
    Any invalid/unknown nucleotide (e.g. 'N') is encoded as [0,0,0,0].

    Args:
        sequence: Raw DNA string
        max_len: Optional fixed length to truncate/pad. If None, uses len(sequence).

    Returns:
        2D numpy array of shape (L, 4), dtype float32
    """
    cleaned = sequence.strip()
    seq_len = max_len if max_len is not None else len(cleaned)
    encoded = np.zeros((seq_len, 4), dtype=np.float32)

    limit = min(len(cleaned), seq_len)
    for i in range(limit):
        base = cleaned[i]
        idx = BASE_TO_INDEX.get(base, None)
        if idx is not None:
            encoded[i, idx] = 1.0

    return encoded


def load_raw_sequences_and_labels(
    seq_path: str, label_path: str, max_len: int = 50
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Loads raw line-by-line sequences and labels from text files.
    Cleans trailing carriage returns (CRLF) and encodes sequences as one-hot arrays.

    Args:
        seq_path: Path to sequence file (e.g. 'human_sequence.txt')
        label_path: Path to label file (e.g. 'human_labels.txt')
        max_len: Sequence length for one-hot matrix (default: 50)

    Returns:
        X_onehot: (N, max_len, 4) numpy array
        y: (N,) integer class labels (0..6)
        raw_sequences: List of raw sequence strings
    """
    with open(seq_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_sequences = [line.strip() for line in f if line.strip()]

    with open(label_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_labels = [line.strip() for line in f if line.strip()]

    if len(raw_sequences) != len(raw_labels):
        raise ValueError(
            f"Mismatch: {len(raw_sequences)} sequences in {seq_path} "
            f"vs {len(raw_labels)} labels in {label_path}"
        )

    y = np.array([int(lbl) for lbl in raw_labels], dtype=np.int64)
    X_list = [one_hot_encode_sequence(seq, max_len=max_len) for seq in raw_sequences]
    X_onehot = np.stack(X_list, axis=0)

    return X_onehot, y, raw_sequences

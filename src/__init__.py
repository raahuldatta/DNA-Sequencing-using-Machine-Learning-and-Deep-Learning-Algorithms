"""
DNA Sequencing using Machine Learning and Deep Learning Algorithms
"""

from .preprocessing import (
    GENE_FAMILY_MAPPING,
    get_kmers,
    sequence_to_kmer_sentence,
    load_tsv_dataset,
    one_hot_encode_sequence,
    load_raw_sequences_and_labels,
)
from .models import (
    create_ml_model,
    DNA_CNN1D,
    DNATransformer,
)
from .pipeline import (
    DNAPipeline,
    evaluate_predictions,
    evaluate_dl_model,
    train_and_evaluate_dl_model,
    plot_confusion_matrix,
)

__all__ = [
    "GENE_FAMILY_MAPPING",
    "get_kmers",
    "sequence_to_kmer_sentence",
    "load_tsv_dataset",
    "one_hot_encode_sequence",
    "load_raw_sequences_and_labels",
    "create_ml_model",
    "DNA_CNN1D",
    "DNATransformer",
    "DNAPipeline",
    "evaluate_predictions",
    "evaluate_dl_model",
    "train_and_evaluate_dl_model",
    "plot_confusion_matrix",
]

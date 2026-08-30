"""
Unit tests for DNA sequence classification package.
"""

import unittest
import os
import shutil
import tempfile
import numpy as np
import torch

from src.preprocessing import (
    GENE_FAMILY_MAPPING,
    get_kmers,
    sequence_to_kmer_sentence,
    one_hot_encode_sequence,
    load_tsv_dataset,
    load_raw_sequences_and_labels,
)
from src.models import (
    create_ml_model,
    DNA_CNN1D,
    DNATransformer,
)
from src.pipeline import (
    DNAPipeline,
    evaluate_predictions,
    train_and_evaluate_dl_model,
    evaluate_dl_model,
)


class TestPreprocessing(unittest.TestCase):
    def test_get_kmers(self):
        seq = "ATGCGTAC"
        kmers = get_kmers(seq, k=6)
        self.assertEqual(len(kmers), 3)
        self.assertEqual(kmers, ["atgcgt", "tgcgta", "gcgtac"])

    def test_short_kmer(self):
        seq = "ATG"
        kmers = get_kmers(seq, k=6)
        self.assertEqual(kmers, ["atg"])

    def test_sequence_to_kmer_sentence(self):
        seq = "ATGCGTAC"
        sentence = sequence_to_kmer_sentence(seq, k=6)
        self.assertEqual(sentence, "atgcgt tgcgta gcgtac")

    def test_one_hot_encode_sequence(self):
        seq = "ACGTN"
        encoded = one_hot_encode_sequence(seq, max_len=5)
        self.assertEqual(encoded.shape, (5, 4))
        # A -> [1, 0, 0, 0]
        np.testing.assert_array_equal(encoded[0], [1, 0, 0, 0])
        # C -> [0, 1, 0, 0]
        np.testing.assert_array_equal(encoded[1], [0, 1, 0, 0])
        # G -> [0, 0, 1, 0]
        np.testing.assert_array_equal(encoded[2], [0, 0, 1, 0])
        # T -> [0, 0, 0, 1]
        np.testing.assert_array_equal(encoded[3], [0, 0, 0, 1])
        # N -> [0, 0, 0, 0]
        np.testing.assert_array_equal(encoded[4], [0, 0, 0, 0])

    def test_load_tsv_dataset(self):
        df, sentences, y = load_tsv_dataset("human_data.txt", k=6)
        self.assertGreater(len(df), 0)
        self.assertEqual(len(sentences), len(df))
        self.assertEqual(len(y), len(df))
        self.assertIn(y[0], range(7))

    def test_load_raw_sequences_and_labels(self):
        X, y, seqs = load_raw_sequences_and_labels("human_sequence.txt", "human_labels.txt", max_len=50)
        self.assertEqual(X.shape, (2000, 50, 4))
        self.assertEqual(len(y), 2000)
        self.assertEqual(len(seqs), 2000)


class TestModels(unittest.TestCase):
    def test_create_ml_models(self):
        for name in ["naive_bayes", "random_forest", "decision_tree", "svm"]:
            model = create_ml_model(name)
            self.assertIsNotNone(model)

    def test_dna_cnn1d_forward(self):
        model = DNA_CNN1D(seq_len=50, in_channels=4, num_classes=7)
        dummy = torch.randn(8, 50, 4)
        out = model(dummy)
        self.assertEqual(out.shape, (8, 7))

    def test_dna_transformer_forward(self):
        model = DNATransformer(seq_len=50, in_dim=4, d_model=32, nhead=2, num_layers=1, num_classes=7)
        dummy = torch.randn(8, 50, 4)
        out = model(dummy)
        self.assertEqual(out.shape, (8, 7))


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_pipeline_fit_predict_save_load(self):
        # Create synthetic toy sequences
        seqs = [
            "ATGCGTACGTAGCTAGCTAGCTAGCTAGCTA",
            "CGTAGCTAGCTAGCTAGCTAGCTAGCTAGCT",
            "GCTAGCTAGCTAGCTAGCTAGCTAGCTAGCT",
            "TAGCTAGCTAGCTAGCTAGCTAGCTAGCTAG",
            "ATGCATGCATGCATGCATGCATGCATGCATG",
            "CGATCGATCGATCGATCGATCGATCGATCGA",
            "GATCGATCGATCGATCGATCGATCGATCGAT",
            "TCGATCGATCGATCGATCGATCGATCGATCG",
        ] * 4
        y = np.array([0, 1, 2, 3, 4, 5, 6, 0] * 4)

        pipeline = DNAPipeline(model_name="naive_bayes", k=4, ngram_range=(2, 2))
        pipeline.fit(seqs, y)
        preds = pipeline.predict(seqs)
        self.assertEqual(len(preds), len(y))

        # Single sequence prediction
        res = pipeline.predict_single(seqs[0])
        self.assertIn("predicted_class", res)
        self.assertIn("gene_family", res)
        self.assertIn("confidence", res)

        # Save and load
        save_path = os.path.join(self.test_dir, "test_pipeline.joblib")
        pipeline.save(save_path)
        self.assertTrue(os.path.exists(save_path))

        loaded = DNAPipeline.load(save_path)
        loaded_preds = loaded.predict(seqs)
        np.testing.assert_array_equal(preds, loaded_preds)

    def test_dl_training_loop(self):
        X = np.random.randn(32, 50, 4).astype(np.float32)
        y = np.random.randint(0, 7, size=(32,)).astype(np.int64)

        model = DNA_CNN1D(seq_len=50, in_channels=4, num_classes=7, num_filters=16)
        history, metrics = train_and_evaluate_dl_model(
            model, X[:24], y[:24], X[24:], y[24:], epochs=2, batch_size=8, device=torch.device("cpu")
        )
        self.assertIn("train_loss", history)
        self.assertIn("accuracy", metrics)


if __name__ == "__main__":
    unittest.main()

"""Tests for the ModelEvaluator class."""

import pytest
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from model_evaluation import ModelEvaluator


class TestModelEvaluatorInit:
    """Test evaluator initialization."""

    def test_default_init(self):
        evaluator = ModelEvaluator()
        assert evaluator.benchmarks_dir == "benchmarks"
        assert evaluator.results == []
        assert evaluator._ground_truth is None

    def test_custom_benchmarks_dir(self):
        evaluator = ModelEvaluator(benchmarks_dir="/custom/path")
        assert evaluator.benchmarks_dir == "/custom/path"


class TestLoadGroundTruth:
    """Test ground truth loading."""

    def test_load_valid_ground_truth(self, tmp_path):
        gt_data = [{"file": "test.pdf", "expected": {"transactor": "Acme"}}]
        gt_file = tmp_path / "ground_truth.json"
        gt_file.write_text(json.dumps(gt_data))

        evaluator = ModelEvaluator(benchmarks_dir=str(tmp_path))
        result = evaluator.load_ground_truth()

        assert len(result) == 1
        assert result[0]['file'] == 'test.pdf'
        assert evaluator._ground_truth == gt_data

    def test_load_missing_file(self, tmp_path):
        evaluator = ModelEvaluator(benchmarks_dir=str(tmp_path))
        result = evaluator.load_ground_truth()
        assert result == []


class TestFieldAccuracy:
    """Test _calculate_field_accuracy method."""

    def test_exact_string_match(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {'invoice_number': 'INV-001'},
            {'invoice_number': 'INV-001'}
        )
        assert scores['invoice_number'] == 1.0

    def test_case_insensitive_match(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {'invoice_number': 'inv-001'},
            {'invoice_number': 'INV-001'}
        )
        assert scores['invoice_number'] == 1.0

    def test_numeric_field_exact(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {'amount': 100.00},
            {'amount': 100.00}
        )
        assert scores['amount'] == 1.0

    def test_numeric_field_close(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {'amount': 101.0},
            {'amount': 100.00}
        )
        assert scores['amount'] >= 0.5

    def test_date_field_exact(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {'date': '2024-01-15'},
            {'date': '2024-01-15'}
        )
        assert scores['date'] == 1.0

    def test_supplier_name_fuzzy(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {'transactor': 'Acme Corp Ltd'},
            {'transactor': 'Acme Corp'}
        )
        assert scores['transactor'] > 0.0

    def test_missing_extracted_field(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {},
            {'transactor': 'Acme Corp'}
        )
        assert scores['transactor'] == 0.0

    def test_none_expected_skipped(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {'transactor': 'Acme'},
            {'transactor': None}
        )
        assert 'transactor' not in scores

    def test_substring_containment(self):
        evaluator = ModelEvaluator()
        scores = evaluator._calculate_field_accuracy(
            {'description': 'Software Development Services'},
            {'description': 'Software Development'}
        )
        assert scores['description'] == 0.8


class TestNumericComparison:
    """Test _compare_numeric method."""

    def test_exact_match(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_numeric(100.00, 100.00) == 1.0

    def test_within_tight_tolerance(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_numeric(100.00, 100.05) == 1.0

    def test_within_5_percent(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_numeric(100.00, 103.0) == 0.8

    def test_within_10_percent(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_numeric(100.00, 108.0) == 0.5

    def test_outside_tolerance(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_numeric(100.00, 200.00) == 0.0

    def test_zero_expected_zero_extracted(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_numeric(0, 0) == 1.0

    def test_zero_expected_nonzero_extracted(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_numeric(0, 50) == 0.0

    def test_invalid_value(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_numeric("abc", 100) == 0.0


class TestDateComparison:
    """Test _compare_dates method."""

    def test_same_date_same_format(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_dates('2024-01-15', '2024-01-15') == 1.0

    def test_different_formats(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_dates('2024-01-15', '15/01/2024') == 1.0

    def test_one_day_apart(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_dates('2024-01-15', '2024-01-16') == 0.8

    def test_week_apart(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_dates('2024-01-15', '2024-01-20') == 0.5

    def test_far_apart(self):
        evaluator = ModelEvaluator()
        assert evaluator._compare_dates('2024-01-15', '2024-06-15') == 0.0


class TestFuzzyStringMatch:
    """Test _fuzzy_string_match method."""

    def test_identical(self):
        evaluator = ModelEvaluator()
        assert evaluator._fuzzy_string_match('acme corp', 'acme corp') == 1.0

    def test_partial_overlap(self):
        evaluator = ModelEvaluator()
        score = evaluator._fuzzy_string_match('acme corp ltd', 'acme corp')
        assert 0.5 <= score <= 0.9

    def test_no_overlap(self):
        evaluator = ModelEvaluator()
        assert evaluator._fuzzy_string_match('acme corp', 'beta inc') == 0.0

    def test_empty_string(self):
        evaluator = ModelEvaluator()
        assert evaluator._fuzzy_string_match('', 'acme') == 0.0

    def test_both_empty(self):
        evaluator = ModelEvaluator()
        assert evaluator._fuzzy_string_match('', '') == 1.0


class TestCalculateWER:
    """Test Word Error Rate calculation."""

    def test_perfect_match(self):
        evaluator = ModelEvaluator()
        assert evaluator._calculate_wer('hello world', 'hello world') == 0.0

    def test_completely_wrong(self):
        evaluator = ModelEvaluator()
        wer = evaluator._calculate_wer('hello world', 'foo bar')
        assert wer == 1.0

    def test_partial_match(self):
        evaluator = ModelEvaluator()
        wer = evaluator._calculate_wer('the quick brown fox', 'the quick red fox')
        assert 0.0 < wer < 1.0

    def test_empty_reference(self):
        evaluator = ModelEvaluator()
        assert evaluator._calculate_wer('', '') == 0.0

    def test_empty_reference_nonempty_hypothesis(self):
        evaluator = ModelEvaluator()
        assert evaluator._calculate_wer('', 'some words') == 1.0


class TestEvaluateExtractionModel:
    """Test evaluate_extraction_model method."""

    def test_evaluate_with_test_files(self, tmp_path):
        # Set up ground truth and sample file
        gt_data = [{"file": "test.pdf", "expected": {"transactor": "Acme", "amount": 100.0}}]
        gt_file = tmp_path / "ground_truth.json"
        gt_file.write_text(json.dumps(gt_data))

        sample_dir = tmp_path / "sample_invoices"
        sample_dir.mkdir()
        (sample_dir / "test.pdf").write_text("dummy content")

        def mock_extract(file_path):
            return {"transactor": "Acme", "amount": 100.0}

        evaluator = ModelEvaluator(benchmarks_dir=str(tmp_path))
        evaluator.load_ground_truth()
        result = evaluator.evaluate_extraction_model("Test Model", mock_extract)

        assert result['model_name'] == 'Test Model'
        assert result['accuracy'] == 1.0
        assert result['failure_rate'] == 0.0
        assert result['successes'] == 1
        assert len(evaluator.results) == 1

    def test_evaluate_no_ground_truth(self, tmp_path):
        evaluator = ModelEvaluator(benchmarks_dir=str(tmp_path))
        result = evaluator.evaluate_extraction_model("Empty Model", lambda f: {})

        assert result['model_name'] == 'Empty Model'
        assert result['accuracy'] == 0.0
        assert result['failure_rate'] == 1.0
        assert len(evaluator.results) == 1

    def test_evaluate_with_failing_extract(self, tmp_path):
        gt_data = [{"file": "test.pdf", "expected": {"transactor": "Acme"}}]
        gt_file = tmp_path / "ground_truth.json"
        gt_file.write_text(json.dumps(gt_data))

        sample_dir = tmp_path / "sample_invoices"
        sample_dir.mkdir()
        (sample_dir / "test.pdf").write_text("dummy")

        def failing_extract(file_path):
            raise RuntimeError("Model crashed")

        evaluator = ModelEvaluator(benchmarks_dir=str(tmp_path))
        evaluator.load_ground_truth()
        result = evaluator.evaluate_extraction_model("Failing Model", failing_extract)

        assert result['failures'] == 1
        assert result['failure_rate'] == 1.0

    def test_evaluate_file_not_found(self, tmp_path):
        gt_data = [{"file": "missing.pdf", "expected": {"transactor": "Acme"}}]
        gt_file = tmp_path / "ground_truth.json"
        gt_file.write_text(json.dumps(gt_data))

        evaluator = ModelEvaluator(benchmarks_dir=str(tmp_path))
        evaluator.load_ground_truth()
        result = evaluator.evaluate_extraction_model("Test Model", lambda f: {})

        assert result['failures'] == 1


class TestCompareModels:
    """Test compare_models method."""

    def test_compare_no_results(self):
        evaluator = ModelEvaluator()
        comparison = evaluator.compare_models()
        assert comparison['models'] == []

    def test_compare_multiple_models(self):
        evaluator = ModelEvaluator()
        evaluator.results = [
            {'model_name': 'Fast Model', 'accuracy': 0.7, 'avg_time': 0.5, 'failure_rate': 0.1},
            {'model_name': 'Accurate Model', 'accuracy': 0.95, 'avg_time': 2.0, 'failure_rate': 0.05},
            {'model_name': 'Reliable Model', 'accuracy': 0.8, 'avg_time': 1.0, 'failure_rate': 0.0},
        ]
        comparison = evaluator.compare_models()

        assert comparison['best_accuracy'] == 'Accurate Model'
        assert comparison['fastest'] == 'Fast Model'
        assert comparison['most_reliable'] == 'Reliable Model'
        assert len(comparison['models']) == 3


class TestEmptyResult:
    """Test _empty_result structure."""

    def test_has_all_required_keys(self):
        evaluator = ModelEvaluator()
        result = evaluator._empty_result("Test Model")

        expected_keys = ['model_name', 'accuracy', 'field_accuracies', 'avg_time',
                         'total_time', 'failure_rate', 'total_files', 'successes',
                         'failures', 'results', 'evaluated_at']
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

        assert result['model_name'] == 'Test Model'
        assert result['accuracy'] == 0.0
        assert result['failure_rate'] == 1.0
        assert result['total_files'] == 0

"""
Model Evaluation Framework

This module provides a systematic benchmarking framework for evaluating
and comparing all pre-trained models used in the invoice processing system.
It measures extraction accuracy, processing time, and failure rates across
models operating in different data domains.

Supports evaluation of:
- LLM models (Gemini, Mistral) for invoice extraction
- OCR models (Tesseract) for text extraction from images
- Audio models (Whisper) for speech-to-text transcription
- Image classification models (DiT) for document classification
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Tuple
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ModelEvaluator:
    """
    Benchmark and compare pre-trained models for accuracy and performance.

    This evaluator runs models against test data with known ground truth
    and produces comparative metrics including accuracy, speed, and reliability.
    """

    def __init__(self, benchmarks_dir: str = "benchmarks"):
        """
        Initialize the model evaluator.

        Args:
            benchmarks_dir: Directory containing ground truth data and test files
        """
        self.benchmarks_dir = benchmarks_dir
        self.results: List[Dict[str, Any]] = []
        self._ground_truth: Optional[List[Dict[str, Any]]] = None

    def load_ground_truth(self) -> List[Dict[str, Any]]:
        """
        Load ground truth data from the benchmarks directory.

        Returns:
            List of ground truth dictionaries with 'file' and 'expected' keys

        Raises:
            FileNotFoundError: If ground truth file doesn't exist
        """
        gt_path = os.path.join(self.benchmarks_dir, "ground_truth.json")

        if not os.path.exists(gt_path):
            logger.warning(f"Ground truth file not found: {gt_path}")
            return []

        try:
            with open(gt_path, 'r', encoding='utf-8') as f:
                self._ground_truth = json.load(f)
            logger.info(f"Loaded {len(self._ground_truth)} ground truth entries")
            return self._ground_truth
        except Exception as e:
            logger.error(f"Error loading ground truth: {str(e)}")
            return []

    def evaluate_extraction_model(
        self,
        model_name: str,
        extract_fn: Callable,
        test_files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate an extraction model against ground truth data.

        Args:
            model_name: Human-readable name for the model
            extract_fn: Callable that takes a file path and returns extracted data dict
            test_files: Optional list of specific test file paths.
                       If None, uses all files from ground truth.

        Returns:
            Dictionary with evaluation metrics:
                - 'model_name': Name of the model
                - 'accuracy': Overall accuracy (0.0 to 1.0)
                - 'field_accuracies': Per-field accuracy scores
                - 'avg_time': Average processing time in seconds
                - 'failure_rate': Percentage of failed extractions
                - 'total_files': Number of files tested
                - 'results': Detailed per-file results
        """
        if self._ground_truth is None:
            self.load_ground_truth()

        if not self._ground_truth:
            logger.warning("No ground truth data available for evaluation")
            return self._empty_result(model_name)

        ground_truth = self._ground_truth
        if test_files:
            ground_truth = [gt for gt in ground_truth if gt['file'] in test_files]

        total = len(ground_truth)
        if total == 0:
            return self._empty_result(model_name)

        successes = 0
        failures = 0
        times = []
        field_scores: Dict[str, List[float]] = {}
        detailed_results = []

        logger.info(f"Evaluating model '{model_name}' on {total} test files...")

        for gt_entry in ground_truth:
            file_name = gt_entry['file']
            expected = gt_entry['expected']
            file_path = os.path.join(self.benchmarks_dir, "sample_invoices", file_name)

            if not os.path.exists(file_path):
                logger.warning(f"Test file not found: {file_path}")
                failures += 1
                detailed_results.append({
                    'file': file_name,
                    'status': 'file_not_found',
                    'extracted': None,
                    'scores': {}
                })
                continue

            # Run extraction
            start_time = time.perf_counter()
            try:
                extracted = extract_fn(file_path)
                elapsed = time.perf_counter() - start_time
                times.append(elapsed)

                if extracted is None:
                    failures += 1
                    detailed_results.append({
                        'file': file_name,
                        'status': 'extraction_returned_none',
                        'time': round(elapsed, 3),
                        'extracted': None,
                        'scores': {}
                    })
                    continue

                # Calculate field-level accuracy
                file_scores = self._calculate_field_accuracy(extracted, expected)

                for field, score in file_scores.items():
                    if field not in field_scores:
                        field_scores[field] = []
                    field_scores[field].append(score)

                # Overall file accuracy is average of field scores
                if file_scores:
                    file_accuracy = sum(file_scores.values()) / len(file_scores)
                else:
                    file_accuracy = 0.0

                successes += 1

                detailed_results.append({
                    'file': file_name,
                    'status': 'success',
                    'time': round(elapsed, 3),
                    'accuracy': round(file_accuracy, 4),
                    'extracted': extracted,
                    'expected': expected,
                    'scores': {k: round(v, 4) for k, v in file_scores.items()}
                })

            except Exception as e:
                elapsed = time.perf_counter() - start_time
                times.append(elapsed)
                failures += 1
                logger.error(f"Extraction failed for {file_name}: {str(e)}")
                detailed_results.append({
                    'file': file_name,
                    'status': 'error',
                    'error': str(e),
                    'time': round(elapsed, 3),
                    'extracted': None,
                    'scores': {}
                })

        # Aggregate metrics
        avg_field_accuracies = {
            field: round(sum(scores) / len(scores), 4) if scores else 0.0
            for field, scores in field_scores.items()
        }

        overall_accuracy = (
            sum(sum(scores) for scores in field_scores.values()) /
            sum(len(scores) for scores in field_scores.values())
            if field_scores else 0.0
        )

        result = {
            'model_name': model_name,
            'accuracy': round(overall_accuracy, 4),
            'field_accuracies': avg_field_accuracies,
            'avg_time': round(sum(times) / len(times), 3) if times else 0.0,
            'total_time': round(sum(times), 3),
            'failure_rate': round(failures / total, 4) if total > 0 else 0.0,
            'total_files': total,
            'successes': successes,
            'failures': failures,
            'results': detailed_results,
            'evaluated_at': datetime.now().isoformat()
        }

        self.results.append(result)
        logger.info(
            f"Model '{model_name}': accuracy={overall_accuracy:.2%}, "
            f"avg_time={result['avg_time']:.3f}s, "
            f"failure_rate={result['failure_rate']:.0%}"
        )

        return result

    def evaluate_classification_model(
        self,
        model_name: str,
        classify_fn: Callable,
        test_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluate a document classification model.

        Args:
            model_name: Human-readable name for the model
            classify_fn: Callable that takes a file path and returns classification dict
            test_data: List of dicts with 'file' and 'expected_type' keys

        Returns:
            Dictionary with classification evaluation metrics
        """
        total = len(test_data)
        correct = 0
        times = []
        detailed_results = []

        logger.info(f"Evaluating classifier '{model_name}' on {total} test files...")

        for entry in test_data:
            file_path = os.path.join(self.benchmarks_dir, "sample_invoices", entry['file'])
            expected_type = entry['expected_type']

            if not os.path.exists(file_path):
                detailed_results.append({
                    'file': entry['file'],
                    'status': 'file_not_found'
                })
                continue

            start_time = time.perf_counter()
            try:
                result = classify_fn(file_path)
                elapsed = time.perf_counter() - start_time
                times.append(elapsed)

                predicted_type = result.get('document_type', 'other')
                is_correct = predicted_type == expected_type

                if is_correct:
                    correct += 1

                detailed_results.append({
                    'file': entry['file'],
                    'expected': expected_type,
                    'predicted': predicted_type,
                    'confidence': result.get('confidence', 0.0),
                    'correct': is_correct,
                    'time': round(elapsed, 3)
                })

            except Exception as e:
                elapsed = time.perf_counter() - start_time
                times.append(elapsed)
                detailed_results.append({
                    'file': entry['file'],
                    'status': 'error',
                    'error': str(e),
                    'time': round(elapsed, 3)
                })

        accuracy = correct / total if total > 0 else 0.0

        result = {
            'model_name': model_name,
            'accuracy': round(accuracy, 4),
            'correct': correct,
            'total': total,
            'avg_time': round(sum(times) / len(times), 3) if times else 0.0,
            'results': detailed_results,
            'evaluated_at': datetime.now().isoformat()
        }

        self.results.append(result)
        logger.info(f"Classifier '{model_name}': accuracy={accuracy:.2%}, correct={correct}/{total}")
        return result

    def evaluate_transcription_model(
        self,
        model_name: str,
        transcribe_fn: Callable,
        test_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluate a speech-to-text model.

        Args:
            model_name: Human-readable name for the model
            transcribe_fn: Callable that takes a file path and returns transcription dict
            test_data: List of dicts with 'file' and 'expected_text' keys

        Returns:
            Dictionary with transcription evaluation metrics (including WER)
        """
        total = len(test_data)
        times = []
        wer_scores = []
        detailed_results = []

        logger.info(f"Evaluating transcription model '{model_name}' on {total} files...")

        for entry in test_data:
            file_path = os.path.join(self.benchmarks_dir, "sample_invoices", entry['file'])
            expected_text = entry['expected_text']

            if not os.path.exists(file_path):
                detailed_results.append({
                    'file': entry['file'],
                    'status': 'file_not_found'
                })
                continue

            start_time = time.perf_counter()
            try:
                result = transcribe_fn(file_path)
                elapsed = time.perf_counter() - start_time
                times.append(elapsed)

                predicted_text = result.get('text', '')
                wer = self._calculate_wer(expected_text, predicted_text)
                wer_scores.append(wer)

                detailed_results.append({
                    'file': entry['file'],
                    'expected': expected_text,
                    'predicted': predicted_text,
                    'wer': round(wer, 4),
                    'time': round(elapsed, 3)
                })

            except Exception as e:
                elapsed = time.perf_counter() - start_time
                times.append(elapsed)
                detailed_results.append({
                    'file': entry['file'],
                    'status': 'error',
                    'error': str(e),
                    'time': round(elapsed, 3)
                })

        avg_wer = sum(wer_scores) / len(wer_scores) if wer_scores else 1.0

        result = {
            'model_name': model_name,
            'avg_wer': round(avg_wer, 4),
            'accuracy': round(1 - avg_wer, 4),  # Inverse of WER as accuracy proxy
            'total': total,
            'avg_time': round(sum(times) / len(times), 3) if times else 0.0,
            'results': detailed_results,
            'evaluated_at': datetime.now().isoformat()
        }

        self.results.append(result)
        logger.info(f"Transcription '{model_name}': avg_wer={avg_wer:.2%}, avg_time={result['avg_time']:.3f}s")
        return result

    def compare_models(self) -> Dict[str, Any]:
        """
        Generate a comparative summary of all evaluated models.

        Returns:
            Dictionary with comparison data including rankings and summaries
        """
        if not self.results:
            return {'models': [], 'summary': 'No models evaluated yet'}

        comparison = {
            'models': [],
            'best_accuracy': None,
            'fastest': None,
            'most_reliable': None,
            'evaluated_at': datetime.now().isoformat()
        }

        for result in self.results:
            summary = {
                'model_name': result['model_name'],
                'accuracy': result.get('accuracy', 0.0),
                'avg_time': result.get('avg_time', 0.0),
                'failure_rate': result.get('failure_rate', 0.0),
            }
            comparison['models'].append(summary)

        # Rank by accuracy
        by_accuracy = sorted(comparison['models'], key=lambda x: x['accuracy'], reverse=True)
        if by_accuracy:
            comparison['best_accuracy'] = by_accuracy[0]['model_name']

        # Rank by speed
        timed_models = [m for m in comparison['models'] if m['avg_time'] > 0]
        if timed_models:
            by_speed = sorted(timed_models, key=lambda x: x['avg_time'])
            comparison['fastest'] = by_speed[0]['model_name']

        # Rank by reliability
        by_reliability = sorted(comparison['models'], key=lambda x: x.get('failure_rate', 1.0))
        if by_reliability:
            comparison['most_reliable'] = by_reliability[0]['model_name']

        return comparison

    def export_results(self, output_path: Optional[str] = None) -> str:
        """
        Save evaluation results as JSON.

        Args:
            output_path: Output file path. Defaults to benchmarks/results.json.

        Returns:
            Path to the saved results file
        """
        if output_path is None:
            output_path = os.path.join(self.benchmarks_dir, "results.json")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        export_data = {
            'evaluation_date': datetime.now().isoformat(),
            'total_models_evaluated': len(self.results),
            'results': self.results,
            'comparison': self.compare_models()
        }

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=4, default=str)
            logger.info(f"Evaluation results saved to {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to save results: {str(e)}")
            raise

    def _calculate_field_accuracy(
        self,
        extracted: Dict[str, Any],
        expected: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Compare individual extracted fields against expected values.

        Args:
            extracted: Dictionary of extracted field values
            expected: Dictionary of expected (ground truth) field values

        Returns:
            Dictionary mapping field names to accuracy scores (0.0 or 1.0 for exact,
            0.0-1.0 for fuzzy matches)
        """
        scores = {}

        for field, expected_value in expected.items():
            if expected_value is None:
                continue

            extracted_value = extracted.get(field)

            if extracted_value is None:
                scores[field] = 0.0
                continue

            # Normalize both values for comparison
            exp_str = str(expected_value).strip().lower()
            ext_str = str(extracted_value).strip().lower()

            if exp_str == ext_str:
                scores[field] = 1.0
            elif field in ['amount', 'vat', 'total_bgn', 'total_euro']:
                # Numeric comparison with tolerance
                scores[field] = self._compare_numeric(expected_value, extracted_value)
            elif field in ['date']:
                # Date comparison
                scores[field] = self._compare_dates(expected_value, extracted_value)
            elif field in ['supplier_name', 'transactor']:
                # Fuzzy string comparison for names
                scores[field] = self._fuzzy_string_match(exp_str, ext_str)
            else:
                # Substring containment check
                if exp_str in ext_str or ext_str in exp_str:
                    scores[field] = 0.8
                else:
                    scores[field] = 0.0

        return scores

    def _compare_numeric(self, expected: Any, extracted: Any) -> float:
        """Compare numeric values with tolerance."""
        try:
            exp_float = float(str(expected).replace(',', '.'))
            ext_float = float(str(extracted).replace(',', '.'))
            if exp_float == 0:
                return 1.0 if ext_float == 0 else 0.0
            diff_pct = abs(exp_float - ext_float) / abs(exp_float)
            if diff_pct <= 0.001:
                return 1.0
            elif diff_pct <= 0.05:
                return 0.8
            elif diff_pct <= 0.1:
                return 0.5
            return 0.0
        except (ValueError, TypeError):
            return 0.0

    def _compare_dates(self, expected: Any, extracted: Any) -> float:
        """Compare date values."""
        exp_str = str(expected).strip()[:10]
        ext_str = str(extracted).strip()[:10]

        if exp_str == ext_str:
            return 1.0

        # Try parsing both dates
        date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%d.%m.%Y']
        exp_date = None
        ext_date = None

        for fmt in date_formats:
            try:
                exp_date = datetime.strptime(exp_str, fmt)
                break
            except ValueError:
                continue

        for fmt in date_formats:
            try:
                ext_date = datetime.strptime(ext_str, fmt)
                break
            except ValueError:
                continue

        if exp_date and ext_date:
            day_diff = abs((exp_date - ext_date).days)
            if day_diff == 0:
                return 1.0
            elif day_diff <= 1:
                return 0.8
            elif day_diff <= 7:
                return 0.5
            return 0.0

        return 0.0

    def _fuzzy_string_match(self, s1: str, s2: str) -> float:
        """Simple fuzzy string matching based on common tokens."""
        if s1 == s2:
            return 1.0

        tokens1 = set(s1.split())
        tokens2 = set(s2.split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        jaccard = len(intersection) / len(union) if union else 0.0
        return round(jaccard, 4)

    def _calculate_wer(self, reference: str, hypothesis: str) -> float:
        """
        Calculate Word Error Rate (WER) between reference and hypothesis text.

        Args:
            reference: Ground truth text
            hypothesis: Predicted text

        Returns:
            WER score (0.0 = perfect, 1.0 = completely wrong)
        """
        ref_words = reference.lower().split()
        hyp_words = hypothesis.lower().split()

        if not ref_words:
            return 0.0 if not hyp_words else 1.0

        # Dynamic programming for edit distance
        d = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]

        for i in range(len(ref_words) + 1):
            d[i][0] = i
        for j in range(len(hyp_words) + 1):
            d[0][j] = j

        for i in range(1, len(ref_words) + 1):
            for j in range(1, len(hyp_words) + 1):
                if ref_words[i - 1] == hyp_words[j - 1]:
                    d[i][j] = d[i - 1][j - 1]
                else:
                    d[i][j] = min(
                        d[i - 1][j] + 1,      # deletion
                        d[i][j - 1] + 1,      # insertion
                        d[i - 1][j - 1] + 1   # substitution
                    )

        wer = d[len(ref_words)][len(hyp_words)] / len(ref_words)
        return min(wer, 1.0)

    def _empty_result(self, model_name: str) -> Dict[str, Any]:
        """Return an empty evaluation result."""
        return {
            'model_name': model_name,
            'accuracy': 0.0,
            'field_accuracies': {},
            'avg_time': 0.0,
            'total_time': 0.0,
            'failure_rate': 1.0,
            'total_files': 0,
            'successes': 0,
            'failures': 0,
            'results': [],
            'evaluated_at': datetime.now().isoformat()
        }

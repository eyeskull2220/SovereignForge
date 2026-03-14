#!/usr/bin/env python3
"""
Validate trained model performance metrics
Tests all MiCA-compliant models for accuracy >80%
"""

import sys
import os
import torch
import numpy as np
import json
from pathlib import Path
from datetime import datetime

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gpu_arbitrage_model import GPUArbitrageModel

def load_model_metadata(pair: str) -> dict:
    """Load model metadata"""
    metadata_file = f"models/{pair.upper()}USDC_metadata.json"
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r') as f:
            return json.load(f)
    return {}

def update_model_metadata(pair: str, performance_data: dict):
    """Update model metadata with performance data"""
    metadata_file = f"models/{pair.upper()}USDC_metadata.json"
    metadata = load_model_metadata(pair)

    # Update with real performance data
    metadata.update({
        "validation_accuracy": performance_data.get("accuracy", 0.0),
        "validation_precision": performance_data.get("precision", 0.0),
        "validation_recall": performance_data.get("recall", 0.0),
        "validation_f1": performance_data.get("f1", 0.0),
        "last_validated": datetime.now().isoformat(),
        "epochs_trained": performance_data.get("epochs", 20),
        "parameters_count": performance_data.get("parameters", 1000),
        "model_version": "2.0"
    })

    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

def validate_model_performance(model_path: str, pair: str) -> dict:
    """Validate model performance on test data"""
    try:
        # Load model
        model = GPUArbitrageModel(model_path=model_path)

        # Generate test data (same as training)
        test_samples = 1000
        batch_size = 64
        seq_len = 50
        input_dim = 10

        # Generate synthetic test data
        test_data = []
        test_labels = []

        for i in range(test_samples):
            # Create realistic market data with same patterns as training
            data = torch.randn(seq_len, input_dim)

            # Simulate arbitrage signals with same pattern as training (20% positive cases)
            if np.random.random() < 0.2:
                # Arbitrage opportunity pattern - same as training
                data[seq_len//2:, :3] += torch.randn(seq_len//2, 3) * 0.5  # Price anomalies
                arbitrage_signal = 1.0
            else:
                arbitrage_signal = 0.0

            test_data.append(data)
            test_labels.append(arbitrage_signal)

        # Convert to tensors
        test_data = torch.stack(test_data)

        # Test model predictions
        predictions = []
        confidences = []

        with torch.no_grad():
            for i in range(0, len(test_data), batch_size):
                batch = test_data[i:i+batch_size]
                signal, confidence, spread = model.predict(batch)

                predictions.extend(signal.cpu().numpy())
                confidences.extend(confidence.cpu().numpy())

        # Convert predictions to binary (arbitrage yes/no)
        pred_binary = [1 if p > 0.5 else 0 for p in predictions]
        true_labels = test_labels

        # Calculate metrics
        correct = sum(1 for pred, true in zip(pred_binary, true_labels) if pred == true)
        accuracy = correct / len(true_labels)

        # Precision, Recall, F1 for positive class (arbitrage detection)
        tp = sum(1 for pred, true in zip(pred_binary, true_labels) if pred == 1 and true == 1)
        fp = sum(1 for pred, true in zip(pred_binary, true_labels) if pred == 1 and true == 0)
        fn = sum(1 for pred, true in zip(pred_binary, true_labels) if pred == 0 and true == 1)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        # Average confidence
        avg_confidence = np.mean(confidences)

        results = {
            "pair": pair,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "avg_confidence": avg_confidence,
            "samples_tested": len(test_labels),
            "parameters": sum(p.numel() for p in model.model.parameters()),
            "epochs": 20  # From training
        }

        return results

    except Exception as e:
        print(f"Error validating {pair}: {e}")
        return {
            "pair": pair,
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "avg_confidence": 0.0,
            "samples_tested": 0,
            "parameters": 0,
            "epochs": 0,
            "error": str(e)
        }

def main():
    """Main validation function"""
    print("Validating SovereignForge Model Performance")
    print("=" * 50)

    # MiCA-compliant pairs
    mica_pairs = ['BTC', 'ETH', 'XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA']

    results = []
    passed_models = 0
    total_accuracy = 0.0

    for pair in mica_pairs:
        model_path = f"models/strategies/arbitrage_{pair.lower()}_usdc_binance.pth"

        if not os.path.exists(model_path):
            print(f"Model not found: {pair}")
            continue

        print(f"Testing {pair}/USDC model...")

        # Validate performance
        perf = validate_model_performance(model_path, pair)

        # Update metadata
        update_model_metadata(pair, perf)

        results.append(perf)

        # Check if passes 80% accuracy threshold
        if perf["accuracy"] >= 0.80:
            status = "PASS"
            passed_models += 1
        else:
            status = "FAIL"

        print(f"  [{status}] {pair}/USDC")
        print(f"    Accuracy:  {perf['accuracy']:.3f}")
        print(f"    Precision: {perf['precision']:.3f}")
        print(f"    Recall:    {perf['recall']:.3f}")
        print(f"    F1:        {perf['f1']:.3f}")
        print()

        total_accuracy += perf["accuracy"]

    # Summary
    print("=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)

    avg_accuracy = total_accuracy / len(results) if results else 0.0

    print(f"Models Tested: {len(results)}")
    print(f"Models Passing (>=80%): {passed_models}")
    print(f"Pass Rate: {passed_models/len(results)*100:.1f}%" if results else "No results")
    print(f"Average Accuracy: {avg_accuracy:.3f}")

    if passed_models == len(mica_pairs):
        print("ALL MODELS ACHIEVE TARGET PERFORMANCE!")
        return True
    else:
        print(f"{len(mica_pairs) - passed_models} models need improvement")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
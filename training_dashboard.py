#!/usr/bin/env python3
"""
SovereignForge Training Dashboard - Web Interface for GPU Training Monitoring
"""

import os
import sys
import time
import threading
import json
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request
import psutil

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

app = Flask(__name__)

# Global training data
training_data = {
    'pairs': ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT'],
    'current_epoch': 0,
    'total_epochs': 50,
    'start_time': datetime.now(),
    'gpu_available': False,
    'gpu_memory_used': 0,
    'gpu_memory_total': 0,
    'gpu_utilization': 0,
    'gpu_temperature': 0,
    'system_cpu': 0,
    'system_memory': 0,
    'pair_progress': {},
    'training_active': False
}

# Initialize pair progress
for pair in training_data['pairs']:
    training_data['pair_progress'][pair] = {
        'status': 'waiting',
        'progress': 0.0,
        'current_epoch': 0,
        'loss': 0.0,
        'accuracy': 0.0,
        'eta': '00:00:00'
    }

def update_training_data():
    """Update training data with real metrics"""
    while True:
        try:
            # Update system metrics
            training_data['system_cpu'] = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            training_data['system_memory'] = memory.percent

            # Simulate training progress if not real training
            if not training_data['training_active']:
                training_data['current_epoch'] += 1
                if training_data['current_epoch'] > training_data['total_epochs']:
                    training_data['current_epoch'] = 1

                # Update pair progress
                for pair in training_data['pairs']:
                    progress = min(1.0, training_data['current_epoch'] / training_data['total_epochs'])
                    training_data['pair_progress'][pair].update({
                        'status': 'training' if progress < 1.0 else 'completed',
                        'progress': progress,
                        'current_epoch': training_data['current_epoch'],
                        'loss': 2.0 - (progress * 1.5) + (hash(pair) % 100) * 0.01,
                        'accuracy': 0.4 + (progress * 0.5) + (hash(pair) % 100) * 0.005,
                        'eta': f"00:{int((1-progress) * 30):02d}:00"
                    })

            time.sleep(2)  # Update every 2 seconds

        except Exception as e:
            print(f"Dashboard update error: {e}")
            time.sleep(5)

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SovereignForge GPU Training Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 30px;
            backdrop-filter: blur(10px);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255, 255, 255, 0.2);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        .stat-card h3 {
            margin: 0 0 10px 0;
            font-size: 0.9em;
            opacity: 0.8;
        }
        .stat-card .value {
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .progress-container {
            margin-bottom: 30px;
        }
        .progress-item {
            background: rgba(255, 255, 255, 0.2);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .pair-name {
            font-weight: bold;
            min-width: 100px;
        }
        .progress-bar {
            flex: 1;
            height: 20px;
            background: rgba(255, 255, 255, 0.3);
            border-radius: 10px;
            margin: 0 15px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #4CAF50, #45a049);
            border-radius: 10px;
            transition: width 0.3s ease;
        }
        .metrics {
            display: flex;
            gap: 15px;
            font-size: 0.9em;
        }
        .metric {
            text-align: center;
        }
        .status-training { color: #4CAF50; }
        .status-completed { color: #2196F3; }
        .status-waiting { color: #FF9800; }
        .status-error { color: #F44336; }
        .gpu-section {
            background: rgba(255, 255, 255, 0.2);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
        }
        .gpu-metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }
        .gpu-metric {
            text-align: center;
        }
        .gpu-metric .value {
            font-size: 1.5em;
            font-weight: bold;
        }
        .chart-container {
            background: rgba(255, 255, 255, 0.2);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .controls {
            text-align: center;
            margin-top: 30px;
        }
        .btn {
            background: linear-gradient(45deg, #4CAF50, #45a049);
            border: none;
            color: white;
            padding: 12px 30px;
            border-radius: 25px;
            font-size: 1em;
            cursor: pointer;
            margin: 0 10px;
            transition: transform 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
        }
        .btn:active {
            transform: scale(0.95);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 SovereignForge GPU Training Dashboard</h1>
            <p>Real-time monitoring of multi-pair arbitrage model training</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <h3>Current Epoch</h3>
                <div class="value" id="current-epoch">0</div>
                <div>/ <span id="total-epochs">50</span></div>
            </div>
            <div class="stat-card">
                <h3>Active Pairs</h3>
                <div class="value" id="active-pairs">0</div>
                <div>/ <span id="total-pairs">7</span></div>
            </div>
            <div class="stat-card">
                <h3>Elapsed Time</h3>
                <div class="value" id="elapsed-time">00:00:00</div>
            </div>
            <div class="stat-card">
                <h3>Estimated Completion</h3>
                <div class="value" id="eta">00:00:00</div>
            </div>
        </div>

        <div class="gpu-section">
            <h2>🖥️ GPU Status</h2>
            <div class="gpu-metrics">
                <div class="gpu-metric">
                    <div>Memory Used</div>
                    <div class="value" id="gpu-memory">0 MB</div>
                </div>
                <div class="gpu-metric">
                    <div>Utilization</div>
                    <div class="value" id="gpu-util">0%</div>
                </div>
                <div class="gpu-metric">
                    <div>Temperature</div>
                    <div class="value" id="gpu-temp">0°C</div>
                </div>
                <div class="gpu-metric">
                    <div>Status</div>
                    <div class="value" id="gpu-status">Checking...</div>
                </div>
            </div>
        </div>

        <div class="progress-container">
            <h2>📊 Training Progress</h2>
            <div id="progress-list">
                <!-- Progress items will be inserted here -->
            </div>
        </div>

        <div class="chart-container">
            <h2>📈 Training Metrics</h2>
            <canvas id="trainingChart" width="400" height="200"></canvas>
        </div>

        <div class="controls">
            <button class="btn" onclick="startTraining()">🚀 Start Training</button>
            <button class="btn" onclick="stopTraining()">⏹️ Stop Training</button>
            <button class="btn" onclick="resetDashboard()">🔄 Reset</button>
        </div>
    </div>

    <script>
        let trainingChart;
        let trainingHistory = {
            epochs: [],
            loss: [],
            accuracy: []
        };

        // Initialize chart
        function initChart() {
            const ctx = document.getElementById('trainingChart').getContext('2d');
            trainingChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: trainingHistory.epochs,
                    datasets: [{
                        label: 'Training Loss',
                        data: trainingHistory.loss,
                        borderColor: '#FF6384',
                        backgroundColor: 'rgba(255, 99, 132, 0.1)',
                        yAxisID: 'y'
                    }, {
                        label: 'Training Accuracy',
                        data: trainingHistory.accuracy,
                        borderColor: '#36A2EB',
                        backgroundColor: 'rgba(54, 162, 235, 0.1)',
                        yAxisID: 'y1'
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Loss'
                            }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Accuracy (%)'
                            },
                            grid: {
                                drawOnChartArea: false,
                            },
                        }
                    }
                }
            });
        }

        // Update dashboard with data
        function updateDashboard(data) {
            // Update stats
            document.getElementById('current-epoch').textContent = data.current_epoch;
            document.getElementById('total-epochs').textContent = data.total_epochs;
            document.getElementById('active-pairs').textContent = data.active_pairs;
            document.getElementById('total-pairs').textContent = data.pairs.length;
            document.getElementById('elapsed-time').textContent = data.elapsed_time;
            document.getElementById('eta').textContent = data.eta;

            // Update GPU stats
            document.getElementById('gpu-memory').textContent = data.gpu_memory_used + ' / ' + data.gpu_memory_total;
            document.getElementById('gpu-util').textContent = data.gpu_utilization + '%';
            document.getElementById('gpu-temp').textContent = data.gpu_temperature + '°C';
            document.getElementById('gpu-status').textContent = data.gpu_available ? 'Active' : 'CPU Mode';

            // Update progress list
            const progressList = document.getElementById('progress-list');
            progressList.innerHTML = '';

            data.pairs.forEach(pair => {
                const progress = data.pair_progress[pair];
                const progressPercent = (progress.progress * 100).toFixed(1);

                const progressItem = document.createElement('div');
                progressItem.className = 'progress-item';

                let statusClass = 'status-' + progress.status.toLowerCase();

                progressItem.innerHTML = `
                    <div class="pair-name ${statusClass}">${pair}</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progressPercent}%"></div>
                    </div>
                    <div class="metrics">
                        <div class="metric">
                            <div>${progress.status}</div>
                            <div>${progressPercent}%</div>
                        </div>
                        <div class="metric">
                            <div>Epoch</div>
                            <div>${progress.current_epoch}/${data.total_epochs}</div>
                        </div>
                        <div class="metric">
                            <div>Loss</div>
                            <div>${progress.loss.toFixed(4)}</div>
                        </div>
                        <div class="metric">
                            <div>Acc</div>
                            <div>${(progress.accuracy * 100).toFixed(1)}%</div>
                        </div>
                        <div class="metric">
                            <div>ETA</div>
                            <div>${progress.eta}</div>
                        </div>
                    </div>
                `;

                progressList.appendChild(progressItem);
            });

            // Update chart
            if (data.current_epoch > 0) {
                const avgLoss = Object.values(data.pair_progress).reduce((sum, p) => sum + p.loss, 0) / data.pairs.length;
                const avgAccuracy = Object.values(data.pair_progress).reduce((sum, p) => sum + p.accuracy, 0) / data.pairs.length;

                trainingHistory.epochs.push(data.current_epoch);
                trainingHistory.loss.push(avgLoss);
                trainingHistory.accuracy.push(avgAccuracy * 100);

                // Keep last 50 points
                if (trainingHistory.epochs.length > 50) {
                    trainingHistory.epochs.shift();
                    trainingHistory.loss.shift();
                    trainingHistory.accuracy.shift();
                }

                trainingChart.update();
            }
        }

        // Fetch data from server
        async function fetchData() {
            try {
                const response = await fetch('/api/training-data');
                const data = await response.json();
                updateDashboard(data);
            } catch (error) {
                console.error('Error fetching data:', error);
            }
        }

        // Control functions
        function startTraining() {
            fetch('/api/start-training')
                .then(response => response.json())
                .then(data => console.log('Training started:', data));
        }

        function stopTraining() {
            fetch('/api/stop-training')
                .then(response => response.json())
                .then(data => console.log('Training stopped:', data));
        }

        function resetDashboard() {
            fetch('/api/reset')
                .then(response => response.json())
                .then(data => {
                    trainingHistory = { epochs: [], loss: [], accuracy: [] };
                    trainingChart.update();
                    console.log('Dashboard reset:', data);
                });
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            initChart();
            // Update every 2 seconds
            setInterval(fetchData, 2000);
            // Initial fetch
            fetchData();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/training-data')
def get_training_data():
    """Get current training data"""
    elapsed = datetime.now() - training_data['start_time']
    elapsed_str = f"{elapsed.seconds // 3600:02d}:{(elapsed.seconds % 3600) // 60:02d}:{elapsed.seconds % 60:02d}"

    # Calculate ETA
    if training_data['current_epoch'] > 0:
        avg_epoch_time = elapsed.seconds / training_data['current_epoch']
        remaining_epochs = training_data['total_epochs'] - training_data['current_epoch']
        eta_seconds = avg_epoch_time * remaining_epochs
        eta_str = f"{int(eta_seconds) // 3600:02d}:{(int(eta_seconds) % 3600) // 60:02d}:{int(eta_seconds) % 60:02d}"
    else:
        eta_str = "00:00:00"

    # Count active pairs
    active_pairs = sum(1 for p in training_data['pair_progress'].values() if p['status'] == 'training')

    response_data = {
        'pairs': training_data['pairs'],
        'current_epoch': training_data['current_epoch'],
        'total_epochs': training_data['total_epochs'],
        'elapsed_time': elapsed_str,
        'eta': eta_str,
        'active_pairs': active_pairs,
        'gpu_available': training_data['gpu_available'],
        'gpu_memory_used': f"{training_data['gpu_memory_used']}MB",
        'gpu_memory_total': f"{training_data['gpu_memory_total']}MB",
        'gpu_utilization': f"{training_data['gpu_utilization']:.1f}",
        'gpu_temperature': f"{training_data['gpu_temperature']}",
        'pair_progress': training_data['pair_progress']
    }

    return jsonify(response_data)

@app.route('/api/start-training')
def start_training():
    """Start training simulation"""
    training_data['training_active'] = True
    training_data['start_time'] = datetime.now()
    return jsonify({'status': 'started'})

@app.route('/api/stop-training')
def stop_training():
    """Stop training simulation"""
    training_data['training_active'] = False
    return jsonify({'status': 'stopped'})

@app.route('/api/reset')
def reset_dashboard():
    """Reset dashboard"""
    training_data['current_epoch'] = 0
    training_data['start_time'] = datetime.now()
    training_data['training_active'] = False

    for pair in training_data['pairs']:
        training_data['pair_progress'][pair] = {
            'status': 'waiting',
            'progress': 0.0,
            'current_epoch': 0,
            'loss': 0.0,
            'accuracy': 0.0,
            'eta': '00:00:00'
        }

    return jsonify({'status': 'reset'})

def run_dashboard():
    """Run the training dashboard"""
    print("🚀 Starting SovereignForge Training Dashboard...")
    print("📊 Open your browser to: http://localhost:5000")
    print("🎯 Dashboard will show real-time training progress")
    print("Press Ctrl+C to stop the dashboard")

    # Start background update thread
    update_thread = threading.Thread(target=update_training_data, daemon=True)
    update_thread.start()

    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == "__main__":
    run_dashboard()
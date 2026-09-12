"""Independent truth and end-to-end export checks for the PNT benchmark."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from models.pnt.estimator import G_STANDARD, PNTStateEstimator
from models.pnt.experiment import PNTExperimentConfig, run_experiment
from models.session_records import load_session
from tools.run_pnt_experiment import main


class PNTExperimentTest(unittest.TestCase):
    def test_constant_acceleration_matches_analytic_trajectory(self):
        estimator = PNTStateEstimator(dt_s=0.01)
        for _ in range(100):
            estimator.predict(np.array([2., 0., G_STANDARD]), np.zeros(3))
        np.testing.assert_allclose(estimator.state.position_m, [1., 0., 0.], atol=1e-12)
        np.testing.assert_allclose(estimator.state.velocity_m_s, [2., 0., 0.], atol=1e-12)

    def test_reference_observes_bias_not_absolute_acceleration(self):
        estimator = PNTStateEstimator()
        reference = np.array([2., 0., G_STANDARD])
        response = estimator.update_quantum_interferometer(reference, reference + [0.01, 0., 0.])
        self.assertEqual(response['status'], 'AI_UPDATE_SUCCESS')
        self.assertGreater(estimator.state.accel_bias_m_s2[0], 0.009)
        self.assertLess(estimator.state.accel_bias_m_s2[0], 0.011)
        self.assertEqual(estimator.state.accel_bias_m_s2[2], 0.)
        self.assertGreaterEqual(np.linalg.eigvalsh(estimator.P).min(), -1e-12)

    def test_outlier_is_rejected_without_mutating_state_or_covariance(self):
        estimator = PNTStateEstimator()
        covariance = estimator.P.copy()
        response = estimator.update_quantum_interferometer(np.array([100., 100., 100.]))
        self.assertEqual(response['status'], 'AI_UPDATE_REJECTED')
        np.testing.assert_array_equal(estimator.P, covariance)
        np.testing.assert_array_equal(estimator.state.accel_bias_m_s2, np.zeros(3))

    def test_nonfinite_measurements_are_rejected_before_mutation(self):
        estimator = PNTStateEstimator()
        with self.assertRaises(ValueError):
            estimator.predict(np.array([np.nan, 0., 0.]), np.zeros(3))
        np.testing.assert_array_equal(estimator.state.position_m, np.zeros(3))
        with self.assertRaises(ValueError):
            estimator.update_quantum_interferometer(np.array([np.inf, 0., 0.]))

    def test_metrics_are_calculated_from_truth_and_change_with_seed(self):
        config = PNTExperimentConfig(duration_s=2.0)
        result = run_experiment(config)
        self.assertEqual(result, run_experiment(config))
        self.assertNotEqual(result['metrics'], run_experiment(PNTExperimentConfig(duration_s=2., seed=17))['metrics'])
        for name in ('classical', 'reference_aided'):
            errors = [np.sum((np.array(row[f'{name}_position_m']) - row['truth_position_m'])**2) for row in result['trajectory']]
            self.assertAlmostEqual(np.sqrt(np.mean(errors)), result['metrics'][name]['position_rmse_m'])
        self.assertEqual(result['reference_samples'], 4)
        self.assertLess(result['metrics']['reference_aided']['position_rmse_m'], result['metrics']['classical']['position_rmse_m'])

    def test_invalid_workloads_are_rejected(self):
        for kwargs in ({'dt_s': 0}, {'duration_s': -1}, {'duration_s': float('inf')},
                       {'duration_s': 1.005}, {'duration_s': .1}, {'seed': -1},
                       {'dt_s': 1}, {'duration_s': 1e9}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PNTExperimentConfig(**kwargs)

    def test_cli_writes_reproducible_metrics_bound_to_valid_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'record.json'
            args = ['--duration', '1', '--seed', '91', '--output-session-record', str(output)]
            self.assertEqual(main(args), 0)
            metrics_file = output.with_suffix('.metrics.json')
            metrics_bytes = metrics_file.read_bytes()
            record_bytes = output.read_bytes()
            record = load_session(output)[0]
            self.assertEqual(record['model']['artifact_id'], 'sha256:' + hashlib.sha256(metrics_bytes).hexdigest())
            self.assertEqual(record['source_sequence_ranges'][0]['last_sequence'], 99)
            self.assertEqual(record['source_sequence_ranges'][1]['last_sequence'], 1)
            self.assertIn('SIMULATED_INPUT', record['status_flags'])
            self.assertEqual(main(args), 0)
            self.assertEqual(metrics_file.read_bytes(), metrics_bytes)
            self.assertEqual(output.read_bytes(), record_bytes)
            bad_output = Path(temporary) / 'bad.json'
            self.assertEqual(main(['--dt','0','--output-session-record',str(bad_output)]), 1)
            self.assertFalse(bad_output.exists())

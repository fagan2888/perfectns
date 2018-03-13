#!/usr/bin/env python
"""
Test the perfectns module installation.
"""

import os
import shutil
import unittest
import numpy as np
import numpy.testing
import pandas as pd
import matplotlib
import perfectns.settings
import perfectns.estimators as e
import perfectns.cached_gaussian_prior
import perfectns.likelihoods as likelihoods
import perfectns.nested_sampling as ns
import perfectns.results_tables as rt
import perfectns.maths_functions
import perfectns.priors as priors
import perfectns.plots
import nestcheck.analyse_run as ar
import nestcheck.data_processing as dp

ESTIMATOR_LIST = [e.LogZ(),
                  e.Z(),
                  e.ParamMean(),
                  e.ParamSquaredMean(),
                  e.ParamCred(0.5),
                  e.ParamCred(0.84),
                  e.RMean(from_theta=True),
                  e.RCred(0.84, from_theta=True)]
TEST_CACHE_DIR = 'cache_tests/'


class TestNestedSampling(unittest.TestCase):

    def setUp(self):
        """Check TEST_CACHE_DIR does not already exist."""
        assert not os.path.exists(TEST_CACHE_DIR[:-1]), \
            ('Directory ' + TEST_CACHE_DIR[:-1] + ' exists! Tests use this ' +
             'dir to check caching then delete it afterwards, so the path ' +
             'should be left empty.')

    def tearDown(self):
        """Remove any caches created by the tests."""
        try:
            shutil.rmtree(TEST_CACHE_DIR[:-1])
        except FileNotFoundError:
            pass

    def test_nestcheck_run_format(self):
        """
        Check perfectns runs are compatable with the nestcheck run format
        (excepting their additional 'logx' and 'r' keys).
        """
        settings = get_minimal_settings()
        for dynamic_goal in [None, 0, 0.5, 1]:
            settings.dynamic_goal = dynamic_goal
            run = ns.generate_ns_run(settings)
            del run['logx']
            del run['r']
            dp.check_ns_run(run)

    def test_get_run_data_caching(self):
        settings = get_minimal_settings()
        settings.n_samples_max = 100
        ns.get_run_data(settings, 1, save=True, load=True,
                        check_loaded_settings=True, cache_dir=TEST_CACHE_DIR)
        # test loading and checking settings
        ns.get_run_data(settings, 1, save=True, load=True,
                        check_loaded_settings=True, cache_dir=TEST_CACHE_DIR)
        # test loading and checking settings when settings are not the same
        # this only works for changing a setting which dosnt affect the save
        # name
        settings.n_samples_max += 1
        ns.get_run_data(settings, 1, save=True, load=True,
                        check_loaded_settings=True, cache_dir=TEST_CACHE_DIR)

    def test_get_run_data_unexpected_kwarg(self):
        settings = get_minimal_settings()
        self.assertRaises(TypeError, ns.get_run_data, settings, 1,
                          unexpected=1)

    def test_no_point_thread(self):
        """
        Check generate_single_thread returns None when keep_final_point is
        False and thread is empty.
        """
        settings = get_minimal_settings()
        self.assertIsNone(ns.generate_single_thread(
            settings, -(10 ** -150), 0, keep_final_point=False))

    def test_exact_z_importance(self):
        """Check z_importance with exact=True."""
        imp_exact = ns.z_importance(np.asarray([1., 2.]), np.asarray([5, 5]),
                                    exact=True)
        self.assertEqual(imp_exact[0], 1.)
        self.assertAlmostEqual(imp_exact[1], 0.99082569, places=6)

    def test_min_max_importance(self):
        """
        Check importance condition when the final point is one of the
        ones with high importance.
        """
        settings = get_minimal_settings()
        samples = np.random.random((2, 3))
        loglmm, logxmm = ns.min_max_importance(np.full(2, 1), samples,
                                               settings)
        self.assertEqual(loglmm[1], samples[-1, 0])
        self.assertEqual(logxmm[1], samples[-1, 2])

    def test_tuned_p_importance(self):
        theta = np.random.random((5, 1))
        w_rel = np.full(5, 1)
        imp = np.abs(theta - np.mean(theta))[:, 0]
        imp /= imp.max()
        self.assertTrue(np.array_equal(
            ns.p_importance(theta, w_rel, tuned_dynamic_p=True), imp))


class TestEstimators(unittest.TestCase):

    """
    Test estimators: largely checking the get_true_estimator_values output
    as the functions used for analysing nested sampling runs are mostly
    imported from nestcheck which has its own tests.
    """

    def setUp(self):
        """Get some settings for the get_true_estimator_values tests."""
        self.settings = get_minimal_settings()

    def test_true_logz_value(self):
        self.assertAlmostEqual(
            e.get_true_estimator_values(e.LogZ(), self.settings),
            -6.4529975832506050, places=10)

    def test_true_z_value(self):
        self.assertAlmostEqual(
            e.get_true_estimator_values(e.Z(), self.settings),
            1.5757915157613399e-03, places=10)

    def test_true_param_mean_value(self):
        self.assertEqual(
            e.get_true_estimator_values(e.ParamMean(), self.settings), 0)

    def test_true_param_mean_squared_value(self):
        self.assertAlmostEqual(
            e.get_true_estimator_values(e.ParamSquaredMean(), self.settings),
            9.9009851517647807e-01, places=10)

    def test_true_param_cred_value(self):
        self.assertEqual(
            e.get_true_estimator_values(e.ParamCred(0.5), self.settings), 0)
        self.assertAlmostEqual(
            e.get_true_estimator_values(e.ParamCred(0.84), self.settings),
            9.8952257789120635e-01, places=10)

    def test_true_r_mean_value(self):
        self.assertAlmostEqual(
            e.get_true_estimator_values(e.RMean(), self.settings),
            1.2470645289408879e+00, places=10)

    def test_true_r_cred_value(self):
        self.assertTrue(np.isnan(
            e.get_true_estimator_values(e.RCred(0.84), self.settings)))
        # Test with a list argument as well to cover list version of true
        # get_true_estimator_values
        self.assertTrue(np.isnan(
            e.get_true_estimator_values([e.RCred(0.84)], self.settings)[0]))

    def test_r_not_from_theta(self):
        run_dict_temp = {'theta': np.full((2, 2), 1),
                         'r': np.full((2,), np.sqrt(2)),
                         'logl': np.full((2,), 0.),
                         'nlive_array': np.full((2,), 5.),
                         'settings': {'dims_to_sample': 2, 'n_dim': 2}}
        self.assertAlmostEqual(e.RMean(from_theta=False)(
            run_dict_temp, logw=None), np.sqrt(2), places=10)
        self.assertAlmostEqual(e.RCred(0.84, from_theta=False)(
            run_dict_temp, logw=None), np.sqrt(2), places=10)

    def test_count_samples(self):
        self.assertEqual(e.CountSamples()({'logl': np.zeros(10)}), 10)

    def test_maths_functions(self):
        # By default only used in high dim so manually test with dim=100
        perfectns.maths_functions.sample_nsphere_shells(
            np.asarray([1]), 100, n_sample=1)
        # Check handling of n_sample=None
        self.assertEqual(
            perfectns.maths_functions.sample_nsphere_shells_normal(
                np.asarray([1]), 2, n_sample=None).shape, (1, 2))
        self.assertEqual(
            perfectns.maths_functions.sample_nsphere_shells_beta(
                np.asarray([1]), 2, n_sample=None).shape, (1, 2))


class TestSettings(unittest.TestCase):

    def test_settings_unexpected_arg(self):
        self.assertRaises(
            TypeError, perfectns.settings.PerfectNSSettings, unexpected=0)

    def test_settings_save_name(self):
        settings = perfectns.settings.PerfectNSSettings()
        settings.dynamic_goal = 1
        settings.nbatch = 2
        settings.nlive_const = None
        settings.tuned_dynamic_p = True
        settings.n_samples_max = 100
        settings.dynamic_fraction = 0.8
        settings.dims_to_sample = 2
        self.assertIsInstance(settings.save_name(), str)

    def test_settings_unexpected_attr(self):
        settings = perfectns.settings.PerfectNSSettings()
        self.assertRaises(TypeError, settings.__setattr__, 'unexpected', 1)


class TestLikelihoods(unittest.TestCase):

    def test_standard_ns_exp_power_likelihood_gaussian_prior(self):
        """Check the exp_power likelihood, as well as some functions in
        analyse_run."""
        settings = get_minimal_settings()
        settings.likelihood = likelihoods.ExpPower(likelihood_scale=1,
                                                   power=2)
        self.assertAlmostEqual(
            settings.logx_given_logl(settings.logl_given_logx(-1.0)),
            -1.0, places=12)
        settings.logz_analytic()
        ns_run = ns.generate_ns_run(settings)
        values = ar.run_estimators(ns_run, ESTIMATOR_LIST)
        self.assertFalse(np.any(np.isnan(values)))

    def test_standard_ns_cauchy_likelihood_gaussian_prior(self):
        """Check the Cauchy likelihood."""
        settings = get_minimal_settings()
        settings.likelihood = likelihoods.Cauchy(likelihood_scale=1)
        self.assertAlmostEqual(
            settings.logx_given_logl(settings.logl_given_logx(-1.0)),
            -1.0, places=12)
        settings.logz_analytic()
        ns_run = ns.generate_ns_run(settings)
        values = ar.run_estimators(ns_run, ESTIMATOR_LIST)
        self.assertFalse(np.any(np.isnan(values)))


class TestPriors(unittest.TestCase):

    def setUp(self):
        """Check TEST_CACHE_DIR does not already exist."""
        assert not os.path.exists(TEST_CACHE_DIR[:-1]), \
            ('Directory ' + TEST_CACHE_DIR[:-1] + ' exists! Tests use this ' +
             'dir to check caching then delete it afterwards, so the path ' +
             'should be left empty.')

    def tearDown(self):
        """Remove any caches created by the tests."""
        try:
            shutil.rmtree(TEST_CACHE_DIR[:-1])
        except FileNotFoundError:
            pass

    def test_standard_ns_gaussian_likelihood_uniform_prior(self):
        """Check the uniform prior."""
        settings = get_minimal_settings()
        settings.prior = priors.Uniform(prior_scale=10)
        self.assertAlmostEqual(
            settings.logx_given_logl(settings.logl_given_logx(-1.0)),
            -1.0, places=12)
        settings.logz_analytic()
        ns_run = ns.generate_ns_run(settings)
        values = ar.run_estimators(ns_run, ESTIMATOR_LIST)
        self.assertFalse(np.any(np.isnan(values)))

    def test_cached_gaussian_prior(self):
        """Check the cached_gaussian prior."""
        settings = get_minimal_settings()
        self.assertRaises(
            TypeError, priors.GaussianCached,
            prior_scale=10, unexpected=0)
        settings.prior = priors.GaussianCached(
            prior_scale=10, save_dict=True, n_dim=settings.n_dim,
            cache_dir=TEST_CACHE_DIR,
            interp_density=10, logx_min=-30)
        # Test inside and outside cached regime (logx<-10).
        # Need fairly low number of places
        for logx in [-1, -11]:
            self.assertAlmostEqual(
                settings.logx_given_logl(settings.logl_given_logx(logx)),
                logx, places=3)
        # Test array version of the function too
        logx = np.asarray([-2])
        self.assertAlmostEqual(
            settings.logx_given_logl(settings.logl_given_logx(logx)[0]),
            logx[0], places=12)
        settings.get_settings_dict()
        # Generate NS run using get_run_data to check it checks the cache
        # before submitting process to parallel apply
        ns_run = ns.get_run_data(settings, 1, load=False, save=False)[0]
        values = ar.run_estimators(ns_run, ESTIMATOR_LIST)
        self.assertFalse(np.any(np.isnan(values)))
        # check the argument options and messages for interp_r_logx_dict
        self.assertRaises(
            TypeError, perfectns.cached_gaussian_prior.interp_r_logx_dict,
            2000, 10, logx_min=-100, interp_density=1, unexpected=0)


class TestPlotting(unittest.TestCase):

    def test_plot_dynamic_nlive(self):
        settings = get_minimal_settings()
        fig = perfectns.plots.plot_dynamic_nlive(
            [None, 0, 1, 1], settings, n_run=2,
            tuned_dynamic_ps=[False, False, False, True],
            save=False, load=False)
        self.assertIsInstance(fig, matplotlib.figure.Figure)
        # Test ymax and the fallback for normalising analytic lines when the
        # dynamic goal which is meant to mirror them is not present
        fig = perfectns.plots.plot_dynamic_nlive(
            [None], settings, n_run=2,
            save=False, load=False,
            tuned_dynamic_ps=[True], ymax=1000)
        # Test unexpected kwargs check
        self.assertRaises(
            TypeError, perfectns.plots.plot_dynamic_nlive,
            [None, 0, 1, 1], settings, n_run=2,
            tuned_dynamic_ps=[False, False, False, True], unexpected=0)

    def test_plot_parameter_logx_diagram(self):
        settings = get_minimal_settings()
        for ftheta in [e.ParamMean(), e.ParamSquaredMean(), e.RMean()]:
            fig = perfectns.plots.plot_parameter_logx_diagram(
                settings, ftheta, x_points=50, y_points=50)
            self.assertIsInstance(fig, matplotlib.figure.Figure)
        # Test warning for estimators without CDF
        perfectns.plots.cdf_given_logx(e.LogZ(), np.zeros(1), np.zeros(1),
                                       settings)
        # Test unexpected kwargs check
        self.assertRaises(
            TypeError, perfectns.plots.plot_parameter_logx_diagram,
            settings, e.ParamMean(), x_points=50, y_points=50,
            unexpected=0)

    def test_plot_rel_posterior_mass(self):
        fig = perfectns.plots.plot_rel_posterior_mass(
            [perfectns.likelihoods.Gaussian(1),
             perfectns.likelihoods.ExpPower(1, 2)],
            perfectns.priors.Gaussian(1),
            [2], np.linspace(-10, 0, 100))
        self.assertIsInstance(fig, matplotlib.figure.Figure)
        self.assertRaises(
            TypeError, perfectns.plots.plot_rel_posterior_mass,
            [perfectns.likelihoods.Gaussian(1),
             perfectns.likelihoods.ExpPower(1, 2)],
            perfectns.priors.Gaussian(1),
            [2], np.linspace(-10, 0, 100), unexpected=0)


class TestResultsTables(unittest.TestCase):

    def setUp(self):
        """
        Set up list of estimator objects and settings for each test.
        Use all the estimators in the module in each case, and choose settings
        so the tests run quickly.
        """
        assert not os.path.exists(TEST_CACHE_DIR[:-1]), \
            ('Directory ' + TEST_CACHE_DIR[:-1] + ' exists! Tests use this ' +
             'dir to check caching then delete it afterwards, so the path ' +
             'should be left empty.')
        self.settings = get_minimal_settings()

    def tearDown(self):
        """Remove any caches created by the tests."""
        try:
            shutil.rmtree(TEST_CACHE_DIR[:-1])
        except FileNotFoundError:
            pass

    def test_dynamic_results_table(self):
        """
        Test generating a table comparing dynamic and standard nested sampling;
        this covers a lot of the perfectns module's functionality.

        As the numerical values produced are stochastic we just test that the
        function runs ok and does not produce NaN values - this should be
        sufficient.
        """
        # Need parallelise=False for coverage module to give correct answers
        dynamic_table = rt.get_dynamic_results(
            5, [0, 0.25, 1, 1], ESTIMATOR_LIST, self.settings, load=True,
            save=True, cache_dir=TEST_CACHE_DIR,
            parallelise=True, tuned_dynamic_ps=[False, False, False, True])
        # Uncomment below line to update values if they change for a known
        # reason
        # dynamic_table.to_pickle('tests/dynamic_table_test_values.pkl')
        # Check the values of every row for the theta1 estimator
        test_values = pd.read_pickle('tests/dynamic_table_test_values.pkl')
        numpy.testing.assert_allclose(dynamic_table.values, test_values.values,
                                      rtol=1e-13)
        # None of the other values in the table should be NaN:
        self.assertFalse(np.any(np.isnan(dynamic_table.values)))
        # Check the kwargs checking
        self.assertRaises(TypeError, rt.get_dynamic_results, 5, [0],
                          ESTIMATOR_LIST, self.settings, unexpected=1)

    def test_bootstrap_results_table(self):
        """
        Generate a table showing sampling error estimates using the bootstrap
        method.

        As the numerical values produced are stochastic we just test that the
        function runs ok and does not produce NaN values - this should be
        sufficient.
        """
        # Need parallelise=False for coverage module to give correct answers
        bootstrap_table = rt.get_bootstrap_results(5, 10,
                                                   ESTIMATOR_LIST,
                                                   self.settings,
                                                   n_run_ci=2,
                                                   n_simulate_ci=100,
                                                   add_sim_method=True,
                                                   cred_int=0.95,
                                                   load=True, save=True,
                                                   cache_dir=TEST_CACHE_DIR,
                                                   ninit_sep=True,
                                                   parallelise=True)
        # The first row of the table contains analytic calculations of the
        # estimators' values given the likelihood and prior which have already
        # been tested in test_dynamic_results_table.
        # None of the other values in the table should be NaN:
        self.assertFalse(np.any(np.isnan(bootstrap_table.values[1:, :])))
        # Check the kwargs checking
        self.assertRaises(TypeError, rt.get_bootstrap_results, 3, 10,
                          ESTIMATOR_LIST, self.settings, unexpected=1)


# Helper functions
# ----------------


def get_minimal_settings():
    """
    Get a perfectns settings object with a minimal number of live points so
    that tests run quickly.
    """
    settings = perfectns.settings.PerfectNSSettings()
    settings.dims_to_sample = 2
    settings.n_dim = 2
    settings.nlive_const = 5
    settings.ninit = 2
    settings.dynamic_goal = None
    return settings


if __name__ == '__main__':
    unittest.main()

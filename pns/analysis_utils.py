#!/usr/bin/python
"""Module for functions used to analyse the nested sampling run's outputs"""

import numpy as np
import scipy.misc  # for scipy.misc.logsumexp
# from numba import jit
import pns.maths_functions as mf


# Helper functions
# ----------------


def get_logx(nlive_array, simulate=False):
    """
    Returns a logx vector showing the expected or simulated logx positions of
    points.
    """
    assert isinstance(nlive_array, np.ndarray), \
        "nlive_array = " + str(nlive_array) + " must be a numpy array"
    assert nlive_array.min() > 0, \
        "nlive_array contains zeros! nlive_array = " + str(nlive_array)
    if simulate:
        logx_steps = np.log(np.random.random(nlive_array.shape)) / nlive_array
    else:
        logx_steps = -1 * (nlive_array ** -1)
    return np.cumsum(logx_steps)


def get_logw(logl, nlive_array, simulate=False):
    """
    tbc
    """
    logx_inc_start = np.zeros(logl.shape[0] + 1)
    # find X value for each point (start is at logX=0)
    logx_inc_start[1:] = get_logx(nlive_array, simulate=simulate)
    logw = np.zeros(logl.shape[0])
    # vectorized trapezium rule:
    logw[:-1] = mf.log_subtract(logx_inc_start[:-2], logx_inc_start[2:])
    logw -= np.log(2)  # divide by 2 as per trapezium rule formulae
    # assign all prior volume between X=0 and the first point to logw[0]
    logw[0] = scipy.misc.logsumexp([logw[0], np.log(0.5) +
                                    mf.log_subtract(logx_inc_start[0],
                                                    logx_inc_start[1])])
    logw[-1] = logw[-2]  # approximate final element as equal to the one before
    logw += logl
    return logw


def get_n_calls(ns_run):
    """
    Returns the number of likelihood calls in a nested sampling run.
    """
    n_calls = 0
    for thread in ns_run['threads']:
        if thread is not None:
            n_calls += thread.shape[0]
    return n_calls


def logl_mm_array(logl_mm_list):
    """
    tbc
    """
    arr = np.zeros((len(logl_mm_list), 3))
    arr[:, 2] = 1  # incriment nlive by 1 unless len(logl_mm) = 3
    for i, logl_mm in enumerate(logl_mm_list):
        arr[i, :len(logl_mm)] = np.asarray(logl_mm)
    return arr


def logl_mm_array_test(logl_mm_list):
    """
    tbc
    """
    arr = np.zeros(2)
    for logl_mm in logl_mm_list[1:]:
        arr = np.vstack((arr, np.reshape(np.asarray(logl_mm), (1, 2))))
    return arr


def get_nlive(run_dict, logl):
    """
    tbc
    """
    if 'nlive_array' in run_dict:
        nlive_array = run_dict['nlive_array']
    elif 'thread_logl_min_max' not in run_dict:  # standard run
        assert run_dict['settings']['dynamic_goal'] is None, \
            "dynamic ns run does not contain thread_logl_min_max!"
        nlive_array = np.zeros(logl.shape[0]) + run_dict['settings']['nlive']
        for i in range(1, run_dict['settings']['nlive']):
            nlive_array[-i] = i
    else:  # dynamic run
        nlive_array = np.zeros(logl.shape[0])
        lmm_ar = run_dict['thread_logl_min_max']
        # no min logl
        for r in lmm_ar[np.isnan(lmm_ar[:, 0])]:
            nlive_array[np.where(r[1] >= logl)] += r[2]
        # no max logl
        for r in lmm_ar[np.isnan(lmm_ar[:, 1])]:
            nlive_array[np.where(logl > r[0])] += r[2]
        # both min and max logl
        for r in lmm_ar[~np.isnan(lmm_ar[:, 0]) & ~np.isnan(lmm_ar[:, 1])]:
            nlive_array[np.where((r[1] >= logl) & (logl > r[0]))] += r[2]
        assert lmm_ar[np.isnan(lmm_ar[:, 0]) &
                      np.isnan(lmm_ar[:, 1])].shape[0] == 0, \
            'Should not have threads with neither start nor end logls'
    # If nlive_array contains zeros then print info and throw error
    assert nlive_array.min() > 0, \
        ("nlive_array contains zeros: " + str(nlive_array))
    return nlive_array


def merge_lrxp(array_list):
    """
    Merges a list of np arrays into a single array using vstack. Ommits list
    elements with value None (these are used to represent dynamic nested
    sampling threads with do not contain a single live point.
    """
    output = None
    for array in array_list:
        if array is not None:
            if output is not None:
                output = np.vstack((output, array))
            else:
                output = array
    if output is not None:
        output = output[np.argsort(output[:, 0])]
    return output


def get_estimators(lrxp, logw, estimator_list):
    """
    tbc
    """
    output = np.zeros(len(estimator_list))
    for i, f in enumerate(estimator_list):
        output[i] = f.estimator(logw=logw, logl=lrxp[:, 0], r=lrxp[:, 1],
                                theta=lrxp[:, 3:])
    return output


# Functions for output from a single nested sampling run
# ------------------------------------------------------
# These all have arguments (ns_run, estimator_list, **kwargs)


def run_estimators(ns_run, estimator_list, **kwargs):
    """
    Calculates values of list of estimators for a single nested sampling run.
    """
    simulate = kwargs.get('simulate', False)
    lrxp = merge_lrxp(ns_run['threads'])
    nlive = get_nlive(ns_run, lrxp[:, 0])
    logw = get_logw(lrxp[:, 0], nlive, simulate=simulate)
    return get_estimators(lrxp, logw, estimator_list)


# Std dev estimators


def run_std_simulate(ns_run, estimator_list, **kwargs):
    """
    Calculates simulated weight standard deviation estimates for a single
    nested sampling run.
    """
    # NB simulate must be True and analytical_w must be False so these are not
    # taken from kwargs
    n_simulate = kwargs["n_simulate"]  # No default, must specify
    return_values = kwargs.get('return_values', False)
    all_values = np.zeros((len(estimator_list), n_simulate))
    lrxp = merge_lrxp(ns_run['threads'])
    nlive = get_nlive(ns_run, lrxp[:, 0])
    for i in range(0, n_simulate):
        logw = get_logw(lrxp[:, 0], nlive, simulate=True)
        all_values[:, i] = get_estimators(lrxp, logw, estimator_list)
    stds = np.zeros(all_values.shape[0])
    for i, _ in enumerate(stds):
        stds[i] = np.std(all_values[i, :], ddof=1)
    if return_values:
        return stds, all_values
    else:
        return stds


def bootstrap_resample_run(ns_run, sample_ninit_sep=True):
    """
    Bootstrap resamples threads of nested sampling run, returning a new
    (resampled) nested sampling run.
    """
    threads_temp = []
    logl_min_max_temp = []
    n_threads = len(ns_run['threads'])
    if ns_run['settings']['dynamic_goal'] is not None and sample_ninit_sep:
        ninit = ns_run["settings"]["nlive_1"]
        inds = np.random.randint(0, ninit, ninit)
        inds = np.append(inds, np.random.randint(ninit, n_threads,
                                                 n_threads - ninit))
    else:
        inds = np.random.randint(0, n_threads, n_threads)
    threads_temp = [ns_run['threads'][i] for i in inds]
    logl_min_max_temp = ns_run["thread_logl_min_max"][inds]
    ns_run_temp = {"thread_logl_min_max": logl_min_max_temp,
                   "settings": ns_run['settings'],
                   "threads": threads_temp}
    return ns_run_temp


def run_std_bootstrap(ns_run, estimator_list, **kwargs):
    """
    Calculates bootstrap standard deviation estimates
    for a single nested sampling run.
    """
    n_simulate = kwargs["n_simulate"]  # No default, must specify
    bs_values = np.zeros((len(estimator_list), n_simulate))
    for i in range(0, n_simulate):
        ns_run_temp = bootstrap_resample_run(ns_run)
        bs_values[:, i] = run_estimators(ns_run_temp, estimator_list)
        del ns_run_temp
    stds = np.zeros(bs_values.shape[0])
    for j, _ in enumerate(stds):
        stds[j] = np.std(bs_values[j, :], ddof=1)
    return stds


def run_ci_bootstrap(ns_run, estimator_list, **kwargs):
    """
    Calculates bootstrap confidence interval estimates for a single nested
    sampling run.
    """
    n_simulate = kwargs["n_simulate"]  # No default, must specify
    cred_int = kwargs["cred_int"]   # No default, must specify
    assert min(cred_int, 1. - cred_int) * n_simulate > 1, \
        "n_simulate = " + str(n_simulate) + " is not big enough to " \
        "calculate the bootstrap " + str(cred_int) + " CI"
    bs_values = np.zeros((len(estimator_list), n_simulate))
    for i in range(0, n_simulate):
        ns_run_temp = bootstrap_resample_run(ns_run)
        bs_values[:, i] = run_estimators(ns_run_temp, estimator_list)
        del ns_run_temp
    # estimate specificed confidence intervals
    # formulae for alpha CI on estimator T = 2 T(x) - G^{-1}(T(x*))
    # where G is the CDF of the bootstrap resamples
    expected_estimators = run_estimators(ns_run, estimator_list)
    cdf = ((np.asarray(range(bs_values.shape[1])) + 0.5) /
           bs_values.shape[1])
    ci_output = expected_estimators * 2
    for i, _ in enumerate(ci_output):
        ci_output[i] -= np.interp(1. - cred_int, cdf,
                                  np.sort(bs_values[i, :]))
    return ci_output

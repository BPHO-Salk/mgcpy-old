import math
import warnings
from statistics import mean, stdev

import numpy as np
from scipy.stats import norm

from mgcpy.independence_tests.abstract_class import IndependenceTest
from mgcpy.independence_tests.utils.compute_distance_matrix import \
    compute_distance
from mgcpy.independence_tests.utils.fast_functions import (_approx_null_dist,
                                                           _fast_pvalue,
                                                           _sample_atrr,
                                                           _sub_sample)
from mgcpy.independence_tests.mgc import MGC

from joblib import Parallel, delayed

class MGCX(IndependenceTest):
    def __init__(self, compute_distance_matrix=None, max_lag = 0):
        '''
        :param compute_distance_matrix: a function to compute the pairwise distance matrix, given a data matrix
        :type compute_distance_matrix: ``FunctionType`` or ``callable()``

        :param base_global_correlation: specifies which global correlation to build up-on,
                                        including 'mgc','dcor','mantel', and 'rank'.
                                        Defaults to mgc.
        :type base_global_correlation: string

        :param max_lag: Furthest lag to check for dependence.
        :type max_lag: int
        '''

        IndependenceTest.__init__(self, compute_distance_matrix)
        self.max_lag = max_lag
        self.which_test = "mgcx"
        self.mgc = MGC()

    def test_statistic(self, matrix_X, matrix_Y, p = None):
        """
        Computes the MGCX measure between two time series datasets.

            - It first computes all the local correlations
            - Then, it returns the maximal statistic among all local correlations based on thresholding.

        :param matrix_X: is interpreted as either:

            - a ``[n*n]`` distance matrix, a square matrix with zeros on diagonal for ``n`` samples OR
            - a ``[n*p]`` data matrix, a matrix with ``n`` samples in ``p`` dimensions
        :type matrix_X: 2D numpy.array

        :param matrix_Y: is interpreted as either:

            - a ``[n*n]`` distance matrix, a square matrix with zeros on diagonal for ``n`` samples OR
            - a ``[n*q]`` data matrix, a matrix with ``n`` samples in ``q`` dimensions
        :type matrix_Y: 2D numpy.array

        :param p: bandwidth parameter for Bartlett Kernel.
        :type p: float

        :return: returns a list of two items, that contains:

            - :test_statistic: the sample mgc_ts statistic (not necessarily within [-1,1])
            - :test_statistic_metadata: a ``dict`` of metadata with the following keys:
                    - :dist_mtx_X: the distance matrix of sample X
                    - :dist_mtx_Y: the distance matrix of sample X
        :rtype: list

        **Example:**

        >>> import numpy as np
        >>> from mgcpy.independence_tests.mgc.mgc import MGC
        >>>
        >>> X = np.array([0.07487683, -0.18073412, 0.37266440, 0.06074847, 0.76899045,
        ...           0.51862516, -0.13480764, -0.54368083, -0.73812644, 0.54910974]).reshape(-1, 1)
        >>> Y = np.array([-1.31741173, -0.41634224, 2.24021815, 0.88317196, 2.00149312,
        ...           1.35857623, -0.06729464, 0.16168344, -0.61048226, 0.41711113]).reshape(-1, 1)
        >>> mgc_ts = MGC_TS()
        >>> mgc_ts_statistic, test_statistic_metadata = mgc.test_statistic(X, Y)
        """
        assert matrix_X.shape[0] == matrix_Y.shape[0], "Matrices X and Y need to be of dimensions [n, p] and [n, q], respectively, where p can be equal to q"

        n = matrix_X.shape[0]
        if len(matrix_X.shape) == 1:
            matrix_X = matrix_X.reshape((n,1))
        if len(matrix_Y.shape) == 1:
            matrix_Y = matrix_Y.reshape((n,1))
        matrix_X, matrix_Y = compute_distance(matrix_X, matrix_Y, self.compute_distance_matrix)

        M = self.max_lag if self.max_lag is not None else math.ceil(math.sqrt(n))
        mgc = self.mgc

        # Collect the test statistic by lag, and sum them for the full test statistic.
        dependence_by_lag = np.zeros(M+1)
        mgc_statistic, mgc_metadata = mgc.test_statistic(matrix_X, matrix_Y)
        dependence_by_lag[0] = np.maximum(0.0, mgc_statistic)
        max_dependence = dependence_by_lag[0]
        optimal_lag = 0
        optimal_scale = mgc_metadata['optimal_scale']

        for j in range(1,M+1):
            dist_mtx_X = matrix_X[j:n,j:n]
            dist_mtx_Y = matrix_Y[0:(n-j),0:(n-j)]
            mgc_statistic, mgc_metadata = mgc.test_statistic(dist_mtx_X, dist_mtx_Y)
            dependence_by_lag[j] = (n-j)*np.maximum(0.0, mgc_statistic) / n
            if dependence_by_lag[j] > max_dependence:
                max_dependence = dependence_by_lag[j]
                optimal_lag = j
                optimal_scale = mgc_metadata['optimal_scale']


        # Reporting optimal lag
        self.test_statistic_metadata_ = { 'optimal_lag' : optimal_lag,
                                    'optimal_scale' : optimal_scale,
                                    'dependence_by_lag' : dependence_by_lag }
        self.test_statistic_ = np.sum(dependence_by_lag)
        return self.test_statistic_, self.test_statistic_metadata_

    def p_value(self, matrix_X, matrix_Y, replication_factor = 1000, is_fast = False):
        """
        Tests independence between two datasets using block permutation test.

        :param matrix_X: is interpreted as either:

            - a ``[n*n]`` distance matrix, a square matrix with zeros on diagonal for ``n`` samples OR
            - a ``[n*p]`` data matrix, a matrix with ``n`` samples in ``p`` dimensions
        :type matrix_X: 2D numpy.array

        :param matrix_Y: is interpreted as either:

            - a ``[n*n]`` distance matrix, a square matrix with zeros on diagonal for ``n`` samples OR
            - a ``[n*q]`` data matrix, a matrix with ``n`` samples in ``q`` dimensions
        :type matrix_Y: 2D numpy.array

        :param replication_factor: specifies the number of replications to use for
                                   the permutation test. Defaults to ``1000``.
        :type replication_factor: integer

        :return: returns a list of two items, that contains:

            - :p_value: P-value of MGC
            - :metadata: a ``dict`` of metadata with the following keys:
                    - :null_distribution: numpy array representing distribution of test statistic under null.
        :rtype: list

        **Example:**

        >>> import numpy as np
        >>> from mgcpy.independence_tests.mgc.mgc_ts import MGC_TS
        >>>
        >>> X = np.array([0.07487683, -0.18073412, 0.37266440, 0.06074847, 0.76899045,
        ...           0.51862516, -0.13480764, -0.54368083, -0.73812644, 0.54910974]).reshape(-1, 1)
        >>> Y = np.array([-1.31741173, -0.41634224, 2.24021815, 0.88317196, 2.00149312,
        ...           1.35857623, -0.06729464, 0.16168344, -0.61048226, 0.41711113]).reshape(-1, 1)
        >>> mgc_ts = MGC_TS()
        >>> p_value, metadata = mgc_ts.p_value(X, Y, replication_factor = 100)
        """
        assert matrix_X.shape[0] == matrix_Y.shape[0], "Matrices X and Y need to be of dimensions [n, p] and [n, q], respectively, where p can be equal to q"

        # Compute test statistic
        n = matrix_X.shape[0]
        if len(matrix_X.shape) == 1:
            matrix_X = matrix_X.reshape((n, 1))
        if len(matrix_Y.shape) == 1:
            matrix_Y = matrix_Y.reshape((n, 1))
        matrix_X, matrix_Y = compute_distance(matrix_X, matrix_Y, self.compute_distance_matrix)
        test_statistic, test_statistic_metadata = self.test_statistic(matrix_X, matrix_Y)

        block_size = int(np.ceil(np.sqrt(n)))
        if is_fast:
            return self._fast_p_value(matrix_X, matrix_Y, test_statistic, block_size)

        # Parallelized block bootstrap.
        def worker(rep):
            permuted_indices = np.r_[[np.arange(t, t + block_size) for t in np.random.choice(n, n // block_size + 1)]].flatten()[:n]
            permuted_indices = np.mod(permuted_indices, n)
            permuted_Y = matrix_Y[np.ix_(permuted_indices, permuted_indices)]

            # Compute test statistic
            ret, _ = self.test_statistic(matrix_X, permuted_Y)
            return ret

        test_stats_null = Parallel(n_jobs=-2)(delayed(worker)(rep) for rep in range(replication_factor))

        # Block bootstrap
        # test_stats_null = np.zeros(replication_factor)
        # for rep in range(replication_factor):
        #     # Generate new time series sample for Y
        #     permuted_indices = np.r_[[np.arange(t, t + block_size) for t in np.random.choice(n, n // block_size + 1)]].flatten()[:n]
        #     permuted_indices = np.mod(permuted_indices, n)
        #     permuted_Y = matrix_Y[np.ix_(permuted_indices, permuted_indices)]
        #
        #     # Compute test statistic
        #     test_stats_null[rep], _ = self.test_statistic(matrix_X, permuted_Y)

        self.p_value_ = np.sum(np.greater(test_stats_null, test_statistic)) / replication_factor
        if self.p_value_ == 0.0:
            self.p_value_ = 1 / replication_factor
        self.p_value_metadata_ = {'null_distribution': test_stats_null}

        return self.p_value_, self.p_value_metadata_

    def _fast_p_value(self, matrix_X, matrix_Y, test_statistic, block_size, subsample_size = 10):
        n = matrix_X.shape[0]
        num_samples = n // subsample_size

        # Permute once.
        permuted_indices = np.r_[[np.arange(t, t + block_size) for t in np.random.choice(n, n // block_size + 1)]].flatten()[:n]
        permuted_indices = np.mod(permuted_indices, n)
        permuted_Y = matrix_Y[np.ix_(permuted_indices, permuted_indices)]

        test_stats_null = np.zeros(num_samples * subsample_size)
        for i in range(num_samples):
            indices = np.arange(subsample_size*i, subsample_size*(i + 1))
            sub_matrix_X = matrix_X[np.ix_(indices, indices)]
            sub_matrix_Y = permuted_Y[np.ix_(indices, indices)]
            test_stats_null[i], _ = self.test_statistic(sub_matrix_X, sub_matrix_Y)

        # Normal approximation for the p_value.
        mu = np.mean(test_stats_null)
        sigma = np.std(test_stats_null) / np.sqrt(num_samples)
        self.p_value_ = 1 - norm.cdf(test_statistic, mu, sigma)
        self.p_value_metadata_ = {'null_distribution': test_stats_null}

        return self.p_value_, self.p_value_metadata_

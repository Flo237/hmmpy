from typing import Callable, Any
from functools import reduce, partial

import numpy as np
from numpy import ma

from numba import njit

from scipy.stats import multivariate_normal

from math import exp, sqrt, pi

from itertools import product


class InitialProbability:
    """Class for representing and evaluating initial probabilties.
    
    Parameters:
    ---
    initial_probability -- A function, taking a single argument, with the argument being
    an actual element of the state space, that returns the probability of starting of the supplied state.
    states -- A list of all states in the state space.
    """
    def __init__(self, initial_probability: Callable[[Any], float], states: list):
        self.states: list = states
        self.n: int = len(states)
        self.pi: Callable[[Any], float] = initial_probability

    def eval(self, x: np.ndarray):
        """Get corresponding initial probability for states identified by state IDs in x. 
        State IDs is the index of the states in the list passed in the constructor. 
        """
        return np.array(list(map(lambda x: self.pi(self.states[x]), x)))


class TransitionProbability:
    """Class for representing and evaluating transition probabilties.
    
    Parameters:
    ---
    transition_probability  -- A function, taking two arguments, with both arguments being
    actual elements of the state space, that returns the probability of moving from the first argument
    to the second argument.
    states -- A list of all states in the state space.
    """
    def __init__(
        self, transition_probability: Callable[[Any, Any], float], states: list
    ):
        self.states: list = states
        self.n: int = len(states)
        self.p: Callable[[Any, Any], float] = transition_probability

    def eval(self, x: np.ndarray, y: np.ndarray):
        """Returns an array of transition probabilities, with the ith element being 
        the probability of transitioning from the ith element of the first argument to
        the ith element of the second argument. The elements should be state IDs, not states. 
        """
        return np.array(
            list(map(lambda x: self.p(self.states[x[0]], self.states[x[1]]), zip(x, y)))
        )


class EmissionProbability:
    """Class for representing and evaluating emission probabilties.
    
    Parameters:
    ---
    emission_probability -- A function, that takes an observation as its first argument and a state as its
    second argument and returns the probability of observing the observation given that we are in the supplied state.
    states -- A list of all the states in the state space.
    """

    def __init__(self, emission_probability: Callable[[Any, Any], float], states: list):
        self.n: int = len(states)
        self.states: list = states
        self.l: Callable[[Any, Any], float] = emission_probability

    def eval(self, z: list, x: np.ndarray):
        """Returns an array of emission probabilities, with the ith element being 
        the probability of observing the ith element of the first argument when in
        the state identified by the state ID in the ith element of the second argument.
        """
        return np.array([self.l(obs, self.states[state]) for obs, state in zip(z, x)])


class HiddenMarkovModel:
    """Class that implements functionality related to Hidden Markov Models.
    Supply functions as expected by the classes InitialProbability, EmissionProbability 
    and TransitionProbability.

    Parameters:
    ---
    transition_probability -- As in TransitionProbability
    emission_probability -- As in EmissionProbability
    initial_probability -- As in InitialProbability
    states -- A list of all the states in the state space.
    """
    def __init__(
        self,
        transition_probability: Callable[[Any, Any], float],
        emission_probability: Callable[[Any, int], float],
        initial_probability: Callable[[int], float],
        states: list,
    ):
        self.states: list = states
        self.M: int = len(states)
        self.state_ids: np.ndarray = np.arange(self.M).astype(int)
        self.transition_probability: TransitionProbability = TransitionProbability(
            transition_probability, self.states
        )
        self.emission_probability: EmissionProbability = EmissionProbability(
            emission_probability, self.states
        )
        self.initial_probability: InitialProbability = InitialProbability(
            initial_probability, self.states
        )

        states_repeated: np.ndarray = np.repeat(self.state_ids, self.M)
        states_tiled: np.ndarray = np.tile(self.state_ids, self.M)

        self.P: np.ndarray = self.transition_probability.eval(
            states_repeated, states_tiled
        ).reshape(self.M, self.M)

        #Ensuring that all rows in P sum to 1.
        sumP: np.ndarray = np.sum(self.P, axis=1)
        self.P = (self.P.T * 1 / sumP).T
    
    def evaluate_initial_probabilities(self):
        pi = self.initial_probability.eval(self.state_ids)
        return pi

    def evaluate_emission_probabilities(self, z: list):
        N: int = len(z)
        l = np.zeros((N, self.M))
        for n in range(N):
            l[n, :] = self.emission_probability.eval([z[n]] * self.M, self.state_ids)
        return l

    def viterbi(self, z: list):
        P = self.P
        pi = self.evaluate_initial_probabilities()
        l = self.evaluate_emission_probabilities(z)
        return self.log_viterbi_internals(z, P, pi, l)

    @staticmethod
    def viterbi_internals(z: list, P: np.ndarray, pi: np.ndarray, l: np.ndarray):
        N: int = len(z)
        assert pi.shape[0] == l.shape[1]
        M = pi.shape[0]

        delta: np.ndarray = np.zeros((N, M))
        phi: np.ndarray = np.zeros((N, M))

        delta[0, :] = pi * l[0, :]
        phi[0, :] = 0

        for n in np.arange(1, N):
            # Multiply delta by each column in P
            # In resulting matrix, for each column, find max entry
            delta[n, :] = l[n, :] * np.max((delta[n - 1, :] * P.T).T, axis=0)
            phi[n, :] = np.argmax((delta[n - 1, :] * P.T).T, axis=0)

        x_star: np.ndarray = np.zeros((N,))
        x_star[N - 1] = np.argmax(delta[N - 1, :])

        for n in np.arange(N - 2, -1, -1):
            x_star[n] = phi[n + 1, x_star[n + 1].astype(int)]

        return x_star.astype(int)

    @staticmethod
    def log_viterbi_internals(z: list, P: np.ndarray, pi: np.ndarray, l: np.ndarray):
        N: int = len(z)
        assert pi.shape[0] == l.shape[1]
        M = pi.shape[0]

        delta: np.ndarray = np.zeros((N, M))
        phi: np.ndarray = np.zeros((N, M))
        log_P = ma.log(P).filled(-np.inf)

        delta[0, :] = ma.log(pi).filled(
            -np.inf
        ) + ma.log(
            l[0, :]
        ).filled(
            -np.inf
        )
        phi[0, :] = 0

        for n in np.arange(1, N):
            # Multiply delta by each column in P
            # In resulting matrix, for each column, find max entry
            log_l: np.ndarray = ma.log(
                l[n, :]
            ).filled(-np.inf)
            delta[n, :] = log_l + np.max(
                (np.expand_dims(delta[n - 1, :], axis=1) + log_P), axis=0
            )
            phi[n, :] = np.argmax(
                (np.expand_dims(delta[n - 1, :], axis=1) + log_P), axis=0
            )

        q_star = np.zeros((N,))
        q_star[N - 1] = np.argmax(delta[N - 1, :])

        for n in np.arange(N - 2, -1, -1):
            q_star[n] = phi[n + 1, q_star[n + 1].astype(int)]

        return q_star.astype(int)

    def decode(self, z: list):
        state_ids = self.viterbi(z)
        return list(map(lambda x: self.states[x], state_ids))

    
    def forward_algorithm(self, z: list):
        P = self.P
        pi = self.evaluate_initial_probabilities()
        l = self.evaluate_emission_probabilities(z)
        self.c, self.alpha = self.forward_algorithm_internals(z, P, l, pi)

    @staticmethod
    def forward_algorithm_internals(z: list, P: np.ndarray, l: np.ndarray, pi: np.ndarray):
        N: int = len(z)
        assert pi.shape[0] == l.shape[1]
        M = pi.shape[0]

        alpha = np.zeros((N, M))
        c = np.zeros((N,))

        alpha[0, :] = l[0, :] * pi
        c[0] = np.reciprocal(np.sum(alpha[0, :]))
        alpha[0, :] = alpha[0, :] * c[0]

        for n in np.arange(N - 1):
            alpha[n + 1, :] = np.sum(alpha[n, :][:, np.newaxis] * P, axis=0) * (
                l[n + 1, :]
            )
            c[n + 1] = np.reciprocal(np.sum(alpha[n + 1, :]))
            alpha[n + 1, :] = alpha[n + 1, :] * c[n + 1]

        return c, alpha

    
    def backward_algorithm(self, z: list):
        assert hasattr(self, "c"), "Run forward algorithm first!"
        P = self.P
        c = self.c
        pi = self.evaluate_initial_probabilities()
        l = self.evaluate_emission_probabilities(z)
        self.beta = self.backward_algorithm_internals(z, P, l, pi, c)

    @staticmethod
    def backward_algorithm_internals(z: list, P: np.ndarray, l: np.ndarray, pi: np.ndarray, c: np.ndarray):
        N = len(z)
        assert pi.shape[0] == l.shape[1]
        M = pi.shape[0]

        beta = np.zeros((N, M))
        beta[N - 1, :] = 1

        for n in np.arange(N - 2, -1, -1):
            b = l[n + 1, :]

            beta[n, :] = np.sum(P * b * beta[n + 1, :], axis=1) * c[n]

        return beta

    def forward_backward_algorithm(self, z: list):
        self.forward_algorithm(z)
        self.backward_algorithm(z)

        l = self.evaluate_emission_probabilities(z)
        P = self.P

        alpha = self.alpha
        beta = self.beta

        self.gamma = self.calculate_gamma(alpha, beta)
        self.ksi = self.calculate_ksi(z, P, l, alpha, beta)

    @staticmethod
    def calculate_ksi(z: list, P: np.ndarray, l: np.ndarray, alpha: np.ndarray, beta: np.ndarray):
        N = len(z)
        assert l.shape[0] == alpha.shape[0] == beta.shape[0] == N
        assert l.shape[1] == alpha.shape[1] == beta.shape[1]
        M = alpha.shape[1]

        ksi = np.zeros((N - 1, M, M))
        for n in range(N - 1):
            b = l[n + 1, :]
            ksi[n, :, :] = (P * b * beta[n + 1, :]) * alpha[n, :][
                :, np.newaxis
            ]
            ksi[n, :, :] = ksi[n, :, :] / np.sum(ksi[n, :, :])

        return ksi

    @staticmethod
    def calculate_gamma(alpha: np.ndarray, beta: np.ndarray):
        alpha_beta_product = alpha * beta
        sum_over_all_states = np.sum(alpha_beta_product, axis=1)
        gamma = alpha_beta_product / sum_over_all_states[:, np.newaxis]
        return gamma

    def observation_log_probability(self, z: list):
        self.forward_algorithm(z)
        return -np.sum(self.c)


class DiscreteEmissionProbability:
    """Class for representing probabilities for discrete observations.
    The initial argument should be a function that takes two arguments and returns the probability of
    the symbol given in the first argument when in the state given by the second argument.

    A symbol refers to a single element from the space of a finite number of possible obserservations.

    Parameters:
    ---
    emission_probability -- A function that returns the probability of symbol given state.
    states -- A list of all states in state space.
    symbols -- A list of all symbols that can be observed. 
    """
    def __init__(self, emission_probability, states, symbols):
        self.symbol_id_dictionary = {k: v for k, v in zip(symbols, range(len(symbols)))}
        self.K = len(symbols)
        self.M = len(states)
        self.l = emission_probability
        self._b = np.array(
            list(map(lambda x: self.l(x[0], x[1]), product(symbols, states)))
        ).reshape(self.K, self.M)
        self._b = self._b / np.sum(self.b, axis=0)

    @property
    def b(self):
        return self._b
    
    @b.setter
    def b(self, value):
        self._b = value

    def eval(self, z: list, x: np.ndarray):
        """Return an array where the ith element is the probability of observing the symbol in
        the ith positon of the first argument when in state identified by the state ID in the ith
        positon of the second argument."""
        return np.array([self.b[self.symbol_id_dictionary[a], b] for a, b in zip(z, x)])


class DiscreteHiddenMarkovModel(HiddenMarkovModel):
    """A class that inherits HiddenMarkovModel and has functionality specific for Hidden Markov Models
    with a finite, discrete observation space. See documentation for HiddenMarkovModel. Notable
    changes/additions is how emission_probability should be a function as expected by DiscreteEmissionProbability,
    how the constructor needs a list of all symbols, and the inclusion of methods specific to reestimation for
    discrete Hidden Markov Models.
    """
    def __init__(
        self,
        transition_probability: Callable[[Any, Any], float],
        emission_probability: Callable[[Any, int], float],
        initial_probability: Callable[[int], float],
        states: list,
        symbols: list,
    ):
        self.states = states
        self.symbols = symbols
        self.M: int = len(states)
        self.state_ids: np.ndarray = np.arange(self.M).astype(int)
        self.transition_probability: TransitionProbability = TransitionProbability(
            transition_probability, self.states
        )
        self.emission_probability: DiscreteEmissionProbability = DiscreteEmissionProbability(
            emission_probability, self.states, self.symbols
        )
        self.initial_probability: InitialProbability = InitialProbability(
            initial_probability, self.states
        )

        states_repeated: np.ndarray = np.repeat(self.state_ids, self.M)
        states_tiled: np.ndarray = np.tile(self.state_ids, self.M)

        self.P: np.ndarray = self.transition_probability.eval(
            states_repeated, states_tiled
        ).reshape(self.M, self.M)

        sumP: np.ndarray = np.sum(self.P, axis=1)
        self.P = (self.P.T * 1 / sumP).T

    def baum_welch(self, zs):
        P_uppers = []
        P_lowers = []
        l_uppers = []
        l_lowers = []
        pis = []

        log_probs = np.array(list(map(lambda z: self.observation_log_probability(z), zs)))
        max_log_prob = np.max(log_probs)
        revised_scalings = np.exp(max_log_prob - log_probs)

        E = len(zs)
        for i, z in enumerate(zs):
            self.forward_backward_algorithm(z)

            P_upper, P_lower = self.calculate_inner_transition_probability_sums(self.ksi, self.gamma)
            P_uppers.append(P_upper*revised_scalings[i])
            P_lowers.append(P_lower*revised_scalings[i])

            l_upper, l_lower = self.calculate_inner_emission_probability_sums(z, self.gamma, self.symbols)
            l_uppers.append(l_upper)
            l_lowers.append(l_lower)

            pi = self.gamma[0, :]
            pis.append(pi)
        
        self.P = sum(P_uppers) / sum(P_lowers)[:, np.newaxis]
        self.b = sum(l_uppers) / sum(l_lowers)[:, np.newaxis]
        self.pi = sum(pis) / E

        self.emission_probability.b = self.b


    @staticmethod
    def calculate_inner_transition_probability_sums(ksi, gamma):
        upper_sum = np.sum(ksi, axis=0)
        lower_sum = np.sum(gamma, axis=0)
        return upper_sum, lower_sum

    @staticmethod
    def calculate_inner_emission_probability_sums(z, gamma, symbols):
        M = gamma.shape[1]
        K = len(symbols)
        upper_sum = np.ones((K, M))
        for k, o in enumerate(symbols):
            #Indices where observation equals symbol k
            ts = np.where(np.array(z) == o)
            #All zeros
            partial_gamma = np.zeros(gamma.shape)
            #Assign non-zero values to rows (times) where observation equals symbol k
            partial_gamma[ts, :] = gamma[ts, :]
            #Sum over all time-steps
            upper_sum[k, :] = np.sum(partial_gamma, axis=0)
        lower_sum = np.sum(gamma, axis=0)

        return upper_sum, lower_sum


class GaussianEmissionProbability:
    """Class for representing state-dependent Gaussian emission probabilties."""

    def __init__(self, mus: list, sigmas: list):
        self.mus = mus
        self.sigmas = sigmas

        def emission_probability(z, x):
            return multivariate_normal.pdf(z, mean=self.mus[x, :], cov=self.sigmas[x, :, :])

        self.l = emission_probability

    def eval(self, z: np.ndarray, x: np.ndarray):
        # Can do apply along axis.
        return np.array([self.l(z, x) for z, x in zip(z, x)])


class GaussianHiddenMarkovModel(HiddenMarkovModel):
    def __init__(
        self,
        transition_probability: Callable[[Any, Any], float],
        initial_probability: Callable[[int], float],
        states: list,
        mus: list,
        sigmas: list,
    ):
        self.states = states
        self.M: int = len(states)
        self.state_ids: np.ndarray = np.arange(self.M).astype(int)
        self.transition_probability: TransitionProbability = TransitionProbability(
            transition_probability, self.states
        )
        self.emission_probability: GaussianEmissionProbability = GaussianEmissionProbability(
            mus, sigmas
        )
        self.initial_probability: InitialProbability = InitialProbability(
            initial_probability, self.states
        )
        self.alpha = None
        self.beta = None
        self.ksi = None
        self.gamma = None

        states_repeated: np.ndarray = np.repeat(self.state_ids, self.M)
        states_tiled: np.ndarray = np.tile(self.state_ids, self.M)

        self.P: np.ndarray = self.transition_probability.eval(
            states_repeated, states_tiled
        ).reshape(self.M, self.M)

        sumP: np.ndarray = np.sum(self.P, axis=1)
        self.P = (self.P.T * 1 / sumP).T

    def learn(self, gamma, ksi):
        a_u = np.sum(ksi, axis=0)
        a_l = np.sum(gamma, axis=0)

        sigma_l = np.sum(gamma, axis=0)

        pi = self.gamma[0, :]

        return a_u, a_l, sigma_l, pi

    def learn_mus(self, z):
        z_arr = np.array(z)
        mus_u = np.sum(self.gamma * z_arr[:, np.newaxis], axis=0)
        mus_l = np.sum(self.gamma, axis=0)

        return mus_u, mus_l

    def learn_from_sequence(self, zs):
        E = len(zs)

        mus_us = []
        mus_ls = []
        gammas = []
        ksis = []

        for z in zs:
            self.forward_algorithm(z)
            self.backward_algorithm(z)
            self.calculate_gamma()
            self.calculate_ksi(z)

            gammas.append(self.gamma)
            ksis.append(self.ksi)

            mus_u, mus_l = self.learn_mus(z)
            mus_us.append(mus_u)
            mus_ls.append(mus_l)

        self.mus = (sum(mus_us) / sum(mus_ls)).reshape(self.M, -1)

        a_us = []
        a_ls = []
        sigma_us = []
        sigma_ls = []
        pis = []
        for z, gamma, ksi in zip(zs, gammas, ksis):
            z_arr = np.array(z).reshape(gamma.shape[0], -1)
            a_u, a_l, sigma_l, pi = self.learn(gamma, ksi)
            sigma_u = self.compute_sigma_u(z_arr, self.mus, gamma)
            a_us.append(a_u)
            a_ls.append(a_l)
            sigma_us.append(sigma_u)
            sigma_ls.append(sigma_l)
            pis.append(pi)

        self.P = sum(a_us) / sum(a_ls)[:, np.newaxis]
        self.sigmas = sum(sigma_us) / sum(sigma_ls)[:, np.newaxis, np.newaxis]
        self.pi = sum(pis) / E
        self.emission_probability = GaussianEmissionProbability(self.mus, self.sigmas)

    def compute_sigma_u(self, z, mus, gamma):
        T = z.shape[0]
        D = z.shape[1]
        M = gamma.shape[1]
        sigmas = []
        for m in range(M):
            comps = []
            for t in range(T):
                arr = (z[t, :] - mus[m, :]).reshape(D, 1)
                comps.append(gamma[t, m] * np.matmul(arr, arr.T))
            comps = np.array(comps)
            assert comps.shape == (T, D, D)
            sum_over_t = np.sum(comps, axis=0)
            assert sum_over_t.shape == (D, D)
            sigmas.append(sum_over_t)

        return np.array(sigmas)

    def reestimate(self, zs: list, iterations=10):
        for _ in range(iterations):
            self.learn_from_sequence(zs)

from typing import Callable, Any
from functools import reduce, partial

import numpy as np


class HiddenMarkovModel:
    """Class that implements functionality related to Hidden Markov Models."""

    def __init__(
        self,
        transition_probability: Callable[[Any, Any], float],
        emission_probability: Callable[[Any, int], float],
        initial_probability: Callable[[int], float],
        states: list,
    ):
        self.states = states
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

    def viterbi(self, z: list):
        N: int = len(z)
        delta: np.ndarray = np.zeros((N, self.M))
        phi: np.ndarray = np.zeros((N, self.M))

        delta[0, :] = self.initial_probability.eval(self.state_ids) * (
            self.emission_probability.eval([z[0]] * self.M, self.state_ids)
        )
        C = np.sum(delta[0, :])
        delta[0, :] = delta[0, :] / C

        phi[0, :] = 0

        for n in np.arange(1, N):
            # Multiply delta by each column in P
            # In resulting matrix, for each column, find max entry
            l: np.ndarray = self.emission_probability.eval(
                [z[n]] * self.M, self.state_ids
            )
            delta[n, :] = l * np.max((delta[n - 1, :] * self.P.T).T, axis=0)
            C = np.sum(delta[n, :])
            delta[n, :] = delta[n, :] / C

            phi[n, :] = np.argmax((delta[n - 1, :] * self.P.T).T, axis=0)

        x_star: np.ndarray = np.zeros((N,))
        x_star[N - 1] = np.argmax(delta[N - 1, :])

        for n in np.arange(N - 2, -1, -1):
            x_star[n] = phi[n + 1, x_star[n + 1].astype(int)]

        return x_star.astype(int)

    def decode(self, z: list):
        state_ids = self.viterbi(z)
        return list(map(lambda x: self.states[x], state_ids))

    def forward_algorithm(self, z: list):
        N: int = len(z)

        alpha = np.zeros((N, self.M))

        alpha[0, :] = self.emission_probability.eval(
            [z[0]] * self.M, self.state_ids
        ) * self.initial_probability.eval(self.state_ids)

        for n in np.arange(N - 1):
            alpha[n + 1, :] = np.sum((alpha[n, :] * self.P.T).T, axis=0) * (
                self.emission_probability.eval([z[n + 1]] * self.M, self.state_ids)
            )

        self.alpha = alpha

    def backward_algorithm(self, z: list):
        N = len(z)
        beta = np.zeros((N, self.M))
        beta[N - 1, :] = 1

        for n in np.arange(N - 2, -1, -1):
            b = self.emission_probability.eval(
                np.array([z[n + 1]] * self.M), np.arange(self.M)
            )
            kernel = self.P * b

            beta[n, :] = np.sum(kernel * beta[n + 1, :], axis=1)

        self.beta = beta

    def calculate_ksi(self, z: list):
        N = len(z)

        ksi = np.zeros((N - 1, self.M, self.M))
        for n in range(N - 1):
            b = self.emission_probability.eval(
                     np.array([z[n + 1]] * self.M), self.state_ids
                     )
            ksi[n, :, :] = ((((self.P*b*self.beta[n + 1, :]).T*self.gamma[n, :]).T).T / self.beta[n, :]).T
            
            #Alternative implementation. Does not require that gamma is calculated before.
            #ksi[n, :, :] = (self.P * b * self.beta[n + 1, :]).T*self.alpha[n, :]
            #ksi[n, :, :] = ksi[n, :, :]/np.sum(ksi[n, :, :])

        self.ksi = ksi

    def calculate_gamma(self):
        alpha_beta_product = self.alpha * self.beta
        sum_over_all_states = np.sum(alpha_beta_product, axis=1)
        self.gamma = alpha_beta_product / sum_over_all_states


class TransitionProbability:
    """Class for representing and evaluating transition probabilties."""

    def __init__(
        self, transition_probability: Callable[[Any, Any], float], states: list
    ):
        self.states = states
        self.n = len(states)
        self.p: Callable[[Any, Any], float] = transition_probability
        self.max_index: int = self.n - 1

    def eval(self, x: np.ndarray, y: np.ndarray):
        assert np.max(x) <= self.max_index and np.max(y) <= self.max_index
        return np.array(list(map(lambda x: self.p(self.states[x[0]], self.states[x[1]]), zip(x, y))))


class EmissionProbability:
    """Class for representing and evaluating emission probabilties."""

    def __init__(self, emission_probability: Callable[[Any, Any], float], states: list):
        self.n = len(states)
        self.states = states
        self.l: Callable[[Any, Any], float] = emission_probability
        self.max_index: int = self.n - 1

    def eval(self, z: list, x: np.ndarray):
        assert np.max(x) <= self.max_index
        return np.array([self.l(obs, self.states[state]) for obs, state in zip(z, x)])


class InitialProbability:
    """Class for representing and evaluating initial probabilties."""

    def __init__(self, initial_probability: Callable[[Any], float], states: list):
        self.states = states
        self.n = len(states)
        self.pi: Callable[[Any], float] = initial_probability
        self.max_index: int = self.n - 1

    def eval(self, x: np.ndarray):
        assert np.max(x) <= self.max_index
        return np.array(list(map(lambda x: self.pi(self.states[x]), x)))
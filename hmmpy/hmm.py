from typing import Callable, Any

import numpy as np
from numba import jit


class HiddenMarkovModel:
    """Class that implements functionality related to Hidden Markov Models."""

    def __init__(
        self,
        transition_probability: Callable[[int, int], float],
        emission_probability: Callable[[Any, int], float],
        initial_probability: Callable[[int], float],
        number_of_states: int,
    ):
        self.M: int = number_of_states
        self.states: np.ndarray = np.arange(self.M).astype(int)
        self.transition_probability: TransitionProbability = TransitionProbability(
            transition_probability, self.M
        )
        self.emission_probability: EmissionProbability = EmissionProbability(
            emission_probability, self.M
        )
        self.initial_probability: InitialProbability = InitialProbability(
            initial_probability, self.M
        )

        states_repeated: np.ndarray = np.repeat(self.states, self.M)
        states_tiled: np.ndarray = np.tile(self.states, self.M)

        self.P: np.ndarray = self.transition_probability.eval(
            states_repeated, states_tiled
        ).reshape(self.M, self.M)

        sumP: np.ndarray = np.sum(self.P, axis=1)
        self.P = (self.P.T*1/sumP).T
        


    def viterbi(self, z: list):
        N: int = len(z)
        delta: np.ndarray = np.zeros((N, self.M))
        phi: np.ndarray = np.zeros((N, self.M))

        delta[0, :] = self.initial_probability.eval(self.states) * (
            self.emission_probability.eval([z[0]]*self.M, self.states)
        )

        phi[0, :] = 0

        for n in np.arange(1, N):
            # Multiply delta by each column in P
            # In resulting matrix, for each column, find max entry
            l: np.ndarray = self.emission_probability.eval([z[n]]*self.M, self.states)
            delta[n, :] = l * np.max((delta[n - 1, :] * self.P.T).T, axis=0)
            phi[n, :] = np.argmax((delta[n - 1, :] * self.P.T).T, axis=0)

        x_star: np.ndarray = np.zeros((N,))
        x_star[N-1] = np.argmax(delta[N-1, :])

        for n in np.arange(N - 2, -1, -1):
            x_star[n] = phi[n + 1, x_star[n + 1].astype(int)]

        return x_star

    def forward_algorithm(self, z: list):
        N: int = len(z)
        
        alpha = np.zeros((N, self.M))

        alpha[0, :] = (
            self.emission_probability.eval([z[0]]*self.M, self.states)
            * self.initial_probability.eval(self.states)
        )

        for n in np.arange(N-1):
            alpha[n + 1, :] = np.sum((alpha[n, :]*self.P.T).T, axis=0) * (
                self.emission_probability.eval([z[n+1]]*self.M, self.states)
            )
        
        return np.sum(alpha[N-1, :])

         


class TransitionProbability:
    """Class for representing and evaluating transition probabilties."""

    def __init__(self, transition_probability: Callable[[int, int], float], n: int):
        self.p: Callable[[int, int], float] = transition_probability
        self.max_index: int = n - 1

    def eval(self, x: np.ndarray, y: np.ndarray):
        assert np.max(x) <= self.max_index and np.max(y) <= self.max_index
        return eval_across_arrays(self.p, x, y)


class EmissionProbability:
    """Class for representing and evaluating emission probabilties."""

    def __init__(self, emission_probability: Callable[[Any, int], float], n: int):
        self.l: Callable[[Any, int], float] = emission_probability
        self.max_index: int = n - 1

    def eval(self, z: list, x: np.ndarray):
        assert np.max(x) <= self.max_index
        return np.array(
            [self.l(obs, state) for obs, state in zip(z, x)]
        )


class InitialProbability:
    """Class for representing and evaluating initial probabilties."""

    def __init__(self, initial_probability: Callable[[int], float], n: int):
        self.pi: Callable[[int], float] = initial_probability
        self.max_index: int = n - 1

    def eval(self, x: np.ndarray):
        assert np.max(x) <= self.max_index
        return np.array(list(map(self.pi, x)))

def eval_across_arrays(
    func: Callable[[int, int], float], arr1: np.ndarray, arr2: np.ndarray
):
    """Evaluate a 2D scalar function repeatedly on arrays of input."""
    assert len(arr1.shape) == len(arr2.shape) == 1, "Need arrays to be 0-dimensional"
    assert arr1.shape == arr2.shape, "Need both arrays to be of same length"


    def func_to_apply(slice):
        return func(slice[0], slice[1])

    return np.apply_along_axis(func_to_apply, 0, np.vstack((arr1, arr2)))

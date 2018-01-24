"""
Dynamics for dicke states exploiting permutational invariance
"""
from math import factorial
from decimal import Decimal
import numpy as np

from scipy import constants
from scipy.integrate import odeint, ode
from scipy.sparse import dok_matrix, csr_matrix

from qutip import Qobj, spre, spost
from qutip import sigmax, sigmay, sigmaz, sigmap, sigmam
from qutip.solver import Result, Options
from qutip import *

from qutip.cy.spmatfuncs import cy_ode_rhs
from qutip.ui.progressbar import BaseProgressBar, TextProgressBar
from qutip.mesolve import _generic_ode_solve
from piqs.cy.dicke import Dicke as _Dicke
from piqs.cy.dicke import (j_min, j_vals, get_blocks, 
                      jmm1_dictionary, num_dicke_states,
                      num_dicke_ladders)
# ============================================================================
# Functions necessary to generate the Lindbladian/Liouvillian for j, m, m1
# ============================================================================
def num_tls(nds):
    """
    The number of two level systems (TLS), given the number of Dicke states.
    Inverse function of num_dicke_states(N)

    Parameters
    ----------
    nds: int
         The number of Dicke states
    Returns
    -------
    N: int
        The number of two level systems
    """
    if np.sqrt(nds).is_integer():
        # N is even
        N = 2 * (np.sqrt(nds) - 1)
    else:
        # N is odd
        N = 2 * (np.sqrt(nds + 1 / 4) - 1)

    return int(N)


def isdiagonal(matrix):
    """
    Check if a matrix is diagonal either if it is a Qobj or a ndarray
    """
    if isinstance(matrix, Qobj):
        matrix = matrix.full()

    isdiag = np.all(matrix == np.diag(np.diagonal(matrix)))

    return isdiag


def block_matrix(N):
    """
    Gives the block diagonal matrix filled with 1 if the matrix element is
    allowed in the reduced basis |j,m><j,m'|.

    Parameters
    ----------
    N: int
        Number of two-level systems

    Returns
    -------
    block_matr: ndarray
        A block diagonal matrix of ones with dimension (nds,nds), where nds
        is the number of Dicke states for N two-level systems.
    """
    nds = num_dicke_states(N)

    # create a list with the sizes of the blocks, in order
    blocks_dimensions = int(N / 2 + 1 - 0.5 * (N % 2))
    blocks_list = [(2 * (i + 1 * (N % 2)) + 1 * ((N + 1) % 2))
                   for i in range(blocks_dimensions)]
    blocks_list = np.flip(blocks_list, 0)

    # create a list with each block matrix as element

    square_blocks = []
    k = 0
    for i in blocks_list:
        square_blocks.append(np.ones((i, i)))
        k = k + 1

    # create the final block diagonal matrix (dense)
    block_matr = block_diag(square_blocks)
    return block_matr


class Piqs(object):
    """
    The Dicke States class.

    Parameters
    ----------
    N : int
        The number of two level systems
        default: 2

    hamiltonian : Qobj matrix
        An Hamiltonian H in the reduced basis set by `reduced_algebra()`.
        Matrix dimensions are (nds, nds), with nds = num_dicke_states.
        The hamiltonian is assumed to be with hbar = 1.
        default: H = jz_op(N)

    emission : float
        Collective spontaneous emmission coefficient
        default: 1.0

    loss : float
        Incoherent loss coefficient
        default: 0.0

    dephasing : float
        Local dephasing coefficient
        default: 0.0

    pumping : float
        Incoherent pumping coefficient
        default: 0.0

    collective_pumping : float
        Collective pumping coefficient
        default: 0.0

    collective_dephasing : float
        Collective dephasing coefficient
        default: 0.0
    nds : int
        The number of Dicke states
        default: nds(2) = 4

    dshape : tuple
        The tuple (nds, nds)
        default: (4,4)

    blocks : array
        A list which gets the number of cumulative elements at each block
        boundary
        default:  array([3, 4])
    """

    def __init__(self, N=1, hamiltonian=None,
                 loss=0., dephasing=0., pumping=0., emission=0.,
                 collective_pumping=0., collective_dephasing=0.):
        self.N = N
        self.hamiltonian = hamiltonian

        self.emission = emission
        self.loss = loss
        self.dephasing = dephasing
        self.pumping = pumping
        self.collective_pumping = collective_pumping
        self.collective_dephasing = collective_dephasing

        self.nds = num_dicke_states(self.N)
        self.dshape = (num_dicke_states(self.N), num_dicke_states(self.N))

    def __repr__(self):
        """
        Print the current parameters of the system.
        """
        string = []
        string.append("N = {}".format(self.N))
        string.append("Hilbert space dim = {}".format(self.dshape))
        string.append("emission = {}".format(self.emission))
        string.append("loss = {}".format(self.loss))
        string.append("dephasing = {}".format(self.dephasing))
        string.append("pumping = {}".format(self.pumping))
        string.append(
            "collective_dephasing = {}".format(
                self.collective_dephasing))
        string.append(
            "collective_pumping = {}".format(
                self.collective_pumping))

        return "\n".join(string)

    def lindbladian(self):
        """
        Build the Lindbladian superoperator of the dissipative dynamics as a
        sparse matrix using a Cythonized function

        Returns
        ----------
        lindbladian: Qobj superoperator (sparse)
                The matrix size is (nds**2, nds**2) where nds is the number of
                Dicke states.
        """
        cythonized_dicke = _Dicke(int(self.N), float(self.loss),
                                  float(self.dephasing),
                                  float(self.pumping),
                                  float(self.emission),
                                  float(self.collective_pumping),
                                  float(self.collective_dephasing))

        return cythonized_dicke.lindbladian()

    def liouvillian(self):
        """
        Gives the total liouvillian in the jmm1 basis |j, m > < j, m1|
        """

        lindblad = self.lindbladian()

        if self.hamiltonian is None:
            liouv = lindblad
        else:
            hamiltonian = self.hamiltonian
            hamiltonian_superoperator = - 1j * \
                spre(hamiltonian) + 1j * spost(hamiltonian)
            liouv = lindblad + hamiltonian_superoperator

        return liouv

    def solve(self, initial_state, tlist, options=None, progress_bar=None):
        """
        Solver for the Dicke model optimized with QuTiP's spmat functions
        """
        if isdiagonal(initial_state) and isdiagonal(self.hamiltonian):
            pass


    def eigenstates(self, liouvillian):
        """
        Calculates the eigenvalues and eigenvectors of the Liouvillian,
        removing the spurious ones.

        Parameters
        ----------
        liouvillian: Qobj superoperator type
            The Liouvillian of which to calculate the spectrum.

        Returns
        -------
        eigen_states: list of Qobj
            The list of eigenvalues and correspondent eigenstates.
        """
        unpruned_eigenstates = liouvillian.eigenstates()
        eigen_states = self.prune_eigenstates(unpruned_eigenstates)
        return eigen_states

    def prune_eigenstates(self, liouvillian_eigenstates):
        """
        Removes the spurious eigenvalues and eigenvectors of the Liouvillian.
        Spurious means that the given eigenvector has elements outside of the
        block diagonal matrix.

        Parameters
        ----------
        liouvillian_eigenstates: list of Qobj
            A list with the eigenvalues and eigenvectors of the Liouvillian
            including spurious ones.

        Returns
        -------
        correct_eigenstates: list of Qobj
            The list with the correct eigenvalues and eigenvectors of the
            Liouvillian.
        """

        N = self.N
        block_mat = block_matrix(N)
        nnz_tuple_bm = [(i, j) for i, j in zip(*block_mat.nonzero())]

        # 0. Create  a copy of the eigenvalues to approximate values
        eig_val, eig_vec = liouvillian_eigenstates
        tol = 10
        eig_val_round = np.round(eig_val, tol)

        # 2. Use 'block_matrix(N)' to remove eigenvectors with matrix
        # elements
        # outside of the block matrix.
        forbidden_eig_index = []
        for k in range(0, len(eig_vec)):
            dm = vector_to_operator(eig_vec[k])
            nnz_tuple = [(i, j) for i, j in zip(*dm.data.nonzero())]
            for i in nnz_tuple:
                if i not in nnz_tuple_bm:
                    if np.round(dm[i], tol) != 0:
                        forbidden_eig_index.append(k)

        forbidden_eig_index = np.array(list(set(forbidden_eig_index)))
        # 3. Remove the forbidden eigenvalues and eigenvectors.
        correct_eig_val = np.delete(eig_val, forbidden_eig_index)
        correct_eig_vec = np.delete(eig_vec, forbidden_eig_index)
        correct_eigenstates = correct_eig_val, correct_eig_vec

        return correct_eigenstates


# ============================================================================
# Functions necessary to generate the Lindbladian/Liouvillian for j, m
# ============================================================================
class Pim(object):
    """
    The permutation invariant matrix class. Initialize the class with the
    parameters for generating a permutation invariant density matrix. This
    is a faster implementation for diagonal Hamiltonians when the initial
    state is also diagonal in the Dicke basis. i.e., we only have non-zero
    coefficient values for |j, m, m>.

    Parameters
    ----------
    N : int
        The number of two level systems
        default: 2

    emission : float
        Collective loss emmission coefficient
        default: 1.0

    loss : float
        Incoherent loss coefficient
        default: 0.0

    dephasing : float
        Local dephasing coefficient
        default: 0.0

    pumping : float
        Incoherent pumping coefficient
        default: 0.0

    collective_pumping : float
        Collective pumping coefficient
        default: 0.0

    M: dict
        A nested dictionary of the structure {row: {col: val}} which holds
        non zero elements of the matrix M

    sparse_M: scipy.sparse.csr_matrix
        A sparse representation of the matrix M for efficient vector
        multiplication
    """

    def __init__(self, N=2, loss=0, dephasing=0, pumping=0,
                 emission=1, collective_pumping=0, collective_dephasing=0):
        self.N = N
        self.emission = emission
        self.loss = loss
        self.dephasing = dephasing
        self.pumping = pumping
        self.collective_pumping = collective_pumping
        self.collective_dephasing = collective_dephasing
        self.M = None

    def sparse_M(self):
        """
        Wraps around the Cythonized _Pim class to generate the sparse matrix
        `M` which can be used to evolve the system as:

        .. math::
            \frac{\partial\rho}{\partial t} = M\rho
        """
        system = _Pim(int(self.N), float(self.loss), float(self.dephasing),
                      float(self.pumping), float(self.emission),
                      float(self.collective_pumping),
                      float(self.collective_dephasing))

        self.M = system.generate_matrix()
        return self.M

    def solve(self, initial_state, tlist, options=None, progress_bar=None):
        """
        An optimized solver for diagonal states using the matrix M and QuTiP's
        sparse `spmat` routine
        """
        if options is None:
            options = Options()
        if progress_bar is None:
            progress_bar = BaseProgressBar()
        elif progress_bar is True:
            progress_bar = TextProgressBar()

        n_tsteps = len(tlist)
        output = Result()
        output.solver = "pim"

        if options.store_states:
            output.states = []

        M = self.M
        r = scipy.integrate.ode(cy_ode_rhs)

        r.set_f_params(M.data, M.indices, M.indptr)
        r.set_integrator('zvode', method=options.method,order=options.order,
                 atol=options.atol, rtol=options.rtol,
                 nsteps=options.nsteps, first_step=options.first_step,
                 min_step=options.min_step,max_step=options.max_step)

        rho0 = None
        if not isinstance(initial_state, Qobj):
            rho0 = Qobj(initial_state)

        else:
            rho0 = initial_state

        r.set_initial_value(initial_state.data, tlist[0])

        return _generic_ode_solve(r, rho0, tlist, e_ops, opt, progress_bar)


# ============================================================================
# Utility functions for operators in the Dicke basis
# ============================================================================
def energy_degeneracy(N, m):
    """
    Calculates how many Dicke states |j, m, alpha> have the same energy
    (hbar * omega_0 * m) given N two-level systems.
    The use of the Decimals class allows to explore N > 1000,
    unlike the built-in function 'scipy.special.binom(N, N/2 + m)'

    Parameters
    ----------
    N: int
        The number of two level systems.
    m: float
        Total spin z-axis projection eigenvalue.
        This is proportional to the total energy)

    Returns
    -------
    degeneracy: int
        The energy degeneracy
    """
    numerator = Decimal(factorial(N))
    d1 = Decimal(factorial(N / 2 + m))
    d2 = Decimal(factorial(N / 2 - m))

    degeneracy = numerator / (d1 * d2)

    return int(degeneracy)


def state_degeneracy(N, j):
    """
    Calculates the degeneracy of the Dicke state |j, m>.
    Each state |j, m> includes D(N,j) irreducible representations |j, m,alpha>.
    Uses Decimals to calculate higher numerator and denominators numbers.

    Parameters
    ----------
    N: int
        The number of two level systems.

    j: float
        Total spin eigenvalue (cooperativity)

    Returns
    -------
    degeneracy: int
        The state degeneracy
    """
    numerator = Decimal(factorial(N)) * Decimal(2 * j + 1)
    denominator_1 = Decimal(factorial(N / 2 + j + 1))
    denominator_2 = Decimal(factorial(N / 2 - j))

    degeneracy = numerator / (denominator_1 * denominator_2)
    degeneracy = int(np.round(float(degeneracy)))

    if degeneracy < 0:
        raise ValueError("m-degeneracy must be >=0")

    return degeneracy


def m_degeneracy(N, m):
    """
    The number of Dicke states |j, m> with same energy (hbar * omega_0 * m)
    for N two-level systems.

    Parameters
    ----------
    N : int
        The number of two level systems
    m: float
        Total spin z-axis projection eigenvalue (proportional to the total
        energy)

    Returns
    -------
    degeneracy: int
        The m-degeneracy
    """
    degeneracy = N / 2 + 1 - abs(m)
    if degeneracy % 1 != 0 or degeneracy <= 0:
        e = "m-degeneracy must be integer >=0, "
        e.append("but degeneracy = {}".format(degeneracy))
        raise ValueError(e)
    return int(degeneracy)


def su2_algebra(N):
    """
    Creates the vector (sx, sy, sz, sm, sp) with the spin operators of a
    collection of N two-level systems (TLSs). Each element of the vector,
    i.e., sx, is a vector of Qobs objects (spin matrices), as it cointains the
    list of the SU(2) Pauli matrices for the N TLSs. Each TLS operator
    sx[i], with i = 0, ..., (N-1), is placed in a 2^N-dimensional
    Hilbert space.

    Parameters
    ----------
    N: int
        The number of two level systems

    Returns
    -------
    su2_operators: list
        A list of Qobs matrices (Qutip objects) - [sx, sy, sz, sm, sp]
    """
    # 1. Define N TLS spin-1/2 matrices in the uncoupled basis
    N = int(N)
    sx = [0 for i in range(N)]
    sy = [0 for i in range(N)]
    sz = [0 for i in range(N)]
    sm = [0 for i in range(N)]
    sp = [0 for i in range(N)]
    sx[0] = 0.5 * sigmax()
    sy[0] = 0.5 * sigmay()
    sz[0] = 0.5 * sigmaz()
    sm[0] = sigmam()
    sp[0] = sigmap()

    # 2. Place operators in total Hilbert space
    for k in range(N - 1):
        sx[0] = tensor(sx[0], identity(2))
        sy[0] = tensor(sy[0], identity(2))
        sz[0] = tensor(sz[0], identity(2))
        sm[0] = tensor(sm[0], identity(2))
        sp[0] = tensor(sp[0], identity(2))

    # 3. Cyclic sequence to create all N operators
    a = [i for i in range(N)]
    b = [[a[i - i2] for i in range(N)] for i2 in range(N)]

    # 4. Create N operators
    for i in range(1, N):
        sx[i] = sx[0].permute(b[i])
        sy[i] = sy[0].permute(b[i])
        sz[i] = sz[0].permute(b[i])
        sm[i] = sm[0].permute(b[i])
        sp[i] = sp[0].permute(b[i])

    su2_operators = [sx, sy, sz, sm, sp]

    return su2_operators


def collective_algebra(N):
    """
    Uses the module su2_algebra to create the collective spin algebra
    Jx, Jy, Jz, Jm, Jp. It uses the basis of the sinlosse two-level system
    (TLS) SU(2) Pauli matrices. Each collective operator is placed in a
    Hilbert space of dimension 2^N.

    Parameters
    ----------
    N: int
        The number of two level systems

    Returns
    -------
    collective_operators: vector of Qobs matrices (Qutip objects)
        collective_operators = [Jx, Jy, Jz, Jm, Jp]
    """
    # 1. Define N TLS spin-1/2 matrices in the uncoupled basis
    N = int(N)

    si_TLS = su2_algebra(N)

    sx = si_TLS[0]
    sy = si_TLS[1]
    sz = si_TLS[2]
    sm = si_TLS[3]
    sp = si_TLS[4]

    jx = sum(sx)
    jy = sum(sy)
    jz = sum(sz)
    jm = sum(sm)
    jp = sum(sp)

    collective_operators = [jx, jy, jz, jm, jp]

    return collective_operators


def c_ops_tls(N=2, emission=1., loss=0., dephasing=0., pumping=0.,
              collective_pumping=0., collective_dephasing=0.):
    """
    Create the collapse operators (c_ops) of the Lindblad master equation in
    the TLS uncoupled basis. The collapse operators oare created to be given
    to the Qutip algorithm 'mesolve'. 'mesolve' is used in the main file to
    calculate the time evolution for N two-level systems (TLSs).
    Notice that the operators are placed in a Hilbert space of dimension 2^N.
    Thus the method is suitable only for small N.

    Parameters
    ----------
    N: int
        The number of two level systems
    emission: float
        default = 2
        Spontaneous emission coefficient
    loss: float
        default = 0
        Losses coefficient (i.e. nonradiative emission)
    dephasing: float
        default = 0
        Dephasing coefficient
    pumping: float
        default = 0
        Incoherent pumping coefficient
    collective_pumping: float
        default = 0
        Collective pumping coefficient
    collective_dephasing: float
        default = 0
        Collective dephasing coefficient

    Returns
    -------
    c_ops: c_ops vector of matrices
        c_ops contains the collapse operators for the Lindbla

    """
    N = int(N)

    if N > 10:
        print("""Warning! N > 10. dim(H) = 2^N. Use only the permutational
              invariant methods for large N. """)

    [sx, sy, sz, sm, sp] = su2_algebra(N)
    [jx, jy, jz, jm, jp] = collective_algebra(N)

    c_ops = []

    if emission != 0:
        c_ops.append(np.sqrt(emission) * jm)

    if dephasing != 0:
        for i in range(0, N):
            c_ops.append(np.sqrt(dephasing) * sz[i])

    if loss != 0:
        for i in range(0, N):
            c_ops.append(np.sqrt(loss) * sm[i])

    if pumping != 0:
        for i in range(0, N):
            c_ops.append(np.sqrt(pumping) * sp[i])

    if collective_pumping != 0:
        c_ops.append(np.sqrt(collective_pumping) * jp)

    if collective_dephasing != 0:
        c_ops.append(np.sqrt(collective_dephasing) * jz)

    return c_ops


# ============================================================================
# State definitions in the Dicke basis with an option for basis transformation
# ============================================================================
def dicke(N, jmm1 = None, basis = "dicke"):
    """
    Initialize a Dicke basis state from a dictionary of coefficients for each
    jmm1 value in the dictionary jmm1. For instance, if we start from the most
    excited state for N = 2, we have the following state represented as a
    density matrix of size (nds, nds) or (4, 4).

    1 0 0 0
    0 0 0 0
    0 0 0 0
    0 0 0 0 
    
    Similarly, if the state was rho0 = |0, 0, 0> + |1, -1, -1>, the density
    matrix in the Dicke basis would be:

    0 0 0 0
    0 1 0 0
    0 0 0 0
    0 0 0 1

    The mapping for the (i, k) index of the density matrix to the |j,m,m1>
    values is given by the cythonized function `jmm1_dictionary`.

    This function can thus be used to build arbitrary states in the Dicke
    basis.

    Parameters
    ==========
    N: int
        The number of two-level systems

    jmm1: dict
        A dictionary of {(j, m, m1): p} which gives the coefficient of the (j, m, m1)
        state in the density matrix.
    """
    if basis == "uncoupled":
        raise NotImplemented

    if jmm1 == None:
        msg = "Please specify the jmm1 values as a dictionary"
        msg += "or use the `excited(N)` function to create an"
        msg += "excited state where jmm1 = {(N/2, N/2, N/2): 1}"
        raise AttributeError(msg)

    nds = num_dicke_states(N)
    rho = np.zeros((nds, nds))

    jmm1_dict = jmm1_dictionary(N)[0]

    for key in jmm1:
        i, k = jmm1_dict[key]
        rho[i, k] = jmm1[key]

    return Qobj(rho)


def excited(N, basis='dicke'):
    """
    Generates an initial dicke state density matrix |N/2, N/2, N/2> in the dicke basis.
    If the argument `basis` is "uncoupled" then it generates the state in
    a 2**N dim Hilbert space.
    """
    if basis == "uncoupled":
        return _uncoupled_excited(N)

    jmm1 = {(N/2, N/2, N/2): 1}
    return dicke(N, jmm1)

def superradiant(N, basis="dicke"):
    """
    Generates the superradiant dicke state as |N/2, 0, 0> or |N/2, 0.5, 0.5>
    in the dicke basis
    """
    if basis == "uncoupled":
        return _uncoupled_superradiant(N)

    if N%2 == 0:
        jmm1 = {N/2, 0, 0}
        return dicke(N, jmm1)
    else:
        jmm1 = {N/2, 0.5, 0.5}
        return dicke(N, jmm1)

def css(N, a=1, b=1, basis="dicke"):
    """
    Loads the separable spin state |->= Prod_i^N(a|1>_i + b|0>_i) into the reduced density matrix rho(j,m,m'). 
    """
    if basis == "uncoupled":
        return _uncoupled_css(N, a, b)

    nds = num_dicke_states(N)
    num_ladders = num_dicke_ladders(N)
    rho = dok_matrix((nds, nds))

    # loop in the allowed matrix elements
    jmm1_dict = jmm1_dictionary(N)[0]

    j = 0.5 * N 
    mmax = int(2 * j + 1)
    for i in range(0, mmax):
        m = j - i
        psi_m = np.sqrt(float(energy_degeneracy(N, m))) * a**( N * 0.5 + m) * b**( N * 0.5 - m)
        for i1 in range(0, mmax):
            m1 = j - i1
            row_column = jmm1_dict[(j, m, m1)]
            psi_m1 = np.sqrt(float(energy_degeneracy(N, m1))) * a**( N * 0.5 + m1) * b**( N * 0.5 - m1)
            rho[row_column] = psi_m * psi_m1
    
    return Qobj(rho)

def ghz(N, basis='dicke'):
    """
    Generates the GHZ state
    """
    if basis == "uncoupled":
        return _uncoupled_ghz(N)

    nds = num_dicke_states(N)
    rho = dok_matrix((nds, nds))

    rho[0,0] = 1/2
    rho[N,N] = 1/2
    rho[N,0] = 1/2
    rho[0,N] = 1/2

    return Qobj(rho)

def ground(N, basis="dicke"):
    """
    Generates the ground state for N spins
    """
    if basis == "uncoupled":
        return _uncoupled_ground(N)

    nds = num_dicke_states(N)
    rho = dok_matrix((nds, nds))

    rho[-1, -1] = 1
    return Qobj(rho)

def uncoupled_identity(N):
    """
    Generates the identity in a 2**N dimensional Hilbert space

    Parameters
    ----------
    N: int
        The number of two level systems

    Returns
    -------
    identity: Qobj matrix (QuTiP class)
        With the correct dimensions (dims)
    """
    N = int(N)
    rho = np.zeros((2**N, 2**N))
    for i in range(0, 2**N):
        rho[i, i] = 1

    spin_dim = [2 for i in range(0, N)]
    spins_dims = list((spin_dim, spin_dim))
    identity = Qobj(rho, dims=spins_dims)
    return identity

# Uncoupled states in the full Hilbert space.
# These functions will be accessed when the input to a state
# generation function is supplied with the parameter `basis`
# as "uncoupled". Otherwise, we work in the default Dicke
# basis
def _uncoupled_excited(N):
    """
    Generates a initial dicke state |N/2, N/2 > as a Qobj in a 2**N
    dimensional Hilbert space

    Parameters
    ----------
    N: int
        The number of two level systems

    Returns
    -------
    psi0: Qobj array (QuTiP class)
    """
    N = int(N)
    jz = collective_algebra(N)[2]
    en, vn = jz.eigenstates()
    psi0 = vn[2**N - 1]
    return psi0

def _uncoupled_superradiant(N):
    """
    Generates a initial dicke state |N/2, 0 > (N even) or |N/2, 0.5 > (N odd)
    as a Qobj in a 2**N dimensional Hilbert space

    Parameters
    ----------
    N: int
        The number of two level systems

    Returns
    -------
    psi0: Qobj array (QuTiP class)
    """
    N = int(N)
    jz = collective_algebra(N)[2]
    en, vn = jz.eigenstates()
    psi0 = vn[2**N - N]

    return psi0

def _uncoupled_ground(N):
    """
    Generates a initial dicke state |N/2, - N/2 > as a Qobj in a 2**N
    dimensional Hilbert space

    Parameters
    ----------
    N: int
        The number of two level systems

    Returns
    -------
    psi0: Qobj array (QuTiP class)
    """
    N = int(N)
    jz = collective_algebra(N)[2]
    en, vn = jz.eigenstates()
    psi0 = vn[0]
    return psi0

def _uncoupled_ghz(N):
    """
    Generates the GHZ density matrix in a 2**N dimensional Hilbert space

    Parameters
    ----------
    N: int
        The number of two level systems

    Returns
    -------
    ghz: Qobj matrix (QuTiP class)
        With the correct dimensions (dims)
    """
    N = int(N)

    rho = np.zeros((2**N, 2**N))
    rho[0, 0] = 1 / 2
    rho[2**N - 1, 0] = 1 / 2
    rho[0, 2**N - 1] = 1 / 2
    rho[2**N - 1, 2**N - 1] = 1 / 2

    spin_dim = [2 for i in range(0, N)]
    spins_dims = list((spin_dim, spin_dim))

    rho = Qobj(rho, dims=spins_dims)
    return rho

# This needs to be consistent to allow for coefficients a and b in the state
# as a|0> + b|1>
def _uncoupled_css(N, a, b):
    """
    Generates the CSS density matrix in a 2**N dimensional Hilbert space.
    The CSS state, also called 'plus state' is,

    |+>_i = 1/np.sqrt(2) * (|0>_i + |1>_i ).

    Parameters
    ----------
    N: int
        The number of two level systems

    Returns
    -------
    ghz: Qobj matrix (QuTiP class)
        With the correct dimensions (dims)
    """
    N = int(N)

    # 1. Define i_th factorized density matrix in the uncoupled basis
    rho = [0 for i in range(N)]
    rho[0] = 0.5 * (qeye(2) + sigmax())

    # 2. Place single-two-level-system density matrices in total Hilbert space
    for k in range(N - 1):
        rho[0] = tensor(rho[0], identity(2))

    # 3. Cyclic sequence to create all N factorized density matrices |+><+|_i
    a = [i for i in range(N)]
    b = [[a[i - i2] for i in range(N)] for i2 in range(N)]

    # 4. Create all other N-1 factorized density matrices
    # |+><+| = Prod_(i=1)^N |+><+|_i
    for i in range(1, N):
        rho[i] = rho[0].permute(b[i])

    identity_i = Qobj(np.eye(2**N), dims=rho[0].dims, shape=rho[0].shape)
    rho_tot = identity_i

    for i in range(0, N):
        rho_tot = rho_tot * rho[i]

    return rho_tot

def _uncoupled_thermal(N, omega_0, temperature):
    """
    Gives the thermal state for a collection of N two-level systems with
    H = omega_0 * j_z. It is calculated in the full 2**N Hilbert state on the
    eigenstates of H in the uncoupled basis, not the Dicke basis.

    Parameters
    ----------
    N: int
        The number of two level systems

    omega_0: float
        The resonance frequency of each two-level system (homogeneous)

    temperature: float
        The absolute temperature in Kelvin

    Returns
    -------
    rho_thermal: Qobj operator
        The thermal state calculated in the full Hilbert space 2**N
    """
    N = int(N)
    x = (omega_0 / temperature) * (constants.hbar / constants.Boltzmann)

    jz = collective_algebra(N)[2]
    m_list = jz.eigenstates()[0]
    m_list = np.flip(m_list, 0)

    rho_thermal = np.zeros(jz.shape)

    for i in range(jz.shape[0]):
        rho_thermal[i, i] = np.exp(- x * m_list[i])
    rho_thermal = Qobj(rho_thermal, dims=jz.dims, shape=jz.shape)

    zeta = uncoupled_partition_function(N, omega_0, temperature)

    rho_thermal = rho_thermal / zeta

    return rho_thermal


def uncoupled_partition_function(N, omega_0, temperature):
    """
    Gives the partition function for a collection of N two-level systems
    with H = omega_0 * j_z.
    It is calculated in the full 2**N Hilbert state, using the eigenstates of
    H in the uncoupled basis, not the Dicke basis.

    Parameters
    ----------
    N: int
        The number of two level systems
    omega_0: float
        The resonance frequency of each two-level system (homogeneous ensemble)
    temperature: float
        The absolute temperature in Kelvin
    Returns
    -------
    zeta: float
        The partition function for the thermal state of H calculated summing
        over all 2**N states
    """
    N = int(N)
    x = (omega_0 / temperature) * (constants.hbar / constants.Boltzmann)

    jz = collective_algebra(N)[2]
    m_list = jz.eigenstates()[0]

    zeta = 0

    for m in m_list:
        zeta = zeta + np.exp(- x * m)

    return zeta

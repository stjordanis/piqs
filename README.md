# Permutational Invariant Quantum Solver (PIQS) <img src="https://github.com/nathanshammah/piqs/blob/master/doc/piqs_logo.png" width="80" height="80"/>

[![Build Status](https://travis-ci.org/nathanshammah/piqs.svg?branch=master)](https://travis-ci.org/nathanshammah/piqs)
[![DOI](https://zenodo.org/badge/104438298.svg)](https://zenodo.org/badge/latestdoi/104438298)
[![codecov](https://codecov.io/gh/nathanshammah/piqs/branch/master/graph/badge.svg)](https://codecov.io/gh/nathanshammah/piqs)

PIQS is an open-source Python library that allows to study the exact Lindbladian dynamics of open quantum systems consisting of identical qubits. The documentation for the package can be found in [piqs.readthedocs.io](http://piqs.readthedocs.io/en/latest/). Example notebooks on how to use the library can be found [here](https://github.com/nathanshammah/notebooks).

## Exponential reduction 
In the case where local processes are included in the model of a system's dynamics, numerical simulation requires dealing with density matrices of exponential sizes. This becomes infeasible for a large number of qubits. We can simplify the calculations by exploiting the permutational invariance of indistinguishable quantum particles which allows the user to study hundreds of qubits.

## Integrated with QuTiP
A major feature of PIQS is that it allows to build the Liouvillian of the system in an optimal way. It uses Cython to optimize performance and by defining sparse matrices it can deal with large systems. Since it is compatible with the `quantum object` class of [QuTiP](http://qutip.org/) one can take full advantage of existing features of this excellent open-source library.


## A wide range of applications
- The time evolution of the total density matrix of quantum optics and cavity QED systems for permutationally symmetric initial states (such as the GHZ state, Dicke states, coherent spin states).
- Phase transitions of driven-dissipative out-of-equilibrium quantum systems.  
- Correlation functions of collective systems in quantum optics experiments, such as the spectral density and second-order correlation functions.
- Various quantum optics phenomena such as resonance fluorescence, steady-state superradiance, superradiant light emission.
- Spin squeezing for quantum metrology, long-range interaction in noisy spin models, decoherence in quantum information processing. 
- Nonlinearities of dissipative cavity QED systems up to the ultrastrong coupling regime.

## Installation
### Linux and MacOS
We have made the package available in [conda-forge](https://conda-forge.org/). Download and install Anaconda or Miniconda from [https://www.anaconda.com/download/](https://www.anaconda.com/download/) and then install `piqs` from the conda-forge repository with,
```
conda install -c conda-forge piqs
```
You may also want to set `conda-forge` as a channel with
```
conda config --add channels conda-forge
```
Then you can fire up a Jupyter notebook and run `piqs` out of your browser.

### Windows
We will add a Windows version soon but if you are on Windows, you can build piqs from source by first installing conda. You can add the conda-forge channel with `conda config --add channels conda-forge`. Then, please install `cython`, `numpy`, `scipy` and `qutip` as `piqs` depends on these packages. The command is simply `conda install cython numpy scipy qutip`.

Then download the [source code](https://github.com/nathanshammah/piqs/archive/v1.2.tar.gz), unzip it and running the setup file inside with,
```
python setup.py install
```
If you have any problems installing the tool, please open an issue or write to us.

## Use
```
from piqs import Dicke
from qutip import steadystate

N = 10
system = Dicke(N, emission = 1, pumping = 3)

L = system.liouvillian()
steady = steadystate(L)
```
For more details and examples on the use of *PIQS* see the [notebooks](https://github.com/nathanshammah/notebooks) folder. 

![Density matrices in the Dicke basis.](https://github.com/nathanshammah/piqs/blob/master/doc/source/examples/images/states_N.png)
## License
PIQS is licensed under the terms of the BSD license.

## Documentation
PIQS documentation can be found at http://piqs.readthedocs.io/.

## Notebooks
### PIQS Notebooks include Jupyter notebooks for the paper https://arxiv.org/abs/1805.05129
- Superradiant light emission
- Steady-state superradiance
- Superradiant phase transition out of equilibrium
- Spin squeezing
- Ultrastrong light-matter coupling 
- Multiple ensembles of qubits
- Boundary time crystals
- Performance of PIQS 

A collection of Jupyter notebooks can be found at https://github.com/nathanshammah/notebooks.

## Citation
DOI:10.5281/zenodo.1212802

## Resources
Theoretical aspects and applications are in Ref. [1]. Other open-source codes using permutational invariance to study open quantum systems and related research papers can be found in [2-3].

[1] N. Shammah, S. Ahmed, N. Lambert, S. De Liberato, and F. Nori, https://arxiv.org/abs/1805.05129

[2] https://github.com/peterkirton/permutations P. Kirton and J. Keeling *Phys. Rev. Lett.*  **118**, 123602 (2017)

[3] https://github.com/modmido/psiquasp M. Gegg and M. Richter, *Sci. Rep.* **7**, 16304 (2017)

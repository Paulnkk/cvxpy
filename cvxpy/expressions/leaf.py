"""
Copyright 2013 Steven Diamond

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from cvxpy import Constant, Parameter, Variable
    from cvxpy.atoms.atom import Atom

import numbers

import numpy as np
import numpy.linalg as LA
import scipy.sparse as sp

import cvxpy.interface as intf
from cvxpy.constraints.constraint import Constraint
from cvxpy.expressions import expression
from cvxpy.settings import (
    GENERAL_PROJECTION_TOL,
    PSD_NSD_PROJECTION_TOL,
    SPARSE_PROJECTION_TOL,
)


class Leaf(expression.Expression):
    """
    A leaf node of an expression tree; i.e., a Variable, Constant, or Parameter.

    A leaf may carry *attributes* that constrain the set values permissible
    for it. Leafs can have no more than one attribute, with the exception
    that a leaf may be both ``nonpos`` and ``nonneg`` or both ``boolean``
    in some indices and ``integer`` in others.

    An error is raised if a leaf is assigned a value that contradicts
    one or more of its attributes. See the ``project`` method for a convenient
    way to project a value onto a leaf's domain.

    Parameters
    ----------
    shape : Iterable of ints or int
        The leaf dimensions. Either an integer n for a 1D shape, or an
        iterable where the semantics are the same as NumPy ndarray shapes.
        **Shapes cannot be more than 2D**.
    value : numeric type
        A value to assign to the leaf.
    nonneg : bool
        Is the variable constrained to be nonnegative?
    nonpos : bool
        Is the variable constrained to be nonpositive?
    complex : bool
        Is the variable complex valued?
    symmetric : bool
        Is the variable symmetric?
    diag : bool
        Is the variable diagonal?
    PSD : bool
        Is the variable constrained to be positive semidefinite?
    NSD : bool
        Is the variable constrained to be negative semidefinite?
    Hermitian : bool
        Is the variable Hermitian?
    boolean : bool or list of tuple
        Is the variable boolean? True, which constrains
        the entire Variable to be boolean, False, or a list of
        indices which should be constrained as boolean, where each
        index is a tuple of length exactly equal to the
        length of shape.
    integer : bool or list of tuple
        Is the variable integer? The semantics are the same as the
        boolean argument.
    sparsity : list of tuplewith
        Fixed sparsity pattern for the variable.
    pos : bool
        Is the variable positive?
    neg : bool
        Is the variable negative?
    """

    __metaclass__ = abc.ABCMeta

    def __init__(
        self, shape: int | Iterable[int, ...], value=None, nonneg: bool = False,
        nonpos: bool = False, complex: bool = False, imag: bool = False,
        symmetric: bool = False, diag: bool = False, PSD: bool = False,
        NSD: bool = False, hermitian: bool = False,
        boolean: bool = False, integer: bool = False,
        sparsity=None, pos: bool = False, neg: bool = False, bounds=None
    ) -> None:
        if isinstance(shape, numbers.Integral):
            shape = (int(shape),)
        elif len(shape) > 2:
            raise ValueError("Expressions of dimension greater than 2 "
                             "are not supported.")
        for d in shape:
            if not isinstance(d, numbers.Integral) or d <= 0:
                raise ValueError("Invalid dimensions %s." % (shape,))
        shape = tuple(np.int32(d) for d in shape)
        self._shape = shape

        if (PSD or NSD or symmetric or diag or hermitian) and (len(shape) != 2
                                                               or shape[0] != shape[1]):
            raise ValueError("Invalid dimensions %s. Must be a square matrix."
                             % (shape,))

        # Process attributes.
        self.attributes = {'nonneg': nonneg, 'nonpos': nonpos,
                           'pos': pos, 'neg': neg,
                           'complex': complex, 'imag': imag,
                           'symmetric': symmetric, 'diag': diag,
                           'PSD': PSD, 'NSD': NSD,
                           'hermitian': hermitian, 'boolean': bool(boolean),
                           'integer':  integer, 'sparsity': sparsity, 'bounds': bounds}

        if boolean:
            self.boolean_idx = boolean if not isinstance(boolean, bool) else list(
                np.ndindex(max(shape, (1,))))
        else:
            self.boolean_idx = []

        if integer:
            self.integer_idx = integer if not isinstance(integer, bool) else list(
                np.ndindex(max(shape, (1,))))
        else:
            self.integer_idx = []

        # Only one attribute be True (except can be boolean and integer).
        true_attr = sum(1 for k, v in self.attributes.items() if v)
        if boolean and integer:
            true_attr -= 1
        if true_attr > 1:
            raise ValueError("Cannot set more than one special attribute in %s."
                             % self.__class__.__name__)

        if value is not None:
            self.value = value

        self.args = []

        self.bounds = bounds

    def _get_attr_str(self) -> str:
        """Get a string representing the attributes.
        """
        attr_str = ""
        for attr, val in self.attributes.items():
            if attr != 'real' and val:
                attr_str += ", %s=%s" % (attr, val)
        return attr_str

    def copy(self, args=None, id_objects=None):
        """Returns a shallow copy of the object.

        Used to reconstruct an object tree.

        Parameters
        ----------
        args : list, optional
            The arguments to reconstruct the object. If args=None, use the
            current args of the object.

        Returns
        -------
        Expression
        """
        id_objects = {} if id_objects is None else id_objects
        if id(self) in id_objects:
            return id_objects[id(self)]
        return self  # Leaves are not deep copied.

    def get_data(self) -> None:
        """Leaves are not copied.
        """

    @property
    def shape(self) -> tuple[int, ...]:
        """ tuple : The dimensions of the expression.
        """
        return self._shape

    def variables(self) -> list[Variable]:
        """Default is empty list of Variables.
        """
        return []

    def parameters(self) -> list[Parameter]:
        """Default is empty list of Parameters.
        """
        return []

    def constants(self) -> list[Constant]:
        """Default is empty list of Constants.
        """
        return []

    def is_convex(self) -> bool:
        """Is the expression convex?
        """
        return True

    def is_concave(self) -> bool:
        """Is the expression concave?
        """
        return True

    def is_log_log_convex(self) -> bool:
        """Is the expression log-log convex?
        """
        return self.is_pos()

    def is_log_log_concave(self) -> bool:
        """Is the expression log-log concave?
        """
        return self.is_pos()

    def is_nonneg(self) -> bool:
        """Is the expression nonnegative?
        """
        return (self.attributes['nonneg'] or self.attributes['pos'] or
                self.attributes['boolean'])

    def is_nonpos(self) -> bool:
        """Is the expression nonpositive?
        """
        return self.attributes['nonpos'] or self.attributes['neg']

    def is_pos(self) -> bool:
        """Is the expression positive?
        """
        return self.attributes['pos']

    def is_neg(self) -> bool:
        """Is the expression negative?
        """
        return self.attributes['neg']

    def is_hermitian(self) -> bool:
        """Is the Leaf hermitian?
        """
        return (self.is_real() and self.is_symmetric()) or \
            self.attributes['hermitian'] or self.is_psd() or self.is_nsd()

    def is_symmetric(self) -> bool:
        """Is the Leaf symmetric?
        """
        return self.is_scalar() or \
            any(self.attributes[key] for key in ['diag', 'symmetric', 'PSD', 'NSD'])

    def is_imag(self) -> bool:
        """Is the Leaf imaginary?
        """
        return self.attributes['imag']

    def is_complex(self) -> bool:
        """Is the Leaf complex valued?
        """
        return self.attributes['complex'] or self.is_imag() or self.attributes['hermitian']

    @property
    def domain(self) -> list[Constraint]:
        """A list of constraints describing the closure of the region
           where the expression is finite.
        """
        # Default is full domain.
        domain = []
        if self.attributes['nonneg'] or self.attributes['pos']:
            domain.append(self >= 0)
        elif self.attributes['nonpos'] or self.attributes['neg']:
            domain.append(self <= 0)
        elif self.attributes['PSD']:
            domain.append(self >> 0)
        elif self.attributes['NSD']:
            domain.append(self << 0)
        return domain

    def project(self, val):
        """Project value onto the attribute set of the leaf.

        A sensible idiom is ``leaf.value = leaf.project(val)``.

        Parameters
        ----------
        val : numeric type
            The value assigned.

        Returns
        -------
        numeric type
            The value rounded to the attribute type.
        """
        # Only one attribute can be active at once (besides real,
        # nonpos/nonneg, and bool/int).
        if not self.is_complex():
            val = np.real(val)

        if self.attributes['nonpos'] and self.attributes['nonneg']:
            return 0*val
        elif self.attributes['nonpos'] or self.attributes['neg']:
            return np.minimum(val, 0.)
        elif self.attributes['nonneg'] or self.attributes['pos']:
            return np.maximum(val, 0.)
        elif self.attributes['imag']:
            return np.imag(val)*1j
        elif self.attributes['complex']:
            return val.astype(complex)
        elif self.attributes['boolean']:
            # TODO(akshayka): respect the boolean indices.
            return np.round(np.clip(val, 0., 1.))
        elif self.attributes['integer']:
            # TODO(akshayka): respect the integer indices.
            # also, a variable may be integer in some indices and
            # boolean in others.
            return np.round(val)
        elif self.attributes['diag']:
            if intf.is_sparse(val):
                val = val.diagonal()
            else:
                val = np.diag(val)
            return sp.diags([val], [0])
        elif self.attributes['hermitian']:
            return (val + np.conj(val).T)/2.
        elif any([self.attributes[key] for
                  key in ['symmetric', 'PSD', 'NSD']]):
            if val.dtype.kind in 'ib':
                val = val.astype(float)
            val = val + val.T
            val /= 2.
            if self.attributes['symmetric']:
                return val
            w, V = LA.eigh(val)
            if self.attributes['PSD']:
                bad = w < 0
                if not bad.any():
                    return val
                w[bad] = 0
            else:  # NSD
                bad = w > 0
                if not bad.any():
                    return val
                w[bad] = 0
            return (V * w).dot(V.T)
        else:
            return val

    # Getter and setter for parameter value.
    def save_value(self, val) -> None:
        self._value = val

    @property
    def value(self):
        """NumPy.ndarray or None: The numeric value of the parameter.
        """
        return self._value

    @value.setter
    def value(self, val) -> None:
        self.save_value(self._validate_value(val))

    def project_and_assign(self, val) -> None:
        """Project and assign a value to the variable.
        """
        self.save_value(self.project(val))

    def _validate_value(self, val):
        """Check that the value satisfies the leaf's symbolic attributes.

        Parameters
        ----------
        val : numeric type
            The value assigned.

        Returns
        -------
        numeric type
            The value converted to the proper matrix type.
        """
        if val is not None:
            # Convert val to ndarray or sparse matrix.
            val = intf.convert(val)
            if intf.shape(val) != self.shape:
                raise ValueError(
                    "Invalid dimensions %s for %s value." %
                    (intf.shape(val), self.__class__.__name__)
                )
            projection = self.project(val)
            # ^ might be a numpy array, or sparse scipy matrix.
            delta = np.abs(val - projection)
            # ^ might be a numpy array, scipy matrix, or sparse scipy matrix.
            if intf.is_sparse(delta):
                # ^ based on current implementation of project(...),
                #   is is not possible for this Leaf to be PSD/NSD *and*
                #   a sparse matrix.
                close_enough = np.allclose(delta.data, 0,
                                           atol=SPARSE_PROJECTION_TOL)
                # ^ only check for near-equality on nonzero values.
            else:
                # the data could be a scipy matrix, or a numpy array.
                # First we convert to a numpy array.
                delta = np.array(delta)
                # Now that we have the residual, we need to measure it
                # in some canonical way.
                if self.attributes['PSD'] or self.attributes['NSD']:
                    # For PSD/NSD Leafs, we use the largest-singular-value norm.
                    close_enough = LA.norm(delta, ord=2) <= PSD_NSD_PROJECTION_TOL
                else:
                    # For all other Leafs we use the infinity norm on
                    # the vectorized Leaf.
                    close_enough = np.allclose(delta, 0,
                                               atol=GENERAL_PROJECTION_TOL)
            if not close_enough:
                if self.attributes['nonneg']:
                    attr_str = 'nonnegative'
                elif self.attributes['pos']:
                    attr_str = 'positive'
                elif self.attributes['nonpos']:
                    attr_str = 'nonpositive'
                elif self.attributes['neg']:
                    attr_str = 'negative'
                elif self.attributes['diag']:
                    attr_str = 'diagonal'
                elif self.attributes['PSD']:
                    attr_str = 'positive semidefinite'
                elif self.attributes['NSD']:
                    attr_str = 'negative semidefinite'
                elif self.attributes['imag']:
                    attr_str = 'imaginary'
                else:
                    attr_str = ([k for (k, v) in self.attributes.items() if v] + ['real'])[0]
                raise ValueError(
                    "%s value must be %s." % (self.__class__.__name__, attr_str)
                )
        return val

    def is_psd(self) -> bool:
        """Is the expression a positive semidefinite matrix?
        """
        return self.attributes['PSD']

    def is_nsd(self) -> bool:
        """Is the expression a negative semidefinite matrix?
        """
        return self.attributes['NSD']

    def is_diag(self) -> bool:
        """Is the expression a diagonal matrix?
        """
        return self.attributes['diag']

    def is_quadratic(self) -> bool:
        """Leaf nodes are always quadratic.
        """
        return True

    def has_quadratic_term(self) -> bool:
        """Leaf nodes are not quadratic terms.
        """
        return False

    def is_pwl(self) -> bool:
        """Leaf nodes are always piecewise linear.
        """
        return True

    def is_dpp(self, context: str = 'dcp') -> bool:
        """The expression is a disciplined parameterized expression.

           context: dcp or dgp
        """
        return True

    def atoms(self) -> list[Atom]:
        return []

    @property
    def bounds(self):
        return self._bounds

    @bounds.setter
    def bounds(self, value):
        # In case for a constant or no bounds
        if value is None:
            self._bounds = None
            return

        # Check that bounds is a list of two items
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("Bounds should be a list of two items.")

        lower_bounds, upper_bounds = value

        # Check if lower and upper bounds are always passed together
        if (lower_bounds is None and upper_bounds is not None):
            raise ValueError("If upper bounds are passed, lower bounds should also be passed.")
        if (lower_bounds is not None and upper_bounds is None):
            raise ValueError("If lower bounds are passed, upper bounds should also be passed.")

        # Check that bounds contains two scalars or two arrays with matching shapes.
        is_lower_scalar = np.isscalar(lower_bounds)
        is_upper_scalar = np.isscalar(upper_bounds)
        is_lower_array = isinstance(lower_bounds, np.ndarray)
        is_upper_array = isinstance(upper_bounds, np.ndarray)
        if not((is_lower_scalar and is_upper_scalar) or
               (is_lower_scalar and is_upper_array
                and upper_bounds.shape == self.shape) or
               (is_upper_scalar and is_lower_array
                and lower_bounds.shape == self.shape) or
               (is_lower_array and is_upper_array
                and lower_bounds.shape == self.shape
                and upper_bounds.shape == self.shape)):
            raise ValueError("Bounds should contain scalars and/or arrays with the same dimensions")

        # Check that upper_bound >= lower_bound
        if np.any(upper_bounds < lower_bounds):
            raise ValueError("Invalid bounds: some upper bounds are less "
                             "than corresponding lower bounds.")

        if is_lower_scalar and is_upper_scalar:
            if (lower_bounds == -np.inf
                    and upper_bounds == -np.inf):
                raise ValueError("-np.inf is not feasible as lower "
                                 "and upper bound.")
            if (lower_bounds == np.inf
                    and upper_bounds == np.inf):
                raise ValueError("np.inf is not feasible as lower "
                                 "and upper bound.")
            if (np.isnan(lower_bounds) == np.nan
                    or np.isnan(upper_bounds) == np.nan):
                raise ValueError("np.nan is not feasible as lower "
                                 "or upper bound.")

        if is_lower_scalar:
            # Convert scalar lower bounds to array for -inf and inf conflict mask
            lower_bounds = np.full(self.shape, lower_bounds)
            if np.any(np.isnan(lower_bounds)) == np.nan or np.any(np.isnan(upper_bounds)):
                raise ValueError("np.nan is not feasible as lower "
                                 "or upper bound.")

        if is_upper_scalar:
            # Convert scalar upper bounds to array for -inf and inf conflict mask
            upper_bounds = np.full(self.shape, upper_bounds)
            if np.any(np.isnan(upper_bounds)) == np.nan or np.any(np.isnan(lower_bounds)):
                raise ValueError("np.nan is not feasible as lower "
                                 "or upper bound.")

        if is_lower_array and is_upper_array:
            if np.any(np.isnan(lower_bounds)) or np.any(np.isnan(upper_bounds)):
                raise ValueError("np.nan is not feasible as lower "
                                 "or upper bound.")

        # Element-wise check for -np.inf and np.inf at the same positions
        negative_inf_conflict_mask = (lower_bounds == -np.inf) & (upper_bounds == -np.inf)
        positive_inf_conflict_mask = (lower_bounds == np.inf) & (upper_bounds == np.inf)

        if np.any(negative_inf_conflict_mask):
            raise ValueError("-np.inf is not feasible as lower and upper bound.")
        if np.any(positive_inf_conflict_mask):
            raise ValueError("np.inf is not feasible as lower and upper bound.")

        self._bounds = [lower_bounds, upper_bounds]
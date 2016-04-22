"""
Copyright 2013 Steven Diamond

This file is part of CVXPY.

CVXPY is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

CVXPY is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with CVXPY.  If not, see <http://www.gnu.org/licenses/>.
"""

import sys
import cvxpy.lin_ops.lin_utils as lu
from cvxpy.atoms.elementwise.elementwise import Elementwise
import numpy as np
if sys.version_info >= (3, 0):
    from functools import reduce

class max_elemwise(Elementwise):
    """ Elementwise maximum. """

    def __init__(self, arg1, arg2, *args):
        """Requires at least 2 arguments.
        """
        super(max_elemwise, self).__init__(arg1, arg2, *args)

    @Elementwise.numpy_numeric
    def numeric(self, values):
        """Returns the elementwise maximum.
        """
        return reduce(np.maximum, values)

    def sign_from_args(self):
        """Returns sign (is positive, is negative) of the expression.
        """
        # Reduces the list of argument signs according to the following rules:
        #     POSITIVE, ANYTHING = POSITIVE
        #     ZERO, UNKNOWN = POSITIVE
        #     ZERO, ZERO = ZERO
        #     ZERO, NEGATIVE = ZERO
        #     UNKNOWN, NEGATIVE = UNKNOWN
        #     NEGATIVE, NEGATIVE = NEGATIVE
        is_pos = any([arg.is_positive() for arg in self.args])
        is_neg = all([arg.is_negative() for arg in self.args])
        return (is_pos, is_neg)

    def is_atom_convex(self):
        """Is the atom convex?
        """
        return True

    def is_atom_concave(self):
        """Is the atom concave?
        """
        return False

    def is_incr(self, idx):
        """Is the composition non-decreasing in argument idx?
        """
        return True

    def is_decr(self, idx):
        """Is the composition non-increasing in argument idx?
        """
        return False

    @staticmethod
    def graph_implementation(arg_objs, size, data=None):
        """Reduces the atom to an affine expression and list of constraints.

        Parameters
        ----------
        arg_objs : list
            LinExpr for each argument.
        size : tuple
            The size of the resulting expression.
        data :
            Additional data required by the atom.

        Returns
        -------
        tuple
            (LinOp for objective, list of constraints)
        """
        t = lu.create_var(size)
        constraints = []
        for obj in arg_objs:
            obj = Elementwise._promote(obj, size)
            constraints.append(lu.create_leq(obj, t))
        return (t, constraints)

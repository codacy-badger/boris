#  SPDX-License-Identifier: GPL-3.0+
#
# Copyright © 2020 O. Papst.
#
# This file is part of boris.
#
# boris is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# boris is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with boris.  If not, see <http://www.gnu.org/licenses/>.

"""boris – bayesian deconvolution of nuclear spectra"""

from typing import Union
from pathlib import Path

import numpy as np
import pymc3 as pm
import uproot

def rebin_hist(
        hist: np.array,
        bin_width: int,
        left: int = 0,
        right: int = None):
    """
    Rebin hist with dimension $N^M$. The binning is reduced by a factor
    of bin_width, i.e. neighboring bins are summed. Bin edges are assumed
    to be at [0, 1, 2, …].
    
    Args:
        hist: Input matrix of type $N^M$ (N bins, M dimensions)
        bin_width: rebinning factor
        left: lower edge of first bin of resulting matrix
        right: maximum upper edge of last bin of resulting matrix
    Returns:
        rebinned matrix, resulting bin edges
    """
    left = left or 0
    right = right or hist.shape[0] + 1
    num_dim = hist.ndim
    num_bins = (right - left)//bin_width
    upper = left + num_bins * bin_width

    if not (np.array(hist.shape)[1:] == np.array(hist.shape)[:-1]).all():
        raise ValueError("Input histogram has to be square.")
    
    res = (
        hist[(slice(left,upper),)*num_dim]
        .reshape(*[num_bins, bin_width]*num_dim)
        .sum(axis=(num_dim * 2 - 1))
    )
    for i in range(1, num_dim):
        res = res.sum(axis=i)
    bin_edges = np.linspace(left, upper, num_bins+1)
    return res, bin_edges

def get_rema(
        path: Union[str, Path],
        bin_width: int,
        left: int,
        right: int):
    """
    Obtain the response matrix from the root file at path.
    root file has to contain "rema" and "n_simulated_particles" (TH1).
    The response matrix is cropped to left and right and rebinned to
    bin_width.
    
    Args:
        path: path of root file
        bin_width: rebin matrix to this width
        left: lower boundary of cropped matrix
        right: maximum upper boundary of cropped matrix.

    Returns:
        response matrix
        number of simulated particles
        bin_edges
    """
    with uproot.open(path) as response_file:
        response = response_file["rema"]
        nsim = response_file["n_simulated_particles"]
    rema, rema_bin_edges = response.numpy()
    rema_nsim = nsim.numpy()[0]
    rema_re = rebin_hist(rema, bin_width, left, right)
    rema_nsim_re = rebin_hist(rema_nsim, bin_width, left, right)
    return rema_re[0], *rema_nsim_re

def deconvolute(rema, spectrum, ndraws=10000, tune=500, thin=1, burn=1000, cores=1):
    start_incident = np.clip(spectrum @ np.linalg.inv(rema), 1, np.inf)
    with pm.Model() as model:
        incident = pm.Exponential(
            "incident",
            1/np.mean(start_incident),
            shape=spectrum.shape[0])
        folded = incident @ rema
        observation = pm.Poisson("spectrum", folded, observed=spectrum)

        step = pm.NUTS()
        trace = pm.sample(
            ndraws,
            step=step,
            start={"incident": start_incident},
            cores=cores
        )
    return trace[burn::thin]
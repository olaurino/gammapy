# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""Make example datasets.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import os
import shutil
import numpy as np
from astropy.units import Quantity
from astropy.time import Time, TimeDelta
from astropy.coordinates import SkyCoord, AltAz, FK5, Angle
from astropy.table import Table
from ..irf import EnergyDependentMultiGaussPSF
from ..obs import ObservationTable, observatory_locations, DataStore
from ..utils.random import sample_sphere, get_random_state
from ..time import time_ref_from_dict, time_relative_to_ref
from ..background import Cube
from ..data import EventList
from ..utils.fits import table_to_fits_table

__all__ = ['make_test_psf',
           'make_test_observation_table',
           'make_test_bg_cube_model',
           'make_test_dataset',
           'make_test_eventlist',
           ]


def make_test_psf(energy_bins=15, theta_bins=12):
    """Create a test FITS PSF file.

    A log-linear dependency in energy is assumed, where the size of
    the PSF decreases by a factor of tow over tow decades. The
    theta dependency is a parabola where at theta = 2 deg the size
    of the PSF has increased by 30%.

    Parameters
    ----------
    energy_bins : int
        Number of energy bins.
    theta_bins : int
        Number of theta bins.

    Returns
    -------
    psf : `~gammapy.irf.EnergyDependentMultiGaussPSF`
        PSF.
    """
    energies_all = np.logspace(-1, 2, energy_bins + 1)
    energies_lo = energies_all[:-1]
    energies_hi = energies_all[1:]
    theta_lo = theta_hi = np.linspace(0, 2.2, theta_bins)
    azimuth_lo = azimuth_hi = 0
    zenith_lo = zenith_hi = 0

    def sigma_energy_theta(energy, theta, sigma):
        # log-linear dependency of sigma with energy
        # m and b are choosen such, that at 100 TeV
        # we have sigma and at 0.1 TeV we have sigma/2
        m = -sigma / 6.
        b = sigma + m
        return (2 * b + m * np.log10(energy)) * (0.3 / 4 * theta ** 2 + 1)

    # Compute norms and sigmas values are taken from the psf.txt in
    # irf/test/data
    energies, thetas = np.meshgrid(energies_lo, theta_lo)

    sigmas = []
    for sigma in [0.0219206, 0.0905762, 0.0426358]:
        sigmas.append(sigma_energy_theta(energies, thetas, sigma))

    norms = []
    for norm in 302.654 * np.array([1, 0.0406003, 0.444632]):
        norms.append(norm * np.ones((theta_bins, energy_bins)))

    psf = EnergyDependentMultiGaussPSF(Quantity(energies_lo, 'TeV'),
                                       Quantity(energies_hi, 'TeV'),
                                       Quantity(theta_lo, 'deg'),
                                       sigmas, norms, azimuth=azimuth_hi,
                                       zenith=zenith_hi)

    return psf


def make_test_observation_table(observatory_name='HESS', n_obs=10,
                                datestart=None, dateend=None,
                                use_abs_time=False,
                                random_state='random-seed'):
    """Make a test observation table.

    For the moment, only random observation tables are created.
    If `datestart` and `dateend` are specified, the starting time
    of the observations will be restricted to the specified interval.
    These parameters are interpreted as date, the precise hour of the
    day is ignored, unless the end date is closer than 1 day to the
    starting date, in which case, the precise time of the day is also
    considered.

    Parameters
    ----------
    observatory_name : str
        Name of the observatory; a list of choices is given in
        `~gammapy.obs.observatory_locations`.
    n_obs : int
        Number of observations for the obs table.
    datestart : `~astropy.time.Time`, optional
        Starting date for random generation of observation start time.
    dateend : `~astropy.time.Time`, optional
        Ending date for random generation of observation start time.
    use_abs_time : bool, optional
        Use absolute UTC times instead of [MET]_ seconds after the reference.
    random_state : {int, 'random-seed', 'global-rng', `~numpy.random.RandomState`}, optional
        Defines random number generator initialisation.
        Passed to `~gammapy.utils.random.get_random_state`.

    Returns
    -------
    obs_table : `~gammapy.obs.ObservationTable`
        Observation table.
    """
    random_state = get_random_state(random_state)

    n_obs_start = 1

    obs_table = ObservationTable()

    # build a time reference as the start of 2010
    dateref = Time('2010-01-01T00:00:00', format='isot', scale='utc')
    dateref_mjd_fra, dateref_mjd_int = np.modf(dateref.mjd)

    # define table header
    obs_table.meta['OBSERVATORY_NAME'] = observatory_name
    obs_table.meta['MJDREFI'] = dateref_mjd_int
    obs_table.meta['MJDREFF'] = dateref_mjd_fra
    if use_abs_time:
        # show the observation times in UTC
        obs_table.meta['TIME_FORMAT'] = 'absolute'
    else:
        # show the observation times in seconds after the reference
        obs_table.meta['TIME_FORMAT'] = 'relative'
    header = obs_table.meta

    # obs id
    obs_id = np.arange(n_obs_start, n_obs_start + n_obs)
    obs_table['OBS_ID'] = obs_id

    # obs time: 30 min
    time_observation = Quantity(30. * np.ones_like(obs_id), 'minute').to('second')
    obs_table['TIME_OBSERVATION'] = time_observation

    # livetime: 25 min
    time_live = Quantity(25. * np.ones_like(obs_id), 'minute').to('second')
    obs_table['TIME_LIVE'] = time_live

    # start time
    #  - random points between the start of 2010 and the end of 2014 (unless
    # otherwise specified)
    #  - using the start of 2010 as a reference time for the header of the table
    #  - observations restrict to night time (only if specified time interval is
    # more than 1 day)
    #  - considering start of astronomical day at midday: implicit in setting
    # the start of the night, when generating random night hours
    if datestart == None:
        datestart = Time('2010-01-01T00:00:00', format='isot', scale='utc')
    if dateend == None:
        dateend = Time('2015-01-01T00:00:00', format='isot', scale='utc')
    time_start = random_state.uniform(datestart.mjd, dateend.mjd, len(obs_id))
    time_start = Time(time_start, format='mjd', scale='utc')

    # check if time interval selected is more than 1 day
    if (dateend - datestart).jd > 1.:
        # keep only the integer part (i.e. the day, not the fraction of the day)
        time_start_f, time_start_i = np.modf(time_start.mjd)
        time_start = Time(time_start_i, format='mjd', scale='utc')

        # random generation of night hours: 6 h (from 22 h to 4 h), leaving 1/2 h
        # time for the last run to finish
        night_start = Quantity(22., 'hour')
        night_duration = Quantity(5.5, 'hour')
        hour_start = random_state.uniform(night_start.value,
                                 night_start.value + night_duration.value,
                                 len(obs_id))
        hour_start = Quantity(hour_start, 'hour')

        # add night hour to integer part of MJD
        time_start += hour_start

    if use_abs_time:
        # show the observation times in UTC
        time_start = Time(time_start.isot)
    else:
        # show the observation times in seconds after the reference
        time_start = time_relative_to_ref(time_start, header)
        # converting to quantity (better treatment of units)
        time_start = Quantity(time_start.sec, 'second')

    obs_table['TIME_START'] = time_start

    # stop time
    # calculated as TIME_START + TIME_OBSERVATION
    if use_abs_time:
        time_stop = Time(obs_table['TIME_START'])
        time_stop += TimeDelta(obs_table['TIME_OBSERVATION'])
    else:
        time_stop = TimeDelta(obs_table['TIME_START'])
        time_stop += TimeDelta(obs_table['TIME_OBSERVATION'])
        # converting to quantity (better treatment of units)
        time_stop = Quantity(time_stop.sec, 'second')

    obs_table['TIME_STOP'] = time_stop

    # az, alt
    # random points in a sphere above 45 deg altitude
    az, alt = sample_sphere(size=len(obs_id),
                            lon_range=Angle([0, 360], 'degree'),
                            lat_range=Angle([45, 90], 'degree'),
                            random_state=random_state)
    az = Angle(az, 'degree')
    alt = Angle(alt, 'degree')
    obs_table['AZ'] = az
    obs_table['ALT'] = alt

    # RA, dec
    # derive from az, alt taking into account that alt, az represent the values
    # at the middle of the observation, i.e. at time_ref + (TIME_START + TIME_STOP)/2
    # (or better: time_ref + TIME_START + (TIME_OBSERVATION/2))
    # in use_abs_time mode, the time_ref should not be added, since it's already included
    # in TIME_START and TIME_STOP
    az = Angle(obs_table['AZ'])
    alt = Angle(obs_table['ALT'])
    if use_abs_time:
        obstime = Time(obs_table['TIME_START'])
        obstime += TimeDelta(obs_table['TIME_OBSERVATION']) / 2.
    else:
        obstime = time_ref_from_dict(obs_table.meta)
        obstime += TimeDelta(obs_table['TIME_START'])
        obstime += TimeDelta(obs_table['TIME_OBSERVATION']) / 2.
    location = observatory_locations[observatory_name]
    alt_az_coord = AltAz(az=az, alt=alt, obstime=obstime, location=location)
    sky_coord = alt_az_coord.transform_to(FK5)
    obs_table['RA'] = sky_coord.ra
    obs_table['DEC'] = sky_coord.dec

    # positions

    # number of telescopes
    # random integers between 3 and 4
    n_tels_min = 3
    n_tels_max = 4
    n_tels = random_state.randint(n_tels_min, n_tels_max + 1, len(obs_id))
    obs_table['N_TELS'] = n_tels

    # muon efficiency
    # random between 0.6 and 1.0
    muon_efficiency = random_state.uniform(low=0.6, high=1.0, size=len(obs_id))
    obs_table['MUON_EFFICIENCY'] = muon_efficiency

    return obs_table


def make_test_bg_cube_model(detx_range=Angle([-10., 10.], 'degree'),
                            ndetx_bins=24,
                            dety_range=Angle([-10., 10.], 'degree'),
                            ndety_bins=24,
                            energy_band=Quantity([0.01, 100.], 'TeV'),
                            nenergy_bins=14,
                            altitude=Angle(70., 'degree'),
                            sigma=Angle(5., 'deg'),
                            spectral_index=2.7,
                            apply_mask=False):
    """Make a test bg cube model.

    The background is created following a 2D symmetric gaussian
    model for the spatial coordinates (X, Y) and a power-law in
    energy.
    The gaussian width varies in energy from sigma/2 to sigma.
    The power-law slope in log-log representation is given by
    the spectral_index parameter.
    The norm depends linearly on the livetime
    and on the altitude angle of the observation.
    It is possible to mask 1/4th of the image (for `x > x_center` and
    `y > y_center`). Useful for testing coordinate rotations.

    This method is useful for instance to produce true (simulated)
    background cube models to compare to the reconstructed ones
    produced with `~gammapy.background.make_bg_cube_model.`

    Parameters
    ----------
    detx_range : `~astropy.coordinates.Angle`, optional
        X coordinate range (min, max).
    ndetx_bins : int, optional
        Number of (linear) bins in X coordinate.
    dety_range : `~astropy.coordinates.Angle`, optional
        Y coordinate range (min, max).
    ndety_bins : int, optional
        Number of (linear) bins in Y coordinate.
    energy_band : `~astropy.units.Quantity`, optional
        Energy range (min, max).
    nenergy_bins : int, optional
        Number of (logarithmic) bins in energy.
    altitude : `~astropy.coordinates.Angle`, optional
        observation altitude angle for the model.
    sigma : `~astropy.coordinates.Angle`, optional
        Width of the gaussian model used for the spatial coordinates.
    spectral_index : double, optional
        Index for the power-law model used for the energy coordinate.
    apply_mask : bool, optional
        If set, 1/4th of the image is masked (for `x > x_center` and
        `y > y_center`).

    Returns
    -------
    bg_cube_model : `~gammapy.background.Cube`
        Bacground cube model.
    """
    # spatial bins (linear)
    delta_x = (detx_range[1] - detx_range[0])/ndetx_bins
    detx_bin_edges = np.arange(ndetx_bins + 1)*delta_x + detx_range[0]

    delta_y = (dety_range[1] - dety_range[0])/ndety_bins
    dety_bin_edges = np.arange(ndety_bins + 1)*delta_y + dety_range[0]

    # energy bins (logarithmic)
    log_delta_energy = (np.log(energy_band[1].value)
                        - np.log(energy_band[0].value))/nenergy_bins
    energy_bin_edges = np.exp(np.arange(nenergy_bins + 1)*log_delta_energy
                              + np.log(energy_band[0].value))
    energy_bin_edges = Quantity(energy_bin_edges, energy_band[0].unit)
    # TODO: this function should be reviewed/re-written, when
    # the following PR is completed:
    # https://github.com/gammapy/gammapy/pull/290

    # define empty bg cube model and set bins
    bg_cube_model = Cube(coordx_edges=detx_bin_edges,
                         coordy_edges=dety_bin_edges,
                         energy_edges=energy_bin_edges,
                         data=None, scheme='bg_cube')

    # background

    # define coordinate grids for the calculations
    det_bin_centers = bg_cube_model.image_bin_centers
    energy_bin_centers = bg_cube_model.energy_bin_centers
    energy_points, dety_points, detx_points = np.meshgrid(energy_bin_centers,
                                                          det_bin_centers[1],
                                                          det_bin_centers[0],
                                                          indexing='ij')

    E_0 = Quantity(1., 'TeV') # reference energy for the model

    # norm of the model
    # taking as reference
    # for now a dummy value of 1 in units of '1 / (s TeV sr)
    # it is linearly dependent on the zenith angle (90 deg - altitude)
    # it is norm_max at alt = 90 deg and norm_max/2 at alt = 0 deg
    norm_max = Quantity(1., '1 / (s TeV sr)')
    alt_min = Angle(0., 'degree')
    alt_max = Angle(90., 'degree')
    slope = (norm_max - norm_max/2)/(alt_max - alt_min)
    free_term = norm_max/2 - slope*alt_min
    norm = altitude*slope + free_term

    # define E dependent sigma
    # it is defined via a PL, in order to be log-linear
    # it is equal to the parameter sigma at E max
    # and sigma/2. at E min
    sigma_min = sigma/2. # at E min
    sigma_max = sigma # at E max
    s_index = np.log(sigma_max/sigma_min)
    s_index /= np.log(energy_bin_edges[-1]/energy_bin_edges[0])
    s_norm = sigma_min*((energy_bin_edges[0]/E_0)**-s_index)
    sigma = s_norm*((energy_points/E_0)**s_index)

    # calculate bg
    gaussian = np.exp(-((detx_points)**2 + (dety_points)**2)/sigma**2)
    powerlaw = (energy_points/E_0)**-spectral_index
    background = norm*gaussian*powerlaw

    # apply mask if requested
    if apply_mask:
        # find central coordinate
        detx_center = (detx_range[1] + detx_range[0])/2.
        dety_center = (dety_range[1] + dety_range[0])/2.
        mask = (detx_points <= detx_center) & (dety_points <= dety_center)
        background = background*mask

    bg_cube_model.data = Quantity(background, '1 / (s TeV sr)')

    return bg_cube_model


def make_test_dataset(fits_path, overwrite=False,
                      observatory_name='HESS', n_obs=10,
                      datestart=None, dateend=None,
                      random_state='random-seed'):
    """
    Make a test dataset and save it to disk.

    Uses:

    * `~gammapy.datasets.make_test_observation_table` to generate an
      observation table

    * `~gammapy.datasets.make_test_eventlist` to generate an event list
      and effective area table for each observation

    * `~gammapy.obs.DataStore` to handle the file naming scheme;
      currently only the H.E.S.S. naming scheme is supported

    This method is useful for instance to produce samples in order
    to test the machinery for reconstructing background (cube) models.

    See also :ref:`datasets_make_datasets_for_testing`.

    Parameters
    ----------
    fits_path : str
        Path to store the files.
    overwrite : bool, optional
        Flag to remove previous datasets in fits_path (if existing).
    observatory_name : str, optional
        Name of the observatory; a list of choices is given in
        `~gammapy.obs.observatory_locations`.
    n_obs : int
        Number of observations for the obs table.
    datestart : `~astropy.time.Time`, optional
        Starting date for random generation of observation start time.
    dateend : `~astropy.time.Time`, optional
        Ending date for random generation of observation start time.
    random_state : {int, 'random-seed', 'global-rng', `~numpy.random.RandomState`}, optional
        Defines random number generator initialisation.
        Passed to `~gammapy.utils.random.get_random_state`.
    """
    random_state = get_random_state(random_state)

    # create output folder
    outdir = fits_path
    if not os.path.isdir(outdir):
        os.mkdir(outdir)
    else:
        if overwrite:
            # delete and create again
            shutil.rmtree(outdir) # recursively
            os.mkdir(outdir)
        else:
            # do not overwrite, hence exit
            s_error = "Cannot continue: directory \'{}\' exists.".format(outdir)
            raise RuntimeError(s_error)

    # generate observation table
    observation_table = make_test_observation_table(observatory_name=observatory_name,
                                                    n_obs=n_obs,
                                                    datestart=datestart, dateend=dateend,
                                                    use_abs_time=False,
                                                    random_state=random_state)

    # save observation list to disk
    outfile = outdir + '/runinfo.fits'
    observation_table.write(outfile)

    # create data store for the organization of the files
    # using H.E.S.S.-like dir/file naming scheme
    if observatory_name == 'HESS':
        scheme = 'HESS'
    else:
        s_error = "Warning! Storage scheme for {}".format(observatory_name)
        s_error += "not implemented. Only H.E.S.S. scheme is available."
        raise ValueError(s_error)

    data_store = DataStore(dir=fits_path, scheme=scheme)

    # loop over observations
    for obs_id in observation_table['OBS_ID']:
        event_list, aeff_hdu = make_test_eventlist(observation_table=observation_table,
                                                   obs_id=obs_id,
                                                   random_state=random_state)

        # save event list and effective area table to disk
        outfile = data_store.filename(obs_id, filetype='events')
        outfile_split = outfile.rsplit("/", 1)
        os.makedirs(outfile_split[0]) # recursively
        event_list.write(outfile)
        outfile = data_store.filename(obs_id, filetype='effective area')
        aeff_hdu.writeto(outfile)


def make_test_eventlist(observation_table,
                        obs_id,
                        sigma=Angle(5., 'deg'),
                        spectral_index=2.7,
                        random_state='random-seed'):
    """
    Make a test event list for a specified observation.

    The observation can be specified with an observation table object
    and the observation ID pointing to the correct observation in the
    table.

    For now, only a very rudimentary event list is generated, containing
    only detector X, Y coordinates (a.k.a. nominal system) and energy
    columns for the events. And the livetime of the observations stored
    in the header.

    The model used to simulate events is also very simple. Only
    dummy background is created (no signal).
    The background is created following a 2D symmetric gaussian
    model for the spatial coordinates (X, Y) and a power-law in
    energy.
    The gaussian width varies in energy from sigma/2 to sigma.
    The number of events generated depends linearly on the livetime
    and on the altitude angle of the observation.
    The model can be tuned via the sigma and spectral_index parameters.

    In addition, an effective area table is produced. For the moment
    only the low energy threshold is filled.

    See also :ref:`datasets_make_datasets_for_testing`.

    Parameters
    ----------
    observation_table : `~gammapy.obs.ObservationTable`
        Observation table containing the observation to fake.
    obs_id : int
        Observation ID of the observation to fake inside the observation table.
    sigma : `~astropy.coordinates.Angle`, optional
        Width of the gaussian model used for the spatial coordinates.
    spectral_index : double, optional
        Index for the power-law model used for the energy coordinate.
    random_state : {int, 'random-seed', 'global-rng', `~numpy.random.RandomState`}, optional
        Defines random number generator initialisation.
        Passed to `~gammapy.utils.random.get_random_state`.

    Returns
    -------
    event_list : `~gammapy.data.EventList`
        Event list.
    aeff_hdu : `~astropy.io.fits.BinTableHDU`
        Effective area table.
    """
    random_state = get_random_state(random_state)

    # find obs row in obs table
    obs_ids = observation_table['OBS_ID'].data
    obs_index = np.where(obs_ids == obs_id)
    row = obs_index[0][0]

    # get observation information
    alt = Angle(observation_table['ALT'])[row]
    livetime = Quantity(observation_table['TIME_LIVE'])[row]

    # number of events to simulate
    # it is linearly dependent on the livetime, taking as reference
    # a trigger rate of 300 Hz
    # it is linearly dependent on the zenith angle (90 deg - altitude)
    # it is n_events_max at alt = 90 deg and n_events_max/2 at alt = 0 deg
    n_events_max = Quantity(300., 'Hz')*livetime
    alt_min = Angle(0., 'degree')
    alt_max = Angle(90., 'degree')
    slope = (n_events_max - n_events_max/2)/(alt_max - alt_min)
    free_term = n_events_max/2 - slope*alt_min
    n_events = alt*slope + free_term

    # simulate energy
    # the index of `~numpy.random.RandomState.power` has to be
    # positive defined, so it is necessary to translate the (0, 1)
    # interval of the random variable to (emax, e_min) in order to
    # have a decreasing power-law
    index = spectral_index + 1
    e_min = Quantity(0.1, 'TeV')
    e_max = Quantity(100., 'TeV')
    energy = Quantity((e_min.value - e_max.value) *
                      random_state.power(a=index, size=n_events) + e_max.value, 'TeV')

    E_0 = Quantity(1., 'TeV') # reference energy for the model

    # define E dependent sigma
    # it is defined via a PL, in order to be log-linear
    # it is equal to the parameter sigma at E max
    # and sigma/2. at E min
    sigma_min = sigma/2. # at E min
    sigma_max = sigma # at E max
    s_index = np.log(sigma_max/sigma_min)
    s_index /= np.log(e_max/e_min)
    s_norm = sigma_min*((e_min/E_0)**-s_index)
    sigma = s_norm*((energy/E_0)**s_index)

    # simulate detx, dety
    detx = Angle(random_state.normal(loc=0, scale=sigma.deg, size=n_events),
                 'degree')
    dety = Angle(random_state.normal(loc=0, scale=sigma.deg, size=n_events),
                 'degree')

    # fill events in an event list
    event_list = EventList()
    event_list['DETX'] = detx
    event_list['DETY'] = dety
    event_list['ENERGY'] = energy

    # store important info in header
    event_list.meta['LIVETIME'] = livetime.to('second').value
    event_list.meta['EUNIT'] = str(energy.unit)

    # effective area table
    aeff_table = Table()

    # fill threshold, for now, a default 100 GeV will be set
    # independently of observation parameters
    energy_threshold = Quantity(0.1, 'TeV')
    aeff_table.meta['LO_THRES'] = energy_threshold.value
    aeff_table.meta['name'] = 'EFFECTIVE AREA'

    # convert to BinTableHDU and add necessary comment for the units
    aeff_hdu = table_to_fits_table(aeff_table)
    aeff_hdu.header.comments['LO_THRES'] = '[' + str(energy_threshold.unit) + ']'

    return event_list, aeff_hdu

# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""Catalog utility functions / classes."""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import numpy as np
from astropy.coordinates import Angle, SkyCoord


__all__ = ['coordinate_iau_format',
           'ra_iau_format',
           'dec_iau_format',
           'skycoord_from_table',
           'select_sky_box',
           'select_sky_circle',
           'to_ds9_region',
           'get_source_by_name'
           ]


def coordinate_iau_format(coordinate, ra_digits, dec_digits=None,
                          prefix=''):
    """Coordinate format as an IAU source designation.

    Reference: http://cdsweb.u-strasbg.fr/Dic/iau-spec.html

    Parameters
    ----------
    coordinate : `~astropy.coordinates.SkyCoord`
        Source coordinate.
    ra_digits : int (>=2)
        Number of digits for the Right Ascension part.
    dec_digits : int (>=2) or None
        Number of digits for the declination part
        Default is ``dec_digits`` = None, meaning ``dec_digits`` = ``ra_digits`` - 1.
    prefix : str
        Prefix to put before the coordinate string, e.g. "SDSS J".

    Returns
    -------
    strrepr : str or list of strings
        IAU format string representation of the coordinate.
        If this input coordinate is an array, the output is a list of strings.

    Examples
    --------
    >>> from astropy.coordinates import SkyCoord
    >>> from gammapy.catalog import coordinate_iau_format

    Example position from IAU specification

    >>> coordinate = SkyCoord('00h51m09.38s -42d26m33.8s', frame='icrs')
    >>> designation = 'QSO J' + coordinate_iau_format(coordinate, ra_digits=6)
    >>> print(designation)
    QSO J005109-4226.5
    >>> coordinate = coordinate.transform_to('fk4')
    >>> designation = 'QSO B' + coordinate_iau_format(coordinate, ra_digits=6)
    >>> print(designation)
    QSO B004848-4242.8

    Crab pulsar position (positive declination)

    >>> coordinate = SkyCoord('05h34m31.93830s +22d00m52.1758s', frame='icrs')
    >>> designation = 'HESS J' + coordinate_iau_format(coordinate, ra_digits=4)
    >>> print(designation)
    HESS J0534+220

    PKS 2155-304 AGN position (negative declination)

    >>> coordinate = SkyCoord('21h58m52.06511s -30d13m32.1182s', frame='icrs')
    >>> designation = '2FGL J' + coordinate_iau_format(coordinate, ra_digits=5)
    >>> print(designation)
    2FGL J2158.8-3013

    Coordinate array inputs result in list of string output.

    >>> coordinates = SkyCoord(ra=[10.68458, 83.82208],
    ...                        dec=[41.26917, -5.39111],
    ...                        unit=('deg', 'deg'), frame='icrs')
    >>> designations = coordinate_iau_format(coordinates, ra_digits=5, prefix='HESS J')
    >>> print(designations)
    ['HESS J0042.7+4116', 'HESS J0535.2-0523']
    """
    if coordinate.frame.name == 'galactic':
        coordinate = coordinate.transform_to('icrs')

    if dec_digits is None:
        dec_digits = max(2, ra_digits - 1)

    ra_str = ra_iau_format(coordinate.ra, ra_digits)
    dec_str = dec_iau_format(coordinate.dec, dec_digits)

    if coordinate.isscalar:
        out = prefix + ra_str + dec_str
    else:
        out = [prefix + r + d for (r, d) in zip(ra_str, dec_str)]

    return out


def ra_iau_format(ra, digits):
    """Right Ascension part of an IAU source designation.

    Reference: http://cdsweb.u-strasbg.fr/Dic/iau-spec.html

    ====== ========
    digits format
    ====== ========
    2      HH
    3      HHh
    4      HHMM
    5      HHMM.m
    6      HHMMSS
    7      HHMMSS.s
    ====== ========

    Parameters
    ----------
    ra : `~astropy.coordinates.Longitude`
        Right ascension.
    digits : int (>=2)
        Number of digits.

    Returns
    -------
    strrepr : str
        IAU format string representation of the angle.
    """
    if (not isinstance(digits, int)) and (digits >= 2):
        raise ValueError('Invalid digits: {0}. Valid options: int >= 2'.format(digits))

    if ra.isscalar:
        out = _ra_iau_format_scalar(ra, digits)
    else:
        out = [_ra_iau_format_scalar(_, digits) for _ in ra]

    return out


def _ra_iau_format_scalar(ra, digits):
    """Format a single Right Ascension."""
    # Note that Python string formatting always rounds the last digit,
    # but the IAU spec requires to truncate instead.
    # That's why integers with the correct digits are computed and formatted
    # instead of formatting floats directly
    ra_h = int(ra.hms[0])
    ra_m = int(ra.hms[1])
    ra_s = ra.hms[2]

    if digits == 2:  # format: HH
        ra_str = '{0:02d}'.format(ra_h)
    elif digits == 3:  # format: HHh
        ra_str = '{0:03d}'.format(int(10 * ra.hour))
    elif digits == 4:  # format: HHMM
        ra_str = '{0:02d}{1:02d}'.format(ra_h, ra_m)
    elif digits == 5:  # format : HHMM.m
        ra_str = '{0:02d}{1:02d}.{2:01d}'.format(ra_h, ra_m, int(ra_s / 6))
    elif digits == 6:  # format: HHMMSS
        ra_str = '{0:02d}{1:02d}{2:02d}'.format(ra_h, ra_m, int(ra_s))
    else:  # format: HHMMSS.s
        SS = int(ra_s)
        s_digits = digits - 6
        s = int(10 ** s_digits * (ra_s - SS))
        fmt = '{0:02d}{1:02d}{2:02d}.{3:0' + str(s_digits) + 'd}'
        ra_str = fmt.format(ra_h, ra_m, SS, s)

    return ra_str


def dec_iau_format(dec, digits):
    """Declination part of an IAU source designation.

    Reference: http://cdsweb.u-strasbg.fr/Dic/iau-spec.html

    ====== =========
    digits format
    ====== =========
    2      +DD
    3      +DDd
    4      +DDMM
    5      +DDMM.m
    6      +DDMMSS
    7      +DDMMSS.s
    ====== =========

    Parameters
    ----------
    dec : `~astropy.coordinates.Latitude`
        Declination.
    digits : int (>=2)
        Number of digits.

    Returns
    -------
    strrepr : str
        IAU format string representation of the angle.
    """
    if not isinstance(digits, int) and digits >= 2:
        raise ValueError('Invalid digits: {0}. Valid options: int >= 2'.format(digits))

    if dec.isscalar:
        out = _dec_iau_format_scalar(dec, digits)
    else:
        out = [_dec_iau_format_scalar(_, digits) for _ in dec]

    return out


def _dec_iau_format_scalar(dec, digits):
    """Format a single declination."""
    # Note that Python string formatting always rounds the last digit,
    # but the IAU spec requires to truncate instead.
    # That's why integers with the correct digits are computed and formatted
    # instead of formatting floats directly
    dec_sign = '+' if dec.deg >= 0 else '-'
    dec_d = int(abs(dec.dms[0]))
    dec_m = int(abs(dec.dms[1]))
    dec_s = abs(dec.dms[2])

    if digits == 2:  # format: +DD
        dec_str = '{0}{1:02d}'.format(dec_sign, dec_d)
    elif digits == 3:  # format: +DDd
        dec_str = '{0:+04d}'.format(int(10 * dec.deg))
    elif digits == 4:  # format : +DDMM
        dec_str = '{0}{1:02d}{2:02d}'.format(dec_sign, dec_d, dec_m)
    elif digits == 5:  # format: +DDMM.m
        dec_str = '{0}{1:02d}{2:02d}.{3:01d}'.format(dec_sign, dec_d, dec_m, int(dec_s / 6))
    elif digits == 6:  # format: +DDMMSS
        dec_str = '{0}{1:02d}{2:02d}.{3:02d}'.format(dec_sign, dec_d, dec_m, int(dec_s))
    else:  # format: +DDMMSS.s
        SS = int(dec_s)
        s_digits = digits - 6
        s = int(10 ** s_digits * (dec_s - SS))
        fmt = '{0}{1:02d}{2:02d}{3:02d}.{4:0' + str(s_digits) + 'd}'
        dec_str = fmt.format(dec_sign, dec_d, dec_m, SS, s)

    return dec_str


def skycoord_from_table(table):
    """Make `~astropy.coordinates.SkyCoord` from lon, lat columns in `~astropy.table.Table`.

    This is a convenience function similar to `~astropy.coordinates.SkyCoord.guess_from_table`,
    but with the column names we usually use.

    TODO: I'm not sure if it's a good idea to use this because it's not always clear
    which positions are taken.
    """

    if set(['RAJ2000', 'DEJ2000']).issubset(table.colnames):
        lon, lat, frame = 'RAJ2000', 'DEJ2000', 'icrs'
    elif set(['RA', 'DEC']).issubset(table.colnames):
        lon, lat, frame = 'RA', 'DEC', 'icrs'
    elif set(['GLON', 'GLAT']).issubset(table.colnames):
        lon, lat, frame = 'GLON', 'GLAT', 'galactic'
    else:
        raise KeyError('No column GLON / GLAT or RA / DEC or RAJ2000 / DEJ2000 found.')

    unit = table[lon].unit if table[lon].unit else 'deg'

    skycoord = SkyCoord(table[lon], table[lat], unit=unit, frame=frame)

    return skycoord


def select_sky_box(table, lon_lim, lat_lim, frame='icrs', inverted=False):
    """Select sky positions in a box.

    This function can be applied e.g. to event lists of source catalogs
    or observation tables.

    Note: if useful we can add a function that returns the mask
    or indices instead of applying the selection directly

    Parameters
    ----------
    table : `~astropy.table.Table`
        Table with sky coordinate columns.
    lon_lim, lat_lim : `~astropy.coordinates.Angle`
        Box limits (each should be a min, max tuple).
    frame : str, optional
        Frame in which to apply the box cut.
        Built-in Astropy coordinate frames are supported, e.g.
        'icrs', 'fk5' or 'galactic'.
    inverted : bool, optional
        Invert selection: keep all entries outside the selected region.

    Returns
    -------
    table : `~astropy.table.Table`
        Copy of input table with box cut applied.

    Examples
    --------
    >>> selected_obs_table = select_sky_box(obs_table,
    ...                                     lon_lim=Angle([150, 300], 'degree'),
    ...                                     lat_lim=Angle([-50, 0], 'degree'),
    ...                                     frame='icrs')
    """
    skycoord = skycoord_from_table(table)
    skycoord = skycoord.transform_to(frame)
    lon = skycoord.data.lon
    lat = skycoord.data.lat
    # SkyCoord automatically wraps lon angles at 360 deg, so in case
    # the lon range is wrapped at 180 deg, lon angles must be wrapped
    # also at 180 deg for the comparison to work
    if any(l < Angle(0., 'degree') for l in lon_lim):
        lon = lon.wrap_at(Angle(180, 'degree'))

    lon_mask = (lon_lim[0] <= lon) & (lon < lon_lim[1])
    lat_mask = (lat_lim[0] <= lat) & (lat < lat_lim[1])
    mask = lon_mask & lat_mask
    if inverted:
        mask = np.invert(mask)

    return table[mask]


def select_sky_circle(table, lon_cen, lat_cen, radius, frame='icrs', inverted=False):
    """Select sky positions in a circle.

    This function can be applied e.g. to event lists of source catalogs
    or observation tables.

    Note: if useful we can add a function that returns the mask
    or indices instead of applying the selection directly

    Parameters
    ----------
    table : `~astropy.table.Table`
        Table with sky coordinate columns.
    lon_cen, lat_cen : `~astropy.coordinates.Angle`
        Circle center.
    radius : `~astropy.coordinates.Angle`
        Circle radius.
    frame : str, optional
        Frame in which to apply the box cut.
        Built-in Astropy coordinate frames are supported, e.g.
        'icrs', 'fk5' or 'galactic'.
    inverted : bool, optional
        Invert selection: keep all entries outside the selected region.

    Returns
    -------
    table : `~astropy.table.Table`
        Copy of input table with circle cut applied.

    Examples
    --------
    >>> selected_obs_table = select_sky_circle(obs_table,
    ...                                        lon=Angle(0, 'degree'),
    ...                                        lat=Angle(0, 'degree'),
    ...                                        radius=Angle(5, 'degree'),
    ...                                        frame='galactic')
    """
    skycoord = skycoord_from_table(table)
    skycoord = skycoord.transform_to(frame)
    # no need to wrap lon angleshere, since the SkyCoord separation
    # method takes care of it
    center = SkyCoord(lon_cen, lat_cen, frame=frame)
    ang_distance = skycoord.separation(center)

    mask = ang_distance < radius
    if inverted:
        mask = np.invert(mask)

    return table[mask]


def get_source_by_name(source, catalog, id_column='Source_Name'):
    """
    Get source catalog entry by source name.

    Parameters
    ----------
    source : string
        Source name.
    catalog : `~astropy.table.Table`
        Catalog table.
    id_column : str (default = 'Source_Name')
        Column name of the source names.

    Returns
    -------
    source : `~astropy.table.Row`
        Entry for the given source.
    """
    index = np.where(catalog[id_column] == source)[0]
    if len(index) == 0:
        raise ValueError('Source {0} not found in catalog!'.format(source))
    else:
        return catalog[index[0]]


def to_ds9_region(catalog, radius=None, color='green', glon='GLON', unc_glon=None,
                  glat='GLAT', unc_glat=None, label=None, label_position='top',
                  label_additional_info=None, label_distance=1.2, marker='diamond',
                  dashed=False, width=3):
    """
    Write ds9 region file from catalog.

    Currently works only for galactic coordinates.


    Parameters
    ----------
    catalog : `~astropy.table.Table`
        Catalog with position and size information.
    glon : str ('GLON')
        Catalog column containing galactic longitude position.
    glat : str ('GLAT')
        Catalog column containing galactic latitude position.
    unc_glon : str (None)
        Catalog column containing galactic longitude position uncertainty.
    unc_glat : str (None)
        Catalog column containing galactic latitude position uncertainty.
    radius : str (None)
        Catalog column containing extension information.
    color : str ('green')
        Valid ds9 color.
    label : str (None)
        Catalog column to use for the label.
    label_position: str ('top')
        Position of the region label. Either 'top' or 'bottom'.
    label_distance: float (1.2)
        Distance of the label from the regions center. Given
        in multiple of the region's radius.
    label_additional_info: dict
        Additional info to be shown in the region label.
    dashed : bool (False)
        Dashed region line.
    width : int
        Width of the region line.

    Examples
    --------
    This example reads Greens catalog from `gammapy.datasets` and writes it to a
    ds9 region file.

    >>> from gammapy.datasets import load_catalog_green
    >>> green = load_catalog_green()
    >>> green['MeanDiam'] /= 120.
    >>> green_str = to_ds9_region(green, radius='MeanDiam',
    >>>                           label='Source_Name', color='red')
    >>> with open("region_green.reg", "w") as region_file:
    >>>     region_file.write(green_str)

    Returns
    -------
    region : str
        DS9 region string.
    """
    region_string = ''

    dash = '1' if dashed else '0'

    format_ = ' color = {color} width = {width} dash = {dash}\n'.format(**locals())
    if radius is not None:
        shape = 'galactic;circle({0:.5f},{1:.5f},{2:.5f}) #'
    else:
        shape = 'galactic;point({0:.5f},{1:.5f})' + ' # point = {0}'.format(marker)
    shape += format_

    text = 'galactic;text({0:5f},{1:5f}) # text = {{{2}}} '
    text += 'color = {0}\n'.format(color)

    for row in catalog:
        label_ = row[label] if label is not None else ''
        if label_additional_info is not None:
            text_add_ = ', '.join([__.format(row[_]) for __, _
                                   in label_additional_info.items()])
            label_ += '(' + text_add_ + ')'
        if radius is not None:
            shape_ = shape.format(row[glon], row[glat], row[radius])
            text_ = text.format(row[glon], row[glat] + row[radius]
                                * label_distance, label_)
        else:
            shape_ = shape.format(row[glon], row[glat])
            text_ = text.format(row[glon], row[glat] + 0.05, label_)

        region_string += shape_ + text_

        if unc_glat and unc_glat is not None:
            cross_ = _get_cross_ds9_region(row[glon], row[glat], row[unc_glon],
                                           row[unc_glat], color, width)
            region_string += cross_
    return region_string


def _get_cross_ds9_region(x, y, unc_x, unc_y, color, width, endbar=0.01):
    """
    Get ds9 region string for a cross that represents position uncertainties.

    Parameters
    ----------
    x : float
        Position in x direction.
    y : float
        Position in y direction.
    unc_x : float
        Uncertainty of the position in x direction.
    unc_y : float
        Uncertainty of the position in y direction.
    color : str ('green')
        Valid ds9 color.
    width : float
        Linewidth of the cross.
    endbar : float (default = 0.01)
        Length of the endbar in deg.
    """
    format_line = ' color = {0} width = {1}\n'.format(color, width)
    line_ = ''
    line = 'galactic;line({0:.5f},{1:.5f},{2:.5f},{3:.5f}) #'
    line_ += line.format(x - unc_x, y, x + unc_x, y) + format_line
    line_ += line.format(x, y - unc_y, x, y + unc_y) + format_line
    line_ += line.format(x - unc_x, y - endbar, x - unc_x, y + endbar) + format_line
    line_ += line.format(x + unc_x, y - endbar, x + unc_x, y + endbar) + format_line
    line_ += line.format(x - endbar, y + unc_y, x + endbar, y + unc_y) + format_line
    line_ += line.format(x - endbar, y - unc_y, x + endbar, y - unc_y) + format_line
    return line_

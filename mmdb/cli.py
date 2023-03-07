import gzip
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from enum import Enum
from ipaddress import ip_address
from ipaddress import ip_network
from os import PathLike
from os.path import abspath
from os.path import basename
from os.path import dirname
from os.path import join
from pathlib import Path
from typing import AnyStr
from typing import Collection
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type
from typing import Union

import maxminddb
import requests
from netaddr import iprange_to_cidrs
from typer import Abort
from typer import Argument
from typer import BadParameter
from typer import Option
from typer import Typer

from mmdb.models import decode_dataset
from mmdb.models import GenericDataset
from mmdb.models import IpToASNLite
from mmdb.models import IpToCityLite
from mmdb.models import IpToCountryLite
from mmdb.models import linewise
from mmdb.models import MMDBDataset
from mmdb.rsc import BuiltinDataset

app = Typer()


class BuiltinFormat(str, Enum):
    generic = "generic"
    asn = "asn"
    country = "country"
    city = "city"


FORMAT_CLAZZ_MAP: Dict[
    BuiltinFormat, Union[Type[MMDBDataset], Type[GenericDataset]]
] = {
    BuiltinFormat.generic: GenericDataset,
    BuiltinFormat.asn: IpToASNLite,
    BuiltinFormat.city: IpToCityLite,
    BuiltinFormat.country: IpToCountryLite,
}


def _download_files(
    *url: str, outdir: Union[str, "PathLike[AnyStr]"], progress: bool = True
) -> Collection[str]:
    """
    Downloads any file from the fiven url. This method does not throw any
    exception on any HTTP or connectivity error.

    :param url: a url to pointing to any file
    :param outdir: a writeable directory to write the files to.
    :param progress:  If `True` show a main progress bar showing how many of the total
        files have been downloaded. If `False`, no progress bars will be shown at all.
    """
    result = []
    for u in url:
        fname = join(str(outdir), basename(u))
        r = requests.get(u, allow_redirects=True)
        with open(fname, "wb") as handle:
            handle.write(r.content)
        result.append(fname)
    return result


def _gunzip(*filename: Union[str, "PathLike[AnyStr]"]) -> List[str]:
    """
    gunzips a file.

    :param filename: one or multiple files
    :return: the filename of the extracted file.

    .. testsetup::

        >>> from os.path import join
        >>> from base64 import b64decode
        >>> from hashlib import md5
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory

    .. doctest::

        >>> payload = b'H4sICIfQ/WMAA3BhY2tlZC5jc3YAM9QzAEEdQzBtZGqqExoMAIZbOagUAAAA'
        >>> with TemporaryDirectory() as tmp:
        ...     fname = Path(join(tmp, 'packet.csv.gz'))
        ...     with open(fname, 'wb') as handle:
        ...         _ = handle.write(b64decode(payload))
        ...     extracted = _gunzip(fname)
        ...     assert len(extracted) == 1
        ...     assert extracted[0] + '.gz' == str(fname)
        ...     with open(extracted[0], 'rb') as handle:
        ...         data = handle.read()
        >>>
        >>> expected = '0fefd46805301bf91a586fd5c2cb6166'
        >>> result = md5(data).hexdigest()
        >>> assert expected == result
    """
    file_list = [str(fname) for fname in filename]
    for i, fname in enumerate(file_list):
        dname = str(dirname(fname))
        bname = str(basename(fname))
        sys.stderr.write(f"extracting {fname} ...\r")
        target = join(dname, bname[:-3])
        with gzip.open(fname, "rb") as f_in, open(target, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        sys.stderr.write(f"extracting {fname} ... done\n")
        os.remove(fname)
        file_list[i] = target
    return file_list


def _find_mmdb(pattern: str) -> str:
    """
    finds any maxmind database that matches the given glob pattern.

    :param pattern: a globable pattern.
    :return: the first file found which was a valid mmdb
    :raises BadParameter: if not database was found
    """
    pattern = abspath(pattern)
    directory = dirname(pattern)
    pattern = basename(pattern)
    candidates = list(Path(directory).glob(pattern))

    for candidate in candidates:
        try:
            maxminddb.open_database(candidate)
            found = True
        except Exception:
            found = False
        if found is True:
            return abspath(candidate)

    raise BadParameter("no valid mmdb found.")


def _validate_ip(ip: str) -> str:
    """
    validates if the given string is an IPv4 or an IPv6 address.

    :param ip: the string to validate.
    :return: a validated ip address.
    :raises BadParameter: if the given string is neither an IPv4 or an
        IPv6 address.

    .. doctest:: Test valid IPv4

        >>> _validate_ip('1.1.1.1')
        '1.1.1.1'

    .. doctest:: Test valid IPv6
        >>> _validate_ip('0::1')
        '::1'

    .. doctest:: Test invalid IP
        >>> _validate_ip('1.1.1.1/21')
        Traceback (most recent call last):
        click.exceptions.BadParameter: ...
        >>> _validate_ip('0::1/21')
        Traceback (most recent call last):
        click.exceptions.BadParameter: ...
        >>> _validate_ip('asdf')
        Traceback (most recent call last):
        click.exceptions.BadParameter: ...
        >>> _validate_ip('1')
        Traceback (most recent call last):
        click.exceptions.BadParameter: ...
        >>> _validate_ip('0')
        Traceback (most recent call last):
        click.exceptions.BadParameter: ...
    """
    try:
        return str(ip_address(ip))
    except ValueError as e:
        raise BadParameter(str(e))


@app.command(
    help="Queries a MaxMind database for an IP address. The output is emtpy if the "
    "IP address was not found."
)
def get(
    ip: str = Argument(..., callback=_validate_ip, help="An IPv4 or IPv6 Address"),
    database: Path = Option(
        "./*.mmdb",
        "--database",
        "-d",
        callback=_find_mmdb,
        help="Choose the mmdb to query. Default: searches for any *.mmdb file in the "
        "current directory and queries the first found one",
    ),
    pretty: bool = Option(
        False, "--pretty", "-p", help="Enable beautified json output."
    ),
    exclude: List[str] = Option(
        [], "--exclude", "-x", help="exclude columns from displaing."
    ),
) -> None:
    with maxminddb.open_database(database) as reader:
        or_dataset = reader.get(ip)

    if isinstance(or_dataset, dict):
        or_dataset = decode_dataset(or_dataset)
        result = {k: v for k, v in or_dataset.items() if k not in set(exclude)}
        indent = 4 if pretty is True else None
        print(json.dumps(result, indent=indent))


def _get_dbip_files(
    baseurl: str,
    month: datetime,
    asn: bool,
    country: bool,
    city: bool,
    progress: bool,
    outdir: Union[str, "PathLike[AnyStr]"],
) -> Dict[str, BuiltinFormat]:
    requested_month = month.strftime("%Y-%m")
    options = {
        BuiltinFormat.city: city,
        BuiltinFormat.asn: asn,
        BuiltinFormat.country: country,
    }
    file_format_map = {
        f"dbip-asn-lite-{requested_month}.csv": BuiltinFormat.asn,
        f"dbip-country-lite-{requested_month}.csv": BuiltinFormat.country,
        f"dbip-city-lite-{requested_month}.csv": BuiltinFormat.city,
    }
    urls = [
        f"{baseurl}/dbip-{db_type.value}-lite-{requested_month}.csv.gz"
        for db_type, dl_requested in options.items()
        if dl_requested is True
    ]
    files = _download_files(*urls, outdir=outdir, progress=progress)
    files = _gunzip(*files)
    download_fmt_map = {f: file_format_map[basename(f)] for f in files}

    requested_db_types = {
        db_type for db_type, dl_requested in options.items() if dl_requested is True
    }
    received_db_types = set(download_fmt_map.values())
    if received_db_types != requested_db_types:  # pragma: no cover
        # this should not happen since there should be some  exceptions beforehand
        err = (
            "did not receive the following files: "
            f"{[s.value for s in requested_db_types.difference(received_db_types)]}"
        )
        logging.critical(err)
        raise Abort(err)
    return download_fmt_map


@app.command(help="Downloads and build from the dbip (free) repository")
def dbip_build(
    city: bool = Option(True, help="build dbip city mmdb"),
    asn: bool = Option(True, help="build dbip asn mmdb"),
    country: bool = Option(True, help="build dbip country mmdb"),
    exclude: List[str] = Option(
        [], "--exclude", "-x", help="exclude columns from writing to the database."
    ),
    lsc: bool = Option(False, help="wrap the payload for logstash compatibility"),
    baseurl: str = Option(
        "https://download.db-ip.com/free",
        "--url",
        "-u",
        help="the url to the dbip source files",
    ),
    month: datetime = Option(
        datetime.now(),
        "--month",
        "-m",
        formats=["%Y-%m", "%y-%m", "%m/%Y", "%m/%y", "%m.%Y", "%m.%y"],
    ),
    outdir: Path = Option(
        ".",
        "--out",
        "-o",
        readable=True,
        exists=True,
        file_okay=True,
        resolve_path=True,
        help="a custom csv file for a custom mmdb",
    ),
) -> None:
    download_fmt_map = _get_dbip_files(
        baseurl=baseurl,
        month=month,
        asn=asn,
        country=country,
        city=city,
        progress=True,
        outdir=outdir,
    )

    for fpath, fmt in download_fmt_map.items():
        clazz = FORMAT_CLAZZ_MAP[fmt]
        build(
            csv=Path(fpath),
            fmt=fmt,
            netcol="ip_start,ip_end",
            headers=",".join(["ip_start", "ip_end"] + clazz.headers),
            out=Path(join(outdir, f"{clazz.database_type}.mmdb")),
            exclude=exclude,
            lsc=lsc,
        )


def _get_cirds_flip(line: List[str], a: int, b: int) -> Collection[str]:
    """
    get validated networks from a csv line. This function ignores if any
    hostbit was set.

    :param a: The list index which is the first ip within the network
    :param b: The list index which is the last ip within the network
    :return: A collection of validated cidrs
    :raises KeyError: if param `a` or param `b` is greater or equeal the length of
        param `line`.
    :raises ValueError: it `line[a]` or `line[b]`  is neither an IPv4 nor an IPv6
        address.
    :raises TypeError: it `line[a]` and `line[b]` are not the same ip version

    .. doctest:: Test valid 24 prefix

        >>> _get_cirds_flip(['1.0.0.0', '1.0.0.255'], 0, 1)
        ['1.0.0.0/24']

    .. doctest:: Test valid multiple cidrs

        >>> _get_cirds_flip(['1.0.0.253', '1.0.0.255'], 0, 1)
        ['1.0.0.253/32', '1.0.0.254/31']

    .. doctest:: Test invalid IPs

        >>> _get_cirds_flip(['1.0.0', '9.9.9'], 0, 1)
        Traceback (most recent call last):
        ValueError: '1.0.0' does not appear to be an IPv4 or IPv6 address
        >>> _get_cirds_flip(['1.0.0.0', '9.9.9'], 0, 1)
        Traceback (most recent call last):
        ValueError: '9.9.9' does not appear to be an IPv4 or IPv6 address

    .. doctest:: Test invalid idx

        >>> _get_cirds_flip(['1.0.0.0', '9.9.9.9', 'a', 'b'], 2, 3)
        Traceback (most recent call last):
        ValueError: 'a' does not appear to be an IPv4 or IPv6 address
        >>> _get_cirds_flip(['1.0.0.0', '9.9.9.9', 'a', 'b'], 0, 3)
        Traceback (most recent call last):
        ValueError: 'b' does not appear to be an IPv4 or IPv6 address


    .. doctest:: Test ip version mixing

        >>> _get_cirds_flip(['1.0.0.0', '::1'], 0, 1)
        Traceback (most recent call last):
        TypeError: IP sequence cannot contain both IPv4 and IPv6!
    """
    first_ip = str(ip_address(line[a]))
    last_ip = str(ip_address(line[b]))
    cidrs = [str(c) for c in iprange_to_cidrs(first_ip, last_ip)]
    return cidrs


def _get_cirds_network(line: List[str], a: int, b: int) -> Collection[str]:
    """
    get validated networks from a csv line. This function ignores if any
    hostbit was set.

    :param a: The list index which is the network column.
    :param b: This parameter does not have any effect. However,
        this function must have the same signature as :func:`_get_cirds_flip`.
    :return: A collection of validated cidrs
    :raises KeyError: if param a is greater or equeal the length of param `line`.
    :raises ValueError: it `line[a]` is neither an IPv4 nor an IPv6 network.

    .. doctest:: Test valid network with hostbit

        >>> _get_cirds_network(['127.0.0.1/24'], 0, 0)
        ['127.0.0.0/24']

    .. doctest:: Test invalid network

        >>> _get_cirds_network(['127.0.0.1/98'], 0, 0)
        Traceback (most recent call last):
        ValueError: '127.0.0.1/98' does not appear to be an IPv4 or IPv6 network

    .. doctest:: Test idx out of range
        >>> _get_cirds_network(['127.0.0.1/24'], 4, 0)
        Traceback (most recent call last):
        IndexError: list index out of range

    .. doctest:: Test idx wrong column
        >>> _get_cirds_network(['127.0.0.1/24', 'Bla'], 1, 0)
        Traceback (most recent call last):
        ValueError: 'Bla' does not appear to be an IPv4 or IPv6 network
    """
    cidrs = [str(ip_network(line[a], False))]
    return cidrs


def _record_generator(
    linegen: Iterator[List[str]],
    keys: List[str],
    idx: Union[int, Tuple[int, int]],
    netcol: str = "network",
    clazz: Union[Type[MMDBDataset], Type[GenericDataset]] = GenericDataset,
) -> Union[Iterator[MMDBDataset], Iterator[GenericDataset]]:
    """
    .. doctest:: Test network based.

        >>> lines = [['127.0.0.1/24']]
        >>> keys = ['network']
        >>> next(_record_generator(lines, keys, 0, clazz=GenericDataset))
        {'network': '127.0.0.0/24'}

    .. doctest:: Test first/last ip based

        >>> lines = [['127.0.0.0','127.0.0.255']]
        >>> keys = ['first_ip', 'last_ip']
        >>> next(_record_generator(lines, keys, (0,1), clazz=GenericDataset))
        {'network': '127.0.0.0/24'}


    .. doctest:: Test BuiltinDataset

        >>> lines = [['127.0.0.1/24', 'ZZ']]
        >>> keys = ['network', 'iso_a2']
        >>> next(_record_generator(lines, keys, 0, clazz=IpToCountryLite))
        IpToCountryLite(name='Unknown', ...

    .. doctest:: Test netcol

        >>> lines = [['127.0.0.1/24', 'ZZ']]
        >>> keys = ['cidr', 'iso_a2']
        >>> next(_record_generator(lines, keys, 0, "cidr", IpToCountryLite))
        IpToCountryLite(name='Unknown', ...

    .. doctest:: Test invalid column count

        >>> lines = [['127.0.0.1/24', 'ZZ']]
        >>> keys = ['network']
        >>> next(_record_generator(lines, keys, 0, clazz=GenericDataset))
        Traceback (most recent call last):
        click.exceptions.Abort: column count in line ...

        >>> lines = [['127.0.0.1/24', 'ZZ']]
        >>> keys = ['network', 'iso_a2', 'xx']
        >>> next(_record_generator(lines, keys, 0, clazz=GenericDataset))
        Traceback (most recent call last):
        click.exceptions.Abort: column count in line ...
    """
    if isinstance(idx, int):
        get_cidrs = _get_cirds_network
        dataset_ignore = {
            netcol,
        }
        a = idx
        b = -1
    else:
        get_cidrs = _get_cirds_flip
        dataset_ignore = {keys[idx[0]], keys[idx[1]]}
        a = idx[0]
        b = idx[1]

    if issubclass(clazz, BuiltinDataset) and clazz != BuiltinDataset:
        kwmod: Type[BuiltinDataset] = clazz
    else:
        kwmod = BuiltinDataset

    if issubclass(clazz, MMDBDataset):
        network_param = "network"
    else:
        network_param = netcol
        clazz.network_key = netcol
    dataset_ignore.add(network_param)

    for i, line in enumerate(linegen):
        if len(line) != len(keys):
            err = f"column count in line {i + 1} does not match header count\n"
            logging.critical(err)
            raise Abort(err)

        cidrs = get_cidrs(line, a, b)
        dset = {k: v for k, v in zip(keys, line) if k not in dataset_ignore}

        for network in cidrs:
            kwnet = {network_param: network}
            kwargs = kwmod.add_builtin_kwargs(**dset, **kwnet)
            record = clazz(**kwargs)
            yield record


@app.command(help="builds an mmdb file from a csv source")
def build(
    csv: Path = Argument(
        ...,
        readable=True,
        exists=True,
        file_okay=True,
        resolve_path=True,
        help="a custom csv file for a custom mmdb",
    ),
    netcol: str = Option(
        "network",
        "--network",
        "-n",
        help="the column name containing network data. Use parameter --headers if "
        "the csv file does not have headers. Sometimes, the csv does not have a "
        "singe network column. Instead, there is a colum for the first ip and a "
        "second column for the last ip within the network. In this case pass both "
        "column names as column seperated values in the format 'first_ip,last_ip'",
    ),
    headers: Optional[str] = Option(
        None,
        "--headers",
        "-h",
        help="A comma separated list of header names. Required, if the csv file does "
        "not have headers.",
    ),
    fmt: BuiltinFormat = Option(
        BuiltinFormat.generic,
        "--format",
        "-f",
        help="validates each dataset against the validator's specifications.",
    ),
    out: Path = Option(
        "custom.mmdb",
        "--out",
        "-o",
        file_okay=True,
        resolve_path=True,
        writable=True,
        help="the output filename",
    ),
    exclude: List[str] = Option(
        [], "--exclude", "-x", help="exclude columns from writing to the database."
    ),
    lsc: bool = Option(False, help="wrap the payload for logstash compatibility"),
) -> None:
    linegen = linewise(csv, desc=f"reading {fmt}")

    if headers is not None:
        keys = headers.split(",")
    else:
        keys = next(linegen)

    block_column = set(exclude)

    if "," in netcol:
        key_first_ip, key_last_ip = netcol.split(",", 1)
        if key_first_ip not in keys:
            err = f"first ip header not available: {key_first_ip}"
            logging.critical(err)
            raise Abort(err)
        if key_last_ip not in keys:
            err = f"last ip header not available: {key_last_ip}"
            logging.critical(err)
            raise Abort(err)

        netcol = "network"
        idx_fip = keys.index(key_first_ip)
        idx_lip = keys.index(key_last_ip)
        block_column.add(key_first_ip)
        block_column.add(key_last_ip)
        idx: Union[int, Tuple[int, int]] = (idx_fip, idx_lip)
    elif netcol not in keys:
        err = f"network header not available: {netcol}"
        logging.critical(err)
        raise Abort(err)
    else:
        idx_net = keys.index(netcol)
        idx = idx_net

    clazz = FORMAT_CLAZZ_MAP[fmt]
    clazz.exclude_fields = block_column
    generator = _record_generator(
        linegen=linegen,
        keys=keys,
        idx=idx,
        netcol=netcol,
        clazz=clazz,
    )

    MMDBDataset.write(generator, outfile=out, wrap_logstash_compatible=lsc)

    sys.stderr.write(f"database written to {out}\n")

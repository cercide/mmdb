import csv
import json
import os
import sys
from ipaddress import ip_address
from ipaddress import ip_network
from ipaddress import IPv4Address
from ipaddress import IPv4Network
from ipaddress import IPv6Address
from ipaddress import IPv6Network
from os import PathLike
from typing import Any
from typing import AnyStr
from typing import ClassVar
from typing import Dict
from typing import IO
from typing import Iterator
from typing import List
from typing import Optional
from typing import Set
from typing import Type
from typing import Union

from maxminddb import MODE_AUTO
from maxminddb import Reader
from mmdb_writer import MMDBWriter
from netaddr import iprange_to_cidrs
from netaddr import IPSet
from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError
from tqdm import tqdm

from mmdb.rsc import COUNTRY_INFO_MAP
from mmdb.rsc import CountrySummary


def linewise(
    filename: Union[str, "PathLike[AnyStr]"],
    *,
    show_status: bool = True,
    desc: str = "reading",
) -> Iterator[List[str]]:
    stat = os.stat(filename)
    with open(filename, "r") as handle, tqdm(
        desc=desc,
        total=stat.st_size,
        ncols=0,
        leave=False,
        disable=show_status is False,
    ) as bar:
        i = 0
        strline = handle.readline()
        while strline:
            i += 1
            line = next(csv.reader([strline], delimiter=",", quotechar='"'))
            bar.n = handle.tell()
            bar.update()
            yield line
            strline = handle.readline()


def encode_dataset(
    result: Dict[str, Any], wrap_logstash_compatible: bool = False
) -> Dict[str, Any]:
    if wrap_logstash_compatible is True:
        result = {
            "autonomous_system_number": 0,
            "autonomous_system_organization": json.dumps(result),
        }
    return dict(result)


def decode_dataset(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """
    decodes a dataset red from the mmdb.

    :param dataset: the fetched value:
    :return: the decoded dataset. Returns decoded json payload, if the dataset was
        wraped as specified in :meth:`_encode_dataset`.

    .. doctest::

            >>> dataset = {
            ...     'autonomous_system_number': 0,
            ...     'autonomous_system_organization': '{"iso_alpha2_code": "US"}'
            ... }
            >>> expected = {"iso_alpha2_code": "US"}
            >>> result = decode_dataset(dataset)
            >>> assert result == expected

    .. doctest::

            >>> dataset = {
            ...     'autonomous_system_number': 0,
            ...     'autonomous_system_organization': '{"invalid json": asd3}'
            ... }
            >>> expected = dict(dataset)
            >>> result = decode_dataset(dataset)
            >>> assert result == expected


    .. doctest::

            >>> dataset = {'asdf': 0, 'foo': '{"iso_alpha2_code": "US"}'}
            >>> expected = dict(dataset)
            >>> result = decode_dataset(dataset)
            >>> assert result == expected
    """
    if (
        "autonomous_system_number" in dataset
        and "autonomous_system_organization" in dataset
        and dataset["autonomous_system_number"] == 0
    ):
        try:
            dataset = json.loads(dataset["autonomous_system_organization"])
        except json.decoder.JSONDecodeError:
            pass
    return dataset


class InstanceReader(Reader):
    def __init__(
        self,
        model: Type["MMDBDataset"],
        database: Union[AnyStr, int, "PathLike[Any]", IO[Any]],
        mode: int = MODE_AUTO,
    ) -> None:
        super().__init__(database, mode)
        self.model = model

    def get(
        self, ip: Union[str, IPv4Address, IPv6Address]
    ) -> Optional["MMDBDataset"]:  # noqa
        """
        query the database for an ip address.#

        :param ip: the ip address to look for
        :return: None, if the ip address was found. Else, an instance of the queried
            mmdb model.
        :raises ValidationError: If the dataset does not net the model's specificaitons.
        """
        result, prefix = self.get_with_prefix_len(ip)
        if isinstance(result, dict):
            result = decode_dataset(result)
            network = ip_network(f"{ip}/{prefix}", False)
            result["network"] = result.get("network") or network
            return self.model(**result)
        return None


class GenericDataset(Dict[str, Any]):
    network_key: str = "network"
    exclude_fields: ClassVar[Set[str]] = set()
    headers: ClassVar[List[str]] = []
    database_type: ClassVar[str] = "generic"

    @property
    def network(self) -> Union[IPv4Network, IPv6Network]:
        """
        a generic wrapper to write arbitarty csv data. This methods mimics
        :attr:`MMDBDataset.network`

        :return: the network from
        :raises ValueError: if the dateset does not have a key referenced by
            :attr:`GenericDataset.network_key`.
        :raises ValueError: if the network info is not IPv4 or IPv6 network
        :raises TypeError: if the value is neither an IPv4 or IPv6 network nor a str.

        .. doctest::

            >>> GenericDataset.network_key = 'network'
            >>> instance = GenericDataset(network='127.0.0.0/24')
            >>> assert isinstance(instance.network, IPv4Network)
            >>> instance = GenericDataset(network='::0/64')
            >>> assert isinstance(instance.network, IPv6Network)

            >>> instance = GenericDataset(network=ip_network('127.0.0.0/24'))
            >>> assert isinstance(instance.network, IPv4Network)
            >>> instance = GenericDataset(network=ip_network('::0/64'))
            >>> assert isinstance(instance.network, IPv6Network)

        .. doctest::

            >>> instance = GenericDataset()
            >>> instance.network
            Traceback (most recent call last):
            ValueError: missing network data

        .. doctest::

            >>> instance = GenericDataset(network=19876543)
            >>> instance.network
            Traceback (most recent call last):
            TypeError: <class 'int'> is neither an IPv4 or IPv6 network nor a str.
        """
        network = self.get(self.network_key)
        if network is None:
            raise ValueError("missing network data")
        if not isinstance(network, (str, IPv4Network, IPv6Network)):
            raise TypeError(
                f"{type(network)} " "is neither an IPv4 or IPv6 network nor a str."
            )
        result = ip_network(network, False)
        return result

    def encode_dataset(self, wrap_logstash_compatible: bool = False) -> Dict[str, Any]:

        """
        encodes the dataset for the mmdb format.

        :param wrap_logstash_compatible: If True, converts the dataset into a json
            string and places
        :return: the encoded dataset.

        .. doctest::
                >>> instance = GenericDataset(
                ...     network='10.0.0.0/24'
                ... )
                >>> GenericDataset.exclude_fields = {'network'}
                >>> encoded = instance.encode_dataset(False)
                >>> assert len(encoded) == 0, encoded

                >>> GenericDataset.exclude_fields = set()
                >>> encoded = instance.encode_dataset(False)
                >>> assert len(encoded) == 1, encoded
                >>> assert 'network' in encoded, encoded

        .. doctest::

                >>> instance = GenericDataset(
                ...     network='10.0.0.0/24',
                ... )
                >>> encoded = instance.encode_dataset(True)
                >>> expected = json.loads(json.dumps(instance))
                >>> decoded = json.loads(encoded['autonomous_system_organization'])
                >>> assert expected == decoded
        """
        dataset = {k: v for k, v in self.items() if k not in self.exclude_fields}
        return encode_dataset(
            dataset, wrap_logstash_compatible=wrap_logstash_compatible
        )


class MMDBDataset(BaseModel):
    """represents a record to write to or read from an mmdb."""

    headers: ClassVar[List[str]] = []
    database_type: ClassVar[str] = "Custom-MMDB"
    exclude_fields: ClassVar[Set[str]] = set()

    network: Union[IPv4Network, IPv6Network] = Field(
        title="Network", description="ipv4 and ipv6 prefix prefix"
    )

    @classmethod
    def _extend_csv_data(cls, **kwargs: Any) -> Dict[str, Any]:
        return kwargs

    @classmethod
    def open(cls, database: str, mode: int = MODE_AUTO) -> InstanceReader:
        return InstanceReader(cls, database, mode)

    @staticmethod
    def _validate_ipvx(*ip: str) -> None:
        """
        validates an ip address.

        :param ip: an aip value to validate
        :raises ValueError: If the parameter is not an ip address

        .. doctest::

            >>> MMDBDataset._validate_ipvx('127.0.0.1', '1.1.1.1')
            >>> MMDBDataset._validate_ipvx('asdf')
            Traceback (most recent call last):
            ValueError: 'asdf' does not appear to be an IPv4 or IPv6 address
        """
        for x in ip:
            ip_address(x)  # raises ValueError if x is not an ip address

    @classmethod
    def _get_database_type(cls, wrap_logstash_compatible: bool = False) -> str:
        """
        determines the database type written to the mmdb file. For logstash
        compatibility, this value must match the geoip plugins specifications.

        :param wrap_logstash_compatible: If True, returns `GeoLite2-ASN`. Else,
                returns the classvar's value of :attr:`database_type`.
        :return: the database type of the mmdb file.

        .. doctest::

            >>> clazz = MMDBDataset
            >>> assert clazz._get_database_type(True) == 'GeoLite2-ASN'
            >>> assert clazz._get_database_type(False) == clazz.database_type
        """
        if wrap_logstash_compatible is True:
            return "GeoLite2-ASN"
        else:
            return cls.database_type

    @classmethod
    def _from_dbip_csv_line(cls, line: List[str]) -> Iterator["MMDBDataset"]:
        """
        Maps a dbip CSV line to an instance of :class:`MMDBDataset`.

        :param line: the corresponding csv line
        :return: an instance of :class:`MMDBDataset`.
        :raises ValueError: if the column length do not match
        :raises ValueError: if the first two adresse have an invalid ip format
        :raises TypeError: if the fist and the second column have a different ip version
        :raises ValidationError: if the model's specifications remain unmet.

        .. doctest:: Test line without any data

            >>> line = ['127.0.0.1', '127.0.0.255']
            >>> instance = next(MMDBDataset._from_dbip_csv_line(line))
            >>> assert isinstance(instance, MMDBDataset)

        .. doctest:: Test invalid column length

            >>> line = ['127.0.0.1']
            >>> instance = next(MMDBDataset._from_dbip_csv_line(line))
            Traceback (most recent call last):
            ValueError: MMDBDataset expects a column length of 2 got 1

            >>> line = ['127.0.0.1','127.0.0.1','127.0.0.1']
            >>> instance = next(MMDBDataset._from_dbip_csv_line(line))
            Traceback (most recent call last):
            ValueError: MMDBDataset expects a column length of 2 got 3

        .. doctest:: Test IPv4/IPv6 mixing

            >>> line = ['127.0.0.1','::1']
            >>> instance = next(MMDBDataset._from_dbip_csv_line(line))
            Traceback (most recent call last):
            TypeError: IP sequence cannot contain both IPv4 and IPv6!

        .. doctest:: Test invalid line

            >>> line = ['127.0.0.1', '127.0.0.255', 'asd', 'ASN Name']
            >>> instance = next(IpToASNLite._from_dbip_csv_line(line))
            Traceback (most recent call last):
            pydantic.error_wrappers.ValidationError: 1 validation error for ...
        """
        if len(line) != len(cls.headers) + 2:
            raise ValueError(
                f"{cls.__name__ } expects a column length of {len(cls.headers) + 2}"
                f" got {len(line)}"
            )

        cls._validate_ipvx(line[0], line[1])
        first_ip = line[0]
        last_ip = line[1]
        for network in iprange_to_cidrs(first_ip, last_ip):
            kwargs = dict(zip(cls.headers, line[2:]))
            kwargs["network"] = network
            kwargs = cls._extend_csv_data(**kwargs)
            yield cls(**kwargs)

    def encode_dataset(self, wrap_logstash_compatible: bool = False) -> Dict[str, Any]:
        """
        encodes the dataset for the mmdb format.

        :param wrap_logstash_compatible: If True, converts the dataset into a json
            string and places
        :return: the encoded dataset.

        .. doctest:: Test exclude all fields

            >>> IpToASNLite.exclude_fields = {'network', 'number', 'organization'}
            >>> instance = IpToASNLite(
            ...     network='10.0.0.0/24',
            ...     number=12345,
            ...     organization='ASN Name',
            ... )
            >>> encoded = instance.encode_dataset(False)
            >>> assert len(encoded) == 0, encoded

        .. doctest:: Test exclude all fields

            >>> IpToASNLite.exclude_fields = {'number', 'organization'}
            >>> encoded = instance.encode_dataset(False)
            >>> assert len(encoded) == 1, encoded
            >>> assert 'network' in encoded, encoded

        .. doctest:: Test lsc wrapping

            >>> IpToASNLite.exclude_fields=set()
            >>> encoded = instance.encode_dataset(True)
            >>> expected = json.loads(instance.json())
            >>> decoded = json.loads(encoded['autonomous_system_organization'])
            >>> assert expected == decoded, decoded
        """
        result = json.loads(self.json(exclude=self.exclude_fields, exclude_none=True))
        return encode_dataset(result, wrap_logstash_compatible=wrap_logstash_compatible)

    @classmethod
    def dbip_csv(
        cls, filename: str, *, show_status: bool = True
    ) -> Iterator["MMDBDataset"]:
        """
        reads a headless csv file whilest a model validates the data.

        :param filename: the path to the csv file:
        :return: all datasets line by line
        :raises ValueError: If a line does not match the model's specifications.
                            Writes the affected line to stderr.
        """

        for i, line in enumerate(
            linewise(filename, show_status=show_status, desc=cls.database_type)
        ):
            try:
                for x in cls._from_dbip_csv_line(line):
                    yield x
            except ValidationError as e:
                sys.stderr.write(f"line {i}: {line}\n")
                raise ValueError(str(e))

    @classmethod
    def write(
        cls,
        source: Union[str, Iterator["MMDBDataset"], Iterator[GenericDataset]],
        outfile: Union[str, "PathLike[AnyStr]"],
        *,
        wrap_logstash_compatible: bool = False,
    ) -> None:
        """
        Writes an mmdb file to the database.

        :param source: A string is treated as file path pointing to an dbip csv file.
            Else, an iterator must serve instances of :class:`MMDBDataset`.
        :param outfile: the file path to write to
        :param wrap_logstash_compatible: embeds the dataset as a json payload into the
            `GeoLite2-ASN` format. As a result, the logstash geoip filter pluging can
            query the database.
        """
        database_type = cls._get_database_type(wrap_logstash_compatible)

        if wrap_logstash_compatible is True:
            description = f"{cls.__name__} (lsc)"
        else:
            description = cls.__name__

        if isinstance(source, str):
            iterator = cls.dbip_csv(source)
        else:
            iterator = source  # type: ignore

        writer = MMDBWriter(
            ip_version=6,
            database_type=database_type,
            description=description,
            ipv4_compatible=True,
        )

        for record in iterator:
            dataset = record.encode_dataset(wrap_logstash_compatible)
            network = str(record.network)
            writer.insert_network(IPSet([network]), dataset)

        writer.to_db_file(outfile)


class IpToCountryLite(MMDBDataset, CountrySummary):
    """The free IP to Country Lite database is a subset of the IP to Country
    database with reduced coverage and accuracy."""

    database_type: ClassVar[str] = "dbip-Country-Lite"

    headers: ClassVar[List[str]] = ["iso_a2"]

    @classmethod
    def _extend_csv_data(cls, **kwargs: Any) -> Dict[str, Any]:
        iso_a2 = kwargs.get("iso_a2")
        if iso_a2 not in COUNTRY_INFO_MAP:
            country_info = COUNTRY_INFO_MAP["ZZ"]
        else:
            country_info = COUNTRY_INFO_MAP[iso_a2]
        result = {**country_info.dict(), **kwargs}
        return result


class IpToASNLite(MMDBDataset):
    """The IP to ASN Lite database is a subset of the IP to ISP commercial
    database with reduced accuracy and number of records."""

    database_type: ClassVar[str] = "dbip-ASN-Lite"

    headers: ClassVar[List[str]] = ["number", "organization"]

    number: int = Field(ge=1, title="AS Number")
    organization: str = Field(
        title="AS Organisation", description="The AS organisation name"
    )


class IpToCityLite(MMDBDataset, CountrySummary):
    database_type: ClassVar[str] = "dbip-City-Lite"
    headers: ClassVar[List[str]] = [
        "cc",
        "iso_a2",
        "region",
        "city",
        "lat",
        "lon",
    ]

    region: str = Field(title="Region", description="State or Province name")
    city: str = Field(title="City", description="City name")
    lat: float
    lon: float

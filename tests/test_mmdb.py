import json
import os
from contextlib import contextmanager
from ipaddress import IPv4Network
from os.path import abspath
from os.path import dirname
from os.path import isfile
from os.path import join
from unittest import TestCase

import maxminddb

from mmdb.models import IpToCountryLite

DIR = dirname(abspath(__file__))
MMDB = "/tmp/test.mmdb"
country_info = dict(
    iso_a2='US',
    iso_a3='USA',
    name='United States of America',
    number='840',
    continent='North America',
    cc='NA',
    is_eu=False,
    is_nato=True,
    is_asean=False,
    is_eawu=False,
    is_g20=True,
    is_g7=True,
)

class MMDBTests(TestCase):
    def test_read_dbip(self) -> None:
        source = join(DIR, "files", "dbip-country-lite.csv")
        for r in IpToCountryLite.dbip_csv(source):
            assert isinstance(r, IpToCountryLite)
        source = join(DIR, "files", "dbip-country-lite-error.csv")
        generator = IpToCountryLite.dbip_csv(source)
        self.assertRaises(ValueError, next, generator)

    @contextmanager
    def tmpdb(self, clazz, iterator, wrap_logstash_compatible) -> None:
        outfile = "/tmp/test.mmdb"
        clazz.write(
            iterator, outfile, wrap_logstash_compatible=wrap_logstash_compatible
        )
        self.assertTrue(os.path.isfile(outfile))

        with clazz.open(outfile) as reader:
            yield reader

        os.remove(outfile)
        self.assertFalse(os.path.isfile(outfile))

    def test_write_iterator(self) -> None:
        iterator = [
            IpToCountryLite(network="127.0.0.0/24", **country_info)
        ]

        with self.tmpdb(IpToCountryLite, iterator, False) as reader:
            instance = reader.get("127.0.0.1")
            self.assertIsInstance(instance, IpToCountryLite)
            expected = IpToCountryLite(network="127.0.0.0/24", **country_info)
            self.assertEqual(instance.dict(), expected.dict())

    def test_write_from_dbip(self) -> None:
        source = join(DIR, "files", "dbip-country-lite.csv")
        with self.tmpdb(IpToCountryLite, source, False) as reader:
            instance = reader.get("1.0.0.0")
            self.assertIsInstance(instance, IpToCountryLite)
            expected = IpToCountryLite(network='1.0.0.0/24', **country_info)
            self.assertEqual(instance.dict(), expected.dict())

    def test_write_without_wrapping(self) -> None:
        self.test_write_from_dbip()

    def test_not_found(self) -> None:
        source = join(DIR, "files", "dbip-country-lite.csv")
        with self.tmpdb(IpToCountryLite, source, True) as reader:
            query = reader.get("8.8.8.8")
            self.assertIsNone(query)

    def test_write_logstash_compatible(self) -> None:
        source = join(DIR, "files", "dbip-country-lite.csv")
        ip = "1.0.0.0"

        with self.tmpdb(IpToCountryLite, source, True) as reader:
            with maxminddb.open_database("/tmp/test.mmdb") as r2:
                query = r2.get(ip)
                expected = {
                    "autonomous_system_number": 0,
                    "autonomous_system_organization": f'{json.dumps(country_info)}',
                }
                self.assertTrue(query['autonomous_system_number'] == 0)
                self.assertIsInstance(query['autonomous_system_organization'], str)
                expected = dict(country_info)
                result = json.loads(query['autonomous_system_organization'])
                self.assertEqual(expected, result)

            instance = reader.get(ip)
            self.assertIsInstance(instance, IpToCountryLite)
            # self.assertEqual(instance.dict(), )
            # expected = IpToCountryLite(**country_info)

    def test_main(self) -> None:
        with self.assertRaises(SystemExit):
            from mmdb import __main__

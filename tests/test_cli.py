import os
import sys
from unittest import TestCase
from tempfile import TemporaryDirectory
from base64 import b64decode
from requests.exceptions import ConnectionError


from click.exceptions import BadParameter, Abort
from http.server import HTTPServer
from os.path import join, isfile
from hashlib import sha1
from mmdb import cli
from io import StringIO
from pathlib import Path
from multiprocessing import Process
from http.server import HTTPServer as BaseHTTPServer
from http.server import SimpleHTTPRequestHandler
from datetime import datetime


class HTTPServer(BaseHTTPServer):
    """The main server, you pass in base_path which is the path you want to serve requests from"""
    def __init__(self, base_path, server_address, RequestHandlerClass=SimpleHTTPRequestHandler):
        self.base_path = base_path
        super().__init__(server_address, RequestHandlerClass)

    def serve_forever(self, *args, **kwargs): #pragma: no cover
        # runs in subprocess --> not affected by coverage
        os.chdir(self.base_path)
        print(self.base_path)
        print(list(Path(self.base_path).rglob('*')))
        super().serve_forever(*args, **kwargs)


class MMDBTests(TestCase):
    def _write_files(self):
        with open(join(self.tmp, 'dbip-country-lite.csv'), 'w') as handle:
            handle.write('1.0.0.0,1.0.0.255,US\n')
        with open(join(self.tmp, 'custom.csv'), 'w') as handle:
            handle.write('netx,cc\n')
            handle.write('1.0.0.0/24,UK\n')
            handle.write('1.0.1.0/24,US\n')
        with open(join(self.tmp, 'test.mmdb'), 'wb') as handle:
            handle.write(b64decode('''
                'AAABAAB4AAACAAB4AAADAAB4AAAEAAB4AAAFAAB4AAAGAAB4AA'
                'AHAAB4AAAIAAB4AAAJAAB4AAAKAAB4AAALAAB4AAAMAAB4AAAN'
                'AAB4AAAOAAB4AAAPAAB4AAAQAAB4AAARAAB4AAASAAB4AAATAA'
                'B4AAAUAAB4AAAVAAB4AAAWAAB4AAAXAAB4AAAYAAB4AAAZAAB4'
                'AAAaAAB4AAAbAAB4AAAcAAB4AAAdAAB4AAAeAAB4AAAfAAB4AA'
                'AgAAB4AAAhAAB4AAAiAAB4AAAjAAB4AAAkAAB4AAAlAAB4AAAm'
                'AAB4AAAnAAB4AAAoAAB4AAApAAB4AAAqAAB4AAArAAB4AAAsAA'
                'B4AAAtAAB4AAAuAAB4AAAvAAB4AAAwAAB4AAAxAAB4AAAyAAB4'
                'AAAzAAB4AAA0AAB4AAA1AAB4AAA2AAB4AAA3AAB4AAA4AAB4AA'
                'A5AAB4AAA6AAB4AAA7AAB4AAA8AAB4AAA9AAB4AAA+AAB4AAA/'
                'AAB4AABAAAB4AABBAAB4AABCAAB4AABDAAB4AABEAAB4AABFAA'
                'B4AABGAAB4AABHAAB4AABIAAB4AABJAAB4AABKAAB4AABLAAB4'
                'AABMAAB4AABNAAB4AABOAAB4AABPAAB4AABQAAB4AABRAAB4AA'
                'BSAAB4AABTAAB4AABUAAB4AABVAAB4AABWAAB4AABXAAB4AABY'
                'AAB4AABZAAB4AABaAAB4AABbAAB4AABcAAB4AABdAAB4AABeAA'
                'B4AABfAAB4AABgAAB4AABhAAB4AABiAAB4AABjAAB4AABkAAB4'
                'AABlAAB4AABmAAB4AABnAAB4AAB4AABoAABpAAB4AABqAAB4AA'
                'BrAAB4AABsAAB4AABtAAB4AABuAAB4AABvAAB4AABwAAB4AABx'
                'AAB4AAByAAB4AABzAAB4AAB0AAB4AAB1AAB4AAB2AAB4AAB3AA'
                'B4AACzAADQAAAAAAAAAAAAAAAAAAAAAENpc28gAEJVSyAGR25l'
                'dHdvcmsgC0oxLjAuMC4wLzI0IBXiIAAgBiALIBUgIkJVUyAtSj'
                'EuMC4xLjAvMjQgMuIgACAtIAsgMiA/q83vTWF4TWluZC5jb23p'
                'Sm5vZGVfY291bnTBeEtyZWNvcmRfc2l6ZaEYSmlwX3ZlcnNpb2'
                '6hBk1kYXRhYmFzZV90eXBlS0N1c3RvbS1NTURCSWxhbmd1YWdl'
                'cwAEW2JpbmFyeV9mb3JtYXRfbWFqb3JfdmVyc2lvbqECW2Jpbm'
                'FyeV9mb3JtYXRfbWlub3JfdmVyc2lvbqBLYnVpbGRfZXBvY2gE'
                'AmP+BGZLZGVzY3JpcHRpb27g'''
            ))

        os.makedirs(join(self.tmp, 'free'), exist_ok=True)
        with open(join(self.tmp, 'free', 'dbip-asn-lite-2023-02.csv.gz'), 'wb') as handle:
            handle.write(b64decode(
                'H4sICCsS/2MAA2RiaXAtYXNuLWxpdGUtMjAyMy0wMi5jc3YAM9QzAEEdQzBtZGqqY2hkbGKqo+QY'
                '7KdgqMRlCJU3gsubmVtYGkDkjZS4AGu3KjJAAAAA'
            ))

        with open(join(self.tmp, 'free', 'dbip-city-lite-2023-02.csv.gz'), 'wb') as handle:
            handle.write(b64decode(
                'H4sICOYV/2MAA2RiaXAtY2l0eS1saXRlLTIwMjMtMDIuY3N2ADPQMwBBHQM9I1NTGNaJigIhHR2g'
                'OJchVAWEBsn6O+uEBuuEJxZnZOall+Tn6Si55JfnlQCxko6ukZmeoZGxiY6hiRGIwQUA/V3JKGEA'
                'AAA='
            ))

        with open(join(self.tmp, 'free', 'dbip-country-lite-2023-02.csv.gz'), 'wb') as handle:
            handle.write(b64decode(
                'H4sICIUS/2MAA2RiaXAtY291bnRyeS1saXRlLTIwMjMtMDIuY3N2ADPQMwBBHQM9I1NTGNaJiuIy'
                'hEpAaJBgaDAXAJuQprcuAAAA'
            ))

    def setUp(self):
        self._tmpdir = TemporaryDirectory()
        self.tmp = str(self._tmpdir.name)
        self._write_files()

    def test_file_download(self):
        port = 48102
        httpd = HTTPServer(self.tmp, ('127.0.0.1', port))
        p = Process(target=httpd.serve_forever)
        p.start()

        result = set()
        with TemporaryDirectory() as tmpdir:
            try:
                file_list = cli._download_files(
                    f'http://localhost:{port}/custom.csv',
                    f'http://localhost:{port}/dbip-country-lite.csv',
                    progress=False,
                    outdir=tmpdir
                )
            except Exception: #pragma: no cover
                raise
            finally:
                p.kill()
                p.terminate()
                p.join()
            self.assertTrue(all(isfile(f) for f in file_list), f'not a file {file_list}')
            self.assertTrue(len(file_list) == 2, f'invalid length: {file_list})')
            with open(file_list[0], 'rb') as h0, open(file_list[1], 'rb') as h1:
                result.add(sha1(h0.read()).hexdigest())
                result.add(sha1(h1.read()).hexdigest())
        expected = {
            'a135d2a1e9203c9f1de5a01c2b92febbc2c5e06c',
            'bd0e362414e8fe044f8781866bda654a877fcd45'
        }
        self.assertEqual(result, expected)


    def test_find_mmdb(self):
        pattern = join(self.tmp, '*.mmdb')
        result = cli._find_mmdb(pattern)
        self.assertTrue(result.endswith('.mmdb'))

        pattern = join(self.tmp, '*.csv')
        with self.assertRaises(BadParameter):
            cli._find_mmdb(pattern)

    def test_get(self):
        db = Path(join(self.tmp, 'test.mmdb'))
        old_stdout = sys.stdout

        # Test record found
        sys.stdout = StringIO()
        cli.get('1.0.0.0', db, False, [])
        result = sys.stdout.getvalue()
        self.assertEqual(result, '{"iso": "UK", "network": "1.0.0.0/24"}\n')

        sys.stdout = StringIO()
        cli.get('1.0.0.0', db, True, [])
        result = sys.stdout.getvalue()
        self.assertEqual(result, '{\n'
            '    "iso": "UK",\n'
            '    "network": "1.0.0.0/24"\n'
            '}\n')

        # Test record not found
        sys.stdout = StringIO()
        cli.get('8.8.8.8', db, False, [])
        result = sys.stdout.getvalue()
        self.assertEqual(result, "")

        # Test exclude field
        sys.stdout = StringIO()
        cli.get('1.0.0.0', db, False, ['network'])
        result = sys.stdout.getvalue()
        self.assertEqual(result, '{"iso": "UK"}\n')

        # Test exclude everything
        sys.stdout = StringIO()
        cli.get('1.0.0.0', db, False, ['iso', 'network'])
        result = sys.stdout.getvalue()
        self.assertEqual(result, '{}\n')

        sys.stdout = old_stdout

    def test_get_dbip_files(self):
        # Download and extract from dummy server
        port = 38102
        httpd = HTTPServer(self.tmp, ('127.0.0.1', port))
        p = Process(target=httpd.serve_forever)
        p.start()

        baseurl = f'http://localhost:{port}/free'
        month = datetime(2023, 2, 1)
        with TemporaryDirectory() as tmpdir:
            try:
                download_fmt_map = cli._get_dbip_files(
                    baseurl=baseurl,
                    month=month,
                    asn=True,
                    country=True,
                    city=True,
                    progress=False,
                    outdir=tmpdir,
                )
            except Exception: #pragma: no cover
                raise
            finally:
                p.kill()
                p.terminate()
                p.join()

            result = set()
            for fname in download_fmt_map.keys():
                with open(fname, 'rb') as handle:
                    result.add(sha1(handle.read()).hexdigest())

        assert cli.BuiltinFormat.asn in download_fmt_map.values(), "missing asn"
        assert cli.BuiltinFormat.city in download_fmt_map.values(), "missing city"
        assert cli.BuiltinFormat.country in download_fmt_map.values(), "missing country"

        expected = {
            '4954ee0a7544a2a004705194e4a473414c5130c4',
            '4abefbd30baed51764d8b44a117a6b2e4e5b86f1',
            '668f50dcc0d9353f80a80add621a9348810ac800'
        }
        assert result == expected, result.difference(expected)

        # Test Download failed
        # no server required
        baseurl = f'http://localhost:{port + 1}/free'
        month = datetime(2023, 2, 1)
        with self.assertRaises(ConnectionError):
            with TemporaryDirectory() as tmpdir:
                download_fmt_map = cli._get_dbip_files(
                    baseurl=baseurl,
                    month=month,
                    asn=True,
                    country=True,
                    city=True,
                    progress=False,
                    outdir=tmpdir,
                )

    def test_build_dbip(self):
        # Download and build
        port = 38104
        httpd = HTTPServer(self.tmp, ('127.0.0.1', port))

        p = Process(target=httpd.serve_forever)
        p.start()
        baseurl = f'http://localhost:{port}/free'
        month = datetime(2023, 2, 1)
        try:
            cli.dbip_build(
                baseurl=baseurl,
                month=month,
                asn=True,
                country=True,
                city=True,
                lsc=False,
                exclude=['network'],
                outdir=self.tmp,
            )
        except Exception: #pragma: no cover
            raise
        finally:
            p.kill()
            p.terminate()
            p.join()

    def test_build(self):
        old_stdout = sys.stdout

        # Test csv header // custom data // custom netcol.
        with TemporaryDirectory() as tmpdir:
            db = Path(join(tmpdir, 'test.mmdb'))
            cli.build(
                csv=Path(join(self.tmp, 'custom.csv')),
                netcol="netx",
                headers=None,
                fmt=cli.BuiltinFormat.generic,
                out=db,
                exclude=[],
                lsc=False,
            )
            sys.stdout = StringIO()
            cli.get('1.0.0.0', db, False, [])
            result = sys.stdout.getvalue()
            self.assertEqual(result, '{"cc": "UK", "netx": "1.0.0.0/24"}\n')

        # missing first ip header
        with self.assertRaises(Abort):
            cli.build(
                csv=Path(join(self.tmp,'dbip-asn-lite-2023-02.csv')),
                netcol="first_ip,last_ip",
                headers='xx,last_ip',
                fmt=cli.BuiltinFormat.generic,
                out=db,
                exclude=[],
                lsc=False,
            )


        # missing ip last ip header
        with self.assertRaises(Abort):
            cli.build(
                csv=Path(join(self.tmp,'dbip-asn-lite-2023-02.csv')),
                netcol="first_ip,last_ip",
                headers='first_ip,xx',
                fmt=cli.BuiltinFormat.generic,
                out=db,
                exclude=[],
                lsc=False,
            )

        # missing netcol
        with self.assertRaises(Abort):
            cli.build(
                csv=Path(join(self.tmp,'dbip-asn-lite-2023-02.csv')),
                netcol="missing",
                headers='cidr,other',
                fmt=cli.BuiltinFormat.generic,
                out=db,
                exclude=[],
                lsc=False,
            )



        sys.stdout = old_stdout
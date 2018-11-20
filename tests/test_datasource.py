import pytest
import numpy

from grplot import DataSource


@pytest.fixture(scope='session')
def invalid_size_file(tmpdir_factory):
    """Fixture for a tmp file of 10 data points plus bogus bytes (81 bytes)"""
    fn = tmpdir_factory.mktemp('data').join('bad_file.bin')
    data = numpy.array(10*[1+1j], dtype=numpy.complex64)
    with open(fn, 'wb') as fh:
        data.tofile(fh)
        # Write a dummy byte at the end
        fh.write(b'\xff')
    return fn


@pytest.fixture(scope='session')
def size_100_file(tmpdir_factory):
    """Fixture for a tmp file of 100 data points"""
    fn = tmpdir_factory.mktemp('data').join('100_point_file.bin')
    data = numpy.array(100*[1+1j], dtype=numpy.complex64)
    with open(fn, 'wb') as fh:
        data.tofile(fh)
    return fn


def test_invalid_file_length(invalid_size_file):
    ds = DataSource()
    ds.load_file(invalid_size_file, True)
    assert ds._end == 10


def test_file_range_full(size_100_file):
    ds = DataSource()
    ds.load_file(size_100_file, True)
    assert ds._end == 100
    assert ds._start == 0


def test_middle_of_file(size_100_file):
    ds = DataSource()
    ds._start = 10
    ds._end = 20
    ds.load_file(size_100_file)
    assert ds._start == 10
    assert ds._end == 20


def test_range_limit_properties(size_100_file):
    ds = DataSource()
    ds._start = 10
    ds._end = 20
    ds.load_file(size_100_file)
    assert ds.start == 10
    assert ds.end == 20
    
    ds.start = 15
    assert ds.start == 15

    ds.end = 19
    assert ds.end == 19

    ds.end = 101
    assert ds.end == 100
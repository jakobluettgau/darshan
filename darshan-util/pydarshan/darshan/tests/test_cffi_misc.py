# miscellaneous tests for the CFFI backend
# that are not specific to any particular
# mod

import re

import pytest
import numpy as np
from numpy.testing import assert_array_equal, assert_allclose
import darshan
import darshan.backend.cffi_backend as backend
from darshan.log_utils import get_log_path

def test_get_lib_version():
    # check for a reasonable version string
    # returned by get_lib_version()
    actual_version = backend.get_lib_version()
    # must be a string
    assert isinstance(actual_version, str)
    # two periods in semantic version num
    assert actual_version.count('.') == 2
    # stricter regular expression match on
    # the semantic version number
    prog = re.compile(r"^\d+\.\d+\.\d+(-.+)?$")
    match = prog.fullmatch(actual_version)
    assert match is not None
    assert match.group(0) == actual_version


@pytest.mark.parametrize(
    "log_path",
    [
        # this log is the only one that returns a dataframe
        # with 'int' file hashes
        # NOTE: this case fails even before the fix
        # because the fix enforces the data type uint64
        "sample.darshan",
        # these following 2 logs return dataframes with
        # 'float' file hashes
        "sample-goodost.darshan",
        "sample-dxt-simple.darshan",
    ],
)
def test_file_hash_type(log_path):
    # regression test for issue #438
    # see: https://github.com/darshan-hpc/darshan/issues/438

    # check that a single record generated by `log_get_generic_record`
    # has the correct data type for the file hash/id
    log_path = get_log_path(log_path)
    log = backend.log_open(log_path)
    rec = backend.log_get_generic_record(log=log, mod_name="POSIX", dtype="pandas")
    # verify the records returned have the correct
    # data type for the ids/hashes
    assert rec["counters"]["id"].dtype == np.uint64
    assert rec["fcounters"]["id"].dtype == np.uint64

    # additionally check that the dataframes
    # generated are of the correct types
    with darshan.DarshanReport(log_path, read_all=True) as report:
        report.mod_read_all_records("POSIX", dtype="pandas")
        rec_counters = report.records["POSIX"][0]["counters"]
        rec_fcounters = report.records["POSIX"][0]["fcounters"]
    # verify the records returned have the correct
    # data type for the ids/hashes
    assert rec_counters["id"].dtype == np.uint64
    assert rec_fcounters["id"].dtype == np.uint64


@pytest.mark.parametrize("dtype", ["numpy", "dict", "pandas"])
def test_log_get_generic_record(dtype):
    # regression test for issue #440
    # see: https://github.com/darshan-hpc/darshan/issues/440

    # collect the expected counter/fcounter column names
    expected_counter_names = backend.counter_names("POSIX")
    expected_fcounter_names = backend.fcounter_names("POSIX")

    # assign the expected counter/fcounter values
    expected_counter_vals = np.array(
        [
            2049, -1, -1, 0, 16402, 16404, 0, 0, 0, 0, -1, -1, 0, 0, 0,
            2199023259968, 0, 2199023261831, 0, 0, 0, 16384, 0, 0, 8,
            16401, 1048576, 0, 134217728, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 4, 14, 0, 0, 0, 0, 0, 0, 16384, 0, 274743689216,
            274743691264, 0, 0, 10240, 4096, 0, 0, 134217728, 272, 544,
            328, 16384, 8, 2, 2, 597, 1073741824, 1312, 1073741824,
        ]
    )
    expected_fcounter_vals = np.array(
        [
            3.9191410541534424, 0.0, 3.940063953399658, 3.927093982696533,
            3.936579942703247, 0.0, 115.0781660079956, 115.77035808563232,
            0.0, 100397.60042190552, 11.300841808319092, 0.0,
            17.940945863723755, 20.436099529266357, 85.47495031356812,
            0.0, 0.0,
        ]
    )

    # generate a record from sample log
    log = backend.log_open(get_log_path("sample.darshan"))
    rec = backend.log_get_generic_record(log=log, mod_name="POSIX", dtype=dtype)

    # each record should have the following keys
    record_keys = ["id", "rank", "counters", "fcounters"]
    assert list(rec.keys()) == record_keys
    # check the file hash/id
    assert rec["id"] == 6301063301082038805
    # check the rank
    assert rec["rank"] == -1

    if dtype == "numpy":
        # check the length of the returned arrays are correct
        assert rec["counters"].size == 69
        assert rec["fcounters"].size == 17
        # collect the actual counter/fcounter values
        actual_counter_vals = rec["counters"]
        actual_fcounter_vals = rec["fcounters"]

    elif dtype == "dict":
        # check the length of the returned dictionaries are correct
        assert len(rec["counters"]) == 69
        assert len(rec["fcounters"]) == 17
        # collect the actual counter/fcounter key names
        actual_counter_names = list(rec["counters"].keys())
        actual_fcounter_names = list(rec["fcounters"].keys())
        # collect the actual counter/fcounter values
        actual_counter_vals = np.array(list(rec["counters"].values()))
        actual_fcounter_vals = np.array(list(rec["fcounters"].values()))

    elif dtype == "pandas":
        # make sure the added column keys are in the dataframes
        for key in ["id", "rank"]:
            assert key in rec["counters"].columns
            assert key in rec["fcounters"].columns
        # double check the id/rank values
        assert rec["counters"]["id"].values == 6301063301082038805
        assert rec["counters"]["rank"].values == -1
        # make sure the dataframes are the expected shapes
        # the shapes are 2 larger than the arrays since the id/rank
        # columns are added to the dataframes
        assert rec["counters"].shape == (1, 71)
        assert rec["fcounters"].shape == (1, 19)
        # collect the actual counter/fcounter key names
        # don't include the id/rank columns
        actual_counter_names = list(rec["counters"].columns)[2:]
        actual_fcounter_names = list(rec["fcounters"].columns)[2:]
        # collect the actual counter/fcounter values
        # don't include the id/rank columns
        actual_counter_vals = rec["counters"].values[0][2:]
        actual_fcounter_vals = rec["fcounters"].values[0][2:]

    # check the actual counter/fcounter values agree
    # with the expected counter/fcounter values
    assert_array_equal(actual_counter_vals, expected_counter_vals)
    assert_allclose(actual_fcounter_vals, expected_fcounter_vals)

    if dtype != "numpy":
        # make sure the returned key/column names agree
        assert actual_counter_names == expected_counter_names
        assert actual_fcounter_names == expected_fcounter_names

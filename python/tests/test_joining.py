from __future__ import print_function
import ctypes
from contextlib import contextmanager

from functools import partial

import pytest

import numpy as np
from numba import cuda

from libgdf_cffi import ffi, libgdf

from .utils import new_column, new_context, unwrap_devary, get_dtype


@contextmanager
def _make_input(left, right):
    d_left = cuda.to_device(left)
    col_left = new_column()
    libgdf.gdf_column_view(col_left, unwrap_devary(d_left), ffi.NULL,
                           left.size, get_dtype(d_left.dtype))

    d_right = cuda.to_device(right)
    col_right = new_column()
    libgdf.gdf_column_view(col_right, unwrap_devary(d_right), ffi.NULL,
                           right.size, get_dtype(d_right.dtype))

    yield col_left, col_right

@contextmanager
def _make_input_multi(left, right, ncols):
    cl = []
    cr = []

    for i in range(ncols):
        d_left = cuda.to_device(left[i])
        col_left = new_column()
        libgdf.gdf_column_view(col_left, unwrap_devary(d_left), ffi.NULL,
                            left[i].size, get_dtype(d_left.dtype))
        cl.append(col_left)

        d_right = cuda.to_device(right[i])
        col_right = new_column()
        libgdf.gdf_column_view(col_right, unwrap_devary(d_right), ffi.NULL,
                            right[i].size, get_dtype(d_right.dtype))
        cr.append(col_right)

    yield cl, cr

def _copy_int_col_to_arr(col):
    dataptr = col.data
    datasize = col.size
    addr = ctypes.c_uint64(int(ffi.cast("uintptr_t", dataptr)))
    memptr = cuda.driver.MemoryPointer(context=cuda.current_context(),
                                       pointer=addr, size=4 * datasize)
    ary = cuda.devicearray.DeviceNDArray(shape=(datasize,), strides=(4,),
                                         dtype=np.dtype(np.int32),
                                         gpu_data=memptr)
    return ary.copy_to_host()


def _call_join(api, col_left, col_right):
    l_res = new_column()
    r_res = new_column()

    api(col_left, col_right, l_res, r_res)

    l_idx = _copy_int_col_to_arr(l_res)
    r_idx = _copy_int_col_to_arr(r_res)

    joined_idx = np.array([l_idx, r_idx])

    libgdf.gdf_column_free(l_res)
    libgdf.gdf_column_free(r_res)
    return joined_idx


def _call_join_multi(api, ncols, col_left, col_right, ctxt):
    l_res = new_column()
    r_res = new_column()

    api(ncols, col_left, col_right, l_res, r_res, ctxt)

    l_idx = _copy_int_col_to_arr(l_res)
    r_idx = _copy_int_col_to_arr(r_res)

    joined_idx = np.array([l_idx, r_idx])

    libgdf.gdf_column_free(l_res)
    libgdf.gdf_column_free(r_res)
    return joined_idx


params_jtypes = [libgdf.GDF_SORT, libgdf.GDF_HASH]
params_dtypes = [np.int8, np.int32, np.int64, np.float32, np.float64]
multi_params_dtypes = [np.int32, np.int64]

@pytest.mark.parametrize('join_type', params_jtypes)
@pytest.mark.parametrize('dtype', params_dtypes)
def test_innerjoin(dtype, join_type):
    # Make data
    left = np.array([[0, 0, 1, 2, 3]], dtype=dtype)
    right = np.array([[0, 1, 2, 2, 3]], dtype=dtype)
#    left = np.array([44, 47, 0, 3, 3, 39, 9, 19, 21, 36, 23, 6, 24, 24, 12, 1, 38, 39, 23, 46, 24, 17, 37, 25, 13, 8, 9, 20, 16, 5, 15, 47, 0, 18, 35, 24, 49, 29, 19, 19, 14, 39, 32, 1, 9, 32, 31, 10, 23, 35, 11, 28, 34, 0, 0, 36, 5, 38, 40, 17, 15, 4, 41, 42, 31, 1, 1, 39, 41, 35, 38, 11, 46, 18, 27, 0, 14, 35, 12, 42, 20, 11, 4, 6, 4, 47, 3, 12, 36, 40, 14, 15, 20, 35, 23, 15, 13, 21, 48, 49], dtype=dtype)
#    right = np.array([5, 41, 35, 0, 31, 5, 30, 0, 49, 36, 34, 48, 29, 3, 34, 42, 13, 48, 39, 21, 9, 0, 10, 43, 23, 2, 34, 35, 30, 3, 18, 46, 35, 20, 17, 27, 14, 41, 1, 36, 10, 22, 43, 40, 11, 2, 16, 32, 0, 38, 19, 46, 42, 40, 13, 30, 24, 2, 3, 30, 34, 43, 13, 48, 40, 8, 19, 31, 8, 26, 2, 3, 44, 14, 32, 4, 3, 45, 11, 22, 13, 45, 11, 16, 24, 29, 21, 46, 25, 16, 19, 33, 40, 32, 36, 6, 21, 31, 13, 7], dtype=dtype)

    gdf_ctxt = new_context()
    libgdf.gdf_context_view(gdf_ctxt, (join_type == libgdf.GDF_SORT), join_type, 0)
    with _make_input_multi(left, right, 1) as (col_left, col_right):
        # Join
        joined_idx = _call_join_multi(libgdf.gdf_inner_join, 1, col_left,
                                col_right, gdf_ctxt)
    print(joined_idx)
    # Check answer
    # Can be generated by:
    # In [56]: df = pd.DataFrame()
    # In [57]: df = pd.DataFrame()
    # In [58]: df['a'] = list(range(5))
    # In [59]: df1 = df.set_index(np.array([0, 0, 1, 2, 3]))
    # In [60]: df2 = df.set_index(np.array([0, 1, 2, 2, 3]))
    # In [61]: df1.join(df2, lsuffix='_left', rsuffix='_right', how='inner')
    # Out[61]:
    #    a_left  a_right
    # 0       0        0
    # 0       1        0
    # 1       2        1
    # 2       3        2
    # 2       3        3
    # 3       4        4
    left_pos, right_pos = joined_idx
    left_idx = left[0][left_pos]
    right_idx = right[0][right_pos]

    assert list(left_idx) == list(right_idx)
    # sort before checking since the hash join may produce results in random order
    tmp = sorted(zip(left_pos, right_pos), key=lambda pair: (pair[0], pair[1]))
    left_pos = [x for x,_ in tmp]
    right_pos = [x for _,x in tmp]
    # left_pos == a_left
    assert tuple(left_pos) == (0, 1, 2, 3, 3, 4)
    # right_pos == a_right
    assert tuple(right_pos) == (0, 0, 1, 2, 3, 4)

@pytest.mark.parametrize('join_type', params_jtypes)
@pytest.mark.parametrize('dtype', params_dtypes)
def test_leftjoin(dtype, join_type):
    # Make data
    left = np.array([[0, 0, 4, 5, 5]], dtype=dtype)
    right = np.array([[0, 0, 2, 3, 5]], dtype=dtype)
    gdf_ctxt = new_context()
    libgdf.gdf_context_view(gdf_ctxt, (join_type == libgdf.GDF_SORT), join_type, 0)
    with _make_input_multi(left, right, 1) as (col_left, col_right):
        # Join
        joined_idx = _call_join_multi(libgdf.gdf_left_join, 1, col_left,
                                col_right, gdf_ctxt)
    # Check answer
    # Can be generated by:
    # In [75]: df = pd.DataFrame()
    # In [76]: df['a'] = list(range(5))
    # In [77]: df1 = df.set_index(np.array([0, 0, 4, 5, 5]))
    # In [78]: df2 = df.set_index(np.array([0, 0, 2, 3, 5]))
    # In [79]: df1.join(df2, lsuffix='_left', rsuffix='_right', how='left')
    # Out[79]:
    #    a_left  a_right
    # 0       0      0.0
    # 0       0      1.0
    # 0       1      0.0
    # 0       1      1.0
    # 4       2      NaN
    # 5       3      4.0
    # 5       4      4.0
    left_pos, right_pos = joined_idx
    left_idx = [left[0][a] for a in left_pos]
    right_idx = [right[0][b] if b != -1 else None for b in right_pos]
    print(left_idx)
    print(right_idx)

    # sort before checking since the hash join may produce results in random order
    left_idx = sorted(left_idx)
    assert tuple(left_idx) == (0, 0, 0, 0, 4, 5, 5)
    # sort wouldn't work for nans
    #assert tuple(right_idx) == (0, 0, 0, 0, None, 5, 5)

    # sort before checking since the hash join may produce results in random order
    tmp = sorted(zip(left_pos, right_pos), key=lambda pair: (pair[0], pair[1]))
    left_pos = [x for x,_ in tmp]
    right_pos = [x for _,x in tmp]
    # left_pos == a_left
    assert tuple(left_pos) == (0, 0, 1, 1, 2, 3, 4)
    # right_pos == a_right
    assert tuple(right_pos) == (0, 1, 0, 1, -1, 4, 4)


@pytest.mark.parametrize('dtype', params_dtypes)
def test_outerjoin(dtype):
    # Make data
    left = np.array([0, 0, 4, 5, 5], dtype=dtype)
    right = np.array([0, 0, 2, 3, 5], dtype=dtype)
    with _make_input(left, right) as (col_left, col_right):
        # Join
        joined_idx = _call_join(libgdf.gdf_outer_join_generic, col_left, col_right)
    # Check answer
    # Can be generated by:
    # In [75]: df = pd.DataFrame()
    # In [76]: df['a'] = list(range(5))
    # In [77]: df1 = df.set_index(np.array([0, 0, 4, 5, 5]))
    # In [78]: df2 = df.set_index(np.array([0, 0, 2, 3, 5]))
    # In [79]: df1.join(df2, lsuffix='_left', rsuffix='_right', how='outer')
    # Out[79]:
    #    a_left  a_right
    # 0     0.0      0.0
    # 0     0.0      1.0
    # 0     1.0      0.0
    # 0     1.0      1.0
    # 2     NaN      2.0
    # 3     NaN      3.0
    # 4     2.0      NaN
    # 5     3.0      4.0
    # 5     4.0      4.0
    #
    # Note: the algorithm is different here that we append the missing rows
    #       from the right to the end.  So the result is actually:
    #    a_left  a_right
    # 0     0.0      0.0
    # 0     0.0      1.0
    # 0     1.0      0.0
    # 0     1.0      1.0
    # 4     2.0      NaN
    # 5     3.0      4.0
    # 5     4.0      4.0
    # 2     NaN      2.0
    # 3     NaN      3.0
    # Note: This is actually leftjoin + append missing

    def at(arr, x):
        if x != -1:
            return arr[x]

    left_pos, right_pos = joined_idx
    left_idx = [at(left, a) for a in left_pos]
    right_idx = [at(right, b) for b in right_pos]

    assert tuple(left_idx) == (0, 0, 0, 0, 4, 5, 5, None, None)
    assert tuple(right_idx) == (0, 0, 0, 0, None, 5, 5, 2, 3)
    # left_pos == a_left
    assert tuple(left_pos) == (0, 0, 1, 1, 2, 3, 4, -1, -1)
    # right_pos == a_right
    assert tuple(right_pos) == (0, 1, 0, 1, -1, 4, 4, 2, 3)


@pytest.mark.parametrize('dtype', multi_params_dtypes)
def test_multileftjoin(dtype):
    # Make data
    left = np.array([[0, 0, 4, 5, 5], [1, 2, 2, 3, 4], [1, 1, 3, 1, 2]], dtype=dtype)
    right = np.array([[0, 0, 2, 3, 5], [1, 2, 3, 3, 4], [3, 3, 2, 1, 1]], dtype=dtype)
    gdf_ctxt = new_context()
    libgdf.gdf_context_view(gdf_ctxt, 0, libgdf.GDF_HASH, 0)

    for k in range(3):
        with _make_input_multi(left, right, k+1) as (col_left, col_right):
            # Join
            joined_idx = _call_join_multi(libgdf.gdf_left_join, k+1, col_left,
                                    col_right, gdf_ctxt)

        # Check answer
        # Can be generated by:
        # >>> df = pd.DataFrame()
        # >>> df2 = pd.DataFrame()
        # >>> df['a'] = [0, 0, 4, 5, 5]
        # >>> df2['a'] = [0, 0, 2, 3, 5]
        # >>> df['b'] = [1, 2, 2, 3,4]
        # >>> df2['b'] = [1, 2, 3, 3,4]
        # >>> df['c'] = [1, 1, 3, 1, 2]
        # >>> df2['c'] = [3, 3, 2, 1, 1]
        # >>> joined = df.merge(df2, how='left', on=['a'], suffixes=['_remove', ''])
        # >>> joined = df.merge(df2, how='left', on=['a'], suffixes=['_remove', ''])
        # >>> joined
        # a  b_remove  c_remove    b    c
        # 0  0         1         1  1.0  3.0
        # 1  0         1         1  2.0  3.0
        # 2  0         2         1  1.0  3.0
        # 3  0         2         1  2.0  3.0
        # 4  4         2         3  NaN  NaN
        # 5  5         3         1  4.0  1.0
        # 6  5         4         2  4.0  1.0
        # >>> joined = df.merge(df2, how='left', on=['a','b'], suffixes=['_remove', ''])
        # >>> joined
        # a  b  c_remove    c
        # 0  0  1         1  3.0
        # 1  0  2         1  3.0
        # 2  4  2         3  NaN
        # 3  5  3         1  NaN
        # 4  5  4         2  1.0
        # >>> joined = df.merge(df2, how='left', suffixes=['_remove', ''])
        # >>> joined
        # a  b  c
        # 0  0  1  1
        # 1  0  2  1
        # 2  4  2  3
        # 3  5  3  1
        # 4  5  4  2

        left_pos, right_pos = joined_idx

        # sort before checking since the hash join may produce results in random order
        tmp = sorted(zip(left_pos, right_pos), key=lambda pair: (pair[0], pair[1]))
        left_pos = [x for x,_ in tmp]
        right_pos = [x for _,x in tmp]

        if(k==0):

            assert tuple(left_pos) == (0, 0, 1, 1, 2, 3, 4)
            assert tuple(right_pos) == (0, 1, 0, 1, -1, 4, 4)

            left_idx = [left[0][a] for a in left_pos]

            assert tuple(left_idx) == (0, 0, 0, 0, 4, 5, 5)


        elif(k==1):

            assert tuple(left_pos) == (0, 1, 2, 3, 4)

            for l in range(2):
                left_idx = [left[l][a] for a in left_pos]

                if(l==0):
                    assert tuple(left_idx) == (0, 0, 4, 5, 5)
                elif(l==1):
                    assert tuple(left_idx) == (1, 2, 2, 3, 4)

        elif(k==2):

            assert tuple(left_pos) == (0, 1, 2, 3, 4)
            for l in range(3):
                left_idx = [left[l][a] for a in left_pos]

                if(l==0):
                    assert tuple(left_idx) == (0, 0, 4, 5, 5)
                elif(l==1):
                    assert tuple(left_idx) == (1, 2, 2, 3, 4)
                elif(l==2):
                    assert tuple(left_idx) == (1, 1, 3, 1, 2)


def tests_two_column_merge_left(left_nkeys=4, right_nkeys=5):
    """Test for issue #57.
    An issue that can trigger an error in cuda-memcheck.
    """
    how='left'
    left_nrows = 60
    right_nrows = 60
    gdf_ctxt = new_context()
    libgdf.gdf_context_view(gdf_ctxt, 0, libgdf.GDF_HASH, 0)

    np.random.seed(0)

    # PyGDF
    left_cols = [
        np.random.randint(0, left_nkeys, size=left_nrows),
        np.random.randint(0, left_nkeys, size=left_nrows),
    ]
    right_cols = [
        np.random.randint(0, right_nkeys, size=right_nrows),
        np.random.randint(0, right_nkeys, size=right_nrows),
    ]

    with _make_input_multi(left_cols, right_cols, 2) as (col_left, col_right):
        joined_idx = _call_join_multi(libgdf.gdf_left_join, 2,
                                      col_left, col_right, gdf_ctxt)

    # Just check that the indices in `joined_idx` are valid
    assert joined_idx.shape[0] == 2
    assert np.all(0 <= joined_idx[0])
    assert np.all(-1 <= joined_idx[1])
    assert np.all(joined_idx[0] < left_nrows)
    assert np.all(joined_idx[1] < right_nrows)

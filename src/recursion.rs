use pyo3::exceptions::PyRecursionError;
use pyo3::prelude::*;

// Also bound Rust stack use when Python's recursion limit has been raised.
const MAX_DEPTH: usize = 256;

pub(crate) struct RecursionGuard<'py> {
    _py: Python<'py>,
}

impl<'py> RecursionGuard<'py> {
    pub(crate) fn enter(py: Python<'py>, depth: usize) -> PyResult<Self> {
        if depth >= MAX_DEPTH {
            return Err(PyRecursionError::new_err(
                "maximum container depth (256) exceeded; cyclic structures are not supported",
            ));
        }
        // SAFETY: The Python token proves this thread is attached. Every
        // successful entry is paired with a leave by this guard's Drop.
        if unsafe { pyo3::ffi::Py_EnterRecursiveCall(c" while merging dictionaries".as_ptr()) } != 0
        {
            return Err(PyErr::fetch(py));
        }
        Ok(Self { _py: py })
    }
}

impl Drop for RecursionGuard<'_> {
    fn drop(&mut self) {
        // SAFETY: The guard retains the Python token, and exists only after a
        // successful Py_EnterRecursiveCall on this same thread.
        unsafe { pyo3::ffi::Py_LeaveRecursiveCall() };
    }
}

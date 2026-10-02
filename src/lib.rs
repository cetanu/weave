mod merge;
mod recursion;

use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Deeply merge two dictionaries into a new dictionary.
///
/// Nested dictionaries merge recursively. Other conflicts take the right-hand
/// value; with concat_lists=True, two lists concatenate in left-to-right order.
/// Dicts and lists in the result are independent of the inputs. Keys and all
/// other values retain their identity. Container subclasses become plain dicts
/// and lists. Cycles and excessive nesting raise RecursionError.
#[pyfunction]
#[pyo3(name = "merge", signature = (left, right, *, concat_lists=false))]
fn py_merge<'py>(
    left: &Bound<'py, PyDict>,
    right: &Bound<'py, PyDict>,
    concat_lists: bool,
) -> PyResult<Bound<'py, PyDict>> {
    merge::merge_dicts(left, right, concat_lists, 0)
}

/// Rust-backed deep merging of Python dictionaries.
#[pymodule(gil_used = true)]
fn _weave(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(py_merge, module)?)?;
    Ok(())
}

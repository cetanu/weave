use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};

use crate::recursion::RecursionGuard;

pub(crate) fn merge_dicts<'py>(
    left: &Bound<'py, PyDict>,
    right: &Bound<'py, PyDict>,
    concat_lists: bool,
    depth: usize,
) -> PyResult<Bound<'py, PyDict>> {
    let _guard = RecursionGuard::enter(left.py(), depth)?;
    let result = left.copy()?;

    // A native dict copy preserves key identity and order and handles scalar
    // values cheaply. Copy only containers that survive the merge.
    for (key, value) in left.iter() {
        if is_container(&value) && !right.contains(&key)? {
            result.set_item(key, copy_value(&value, depth + 1)?)?;
        }
    }

    if right.len() >= 64 {
        let py = left.py();
        let mut position = 0;
        let mut key_ptr = std::ptr::null_mut();
        let mut value_ptr = std::ptr::null_mut();
        let mut inspected = 0;
        let mut prefix_contains_containers = false;
        let mut exact_string_keys = true;
        let mut container_entries = Vec::new();

        while inspected < right.len() {
            // SAFETY: `right` remains alive and unmodified for this scan, and
            // the GIL is held for the full call.
            if unsafe {
                pyo3::ffi::PyDict_Next(right.as_ptr(), &mut position, &mut key_ptr, &mut value_ptr)
            } == 0
            {
                break;
            }
            // SAFETY: PyDict_Next returned a live key pointer while `right`
            // is alive and the GIL remains held.
            if unsafe { pyo3::ffi::PyUnicode_CheckExact(key_ptr) == 0 } {
                exact_string_keys = false;
                break;
            }

            // SAFETY: PyDict_Next returned a live value pointer while `right`
            // is alive and the GIL remains held.
            let is_container = unsafe {
                pyo3::ffi::PyDict_Check(value_ptr) != 0 || pyo3::ffi::PyList_Check(value_ptr) != 0
            };
            if inspected < 64 && is_container {
                prefix_contains_containers = true;
                break;
            } else if is_container {
                // SAFETY: both pointers are borrowed from the live `right` dict;
                // the constructors increment their references for these Bounds.
                container_entries.push(unsafe {
                    (
                        Bound::from_borrowed_ptr(py, key_ptr),
                        Bound::from_borrowed_ptr(py, value_ptr),
                    )
                });
            }
            inspected += 1;
        }

        if !exact_string_keys || prefix_contains_containers {
            for (key, right_value) in right.iter() {
                result.set_item(
                    &key,
                    merge_entry(left, &key, &right_value, concat_lists, depth + 1)?,
                )?;
            }
            return Ok(result);
        }

        result.update(right.as_mapping())?;
        for (key, right_value) in container_entries {
            result.set_item(
                &key,
                merge_entry(left, &key, &right_value, concat_lists, depth + 1)?,
            )?;
        }
        return Ok(result);
    } else if right.len() >= 4
        && right
            .iter()
            .all(|(key, value)| !is_container(&value) && key.is_exact_instance_of::<PyString>())
    {
        result.update(right.as_mapping())?;
        return Ok(result);
    }

    for (key, right_value) in right.iter() {
        result.set_item(
            &key,
            merge_entry(left, &key, &right_value, concat_lists, depth + 1)?,
        )?;
    }

    Ok(result)
}

fn merge_entry<'py>(
    left: &Bound<'py, PyDict>,
    key: &Bound<'py, PyAny>,
    right: &Bound<'py, PyAny>,
    concat_lists: bool,
    depth: usize,
) -> PyResult<Bound<'py, PyAny>> {
    if let Ok(right_dict) = right.cast::<PyDict>() {
        if let Some(left_dict) = left
            .get_item(key)?
            .and_then(|value| value.cast_into::<PyDict>().ok())
        {
            return Ok(merge_dicts(&left_dict, right_dict, concat_lists, depth)?.into_any());
        }
    } else if concat_lists {
        if let Ok(right_list) = right.cast::<PyList>() {
            if let Some(left_list) = left
                .get_item(key)?
                .and_then(|value| value.cast_into::<PyList>().ok())
            {
                return Ok(copy_list(&left_list, Some(right_list), depth)?.into_any());
            }
        }
    }

    copy_value(right, depth)
}

fn is_container(value: &Bound<'_, PyAny>) -> bool {
    value.is_instance_of::<PyDict>() || value.is_instance_of::<PyList>()
}

fn copy_value<'py>(value: &Bound<'py, PyAny>, depth: usize) -> PyResult<Bound<'py, PyAny>> {
    if let Ok(dict) = value.cast::<PyDict>() {
        let _guard = RecursionGuard::enter(value.py(), depth)?;
        let result = dict.copy()?;
        let py = value.py();
        let mut position = 0;
        let mut key_ptr = std::ptr::null_mut();
        let mut child_ptr = std::ptr::null_mut();
        loop {
            // SAFETY: `dict` remains alive and unmodified during the scan, and
            // the GIL is held for the full call.
            if unsafe {
                pyo3::ffi::PyDict_Next(dict.as_ptr(), &mut position, &mut key_ptr, &mut child_ptr)
            } == 0
            {
                break;
            }
            // SAFETY: PyDict_Next returned a live value pointer while `dict`
            // is alive and the GIL remains held.
            let is_container = unsafe {
                pyo3::ffi::PyDict_Check(child_ptr) != 0 || pyo3::ffi::PyList_Check(child_ptr) != 0
            };
            if is_container {
                // SAFETY: both pointers are borrowed from the live `dict`;
                // the constructors increment their references for these Bounds.
                let key = unsafe { Bound::from_borrowed_ptr(py, key_ptr) };
                let child = unsafe { Bound::from_borrowed_ptr(py, child_ptr) };
                result.set_item(&key, copy_value(&child, depth + 1)?)?;
            }
        }
        Ok(result.into_any())
    } else if let Ok(list) = value.cast::<PyList>() {
        Ok(copy_list(list, None, depth)?.into_any())
    } else {
        Ok(value.clone())
    }
}

fn copy_list<'py>(
    list: &Bound<'py, PyList>,
    append: Option<&Bound<'py, PyList>>,
    depth: usize,
) -> PyResult<Bound<'py, PyList>> {
    let _guard = RecursionGuard::enter(list.py(), depth)?;
    let result = match append {
        Some(right) => {
            // Normalize subclasses so concatenation bypasses __add__ overrides.
            let plain_list = match list.cast_exact::<PyList>() {
                Ok(_) => list.clone(),
                Err(_) => list.get_slice(0, list.len()),
            };
            plain_list
                .as_sequence()
                .concat(right.as_sequence())?
                .cast_into::<PyList>()?
        }
        None => list.get_slice(0, list.len()),
    };

    // SAFETY: `result` is a live Python list and the GIL is held.
    let len = unsafe { pyo3::ffi::PyList_GET_SIZE(result.as_ptr()) };
    let mut index = 0;
    loop {
        if index >= len {
            break;
        }

        // SAFETY: the index is in range and `result` remains alive under the GIL.
        let child_ptr = unsafe { pyo3::ffi::PyList_GET_ITEM(result.as_ptr(), index) };
        // SAFETY: PyList_GET_ITEM returns a live borrowed item for this list.
        let is_container = unsafe {
            pyo3::ffi::PyDict_Check(child_ptr) != 0 || pyo3::ffi::PyList_Check(child_ptr) != 0
        };
        if is_container {
            // SAFETY: the pointer is borrowed from the live list; the constructor
            // increments its reference for this Bound.
            let child = unsafe { Bound::from_borrowed_ptr(list.py(), child_ptr) };
            result.set_item(index as usize, copy_value(&child, depth + 1)?)?;
        }
        index += 1;
    }
    Ok(result)
}

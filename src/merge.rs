use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

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

    if right.len() >= 64 && !right.iter().any(|(_, value)| is_container(&value)) {
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
        for (key, child) in dict.iter() {
            if is_container(&child) {
                result.set_item(key, copy_value(&child, depth + 1)?)?;
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

    for (index, child) in result.iter().enumerate() {
        if is_container(&child) {
            result.set_item(index, copy_value(&child, depth + 1)?)?;
        }
    }
    Ok(result)
}

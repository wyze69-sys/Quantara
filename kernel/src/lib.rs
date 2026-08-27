use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyFloat, PyInt, PyIterator, PySequence, PyString};
use sha2::{Digest, Sha256};

const CONTENT_HASH_DOMAIN: &str = "quantara-canonical-content-v1";
const RESEARCH_CONTENT_HASH_DOMAIN: &str = "quantara-research-content-v1";
const CANONICAL_FIELD_COUNT: usize = 23;
const RESEARCH_FIELD_COUNT: usize = 7;

create_exception!(quantara_kernel, KernelHashPayloadError, PyException);

fn hash_prefix(domain: &str, fingerprint: &str) -> Sha256 {
    let mut digest = Sha256::new();
    digest.update(domain.as_bytes());
    digest.update(b"\0");
    digest.update(fingerprint.to_ascii_lowercase().as_bytes());
    digest.update(b"\n");
    digest
}

fn update_jcs_string(digest: &mut Sha256, value: &str) {
    digest.update(b"\"");
    for character in value.chars() {
        match character {
            '"' => digest.update(b"\\\""),
            '\\' => digest.update(b"\\\\"),
            '\u{0008}' => digest.update(b"\\b"),
            '\u{000c}' => digest.update(b"\\f"),
            '\n' => digest.update(b"\\n"),
            '\r' => digest.update(b"\\r"),
            '\t' => digest.update(b"\\t"),
            control if control < '\u{0020}' => {
                const HEX: &[u8; 16] = b"0123456789abcdef";
                let code = control as usize;
                digest.update([b'\\', b'u', b'0', b'0', HEX[code >> 4], HEX[code & 0x0f]]);
            }
            unescaped => {
                let mut buffer = [0_u8; 4];
                digest.update(unescaped.encode_utf8(&mut buffer).as_bytes());
            }
        }
    }
    digest.update(b"\"");
}

fn type_repr(value: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(value.get_type().repr()?.to_str()?.to_owned())
}

fn value_repr(value: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(value.repr()?.to_str()?.to_owned())
}

fn update_jcs_scalar(digest: &mut Sha256, value: &Bound<'_, PyAny>) -> PyResult<()> {
    if value.is_instance_of::<PyBool>() {
        if value.is_truthy()? {
            digest.update(b"true");
        } else {
            digest.update(b"false");
        }
    } else if value.is_instance_of::<PyInt>() {
        digest.update(value.str()?.to_str()?.as_bytes());
    } else if value.is_instance_of::<PyString>() {
        update_jcs_string(digest, value.extract::<String>()?.as_str());
    }
    Ok(())
}

fn update_canonical_row(digest: &mut Sha256, row: &Bound<'_, PyAny>) -> PyResult<()> {
    let sequence = row.downcast::<PySequence>()?;
    if sequence.len()? != CANONICAL_FIELD_COUNT {
        return Err(KernelHashPayloadError::new_err(format!(
            "canonical row must have exactly {CANONICAL_FIELD_COUNT} fields"
        )));
    }

    digest.update(b"[");
    for index in 0..CANONICAL_FIELD_COUNT {
        if index != 0 {
            digest.update(b",");
        }
        let value = sequence.get_item(index)?;
        if value.is_instance_of::<PyFloat>() {
            return Err(KernelHashPayloadError::new_err(
                "binary floats are forbidden in canonical rows",
            ));
        }
        if !(value.is_instance_of::<PyBool>()
            || value.is_instance_of::<PyInt>()
            || value.is_instance_of::<PyString>())
        {
            return Err(KernelHashPayloadError::new_err(format!(
                "canonical rows admit strings/ints/bools/nulls only, got {}",
                type_repr(&value)?
            )));
        }
        update_jcs_scalar(digest, &value)?;
    }
    digest.update(b"]\n");
    Ok(())
}

fn valid_q18(value: &str) -> bool {
    let unsigned = value.strip_prefix('-').unwrap_or(value);
    let Some((integer, fraction)) = unsigned.split_once('.') else {
        return false;
    };
    !integer.is_empty()
        && integer.bytes().all(|byte| byte.is_ascii_digit())
        && fraction.len() == 18
        && fraction.bytes().all(|byte| byte.is_ascii_digit())
}

fn update_research_row(digest: &mut Sha256, row: &Bound<'_, PyAny>) -> PyResult<()> {
    const NAMES: [&str; RESEARCH_FIELD_COUNT] = [
        "open_time_ms",
        "f_ret_1",
        "f_roc_60",
        "f_rvol_20",
        "f_volratio_20",
        "l_fwdret_24",
        "l_fwddir_24",
    ];
    const NULLABLE: [bool; RESEARCH_FIELD_COUNT] = [false, true, true, true, true, true, true];

    let sequence = row.downcast::<PySequence>()?;
    if sequence.len()? != RESEARCH_FIELD_COUNT {
        return Err(KernelHashPayloadError::new_err(format!(
            "research row must have exactly {RESEARCH_FIELD_COUNT} fields"
        )));
    }

    digest.update(b"[");
    for index in 0..RESEARCH_FIELD_COUNT {
        if index != 0 {
            digest.update(b",");
        }
        let value = sequence.get_item(index)?;
        let name = NAMES[index];
        if value.is_instance_of::<PyFloat>() {
            return Err(KernelHashPayloadError::new_err(
                "binary floats are forbidden in research rows",
            ));
        }
        if value.is_none() {
            if !NULLABLE[index] {
                return Err(KernelHashPayloadError::new_err(format!(
                    "research column {name} is never null"
                )));
            }
            digest.update(b"null");
            continue;
        }
        if (1..=5).contains(&index) {
            let valid = value
                .downcast::<PyString>()
                .ok()
                .and_then(|text| text.to_str().ok())
                .is_some_and(valid_q18);
            if !valid {
                return Err(KernelHashPayloadError::new_err(format!(
                    "research column {name} must be a Q18-framed string \
                     (exactly 18 fractional digits), got {}",
                    value_repr(&value)?
                )));
            }
        } else if value.is_instance_of::<PyBool>() || !value.is_instance_of::<PyInt>() {
            return Err(KernelHashPayloadError::new_err(format!(
                "research column {name} must be an int, got {}",
                type_repr(&value)?
            )));
        }
        update_jcs_scalar(digest, &value)?;
    }
    digest.update(b"]\n");
    Ok(())
}

#[pyfunction]
fn hash_canonical_rows(fingerprint: &str, rows: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut digest = hash_prefix(CONTENT_HASH_DOMAIN, fingerprint);
    for row in PyIterator::from_object(rows)? {
        update_canonical_row(&mut digest, &row?)?;
    }
    Ok(format!("{:x}", digest.finalize()))
}

#[pyfunction]
fn hash_research_rows(fingerprint: &str, rows: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut digest = hash_prefix(RESEARCH_CONTENT_HASH_DOMAIN, fingerprint);
    for row in PyIterator::from_object(rows)? {
        update_research_row(&mut digest, &row?)?;
    }
    Ok(format!("{:x}", digest.finalize()))
}

#[pyfunction]
fn module_version() -> String {
    env!("CARGO_PKG_VERSION").to_owned()
}

#[pymodule]
fn quantara_kernel(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(hash_canonical_rows, module)?)?;
    module.add_function(wrap_pyfunction!(hash_research_rows, module)?)?;
    module.add_function(wrap_pyfunction!(module_version, module)?)?;
    module.add(
        "KernelHashPayloadError",
        module.py().get_type::<KernelHashPayloadError>(),
    )?;
    module.add("CONTENT_HASH_DOMAIN", CONTENT_HASH_DOMAIN)?;
    module.add("RESEARCH_CONTENT_HASH_DOMAIN", RESEARCH_CONTENT_HASH_DOMAIN)?;
    Ok(())
}

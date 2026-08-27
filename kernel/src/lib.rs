use pyo3::create_exception;
use pyo3::exceptions::{PyException, PyOverflowError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyFloat, PyInt, PyIterator, PyList, PySequence, PyString};
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

// --- Slice 009: Q18 decimal rendering (byte-identical with the Python oracle) ---

const Q18_FRACTIONAL_DIGITS: usize = 18;
const Q18_REJECTION_SUFFIX: &str = " exceeds 18 fractional digits; rounding is forbidden";

enum DecimalForm {
    Finite {
        negative: bool,
        digits: String,
        exponent: i64,
    },
    Infinity,
    NaN {
        negative: bool,
        signaling: bool,
        payload: String,
    },
}

/// Remove insignificant surface characters the way CPython's string-to-Decimal
/// conversion does: surrounding whitespace is trimmed and underscore digit
/// separators must sit strictly between two digits.
fn pack_decimal_literal(text: &str) -> Option<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return None;
    }
    let characters: Vec<char> = trimmed.chars().collect();
    let mut packed = String::with_capacity(characters.len());
    for (index, character) in characters.iter().enumerate() {
        if *character != '_' {
            packed.push(*character);
            continue;
        }
        if index == 0 {
            return None;
        }
        match (characters.get(index - 1), characters.get(index + 1)) {
            (Some(previous), Some(following))
                if previous.is_ascii_digit() && following.is_ascii_digit() => {}
            _ => return None,
        }
    }
    Some(packed)
}

fn parse_decimal_literal(text: &str) -> Option<DecimalForm> {
    let (negative, body) = match text.as_bytes().first() {
        Some(b'+') => (false, &text[1..]),
        Some(b'-') => (true, &text[1..]),
        _ => (false, text),
    };
    let lower = body.to_ascii_lowercase();
    if lower == "inf" || lower == "infinity" {
        return Some(DecimalForm::Infinity);
    }
    if let Some(payload) = lower.strip_prefix("snan") {
        if payload.chars().all(|character| character.is_ascii_digit()) {
            return Some(DecimalForm::NaN {
                negative,
                signaling: true,
                payload: payload.to_owned(),
            });
        }
        return None;
    }
    if let Some(payload) = lower.strip_prefix("nan") {
        if payload.chars().all(|character| character.is_ascii_digit()) {
            return Some(DecimalForm::NaN {
                negative,
                signaling: false,
                payload: payload.to_owned(),
            });
        }
        return None;
    }

    let (mantissa, exponent_text) = match lower.find('e') {
        Some(position) => (&body[..position], Some(&body[position + 1..])),
        None => (body, None),
    };
    let (integer_part, fraction_part) = match mantissa.split_once('.') {
        Some((left, right)) => (left, Some(right)),
        None => (mantissa, None),
    };
    let any_digits =
        !integer_part.is_empty() || fraction_part.is_some_and(|fraction| !fraction.is_empty());
    if !any_digits {
        return None;
    }
    if !integer_part
        .chars()
        .all(|character| character.is_ascii_digit())
    {
        return None;
    }
    if let Some(fraction) = fraction_part {
        if !fraction.chars().all(|character| character.is_ascii_digit()) {
            return None;
        }
    }
    let mut digits = String::from(integer_part);
    let mut exponent: i64 = 0;
    if let Some(fraction) = fraction_part {
        digits.push_str(fraction);
        exponent = exponent.checked_sub(fraction.len() as i64)?;
    }
    if let Some(exponent_text) = exponent_text {
        let (exponent_negative, exponent_digits) = match exponent_text.as_bytes().first() {
            Some(b'+') => (false, &exponent_text[1..]),
            Some(b'-') => (true, &exponent_text[1..]),
            _ => (false, exponent_text),
        };
        if exponent_digits.is_empty()
            || !exponent_digits
                .chars()
                .all(|character| character.is_ascii_digit())
        {
            return None;
        }
        let mut parsed_exponent: i64 = 0;
        for character in exponent_digits.chars() {
            parsed_exponent = parsed_exponent
                .checked_mul(10)?
                .checked_add(i64::from(character.to_digit(10)?))?;
            if parsed_exponent > 1_000_000_000_000_000 {
                return None;
            }
        }
        if exponent_negative {
            parsed_exponent = parsed_exponent.checked_neg()?;
        }
        exponent = exponent.checked_add(parsed_exponent)?;
    }
    let significant = digits.trim_start_matches('0');
    if significant.is_empty() {
        return Some(DecimalForm::Finite {
            negative,
            digits: "0".to_owned(),
            exponent: 0,
        });
    }
    Some(DecimalForm::Finite {
        negative,
        digits: significant.to_owned(),
        exponent,
    })
}

/// CPython's ``str(Decimal)`` spelling for a parsed finite value. Used only in
/// rejection messages, where the oracle interpolates the parsed number itself.
fn decimal_display(negative: bool, digits: &str, exponent: i64) -> String {
    let mut display = String::new();
    if negative {
        display.push('-');
    }
    let adjusted = exponent + digits.len() as i64 - 1;
    if exponent <= 0 && adjusted >= -6 {
        let integer_digit_count = digits.len() as i64 + exponent;
        if exponent == 0 {
            display.push_str(digits);
        } else if integer_digit_count > 0 {
            let split = integer_digit_count as usize;
            display.push_str(&digits[..split]);
            display.push('.');
            display.push_str(&digits[split..]);
        } else {
            display.push_str("0.");
            display.extend(std::iter::repeat_n('0', (-integer_digit_count) as usize));
            display.push_str(digits);
        }
        return display;
    }
    display.push(char::from(digits.as_bytes()[0]));
    if digits.len() > 1 {
        display.push('.');
        display.push_str(&digits[1..]);
    }
    display.push('E');
    if adjusted >= 0 {
        display.push('+');
    } else {
        display.push('-');
    }
    display.push_str(&adjusted.unsigned_abs().to_string());
    display
}

fn rendering_rejection(rendered_value: &str) -> PyErr {
    KernelHashPayloadError::new_err(format!("decimal {rendered_value}{Q18_REJECTION_SUFFIX}"))
}

/// ``decimal.InvalidOperation`` carrying ``[decimal.ConversionSyntax]``, the
/// exception the Python oracle raises for unparseable decimal strings.
fn conversion_syntax_error(py: Python<'_>) -> PyErr {
    let built = py.import("decimal").and_then(|decimal| {
        let invalid_operation = decimal.getattr("InvalidOperation")?;
        let conversion_syntax = decimal.getattr("ConversionSyntax")?;
        let arguments = PyList::new(py, [conversion_syntax])?;
        unsafe {
            pyo3::ffi::PyErr_SetObject(invalid_operation.as_ptr(), arguments.as_ptr());
        }
        Ok::<PyErr, PyErr>(PyErr::fetch(py))
    });
    match built {
        Ok(error) | Err(error) => error,
    }
}

fn render_finite_q18(negative: bool, digits: &str, exponent: i64) -> PyResult<String> {
    if digits == "0" {
        return Ok(String::from("0.000000000000000000"));
    }
    let significant = digits.trim_end_matches('0');
    let mut magnitude = String::from(significant);
    let trailing_zeros = digits.len() - significant.len();
    match exponent.checked_add(trailing_zeros as i64) {
        Some(shifted) if shifted >= -(Q18_FRACTIONAL_DIGITS as i64) => {
            magnitude.extend(std::iter::repeat_n(
                '0',
                (shifted + Q18_FRACTIONAL_DIGITS as i64) as usize,
            ));
        }
        _ => {
            return Err(rendering_rejection(&decimal_display(
                negative, digits, exponent,
            )));
        }
    }
    while magnitude.len() < Q18_FRACTIONAL_DIGITS + 1 {
        magnitude.insert(0, '0');
    }
    let split = magnitude.len() - Q18_FRACTIONAL_DIGITS;
    let mut rendered = String::with_capacity(magnitude.len() + 2);
    if negative {
        rendered.push('-');
    }
    rendered.push_str(&magnitude[..split]);
    rendered.push('.');
    rendered.push_str(&magnitude[split..]);
    Ok(rendered)
}

fn render_decimal_text(py: Python<'_>, raw: &str) -> PyResult<String> {
    let Some(packed) = pack_decimal_literal(raw) else {
        return Err(conversion_syntax_error(py));
    };
    let Some(form) = parse_decimal_literal(&packed) else {
        return Err(conversion_syntax_error(py));
    };
    match form {
        DecimalForm::Infinity => Err(PyOverflowError::new_err(
            "cannot convert Infinity to integer",
        )),
        DecimalForm::NaN {
            negative,
            signaling,
            payload,
        } => {
            let mut label = String::new();
            if negative {
                label.push('-');
            }
            if signaling {
                label.push_str("sNaN");
            } else {
                label.push_str("NaN");
            }
            label.push_str(&payload);
            Err(rendering_rejection(&label))
        }
        DecimalForm::Finite {
            negative,
            digits,
            exponent,
        } => render_finite_q18(negative, &digits, exponent),
    }
}

#[pyfunction]
fn render_decimal_18(value: &Bound<'_, PyAny>) -> PyResult<String> {
    let py = value.py();
    let raw: String = if let Ok(text) = value.downcast::<PyString>() {
        text.to_str()?.to_owned()
    } else {
        value.str()?.to_str()?.to_owned()
    };
    render_decimal_text(py, &raw)
}

#[pymodule]
fn quantara_kernel(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(hash_canonical_rows, module)?)?;
    module.add_function(wrap_pyfunction!(hash_research_rows, module)?)?;
    module.add_function(wrap_pyfunction!(render_decimal_18, module)?)?;
    module.add_function(wrap_pyfunction!(module_version, module)?)?;
    module.add(
        "KernelHashPayloadError",
        module.py().get_type::<KernelHashPayloadError>(),
    )?;
    module.add("CONTENT_HASH_DOMAIN", CONTENT_HASH_DOMAIN)?;
    module.add("RESEARCH_CONTENT_HASH_DOMAIN", RESEARCH_CONTENT_HASH_DOMAIN)?;
    Ok(())
}

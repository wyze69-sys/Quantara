use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;

const CONTENT_HASH_DOMAIN: &str = "quantara-canonical-content-v1";
const RESEARCH_CONTENT_HASH_DOMAIN: &str = "quantara-research-content-v1";

create_exception!(quantara_kernel, KernelHashPayloadError, PyException);

#[pyfunction]
fn hash_canonical_rows(
    _fingerprint: &str,
    _rows: &Bound<'_, PyAny>,
) -> PyResult<&'static str> {
    Ok("unimplemented")
}

#[pyfunction]
fn hash_research_rows(
    _fingerprint: &str,
    _rows: &Bound<'_, PyAny>,
) -> PyResult<&'static str> {
    Ok("unimplemented")
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

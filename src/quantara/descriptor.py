"""Source descriptor and provider-rights record loading/validation (component 1).

Declares and strictly validates the approved dataset descriptor (identities,
half-open UTC period, allow-listed source URLs, schema versions) and the
versioned provider-rights record that gates every performed operation before
any network or filesystem action.
"""

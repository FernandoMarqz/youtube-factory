"""Domain-specific exceptions."""


class DomainValidationError(ValueError):
    """Raised when cross-model domain invariants are not met."""

class CompanyPackError(Exception):
    """Base exception for company pack operations."""


class CompanyPackNotFoundError(CompanyPackError):
    pass


class CompanyPackValidationError(CompanyPackError):
    pass


class CompanyPackExtractionError(CompanyPackError):
    pass

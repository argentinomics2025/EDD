"""Fixed, non-sensitive setup failure categories; never serialize exceptions."""
CODES = frozenset({'SETUP_POSTGRES_CONNECTION', 'SETUP_POSTGREST_UNAVAILABLE',
                   'SETUP_SDK', 'SETUP_METADATA_QUERY', 'SETUP_IDENTITY', 'SETUP_SESSION_CLOSE'})


class StartupError(RuntimeError):
    def __init__(self, code):
        if code not in CODES:
            raise ValueError('Unknown startup code')
        self.code = code
        super().__init__(code)


def code_from_exception(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, StartupError):
            return error.code
        error = error.__cause__ or error.__context__
    return None

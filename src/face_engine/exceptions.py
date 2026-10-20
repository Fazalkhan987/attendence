"""Exception hierarchy. API layers can map these to HTTP status codes later."""


class FaceEngineError(Exception):
    """Base class for all engine errors."""


class ConfigError(FaceEngineError): ...
class BackendError(FaceEngineError): ...          # model missing / library missing
class InvalidFrameError(FaceEngineError): ...
class ImageLoadError(FaceEngineError): ...
class CameraError(FaceEngineError): ...
class ValidationError(FaceEngineError): ...        # bad person id, empty name, ...
class PersonNotFoundError(FaceEngineError): ...
class DuplicatePersonError(FaceEngineError): ...   # same person_id already exists
class PossibleDuplicateIdentityError(FaceEngineError):
    def __init__(self, message, candidates):
        super().__init__(message)
        self.candidates = candidates               # list[(person_id, name, similarity)]
class InsufficientSamplesError(FaceEngineError):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report
class ModelMismatchError(FaceEngineError): ...
class AuthError(FaceEngineError): ...              # bad passcode / locked out
class AuthorizationError(FaceEngineError): ...     # missing/expired admin session
class DatasetError(FaceEngineError): ...           # evaluation dataset problems (incl. leakage)
